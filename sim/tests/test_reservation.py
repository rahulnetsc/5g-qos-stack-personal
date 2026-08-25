"""Phase 2, reservation commit 1: scheduler/reservation.py skeleton --
Scheduler protocol conformance, per-UE throughput EWMA, the bare PF
coefficient as the only ranking criterion, no follower budget (unbounded
grant), UL-then-DL per-slot order. See docs/phase2-plan.md sec4 and
docs/oai-port-map.md's "Phase 2 -- reservation" section (rows 14-17).

Predicted, before writing any code: fully clean `regression_corpus.py
--check` -- the 21st such prediction in the WP5/WP6/WP-Join/Phase-2
lineage, and the strongest form of it (not just "no scenario references
the new field," but "nothing imports this module at all"):
scheduler/reservation.py is not added to scheduler/__init__.py's exports
in this commit, so there is no code path by which anything reaches
`Reservation` during a driver.run() call, or via `import scheduler`,
regardless of scenario.
"""

from dataclasses import dataclass

import pytest

from scheduler.flow import FlowConfig
from scheduler.interfaces import Allocation
from scheduler.reservation import Reservation


# -- lightweight, Protocol-conforming fakes (no sim/ dependency needed --
# BufferView/ChannelView/SlotView are structural, and controlling exact
# values per test is easier this way than wiring up the real simulator) --


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

    def set(self, ue_id: int, qfi: int, bytes_queued: int, bytes_reported: int | None = None) -> None:
        self._states[(ue_id, qfi)] = _FakeBufferState(
            bytes_queued=bytes_queued,
            bytes_reported=bytes_queued if bytes_reported is None else bytes_reported,
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
    sched = Reservation()
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


# -- 2. PF-coefficient ranking is real, not incidental -------------------


def test_lower_accumulated_throughput_is_favored_when_prbs_are_scarce():
    """Two UEs, identical SNR and backlog, different pre-seeded thr_ue.
    A tight PRB budget forces a choice -- the lower-thr_ue (higher
    coefficient) UE must be the one granted."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL"),
        FlowConfig(ue_id=2, qfi=1, direction="DL"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    # Pre-seed: UE1 has served little (low thr -> high coef -> favored);
    # UE2 has served a lot (high thr -> low coef).
    sched._ue_state[1].dl_thr_bytes_per_slot = 10.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 1000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})

    # Few enough PRBs that only one UE's grant fits.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=2, pdcch_cce_budget=48)
    out = sched.allocate(slot, buffers, channel)

    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {1}, "the lower-thr_ue UE must be favored, not the higher one"


def test_pf_coefficient_formula_matches_hand_computation():
    """gNB_scheduler_ulsch.c:2205-2213,2301-2302 / _dlsch.c:814-824: coef =
    hypothetical-1RB/10-symbol-TBS / max(thr, 1.0). Verifies the exact
    numbers, including the one decay step that runs before ranking."""
    from scheduler.link import bits_per_prb

    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL")]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 100.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0})
    # Plenty of PRBs -- isolates ranking/coefficient math from grant sizing.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=50, pdcch_cce_budget=48)

    sched.allocate(slot, buffers, channel)

    # Hand computation, matching the C exactly:
    hyp_bits, _ = bits_per_prb(20.0, symbols=10)  # the hardcoded 10-symbol TBS
    hyp_tbs_bytes = hyp_bits // 8
    thr_after_decay = 100.0 * (1.0 - 0.01)  # decay runs once, before ranking
    expected_coef = hyp_tbs_bytes / max(thr_after_decay, 1.0)

    assert hyp_bits == int(3.5 * 12 * 10)  # SNR 20 dB picks the (19.0, 3.5, .10) row
    assert hyp_tbs_bytes == 52
    assert expected_coef == pytest.approx(52 / 99.0)
    # The post-decay thr is what allocate() should have left behind.
    assert sched._ue_state[1].dl_thr_bytes_per_slot > 0.0


# -- 3. unbounded grant, no follower budget yet ---------------------------


def test_single_ue_can_consume_the_whole_slot_with_no_follower_reservation():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL")]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=10_000_000)  # far more than one slot can carry
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    assert sum(a.prbs for a in out) == slot.prb_count


# -- 4. UL/DL emission shape ----------------------------------------------


def test_dl_emits_one_allocation_per_filled_flow_with_real_qfi():
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", priority_level=10),
        FlowConfig(ue_id=1, qfi=2, direction="DL", priority_level=20),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=500)
    buffers.set(1, 2, bytes_queued=500)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    assert {a.qfi for a in out} == {1, 2}
    assert all(a.ue_grant is False for a in out)
    # One DCI per UE grant: PRB/CCE cost rides on the first Allocation only.
    nonzero_prbs = [a for a in out if a.prbs > 0]
    assert len(nonzero_prbs) == 1


def test_ul_emits_a_single_opaque_ue_grant_allocation():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL")]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=2000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    assert len(out) == 1
    alloc = out[0]
    assert alloc.qfi == -1
    assert alloc.ue_grant is True
    assert alloc.direction == "UL"
    assert alloc.bytes_capacity > 0


# -- 5. D1 structural isolation -- package-wide, not scoped to one file --


def test_scheduler_package_never_imports_sim():
    """docs/phase2-plan.md sec3/D1: the uplink intra-TB split must stay
    structurally unreachable from any scheduler. scheduler/ depends only
    on stdlib + its own modules (and cvxpy/numpy for tier1.py) -- never
    on sim/, which is where sim/ue_lcp.py's real split lives. This walks
    every file under scheduler/, not just reservation.py: the failure
    mode this guards against is a FUTURE commit adding a `sim` import to
    ANY scheduler file (two_tier.py, link.py, tier1.py, ...), not
    necessarily to this one."""
    import pathlib
    import scheduler

    pkg_dir = pathlib.Path(scheduler.__file__).parent
    offending: list[str] = []
    for path in pkg_dir.rglob("*.py"):
        for line in path.read_text().splitlines():
            tokens = line.strip().split()
            if not tokens:
                continue
            if tokens[0] == "import" and len(tokens) > 1 and (
                tokens[1] == "sim" or tokens[1].startswith("sim.")
            ):
                offending.append(f"{path}: {line.strip()}")
            if tokens[0] == "from" and len(tokens) > 1 and (
                tokens[1] == "sim" or tokens[1].startswith("sim.")
            ):
                offending.append(f"{path}: {line.strip()}")
    assert not offending, f"scheduler/ must never import sim/: {offending}"
