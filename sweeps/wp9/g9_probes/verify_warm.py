import sys, json
from pathlib import Path
ROOT = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"scripts"))
from regime_sweep import paired_seeds
from sim.driver import run
from sim.run_record import RunRecord
from sim.scenarios.g9 import gt61_warm_rejoin
from scheduler import load_two_tier
_TT = str(ROOT/"scheduler"/"scheduler_config.yaml")
rows=[]
for seed in paired_seeds(10):
    sc = gt61_warm_rejoin(seed=seed, n_neighbours=7)
    j=[u for u in sc.ues if u.join is not None][0]
    sched=sum(1 for e in j.join.events if e.kind=="app_restart")
    s=run(sc, load_two_tier(_TT, min_rb=5), cqi_delay_slots=8, record_timeseries=True)
    rec=RunRecord.from_summary(scenario_name=sc.name, scheduler_name="TwoTier", seed=seed,
                               flow_configs=sc.flows, summary=s, arm={}, meta={})
    ev=[e for e in (rec.join_events or []) if e.path=="warm"]
    row={"seed":seed,"sched":sched,"n_ev":len(ev),
         "n_completed":sum(1 for e in ev if e.attached_ts_s is not None),
         "trigger_attach":[(e.trigger_slot,e.attached_slot) for e in ev]}
    rows.append(row); print(json.dumps(row), flush=True)
print("TOTAL sched", sum(r["sched"] for r in rows), "events", sum(r["n_ev"] for r in rows),
      "completed", sum(r["n_completed"] for r in rows))
