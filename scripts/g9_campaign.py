"""G9's join/re-join campaign (docs/wp9-plan.md §31, commit 4).

Scores J1-J5. Two assertions run BEFORE any metric is read, and the runner
refuses to report if either fails:

  1. THE EVENT-COUNT ASSERTION (CLAUDE.md's sixth empty-selection instance).
     A scenario that produces no events reads identically to one where
     everything went well: GT-6.3's first fade was half of t310, RLF never
     fired, and M18/M19 reported instant recovery. Every number was correct
     for the events that happened and there were none. So: assert non-zero
     events of the EXPECTED PATH before trusting any metric over them.

  2. THE NEIGHBOURS-POPULATION ASSERTION (§31.6). "Neighbours unaffected"
     is a delta guarantee of exactly G6's shape, and the G6 item cost four
     corrections to the same error. The population is fixed in advance --
     every UE EXCEPT the joiner, protected bearers only -- and asserted by
     printing the flow set and checking the joiner's flows are absent. A
     neighbours statistic that includes the recovering UE measures the
     event, not the containment.

Usage:
    uv run python scripts/g9_campaign.py [--smoke] [--seeds N]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import (arm_cost, bootstrap_ci,  # noqa: E402
                          paired_seeds, run_cells)
from sim.baselines.pf import ProportionalFair  # noqa: E402
from sim.driver import run  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.scenarios.g9 import (gt61_warm_rejoin, gt62_cold_attach,  # noqa: E402
                              gt63_rlf_recovery, joiner_ue_id,
                              neighbour_ue_ids)
from sim.scorecard import Population, Scorecard  # noqa: E402
from scheduler import load_two_tier  # noqa: E402
from scheduler.reservation import Reservation  # noqa: E402

_TT = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")
CQI_DELAY_SLOTS = 8
# 16 physical cores; 77 % measured efficiency at W=16 (wp9-g11-plan §1.3).
_DEFAULT_WORKERS = 16
# GT-6.1 expects `warm`, GT-6.2 `cold`, GT-6.3 `reestablish`. Named per
# scenario so the assertion checks the RIGHT path, not merely "some events".
CASES = {
    "GT-6.1_warm": (gt61_warm_rejoin, "warm"),
    "GT-6.2_cold": (gt62_cold_attach, "cold"),
    "GT-6.3_rlf": (gt63_rlf_recovery, "reestablish"),
}


def _arms():
    return {"PF": lambda: ProportionalFair(ewma_window_slots=200),
            "Reservation": lambda: Reservation(min_rb=5),
            "TwoTier": lambda: load_two_tier(_TT, min_rb=5)}


def expected_event_count(sc, want_path: str) -> int | None:
    """How many events the SCENARIO SPECIFIES **AND THE HORIZON CAN REACH** --
    derived from the schedule, never restated. `reestablish` is emergent
    (sim/rlf.py observing the SNR trace), so it has no scheduled count and
    returns None.

    **THE CLIP IS A DIFFERENT DEFECT FROM A SCENARIO NO-OPPING, AND IT FAILS
    IN THE OPPOSITE DIRECTION** (`docs/wp9-defects-log.md` #23). A scenario
    whose events fall past the horizon reports FEWER events than it
    scheduled; this function, unclipped, reported the FULL scheduled count.
    So the guard compared a real count against a number the horizon could
    not reach, and **refused to score at all** -- an abort, not a partial
    score. That is the safe direction to fail in, and it may well be why G9
    aborted rather than publishing a partial run; but "the guard is
    unsatisfiable" and "the arm is degenerate" are different diagnoses and
    the abort message could not distinguish them.

    `sim/scenarios/schedule_guard.py` now refuses to BUILD such a scenario,
    so this clip is the second line of defence rather than the first -- kept
    because a caller may pass `allow_partial_schedule=True`, which is exactly
    the case where the scheduled and reachable counts legitimately differ.
    """
    if want_path == "reestablish":
        return None
    joiner = [ue for ue in sc.ues if ue.join is not None][0]
    kinds = {"warm": ("app_restart",), "cold": ("power_on",)}[want_path]
    horizon = getattr(sc, "horizon_slots", None)
    return sum(1 for e in joiner.join.events
               if e.kind in kinds and (horizon is None or e.slot < horizon))


def assert_events_fired(rec: RunRecord, want_path: str, label: str,
                        expected: int | None = None) -> int:
    """ASSERTION 1, STRENGTHENED: assert the EXPECTED count, not non-zero.

    The first version asked only "did the mechanism fire at all". That is a
    WEAKER QUESTION than "did it fire as often as the scenario specifies",
    and the gap between them is exactly where a PARTIALLY degenerate run
    hides. It did: TwoTier recorded 3.8 of 10 scripted warm restarts and
    1.0 of 5 cold cycles, and the non-zero check passed on every one --
    so M18/M19/M21 were computed over a different, smaller event set than
    the other arms, and the arms were compared as though they were not.

    AND THE COUNT CHECK IS STILL NOT ENOUGH (§34.5a). Those figures count
    events RECORDED. Re-running the campaign and counting attaches
    COMPLETED gives TwoTier 0 of 50 scheduled cold cycles -- on every seed --
    against PF and Reservation at 50 of 50. An arm can register its full
    scheduled count and complete none of them, and a count assertion passes
    on that while M19/M21 report 0.0 ms, i.e. INSTANT RECOVERY, for a robot
    that never came back. Firing and finishing are different questions.
    Assert `n_never_completed == 0` alongside the count -- M18 already
    computes it.
    """
    events = [e for e in (rec.join_events or []) if e.path == want_path]
    if not events:
        raise AssertionError(
            f"{label}: ZERO '{want_path}' events. Every metric over them "
            f"would be correct-for-nothing and read as instant success -- "
            f"CLAUDE.md's sixth empty-selection instance. Check the scenario "
            f"fired at all (for reestablish: is the fade longer than t310?).")
    if expected is not None and len(events) != expected:
        raise AssertionError(
            f"{label}: {len(events)} '{want_path}' events but the scenario "
            f"schedules {expected}. A partially-degenerate run is NOT a "
            f"smaller sample of the same thing -- the survivors are "
            f"self-selected, so arms with different counts are not "
            f"comparable. CAUSE, measured (§34.5a): NOT the overlap "
            f"hypothesis §34.4 proposed -- no completed handshake ever "
            f"collides with its successor. On TwoTier the app handshake "
            f"never completes at all (0 of 50 cold attaches), the joiner "
            f"gets zero UL grants after re-attach, and every later scripted "
            f"event is consumed-and-discarded by sim/join.py rather than "
            f"deferred. Lengthening the period does not fix it.")
    return len(events)


def assert_neighbour_population(rec: RunRecord, joiner: int,
                                neighbours: list[int], label: str) -> list[str]:
    """ASSERTION 2 (§31.6). Returns the flow keys that entered the
    neighbours statistic, so the population is PRINTED, not assumed."""
    excl = Scorecard.NON_PROTECTED_5QI
    keys = sorted(fr.key for fr in rec.flows.values()
                  if fr.ue_id in neighbours and fr.qfi not in excl)
    bad = [k for k in keys if k.startswith(f"ue{joiner}_")]
    if bad:
        raise AssertionError(
            f"{label}: joiner's flows {bad} entered the NEIGHBOURS "
            f"statistic -- that measures the event, not the containment")
    if not keys:
        raise AssertionError(f"{label}: neighbours statistic selected NO flows")
    return keys


def _neighbour_stats(rec: RunRecord, neighbours: list[int]) -> dict:
    """Protected-bearer aggregates over the neighbours only."""
    excl = Scorecard.NON_PROTECTED_5QI
    flows = [fr for fr in rec.flows.values()
             if fr.ue_id in neighbours and fr.qfi not in excl]
    arr = sum(fr.bytes_arrived for fr in flows)
    bad = sum(fr.bytes_dropped_pdb + fr.bytes_delivered_late_pdb for fr in flows)
    return {"m02": (bad / arr) if arr else 0.0,
            "worst_p98_ms": max((fr.delay_p98_ms for fr in flows), default=0.0)}


def run_one(build, path, arm_name, arm_factory, seed, n_neighbours, joiner_on,
            rejoin_seed=False):
    """One run. `joiner_on=False` builds the paired CONTROL -- same seed,
    same fleet, no join schedule -- so the neighbours delta is within-seed."""
    sc = build(seed=seed, n_neighbours=n_neighbours)
    if not joiner_on:
        ues = [dataclasses.replace(ue, join=None, scripted_fade=())
               for ue in sc.ues]
        sc = dataclasses.replace(sc, ues=ues, name=sc.name + "_control")
    summary = run(sc, arm_factory(), cqi_delay_slots=CQI_DELAY_SLOTS,
                  record_timeseries=True, rejoin_seed_bsr=rejoin_seed)
    return sc, RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=arm_name, seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def _task(task: tuple) -> dict:
    """One (case, arm, seed): the joined run, its paired no-join CONTROL, and
    both assertions -- run HERE, in the worker, so a scenario that produced
    no events still stops the campaign rather than being aggregated.

    Returns only reduced scalars and the neighbour flow-key list. The two
    RunRecords stay in the worker and die with it; nothing live crosses back
    (wp9_sweep.m13_projection's 25 GB note).
    """
    # The re-join-seed flag travels IN THE TASK, not in a module-level
    # cell: `spawn` workers re-import this module and would read the
    # default. Same trap as monkeypatching a pool worker.
    label, arm_name, seed, n_nb, rejoin_seed = task
    build, want_path = CASES[label]
    factory = _arms()[arm_name]
    sc, rec = run_one(build, want_path, arm_name, factory, seed, n_nb,
                      joiner_on=True, rejoin_seed=rejoin_seed)
    joiner, neighbours = joiner_ue_id(sc), neighbour_ue_ids(sc)
    n_ev = assert_events_fired(rec, want_path, f"{label}/{arm_name}",
                               expected=expected_event_count(sc, want_path))
    keys = assert_neighbour_population(rec, joiner, neighbours,
                                       f"{label}/{arm_name}")
    # G9 is about what the FLEET receives across a join -- the neighbours
    # clause explicitly excludes the background aggressor -- so the
    # population is the protected fleet, stated rather than inherited.
    scored = Scorecard().score(rec, population=Population.protected_fleet())
    out = {"n_ev": n_ev, "keys": keys}
    for key in ("M18", "M19", "M21"):
        v = (scored[key].value or {}).get("by_path", {}).get(want_path)
        out[key] = v["p95_ms"] if v and v.get("p95_ms") is not None else None
    _, ctl = run_one(build, want_path, arm_name, factory, seed, n_nb,
                     joiner_on=False, rejoin_seed=rejoin_seed)
    a, b = _neighbour_stats(rec, neighbours), _neighbour_stats(ctl, neighbours)
    # M02 on the neighbours is SATURATED AT ZERO even with bg at 0.876 UL
    # utilisation -- their protected flows sit at p98 15.5 ms against a
    # 100 ms PDB, ~6x headroom. A delta of a floored statistic cannot move,
    # so the sensitive instrument is the p98 delay delta. Both are reported:
    # M02 is the guarantee's own currency, p98 is what can actually detect a
    # change.
    out["nb_dm02"] = a["m02"] - b["m02"]
    out["nb_dp98"] = a["worst_p98_ms"] - b["worst_p98_ms"]
    return out


def _aggregate(per_seed: list[dict]) -> dict:
    """The per-arm summary, from results already ordered by seed. Split out
    so it reads the same list the serial path built, in the same order --
    the bootstrap CIs are seeded, so order is load-bearing here."""
    m18 = [r["M18"] for r in per_seed if r["M18"] is not None]
    m19 = [r["M19"] for r in per_seed if r["M19"] is not None]
    m21 = [r["M21"] for r in per_seed if r["M21"] is not None]
    nb_deltas = [r["nb_dm02"] for r in per_seed]
    nb_p98_deltas = [r["nb_dp98"] for r in per_seed]
    ci = bootstrap_ci(nb_deltas, seed=4242) if nb_deltas else None
    ci_p98 = bootstrap_ci(nb_p98_deltas, seed=4243) if nb_p98_deltas else None
    return {
        "events_per_run": statistics.mean([r["n_ev"] for r in per_seed]),
        "m18_p95_median": statistics.median(m18) if m18 else None,
        "m19_p95_median": statistics.median(m19) if m19 else None,
        "m21_p95_median": statistics.median(m21) if m21 else None,
        "neighbour_dm02": {"ci": ci, **Scorecard.robust_delta_summary(nb_deltas)},
        "neighbour_dp98_ms": {"ci": ci_p98,
                              **Scorecard.robust_delta_summary(nb_p98_deltas)},
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rejoin-seed", action="store_true",
                    help="MODEL C at the join edges "
                         "(docs/rejoin-seed-and-desync-registration.md)")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--neighbours", type=int, default=7)
    # Exists so the serial-vs-parallel identity check has a grid that runs to
    # completion. The default is every arm, and on the default grid TwoTier
    # still aborts on the event-count assertion -- that abort IS G9's
    # published result (docs/phase2-results.md) and is checked separately, by
    # verify_parallel's `g9_campaign_stop` case.
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--out", default="sweeps/wp9/g9_campaign.json")
    ap.add_argument("--workers", type=int, default=_DEFAULT_WORKERS,
                    help="0 or 1 runs serially -- the reference path "
                         "scripts/verify_parallel.py checks against")
    args = ap.parse_args(argv[1:])
    n_seeds = 2 if args.smoke else args.seeds
    n_nb = 3 if args.smoke else args.neighbours
    seeds = paired_seeds(n_seeds)
    all_arms = _arms()
    arms = [a for a in args.arms.split(",") if a]
    unknown = [a for a in arms if a not in all_arms]
    if unknown:
        raise SystemExit(f"unknown arm(s) {unknown}; known: {list(all_arms)}")

    # Task order is the serial order -- case, then arm, then seed -- so the
    # per-arm lists the aggregation reads are seed-ordered whatever order the
    # pool returns them in. The seeded bootstrap makes that load-bearing.
    tasks = [(label, arm_name, seed, n_nb, args.rejoin_seed)
             for label in CASES for arm_name in arms for seed in seeds]
    results: list[dict | None] = [None] * len(tasks)
    per_group = len(seeds)
    done_in_group: dict[tuple[str, str], int] = {}
    out: dict = {}

    def _flush(partial: bool) -> None:
        """Rebuild the whole document in CANONICAL order and write it. The
        partial writes exist because this machine has lost three runs to
        environmental kills (see the note this replaces); rebuilding rather
        than appending means the surviving file is in the same order as a
        completed one, so a partial and a final are diffable."""
        doc = {label: {arm: out[(label, arm)]
                       for arm in arms if (label, arm) in out}
               for label in CASES}
        doc = {k: v for k, v in doc.items() if v}
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {**doc, "_partial": True} if partial else doc,
            indent=2, default=str))

    for i, res in run_cells(_task, tasks, args.workers,
                            cost=lambda t: arm_cost(t[1])):
        results[i] = res
        label, arm_name, seed, _, _ = tasks[i]
        # PER-RESULT HEARTBEAT. Without it the only progress signal is
        # process liveness: this runner's first launch wrote a ZERO-LINE log
        # for its entire duration, because Python block-buffers a redirected
        # stdout and the summary prints come only at the end of an arm. Same
        # family as the run logs lost to session-scoped scratchpads. In
        # completion order, which is a log, not a result.
        print(f"    ... {label}/{arm_name} seed {seed} done", flush=True)
        key = (label, arm_name)
        done_in_group[key] = done_in_group.get(key, 0) + 1
        if done_in_group[key] != per_group:
            continue
        idx0 = tasks.index((label, arm_name, seeds[0], n_nb, args.rejoin_seed))
        group = [results[idx0 + k] for k in range(per_group)]
        # ASSERTION 2's population is PRINTED, not assumed (§31.6).
        print(f"\n{'=' * 78}\n{label}/{arm_name}\n{'=' * 78}", flush=True)
        keys = group[0]["keys"]
        print(f"  [{arm_name}] neighbours population ({len(keys)} flows): "
              f"{keys[:4]}{' ...' if len(keys) > 4 else ''}", flush=True)
        summary = _aggregate(group)
        ci, ci_p98 = summary["neighbour_dm02"], summary["neighbour_dp98_ms"]
        print(f"  {arm_name:<12} events/run={summary['events_per_run']:5.1f}  "
              f"M18 p95={summary['m18_p95_median']}  "
              f"M19 p95={summary['m19_p95_median']}  "
              f"M21 p95={summary['m21_p95_median']}", flush=True)
        print(f"  {'':<12} neighbours ΔM02  mean {ci['ci']['point']:+.6f} "
              f"[{ci['ci']['lo']:+.6f},{ci['ci']['hi']:+.6f}]  "
              f"median {ci['median']:+.6f} worse {ci['frac_worse']:.0%}  "
              f"n_seeds={ci['n']} paired")
        print(f"  {'':<12} neighbours Δp98  mean {ci_p98['ci']['point']:+.3f} ms "
              f"[{ci_p98['ci']['lo']:+.3f},{ci_p98['ci']['hi']:+.3f}]  "
              f"median {ci_p98['median']:+.3f} "
              f"worse {ci_p98['frac_worse']:.0%}", flush=True)
        out[key] = summary
        # DURABLE AFTER EVERY (case, arm), not once at the end. The only
        # write used to be the terminal one below, so a kill at hour 9 of an
        # overnight run lost the whole campaign.
        #
        # This is DURABILITY, not resume: a relaunch still recomputes
        # everything. True resume needs a per-(case, arm) ledger and a skip,
        # ~25 lines, and is deliberately deferred -- it buys nothing at Phase
        # 2's 5-10 minute budget and the incremental write already removes
        # the catastrophic case.
        _flush(partial=True)

    out = {label: {arm: out[(label, arm)] for arm in arms}
           for label in CASES}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
