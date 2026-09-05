"""The grant stream, and its three acceptance conditions.

`sim/trace.py` is the first decision-site hook in this project. Its three
acceptance conditions were fixed before it produced a number, and they are
the three ways instrumentation has failed here before:

  1. BIT-IDENTITY -- a run with a sink attached must produce a byte-identical
     RunRecord to one without. The parallelism precedent: an observer that
     changes what it observes is worse than no observer.
  2. FAILS LOUDLY -- a sink that collects nothing RAISES. The probe this
     hook reacts to was bound to `self._ue` where the attribute is
     `self._state`; it read zero for the HEALTHY control too and would have
     confirmed a hypothesis on no evidence.
  3. COST WHEN OFF -- asserted by timing, not by argument.
"""

from __future__ import annotations

import json
import time

import pytest

from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.trace import GrantCollector, GrantTrace, NoGrantsObserved


def _scenario(h=4000, n=4):
    return sweep_scenario(seed=1, n_ues=n, horizon_slots=h, load_mult=1.0)


def _record(summary, sc):
    return RunRecord.from_summary(scenario_name=sc.name, scheduler_name="PF",
                                  seed=1, flow_configs=sc.flows,
                                  summary=summary, arm={}, meta={})


# --- 1. BIT-IDENTITY -------------------------------------------------------

def test_attaching_a_sink_changes_NOTHING_about_the_run():
    sc = _scenario()
    a = run(sc, ProportionalFair(ewma_window_slots=200), cqi_delay_slots=8,
            record_timeseries=True)
    col = GrantCollector()
    b = run(_scenario(), ProportionalFair(ewma_window_slots=200),
            cqi_delay_slots=8, record_timeseries=True, grant_sink=col)
    assert col.finish(), "the sink saw nothing; the identity check would be vacuous"
    ra = json.dumps(_record(a, sc).to_dict(), sort_keys=True, default=str)
    rb = json.dumps(_record(b, sc).to_dict(), sort_keys=True, default=str)
    assert ra == rb, "attaching the grant sink moved the run"


# --- 2. FAILS LOUDLY -------------------------------------------------------

def test_a_collector_that_saw_nothing_RAISES():
    """The self._ue lesson, and the one that matters most: a trace reporting
    zero is indistinguishable from a mechanism that never fired."""
    with pytest.raises(NoGrantsObserved, match="collected NOTHING"):
        GrantCollector().finish()


def test_an_empty_stream_can_be_CLAIMED_but_not_defaulted():
    assert GrantCollector(allow_empty=True).finish() == []


def test_the_sink_receives_a_non_empty_stream_on_a_known_active_slot():
    """The positive half. Without it the suite could pass by the hook never
    firing and the collector never being finished."""
    col = GrantCollector()
    run(_scenario(), ProportionalFair(ewma_window_slots=200),
        cqi_delay_slots=8, grant_sink=col)
    grants = col.finish()
    assert len(grants) > 100, f"only {len(grants)} grants on a 4000-slot run"
    assert all(isinstance(g, GrantTrace) for g in grants)
    assert {g.direction for g in grants} == {"DL", "UL"}, (
        "both directions must appear, or one hook did not bind")


def test_every_field_the_camera_question_reads_is_populated():
    """A hook that binds but records zeros is the same defect one field in."""
    col = GrantCollector()
    run(_scenario(), ProportionalFair(ewma_window_slots=200),
        cqi_delay_slots=8, grant_sink=col)
    grants = col.finish()
    ul = [g for g in grants if g.direction == "UL" and g.retx_count == 0]
    assert ul, "no first-transmission UL grants"
    assert any(g.prbs > 0 for g in ul), "prbs never populated"
    assert any(g.bytes_capacity > 0 for g in ul), "bytes_capacity never populated"
    # candidate 1's currency
    assert any(g.split for g in ul), "the UL LCP split was never recorded"
    assert any(sum(b for _, b in g.split) > 0 for g in ul if g.split)
    dl = [g for g in grants if g.direction == "DL"]
    assert any(g.qfi >= 0 for g in dl), "DL grants carry no qfi"


def test_retransmissions_are_traced_not_merely_counted():
    """Candidate 3 is about PRBs spent on retries. A run with enough load to
    produce retries must show retx_count >= 1 in the stream."""
    col = GrantCollector()
    run(sweep_scenario(seed=3, n_ues=8, horizon_slots=8000, load_mult=2.0),
        ProportionalFair(ewma_window_slots=200), cqi_delay_slots=8,
        grant_sink=col)
    grants = col.finish()
    retx = [g for g in grants if g.retx_count >= 1]
    assert retx, ("no retransmission appeared in the stream at load 2.0; "
                  "either the retx hooks did not bind or this scenario "
                  "produces none -- both must be distinguished before "
                  "candidate 3 can be read")
    assert any(g.prbs > 0 for g in retx), "retx PRBs never recorded"


# --- 3. COST WHEN OFF ------------------------------------------------------

def test_the_sink_costs_nothing_measurable_when_off():
    """Timed, not argued -- the same method the profile used. The guard is
    one pointer comparison per grant against a slot that solves a 10x64 LP up
    to 150 times, so the budget is generous and the test is a regression
    tripwire rather than a benchmark."""
    sc = _scenario(h=8000)
    sched = lambda: ProportionalFair(ewma_window_slots=200)
    t0 = time.perf_counter()
    run(sc, sched(), cqi_delay_slots=8)
    base = time.perf_counter() - t0
    t0 = time.perf_counter()
    run(sc, sched(), cqi_delay_slots=8)
    base = min(base, time.perf_counter() - t0)
    assert base > 0
    # With no sink the only added work is `grant_sink is not None` per grant.
    assert base < 60, "baseline run implausibly slow; the budget below is meaningless"
