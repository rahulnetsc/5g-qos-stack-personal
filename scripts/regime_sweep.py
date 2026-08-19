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
from sim.scorecard import MetricResult, Scorecard
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


def sweep(
    axes: dict[str, list],
    build_scenario: Callable[..., ScenarioConfig],
    schedulers: dict[str, Callable[[], Scheduler]],
    n_seeds: int = 10,
    base_seed: int = 0,
    driver_kwargs: Optional[dict] = None,
    scorecard: Optional[Scorecard] = None,
    metric_overrides: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """Run every (cell, scheduler, seed) combination and return tidy rows.

    ``build_scenario(**axis_values, seed=seed)`` must return a ScenarioConfig
    for that grid cell and seed -- how axis values map onto a scenario
    mutation is scenario-specific (see e.g. scripts/scheduler_study.py's
    ``_scale_capacity`` for a one-axis example), so it's supplied by the
    caller rather than assumed here.

    Each row: {**axis_values, "scheduler": name, "seed": seed,
               "record_id": ..., <flattened per-metric fields>}.
    Metrics needing extra arguments (M13, M16) are not included -- call
    them separately over the returned RunRecords (not returned by this
    function to keep row size bounded; re-run build_scenario + run() with
    the same seed if you need the full RunRecord back for those).
    """
    driver_kwargs = driver_kwargs or {}
    scorecard = scorecard or Scorecard()
    metric_overrides = metric_overrides or {}
    seeds = paired_seeds(n_seeds, base_seed)

    axis_names = list(axes.keys())
    rows: list[dict[str, Any]] = []
    for combo in itertools.product(*axes.values()):
        axis_values = dict(zip(axis_names, combo))
        for seed in seeds:
            sc = build_scenario(seed=seed, **axis_values)
            for sched_name, factory in schedulers.items():
                summary = run(sc, factory(), **driver_kwargs)
                rec = RunRecord.from_summary(
                    scenario_name=sc.name, scheduler_name=sched_name, seed=seed,
                    flow_configs=sc.flows, summary=summary, arm=dict(driver_kwargs),
                    meta=dict(axis_values),
                )
                scores = scorecard.score(rec, **metric_overrides)
                row: dict[str, Any] = {
                    **axis_values,
                    "scheduler": sched_name,
                    "seed": seed,
                }
                for mid, res in scores.items():
                    row[f"{mid}.status"] = res.status
                    if isinstance(res.value, dict):
                        row.update(_flatten({mid: res.value}))
                    else:
                        row[mid] = res.value
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
