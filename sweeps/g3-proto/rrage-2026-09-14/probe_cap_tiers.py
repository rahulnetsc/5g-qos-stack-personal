"""Probe: (1) UL PRB allocated-then-discarded by cap_ues_per_slot, per arm;
(2) which key tier decides the top UL rank per slot.  GT-2.2, cap 4.
Scratch only -- nothing here touches the repo."""
from __future__ import annotations
import json, os, sys, time
from collections import Counter
from pathlib import Path

REPO = Path(r"c:/Users/Smart/Documents/Personal/Rahul R/5g/5g-qos-stack-personal")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))

HORIZON = int(os.environ.get("PROBE_HORIZON", "8000"))
SEEDS = (1097657231, 87989972)
ARMS = ("TwoTier", "ProtoGkpiD2", "PF", "Reservation")
NS = (8, 12, 16)


def one(task):
    arm, n, seed = task
    import scheduler.two_tier as tt
    import scheduler.reservation as rs
    import sim.baselines.pf as pfm
    from scheduler.link import cap_ues_per_slot as real_cap
    from proto_arms import resolve_arm
    from sim.driver import run as driver_run
    from sim.random_access import RandomAccessConfig
    from sim.scenarios.g3 import build_gt22_scenario
    from sim.srb import with_srb

    stats = Counter()

    def counting_cap(allocs, max_ues):
        out = real_cap(allocs, max_ues)
        ul_in = [a for a in allocs if a.direction == "UL"]
        if ul_in:
            ul_out = [a for a in out if a.direction == "UL"]
            stats["ul_prb_alloc"] += sum(int(a.prbs) for a in ul_in)
            stats["ul_prb_kept"] += sum(int(a.prbs) for a in ul_out)
            stats["ul_ues_alloc"] += len({a.ue_id for a in ul_in})
            stats["ul_ues_kept"] += len({a.ue_id for a in ul_out})
            stats["ul_slots"] += 1
            if len({a.ue_id for a in ul_in}) > max_ues:
                stats["ul_slots_truncated"] += 1
        return out

    for mod in (tt, rs, pfm):
        mod.cap_ues_per_slot = counting_cap

    decide = Counter()          # which term decides top-1 vs top-2 (UL)
    top_tier = Counter()        # top-1's own tier-1/1.5 state

    def sink(snap):
        if snap.direction != "UL" or len(snap.entries) < 1:
            return
        names = snap.term_names
        e0 = snap.entries[0]
        if len(snap.entries) >= 2:
            e1 = snap.entries[1]
            for i, nm in enumerate(names):
                if e0.key[i] != e1.key[i]:
                    decide[nm] += 1
                    break
            else:
                decide["<tie>"] += 1
        else:
            decide["<single>"] += 1
        # For arms whose key carries sched_inactive / floor_fire, count the
        # top-1 entries that are decided by those tiers being active.
        for i, nm in enumerate(names):
            if nm in ("sched_inactive", "floor_fire") and e0.key[i] == 0:
                top_tier[nm] += 1

    sc = build_gt22_scenario(seed=seed, n_ues=n, horizon_slots=HORIZON)
    sched = resolve_arm(arm)
    sched.rank_sink = sink
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    t0 = time.time()
    summ = driver_run(with_srb(sc), sched, cqi_delay_slots=8,
                      max_sched_ues=4, random_access=ra)
    wall = time.time() - t0
    counters = dict(getattr(sched, "counters", {}) or {})
    return {
        "arm": arm, "n": n, "seed": seed, "wall_s": round(wall, 1),
        "cap": dict(stats),
        "decide": dict(decide),
        "top_tier": dict(top_tier),
        "ul_util": summ.get("ul_prb_utilization"),
        "counters": {k: v for k, v in counters.items()
                     if k.startswith(("gpd_", "gper_", "gpb_", "gkpi_"))},
    }


def main():
    from regime_sweep import run_cells
    tasks = [(a, n, s) for a in ARMS for n in NS for s in SEEDS]
    workers = max(1, os.cpu_count() - 1)
    rows = [None] * len(tasks)
    t0 = time.time()
    for i, r in run_cells(one, tasks, workers, cost=lambda t: t[1]):
        rows[i] = r
        c = r["cap"]
        disc = 1 - c["ul_prb_kept"] / c["ul_prb_alloc"] if c.get("ul_prb_alloc") else float("nan")
        print(f"{r['arm']:12s} N={r['n']:2d} seed={r['seed']:<11d} "
              f"UL PRB discarded={disc:6.1%}  ul_util={r['ul_util']}  "
              f"slots_trunc={c.get('ul_slots_truncated',0)}/{c.get('ul_slots',0)}  "
              f"{r['wall_s']}s", flush=True)
    out = Path(__file__).with_suffix(".json")
    out.write_text(json.dumps({"horizon": HORIZON, "rows": rows}, indent=1))
    print(f"\nwrote {out}  ({time.time()-t0:.0f}s, {workers} workers)")
    print("\n=== which key term decides top-1 vs top-2 (UL slots) ===")
    for r in rows:
        tot = sum(r["decide"].values()) or 1
        parts = ", ".join(f"{k}={v/tot:.1%}" for k, v in
                          sorted(r["decide"].items(), key=lambda kv: -kv[1]))
        print(f"{r['arm']:12s} N={r['n']:2d} seed={r['seed']:<11d} {parts}")
    print("\n=== proto counters ===")
    for r in rows:
        if r["counters"]:
            print(f"{r['arm']:12s} N={r['n']:2d} {r['counters']}")


if __name__ == "__main__":
    main()
