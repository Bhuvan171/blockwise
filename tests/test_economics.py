import numpy as np
import pytest

from invopt.config import ContractTerms
from invopt.economics import Cells, Plan, evaluate

TERMS = ContractTerms()  # hard 70, soft 80, dyn 90, hold 2/unit, stockout 10 at price=ref=100


def one_cell(late, early, dyn_cap=np.inf, price=100.0, ref=100.0):
    return Cells(
        group=np.array([0]),
        price=np.array([price]),
        ref_rate=np.array([ref]),
        late=np.array([[late]], dtype=float),
        early=np.array([[early]], dtype=float),
        dyn_cap=np.array([[dyn_cap]], dtype=float),
    )


def test_mixed_contracts():
    out = evaluate(one_cell(5, 10), Plan(hard=np.array([8.0]), soft=np.array([6.0])), TERMS)
    # 100*15 - 70*8 - 80*6 - 90*1 - 2*6 = 358
    assert out.profit[0] == pytest.approx(358.0)
    assert out.served[0, 0] == pytest.approx(15.0)
    assert out.lost[0, 0] == pytest.approx(0.0)


def test_soldout_market():
    out = evaluate(one_cell(5, 10, dyn_cap=0.0), Plan(hard=np.array([8.0]), soft=np.array([6.0])), TERMS)
    # 100*14 - 560 - 480 - 12 - 10*1 = 338
    assert out.profit[0] == pytest.approx(338.0)
    assert out.lost[0, 0] == pytest.approx(1.0)


def test_unsold_hard():
    out = evaluate(one_cell(2, 1), Plan(hard=np.array([8.0]), soft=np.array([6.0])), TERMS)
    # 100*3 - 560 - 0 - 12 = -272 ; 5 hard units unsold
    assert out.profit[0] == pytest.approx(-272.0)
    assert out.unsold_hard[0, 0] == pytest.approx(5.0)


def test_group_broadcast():
    cells = Cells(
        group=np.array([0, 0, 0]),
        price=np.full(3, 100.0),
        ref_rate=np.full(3, 100.0),
        late=np.zeros((3, 1)),
        early=np.zeros((3, 1)),
        dyn_cap=np.full((3, 1), np.inf),
    )
    out = evaluate(cells, Plan(hard=np.array([2.0]), soft=np.array([0.0])), TERMS)
    assert out.summary()["spend"] == pytest.approx(3 * 2 * 70.0)
    assert out.profit[0] == pytest.approx(-3 * 2 * 70.0)


def test_summary_cvar():
    S = 20
    late = np.zeros((1, S))
    late[0, 1:] = 1.0  # scenario 0: no demand; others: 1 unit
    cells = Cells(group=np.array([0]), price=np.array([100.0]), ref_rate=np.array([100.0]),
                  late=late, early=np.zeros((1, S)), dyn_cap=np.full((1, S), np.inf))
    # hard 1 unit: scenario 0 loses 70; others earn 30
    s = evaluate(cells, Plan(hard=np.array([1.0]), soft=np.array([0.0])), TERMS).summary()
    assert s["cvar95_profit"] == pytest.approx(-70.0)
    assert s["p_loss"] == pytest.approx(0.05)
    assert s["mean"] == pytest.approx((19 * 30 - 70) / 20)
    assert s["fill_rate"] == pytest.approx(1.0)


def test_dyn_cheaper_than_soft_uses_dyn_first():
    # market price fell: dyn cost 0.9*80=72 < soft cost 80 -> early demand bought as needed first
    cells = one_cell(0, 10, dyn_cap=4.0, price=80.0, ref=100.0)
    out = evaluate(cells, Plan(hard=np.array([0.0]), soft=np.array([10.0])), TERMS)
    # revenue 80*10 ; dyn 4*72 ; soft 6*80 ; hold 10*2
    assert out.profit[0] == pytest.approx(800 - 288 - 480 - 20)


def test_unprofitable_soft_not_used():
    # soft cost 80 > price 50 + stockout 10 -> better to lose the sale than use the allotment
    cells = one_cell(0, 5, dyn_cap=0.0, price=50.0, ref=100.0)
    out = evaluate(cells, Plan(hard=np.array([0.0]), soft=np.array([5.0])), TERMS)
    assert out.lost[0, 0] == pytest.approx(5.0)
    assert out.profit[0] == pytest.approx(-10 * 5 - 2 * 5)


def test_terms_validate():
    with pytest.raises(ValueError):
        ContractTerms(soft_discount=0.35).validate()
