import numpy as np
import pandas as pd
import pytest

from invopt.forecast import (QUANTILES, ConformalWrapper, GBMQuantileForecaster, QuantileForecaster, coverage,
                             make_forecaster)


def _data(n, seed, noise=2.0):
    rng = np.random.default_rng(seed)
    x = rng.uniform(5, 50, n)
    X = pd.DataFrame({"x": x, "x2": rng.uniform(0, 1, n), "trail28": np.full(n, 30.0)})
    y = 2 * x + rng.normal(0, noise, n)
    return X, y


class TooNarrow:
    """Median is right, spread is 30% of the truth: badly under-covers."""

    feature_set = "base"

    def fit(self, X, y):
        return self

    def predict(self, X):
        from scipy.stats import norm
        z = norm.ppf(QUANTILES)
        return 2 * X["x"].to_numpy()[:, None] + 0.3 * 2.0 * z[None, :]


def test_gbm_accurate_and_ordered():
    from invopt.forecast import wape
    X, y = _data(1200, 0)
    q = GBMQuantileForecaster().fit(X.iloc[:900], y[:900]).predict(X.iloc[900:])
    assert q.shape == (300, len(QUANTILES))
    assert np.all(np.diff(q, axis=1) >= -1e-9) and np.all(q >= 0)
    assert wape(y[900:], q[:, QUANTILES.index(0.5)]) < 0.06


def test_gbm_conformal_calibrated():
    X, y = _data(1600, 0)
    q = make_forecaster("gbm_conf").fit(X.iloc[:1200], y[:1200]).predict(X.iloc[1200:])
    assert 0.74 <= coverage(y[1200:], q) <= 0.88


def test_conformal_fixes_undercoverage():
    X, y = _data(1600, 1)
    base_cov = coverage(y[1200:], TooNarrow().predict(X.iloc[1200:]))
    wrapped = ConformalWrapper(TooNarrow, cal_frac=0.3).fit(X.iloc[:1200], y[:1200])
    q = wrapped.predict(X.iloc[1200:])
    assert base_cov < 0.5
    assert 0.74 <= coverage(y[1200:], q) <= 0.86
    assert np.all(np.diff(q, axis=1) >= -1e-9) and np.all(q >= 0)


def test_conformal_uses_latest_rows_for_calibration():
    X, y = _data(100, 2)
    w = ConformalWrapper(QuantileForecaster, cal_frac=0.25)
    tr, cal = w._split(len(y))
    assert tr.stop == cal.start and cal.stop == 100 and (cal.stop - cal.start) == 25  # time order kept


def test_registry_names():
    for name in ("qr", "qr_conf", "gbm", "gbm_conf"):
        f = make_forecaster(name)
        assert hasattr(f, "fit") and hasattr(f, "predict") and f.feature_set in ("base", "pace")
    assert make_forecaster("qr").feature_set == "base" and make_forecaster("gbm_conf").feature_set == "pace"
    with pytest.raises(ValueError):
        make_forecaster("nope")
