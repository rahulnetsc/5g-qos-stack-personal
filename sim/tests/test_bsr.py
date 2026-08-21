"""Tests for sim/bsr.py (WP3).

Commit 1: quantisation, per-LCG structure, the cold-start/re-arm probe.
Commit 2: event-triggering (regular/periodic/retx) and the resulting
sched_ul_bytes crumb-collapse gate -- a BSR is now assembled only when
`pending`, not on every grant.

WP4 note: the cold-start/re-arm probe from commit 1 was replaced by the
real SR mechanism in `sim/ul_access.py` -- `broadcast()` now takes a
`ul_access` argument instead of bypassing to the true backlog itself. Most
tests below just need a `UlAccessModel` that never fires (constructed but
never ticked) to keep testing quantisation/aggregation mechanics in
isolation from SR; see `_no_sr()`. SR-specific behaviour has its own tests
in `sim/tests/test_ul_access.py`.
"""

import re
from pathlib import Path

import pytest

from sim.bsr import (
    NR_LONG_BSR_TABLE,
    NR_SHORT_BSR_TABLE,
    BsrModel,
    quantise_long,
    quantise_short,
)
from sim.buffer import BufferModel
from sim.ul_access import UlAccessModel
from scheduler.flow import FlowConfig

_OAI_SOURCE = Path(__file__).resolve().parents[2] / "oai-branches" / "two-tier" / "nr_mac_common.c"

# A representative mu=1 slot duration (0.5 ms), used throughout so the
# 5 ms/80 ms hardware timer values land on convenient slot counts (10/160).
_SLOT_S = 0.0005


def _parse_c_table(name: str) -> tuple[int, ...]:
    src = _OAI_SOURCE.read_text()
    m = re.search(rf"{name}\[{name}_SIZE\]\s*=\s*{{([^}}]*)}}", src)
    return tuple(int(x) for x in m.group(1).replace(",", " ").split())


def test_short_bsr_table_matches_vendored_oai_source():
    """sim/bsr.py's transcription must match oai-branches/two-tier/
    nr_mac_common.c byte-for-byte -- a wrong table would be silently wrong
    in exactly the metric (quantisation error) this WP exists to fix."""
    assert NR_SHORT_BSR_TABLE == _parse_c_table("NR_SHORT_BSR_TABLE")
    assert len(NR_SHORT_BSR_TABLE) == 32
    assert NR_SHORT_BSR_TABLE[0] == 0
    assert list(NR_SHORT_BSR_TABLE) == sorted(NR_SHORT_BSR_TABLE)


def test_long_bsr_table_matches_vendored_oai_source():
    assert NR_LONG_BSR_TABLE == _parse_c_table("NR_LONG_BSR_TABLE")
    assert len(NR_LONG_BSR_TABLE) == 256
    assert NR_LONG_BSR_TABLE[0] == 0
    assert list(NR_LONG_BSR_TABLE) == sorted(NR_LONG_BSR_TABLE)


def test_quantise_short_zero_is_zero():
    """A reported index of 0 ("no data") is never overestimated (the +1
    headroom bump is skipped) -- matches overestim_bsr_index's `idx > 0`
    guard, gNB_scheduler_ulsch.c:243-244."""
    assert quantise_short(0) == 0
    assert quantise_long(0) == 0


def test_quantise_short_overestimates_below_saturation():
    """quantise_short(x) >= x for every x the table can actually represent
    (below its last, open-ended bucket) -- the UE's own ceiling-quantise
    plus the gNB's +1-index headroom bump are both only-increasing steps.
    Above the table's max representable size it saturates instead (a real
    BSR limitation, not a bug) -- see test_quantise_short_saturates_above_max."""
    for x in range(0, NR_SHORT_BSR_TABLE[-2] + 1, 137):
        assert quantise_short(x) >= x, x


def test_quantise_long_overestimates_below_saturation():
    for x in range(0, 200_000, 4001):
        assert quantise_long(x) >= x, x


def test_quantise_short_monotonic():
    prev = -1
    for x in range(0, 400_000, 211):
        q = quantise_short(x)
        assert q >= prev
        prev = q


def test_quantise_short_saturates_above_max():
    """A buffer larger than the table's last bucket cannot be represented
    exactly -- BSR saturates at the max value, same as real hardware."""
    assert quantise_short(NR_SHORT_BSR_TABLE[-1]) == NR_SHORT_BSR_TABLE[-1]
    assert quantise_short(NR_SHORT_BSR_TABLE[-1] * 10) == NR_SHORT_BSR_TABLE[-1]


def test_quantise_short_is_not_idempotent():
    """Re-quantising an already-quantised value is NOT a no-op: the gNB's
    +1-index headroom bump (overestim_bsr_index) compounds on a second
    pass. Documented explicitly since it is easy to assume otherwise."""
    once = quantise_short(11)
    twice = quantise_short(once)
    assert once != twice
    assert twice > once


def _flow(ue_id, qfi, lcg, priority_level=100):
    return FlowConfig(ue_id=ue_id, qfi=qfi, direction="UL", lcg=lcg, priority_level=priority_level)


def test_flowconfig_defaults_lcg_from_5qi_and_rejects_out_of_range():
    """FlowConfig.__post_init__ resolves lcg=-1 from the 5QI table and
    raises on an explicit out-of-range override -- the one new invariant
    this port introduces (no OAI AssertFatal maps to it directly)."""
    f = FlowConfig(ue_id=1, qfi=2, direction="UL")
    assert 0 <= f.lcg < 8

    with pytest.raises(ValueError):
        FlowConfig(ue_id=1, qfi=2, direction="UL", lcg=8)
    with pytest.raises(ValueError):
        FlowConfig(ue_id=1, qfi=2, direction="UL", lcg=-2)


def _no_sr(flows):
    """A UlAccessModel that never fires -- never had on_arrivals/tick
    called, so sr_report_floor() always returns 0. Used by tests about
    quantisation/aggregation mechanics, which are orthogonal to SR."""
    return UlAccessModel(flows, _SLOT_S)


def _force_pending(bsr, ue_id):
    """Test helper: jump straight to "a BSR is due" without exercising the
    trigger logic itself -- used by tests about quantisation/aggregation
    mechanics, which are orthogonal to why a report was due."""
    bsr._state[ue_id].pending = True


def test_short_bsr_used_and_other_lcgs_zeroed_when_one_lcg_active():
    """When exactly one LCG has real backlog, the assembled BSR is short
    format: that LCG's estimate is set, every other LCG's slot reads 0 --
    the aliasing mechanic (gNB_scheduler_ulsch.c:631-632)."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    buffers.register(1, 9, is_ul=True, lcg=1)
    flows = [_flow(1, 2, 0), _flow(1, 9, 1)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 0, 0.0)      # LCG 0: no data
    buffers.enqueue(1, 9, 2000, 0.0)   # LCG 1: only active LCG

    _force_pending(bsr, 1)
    bsr.on_ul_grant(ue_id=1, tb_size=0, delivered_bytes=0, slot_index=0, buffers=buffers)
    bsr.broadcast(buffers, _no_sr(flows))  # BsrModel's internal state -> BufferState

    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == 0
    assert buffers.state(1, 9).estimated_ul_buffer_per_lcg == quantise_short(2000)


def test_long_bsr_used_when_multiple_lcgs_active():
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    buffers.register(1, 9, is_ul=True, lcg=1)
    flows = [_flow(1, 2, 0), _flow(1, 9, 1)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 500, 0.0)
    buffers.enqueue(1, 9, 2000, 0.0)

    _force_pending(bsr, 1)
    bsr.on_ul_grant(ue_id=1, tb_size=0, delivered_bytes=0, slot_index=0, buffers=buffers)
    bsr.broadcast(buffers, _no_sr(flows))

    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == quantise_long(500)
    assert buffers.state(1, 9).estimated_ul_buffer_per_lcg == quantise_long(2000)


def test_per_lcg_estimate_frozen_between_grants_not_drained():
    """estimated_ul_buffer_per_lcg is never written back after a grant --
    only reset-then-repopulated on the next BSR. README §7 finding (a):
    port the frozen behaviour faithfully, do not drain it."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 1000, 0.0)
    _force_pending(bsr, 1)
    bsr.on_ul_grant(ue_id=1, tb_size=1000, delivered_bytes=1000, slot_index=0, buffers=buffers)
    ul_access = _no_sr(flows)
    bsr.broadcast(buffers, ul_access)
    reported_after_first_bsr = buffers.state(1, 2).estimated_ul_buffer_per_lcg
    assert reported_after_first_bsr == quantise_short(1000)

    # No new grant: broadcast() alone must not change the frozen estimate,
    # even though the true backlog is now 0 (fully drained).
    for _ in range(5):
        bsr.broadcast(buffers, ul_access)
    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == reported_after_first_bsr


def test_sched_ul_bytes_resets_to_zero_only_when_pending():
    """Both BSR formats reset sched_ul_bytes = 0 unconditionally on
    reception (gNB_scheduler_ulsch.c:630, 651) -- but only on an actual
    BSR, not every grant (that's the whole point of event-triggering)."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 5000, 0.0)
    # Not pending: sched_ul_bytes accumulates, no reset.
    bsr.on_ul_grant(ue_id=1, tb_size=200, delivered_bytes=200, slot_index=0, buffers=buffers)
    assert bsr._state[1].sched_ul_bytes == 200

    _force_pending(bsr, 1)
    bsr.on_ul_grant(ue_id=1, tb_size=200, delivered_bytes=200, slot_index=1, buffers=buffers)
    assert bsr._state[1].sched_ul_bytes == 0


def test_scalar_decrements_on_every_grant_independent_of_pending():
    """README §7 finding (b): the scalar estimated_ul_buffer decrements on
    actual data receipt regardless of whether this grant also carries a
    BSR -- independent of the per-LCG array, which only a BSR touches.
    This is what lets the two desync between BSRs."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    st = bsr._state[1]
    st.estimated_ul_buffer = 1000
    buffers.enqueue(1, 2, 9999, 0.0)  # true backlog present, but not pending
    bsr.on_ul_grant(ue_id=1, tb_size=300, delivered_bytes=300, slot_index=0, buffers=buffers)
    assert st.estimated_ul_buffer == 700  # decremented, NOT reassembled
    assert st.estimated_ul_buffer_per_lcg == [0] * 8  # per-LCG array untouched


def test_bsr_not_assembled_when_not_pending():
    """on_ul_grant must not touch estimated_ul_buffer_per_lcg at all unless
    pending -- the crux of event-triggering."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 5000, 0.0)
    bsr.on_ul_grant(ue_id=1, tb_size=500, delivered_bytes=500, slot_index=0, buffers=buffers)
    assert bsr._state[1].estimated_ul_buffer_per_lcg == [0] * 8
    assert bsr._state[1].pending is False


def test_broadcast_alone_cannot_report_without_a_grant_or_sr():
    """A flow with real data but no UL grant and no SR engagement never
    becomes visible -- broadcast() alone does nothing. WP3's cold-start
    probe used to bypass straight to the true backlog here; WP4 replaced
    it with the real SR path (sim/ul_access.py), which this test
    deliberately never engages (ul_access is constructed but never ticked)
    to isolate bsr.py's own contract. SR's re-arm behaviour has its own
    integration test in sim/tests/test_ul_access.py."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)
    ul_access = _no_sr(flows)

    buffers.enqueue(1, 2, 1234, 0.0)
    bsr.on_arrivals({(1, 2): 1234}, buffers)  # legitimate regular trigger
    for _ in range(10):
        bsr.broadcast(buffers, ul_access)
    # Never granted, SR never engaged -> stays at 0.
    assert buffers.state(1, 2).bytes_reported == 0


def test_crumb_collapse_not_defeated_by_sr():
    """SR only ever reports once its own state machine has fired
    (sim/ul_access.py) -- a nonzero-but-B-capped estimate (genuine crumb
    collapse) must still gate to a small/zero bytes_reported when SR was
    never engaged, not bypass to the true backlog."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 50_000, 0.0)
    buffers.drain(1, 2, 10_000)  # partial: 40_000 left, LCG still active
    _force_pending(bsr, 1)
    bsr.on_ul_grant(ue_id=1, tb_size=10_000, delivered_bytes=10_000, slot_index=0, buffers=buffers)
    st = bsr._state[1]
    assert st.estimated_ul_buffer_per_lcg[0] > 0

    # Simulate the gNB having already granted more than the BSR reported,
    # without a new BSR arriving (sched_ul_bytes >= estimated_ul_buffer).
    st.sched_ul_bytes = st.estimated_ul_buffer
    bsr.broadcast(buffers, _no_sr(flows))
    assert buffers.state(1, 2).bytes_reported == 0
    # The frozen per-LCG estimate itself is untouched by the gate.
    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == st.estimated_ul_buffer_per_lcg[0]


# --- Event-triggering (commit 2) --------------------------------------------


def test_regular_trigger_fires_on_previously_empty_lcg():
    """An arrival on an LCG that had zero backlog sets `pending` -- the
    regular-BSR trigger (TS 38.321 §5.4.5 condition (ii), condensed to LCG
    granularity)."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    buffers.enqueue(1, 2, 100, 0.0)
    assert bsr._state[1].pending is False  # on_arrivals not called yet
    bsr.on_arrivals({(1, 2): 100}, buffers)
    assert bsr._state[1].pending is True


def test_no_regular_trigger_without_an_arrival():
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S)

    bsr.on_arrivals({}, buffers)
    assert bsr._state[1].pending is False


def test_periodic_timer_fires_pending_after_deadline():
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    # periodicBSR = 5 ms = 10 slots at _SLOT_S; retxBSR set huge so it
    # cannot be the one that fires here.
    bsr = BsrModel(flows, _SLOT_S, periodic_bsr_ms=5.0, retx_bsr_ms=100_000.0)

    for slot in range(9):
        bsr.tick_timers(slot)
        assert bsr._state[1].pending is False, slot
    bsr.tick_timers(10)
    assert bsr._state[1].pending is True


def test_retx_timer_restarts_on_every_grant_suppressing_recovery():
    """The ground truth's own note: retxBSR restarts on every received
    grant, so a min_rb crumb trickle suppresses the one non-regular,
    non-periodic recovery path. Simulate a trickle of grants (no arrivals,
    so no regular trigger) shorter than the retx window and confirm
    `pending` never flips from the retx timer while the trickle continues,
    then confirm it DOES fire once grants stop for longer than the window."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    # retxBSR = 80 ms = 160 slots; periodic set huge so only retx is live.
    bsr = BsrModel(flows, _SLOT_S, periodic_bsr_ms=100_000.0, retx_bsr_ms=80.0)
    buffers.enqueue(1, 2, 1_000_000, 0.0)

    for slot in range(0, 400, 50):  # grants every 50 slots, well under 160
        bsr.tick_timers(slot)
        assert bsr._state[1].pending is False, slot
        bsr.on_ul_grant(ue_id=1, tb_size=10, delivered_bytes=10, slot_index=slot, buffers=buffers)

    # Grants stop; the retx window (160 slots) elapses with no more grants.
    last_grant_slot = 350
    bsr.tick_timers(last_grant_slot + 160)
    assert bsr._state[1].pending is True


def test_crumb_fraction_emerges_from_fast_grants_slow_bsr():
    """End-to-end sanity check of the mechanism the charter names: a UE
    granted every slot but only BSR-triggered once collapses to
    bytes_reported == 0 (a min_rb-crumb-forcing signal from B hitting 0)
    well before the next report is due, purely from sched_ul_bytes
    outracing the one stale estimate -- no new arrivals needed to produce
    the collapse."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows, _SLOT_S, periodic_bsr_ms=100_000.0, retx_bsr_ms=100_000.0)

    buffers.enqueue(1, 2, 100_000, 0.0)
    bsr.on_arrivals({(1, 2): 100_000}, buffers)  # one regular trigger, then none
    bsr.on_ul_grant(ue_id=1, tb_size=2000, delivered_bytes=2000, slot_index=0, buffers=buffers)
    assert bsr._state[1].estimated_ul_buffer > 0

    ul_access = _no_sr(flows)
    saw_collapse = False
    for slot in range(1, 100):
        bsr.broadcast(buffers, ul_access)
        if buffers.state(1, 2).bytes_reported == 0:
            saw_collapse = True
        # Not pending (no arrivals, timers far off): sched_ul_bytes just
        # keeps accumulating grant after grant with no reset.
        bsr.on_ul_grant(ue_id=1, tb_size=2000, delivered_bytes=0, slot_index=slot, buffers=buffers)
    assert saw_collapse
    assert bsr._state[1].pending is False  # collapsed without any new trigger
