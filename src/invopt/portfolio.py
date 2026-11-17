"""A synthetic, TBO-like portfolio: Indian outbound + domestic B2B demand, Jan-Mar 2027.

FULLY SYNTHETIC. Every number below is a labelled assumption chosen to look like
a B2B distributor's book (weekly room-nights / seats it could commit to, INR
prices per night or seat, monthly seasonality for Indian travellers). They are
not TBO data. The point of this world is to exercise the planner on a realistic
portfolio and to test it in worlds it was NOT planned in (`WORLDS`, `SHOCKS`).

Demand per (product, week, scenario) = Poisson( mean * lognormal factor ), where
the log factor = global + region + idiosyncratic parts (so destinations in one
region move together). The market for buy-as-needed units tightens when demand
is high: cap = mean * clip(1.6 - demand/mean, 0, 1).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from invopt.economics import Cells

# monthly multipliers Jan..Dec (assumption: Indian outbound/domestic seasonality)
_WINTER_GULF = [1.25, 1.2, 1.1, 0.9, 0.7, 0.6, 0.6, 0.65, 0.8, 1.0, 1.15, 1.35]  # Gulf peaks in the cool months
_THAI = [1.2, 1.15, 1.05, 1.0, 0.8, 0.75, 0.8, 0.8, 0.75, 0.95, 1.1, 1.25]
_BEACH_ASIA = [1.3, 1.25, 1.1, 0.95, 0.6, 0.55, 0.6, 0.6, 0.55, 0.8, 1.1, 1.35]  # Andaman-sea dry season
_FLAT = [1.0, 1.05, 1.0, 0.95, 1.05, 1.1, 1.0, 0.95, 0.9, 0.95, 1.0, 1.1]
_BALI = [0.9, 0.8, 0.85, 0.95, 1.0, 1.15, 1.3, 1.3, 1.1, 1.0, 0.9, 1.2]  # Bali dry season peaks mid-year
_EUROPE = [0.6, 0.65, 0.8, 0.95, 1.1, 1.3, 1.4, 1.3, 1.0, 0.9, 0.8, 0.95]  # Indian summer-holiday travel
_MALDIVES = [1.35, 1.3, 1.2, 1.0, 0.7, 0.6, 0.65, 0.7, 0.65, 0.85, 1.1, 1.4]
_GOA = [1.3, 1.05, 0.9, 0.75, 0.6, 0.45, 0.45, 0.5, 0.6, 0.9, 1.2, 1.6]  # Dec-Jan peak, monsoon trough
_RAJASTHAN = [1.3, 1.2, 1.0, 0.75, 0.5, 0.45, 0.55, 0.6, 0.7, 1.0, 1.2, 1.35]


def _hotel(city, region, season, star, units, price, early, disp):
    return {"id": f"{city.lower().replace(' ', '_')}_{star}s", "kind": "hotel", "name": f"{city} {star}★",
            "region": region, "base_weekly_units": units, "price_inr": price, "season": season,
            "early_share": early, "dispersion": disp}


# (city, region, season, (5★ units/wk, 5★ INR/night), (4★ units/wk, 4★ INR/night), early share, dispersion)
_CITIES = [
    ("Dubai", "Middle East", _WINTER_GULF, (1200, 16000), (1800, 8500), 0.75, 0.22),
    ("Abu Dhabi", "Middle East", _WINTER_GULF, (400, 14000), (600, 7500), 0.75, 0.25),
    ("Bangkok", "SE Asia", _THAI, (700, 9000), (1400, 4500), 0.70, 0.22),
    ("Phuket", "SE Asia", _BEACH_ASIA, (500, 13000), (800, 6000), 0.78, 0.25),
    ("Singapore", "SE Asia", _FLAT, (600, 20000), (900, 11000), 0.72, 0.18),
    ("Bali", "SE Asia", _BALI, (700, 14000), (1000, 6500), 0.80, 0.25),
    ("Kuala Lumpur", "SE Asia", _FLAT, (300, 8000), (600, 4000), 0.70, 0.25),
    ("London", "Europe", _EUROPE, (350, 32000), (600, 16000), 0.85, 0.20),
    ("Paris", "Europe", _EUROPE, (300, 34000), (500, 15000), 0.85, 0.22),
    ("Maldives", "Indian Ocean", _MALDIVES, (250, 45000), (300, 22000), 0.85, 0.30),
    ("Goa", "India", _GOA, (900, 15000), (1400, 7000), 0.60, 0.28),
    ("Jaipur", "India", _RAJASTHAN, (500, 12000), (800, 5500), 0.62, 0.28),
]

PRODUCTS: list[dict] = []
for city, region, season, five, four, early, disp in _CITIES:
    PRODUCTS.append(_hotel(city, region, season, 5, five[0], five[1], early, disp))
    PRODUCTS.append(_hotel(city, region, season, 4, four[0], four[1], early, disp))
# seat blocks (series / group fares), INR per seat one way; seasonality follows the destination
PRODUCTS += [
    {"id": "del_dxb", "kind": "flight", "name": "DEL–DXB seats", "region": "Middle East", "base_weekly_units": 1500,
     "price_inr": 14000, "season": _WINTER_GULF, "early_share": 0.75, "dispersion": 0.20},
    {"id": "bom_dxb", "kind": "flight", "name": "BOM–DXB seats", "region": "Middle East", "base_weekly_units": 1800,
     "price_inr": 12500, "season": _WINTER_GULF, "early_share": 0.75, "dispersion": 0.20},
    {"id": "del_bkk", "kind": "flight", "name": "DEL–BKK seats", "region": "SE Asia", "base_weekly_units": 900,
     "price_inr": 16000, "season": _THAI, "early_share": 0.72, "dispersion": 0.22},
    {"id": "bom_sin", "kind": "flight", "name": "BOM–SIN seats", "region": "SE Asia", "base_weekly_units": 700,
     "price_inr": 18000, "season": _FLAT, "early_share": 0.72, "dispersion": 0.20},
]

REGIONS = ["Middle East", "SE Asia", "Europe", "Indian Ocean", "India"]

# event uplifts (assumed windows, illustrative)
EVENTS = [
    {"name": "Gulf winter festival season (assumed: first 4 weeks of Jan)", "region": "Middle East",
     "weeks": [0, 1, 2, 3], "uplift": 1.15},
    {"name": "Lunar New Year week (assumed: week of 8 Feb 2027)", "region": "SE Asia", "weeks": [5], "uplift": 1.20},
    {"name": "Wedding season (assumed: Jan–Feb weekends)", "region": "India", "weeks": [1, 3, 5, 7], "uplift": 1.10},
]


@dataclass(frozen=True)
class WorldParams:
    level: float = 1.0  # overall demand multiplier
    season_amp: float = 1.0  # 1 + amp * (season - 1)
    rho_global: float = 0.15  # share of log-variance common to every product
    rho_region: float = 0.35  # share common within a region
    early_mult: float = 1.0  # multiplies each product's early-booking share
    dispersion_mult: float = 1.0
    price_mult: float = 1.0
    shock: str | None = None


def _shock_middle_east(meta):  # demand x0.45 in the Middle East; fewer flights operating to the Gulf
    me = (meta["region"] == "Middle East").to_numpy()
    flight = (meta["kind"] == "flight").to_numpy()
    return np.where(me, 0.45, 1.0), np.where(me & flight, 0.5, 1.0)


def _shock_airline(meta):  # a major Indian airline stops flying: seat market dries up, outbound demand dips
    flight = (meta["kind"] == "flight").to_numpy()
    intl = (meta["region"] != "India").to_numpy()
    return np.where(intl & ~flight, 0.85, 1.0), np.where(flight, 0.3, 1.0)


def _shock_rupee(meta):  # rupee slides: international trips cost more, demand falls
    intl = (meta["region"] != "India").to_numpy()
    return np.where(intl, 0.88, 1.0), np.ones(len(meta))


SHOCKS = {
    "middle_east_disruption": _shock_middle_east,
    "india_airline_collapse": _shock_airline,
    "rupee_slide": _shock_rupee,
}

SHOCK_LABELS = {
    "middle_east_disruption": "Middle East disruption: Gulf demand −55%, Gulf seat supply halved",
    "india_airline_collapse": "Indian airline collapse: seat market −70%, international hotel demand −15%",
    "rupee_slide": "Rupee slide: international demand −12%",
}

_BASE = WorldParams()
WORLDS = {
    "base": _BASE,
    "demand -20%": replace(_BASE, level=0.8),
    "demand +20%": replace(_BASE, level=1.2),
    "stronger seasons": replace(_BASE, season_amp=1.5),
    "higher correlation": replace(_BASE, rho_global=0.35, rho_region=0.45),
    "later bookings": replace(_BASE, early_mult=0.75),
    "more volatile": replace(_BASE, dispersion_mult=1.6),
}


def catalogue_meta(start: str = "2027-01-04", weeks: int = 13, world: WorldParams = _BASE) -> pd.DataFrame:
    """One row per product-week with the world's mean demand (before any shock)."""
    weeks_idx = pd.date_range(start, periods=weeks, freq="7D")
    rows = []
    for p in PRODUCTS:
        for w, ws in enumerate(weeks_idx):
            month = (ws + pd.Timedelta(days=3)).month
            season = 1.0 + world.season_amp * (p["season"][month - 1] - 1.0)
            uplift = np.prod([e["uplift"] for e in EVENTS if e["region"] == p["region"] and w in e["weeks"]] or [1.0])
            rows.append({"product_id": p["id"], "name": p["name"], "kind": p["kind"], "region": p["region"],
                         "week": w, "week_start": ws, "price_inr": p["price_inr"] * world.price_mult,
                         "early_share": min(p["early_share"] * world.early_mult, 0.98),
                         "dispersion": p["dispersion"] * world.dispersion_mult,
                         "mean_demand": p["base_weekly_units"] * max(season, 0.05) * world.level * uplift})
    return pd.DataFrame(rows)


def generate(world: WorldParams, n_scen: int, seed: int, start: str = "2027-01-04", weeks: int = 13) -> Cells:
    meta = catalogue_meta(start, weeks, world)
    demand_mult, cap_mult = (np.ones(len(meta)), np.ones(len(meta)))
    if world.shock is not None:
        demand_mult, cap_mult = SHOCKS[world.shock](meta)
    meta["mean_demand"] = meta["mean_demand"] * demand_mult
    C, S = len(meta), n_scen
    rng = np.random.default_rng(seed)
    rg, rr = world.rho_global, world.rho_region
    if rg < 0 or rr < 0 or rg + rr > 1:
        raise ValueError("rho_global + rho_region must be in [0, 1]")
    region_id = meta["region"].map({r: i for i, r in enumerate(REGIONS)}).to_numpy()
    z_g = rng.standard_normal(S)[None, :]
    z_r = rng.standard_normal((len(REGIONS), S))[region_id]
    eps = rng.standard_normal((C, S))
    sigma = meta["dispersion"].to_numpy()[:, None]
    log_f = sigma * (np.sqrt(rg) * z_g + np.sqrt(rr) * z_r + np.sqrt(1 - rg - rr) * eps) - sigma ** 2 / 2
    mean = meta["mean_demand"].to_numpy()[:, None]
    demand = rng.poisson(mean * np.exp(log_f)).astype(float)
    early = rng.binomial(demand.astype(np.int64), meta["early_share"].to_numpy()[:, None]).astype(float)
    dyn_cap = mean * np.clip(1.6 - demand / mean, 0.0, 1.0) * cap_mult[:, None]
    price = meta["price_inr"].to_numpy(dtype=float)
    return Cells(group=np.arange(C), price=price, ref_rate=price.copy(), late=demand - early, early=early,
                 dyn_cap=dyn_cap, meta=meta).validate()
