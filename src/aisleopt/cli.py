"""Command line: validated inputs, bounded run time, fixed seeds, a JSON result with run metadata.

aisleopt range    --source real|twin|csv ...
aisleopt promo    --source real|twin ...
aisleopt replen   --source real|twin ...
aisleopt markdown --source real|twin ...
aisleopt bench    --quick
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, ValidationError, model_validator

from . import __version__


class _Base(BaseModel):
    model_config = {"extra": "forbid"}
    seed: int = Field(0, ge=0, le=2**31 - 1)
    time_limit_s: float = Field(30.0, gt=0, le=600)
    out: str = "outputs"


class RangeConfig(_Base):
    source: Literal["real", "twin", "csv"] = "real"
    n: int = Field(200, ge=5, le=5000)
    capacity_share: float = Field(0.45, gt=0.05, lt=0.95)
    tau: float = Field(0.6, ge=0, le=1)
    solver: Literal["highs", "cbc"] = "highs"
    csv: str | None = None
    capacity: float | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _csv(self):
        if self.source == "csv" and (not self.csv or self.capacity is None):
            raise ValueError("source=csv needs --csv and --capacity")
        return self


class PromoConfig(_Base):
    source: Literal["real", "twin"] = "real"
    items: int = Field(40, ge=5, le=200)
    slots_per_week: int = Field(6, ge=1, le=50)


class ReplenConfig(_Base):
    source: Literal["real", "twin"] = "real"
    capacity_factor: float = Field(0.9, gt=0.3, le=3.0)
    reps: int = Field(60, ge=5, le=1000)
    days: int = Field(28, ge=7, le=120)
    scenarios: int = Field(1000, ge=50, le=20000)


class MarkdownConfig(_Base):
    source: Literal["real", "twin"] = "real"
    lots: int = Field(10, ge=1, le=100)
    periods: int = Field(6, ge=2, le=26)


def _meta(cfg, t0):
    import highspy, pyomo, scipy
    return {"aisleopt": __version__, "python": platform.python_version(), "pyomo": pyomo.version.version, "scipy": scipy.__version__,
            "numpy": np.__version__, "config": cfg.model_dump(), "config_sha256": hashlib.sha256(cfg.model_dump_json().encode()).hexdigest()[:16],
            "wall_s": round(time.time() - t0, 2)}


def _dump(name, cfg, body, t0):
    out = {"meta": _meta(cfg, t0), "result": body}
    Path(cfg.out).mkdir(parents=True, exist_ok=True)
    p = Path(cfg.out) / f"{name}.json"
    p.write_text(json.dumps(out, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    return out, p


def run_range(cfg: RangeConfig):
    from . import range_model as rm
    from .data import range_from_csv, real_range_instance, twin_range_instance
    t0 = time.time()
    if cfg.source == "real": inst = real_range_instance(cfg.capacity_share, cfg.tau)
    elif cfg.source == "twin": inst = twin_range_instance(cfg.n, cfg.seed, cfg.tau, capacity_share=cfg.capacity_share)
    else: inst = range_from_csv(cfg.csv, cfg.capacity, cfg.tau)
    ex = rm.solve_exact(inst, cfg.solver, cfg.time_limit_s)
    gr = rm.greedy(inst)
    sa = rm.anneal(inst, cfg.seed, min(cfg.time_limit_s, 10.0), x0=gr["x"])
    best = max((ex, sa, gr), key=lambda r: r["objective"] if r["feasible"] else -1)
    body = {"instance": inst.name, "kind": inst.kind, "products": inst.n, "ranged": int(best["x"].sum()), "best_solver": best["solver"],
            "objective_per_week": best["objective"], "exact": {k: ex[k] for k in ("objective", "bound", "gap", "solve_s", "status", "feasible")},
            "greedy": {"objective": gr["objective"], "solve_s": gr["solve_s"]}, "anneal": {"objective": sa["objective"], "solve_s": sa["solve_s"]},
            "ranged_ids": np.where(best["x"] == 1)[0].tolist()}
    return _dump("range", cfg, body, t0)


def run_promo(cfg: PromoConfig):
    from . import promo_model as pm
    from .data import real_promo_instance, twin_promo_instance
    t0 = time.time()
    inst = real_promo_instance(cfg.items, cfg.slots_per_week) if cfg.source == "real" else twin_promo_instance(cfg.items, 52, cfg.seed, cfg.slots_per_week)
    m = pm.solve_mip(inst, time_limit=cfg.time_limit_s); g = pm.greedy(inst)
    body = {"instance": inst.name, "promos": int(m["y"].sum()), "gain_per_year": m["objective"], "gap": m["gap"], "violations": m["violations"],
            "greedy_gain": g["objective"], "monte_carlo": pm.monte_carlo(inst, m["y"], 1000, cfg.seed), "calendar": np.argwhere(m["y"] == 1).tolist()}
    return _dump("promo", cfg, body, t0)


def run_replen(cfg: ReplenConfig):
    from . import replen as rp
    t0 = time.time()
    inst = rp.real_replen_instance(cap_factor=cfg.capacity_factor) if cfg.source == "real" else rp.twin_replen_instance(12, cfg.seed, slack=False)
    c = rp.compare(inst, cfg.reps, cfg.days, cfg.scenarios, cfg.seed)
    return _dump("replen", cfg, c, t0)


def run_markdown(cfg: MarkdownConfig):
    from . import markdown as md
    t0 = time.time()
    lots = md.real_markdown_instances(cfg.lots, cfg.periods, cfg.seed) if cfg.source == "real" else [md.twin_markdown_instance(cfg.seed + k, cfg.periods) for k in range(cfg.lots)]
    rows = []
    for l in lots:
        s = md.solve_nlp(l, cfg.seed)
        rows.append({"lot": l.name, "elasticity": l.e, "price_path": s["prices"].round(3), "revenue": s["objective"], "hold_full_price": md.revenue(l, [l.p0] * l.T)})
    return _dump("markdown", cfg, {"lots": rows}, t0)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aisleopt", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, cls in (("range", RangeConfig), ("promo", PromoConfig), ("replen", ReplenConfig), ("markdown", MarkdownConfig)):
        p = sub.add_parser(name)
        for fname, f in cls.model_fields.items():
            p.add_argument("--" + fname.replace("_", "-"), dest=fname, default=None, type=(float if f.annotation in (float, "float | None") else None))
    b = sub.add_parser("bench"); b.add_argument("--quick", action="store_true"); b.add_argument("--out", default="outputs")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "bench":
            from .bench import run_all
            run_all(args.quick, args.out); return 0
        cls = {"range": RangeConfig, "promo": PromoConfig, "replen": ReplenConfig, "markdown": MarkdownConfig}[args.cmd]
        raw = {k: v for k, v in vars(args).items() if k != "cmd" and v is not None}
        cfg = cls(**raw)
        out, path = {"range": run_range, "promo": run_promo, "replen": run_replen, "markdown": run_markdown}[args.cmd](cfg)
        print(f"wrote {path} in {out['meta']['wall_s']}s")
        return 0
    except (ValidationError, ValueError) as e:
        print(f"invalid input: {e}", file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main())
