"""Are G5, G10's admissible-fleet boundary and the UL blackout ONE mechanism?

The chain traced in `docs/g5-lever-2026-09-05.md` and defect #24 predicts a
specific, falsifiable thing: at cold start every UE's ranking key is
identical (no UE has been granted, so `has_gbr` is False and `pdb_ms` is the
9999 sentinel on all of them), the stable sort therefore serves declaration
order, and whichever UEs the first slot's PRB budget does NOT reach can never
acquire the QoS state that would let them compete afterwards.

If that is right then ONE quantity -- how many UEs the cold-start slot can
serve -- sets all three observations:

  * G5   : the last-position UE's PDU sets never complete
  * G10  : the admissible fleet, since M08 is a WORST-GBR-flow statistic and
           one permanently-ungranted UE floors it
  * blackout: a "total UL blackout" IS a UE that was never granted

So the prediction is `n_never_granted > 0`  <=>  M08 fails, on every arm,
fleet size and seed -- and PF, which has no tie structure, never starves one.
A single counterexample in either direction refutes the consolidation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                              # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells   # noqa: E402
from sim.driver import run as driver_run                     # noqa: E402
from sim.parametric import sweep_scenario                    # noqa: E402
from sim.run_record import RunRecord                         # noqa: E402
from sim.scorecard import Population, Scorecard              # noqa: E402
from sim.trace import GrantCollector                         # noqa: E402
from g11_campaign import _arm                                # noqa: E402


def one(arm: str, seed: int, n_ues: int, horizon: int,
        attach_seed: bool = False) -> dict:
    # `attach_seed` supplies the attach BSR at slot 0 with NO stagger, so the
    # ONLY difference from the control is the seed. The staggered arm in
    # docs/attach-path-result depresses M07/M08 through pre-attach time
    # (defects-log #27), which is why that data cannot answer whether the
    # lock-out sets G10's boundary and this can.
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=1.0)
    seed_slots = ({f.ue_id: 0 for f in sc.flows if f.direction == "UL"}
                  if attach_seed else None)
    grants = GrantCollector()
    t0 = time.time()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True,
                   grant_sink=grants, attach_seed_slots=seed_slots)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows, summary=s,
                                 arm={}, meta={})
    scored = Scorecard().score(rec, population=Population.protected_fleet())
    m7 = scored["M07"].value or {}
    m8 = scored["M08"].value or {}

    ever, first_slot = set(), {}
    for g in grants.finish():
        if g.direction != "UL" or g.retx_count:
            continue
        ever.add(g.ue_id)
        first_slot.setdefault(g.ue_id, g.slot_index)
    all_ues = {f.ue_id for f in sc.flows if f.direction == "UL"}
    never = sorted(all_ues - ever)
    # How many distinct UEs the FIRST ranked slot could actually serve --
    # the quantity the consolidation says sets everything else.
    served_slot1 = sum(1 for v in first_slot.values() if v <= 1)
    return {
        "arm": arm, "seed": seed, "n_ues": n_ues, "horizon": horizon,
        "attach_seed": attach_seed,
        "wall_s": round(time.time() - t0, 1),
        "n_ul_ues": len(all_ues), "n_never_granted": len(never),
        "never_granted": never, "served_at_slot_1": served_slot1,
        "last_first_grant_slot": max(first_slot.values()) if first_slot else None,
        "M07_met": m7.get("met"), "M07_total": m7.get("total"),
        "M08_fraction": m8.get("fraction"),
    }


def _task(t):
    return one(*t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-ues", default="2,4,8,16")
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--out", default="sweeps/phase2/g5_consolidation.json")
    ap.add_argument("--attach-seed", action="store_true",
                    help="seed the attach BSR at slot 0, no stagger")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    arms = [x for x in a.arms.split(",") if x]
    ns = [int(x) for x in a.n_ues.split(",")]
    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, n, a.horizon, a.attach_seed)
             for arm in arms for n in ns for s in seeds]
    print(f"{len(tasks)} runs = {len(arms)} arms x {len(ns)} fleet sizes "
          f"x {len(seeds)} seeds @ horizon {a.horizon}")

    rows = [None] * len(tasks)
    for i, (idx, r) in enumerate(run_cells(_task, tasks, a.workers,
                                           cost=lambda t: arm_cost(t[0]) * t[2]),
                                 start=1):
        rows[idx] = r
        print(f"  [{i}/{len(tasks)}] {r['arm']:<12} N={r['n_ues']:<3} "
              f"never_granted={r['n_never_granted']:<3} "
              f"M08={r['M08_fraction']}", flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_state": stamp(), "rows": rows},
                              indent=1, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
