"""Data: REAL (Complete Journey cold-cereal extract) and SIMULATED (twin with planted optimum).

REAL   product-week units, net sales, feature/display/mailer shares: 565 products, 52 weeks, 10 manufacturers, from
       The Complete Journey (84.51 degrees, CC0, a US grocer, 2017, 2,469 households). Not Sainsbury's, not UK.
ASSUMED margin, shelf width, substitution rate, promotion cost, shelf life, lead time, costs. None of these are in the data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

REAL_DIR = Path(__file__).resolve().parents[2] / "data" / "real"
PRIVATE_LABEL_ID = 69  # the retailer's private label in the data (see basketlens DATA_NOTES)

ASSUMED = {
    "margin_brand": 0.28, "margin_private": 0.38,      # gross margin on net price; not in the data
    "substitution_rate": 0.6,                           # share of a delisted item's demand kept by a substitute; basketlens used 0.5 to 1.0
    "promo_cost_rate": 0.18,                            # price funding per promoted unit as a share of price
}


@dataclass
class RangeInstance:
    """Range and shelf-space instance. All arrays are length n."""
    name: str
    demand: np.ndarray        # units per week if ranged
    price: np.ndarray
    margin_rate: np.ndarray
    width: np.ndarray         # shelf facings needed
    group: np.ndarray         # int group id (sub-category)
    supplier: np.ndarray      # int supplier id
    capacity: float           # total shelf width
    min_per_group: dict       # group -> min ranged items
    max_share_supplier: float # one supplier may hold at most this share of the capacity
    neighbours: np.ndarray    # n x K substitute indices (-1 = none)
    sim: np.ndarray           # n x K similarity in [0,1]
    tau: float = ASSUMED["substitution_rate"]
    planted: np.ndarray | None = None  # planted optimal 0/1 vector, only for tau=0 twin
    kind: str = "real"
    notes: str = ""

    @property
    def n(self) -> int:
        return len(self.demand)

    @property
    def profit(self) -> np.ndarray:
        return self.demand * self.price * self.margin_rate


def _build_neighbours(group: np.ndarray, price: np.ndarray, K: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(group)
    nb = -np.ones((n, K), dtype=int)
    sm = np.zeros((n, K))
    for g in np.unique(group):
        idx = np.where(group == g)[0]
        for i in idx:
            others = idx[idx != i]
            if len(others) == 0:
                continue
            d = np.abs(np.log(price[others]) - np.log(price[i]))
            o = np.argsort(d)[:K]
            nb[i, : len(o)] = others[o]
            sm[i, : len(o)] = np.exp(-3.0 * d[o])
    return nb, sm


def _width_from_size(size: str | float) -> float:
    m = re.search(r"([\d.]+)", str(size))
    oz = float(m.group(1)) if m else 14.0
    return float(np.clip(0.6 + oz / 24.0, 0.8, 2.0))


def load_real_products() -> pd.DataFrame:
    """One row per product with REAL weekly demand statistics and ASSUMED margin and width."""
    pw = pd.read_csv(REAL_DIR / "product_week_promo.csv")
    g = pw.groupby("product_id")
    t = pd.DataFrame({
        "manufacturer_id": g.manufacturer_id.first(), "ptype": g.ptype.first(),
        "units": g.units.sum(), "net_sales": g.net_sales.sum(),
        "weekly_mean": g.units.mean(), "weekly_sd": g.units.std(ddof=1),
    })
    t = t[t.units > 0].copy()
    t["price"] = t.net_sales / t.units
    t["is_private"] = t.manufacturer_id == PRIVATE_LABEL_ID
    t["margin_rate"] = np.where(t.is_private, ASSUMED["margin_private"], ASSUMED["margin_brand"])
    # width is assumed from price (bigger packs cost more); the size field is only kept for the supplier extract
    t["width"] = np.clip(0.7 + 0.12 * t.price, 0.8, 2.0)
    return t.reset_index()


def real_range_instance(capacity_share: float = 0.45, tau: float | None = None, K: int = 5) -> RangeInstance:
    """Real cold-cereal catalogue. Demand is the REAL mean weekly panel units. Shelf capacity is a share of the full-range width."""
    t = load_real_products()
    group = pd.factorize(t.ptype)[0]
    sup = pd.factorize(t.manufacturer_id)[0]
    nb, sm = _build_neighbours(group, t.price.values, K)
    cap = float(t.width.sum() * capacity_share)
    mpg = {int(g): 2 for g in np.unique(group) if (group == g).sum() >= 10}
    return RangeInstance("real_cold_cereal", t.weekly_mean.values, t.price.values, t.margin_rate.values, t.width.values,
                         group, sup, cap, mpg, 0.35, nb, sm, tau if tau is not None else ASSUMED["substitution_rate"],
                         None, "real", "Real demand, assumed margins/widths/substitution.")


def twin_range_instance(n: int, seed: int, tau: float = 0.0, K: int = 5, capacity_share: float = 0.4) -> RangeInstance:
    """Simulated twin with a PLANTED optimum for tau = 0 (pure knapsack): the planted set fills the shelf exactly and every
    planted item has a better profit per unit of width than every other item, so it also maximises the linear relaxation.
    A feasible solution that reaches the relaxation bound is optimal. For tau > 0 no planted answer exists; use the exact solver."""
    rng = np.random.default_rng(seed)
    n_groups = max(3, min(12, n // 8))
    group = rng.integers(0, n_groups, n)
    sup = rng.integers(0, max(4, n // 25), n)
    price = np.exp(rng.normal(1.1, 0.5, n))
    demand = np.exp(rng.normal(2.0, 0.9, n))
    margin = rng.uniform(0.15, 0.45, n)
    width = rng.uniform(0.8, 2.0, n)
    profit = demand * price * margin
    dens = profit / width
    # plant: choose a set that spans every group, then make it the densest items by lifting its demand
    k = max(n_groups * 2, int(n * capacity_share * 0.7))
    k = min(k, n - 1)
    chosen = []
    for g in range(n_groups):
        idx = np.where(group == g)[0]
        if len(idx) >= 2:
            chosen += list(rng.choice(idx, 2, replace=False))
    rest = [i for i in range(n) if i not in set(chosen)]
    chosen += list(rng.choice(rest, max(0, k - len(chosen)), replace=False)) if k > len(chosen) else []
    S = np.zeros(n, bool); S[chosen] = True
    cut = dens[~S].max() if (~S).sum() > 0 else dens.max()
    # lift planted items so each has density >= cut * 1.05 (strict gap), then fix capacity = their exact width
    lift = np.maximum(1.0, cut * 1.05 / np.maximum(dens, 1e-9))
    demand = np.where(S, demand * lift, demand)
    cap = float(width[S].sum())
    # supplier concentration cap must hold for the planted set
    share = max(width[S & (sup == s)].sum() for s in np.unique(sup)) / cap
    max_share = float(max(0.35, share + 0.02))
    # group minimum: planted set holds >= 2 per group, so require 2 (satisfied)
    mpg = {int(g): 2 for g in range(n_groups) if (group == g).sum() >= 2}
    nb, sm = _build_neighbours(group, price, K)
    inst = RangeInstance(f"twin_n{n}_s{seed}", demand, price, margin, width, group, sup, cap, mpg, max_share, nb, sm, tau,
                         S.astype(int) if tau == 0 else None, "twin")
    return inst


# ---------------------------------------------------------------- promotion calendar data
@dataclass
class PromoInstance:
    name: str
    base: np.ndarray            # P x T baseline units without promotion
    price: np.ndarray           # P
    margin_rate: np.ndarray     # P
    uplift: np.ndarray          # K x P log-uplift per promo type (type 0 = mailer/feature, 1 = display)
    uplift_se: np.ndarray       # K x P standard error of log-uplift
    slots_per_week: int         # max promoted items per week (feature page + display space)
    min_gap: int                # weeks between promotions of the same item
    cost_rate: float            # price funding as share of price, per promoted unit
    max_promos_item: int        # per item over the horizon
    truth_uplift: np.ndarray | None = None
    kind: str = "real"

    @property
    def P(self): return self.base.shape[0]
    @property
    def T(self): return self.base.shape[1]


def real_promo_instance(top: int = 40, slots: int = 6, seed: int = 0) -> PromoInstance:
    """Top-selling REAL cereal products. Baseline = the item's median-demand non-promoted weeks (REAL), uplift = REAL
    category log coefficients (feature, display) from basketlens, with the standard errors. Week pattern from REAL data."""
    pw = pd.read_csv(REAL_DIR / "product_week_promo.csv")
    co = pd.read_csv(REAL_DIR / "promo_coefs_category.csv").set_index("term")
    tot = pw.groupby("product_id").units.sum().sort_values(ascending=False).head(top)
    ids = tot.index.values
    sub = pw[pw.product_id.isin(ids)]
    piv = sub.pivot(index="product_id", columns="week", values="units").loc[ids].fillna(0)
    promo = sub.assign(p=(sub.feat_share > 0) | (sub.display_share > 0) | (sub.mailer_share > 0)).pivot(
        index="product_id", columns="week", values="p").loc[ids].fillna(False)
    base = np.zeros(piv.shape)
    for i in range(len(ids)):
        non = piv.values[i][~promo.values[i].astype(bool)]
        b = np.median(non) if len(non) > 3 else piv.values[i].mean()
        base[i] = max(b, 0.5)
    price = (sub.groupby("product_id").net_sales.sum() / sub.groupby("product_id").units.sum()).loc[ids].values
    mp = sub.groupby("product_id").manufacturer_id.first().loc[ids].values == PRIVATE_LABEL_ID
    margin = np.where(mp, ASSUMED["margin_private"], ASSUMED["margin_brand"])
    P = len(ids)
    # type 0: mailer (feature), type 1: display. Display coefficient is on a share of stores, so it is capped for planning
    up = np.vstack([np.full(P, co.loc["mail", "coef"]), np.full(P, min(co.loc["disp", "coef"], 1.2))])
    se = np.vstack([np.full(P, co.loc["mail", "se"]), np.full(P, co.loc["disp", "se"])])
    return PromoInstance("real_cereal_top40", base, price, margin, up, se, slots, 3, ASSUMED["promo_cost_rate"], 8, None, "real")


def twin_promo_instance(P: int, T: int, seed: int, slots: int | None = None) -> PromoInstance:
    """Twin: TRUE uplifts are known; the planner only sees noisy estimates (se), so regret against the true optimum is scored."""
    rng = np.random.default_rng(seed)
    base = np.exp(rng.normal(2.3, 0.7, (P, 1))) * np.exp(rng.normal(0, 0.15, (P, T)))
    price = np.exp(rng.normal(1.2, 0.4, P))
    margin = rng.uniform(0.2, 0.4, P)
    truth = np.vstack([rng.normal(0.30, 0.15, P), rng.normal(0.85, 0.30, P)])
    se = np.vstack([np.full(P, 0.08), np.full(P, 0.20)])
    est = truth + rng.normal(0, 1, truth.shape) * se
    return PromoInstance(f"twin_P{P}_T{T}_s{seed}", base, price, margin, est, se, slots or max(2, P // 6), 3, 0.18,
                         max(2, T // 6), truth, "twin")


# ---------------------------------------------------------------- your own catalogue
REQUIRED_COLUMNS = ["product_id", "demand", "price", "margin_rate", "width", "group", "supplier"]


def range_from_csv(path: str | Path, capacity: float, tau: float = ASSUMED["substitution_rate"], max_share_supplier: float = 0.35,
                   min_per_group: int = 1, K: int = 5) -> RangeInstance:
    """Read a catalogue CSV and validate it before any solver runs. Raises ValueError with the first problems found."""
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {missing}")
    problems = []
    if df.product_id.duplicated().any(): problems.append("duplicate product_id")
    if df[REQUIRED_COLUMNS].isna().any().any(): problems.append("missing values")
    for c in ("demand", "price", "width"):
        if (df[c] <= 0).any(): problems.append(f"{c} must be > 0")
    if ((df.margin_rate <= 0) | (df.margin_rate >= 1)).any(): problems.append("margin_rate must be in (0, 1)")
    if capacity <= 0 or capacity < df.width.min(): problems.append("capacity cannot hold a single product")
    if problems:
        raise ValueError("; ".join(problems))
    group = pd.factorize(df.group)[0]; sup = pd.factorize(df.supplier)[0]
    nb, sm = _build_neighbours(group, df.price.values, K)
    mpg = {int(g): min_per_group for g in np.unique(group) if (group == g).sum() >= min_per_group}
    return RangeInstance(Path(path).stem, df.demand.values.astype(float), df.price.values.astype(float), df.margin_rate.values.astype(float),
                         df.width.values.astype(float), group, sup, float(capacity), mpg, max_share_supplier, nb, sm, tau, None, "user")
