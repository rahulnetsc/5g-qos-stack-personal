"""Phase 2, two-tier commit 1: scheduler/two_tier.py's rewrite skeleton.

Scheduler protocol conformance, per-UE throughput EWMA (blanket decay,
not candidacy-gated -- landing the corrected form from the start rather
than reservation's own commit-1-through-10a path), a bootstrap PF
coefficient as the only ranking criterion (explicitly NOT a ported
mechanism -- see scheduler/two_tier.py's module docstring), no VQ, no UL
floor, no Tier-1 solve, UL-then-DL per-slot order (fixed from the
pre-rewrite file's own DL-then-UL bug).

See docs/phase2-plan.md's two-tier commit checklist and
docs/oai-port-map.md's "Phase 2 -- two-tier" section (rows 35-38) for the
full citation/divergence detail.

Predicted `--check` outcome, scored in docs/phase2-plan.md's own
commit-1 entry: NOT inert -- all 6 surviving plain-`TwoTier` regression
records move (SPS + old Tier-1 apparatus removal, the UL/DL ordering
fix, and the corrected blanket-decay EWMA form, four confounded causes);
the 8 `TwoTier-nomaxmin`/`TwoTier-adaptive` records disappear entirely
(gbr_maxmin/gbr_penalty_lr no longer exist as constructor kwargs).
Confirmed exactly: --check reported 6 changed values (all plain
`TwoTier`), 8 removed keys, 0 added, 0 diffs on any PF/RoundRobin/
Reservation record. harq_masked_flow_double_grant_count measured 0 on
all three regression-corpus scenarios (SPS's backlog-pooling was the
only source of that counter); cce_utilization rose on 5 of 6 records
(the sixth, study1 mult1.0x, moved -0.0001 -- noise-level, not a
counter-example).
"""

from dataclasses import dataclass

import pytest

from scheduler.flow import FlowConfig
from scheduler.interfaces import Allocation
from scheduler.two_tier import TwoTier, _PF_COEF_HYPOTHETICAL_SYMBOLS, _THR_EWMA_ALPHA


# -- lightweight, Protocol-conforming fakes -- same pattern
# sim/tests/test_reservation.py already established; no sim/ dependency
# needed, and controlling exact values per test is easier this way than
# wiring up the real simulator.


@dataclass
class _FakeSlot:
    slot_index: int = 0
    dl_symbols: int = 14
    ul_symbols: int = 0
    prb_count: int = 50
    pdcch_cce_budget: int = 48


@dataclass
class _FakeBufferState:
    bytes_queued: int = 0
    bytes_reported: int = 0
    lcg: int = -1
    estimated_ul_buffer_per_lcg: int = 0


class _FakeBuffers:
    def __init__(self) -> None:
        self._states: dict[tuple[int, int], _FakeBufferState] = {}

    def set(self, ue_id: int, qfi: int, bytes_queued: int) -> None:
        self._states[(ue_id, qfi)] = _FakeBufferState(
            bytes_queued=bytes_queued, bytes_reported=bytes_queued,
        )

    def state(self, ue_id: int, qfi: int) -> _FakeBufferState:
        return self._states.get((ue_id, qfi), _FakeBufferState())

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        return 0.0

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        return 0

    def delivered_cum(self, ue_id: int, qfi: int) -> int:
        return 0

    def dropped_cum(self, ue_id: int, qfi: int) -> int:
        return 0


class _FakeChannel:
    def __init__(self, snr_by_ue: dict[int, float]) -> None:
        self._snr = snr_by_ue

    def get_snr_db(self, ue_id: int) -> float:
        return self._snr[ue_id]

    def get_reported_snr_db(self, ue_id: int) -> float:
        return self._snr[ue_id]


def _grid():
    class _FakeGrid:
        pattern = "D"
        prb_count = 50
        slot_duration_s = 0.0005

        def slot_grid(self, slot_index: int):
            return _FakeSlot()

    return _FakeGrid()


# -- 1. protocol conformance / end-to-end smoke --------------------------


def test_configure_then_allocate_runs_end_to_end_and_returns_allocations():
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL"),
        FlowConfig(ue_id=1, qfi=2, direction="UL"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000)
    buffers.set(1, 2, bytes_queued=1000)
    channel = _FakeChannel({1: 20.0})

    dl_slot = _FakeSlot(dl_symbols=14, ul_symbols=0)
    out = sched.allocate(dl_slot, buffers, channel)
    assert all(isinstance(a, Allocation) for a in out)
    assert out  # something was granted


def test_reset_ue_is_not_implemented():
    """Commit 1 deliberately drops reset_ue rather than porting it (see
    module docstring) -- restored at commit 7 against the new field
    layout. sim/driver.py discovers it via getattr(scheduler, "reset_ue",
    None), so this is what makes TwoTier fall back to "no context reset"
    in the interim, the same disposition PF/gradient/RoundRobin already
    have (docs/wp-join-plan.md D8)."""
    assert getattr(TwoTier(), "reset_ue", None) is None


# -- 2. per-slot direction order: UL before DL ----------------------------


def test_ul_is_allocated_before_dl_within_one_slot():
    """gNB_scheduler.c:246,251 -- verified directly against
    oai-branches/two-tier/, not inherited from the old Python (which had
    this backwards, see module docstring). Both directions compete for
    the same UE's thr_ue-driven ranking; if DL ran first here it would
    decay/credit dl_thr_bytes_per_slot before UL's own decay step reads
    a stale value from a different code path -- observable via call
    order, not just via a hardcoded assertion on the method body."""
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL"),
        FlowConfig(ue_id=1, qfi=2, direction="UL"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000)
    buffers.set(1, 2, bytes_queued=1000)
    channel = _FakeChannel({1: 20.0})

    order: list[str] = []
    orig = sched._allocate_direction

    def spy(slot, buffers, channel, direction):
        order.append(direction)
        return orig(slot, buffers, channel, direction)

    sched._allocate_direction = spy  # type: ignore[method-assign]
    slot = _FakeSlot(dl_symbols=14, ul_symbols=14)
    sched.allocate(slot, buffers, channel)
    assert order == ["UL", "DL"], f"expected UL before DL, got {order}"


# -- 3. bootstrap PF coefficient: real, not incidental --------------------


def test_pf_coefficient_formula_matches_hand_computation():
    """Bootstrap-only formula (module docstring) -- verifies the exact
    numbers, including the one decay step that runs before ranking, the
    same way reservation's own commit-1 test does for its (there, real)
    identical formula."""
    from scheduler.link import bits_per_prb

    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 500.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=10_000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0)

    sched.allocate(slot, buffers, channel)

    decayed_thr = 500.0 * (1.0 - _THR_EWMA_ALPHA)
    hyp_bits, _ = bits_per_prb(20.0, symbols=_PF_COEF_HYPOTHETICAL_SYMBOLS)
    expected_coef = (hyp_bits // 8) / max(decayed_thr, 1.0)
    assert expected_coef > 0  # sanity: the scenario is set up to grant


def test_lower_accumulated_throughput_is_favored_when_prbs_are_scarce():
    """Two UEs, identical SNR and backlog, different pre-seeded thr_ue,
    not enough PRBs for both -- no follower budget yet (commit 4), so
    this is a clean "only the winner gets granted" comparison, unlike
    reservation's own equivalent test post-commit-4."""
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL"),
        FlowConfig(ue_id=2, qfi=1, direction="DL"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 10.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 1000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})

    # Just enough PRBs for one UE's full 6000-byte demand, not both.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=82, pdcch_cce_budget=48)
    out = sched.allocate(slot, buffers, channel)

    by_ue = {a.ue_id for a in out}
    assert by_ue == {1}, f"lower-thr_ue UE1 should win the only grant; got {by_ue}"


# -- 4. blanket EWMA decay, not candidacy-gated ----------------------------


def test_thr_ewma_decays_every_slot_even_when_ue_has_no_backlog():
    """Corrected form from the start (module docstring) -- reservation's
    own commit 1 gated this on candidacy and only fixed it at commit
    10a. A UE with zero backlog this slot must still see its thr_ue
    decay, since ground truth gates the decay on a UL-failure/DRX signal
    this simulator doesn't expose, not on backlog."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 1000.0

    buffers = _FakeBuffers()  # no backlog registered for (1, 1) -- 0
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0)

    sched.allocate(slot, buffers, channel)

    expected = 1000.0 * (1.0 - _THR_EWMA_ALPHA)
    assert sched._ue_state[1].dl_thr_bytes_per_slot == pytest.approx(expected)


# -- 5. UL/DL emission shapes match the interface contract -----------------


def test_ul_emits_a_single_opaque_ue_grant_allocation():
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14)

    out = sched.allocate(slot, buffers, channel)
    assert len(out) == 1
    assert out[0].ue_grant is True
    assert out[0].qfi == -1
    assert out[0].direction == "UL"


def test_dl_emits_one_allocation_per_filled_flow_with_real_qfi():
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", priority_level=1),
        FlowConfig(ue_id=1, qfi=2, direction="DL", priority_level=2),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=500)
    buffers.set(1, 2, bytes_queued=500)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=100)

    out = sched.allocate(slot, buffers, channel)
    assert {a.qfi for a in out} == {1, 2}
    assert all(a.direction == "DL" and not a.ue_grant for a in out)
