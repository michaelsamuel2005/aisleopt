"""Benchmarks and the scorecard against planted answers. `run_all(quick=True)` is small enough for CI; the full run takes several minutes."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import markdown as md, promo_model as pm, range_model as rm, replen as rp, testplans as tp
from .data import real_promo_instance, real_range_instance, twin_promo_instance, twin_range_instance


def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def bench_range_scaling(sizes, seeds, tl_exact=15.0, tl_sa=5.0, tau=0.6):
    rows = []
    for n in sizes:
        for sd in seeds:
            inst = twin_range_instance(n, sd, tau=tau)
            res = {}
            for sv in ("highs", "cbc"):
                r = rm.solve_exact(inst, sv, tl_exact)
                res[sv] = r
            res["greedy"] = rm.greedy(inst)
            res["anneal"] = rm.anneal(inst, seed=sd, time_limit=tl_sa, iters=150000)
            bound = np.nanmin([res[s]["bound"] for s in ("highs", "cbc") if res[s]["bound"] == res[s]["bound"]] or [np.nan])
            best = max(r["objective"] for r in res.values() if r["feasible"])
            for name, r in res.items():
                rows.append({"n": n, "seed": sd, "solver": name, "objective": r["objective"], "feasible": bool(r["feasible"]),
                             "gap_to_best_pct": 100 * (best - r["objective"]) / best,
                             "gap_to_bound_pct": (100 * (bound - r["objective"]) / bound) if bound == bound else None,
                             "solve_s": r["solve_s"], "build_s": r.get("build_s"), "status": r.get("status")})
            _log(f"range n={n} seed={sd} " + " ".join(f"{k}={v['objective']:.1f}/{v['solve_s']:.1f}s" for k, v in res.items()))
    return rows


def bench_range_planted(sizes, seeds):
    rows = []
    for n in sizes:
        for sd in seeds:
            inst = twin_range_instance(n, sd, tau=0.0)
            target = rm.objective(inst, inst.planted)
            out = {"n": n, "seed": sd, "planted_feasible": rm.feasible(inst, inst.planted)}
            for name, r in (("highs", rm.solve_exact(inst, "highs", 20)), ("cbc", rm.solve_exact(inst, "cbc", 20)),
                            ("greedy", rm.greedy(inst)), ("anneal", rm.anneal(inst, sd, 3, iters=60000))):
                out[name] = bool(r["objective"] >= target * (1 - 1e-6))
                out[name + "_gap_pct"] = 100 * (target - r["objective"]) / target
            rows.append(out)
    return rows


def bench_range_real():
    out = {}
    for cap in (0.35, 0.45, 0.55):
        for tau in (0.3, 0.6, 0.9):
            inst = real_range_instance(cap, tau)
            ex = rm.solve_exact(inst, "highs", 30)
            gr = rm.greedy(inst)
            sa = rm.anneal(inst, 0, 5, x0=gr["x"], iters=100000)
            # naive baseline: rank by profit per unit width and fill, ignoring substitution, depth and supplier caps
            order = np.argsort(-inst.profit / inst.width); used = 0; x = np.zeros(inst.n, int)
            for i in order:
                if used + inst.width[i] <= inst.capacity: x[i] = 1; used += inst.width[i]
            naive = rm.objective(inst, x)
            out[f"cap{cap}_tau{tau}"] = {"items_ranged": int(ex["x"].sum()), "of": inst.n, "exact": ex["objective"], "gap": ex["gap"],
                                         "greedy": gr["objective"], "anneal": sa["objective"], "naive_rank_and_fill": naive,
                                         "naive_feasible": rm.feasible(inst, x), "uplift_vs_naive_pct": 100 * (ex["objective"] - naive) / naive,
                                         "solve_s": ex["solve_s"]}
    return out


def bench_promo(seeds, sizes):
    out = {}
    real = real_promo_instance()
    m = pm.solve_mip(real, time_limit=30); g = pm.greedy(real)
    base = float((real.base * real.price[:, None] * real.margin_rate[:, None]).sum())
    out["real"] = {"mip_gain": m["objective"], "mip_gap": m["gap"], "greedy_gain": g["objective"], "baseline_profit": base,
                   "gain_pct_of_baseline": 100 * m["objective"] / base, "promos": int(m["y"].sum()), "mc": pm.monte_carlo(real, m["y"], 1000),
                   "violations": m["violations"], "solve_s": m["solve_s"]}
    rows = []
    for sd in seeds:
        t = twin_promo_instance(40, 52, sd)
        tru = pm.solve_mip(t, u=t.truth_uplift, time_limit=20)
        f = lambda y: pm.plan_value(t, y, t.truth_uplift)
        pt = pm.solve_mip(t, time_limit=20); pc = pm.solve_mip(t, u=pm.conservative(t), time_limit=20); gr = pm.greedy(t)
        rows.append({"seed": sd, "true_opt": tru["objective"], "point_regret_pct": 100 * (tru["objective"] - f(pt["y"])) / tru["objective"],
                     "conservative_regret_pct": 100 * (tru["objective"] - f(pc["y"])) / tru["objective"],
                     "greedy_regret_pct": 100 * (tru["objective"] - f(gr["y"])) / tru["objective"]})
    out["twin_regret"] = rows
    sc = []
    for P in sizes:
        t = twin_promo_instance(P, 52, 0)
        mm = pm.solve_mip(t, time_limit=30); gg = pm.greedy(t)
        sc.append({"items": P, "binaries": int(2 * P * 52), "mip_s": mm["solve_s"], "mip_gap": mm["gap"], "greedy_s": gg["solve_s"],
                   "greedy_gap_pct": 100 * (mm["objective"] - gg["objective"]) / mm["objective"]})
        _log(f"promo P={P} {sc[-1]}")
    out["scaling"] = sc
    return out


def bench_replen(reps, days):
    out = {"real": {}, "twin_planted": []}
    for cf in (0.7, 0.9, 1.15):
        c = rp.compare(rp.real_replen_instance(cap_factor=cf), reps=reps, days=days, carry=True)
        out["real"][f"capacity_{cf}"] = {k: v for k, v in c.items() if k not in ("levels_det", "levels_sp")}
        _log(f"replen cap {cf} diff {c['profit_diff']}")
    for sd in (1, 2, 3):
        t = rp.twin_replen_instance(10, sd)
        pl = rp.planted_levels(t, 2); sp = rp.solve_two_stage(t, 2, 4000, carry=False)
        out["twin_planted"].append({"seed": sd, "mean_abs_diff_units": float(np.abs(sp["S"] - pl).mean()), "max_abs_diff_units": float(np.abs(sp["S"] - pl).max()),
                                    "mean_level": float(pl.mean())})
    return out


def bench_markdown(seeds):
    out = {"elasticity": md.estimate_elasticity(), "twin": [], "real_lots": {}}
    for sd in seeds:
        t = md.twin_markdown_instance(sd)
        pp = md.planted_price(t); target = md.revenue(t, [pp] * t.T)
        n = md.solve_nlp(t); d = md.solve_dp(t, 400, 200)
        row = {"seed": sd, "e": t.e, "planted_price": pp, "planted_revenue": target,
               "nlp_gap_pct": 100 * (target - n["objective"]) / target, "nlp_s": n["solve_s"],
               "dp_gap_pct": 100 * (target - d["objective"]) / target, "dp_s": d["solve_s"]}
        for L in (4, 8, 16, 32):
            m = md.solve_mip(t, L); row[f"mip{L}_gap_pct"] = 100 * (target - m["objective"]) / target; row[f"mip{L}_s"] = m["solve_s"]
        out["twin"].append(row)
    lots = md.real_markdown_instances(20)
    gain, hold = [], []
    for l in lots:
        s = md.solve_nlp(l); hold_rev = md.revenue(l, [l.p0] * l.T)
        gain.append(100 * (s["objective"] - hold_rev) / hold_rev)
    out["real_lots"] = {"lots": len(lots), "mean_revenue_gain_vs_holding_full_price_pct": float(np.mean(gain)), "min": float(np.min(gain)), "max": float(np.max(gain))}
    return out


def bench_testplans():
    n = tp.ab_sample_size(0.05, 0.10)
    out = {"ab": {"baseline": 0.05, "mde_rel": 0.10, "n_per_arm": n, "type_I": tp.ab_simulate(0.05, 0.0, n, 4000), "power": tp.ab_simulate(0.05, 0.10, n, 4000)},
           "srm": [tp.srm_check([50500, 49500], [.5, .5]), tp.srm_check([52000, 48000], [.5, .5])],
           "store_trial": []}
    for pairs in (10, 20, 40):
        for eff in (0.0, 0.03, 0.05):
            out["store_trial"].append({"pairs": pairs, "true_lift": eff, "rejection_rate": tp.store_trial_power(pairs, eff, sims=120)})
    return out


def run_all(quick: bool = False, out_dir: str | Path = "outputs") -> dict:
    t0 = time.time(); out = {"quick": quick}
    sizes = [10, 25, 50] if quick else [10, 25, 50, 100, 250, 500, 1000, 2000]
    out["range_scaling"] = bench_range_scaling(sizes, [1] if quick else [1, 2], 5 if quick else 15, 1 if quick else 5)
    out["range_planted"] = bench_range_planted([20, 100] if quick else [20, 100, 500, 1000], [1, 2] if quick else [1, 2, 3])
    out["range_real"] = bench_range_real() if not quick else {}
    out["promo"] = bench_promo([0] if quick else range(6), [10] if quick else [10, 20, 40, 80])
    out["replen"] = bench_replen(10 if quick else 60, 14 if quick else 28)
    out["markdown"] = bench_markdown([0, 1] if quick else range(8))
    out["testplans"] = bench_testplans() if not quick else {}
    out["wall_s"] = time.time() - t0
    Path(out_dir).mkdir(exist_ok=True, parents=True)
    Path(out_dir, "results_quick.json" if quick else "results.json").write_text(json.dumps(out, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    return out
