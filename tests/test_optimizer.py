import time

import numpy as np
import pytest

from invopt.config import ContractTerms
from invopt.economics import Cells, Plan, evaluate
from invopt.optimizer import OptimizerParams, fallback_plan, optimize

TERMS = ContractTerms()


def cells_from(late, early, price=100.0, ref=100.0, dyn_cap=np.inf):
    late = np.atleast_2d(np.asarray(late, dtype=float))
    early = np.atleast_2d(np.asarray(early, dtype=float))
    C, S = late.shape
    cap = np.full((C, S), dyn_cap, dtype=float) if np.isscalar(dyn_cap) else np.asarray(dyn_cap, float)
    return Cells(group=np.arange(C), price=np.full(C, price), ref_rate=np.full(C, ref),
                 late=late, early=early, dyn_cap=cap)


def random_instance(C, S, seed=0, groups=None):
    rng = np.random.default_rng(seed)
    mean = rng.uniform(5, 50, size=C)
    demand = rng.poisson(mean[:, None] * rng.lognormal(0, 0.4, size=(1, S)), size=(C, S)).astype(float)
    share = rng.uniform(0.5, 0.95, size=(C, 1))
    early = np.floor(demand * share)
    late = demand - early
    ref = rng.uniform(80, 200, size=C)
    price = ref[:, None] * rng.lognormal(0, 0.1, size=(C, S))
    cap = np.where(rng.uniform(size=(C, S)) < 0.15, 0.0, np.inf)
    group = np.arange(C) if groups is None else np.arange(C) % groups
    return Cells(group=group, price=price, ref_rate=ref, late=late, early=early, dyn_cap=cap)


def test_deterministic_full_cover():
    res = optimize(cells_from([[5]], [[10]]), TERMS, OptimizerParams())
    assert res.status == "optimal"
    assert res.plan.hard[0] == pytest.approx(15, abs=1e-6)
    assert res.plan.soft[0] == pytest.approx(0, abs=1e-6)
    assert res.objective == pytest.approx(450, abs=1e-6)


def test_budget_binding_and_shadow():
    res = optimize(cells_from([[5]], [[10]]), TERMS, OptimizerParams(budget=700.0))
    assert res.plan.hard[0] == pytest.approx(10, abs=1e-6)
    assert res.plan.soft[0] == pytest.approx(5, abs=1e-6)
    assert res.objective == pytest.approx(390, abs=1e-6)
    assert res.budget_shadow_price == pytest.approx(12 / 70, abs=1e-6)


def test_risky_demand_no_hard():
    res = optimize(cells_from([[0, 10]], [[0, 0]]), TERMS, OptimizerParams())
    assert res.plan.hard[0] == pytest.approx(0, abs=1e-6)
    assert res.objective == pytest.approx(50, abs=1e-6)


def test_cvar_reduces_commitment():
    cells = cells_from([[0, 20]], [[0, 0]], price=200.0, ref=100.0, dyn_cap=0.0)
    neutral = optimize(cells, TERMS, OptimizerParams(risk_aversion=0.0, alpha=0.5))
    careful = optimize(cells, TERMS, OptimizerParams(risk_aversion=5.0, alpha=0.5))
    assert neutral.plan.hard[0] == pytest.approx(20, abs=1e-5)
    assert careful.plan.hard[0] == pytest.approx(200 / 210, abs=1e-5)


def test_lp_matches_evaluator():
    cells = random_instance(20, 50, seed=3)
    res = optimize(cells, TERMS, OptimizerParams())
    assert res.status == "optimal"
    lp_mean = res.objective  # risk-neutral: objective == in-sample mean profit
    ev = evaluate(cells, res.plan, TERMS).summary()["mean"]
    assert ev == pytest.approx(lp_mean, rel=1e-6, abs=1e-6)


def test_lp_matches_evaluator_with_risk_and_groups():
    cells = random_instance(24, 40, seed=5, groups=6)
    params = OptimizerParams(risk_aversion=1.0, alpha=0.9, budget=5000.0)
    res = optimize(cells, TERMS, params)
    out = evaluate(cells, res.plan, TERMS)
    from invopt.economics import cvar_profit
    recomputed = out.profit.mean() + 1.0 * cvar_profit(out.profit, 0.9)  # -lambda*CVaR(loss) = +lambda*CVaR(profit)
    assert recomputed == pytest.approx(res.objective, rel=1e-6, abs=1e-4)
    assert out.spend <= 5000.0 + 1e-6


def test_degenerate_inputs():
    cells = random_instance(10, 20, seed=1)
    zero = optimize(cells, TERMS, OptimizerParams(budget=0.0))
    assert np.allclose(zero.plan.hard, 0, atol=1e-9)
    tiny = optimize(cells, TERMS, OptimizerParams(budget=1e-9))
    assert evaluate(cells, tiny.plan, TERMS).spend <= 1e-9 + 1e-12
    huge = optimize(cells, TERMS, OptimizerParams(risk_aversion=1e4))
    assert huge.status == "optimal"
    assert np.all(np.isfinite(huge.plan.hard)) and np.all(np.isfinite(huge.plan.soft))


def test_integer_plan_within_budget():
    cells = random_instance(10, 20, seed=2)
    res = optimize(cells, TERMS, OptimizerParams(budget=3000.0))
    assert np.allclose(res.plan_int.hard, np.floor(res.plan_int.hard))
    assert evaluate(cells, res.plan_int, TERMS).spend <= 3000.0 + 1e-6


def test_nonfinite_rejected():
    cells = cells_from([[5]], [[10]])
    cells.price = np.array([np.nan])
    with pytest.raises(ValueError, match="price"):
        optimize(cells, TERMS, OptimizerParams())


def test_time_limit_status():
    cells = random_instance(200, 100, seed=4)
    res = optimize(cells, TERMS, OptimizerParams(time_limit_s=1e-6))
    assert res.status != "optimal"
    fb = fallback_plan(cells)
    assert np.all(fb.hard == 0) and np.all(fb.soft == 0)


def test_soft_cap_respected():
    cells = cells_from([[0]], [[30]])
    res = optimize(cells, TERMS, OptimizerParams(budget=0.0, soft_cap=np.array([7.0])))
    assert res.plan.soft[0] == pytest.approx(7, abs=1e-6)
