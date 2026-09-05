"""Map the conditioning plateau, so K is chosen as a plateau INTERIOR
rather than fitted. Two independent metrics per K:
  * agreement with the exact greedy (correctness)
  * stability under an argmax-invariant column permutation (numerics)
"""
import pickle, sys, json
import numpy as np
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal")
from scipy.optimize import linprog
src = open("greedy.py").read().split("rows = []")[0]
exec(src)
SUB = CAP[::16]
rng = np.random.default_rng(0)
perm = rng.permutation(2*n); inv = np.argsort(perm)

def greedy_x(L):
    coef, se, direc, gfbr, isg, dem, capdl, capul, P = parse(L)
    globals()["P_GLOBAL"] = P
    r = np.zeros(n)
    for d, cap in ((0, capdl), (1, capul)):
        m = (direc == d)
        r += greedy(np.where(m, coef, 0), np.where(m, se, 0),
                    np.where(m, direc, -1), gfbr, isg & m, np.where(m, dem, 0), cap)
    return r

out = []
print(" K          agrees w/ exact greedy    stable under permutation")
for e in range(0, 13):
    K = 10.0**e
    ag = st = tot = 0
    for L in SUB:
        if L["x"] is None: continue
        r1 = linprog(L["c"]*K, A_ub=L["A_ub"], b_ub=L["b_ub"], bounds=L["bounds"], method="highs")
        r2 = linprog((L["c"]*K)[perm], A_ub=L["A_ub"][:, perm], b_ub=L["b_ub"],
                     bounds=[L["bounds"][i] for i in perm], method="highs")
        if not (r1.success and r2.success): continue
        tot += 1
        g = greedy_x(L)
        if np.max(np.abs(r1.x[:n] - g)) <= 1.0: ag += 1
        if np.max(np.abs(r1.x - r2.x[inv])) <= 1.0: st += 1
    out.append({"K": K, "n": tot, "agree_pct": 100*ag/tot, "stable_pct": 100*st/tot})
    print(" 1e%-2d       %6.1f%%                   %6.1f%%" % (e, 100*ag/tot, 100*st/tot))
json.dump(out, open("plateau.json", "w"), indent=1)
