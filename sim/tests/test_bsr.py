"""Tests for sim/bsr.py (WP3, commit 1: quantisation + per-LCG structure,
no event-triggering yet -- a BSR is assembled on every UL grant)."""

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
from scheduler.flow import FlowConfig

_OAI_SOURCE = Path(__file__).resolve().parents[2] / "oai-branches" / "two-tier" / "nr_mac_common.c"


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


def _flow(ue_id, qfi, lcg):
    return FlowConfig(ue_id=ue_id, qfi=qfi, direction="UL", lcg=lcg)


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


def test_short_bsr_used_and_other_lcgs_zeroed_when_one_lcg_active():
    """When exactly one LCG has real backlog, the assembled BSR is short
    format: that LCG's estimate is set, every other LCG's slot reads 0 --
    the aliasing mechanic (gNB_scheduler_ulsch.c:631-632)."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    buffers.register(1, 9, is_ul=True, lcg=1)
    flows = [_flow(1, 2, 0), _flow(1, 9, 1)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 0, 0.0)      # LCG 0: no data
    buffers.enqueue(1, 9, 2000, 0.0)   # LCG 1: only active LCG

    bsr.on_ul_grant(ue_id=1, tb_size=0, delivered_bytes=0, buffers=buffers)
    bsr.broadcast(buffers)  # BsrModel's internal state -> BufferState

    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == 0
    assert buffers.state(1, 9).estimated_ul_buffer_per_lcg == quantise_short(2000)


def test_long_bsr_used_when_multiple_lcgs_active():
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    buffers.register(1, 9, is_ul=True, lcg=1)
    flows = [_flow(1, 2, 0), _flow(1, 9, 1)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 500, 0.0)
    buffers.enqueue(1, 9, 2000, 0.0)

    bsr.on_ul_grant(ue_id=1, tb_size=0, delivered_bytes=0, buffers=buffers)
    bsr.broadcast(buffers)

    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == quantise_long(500)
    assert buffers.state(1, 9).estimated_ul_buffer_per_lcg == quantise_long(2000)


def test_per_lcg_estimate_frozen_between_grants_not_drained():
    """estimated_ul_buffer_per_lcg is never written back after a grant --
    only reset-then-repopulated on the next BSR. README §7 finding (a):
    port the frozen behaviour faithfully, do not drain it."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 1000, 0.0)
    bsr.on_ul_grant(ue_id=1, tb_size=1000, delivered_bytes=1000, buffers=buffers)
    bsr.broadcast(buffers)
    reported_after_first_bsr = buffers.state(1, 2).estimated_ul_buffer_per_lcg
    assert reported_after_first_bsr == quantise_short(1000)

    # No new grant: broadcast() alone must not change the frozen estimate,
    # even though the true backlog is now 0 (fully drained).
    for _ in range(5):
        bsr.broadcast(buffers)
    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == reported_after_first_bsr


def test_sched_ul_bytes_resets_to_zero_on_every_bsr():
    """Both BSR formats reset sched_ul_bytes = 0 unconditionally on
    reception (gNB_scheduler_ulsch.c:630, 651), regardless of how much was
    granted since the last one."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 5000, 0.0)
    bsr.on_ul_grant(ue_id=1, tb_size=200, delivered_bytes=200, buffers=buffers)
    assert bsr._state[1].sched_ul_bytes == 0


def test_rides_on_a_grant_no_change_without_one():
    """A flow with real data but no UL grant this run never gets a BSR
    assembled -- on_ul_grant is only called for actual grants. broadcast()
    alone (the cold-start/re-arm probe) is the only thing keeping it from
    a permanent 0, and it reports the true backlog directly, not a
    quantised estimate, until a real grant lands."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 1234, 0.0)
    for _ in range(10):
        bsr.broadcast(buffers)
    # Never granted -> still the true-backlog probe, not a quantised value.
    assert buffers.state(1, 2).bytes_reported == 1234


def test_cold_start_probe_rearms_after_a_flow_drains_to_empty():
    """The probe is not one-shot: once a flow's per-LCG estimate reads 0
    (whether from a genuine empty-backlog BSR or because it was never
    reported), a fresh arrival must be visible again via the probe, not
    stuck at the frozen 0 -- otherwise any bursty UL flow deadlocks after
    its first empty buffer (see README §8's WP3 finding)."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 500, 0.0)
    buffers.drain(1, 2, 500)
    bsr.on_ul_grant(ue_id=1, tb_size=500, delivered_bytes=500, buffers=buffers)
    bsr.broadcast(buffers)
    assert buffers.state(1, 2).bytes_reported == 0

    # New data arrives with no further grant -- must become visible again.
    buffers.enqueue(1, 2, 300, 0.001)
    bsr.broadcast(buffers)
    assert buffers.state(1, 2).bytes_reported == 300


def test_crumb_collapse_not_defeated_by_the_probe():
    """The probe only fires when the per-LCG estimate is exactly 0 (no
    evidence at all). A nonzero-but-B-capped estimate (genuine crumb
    collapse) must still gate to a small/zero bytes_reported, not bypass
    to the true backlog."""
    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True, lcg=0)
    flows = [_flow(1, 2, 0)]
    bsr = BsrModel(flows)

    buffers.enqueue(1, 2, 50_000, 0.0)
    buffers.drain(1, 2, 10_000)  # partial: 40_000 left, LCG still active
    bsr.on_ul_grant(ue_id=1, tb_size=10_000, delivered_bytes=10_000, buffers=buffers)
    st = bsr._state[1]
    assert st.estimated_ul_buffer_per_lcg[0] > 0

    # Simulate the gNB having already granted more than the BSR reported,
    # without a new BSR arriving (sched_ul_bytes >= estimated_ul_buffer).
    st.sched_ul_bytes = st.estimated_ul_buffer
    bsr.broadcast(buffers)
    assert buffers.state(1, 2).bytes_reported == 0
    # The frozen per-LCG estimate itself is untouched by the gate.
    assert buffers.state(1, 2).estimated_ul_buffer_per_lcg == st.estimated_ul_buffer_per_lcg[0]
