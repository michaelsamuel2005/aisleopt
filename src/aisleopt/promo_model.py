"""Model 2: 52-week promotion calendar as an integer programme, with a greedy repair heuristic and Monte Carlo of the uplift.

y[p,t,k] = 1 if item p gets promotion type k (0 mailer/feature, 1 display) in week t.
gain(p,t,k) = base[p,t] * price[p] * ( exp(u[k,p]) * (margin[p] - c) - margin[p] )     (price funding c on every promoted unit)
max  sum gain * y   s.t.  at most `slots` promoted items per week; at most half of them displays; at least `min_gap` weeks between
promotions of one item; at most `max_promos_item` per item; one type per item-week.
Uplifts are log-linear coefficients (REAL category estimates in the real instance; noisy estimates of known truth in the twin).
"""
from __future__ import annotations

import time

import numpy as np
import pyomo.environ as pe

from .data import PromoInstance


def gains(inst: PromoInstance, u: np.ndarray | None = None, dip: float = 0.0) -> np.ndarray:
    """K x P x T matrix of profit gain versus no promotion. dip = share of the extra units pulled out of the next week (assumed 0:
    the real data shows no dip, the week after a promotion is higher)."""
    u = inst.uplift if u is None else u
    P, T = inst.base.shape
    g = np.zeros((u.shape[0], P, T))
    for k in range(u.shape[0]):
        e = np.exp(u[k])[:, None]
        g[k] = inst.base * inst.price[:, None] * (e * (inst.margin_rate[:, None] - inst.cost_rate) - inst.margin_rate[:, None])
        if dip > 0:
            loss = dip * inst.base * (e - 1) * (inst.price * inst.margin_rate)[:, None]
            g[k][:, :-1] -= loss[:, :-1]      # the extra units are taken out of the following week
    return g


def plan_value(inst: PromoInstance, y: np.ndarray, u: np.ndarray | None = None, dip: float = 0.0) -> float:
    return float((gains(inst, u, dip) * y).sum())


def check_plan(inst: PromoInstance, y: np.ndarray) -> list[str]:
    """Return a list of violated rules (empty = feasible)."""
    bad = []
    any_k = y.sum(0)                                  # P x T
    if (any_k > 1).any(): bad.append("two types in one item-week")
    if (any_k.sum(0) > inst.slots_per_week).any(): bad.append("weekly slots")
    if (y[1].sum(0) > max(1, inst.slots_per_week // 2)).any(): bad.append("display slots")
    if (any_k.sum(1) > inst.max_promos_item).any(): bad.append("per-item cap")
    P, T = any_k.shape
    for p in range(P):
        for t in range(T):
            if any_k[p, t:t + inst.min_gap].sum() > 1: bad.append("min gap"); break
    return bad


def solve_mip(inst: PromoInstance, u: np.ndarray | None = None, time_limit: float = 30.0, mip_gap: float = 1e-3, dip: float = 0.0) -> dict:
    t0 = time.perf_counter()
    K, P, T = 2, inst.P, inst.T
    g = gains(inst, u, dip)
    m = pe.ConcreteModel()
    m.K = pe.RangeSet(0, K - 1); m.P = pe.RangeSet(0, P - 1); m.T = pe.RangeSet(0, T - 1)
    m.y = pe.Var(m.K, m.P, m.T, domain=pe.Binary)
    m.obj = pe.Objective(expr=sum(float(g[k, p, t]) * m.y[k, p, t] for k in m.K for p in m.P for t in m.T if g[k, p, t] > 0),
                         sense=pe.maximize)
    m.one = pe.ConstraintList(); m.slot = pe.ConstraintList(); m.disp = pe.ConstraintList(); m.gap = pe.ConstraintList(); m.cap = pe.ConstraintList()
    for p in range(P):
        for t in range(T):
            m.one.add(sum(m.y[k, p, t] for k in range(K)) <= 1)
            m.gap.add(sum(m.y[k, p, s] for k in range(K) for s in range(t, min(T, t + inst.min_gap))) <= 1)
        m.cap.add(sum(m.y[k, p, t] for k in range(K) for t in range(T)) <= inst.max_promos_item)
    for t in range(T):
        m.slot.add(sum(m.y[k, p, t] for k in range(K) for p in range(P)) <= inst.slots_per_week)
        m.disp.add(sum(m.y[1, p, t] for p in range(P)) <= max(1, inst.slots_per_week // 2))
    build = time.perf_counter() - t0
    opt = pe.SolverFactory("appsi_highs"); opt.config.time_limit = time_limit; opt.config.mip_gap = mip_gap
    t1 = time.perf_counter(); res = opt.solve(m); solve = time.perf_counter() - t1
    y = np.array([[[round(pe.value(m.y[k, p, t])) if m.y[k, p, t].value is not None else 0 for t in range(T)] for p in range(P)] for k in range(K)])
    obj = plan_value(inst, y, u, dip)
    bound = getattr(res.problem, "upper_bound", float("nan"))
    return {"solver": "highs", "y": y, "objective": obj, "bound": bound, "gap": max(0.0, (bound - obj) / max(abs(obj), 1e-9)) if bound == bound else float("nan"),
            "build_s": build, "solve_s": solve, "status": str(res.solver.termination_condition), "violations": check_plan(inst, y)}


def greedy(inst: PromoInstance, u: np.ndarray | None = None, dip: float = 0.0) -> dict:
    """Take (type, item, week) triples in order of gain; keep a triple if it breaks no rule."""
    t0 = time.perf_counter()
    g = gains(inst, u, dip)
    K, P, T = g.shape
    y = np.zeros((K, P, T), int)
    wk = np.zeros(T, int); wkd = np.zeros(T, int); cnt = np.zeros(P, int); last = np.full((P, T + 2 * inst.min_gap), 0)
    occupied = np.zeros((P, T), bool)
    order = np.dstack(np.unravel_index(np.argsort(-g, axis=None), g.shape))[0]
    for k, p, t in order:
        if g[k, p, t] <= 0: break
        if wk[t] >= inst.slots_per_week or cnt[p] >= inst.max_promos_item: continue
        if k == 1 and wkd[t] >= max(1, inst.slots_per_week // 2): continue
        lo, hi = max(0, t - inst.min_gap + 1), min(T, t + inst.min_gap)
        if occupied[p, lo:hi].any(): continue
        y[k, p, t] = 1; wk[t] += 1; cnt[p] += 1; occupied[p, t] = True
        if k == 1: wkd[t] += 1
    return {"solver": "greedy", "y": y, "objective": plan_value(inst, y, u, dip), "solve_s": time.perf_counter() - t0,
            "violations": check_plan(inst, y)}


def monte_carlo(inst: PromoInstance, y: np.ndarray, draws: int = 2000, seed: int = 0, dip: float = 0.0) -> dict:
    """Distribution of the plan's profit gain when the uplifts are drawn from N(estimate, se^2) (log scale)."""
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for d in range(draws):
        u = inst.uplift + rng.normal(size=inst.uplift.shape) * inst.uplift_se
        out[d] = plan_value(inst, y, u, dip)
    return {"mean": float(out.mean()), "p05": float(np.quantile(out, 0.05)), "p50": float(np.quantile(out, 0.5)),
            "p95": float(np.quantile(out, 0.95)), "prob_positive": float((out > 0).mean())}


def conservative(inst: PromoInstance, z: float = 1.0) -> np.ndarray:
    """Uplift shaded down by z standard errors: the planner picks the best of many noisy estimates (winner's curse)."""
    return inst.uplift - z * inst.uplift_se
