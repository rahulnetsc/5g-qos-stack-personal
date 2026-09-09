"""G1 as a stress experiment: does driving a robot feel immediate while the
rest of the fleet works?

Registered in `docs/g1-step0-2026-09-09.md`; the result is
`docs/g1-stress-experiment-2026-09-09.md`.

WHAT IS DIFFERENT FROM EVERY EARLIER G1 ROW, and why each difference had to
be made before a number was worth taking:

  * **IT SCORES THE DOWNLINK.** G1 is a DL guarantee -- cmd_vel 20 Hz on
    5QI 1 DL -- and the published row was `M01`, a worst-flow maximum that
    landed on UPLINK 9 times out of 9 (Step 0 (b)). This runner scores the
    cmd_vel flows and nothing else, and derives that population from the
    scenario rather than naming it.

  * **BOTH PASS CRITERIA, SCORED SEPARATELY.** GT-1.1 is "p98 <= RAN PDB"
    AND "zero command gaps >= 200 ms". They fail in opposite directions: a
    percentile ranges over DELIVERED commands, so dropping commands improves
    it, while a receiver-side gap widens around a command that never came.
    Reporting one as G1 is what let a delivery failure look like a pass.

  * **A FLOW THAT DELIVERED FEWER THAN TWO COMMANDS FAILS BOTH PARTS.**
    `sim/scorecard.py`'s M01 excludes a zero-completion flow from its worst
    contest and M03 excludes a <2-completion flow from its worst-gap
    contest. Both dispositions are right for a worst-of-fleet statistic and
    wrong here: for G1 the instrument going silent IS the failure.

  * **THE INSTRUMENT POPULATION IS FIXED** at `N_DRIVEN`, so the UE axis
    moves load and not the statistic -- see `sim/scenarios/g1.py`.

  * **THE RANK TRACE TRAVELS WITH EVERY RUN.** The registered prediction is
    that drive commands now take precedence; the falsifier is that they do
    not, and "which term decided the adjacencies a driven UE lost" is the
    only thing that distinguishes "priority ordering did not reach them"
    from "the cell was simply full". `LossPointTally` is O(UEs^2 x terms),
    so it is safe at any horizon -- the parent never sees a snapshot.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                    # noqa: E402
from regime_sweep import (arm_cost, invocation_config, paired_seeds,  # noqa: E402
                          RunLedger, run_cells)
from scheduler.rank_trace import LossPointTally                  # noqa: E402
from sim.driver import run as driver_run                         # noqa: E402
from sim.random_access import RandomAccessConfig                 # noqa: E402
from sim.run_record import RunRecord                             # noqa: E402
from sim.scenarios.g1 import (GAP_BOUND_MS, N_DRIVEN, RAN_PDB_MS,  # noqa: E402
                              assert_cmd_instrument_live,
                              build_gt11_scenario, cmd_flow_keys)
from sim.srb import with_srb                                     # noqa: E402
from g11_campaign import _arm                                    # noqa: E402

#: `sim/scenarios/g9.py` and the G12 stress runner both run at 8, and every
#: real study in this branch runs with a delayed CQI rather than the
#: driver's bare 0 (CLAUDE.md's cqi_delay_slots invariant).
CQI_DELAY_SLOTS = 8

#: 40,000 slots at mu=2 (0.25 ms) is 10.0 s -- **200 cmd_vel messages per
#: driven robot per run** at 20 Hz.
#:
#: DELIBERATELY LONGER than G9/G12's 20,000. The percentile index convention
#: is `k = min(n-1, int(n*p))`, so p98 is the 3rd-largest sample at n=100
#: (a 20,000-slot run) and the 4th-largest at n=200. The statistic is thin
#: either way and the 10-seed yield rule is what carries it; 20,000 makes it
#: thin enough to be shaped by its own quantisation.
#:
#: GT-1.1 ASKS FOR 10 MINUTES of steady state, which this is not: 10 s is
#: one sixtieth of it per run, though 960 runs give 1.9x the plan's
#: AGGREGATE observation. `docs/g1-stress-experiment-2026-09-09.md` §3b
#: states every pass's horizon and which statistic each one supports --
#: including that a 10 s window demonstrably CAN hold a 200 ms gap (the
#: positive control records 698.8 ms at this same horizon), so the gap
#: criterion is not passing for want of a window to fail in.
#:
#: The same convention is why p99.9 comes from a separate long-horizon pass
#: and not from this grid: at n <= 1000 the p99.9 INDEX IS THE MAXIMUM.
HORIZON_SLOTS = 40_000

#: Sub-experiment A. Brackets every arm's re-measured G10 boundary so each
#: arm's own boundary falls strictly inside the swept range rather than at
#: an endpoint -- the defect that put G10's own answer inside an unresolved
#: 2x gap.
#: 6, 7 and 12 are on the grid because they ARE the three arms' re-measured
#: G10 boundaries; 24 is past the largest by 2x, so the table shows the
#: trend rather than a flat row of passes.
UE_AXIS: tuple[int, ...] = (4, 6, 7, 8, 10, 12, 14, 16, 24)

#: Sub-experiment B. The committed axis, same shape as G12's ramp: the whole
#: committed workload, offered bytes and contract together. cmd_vel is NOT
#: scaled -- a robot asked to do more work does not receive more drive
#: commands (sim/scenarios/g1.py).
LOAD_AXIS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0)


def _gaps_ms(fr) -> list[float]:
    """Receiver-side inter-arrival gaps, ms, over this flow's completions."""
    out: list[float] = []
    for ts in (fr.completion_ts_by_role_s or {}).values():
        out += [(b - a) * 1000.0 for a, b in zip(ts, ts[1:])]
    return out


def one(task: tuple) -> dict[str, Any]:
    n_ues, cm, arm_name, seed, cap = task
    sc = build_gt11_scenario(seed=seed, n_ues=n_ues, committed_mult=cm,
                             horizon_slots=HORIZON_SLOTS)
    assert_cmd_instrument_live(sc)
    keys = cmd_flow_keys(sc)
    driven_ues = sorted({int(k.split("_")[0][2:]) for k in keys})
    sc = with_srb(sc)

    sched = _arm(arm_name)
    tally = LossPointTally(direction="DL")
    sched.rank_sink = tally
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}

    t0 = time.time()
    summ = driver_run(sc, sched, cqi_delay_slots=CQI_DELAY_SLOTS,
                      max_sched_ues=cap, random_access=ra)
    wall = time.time() - t0
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm_name,
                                 seed=seed, flow_configs=sc.flows, summary=summ,
                                 arm={"cqi_delay_slots": CQI_DELAY_SLOTS,
                                      "max_sched_ues": cap}, meta={})

    # --- the two pass criteria, per cmd_vel flow, worst taken ------------
    per_flow = []
    for k in keys:
        fr = rec.flows[k]
        gaps = _gaps_ms(fr)
        per_flow.append({
            "flow": k,
            "msgs": fr.message_count,
            # An instrument that went silent is a FAILURE here, not an
            # exclusion -- see the module docstring.
            "silent": (fr.message_count or 0) < 2,
            "p50": fr.delay_p50_ms, "p98": fr.delay_p98_ms,
            "p99": fr.delay_p99_ms, "p999": fr.delay_p999_ms,
            "max": fr.delay_max_ms,
            "max_gap_ms": max(gaps) if gaps else None,
            "n_gaps_over": sum(1 for g in gaps if g >= GAP_BOUND_MS),
            "dropped_bytes": fr.bytes_dropped_pdb,
        })
    silent = any(f["silent"] for f in per_flow)
    p98_worst = max((f["p98"] or 0.0) for f in per_flow)
    max_worst = max((f["max"] or 0.0) for f in per_flow)
    gap_worst = max((f["max_gap_ms"] or 0.0) for f in per_flow)
    n_gaps = sum(f["n_gaps_over"] for f in per_flow)

    # --- the diagnostic: which term put a driven UE behind ---------------
    tally.finish(allow_empty=True)
    losses = {}
    for ue in driven_ues:
        losses[str(ue)] = {k: v for k, v in tally.losses_for(ue).items() if v}
    terms = {k: v for k, v in tally.term_totals().items() if v}
    mean_rank = tally.mean_rank()

    ul = sum(fr.throughput_bps for fr in rec.flows.values() if fr.direction == "UL")
    dl = sum(fr.throughput_bps for fr in rec.flows.values() if fr.direction == "DL")

    return {
        "n_ues": n_ues, "committed_mult": cm, "arm": arm_name, "seed": seed,
        "cap": cap, "wall_s": round(wall, 2),
        # part 1 -- responsiveness; part 2 -- no command ever missing
        "part1_pass": (not silent) and p98_worst <= RAN_PDB_MS,
        "part2_pass": (not silent) and n_gaps == 0,
        "silent_instrument": silent,
        "p98_worst_ms": p98_worst, "max_worst_ms": max_worst,
        "gap_worst_ms": round(gap_worst, 3), "n_gaps_over": n_gaps,
        "per_flow": per_flow,
        "dl_mbps": round(dl / 1e6, 3), "ul_mbps": round(ul / 1e6, 3),
        "dl_terms": terms, "dl_losses_driven": losses,
        "dl_mean_rank_driven": {str(u): round(mean_rank.get(u, float("nan")), 3)
                                for u in driven_ues},
        "dl_slots_ranked": tally.slots_seen,
    }


def _summarise(rows: list[dict[str, Any]], axis_key: str,
               axis: tuple) -> dict[str, Any]:
    """Per axis point: pass rate for each clause part, plus the reported
    tail. The BOUNDARY is the last axis point passing on every seed,
    contiguous from the smallest -- G10's own standing rule, so a
    non-monotone arm is reported rather than smoothed."""
    n_seeds = max((sum(1 for r in rows if r[axis_key] == a) for a in axis),
                  default=0)
    per_point = []
    for a in axis:
        cell = [r for r in rows if r[axis_key] == a]
        if not cell:
            continue
        assert len(cell) == n_seeds, (
            f"axis point {axis_key}={a} has {len(cell)} rows, expected "
            f"{n_seeds} -- never score a short or empty selection")
        p98s = [r["p98_worst_ms"] for r in cell]
        per_point.append({
            axis_key: a,
            "part1_pass": sum(1 for r in cell if r["part1_pass"]),
            "part2_pass": sum(1 for r in cell if r["part2_pass"]),
            "both_pass": sum(1 for r in cell
                             if r["part1_pass"] and r["part2_pass"]),
            "n_seeds": len(cell),
            "silent_seeds": sum(1 for r in cell if r["silent_instrument"]),
            "p98_median_ms": round(statistics.median(p98s), 3),
            "p98_worst_ms": round(max(p98s), 3),
            # p99.9 over 200 delivered commands IS the maximum, so the
            # pooled tail is reported as a max over the cell rather than as
            # a second percentile that would read as an independent figure.
            "max_over_cell_ms": round(max(r["max_worst_ms"] for r in cell), 3),
            "worst_gap_ms": round(max(r["gap_worst_ms"] for r in cell), 3),
            "n_gaps_over_total": sum(r["n_gaps_over"] for r in cell),
            "dl_mbps_median": round(statistics.median(
                [r["dl_mbps"] for r in cell]), 3),
            "ul_mbps_median": round(statistics.median(
                [r["ul_mbps"] for r in cell]), 3),
            "wall_s_total": round(sum(r["wall_s"] for r in cell), 1),
        })

    def boundary(field: str) -> Optional[Any]:
        best = None
        for p in per_point:
            if p[field] == p["n_seeds"]:
                best = p[axis_key]
            else:
                break
        return best

    return {
        "axis": axis_key, "points": per_point,
        "boundary_part1": boundary("part1_pass"),
        "boundary_part2": boundary("part2_pass"),
        "boundary_both": boundary("both_pass"),
        "wall_s_total": round(sum(r["wall_s"] for r in rows), 1),
        "n_runs": len(rows),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--caps", default="4,2")
    ap.add_argument("--ue-axis", default=",".join(str(n) for n in UE_AXIS))
    ap.add_argument("--load-axis", default=",".join(str(x) for x in LOAD_AXIS))
    ap.add_argument("--fixed-n", type=int, required=True,
                    help="sub-experiment B's fleet size; DERIVED from the "
                         "re-measured G10 boundary, never a default")
    ap.add_argument("--fixed-load", type=float, default=1.0)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default="sweeps/g1-stress/g1_stress.json")
    a = ap.parse_args(argv[1:])

    arms = [x for x in a.arms.split(",") if x]
    caps = [int(x) for x in a.caps.split(",") if x]
    ue_axis = tuple(int(x) for x in a.ue_axis.split(",") if x)
    load_axis = tuple(float(x) for x in a.load_axis.split(",") if x)
    seeds = paired_seeds(a.seeds)

    tasks: list[tuple] = []
    for cap in caps:
        for arm in arms:
            for s in seeds:
                for n in ue_axis:                       # A: fleet size
                    tasks.append((n, a.fixed_load, arm, s, cap))
                for cm in load_axis:                    # B: load per robot
                    if (a.fixed_n, cm) == (n, a.fixed_load):
                        continue                        # A already has it
                    tasks.append((a.fixed_n, cm, arm, s, cap))
    # A and B share the point (fixed_n, fixed_load); de-duplicate so the
    # ledger key cannot collide and a cell is not double-counted.
    tasks = list(dict.fromkeys(tasks))

    print(f"G1 stress: {len(tasks)} driver runs\n"
          f"  A  2 clause parts x {len(ue_axis)} UE counts x {len(arms)} arms "
          f"x {len(seeds)} seeds x {len(caps)} caps  (committed x{a.fixed_load:g})\n"
          f"  B  2 clause parts x {len(load_axis)} load levels x {len(arms)} arms "
          f"x {len(seeds)} seeds x {len(caps)} caps  (N={a.fixed_n})\n"
          f"  horizon {HORIZON_SLOTS} slots, {N_DRIVEN} driven robots, "
          f"bound p98 <= {RAN_PDB_MS:g} ms, gap bound {GAP_BOUND_MS:g} ms",
          flush=True)

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    ledger = RunLedger(out.with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "horizon": HORIZON_SLOTS,
                        "n_driven": N_DRIVEN},
                       ("n_ues", "committed_mult", "arm", "seed", "cap"))
    done = ledger.done_keys()
    rows: list[dict] = list(ledger.banked())
    todo = [t for t in tasks
            if (t[0], t[1], t[2], t[3], t[4]) not in done]
    print(f"  {len(rows)} banked, {len(todo)} to run", flush=True)

    t0 = time.time()
    for _i, r in run_cells(one, todo, a.workers,
                           cost=lambda t: arm_cost(t[2]) * t[0]):
        rows.append(r); ledger.bank(r)
        if len(rows) % 25 == 0:
            print(f"    ... {len(rows)}/{len(tasks)} ({time.time()-t0:.0f}s)",
                  flush=True)
    wall = time.time() - t0

    # A PROJECTED, STAMPED ROW LIST, so `scripts/verify_claims.py` can
    # re-derive this campaign's published figures from the artefact rather
    # than from the ledger -- the ledger carries no code-state stamp, and an
    # unstamped artefact cannot be shown to match current code. Projected
    # (scalars only), because the rank-trace dicts and per-flow lists are
    # diagnostics, not figures, and the parent must not grow a second copy
    # of them.
    _FIGURE_FIELDS = ("n_ues", "committed_mult", "arm", "seed", "cap",
                      "part1_pass", "part2_pass", "silent_instrument",
                      "p98_worst_ms", "max_worst_ms", "gap_worst_ms",
                      "n_gaps_over", "dl_mbps", "ul_mbps", "wall_s")
    doc: dict[str, Any] = {
        "code_state": stamp(),
        "rows": [{k: r[k] for k in _FIGURE_FIELDS} for r in rows],
        "_horizon_slots": HORIZON_SLOTS, "_n_driven": N_DRIVEN,
        "_ran_pdb_ms": RAN_PDB_MS, "_gap_bound_ms": GAP_BOUND_MS,
        "_ue_axis": list(ue_axis), "_load_axis": list(load_axis),
        "_fixed_n": a.fixed_n, "_fixed_load": a.fixed_load,
        "_caps": caps, "_seeds": a.seeds,
        # THIS INVOCATION's wall clock, which is 0 on a pure re-entry from
        # the ledger -- so the campaign's own cost is carried separately as
        # the sum of per-run times, which survives a resume. A bare
        # `_wall_s: 0.0` in a regenerated artefact reads as a measurement,
        # and it is not one.
        "_wall_s_this_invocation": round(wall, 1),
        "_ran_this_invocation": len(todo),
        "_cpu_s_total": round(sum(r["wall_s"] for r in rows), 1),
        "_n_runs": len(rows),
    }
    for cap in caps:
        for arm in arms:
            base = [r for r in rows if r["cap"] == cap and r["arm"] == arm]
            aa = [r for r in base if r["committed_mult"] == a.fixed_load]
            bb = [r for r in base if r["n_ues"] == a.fixed_n]
            if aa:
                doc[f"A/cap{cap}/{arm}"] = _summarise(aa, "n_ues", ue_axis)
            if bb:
                doc[f"B/cap{cap}/{arm}"] = _summarise(
                    bb, "committed_mult", load_axis)
    out.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nwrote {out}  ({wall:.0f}s, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
