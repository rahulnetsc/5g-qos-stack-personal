"""Is the SCA's failure structural, or a tolerance artefact?

THE ARGUMENT TO TEST. The iteration is r_{k+1} = a*v_k + (1-a)*r_k with
v_k = argmax of the LINEARIZED objective, so v_k is a vertex. A fixed point
requires r* = a*v* + (1-a)*r*, i.e. r* = v*: **the fixed-point set is
exactly the set of vertices that are their own linearized optimum.** Damping
changes the path, never the fixed points. So if the true log-utility optimum
is INTERIOR, no amount of damping or iteration can reach it, and the
sequence must cycle. That is a stronger and more precise claim than "every
iterate is a vertex" -- the iterates are damped and are NOT vertices.

Measured here on real captured LPs:
  1. solve max sum w_i log(r_i) exactly (cvxpy, ECOS/Clarabel)
  2. is that optimum interior, or at a vertex?
  3. run the SCA to the cap and look at the tail -- does it cycle?
"""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal")
import cvxpy as cp
from scipy.optimize import linprog

CAP = pickle.load(open("lps.pkl", "rb"))
n = len(CAP[0]["c"])//2
ALPHA, TOL, MAXIT = 0.2, 1e-6, 150

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
    return A, b, bnds, se, direc, gfbr, isg, dem, P

# weights are recoverable: coef = w/(r_prev+1) and at iteration 0 r_prev=1,
# so the FIRST LP of each solve has coef = w/2 exactly.
first = CAP[0]
w = (-first["c"][:n]) * 2.0
print("recovered weights (should be {1,5}):", sorted(set(np.round(w,6).tolist())))

A, b, bnds, se, direc, gfbr, isg, dem, P = parse(first)

# --- the exact log-utility optimum ---------------------------------------
r = cp.Variable(n, nonneg=True)
s = cp.Variable(n, nonneg=True)
cons = [r <= np.where(np.isfinite(dem), dem, 1e12)]
for d in (0, 1):
    m = (direc == d)
    if m.any():
        cons.append(cp.sum(cp.multiply(np.where(m, 1.0/np.where(se>0,se,1), 0.0), r)) <= b[d])
for i in range(n):
    if isg[i]:
        cons.append(r[i] + s[i] >= gfbr[i])
    else:
        cons.append(s[i] == 0)
obj = cp.Maximize(cp.sum(cp.multiply(w, cp.log(r + 1.0))) - P*cp.sum(s))
prob = cp.Problem(obj, cons)
prob.solve(solver=cp.CLARABEL)
rstar = np.maximum(0.0, r.value)
print("\nexact log-utility optimum solved:", prob.status)

# --- is it interior? A vertex of this polytope has at most (#rows) many
#     variables strictly between their bounds. Count them.
free = 0
for i in range(n):
    lo, hi = 0.0, (dem[i] if np.isfinite(dem[i]) else np.inf)
    if rstar[i] > lo + 1e-3 and rstar[i] < hi - 1e-3:
        free += 1
print("  variables strictly BETWEEN their bounds at the optimum: %d of %d" % (free, n))
print("  (a vertex needs the number of strictly-interior components <= number of")
print("   active constraint rows = %d, so > that means the optimum is NOT a vertex)" % A.shape[0])

# --- run the SCA and look at the tail ------------------------------------
r_prev = np.full(n, 1.0)
hist = []
for it in range(MAXIT):
    coef = w/(r_prev + 1.0)
    c = np.zeros(2*n); c[:n] = -coef; c[n:] = P
    res = linprog(c, A_ub=A, b_ub=b, bounds=bnds, method="highs")
    v = np.maximum(0.0, res.x[:n])
    damped = ALPHA*v + (1-ALPHA)*r_prev
    rel = np.max(np.abs(damped - r_prev)/(r_prev + 1.0))
    hist.append((it, rel, damped.copy(), v.copy()))
    r_prev = damped
print("\nSCA over %d iterations:" % MAXIT)
print("  rel_change at iterations 140-149:", ["%.4g" % h[1] for h in hist[-10:]])
print("  TOL = %g -- reached: %s" % (TOL, any(h[1] < TOL for h in hist)))
tail = np.array([h[2] for h in hist[-20:]])
print("  period-2 test on the tail: max |r_k - r_{k-2}| = %.6g" %
      np.max(np.abs(tail[2:] - tail[:-2])))
print("  period-1 test on the tail: max |r_k - r_{k-1}| = %.6g" %
      np.max(np.abs(tail[1:] - tail[:-1])))
print("\n  distance from the SCA's final iterate to the exact optimum:")
print("     max |r_sca - r*| = %.6g bps" % np.max(np.abs(hist[-1][2] - rstar)))
print("     ||r_sca - r*||/||r*|| = %.4g" % (np.linalg.norm(hist[-1][2]-rstar)/max(1e-9,np.linalg.norm(rstar))))
