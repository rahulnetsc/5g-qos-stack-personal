"""Windowed ledger eviction: nothing is lost, nothing is retained, and the
run-level aggregates it invalidates are emitted as None rather than wrong.

WP9 G11 commit 2. A 30-minute soak retains ~24 GiB of per-message
bookkeeping with no flag to disable it (docs/wp9-plan.md §37). G11 scores
in 60 s windows and never needs the whole run at once.

THE GUARD THAT BINDS. Per CLAUDE.md, name what the check reads and what the
commit touches: `regression_corpus.py --check` reads RunRecords and this
commit touches the message ledger and the driver's end-of-run block -- they
DO intersect on the per-flow delay_* fields, but only on the WINDOWED path,
which the corpus never exercises. So --check is blind here and these tests
are the guard:

  1. UNION IDENTITY -- the completions handed to the sink, concatenated,
     are exactly the completions an unwindowed run produces. This is what
     makes eviction lossless rather than merely cheap.
  2. BOUNDED RETENTION -- the ledger never holds more than one window.
  3. HONEST DEGRADATION -- run-level message aggregates become None with a
     reason, not a number computed over the last partial window.
"""

from __future__ import annotations

from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.parametric import sweep_scenario

HORIZON = 8_000
WINDOW = 1_000


def _scenario(seed: int = 1, n_ues: int = 4):
    return sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=HORIZON)


def _key(c):
    """Identity of a completion, independent of object identity."""
    return (c.message.id, c.complete, c.late, c.completion_ts_s,
            c.delivered_bytes, c.dropped_bytes)


def _run(window: bool):
    seen: list[tuple[int, list]] = []
    sink = (lambda idx, comps: seen.append((idx, comps))) if window else None
    summary = run(_scenario(), ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=False,
                  window_slots=WINDOW if window else None,
                  window_sink=sink)
    return summary, seen


def test_eviction_loses_nothing_the_union_is_the_whole_run():
    """The load-bearing test: windowing must be a partition, not a filter."""
    plain, _ = _run(window=False)
    windowed, seen = _run(window=True)

    whole = sorted(_key(c) for c in plain["_message_ledger"].completions())
    # EVERYTHING must arrive through the sink -- there is no legitimate
    # residue, because the driver flushes the partial final window too.
    got = sorted(_key(c) for _, batch in seen for c in batch)

    assert got == whole, (
        f"windowed run saw {len(got)} completions, unwindowed {len(whole)}. "
        "Eviction must partition the run, not drop or duplicate any of it."
    )
    assert seen, "no window ever closed -- the sink was never called"


def test_each_completion_is_delivered_to_exactly_one_window():
    _, seen = _run(window=True)
    ids = [_key(c) for _, batch in seen for c in batch]
    assert len(ids) == len(set(ids)), "a completion was handed to two windows"


def test_retention_is_bounded_by_one_window_not_the_run():
    """What the commit exists for."""
    import math
    _, seen = _run(window=True)
    assert len(seen) == math.ceil(HORIZON / WINDOW), (
        f"expected {math.ceil(HORIZON / WINDOW)} windows, got {len(seen)} -- "
        "the boundary arithmetic is wrong")
    assert [i for i, _ in seen] == list(range(len(seen))), \
        "window indices are not contiguous from 0"
    plain, _ = _run(window=False)
    whole = len(plain["_message_ledger"].completions())
    worst_window = max(len(b) for _, b in seen)
    assert worst_window < whole, (
        "the largest single window is not smaller than the whole run; "
        "eviction is buying nothing")


def test_run_level_message_aggregates_are_None_with_a_reason_not_wrong():
    """Eviction invalidates run-level percentiles. Say so, do not fake it.

    Percentiles are not associative, so there is no honest run-level value
    to reassemble from per-window summaries -- emitting the last partial
    window's number would look exactly like a whole-run figure.
    """
    windowed, _ = _run(window=True)
    assert windowed["_ledger_windowed"] is True
    checked = 0
    for key, fl in windowed["flows"].items():
        if "message_stats_unavailable_reason" not in fl:
            continue
        checked += 1
        for fld in ("delay_p50_ms", "delay_p95_ms", "delay_p98_ms",
                    "delay_p99_ms", "message_count"):
            assert fl[fld] is None, f"{key}.{fld} is {fl[fld]!r}, expected None"
        assert fl["completion_ts_by_role_s"] is None
        assert fl["frame_completions"] is None
        assert "score per window" in fl["message_stats_unavailable_reason"]
    assert checked, "no flow carried the unavailable-reason marker"


def test_the_unwindowed_path_is_completely_unchanged():
    """The default must not move -- every existing caller passes no sink."""
    plain, seen = _run(window=False)
    assert seen == []
    assert plain["_ledger_windowed"] is False
    some = [fl for fl in plain["flows"].values() if fl.get("message_count")]
    assert some, "fixture produced no messages; the test proves nothing"
    for fl in some:
        assert fl["delay_p98_ms"] is not None
        assert "message_stats_unavailable_reason" not in fl


def test_a_partial_final_window_is_delivered_not_silently_dropped():
    """A horizon that is not a multiple of the window must not lose its tail.

    Without the residual flush the consumer scores one window fewer than the
    run contains and has no way to notice -- the same silent-truncation shape
    as G9's discarded scripted events.
    """
    import math
    seen = []
    h, w = 7_000, 2_000                       # deliberately not a multiple
    sc = sweep_scenario(seed=1, n_ues=4, horizon_slots=h)
    run(sc, ProportionalFair(ewma_window_slots=200), cqi_delay_slots=8,
        record_timeseries=False, window_slots=w,
        window_sink=lambda i, c: seen.append((i, c)))
    assert len(seen) == math.ceil(h / w) == 4
    assert [i for i, _ in seen] == [0, 1, 2, 3]


def test_a_drained_ledger_refuses_to_return_its_tail_as_a_result():
    """Loud beats silent: a tail is indistinguishable from a small run."""
    import pytest
    windowed, _ = _run(window=True)
    led = windowed["_message_ledger"]
    assert led.drained and led.drained_count > 0
    with pytest.raises(RuntimeError, match="drained"):
        led.completions()
    with pytest.raises(RuntimeError, match="drained"):
        led.completions_for(1, 1)


def test_M01_and_M15_report_PENDING_not_the_head_of_line_proxy():
    """The defect this test exists for, and the one a None-check missed.

    Setting message_count to None makes Scorecard._has_true_latency answer
    False, which it reads as "pre-WP7 record" and services with the
    head-of-line PROXY -- a different estimator reported under the same
    metric id, with no indication anything changed. Asserting the fields are
    None cannot catch that; asserting what the scorecard DOES with None can.
    """
    from sim.run_record import RunRecord
    from sim.scorecard import Population, Scorecard

    sc_cfg = _scenario()
    summary, _ = _run(window=True)
    rec = RunRecord.from_summary(
        scenario_name=sc_cfg.name, scheduler_name="PF", seed=1,
        flow_configs=sc_cfg.flows, summary=summary, arm={}, meta={})
    assert rec.message_ledger_windowed is True

    scores = Scorecard().score(rec, population=Population.all_flows())
    for mid in ("M01", "M15"):
        assert scores[mid].status == "pending", (
            f"{mid} is {scores[mid].status!r} with value {scores[mid].value!r} "
            "-- a windowed record must not be serviced by the head-of-line "
            "proxy under the same metric id")
        assert "window" in (scores[mid].note or "").lower()


def test_the_windowed_marker_survives_a_dict_round_trip():
    from sim.run_record import RunRecord
    sc_cfg = _scenario()
    summary, _ = _run(window=True)
    rec = RunRecord.from_summary(
        scenario_name=sc_cfg.name, scheduler_name="PF", seed=1,
        flow_configs=sc_cfg.flows, summary=summary, arm={}, meta={})
    assert RunRecord.from_dict(rec.to_dict()).message_ledger_windowed is True
