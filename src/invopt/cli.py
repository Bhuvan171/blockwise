"""Command line: python -m invopt.cli backtest|grid|page|all"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
DATA = ROOT / "data" / "raw" / "hotels.csv"


def terms_from_args(args):
    """ContractTerms from --hard/--soft/--dyn-discount (defaults = the headline assumptions), validated."""
    from invopt.config import ContractTerms

    d = ContractTerms()

    def pick(name):
        v = getattr(args, name, None)
        return getattr(d, name) if v is None else v

    return ContractTerms(hard_discount=pick("hard_discount"), soft_discount=pick("soft_discount"),
                         dyn_discount=pick("dyn_discount")).validate()


def _add_terms_flags(parser) -> None:
    parser.add_argument("--hard-discount", type=float, default=None, help="hard block rate vs reference (default 0.30)")
    parser.add_argument("--soft-discount", type=float, default=None, help="allotment rate vs reference (default 0.20)")
    parser.add_argument("--dyn-discount", type=float, default=None, help="buy-as-needed rate vs market (default 0.10)")


def cmd_backtest(args) -> None:
    from invopt.backtest import BacktestConfig, run_backtest
    from invopt.hotel_data import load_bookings

    if not DATA.exists():
        raise SystemExit("Missing data/raw/hotels.csv: run scripts/fetch_data.sh first")
    t0 = time.perf_counter()
    bookings, _ = load_bookings(DATA)
    cap = None if args.soft_cap_mult.lower() == "none" else float(args.soft_cap_mult)
    cfg = BacktestConfig(budget_share=args.budget_share, soft_cap_mult=cap, soldout_tau=args.soldout_tau,
                         forecaster=getattr(args, "forecaster", "qr"))
    res = run_backtest(bookings, cfg, terms_from_args(args))
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


def cmd_grid(args) -> None:
    import json

    from invopt.grid import run_grid

    t0 = time.perf_counter()
    res = run_grid(n_plan=args.n_plan, n_eval=args.n_eval, workers=args.workers,
                   backtest_path=OUT / "backtest.json", terms=terms_from_args(args))
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, allow_nan=False, separators=(",", ":")))
    bad = [(b, r, c["status"]) for b, row in res["cells"].items() for r, c in row.items() if c["status"] != "optimal"]
    print(f"budgets (INR crore): {[round(b / 1e7, 1) for b in res['budgets_inr']]}  B* = {res['b_star_inr'] / 1e7:.1f} Cr")
    for risk, f in res["frontier"].items():
        print(f"  {risk:13s} mean (Cr): {[round(m / 1e7, 2) for m in f['mean']]}  "
              f"worst-5% (Cr): {[round(c / 1e7, 2) for c in f['cvar95']]}")
    print("non-optimal solves:", bad or "none")
    print(f"results.json {(OUT / 'results.json').stat().st_size / 1e6:.2f} MB, done in {time.perf_counter() - t0:.0f}s")


def cmd_page(args) -> None:
    from invopt.page import build_page

    src = OUT / "results.json"
    if not src.exists():
        raise SystemExit("Missing out/results.json: run `python -m invopt.cli grid` first")
    a = build_page(src, OUT / "blockwise.html")
    b = build_page(src, OUT / "blockwise_standalone.html", standalone=True)
    print(f"wrote {a} ({a.stat().st_size / 1e6:.2f} MB, artifact content) and {b} (open in a browser)")


def cmd_all(args) -> None:
    cmd_backtest(args)
    cmd_grid(args)
    cmd_page(args)


def cmd_bench(args) -> None:
    from invopt.forecast_bench import run_bench

    t0 = time.perf_counter()
    res = run_bench([n.strip() for n in args.forecasters.split(",") if n.strip()], workers=args.workers, out_dir=OUT)
    print(res["markdown"])
    print(f"done in {time.perf_counter() - t0:.0f}s")


def cmd_singapore(args) -> None:
    import json

    from invopt.sg_backtest import SGConfig, run_sg, to_markdown
    from invopt.sg_data import load_panel

    a, h = ROOT / "data/raw/singstat_M550001.json", ROOT / "data/raw/singstat_M550081.json"
    if not (a.exists() and h.exists()):
        raise SystemExit("Missing SingStat files: run scripts/fetch_singstat.sh first")
    t0 = time.perf_counter()
    rep = run_sg(load_panel(a, h), SGConfig(half_life=args.half_life), terms_from_args(args))
    OUT.mkdir(exist_ok=True)
    (OUT / f"singapore{args.tag}.json").write_text(json.dumps(rep, allow_nan=False, default=str))
    md = to_markdown(rep)
    (OUT / f"singapore{args.tag}.md").write_text(md + "\n")
    print(md)
    print("methods used (Balanced):", rep["methods_used"], "| notes:", rep["notes"][:5])
    for m, f in rep["forecast"].items():
        print(m, {k: (round(v["coverage_80"], 2), round(v["wape"], 3)) for k, v in f.items()})
    print(f"done in {time.perf_counter() - t0:.0f}s")


def build_parser() -> argparse.ArgumentParser:
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
    b.add_argument("--forecaster", default="qr", help="qr | qr_conf | gbm | gbm_conf | chronos2 | ensemble_conf | auto")
    _add_terms_flags(b)
    b.set_defaults(func=cmd_backtest)
    g = sub.add_parser("grid", help="plans for every budget x risk level on the synthetic portfolio")
    g.add_argument("--n-plan", type=int, default=150)
    g.add_argument("--n-eval", type=int, default=4000)
    g.add_argument("--workers", type=int, default=2)
    _add_terms_flags(g)
    g.set_defaults(func=cmd_grid)
    fb = sub.add_parser("bench", help="forecaster benchmark: accuracy + profit in the real-bookings backtest")
    fb.add_argument("--forecasters", default="qr,qr_conf,gbm_conf,chronos2,ensemble_conf,auto")
    fb.add_argument("--workers", type=int, default=3)
    fb.set_defaults(func=cmd_bench)
    sg = sub.add_parser("singapore", help="real-shock replay on official SingStat data, 2011-2026")
    sg.add_argument("--half-life", type=float, default=6.0,
                    help="months; weighting of past errors in calibration (1e9 = static, equal weights)")
    sg.add_argument("--tag", default="", help="suffix for output files, e.g. _static")
    _add_terms_flags(sg)
    sg.set_defaults(func=cmd_singapore)
    p = sub.add_parser("page", help="render out/blockwise*.html from out/results.json")
    p.set_defaults(func=cmd_page)
    a = sub.add_parser("all", help="backtest, grid, then page (headline settings)")
    a.set_defaults(func=cmd_all, budget_share=None, soft_cap_mult="1.0", soldout_tau=0.98, tag="",
                   n_plan=150, n_eval=4000, workers=2)
    _add_terms_flags(a)
    return ap


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
