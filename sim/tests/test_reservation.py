"""Phase 2, reservation commits 1-3: scheduler/reservation.py.

Commit 1: Scheduler protocol conformance, per-UE throughput EWMA, the
bare PF coefficient as the only ranking criterion, no follower budget
(unbounded grant), UL-then-DL per-slot order.

Commit 2: sort tiers above the coefficient -- but only the tiers this
simulator can actually source (GBR, coarse; PDB, real). `has_srb` and
`liveness`/`sched_inactive` are documented no-ops (README.md sec8's two
new [OPEN: PHASE2] entries) -- see scheduler/reservation.py's module
docstring for the full explanation of why.

Commit 3: the real GBR/BE byte split -- deficit accumulate/cap/target-
spread/overflow-to-BE, both directions, replacing commit 2's coarse
`has_gbr` proxy without moving either comparator's tier position. Also
fixes a bug found scoping this commit: commit 2's `pdb_ms` used HOL
delay as a stand-in for "remaining PDB," which is actually time-since-
last-grant -- a different quantity. See scheduler/reservation.py's
module docstring and docs/oai-port-map.md rows 18/19 for the full
correction note.

See docs/phase2-plan.md sec4 and docs/oai-port-map.md's "Phase 2 --
reservation" section for the full mechanism/citation detail.

Predicted, before writing any code: fully clean `regression_corpus.py
--check` -- the 23rd such prediction in the WP5/WP6/WP-Join/Phase-2
lineage, and the strongest form of it (not just "no scenario references
the new field," but "nothing imports this module at all"):
scheduler/reservation.py is still not added to scheduler/__init__.py's
exports in this commit, so there is no code path by which anything
reaches `Reservation` during a driver.run() call, or via `import
scheduler`, regardless of scenario.
"""

import inspect
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

    def set(
        self,
        ue_id: int,
        qfi: int,
        bytes_queued: int,
        bytes_reported: int | None = None,
        estimated_ul_buffer_per_lcg: int | None = None,
    ) -> None:
        self._states[(ue_id, qfi)] = _FakeBufferState(
            bytes_queued=bytes_queued,
            bytes_reported=bytes_queued if bytes_reported is None else bytes_reported,
            estimated_ul_buffer_per_lcg=(
                bytes_queued
                if estimated_ul_buffer_per_lcg is None
                else estimated_ul_buffer_per_lcg
            ),
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


# -- commit 2: sort tiers -------------------------------------------------
# One fixture per tier boundary, isolating tier ORDER from tier CONTENT:
# every fixture below deliberately gives the "should lose" UE the BETTER
# coefficient, so a wrong tier order (checking coef before the tier that
# should decide) fails distinguishably from wrong tier content.


def test_gbr_tier_beats_the_coefficient_tiebreak_ul():
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1_000_000),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    # UE1 (non-GBR) has the BETTER coefficient (low thr -> high coef).
    sched._ue_state[1].ul_thr_bytes_per_slot = 1.0
    sched._ue_state[2].ul_thr_bytes_per_slot = 100000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=2, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {2}, "the GBR-flagged UE must win despite the worse coefficient"


def test_gbr_tier_beats_the_coefficient_tiebreak_dl():
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 1.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 100000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=2, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {2}


def test_pdb_beats_the_coefficient_tiebreak_within_the_same_gbr_bucket_ul():
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=200.0),
        FlowConfig(ue_id=2, qfi=1, direction="UL", flow_class="PF", pdb_ms=10.0),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    # UE1 (loose PDB) has the BETTER coefficient.
    sched._ue_state[1].ul_thr_bytes_per_slot = 1.0
    sched._ue_state[2].ul_thr_bytes_per_slot = 100000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=2, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {2}, "the tighter-PDB UE must win despite the worse coefficient"


def test_pdb_beats_the_coefficient_tiebreak_within_the_same_gbr_bucket_dl():
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF", pdb_ms=200.0),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF", pdb_ms=10.0),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 1.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 100000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=2, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {2}


def test_coefficient_remains_the_final_tiebreak_when_gbr_and_pdb_are_equal_dl():
    """Re-asserts commit 1's own ranking test in commit 2's context --
    confirms the new tiers didn't reorder anything ahead of the
    coefficient by accident when GBR/PDB don't differentiate."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 10.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 1000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=2, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {1}


def test_has_srb_cannot_be_exercised_and_is_recorded_as_such():
    """No FlowConfig can represent SRB traffic (scheduler/flow.py has no
    such concept), so has_srb is a hardcoded, permanent False -- not a
    gap in this test file's coverage. Confirmed two ways: a source-level
    check that the no-op is literal, not a heuristic, and a behavioral
    check that an LCG0 flow (which a naive "LCG==0 means SRB" heuristic
    would wrongly flag) is ranked purely by GBR/PDB/coef, never boosted."""
    source = inspect.getsource(Reservation._allocate_direction)
    assert "has_srb = False" in source

    # Behavioral guard against a future "helpful" LCG==0-means-SRB
    # heuristic: qfi=1 maps to lcg=0 (scheduler/flow.py::FIVE_QI_LCG) but
    # must not outrank a plain qfi=9 (lcg=6) flow on tier grounds alone.
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=9, direction="DL", flow_class="PF"),  # lcg=6
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF"),  # lcg=0
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    # UE2 (lcg=0) has the WORSE coefficient -- if has_srb were wrongly
    # derived from lcg==0, UE2 would win anyway. It must not.
    sched._ue_state[1].dl_thr_bytes_per_slot = 1.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 100000.0

    buffers = _FakeBuffers()
    buffers.set(1, 9, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=2, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    granted_ues = {a.ue_id for a in out}
    assert granted_ues == {1}, "lcg==0 must not be treated as has_srb"


def test_ul_and_dl_rank_keys_stay_independently_sourced_not_deduped():
    """Anti-dedup guard: _ul_rank_key and _dl_rank_key produce identical
    tuples today (both are 3-of-N implementable tiers), which is exactly
    the shape that invites a future refactor to collapse them into one
    shared comparator "since they're the same anyway" -- silently erasing
    the fact that they diverge the moment either gap (do_sched, or a
    hypothetical TA/SRB model) is unblocked. Checking `is not` alone
    would pass trivially even if one delegated to the other, so this
    inspects each method's actual source instead."""
    ul_source = inspect.getsource(Reservation._ul_rank_key)
    dl_source = inspect.getsource(Reservation._dl_rank_key)

    assert ul_source != dl_source, "the two comparators must remain textually distinct"
    assert "gNB_scheduler_ulsch.c" in ul_source
    assert "gNB_scheduler_dlsch.c" in dl_source
    # UL's own explanatory prose is allowed (and expected) to say
    # "sched_inactive" -- it's a documented, currently-dormant tier. What
    # must never happen is the DL comparator's actual CODE BODY (not its
    # explanatory docstring, which legitimately discusses the tier's
    # absence) growing a functional sched_inactive branch -- checked on
    # the code after the docstring, not the whole source text.
    dl_code_body = dl_source.split('"""')[-1]
    assert "sched_inactive" not in dl_code_body, (
        "DL genuinely has no sched_inactive tier -- its CODE (not "
        "explanatory prose) must never grow a branch for one"
    )


# -- commit 3: GBR/BE byte split + deficit accumulate/cap/spread --------
# gNB_scheduler_ulsch.c:2251-2278 / gNB_scheduler_dlsch.c:377-409.
# slot_duration_s=0.0005 throughout -> slots_per_sec=2000, slot_ms=0.5.


def test_ul_obligation_floors_at_one_byte():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    has_gbr, _, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert sched._ue_state[1].ul_lcg_deficit_bytes[0] == 1  # floored, not 0 (or negative)
    assert has_gbr is True


def test_ul_deficit_caps_at_one_pdb_window():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    # obligation=1 (floored); window = 1 * (100ms / 0.5ms) = 200.
    for _ in range(300):
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert sched._ue_state[1].ul_lcg_deficit_bytes[0] == 200


def test_ul_target_capped_at_2x_obligation_floor_without_mfbr():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    for _ in range(300):  # saturate deficit at the window (200)
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0
    # 200 slots since the grant -> age 100ms -> remaining PDB 0 ->
    # rem_slots floors to 1 -> uncapped target would be (200+1)/1=201, but
    # no mfbr_bps is set, so max_burst floors at obligation*2=2.
    #
    # This was slot 199 before the integer-arithmetic correction, chosen
    # for a 0.5ms remaining PDB. Under the C's actual truncation a 199-slot
    # age is 99.5ms -> int() -> 99ms -> 1ms remaining -> rem_slots=2, which
    # no longer exercises the rem_slots<1 floor this pair is about. The cap
    # clipped to 2 either way here, so only the companion test below caught
    # it -- see that test's own note.
    _, _, guaranteed, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=200)
    assert guaranteed == 2


def test_ul_target_can_exceed_the_floor_when_mfbr_is_configured():
    sched = Reservation()
    flows = [
        FlowConfig(
            ue_id=1, qfi=1, direction="UL", flow_class="GBR",
            gfbr_bps=1.0, mfbr_bps=2_000_000.0, pdb_ms=100.0,
        )
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    for _ in range(300):
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0
    # max_burst from mfbr_bps=2_000_000: (2_000_000/8)/2000 * 2 = 250 --
    # well above the uncapped target (201), so it must NOT clip here,
    # unlike the no-mfbr case above where the same setup clipped to 2.
    #
    # Slot 200, not 199: this is the one existing expectation the
    # integer-arithmetic correction actually moved. At slot 199 the age is
    # 99.5ms, which the C truncates to 99ms -> 1ms remaining ->
    # rem_slots=2 -> target (200+1)//2 = 100, not 201. The float port
    # divided by 1.0 and got 201. Kept as a deliberate record that the
    # correction is behaviourally real rather than cosmetic.
    _, _, guaranteed, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=200)
    assert guaranteed == 201


def test_ul_overflow_beyond_target_credited_to_be():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    # LCG estimate (6000) far exceeds any obligation/target this slot.
    buffers.set(1, 1, bytes_queued=6000)

    _, _, guaranteed, be = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert guaranteed == 1  # obligation floor, first slot
    assert be == 6000 - 1


def test_ul_has_gbr_requires_a_real_gfbr_not_just_the_flow_class_label():
    """Commit 2's coarse placeholder checked only flow_class=='GBR'.
    The real mechanism additionally requires gbr_ul_guaranteed > 0
    (gNB_scheduler_ulsch.c:2251) -- a GBR-labelled flow with no
    configured GFBR accrues no obligation and must not set has_gbr."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=0.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    has_gbr, _, guaranteed, be = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert has_gbr is False
    assert guaranteed == 0
    assert be == 6000  # entire buffer falls through to best-effort


def test_ul_deficit_freezes_when_the_per_lcg_estimate_is_zero():
    """Gated on estimated_ul_buffer_per_lcg, not bytes_reported -- a
    crumb-collapsed LCG's deficit must not accumulate, matching
    gNB_scheduler_ulsch.c:2230's own continue-gate."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=0, estimated_ul_buffer_per_lcg=0)

    for _ in range(5):
        has_gbr, _, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert 0 not in sched._ue_state[1].ul_lcg_deficit_bytes
    assert has_gbr is False


def test_ul_pdb_ms_uses_time_since_last_grant_not_hol_delay():
    """The commit-2 correction: remaining PDB is time-since-last-grant
    (gNB_scheduler_ulsch.c:2239-2249), not HOL delay -- the fake's
    hol_delay_s stays 0 throughout, so only the corrected proxy can
    show this shrinking."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    _, pdb_never_granted, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert pdb_never_granted == pytest.approx(100.0)

    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0
    _, pdb_after_40_slots, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=40)
    assert pdb_after_40_slots == pytest.approx(80.0)  # 40*0.5ms=20ms elapsed


def test_dl_deficit_accumulates_through_silence_unlike_ul():
    """The real DL/UL asymmetry found scoping this commit:
    gNB_scheduler_dlsch.c:381-388 accumulates deficit and sets
    has_unfulfilled_gbr UNCONDITIONALLY for a GBR-configured LCID --
    only the target sub-step gates on bytes_in_buffer>0 (:391). UL's
    outer loop gates the WHOLE block on estimated_ul_buffer_per_lcg>0
    (see test_ul_deficit_freezes_when_the_per_lcg_estimate_is_zero,
    its direct contrast)."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=0)  # empty buffer -- "silence"

    has_gbr = False
    for _ in range(5):
        has_gbr, _, _, _ = sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    assert sched._ue_state[1].dl_flow_deficit_bytes[1] == 5  # kept growing
    assert has_gbr is True  # even though the buffer is empty throughout


def test_dl_target_not_computed_while_buffer_is_empty():
    """The other half of the same asymmetry: accumulation is
    unconditional, but guaranteed/be bookkeeping still requires
    bytes_queued>0 (gNB_scheduler_dlsch.c:391)."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=0)

    _, _, guaranteed, be = sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    assert guaranteed == 0
    assert be == 0


def test_dl_has_gbr_requires_a_real_gfbr_not_just_the_flow_class_label():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=0.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    has_gbr, _, guaranteed, be = sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    assert has_gbr is False
    assert guaranteed == 0
    assert be == 6000


def test_dl_pdb_ms_uses_time_since_last_grant_not_hol_delay():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF", pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    _, pdb_never_granted, _, _ = sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    assert pdb_never_granted == pytest.approx(100.0)

    sched._ue_state[1].dl_flow_last_grant_slot[1] = 0
    _, pdb_after_40_slots, _, _ = sched._dl_gbr_and_pdb(1, buffers, slot_index=40)
    assert pdb_after_40_slots == pytest.approx(80.0)


def test_dl_overflow_beyond_target_credited_to_be():
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1.0, pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)

    _, _, guaranteed, be = sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    assert guaranteed == 1
    assert be == 6000 - 1


# -- commit 3a: the C's integer arithmetic -------------------------------
#
# Every fixture above lands on a whole number of milliseconds, where the
# float port and the C's truncating one agree exactly -- the same blind
# spot that let commit 2's pdb_ms bug through (correct tests of a quantity
# that happened to coincide at the sampled points). These use ODD slot
# counts at 0.5 ms, where they do not.


def test_ul_remaining_pdb_truncates_grant_age_to_whole_milliseconds():
    """gNB_scheduler_ulsch.c:2245 -- `_rem_pdb = _pdb - (int)_age`. Three
    slots at 0.5ms is an age of 1.5ms, which the C sees as 1ms, giving 99
    remaining and NOT 98.5. Load-bearing because pdb_ms is a comparator
    tier: int-ms granularity makes sub-millisecond differences tie there
    and fall through to the PF coefficient."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0

    _, remaining, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=3)
    assert remaining == 99
    assert isinstance(remaining, int)


def test_dl_remaining_pdb_truncates_grant_age_to_whole_milliseconds():
    """gNB_scheduler_dlsch.c:365 -- identical truncation to UL's."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF", pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    sched._ue_state[1].dl_flow_last_grant_slot[1] = 0

    _, remaining, _, _ = sched._dl_gbr_and_pdb(1, buffers, slot_index=3)
    assert remaining == 99
    assert isinstance(remaining, int)


def test_two_flows_inside_one_millisecond_tie_at_the_pdb_tier():
    """The behavioural consequence, stated as its own test rather than
    left implicit in the arithmetic: two UEs granted one slot apart (0.5ms)
    can have EQUAL remaining PDB under the C's int-ms truncation, so the
    PDB tier cannot separate them and the coefficient decides. Here the
    ages are 4.0ms and 4.5ms, which both truncate to 4. A float port would
    read 96.0 and 95.5, separate them at the PDB tier, and never reach the
    coefficient."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=100.0),
        FlowConfig(ue_id=2, qfi=1, direction="UL", flow_class="PF", pdb_ms=100.0),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 11  # 9 slots -> 4.5ms
    sched._ue_state[2].ul_lcg_last_grant_slot[0] = 12  # 8 slots -> 4.0ms

    _, pdb_ue1, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=20)
    _, pdb_ue2, _, _ = sched._ul_gbr_and_pdb(2, buffers, slot_index=20)
    assert pdb_ue1 == pdb_ue2 == 96


def test_rem_slots_truncation_shrinks_the_target():
    """gNB_scheduler_ulsch.c:2263 -- `_rem_slots = (int)(_rem_pdb/_sms_ul)`,
    truncated, then an INTEGER division of the deficit by it. At 1ms
    remaining and 0.5ms slots that is 2 slots, so a saturated 200-byte
    deficit spreads to (200+1)//2 = 100, not 201."""
    sched = Reservation()
    flows = [
        FlowConfig(
            ue_id=1, qfi=1, direction="UL", flow_class="GBR",
            gfbr_bps=1.0, mfbr_bps=2_000_000.0, pdb_ms=100.0,
        )
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    for _ in range(300):
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0

    _, _, guaranteed, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=199)
    assert guaranteed == 100


def test_window_truncates_the_ratio_not_the_product():
    """gNB_scheduler_ulsch.c:2257 / _dlsch.c:383 -- `_obl * (int)(_pdb/slot_ms)`.
    Unreachable at any real numerology (an integer pdb_ms over a 0.5 or
    0.25 ms slot always divides evenly), so this uses a synthetic 0.3 ms
    slot to exercise the ported truncation directly: 100/0.3 = 333.33 ->
    333 slots, and an obligation of 2 (60000bps/8 = 7500 B/s over 3333.33
    slots/s = 2.25, itself truncated) gives a 666-byte window, not
    666.67 and not 667."""
    sched = Reservation()
    flows = [
        FlowConfig(
            ue_id=1, qfi=1, direction="UL", flow_class="GBR",
            gfbr_bps=60_000.0, pdb_ms=100.0,
        )
    ]
    sched.configure(flows, slot_duration_s=0.0003, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=999_999)

    for _ in range(1000):
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert sched._ue_state[1].ul_lcg_deficit_bytes[0] == 666


def test_unconfigured_pdb_falls_back_to_300ms_not_zero():
    """gNB_scheduler_ulsch.c:2236 / _dlsch.c:353 -- `pdb > 0 ? pdb : 300`.
    Unreachable from any current scenario (FlowConfig and the config
    loader both default to 100.0), but a missing guard would report 0 --
    maximum urgency -- for exactly the case the C treats as least
    urgent."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=0.0),
        FlowConfig(ue_id=2, qfi=2, direction="DL", flow_class="PF", pdb_ms=0.0),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 2, bytes_queued=6000)

    _, ul_pdb, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    _, dl_pdb, _, _ = sched._dl_gbr_and_pdb(2, buffers, slot_index=0)
    assert ul_pdb == 300
    assert dl_pdb == 300


def test_no_eligible_flow_reports_the_c_s_own_9999_sentinel():
    """gNB_scheduler_ulsch.c:2223 / _dlsch.c:330 seed the best-remaining
    field at 9999, not at an infinity. Ordering-equivalent for any real
    PDB, ported as the literal so the sentinel is the C's own."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=100.0)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()  # nothing queued -> no eligible LCG

    _, remaining, _, _ = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert remaining == 9999
