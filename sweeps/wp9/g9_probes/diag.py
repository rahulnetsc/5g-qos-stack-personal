import sys, json
from pathlib import Path
ROOT = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"scripts"))
from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.run_record import RunRecord
from sim.scenarios.g9 import gt62_cold_attach, gt61_warm_rejoin
from scheduler import load_two_tier
_TT = str(ROOT/"scheduler"/"scheduler_config.yaml")
seed = 1826701614
for label, build, armname, fac in [
    ("cold/TwoTier", gt62_cold_attach, "TwoTier", lambda: load_two_tier(_TT, min_rb=5)),
    ("cold/PF", gt62_cold_attach, "PF", lambda: ProportionalFair(ewma_window_slots=200)),
    ("warm/TwoTier", gt61_warm_rejoin, "TwoTier", lambda: load_two_tier(_TT, min_rb=5)),
]:
    sc = build(seed=seed, n_neighbours=7)
    s = run(sc, fac(), cqi_delay_slots=8, record_timeseries=True)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=armname, seed=seed,
                                 flow_configs=sc.flows, summary=s, arm={}, meta={})
    print("==", label)
    for fr in rec.flows.values():
        if fr.ue_id == 1:
            print(f"   {fr.key:16s} dir={fr.direction} qfi={fr.qfi} arrived={fr.bytes_arrived} "
                  f"delivered={fr.bytes_delivered} dropped_pdb={fr.bytes_dropped_pdb}")
    ev = [(e.path, e.trigger_slot, e.attached_slot) for e in (rec.join_events or [])]
    print("   events:", ev)
