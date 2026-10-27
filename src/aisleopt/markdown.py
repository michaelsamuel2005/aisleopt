"""Model 4: price and markdown path for a lot of stock that must clear over T periods (non-linear programme).

demand_t(p) = a_t * (p / p0)^(-e)         constant elasticity; a_t is the demand at the full price in period t
max  sum_t p_t s_t + v (I0 - sum_t s_t)    s_t <= demand_t(p_t),  sum_t s_t <= I0,  p_t >= p_{t+1} >= floor
Three solvers: SLSQP on the continuous problem (SciPy), dynamic programme on a fine price grid (the reference answer, exact for
the grid) and a MIP over L price levels that linearises the revenue curve (Pyomo + HiGHS).
The elasticity e is ESTIMATED on the real cereal data (within-product log-log regression with week effects and promotion controls).
It is an association from a shop's own price variation, not a randomised price test: treat it as an input to be tested, see the test plan.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyomo.environ as pe
from scipy.optimize import minimize

from .data import REAL_DIR


def estimate_elasticity(min_weeks: int = 20) -> dict:
    """Within-product regression of log units on log price. Controls: display, mailer and feature shares and week fixed effects.
    Standard error clustered by product. Returns the coefficient and a 95% interval."""
    pw = pd.read_csv(REAL_DIR / "product_week_promo.csv")
    d = pw[pw.units > 0].copy()
    d["lp"] = np.log(d.net_sales / d.units); d["lu"] = np.log(d.units)
    d = d[d.groupby("product_id").week.transform("size") >= min_weeks]
    W = pd.get_dummies(d.week, drop_first=True, dtype=float)
    X = pd.concat([d[["lp", "feat_share", "display_share", "mailer_share"]].reset_index(drop=True), W.reset_index(drop=True)], axis=1)
    y = d.lu.reset_index(drop=True)
    grp = d.product_id.reset_index(drop=True)
    Xd = X - X.groupby(grp).transform("mean"); yd = y - y.groupby(grp).transform("mean")
    A = Xd.values.astype(float); b = yd.values
    beta, *_ = np.linalg.lstsq(A, b, rcond=None)
    r = b - A @ beta
    XtXi = np.linalg.pinv(A.T @ A)
    meat = np.zeros((A.shape[1], A.shape[1]))
    for g in np.unique(grp):
        mk = (grp == g).values
        sg = A[mk].T @ r[mk]
        meat += np.outer(sg, sg)
    V = XtXi @ meat @ XtXi
    se = float(np.sqrt(V[0, 0]))
    return {"elasticity": float(-beta[0]), "se": se, "ci": (float(-beta[0] - 1.96 * se), float(-beta[0] + 1.96 * se)),
            "products": int(grp.nunique()), "rows": int(len(d))}


@dataclass
class MarkdownInstance:
    name: str
    p0: float
    cost: float
    floor: float
    salvage: float
    stock: float
    a: np.ndarray        # demand at full price per period
    e: float
    kind: str = "real"

    @property
    def T(self): return len(self.a)


def demand(inst, t, p):
    return inst.a[t] * (np.asarray(p) / inst.p0) ** (-inst.e)


def revenue(inst: MarkdownInstance, prices: np.ndarray) -> float:
    """Exact value of a price path: sell greedily in time order up to the stock; leftover earns salvage."""
    left = inst.stock; rev = 0.0
    for t, p in enumerate(prices):
        s = min(demand(inst, t, p), left); rev += p * s; left -= s
    return rev + inst.salvage * left


def solve_nlp(inst: MarkdownInstance, seed: int = 0, starts: int = 5) -> dict:
    t0 = time.perf_counter(); T = inst.T
    rng = np.random.default_rng(seed)

    def unpack(z): return z[:T], z[T:]
    def f(z): p, s = unpack(z); return -(np.dot(p, s) + inst.salvage * (inst.stock - s.sum()))
    cons = [{"type": "ineq", "fun": lambda z: np.array([demand(inst, t, z[t]) - z[T + t] for t in range(T)])},
            {"type": "ineq", "fun": lambda z: inst.stock - z[T:].sum()},
            {"type": "ineq", "fun": lambda z: z[:T - 1] - z[1:T]}]
    bnds = [(inst.floor, inst.p0)] * T + [(0, inst.stock)] * T
    best = None
    for k in range(starts):
        p0 = np.sort(rng.uniform(inst.floor, inst.p0, T))[::-1] if k else np.linspace(inst.p0, inst.floor, T)
        s0 = np.minimum(demand(inst, np.arange(T), p0), inst.stock / T)
        r = minimize(f, np.r_[p0, s0], method="SLSQP", bounds=bnds, constraints=cons, options={"maxiter": 300, "ftol": 1e-10})
        if r.success or best is None:
            val = revenue(inst, np.minimum(np.maximum(r.x[:T], inst.floor), inst.p0))
            if best is None or val > best[0]: best = (val, r.x[:T].copy())
    p = np.minimum.accumulate(np.clip(best[1], inst.floor, inst.p0))
    return {"solver": "slsqp", "prices": p, "objective": revenue(inst, p), "solve_s": time.perf_counter() - t0}


def solve_dp(inst: MarkdownInstance, levels: int = 400, stock_grid: int = 200) -> dict:
    """Backward recursion over (period, price index so far, remaining stock on a grid). The reference answer for the price grid."""
    t0 = time.perf_counter(); T = inst.T
    grid = np.linspace(inst.p0, inst.floor, levels)           # descending prices
    st = np.linspace(0, inst.stock, stock_grid)
    V = np.tile(inst.salvage * st, (levels + 1, 1))            # V[T]: salvage on leftover; extra row unused
    Vt = [None] * (T + 1)
    Vt[T] = np.tile(inst.salvage * st, (levels, 1))           # [price_idx_floor, stock]
    pol = [None] * T
    for t in range(T - 1, -1, -1):
        cur = np.zeros((levels, stock_grid)); ch = np.zeros((levels, stock_grid), int)
        dem = demand(inst, t, grid)
        # value of choosing price index j at period t with stock x: p_j*min(d_j,x) + Vnext[j, x - sales]
        val = np.full((levels, stock_grid), -1e18); 
        for j in range(levels):
            s = np.minimum(dem[j], st)
            xnext = st - s
            nxt = np.array([np.interp(xnext, st, Vt[t + 1][j])]).reshape(-1)
            val[j] = grid[j] * s + nxt
        # prices must not rise: index at t+1 >= index at t, so Vt[t][i] = max_{j>=i} val[j]
        rev_cummax = np.maximum.accumulate(val[::-1], axis=0)[::-1]
        arg = np.zeros((levels, stock_grid), int)
        for i in range(levels - 1, -1, -1):
            arg[i] = i if i == levels - 1 else np.where(val[i] >= rev_cummax[i + 1], i, arg[i + 1])
        Vt[t] = rev_cummax; pol[t] = arg
    x = inst.stock; i = 0; path = []
    for t in range(T):
        j = pol[t][i][int(np.argmin(np.abs(st - x)))]
        path.append(grid[j]); s = min(demand(inst, t, grid[j]), x); x -= s; i = j
    p = np.array(path)
    return {"solver": "dp", "prices": p, "objective": revenue(inst, p), "solve_s": time.perf_counter() - t0}


def solve_mip(inst: MarkdownInstance, levels: int = 10, time_limit: float = 30.0) -> dict:
    """Price on L levels (piecewise-constant revenue curve): z[t,l] picks a level; s[t,l] <= demand(p_l) z[t,l]; prices non-increasing."""
    t0 = time.perf_counter(); T = inst.T
    grid = np.linspace(inst.p0, inst.floor, levels)
    m = pe.ConcreteModel(); m.T = pe.RangeSet(0, T - 1); m.L = pe.RangeSet(0, levels - 1)
    m.z = pe.Var(m.T, m.L, domain=pe.Binary); m.s = pe.Var(m.T, m.L, bounds=(0, None))
    m.pick = pe.Constraint(m.T, rule=lambda m, t: sum(m.z[t, l] for l in m.L) == 1)
    m.cap = pe.Constraint(m.T, m.L, rule=lambda m, t, l: m.s[t, l] <= float(demand(inst, t, grid[l])) * m.z[t, l])
    m.stock = pe.Constraint(expr=sum(m.s[t, l] for t in m.T for l in m.L) <= inst.stock)
    m.mono = pe.Constraint(pe.RangeSet(0, T - 2), rule=lambda m, t: sum(l * m.z[t, l] for l in m.L) <= sum(l * m.z[t + 1, l] for l in m.L))
    m.obj = pe.Objective(expr=sum((float(grid[l]) - inst.salvage) * m.s[t, l] for t in m.T for l in m.L) + inst.salvage * inst.stock, sense=pe.maximize)
    opt = pe.SolverFactory("appsi_highs"); opt.config.time_limit = time_limit
    res = opt.solve(m)
    p = np.array([grid[int(np.argmax([pe.value(m.z[t, l]) for l in range(levels)]))] for t in range(T)])
    return {"solver": f"mip{levels}", "prices": p, "objective": revenue(inst, p), "solve_s": time.perf_counter() - t0,
            "status": str(res.solver.termination_condition)}


def real_markdown_instances(n: int = 20, T: int = 6, seed: int = 0) -> list[MarkdownInstance]:
    """One lot per top REAL product: real price, real weekly demand shape scaled to a lot; ASSUMED stock of 2.0x the full-price demand over
    the horizon, decaying demand (freshness) of 12% per period, salvage at 20% of cost, floor at 40% of price."""
    from .data import load_real_products
    est = estimate_elasticity()
    t = load_real_products().sort_values("units", ascending=False).head(n)
    out = []
    for _, r in t.iterrows():
        a = np.array([r.weekly_mean * 6.0 * 0.88 ** k for k in range(T)])
        out.append(MarkdownInstance(f"real_{int(r.product_id)}", float(r.price), float(r.price * (1 - r.margin_rate)), float(r.price * 0.4),
                                    float(0.2 * r.price * (1 - r.margin_rate)), float(2.0 * a.sum()), a, est["elasticity"], "real"))
    return out


def twin_markdown_instance(seed: int, T: int = 6, e: float | None = None) -> MarkdownInstance:
    rng = np.random.default_rng(seed)
    p0 = float(np.exp(rng.normal(1.3, 0.3)))
    e = float(e if e is not None else rng.uniform(1.3, 3.0))
    a = rng.uniform(20, 60) * 0.85 ** np.arange(T)
    return MarkdownInstance(f"twin_s{seed}", p0, p0 * 0.6, p0 * 0.4, p0 * 0.12, float(a.sum() * rng.uniform(1.5, 3.0)), a, e, "twin")


def planted_price(inst: MarkdownInstance) -> float:
    """Twin only. With constant elasticity e > 1 and demand shape a_t, revenue per unit of stock is maximised by ONE price for all periods
    (marginal revenue is equalised when s_t is proportional to a_t). That price is the stock-clearing price p0*(sum(a)/I0)^(1/e), or, if stock
    is plentiful, the price where marginal revenue equals the salvage value, v*e/(e-1); then clipped to [floor, p0]."""
    clear = inst.p0 * (inst.a.sum() / inst.stock) ** (1.0 / inst.e)
    pv = inst.salvage * inst.e / (inst.e - 1.0)
    return float(np.clip(max(clear, pv), inst.floor, inst.p0))
