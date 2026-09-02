import sys, json
from pathlib import Path
ROOT = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"scripts"))
from regime_sweep import paired_seeds
from sim.driver import run
from sim.run_record import RunRecord
from sim.scenarios.g9 import gt61_warm_rejoin
from sim.baselines.pf import ProportionalFair
from scheduler.reservation import Reservation
tot={}
for name, fac in (("PF", lambda: ProportionalFair(ewma_window_slots=200)),
                  ("Reservation", lambda: Reservation(min_rb=5))):
    sched=ev=comp=0
    for seed in paired_seeds(10):
        sc = gt61_warm_rejoin(seed=seed, n_neighbours=7)
        j=[u for u in sc.ues if u.join is not None][0]
        sched+=sum(1 for e in j.join.events if e.kind=="app_restart")
        s=run(sc, fac(), cqi_delay_slots=8, record_timeseries=True)
        rec=RunRecord.from_summary(scenario_name=sc.name, scheduler_name=name, seed=seed,
                                   flow_configs=sc.flows, summary=s, arm={}, meta={})
        e=[x for x in (rec.join_events or []) if x.path=="warm"]
        ev+=len(e); comp+=sum(1 for x in e if x.attached_ts_s is not None)
    tot[name]=(sched,ev,comp); print(name, "sched",sched,"events",ev,"completed",comp, flush=True)
