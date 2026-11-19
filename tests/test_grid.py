import json

import numpy as np
import pytest

from invopt.grid import run_grid

RISKS = {"Max profit": 0.0, "Very careful": 3.0}


@pytest.fixture(scope="module")
def tiny():
    return run_grid(budget_fracs=(0.5, 1.0), risk_levels=RISKS, n_plan=60, n_eval=300, weeks=3, workers=1,
                    backtest_path=None)


def test_grid_keys(tiny):
    for key in ("budgets_inr", "risk_levels", "cells", "frontier", "robustness", "assumptions", "shock_labels"):
        assert key in tiny
    cell = tiny["cells"]["0"]["Max profit"]
    for key in ("kpis", "lines", "exposure", "gaps", "shocks", "status", "histogram_base"):
        assert key in cell
    for key in ("mean", "cvar95_profit", "p_loss", "fill_rate", "spend", "budget_shadow_price"):
        assert key in cell["kpis"]
    assert {"middle_east_disruption", "india_airline_collapse", "rupee_slide"} <= set(cell["shocks"])
    line = cell["lines"][0]
    for key in ("product", "region", "week_start", "hard", "soft", "prepaid_inr", "exp_profit_inr",
                "p_line_loss", "hard_sell_through", "reason"):
        assert key in line
    json.dumps(tiny, allow_nan=False)


def test_spend_within_budget(tiny):
    for bi, budget in enumerate(tiny["budgets_inr"]):
        for risk in RISKS:
            assert tiny["cells"][str(bi)][risk]["kpis"]["spend"] <= budget + 1e-6


def test_frontier_monotone_in_budget(tiny):
    means = np.array(tiny["frontier"]["Max profit"]["mean"])
    assert np.all(np.diff(means) >= -0.005 * np.abs(means).max())


def test_more_careful_lower_tail_risk(tiny):
    for bi in range(len(tiny["budgets_inr"])):
        bold = tiny["cells"][str(bi)]["Max profit"]["kpis"]
        careful = tiny["cells"][str(bi)]["Very careful"]["kpis"]
        assert careful["cvar95_profit"] >= bold["cvar95_profit"] - 0.02 * abs(bold["mean"])


def test_robustness_table(tiny):
    rob = tiny["robustness"]
    assert set(rob["worlds"]) == {"base", "demand -20%", "demand +20%", "stronger seasons",
                                  "higher correlation", "later bookings", "more volatile"}
    for world, by_policy in rob["results"].items():
        assert {"Blockwise (Balanced)", "point_forecast_hard", "expected_volume_hard", "dynamic_only"} <= set(by_policy)


def test_marginal_profit_is_out_of_sample_frontier_slope(tiny):
    b = tiny["budgets_inr"]
    for risk in RISKS:
        means = tiny["frontier"][risk]["mean"]
        for i in range(len(b) - 1):
            k = tiny["cells"][str(i)][risk]["kpis"]
            expected = (means[i + 1] - means[i]) / (b[i + 1] - b[i]) * 1e7
            assert k["marginal_profit_per_cr"] == pytest.approx(expected, abs=1e-2)
        assert tiny["cells"][str(len(b) - 1)][risk]["kpis"]["marginal_profit_per_cr"] is None


def test_robustness_has_two_contract_rule_and_unseen_worlds(tiny):
    rob = tiny["robustness"]
    for world in rob["worlds"]:
        assert "allot_expected_block_p25" in rob["results"][world]
    assert "base" not in rob["unseen_worlds"] and len(rob["unseen_worlds"]) == len(rob["worlds"]) - 1
    assert rob["status"] == "optimal"


def test_fallbacks_counted_and_marked(tiny):
    assert tiny["fallback_count"] == 0
    for risk in RISKS:
        assert tiny["frontier"][risk]["status"] == ["optimal"] * len(tiny["budgets_inr"])


def test_reference_solve_failure_aborts(monkeypatch):
    import invopt.grid as g
    from invopt.economics import Plan
    from invopt.optimizer import OptResult

    def failing(cells, terms, params):
        z = Plan.zeros(cells.n_groups)
        return OptResult(plan=z, plan_int=z, status="time_limit", objective=float("nan"),
                         budget_shadow_price=0.0, solve_seconds=0.0)
    monkeypatch.setattr(g, "optimize", failing)
    with pytest.raises(RuntimeError, match="reference"):
        g.run_grid(budget_fracs=(1.0,), risk_levels={"Max profit": 0.0}, n_plan=10, n_eval=20, weeks=1, workers=1,
                   backtest_path=None)


def test_singapore_section_copied_without_monthly_rows(tmp_path):
    import json as _json
    sg = {"summary": {"ours_0.25": {"pct_of_hindsight": 90.0}}, "by_period": {}, "forecast": {}, "timeline": [],
          "assumptions": {}, "methods_used": {}, "notes": [], "by_month": [{"x": 1}] * 50}
    p = tmp_path / "singapore.json"
    p.write_text(_json.dumps(sg))
    res = run_grid(budget_fracs=(1.0,), risk_levels={"Max profit": 0.0}, n_plan=10, n_eval=30, weeks=1, workers=1,
                   backtest_path=None, singapore_path=p)
    assert res["singapore"]["summary"]["ours_0.25"]["pct_of_hindsight"] == 90.0
    assert "by_month" not in res["singapore"]


def test_singapore_static_ablation_attached(tmp_path):
    import json as _json
    base = {"summary": {}, "by_period": {}, "forecast": {"headline": {"all": {"coverage_80": 0.8}}}, "timeline": [],
            "assumptions": {}, "methods_used": {}, "notes": [], "by_month": []}
    static = dict(base, forecast={"headline": {"all": {"coverage_80": 0.5}}}, summary={"ours_0.25": {"x": 1}})
    (tmp_path / "singapore.json").write_text(_json.dumps(base))
    (tmp_path / "singapore_static.json").write_text(_json.dumps(static))
    res = run_grid(budget_fracs=(1.0,), risk_levels={"Max profit": 0.0}, n_plan=10, n_eval=30, weeks=1, workers=1,
                   backtest_path=None, singapore_path=tmp_path / "singapore.json")
    assert res["singapore"]["static_forecast"]["all"]["coverage_80"] == 0.5
    assert res["singapore"]["static_summary"]["ours_0.25"]["x"] == 1


def test_attach_singapore_builds_ablation_rows(tmp_path):
    import json as _json
    from invopt.grid import attach_singapore

    def rep(pct, covid, rec, recent, w5, br):
        per = {"2020–21 COVID": {"ours_0.25": {"profit": covid}}, "2022–23 recovery": {"ours_0.25": {"profit": rec}},
               "2024–26 recent": {"ours_0.25": {"pct_of_hindsight": recent}}}
        return {"summary": {"ours_0.25": {"pct_of_hindsight": pct, "worst5_month_avg": w5}}, "by_period": per,
                "forecast": {"headline": {}}, "timeline": [], "assumptions": {}, "methods_used": {}, "notes": [],
                "breaker_months": ["2020-07-01"] * br, "by_month": []}
    for name, r in {"singapore": rep(80, -2.5e6, 4.5e6, 88.5, -3e5, 33),
                    "singapore_nosafeguards": rep(47.7, -7.9e6, -5.7e6, 90.8, -1.3e6, 0)}.items():
        (tmp_path / f"{name}.json").write_text(_json.dumps(r))
    res = attach_singapore({}, tmp_path / "singapore.json")
    rows = {r["key"]: r for r in res["singapore"]["ablations"]}
    assert rows["headline"]["pct_of_hindsight"] == 80 and rows["nosafeguards"]["covid_profit"] == -7.9e6
    assert "static" not in rows  # absent files are skipped
    assert "by_month" not in res["singapore"]
