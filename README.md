# aisleopt

Four retail decision models, built as an operational researcher would build them: an exact method, a heuristic, a simulation to judge them, and a written recommendation a buyer can act on. Each is run on **real grocery data** and on a **simulated twin that has the right answer planted in it**, so the methods are scored rather than admired.

| Decision | Model | Methods compared |
|---|---|---|
| Which products to range, in how much shelf space | Integer programme with demand transfer to substitutes (Pyomo) | HiGHS, CBC, marginal-gain greedy, simulated annealing |
| Which products to promote in which of 52 weeks | Integer programme with slot, spacing and frequency rules | HiGHS, greedy, Monte Carlo on the uplift |
| How much to stock of a short-life line | Two-stage stochastic programme (LP, HiGHS) | Mean-demand plan, scored in a SimPy discrete-event simulation |
| How to mark a lot down | Non-linear programme in price | SLSQP, dynamic programme, MIP on 4 to 32 price levels |

Also in the package: A/B test design (sample size, sample-ratio-mismatch check, guardrail non-inferiority), a matched-store trial for physical tests (matching, difference-in-differences, power), a command line with validated inputs and bounded run time, a model card, and four one-page decision memos.

## What is real, simulated, assumed, and not known

**Real.** The cold-cereal category of *The Complete Journey* (84.51°, a US grocery retailer, CC0, 2017, 2,469 households): 565 products appear, 274 sold at least one unit, 52 weeks, 10 manufacturers (one is the retailer's private label). Product-week units, net sales, feature, display and mailer shares, and the category promotion coefficients come from the same extract used in my basketlens project. **This is American data from 2017 and a sample of households. It is not Sainsbury's, Nectar or UK data.**

**Simulated.** The twin: catalogues of 10 to 2,000 products, promotion panels, demand streams, markdown lots and store panels, generated from a seed. Where an optimum can be planted it is (see below), so a method's answer can be marked right or wrong.

**Assumed (not in the data; every one is a named constant or parameter).** Gross margin (28% brand, 38% private label), shelf width per product, the share of a delisted item's demand that moves to a substitute (0.6 by default, 0.3 to 0.9 tested; basketlens also assumed this), promotion price funding (18%), that the replenishment line is short-life (3 days; cereal is not), lead time (1 day), the day-of-week pattern, store scale, salvage value, stock of twice the full-price demand for the markdown lots, and a 12% weekly demand decay.

**Not known / not tested.** No store-level data, no cost data, no real shelf-space or planogram data, no UK price or promotion history. The price elasticity is an association from the shop's own price variation (1.32, 95% interval 1.16 to 1.48), not a price experiment. Nothing here has been run against Sainsbury's systems or people. The recommendations are what the models say on public US data and labelled assumptions; the test plans exist because the next step is to test them.

## Planted answers

* **Range (tau = 0):** the planted set fills the shelf exactly and every planted item earns more profit per unit of width than every other item, so it also solves the linear relaxation; a feasible solution that reaches the relaxation bound is optimal. All four methods recover it on 12 of 12 instances (20 to 1,000 products). This case is easy by construction; the harder comparison (tau = 0.6, no planted answer) is the gap table.
* **Replenishment:** with the shelf slack, the optimal order-up-to level is the newsvendor quantile at the critical ratio. The stochastic programme matches it within 0 to 1 unit on levels near 7.
* **Markdown:** with constant elasticity above 1, one price for all periods is optimal (marginal revenue is equalised when sales follow the demand shape). SLSQP reaches it to 0.000%.
* **Promotion:** the twin knows the true uplifts; the planner sees noisy estimates, and regret is measured against the plan built on the truth.

## Headline results (full tables in `docs/RESULTS.md`, produced by `aisleopt bench`)

* **Range, scale.** HiGHS solves 2,000 products (about 12,000 variables with substitution) to a proven gap under 0.01% in a mean of 2.6 s, CBC in 6.5 s. Greedy takes 0.17 s and is 0.8% to 12% short of optimal across the 16 instances (0.8% to 9% averaged by size). Simulated annealing (5 s) is 0% to 1.6% short and is not better than the greedy start at 1,000 and 2,000 products. On this structure the exact solvers win; the heuristics are the fallback when side constraints make the model too large or non-linear.
* **Range, real catalogue.** The exact answer ranges 96 to 151 of 274 products depending on shelf share, in under 2 s. It beats a rank-by-profit-density fill by 0.15% to 5.9%; the advantage grows with the substitution rate, because the naive fill ignores where delisted demand goes. Greedy is within 0.65% of optimal.
* **Promotion.** On the real top 40 products the plan holds 156 promotions and adds 4.4% to modelled profit (5th to 95th percentile of the uplift uncertainty: 175.7 to 250.3 on a gain of 206; this interval covers uplift noise only, not model error). On the twin, noisy uplift estimates cost 3% to 29% of the achievable gain, and shading the estimates down by one standard error made it worse (8% to 42%), so I do not recommend that fix.
* **Replenishment.** The stochastic plan earns more only when the shelf is tight: +9.5 over 28 days at 70% shelf (95% interval 5.7 to 13.3, about 1.4%), no detectable difference at 90%, and slightly worse at 115% (−4.4, interval −8.4 to −0.4). A mean-demand plan is hard to beat when space is plentiful.
* **Markdown.** The MIP's error falls from 0.04% to 2.7% on 4 price levels to at most 0.1% on 32; DP is within 0.08% and SLSQP exact. On 20 real lots with assumed overstock, the optimal path adds 3.4% to 5.2% revenue over holding the full price.
* **Tests.** An A/B test for a 5% to 5.5% conversion lift needs 31,234 per arm (simulated type I 0.052, power 0.804). A matched-store trial with 20 pairs detects a 5% lift 95% of the time and a 3% lift 60% of the time; 40 pairs detect 3% 92% of the time; false-positive rates are 3% to 5%.

## Run it

```bash
pip install -e ".[dev]"          # also: apt-get install coinor-cbc  (for the CBC comparison)
pytest -q -m "not slow"          # 33 tests; add "-m slow" for the quick benchmark
aisleopt range --source real --time-limit-s 30
aisleopt range --source csv --csv my_catalogue.csv --capacity 400
aisleopt promo | replen | markdown
aisleopt bench                   # the full scorecard, about 5 minutes -> outputs/results.json
python scripts/make_figs_and_results.py
```

Inputs are validated (pydantic for settings; schema, sign and range checks for catalogues), every run takes a seed and a time limit (at most 600 s per solve), and the JSON result records the versions, settings and a hash of them. A catalogue CSV needs the columns `product_id, demand, price, margin_rate, width, group, supplier`.

## What has not been run

CI is written (`.github/workflows/ci.yml`) but has not run on GitHub; the tests and benchmark ran locally on Python 3.13. Gurobi and CPLEX are not used (HiGHS and CBC are open source). There is no live deployment, no scheduler, and no comparison to a retailer's actual plans.

## Layout

`src/aisleopt/` data, range_model, promo_model, replen, markdown, testplans, bench, cli · `tests/` 34 tests · `docs/` MODEL_CARD, DECISION_MEMOS, RESULTS, fig_scaling.png · `data/real/` the real extract (CC0).
