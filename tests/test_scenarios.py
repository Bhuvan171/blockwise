import numpy as np
import pandas as pd
import pytest
from scipy.special import ndtri

from invopt.forecast import QUANTILES
from invopt.scenarios import correlated_uniforms, estimate_rhos, sample_from_quantiles

Q = np.array([[5, 6, 8, 10, 12, 14, 15], [0, 0, 1, 2, 3, 5, 6]], dtype=float)


def test_sample_hits_quantiles():
    out = sample_from_quantiles(Q, np.full((2, 3), 0.5))
    assert np.allclose(out, Q[:, [3]])
    out = sample_from_quantiles(Q, np.full((2, 1), 0.9))
    assert np.allclose(out[:, 0], Q[:, QUANTILES.index(0.9)])


def test_sample_tails_and_nonnegative():
    out = sample_from_quantiles(Q, np.array([[0.001, 0.999], [0.001, 0.999]]))
    assert np.all(out >= 0)
    assert out[0, 0] < 5 and out[0, 1] > 15  # linear extrapolation beyond the 5% / 95% points


def test_copula_correlation():
    rng = np.random.default_rng(0)
    group = np.repeat(np.arange(4), 10)
    u = correlated_uniforms(group, 20000, 0.3, 0.4, rng)
    z = ndtri(u)
    corr = np.corrcoef(z)
    same = corr[group[:, None] == group[None, :]]
    same = same[same < 0.999]  # drop the diagonal
    diff = corr[group[:, None] != group[None, :]]
    assert same.mean() == pytest.approx(0.7, abs=0.03)
    assert diff.mean() == pytest.approx(0.3, abs=0.03)


def test_estimate_rhos_recovers_truth():
    rng = np.random.default_rng(1)
    rows = []
    for batch in range(60):
        group = np.repeat(np.arange(4), 7)
        u = correlated_uniforms(group, 1, 0.25, 0.35, rng)[:, 0]
        rows.append(pd.DataFrame({"batch": batch, "group": group, "pit": u}))
    rc, rg = estimate_rhos(pd.concat(rows))
    assert rc == pytest.approx(0.25, abs=0.1)
    assert rg == pytest.approx(0.35, abs=0.1)


def test_estimate_rhos_defaults_when_sparse():
    df = pd.DataFrame({"batch": [0] * 10, "group": [0] * 10, "pit": np.linspace(0.1, 0.9, 10)})
    assert estimate_rhos(df) == (0.3, 0.4)
