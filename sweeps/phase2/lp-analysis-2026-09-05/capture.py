"""Capture every Tier-1 LP of one real run, unperturbed.

Wraps `scipy.optimize.linprog` where `scheduler/tier1.py` imported it and
PASSES THROUGH -- the run gets the real solver's real answer, so the
capture is a pure observation and the run is not disturbed. Everything
downstream is analysis on the captured models.
"""
import sys, pickle
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import numpy as np
import scheduler.tier1 as T1
from sim.driver import run
from sim.parametric import sweep_scenario
from scheduler.two_tier import TwoTier

CAP = []
_orig = T1.linprog
def spy(c, A_ub=None, b_ub=None, bounds=None, method="highs", **kw):
    res = _orig(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method=method, **kw)
    CAP.append({"c": np.array(c, float), "A_ub": np.array(A_ub, float),
                "b_ub": np.array(b_ub, float), "bounds": list(bounds),
                "x": np.array(res.x, float) if res.success else None,
                "fun": float(res.fun) if res.success else None,
                "ok": bool(res.success)})
    return res
T1.linprog = spy

sc = sweep_scenario(seed=1097657231, n_ues=16, horizon_slots=20_000, load_mult=1.0)
run(sc, TwoTier(min_rb=5), cqi_delay_slots=8, record_timeseries=True)
T1.linprog = _orig

out = Path(__file__).parent / "lps_n16.pkl"
with out.open("wb") as fh:
    pickle.dump(CAP, fh)
print(f"captured {len(CAP)} LPs -> {out}")
n = (len(CAP[0]['c']))//2
print(f"n_flows={n}  n_cols={len(CAP[0]['c'])}  n_rows={CAP[0]['A_ub'].shape[0]}")
