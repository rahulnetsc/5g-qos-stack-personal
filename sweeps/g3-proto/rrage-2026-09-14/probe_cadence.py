"""Probe: per-UE UL inter-grant interval (service cadence) vs telemetry
latency, PF / TwoTier / ProtoGkpiD2, GT-2.2 cap 4.  Hypothesis: Proto's
telemetry p98 at large N is set by per-UE cycle time (long bursts, rare
visits), not by capacity -- protected UL throughput already equals PF's.
Scratch only."""
from __future__ import annotations
import json, os, sys, time
from collections import defaultdict
from pathlib import Path

REPO = Path(r"c:/Users/Smart/Documents/Personal/Rahul R/5g/5g-qos-stack-personal")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))

HORIZON = int(os.environ.get("PROBE_HORIZON", "20000"))
SEEDS = (1097657231, 87989972)
ARMS = tuple(os.environ.get("PROBE_ARMS", "PF,TwoTier,ProtoGkpiD2").split(","))
NS = tuple(int(x) for x in os.environ.get("PROBE_NS", "8,16,24").split(","))


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
    from sim.scenarios.g3 import build_gt22_scenario, instrument_ue_ids
    from sim.srb import with_srb

    sc = build_gt22_scenario(seed=seed, n_ues=n, horizon_slots=HORIZON)
    sched = resolve_arm(arm)
    orig = sched.allocate
    last = {}
    gaps = defaultdict(list)          # ue -> inter-grant gaps (slots)
    prbs = defaultdict(list)          # ue -> PRB per grant
    ngr = defaultdict(int)

    def wrapped(slot, buffers, channel):
        out = orig(slot, buffers, channel)
        seen = set()
        for a in out:
            if a.direction != "UL" or a.ue_id in seen:
                continue
            seen.add(a.ue_id)
            ngr[a.ue_id] += 1
            prbs[a.ue_id].append(int(a.prbs))
            if a.ue_id in last:
                gaps[a.ue_id].append(slot.slot_index - last[a.ue_id])
            last[a.ue_id] = slot.slot_index
        return out
    sched.allocate = wrapped
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    t0 = time.time()
    summ = driver_run(with_srb(sc), sched, cqi_delay_slots=8,
                      max_sched_ues=4, random_access=ra)
    wall = time.time() - t0

    # telemetry flows: 5QI-ish by name -- use the scenario's own instrument ids
    instr = set(instrument_ue_ids(sc))
    from sim.scenarios.g3 import QFI_TELEMETRY
    tele = [f for f in sc.flows if f.direction == "UL" and f.qfi == QFI_TELEMETRY]
    fl = summ.get("flows", {})
    tele_lat = {}
    for f in tele:
        rec = fl.get(f"ue{f.ue_id}_qfi{f.qfi}") or {}
        tele_lat[f.ue_id] = {k: rec.get(k) for k in rec
                             if any(s in k for s in ("p98", "p50", "max", "complet", "delivered"))}
    all_gaps = [g for ue in gaps for g in gaps[ue]]
    per_ue = {ue: {"n": ngr[ue], "gap_p50": pct(gaps[ue], .5), "gap_p98": pct(gaps[ue], .98),
                   "gap_max": max(gaps[ue]) if gaps[ue] else None,
                   "prb_p50": pct(prbs[ue], .5)} for ue in sorted(ngr)}
    return {"arm": arm, "n": n, "seed": seed, "wall_s": round(wall, 1),
            "gap_p50": pct(all_gaps, .5), "gap_p98": pct(all_gaps, .98),
            "gap_max": max(all_gaps) if all_gaps else None,
            "prb_p50": pct([p for ue in prbs for p in prbs[ue]], .5),
            "ul_util": summ.get("ul_prb_utilization"),
            "per_ue": per_ue, "tele_lat": tele_lat, "instr": sorted(instr),
            "flow_keys_sample": list(fl)[:3]}


def main():
    from regime_sweep import run_cells
    tasks = [(a, n, s) for a in ARMS for n in NS for s in SEEDS]
    workers = max(1, os.cpu_count() - 1)
    rows = [None] * len(tasks)
    t0 = time.time()
    for i, r in run_cells(one, tasks, workers, cost=lambda t: t[1]):
        rows[i] = r
        print(f"{r['arm']:12s} N={r['n']:2d} seed={r['seed']:<11d} "
              f"UL inter-grant slots p50={r['gap_p50']} p98={r['gap_p98']} max={r['gap_max']}  "
              f"PRB/grant p50={r['prb_p50']}  util={r['ul_util']:.3f}  {r['wall_s']}s", flush=True)
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps({"horizon": HORIZON, "rows": rows}, indent=1))
    print(f"\nwrote {out} ({time.time()-t0:.0f}s)")
    print("\n=== instrument UE telemetry latency (from summary) ===")
    for r in rows:
        print(f"{r['arm']:12s} N={r['n']:2d} seed={r['seed']:<11d} instr={r['instr']} keys={r['flow_keys_sample']}")
        for ue, d in r["tele_lat"].items():
            if ue in r["instr"]:
                pu = r["per_ue"].get(ue, {})
                print(f"    ue{ue}: {d}  | grants={pu.get('n')} gap_p50={pu.get('gap_p50')} gap_p98={pu.get('gap_p98')} gap_max={pu.get('gap_max')}")


if __name__ == "__main__":
    main()
