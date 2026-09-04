"""What does an UNCONVERGED Tier-1 solve return, and does it matter?

`sweeps/phase2/lp-degeneracy-2026-09-04/` established that 41 of 50 Tier-1
solves hit `_SCA_MAXITERS = 150` without reaching `_SCA_TOL = 1e-6`. That is
a performance observation only if the iterate at 150 is close to where the
loop was heading. This probe asks whether it is.

Four modes, each answering a question the previous one raises:

  --trace     Per-iteration `rel_change` and the iterate, for the first few
              solves, at the shipped cap and at a much larger one. DECAY,
              PLATEAU or OSCILLATION are three different diagnoses and the
              series distinguishes them: a decaying series means 150 is
              merely too few; a plateau or a limit cycle means more
              iterations buy nothing and the loop has no fixed point to
              reach.

  --targets   The targets `solve_tier1` RETURNS at iteration 150 against the
              targets it would return with the cap lifted. This is the
              question "what does an unconverged solve return" in the only
              currency that matters -- the vector the scheduler consumes.

  --alloc     THE DOWNSTREAM QUESTION. A full run at the shipped cap and the
              same run with the cap lifted, compared on delivered bytes per
              flow and on the panel. If the allocations agree, non-
              convergence is a cost and not a defect; if they differ, every
              published two-tier number was produced by a loop stopped
              short of the allocation it was computing.

  --alpha     `_SCA_ALPHA = 0.2` damps toward the LP's vertex. If the loop
              is oscillating between degenerate vertices rather than
              converging, the damping constant is what decides whether the
              oscillation dies out. Sweeps it, reporting the iteration count
              reached -- diagnostic only; ALPHA is ground truth
              (`IA_P5G_TIER1_SCA_ALPHA`) and is not a knob to tune.

NOTHING HERE CHANGES `scheduler/tier1.py`. The cap and alpha are patched on
the module for the duration of a probe run and restored, so this asks what
the scheduler WOULD do without altering what it does.

Usage:
    uv run python sweeps/phase2/sca-convergence-2026-09-04/sca_probe.py --trace
    uv run python sweeps/phase2/sca-convergence-2026-09-04/sca_probe.py --targets
    uv run python sweeps/phase2/sca-convergence-2026-09-04/sca_probe.py --alloc
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import scheduler.tier1 as T                       # noqa: E402

N_UES = 8
SEED = 1
BIG_CAP = 20_000        # far past any plausible convergence horizon


@contextmanager
def sca(maxiters=None, alpha=None):
    """Patch the SCA constants for the duration of a probe, then restore."""
    old_m, old_a = T._SCA_MAXITERS, T._SCA_ALPHA
    if maxiters is not None:
        T._SCA_MAXITERS = maxiters
    if alpha is not None:
        T._SCA_ALPHA = alpha
    try:
        yield
    finally:
        T._SCA_MAXITERS, T._SCA_ALPHA = old_m, old_a


def _driver_run(horizon, record_timeseries=True):
    import wp9_sweep as W
    from sim.driver import run
    from scheduler import load_two_tier
    W._HORIZON[0] = horizon
    av = {"n_ues": N_UES, "load_mult": 1.0}
    sc = W._build(seed=SEED, **av)
    dk = W._driver_kwargs(**av)
    dk["record_timeseries"] = record_timeseries
    return sc, run(sc, load_two_tier(W._TT_CONFIG, min_rb=5), **dk)


# --- instrumentation ------------------------------------------------------

def _instrument(store: list):
    """Delimit solves by `solve_tier1`, record iterations by `linprog`.

    THE FIRST VERSION OF THIS DELIMITED SOLVES BY CONVERGENCE -- it reset its
    accumulator only when `rel_change` fell under the tolerance, so every
    solve that hit the CAP was concatenated onto the next one. It reported
    iteration counts of 498, 5,312 and 720,064 against caps of 150 and
    20,000. Those are arithmetically impossible against the cap, which is
    what caught it (CLAUDE.md: ask whether a surprising count factors into
    the run's own dimensions -- 720,064 cannot be a count of iterations under
    a 20,000 limit). Delimiting by the function whose loop it is cannot make
    that mistake.

    Returns a restore callable.
    """
    import scheduler.two_tier as TT
    real_lp = T.linprog
    real_solve = T.solve_tier1
    old_tt = TT.solve_tier1
    state = {"prev": None, "series": None}

    def lp(c, **kw):
        res = real_lp(c, **kw)
        if res.success and state["series"] is not None:
            n = len(c) // 2
            v = np.maximum(0.0, res.x[:n])
            prev = state["prev"]
            if prev is None or len(prev) != n:
                prev = np.full(n, T._EPSILON)
            damped = T._SCA_ALPHA * v + (1.0 - T._SCA_ALPHA) * prev
            rel = float(np.max(np.abs(damped - prev) / (prev + 1.0))) if n else 0.0
            state["series"].append({"rel_change": rel,
                                    "iterate_sum": float(damped.sum()),
                                    "vertex_sum": float(v.sum())})
            state["prev"] = damped
        return res

    def solve(*a, **k):
        state["series"] = []
        state["prev"] = None
        store.append(state["series"])
        try:
            return real_solve(*a, **k)
        finally:
            state["series"] = None

    T.linprog, T.solve_tier1, TT.solve_tier1 = lp, solve, solve

    def restore():
        T.linprog, T.solve_tier1, TT.solve_tier1 = real_lp, real_solve, old_tt
    return restore


def probe_trace(horizon=20_000, detail=4) -> dict:
    """EVERY solve, not the first few. The first solves of a run converge in
    ~56 iterations; the ones that hit the cap are later, once the fleet's
    demand vector has moved, so tracing the head of the run answers about
    the easy cases only -- which is how a trace can report health that the
    aggregate contradicts."""
    out = {}
    for label, cap in (("shipped_cap_150", 150), ("big_cap", BIG_CAP)):
        store: list = []
        restore = _instrument(store)
        try:
            with sca(maxiters=cap):
                _driver_run(horizon=horizon, record_timeseries=False)
        finally:
            restore()
        store = [s for s in store if s]
        # THE GUARD THE FIRST VERSION LACKED: no series may exceed the cap.
        over = [len(s) for s in store if len(s) > cap]
        if over:
            raise AssertionError(
                f"{len(over)} solve(s) recorded more iterations than the cap "
                f"{cap} (max {max(over)}) -- the instrument is concatenating "
                f"solves, not measuring them")
        hit = [s for s in store if len(s) >= cap]
        conv = [s for s in store if len(s) < cap]
        out[label + "_summary"] = {
            "solves": len(store),
            "converged": len(conv),
            "hit_cap": len(hit),
            "iters_converged_median": (float(np.median([len(s) for s in conv]))
                                       if conv else None),
            # THE DIAGNOSIS. A decaying series has its minimum at the end;
            # a plateau or a limit cycle does not.
            "capped_with_min_at_end": sum(
                1 for s in hit
                if int(np.argmin([x["rel_change"] for x in s])) == len(s) - 1),
            "capped_min_rel_change_median": (
                float(np.median([min(x["rel_change"] for x in s) for s in hit]))
                if hit else None),
            "capped_distinct_vertex_sums_median": (
                float(np.median([len({round(x["vertex_sum"], 6) for x in s})
                                 for s in hit])) if hit else None),
        }
        series = (hit or store)[:detail]
        out[label] = []
        for s in series:
            rc = [x["rel_change"] for x in s]
            out[label].append({
                "iterations": len(rc),
                "rel_change_first5": [round(x, 8) for x in rc[:5]],
                "rel_change_last5": [round(x, 8) for x in rc[-5:]],
                "min_rel_change": round(min(rc), 10),
                "min_at_iteration": int(np.argmin(rc)) + 1,
                # A decaying series has its minimum at the end. A plateau or
                # a limit cycle does not.
                "min_is_at_the_end": int(np.argmin(rc)) == len(rc) - 1,
                "distinct_vertex_sums": len({round(x["vertex_sum"], 6)
                                             for x in s}),
            })
    return out


def probe_targets() -> dict:
    """The vector the scheduler consumes, at the cap and past it."""
    captured: dict = {}
    real_solve = T.solve_tier1

    def capture(flows, snr_avg, grid, demand_bps):
        out = real_solve(flows, snr_avg, grid, demand_bps)
        captured.setdefault(_key(demand_bps), []).append(out)
        return out

    def _key(d):
        return round(sum(d.values()), 3)

    results = {}
    for label, cap in (("cap_150", 150), ("cap_big", BIG_CAP)):
        captured.clear()
        T.solve_tier1 = capture
        import scheduler.two_tier as TT
        old_tt = TT.solve_tier1
        TT.solve_tier1 = capture
        try:
            with sca(maxiters=cap):
                _driver_run(horizon=4000, record_timeseries=False)
        finally:
            T.solve_tier1, TT.solve_tier1 = real_solve, old_tt
        results[label] = {k: v[0] for k, v in captured.items()}

    shared = sorted(set(results["cap_150"]) & set(results["cap_big"]))
    rows = []
    for k in shared:
        a, b = results["cap_150"][k], results["cap_big"][k]
        keys = sorted(set(a) & set(b))
        if not keys:
            continue
        va = np.array([a[q] for q in keys])
        vb = np.array([b[q] for q in keys])
        denom = np.maximum(np.abs(vb), 1.0)
        rows.append({
            "solve": k, "n_flows": len(keys),
            "max_rel_diff": float(np.max(np.abs(va - vb) / denom)),
            "median_rel_diff": float(np.median(np.abs(va - vb) / denom)),
            "sum_150": float(va.sum()), "sum_big": float(vb.sum()),
            # Does the ORDER of the targets change? The scheduler consumes a
            # ranking as much as a magnitude.
            "rank_identical": bool(np.array_equal(np.argsort(va),
                                                  np.argsort(vb))),
        })
    return {"n_solves_compared": len(rows), "solves": rows}


def probe_alloc(horizon=20_000, cap_b=1000) -> dict:
    """THE DOWNSTREAM QUESTION, on a full run.

    `cap_b=151` is the sharpest form of it. If stopping the loop ONE
    iteration later changes the allocation, then the returned target is a
    point on a limit cycle rather than an approximation of a fixed point,
    and "which allocation two-tier produced" is decided by the cap rather
    than by the optimum.
    """
    from sim.run_record import RunRecord
    from sim.scorecard import Population, Scorecard

    out = {}
    recs = {}
    for label, cap in (("cap_150", 150), ("cap_b", cap_b)):
        with sca(maxiters=cap):
            sc, summary = _driver_run(horizon=horizon)
        recs[label] = RunRecord.from_summary(
            scenario_name=sc.name, scheduler_name="TwoTier", seed=SEED,
            flow_configs=sc.flows, summary=summary, arm={}, meta={})

    a, b = recs["cap_150"], recs["cap_b"]
    keys = sorted(set(a.flows) & set(b.flows))
    diffs = []
    for k in keys:
        fa, fb = a.flows[k], b.flows[k]
        d = fa.bytes_delivered - fb.bytes_delivered
        base = max(fb.bytes_delivered, 1)
        diffs.append({"flow": k, "delta_bytes": int(d),
                      "rel": d / base,
                      "delivered_150": int(fa.bytes_delivered),
                      "delivered_b": int(fb.bytes_delivered)})
    diffs.sort(key=lambda r: -abs(r["rel"]))
    card = Scorecard()
    sa = card.score(a, population=Population.protected_fleet())
    sb = card.score(b, population=Population.protected_fleet())
    panel = {}
    for mid in sorted(set(sa) & set(sb)):
        va, vb = sa[mid].value, sb[mid].value
        if va != vb:
            panel[mid] = {"cap_150": va, "cap_b": vb}
    out["cap_b"] = cap_b
    out["n_flows"] = len(keys)
    out["n_flows_differing"] = sum(1 for d in diffs if d["delta_bytes"] != 0)
    out["max_abs_rel_delta"] = max((abs(d["rel"]) for d in diffs), default=0.0)
    out["worst_flows"] = diffs[:6]
    out["panel_metrics_that_moved"] = panel
    return out


def probe_alpha() -> dict:
    rows = []
    for alpha in (0.05, 0.1, 0.2, 0.4, 0.8, 1.0):
        counts: list[int] = []
        real = T.linprog
        box = {"n": 0}
        real_solve = T.solve_tier1

        def counting(c, **kw):
            box["n"] += 1
            return real(c, **kw)

        def wrapped(*a, **k):
            box["n"] = 0
            try:
                return real_solve(*a, **k)
            finally:
                counts.append(box["n"])

        T.linprog, T.solve_tier1 = counting, wrapped
        import scheduler.two_tier as TT
        old_tt = TT.solve_tier1
        TT.solve_tier1 = wrapped
        try:
            with sca(maxiters=BIG_CAP, alpha=alpha):
                _driver_run(horizon=4000, record_timeseries=False)
        finally:
            T.linprog, T.solve_tier1, TT.solve_tier1 = real, real_solve, old_tt
        arr = np.array([c for c in counts if c])
        rows.append({"alpha": alpha, "solves": int(len(arr)),
                     "iters_median": float(np.median(arr)),
                     "iters_max": int(arr.max()),
                     "converged_under_big_cap": int((arr < BIG_CAP).sum())})
    return {"note": "_SCA_ALPHA is ground truth; this is diagnostic only",
            "rows": rows}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--targets", action="store_true")
    ap.add_argument("--alloc", action="store_true")
    ap.add_argument("--alpha", action="store_true")
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--cap-b", type=int, default=1000,
                    help="the second cap to compare against 150; 151 is the "
                         "sharpest form -- does ONE more iteration change it")
    a = ap.parse_args(argv[1:])
    if not any((a.trace, a.targets, a.alloc, a.alpha)):
        a.trace = a.targets = a.alloc = True
    if a.trace:
        print(json.dumps({"trace": probe_trace(a.horizon)}, indent=2))
    if a.targets:
        print(json.dumps({"targets": probe_targets()}, indent=2))
    if a.alloc:
        print(json.dumps({"alloc": probe_alloc(a.horizon, a.cap_b)}, indent=2, default=str))
    if a.alpha:
        print(json.dumps({"alpha": probe_alpha()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
