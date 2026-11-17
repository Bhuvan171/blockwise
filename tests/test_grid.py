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
