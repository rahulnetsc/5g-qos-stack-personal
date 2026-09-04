"""Capture ONE real Tier-1 LP from a live run, then time it three ways:
scipy linprog (what ships), scipy linprog with the HiGHS options dict
pre-checked out of the way, and a direct highspy solve of the same model.
The question is how much of the 0.66 ms/call is the simplex and how much is
scipy's Python-side wrapper."""
import sys, time, json
from pathlib import Path
import numpy as np
REPO = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import scheduler.tier1 as T

captured = {}
_orig = T.linprog
def grab(c, **kw):
    if not captured:
        captured.update({"c": np.array(c), **{k: kw.get(k) for k in ("A_ub","b_ub","bounds")}})
    return _orig(c, **kw)
T.linprog = grab

import wp9_sweep as W
from sim.driver import run
from scheduler import load_two_tier
W._HORIZON[0] = 800          # just long enough to trigger one Tier-1 solve
av = {"n_ues": 8, "load_mult": 1.0}
sc = W._build(seed=1, **av)
run(sc, load_two_tier(W._TT_CONFIG, min_rb=5), **W._driver_kwargs(**av))
T.linprog = _orig

c, A, b, bnds = captured["c"], captured["A_ub"], captured["b_ub"], captured["bounds"]
print("LP shape:", A.shape, "n_vars", c.size)

from scipy.optimize import linprog
N = 400
t0 = time.perf_counter()
for _ in range(N):
    r = linprog(c, A_ub=A, b_ub=b, bounds=bnds, method="highs")
t_scipy = (time.perf_counter() - t0) / N

# Direct highspy on the identical model.
import highspy
from scipy.sparse import csc_matrix
Acsc = csc_matrix(A)
lo = np.array([x[0] if x[0] is not None else -highspy.kHighsInf for x in bnds], dtype=float) \
     if isinstance(bnds, (list, tuple)) and not isinstance(bnds[0], (int, float)) else None
if lo is None:
    lo = np.full(c.size, float(bnds[0])); hi = np.full(c.size, highspy.kHighsInf if bnds[1] is None else float(bnds[1]))
else:
    hi = np.array([x[1] if x[1] is not None else highspy.kHighsInf for x in bnds], dtype=float)

def build_and_solve():
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    lp = highspy.HighsLp()
    lp.num_col_ = c.size
    lp.num_row_ = A.shape[0]
    lp.col_cost_ = c
    lp.col_lower_ = lo
    lp.col_upper_ = hi
    lp.row_lower_ = np.full(A.shape[0], -highspy.kHighsInf)
    lp.row_upper_ = b
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_ = Acsc.indptr
    lp.a_matrix_.index_ = Acsc.indices
    lp.a_matrix_.value_ = Acsc.data
    h.passModel(lp)
    h.run()
    return np.array(h.getSolution().col_value)

x_ref = r.x
x_hs = build_and_solve()
t0 = time.perf_counter()
for _ in range(N):
    build_and_solve()
t_direct = (time.perf_counter() - t0) / N

# And a reused Highs instance with only the objective changed -- the SCA
# loop changes ONLY `c` between iterations (A_ub, b_ub, bounds are built
# once outside the loop in tier1.py).
h = highspy.Highs()
h.setOptionValue("output_flag", False)
lp = highspy.HighsLp()
lp.num_col_ = c.size; lp.num_row_ = A.shape[0]
lp.col_cost_ = c; lp.col_lower_ = lo; lp.col_upper_ = hi
lp.row_lower_ = np.full(A.shape[0], -highspy.kHighsInf); lp.row_upper_ = b
lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
lp.a_matrix_.start_ = Acsc.indptr; lp.a_matrix_.index_ = Acsc.indices
lp.a_matrix_.value_ = Acsc.data
h.passModel(lp)
h.run()
idx = np.arange(c.size, dtype=np.int32)
t0 = time.perf_counter()
for _ in range(N):
    h.changeColsCost(c.size, idx, c)
    h.run()
    _ = np.array(h.getSolution().col_value)
t_warm = (time.perf_counter() - t0) / N

print(json.dumps({
    "scipy_linprog_ms": 1000*t_scipy,
    "highspy_fresh_ms": 1000*t_direct,
    "highspy_warm_reuse_ms": 1000*t_warm,
    "max_abs_diff_scipy_vs_highspy": float(np.max(np.abs(x_ref - x_hs))),
}, indent=2))
