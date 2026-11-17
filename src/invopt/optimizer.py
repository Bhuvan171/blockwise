"""Choose hard-block and allotment sizes by sample-average approximation.

    maximise   mean_s Profit_s  -  lambda * CVaR_alpha(-Profit)
    subject to prepaid hard spend <= budget, optional per-group caps and region shares

Profit_s is the same quantity `economics.evaluate` computes; the second-stage
allocation (hard -> late/early, allotment -> early, buy-as-needed -> rest) is
modelled with per-(cell, scenario) variables so the LP picks the optimal one.
CVaR uses the Rockafellar-Uryasev linearisation. Solved with HiGHS via SciPy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from invopt.config import ContractTerms
from invopt.economics import Cells, Plan


@dataclass(frozen=True)
class OptimizerParams:
    risk_aversion: float = 0.0  # lambda
    alpha: float = 0.95
    budget: float = np.inf  # cap on prepaid hard-block spend
    hard_cap: np.ndarray | None = None  # float[G] max hard units per cell
    soft_cap: np.ndarray | None = None  # float[G] max allotted units per cell
    group_region: np.ndarray | None = None  # int[G] region id per group
    region_share: float = 1.0  # max share of budget in any one region
    time_limit_s: float = 300.0


@dataclass
class OptResult:
    plan: Plan  # LP solution (continuous)
    plan_int: Plan  # hard floored, allotment rounded (whole rooms/seats)
    status: str  # "optimal" | "time_limit" | "failed"
    objective: float
    budget_shadow_price: float  # objective gain per extra currency unit of budget
    solve_seconds: float
    message: str = ""


def fallback_plan(cells: Cells) -> Plan:
    """Commit nothing: buy everything as needed."""
    return Plan.zeros(cells.n_groups)


def optimize(cells: Cells, terms: ContractTerms, params: OptimizerParams) -> OptResult:
    cells.validate()
    terms.validate()
    if not (0.0 < params.alpha < 1.0):
        raise ValueError("alpha must be in (0, 1)")
    if params.risk_aversion < 0 or not np.isfinite(params.risk_aversion):
        raise ValueError("risk_aversion must be finite and >= 0")
    if params.budget < 0 or np.isnan(params.budget):
        raise ValueError("budget must be >= 0")

    C, S, G = cells.n_cells, cells.n_scen, cells.n_groups
    g = np.asarray(cells.group)
    p = cells.price2d()
    c = terms.costs(np.asarray(cells.ref_rate, float)[:, None], cells.market2d())
    hard_c, soft_c, hold, stock, salv = (c[k][:, 0] for k in ("hard", "soft", "hold", "stockout", "salvage"))
    dyn_c = c["dyn"]
    L, E, V = cells.late, cells.early, cells.dyn_cap

    # per-unit profit contributions of second-stage variables, shape [C, S]
    a12 = p + stock[:, None] - salv[:, None]
    a3 = p + stock[:, None] - soft_c[:, None]
    a4 = p + stock[:, None] - dyn_c
    k_s = -(stock[:, None] * (L + E)).sum(axis=0)  # constant part of Profit_s
    F_hard = np.bincount(g, weights=hard_c - salv, minlength=G)  # first-stage cost per unit of H_g
    F_soft = np.bincount(g, weights=hold, minlength=G)
    spend_coef = np.bincount(g, weights=hard_c, minlength=G)  # prepaid spend per unit of H_g
    for name, arr in (("a12", a12), ("a3", a3), ("a4", a4), ("k_s", k_s), ("F_hard", F_hard), ("F_soft", F_soft)):
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"non-finite LP coefficient in {name}")

    lam = float(params.risk_aversion)
    use_cvar = lam > 0
    CS = C * S
    iH, iSO = 0, G
    b1, b2, b3, b4 = 2 * G, 2 * G + CS, 2 * G + 2 * CS, 2 * G + 3 * CS
    i_eta = 2 * G + 4 * CS
    i_z = i_eta + 1
    i_phi = i_z + S  # phi = first-stage cost F(H, SO), shared by every CVaR row
    n_var = i_phi + 1 if use_cvar else 2 * G + 4 * CS

    # objective (minimise the negative)
    cost = np.zeros(n_var)
    cost[iH:iH + G] = F_hard
    cost[iSO:iSO + G] = F_soft
    cost[b1:b1 + CS] = -(a12 / S).ravel()
    cost[b2:b2 + CS] = -(a12 / S).ravel()
    cost[b3:b3 + CS] = -(a3 / S).ravel()
    cost[b4:b4 + CS] = -(a4 / S).ravel()
    const = -k_s.mean()
    if use_cvar:
        cost[i_eta] = lam
        cost[i_z:i_z + S] = lam / ((1.0 - params.alpha) * S)

    idx = np.arange(CS)
    cell_of = idx // S
    rows, cols, vals, rhs = [], [], [], []

    def add(r, cl, v):
        rows.append(np.asarray(r)), cols.append(np.asarray(cl)), vals.append(np.broadcast_to(v, np.shape(r)).astype(float))

    # R1: u2 + u3 <= E
    add(idx, b2 + idx, 1.0), add(idx, b3 + idx, 1.0)
    rhs.append(E.ravel())
    # R2: u1+u2+u3+u4 <= L+E
    r = CS + idx
    for base in (b1, b2, b3, b4):
        add(r, base + idx, 1.0)
    rhs.append((L + E).ravel())
    # R3: u1 + u2 - H_g <= 0
    r = 2 * CS + idx
    add(r, b1 + idx, 1.0), add(r, b2 + idx, 1.0), add(r, iH + g[cell_of], -1.0)
    rhs.append(np.zeros(CS))
    # R4: u3 - SO_g <= 0
    r = 3 * CS + idx
    add(r, b3 + idx, 1.0), add(r, iSO + g[cell_of], -1.0)
    rhs.append(np.zeros(CS))
    n_rows = 4 * CS
    if use_cvar:
        s_of = idx % S
        r = n_rows + s_of
        add(r, b1 + idx, -a12.ravel()), add(r, b2 + idx, -a12.ravel())
        add(r, b3 + idx, -a3.ravel()), add(r, b4 + idx, -a4.ravel())
        add(n_rows + np.arange(S), np.full(S, i_phi), 1.0)
        add(n_rows + np.arange(S), np.full(S, i_eta), -1.0)
        add(n_rows + np.arange(S), i_z + np.arange(S), -1.0)
        rhs.append(k_s)
        n_rows += S
        # phi >= F(H, SO); tight at the optimum because a larger phi only tightens the CVaR rows
        add(np.full(G, n_rows), iH + np.arange(G), F_hard)
        add(np.full(G, n_rows), iSO + np.arange(G), F_soft)
        add([n_rows], [i_phi], -1.0)
        rhs.append(np.array([0.0]))
        n_rows += 1
    budget_row = None
    if np.isfinite(params.budget):
        budget_row = n_rows
        add(np.full(G, n_rows), iH + np.arange(G), spend_coef)
        rhs.append(np.array([params.budget]))
        n_rows += 1
        if params.group_region is not None and params.region_share < 1.0:
            reg = np.asarray(params.group_region)
            for k, rid in enumerate(np.unique(reg)):
                members = np.flatnonzero(reg == rid)
                add(np.full(len(members), n_rows), iH + members, spend_coef[members])
                rhs.append(np.array([params.region_share * params.budget]))
                n_rows += 1

    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n_rows, n_var))
    b = np.concatenate(rhs)

    lo = np.zeros(n_var)
    hi = np.full(n_var, np.inf)
    if params.hard_cap is not None:
        hi[iH:iH + G] = np.asarray(params.hard_cap, float)
    if params.soft_cap is not None:
        hi[iSO:iSO + G] = np.asarray(params.soft_cap, float)
    hi[b1:b1 + CS] = L.ravel()
    hi[b4:b4 + CS] = V.ravel()
    if use_cvar:
        lo[i_eta] = -np.inf
        lo[i_phi] = -np.inf

    t0 = time.perf_counter()
    res = linprog(cost, A_ub=A, b_ub=b, bounds=np.column_stack([lo, hi]), method="highs",
                  options={"time_limit": float(params.time_limit_s), "presolve": True})
    secs = time.perf_counter() - t0

    status = {0: "optimal", 1: "time_limit"}.get(res.status, "failed")
    if status != "optimal" or res.x is None:
        zero = fallback_plan(cells)
        return OptResult(plan=zero, plan_int=zero, status=status, objective=float("nan"),
                         budget_shadow_price=0.0, solve_seconds=secs, message=str(res.message))

    x = res.x
    hard = np.maximum(x[iH:iH + G], 0.0)
    soft = np.maximum(x[iSO:iSO + G], 0.0)
    shadow = 0.0
    if budget_row is not None and res.ineqlin is not None:
        shadow = max(0.0, -float(res.ineqlin.marginals[budget_row]))
    hard_i = np.floor(hard + 1e-9)
    soft_i = np.round(soft)
    if params.soft_cap is not None:
        soft_i = np.minimum(soft_i, np.floor(np.asarray(params.soft_cap, float) + 1e-9))
    return OptResult(
        plan=Plan(hard=hard, soft=soft),
        plan_int=Plan(hard=hard_i, soft=soft_i),
        status=status,
        objective=float(-(res.fun) - const),
        budget_shadow_price=shadow,
        solve_seconds=secs,
        message=str(res.message),
    )
