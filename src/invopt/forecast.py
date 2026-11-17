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
