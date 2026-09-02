"""Verify: per arm/seed, scheduled cold cycles vs recorded cold events vs completed attaches."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
ROOT = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from regime_sweep import paired_seeds
from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.run_record import RunRecord
from sim.scenarios.g9 import gt62_cold_attach, joiner_ue_id
from scheduler import load_two_tier
from scheduler.reservation import Reservation

_TT = str(ROOT / "scheduler" / "scheduler_config.yaml")
ARMS = {"PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": lambda: Reservation(min_rb=5),
        "TwoTier": lambda: load_two_tier(_TT, min_rb=5)}

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    n_seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    seeds = paired_seeds(n_seeds)
    rows = []
    for arm, fac in ARMS.items():
        if which != "all" and arm != which:
            continue
        for seed in seeds:
            t0 = time.time()
            sc = gt62_cold_attach(seed=seed, n_neighbours=7)
            joiner = [ue for ue in sc.ues if ue.join is not None][0]
            sched_on = sum(1 for e in joiner.join.events if e.kind == "power_on")
            sched_off = sum(1 for e in joiner.join.events if e.kind == "power_off")
            summary = run(sc, fac(), cqi_delay_slots=8, record_timeseries=True)
            rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                         seed=seed, flow_configs=sc.flows,
                                         summary=summary, arm={}, meta={})
            ev = [e for e in (rec.join_events or []) if e.path == "cold"]
            other = [(e.path, e.trigger_slot) for e in (rec.join_events or []) if e.path != "cold"]
            comp = [e for e in ev if e.attached_ts_s is not None]
            row = {"arm": arm, "seed": seed, "sched_power_on": sched_on,
                   "sched_power_off": sched_off,
                   "n_cold_events": len(ev), "n_completed": len(comp),
                   "other_path_events": other,
                   "events": [{"trigger_slot": e.trigger_slot,
                               "attached_slot": e.attached_slot,
                               "phases": e.phases,
                               "timer_expiries": e.timer_expiries,
                               "handshake_rtt_ms": e.handshake_rtt_ms} for e in ev],
                   "secs": round(time.time() - t0, 1)}
            rows.append(row)
            print(json.dumps(row), flush=True)
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("/tmp/verify_cold.json")
    out.write_text(json.dumps(rows, indent=2))
    print("wrote", out)

main()
