"""Turn quantile forecasts into joint demand scenarios.

`correlated_uniforms` draws one uniform per (cell, scenario) from a Gaussian
copula with a common factor (whole batch moves together) and a group factor
(cells of the same contract group, e.g. nights of one week, move together).
`sample_from_quantiles` maps those uniforms through each cell's forecast
quantile function (piecewise linear, linear tails, never negative).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import ndtr, ndtri

from invopt.forecast import QUANTILES

_QS = np.asarray(QUANTILES)
DEFAULT_RHOS = (0.3, 0.4)


def sample_from_quantiles(q: np.ndarray, u: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    u = np.asarray(u, dtype=float)
    k = np.clip(np.searchsorted(_QS, u, side="right") - 1, 0, len(_QS) - 2)
    x0, x1 = _QS[k], _QS[k + 1]
    rows = np.arange(q.shape[0])[:, None]
    y0, y1 = q[rows, k], q[rows, k + 1]
    slope = np.where(x1 > x0, (y1 - y0) / (x1 - x0), 0.0)
    return np.clip(y0 + slope * (u - x0), 0.0, None)


def correlated_uniforms(group: np.ndarray, S: int, rho_common: float, rho_group: float,
                        rng: np.random.Generator) -> np.ndarray:
    if rho_common < 0 or rho_group < 0 or rho_common + rho_group > 1:
        raise ValueError("need rho_common, rho_group >= 0 and rho_common + rho_group <= 1")
    group = np.asarray(group)
    _, gidx = np.unique(group, return_inverse=True)
    n_g = gidx.max() + 1 if len(gidx) else 0
    z_c = rng.standard_normal(S)[None, :]
    z_g = rng.standard_normal((n_g, S))[gidx]
    eps = rng.standard_normal((len(group), S))
    x = np.sqrt(rho_common) * z_c + np.sqrt(rho_group) * z_g + np.sqrt(1.0 - rho_common - rho_group) * eps
    return ndtr(x)


def estimate_rhos(pit_residuals: pd.DataFrame, min_obs: int = 30) -> tuple[float, float]:
    """Method-of-moments copula correlations from past forecast PIT values.

    `pit_residuals` has columns batch, group, pit (the realised value's position in its
    forecast distribution, in (0, 1)). Pairs in the same batch and group estimate
    rho_common + rho_group; pairs in the same batch but different groups estimate rho_common.
    """
    df = pit_residuals.dropna(subset=["pit"])
    if len(df) < min_obs or df["batch"].nunique() < 3:
        return DEFAULT_RHOS
    z = ndtri(np.clip(df["pit"].to_numpy(float), 1e-4, 1 - 1e-4))
    z = (z - z.mean()) / (z.std() or 1.0)
    df = df.assign(z=z)
    same_sum = same_n = batch_sum = batch_n = 0.0
    for _, b in df.groupby("batch"):
        zb = b["z"].to_numpy()
        batch_sum += zb.sum() ** 2 - (zb ** 2).sum()
        batch_n += len(zb) * (len(zb) - 1)
        for _, gdf in b.groupby("group"):
            zg = gdf["z"].to_numpy()
            same_sum += zg.sum() ** 2 - (zg ** 2).sum()
            same_n += len(zg) * (len(zg) - 1)
    if same_n == 0 or batch_n - same_n <= 0:
        return DEFAULT_RHOS
    within = same_sum / same_n
    across = (batch_sum - same_sum) / (batch_n - same_n)
    rc = float(np.clip(across, 0.0, 0.9))
    rg = float(np.clip(within - rc, 0.0, 0.95 - rc))
    return rc, rg
