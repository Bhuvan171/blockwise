import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from invopt.sg_data import TIERS, load_panel, parse_singstat

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
A, H = RAW / "singstat_M550001.json", RAW / "singstat_M550081.json"
pytestmark = pytest.mark.skipif(not (A.exists() and H.exists()), reason="run scripts/fetch_singstat.sh first")


def test_panel_shape_and_known_values():
    p = load_panel(A, H)
    assert p.index[0] == pd.Timestamp("2008-01-01") and p.index[-1] >= pd.Timestamp("2026-09-01")  # later fetches add months
    assert len(p) >= 225 and p.index.freqstr.startswith("MS")
    assert p.loc["2019-05-01", "india_arrivals"] == 182727
    assert p.loc["2019-02-01", "india_arrivals"] == 88926
    for t in TIERS:
        assert (p[f"rate_{t}"].dropna() > 0).all() and p[f"occ_{t}"].dropna().between(0, 100).all()
    assert p.attrs["missing"] == {} or all(v >= 0 for v in p.attrs["missing"].values())


def test_parse_marks_missing(tmp_path):
    d = {"Data": {"row": [{"rowText": "India", "columns": [{"key": "2020 Jan", "value": "5"},
                                                            {"key": "2020 Feb", "value": "na"}]}]}}
    f = tmp_path / "t.json"
    f.write_text(json.dumps(d))
    s = parse_singstat(f)["India"]
    assert s.loc["2020-01-01"] == 5 and np.isnan(s.loc["2020-02-01"])
