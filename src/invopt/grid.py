"""Precompute every plan the decision page can show.

Budgets x risk levels on the synthetic TBO-like portfolio, each plan scored on
fresh scenarios (never the planning draws), under three shocks, and, for the
Balanced plan, in seven worlds it was not planned in. The real-data backtest
summary is copied in so the page shows both. Output: one JSON-safe dict.
"""
from __future__ import annotations

import json
import math
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from invopt.config import RISK_LEVELS, ContractTerms
from invopt.economics import Cells, Plan, evaluate
from invopt.optimizer import OptimizerParams, OptResult, optimize
from invopt.portfolio import EVENTS, PRODUCTS, REGIONS, SHOCK_LABELS, SHOCKS, WORLDS, WorldParams, generate

CRORE = 1e7
PLAN_SEED = 1
EVAL_SEED = 100
WORLD_SEED = 200
REGION_SHARE = 0.6  # risk policy (assumption): at most 60% of prepaid spend in any one region
SOFT_CAP_MULT = 1.0  # allotment per week <= expected production (same realism rule as the backtest)
HIST_BINS = 30

_PLAN: Cells | None = None


def _init(cells: Cells) -> None:
    global _PLAN
    _PLAN = cells


def _solve(args) -> OptResult:
    budget, lam, soft_cap, group_region, terms = args
    return optimize(_PLAN, terms, OptimizerParams(risk_aversion=lam, budget=budget, soft_cap=soft_cap,
                                                  group_region=group_region, region_share=REGION_SHARE))


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return round(f, 4) if math.isfinite(f) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    return obj


def _kpis(out, res: OptResult | None = None) -> dict:
    k = out.summary()
    if res is not None:
        k["budget_shadow_price"] = res.budget_shadow_price  # profit per extra rupee of budget
        k["status"] = res.status
        k["solve_seconds"] = res.solve_seconds
    return k


def _reason(hard: float, soft: float, p_late: float, release: int, profit: float, p_loss: float) -> str:
    parts = []
    if hard > 0:
        parts.append(f"{hard:.0f} hard: covers late bookings in {p_late:.0f}% of futures")
    if soft > 0:
        parts.append(f"{soft:.0f} allotted: early demand, released free {release} days out if unsold")
    head = "; ".join(parts) if parts else "No commitment"
    return f"{head}. Expected ₹{profit:,.0f}; chance this line loses money {100 * p_loss:.0f}%."


def _plan_detail(cells: Cells, plan: Plan, out, terms: ContractTerms) -> tuple[list, dict, list]:
    meta = cells.meta
    hard_cost = terms.costs(cells.ref_rate, cells.ref_rate)["hard"]
    dyn_cost = terms.costs(cells.ref_rate, cells.ref_rate)["dyn"]
    stock = terms.costs(cells.ref_rate, cells.ref_rate)["stockout"]
    lines, exposure = [], {r: {} for r in REGIONS}
    H, SO = np.asarray(plan.hard)[cells.group], np.asarray(plan.soft)[cells.group]
    for c in np.flatnonzero((H > 0) | (SO > 0)):
        cp = out.cell_profit[c]
        hard_used = H[c] - out.unsold_hard[c]
        p_late = float((cells.late[c] <= H[c]).mean() * 100) if H[c] > 0 else 0.0
        row = meta.iloc[c]
        exp_profit, p_loss = float(cp.mean()), float((cp < 0).mean())
        lines.append({
            "product": row["name"], "kind": row["kind"], "region": row["region"],
            "week_start": str(row["week_start"].date()), "hard": float(H[c]), "soft": float(SO[c]),
            "prepaid_inr": float(H[c] * hard_cost[c]), "exp_profit_inr": exp_profit, "p_line_loss": p_loss,
            "hard_sell_through": float((hard_used / H[c]).mean()) if H[c] > 0 else None,
            "mean_demand": float(row["mean_demand"]),
            "reason": _reason(H[c], SO[c], p_late, terms.release_days, exp_profit, p_loss),
        })
        month = row["week_start"].strftime("%b %Y")
        exposure[row["region"]][month] = exposure[row["region"]].get(month, 0.0) + float(H[c] * hard_cost[c])
    lost = out.lost.mean(axis=1)
    value = lost * (np.asarray(cells.ref_rate) - dyn_cost + stock)
    gaps = []
    for c in np.argsort(-value)[:10]:
        if value[c] <= 0:
            break
        row = meta.iloc[c]
        gaps.append({"product": row["name"], "region": row["region"], "week_start": str(row["week_start"].date()),
                     "exp_lost_units": float(lost[c]), "value_inr": float(value[c])})
    return lines, exposure, gaps


def _hist(values: dict[str, np.ndarray]) -> dict:
    allv = np.concatenate(list(values.values()))
    edges = np.linspace(np.percentile(allv, 0.5), np.percentile(allv, 99.5), HIST_BINS + 1)
    return {"edges": edges, **{k: np.histogram(np.clip(v, edges[0], edges[-1]), bins=edges)[0] for k, v in values.items()}}


def _scale_hard(hard: np.ndarray, hard_cost: np.ndarray, budget: float) -> np.ndarray:
    hard = np.floor(np.maximum(hard, 0.0))
    spend = float(hard_cost @ hard)
    if spend > budget > 0:
        hard = np.floor(hard * budget / spend)
    return hard


def run_grid(budget_fracs=(0.25, 0.5, 0.75, 1.0, 1.25), risk_levels: dict[str, float] | None = None,
             n_plan: int = 150, n_eval: int = 4000, weeks: int = 13, workers: int = 2,
             backtest_path: str | Path | None = "out/backtest.json", terms: ContractTerms | None = None) -> dict:
    t0 = time.perf_counter()
    terms = (terms or ContractTerms()).validate()
    risk_levels = dict(risk_levels or RISK_LEVELS)
    plan = generate(WORLDS["base"], n_plan, PLAN_SEED, weeks=weeks)
    meta = plan.meta
    soft_cap = np.floor(meta["mean_demand"].to_numpy() * SOFT_CAP_MULT)
    group_region = meta["region"].map({r: i for i, r in enumerate(REGIONS)}).to_numpy()
    hard_cost = terms.costs(plan.ref_rate, plan.ref_rate)["hard"]

    unconstrained = optimize(plan, terms, OptimizerParams(soft_cap=soft_cap))
    b_star = float(hard_cost @ unconstrained.plan_int.hard)
    budgets = sorted({max(0.5, round(f * b_star / CRORE * 2) / 2) * CRORE for f in budget_fracs})

    tasks = [(b, lam, soft_cap, group_region, terms) for b in budgets for lam in risk_levels.values()]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(plan,)) as ex:
            results = list(ex.map(_solve, tasks))
    else:
        _init(plan)
        results = [_solve(t) for t in tasks]

    base_eval = generate(WORLDS["base"], n_eval, EVAL_SEED, weeks=weeks)
    shock_eval = {s: generate(WorldParams(shock=s), n_eval, EVAL_SEED, weeks=weeks) for s in SHOCKS}

    cells_out: dict = {}
    frontier = {r: {"budgets": budgets, "mean": [], "cvar95": [], "fill_rate": []} for r in risk_levels}
    it = iter(results)
    for bi, b in enumerate(budgets):
        cells_out[str(bi)] = {}
        for risk in risk_levels:
            res = next(it)
            p = res.plan_int if res.status == "optimal" else Plan.zeros(plan.n_groups)
            out = evaluate(base_eval, p, terms)
            lines, exposure, gaps = _plan_detail(base_eval, p, out, terms)
            shock_outs = {s: evaluate(c, p, terms) for s, c in shock_eval.items()}
            hist = _hist({"base": out.profit, **{s: o.profit for s, o in shock_outs.items()}})
            cells_out[str(bi)][risk] = {
                "kpis": _kpis(out, res), "status": res.status, "lines": lines, "exposure": exposure, "gaps": gaps,
                "histogram_base": {"edges": hist["edges"], "counts": hist["base"]},
                "shocks": {s: {"kpis": _kpis(o), "histogram": {"edges": hist["edges"], "counts": hist[s]}}
                           for s, o in shock_outs.items()},
            }
            k = cells_out[str(bi)][risk]["kpis"]
            frontier[risk]["mean"].append(k["mean"])
            frontier[risk]["cvar95"].append(k["cvar95_profit"])
            frontier[risk]["fill_rate"].append(k["fill_rate"])

    # robustness: the Balanced plan at the reference budget vs simple rules, in worlds it was not planned in
    ref_i = int(np.argmin([abs(b - b_star) for b in budgets]))
    ref_budget = budgets[ref_i]
    lam_bal = RISK_LEVELS["Balanced"]
    bal = (cells_out[str(ref_i)].get("Balanced") and results[ref_i * len(risk_levels) + list(risk_levels).index("Balanced")]) \
        if "Balanced" in risk_levels else None
    if bal is None:
        _init(plan)
        bal = _solve((ref_budget, lam_bal, soft_cap, group_region, terms))
    demand_plan = plan.late + plan.early
    policies = {
        "Blockwise (Balanced)": bal.plan_int if bal.status == "optimal" else Plan.zeros(plan.n_groups),
        "point_forecast_hard": Plan(hard=_scale_hard(np.median(demand_plan, axis=1), hard_cost, ref_budget),
                                    soft=np.zeros(plan.n_groups)),
        "expected_volume_hard": Plan(hard=_scale_hard(meta["mean_demand"].to_numpy(), hard_cost, ref_budget),
                                     soft=np.zeros(plan.n_groups)),
        "dynamic_only": Plan.zeros(plan.n_groups),
    }
    rob = {"budget_inr": ref_budget, "worlds": list(WORLDS), "results": {}}
    for wi, (name, params) in enumerate(WORLDS.items()):
        w_cells = generate(params, n_eval, WORLD_SEED + wi, weeks=weeks)
        rob["results"][name] = {pol: evaluate(w_cells, pl, terms).summary() for pol, pl in policies.items()}

    backtest = None
    if backtest_path is not None and Path(backtest_path).exists():
        bt = json.loads(Path(backtest_path).read_text())
        backtest = {"summary": bt["summary"], "forecast_metrics": bt["forecast_metrics"],
                    "capacity": bt["meta"]["capacity"], "config": bt["meta"]["config"],
                    "n_batches": len(bt["meta"]["batches"])}
        for extra in ("backtest_uncapped.json", "backtest_tau1.json", "backtest_budget0.5.json"):
            p = Path(backtest_path).parent / extra
            if p.exists():
                backtest.setdefault("sensitivity", {})[extra.removeprefix("backtest_").removesuffix(".json")] = \
                    json.loads(p.read_text())["summary"]

    payload = {
        "generated_seconds": time.perf_counter() - t0,
        "currency": "INR",
        "b_star_inr": b_star,
        "budgets_inr": budgets,
        "reference_budget_index": ref_i,
        "risk_levels": risk_levels,
        "cells": cells_out,
        "frontier": frontier,
        "robustness": rob,
        "backtest": backtest,
        "shock_labels": SHOCK_LABELS,
        "assumptions": {
            "terms": terms.as_dict(),
            "region_share": REGION_SHARE,
            "soft_cap_rule": "allotment per week <= expected weekly production",
            "n_plan": n_plan, "n_eval": n_eval, "weeks": weeks, "plan_seed": PLAN_SEED, "eval_seed": EVAL_SEED,
            "products": [{k: p[k] for k in ("name", "kind", "region", "base_weekly_units", "price_inr",
                                            "early_share", "dispersion")} for p in PRODUCTS],
            "events": EVENTS,
            "worlds": {k: v.__dict__ for k, v in WORLDS.items()},
        },
    }
    return _clean(payload)
