import numpy as np
import pytest

from invopt.portfolio import PRODUCTS, SHOCKS, WORLDS, WorldParams, generate


def test_catalogue_shape():
    hotels = [p for p in PRODUCTS if p["kind"] == "hotel"]
    flights = [p for p in PRODUCTS if p["kind"] == "flight"]
    assert len(hotels) == 24 and len(flights) == 4
    assert {p["region"] for p in PRODUCTS} == {"Middle East", "SE Asia", "Europe", "Indian Ocean", "India"}
    for p in PRODUCTS:
        assert len(p["season"]) == 12 and p["price_inr"] > 0 and 0 < p["early_share"] < 1


def test_means_match_base():
    cells = generate(WorldParams(), n_scen=20000, seed=1)
    assert cells.late.shape == (28 * 13, 20000)
    mean = (cells.late + cells.early).mean(axis=1)
    expected = cells.meta["mean_demand"].to_numpy()
    np.testing.assert_allclose(mean, expected, rtol=0.03)


def test_shock_scales_region():
    base = generate(WorldParams(), n_scen=20000, seed=2)
    shocked = generate(WorldParams(shock="middle_east_disruption"), n_scen=20000, seed=2)
    me = (base.meta["region"] == "Middle East").to_numpy()
    b = (base.late + base.early).mean(axis=1)
    s = (shocked.late + shocked.early).mean(axis=1)
    np.testing.assert_allclose(s[me], 0.45 * b[me], rtol=0.03)
    np.testing.assert_allclose(s[~me], b[~me], rtol=0.03)


def test_seed_reproducible():
    a = generate(WorldParams(), n_scen=50, seed=7)
    b = generate(WorldParams(), n_scen=50, seed=7)
    c = generate(WorldParams(), n_scen=50, seed=8)
    np.testing.assert_array_equal(a.late, b.late)
    np.testing.assert_array_equal(a.dyn_cap, b.dyn_cap)
    assert not np.array_equal(a.late, c.late)


def test_region_correlation_positive():
    cells = generate(WorldParams(), n_scen=4000, seed=3)
    d = (cells.late + cells.early) / cells.meta["mean_demand"].to_numpy()[:, None]
    week0 = (cells.meta["week_start"] == cells.meta["week_start"].min()).to_numpy()
    reg = cells.meta["region"].to_numpy()[week0]
    corr = np.corrcoef(d[week0])
    same = corr[(reg[:, None] == reg[None, :]) & ~np.eye(len(reg), dtype=bool)]
    diff = corr[reg[:, None] != reg[None, :]]
    assert same.mean() > diff.mean() + 0.1


def test_worlds_and_shocks_defined():
    assert {"base", "demand -20%", "demand +20%", "stronger seasons", "higher correlation",
            "later bookings", "more volatile"} == set(WORLDS)
    assert {"middle_east_disruption", "india_airline_collapse", "rupee_slide"} == set(SHOCKS)
    for name in SHOCKS:
        cells = generate(WorldParams(shock=name), n_scen=20, seed=1)
        cells.validate()


def test_market_tightens_when_demand_high():
    cells = generate(WorldParams(), n_scen=4000, seed=4)
    ratio = (cells.late + cells.early) / cells.meta["mean_demand"].to_numpy()[:, None]
    cap_rel = cells.dyn_cap / cells.meta["mean_demand"].to_numpy()[:, None]
    assert cap_rel[ratio >= 1.6].max() == pytest.approx(0.0)
    assert cap_rel[ratio <= 0.6].min() == pytest.approx(1.0)
