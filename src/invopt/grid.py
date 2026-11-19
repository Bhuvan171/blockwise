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


TIME_LIMIT_S = 900.0  # observed max ~200 s on a laptop; generous margin for slower machines


def _solve(args) -> OptResult:
    budget, lam, soft_cap, group_region, terms = args
    return optimize(_PLAN, terms, OptimizerParams(risk_aversion=lam, budget=budget, soft_cap=soft_cap,
                                                  group_region=group_region, region_share=REGION_SHARE,
                                                  time_limit_s=TIME_LIMIT_S))


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


ABLATIONS = [  # (key, file suffix, label)
    ("headline", "", "Blockwise: adaptive calibration + safeguards (headline)"),
    ("br1.5", "_br1.5", "Same, breaker at 1.5x error"),
    ("br3", "_br3", "Same, breaker at 3x error"),
    ("static", "_static", "Static calibration (equal weights) + safeguards"),
    ("nosafeguards", "_nosafeguards", "Adaptive calibration, no safeguards (no breaker, no cap)"),
    ("occ75", "_occ75", "Same as headline, buy-as-needed cut-offs 75/90% occupancy"),
    ("occ85", "_occ85", "Same as headline, buy-as-needed cut-offs 85/98% occupancy"),
]
SG_RULES = ("last_year_hard", "point_forecast_hard", "allot_ly_block_p25",
            "last_year_hard_brk", "point_forecast_hard_brk", "allot_ly_block_p25_brk")


def attach_singapore(results: dict, singapore_path) -> dict:
    """Add the Singapore replay (without its monthly rows) and its ablation table to `results`."""
    path = Path(singapore_path) if singapore_path is not None else None
    if path is None or not path.exists():
        results["singapore"] = None
        return results
    sg = json.loads(path.read_text())
    out = {k: v for k, v in sg.items() if k != "by_month"}  # monthly rows stay in out/singapore.json
    rows = []
    for key, suffix, label in ABLATIONS:
        f = path.with_name(path.stem + suffix + ".json")
        if not f.exists():
            continue
        r = json.loads(f.read_text())
        b, per = r.get("summary", {}).get("ours_0.25", {}), r.get("by_period", {})
        summ = r.get("summary", {})
        rules = [p for p in SG_RULES if summ.get(p, {}).get("pct_of_hindsight") is not None]
        best = max(rules, key=lambda p: summ[p]["pct_of_hindsight"]) if rules else None
        covid = per.get("2020–21 COVID", {})
        covid_rules = [covid[p]["profit"] for p in rules if covid.get(p, {}).get("profit") is not None]
        rows.append({"key": key, "label": label, "pct_of_hindsight": b.get("pct_of_hindsight"),
                     "best_rule": best, "best_rule_pct": summ[best]["pct_of_hindsight"] if best else None,
                     "best_rule_covid": max(covid_rules) if covid_rules else None,
                     "best_rule_worst5": max(summ[p].get("worst5_month_avg", -np.inf) for p in rules) if rules else None,
                     "worst5_month_avg": b.get("worst5_month_avg"),
                     "covid_profit": per.get("2020–21 COVID", {}).get("ours_0.25", {}).get("profit"),
                     "recovery_profit": per.get("2022–23 recovery", {}).get("ours_0.25", {}).get("profit"),
                     "recent_pct": per.get("2024–26 recent", {}).get("ours_0.25", {}).get("pct_of_hindsight"),
                     "breaker_months": len(r.get("breaker_months", []))})
        if key == "static":  # calibration coverage of the static variant, for the page's calibration table
            out["static_forecast"] = r.get("forecast", {}).get("headline")
            out["static_summary"] = r.get("summary")
    out["ablations"] = rows
    results["singapore"] = out
    return results


def run_grid(budget_fracs=(0.25, 0.5, 0.75, 1.0, 1.25), risk_levels: dict[str, float] | None = None,
             n_plan: int = 150, n_eval: int = 4000, weeks: int = 13, workers: int = 2,
             backtest_path: str | Path | None = "out/backtest.json", terms: ContractTerms | None = None,
             singapore_path: str | Path | None = "out/singapore.json",
             bench_path: str | Path | None = "out/forecast_bench.json") -> dict:
    t0 = time.perf_counter()
    terms = (terms or ContractTerms()).validate()
    risk_levels = dict(risk_levels or RISK_LEVELS)
    plan = generate(WORLDS["base"], n_plan, PLAN_SEED, weeks=weeks)
    meta = plan.meta
    soft_cap = np.floor(meta["mean_demand"].to_numpy() * SOFT_CAP_MULT)
    group_region = meta["region"].map({r: i for i, r in enumerate(REGIONS)}).to_numpy()
    hard_cost = terms.costs(plan.ref_rate, plan.ref_rate)["hard"]

    unconstrained = optimize(plan, terms, OptimizerParams(soft_cap=soft_cap, time_limit_s=TIME_LIMIT_S))
    if unconstrained.status != "optimal":
        raise RuntimeError(f"reference (unconstrained Max profit) solve returned {unconstrained.status!r}; "
                           "every budget is derived from it, so the grid stops")
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
    frontier = {r: {"budgets": budgets, "mean": [], "cvar95": [], "fill_rate": [], "status": []} for r in risk_levels}
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
            frontier[risk]["status"].append(res.status)

    # what the next rupee of budget adds to EXPECTED profit, measured on fresh futures (frontier slope),
    # not the LP dual (which prices the risk-weighted objective on the planning draws)
    for risk in risk_levels:
        means = frontier[risk]["mean"]
        for bi in range(len(budgets)):
            nxt = None if bi == len(budgets) - 1 else (means[bi + 1] - means[bi]) / (budgets[bi + 1] - budgets[bi]) * CRORE
            cells_out[str(bi)][risk]["kpis"]["marginal_profit_per_cr"] = nxt
    fallback_count = sum(1 for row in cells_out.values() for c in row.values() if c["status"] != "optimal")

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
        # two-contract rule (fixed before seeing results): allot expected volume, hard-block the 25th percentile
        "allot_expected_block_p25": Plan(hard=_scale_hard(np.percentile(demand_plan, 25, axis=1), hard_cost, ref_budget),
                                         soft=soft_cap.copy()),
        "dynamic_only": Plan.zeros(plan.n_groups),
    }
    rob = {"budget_inr": ref_budget, "worlds": list(WORLDS), "unseen_worlds": [w for w in WORLDS if w != "base"],
           "status": bal.status, "results": {}}
    for wi, (name, params) in enumerate(WORLDS.items()):
        w_cells = generate(params, n_eval, WORLD_SEED + wi, weeks=weeks)
        rob["results"][name] = {pol: evaluate(w_cells, pl, terms).summary() for pol, pl in policies.items()}

    backtest = None
    if backtest_path is not None and Path(backtest_path).exists():
        bt = json.loads(Path(backtest_path).read_text())
        backtest = {"summary": bt["summary"], "forecast_metrics": bt["forecast_metrics"],
                    "capacity": bt["meta"]["capacity"], "config": bt["meta"]["config"],
                    "n_batches": len(bt["meta"]["batches"])}
        for extra in ("backtest_uncapped.json", "backtest_tau1.json", "backtest_budget0.5.json",
                      "backtest_rates_low.json", "backtest_rates_high.json"):
            p = Path(backtest_path).parent / extra
            if p.exists():
                backtest.setdefault("sensitivity", {})[extra.removeprefix("backtest_").removesuffix(".json")] = \
                    json.loads(p.read_text())["summary"]

    singapore = attach_singapore({}, singapore_path)["singapore"] if singapore_path is not None else None
    bench = None
    if bench_path is not None and Path(bench_path).exists():
        b = json.loads(Path(bench_path).read_text())
        bench = {"headline": b["headline"], "rows": b["rows"]}

    payload = {
        "generated_seconds": time.perf_counter() - t0,
        "singapore": singapore,
        "forecast_bench": bench,
        "currency": "INR",
        "b_star_inr": b_star,
        "budgets_inr": budgets,
        "reference_budget_index": ref_i,
        "fallback_count": fallback_count,
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
