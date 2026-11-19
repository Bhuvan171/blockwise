"""Real-shock replay: Singapore hotels for Indian travellers, 2011-2026, on official SingStat data.

At the start of each month d the planner knows SingStat data through month d-2 (publication lag)
and commits inventory for month d+2 in three hotel size bands. It is scored against what really
happened: real Indian arrivals (demand), real room rates (selling price), real occupancy
(whether buying as needed was possible). Contract terms and the demand conversion are stated
assumptions. Currency: SGD.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from invopt.config import ContractTerms
from invopt.economics import Cells, Plan, cvar_profit, evaluate
from invopt.forecast import QUANTILES, coverage, pinball_loss, wape
from invopt.optimizer import OptimizerParams, optimize
from invopt.scenarios import sample_from_quantiles
from invopt.sg_data import TIERS
from invopt.sg_forecast import chronos_monthly_medians, slevel_median, snaive_median, weighted_conformal

SERIES = ["india_arrivals"] + [f"occ_{t}" for t in TIERS] + [f"rate_{t}" for t in TIERS]
PERIODS = {
    "2011–19 normal": ("2011-01-01", "2019-12-01"),
    "2020–21 COVID": ("2020-01-01", "2021-12-01"),
    "2022–23 recovery": ("2022-01-01", "2023-12-01"),
    "2024–26 recent": ("2024-01-01", "2026-12-01"),
}
MONTH = pd.DateOffset(months=1)


@dataclass(frozen=True)
class SGConfig:
    start: str = "2011-01-01"  # first decision month
    end: str = "2026-07-01"  # last decision month (its target is end + 2 months)
    lag_months: int = 2  # data through d-2 is published at the start of month d
    lead_months: int = 2  # commit for month d+2
    kappa: float = 0.05  # B2B room-nights per Indian arrival (assumption; % of hindsight is invariant to it)
    tier_share: tuple[float, ...] = (0.35, 0.40, 0.25)  # small / medium / large hotels (assumption)
    early_share: float = 0.85  # booked >= 21 days ahead (from the real Offline TA/TO bookings)
    occ_free: float = 80.0  # occupancy at or below which buying as needed is always possible
    occ_full: float = 95.0  # occupancy at or above which buying as needed is impossible
    methods: tuple[str, ...] = ("slevel_wc", "chronos2_wc")
    headline: str = "auto"  # pre-declared: pick the method with the lowest recent realised error
    half_life: float = 6.0  # months, recency weighting of past forecast errors (width calibration)
    n_scen: int = 200
    seed: int = 11
    lambdas: tuple[float, ...] = (0.0, 0.25, 1.0)
    # safeguards: added after the first replay exposed over-commitment through COVID (disclosed in the README)
    breaker_ratio: float | None = 2.0  # no prepaid blocks if the forecast was off by > 2x in any recent published month
    breaker_lookback: int = 3
    support_mult: float | None = 1.5  # forecast quantiles never exceed 1.5x the highest month ever published


def _months(cfg: SGConfig) -> pd.DatetimeIndex:
    return pd.date_range(cfg.start, cfg.end, freq="MS")


def _medians(panel: pd.DataFrame, hist: pd.DataFrame, target: pd.Timestamp, method: str, steps: int) -> dict:
    if method.startswith("slevel"):
        return {c: slevel_median(hist[c], target) for c in SERIES}
    if method.startswith("snaive"):
        return {c: snaive_median(hist[c], target) for c in SERIES}
    if method.startswith("chronos2"):
        try:
            return chronos_monthly_medians(hist, SERIES, steps)
        except Exception:  # noqa: BLE001 - fall back and keep going; recorded by the caller
            return {c: slevel_median(hist[c], target) for c in SERIES} | {"_fallback": True}
    raise ValueError(f"unknown method {method!r}")


def decision_inputs(panel: pd.DataFrame, d: pd.Timestamp, cfg: SGConfig, history: dict) -> dict:
    """What the planner knows at the start of month d. `history[(method, series)]` holds past
    forecasts ({target, median, q}); only those whose target month is already published are used."""
    d = pd.Timestamp(d)
    L = d - cfg.lag_months * MONTH
    t = d + cfg.lead_months * MONTH
    hist = panel.loc[panel.index <= L]
    steps = cfg.lag_months + cfg.lead_months
    per_method = {}
    for m in cfg.methods:
        med = _medians(panel, hist, t, m, steps)
        qs = {}
        for c in SERIES:
            past = [h for h in history.get((m, c), []) if h["target"] <= L]
            res = np.array([np.log(max(panel.at[h["target"], c], 1.0)) - np.log(max(h["median"], 1.0)) for h in past])
            ages = np.array([(L.year - h["target"].year) * 12 + (L.month - h["target"].month) for h in past], float)
            q = weighted_conformal(med[c], res, ages, cfg.half_life)
            upper = (100.0 if c.startswith("occ_") else
                     cfg.support_mult * float(hist[c].max()) if cfg.support_mult is not None else np.inf)
            qs[c] = np.minimum(q, upper)  # physical plausibility: no market far beyond anything ever seen
        per_method[m] = {"median": med, "q": qs, "fallback": bool(med.get("_fallback", False))}

    # auto: lowest mean scaled pinball loss on arrivals over the last 24 published targets
    chosen = cfg.headline
    if cfg.headline == "auto":
        scores = {}
        for m in cfg.methods:
            past = [h for h in history.get((m, "india_arrivals"), []) if h["target"] <= L][-24:]
            if len(past) >= 6:
                ys = np.array([panel.at[h["target"], "india_arrivals"] for h in past], float)
                qq = np.vstack([h["q"] for h in past])
                scores[m] = pinball_loss(ys, qq) / max(ys.mean(), 1.0)
        chosen = min(scores, key=scores.get) if scores else cfg.methods[0]
    pm = per_method[chosen]
    # circuit breaker: how wrong was the chosen model on the latest published months?
    recent = [h for h in history.get((chosen, "india_arrivals"), []) if h["target"] <= L][-cfg.breaker_lookback:]
    recent_err = max((abs(np.log(max(panel.at[h["target"], "india_arrivals"], 1.0)) - np.log(max(h["median"], 1.0)))
                      for h in recent), default=0.0)
    breaker = bool(cfg.breaker_ratio is not None and recent_err > np.log(cfg.breaker_ratio))
    ly_t = t - 12 * MONTH
    shares = np.asarray(cfg.tier_share)
    ly_arr = float(panel.at[ly_t, "india_arrivals"]) if ly_t <= L else float(hist["india_arrivals"].iloc[-12:].mean())
    return {
        "decision": d, "target": t, "last_published": L, "method": chosen, "per_method": per_method,
        "breaker": breaker, "recent_error_ratio": float(np.exp(recent_err)),
        "arrivals_q": pm["q"]["india_arrivals"],
        "occ_q": np.vstack([pm["q"][f"occ_{x}"] for x in TIERS]),
        "rate_q": np.vstack([pm["q"][f"rate_{x}"] for x in TIERS]),
        # contract reference rate: negotiated on the recent rate level x the month's seasonal factor, per tier
        "ref_rate": np.array([slevel_median(hist[f"rate_{x}"], t) for x in TIERS]),
        "ly_demand": cfg.kappa * shares * ly_arr,
    }


def _dyn_fraction(occ: np.ndarray, cfg: SGConfig) -> np.ndarray:
    return np.clip((cfg.occ_full - occ) / (cfg.occ_full - cfg.occ_free), 0.0, 1.0)


def _plan_cells(inp: dict, cfg: SGConfig, rng: np.random.Generator) -> Cells:
    S = cfg.n_scen
    u = rng.uniform(size=(1, S))  # one draw drives arrivals, occupancy and rates (comonotone: shocks hit all)
    arr = sample_from_quantiles(inp["arrivals_q"][None, :], u)[0]
    occ = sample_from_quantiles(inp["occ_q"], np.repeat(u, len(TIERS), 0))
    price = sample_from_quantiles(inp["rate_q"], np.repeat(u, len(TIERS), 0))
    demand = cfg.kappa * np.asarray(cfg.tier_share)[:, None] * arr[None, :]
    early = cfg.early_share * demand
    return Cells(group=np.arange(len(TIERS)), price=price, ref_rate=inp["ref_rate"], late=demand - early,
                 early=early, dyn_cap=_dyn_fraction(occ, cfg) * demand, dyn_price=price).validate()


def _real_cells(panel: pd.DataFrame, inp: dict, cfg: SGConfig) -> Cells:
    t = inp["target"]
    arr = float(panel.at[t, "india_arrivals"])
    demand = (cfg.kappa * np.asarray(cfg.tier_share) * arr)[:, None]
    occ = np.array([panel.at[t, f"occ_{x}"] for x in TIERS], float)[:, None]
    price = np.array([panel.at[t, f"rate_{x}"] for x in TIERS], float)[:, None]
    early = cfg.early_share * demand
    return Cells(group=np.arange(len(TIERS)), price=price, ref_rate=inp["ref_rate"], late=demand - early,
                 early=early, dyn_cap=_dyn_fraction(occ, cfg) * demand, dyn_price=price).validate()


def run_sg(panel: pd.DataFrame, cfg: SGConfig | None = None, terms: ContractTerms | None = None) -> dict:
    cfg = cfg or SGConfig()
    terms = (terms or ContractTerms()).validate()
    rng = np.random.default_rng(cfg.seed)
    shares = np.asarray(cfg.tier_share)
    i50, i25, i10, i90 = (QUANTILES.index(x) for x in (0.5, 0.25, 0.1, 0.9))
    history: dict = {}
    rows, fc_rows, timeline, notes = [], [], [], []
    for d in _months(cfg):
        inp = decision_inputs(panel, d, cfg, history)
        t = inp["target"]
        for m, pm in inp["per_method"].items():  # remember every method's forecast for later calibration/selection
            for c in SERIES:
                history.setdefault((m, c), []).append({"target": t, "median": pm["median"][c], "q": pm["q"][c]})
            if pm["fallback"]:
                notes.append(f"{d.date()}: {m} failed, used seasonal level")
        plan_cells = _plan_cells(inp, cfg, rng)
        real = _real_cells(panel, inp, cfg)
        med_d = cfg.kappa * shares * inp["arrivals_q"][i50]
        cap = np.floor(np.maximum(inp["ly_demand"], med_d))
        plans = {
            "dynamic_only": Plan.zeros(3),
            "last_year_hard": Plan(hard=np.floor(inp["ly_demand"]), soft=np.zeros(3)),
            "point_forecast_hard": Plan(hard=np.floor(med_d), soft=np.zeros(3)),
            "allot_ly_block_p25": Plan(hard=np.floor(cfg.kappa * shares * inp["arrivals_q"][i25]), soft=cap.copy()),
        }
        # like-for-like: every rule also gets a twin with the same breaker (no prepaid blocks, allot up to the cap)
        for base in ("last_year_hard", "point_forecast_hard", "allot_ly_block_p25"):
            p0 = plans[base]
            plans[base + "_brk"] = (Plan(hard=np.zeros(3), soft=cap.copy()) if inp["breaker"]
                                    else Plan(hard=p0.hard.copy(), soft=p0.soft.copy()))
        hard_cap = np.zeros(3) if inp["breaker"] else None  # breaker: allotments and buy-as-needed only
        for lam in cfg.lambdas:
            res = optimize(plan_cells, terms, OptimizerParams(risk_aversion=lam, soft_cap=cap, hard_cap=hard_cap))
            plans[f"ours_{lam:g}"] = res.plan_int if res.status == "optimal" else Plan.zeros(3)
            if res.status != "optimal":
                notes.append(f"{d.date()}: ours_{lam:g} solve {res.status}, used buy-as-needed")
        hs = optimize(real, terms, OptimizerParams(soft_cap=cap))
        if hs.status != "optimal":
            raise RuntimeError(f"hindsight solve for {t.date()} returned {hs.status!r}")
        plans["hindsight"] = hs.plan
        hard_cost = terms.costs(real.ref_rate, real.ref_rate)["hard"]
        for name, p in plans.items():
            out = evaluate(real, p, terms)
            rows.append({"decision": str(d.date()), "target": str(t.date()), "policy": name,
                         "profit": float(out.profit[0]), "demand": float(out.demand.sum()),
                         "served": float(out.served.sum()), "hard": float(np.sum(p.hard)), "soft": float(np.sum(p.soft)),
                         "soft_cap": float(cap.sum()), "spend": float(hard_cost @ np.asarray(p.hard)),
                         "unsold_cost": float(out.unsold_cost[0]), "method": inp["method"]})
        y = float(panel.at[t, "india_arrivals"])
        for m, pm in inp["per_method"].items():
            fc_rows.append({"target": t, "method": m, "y": y, **{f"q{k}": v for k, v in zip(QUANTILES, pm["q"]["india_arrivals"])}})
        fc_rows.append({"target": t, "method": "headline", "y": y,
                        **{f"q{k}": v for k, v in zip(QUANTILES, inp["arrivals_q"])}})
        def total(name: str) -> tuple[float, float]:
            return float(np.sum(plans[name].hard)), float(np.sum(plans[name].soft))

        timeline.append({"target": str(t.date()), "demand": float(cfg.kappa * y),
                         "median": float(cfg.kappa * inp["arrivals_q"][i50]),
                         "p10": float(cfg.kappa * inp["arrivals_q"][i10]), "p90": float(cfg.kappa * inp["arrivals_q"][i90]),
                         "ours_hard": total("ours_0.25")[0], "ours_soft": total("ours_0.25")[1],
                         "pf_hard": total("point_forecast_hard")[0], "method": inp["method"],
                         "breaker": inp["breaker"], "error_ratio": inp["recent_error_ratio"],
                         "occ_all": float(panel.at[t, "occ_all"]), "rate_all": float(panel.at[t, "rate_all"])})
    return _report(pd.DataFrame(rows), pd.DataFrame(fc_rows), timeline, notes, cfg, terms)


def _summ(df: pd.DataFrame) -> dict:
    piv = df.pivot_table(index="target", columns="policy", values="profit", aggfunc="sum")
    h = piv["hindsight"].sum()
    out = {}
    for pol in piv.columns:
        p = piv[pol]
        sub = df[df.policy == pol]
        out[pol] = {"profit": float(p.sum()), "pct_of_hindsight": float(100 * p.sum() / h) if h else None,
                    "worst_month": float(p.min()), "months_with_loss": int((p < 0).sum()),
                    "worst5_month_avg": float(cvar_profit(p.to_numpy(), 0.95)), "months": int(len(p)),
                    "fill_rate": float(sub.served.sum() / max(sub.demand.sum(), 1e-9)),
                    "unsold_cost": float(sub.unsold_cost.sum())}
    return out


def _report(df: pd.DataFrame, fc: pd.DataFrame, timeline: list, notes: list, cfg: SGConfig, terms: ContractTerms) -> dict:
    df["t"] = pd.to_datetime(df["target"])
    by_period = {}
    for name, (a, b) in PERIODS.items():
        sub = df[(df.t >= a) & (df.t <= b)]
        if len(sub):
            by_period[name] = _summ(sub)
    forecast = {}
    qcols = [f"q{k}" for k in QUANTILES]
    for m, g in fc.groupby("method"):
        forecast[m] = {}
        for name, (a, b) in [("all", ("2000-01-01", "2100-01-01"))] + list(PERIODS.items()):
            s = g[(g.target >= a) & (g.target <= b)]
            if len(s):
                q = s[qcols].to_numpy()
                forecast[m][name] = {"months": int(len(s)), "coverage_80": coverage(s.y.to_numpy(), q),
                                     "wape": wape(s.y.to_numpy(), q[:, QUANTILES.index(0.5)])}
    methods_used = df[df.policy == "ours_0.25"]["method"].value_counts().to_dict()
    breaker_months = [r["target"] for r in timeline if r.get("breaker")]
    return {
        "summary": _summ(df.drop(columns="t")),
        "by_period": by_period,
        "forecast": forecast,
        "methods_used": {k: int(v) for k, v in methods_used.items()},
        "breaker_months": breaker_months,
        "timeline": timeline,
        "by_month": df.drop(columns="t").to_dict(orient="records"),
        "notes": notes,
        "assumptions": {**{k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(cfg).items()},
                        "terms": terms.as_dict(), "currency": "SGD",
                        "sources": "SingStat M550001 (India arrivals), M550081 (hotel rates & occupancy by size band); "
                                   "Singapore Open Data Licence"},
    }


NAMES = {"dynamic_only": "Buy as needed only", "last_year_hard": "Block last year's volume",
         "point_forecast_hard": "Block the median forecast",
         "allot_ly_block_p25": "Allot expected volume + block the 25th-percentile forecast",
         "last_year_hard_brk": "Block last year's volume + same breaker",
         "point_forecast_hard_brk": "Block the median forecast + same breaker",
         "allot_ly_block_p25_brk": "Allot + block p25 + same breaker",
         "ours_0": "Blockwise · Max profit", "ours_0.25": "Blockwise · Balanced", "ours_1": "Blockwise · Careful",
         "hindsight": "Perfect hindsight"}
ORDER = ["dynamic_only", "last_year_hard", "point_forecast_hard", "allot_ly_block_p25", "last_year_hard_brk",
         "point_forecast_hard_brk", "allot_ly_block_p25_brk", "ours_0", "ours_0.25", "ours_1", "hindsight"]


def to_markdown(rep: dict) -> str:
    def table(s: dict) -> list[str]:
        out = ["| policy | profit (SGD) | % of hindsight | worst month | months with a loss | worst-5% month avg |",
               "|---|---|---|---|---|---|"]
        for p in ORDER:
            if p in s:
                r = s[p]
                out.append(f"| {NAMES[p]} | {r['profit']:,.0f} | {r['pct_of_hindsight']:.1f}% | {r['worst_month']:,.0f} | "
                           f"{r['months_with_loss']} | {r['worst5_month_avg']:,.0f} |")
        return out
    lines = ["## All months"] + table(rep["summary"])
    for name, s in rep["by_period"].items():
        lines += ["", f"## {name}"] + table(s)
    return "\n".join(lines)
