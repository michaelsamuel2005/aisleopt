# Results (generated from outputs/results.json; do not edit by hand)

Full run wall time 295 s. Twin instances are simulated; the real instance is the cold-cereal extract.

## Range model: scaling on the twin (tau = 0.6, mean of 2 seeds)

| products | solver | gap to best known % | solve s |
|---|---|---|---|
| 10 | anneal | 0.000 | 5.01 |
| 10 | cbc | 0.000 | 0.04 |
| 10 | greedy | 1.613 | 0.00 |
| 10 | highs | 0.000 | 0.04 |
| 25 | anneal | 0.000 | 5.01 |
| 25 | cbc | 0.000 | 0.07 |
| 25 | greedy | 9.237 | 0.00 |
| 25 | highs | 0.000 | 0.04 |
| 50 | anneal | 0.265 | 5.02 |
| 50 | cbc | 0.000 | 0.29 |
| 50 | greedy | 6.832 | 0.00 |
| 50 | highs | 0.000 | 0.17 |
| 100 | anneal | 0.038 | 5.01 |
| 100 | cbc | 0.000 | 0.21 |
| 100 | greedy | 4.350 | 0.00 |
| 100 | highs | 0.000 | 0.17 |
| 250 | anneal | 0.267 | 5.01 |
| 250 | cbc | 0.000 | 0.61 |
| 250 | greedy | 1.982 | 0.01 |
| 250 | highs | 0.000 | 0.43 |
| 500 | anneal | 0.683 | 5.01 |
| 500 | cbc | 0.002 | 0.84 |
| 500 | greedy | 1.421 | 0.02 |
| 500 | highs | 0.000 | 0.61 |
| 1000 | anneal | 1.214 | 5.02 |
| 1000 | cbc | 0.000 | 1.64 |
| 1000 | greedy | 1.223 | 0.05 |
| 1000 | highs | 0.002 | 0.93 |
| 2000 | anneal | 0.833 | 5.05 |
| 2000 | cbc | 0.000 | 6.49 |
| 2000 | greedy | 0.833 | 0.17 |
| 2000 | highs | 0.000 | 2.57 |

## Range model: planted optimum (tau = 0), all methods

| n | seed | highs | cbc | greedy | anneal |
|---|---|---|---|---|---|
| 20 | 1 | True | True | True | True |
| 20 | 2 | True | True | True | True |
| 20 | 3 | True | True | True | True |
| 100 | 1 | True | True | True | True |
| 100 | 2 | True | True | True | True |
| 100 | 3 | True | True | True | True |
| 500 | 1 | True | True | True | True |
| 500 | 2 | True | True | True | True |
| 500 | 3 | True | True | True | True |
| 1000 | 1 | True | True | True | True |
| 1000 | 2 | True | True | True | True |
| 1000 | 3 | True | True | True | True |

## Range model: real cold-cereal catalogue (274 products with sales)

| shelf share | substitution | ranged | exact | greedy | anneal | naive rank-and-fill | exact vs naive % |
|---|---|---|---|---|---|---|---|
| 0.35 | 0.3 | 96 | 280.5 | 280.4 | 280.4 | 277.2 | 1.16 |
| 0.35 | 0.6 | 96 | 313.0 | 311.0 | 312.5 | 304.4 | 2.82 |
| 0.35 | 0.9 | 96 | 351.1 | 350.0 | 350.3 | 331.6 | 5.87 |
| 0.45 | 0.3 | 124 | 306.3 | 306.0 | 306.1 | 305.8 | 0.17 |
| 0.45 | 0.6 | 123 | 328.1 | 327.2 | 327.6 | 325.8 | 0.69 |
| 0.45 | 0.9 | 123 | 355.9 | 355.1 | 355.1 | 345.9 | 2.87 |
| 0.55 | 0.3 | 151 | 325.8 | 325.6 | 325.6 | 325.3 | 0.15 |
| 0.55 | 0.6 | 151 | 339.3 | 338.8 | 339.0 | 337.8 | 0.45 |
| 0.55 | 0.9 | 150 | 359.0 | 358.7 | 358.7 | 350.2 | 2.52 |

## Promotion calendar

Real instance (top 40 products, 52 weeks): 156 promotions, gain 206.1 on a baseline profit of 4671 (4.4%), MIP gap 0.0000, Monte Carlo 5th to 95th percentile 176 to 250.

Twin regret against the plan built on the TRUE uplifts:

| seed | point-estimate plan % | shaded by 1 se % | greedy % |
|---|---|---|---|
| 0 | 29.0 | 30.7 | 29.0 |
| 1 | 3.3 | 7.8 | 3.3 |
| 2 | 18.9 | 24.1 | 18.7 |
| 3 | 18.6 | 33.5 | 18.7 |
| 4 | 15.4 | 41.8 | 15.8 |
| 5 | 14.4 | 24.9 | 14.5 |

Scaling (twin, 52 weeks):

| items | binaries | MIP s | MIP gap | greedy s | greedy shortfall % |
|---|---|---|---|---|---|
| 10 | 1040 | 0.11 | 0.0000 | 0.001 | 0.10 |
| 20 | 2080 | 0.20 | 0.0000 | 0.001 | 0.29 |
| 40 | 4160 | 0.46 | 0.0000 | 0.002 | 0.08 |
| 80 | 8320 | 0.81 | 0.0000 | 0.006 | 0.29 |

## Replenishment (SimPy, paired replications, 28 days)

| shelf capacity vs 2 days of demand | profit gain of the stochastic plan | 95% interval | fill det / SP | waste det / SP |
|---|---|---|---|---|
| 0.7 | 9.5 | 5.7 to 13.3 | 0.745 / 0.725 | 0.056 / 0.047 |
| 0.9 | -1.9 | -5.9 to 2.0 | 0.805 / 0.799 | 0.081 / 0.082 |
| 1.15 | -4.4 | -8.4 to -0.4 | 0.805 / 0.804 | 0.081 / 0.085 |

Planted newsvendor levels versus the LP (twin): seed 1: mean abs diff 0.0 units (max 0) on levels averaging 7.3; seed 2: mean abs diff 0.3 units (max 1) on levels averaging 6.9; seed 3: mean abs diff 0.1 units (max 1) on levels averaging 9.3

## Markdown

Elasticity estimated on the real data: 1.32 (95% interval 1.16 to 1.48; 183 products, 7083 product-weeks). Real lots: optimal path vs holding full price, mean revenue +3.8% (range 3.4 to 5.2) with an ASSUMED stock of 2x full-price demand.

Twin, shortfall against the planted revenue (%):

| seed | e | NLP | DP | MIP 4 | MIP 8 | MIP 16 | MIP 32 |
|---|---|---|---|---|---|---|---|
| 0 | 1.76 | 0.000 | 0.066 | 0.819 | 0.489 | 0.145 | 0.023 |
| 1 | 2.92 | 0.000 | 0.032 | 2.727 | 0.576 | 0.228 | 0.096 |
| 2 | 1.81 | 0.000 | 0.015 | 0.952 | 0.090 | 0.123 | 0.024 |
| 3 | 1.70 | 0.000 | 0.007 | 0.320 | 0.392 | 0.186 | 0.011 |
| 4 | 2.17 | 0.000 | 0.027 | 0.039 | 0.665 | 0.039 | 0.077 |
| 5 | 2.67 | 0.000 | 0.022 | 1.788 | 0.840 | 0.329 | 0.053 |
| 6 | 1.88 | 0.000 | 0.074 | 2.237 | 0.547 | 0.152 | 0.049 |
| 7 | 2.83 | 0.000 | 0.021 | 0.771 | 0.306 | 0.163 | 0.028 |

## Test plans

A/B: baseline 5%, relative lift 10%: 31,234 per arm; simulated type I 0.051, power 0.804.

Matched-store trial (simulated panels, 26 pre-weeks, 8 post-weeks, 6% weekly noise): share of trials that reject.

| pairs | true lift | rejection rate |
|---|---|---|
| 10 | 0% | 0.04 |
| 10 | 3% | 0.41 |
| 10 | 5% | 0.69 |
| 20 | 0% | 0.05 |
| 20 | 3% | 0.60 |
| 20 | 5% | 0.95 |
| 40 | 0% | 0.03 |
| 40 | 3% | 0.92 |
| 40 | 5% | 1.00 |
