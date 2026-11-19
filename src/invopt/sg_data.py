"""Official Singapore statistics (SingStat Table Builder, Singapore Open Data Licence).

M550001: International Visitor Arrivals by Place of Residence, monthly. We use row "India".
M550081: Hotel Statistics, monthly. Average room rate (SGD) and average occupancy (%) by
         hotel size band (small / medium / large), plus all hotels.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TIERS = ("small", "medium", "large")
_HOTEL_ROWS = {
    "rate_all": "Average Room Rate", "occ_all": "Average Hotel Occupancy Rate",
    "rate_small": "Average Room Rate - Small", "rate_medium": "Average Room Rate - Medium",
    "rate_large": "Average Room Rate - Large", "occ_small": "Average Occupancy Rate - Small",
    "occ_medium": "Average Occupancy Rate - Medium", "occ_large": "Average Occupancy Rate - Large",
}


def parse_singstat(path: str | Path) -> dict[str, pd.Series]:
    """Every row of a SingStat table as a monthly float series ('na', '-', '' -> NaN)."""
    rows = json.loads(Path(path).read_text())["Data"]["row"]
    out = {}
    for r in rows:
        idx = pd.to_datetime([c["key"] for c in r["columns"]], format="%Y %b")
        vals = pd.to_numeric(pd.Series([c["value"] for c in r["columns"]]), errors="coerce").to_numpy()
        out[r["rowText"]] = pd.Series(vals, index=idx, name=r["rowText"]).sort_index()
    return out


def load_panel(arrivals_path: str | Path, hotel_path: str | Path) -> pd.DataFrame:
    """Monthly panel (month-start index) with India arrivals and hotel rates/occupancy by size band."""
    arr = parse_singstat(arrivals_path)
    hot = parse_singstat(hotel_path)
    cols = {"india_arrivals": arr["India"]}
    for col, label in _HOTEL_ROWS.items():
        cols[col] = hot[label]
    p = pd.DataFrame(cols)
    p = p.asfreq("MS")
    p.attrs["missing"] = {c: int(n) for c, n in p.isna().sum().items() if n > 0}
    p.attrs["source"] = "SingStat Table Builder M550001 (India row) and M550081; Singapore Open Data Licence"
    return p


def tier_series(p: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per tier: rate and occupancy columns renamed to a common shape."""
    return {t: p[[f"rate_{t}", f"occ_{t}"]].rename(columns={f"rate_{t}": "rate", f"occ_{t}": "occ"}) for t in TIERS}
