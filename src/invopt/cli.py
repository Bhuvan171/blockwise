"""Command line: python -m invopt.cli backtest|grid|page|all"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
DATA = ROOT / "data" / "raw" / "hotels.csv"


def cmd_backtest(args) -> None:
    from invopt.backtest import BacktestConfig, run_backtest
    from invopt.config import ContractTerms
    from invopt.hotel_data import load_bookings

    if not DATA.exists():
        raise SystemExit("Missing data/raw/hotels.csv: run scripts/fetch_data.sh first")
    t0 = time.perf_counter()
    bookings, _ = load_bookings(DATA)
    cap = None if args.soft_cap_mult.lower() == "none" else float(args.soft_cap_mult)
    cfg = BacktestConfig(budget_share=args.budget_share, soft_cap_mult=cap, soldout_tau=args.soldout_tau)
    res = run_backtest(bookings, cfg, ContractTerms())
    OUT.mkdir(exist_ok=True)
    suffix = args.tag or ""
    res.to_json(OUT / f"backtest{suffix}.json")
    md = res.to_markdown()
    (OUT / f"backtest{suffix}.md").write_text(md + "\n")
    print(md)
    fm = res.forecast_metrics["all"]
    print(f"\nforecast: WAPE median {fm['wape_median']:.3f} vs last-year {fm['wape_last_year']:.3f}, "
          f"80% band coverage {fm['coverage_80']:.2f}, nights {fm['nights']}")
    print(f"done in {time.perf_counter() - t0:.0f}s")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="invopt")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest", help="walk-forward backtest on real bookings")
    b.add_argument("--budget-share", type=float, default=None,
                   help="prepaid budget per batch as a share of last year's volume at hard-block cost")
    b.add_argument("--soft-cap-mult", default="1.0",
                   help="allotment cap as a multiple of last year's weekly production, or 'none'")
    b.add_argument("--soldout-tau", type=float, default=0.98,
                   help="a night counts as sold out when occupancy >= tau x estimated capacity")
    b.add_argument("--tag", default="", help="suffix for output files, e.g. _uncapped")
    b.set_defaults(func=cmd_backtest)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
