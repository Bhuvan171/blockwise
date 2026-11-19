"""Probabilistic forecast of a night's final (net, checked-out) B2B room-nights.

Inputs are only what is known at the decision date `asof`: rooms already on the
books for that night (`on_hand`), the same night last year, and the trailing
28-night level. One linear quantile regression per quantile (HiGHS solver);
outputs are sorted per row (no quantile crossing) and clipped at 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import QuantileRegressor

QUANTILES: tuple[float, ...] = (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)
FEATURES = ["on_hand", "ly_final", "trail28"] + [f"dow_{i}" for i in range(7)] + ["woy_sin", "woy_cos"]
MIN_ROWS = 60


def build_features(panel_hist: pd.DataFrame, nights: pd.DatetimeIndex, on_hand: pd.Series,
                   asof: pd.Timestamp) -> pd.DataFrame:
    """Features for `nights`, reading `panel_hist` only for nights strictly before `asof`."""
    asof = pd.Timestamp(asof)
    nights = pd.DatetimeIndex(nights)
    known = panel_hist.loc[panel_hist.index < asof, "final"].astype(float)
    window = known[known.index >= asof - pd.Timedelta(days=28)]
    trail28 = float(window.mean()) if len(window) else (float(known.mean()) if len(known) else 0.0)
    ly_dates = nights - pd.Timedelta(days=364)
    ly = known.reindex(ly_dates).to_numpy()
    ly = np.where(np.isfinite(ly), ly, trail28)
    oh = on_hand.reindex(nights).fillna(0.0).to_numpy(dtype=float)
    out = pd.DataFrame({"on_hand": oh, "ly_final": ly, "trail28": np.full(len(nights), trail28)}, index=nights)
    dow = nights.day_of_week.to_numpy()
    for i in range(7):
        out[f"dow_{i}"] = (dow == i).astype(float)
    angle = 2 * np.pi * (nights.day_of_year.to_numpy() - 1) / 365.25
    out["woy_sin"], out["woy_cos"] = np.sin(angle), np.cos(angle)
    return out[FEATURES]


class QuantileForecaster:
    def __init__(self, alpha_reg: float = 0.0):
        self.alpha_reg = alpha_reg
        self.models: list[QuantileRegressor] | None = None
        self.ratio_q: np.ndarray | None = None
        self.columns: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "QuantileForecaster":
        X = pd.DataFrame(X)
        y = np.asarray(y, dtype=float)
        self.columns = list(X.columns)
        if len(y) < MIN_ROWS:
            base = self._scale(X)
            self.ratio_q = np.quantile(y / base, QUANTILES)
            self.models = None
            return self
        self.models = [QuantileRegressor(quantile=q, alpha=self.alpha_reg, solver="highs").fit(X.to_numpy(), y)
                       for q in QUANTILES]
        self.ratio_q = None
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = pd.DataFrame(X)[self.columns]
        if self.models is None:
            q = self._scale(X)[:, None] * self.ratio_q[None, :]
        else:
            q = np.column_stack([m.predict(X.to_numpy()) for m in self.models])
        return np.clip(np.sort(q, axis=1), 0.0, None)

    @staticmethod
    def _scale(X: pd.DataFrame) -> np.ndarray:
        if "trail28" in X:
            return np.maximum(X["trail28"].to_numpy(dtype=float), 1.0)
        return np.ones(len(X))


QuantileForecaster.feature_set = "base"


class GBMQuantileForecaster:
    """Gradient-boosted trees, one model per quantile (sklearn HistGradientBoosting, quantile loss).

    Captures non-linear booking-pace effects that the linear model can't (e.g. pickup that
    depends on both rooms on the books and how far ahead the night is).
    """

    feature_set = "pace"

    def __init__(self, max_iter: int = 250, learning_rate: float = 0.05, max_leaf_nodes: int = 15,
                 min_samples_leaf: int = 20, l2_regularization: float = 1.0, random_state: int = 0):
        self.params = dict(max_iter=max_iter, learning_rate=learning_rate, max_leaf_nodes=max_leaf_nodes,
                           min_samples_leaf=min_samples_leaf, l2_regularization=l2_regularization,
                           random_state=random_state)
        self.models = None
        self.fallback: QuantileForecaster | None = None
        self.columns: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "GBMQuantileForecaster":
        from sklearn.ensemble import HistGradientBoostingRegressor

        X = pd.DataFrame(X)
        y = np.asarray(y, dtype=float)
        self.columns = list(X.columns)
        if len(y) < MIN_ROWS:
            self.fallback = QuantileForecaster().fit(X, y)
            self.models = None
            return self
        self.models = [HistGradientBoostingRegressor(loss="quantile", quantile=q, **self.params).fit(X.to_numpy(), y)
                       for q in QUANTILES]
        self.fallback = None
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = pd.DataFrame(X)[self.columns]
        if self.models is None:
            return self.fallback.predict(X)
        q = np.column_stack([m.predict(X.to_numpy()) for m in self.models])
        return np.clip(np.sort(q, axis=1), 0.0, None)


class ConformalWrapper:
    """Rolling split-conformal calibration of every quantile level.

    Fit the base model on the earlier rows, measure on the latest `cal_frac` rows how far
    reality fell from each predicted quantile, shift each quantile by the matching
    empirical quantile of those residuals, then refit the base on all rows. Rows must be in
    time order (they are: one row per past night). Outputs stay sorted and non-negative.
    """

    def __init__(self, base_factory, cal_frac: float = 0.25, min_cal: int = 30):
        self.base_factory = base_factory
        self.cal_frac = cal_frac
        self.min_cal = min_cal
        self.feature_set = getattr(base_factory(), "feature_set", "base")
        self.shift = np.zeros(len(QUANTILES))
        self.base = None

    def _split(self, n: int) -> tuple[slice, slice]:
        n_cal = int(round(n * self.cal_frac))
        return slice(0, n - n_cal), slice(n - n_cal, n)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "ConformalWrapper":
        X = pd.DataFrame(X)
        y = np.asarray(y, dtype=float)
        tr, cal = self._split(len(y))
        self.shift = np.zeros(len(QUANTILES))
        if cal.stop - cal.start >= self.min_cal and tr.stop >= self.min_cal:
            q_cal = self.base_factory().fit(X.iloc[tr], y[tr]).predict(X.iloc[cal])
            resid = y[cal][:, None] - q_cal
            n = len(resid)
            # finite-sample corrected level per quantile, clipped to the observed range
            levels = np.clip(np.ceil((n + 1) * np.asarray(QUANTILES)) / n, 0.0, 1.0)
            self.shift = np.array([np.quantile(resid[:, j], levels[j]) for j in range(len(QUANTILES))])
        self.base = self.base_factory().fit(X, y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        q = self.base.predict(X) + self.shift[None, :]
        return np.clip(np.sort(q, axis=1), 0.0, None)


_REGISTRY = {
    "qr": lambda: QuantileForecaster(),
    "gbm": lambda: GBMQuantileForecaster(),
    "qr_conf": lambda: ConformalWrapper(QuantileForecaster),
    "gbm_conf": lambda: ConformalWrapper(GBMQuantileForecaster),
}
FORECASTERS = tuple(_REGISTRY)


def make_forecaster(name: str):
    if name not in _REGISTRY:
        raise ValueError(f"unknown forecaster {name!r}; choose from {sorted(_REGISTRY)}")
    return _REGISTRY[name]()


def pinball_loss(y: np.ndarray, q: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)[:, None]
    taus = np.asarray(QUANTILES)[None, :]
    diff = y - q
    return float(np.mean(np.maximum(taus * diff, (taus - 1) * diff)))


def coverage(y: np.ndarray, q: np.ndarray, lo: float = 0.1, hi: float = 0.9) -> float:
    y = np.asarray(y, dtype=float)
    i_lo, i_hi = QUANTILES.index(lo), QUANTILES.index(hi)
    return float(np.mean((y >= q[:, i_lo]) & (y <= q[:, i_hi])))


def wape(y: np.ndarray, yhat: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    denom = np.abs(y).sum()
    return float(np.abs(y - np.asarray(yhat, dtype=float)).sum() / denom) if denom > 0 else 0.0
