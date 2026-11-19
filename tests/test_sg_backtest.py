import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from invopt.sg_backtest import SGConfig, decision_inputs, run_sg
from invopt.sg_data import load_panel

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
pytestmark = pytest.mark.skipif(not (RAW / "singstat_M550081.json").exists(), reason="fetch SingStat first")


@pytest.fixture(scope="module")
def panel():
    return load_panel(RAW / "singstat_M550001.json", RAW / "singstat_M550081.json")


def test_no_lookahead_publication_lag(panel):
    d = pd.Timestamp("2019-11-01")  # data through 2019-09; target 2020-01
    cfg = SGConfig(methods=("snaive_wc",))
    a = decision_inputs(panel, d, cfg, history={})
    alt = panel.copy()
    alt.loc[alt.index >= d - pd.DateOffset(months=1)] *= 7  # months d-1 onward are not yet published
    b = decision_inputs(alt, d, cfg, history={})
    for k in ("arrivals_q", "occ_q", "rate_q", "ref_rate", "ly_demand"):
        np.testing.assert_allclose(a[k], b[k], err_msg=k)


@pytest.fixture(scope="module")
def short(panel):
    cfg = SGConfig(start="2019-06-01", end="2020-08-01", methods=("snaive_wc",), headline="snaive_wc", n_scen=60)
    return run_sg(panel, cfg)


def test_hindsight_dominates_each_month(short):
    m = short["by_month"]
    piv = pd.DataFrame(m).pivot_table(index="target", columns="policy", values="profit")
    for pol in piv.columns:
        assert (piv["hindsight"] >= piv[pol] - 1e-6).all(), pol


def test_allotment_cap_respected(short):
    rows = [r for r in short["by_month"] if r["policy"] in ("ours_0.25", "hindsight")]
    assert all(r["soft"] <= r["soft_cap"] + 1e-6 for r in rows)


def test_report_structure(short):
    assert {"summary", "by_period", "forecast", "timeline", "assumptions"} <= set(short)
    assert {"2011–19 normal", "2020–21 COVID", "2022–23 recovery", "2024–26 recent"} >= set(short["by_period"])
    json.dumps(short, allow_nan=False)


def _hist_entries(panel, cfg, d, ratio):
    """Fake past forecasts for the 3 latest published targets, each off by `ratio`."""
    L = pd.Timestamp(d) - cfg.lag_months * pd.DateOffset(months=1)
    entries = []
    for k in range(3):
        t = L - k * pd.DateOffset(months=1)
        y = float(panel.at[t, "india_arrivals"])
        entries.append({"target": t, "median": y / ratio, "q": np.full(7, y / ratio)})
    return {(cfg.methods[0], "india_arrivals"): entries}


def test_circuit_breaker_trips_on_large_recent_errors(panel):
    cfg = SGConfig(methods=("slevel_wc",), headline="slevel_wc")
    d = pd.Timestamp("2019-11-01")
    assert decision_inputs(panel, d, cfg, history=_hist_entries(panel, cfg, d, 1.2))["breaker"] is False
    assert decision_inputs(panel, d, cfg, history=_hist_entries(panel, cfg, d, 3.0))["breaker"] is True


def test_forecast_support_is_bounded(panel):
    cfg = SGConfig(methods=("slevel_wc",), headline="slevel_wc")
    d = pd.Timestamp("2022-06-01")
    inp = decision_inputs(panel, d, cfg, history={})
    L = d - 2 * pd.DateOffset(months=1)
    assert inp["arrivals_q"].max() <= cfg.support_mult * panel.loc[:L, "india_arrivals"].max() + 1e-6
    assert inp["occ_q"].max() <= 100.0 + 1e-9


def test_no_hard_blocks_while_breaker_is_on(panel):
    cfg = SGConfig(start="2020-03-01", end="2020-12-01", methods=("slevel_wc",), headline="slevel_wc", n_scen=60)
    rep = run_sg(panel, cfg)
    on = [r for r in rep["timeline"] if r["breaker"]]
    assert on, "expected the breaker to trip during 2020"
    assert all(r["ours_hard"] == 0 for r in on)
