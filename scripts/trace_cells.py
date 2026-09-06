"""Persist MECHANISM traces on the cells that produce unexplained results.

A re-run that confirms verdicts leaves nothing to diagnose from afterwards,
and re-running to add a trace costs the same budget again. So the four
unexplained results get their rank stream and grant stream captured on the
specific cells that produce them, reduced in the worker and persisted.

THE ACCEPTANCE CONDITIONS ARE G5's, UNCHANGED:

  * **Declared at construction.** The hook is an attribute set on the arm's
    own instance; a scheduler built without it is the object every other
    runner in this repo uses, byte-for-byte.
  * **Bit-identical with the hook off.** `--identity` runs each cell twice,
    hooked and unhooked, and compares `RunRecord.to_dict()` -- not the raw
    summary, whose `_ue_lcp`/`_message_ledger` reprs embed memory addresses
    and differ between two identical runs (defects log #26).
  * **Fails loudly on an empty collection.** Both sinks raise rather than
    report zero. A trace that silently records nothing is indistinguishable
    from a mechanism that never fired, which is this project's most-recorded
    failure shape.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from attach_path_experiment import STAGGER_SLOTS, _stagger          # noqa: E402
from code_state import stamp                                        # noqa: E402
from g7_aggressor import build as g7_build                          # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells          # noqa: E402
from scheduler.rank_trace import LossPointTally                     # noqa: E402
from sim.driver import run as driver_run                            # noqa: E402
from sim.parametric import sweep_scenario                           # noqa: E402
from sim.resource import ResourceGrid                               # noqa: E402
from sim.run_record import RunRecord                                # noqa: E402
from sim.scorecard import Population, Scorecard                     # noqa: E402
from sim.trace import GrantCollector                                # noqa: E402
from g11_campaign import _arm                                       # noqa: E402

HORIZON = 20_000
N_UES = 8


def _cell(name: str, seed: int):
    """(scenario, attach_seed_slots) for a named cell. Each is the cell that
    PRODUCES the unexplained result, not a nearby one."""
    if name == "g7":
        sc = g7_build(seed=seed, n_ues=N_UES, horizon=HORIZON,
                      offer_x_mfbr=2.1, load_mult=1.0)
        return sc, None
    if name == "attach":                       # M06 14/40 -> 40/40
        sc = sweep_scenario(seed=seed, n_ues=N_UES, horizon_slots=HORIZON,
                            load_mult=1.0)
        sc, slots = _stagger(sc, STAGGER_SLOTS)
        return sc, slots
    if name == "attach_control":               # the same cell, no attach path
        return sweep_scenario(seed=seed, n_ues=N_UES, horizon_slots=HORIZON,
                              load_mult=1.0), None
    if name == "g5_residual":                  # G5 after the lock-out clears
        sc = sweep_scenario(seed=seed, n_ues=10, horizon_slots=40_000,
                            load_mult=1.0)
        sc, slots = _stagger(sc, STAGGER_SLOTS)
        return sc, slots
    raise SystemExit(f"unknown cell {name!r}")


def _grant_reduction(grants, sc, rec):
    """Per-(UE, 5QI) service cadence and LCP deferral, from the grant's own
    per-flow split. The DEFERRAL count is the load-bearing one: it separates
    "the flow waited because its UE got no grant" (a sort loss, which the rank
    stream can see) from "it waited through grants that carried only its
    sibling's bytes" (inside the TB, which the rank stream cannot)."""
    slot_ms = ResourceGrid(sc.carrier, sc.tdd).slot_duration_s * 1000.0
    per_ue: dict[int, list] = {}
    for g in grants:
        if g.direction != "UL":
            continue
        per_ue.setdefault(g.ue_id, []).append(g)
    out = {}
    for ue, gl in per_ue.items():
        last: dict[int, int] = {}
        since: dict[int, int] = {}
        gaps: dict[int, list] = {}
        skip: dict[int, list] = {}
        carried: dict[int, int] = {}
        for g in gl:
            served = {q for q, b in (g.split or ()) if b > 0}
            for q in list(since):
                if q not in served:
                    since[q] += 1
            for q, b in (g.split or ()):
                if b <= 0:
                    continue
                carried[q] = carried.get(q, 0) + 1
                if q in last:
                    gaps.setdefault(q, []).append(g.slot_index - last[q])
                    skip.setdefault(q, []).append(since.get(q, 0))
                last[q] = g.slot_index
                since[q] = 0

        def p(xs, q, scale=1.0):
            if not xs:
                return None
            xs = sorted(xs)
            return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] * scale

        out[str(ue)] = {"n_ul_grants": len(gl), "by_qfi": {
            str(q): {"services": carried.get(q, 0),
                     "gap_p50_ms": p(gaps.get(q, []), .50, slot_ms),
                     "gap_p98_ms": p(gaps.get(q, []), .98, slot_ms),
                     "skipped_p50": p(skip.get(q, []), .50),
                     "skipped_p98": p(skip.get(q, []), .98),
                     "frac_grants_carrying": carried.get(q, 0) / len(gl)}
            for q in sorted(carried)}}
    return out


def _run(cell, arm, seed, hooked: bool):
    sc, slots = _cell(cell, seed)
    sched = _arm(arm)
    tally = grants = None
    if hooked:
        tally = LossPointTally("UL")
        sched.rank_sink = tally             # declared at construction
        grants = GrantCollector()
    s = driver_run(sc, sched, cqi_delay_slots=8, record_timeseries=False,
                   attach_seed_slots=slots,
                   **({"grant_sink": grants} if hooked else {}))
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=s, arm={}, meta={})
    return sc, s, rec, tally, grants


def one(task) -> dict:
    cell, arm, seed, identity = task
    t0 = time.time()
    sc, s, rec, tally, grants = _run(cell, arm, seed, hooked=True)
    tally.finish()                          # RAISES on an empty stream
    gl = grants.finish()                    # RAISES on an empty stream

    ident = None
    if identity:
        _, _, rec2, _, _ = _run(cell, arm, seed, hooked=False)
        ident = (rec.to_dict() == rec2.to_dict())

    card = Scorecard()
    scored = card.score(rec, population=Population.protected_fleet())
    return {
        "cell": cell, "arm": arm, "seed": seed,
        "wall_s": round(time.time() - t0, 1),
        "bit_identical_hook_off": ident,
        "metrics": {k: (v.value if hasattr(v, "value") else None)
                    for k, v in scored.items()
                    if k in ("M01", "M05", "M06", "M09", "M13")},
        "rank": {"slots_seen": tally.slots_seen,
                 "term_totals": tally.term_totals(),
                 "mean_rank": {str(k): v for k, v in tally.mean_rank().items()},
                 "losses_by_ue": {str(u): tally.losses_for(u)
                                  for u in sorted(tally.present)}},
        "grants": _grant_reduction(gl, sc, rec),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default="g7,attach,attach_control,g5_residual")
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--identity", action="store_true",
                    help="also run each cell UNHOOKED and require identity")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    seeds = paired_seeds(a.seeds)
    tasks = [(c, arm, s, a.identity)
             for c in a.cells.split(",")
             for arm in a.arms.split(",")
             for s in seeds]
    rows = [None] * len(tasks)
    for i, r in run_cells(one, tasks, a.workers,
                          cost=lambda t: arm_cost(t[1])):
        rows[i] = r
        print(f"  {r['cell']:15s} {r['arm']:12s} seed={r['seed']} "
              f"identical={r['bit_identical_hook_off']}", flush=True)
    bad = [r for r in rows if r["bit_identical_hook_off"] is False]
    Path(a.out).write_text(json.dumps(
        {"code_state": stamp(), "identity_checked": a.identity,
         "identity_failures": len(bad), "rows": rows}, indent=1))
    print(f"wrote {a.out}")
    if bad:
        print(f"REFUSING: {len(bad)} cells differ with the hook off -- the "
              f"trace is not passive and nothing here may be scored")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
