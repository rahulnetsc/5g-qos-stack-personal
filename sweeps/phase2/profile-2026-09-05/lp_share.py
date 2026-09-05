"""LP share of driver_run, post-scaling -- same configuration as the
2026-09-04 profile so the numbers are comparable.

Scaling fixes CORRECTNESS, not speed: the LP call is the same call with a
multiplied vector. This measures where the time is, and what the ordering
would be if the LP were made free -- so the post-swap picture is visible
without doing the swap.
"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal")
import numpy as np
import scheduler.tier1 as T1
from sim.driver import run
from sim.parametric import sweep_scenario
from scheduler.two_tier import TwoTier
from scheduler.reservation import Reservation
from sim.baselines.pf import ProportionalFair

ARMS = {"PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": lambda: Reservation(min_rb=5),
        "TwoTier": lambda: TwoTier(min_rb=5)}
out = {}
for arm in ("PF", "Reservation", "TwoTier"):
    lp_t = [0.0]; lp_n = [0]; sca_t = [0.0]; sca_n = [0]
    _lin = T1.linprog
    def timed(*a, **k):
        t = time.perf_counter(); r = _lin(*a, **k)
        lp_t[0] += time.perf_counter()-t; lp_n[0] += 1
        return r
    _sca = T1.solve_tier1
    def timed_sca(*a, **k):
        t = time.perf_counter(); r = _sca(*a, **k)
        sca_t[0] += time.perf_counter()-t; sca_n[0] += 1
        return r
    T1.linprog = timed
    import scheduler.two_tier as TT
    TT.solve_tier1 = timed_sca
    sc = sweep_scenario(seed=1, n_ues=8, horizon_slots=20_000, load_mult=1.0)
    t0 = time.perf_counter()
    run(sc, ARMS[arm](), cqi_delay_slots=8, record_timeseries=True)
    drv = time.perf_counter()-t0
    T1.linprog = _lin; TT.solve_tier1 = _sca
    out[arm] = {"driver_s": drv, "lp_s": lp_t[0], "lp_calls": lp_n[0],
                "tier1_s": sca_t[0], "tier1_calls": sca_n[0]}
    print("%-12s driver=%7.3fs  LP=%7.3fs (%5.1f%%) over %5d calls   "
          "solve_tier1 total=%7.3fs (%5.1f%%) over %d solves"
          % (arm, drv, lp_t[0], 100*lp_t[0]/drv, lp_n[0],
             sca_t[0], 100*sca_t[0]/drv, sca_n[0]))
print()
print("IF THE LP WERE FREE (the 41x-swap upper bound -- not the swap's real gain):")
for arm, v in out.items():
    rem = v["driver_s"] - v["lp_s"]
    print("   %-12s driver %7.3f -> %7.3f s  (%.2fx)   LP share after: 0%%"
          % (arm, v["driver_s"], rem, v["driver_s"]/rem if rem > 0 else float('nan')))
print()
print("IF THE LP WERE 41x FASTER (the measured direct-HiGHS figure):")
for arm, v in out.items():
    rem = v["driver_s"] - v["lp_s"]*(1-1/41)
    print("   %-12s driver %7.3f -> %7.3f s  (%.2fx)   LP share after: %.1f%%"
          % (arm, v["driver_s"], rem, v["driver_s"]/rem, 100*(v["lp_s"]/41)/rem))
json.dump(out, open(Path(__file__).parent/"lp_share.json","w"), indent=1)
