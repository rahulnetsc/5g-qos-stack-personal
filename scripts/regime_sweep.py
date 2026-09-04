"""Regime sweep -- the grid runner behind WP9's characterisation sweep, built
now (WP0) so every fidelity work package can use it for its own acceptance
checks, not just the final sweep.

Implements three disciplines from docs/p5g-sim-plan.md, load-bearing enough
to name explicitly:

  sec 5.2 Multiplicity guard: every result carries an effect size with a
      bootstrap confidence interval, never a bare winner; a claimed regime
      boundary must be contiguous across adjacent grid cells (an isolated
      winning cell surrounded by losses is noise) -- see check_contiguity().
  sec 5.3 Paired seeds: for a given cell, every arm runs on identical seeds,
      so the comparison is within-seed, not between independently-sampled
      runs -- see paired_seeds().
  sec 9 WP9 Regime selection: a cell producing 0% loss on both arms carries
      no information and must be excluded -- see regime_selection_excluded().

No pandas dependency (the project's own dependencies are numpy / cvxpy /
matplotlib / pyyaml only) -- tidy rows are plain dicts, written with the
stdlib csv module.
"""

from __future__ import annotations

import csv
import itertools
import multiprocessing as mp
import os
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Optional, Sequence

import numpy as np

from sim.config import ScenarioConfig
from sim.driver import run
from sim.run_record import RunRecord
from sim.scorecard import MetricResult, Population, Scorecard
from scheduler.interfaces import Scheduler


def paired_seeds(n_seeds: int, base_seed: int = 0) -> list[int]:
    """n_seeds deterministic seeds, identical across every arm in a cell --
    the pairing that makes the comparison within-seed (sec 5.3)."""
    rng = np.random.default_rng(base_seed)
    # Draw from a wide range so seeds don't collide with small hand-picked
    # scenario seeds elsewhere in the codebase.
    return [int(x) for x in rng.integers(0, 2**31 - 1, size=n_seeds)]


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts to dotted keys, for tidy CSV output."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, prefix=f"{key}."))
        else:
            out[key] = v
    return out


@dataclass
class SweepCell:
    """One point in the grid, before scheduler/seed are applied."""
    axis_values: dict[str, Any]
    scenario: ScenarioConfig


def axis_aware(factory: Callable[..., Scheduler]) -> Callable[..., Scheduler]:
    """Mark a scheduler factory as wanting the cell's axis values.

    WP9 (docs/wp9-plan.md, build item B2) needs `min_rb` as an axis, and
    `min_rb` is an *arm-config* value -- it reaches the scheduler through
    its constructor, not through the ScenarioConfig `build_scenario`
    produces. So some factories need the cell's axis values and some
    don't.

    This is an explicit opt-in rather than signature introspection on
    purpose: `ProportionalFair` is passed as a bare class in existing
    callers and its __init__ *does* accept parameters
    (`ewma_window_slots`), so "call with axis values if the signature
    accepts arguments" would call `ProportionalFair(min_rb=...)` and
    raise. A marker attribute cannot guess wrong.

        schedulers={
            "PF": ProportionalFair,                                  # unchanged
            "Reservation": axis_aware(lambda min_rb, **_: Reservation(min_rb=min_rb)),
        }

    The factory is called as `factory(**axis_values)`, so it should take
    `**_` to ignore the axes it doesn't care about.
    """
    factory._regime_sweep_axis_aware = True  # type: ignore[attr-defined]
    return factory


def sweep(
    axes: dict[str, list],
    build_scenario: Callable[..., ScenarioConfig],
    schedulers: dict[str, Callable[[], Scheduler]],
    n_seeds: int = 10,
    base_seed: int = 0,
    seeds: Optional[Sequence[int]] = None,
    driver_kwargs: Optional[dict] | Callable[..., dict] = None,
    scorecard: Optional[Scorecard] = None,
    metric_overrides: Optional[dict] = None,
    record_sink: Optional[Callable[[RunRecord, dict[str, Any]], None]] = None,
    run_sink: Optional[Callable[[RunRecord, dict[str, Any], dict], None]] = None,
) -> list[dict[str, Any]]:
    """Run every (cell, scheduler, seed) combination and return tidy rows.

    ``build_scenario(**axis_values, seed=seed)`` must return a ScenarioConfig
    for that grid cell and seed -- how axis values map onto a scenario
    mutation is scenario-specific (see e.g. scripts/scheduler_study.py's
    ``_scale_capacity`` for a one-axis example), so it's supplied by the
    caller rather than assumed here.

    Each row: {**axis_values, "scheduler": name, "seed": seed,
               "record_id": ..., <flattened per-metric fields>}.

    ``seeds``, if given, replaces ``paired_seeds(n_seeds, base_seed)``
    verbatim -- it is how a parallel runner hands one worker a single seed
    while keeping the pairing the caller already drew.

    ``driver_kwargs`` may be a plain dict (the same kwargs for every cell,
    as before) or a callable ``f(**axis_values) -> dict``, for axes that
    are driver knobs rather than scenario properties (WP9's
    ``sr_period_slots`` / ``k2_slots``). A dict is not callable, so the
    two cases are distinguishable without a flag.

    ``record_sink(record, axis_values)``, if given, is called once per run
    with the full RunRecord. Metrics needing extra arguments (M13, M16)
    are still not in the returned rows -- M13 is a cross-run metric and
    M16 needs a named flow pair -- but with a sink the caller can compute
    them, and re-score at different panel defaults, WITHOUT re-running:
    ``Scorecard.score()`` takes overrides and ``RunRecord.to_dict()``
    round-trips. Rows stay bounded; records go to the sink.

    ``run_sink(record, axis_values, summary)``, if given, is called once
    per run with the RAW driver summary alongside the record. It exists
    for the one thing ``record_sink`` structurally cannot supply: the live
    objects ``RunRecord.from_summary`` deliberately drops, above all
    ``summary["_message_ledger"]`` (WP7), whose own docstring in
    sim/driver.py says it is there so "a study can inspect raw per-message
    completions beyond the percentiles". WP9 stage 5 needs exactly that --
    a windowed M01/M02 restricted to a lidar-activation interval is not
    derivable from the whole-run percentiles the record carries, and the
    ledger survives neither ``from_summary`` nor persistence
    (docs/wp9-plan.md §16.2).

    A SECOND EXPLICIT PARAMETER, not a wider signature on ``record_sink``
    and not arity introspection on it -- ``axis_aware`` above already
    rejects introspection for this codebase, and for the same reason:
    every existing ``record_sink`` caller must keep working untouched, and
    a silently-widened callback would break them by arity rather than
    visibly.

    Called BEFORE ``record_sink`` so that whatever a record sink does to
    the record (stripping timeseries, projecting, persisting) cannot
    affect what the run sink observes. The summary is NOT retained here --
    a run sink that wants anything out of it must extract and discard, or
    it holds the ledger and the UE LCP state for the whole sweep.
    """
    driver_kwargs = {} if driver_kwargs is None else driver_kwargs
    scorecard = scorecard or Scorecard()
    metric_overrides = metric_overrides or {}
    # `seeds` EXISTS SO A POOL WORKER CAN RUN ONE SEED THROUGH THIS SAME
    # FUNCTION rather than through a second implementation of it. The
    # alternative -- a worker that rebuilds the scenario, runs the driver and
    # assembles the row itself -- is exactly the divergence 0ec8ddb avoided
    # by extracting `_online_rows_for`: two code paths that must stay in step
    # for a determinism claim to hold. The caller slices `paired_seeds()`
    # itself, so the pairing is unchanged; nothing here re-derives it.
    seeds = list(seeds) if seeds is not None else paired_seeds(n_seeds, base_seed)

    axis_names = list(axes.keys())
    rows: list[dict[str, Any]] = []
    for combo in itertools.product(*axes.values()):
        axis_values = dict(zip(axis_names, combo))
        dk = driver_kwargs(**axis_values) if callable(driver_kwargs) else driver_kwargs
        for seed in seeds:
            sc = build_scenario(seed=seed, **axis_values)
            for sched_name, factory in schedulers.items():
                sched = (
                    factory(**axis_values)
                    if getattr(factory, "_regime_sweep_axis_aware", False)
                    else factory()
                )
                summary = run(sc, sched, **dk)
                rec = RunRecord.from_summary(
                    scenario_name=sc.name, scheduler_name=sched_name, seed=seed,
                    flow_configs=sc.flows, summary=summary, arm=dict(dk),
                    meta=dict(axis_values),
                )
                if run_sink is not None:
                    run_sink(rec, axis_values, summary)
                if record_sink is not None:
                    record_sink(rec, axis_values)
                # BOTH POPULATIONS, EVERY ROW. Scorecard.score() now requires
                # an explicit population because a worst-flow statistic has
                # no meaning without one, and on a measured N=8 run the two
                # give OPPOSITE VERDICTS on G1 and G8 (sim/scorecard.py::
                # Population). Emitting one would just re-make the choice
                # silently, one layer out.
                #
                # ADD BESIDE, NEVER REDEFINE -- the same disposition WP9
                # Step 2 used for M20 against M03. The unsuffixed columns
                # keep meaning exactly what they have always meant
                # (all-flow), so no analyser or committed artefact changes
                # interpretation; the protected-fleet reading arrives as new
                # `.prot.` columns. A `.population` column records which is
                # which, so a reader never has to know the convention.
                scores = scorecard.score(
                    rec, population=Population.all_flows(), **metric_overrides)
                scores_prot = scorecard.score(
                    rec, population=Population.protected_fleet(),
                    **metric_overrides)
                row: dict[str, Any] = {
                    **axis_values,
                    "scheduler": sched_name,
                    "seed": seed,
                }
                for mid, res in scores.items():
                    row[f"{mid}.status"] = res.status
                    if res.population is not None:
                        row[f"{mid}.population"] = res.population
                    if isinstance(res.value, dict):
                        row.update(_flatten({mid: res.value}))
                    else:
                        row[mid] = res.value
                for mid, res in scores_prot.items():
                    if res.population is None:
                        continue          # system-level: one value, no subset
                    if isinstance(res.value, dict):
                        row.update(_flatten({f"{mid}.prot": res.value}))
                    else:
                        row[f"{mid}.prot"] = res.value
                rows.append(row)
    return rows


# --- the shared process pool ---------------------------------------------
#
# WHY THIS IS HERE AND NOT COPIED INTO EACH RUNNER. Parallelism landed once,
# at `scripts/wp9_sweep.py` (0ec8ddb), with a full determinism argument and a
# bit-identity check -- and nothing asked where else it belonged. Five later
# campaign runners imported that module's BASE / _arms / _driver_kwargs and
# inherited its CONFIGURATION but not its POOL, so every Phase 2 result
# (G1/G3/G5/G8 via phase2_core.py, G4, G6 at n=40, G9, G12) was produced on
# one of this machine's sixteen cores. G12 then timed out at 2,400 s having
# completed a single cell. See prediction-journal.md's fix-at-the-category
# rule, of which this is the second clean instance.
#
# So the pool lives beside `sweep()`, in the module every runner already
# imports, and a new runner gets it by importing it rather than by
# remembering to write it.

_THREAD_ENV = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
)


def pin_worker_threads() -> None:
    """Pin every numeric backend to one thread, in the PARENT, before any
    worker is spawned.

    W processes each running a multi-threaded BLAS/HiGHS oversubscribe the
    machine and run slower than the same W with one thread apiece. It has to
    happen here rather than in a Pool `initializer=`: with the spawn start
    method a worker imports numpy while unpickling the task function, which
    is BEFORE the initializer runs, and these variables are read at import.
    Spawned children inherit `os.environ`, so setting it in the parent is
    what reaches them.

    The parent's OWN already-imported numpy is unaffected, so in principle a
    BLAS-threaded reduction could order its sum differently between the
    serial reference path and a worker. Nothing in this simulator dispatches
    to a threaded BLAS kernel (the largest array in the hot path is Tier-1's
    10x64 LP, solved by HiGHS), and the per-script serial-vs-parallel
    identity check is what would catch it if that ever stopped being true --
    which is the point of running that check rather than asserting this.
    """
    for var in _THREAD_ENV:
        os.environ.setdefault(var, "1")


# Relative per-run cost, measured on the N=8 / 20,000-slot base cell
# (sweeps/phase2/profile-2026-09-04): driver+scoring+persist per record is
# 6.35 / 8.08 / 12.99 s for PF / Reservation / TwoTier. Used ONLY to order
# submission longest-first, so it never has to be exact -- a wrong cost costs
# balance, not correctness.
ARM_COST = {"PF": 1.00, "Reservation": 1.27, "TwoTier": 2.05}


def arm_cost(arm: str, n_ues: int = 1, points: int = 1) -> float:
    """Submission-ordering weight for one unit of work. Cost rises with the
    arm and with fleet size (measured super-linear in `n_ues`; the exponent
    is not load-bearing here, only the ordering it induces)."""
    return ARM_COST.get(arm, 1.0) * float(n_ues) * float(points)


def run_cells(
    fn: Callable[[Any], Any],
    tasks: Sequence[Any],
    workers: int,
    *,
    cost: Optional[Callable[[Any], float]] = None,
) -> Iterator[tuple[int, Any]]:
    """Run `fn` over independent `tasks`, yielding `(index, result)` as each
    completes. `index` is the task's position in the ORIGINAL `tasks` list,
    so a caller that needs serial-identical output ordering can place results
    itself without depending on completion order.

    `workers <= 1` runs serially in this process, yielding in task order.
    That path is the REFERENCE every converted runner is checked against, and
    it is kept for that reason rather than as a convenience -- 0ec8ddb's own
    `--workers 0`.

    THREE THINGS CARRIED FORWARD, each from a measured failure:

      * `pin_worker_threads()` above -- oversubscription.
      * **LONGEST FIRST, `chunksize=1`.** `cost(task)` orders submission
        descending. `pool.map`'s default chunking hands one worker a
        contiguous block of a cost-ordered list, which on g10_rerun.py's
        first run gave one worker every N=32 TwoTier cell and another every
        N=2 PF one -- worker CPU 7:55 against 4:35, a 1.7x imbalance. Without
        a cost the order is left alone; a wrong cost only costs balance,
        never correctness, since `index` is carried through.
      * **THIS GENERATOR RETAINS NOTHING.** `imap_unordered` is consumed one
        result at a time and each is handed straight to the caller. The 25 GB
        stall (wp9_sweep.m13_projection's docstring) was a parent holding
        live RunRecords; a worker must reduce or strip before returning, and
        this helper deliberately gives the parent no list to append to.

    An exception in a worker propagates out of the generator, which is what
    every one of these runners wants -- g9's event-count assertion and g12's
    census assertion are stop conditions, not warnings.
    """
    if not tasks:
        return
    if workers <= 1:
        for i, task in enumerate(tasks):
            yield i, fn(task)
        return

    order = list(range(len(tasks)))
    if cost is not None:
        order.sort(key=lambda i: -float(cost(tasks[i])))
    pin_worker_threads()
    payload = [(i, tasks[i]) for i in order]
    with mp.get_context("spawn").Pool(workers) as pool:
        for idx, result in pool.imap_unordered(
                _run_one_indexed, [(fn, i, t) for i, t in payload], chunksize=1):
            yield idx, result


def _run_one_indexed(packed: tuple) -> tuple[int, Any]:
    """Top-level so `spawn` can pickle it. Carries the ORIGINAL index through
    the pool so completion order and output order stay independent."""
    fn, idx, task = packed
    return idx, fn(task)


def write_csv(rows: list[dict[str, Any]], path: str) -> None:
    if not rows:
        raise ValueError("no rows to write")
    fieldnames = sorted({k for row in rows for k in row.keys()})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


# -- aggregation: bootstrap CIs -------------------------------------------

def bootstrap_ci(
    values: list[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0,
) -> dict[str, float]:
    """Percentile bootstrap: point estimate (sample mean) + a (1-alpha) CI."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {"point": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    boot_means = np.empty(n_boot)
    n = arr.size
    for i in range(n_boot):
        sample = arr[rng.integers(0, n, size=n)]
        boot_means[i] = sample.mean()
    lo, hi = np.percentile(boot_means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"point": float(arr.mean()), "lo": float(lo), "hi": float(hi), "n": int(n)}


def aggregate(
    rows: list[dict[str, Any]], group_keys: list[str], value_key: str, **boot_kwargs,
) -> list[dict[str, Any]]:
    """Group tidy rows by ``group_keys`` (e.g. axis values + scheduler) and
    bootstrap-CI ``value_key`` (a numeric metric column) within each group.
    Rows whose value_key is None or non-numeric are dropped from that group
    with a note, not silently averaged as zero."""
    groups: dict[tuple, list[float]] = {}
    dropped: dict[tuple, int] = {}
    for row in rows:
        key = tuple(row[k] for k in group_keys)
        v = row.get(value_key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            groups.setdefault(key, []).append(float(v))
        else:
            dropped[key] = dropped.get(key, 0) + 1

    out = []
    for key, values in groups.items():
        ci = bootstrap_ci(values, **boot_kwargs)
        out.append({
            **dict(zip(group_keys, key)),
            "metric": value_key,
            **ci,
            "n_dropped_non_numeric": dropped.get(key, 0),
        })
    return out


# -- multiplicity guard: contiguity ---------------------------------------

def check_contiguity(
    winners: dict[tuple, str], axes: dict[str, list],
) -> dict[tuple, bool]:
    """For each grid cell with a declared 'winner' (e.g. the scheduler with
    the better metric at that cell), check whether at least one grid-
    adjacent cell (one axis step away, all others held fixed) shares the
    same winner. A cell whose winner has NO adjacent agreement is flagged
    isolated=True -- per sec 5.2, an isolated winning cell is noise, not a
    regime boundary.

    ``winners`` keys are axis-value tuples in the same order as
    ``axes.keys()``; a cell not in ``winners`` (e.g. excluded by
    regime_selection_excluded) is treated as having no winner and cannot
    support a neighbour's claim.
    """
    axis_names = list(axes.keys())
    axis_index = {name: {v: i for i, v in enumerate(vals)} for name, vals in axes.items()}
    isolated: dict[tuple, bool] = {}

    for cell, winner in winners.items():
        has_agreeing_neighbour = False
        for axis_pos, axis_name in enumerate(axis_names):
            vals = axes[axis_name]
            idx = axis_index[axis_name][cell[axis_pos]]
            for step in (-1, 1):
                nidx = idx + step
                if not (0 <= nidx < len(vals)):
                    continue
                neighbour = list(cell)
                neighbour[axis_pos] = vals[nidx]
                neighbour = tuple(neighbour)
                if winners.get(neighbour) == winner:
                    has_agreeing_neighbour = True
        isolated[cell] = not has_agreeing_neighbour
    return isolated


# -- WP9 regime-selection discipline --------------------------------------

def regime_selection_excluded(
    arm_a_loss: Optional[float], arm_b_loss: Optional[float], eps: float = 1e-12,
) -> bool:
    """True if both arms show (numerically) zero loss at this cell -- such a
    cell carries no information about which scheduler is better and must be
    excluded from the swept grid's reported regime map (sec 9's WP9 note;
    this is the mistake sec 3 diagnoses in the original hardware sweep)."""
    if arm_a_loss is None or arm_b_loss is None:
        return False
    return arm_a_loss <= eps and arm_b_loss <= eps
