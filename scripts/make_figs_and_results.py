"""Reads outputs/results.json and writes docs/RESULTS.md and docs/fig_scaling.png."""
import json, sys
from pathlib import Path
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

root = Path(__file__).resolve().parents[1]
r = json.loads((root / "outputs" / "results.json").read_text())
d = pd.DataFrame(r["range_scaling"])
g = d.groupby(["n", "solver"]).agg(gap=("gap_to_best_pct", "mean"), t=("solve_s", "mean")).reset_index()
fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), constrained_layout=True)
col = {"highs": "#1b6ca8", "cbc": "#d97706", "greedy": "#6b7280", "anneal": "#15803d"}
for s, c in col.items():
    q = g[g.solver == s]
    ax[0].plot(q.n, q.t, marker="o", color=c, label=s); ax[1].plot(q.n, q.gap + 1e-3, marker="o", color=c, label=s)
ax[0].set_xscale("log"); ax[0].set_yscale("log"); ax[0].set_xlabel("products"); ax[0].set_ylabel("solve time (s)"); ax[0].set_title("Range model: time vs size")
ax[1].set_xscale("log"); ax[1].set_yscale("log"); ax[1].set_xlabel("products"); ax[1].set_ylabel("gap to best known (%, +0.001)"); ax[1].set_title("Range model: quality vs size")
ax[0].legend(frameon=False)
for a in ax: a.spines[["top", "right"]].set_visible(False)
fig.savefig(root / "docs" / "fig_scaling.png", dpi=160)

L = ["# Results (generated from outputs/results.json; do not edit by hand)\n",
     f"Full run wall time {r['wall_s']:.0f} s. Twin instances are simulated; the real instance is the cold-cereal extract.\n",
     "## Range model: scaling on the twin (tau = 0.6, mean of 2 seeds)\n",
     "| products | solver | gap to best known % | solve s |", "|---|---|---|---|"]
for _, x in g.iterrows(): L.append(f"| {int(x.n)} | {x.solver} | {x.gap:.3f} | {x.t:.2f} |")
L += ["\n## Range model: planted optimum (tau = 0), all methods\n", "| n | seed | highs | cbc | greedy | anneal |", "|---|---|---|---|---|---|"]
for x in r["range_planted"]: L.append(f"| {x['n']} | {x['seed']} | {x['highs']} | {x['cbc']} | {x['greedy']} | {x['anneal']} |")
L += ["\n## Range model: real cold-cereal catalogue (274 products with sales)\n", "| shelf share | substitution | ranged | exact | greedy | anneal | naive rank-and-fill | exact vs naive % |", "|---|---|---|---|---|---|---|---|"]
for k, v in r["range_real"].items():
    cap, tau = k.replace("cap", "").split("_tau")
    L.append(f"| {cap} | {tau} | {v['items_ranged']} | {v['exact']:.1f} | {v['greedy']:.1f} | {v['anneal']:.1f} | {v['naive_rank_and_fill']:.1f} | {v['uplift_vs_naive_pct']:.2f} |")
p = r["promo"]
L += ["\n## Promotion calendar\n", f"Real instance (top 40 products, 52 weeks): {p['real']['promos']} promotions, gain {p['real']['mip_gain']:.1f} on a baseline profit of {p['real']['baseline_profit']:.0f} ({p['real']['gain_pct_of_baseline']:.1f}%), MIP gap {p['real']['mip_gap']:.4f}, "
      f"Monte Carlo 5th to 95th percentile {p['real']['mc']['p05']:.0f} to {p['real']['mc']['p95']:.0f}.\n",
      "Twin regret against the plan built on the TRUE uplifts:\n", "| seed | point-estimate plan % | shaded by 1 se % | greedy % |", "|---|---|---|---|"]
for x in p["twin_regret"]: L.append(f"| {x['seed']} | {x['point_regret_pct']:.1f} | {x['conservative_regret_pct']:.1f} | {x['greedy_regret_pct']:.1f} |")
L += ["\nScaling (twin, 52 weeks):\n", "| items | binaries | MIP s | MIP gap | greedy s | greedy shortfall % |", "|---|---|---|---|---|---|"]
for x in p["scaling"]: L.append(f"| {x['items']} | {x['binaries']} | {x['mip_s']:.2f} | {x['mip_gap']:.4f} | {x['greedy_s']:.3f} | {x['greedy_gap_pct']:.2f} |")
rp = r["replen"]
L += ["\n## Replenishment (SimPy, paired replications, 28 days)\n", "| shelf capacity vs 2 days of demand | profit gain of the stochastic plan | 95% interval | fill det / SP | waste det / SP |", "|---|---|---|---|---|"]
for k, v in rp["real"].items():
    L.append(f"| {k.split('_')[1]} | {v['profit_diff'][0]:.1f} | {v['profit_diff'][1]:.1f} to {v['profit_diff'][2]:.1f} | {v['deterministic']['fill'][0]:.3f} / {v['stochastic']['fill'][0]:.3f} | {v['deterministic']['waste'][0]:.3f} / {v['stochastic']['waste'][0]:.3f} |")
L += ["\nPlanted newsvendor levels versus the LP (twin): " + "; ".join(f"seed {x['seed']}: mean abs diff {x['mean_abs_diff_units']:.1f} units (max {x['max_abs_diff_units']:.0f}) on levels averaging {x['mean_level']:.1f}" for x in rp["twin_planted"])]
m = r["markdown"]
L += ["\n## Markdown\n", f"Elasticity estimated on the real data: {m['elasticity']['elasticity']:.2f} (95% interval {m['elasticity']['ci'][0]:.2f} to {m['elasticity']['ci'][1]:.2f}; {m['elasticity']['products']} products, {m['elasticity']['rows']} product-weeks). "
      f"Real lots: optimal path vs holding full price, mean revenue +{m['real_lots']['mean_revenue_gain_vs_holding_full_price_pct']:.1f}% (range {m['real_lots']['min']:.1f} to {m['real_lots']['max']:.1f}) with an ASSUMED stock of 2x full-price demand.\n",
      "Twin, shortfall against the planted revenue (%):\n", "| seed | e | NLP | DP | MIP 4 | MIP 8 | MIP 16 | MIP 32 |", "|---|---|---|---|---|---|---|---|"]
for x in m["twin"]: L.append(f"| {x['seed']} | {x['e']:.2f} | {x['nlp_gap_pct']:.3f} | {x['dp_gap_pct']:.3f} | {x['mip4_gap_pct']:.3f} | {x['mip8_gap_pct']:.3f} | {x['mip16_gap_pct']:.3f} | {x['mip32_gap_pct']:.3f} |")
t = r["testplans"]
L += ["\n## Test plans\n", f"A/B: baseline {t['ab']['baseline']:.0%}, relative lift {t['ab']['mde_rel']:.0%}: {t['ab']['n_per_arm']:,} per arm; simulated type I {t['ab']['type_I']:.3f}, power {t['ab']['power']:.3f}.\n",
      "Matched-store trial (simulated panels, 26 pre-weeks, 8 post-weeks, 6% weekly noise): share of trials that reject.\n", "| pairs | true lift | rejection rate |", "|---|---|---|"]
for x in t["store_trial"]: L.append(f"| {x['pairs']} | {x['true_lift']:.0%} | {x['rejection_rate']:.2f} |")
(root / "docs" / "RESULTS.md").write_text("\n".join(L) + "\n")
print("ok")
