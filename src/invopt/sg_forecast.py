"""Monthly forecasting for the Singapore replay: point forecasts + shift-aware calibration.

Point forecasts (4 months beyond the last published month):
  snaive   same month last year x recent year-on-year trend, in log space (floors at 1)
  chronos2 Chronos-2 zero-shot median (Amazon, Apache-2.0)

Uncertainty: weighted (non-exchangeable) split conformal on log residuals.
Barber, Candes, Ramdas & Tibshirani (2023), "Conformal prediction beyond exchangeability":
recent forecast errors get exponentially more weight (half-life in months), so intervals
widen within months of a shock (COVID) and tighten again in calm periods. The method is
scale-free, so a 99.9% collapse does not need hundreds of small update steps.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from invopt.forecast import QUANTILES

QS = np.asarray(QUANTILES)
PRIOR_LOG = np.array([-1.0, -0.6, -0.25, 0.0, 0.25, 0.6, 1.0])  # wide default spread before any errors are seen
MIN_RESIDUALS = 12


def snaive_median(hist: pd.Series, target: pd.Timestamp) -> float:
    """Same month last year, scaled by the year-on-year change of the last 3 published months."""
    y = np.log(np.maximum(hist.astype(float), 1.0))
    base_t = pd.Timestamp(target) - pd.DateOffset(months=12)
    base = float(y.loc[base_t]) if base_t in y.index else float(y.iloc[-12:].mean())
    recent = y.iloc[-3:]
    prior = y.reindex(recent.index - pd.DateOffset(months=12))
    trend = float((recent.to_numpy() - prior.to_numpy()).mean()) if prior.notna().all() else 0.0
    return float(np.exp(base + trend))


def seasonal_profile(hist: pd.Series) -> np.ndarray:
    """Month-of-year factors: median over complete past years of (month / that year's mean).

    The median across years ignores one-off years (e.g. 2020-21), so a collapse does not distort the profile.
    """
    y = hist.astype(float).clip(lower=1.0)
    ratios = []
    for _, g in y.groupby(y.index.year):
        if len(g) == 12:
            ratios.append((g / g.mean()).to_numpy()[np.argsort(g.index.month)])
    if not ratios:
        return np.ones(12)
    prof = np.median(np.vstack(ratios), axis=0)
    return prof / prof.mean()


def slevel_median(hist: pd.Series, target: pd.Timestamp) -> float:
    """Seasonal level: the latest deseasonalised level (last 3 published months) x the target month's factor.

    Unlike same-month-last-year x trend, it never multiplies one abnormal year by another, so it stays
    sane through a collapse and the recovery after it.
    """
    prof = seasonal_profile(hist)
    recent = hist.astype(float).clip(lower=1.0).iloc[-3:]
    level = float(np.mean(recent.to_numpy() / prof[recent.index.month.to_numpy() - 1]))
    return level * float(prof[pd.Timestamp(target).month - 1])


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w) - 0.5 * w  # midpoint rule
    return float(np.interp(q, cum / w.sum(), v))


def weighted_conformal(median: float, residuals: np.ndarray, ages: np.ndarray, half_life: float = 6.0) -> np.ndarray:
    """Quantiles = median x exp(weighted quantile of past log residuals); prior spread if too few."""
    median = max(float(median), 1e-9)
    residuals = np.asarray(residuals, float)
    if len(residuals) < MIN_RESIDUALS:
        return median * np.exp(PRIOR_LOG)
    w = 0.5 ** (np.asarray(ages, float) / half_life)
    q = np.array([_weighted_quantile(residuals, w, t) for t in QS])
    return np.sort(median * np.exp(q))


def chronos_monthly_medians(hist: pd.DataFrame, cols: list[str], steps: int) -> dict[str, float]:
    """Chronos-2 median `steps` months after the last row of `hist`, for each column."""
    from invopt.chronos_fc import _pipe

    frames = [pd.DataFrame({"item_id": c, "timestamp": hist.index, "target": hist[c].astype(float).to_numpy()})
              for c in cols]
    pred = _pipe().predict_df(pd.concat(frames, ignore_index=True), prediction_length=steps,
                              quantile_levels=[0.5], id_column="item_id")
    last = pred.sort_values("timestamp").groupby("item_id").tail(1).set_index("item_id")["0.5"]
    return {c: max(float(last[c]), 1e-9) for c in cols}
