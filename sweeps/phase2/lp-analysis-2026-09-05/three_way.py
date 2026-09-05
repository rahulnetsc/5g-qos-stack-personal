"""Shipped vs scaled HiGHS vs exact greedy: correctness, speed, determinism.

REPORT ONLY. Nothing is implemented; this decides which is the right target
and what its fidelity argument would have to be.
"""
import pickle, sys, time, json
import numpy as np
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal")
from scipy.optimize import linprog
exec(open("greedy.py").read().split("rows = []")[0])
SUB = CAP[::8]
K = 1e4

def greedy_x(L):
    coef, se, direc, gfbr, isg, dem, capdl, capul, P = parse(L)
    globals()["P_GLOBAL"] = P
    r = np.zeros(n)
    for d, cap in ((0, capdl), (1, capul)):
        m = (direc == d)
        r += greedy(np.where(m, coef, 0), np.where(m, se, 0),
                    np.where(m, direc, -1), gfbr, isg & m, np.where(m, dem, 0), cap)
    return r

# --- correctness (exact greedy is the reference) ------------------------
res = {}
for name, K_ in (("shipped (K=1)", 1.0), ("scaled (K=1e4)", K)):
    ag = 0; better = 0; tot = 0
    for L in SUB:
        if L["x"] is None: continue
        r = linprog(L["c"]*K_, A_ub=L["A_ub"], b_ub=L["b_ub"], bounds=L["bounds"], method="highs")
        if not r.success: continue
        tot += 1
        g = greedy_x(L)
        if np.max(np.abs(r.x[:n] - g)) <= 1.0: ag += 1
        coef, se, direc, gfbr, isg, dem, cd, cu, P = parse(L)
        fg, fh = objective(g, coef, gfbr, isg, P), objective(r.x[:n], coef, gfbr, isg, P)
        if fg - fh > 1e-9*max(1.0, abs(fh)): better += 1
    res[name] = {"agree_pct": 100*ag/tot, "greedy_strictly_better": better, "n": tot}
    print("%-16s exact on %5.1f%% of %d LPs;  greedy strictly better on %d"
          % (name, 100*ag/tot, tot, better))
print("%-16s exact by construction (0 disagreements with itself)" % "greedy")

# --- speed --------------------------------------------------------------
print()
T = {}
for name, fn in (("shipped (K=1)", lambda L: linprog(L["c"], A_ub=L["A_ub"], b_ub=L["b_ub"], bounds=L["bounds"], method="highs")),
                 ("scaled (K=1e4)", lambda L: linprog(L["c"]*K, A_ub=L["A_ub"], b_ub=L["b_ub"], bounds=L["bounds"], method="highs")),
                 ("greedy", greedy_x)):
    t0 = time.perf_counter()
    for L in SUB:
        fn(L)
    dt = time.perf_counter()-t0
    T[name] = dt/len(SUB)
    print("%-16s %8.4f ms per LP" % (name, 1e3*dt/len(SUB)))
print()
print("greedy is %.1fx faster than the scaled solver call"
      % (T["scaled (K=1e4)"]/T["greedy"]))

# --- determinism --------------------------------------------------------
print()
rng = np.random.default_rng(0); perm = rng.permutation(2*n); inv = np.argsort(perm)
for name, K_ in (("shipped (K=1)", 1.0), ("scaled (K=1e4)", K)):
    st = tot = 0
    for L in SUB:
        a = linprog(L["c"]*K_, A_ub=L["A_ub"], b_ub=L["b_ub"], bounds=L["bounds"], method="highs")
        b = linprog((L["c"]*K_)[perm], A_ub=L["A_ub"][:, perm], b_ub=L["b_ub"],
                    bounds=[L["bounds"][i] for i in perm], method="highs")
        if not (a.success and b.success): continue
        tot += 1
        if np.max(np.abs(a.x - b.x[inv])) <= 1.0: st += 1
    print("%-16s stable under column permutation: %5.1f%%" % (name, 100*st/tot))
# greedy: stable iff the tie-break is explicit
gs = tot = 0
for L in SUB:
    a = greedy_x(L)
    coef, se, direc, gfbr, isg, dem, cd, cu, P = parse(L)
    b = greedy_x(L)
    tot += 1
    if np.array_equal(a, b): gs += 1
print("%-16s stable under repetition: %5.1f%%  (ties resolved by list order --"
      % ("greedy", 100*gs/tot))
print("                 an EXPLICIT tie-break would be required, see the report)")
