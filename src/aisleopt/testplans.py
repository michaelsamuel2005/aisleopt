"""Test design for the decisions the models recommend: digital (A/B) and physical (matched-store) trials.

Digital: sample size, power by simulation, sample-ratio-mismatch check, guardrail non-inferiority test.
Physical: match each test store to a control store on its pre-period sales, difference-in-differences, permutation interval, power.
Store panels here are SIMULATED (the real data has no store-level series in the extract); the code works on any store x week table.
"""
from __future__ import annotations

import numpy as np
from scipy import stats


# ---------------------------------------------------------------- digital
def ab_sample_size(p0: float, mde_rel: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Per-arm sample size for a two-sided test of two proportions (baseline p0, relative lift mde_rel)."""
    p1 = p0 * (1 + mde_rel)
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    pb = (p0 + p1) / 2
    n = ((za * np.sqrt(2 * pb * (1 - pb)) + zb * np.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2) / (p1 - p0) ** 2
    return int(np.ceil(n))


def ab_simulate(p0: float, lift_rel: float, n: int, sims: int = 2000, alpha: float = 0.05, seed: int = 0) -> float:
    """Share of simulated trials with p < alpha (type I error when lift_rel = 0, power otherwise)."""
    rng = np.random.default_rng(seed)
    a = rng.binomial(n, p0, sims); b = rng.binomial(n, p0 * (1 + lift_rel), sims)
    pa, pb = a / n, b / n
    pp = (a + b) / (2 * n)
    z = (pb - pa) / np.sqrt(2 * pp * (1 - pp) / n + 1e-18)
    return float((2 * (1 - stats.norm.cdf(np.abs(z))) < alpha).mean())


def srm_check(counts: list[int], expected_share: list[float], alpha: float = 0.001) -> dict:
    """Sample ratio mismatch: chi-square of arm counts against the planned split. A small p means the assignment is broken."""
    counts = np.asarray(counts, float); exp = np.asarray(expected_share, float) * counts.sum()
    chi = float(((counts - exp) ** 2 / exp).sum()); p = float(1 - stats.chi2.cdf(chi, len(counts) - 1))
    return {"chi2": chi, "p_value": p, "mismatch": p < alpha}


def guardrail_noninferior(mean_c: float, mean_t: float, sd: float, n: int, margin_rel: float, alpha: float = 0.05) -> dict:
    """One-sided non-inferiority: H0 treatment is worse than control by more than margin_rel (e.g. basket size, complaint rate sign flipped)."""
    se = sd * np.sqrt(2.0 / n); delta = mean_t - mean_c; lim = -margin_rel * abs(mean_c)
    z = (delta - lim) / se; p = float(1 - stats.norm.cdf(z))
    return {"delta": float(delta), "lower_bound": float(delta - stats.norm.ppf(1 - alpha) * se), "p_value": p, "noninferior": p < alpha}


# ---------------------------------------------------------------- physical
def match_stores(pre: np.ndarray, test_idx: list[int], pool_idx: list[int]) -> dict[int, int]:
    """1:1 matching without replacement on the standardised pre-period weekly series (Euclidean). Greedy by hardest-to-match first."""
    Z = (pre - pre.mean(1, keepdims=True)) / (pre.std(1, keepdims=True) + 1e-9)
    level = np.log(pre.mean(1) + 1e-9)[:, None] * np.ones((1, 1))
    F = np.hstack([Z, 3.0 * (level - level.mean()) / (level.std() + 1e-9)])
    free = set(pool_idx); out = {}
    cost = {t: np.sort([np.linalg.norm(F[t] - F[c]) for c in pool_idx])[0] for t in test_idx}
    for t in sorted(test_idx, key=lambda t: -cost[t]):
        c = min(free, key=lambda c: np.linalg.norm(F[t] - F[c]))
        out[t] = c; free.remove(c)
    return out


def did_estimate(pre_t: np.ndarray, post_t: np.ndarray, pre_c: np.ndarray, post_c: np.ndarray, seed: int = 0, perms: int = 2000) -> dict:
    """Relative difference-in-differences on matched pairs (rows = pairs). t interval on the pair differences, sign-flip permutation p-value
    (valid under the null that the pair-level effect is symmetric around zero); also returns a pre-period placebo."""
    base = pre_t.mean(1).mean()
    d = ((post_t.mean(1) - pre_t.mean(1)) - (post_c.mean(1) - pre_c.mean(1))) / base
    est = float(d.mean())
    rng = np.random.default_rng(seed)
    flips = rng.choice([-1, 1], size=(perms, len(d)))
    null = (flips * (d - 0)).mean(1)
    p = float((np.abs(null) >= abs(est)).mean())
    # bootstrap interval on pairs
    se = float(d.std(ddof=1) / np.sqrt(len(d))); tq = float(stats.t.ppf(0.975, len(d) - 1))
    half = pre_t.shape[1] // 2
    placebo = ((pre_t[:, half:].mean(1) - pre_t[:, :half].mean(1)) - (pre_c[:, half:].mean(1) - pre_c[:, :half].mean(1))) / base
    return {"lift_rel": est, "ci": (est - tq * se, est + tq * se), "p_value": p,
            "placebo_pre_lift": float(placebo.mean()), "pairs": int(len(d))}


def simulate_store_panel(stores: int, pre_weeks: int, post_weeks: int, seed: int, noise: float = 0.06, effect: float = 0.0,
                         treated: list[int] | None = None) -> dict:
    """Simulated panel: store level, seasonality shared by all stores, store-specific trend and noise; an optional lift for treated stores."""
    rng = np.random.default_rng(seed)
    W = pre_weeks + post_weeks
    level = np.exp(rng.normal(8.0, 0.4, stores)); trend = rng.normal(0, 0.0015, stores)
    season = 1 + 0.1 * np.sin(2 * np.pi * np.arange(W) / 52)
    y = level[:, None] * season[None] * np.exp(trend[:, None] * np.arange(W)[None] + rng.normal(0, noise, (stores, W)))
    if treated is not None and effect:
        y[np.ix_(treated, np.arange(pre_weeks, W))] *= 1 + effect
    return {"pre": y[:, :pre_weeks], "post": y[:, pre_weeks:]}


def store_trial_power(pairs: int, effect: float, noise: float = 0.06, pre_weeks: int = 26, post_weeks: int = 8, sims: int = 200, seed: int = 0,
                      alpha: float = 0.05) -> float:
    """Power of the matched-pair DiD: simulate panels with a true lift in `pairs` treated stores, match, test."""
    hits = 0; rng = np.random.default_rng(seed)
    for s in range(sims):
        stores = pairs * 4
        panel = simulate_store_panel(stores, pre_weeks, post_weeks, int(rng.integers(1 << 30)), noise, effect, list(range(pairs)))
        # the trial design: stores are randomly drawn as test, the rest are the control pool
        m = match_stores(panel["pre"], list(range(pairs)), list(range(pairs, stores)))
        t = list(m.keys()); c = [m[k] for k in t]
        r = did_estimate(panel["pre"][t], panel["post"][t], panel["pre"][c], panel["post"][c], seed=s, perms=400)
        hits += r["ci"][0] > 0 or r["ci"][1] < 0
    return hits / sims
