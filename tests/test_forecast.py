import numpy as np
import pandas as pd
import pytest

from invopt.forecast import (QUANTILES, QuantileForecaster, build_features, coverage, pinball_loss, wape)


def test_quantiles_monotone_and_calibrated():
    rng = np.random.default_rng(0)
    x = rng.uniform(5, 50, size=800)
    X = pd.DataFrame({"x": x, "trail28": np.full(800, 30.0)})
    y = 2 * x + rng.normal(0, 1, size=800)
    model = QuantileForecaster().fit(X.iloc[:600], y[:600])
    q = model.predict(X.iloc[600:])
    assert q.shape == (200, len(QUANTILES))
    assert np.all(np.diff(q, axis=1) >= -1e-9)
    assert 0.72 <= coverage(y[600:], q) <= 0.88


def test_small_sample_fallback():
    rng = np.random.default_rng(1)
    X = pd.DataFrame({"on_hand": rng.uniform(0, 10, 30), "trail28": rng.uniform(20, 40, 30)})
    y = rng.poisson(30, 30).astype(float)
    q = QuantileForecaster().fit(X, y).predict(X)
    assert np.all(np.isfinite(q)) and np.all(q >= 0)
    assert np.all(np.diff(q, axis=1) >= -1e-9)


def _panel():
    idx = pd.date_range("2016-01-01", "2016-12-31", freq="D", name="night")
    rng = np.random.default_rng(2)
    return pd.DataFrame({"final": rng.poisson(30, len(idx)).astype(float)}, index=idx)


def test_features_ignore_future():
    panel = _panel()
    asof = pd.Timestamp("2016-09-01")
    nights = pd.date_range("2016-10-27", periods=28, freq="D")
    on_hand = pd.Series(5.0, index=nights)
    f1 = build_features(panel, nights, on_hand, asof)
    altered = panel.copy()
    altered.loc[altered.index >= asof, "final"] *= 7
    f2 = build_features(altered, nights, on_hand, asof)
    pd.testing.assert_frame_equal(f1, f2)
    assert list(f1.columns) == ["on_hand", "ly_final", "trail28"] + [f"dow_{i}" for i in range(7)] + ["woy_sin", "woy_cos"]
    assert np.isfinite(f1.to_numpy()).all()


def test_features_last_year_and_trailing():
    panel = _panel()
    asof = pd.Timestamp("2016-09-01")
    nights = pd.DatetimeIndex([pd.Timestamp("2016-08-01") + pd.Timedelta(days=364)])  # needs ly = 2016-08-01 (< asof)
    f = build_features(panel, nights, pd.Series(3.0, index=nights), asof)
    assert f["ly_final"].iloc[0] == panel.loc["2016-08-01", "final"]
    assert f["trail28"].iloc[0] == pytest.approx(panel.loc["2016-08-04":"2016-08-31", "final"].mean())


def test_metrics():
    y = np.array([10.0, 20.0])
    q = np.tile(np.array([5, 6, 8, 10, 12, 14, 15], dtype=float), (2, 1))
    assert wape(y, q[:, 3]) == pytest.approx(10 / 30)
    assert coverage(y, q) == pytest.approx(0.5)
    assert pinball_loss(y, q) > 0
