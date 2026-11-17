"""What a commitment plan earns, scenario by scenario. This module is the truth.

A *cell* is one unit of inventory time: a hotel night, or a product-week pool.
Cells sharing a contract *group* share one decision (e.g. every night of a week
gets the same block size). For each cell and scenario:

  late  = demand booked after the allotment release date (only hard or buy-as-needed can serve it)
  early = demand booked before release (hard, allotment or buy-as-needed can serve it)

Resources and their marginal cost once the plan is fixed:
  hard block      prepaid, so using a unit only forgoes its salvage value (cheapest)
  soft allotment  pay the allotment rate per unit used; early demand only
  buy as needed   pay the market net rate per unit, up to `dyn_cap` (0 when the market is sold out)

The allocation below is the optimal second-stage decision (it equals the LP's
choice; `tests/test_optimizer.py::test_lp_matches_evaluator` checks this).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from invopt.config import ContractTerms


@dataclass
class Cells:
    group: np.ndarray  # int[C]
    price: np.ndarray  # float[C] or float[C,S]: selling price per unit
    ref_rate: np.ndarray  # float[C]: contract reference rate
    late: np.ndarray  # float[C,S]
    early: np.ndarray  # float[C,S]
    dyn_cap: np.ndarray  # float[C,S]; np.inf = unlimited
    dyn_price: np.ndarray | None = None  # float[C,S] market price for buy-as-needed (default: price)
    meta: pd.DataFrame | None = field(default=None, repr=False)

    @property
    def n_cells(self) -> int:
        return int(self.late.shape[0])

    @property
    def n_scen(self) -> int:
        return int(self.late.shape[1])

    @property
    def n_groups(self) -> int:
        return int(self.group.max()) + 1 if len(self.group) else 0

    def price2d(self) -> np.ndarray:
        p = np.asarray(self.price, dtype=float)
        return np.broadcast_to(p[:, None] if p.ndim == 1 else p, self.late.shape)

    def market2d(self) -> np.ndarray:
        if self.dyn_price is None:
            return self.price2d()
        return np.broadcast_to(np.asarray(self.dyn_price, dtype=float), self.late.shape)

    def validate(self) -> "Cells":
        C, S = self.late.shape
        if self.early.shape != (C, S) or self.dyn_cap.shape != (C, S):
            raise ValueError("late, early and dyn_cap must share shape [C, S]")
        if self.group.shape != (C,) or self.ref_rate.shape != (C,):
            raise ValueError("group and ref_rate must have shape [C]")
        for name, arr in (("price", self.price2d()), ("ref_rate", self.ref_rate),
                          ("late", self.late), ("early", self.early), ("dyn_price", self.market2d())):
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"non-finite values in {name}")
        if (self.late < 0).any() or (self.early < 0).any() or (self.dyn_cap < 0).any() or np.isnan(self.dyn_cap).any():
            raise ValueError("demand and dyn_cap must be >= 0")
        if len(self.group) and (self.group.min() < 0 or not np.issubdtype(self.group.dtype, np.integer)):
            raise ValueError("group must hold non-negative integers")
        return self


@dataclass
class Plan:
    hard: np.ndarray  # float[G]: hard units per cell in each group
    soft: np.ndarray  # float[G]: allotted units per cell in each group

    @staticmethod
    def zeros(n_groups: int) -> "Plan":
        return Plan(hard=np.zeros(n_groups), soft=np.zeros(n_groups))


@dataclass
class Outcome:
    profit: np.ndarray  # float[S]
    cell_profit: np.ndarray  # float[C,S]
    served: np.ndarray
    lost: np.ndarray
    unsold_hard: np.ndarray
    demand: np.ndarray
    spend: float  # prepaid hard-block spend
    unsold_cost: np.ndarray  # float[S]: net cost of unsold hard units per scenario

    def summary(self, alpha: float = 0.95) -> dict:
        total_demand = float(self.demand.sum())
        return {
            "mean": float(self.profit.mean()),
            "cvar95_profit": float(cvar_profit(self.profit, alpha)),
            "p_loss": float((self.profit < 0).mean()),
            "fill_rate": float(self.served.sum() / total_demand) if total_demand > 0 else 1.0,
            "unsold_hard_cost": float(self.unsold_cost.mean()),
            "spend": float(self.spend),
        }


def cvar_profit(profit: np.ndarray, alpha: float = 0.95) -> float:
    """Mean of the worst (1 - alpha) share of equally likely profits (fractional tail weight)."""
    p = np.sort(np.asarray(profit, dtype=float))
    tail = (1.0 - alpha) * len(p)
    k = int(np.floor(tail + 1e-12))
    frac = tail - k
    total = p[:k].sum() + (frac * p[k] if frac > 1e-12 and k < len(p) else 0.0)
    return total / tail


def evaluate(cells: Cells, plan: Plan, terms: ContractTerms) -> Outcome:
    g = np.asarray(cells.group)
    H = np.asarray(plan.hard, dtype=float)[g][:, None]
    SO = np.asarray(plan.soft, dtype=float)[g][:, None]
    p = cells.price2d()
    c = terms.costs(np.asarray(cells.ref_rate, dtype=float)[:, None], cells.market2d())
    L, E, V = cells.late, cells.early, cells.dyn_cap

    value = p + c["stockout"]  # what serving one more unit is worth vs losing the sale
    use_h = c["salvage"] < value
    use_s = c["soft"] < value
    use_d = c["dyn"] < value

    # Hard first (cheapest marginal), late before early: early still has the allotment as a fallback.
    u1 = np.where(use_h, np.minimum(L, H), 0.0)
    u2 = np.where(use_h, np.minimum(E, H - u1), 0.0)
    Lr, Er = L - u1, E - u2

    soft_first = c["soft"] <= c["dyn"]
    # (a) allotment before buy-as-needed
    s_a = np.where(use_s, np.minimum(Er, SO), 0.0)
    d_a = np.where(use_d, np.minimum(V, Lr + Er - s_a), 0.0)
    # (b) buy-as-needed is cheaper: it serves late first (late has no allotment option), then early
    d_b = np.where(use_d, np.minimum(V, Lr + Er), 0.0)
    s_b = np.where(use_s, np.minimum(Er - np.maximum(d_b - Lr, 0.0), SO), 0.0)
    s = np.where(soft_first, s_a, s_b)
    d = np.where(soft_first, d_a, d_b)

    served = u1 + u2 + s + d
    demand = L + E
    lost = demand - served
    unsold = H - u1 - u2
    unsold_cost = (c["hard"] - c["salvage"]) * unsold
    cell_profit = (p * served - c["hard"] * H - c["soft"] * s - c["dyn"] * d
                   - c["hold"] * SO - c["stockout"] * lost + c["salvage"] * unsold)
    spend = float((c["hard"][:, 0] * H[:, 0]).sum())
    return Outcome(
        profit=cell_profit.sum(axis=0),
        cell_profit=cell_profit,
        served=served,
        lost=lost,
        unsold_hard=np.broadcast_to(unsold, demand.shape).copy(),
        demand=demand,
        spend=spend,
        unsold_cost=unsold_cost.sum(axis=0) if unsold_cost.ndim == 2 else np.zeros(cells.n_scen),
    )
