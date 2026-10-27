import json
import numpy as np
import pandas as pd
import pytest

from aisleopt import markdown as md, promo_model as pm, range_model as rm, replen as rp, testplans as tp
from aisleopt.cli import MarkdownConfig, PromoConfig, RangeConfig, main, run_range
from aisleopt.data import (REQUIRED_COLUMNS, range_from_csv, real_promo_instance, real_range_instance, twin_promo_instance,
                           twin_range_instance, load_real_products)
from pydantic import ValidationError


# ---------------------------------------------------------------- data
def test_real_data_loads_and_is_sane():
    t = load_real_products()
    assert len(t) == 274 and (t.price > 0).all() and (t.weekly_mean > 0).all()
    r = real_range_instance()
    assert r.n == 274 and r.capacity > 0 and r.kind == "real"


def test_twin_is_reproducible():
    a, b = twin_range_instance(80, 3), twin_range_instance(80, 3)
    assert np.array_equal(a.demand, b.demand) and np.array_equal(a.planted, b.planted)


# ---------------------------------------------------------------- range
@pytest.mark.parametrize("n,seed", [(20, 1), (60, 2), (150, 3)])
def test_planted_optimum_is_feasible_and_recovered(n, seed):
    inst = twin_range_instance(n, seed, tau=0.0)
    assert rm.feasible(inst, inst.planted)
    target = rm.objective(inst, inst.planted)
    for solver in ("highs", "cbc"):
        r = rm.solve_exact(inst, solver, 20)
        assert r["feasible"] and r["objective"] >= target * (1 - 1e-6) and r["objective"] <= target * (1 + 1e-6)


def test_planted_set_fills_shelf_exactly_and_has_density_gap():
    inst = twin_range_instance(100, 4, tau=0.0)
    S = inst.planted.astype(bool)
    assert abs(inst.width[S].sum() - inst.capacity) < 1e-9
    d = inst.profit / inst.width
    assert d[S].min() >= d[~S].max() - 1e-12


def test_objective_matches_brute_force_formula():
    inst = twin_range_instance(40, 5, tau=0.6)
    rng = np.random.default_rng(0)
    um = inst.price * inst.margin_rate
    for _ in range(5):
        x = (rng.random(inst.n) < 0.4).astype(int)
        total = float(inst.profit[x == 1].sum())
        for i in np.where(x == 0)[0]:
            best = 0.0
            for k in range(inst.neighbours.shape[1]):
                j = inst.neighbours[i, k]
                if j >= 0 and x[j]:
                    best = max(best, inst.tau * inst.sim[i, k] * um[j] * inst.demand[i])
            total += best
        assert rm.objective(inst, x) == pytest.approx(total)


def test_exact_solvers_agree_and_heuristics_never_beat_them():
    inst = twin_range_instance(60, 6, tau=0.6)
    h, c = rm.solve_exact(inst, "highs", 20), rm.solve_exact(inst, "cbc", 20)
    assert h["objective"] == pytest.approx(c["objective"], rel=2e-4)
    g, a = rm.greedy(inst), rm.anneal(inst, 0, 2, iters=20000)
    for r in (g, a):
        assert r["feasible"] and r["objective"] <= h["objective"] * (1 + 1e-6)


def test_infeasible_vectors_are_rejected():
    inst = twin_range_instance(30, 7, tau=0.0)
    assert not rm.feasible(inst, np.ones(inst.n))               # over capacity
    assert not rm.feasible(inst, np.zeros(inst.n))              # violates group minimum


def test_real_instance_exact_beats_naive_rank_and_fill_or_ties():
    inst = real_range_instance(0.45, 0.6)
    ex = rm.solve_exact(inst, "highs", 30)
    assert ex["feasible"] and ex["gap"] < 1e-3
    assert rm.greedy(inst)["objective"] <= ex["objective"] * (1 + 1e-9)


# ---------------------------------------------------------------- promo
def test_promo_mip_feasible_and_beats_or_ties_greedy():
    inst = twin_promo_instance(15, 52, 1)
    m, g = pm.solve_mip(inst, time_limit=20), pm.greedy(inst)
    assert m["violations"] == [] and g["violations"] == []
    assert m["objective"] >= g["objective"] - 1e-6


def test_check_plan_detects_each_rule():
    inst = twin_promo_instance(10, 52, 2)
    y = np.zeros((2, 10, 52), int)
    y[0, 0, 5] = 1; y[0, 0, 6] = 1
    assert "min gap" in pm.check_plan(inst, y)
    y = np.zeros((2, 10, 52), int); y[:, 0, 3] = 1
    assert "two types in one item-week" in pm.check_plan(inst, y)
    y = np.zeros((2, 10, 52), int); y[0, :, 4] = 1
    assert "weekly slots" in pm.check_plan(inst, y)


def test_true_uplifts_give_the_best_plan_under_truth():
    inst = twin_promo_instance(20, 52, 3)
    tru = pm.solve_mip(inst, u=inst.truth_uplift, time_limit=20)
    est = pm.solve_mip(inst, time_limit=20)
    assert pm.plan_value(inst, est["y"], inst.truth_uplift) <= tru["objective"] + 1e-6


def test_monte_carlo_is_seeded():
    inst = real_promo_instance(15)
    y = pm.greedy(inst)["y"]
    assert pm.monte_carlo(inst, y, 200, 1) == pm.monte_carlo(inst, y, 200, 1)


# ---------------------------------------------------------------- replenishment
def test_two_stage_matches_planted_newsvendor_levels():
    inst = rp.twin_replen_instance(8, 1)
    pl = rp.planted_levels(inst, 2)
    sp = rp.solve_two_stage(inst, 2, 4000, carry=False)
    assert np.abs(sp["S"] - pl).mean() < 1.0 and np.abs(sp["S"] - pl).max() <= 3


def test_capacity_binds_in_two_stage():
    inst = rp.real_replen_instance(cap_factor=0.7)
    sp = rp.solve_two_stage(inst, 2, 300, carry=True)
    assert (inst.space * sp["S"]).sum() <= inst.capacity + 1e-6


def test_simulation_is_reproducible_and_bounded():
    inst = rp.real_replen_instance()
    S = rp.deterministic_levels(inst, 2)
    a, b = rp.simulate(inst, S, 14, 5, seed=3), rp.simulate(inst, S, 14, 5, seed=3)
    assert np.array_equal(a["profit"], b["profit"])
    assert ((a["fill"] >= 0) & (a["fill"] <= 1)).all() and ((a["waste"] >= 0) & (a["waste"] <= 1)).all()


def test_zero_stock_sells_nothing():
    inst = rp.real_replen_instance()
    r = rp.simulate(inst, np.zeros(inst.n), 14, 3, seed=0)
    assert (r["fill"] == 0).all() and (r["waste"] == 0).all()


# ---------------------------------------------------------------- markdown
def test_elasticity_estimate_is_plausible():
    e = md.estimate_elasticity()
    assert 0.8 < e["elasticity"] < 2.2 and e["ci"][0] < e["elasticity"] < e["ci"][1]


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_nlp_reaches_planted_markdown_price(seed):
    inst = md.twin_markdown_instance(seed)
    target = md.revenue(inst, [md.planted_price(inst)] * inst.T)
    n = md.solve_nlp(inst)
    assert n["objective"] >= target * (1 - 1e-4)
    assert np.all(np.diff(n["prices"]) <= 1e-9)           # prices never rise


def test_mip_gap_shrinks_with_more_price_levels():
    inst = md.twin_markdown_instance(1)
    target = md.revenue(inst, [md.planted_price(inst)] * inst.T)
    gaps = [(target - md.solve_mip(inst, L)["objective"]) / target for L in (4, 16, 32)]
    assert gaps[0] >= gaps[1] - 1e-9 and gaps[1] >= gaps[2] - 1e-3 and gaps[2] < 0.01


# ---------------------------------------------------------------- test plans
def test_ab_sample_size_and_error_rates():
    n = tp.ab_sample_size(0.05, 0.10)
    assert tp.ab_sample_size(0.05, 0.05) > n > tp.ab_sample_size(0.05, 0.20)
    assert 0.035 < tp.ab_simulate(0.05, 0.0, n, 4000) < 0.065
    assert 0.76 < tp.ab_simulate(0.05, 0.10, n, 4000) < 0.84


def test_srm_and_guardrail():
    assert not tp.srm_check([50500, 49500], [.5, .5])["mismatch"]
    assert tp.srm_check([52000, 48000], [.5, .5])["mismatch"]
    assert tp.guardrail_noninferior(25, 24.8, 12, 20000, 0.02)["noninferior"]
    assert not tp.guardrail_noninferior(25, 23.0, 12, 20000, 0.02)["noninferior"]


def test_store_trial_error_rate_and_power():
    assert tp.store_trial_power(20, 0.0, sims=150, seed=1) < 0.10
    assert tp.store_trial_power(20, 0.05, sims=80, seed=1) > 0.85


def test_matching_is_one_to_one():
    panel = tp.simulate_store_panel(40, 26, 8, 0)
    m = tp.match_stores(panel["pre"], list(range(10)), list(range(10, 40)))
    assert len(set(m.values())) == 10 and all(c >= 10 for c in m.values())


# ---------------------------------------------------------------- CLI and validation
def test_config_rejects_bad_inputs():
    with pytest.raises(ValidationError): RangeConfig(n=2)
    with pytest.raises(ValidationError): RangeConfig(time_limit_s=10_000)
    with pytest.raises(ValidationError): RangeConfig(source="csv")
    with pytest.raises(ValidationError): PromoConfig(unknown=1)
    with pytest.raises(ValidationError): MarkdownConfig(lots=0)


def test_csv_validation(tmp_path):
    good = pd.DataFrame({"product_id": range(12), "demand": 5.0, "price": 2.0, "margin_rate": 0.3, "width": 1.0,
                         "group": ["a", "b"] * 6, "supplier": ["x", "y", "z"] * 4})
    p = tmp_path / "ok.csv"; good.to_csv(p, index=False)
    assert range_from_csv(p, capacity=6.0).n == 12
    bad = good.copy(); bad.loc[0, "margin_rate"] = 1.4; bad.to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(ValueError, match="margin_rate"): range_from_csv(tmp_path / "bad.csv", capacity=6.0)
    good.drop(columns=["width"]).to_csv(tmp_path / "miss.csv", index=False)
    with pytest.raises(ValueError, match="missing columns"): range_from_csv(tmp_path / "miss.csv", capacity=6.0)


def test_cli_range_writes_json_with_metadata(tmp_path):
    rc = main(["range", "--source", "twin", "--n", "40", "--seed", "3", "--time-limit-s", "10", "--out", str(tmp_path)])
    assert rc == 0
    d = json.loads((tmp_path / "range.json").read_text())
    assert d["meta"]["config"]["seed"] == 3 and d["meta"]["wall_s"] < 60 and d["result"]["products"] == 40


def test_cli_returns_2_on_invalid_input(tmp_path, capsys):
    assert main(["range", "--source", "csv", "--out", str(tmp_path)]) == 2


def test_same_seed_same_result(tmp_path):
    a, _ = run_range(RangeConfig(source="twin", n=50, seed=4, time_limit_s=10, out=str(tmp_path / "a")))
    b, _ = run_range(RangeConfig(source="twin", n=50, seed=4, time_limit_s=10, out=str(tmp_path / "b")))
    assert a["result"]["ranged_ids"] == b["result"]["ranged_ids"]


@pytest.mark.slow
def test_quick_benchmark_runs(tmp_path):
    from aisleopt.bench import run_all
    out = run_all(quick=True, out_dir=tmp_path)
    assert all(r["feasible"] for r in out["range_scaling"])
    assert all(r["highs"] and r["cbc"] for r in out["range_planted"])
