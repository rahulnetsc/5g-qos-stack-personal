"""Is the cap-induced movement small against the ARM separation?

The SCA loop has no fixed point on most solves, so where it stops decides
the allocation. That is a defect only if the movement is large enough to
matter, and the scale that decides "large enough" is not absolute -- it is
the between-arm difference these guarantees are built to measure.

So: for each seed, TwoTier at cap 150 and at cap 151 (one iteration apart,
both arbitrary points on the same limit cycle), against PF and Reservation
on the identical scenario and seed. If |TT150 - TT151| is comparable to
|TT150 - PF|, then an arm comparison at that margin is not resolvable,
whatever its confidence interval says -- the interval is over seeds and this
variance is within a seed.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import scheduler.tier1 as T                        # noqa: E402
from sim.driver import run                          # noqa: E402
from sim.run_record import RunRecord                # noqa: E402
from sim.scorecard import Population, Scorecard     # noqa: E402
import wp9_sweep as W                               # noqa: E402

METRICS = [("M01", "p98"), ("M06", "p95_ms"), ("M14", "fraction"),
           ("M03", "max_gap_ms"), ("M15", "jitter_ms"), ("M09", "worst")]
SEEDS = [int(s) for s in (sys.argv[1:] or ["1", "2", "3", "4", "5"])]
HORIZON = 20_000


def score_one(arm: str, seed: int, cap: int | None = None) -> dict:
    from scheduler import load_two_tier
    from sim.baselines.pf import ProportionalFair
    from scheduler.reservation import Reservation
    W._HORIZON[0] = HORIZON
    av = {"n_ues": 8, "load_mult": 1.0}
    sc = W._build(seed=seed, **av)
    sched = {"TwoTier": lambda: load_two_tier(W._TT_CONFIG, min_rb=5),
             "PF": lambda: ProportionalFair(ewma_window_slots=200),
             "Reservation": lambda: Reservation(min_rb=5)}[arm]()
    old = T._SCA_MAXITERS
    if cap is not None:
        T._SCA_MAXITERS = cap
    try:
        summary = run(sc, sched, **W._driver_kwargs(**av))
    finally:
        T._SCA_MAXITERS = old
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    s = Scorecard().score(rec, population=Population.protected_fleet())
    out = {}
    for mid, key in METRICS:
        v = s[mid].value
        out[f"{mid}.{key}"] = (v or {}).get(key) if isinstance(v, dict) else None
    return out


rows = {}
for seed in SEEDS:
    rows[seed] = {
        "TT@150": score_one("TwoTier", seed, 150),
        "TT@151": score_one("TwoTier", seed, 151),
        "PF": score_one("PF", seed),
        "Reservation": score_one("Reservation", seed),
    }
    print(f"  seed {seed} done", flush=True)

print()
hdr = f"{'metric':<16}{'|TT150-TT151|':>16}{'|TT150-PF|':>14}{'|TT150-Res|':>14}{'cap/arm(PF)':>13}"
print(hdr); print("-" * len(hdr))
summary = {}
for mid, key in METRICS:
    k = f"{mid}.{key}"
    cap_d, pf_d, res_d = [], [], []
    for seed in SEEDS:
        r = rows[seed]
        a, b = r["TT@150"][k], r["TT@151"][k]
        p, q = r["PF"][k], r["Reservation"][k]
        if None in (a, b, p, q):
            continue
        cap_d.append(abs(a - b)); pf_d.append(abs(a - p)); res_d.append(abs(a - q))
    if not cap_d:
        continue
    c, pf, rs = np.median(cap_d), np.median(pf_d), np.median(res_d)
    ratio = c / pf if pf else float("inf")
    summary[k] = {"cap_median": c, "pf_median": pf, "res_median": rs,
                  "cap_over_arm": ratio, "n_seeds": len(cap_d)}
    print(f"{k:<16}{c:>16.4g}{pf:>14.4g}{rs:>14.4g}{ratio:>13.2%}")
Path(__file__).with_name("cap_vs_arm.json").write_text(
    json.dumps({"seeds": SEEDS, "per_seed": rows, "summary": summary},
               indent=2, default=str))
print("\nmedians over", len(SEEDS), "seeds; cap/arm = how much of the TwoTier-vs-PF")
print("difference is reproduced by moving the iteration cap by ONE.")
