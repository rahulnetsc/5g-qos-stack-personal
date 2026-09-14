"""Probe: does a crumb grant (TB too small for one 300 B heartbeat) reset the
urgency clock without carrying the message?  Per instrument UE: grant-size
split, cadence of HEARTBEAT-CAPABLE grants, and the urgency01 the arm saw for
that UE.  GT-2.2, cap 4.  Scratch only."""
from __future__ import annotations
import json, os, sys, time
from collections import defaultdict, Counter
from pathlib import Path

REPO = Path(r"c:/Users/Smart/Documents/Personal/Rahul R/5g/5g-qos-stack-personal")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))

HORIZON = int(os.environ.get("PROBE_HORIZON", "20000"))
SEEDS = (1097657231, 87989972)
ARMS = tuple(os.environ.get("PROBE_ARMS", "PF,TwoTier,ProtoGkpiD2,ProtoGkpi100").split(","))
NS = tuple(int(x) for x in os.environ.get("PROBE_NS", "16").split(","))
CAPABLE_B = 320   # 300 B heartbeat + L2 headers


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def one(task):
    arm, n, seed = task
    from proto_arms import resolve_arm
    from sim.driver import run as driver_run
    from sim.random_access import RandomAccessConfig
    from sim.scenarios.g3 import build_gt22_scenario, instrument_ue_ids, QFI_TELEMETRY
    from sim.srb import with_srb

    sc = build_gt22_scenario(seed=seed, n_ues=n, horizon_slots=HORIZON)
    instr = sorted(instrument_ue_ids(sc))
    if arm == "ProtoRRage":
        # Existing flags only: every slot is a "reserve slot" (P forced to 1),
        # ordered by slots-since-last-UL-grant, spatial reserve removed.
        # i.e. age-fair round robin with full-band grants, Tiers 1/1.5 intact.
        from scheduler.two_tier_proto import TwoTierProto
        sched = TwoTierProto(min_rb=5, periodic_reserve=True,
                             denial_ordered_periodic=True,
                             reserve_period_mult=1e-6)
    elif arm == "ProtoRRageD2":
        from scheduler.two_tier_proto import TwoTierProto
        sched = TwoTierProto(min_rb=5, periodic_reserve=True,
                             denial_ordered_periodic=True,
                             reserve_depth_under_periodic=2,
                             reserve_period_mult=1e-6)
    else:
        sched = resolve_arm(arm)
    orig = sched.allocate
    last_cap = {}
    cap_gaps = defaultdict(list)     # ue -> gaps between capable grants
    sizes = defaultdict(list)        # ue -> bytes_capacity per grant
    urg = defaultdict(list)          # ue -> urgency01 seen at ranking (proto/twotier)
    rankpos = defaultdict(list)      # ue -> rank position when candidate

    def sink(snap):
        if snap.direction != "UL":
            return
        for pos, e in enumerate(snap.entries):
            if e.ue_id in instr:
                rankpos[e.ue_id].append(pos)
                for nm, v in e.factors:
                    if nm == "urgency01":
                        urg[e.ue_id].append(v)
    sched.rank_sink = sink

    def wrapped(slot, buffers, channel):
        out = orig(slot, buffers, channel)
        for a in out:
            if a.direction != "UL" or a.ue_id not in instr:
                continue
            b = int(a.bytes_capacity)
            sizes[a.ue_id].append(b)
            if b >= CAPABLE_B:
                if a.ue_id in last_cap:
                    cap_gaps[a.ue_id].append(slot.slot_index - last_cap[a.ue_id])
                last_cap[a.ue_id] = slot.slot_index
        return out
    sched.allocate = wrapped
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    t0 = time.time()
    summ = driver_run(with_srb(sc), sched, cqi_delay_slots=8,
                      max_sched_ues=4, random_access=ra)
    wall = time.time() - t0
    fl = summ["flows"]
    res = {}
    for ue in instr:
        rec = fl.get(f"ue{ue}_qfi{QFI_TELEMETRY}", {})
        sz = sizes[ue]
        res[ue] = {
            "grants": len(sz), "crumb_frac": (sum(1 for b in sz if b < CAPABLE_B) / len(sz)) if sz else None,
            "size_p50": pct(sz, .5), "size_p90": pct(sz, .9),
            "capable_gap_p50_ms": (pct(cap_gaps[ue], .5) or 0) * 0.25,
            "capable_gap_p98_ms": (pct(cap_gaps[ue], .98) or 0) * 0.25,
            "capable_gap_max_ms": (max(cap_gaps[ue]) if cap_gaps[ue] else 0) * 0.25,
            "n_capable": len(cap_gaps[ue]) + (1 if ue in last_cap else 0),
            "urg_p50": pct(urg[ue], .5), "urg_p98": pct(urg[ue], .98), "urg_max": max(urg[ue]) if urg[ue] else None,
            "rank_p50": pct(rankpos[ue], .5), "cand_slots": len(rankpos[ue]),
            "tele_delay_p50": rec.get("delay_p50_ms"), "tele_delay_p98": rec.get("delay_p98_ms"),
            "tele_delivered": rec.get("bytes_delivered"),
        }
    return {"arm": arm, "n": n, "seed": seed, "wall_s": round(wall, 1), "ues": res}


def main():
    from regime_sweep import run_cells
    tasks = [(a, n, s) for a in ARMS for n in NS for s in SEEDS]
    workers = max(1, os.cpu_count() - 1)
    rows = [None] * len(tasks)
    for i, r in run_cells(one, tasks, workers, cost=lambda t: t[1]):
        rows[i] = r
    Path(__file__).with_suffix(".json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(f"\n{r['arm']} N={r['n']} seed={r['seed']} ({r['wall_s']}s)")
        for ue, d in r["ues"].items():
            print(f"  ue{ue:<2} grants={d['grants']:5d} crumb={d['crumb_frac']:.2f} sizeB p50/p90={d['size_p50']}/{d['size_p90']}"
                  f" | capable n={d['n_capable']} gap ms p50/p98/max={d['capable_gap_p50_ms']:.1f}/{d['capable_gap_p98_ms']:.1f}/{d['capable_gap_max_ms']:.1f}"
                  f" | urg p50/p98/max={d['urg_p50']}/{d['urg_p98']}/{d['urg_max']} rank_p50={d['rank_p50']} cand={d['cand_slots']}"
                  f" | tele p50/p98={d['tele_delay_p50']}/{d['tele_delay_p98']} deliv={d['tele_delivered']}")


if __name__ == "__main__":
    main()
