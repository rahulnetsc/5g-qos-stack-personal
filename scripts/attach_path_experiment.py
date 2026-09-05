"""G5's registered falsifier: does an attach-path grant remove the starvation?

Reads against `docs/attach-path-map.md`, which is CLOSED. Outcomes A1-A6 were
fixed before this file existed; a result fitting none of them is a residual.

THREE CONDITIONS, NOT TWO -- and this is an addition to the DESIGN, not to
the map's outcomes. The map specifies "staggered arrival plus the seed", but
that bundles two changes, and this project's own rule is to decompose before
attributing. Staggering alone could clear the starvation by itself: a UE that
attaches into an empty cell gets served with no competition and populates its
array through the ordinary BSR path, no seed required. Without a stagger-only
arm the result would be unattributable between the two.

    off           no stagger, no seed        -- reproduces the published baseline
    stagger_only  staggered arrival only     -- the hardware-realistic BAD case:
                                                a late joiner meets a loaded cell
                                                with an empty array and no rescue
    stagger_seed  MODEL C                    -- the treatment

THE INSTRUMENT IS UNCHANGED from `scripts/g5_consolidation.py`, so before and
after are within-instrument: `n_never_granted`, `served_at_slot_1`, M07, M08.
That matters because the consolidation
(`n_never_granted > 0` <=> M08 floored, 0 counterexamples in 36 runs) is what
makes this experiment sharp -- if it breaks under the treatment, the
sharpness was borrowed and outcome A5 fires.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import arm_cost, paired_seeds, run_cells   # noqa: E402
from sim.driver import run as driver_run                     # noqa: E402
from sim.parametric import sweep_scenario                    # noqa: E402
from sim.run_record import RunRecord                         # noqa: E402
from sim.scorecard import Population, Scorecard              # noqa: E402
from sim.trace import GrantCollector                         # noqa: E402
from g11_campaign import _arm                                # noqa: E402

SLOT_S = 0.00025
#: Slots between consecutive UE attachments. 200 slots = 50 ms, roughly an
#: RRC-setup interval, and at N=16 the whole stagger is 3,000 slots of a
#: 20,000-slot run -- enough load built up for the last joiner to face a
#: genuinely busy cell, while leaving most of the horizon post-attach.
STAGGER_SLOTS = 200


def _stagger(sc, stagger_slots: int):
    """Give each UE an `active_from_s`, using the EXISTING activation gate
    (`sim/traffic.py`, WP9 G11 commit 4). No new masking mechanism: a UE
    that has not attached generates no traffic, so it has no backlog and is
    not a candidate. Returns (scenario, {ue_id: attach_slot})."""
    ues = sorted({f.ue_id for f in sc.flows})
    at = {u: i * stagger_slots for i, u in enumerate(ues)}
    flows = []
    for f in sc.flows:
        p = dict(f.traffic_params)
        p["active_from_s"] = at[f.ue_id] * SLOT_S
        flows.append(dataclasses.replace(f, traffic_params=p))
    ul = sorted({f.ue_id for f in sc.flows if f.direction == "UL"})
    return dataclasses.replace(sc, flows=flows), {u: at[u] for u in ul}


def one(condition: str, arm: str, seed: int, n_ues: int, horizon: int) -> dict:
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=1.0)
    attach = None
    if condition in ("stagger_only", "stagger_seed"):
        sc, attach = _stagger(sc, STAGGER_SLOTS)
    seed_slots = attach if condition == "stagger_seed" else None

    grants = GrantCollector()
    t0 = time.time()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True,
                   grant_sink=grants, attach_seed_slots=seed_slots)

    # THE MAP'S ACCEPTANCE CONDITION 3, enforced at the point of use rather
    # than trusted: assert the EXPECTED COUNT, derived from the scenario.
    if seed_slots is not None:
        exp, got = s["attach_seeds_expected"], s["attach_seeds_fired"]
        if got != exp:
            raise SystemExit(
                f"attach seed fired {got} of {exp} expected "
                f"({arm} N={n_ues} seed={seed}). A partially-seeded run is "
                f"not a smaller sample of a seeded one -- the UEs that "
                f"missed are self-selected. Refusing to score it.")

    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows, summary=s,
                                 arm={}, meta={})
    scored = Scorecard().score(rec, population=Population.protected_fleet())
    m7, m8 = scored["M07"].value or {}, scored["M08"].value or {}

    ever, first = set(), {}
    for g in grants.finish():
        if g.direction != "UL" or g.retx_count:
            continue
        ever.add(g.ue_id)
        first.setdefault(g.ue_id, g.slot_index)
    all_ul = {f.ue_id for f in sc.flows if f.direction == "UL"}
    never = sorted(all_ul - ever)

    # A UE's own first grant relative to ITS OWN attach, not to slot 0 --
    # under a stagger the two are different questions and only the first
    # one is about the lock-in.
    delay = {u: first[u] - (attach or {}).get(u, 0)
             for u in first} if first else {}
    return {
        "condition": condition, "arm": arm, "seed": seed, "n_ues": n_ues,
        "horizon": horizon, "wall_s": round(time.time() - t0, 1),
        "n_never_granted": len(never), "never_granted": never,
        "seeds_fired": s.get("attach_seeds_fired"),
        "max_first_grant_delay_slots": max(delay.values()) if delay else None,
        "M07_met": m7.get("met"), "M07_total": m7.get("total"),
        "M08_fraction": m8.get("fraction"),
    }


def _task(t):
    return one(*t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="off,stagger_only,stagger_seed")
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-ues", default="2,4,8,16")
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--out", default="sweeps/phase2/attach_path.json")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    conds = [x for x in a.conditions.split(",") if x]
    arms = [x for x in a.arms.split(",") if x]
    ns = [int(x) for x in a.n_ues.split(",")]
    seeds = paired_seeds(a.seeds)
    tasks = [(c, arm, s, n, a.horizon)
             for c in conds for arm in arms for n in ns for s in seeds]
    print(f"{len(tasks)} runs = {len(conds)} conditions x {len(arms)} arms "
          f"x {len(ns)} fleet sizes x {len(seeds)} seeds")

    rows = [None] * len(tasks)
    for i, (idx, r) in enumerate(run_cells(_task, tasks, a.workers,
                                           cost=lambda t: arm_cost(t[1]) * t[3]),
                                 start=1):
        rows[idx] = r
        print(f"  [{i}/{len(tasks)}] {r['condition']:<13} {r['arm']:<12} "
              f"N={r['n_ues']:<3} never={r['n_never_granted']:<3} "
              f"M08={r['M08_fraction']}", flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows}, indent=1, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
