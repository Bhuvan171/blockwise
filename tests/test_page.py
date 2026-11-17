import json
import re

import pytest

from invopt.page import PLACEHOLDER, build_page

SAMPLE = {"budgets_inr": [50000000.0, 100000000.0], "risk_levels": {"Max profit": 0.0}, "cells": {},
          "note": "</script><script>alert(1)</script>"}


@pytest.fixture()
def built(tmp_path):
    src = tmp_path / "results.json"
    src.write_text(json.dumps(SAMPLE))
    out = build_page(src, tmp_path / "page.html")
    return out.read_text()


def test_page_embeds_results(built):
    assert "50000000" in built and "100000000" in built
    assert PLACEHOLDER not in built


def test_page_escapes_script_breakout(built):
    # the embedded JSON must not be able to close the <script> element early
    assert "</script><script>alert(1)" not in built


def test_page_size(built):
    assert len(built.encode()) < 3_000_000


def test_page_offline_safe(built):
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', built)
    assert all(s.startswith("https://cdnjs.cloudflare.com/") for s in srcs)
    assert "http://" not in built


def test_standalone_has_document_skeleton(tmp_path):
    src = tmp_path / "results.json"
    src.write_text(json.dumps(SAMPLE))
    html = build_page(src, tmp_path / "s.html", standalone=True).read_text()
    assert html.lower().startswith("<!doctype html>")
    assert 'name="viewport"' in html and "<body>" in html and html.rstrip().endswith("</html>")


def _expand(data, lines):
    """Reference for the page's JS: rebuild row objects from the columnar form."""
    out = []
    for i, pi in enumerate(lines["product"]):
        prod = data["line_products"][pi]
        out.append({"product": prod["name"], "kind": prod["kind"], "region": prod["region"],
                    "week_start": data["line_weeks"][lines["week"][i]], "hard": lines["hard"][i],
                    "soft": lines["soft"][i], "prepaid_inr": lines["prepaid"][i], "exp_profit_inr": lines["profit"][i],
                    "p_line_loss": lines["p_loss"][i], "hard_sell_through": lines["sell"][i], "reason": lines["reason"][i]})
    return out


def test_compact_lines_roundtrip_and_shrinks():
    from invopt.page import compact

    line = lambda n, w, h: {"product": n, "kind": "hotel", "region": "SE Asia", "week_start": w, "hard": h, "soft": 3.0,
                            "prepaid_inr": 1234567.4, "exp_profit_inr": 76543.6, "p_line_loss": 0.01234,
                            "hard_sell_through": None if h == 0 else 0.98765, "mean_demand": 10.0, "reason": f"r{n}{w}"}
    rows = [line(n, w, h) for n in ("Bali 5★", "Goa 4★") for w in ("2027-01-04", "2027-01-11") for h in (0.0, 7.0)]
    data = {"cells": {"0": {"Balanced": {"lines": rows, "kpis": {}}}}}
    c = compact(data)
    back = _expand(c, c["cells"]["0"]["Balanced"]["lines"])
    assert len(back) == len(rows)
    for a, b in zip(rows, back):
        assert a["product"] == b["product"] and a["week_start"] == b["week_start"] and a["reason"] == b["reason"]
        assert b["hard"] == a["hard"] and b["prepaid_inr"] == round(a["prepaid_inr"])
        assert b["p_line_loss"] == pytest.approx(a["p_line_loss"], abs=1e-4)
        assert (b["hard_sell_through"] is None) == (a["hard_sell_through"] is None)
    assert "lines" in data["cells"]["0"]["Balanced"] and isinstance(data["cells"]["0"]["Balanced"]["lines"], list)  # input untouched
    big = {"cells": {"0": {"x": {"lines": rows * 200}}}}
    assert len(json.dumps(compact(big))) < 0.6 * len(json.dumps(big))
