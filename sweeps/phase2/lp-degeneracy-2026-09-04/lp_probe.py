"""Is Tier-1's LP solution unique, and does its SCA loop converge?

Self-contained -- it builds the HiGHS model inline rather than importing a
module, because the direct-HiGHS backend this probe was written to validate
was NOT landed and does not exist. See README.md beside this file.

Three measurements, in the order they were taken:

  --diff   every Tier-1 LP of one real run, solved by scipy.optimize.linprog
           and by a directly-built HiGHS model, compared exactly. scipy's
           answer is the one returned to the caller, so the run itself is
           unperturbed and the comparison is a pure observation.
  --degen  the discriminator: relative objective gap vs max |dx|, plus a
           feasibility check of each solution against the model. If the
           objectives agree and both points are feasible, the LP has
           multiple optima and the difference is vertex selection, not
           disagreement about the optimum.
  --sca    how many SCA iterations each Tier-1 solve takes, and how many
           reach `_SCA_TOL` before `_SCA_MAXITERS`.

Usage:
    uv run python sweeps/phase2/lp-degeneracy-2026-09-04/lp_probe.py --degen
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from scipy.optimize import linprog          # noqa: E402
from scipy.sparse import csc_matrix         # noqa: E402

import scheduler.tier1 as T                 # noqa: E402

HORIZON = 8000
N_UES = 8
SEED = 1


def _highs_solve(A_ub, b_ub, bounds, c, options):
    """The direct model, built the way scipy's own wrapper builds it: HiGHS
    solves `lhs <= Ax <= rhs`, and scipy sets lhs to -inf on every A_ub row."""
    import highspy as hs
    inf = hs.kHighsInf
    lo = np.array([b[0] if b[0] is not None else -inf for b in bounds], float)
    hi = np.array([b[1] if b[1] is not None else inf for b in bounds], float)
    A = csc_matrix(np.asarray(A_ub, float))
    lp = hs.HighsLp()
    lp.num_col_ = len(c)
    lp.num_row_ = A.shape[0]
    lp.col_cost_ = np.asarray(c, float)
    lp.col_lower_, lp.col_upper_ = lo, hi
    lp.row_lower_ = np.full(A.shape[0], -inf)
    lp.row_upper_ = np.asarray(b_ub, float)
    lp.a_matrix_.format_ = hs.MatrixFormat.kColwise
    lp.a_matrix_.start_ = A.indptr
    lp.a_matrix_.index_ = A.indices
    lp.a_matrix_.value_ = A.data
    h = hs.Highs()
    for k, v in options:
        h.setOptionValue(k, v)
    h.passModel(lp)
    h.run()
    if h.getModelStatus() != hs.HighsModelStatus.kOptimal:
        return False, None
    return True, np.asarray(h.getSolution().col_value, float)


def _run_one(horizon=HORIZON):
    import wp9_sweep as W
    from sim.driver import run
    from scheduler import load_two_tier
    W._HORIZON[0] = horizon
    av = {"n_ues": N_UES, "load_mult": 1.0}
    sc = W._build(seed=SEED, **av)
    run(sc, load_two_tier(W._TT_CONFIG, min_rb=5), **W._driver_kwargs(**av))


def probe_lp(presolve: str, degen: bool) -> dict:
    """Wrap `solve_tier1`'s inner linprog so every call is solved twice."""
    options = (("output_flag", False), ("log_to_console", False),
               ("presolve", presolve), ("simplex_strategy", 1))
    rel_obj, absx = [], []
    feas = {"highs": 0, "scipy": 0}
    state = {"n": 0, "status_diff": 0, "ctx": None}
    real_linprog = T.linprog

    def observing(c, A_ub=None, b_ub=None, bounds=None, **kw):
        res = real_linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, **kw)
        ok_h, x_h = _highs_solve(A_ub, b_ub, bounds, c, options)
        state["n"] += 1
        if bool(res.success) != ok_h:
            state["status_diff"] += 1
        if ok_h and res.success:
            oh, os_ = float(c @ x_h), float(c @ res.x)
            rel_obj.append(abs(oh - os_) / max(abs(oh), abs(os_), 1.0))
            absx.append(float(np.max(np.abs(x_h - res.x))))
            if degen:
                A = np.asarray(A_ub, float)
                b = np.asarray(b_ub, float)
                lo = np.array([q[0] for q in bounds])
                hi = np.array([1e30 if q[1] is None else q[1] for q in bounds])
                for x, tag in ((x_h, "highs"), (res.x, "scipy")):
                    if ((A @ x <= b + 1e-6).all() and (x >= lo - 1e-6).all()
                            and (x <= hi + 1e-6).all()):
                        feas[tag] += 1
        return res            # scipy drives; the run is unperturbed

    T.linprog = observing
    try:
        _run_one()
    finally:
        T.linprog = real_linprog

    r, a = np.array(rel_obj), np.array(absx)
    out = {"presolve": presolve, "solves": int(len(r)),
           "status_disagreements": state["status_diff"],
           "relative_objective_gap": {
               "max": float(r.max()), "median": float(np.median(r)),
               "above_1e-9": int((r > 1e-9).sum())},
           "max_abs_x_difference": {
               "max": float(a.max()), "median": float(np.median(a)),
               "nonzero": int((a > 0).sum())}}
    if degen:
        out["both_solutions_feasible"] = {**feas, "of": int(len(r))}
    return out


def probe_sca() -> dict:
    """Count linprog calls per solve_tier1 call -- i.e. SCA iterations."""
    iters: list[int] = []
    box = {"n": 0}
    real_linprog = T.linprog
    real_solve = T.solve_tier1

    def counting(c, **kw):
        box["n"] += 1
        return real_linprog(c, **kw)

    def wrapped(*a, **k):
        box["n"] = 0
        try:
            return real_solve(*a, **k)
        finally:
            if box["n"]:
                iters.append(box["n"])

    T.linprog = counting
    T.solve_tier1 = wrapped
    import scheduler.two_tier as TT
    real_tt = TT.solve_tier1
    TT.solve_tier1 = wrapped
    try:
        _run_one(horizon=20000)
    finally:
        T.linprog, T.solve_tier1, TT.solve_tier1 = (
            real_linprog, real_solve, real_tt)

    arr = np.array(iters)
    return {"tier1_solves": int(len(arr)), "sca_maxiters": T._SCA_MAXITERS,
            "sca_tol": T._SCA_TOL,
            "iterations": {"min": int(arr.min()), "median": float(np.median(arr)),
                           "max": int(arr.max()), "mean": float(arr.mean())},
            "converged_before_cap": int((arr < T._SCA_MAXITERS).sum()),
            "hit_the_cap": int((arr >= T._SCA_MAXITERS).sum()),
            "total_lp_solves": int(arr.sum())}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--degen", action="store_true")
    ap.add_argument("--sca", action="store_true")
    ap.add_argument("--presolve", default="on",
                    choices=("on", "choose", "off"))
    a = ap.parse_args(argv[1:])
    if not (a.diff or a.degen or a.sca):
        a.diff = a.degen = a.sca = True
    if a.diff or a.degen:
        print(json.dumps(probe_lp(a.presolve, a.degen), indent=2))
    if a.sca:
        print(json.dumps(probe_sca(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
