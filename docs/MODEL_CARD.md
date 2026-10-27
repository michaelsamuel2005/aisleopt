# Model card: aisleopt v0.1

**Intended use.** Show how retail range, promotion, replenishment and markdown decisions can be formulated, solved, simulated, scored against a planted answer and handed over for testing. A portfolio and learning project. **Not for operational use without data from the retailer and a test.**

**Data.** Real: The Complete Journey cold-cereal extract (US, 2017, CC0). Simulated: seeded twins. Assumed: margins, widths, substitution rate, promotion funding, shelf life, lead time, salvage, overstock (all listed in the README).

**Method and known limits.**
* Range: demand transfer is one-step to the best ranged neighbour in the same sub-category (five nearest by price); no cross-category effects, no space elasticity (sales do not rise with more facings), no planogram geometry.
* Promotion: log-linear uplift with category-level coefficients, the same for every product; no cannibalisation across products beyond the slot limit, no pull-forward (the real data shows none), no stock-outs.
* Replenishment: independent items, one shared shelf limit, order-up-to policy, FIFO, shelf life; demand is negative binomial with dispersion estimated from weekly data, the day-of-week shape assumed.
* Markdown: constant elasticity, one lot, monotone price path; elasticity estimated from observational price variation (confounding is possible).
* Heuristics are compared on the model's own objective, not on a retailer's profit.

**Evaluation.** Planted-optimum recovery, exact-versus-heuristic gaps, paired simulation intervals, regret under noisy estimates. Tests: 34, run in CI on push.

**Risks.** Using the US numbers as UK effects; treating the elasticity as causal; reading a Monte Carlo interval as model uncertainty (it covers uplift noise only). The memos say what to test before acting.

**Reproducibility.** Seeds on every generator and solver; settings and library versions in each JSON output; solver time limits recorded.
