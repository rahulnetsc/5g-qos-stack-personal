"""Across MANY Tier-1 solves: does convergence track whether the exact
log-utility optimum is a vertex? That is the claim's real content."""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/smart/projects/5g-qos-stack-personal")
import cvxpy as cp
from scipy.optimize import linprog
exec(open("sca.py").read().split("# weights are recoverable")[0].split("CAP = pickle")[0])
CAP = pickle.load(open("lps.pkl","rb"))
n = len(CAP[0]["c"])//2
ALPHA, TOL, MAXIT = 0.2, 1e-6, 150

def parse(L):
    c, A, b, bnds = L["c"], L["A_ub"], L["b_ub"], L["bounds"]
    se=np.zeros(n); direc=np.full(n,-1)
    for i in range(n):
        for row in (0,1):
            if A[row,i]!=0: se[i]=1.0/A[row,i]; direc[i]=row
    gfbr=np.zeros(n); isg=np.zeros(n,bool); P=0.0
    for r in range(2,A.shape[0]):
        cols=np.nonzero(A[r,:n])[0]
        if len(cols)==1:
            i=cols[0]; isg[i]=True; gfbr[i]=-b[r]; P=c[n+i]
    dem=np.array([bnds[i][1] if bnds[i][1] is not None else np.inf for i in range(n)])
    return A,b,bnds,se,direc,gfbr,isg,dem,P

# delimit solves: the FIRST LP of a solve has r_prev = EPSILON = 1, so
# coef = w/2 exactly. Weights are in {1,5} => coef in {0.5, 2.5}.
starts=[i for i,L in enumerate(CAP) if set(np.round(-L["c"][:n][-L["c"][:n]>0],6)) <= {0.5,2.5}]
print("Tier-1 solves detected: %d (from %d LPs)" % (len(starts), len(CAP)))
res_rows=[]
for si in starts[:20]:
    L=CAP[si]
    A,b,bnds,se,direc,gfbr,isg,dem,P = parse(L)
    w=(-L["c"][:n])*2.0
    # exact log-utility optimum
    r=cp.Variable(n,nonneg=True); s=cp.Variable(n,nonneg=True)
    cons=[r<=np.where(np.isfinite(dem),dem,1e12)]
    for d in (0,1):
        m=(direc==d)
        if m.any(): cons.append(cp.sum(cp.multiply(np.where(m,1.0/np.where(se>0,se,1),0.0),r))<=b[d])
    for i in range(n):
        cons.append(r[i]+s[i]>=gfbr[i]) if isg[i] else cons.append(s[i]==0)
    try:
        cp.Problem(cp.Maximize(cp.sum(cp.multiply(w,cp.log(r+1.0)))-P*cp.sum(s)),cons).solve(solver=cp.CLARABEL)
        rstar=np.maximum(0.0,r.value)
    except Exception:
        continue
    interior=sum(1 for i in range(n)
                 if rstar[i]>1e-3 and (not np.isfinite(dem[i]) or rstar[i]<dem[i]-1e-3))
    # run the SCA
    rp=np.full(n,1.0); conv=None
    for it in range(MAXIT):
        coef=w/(rp+1.0); c=np.zeros(2*n); c[:n]=-coef; c[n:]=P
        rr=linprog(c,A_ub=A,b_ub=b,bounds=bnds,method="highs")
        v=np.maximum(0.0,rr.x[:n]); dmp=ALPHA*v+(1-ALPHA)*rp
        rel=np.max(np.abs(dmp-rp)/(rp+1.0)); rp=dmp
        if rel<TOL: conv=it+1; break
    gap=np.max(np.abs(rp-rstar))
    res_rows.append((si,interior,conv,gap))
print()
print(" LP#   interior_vars  converged_at  max|r_sca - r*| (bps)")
for si,inter,conv,gap in res_rows:
    print(" %-6d %-14d %-13s %.4g" % (si,inter,conv if conv else "CAP(150)",gap))
c_yes=[r for r in res_rows if r[2]]; c_no=[r for r in res_rows if not r[2]]
print()
print("converged: %d   hit cap: %d" % (len(c_yes),len(c_no)))
if c_yes: print("  interior_vars when CONVERGED: median %.1f" % np.median([r[1] for r in c_yes]))
if c_no:  print("  interior_vars when CAPPED   : median %.1f" % np.median([r[1] for r in c_no]))
print("  n_constraint_rows = %d" % CAP[0]["A_ub"].shape[0])
