"""Model 1: range and shelf-space allocation as an integer programme, with a greedy heuristic and simulated annealing.

max  sum_i p_i x_i + tau * sum_i sum_{j in N(i)} s_ij * m_j * d_i * y_ij
s.t. sum_i w_i x_i <= W                        shelf space
     y_ij <= x_j,  sum_j y_ij + x_i <= 1       a delisted item's demand moves to at most one ranged neighbour
     sum_{i in g} x_i >= L_g                   minimum range depth per sub-category
     sum_{i of supplier s} w_i x_i <= u * W    no supplier holds more than u of the shelf
p_i = weekly profit of item i; m_j = profit per unit of j (so a transferred unit earns j's margin, not i's).
"""
from __future__ import annotations

import math
import time

import numpy as np
import pyomo.environ as pe

from .data import RangeInstance


def unit_profit(inst: RangeInstance) -> np.ndarray:
    return inst.price * inst.margin_rate


def _edges(inst: RangeInstance):
    """Edges (i, j, v_ij): value earned if delisted item i sends its transferable demand to ranged neighbour j."""
    nb = inst.neighbours
    ii, kk = np.where(nb >= 0)
    jj = nb[ii, kk]
    v = inst.tau * inst.sim[ii, kk] * unit_profit(inst)[jj] * inst.demand[ii]
    return ii, jj, v


def objective(inst: RangeInstance, x: np.ndarray) -> float:
    """Exact objective for a 0/1 vector: each delisted item sends tau * s_ij of its demand to its best ranged neighbour."""
    x = np.asarray(x).astype(bool)
    base = float(inst.profit[x].sum())
    if inst.tau <= 0:
        return base
    ii, jj, v = _edges(inst)
    best = np.zeros(inst.n)
    np.maximum.at(best, ii, v * x[jj])
    return base + float(best[~x].sum())


def feasible(inst: RangeInstance, x: np.ndarray, tol: float = 1e-6) -> bool:
    x = np.asarray(x).astype(bool)
    w = inst.width * x
    if w.sum() > inst.capacity + tol:
        return False
    for g, L in inst.min_per_group.items():
        if (x & (inst.group == g)).sum() < L:
            return False
    ws = np.bincount(inst.supplier, weights=w)
    return bool((ws <= inst.max_share_supplier * inst.capacity + tol).all())


# ------------------------------------------------------------------ exact
def build_mip(inst: RangeInstance) -> pe.ConcreteModel:
    n, K = inst.n, inst.neighbours.shape[1]
    m = pe.ConcreteModel()
    m.I = pe.RangeSet(0, n - 1)
    m.x = pe.Var(m.I, domain=pe.Binary)
    pairs = [(i, int(inst.neighbours[i, k]), k) for i in range(n) for k in range(K)
             if inst.tau > 0 and inst.neighbours[i, k] >= 0]
    m.P = pe.Set(initialize=[(i, j) for i, j, _ in pairs], dimen=2)
    m.y = pe.Var(m.P, bounds=(0, 1))
    um = unit_profit(inst)
    coef = {(i, j): inst.tau * inst.sim[i, k] * um[j] * inst.demand[i] for i, j, k in pairs}
    m.obj = pe.Objective(expr=sum(inst.profit[i] * m.x[i] for i in m.I) + sum(coef[p] * m.y[p] for p in m.P),
                         sense=pe.maximize)
    m.space = pe.Constraint(expr=sum(inst.width[i] * m.x[i] for i in m.I) <= inst.capacity)
    by_i: dict[int, list] = {}
    for (i, j) in m.P:
        by_i.setdefault(i, []).append((i, j))
    m.link = pe.ConstraintList()
    for (i, j) in m.P:
        m.link.add(m.y[i, j] <= m.x[j])
    m.once = pe.ConstraintList()
    for i, lst in by_i.items():
        m.once.add(sum(m.y[p] for p in lst) + m.x[i] <= 1)
    m.depth = pe.ConstraintList()
    for g, L in inst.min_per_group.items():
        m.depth.add(sum(m.x[i] for i in m.I if inst.group[i] == g) >= L)
    m.cap_s = pe.ConstraintList()
    for s in np.unique(inst.supplier):
        idx = [i for i in range(n) if inst.supplier[i] == s]
        if inst.width[idx].sum() > inst.max_share_supplier * inst.capacity:
            m.cap_s.add(sum(inst.width[i] * m.x[i] for i in idx) <= inst.max_share_supplier * inst.capacity)
    return m


def solve_exact(inst: RangeInstance, solver: str = "highs", time_limit: float = 30.0, mip_gap: float = 1e-4) -> dict:
    """solver: 'highs' (appsi_highs) or 'cbc'. Returns solution, objective, bound, gap and wall time."""
    t0 = time.perf_counter()
    m = build_mip(inst)
    build = time.perf_counter() - t0
    t1 = time.perf_counter()
    if solver == "highs":
        opt = pe.SolverFactory("appsi_highs")
        opt.config.time_limit = time_limit
        opt.config.mip_gap = mip_gap
        res = opt.solve(m)
        bound = getattr(res.problem, "upper_bound", None)
        status = str(res.solver.termination_condition)
    else:
        opt = pe.SolverFactory("cbc")
        opt.options["seconds"] = time_limit
        opt.options["ratioGap"] = mip_gap
        res = opt.solve(m, load_solutions=True, tee=False)
        bound = getattr(res.problem, "upper_bound", None)
        status = str(res.solver.termination_condition)
    solve = time.perf_counter() - t1
    x = np.array([round(pe.value(m.x[i])) if m.x[i].value is not None else 0 for i in range(inst.n)])
    obj = objective(inst, x)
    if bound is None or (isinstance(bound, float) and (math.isnan(bound) or math.isinf(bound))):
        bound = float("nan")
    gap = (bound - obj) / max(abs(obj), 1e-9) if bound == bound else float("nan")
    return {"solver": solver, "x": x, "objective": obj, "bound": bound, "gap": max(gap, 0.0) if gap == gap else gap,
            "build_s": build, "solve_s": solve, "status": status, "feasible": feasible(inst, x)}


# ------------------------------------------------------------------ heuristics
def _repair(inst: RangeInstance, x: np.ndarray) -> np.ndarray:
    """Drop lowest-density items until space and supplier caps hold (depth minima are re-added in greedy)."""
    x = x.copy()
    dens = inst.profit / inst.width
    while inst.width[x.astype(bool)].sum() > inst.capacity + 1e-9:
        idx = np.where(x == 1)[0]
        x[idx[np.argmin(dens[idx])]] = 0
    return x


def greedy(inst: RangeInstance) -> dict:
    """Marginal-gain greedy with the exact objective: seed the depth minima, then repeatedly add the item with the best marginal
    gain per unit width that keeps the shelf and supplier caps (gains for all candidates are computed in one vector pass)."""
    t0 = time.perf_counter()
    n = inst.n
    x = np.zeros(n, int)
    wsup = np.zeros(inst.supplier.max() + 1)
    cap_s = inst.max_share_supplier * inst.capacity
    used = 0.0
    ii, jj, v = _edges(inst) if inst.tau > 0 else (np.array([], int), np.array([], int), np.array([]))

    def can_add_mask():
        return (x == 0) & (used + inst.width <= inst.capacity + 1e-9) & (wsup[inst.supplier] + inst.width <= cap_s + 1e-9)

    def add(i):
        nonlocal used
        x[i] = 1; used += inst.width[i]; wsup[inst.supplier[i]] += inst.width[i]

    for g, L in inst.min_per_group.items():
        idx = [i for i in np.where(inst.group == g)[0]]
        idx.sort(key=lambda i: -inst.profit[i] / inst.width[i])
        c = 0
        for i in idx:
            if c >= L: break
            if can_add_mask()[i]:
                add(i); c += 1
    while True:
        mask = can_add_mask()
        if not mask.any(): break
        gain = inst.profit.copy()
        if len(ii):
            rec = np.zeros(n)
            np.maximum.at(rec, ii, v * x[jj])          # recovery each delisted item currently earns
            live = x[ii] == 0
            inc = np.maximum(0.0, v - rec[ii])[live]
            others = np.bincount(jj[live], weights=inc, minlength=n)
            gain = gain - rec + others
        ratio = np.where(mask, gain / inst.width, -np.inf)
        i = int(np.argmax(ratio))
        if ratio[i] <= 0: break
        add(i)
    return {"solver": "greedy", "x": x, "objective": objective(inst, x), "solve_s": time.perf_counter() - t0,
            "feasible": feasible(inst, x)}


def anneal(inst: RangeInstance, seed: int = 0, time_limit: float = 10.0, x0: np.ndarray | None = None, iters: int = 200000) -> dict:
    """Simulated annealing on swaps and flips with a feasibility check; geometric cooling; stops at time_limit or iters."""
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    n = inst.n
    x = (x0 if x0 is not None else greedy(inst)["x"]).copy()
    cur = objective(inst, x)
    best, best_x = cur, x.copy()
    T0 = max(cur / max(n, 1), 1e-6) * 0.5
    T1 = T0 * 1e-3
    for it in range(iters):
        if it % 256 == 0 and time.perf_counter() - t0 > time_limit:
            break
        T = T0 * (T1 / T0) ** (it / iters)
        y = x.copy()
        r = rng.random()
        if r < 0.5:  # swap one in, one out
            ins = np.where(y == 0)[0]; outs = np.where(y == 1)[0]
            if len(ins) == 0 or len(outs) == 0: continue
            y[rng.choice(ins)] = 1; y[rng.choice(outs)] = 0
        else:       # flip one
            i = rng.integers(n); y[i] ^= 1
        if not feasible(inst, y):
            continue
        v = objective(inst, y)
        if v >= cur or rng.random() < math.exp((v - cur) / T):
            x, cur = y, v
            if cur > best:
                best, best_x = cur, x.copy()
    return {"solver": "anneal", "x": best_x, "objective": best, "solve_s": time.perf_counter() - t0, "feasible": feasible(inst, best_x)}
