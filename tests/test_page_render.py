"""Render the real page headlessly and check what a viewer would see (skipped without Chrome or results)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from invopt.page import build_page

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "out" / "results.json"
CHROME = shutil.which("google-chrome-stable") or shutil.which("google-chrome") or shutil.which("chromium")
pytestmark = pytest.mark.skipif(not (CHROME and RESULTS.exists()), reason="needs Chrome and out/results.json")


def _upgrade(d):
    """Fill fields that results.json files from before the review fixes lack."""
    n = len(d["budgets_inr"])
    d.setdefault("fallback_count", 0)
    for risk, f in d["frontier"].items():
        f.setdefault("status", ["optimal"] * n)
        for i in range(n):
            nxt = None if i == n - 1 else (f["mean"][i + 1] - f["mean"][i]) / (d["budgets_inr"][i + 1] - d["budgets_inr"][i]) * 1e7
            d["cells"][str(i)][risk]["kpis"].setdefault("marginal_profit_per_cr", nxt)
    rob = d["robustness"]
    rob.setdefault("unseen_worlds", [w for w in rob["worlds"] if w != "base"])
    rob.setdefault("status", "optimal")
    return d


def render(tmp_path, mutate=lambda d: None):
    d = _upgrade(json.loads(RESULTS.read_text()))
    mutate(d)
    src = tmp_path / "r.json"
    src.write_text(json.dumps(d))
    page = build_page(src, tmp_path / "p.html", standalone=True)
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--virtual-time-budget=5000",
                          "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=180)
    return out.stdout


def test_fallback_banner_and_marker(tmp_path):
    def mut(d):
        d["cells"]["0"]["Max profit"]["status"] = "time_limit"
        d["frontier"]["Max profit"]["status"][0] = "time_limit"
        d["fallback_count"] = 1
    dom = render(tmp_path, mut)
    total = 5 * 4
    assert f"1 of {total} plans" in dom
    assert 'class="fallback"' in dom


def test_marginal_tile_is_expected_profit(tmp_path):
    dom = render(tmp_path)
    assert "Next ₹1 Cr of budget adds" in dom
    assert "to expected profit" in dom


def test_robustness_counts_unseen_worlds(tmp_path):
    dom = render(tmp_path)
    assert "of 6 worlds it was not planned for" in dom
