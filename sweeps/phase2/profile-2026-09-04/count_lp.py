import sys, time, json
from pathlib import Path
REPO = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import scheduler.tier1 as T
_orig = T.linprog
stats = {"n": 0, "t": 0.0, "shapes": {}}
def counted(c, **kw):
    t0 = time.perf_counter(); r = _orig(c, **kw); stats["t"] += time.perf_counter() - t0
    stats["n"] += 1
    A = kw.get("A_ub")
    if A is not None:
        stats["shapes"][str(A.shape)] = stats["shapes"].get(str(A.shape), 0) + 1
    return r
T.linprog = counted

import wp9_sweep as W
from sim.driver import run
from scheduler import load_two_tier
W._HORIZON[0] = 20000
av = {"n_ues": 8, "load_mult": 1.0}
sc = W._build(seed=1, **av)
sched = load_two_tier(W._TT_CONFIG, min_rb=5)
t0 = time.perf_counter()
run(sc, sched, **W._driver_kwargs(**av))
wall = time.perf_counter() - t0
print(json.dumps({"driver_wall_s": wall, "linprog_calls": stats["n"],
                  "linprog_total_s": stats["t"],
                  "linprog_pct_of_driver": 100*stats["t"]/wall,
                  "mean_ms_per_call": 1000*stats["t"]/max(1,stats["n"]),
                  "A_ub_shapes": stats["shapes"]}, indent=2))
