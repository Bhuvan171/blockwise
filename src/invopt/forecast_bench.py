"""Forecaster benchmark, judged two ways: forecast accuracy, and the profit the planner earns with it.

Each forecaster drives a full real-bookings backtest (same rounds, same rules, same seeds).
Accuracy: WAPE of the median, pinball loss (all 7 quantiles), 80%/90% band coverage, band width.
Profit: Blockwise-Balanced share of perfect-hindsight profit (90% range from resampling rounds).
The headline forecaster is fixed before running (`auto`: online selection on realised error).
"""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

LABELS = {
    "qr": "Linear quantile regression (Round 1 baseline)",
    "qr_conf": "Linear quantile regression + conformal",
    "gbm": "Gradient-boosted quantiles + booking pace",
    "gbm_conf": "Gradient-boosted quantiles + booking pace + conformal",
    "chronos2": "Chronos-2 foundation model (zero-shot, pace covariates)",
    "ensemble_conf": "Ensemble: conformal LQR + conformal GBM + Chronos-2",
    "auto": "Auto: pick the model with the lowest realised error so far",
}


def _one(name: str) -> tuple[str, dict]:
    try:  # optional stack: only Chronos-2 needs it
        import torch

        torch.set_num_threads(4)
    except ImportError:
        pass
    from invopt.backtest import BacktestConfig, run_backtest
    from invopt.cli import DATA, OUT
    from invopt.config import ContractTerms
    from invopt.hotel_data import load_bookings

    bookings, _ = load_bookings(DATA)
    res = run_backtest(bookings, BacktestConfig(forecaster=name), ContractTerms())
    res.to_json(OUT / f"backtest_fc_{name}.json")
    return name, json.loads((OUT / f"backtest_fc_{name}.json").read_text())


def aggregate(runs: dict[str, dict], headline: str = "auto") -> dict:
    rows = []
    for name, r in runs.items():
        s = {x["policy"]: x for x in r["summary"]}
        ours = s["ours_0.25"]
        fm = r["forecast_metrics"]["all"]
        rows.append({
            "forecaster": name, "label": LABELS.get(name, name),
            "pct_of_hindsight": ours["pct_of_hindsight"], "pct_ci_lo": ours["pct_ci_lo"], "pct_ci_hi": ours["pct_ci_hi"],
            "profit": ours["total_profit"], "rounds_with_loss": ours["batches_with_loss"],
            "wape": fm["wape_median"], "pinball": fm["pinball"], "coverage_80": fm["coverage_80"],
            "coverage_90": fm.get("coverage_90"), "width_80_rel": fm.get("width_80_rel"),
        })
    rows.sort(key=lambda x: -x["pct_of_hindsight"])
    head = ("| forecaster | Blockwise·Balanced % of hindsight (90% range) | WAPE | pinball | 80% band holds | "
            "90% band holds | 80% band width |\n|---|---|---|---|---|---|---|")
    lines = [head]
    for x in rows:
        star = " **(headline, pre-declared)**" if x["forecaster"] == headline else ""
        c90 = f"{x['coverage_90']:.0%}" if x["coverage_90"] is not None else "–"
        w = f"{x['width_80_rel']:.0%} of demand" if x["width_80_rel"] is not None else "–"
        lines.append(f"| {x['label']} (`{x['forecaster']}`){star} | {x['pct_of_hindsight']:.1f}% ({x['pct_ci_lo']:.0f}–{x['pct_ci_hi']:.0f}) | "
                     f"{x['wape']:.1%} | {x['pinball']:.2f} | {x['coverage_80']:.0%} | {c90} | {w} |")
    cands = runs.get("auto", {}).get("forecast_metrics", {}).get("candidates")
    if cands:
        lines += ["", "Accuracy of every candidate inside the auto run (same nights):", "",
                  "| candidate | WAPE | pinball | 80% band holds | 90% band holds |", "|---|---|---|---|---|"]
        for n, m in sorted(cands.items(), key=lambda kv: kv[1]["pinball"]):
            lines.append(f"| {LABELS.get(n, n)} | {m['wape_median']:.1%} | {m['pinball']:.2f} | "
                         f"{m['coverage_80']:.0%} | {m.get('coverage_90', float('nan')):.0%} |")
    choices = None
    if "auto" in runs:
        choices = [b.get("forecaster") for b in runs["auto"].get("meta", {}).get("batches", [])]
    return {"headline": headline, "rows": rows, "auto_choices": choices, "markdown": "\n".join(lines)}


def run_bench(names: list[str], workers: int = 3, out_dir: Path | None = None) -> dict:
    with ProcessPoolExecutor(max_workers=workers) as ex:
        runs = dict(ex.map(_one, names))
    res = aggregate(runs, headline="auto" if "auto" in runs else names[0])
    if out_dir is not None:
        Path(out_dir, "forecast_bench.json").write_text(json.dumps(res, indent=2, default=str))
        Path(out_dir, "forecast_bench.md").write_text(res["markdown"] + "\n")
    return res
