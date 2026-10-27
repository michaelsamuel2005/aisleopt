"""Model 3: replenishment of a short-life line under uncertain demand.

Two-stage stochastic programme (first stage: order-up-to level S_i; second stage: sales in each demand scenario) against a
deterministic plan (order up to mean demand over the cover period), both scored in a SimPy discrete-event simulation with
FIFO shelf-life, delivery lead time and a shared shelf capacity.

REAL: weekly demand level and dispersion per product (cold-cereal series). ASSUMED: that the line is short-life, the shelf life,
lead time, unit cost, salvage = 0, the store scale factor and the day-of-week pattern. Cereal is not perishable; the demand shapes
are real, the perishability is a modelling assumption stated in the README.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pyomo.environ as pe
import simpy
from scipy import stats

from .data import ASSUMED, REAL_DIR, PRIVATE_LABEL_ID

DOW = np.array([0.85, 0.85, 0.9, 0.95, 1.1, 1.35, 1.0])  # ASSUMED weekly shape, mean 1.0
DOW = DOW / DOW.mean()


@dataclass
class ReplenInstance:
    name: str
    mean_day: np.ndarray      # mean units per day
    disp: np.ndarray          # negative-binomial dispersion k (var = mu + mu^2 / k); large k = Poisson-like
    price: np.ndarray
    cost: np.ndarray
    space: np.ndarray         # shelf space units per item
    capacity: float
    shelf_life: int = 3       # days
    lead: int = 1             # days between order and delivery
    kind: str = "real"

    @property
    def n(self): return len(self.mean_day)


def real_replen_instance(n: int = 12, scale: float = 6.0, cap_factor: float = 1.15) -> ReplenInstance:
    pw = pd.read_csv(REAL_DIR / "product_week_promo.csv")
    top = pw.groupby("product_id").units.sum().sort_values(ascending=False).head(n).index
    sub = pw[pw.product_id.isin(top)]
    mu_w = sub.groupby("product_id").units.mean().loc[top].values
    var_w = sub.groupby("product_id").units.var().loc[top].values
    k = np.clip(mu_w ** 2 / np.maximum(var_w - mu_w, 1e-6), 0.3, 50.0)    # REAL overdispersion of weekly units
    price = (sub.groupby("product_id").net_sales.sum() / sub.groupby("product_id").units.sum()).loc[top].values
    mf = sub.groupby("product_id").manufacturer_id.first().loc[top].values
    margin = np.where(mf == PRIVATE_LABEL_ID, ASSUMED["margin_private"], ASSUMED["margin_brand"])
    cost = price * (1 - margin)
    mean_day = mu_w * scale / 7.0
    space = np.ones(n)
    cap = float(cap_factor * (mean_day * 2.0).sum())
    return ReplenInstance("real_cereal_demand_shapes", mean_day, k, price, cost, space, cap)


def twin_replen_instance(n: int, seed: int, slack: bool = True) -> ReplenInstance:
    rng = np.random.default_rng(seed)
    mean_day = np.exp(rng.normal(1.6, 0.5, n))
    disp = rng.uniform(1.0, 6.0, n)
    price = np.exp(rng.normal(1.0, 0.3, n))
    cost = price * rng.uniform(0.5, 0.8, n)
    space = rng.uniform(0.8, 1.5, n)
    cap = 1e9 if slack else float(0.8 * (space * mean_day * 2).sum())
    return ReplenInstance(f"twin_n{n}_s{seed}", mean_day, disp, price, cost, space, cap, kind="twin")


def _nb_params(mu, k):
    return k, k / (k + mu)   # scipy nbinom(n, p)


def demand_scenarios(inst: ReplenInstance, cover_days: int, scenarios: int, seed: int) -> np.ndarray:
    """scenarios x n matrix of demand over the cover period (sum of daily negative binomials with the day-of-week shape)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((scenarios, inst.n))
    for d in range(cover_days):
        mu = inst.mean_day * DOW[d % 7]
        k = inst.disp
        out += rng.negative_binomial(k, k / (k + mu), size=(scenarios, inst.n))
    return out


def planted_levels(inst: ReplenInstance, cover_days: int) -> np.ndarray:
    """Twin only, shelf capacity slack: S* is the demand quantile at the critical ratio (p-c)/(p-v) with v = 0 (newsvendor).
    The cover demand is approximated by one negative binomial with the summed mean and the same dispersion (exact for equal
    day factors, close otherwise); the stochastic programme is scored against this."""
    mu = inst.mean_day * DOW[:cover_days].sum()
    k = inst.disp * cover_days
    cr = (inst.price - inst.cost) / inst.price
    return stats.nbinom.ppf(cr, k, k / (k + mu))


def deterministic_levels(inst: ReplenInstance, cover_days: int) -> np.ndarray:
    """Order up to mean demand over the cover period; scale down proportionally if the shelf cannot hold it."""
    S = inst.mean_day * DOW[:cover_days].sum()
    tot = (inst.space * S).sum()
    return S * min(1.0, inst.capacity / tot)


def solve_two_stage(inst: ReplenInstance, cover_days: int = 2, scenarios: int = 1000, seed: int = 11, time_limit: float = 60.0,
                    carry: bool = False) -> dict:
    """max E[ sum_i p_i * q_is - c_i * S_i + c_i * r_is ]
    s.t. q_is <= S_i, q_is <= D_is, sum_i space_i S_i <= capacity.            (first stage S_i, second stage q_is)
    carry=True adds the value of carry-over: r_is <= S_i - q_is, r_is <= D'_is  (unsold units that sell in the next cycle displace an
    order of cost c_i, because the line has a shelf life longer than one cycle). carry=False is the classic single-cycle newsvendor,
    whose closed-form answer is the planted answer in the twin. LP, solved with HiGHS."""
    t0 = time.perf_counter()
    D = demand_scenarios(inst, cover_days, scenarios, seed)
    n = inst.n
    m = pe.ConcreteModel()
    m.I = pe.RangeSet(0, n - 1); m.S_ = pe.RangeSet(0, scenarios - 1)
    m.S = pe.Var(m.I, bounds=(0, None))
    m.q = pe.Var(m.I, m.S_, bounds=(0, None))
    D2 = demand_scenarios(inst, cover_days, scenarios, seed + 1) if carry else None
    if carry:
        m.r = pe.Var(m.I, m.S_, bounds=(0, None))
        m.c1 = pe.Constraint(m.I, m.S_, rule=lambda m, i, s: m.r[i, s] <= m.S[i] - m.q[i, s])
        m.c2 = pe.Constraint(m.I, m.S_, rule=lambda m, i, s: m.r[i, s] <= float(D2[s, i]))
    m.obj = pe.Objective(expr=sum(inst.price[i] * sum(m.q[i, s] for s in m.S_) / scenarios - inst.cost[i] * m.S[i]
                                  + (inst.cost[i] * sum(m.r[i, s] for s in m.S_) / scenarios if carry else 0) for i in m.I), sense=pe.maximize)
    m.a = pe.Constraint(m.I, m.S_, rule=lambda m, i, s: m.q[i, s] <= m.S[i])
    m.b = pe.Constraint(m.I, m.S_, rule=lambda m, i, s: m.q[i, s] <= float(D[s, i]))
    m.cap = pe.Constraint(expr=sum(inst.space[i] * m.S[i] for i in m.I) <= inst.capacity)
    build = time.perf_counter() - t0
    opt = pe.SolverFactory("appsi_highs"); opt.config.time_limit = time_limit
    t1 = time.perf_counter(); res = opt.solve(m); solve = time.perf_counter() - t1
    S = np.array([pe.value(m.S[i]) for i in m.I])
    return {"S": S, "objective": float(pe.value(m.obj)), "build_s": build, "solve_s": solve, "scenarios": scenarios,
            "status": str(res.solver.termination_condition)}


# ------------------------------------------------------------------ SimPy
def simulate(inst: ReplenInstance, S: np.ndarray, days: int = 28, reps: int = 100, seed: int = 0, warm: int = 4) -> dict:
    """Discrete-event simulation. Each morning: expire stock, receive the order placed `lead` days earlier. Customers (units)
    arrive through the day as a Poisson stream whose daily count is negative binomial; each takes one unit, oldest first.
    At close the store orders up to S (inventory position). Common random numbers: replication r uses seed + r for every policy."""
    S = np.maximum(np.round(S), 0).astype(int)
    prof, fill, waste = [], [], []
    for r in range(reps):
        rng = np.random.default_rng(seed + r)
        env = simpy.Environment()
        n = inst.n
        batches = [[] for _ in range(n)]          # list of [expiry_day, qty], oldest first
        pipeline = [[0] * n for _ in range(days + inst.lead + 2)]
        stats_ = {"rev": 0.0, "cost": 0.0, "sold": 0, "dem": 0, "waste": 0, "wunits_cost": 0.0}
        counted = {"on": False}
        draws = np.zeros((days, n), int)
        for d in range(days):
            mu = inst.mean_day * DOW[d % 7]
            draws[d] = rng.negative_binomial(inst.disp, inst.disp / (inst.disp + mu))

        def customer(env, i, day):
            if counted["on"]: stats_["dem"] += 1
            for b in batches[i]:
                if b[1] > 0:
                    b[1] -= 1
                    if counted["on"]:
                        stats_["sold"] += 1; stats_["rev"] += inst.price[i]
                    return

        def day_proc(env):
            for d in range(days):
                counted["on"] = d >= warm
                for i in range(n):
                    kept = []
                    for b in batches[i]:
                        if b[0] <= d:
                            if counted["on"]:
                                stats_["waste"] += b[1]; stats_["wunits_cost"] += b[1] * inst.cost[i]
                        else:
                            kept.append(b)
                    batches[i] = kept
                    q = pipeline[d][i]
                    if q:
                        batches[i].append([d + inst.shelf_life, q])
                events = []
                for i in range(n):
                    for _ in range(int(draws[d, i])):
                        events.append((rng.random(), i))
                events.sort()
                t_prev = 0.0
                for t, i in events:
                    yield env.timeout(t - t_prev); t_prev = t
                    customer(env, i, d)
                yield env.timeout(1.0 - t_prev)
                for i in range(n):
                    inv = sum(b[1] for b in batches[i]) + sum(pipeline[dd][i] for dd in range(d + 1, d + inst.lead + 1))
                    order = max(0, int(S[i]) - inv)
                    if order:
                        pipeline[d + inst.lead][i] += order
                        if counted["on"]: stats_["cost"] += order * inst.cost[i]
        # day 0 starts with a full shelf at the order-up-to level
        for i in range(n):
            batches[i].append([inst.shelf_life, int(S[i])])
        env.process(day_proc(env)); env.run()
        prof.append(stats_["rev"] - stats_["cost"])
        fill.append(stats_["sold"] / max(stats_["dem"], 1))
        waste.append(stats_["waste"] / max(stats_["sold"] + stats_["waste"], 1))
    return {"profit": np.array(prof), "fill": np.array(fill), "waste": np.array(waste)}


def ci(x: np.ndarray) -> tuple[float, float, float]:
    m = float(np.mean(x)); h = 1.96 * float(np.std(x, ddof=1)) / np.sqrt(len(x))
    return m, m - h, m + h


def compare(inst: ReplenInstance, reps: int = 100, days: int = 28, scenarios: int = 1000, seed: int = 0, carry: bool = True) -> dict:
    cover = inst.lead + 1
    sp = solve_two_stage(inst, cover, scenarios, carry=carry)
    det = deterministic_levels(inst, cover)
    a = simulate(inst, det, days, reps, seed)
    b = simulate(inst, sp["S"], days, reps, seed)
    d = b["profit"] - a["profit"]
    out = {"deterministic": {k: ci(v) for k, v in a.items()}, "stochastic": {k: ci(v) for k, v in b.items()},
           "profit_diff": ci(d), "levels_det": det.round(1).tolist(), "levels_sp": sp["S"].round(1).tolist(),
           "lp_solve_s": sp["solve_s"], "scenarios": scenarios, "reps": reps, "days": days}
    return out
