"""M09's hoist: the VALUE must not move, and the COMPLEXITY CLASS must not
come back.

`Scorecard._m09_per_second_jain` used to re-bucket the whole
`ts_arrived_bytes` array once per second-bucket, inside the per-second loop
-- O(flows x seconds x slots), quadratic in horizon. Hoisting the arrived
bucketing out of that loop is a pure refactor, and G11 cannot run without
it (docs/wp9-plan.md §37).

TWO TESTS, AND THE SECOND IS THE POINT. A value test proves the helper
still returns what it returned; it CANNOT catch someone moving the
bucketing back inside the loop, because the answer would be identical and
only the cost would change. Per CLAUDE.md's guard-test invariant -- a test
pins the thing you were looking at, not the pipeline around it -- the guard
that actually binds here is a SCALING assertion.

The scaling test is written to be robust on a loaded machine: it compares
the growth RATIO between two horizons against a threshold far from both the
linear expectation (~2x for a 2x horizon) and the quadratic one (~4x), so
ordinary timing noise cannot flip it. It is a complexity-class check, not a
benchmark.
"""

from __future__ import annotations

import time

import pytest

from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Scorecard, _bucket_by_second, _jain


def _record(horizon: int, n_ues: int = 4, seed: int = 1) -> RunRecord:
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon)
    summary = run(sc, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=True)
    return RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def _m09_original(record: RunRecord):
    """The pre-hoist nesting, kept verbatim as the reference.

    This is the ONLY place the quadratic form still exists, and it exists so
    the hoisted version can be diffed against it rather than trusted.
    """
    flows = [fr for fr in record.flows.values() if fr.ts_delivered_bytes is not None]
    if len(flows) < 2:
        return None
    time_s = record.timeseries_time_s
    per_flow_ratio_by_sec: dict[int, list[float]] = {}
    for fr in flows:
        for sec, delivered_list in _bucket_by_second(time_s, fr.ts_delivered_bytes).items():
            arrived_list = _bucket_by_second(time_s, fr.ts_arrived_bytes)[sec]   # inside the loop
            delivered = sum(delivered_list)
            arrived = sum(arrived_list)
            ratio = (delivered / arrived) if arrived > 0 else 1.0
            per_flow_ratio_by_sec.setdefault(sec, []).append(ratio)
    per_sec = [j for j in (_jain(v) for v in per_flow_ratio_by_sec.values()) if j is not None]
    if not per_sec:
        return None
    return {"worst": min(per_sec), "mean": sum(per_sec) / len(per_sec),
            "windows": len(per_sec)}


@pytest.mark.parametrize("horizon", [8_000, 20_000])
def test_hoist_is_bit_identical_to_the_original_nesting(horizon):
    """The refactor must not move the value -- at any horizon."""
    rec = _record(horizon)
    shipped = Scorecard()._m09_per_second_jain(rec).value
    reference = _m09_original(rec)
    assert reference is not None, "fixture produced no scoreable window"
    assert shipped == reference, (
        f"M09 changed value at horizon {horizon}: {shipped} != {reference}. "
        "The hoist is supposed to be a pure refactor; a difference here is a "
        "finding, not a re-baseline."
    )


def test_m09_cost_growth_is_not_quadratic_in_horizon():
    """The guard that a value test cannot provide.

    Doubling the horizon doubles both the sample count and the number of
    second-buckets. Linear-in-horizon work grows ~2x; the old nesting grew
    ~4x. Assert well below the midpoint so noise cannot flip the verdict.
    """
    small, large = 20_000, 40_000
    rec_s, rec_l = _record(small), _record(large)
    card = Scorecard()

    # warm the code path so first-call overhead is not in the measurement
    card._m09_per_second_jain(rec_s)

    def timed(rec) -> float:
        best = float("inf")
        for _ in range(3):                      # min of 3: noise is one-sided
            t0 = time.perf_counter()
            card._m09_per_second_jain(rec)
            best = min(best, time.perf_counter() - t0)
        return best

    t_small, t_large = timed(rec_s), timed(rec_l)
    ratio = t_large / max(t_small, 1e-9)

    # linear ~2.0, quadratic ~4.0. 3.0 is the midpoint; anything at or above
    # it means the arrived-series bucketing is back inside the per-second
    # loop (or something else superlinear was added).
    assert ratio < 3.0, (
        f"M09 cost grew {ratio:.2f}x for a 2x horizon "
        f"({t_small*1e3:.1f} ms -> {t_large*1e3:.1f} ms). Linear is ~2x and "
        "quadratic is ~4x -- the per-second loop is re-scanning a whole "
        "per-slot array again. See sim/scorecard.py's _m09_per_second_jain."
    )


def test_the_reference_implementation_really_is_quadratic():
    """Guards the guard.

    If the reference above were accidentally 'fixed' to match the shipped
    code, the identity test would still pass and would be comparing the
    hoisted version to itself. This asserts the reference still exhibits the
    growth the shipped one must not -- so the identity test is known to be
    comparing two different implementations.
    """
    small, large = 20_000, 40_000
    rec_s, rec_l = _record(small), _record(large)
    _m09_original(rec_s)

    def timed(rec) -> float:
        best = float("inf")
        for _ in range(3):
            t0 = time.perf_counter()
            _m09_original(rec)
            best = min(best, time.perf_counter() - t0)
        return best

    ratio = timed(rec_l) / max(timed(rec_s), 1e-9)
    assert ratio > 3.0, (
        f"the reference implementation grew only {ratio:.2f}x for a 2x "
        "horizon -- it is no longer quadratic, so "
        "test_hoist_is_bit_identical_to_the_original_nesting is comparing "
        "the shipped code against a copy of itself and is not a guard."
    )
