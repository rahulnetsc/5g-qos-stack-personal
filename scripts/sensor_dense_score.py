"""Score the guarantees on `sensor_dense` -- the only control-channel-bound
workload in this repository.

WHY THIS WORKLOAD. Every WP9 and Phase 2 result is on the parametric mix,
which is **PRB-bound at 93 % with a tightest PDB of 100 ms**. No
latency-critical conclusion is available there. `sensor_dense` is 30 UL
periodic sensors with a **15 ms PDB**, and CCE utilisation of 47-64 %
against the parametric mix's 7-9 %. `docs/wp9-regime-map.md` §0.1 says the
ranking does not generalise across regimes; this is the first test of that
on a regime where the control channel is under pressure.

WHAT IT CAN SCORE: G1 (M01 p98 / M15 jitter), G3 (M20), G8 (M09 / M22).
NOT G5 (no `frame_id`, so M05/M06 are `pending`), not G10 (no GBR flow),
not G4/G6/G12 (need a duty axis, an aggressor, and a ramp).

EXPECTATIONS ARE REGISTERED IN `docs/sensor-dense-registration.md`, and the
one that matters most is that **the study's 30/30-vs-2/30 headline is NOT
reproducible in this branch**: it is credited to Configured Grants, and
`_SPSReservation` / `_allocate_sps` were deleted at Phase 2 two-tier
commit 1.

SEEDING. `sensor_dense_scenario()` takes no seed, so the seed is applied by
replacing `ScenarioConfig.seed` -- the driver's own RNG streams are all
derived from it, so this varies the channel and traffic realisation exactly
as `sweep_scenario(seed=...)` does.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                  # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells    # noqa: E402
from sim.driver import run as driver_run                      # noqa: E402
from sim.run_record import RunRecord                          # noqa: E402
from sim.scenarios import sensor_dense_scenario               # noqa: E402
from sim.scorecard import Population, Scorecard               # noqa: E402
from sim.trace import GrantCollector                          # noqa: E402
from g11_campaign import _arm                                 # noqa: E402

#: The flows' own PDB. THIS is the bound G1 must be read against here -- the
#: parametric mix's 100 ms is a different workload's number.
PDB_MS = 15.0


#: Registered decision, docs/attach-path-default-registration.md.
#: `"all"` seeds every UL UE with the BSR hardware supplies during
#: attach. A DIVERGENCE from the port, justified by the sim having no
#: RA procedure (Reservation's `has_srb` is hardcoded False), not by
#: the outcome. Module-level so `spawn` workers inherit it.
ATTACH_SEED = None

def one(arm: str, seed: int, horizon: int, attach: bool = False) -> dict:
    sc = sensor_dense_scenario()
    sc = dataclasses.replace(sc, seed=seed, horizon_slots=horizon)
    grants = GrantCollector()
    t0 = time.time()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True,
                   attach_seed_slots=("all" if attach else None),
                   grant_sink=grants)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=s, arm={}, meta={})
    card = Scorecard()
    full = card.score(rec, population=Population.all_flows())

    def val(mid, *path):
        r = full.get(mid)
        v = r.value if r else None
        for p in path:
            v = (v or {}).get(p) if isinstance(v, dict) else None
        return v

    # THE LATENCY-CRITICAL READING: how many of the 30 flows hold p98 within
    # their OWN 15 ms budget. This is the statistic the study reports as
    # "flows on time", and it cannot be computed on the parametric mix.
    #
    # **A FLOW THAT DELIVERED NOTHING REPORTS p98 = 0.0**, and the first
    # version of this counted that as on-time -- three fully-starved flows
    # scored as perfect. Measured: ue24/27/28 with arrived=80000,
    # delivered=0, p98=0.0. Same shape as M19's p95=0.0 failure signature and
    # as the journal's "a statistic undefined on the data returns a confident
    # value" class. So delivery is a PRECONDITION for being on time, and
    # starved flows are counted separately rather than silently passing.
    #
    # (`sim/scorecard.py::_m01` gets this right for its own contest -- it
    # filters on `message_count` and reports `excluded` -- which is why the
    # bug was mine and not the metric layer's.)
    delivering = {fr.key: fr.delay_p98_ms for fr in rec.flows.values()
                  if fr.delay_p98_ms is not None and fr.bytes_delivered > 0}
    starved = [fr.key for fr in rec.flows.values() if fr.bytes_delivered == 0]
    p98s = delivering
    on_time = sum(1 for v in delivering.values() if v <= PDB_MS)

    ever = {g.ue_id for g in grants.finish()
            if g.direction == "UL" and not g.retx_count}
    all_ul = {f.ue_id for f in sc.flows if f.direction == "UL"}

    _m02 = full.get("M02")
    _m02 = _m02.value if _m02 else None
    # Severity is ONE population across the whole scorecard: the protected
    # fleet. Mixing M02_all and M02_prot in one column is the population
    # defect at table level (docs/scorecard-audit-2026-09-07.md 4.1).
    _m02p = card.score(rec, population=Population.protected_fleet()).get("M02")
    _m02p = _m02p.value if _m02p else None
    return {
        # SEVERITY, uniform across the scorecard: the fraction of RESOLVED
        # bytes that missed their PDB (M02). See phase2_core.py.
        "M02_all": _m02,
        "M02_prot": _m02p,

        "arm": arm, "seed": seed, "horizon": horizon,
        "wall_s": round(time.time() - t0, 1),
        "n_flows": len(rec.flows),
        "n_delivering": len(delivering),
        "n_starved": len(starved), "starved": starved,
        "flows_on_time": on_time,
        "worst_p98_ms": max(p98s.values()) if p98s else None,
        "median_p98_ms": statistics.median(p98s.values()) if p98s else None,
        "G1_M01_p98": val("M01", "p98"),
        "G1_M15_jitter": val("M15", "jitter_ms"),
        "G3_M20_ms": val("M20", "max_gap_ms"),
        "G8_M09_worst": val("M09", "worst"),
        "G8_M22_epochs": val("M22", "epochs"),
        "n_never_granted": len(all_ul - ever),
        "cce_util": rec.system.cce_utilization,
        "ul_prb_util": rec.system.ul_prb_utilization,
    }


def _task(t):
    return one(*t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--attach-seed", action="store_true",
                    help="seed the attach BSR on every UL UE (registered decision, docs/attach-path-default-registration.md)")
    ap.add_argument("--out", default="sweeps/postscaling-2026-09-05/sensor_dense.json")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    arms = [x for x in a.arms.split(",") if x]
    seeds = paired_seeds(a.seeds)
    # THE ATTACH FLAG TRAVELS IN THE TASK TUPLE, NOT A MODULE GLOBAL.
    # A global set in main() does not reach a `spawn` worker -- the
    # worker re-imports the module and sees the declared default. The
    # first version did exactly that and produced a with-attach run
    # BYTE-IDENTICAL to the without one, i.e. a false null. Same trap
    # CLAUDE.md records from G9.
    tasks = [(arm, s, a.horizon, a.attach_seed) for arm in arms for s in seeds]
    print(f"{len(tasks)} runs = {len(arms)} arms x {len(seeds)} seeds, "
          f"sensor_dense @ horizon {a.horizon}, PDB {PDB_MS} ms")
    rows = [None] * len(tasks)
    for i, (idx, r) in enumerate(run_cells(_task, tasks, a.workers,
                                           cost=lambda t: arm_cost(t[0])), 1):
        rows[idx] = r
        print(f"  [{i}/{len(tasks)}] {r['arm']:<12} seed={r['seed']} "
              f"on_time={r['flows_on_time']}/{r['n_flows']} "
              f"starved={r['n_starved']} "
              f"cce={r['cce_util']:.3f} never={r['n_never_granted']}", flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_state": stamp(), "pdb_ms": PDB_MS,
                               "rows": rows}, indent=1, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
