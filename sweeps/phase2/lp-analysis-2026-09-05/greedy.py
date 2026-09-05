"""If the LP separates into two continuous knapsacks, a greedy solves it exactly.

Everything is recovered FROM THE CAPTURED MODEL, not from the scenario:
direction from which capacity row holds the column's nonzero, se from that
entry (a_ij = 1/se), GBR membership and gfbr from the per-flow row, demand
from the column bound, coef from the objective. So this tests the model as
the solver actually received it.

Value per unit of CAPACITY for flow i:
    (coef_i + P) * se_i   while r_i < min(gfbr_i, d_i)   -- also buys down slack
     coef_i      * se_i   above that
Concave in r_i (P > 0), so the greedy by density is exact for a continuous
knapsack.
"""
import sys, pickle, json
from pathlib import Path
import numpy as np

D = Path(__file__).parent
CAP = pickle.load(open(D/"lps.pkl","rb"))
n = len(CAP[0]["c"])//2

def parse(L):
    c, A, b, bnds = L["c"], L["A_ub"], L["b_ub"], L["bounds"]
    se = np.zeros(n); direc = np.full(n, -1)
    for i in range(n):
        for row in (0, 1):
            if A[row, i] != 0:
                se[i] = 1.0/A[row, i]; direc[i] = row
    gfbr = np.zeros(n); isg = np.zeros(n, bool); P = 0.0
    for r in range(2, A.shape[0]):
        cols = np.nonzero(A[r, :n])[0]
        if len(cols) == 1:
            i = cols[0]; isg[i] = True; gfbr[i] = -b[r]; P = c[n+i]
    dem = np.array([bnds[i][1] if bnds[i][1] is not None else np.inf for i in range(n)])
    return -c[:n], se, direc, gfbr, isg, dem, b[0], b[1], P

def greedy(coef, se, direc, gfbr, isg, dem, cap):
    """One direction. Returns r for the flows in `idx`."""
    r = np.zeros(n)
    pieces = []
    for i in range(n):
        if direc[i] < 0 or dem[i] <= 0 or se[i] <= 0:
            continue
        lo = min(gfbr[i], dem[i]) if isg[i] else 0.0
        if lo > 0:
            pieces.append(((coef[i] + P_GLOBAL)*se[i], i, lo))
        hi = dem[i] - lo
        if hi > 0:
            pieces.append((coef[i]*se[i], i, hi))
    pieces.sort(key=lambda t: -t[0])
    left = cap
    for dens, i, q in pieces:
        if left <= 0:
            break
        take = min(q, left*se[i])          # q is in bps; capacity costs 1/se per bps
        r[i] += take
        left -= take/se[i]
    return r

def objective(r, coef, gfbr, isg, P):
    return float(coef @ r - P*np.sum(np.maximum(0.0, gfbr[isg] - r[isg])))

rows = []
SUB = CAP[::8]
nobj = 0; nx = 0; ties = 0; ok = 0
worst = []
for L in SUB:
    if L["x"] is None:
        continue
    coef, se, direc, gfbr, isg, dem, capdl, capul, P = parse(L)
    P_GLOBAL = P
    globals()["P_GLOBAL"] = P
    r = np.zeros(n)
    for d, cap in ((0, capdl), (1, capul)):
        mask = (direc == d)
        rr = greedy(np.where(mask, coef, 0), np.where(mask, se, 0),
                    np.where(mask, direc, -1), gfbr, isg & mask, np.where(mask, dem, 0), cap)
        r += rr
    ok += 1
    xh = L["x"][:n]
    fg, fh = objective(r, coef, gfbr, isg, P), objective(xh, coef, gfbr, isg, P)
    denom = max(1.0, abs(fh))
    if abs(fg - fh)/denom > 1e-9:
        nobj += 1
        worst.append(abs(fg-fh)/denom)
    dx = np.max(np.abs(r - xh))
    if dx > 1.0:
        nx += 1
        if abs(fg - fh)/denom <= 1e-9:
            ties += 1
print("greedy vs HiGHS on %d captured LPs" % ok)
print("  objective differs (rel > 1e-9)   : %d (%.2f%%)" % (nobj, 100*nobj/ok))
if worst:
    print("     worst relative objective gap : %.3g   (greedy WORSE if positive below)" % max(worst))
print("  x differs by > 1 bps             : %d (%.2f%%)" % (nx, 100*nx/ok))
print("  ... of which the objectives AGREE (a TIE, not a disagreement): %d (%.1f%% of the differing)"
      % (ties, 100*ties/max(1,nx)))
json.dump({"solves": ok, "objective_differs": nobj, "x_differs": nx, "of_which_ties": ties},
          open(D/"greedy.json","w"), indent=1)

# --- and against a WELL-CONDITIONED HiGHS -------------------------------
# The greedy is exact by construction, so it is the reference. If scaling
# moves HiGHS TOWARD the greedy, the scaled answer is the true optimum and
# the shipped one is the numerical artefact.
from scipy.optimize import linprog
print()
print("greedy vs HiGHS at several objective scalings (greedy is the exact reference):")
for K in (1.0, 1e3, 1e6):
    agree = 0; tot = 0
    for L in SUB:
        if L["x"] is None:
            continue
        res = linprog(L["c"]*K, A_ub=L["A_ub"], b_ub=L["b_ub"],
                      bounds=L["bounds"], method="highs")
        if not res.success:
            continue
        coef, se, direc, gfbr, isg, dem, capdl, capul, P = parse(L)
        globals()["P_GLOBAL"] = P
        r = np.zeros(n)
        for d, cap in ((0, capdl), (1, capul)):
            mask = (direc == d)
            r += greedy(np.where(mask, coef, 0), np.where(mask, se, 0),
                        np.where(mask, direc, -1), gfbr, isg & mask,
                        np.where(mask, dem, 0), cap)
        tot += 1
        if np.max(np.abs(r - res.x[:n])) <= 1.0:
            agree += 1
    print("   K=%-8g  x agrees with greedy on %d of %d  (%.1f%%)" % (K, agree, tot, 100*agree/tot))
