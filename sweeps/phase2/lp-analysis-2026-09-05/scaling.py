"""Does scaling the objective by a constant reduce vertex ambiguity?

THE INSTRUMENT IS COLUMN PERMUTATION, and it is chosen deliberately.
Scaling `c` by K > 0 is argmax-invariant, so ANY change in the returned `x`
is the solver choosing differently among equal optima -- but comparing
scaled against unscaled conflates "scaling changed the vertex" with "the
vertex was ambiguous". Permuting the columns is a presentation change that
is also exactly argmax-invariant, and it can be applied at EACH scaling
independently. A unique optimum returns the same point under any column
order; a degenerate one need not. So the permutation-disagreement rate at a
given K measures that K's ambiguity, and the comparison across K is
like-for-like.
"""
import sys, pickle, json
from pathlib import Path
import numpy as np
from scipy.optimize import linprog

D = Path(__file__).parent
CAP = pickle.load(open(D/"lps.pkl","rb"))
rng = np.random.default_rng(0)
SUB = CAP[::8]                      # even subsample, deterministic
n_cols = len(CAP[0]["c"])
perm = rng.permutation(n_cols)
inv = np.argsort(perm)

def solve(c, A, b, bnds):
    r = linprog(c, A_ub=A, b_ub=b, bounds=bnds, method="highs")
    return (r.x, r.fun) if r.success else (None, None)

rows = []
for K in (1.0, 1e3, 1e6, 1e7):
    diff = 0; ok = 0; maxdx = []; objgap = []
    for L in SUB:
        c, A, b, bnds = L["c"]*K, L["A_ub"], L["b_ub"], L["bounds"]
        x1, f1 = solve(c, A, b, bnds)
        # same model, columns permuted -- mathematically identical
        x2p, f2 = solve(c[perm], A[:, perm], b, [bnds[i] for i in perm])
        if x1 is None or x2p is None:
            continue
        ok += 1
        x2 = x2p[inv]
        d = np.max(np.abs(x1 - x2))
        maxdx.append(d)
        denom = max(1.0, abs(f1))
        objgap.append(abs(f1 - f2)/denom)
        if d > 1.0:                 # 1 bps -- far below any meaningful rate
            diff += 1
    rows.append({"K": K, "solves": ok, "different_vertex": diff,
                 "pct": 100*diff/max(1,ok),
                 "median_max_dx": float(np.median(maxdx)) if maxdx else None,
                 "max_max_dx": float(np.max(maxdx)) if maxdx else None,
                 "max_rel_obj_gap": float(np.max(objgap)) if objgap else None})
    print("K=%-8g solves=%-5d different vertex=%-5d (%5.1f%%)  median|dx|=%-12.6g "
          "max|dx|=%-12.6g  max rel obj gap=%.3g"
          % (K, ok, diff, 100*diff/max(1,ok),
             np.median(maxdx), np.max(maxdx), np.max(objgap)))
json.dump(rows, open(D/"scaling.json","w"), indent=1)
