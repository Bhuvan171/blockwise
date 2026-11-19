import numpy as np
import pandas as pd
import pytest

from invopt.forecast import QUANTILES, coverage
from invopt.sg_forecast import snaive_median, weighted_conformal


def _shift_series(seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2010-01-01", periods=120, freq="MS")
    season = np.ones(120)  # no seasonality: pre-shift errors are pure noise, so the test isolates calibration
    noise = np.where(np.arange(120) < 80, 0.05, 0.35)  # volatility jumps after month 80
    level = np.where(np.arange(120) < 80, 100.0, 40.0)
    return pd.Series(level * season * np.exp(rng.normal(0, noise)), index=idx)


def test_snaive_uses_only_history():
    y = _shift_series()
    t = pd.Timestamp("2016-05-01")
    m1 = snaive_median(y[y.index <= t - pd.DateOffset(months=4)], t)
    y2 = y.copy()
    y2[y2.index > t - pd.DateOffset(months=4)] *= 50
    m2 = snaive_median(y2[y2.index <= t - pd.DateOffset(months=4)], t)
    assert m1 == m2 and np.isfinite(m1) and m1 > 0


def test_snaive_survives_zeros():
    idx = pd.date_range("2018-01-01", periods=40, freq="MS")
    y = pd.Series(np.r_[np.full(26, 1000.0), np.zeros(6), np.full(8, 300.0)], index=idx)
    assert np.isfinite(snaive_median(y, idx[-1] + pd.DateOffset(months=4)))


def _replay(half_life):
    y = _shift_series(1)
    meds, ys, qs = [], [], []
    for i in range(30, 120):
        t = y.index[i]
        hist = y[y.index <= t - pd.DateOffset(months=4)]
        med = float(hist.iloc[-1])  # last observed value as the point forecast
        past_res = np.log(np.maximum(ys, 1)) - np.log(np.maximum(meds, 1)) if ys else np.array([])
        ages = np.arange(len(past_res))[::-1] + 4.0
        q = weighted_conformal(med, past_res, ages, half_life=half_life)
        meds.append(med), ys.append(float(y.iloc[i])), qs.append(q)
    q = np.array(qs)
    post = slice(80 - 30 + 6, 120 - 30)  # months 6+ after the shift
    return coverage(np.array(ys)[post], q[post])


def test_weighted_conformal_recovers_after_shift():
    adaptive, static = _replay(half_life=6.0), _replay(half_life=1e9)  # 1e9 = equal weights over all history
    assert adaptive >= 0.6
    assert adaptive - static >= 0.25


def test_weighted_conformal_shape_and_order():
    q = weighted_conformal(100.0, np.array([0.1, -0.2, 0.05] * 10), np.arange(30, dtype=float), half_life=6)
    assert q.shape == (len(QUANTILES),) and np.all(np.diff(q) >= 0) and np.all(q > 0)
    q0 = weighted_conformal(100.0, np.array([]), np.array([]), half_life=6)
    assert np.allclose(q0, 100.0 * np.exp(np.array([-1.0, -0.6, -0.25, 0.0, 0.25, 0.6, 1.0])), rtol=0.5)


def _covid_like():
    idx = pd.date_range("2012-01-01", periods=132, freq="MS")
    season = 1 + 0.3 * np.sin(2 * np.pi * np.arange(132) / 12)
    level = np.r_[np.full(96, 1000.0), np.full(20, 5.0), np.linspace(50, 900, 16)]  # normal, collapse, recovery
    return pd.Series(level * season, index=idx)


def test_seasonal_level_does_not_explode_in_recovery():
    from invopt.sg_forecast import slevel_median
    y = _covid_like()
    for i in range(118, 128):  # decisions during the recovery ramp
        L = y.index[i]
        hist = y[y.index <= L]
        target = L + pd.DateOffset(months=4)
        recent_max = hist.iloc[-12:].max()
        assert slevel_median(hist, target) <= 3 * recent_max
    # the seasonal naive does explode here (documents why it was replaced as the default point forecast)
    L = y.index[127]  # base month (t-12) sits in the collapse while the trend comes from the recovery
    assert snaive_median(y[y.index <= L], L + pd.DateOffset(months=4)) > 3 * y[y.index <= L].iloc[-12:].max()


def test_seasonal_level_tracks_seasonality_in_normal_times():
    from invopt.sg_forecast import slevel_median
    y = _covid_like()
    L = y.index[70]
    t = L + pd.DateOffset(months=4)
    assert abs(slevel_median(y[y.index <= L], t) / y.loc[t] - 1) < 0.05


def test_calibration_sets_width_not_level():
    # residuals all strongly positive (the model under-forecast a ramp): the median must stay the point forecast
    res = np.full(30, 1.0) + np.linspace(-0.2, 0.2, 30)
    q = weighted_conformal(100.0, res, np.arange(30, dtype=float), half_life=6)
    assert q[QUANTILES.index(0.5)] == pytest.approx(100.0)
    assert q[0] < 100.0 < q[-1]  # still a spread around it
