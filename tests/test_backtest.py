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


@pytest.mark.parametrize("fc", ["gbm_conf", "qr_conf"])
def test_no_lookahead_new_forecasters(bookings, short_cfg, fc):
    from dataclasses import replace
    cfg = replace(short_cfg, forecaster=fc)
    nights = pd.date_range(T + pd.Timedelta(days=56), periods=28, freq="D")
    outs = []
    for bk in (bookings, _alter_after(bookings, T)):
        book = HotelBook(bk, "City Hotel", B2B_SEGMENTS, cfg.release_days)
        outs.append(planning_inputs(book, T, nights, cfg, capacity(book, T)))
    np.testing.assert_allclose(outs[0]["quantiles"], outs[1]["quantiles"])


def test_backtest_accepts_forecaster(bookings, short_cfg):
    from dataclasses import replace
    nights = pd.date_range(T + pd.Timedelta(days=56), periods=28, freq="D")
    book = HotelBook(bookings, "City Hotel", B2B_SEGMENTS, short_cfg.release_days)
    K = capacity(book, T)
    q_qr = planning_inputs(book, T, nights, short_cfg, K)["quantiles"]
    q_gbm = planning_inputs(book, T, nights, replace(short_cfg, forecaster="gbm_conf"), K)["quantiles"]
    assert q_gbm.shape == q_qr.shape and not np.allclose(q_gbm, q_qr)
    assert np.all(np.diff(q_gbm, axis=1) >= -1e-9)


def test_selector_uses_only_realised_history():
    from invopt.backtest import _select_forecaster
    t = pd.Timestamp("2017-01-01")
    hist = [
        {"available_from": t - pd.Timedelta(days=10), "name": "gbm_conf", "pinball": 1.0},
        {"available_from": t - pd.Timedelta(days=10), "name": "qr", "pinball": 2.0},
        {"available_from": t + pd.Timedelta(days=1), "name": "qr", "pinball": 0.1},  # not realised yet
    ]
    assert _select_forecaster(hist, t, default="qr") == "gbm_conf"
    assert _select_forecaster([], t, default="qr") == "qr"
    assert _select_forecaster(hist[2:], t, default="qr") == "qr"


def test_auto_backtest_records_choices(bookings):
    cfg = BacktestConfig(start="2016-07-04", end="2016-08-28", n_scen=30, lambdas=(0.0,), seed=3, forecaster="auto")
    res = run_backtest(bookings, cfg, ContractTerms())
    for b in res.meta["batches"]:
        assert set(b["forecaster"]) == {"City Hotel", "Resort Hotel"}
        assert all(v == "qr" for v in b["forecaster"].values())  # nothing realised yet in the first 2 rounds
    assert "candidates" in res.forecast_metrics


def test_chronos_failure_falls_back_to_qr(bookings, short_cfg, monkeypatch):
    from dataclasses import replace

    import invopt.chronos_fc as cf

    def boom(*a, **k):
        raise FloatingPointError("simulated Chronos failure")
    monkeypatch.setattr(cf, "chronos2_quantiles", boom)
    nights = pd.date_range(T + pd.Timedelta(days=56), periods=28, freq="D")
    book = HotelBook(bookings, "City Hotel", B2B_SEGMENTS, short_cfg.release_days)
    K = capacity(book, T)
    a = planning_inputs(book, T, nights, replace(short_cfg, forecaster="chronos2"), K)
    b = planning_inputs(book, T, nights, short_cfg, K)
    np.testing.assert_allclose(a["quantiles"], b["quantiles"])
    assert a["notes"] and "chronos2" in a["notes"][0]
