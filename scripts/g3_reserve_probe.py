"""Does FIX-2's GBR follower reserve clamp every uplink grant to min_rb?

  reserve_rb = gbr_below[i] * min_rb
  cap        = max(prbs_left - reserve_rb, min_rb)
  max_rbSize = min(slot.prb_count, cap)

`gbr_below[i]` counts still-unserved candidates ranked STRICTLY AFTER i that
have `has_gbr and gbr_bytes_slot > 0`. On a 55-PRB carrier with min_rb = 5,
eleven such followers exhaust the band and the `max(..., min_rb)` floor pins
EVERY candidate -- including the top-ranked one -- at 5 PRB.

Reconstructed exactly, without touching the scheduler: the rank sink gives the
sorted candidate list per slot with `has_gbr`/`gbr_bytes_slot` as recorded
factors, and a pass-through wrapper on `_emit_grant` gives the realised PRB
count per grant in emission (= candidate) order, which is what makes
`prbs_left` recoverable.
"""
import sys
from collections import defaultdict
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal/scripts")

from scheduler.two_tier import TwoTier, _UL_TERMS, _UL_FACTORS
from sim.scenarios.g3 import build_gt22_scenario, QFI_TELEMETRY
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.run_record import RunRecord
from sim.srb import with_srb
from g11_campaign import _arm

SNAPS = {}          # slot -> [(ue_id, key, factors dict)]
GRANTS = []         # (slot, ue_id, prbs_used, tbs_bytes) in emission order


class Sink:
    def __call__(self, snap):
        if snap.direction != "UL":
            return
        SNAPS[snap.slot_index] = [
            (e.ue_id, e.key, dict(e.factors)) for e in snap.entries]


_real_emit = TwoTier._emit_grant


def emit_spy(self, ue_id, direction, prbs_used, tbs_bytes, flows, buffers,
             cce_cost, snr_db, slot_index, bler):
    if direction == "UL":
        GRANTS.append((slot_index, ue_id, prbs_used, tbs_bytes))
    return _real_emit(self, ue_id, direction, prbs_used, tbs_bytes, flows,
                      buffers, cce_cost, snr_db, slot_index, bler)


def run(n_ues, seed, instrument=True, tgbr=False):
    SNAPS.clear(); GRANTS.clear()
    sc = build_gt22_scenario(seed=seed, n_ues=n_ues, horizon_slots=40_000,
                             telemetry_gbr=tgbr)
    sched = _arm("TwoTier")
    if instrument:
        sched.rank_sink = Sink()
        TwoTier._emit_grant = emit_spy
    try:
        ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
        summ = driver_run(with_srb(sc), sched, cqi_delay_slots=8,
                          max_sched_ues=4, random_access=ra)
    finally:
        TwoTier._emit_grant = _real_emit
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="TwoTier",
                                 seed=seed, flow_configs=sc.flows, summary=summ,
                                 arm={}, meta={})
    return sc, rec


def analyse(n_ues, prb_count, min_rb=5):
    si = _UL_TERMS.index("sched_inactive")
    by_slot = defaultdict(list)
    for g in GRANTS:
        by_slot[g[0]].append(g)

    rows = []
    for slot, gs in by_slot.items():
        snap = SNAPS.get(slot)
        if not snap:
            continue
        rank_of = {ue: i for i, (ue, _, _) in enumerate(snap)}
        # gbr_below[i], exactly as FIX-2 computes it
        gbr_below = [0] * len(snap)
        running = 0
        for i in range(len(snap) - 1, -1, -1):
            gbr_below[i] = running
            ue, key, fac = snap[i]
            if (key[si] != 0) and fac["has_gbr"] and fac["gbr_bytes_slot"] > 0:
                running += 1
        # walk grants in candidate order to recover prbs_left
        gs = sorted(gs, key=lambda g: rank_of.get(g[1], 10**6))
        prbs_left = prb_count
        for slot_, ue, prbs, tbs in gs:
            i = rank_of.get(ue)
            if i is None:
                continue
            reserve = gbr_below[i] * min_rb
            raw_cap = prbs_left - reserve
            clamped = raw_cap < min_rb
            cap = max(raw_cap, min_rb)
            rows.append({
                "slot": slot_, "ue": ue, "rank": i, "n_cand": len(snap),
                "gbr_below": gbr_below[i], "prbs_left": prbs_left,
                "raw_cap": raw_cap, "cap": cap, "clamped": clamped,
                "max_rbSize": min(prb_count, cap),
                "prbs_used": prbs, "tbs": tbs,
                "prb_limited_by_cap": prbs == min(prb_count, cap),
            })
            prbs_left -= prbs
    return rows


def report(tag, rows, min_rb=5):
    if not rows:
        print(f"{tag}: no rows"); return
    top = [r for r in rows if r["rank"] == 0]
    cl = [r for r in rows if r["clamped"]]
    at_min = [r for r in rows if r["prbs_used"] == min_rb]
    capbound = [r for r in rows if r["prb_limited_by_cap"]]
    print(f"\n=== {tag} ===")
    print(f"  UL grants reconstructed              {len(rows)}")
    print(f"  gbr_below: median {sorted(r['gbr_below'] for r in rows)[len(rows)//2]}  "
          f"max {max(r['gbr_below'] for r in rows)}")
    print(f"  reserve CLAMPED to min_rb (raw cap < {min_rb}):  "
          f"{len(cl)} of {len(rows)}  ({100.0*len(cl)/len(rows):.1f}%)")
    print(f"  grant EQUALS max_rbSize (cap is what binds):     "
          f"{len(capbound)} of {len(rows)}  ({100.0*len(capbound)/len(rows):.1f}%)")
    print(f"  grant is exactly min_rb = {min_rb} PRB:                    "
          f"{len(at_min)} of {len(rows)}  ({100.0*len(at_min)/len(rows):.1f}%)")
    if top:
        tcl = [r for r in top if r["clamped"]]
        print(f"  TOP-RANKED candidate: {len(top)} grants, clamped on {len(tcl)} "
              f"({100.0*len(tcl)/len(top):.1f}%)  -- ranked first, still floored")
    prbs = sorted(r["prbs_used"] for r in rows)
    tbs = sorted(r["tbs"] for r in rows)
    print(f"  PRB per grant: median {prbs[len(prbs)//2]}  max {prbs[-1]}")
    print(f"  TB  per grant: median {tbs[len(tbs)//2]}  max {tbs[-1]}")


if __name__ == "__main__":
    from sim.config import CarrierConfig
    import os
    TG = os.environ.get("TGBR", "0") == "1"
    NS = [int(x) for x in os.environ.get("NS", "6,12,16,24").split(",")]
    for n in NS:
        sc, rec = run(n, 1, tgbr=TG)
        # PRB count from the scenario's own carrier, not assumed
        from sim.resource import ResourceGrid
        grid = ResourceGrid(sc.carrier, sc.tdd)
        prb = grid.prb_count
        rows = analyse(n, prb)
        report(f"N={n}, TwoTier, telemetry PBR {'GFBR' if TG else '0'}, "
                     f"prb_count={prb}, min_rb=5", rows)
        tel = {k: v.message_count for k, v in rec.flows.items()
               if v.qfi == QFI_TELEMETRY}
        print(f"  telemetry delivered: {sorted(tel.values())}")
