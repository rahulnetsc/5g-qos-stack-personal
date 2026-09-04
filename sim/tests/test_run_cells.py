"""`regime_sweep.run_cells` -- the shared process pool.

These pin the properties the per-runner identity checks
(`scripts/verify_parallel.py`) depend on but cannot isolate: that the index
travels with the result, that a worker exception is not swallowed, and that
the thread pinning actually reaches a worker. The identity checks answer
"does this runner still produce the same output"; these answer "does the
helper they all sit on behave", which is the layer the guard-test rule in
CLAUDE.md says a test can honestly pin.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from regime_sweep import arm_cost, run_cells  # noqa: E402


def _square(t):
    return t * t


def _omp(_t):
    return os.environ.get("OMP_NUM_THREADS")


def _boom(t):
    if t == 3:
        raise AssertionError("stop condition")
    return t


def _order_seen(t):
    return t


def test_serial_and_parallel_agree_and_carry_the_index():
    tasks = list(range(12))
    serial = [None] * len(tasks)
    for i, r in run_cells(_square, tasks, 1):
        serial[i] = r
    parallel = [None] * len(tasks)
    for i, r in run_cells(_square, tasks, 4):
        parallel[i] = r
    assert serial == [t * t for t in tasks]
    assert parallel == serial


def test_cost_ordering_does_not_change_the_indexed_result():
    """LONGEST-FIRST IS A SCHEDULING CHOICE, NOT A RESULT ONE. Submission is
    reordered by cost; the index carried through is what keeps the caller's
    output order independent of it."""
    tasks = list(range(12))
    out = [None] * len(tasks)
    for i, r in run_cells(_square, tasks, 4, cost=lambda t: t):
        out[i] = r
    assert out == [t * t for t in tasks]


def test_worker_exception_propagates():
    """g9's event-count assertion and g12's census assertion are STOP
    CONDITIONS. A pool that swallowed one would turn a refusal-to-score into
    a score -- which is the failure this runner's own published result is."""
    with pytest.raises(AssertionError, match="stop condition"):
        list(run_cells(_boom, list(range(6)), 4))
    with pytest.raises(AssertionError, match="stop condition"):
        list(run_cells(_boom, list(range(6)), 1))


def test_workers_get_single_threaded_numeric_backends():
    """W processes each running a multi-threaded BLAS oversubscribe the
    machine. Asserted in a worker rather than in the parent, because the
    parent's own numpy is already imported and would not show it."""
    seen = [r for _, r in run_cells(_omp, list(range(4)), 2)]
    assert seen == ["1", "1", "1", "1"]


def test_empty_task_list_yields_nothing():
    assert list(run_cells(_square, [], 4)) == []


def test_arm_cost_orders_the_arms_as_measured():
    """Ordering only -- the absolute values are a submission weight, not a
    prediction. Measured per-record cost at the N=8 / 20,000-slot base cell
    is PF 6.35 s < Reservation 8.08 s < TwoTier 12.99 s
    (sweeps/phase2/profile-2026-09-04)."""
    assert arm_cost("PF") < arm_cost("Reservation") < arm_cost("TwoTier")
    assert arm_cost("TwoTier", n_ues=32) > arm_cost("TwoTier", n_ues=8)
    assert arm_cost("TwoTier", points=8) > arm_cost("TwoTier", points=1)
    # An unknown arm must not sort to zero and starve itself to the tail.
    assert arm_cost("SomethingNew") > 0
