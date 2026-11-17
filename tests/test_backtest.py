from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from invopt.backtest import BacktestConfig, HotelBook, capacity, planning_inputs, run_backtest
from invopt.config import ContractTerms
from invopt.hotel_data import B2B_SEGMENTS, load_bookings

DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "hotels.csv"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="run scripts/fetch_data.sh first")

T = pd.Timestamp("2016-05-09")  # first decision date for start 2016-07-04, horizon 56


@pytest.fixture(scope="module")
def bookings():
    return load_bookings(DATA)[0]


@pytest.fixture(scope="module")
def short_cfg():
    return BacktestConfig(start="2016-07-04", end="2016-08-28", n_scen=30, lambdas=(0.0,), seed=3)


def _alter_after(bookings, t):
    alt = bookings.copy()
    m = alt["booking_date"] > t
    alt.loc[m, "arrival"] = alt.loc[m, "arrival"] + pd.Timedelta(days=3)
    alt.loc[m, "booking_date"] = alt.loc[m, "booking_date"] + pd.Timedelta(days=3)
    alt.loc[m, "adr"] = alt.loc[m, "adr"] * 2
    return alt


def test_no_lookahead(bookings, short_cfg):
    nights = pd.date_range(T + pd.Timedelta(days=56), periods=28, freq="D")
    out = []
    for bk in (bookings, _alter_after(bookings, T)):
        book = HotelBook(bk, "City Hotel", B2B_SEGMENTS, short_cfg.release_days)
        K = capacity(book, T)
        out.append((K, planning_inputs(book, T, nights, short_cfg, K)))
    (k1, a), (k2, b) = out
    assert k1 == k2
    for key in ("quantiles", "early_share", "ref_rate", "q_soldout", "ly_final", "on_hand"):
        np.testing.assert_allclose(a[key], b[key], err_msg=key)
    pd.testing.assert_frame_equal(a["features"], b["features"])


def test_capacity_uses_data_before_first_decision(bookings, short_cfg):
    book = HotelBook(bookings, "City Hotel", B2B_SEGMENTS, short_cfg.release_days)
    dup = pd.concat([bookings, bookings[bookings["arrival"] >= T]], ignore_index=True)  # double later occupancy
    book2 = HotelBook(dup, "City Hotel", B2B_SEGMENTS, short_cfg.release_days)
    assert capacity(book, T) == capacity(book2, T)


@pytest.fixture(scope="module")
def short_run(bookings, short_cfg):
    return run_backtest(bookings, short_cfg, ContractTerms())


def test_hindsight_dominates(short_run):
    bb = short_run.by_batch.groupby(["batch_start", "policy"])["profit"].sum().unstack()
    for pol in bb.columns:
        assert (bb["hindsight"] >= bb[pol] - 1e-6).all(), pol


def test_policies_respect_budget(bookings):
    cfg = BacktestConfig(start="2016-07-04", end="2016-08-28", n_scen=30, lambdas=(0.0,), seed=3, budget_share=0.3)
    res = run_backtest(bookings, cfg, ContractTerms())
    per = res.by_batch.groupby(["batch_start", "policy"]).agg(spend=("spend", "sum"), budget=("budget", "first"))
    assert (per["spend"] <= per["budget"] + 1e-6).all()


def test_summary_and_json(short_run, tmp_path):
    s = short_run.summary
    assert {"dynamic_only", "last_year_hard", "point_forecast_hard", "ours_0", "hindsight"} <= set(s.index)
    assert s.loc["hindsight", "pct_of_hindsight"] == pytest.approx(100.0)
    p = tmp_path / "bt.json"
    short_run.to_json(p)
    assert p.read_text().startswith("{")
    assert "| policy" in short_run.to_markdown()


def test_allotment_capped_at_last_year_production(bookings):
    cfg = BacktestConfig(start="2016-07-04", end="2016-08-28", n_scen=30, lambdas=(0.0,), seed=3, soft_cap_mult=1.0)
    res = run_backtest(bookings, cfg, ContractTerms())
    bb = res.by_batch
    for pol in ("ours_0", "hindsight"):
        rows = bb[bb.policy == pol]
        assert (rows["soft_units"] <= rows["soft_cap_units"] + 1e-6).all(), pol
    assert (bb["soft_cap_units"] > 0).any()


def test_two_contract_rule_baseline(short_run):
    s = short_run.summary
    assert "allot_ly_block_p25" in s.index
    rows = short_run.by_batch[short_run.by_batch.policy == "allot_ly_block_p25"]
    assert (rows["soft_units"] <= rows["soft_cap_units"] + 1e-6).all()
    assert (rows["soft_units"] > 0).any() and (rows["hard_units"] > 0).any()


def test_bootstrap_interval_brackets_point(short_run):
    s = short_run.summary
    for pol, r in s.iterrows():
        assert r.pct_ci_lo <= r.pct_of_hindsight + 1e-9 <= r.pct_ci_hi + 2e-9, pol
    assert s.loc["hindsight", "pct_ci_lo"] == pytest.approx(100.0)


def test_hindsight_failure_aborts(bookings, short_cfg, monkeypatch):
    import invopt.backtest as bt
    from invopt.economics import Plan
    from invopt.optimizer import OptResult
    real = bt.optimize

    def flaky(cells, terms, params):
        if cells.n_scen == 1:  # the hindsight solve
            z = Plan.zeros(cells.n_groups)
            return OptResult(plan=z, plan_int=z, status="time_limit", objective=float("nan"),
                             budget_shadow_price=0.0, solve_seconds=0.0)
        return real(cells, terms, params)
    monkeypatch.setattr(bt, "optimize", flaky)
    with pytest.raises(RuntimeError, match="hindsight"):
        run_backtest(bookings, short_cfg, ContractTerms())
