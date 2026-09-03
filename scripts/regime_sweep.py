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
from dataclasses import dataclass
from typing import Any, Callable, Optional

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
    seeds = paired_seeds(n_seeds, base_seed)

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
