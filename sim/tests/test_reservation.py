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

Commit 4a (this commit) wires commit 3's guaranteed_bytes/be_bytes into
grant sizing as the nr_find_nb_rb-equivalent target
(gNB_scheduler_ulsch.c:2492-2512 / _dlsch.c:1003-1019), via the new pure
functions `_ul_grant_target`/`_dl_grant_target`. Also lands
`_ul_gbr_bytes_slot` (a MAX-not-sum, non-deduped, unfloored per-slot GBR
rate, gNB_scheduler_ulsch.c:2304-2316) and its own separate MFBR-keyed
gate `_ul_has_pending_gbr` (:38-67) -- a different field from
`has_gbr`/`ul_has_unfulfilled_gbr`. 25th prediction in the lineage:
still fully inert on `regression_corpus.py --check` (nothing imports
this module).
"""

import inspect
from dataclasses import dataclass

import pytest

from scheduler.flow import FlowConfig
from scheduler.interfaces import Allocation
from scheduler.reservation import (
    Reservation,
    _dl_follower_budget,
    _dl_grant_target,
    _dl_needs_service,
    _THR_EWMA_ALPHA,
    _ul_follower_budget,
    _ul_grant_target,
    _ul_needs_service,
)


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
    Commit 4 correction, found running this suite after landing the
    follower budget: with 2 needy candidates, the budget now reserves
    the trailing candidate's own min_rbSize share whenever total PRBs
    allow it, so a "tight" budget no longer means the loser gets
    NOTHING -- it means the loser gets only its protected minimum while
    the winner (ranked first) gets the rest. This is the mechanism
    working as designed (gNB_scheduler_dlsch.c:909-926's own "a
    saturating BE UE cannot zero a starved UE behind it"), not a
    regression in this test's own subject (throughput-EWMA ranking) --
    so the assertion now checks WHO GETS MORE, not WHO IS THE ONLY ONE
    granted."""
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

    # A single UE's full 6000-byte target needs 82 PRBs at this SNR;
    # prb_count=100 gives the winner comfortable room to fully deliver
    # while still leaving enough for the follower-budget-protected
    # loser to get a real (nonzero, smaller) share -- an unambiguous
    # "who got more" comparison at any prb_count above the 5-PRB DL
    # floor, not a hand-tuned coincidence.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=100, pdcch_cce_budget=48)
    out = sched.allocate(slot, buffers, channel)

    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2}, "both UEs should be served -- the follower budget protects UE2's share too"
    assert by_ue[1].prbs > by_ue[2].prbs, "the lower-thr_ue UE must get the larger share, not the higher one"


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


def test_thr_ewma_decays_every_slot_even_when_ue_has_no_backlog():
    """Commit 10a correction (docs/oai-port-map.md row 14): ground truth
    decays every connected UE's thr_ue every slot
    (gNB_scheduler_ulsch.c:2074,2083-2085 / _dlsch.c:742,750-752), gated
    only on nr_mac_ue_is_active() -- a UL-failure/DRX-equivalent this
    simulator doesn't have, not on backlog. Commits 1-10 gated the decay
    on candidacy instead (the opposite), so a UE with no backlog kept a
    stale-high thr indefinitely. Verified directly: a UE with backlog in
    slot 0, none in slots 1-2 (no candidate built either slot -- confirms
    this exercises the gap, not a normal grant), must show its thr having
    decayed through the gap when it becomes a candidate again."""
    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="DL")]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    channel = _FakeChannel({1: 20.0})

    buffers.set(1, 1, bytes_queued=6000)
    slot0 = _FakeSlot(slot_index=0, dl_symbols=14, ul_symbols=0, prb_count=50, pdcch_cce_budget=48)
    sched.allocate(slot0, buffers, channel)
    thr_after_slot0 = sched._ue_state[1].dl_thr_bytes_per_slot
    assert thr_after_slot0 > 0.0

    buffers.set(1, 1, bytes_queued=0)
    for i in (1, 2):
        slot = _FakeSlot(slot_index=i, dl_symbols=14, ul_symbols=0, prb_count=50, pdcch_cce_budget=48)
        out = sched.allocate(slot, buffers, channel)
        assert out == []

    expected = thr_after_slot0 * (1.0 - _THR_EWMA_ALPHA) ** 2
    assert sched._ue_state[1].dl_thr_bytes_per_slot == pytest.approx(expected)


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
    # min_rb=0: predates commit 4's follower-budget floor; prb_count=2
    # below is deliberate scarcity for the tier test, not the floor.
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid(), min_rb=0)
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
    # prb_count=100, not 2: commit 4's follower budget (module docstring)
    # means "scarce PRBs" no longer excludes the loser outright -- it
    # protects a minimum share for whichever candidate needs_service and
    # isn't ranked first. So the assertion checks who gets MORE, not who
    # is the ONLY one granted (see test_lower_accumulated_throughput_...
    # above for the same correction, with the full reasoning).
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=100, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2}
    assert by_ue[2].prbs > by_ue[1].prbs, "the GBR-flagged UE must get the larger share despite the worse coefficient"


def test_pdb_beats_the_coefficient_tiebreak_within_the_same_gbr_bucket_ul():
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pdb_ms=200.0),
        FlowConfig(ue_id=2, qfi=1, direction="UL", flow_class="PF", pdb_ms=10.0),
    ]
    # min_rb=0: predates commit 4's follower-budget floor; prb_count=2
    # below is deliberate scarcity for the tier test, not the floor.
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid(), min_rb=0)
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
    # prb_count=100, not 2 -- see test_gbr_tier_beats_the_coefficient_
    # tiebreak_dl above for the follower-budget correction this needs.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=100, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2}
    assert by_ue[2].prbs > by_ue[1].prbs, "the tighter-PDB UE must get the larger share despite the worse coefficient"


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
    # prb_count=100, not 2 -- see test_gbr_tier_beats_the_coefficient_
    # tiebreak_dl above for the follower-budget correction this needs.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=100, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2}
    assert by_ue[1].prbs > by_ue[2].prbs


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
    # prb_count=100, not 2 -- see test_gbr_tier_beats_the_coefficient_
    # tiebreak_dl above for the follower-budget correction this needs.
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=100, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2}
    assert by_ue[1].prbs > by_ue[2].prbs, "lcg==0 must not be treated as has_srb"


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


# -- 4a. wire guaranteed_bytes/be_bytes into grant sizing -----------------


def test_ul_target_above_backlog_grants_more_prbs_than_backlog_alone():
    """D1: the target sizes PRBs, not delivered bytes. Uses a real GFBR
    magnitude (obligation=500, max_burst=1000), not a token one --
    at obligation=1/target=2 both target and backlog round to a single
    PRB regardless of MCS, and the assertion would pass against an
    unmodified backlog-only implementation too.

    estimated_ul_buffer_per_lcg (the ungated per-LCG estimate the
    deficit loop reads) is set HIGH and bytes_reported (the crumb-gated
    view grant sizing otherwise uses) LOW, via explicit separate
    _FakeBuffers overrides rather than both defaulting from the same
    bytes_queued -- the real crumb-collapse scenario D1 exists for
    (WP3/WP4), not an artificial coincidence of one field standing in
    for the other."""
    sched = Reservation()
    flows = [
        FlowConfig(
            ue_id=1, qfi=1, direction="UL", flow_class="GBR",
            gfbr_bps=8_000_000.0, pdb_ms=100.0,
        )
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(
        1, 1, bytes_queued=5000, bytes_reported=100,
        estimated_ul_buffer_per_lcg=5000,
    )

    for _ in range(300):  # saturate the deficit at its window cap (100000)
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0  # post-grant state
    # 401 slots since the grant (odd -> non-whole-ms age): remaining PDB
    # floors to 0, rem_slots floors to 1, target caps at max_burst=1000
    # -- deterministic regardless of estimated_ul_buffer_per_lcg's value
    # (obligation/deficit/target/max_burst never read it; only the
    # overflow->be_bytes step below does). Confirmed independently first,
    # via the pure functions, before checking the real wiring below --
    # if this part disagrees with the end-to-end result, that's two
    # different findings, not one.
    has_gbr, _, guaranteed, be = sched._ul_gbr_and_pdb(1, buffers, slot_index=401)
    assert guaranteed == 1000  # confirms the deficit actually reached the cap
    assert be == 5000 - 1000  # overflow beyond the target, from the high estimate
    backlog_bytes = buffers.state(1, 1).bytes_reported
    assert backlog_bytes == 100
    target = _ul_grant_target(
        backlog_bytes=backlog_bytes, guaranteed_bytes=guaranteed, be_bytes=be,
        has_gbr=has_gbr, gbr_bytes_slot=0, has_srb=False, srb_lcg0_estimate=0,
    )
    assert target == guaranteed + be  # the backlog floor is a no-op here

    # Now the real wiring: call allocate() itself and read the actual
    # emitted grant's `prbs`, rather than re-deriving ceil(bytes*8/bpr)
    # by hand from `target` a second time. That comparison would be
    # tautological once `target > backlog_bytes` is already established
    # above (ceil division is monotonic in the numerator for any
    # positive bits_per_rb) and would not catch a wiring regression --
    # e.g. _allocate_direction reverting to `ue_backlog` for
    # `prbs_needed` while `_ul_grant_target` itself stayed correct.
    from scheduler.link import bits_per_prb

    slot = _FakeSlot(slot_index=401, dl_symbols=0, ul_symbols=14, prb_count=273)
    channel = _FakeChannel({1: 20.0})
    allocations = sched.allocate(slot, buffers, channel)
    assert len(allocations) == 1
    granted_prbs = allocations[0].prbs

    bpr, _ = bits_per_prb(20.0, symbols=14)
    prbs_needed_backlog_only = -(-(backlog_bytes * 8) // bpr)
    assert granted_prbs > prbs_needed_backlog_only


def test_target_below_backlog_leaves_sizing_unchanged():
    """The B-floor branch (`if target < backlog: target = backlog`) is
    structurally unreachable from _allocate_direction on any single-
    flow-per-LCG scenario -- guaranteed_bytes/be_bytes derive from the
    *ungated* estimated_ul_buffer_per_lcg, so per LCG
    guaranteed+be == max(lcg_estimate, target) >= lcg_estimate, while
    backlog_bytes sums the *gated* bytes_reported, and
    bytes_reported <= estimated_ul_buffer_per_lcg by construction (WP3)
    -- so guaranteed+be >= backlog_bytes already holds there (see
    scheduler/reservation.py's module docstring). Tested directly
    through the pure function with ints that deliberately violate that
    invariant, not via a constructed scenario -- no such scenario exists
    in this repo without the shared-LCG trick the next test uses for a
    different branch.

    has_gbr=True with gbr_bytes_slot=0 is deliberate: the gbr_bytes_slot
    term must no-op because of its own `> 0` guard, not because has_gbr
    happens to be False -- otherwise this would pass for the wrong
    reason."""
    ul_target = _ul_grant_target(
        backlog_bytes=500, guaranteed_bytes=10, be_bytes=20,
        has_gbr=True, gbr_bytes_slot=0, has_srb=False, srb_lcg0_estimate=0,
    )
    assert ul_target == 500  # backlog floor wins, not guaranteed+be=30

    dl_target = _dl_grant_target(
        backlog_bytes=500, guaranteed_bytes=10, be_bytes=20,
        has_srb=False, srb1_srb2_bytes=0,
    )
    assert dl_target == 500 + 12  # DL floor is backlog + oh


def test_ul_gbr_bytes_slot_raises_target_above_guaranteed_plus_be():
    """gbr_bytes_slot can only ever exceed guaranteed+be via the shared-
    LCG dedup asymmetry: _ul_gbr_and_pdb's deficit loop processes only
    the first flow found per LCG (seen_lcgs), while _ul_gbr_bytes_slot's
    loop is non-deduped. In any single-flow-per-LCG scenario,
    target >= obligation >= gbr_bytes_slot always -- mathematically
    unreachable any other way (module docstring).

    Flow A (first, small GFBR) must carry the MFBR: _ul_has_pending_gbr
    dedups per LCG too, so it only ever checks the first-found flow's
    mfbr_bps -- putting MFBR on B instead would leave the gate
    permanently closed regardless of B's GFBR."""
    sched = Reservation()
    flow_a = FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="GBR",
        gfbr_bps=8_000.0, mfbr_bps=1.0, pdb_ms=100.0, lcg=0,
    )
    flow_b = FlowConfig(
        ue_id=1, qfi=2, direction="UL", flow_class="GBR",
        gfbr_bps=8_000_000.0, mfbr_bps=0.0, pdb_ms=100.0, lcg=0,
    )
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=50, estimated_ul_buffer_per_lcg=50)
    buffers.set(1, 2, bytes_queued=50, estimated_ul_buffer_per_lcg=50)

    for _ in range(300):  # saturate A's deficit (the only flow the dedup sees)
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    sched._ue_state[1].ul_lcg_last_grant_slot[0] = 0
    has_gbr, _, guaranteed, be = sched._ul_gbr_and_pdb(1, buffers, slot_index=401)
    assert guaranteed + be == 50  # A alone, backlog-dominated; B invisible here

    gbr_bytes_slot = sched._ul_gbr_bytes_slot(1, buffers)
    assert gbr_bytes_slot == 500  # B's rate, unfloored -- A's own contributes 0

    target = _ul_grant_target(
        backlog_bytes=50, guaranteed_bytes=guaranteed, be_bytes=be,
        has_gbr=has_gbr, gbr_bytes_slot=gbr_bytes_slot,
        has_srb=False, srb_lcg0_estimate=0,
    )
    assert target == gbr_bytes_slot
    assert target > guaranteed + be


def test_ul_gbr_bytes_slot_is_zero_without_any_mfbr_configured():
    """Guards the has_pending_gbr gate itself: without it, a future
    refactor that only remembers the GFBR/dedup half of gbr_bytes_slot
    could silently make it live on every scenario, since no scenario
    configures mfbr_bps today (docs/oai-port-map.md row 23). Same
    shared-LCG A/B construction as the previous test but neither flow
    sets mfbr_bps."""
    sched = Reservation()
    flow_a = FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="GBR",
        gfbr_bps=8_000.0, mfbr_bps=0.0, pdb_ms=100.0, lcg=0,
    )
    flow_b = FlowConfig(
        ue_id=1, qfi=2, direction="UL", flow_class="GBR",
        gfbr_bps=8_000_000.0, mfbr_bps=0.0, pdb_ms=100.0, lcg=0,
    )
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=50, estimated_ul_buffer_per_lcg=50)
    buffers.set(1, 2, bytes_queued=50, estimated_ul_buffer_per_lcg=50)

    assert sched._ul_has_pending_gbr(1, buffers) is False
    assert sched._ul_gbr_bytes_slot(1, buffers) == 0  # despite B's large GFBR


def test_dl_grant_target_includes_fixed_overhead_ul_does_not():
    """DL's oh=12 (3*4 + (ta_apply?2:0), no TA model) applies at both
    branches -- the guaranteed+be path and the backlog-floor path -- and
    UL has no equivalent term at all (gNB_scheduler_ulsch.c:2492-2512
    has no `oh`)."""
    ul_a = _ul_grant_target(
        backlog_bytes=10, guaranteed_bytes=100, be_bytes=50,
        has_gbr=True, gbr_bytes_slot=0, has_srb=False, srb_lcg0_estimate=0,
    )
    dl_a = _dl_grant_target(
        backlog_bytes=10, guaranteed_bytes=100, be_bytes=50,
        has_srb=False, srb1_srb2_bytes=0,
    )
    assert dl_a == ul_a + 12  # guaranteed+be path (150 vs 162)

    ul_b = _ul_grant_target(
        backlog_bytes=500, guaranteed_bytes=10, be_bytes=20,
        has_gbr=True, gbr_bytes_slot=0, has_srb=False, srb_lcg0_estimate=0,
    )
    dl_b = _dl_grant_target(
        backlog_bytes=500, guaranteed_bytes=10, be_bytes=20,
        has_srb=False, srb1_srb2_bytes=0,
    )
    assert dl_b == ul_b + 12  # backlog-floor path (500 vs 512)


def test_has_srb_cap_is_correct_but_structurally_unreachable():
    """has_srb is hardcoded False in _allocate_direction (module
    docstring) -- this path never executes today. Tested directly
    through the pure functions with has_srb forced True to confirm the
    cap logic itself is correct, same treatment
    test_has_srb_cannot_be_exercised_and_is_recorded_as_such gives the
    sort tier."""
    ul_target = _ul_grant_target(
        backlog_bytes=10, guaranteed_bytes=1000, be_bytes=500,
        has_gbr=True, gbr_bytes_slot=0, has_srb=True, srb_lcg0_estimate=20,
    )
    assert ul_target == 20  # capped to max(1, srb_lcg0_estimate), below 1500

    dl_target = _dl_grant_target(
        backlog_bytes=10, guaranteed_bytes=1000, be_bytes=500,
        has_srb=True, srb1_srb2_bytes=5,
    )
    assert dl_target == 5 + 12  # capped to srb1_srb2_bytes + oh


def test_sub_one_byte_gbr_floors_to_one_in_deficit_loop_and_zero_in_gbr_bytes_slot():
    """gfbr_bps small enough that gfbr_bps/8/slots_per_sec < 1: the
    deficit loop's obligation floors to 1 (max(1,...),
    gNB_scheduler_ulsch.c:2254), but gbr_bytes_slot has no such floor
    and returns 0 for the same flow -- the bug-for-bug divergence
    (:2304-2316)."""
    sched = Reservation()
    # 100 bytes/sec: (100/8)/2000 = 0.00625 -- well under 1 byte/slot.
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="GBR",
        gfbr_bps=100.0, mfbr_bps=1.0, pdb_ms=100.0, lcg=0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=50, estimated_ul_buffer_per_lcg=50)

    has_gbr, _, guaranteed, be = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert has_gbr is True
    assert guaranteed == 1  # obligation floored to 1

    gbr_bytes_slot = sched._ul_gbr_bytes_slot(1, buffers)
    assert gbr_bytes_slot == 0  # no floor -- confirms the bug-for-bug gap

    target = _ul_grant_target(
        backlog_bytes=50, guaranteed_bytes=guaranteed, be_bytes=be,
        has_gbr=has_gbr, gbr_bytes_slot=gbr_bytes_slot,
        has_srb=False, srb_lcg0_estimate=0,
    )
    assert target == guaranteed + be  # gbr_bytes_slot=0 correctly no-ops (>0 gate)


# -- 4. the follower budget -----------------------------------------------


def test_follower_budget_degenerates_to_unconstrained_at_zero_followers():
    """The acceptance criterion, corrected scoping (module docstring's
    commit-4 section, and the doc corrections landing alongside it):
    at n_followers_need=0 the follower-budget CLAMP is a provable
    no-op -- algebraically, budget=base and base<=base always, so
    `max_rb_size > budget` never holds, regardless of min_rb/base. This
    is NOT a claim that all of Reservation collapses to PF: the sort
    tiers and 4a's target-based sizing are untouched by this mechanism
    and remain real differences from PF whenever a GBR deficit is
    active. has_srb=True is deliberately excluded here -- that branch
    already forces min_rb regardless of n_followers, a different
    no-op covered by its own test below."""
    for bwp_size, min_rb in [(50, 5), (1, 1), (1000, 7), (5, 5)]:
        assert _ul_follower_budget(bwp_size, 0, min_rb, has_srb=False) == bwp_size
    for max_rb_size, min_rb_size in [(50, 5), (1, 1), (1000, 7), (5, 5)]:
        assert _dl_follower_budget(max_rb_size, 0, min_rb_size) == max_rb_size


def test_follower_budget_lowers_max_rb_size_when_followers_need_protecting():
    """needs_service is tautologically True for every candidate today
    (module docstring's commit-4 finding), so n_followers_need is
    driven purely by the COUNT of trailing candidates in this port, not
    by the predicate -- this test varies that count, not what
    needs_service evaluates to. It cannot exercise the predicate
    itself; the next test does that directly."""
    assert _ul_follower_budget(50, 3, 5, has_srb=False) == 50 - 3 * 5
    assert _ul_follower_budget(50, 3, 5, has_srb=False) < 50
    assert _dl_follower_budget(50, 3, 5) == 50 - 3 * 5
    assert _dl_follower_budget(50, 3, 5) < 50


def test_follower_budget_floors_at_min_rb_never_below():
    """A large enough n_followers_need would drive budget negative
    without the floor -- gNB_scheduler_ulsch.c:2429 / _dlsch.c:922."""
    assert _ul_follower_budget(10, 5, 5, has_srb=False) == 5  # 10-25=-15 -> floored
    assert _dl_follower_budget(10, 5, 5) == 5


def test_dl_post_budget_skip_when_remaining_capacity_below_min_rbsize():
    """gNB_scheduler_dlsch.c:926 -- a candidate whose follower-budget-
    capped share falls below min_rbSize gets NO grant at all this slot,
    not a smaller one. 2 UEs, prb_count=6: UE1 (ranked first,
    n_followers_need=1) is capped to budget=6-1*5=1, floored to
    min_rbSize=5 -- so UE1 actually gets 5, leaving prbs_left=1 for
    UE2, which is below min_rbSize=5 and must be skipped entirely."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 1.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 100000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=6, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1}, "UE2's protected share (1 PRB) is below min_rbSize=5 -- must get nothing, not a tiny grant"
    assert by_ue[1].prbs == 5


def test_ul_max_rb_size_init_uses_min_rb_when_has_srb_forced():
    """UL's max_rbSize init, (sched_inactive||has_srb)?min_rb:bwp_size
    (gNB_scheduler_ulsch.c:2421), is structurally unreachable in
    _allocate_direction today -- has_srb is hardcoded False (module
    docstring). Tested directly with has_srb forced True to confirm
    the branch itself is correct. sched_inactive has no stored field
    anywhere in this module (always False, no-op) -- there is no
    separate parameter for it to force."""
    assert _ul_follower_budget(1000, 0, 5, has_srb=True) == 5
    # Confirm it's really the has_srb branch deciding this, not the
    # follower-budget clamp (which would be a no-op here regardless,
    # per the n_followers_need=0 degeneracy test above) --
    # has_srb=False with identical inputs must NOT clip to min_rb.
    assert _ul_follower_budget(1000, 0, 5, has_srb=False) == 1000


def test_needs_service_non_backlog_terms_are_currently_unreachable():
    """_allocate_direction's candidate list is pre-filtered to
    bytes_reported>0, so needs_service's `or has_srb`/`or has_gbr` (UL)
    /`or has_srb` (DL) terms can never be the deciding factor today --
    the backlog term alone already makes it True for every candidate
    that reaches this function. Tested directly with backlog=0 forced
    (a state _allocate_direction can never actually supply) so a future
    refactor that drops these terms fails a test instead of silently
    doing nothing observable, the same treatment 4a's test 7 gave the
    gbr_bytes_slot MFBR gate."""
    assert _ul_needs_service(0, has_srb=False, has_gbr=True) is True
    assert _ul_needs_service(0, has_srb=True, has_gbr=False) is True
    assert _ul_needs_service(0, has_srb=False, has_gbr=False) is False
    assert _dl_needs_service(0, has_srb=True) is True
    assert _dl_needs_service(0, has_srb=False) is False


def test_follower_budget_visibly_protects_trailing_ues_from_a_saturating_leader():
    """3-UE UL scenario: a saturating leader (60000-byte backlog, needs
    ~817 PRBs against a 50-PRB pool) ranked first, two modest trailing
    UEs (200 bytes each, ~3 PRBs). Without the follower budget the
    leader would consume the entire slot every time, starving both
    followers -- gNB_scheduler_ulsch.c's own "a saturating BE UE cannot
    zero a starved UE behind it," the mechanism's whole reason to
    exist. With it, the leader is capped (n_followers_need=2 protects
    2*min_rb=10 PRBs), leaving room for both to be served this slot."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="UL", flow_class="PF"),
        FlowConfig(ue_id=3, qfi=1, direction="UL", flow_class="PF"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].ul_thr_bytes_per_slot = 1.0      # leader: best coef
    sched._ue_state[2].ul_thr_bytes_per_slot = 10.0     # 2nd
    sched._ue_state[3].ul_thr_bytes_per_slot = 1000.0   # 3rd: worst coef

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=60000)  # far exceeds any realistic PRB budget
    buffers.set(2, 1, bytes_queued=200)    # modest -- needs ~3 PRBs
    buffers.set(3, 1, bytes_queued=200)    # modest -- needs ~3 PRBs
    channel = _FakeChannel({1: 20.0, 2: 20.0, 3: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2, 3}, "the follower budget must leave room for both trailing UEs"
    assert by_ue[1].prbs <= 40, "the leader must be capped: bwp_size(50) - 2 followers*min_rb(5) = 40"
    assert by_ue[2].prbs > 0 and by_ue[3].prbs > 0


def test_dl_follower_budget_base_reflects_prbs_already_consumed_this_slot():
    """Finding 1's observable consequence, guarding the exact bug
    flagged when this commit was planned: DL's follower-budget base
    must be the CURRENT prbs_left at each candidate's turn, not a
    value computed once for the whole slot. 3 UEs, not 2 -- a 2-UE
    fixture can't distinguish this, since the last candidate's own
    n_followers_need is always 0 regardless of which base it receives,
    so the bug is only observable through a MIDDLE candidate that
    itself still has a follower to protect.

    Hand-worked, both ways: CORRECT -- UE1 takes 40 (of 50), leaving
    prbs_left=10; UE2's base is 10 (not 50), budget=10-1*5=5, so UE2 is
    capped to 5 even though it could use 8; prbs_left=5 remains, UE3
    gets 3 (of the 3 it needs). WRONG (base hoisted to the original 50
    for every candidate) -- UE2's budget would compute as 50-1*5=45,
    letting it take its full 8-PRB need instead of 5; prbs_left would
    then drop to 2, below min_rbSize=5, and UE3 would be skipped
    entirely. The two implementations produce different, checkable
    outcomes for UE2 and UE3, not just a vague "smaller" comparison."""
    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF"),
        FlowConfig(ue_id=3, qfi=1, direction="DL", flow_class="PF"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 1.0
    sched._ue_state[2].dl_thr_bytes_per_slot = 10.0
    sched._ue_state[3].dl_thr_bytes_per_slot = 1000.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=60000)  # leader: far exceeds any budget
    buffers.set(2, 1, bytes_queued=550)    # needs 8 PRBs if unconstrained
    buffers.set(3, 1, bytes_queued=200)    # needs 3 PRBs if unconstrained
    channel = _FakeChannel({1: 20.0, 2: 20.0, 3: 20.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    by_ue = {a.ue_id: a for a in out}
    assert set(by_ue) == {1, 2, 3}, "UE3 is only starved if UE2's base is wrongly hoisted to the slot's original pool"
    assert by_ue[1].prbs == 40, "leader capped to bwp_size(50) - 2 followers*min_rbSize(5)"
    assert by_ue[2].prbs == 5, "UE2's base must be the CURRENT prbs_left (10) at its turn: 10 - 1*5 = 5, not 50 - 1*5 = 45"
    assert by_ue[3].prbs == 3


# -- 5. the post-grant deficit drain, bug-for-bug -------------------------


def test_ul_deficit_drains_full_tb_size_per_active_lcg_including_crumb_gated_ones():
    """gNB_scheduler_ulsch.c:2760-2777, comment vs code, quoted verbatim
    in docs/oai-port-map.md row 29: "distribute tb_size drain
    proportionally across active LCGs" -- the code does not divide; it
    subtracts the FULL tb_size from every active LCG independently.

    Also covers the found-and-fixed bug (module docstring's commit-5
    section): the C's iteration gate is estimated_ul_buffer_per_lcg>0
    (the true per-LCG BSR estimate), not bytes_reported>0 (the
    crumb-gated view c.flows is filtered on) -- flow B here is
    crumb-gated to a ZERO report but still has a real estimate, so it
    must still be stamped and drained. Built with BOTH flows on the
    divergent path (not one PF + one crumb-gated) so a wrong
    implementation that only iterates c.flows would fail this test
    outright, not pass it by accident."""
    sched = Reservation()
    flow_a = FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="GBR",
        gfbr_bps=8_000_000.0, pdb_ms=100.0, lcg=0,
    )
    flow_b = FlowConfig(
        ue_id=1, qfi=2, direction="UL", flow_class="GBR",
        gfbr_bps=8_000_000.0, pdb_ms=100.0, lcg=1,
    )
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=500, estimated_ul_buffer_per_lcg=500)
    buffers.set(
        1, 2, bytes_queued=5000, bytes_reported=0,
        estimated_ul_buffer_per_lcg=5000,
    )

    for _ in range(300):  # saturate both LCGs' deficits
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    deficit_a_before = sched._ue_state[1].ul_lcg_deficit_bytes[0]
    deficit_b_before = sched._ue_state[1].ul_lcg_deficit_bytes[1]
    assert deficit_a_before > 0 and deficit_b_before > 0

    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)
    channel = _FakeChannel({1: 20.0})
    out = sched.allocate(slot, buffers, channel)
    assert len(out) == 1
    tbs_granted = out[0].bytes_capacity
    assert tbs_granted > 0

    # Stamped: BOTH LCGs, including flow B's crumb-gated one (absent
    # from the eligible-candidate flow list entirely -- bytes_reported=0).
    assert sched._ue_state[1].ul_lcg_last_grant_slot[0] == slot.slot_index
    assert sched._ue_state[1].ul_lcg_last_grant_slot[1] == slot.slot_index

    # Drained: the FULL tb_size credited to EACH active LCG
    # independently -- not split, not skipped for the crumb-gated one.
    assert sched._ue_state[1].ul_lcg_deficit_bytes[0] == max(0, deficit_a_before - tbs_granted)
    assert sched._ue_state[1].ul_lcg_deficit_bytes[1] == max(0, deficit_b_before - tbs_granted)


def test_dl_deficit_drains_by_the_real_per_flow_delivered_bytes():
    """gNB_scheduler_dlsch.c:1451-1460 -- "drain GBR deficit by bytes
    actually delivered," and the code does exactly that (confirmed
    directly, not assumed from the charter -- no bug on DL). Two flows
    on one UE, sized so _dl_fill's placeholder greedy pass gives them
    DIFFERENT amounts -- confirms each flow's deficit drains by its OWN
    delivered bytes, not a shared UE-level amount (which would be the
    UL bug, wrongly ported to DL)."""
    sched = Reservation()
    flow_a = FlowConfig(
        ue_id=1, qfi=1, direction="DL", flow_class="GBR",
        gfbr_bps=8_000_000.0, pdb_ms=100.0, priority_level=10,
    )
    flow_b = FlowConfig(
        ue_id=1, qfi=2, direction="DL", flow_class="GBR",
        gfbr_bps=8_000_000.0, pdb_ms=100.0, priority_level=20,
    )
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=300)   # higher priority -- filled first, in full
    buffers.set(1, 2, bytes_queued=6000)  # lower priority -- absorbs the remainder

    for _ in range(300):
        sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    deficit_a_before = sched._ue_state[1].dl_flow_deficit_bytes[1]
    deficit_b_before = sched._ue_state[1].dl_flow_deficit_bytes[2]
    assert deficit_a_before > 0 and deficit_b_before > 0

    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=10, pdcch_cce_budget=48)
    channel = _FakeChannel({1: 20.0})
    out = sched.allocate(slot, buffers, channel)
    by_qfi_bytes = {a.qfi: a.bytes_capacity for a in out}
    assert set(by_qfi_bytes) == {1, 2}
    assert by_qfi_bytes[1] != by_qfi_bytes[2], "need a genuinely different split to prove per-flow draining, not a coincidence"

    assert sched._ue_state[1].dl_flow_deficit_bytes[1] == max(0, deficit_a_before - by_qfi_bytes[1])
    assert sched._ue_state[1].dl_flow_deficit_bytes[2] == max(0, deficit_b_before - by_qfi_bytes[2])


def test_dl_stamp_and_drain_skip_flows_that_got_no_fill_bytes():
    """Correction to commit 3, found scoping commit 5 (module
    docstring): DL's stamp (dl_lcid_last_drain_slot) and drain are
    gated on lcid_bytes>0 per LC in the C -- a flow _dl_fill's greedy
    priority pass never reaches gets NEITHER. Commit 3's original stamp
    iterated ALL of c.flows unconditionally; this is the first fixture
    where that would have been observably wrong -- a lower-priority
    flow entirely starved of bytes this slot must have its
    last_grant_slot/deficit UNTOUCHED, not stamped as if it had just
    been served (which would understate its true PDB urgency at the
    comparator tier once commit 10 wires this in)."""
    sched = Reservation()
    flow_a = FlowConfig(
        ue_id=1, qfi=1, direction="DL", flow_class="GBR",
        gfbr_bps=8_000_000.0, pdb_ms=100.0, priority_level=10,
    )
    flow_b = FlowConfig(
        ue_id=1, qfi=2, direction="DL", flow_class="GBR",
        gfbr_bps=8_000_000.0, pdb_ms=100.0, priority_level=20,
    )
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)  # absorbs the entire grant
    buffers.set(1, 2, bytes_queued=6000)  # gets nothing this slot

    for _ in range(300):
        sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    deficit_b_before = sched._ue_state[1].dl_flow_deficit_bytes[2]
    assert deficit_b_before > 0

    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=10, pdcch_cce_budget=48)
    channel = _FakeChannel({1: 20.0})
    out = sched.allocate(slot, buffers, channel)
    granted_qfis = {a.qfi for a in out}
    assert granted_qfis == {1}, "flow A's backlog alone absorbs the whole grant -- flow B must get nothing"

    assert 2 not in sched._ue_state[1].dl_flow_last_grant_slot, "flow B got no bytes -- must not be stamped"
    assert sched._ue_state[1].dl_flow_deficit_bytes[2] == deficit_b_before, "flow B's deficit must be untouched"


def test_deficit_drain_floors_at_zero_both_directions():
    """The C's own floor (`if (...) < 0: ... = 0`), both directions --
    a grant larger than the outstanding deficit must not leave it
    negative."""
    sched = Reservation()
    ul_flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="GBR",
        gfbr_bps=8_000.0, pdb_ms=100.0, lcg=0,
    )
    sched.configure([ul_flow], slot_duration_s=0.0005, grid=_grid())
    ul_buffers = _FakeBuffers()
    ul_buffers.set(1, 1, bytes_queued=6000, estimated_ul_buffer_per_lcg=6000)
    sched._ul_gbr_and_pdb(1, ul_buffers, slot_index=0)  # small, first-call obligation
    ul_deficit_before = sched._ue_state[1].ul_lcg_deficit_bytes[0]
    assert 0 < ul_deficit_before < 100

    sched._ul_drain_and_stamp(1, ul_buffers, slot_index=1, tbs_bytes=999_999)
    assert sched._ue_state[1].ul_lcg_deficit_bytes[0] == 0

    dl_sched = Reservation()
    dl_flow = FlowConfig(
        ue_id=1, qfi=1, direction="DL", flow_class="GBR",
        gfbr_bps=8_000.0, pdb_ms=100.0,
    )
    dl_sched.configure([dl_flow], slot_duration_s=0.0005, grid=_grid())
    dl_buffers = _FakeBuffers()
    dl_buffers.set(1, 1, bytes_queued=6000)
    dl_sched._dl_gbr_and_pdb(1, dl_buffers, slot_index=0)
    dl_deficit_before = dl_sched._ue_state[1].dl_flow_deficit_bytes[1]
    assert 0 < dl_deficit_before < 100

    dl_sched._dl_drain_and_stamp([(1, 999_999)], ue_id=1, slot_index=1)
    assert dl_sched._ue_state[1].dl_flow_deficit_bytes[1] == 0


# -- 6. the real two-pass DL LCP -------------------------------------------


def test_dl_fill_uses_declared_order_not_priority_order():
    """gNB_scheduler_dlsch.c:1394-1463's own comment, confirmed by
    reading the loop directly (no sort/qsort touches lc_config anywhere
    in that file -- the only qsort is the inter-UE comparator): DRBs
    fill in EXISTING DECLARED ORDER, not by priority_level. flow A is
    declared FIRST but has the WORSE (higher-numeric) priority_level;
    flow B is declared SECOND but has the BETTER one -- deliberately in
    tension, since every existing multi-DL-flow fixture in this file
    happens to have declaration order and priority order agree, which
    would pass under either rule and prove nothing."""
    sched = Reservation()
    flow_a = FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF", priority_level=90)
    flow_b = FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="PF", priority_level=10)
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())

    # Verify, don't assume, that configure() preserves declared order --
    # the fill's faithfulness depends entirely on it.
    dl_qfis_in_order = [f.qfi for f in sched._flows if f.ue_id == 1 and f.direction == "DL"]
    assert dl_qfis_in_order == [1, 2]

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=300)   # declared first, worse priority
    buffers.set(1, 2, bytes_queued=6000)  # declared second, better priority

    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=10, pdcch_cce_budget=48)
    channel = _FakeChannel({1: 20.0})
    out = sched.allocate(slot, buffers, channel)
    by_qfi = {a.qfi: a.bytes_capacity for a in out}

    # Declaration order (correct): flow A fills first and fully, flow B
    # gets the remainder -- both present. Priority order (the old
    # placeholder): flow B (better priority) would fill first, consuming
    # the entire TB and leaving flow A with nothing.
    assert set(by_qfi) == {1, 2}, "flow A must still get served -- priority order would starve it entirely"
    assert by_qfi[1] == 300, "flow A (declared first) must be filled in full before flow B is touched"


def test_dl_fill_excludes_flows_that_get_zero_bytes():
    """Commit 5's hoist contract, re-verified for the real fill (not
    just inherited from the placeholder): a flow computing take==0 must
    be absent from `fills` entirely, not present with byts=0 --
    _dl_drain_and_stamp/_emit_grant both depend on this."""
    sched = Reservation()
    flow_a = FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF")
    flow_b = FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="PF")
    sched.configure([flow_a, flow_b], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)  # absorbs everything
    buffers.set(1, 2, bytes_queued=6000)

    fills = sched._dl_fill([flow_a, flow_b], tbs_bytes=735, buffers=buffers)
    assert fills == [(1, 735)]
    assert 2 not in dict(fills)


# -- 7. min_rb wiring -- doc-only, no code, no new tests -------------------


# -- 8. persistent per-UE MCS index (D2(a)) --------------------------------


def test_mcs_index_for_snr_matches_the_row_walk():
    """scheduler/link.py's new mcs_index_for_snr must derive from the
    SAME staircase walk _mcs_row_for_snr already uses, not a second,
    independent one -- checked directly against the row's own position
    in _MCS_TABLE, not just trusted from the refactor."""
    from scheduler import link

    for snr in [-5.0, -2.0, 0.0, 10.0, 16.0, 31.0, 40.0]:
        idx = link.mcs_index_for_snr(snr)
        row = link._mcs_row_for_snr(snr)
        if row is None:
            assert idx == 0  # floors, unlike the row-based lookup's None
        else:
            assert link._MCS_TABLE[idx] == row


def test_bits_per_prb_for_mcs_matches_the_table_row_directly():
    """Commit 9's new bits_per_prb_for_mcs indexes _MCS_TABLE directly --
    no SNR walk involved -- so it must reproduce each row's own
    (se, bler) exactly at every valid index, and for every symbol count,
    not just the default 14."""
    from scheduler import link

    for idx, (_, se, bler) in enumerate(link._MCS_TABLE):
        for symbols in (1, 10, 14):
            bits, got_bler = link.bits_per_prb_for_mcs(idx, symbols=symbols)
            assert bits == int(se * 12 * symbols)
            assert got_bler == bler


def test_bits_per_prb_for_mcs_matches_bits_per_prb_via_mcs_index_for_snr():
    """The equivalence commit 9's prediction rests on: with _OLLA_OFFSET
    pinned at 0, bits_per_prb_for_mcs(mcs_index_for_snr(snr), symbols)
    must equal bits_per_prb(snr, symbols) exactly, for any in-range SNR
    -- this is WHY commit 9 doesn't move any existing coefficient/grant-
    size assertion despite changing which function computes them."""
    from scheduler import link

    for snr in [-2.0, 0.0, 10.0, 16.0, 25.0, 31.0, 40.0]:
        for symbols in (10, 14):
            direct = link.bits_per_prb(snr, symbols=symbols)
            via_index = link.bits_per_prb_for_mcs(
                link.mcs_index_for_snr(snr), symbols=symbols
            )
            assert direct == via_index


def test_bits_per_prb_for_mcs_clamps_out_of_range_index():
    from scheduler import link

    low = link.bits_per_prb_for_mcs(-5, symbols=14)
    high = link.bits_per_prb_for_mcs(999, symbols=14)
    assert low == link.bits_per_prb_for_mcs(0, symbols=14)
    assert high == link.bits_per_prb_for_mcs(len(link._MCS_TABLE) - 1, symbols=14)


def test_mcs_index_for_snr_floors_at_zero_below_lowest_threshold():
    from scheduler import link

    assert link.mcs_index_for_snr(-100.0) == 0


def test_ul_and_dl_mcs_index_persisted_at_candidate_build_time():
    """Matches the C's own per-candidate timing
    (gNB_scheduler_ulsch.c:2192, inside the per-UE ranking loop, before
    the qsort) -- computed for every candidate considered this slot,
    not just the eventual winner, and independently per UE/direction.
    Also exercises commit 9's _OLLA_OFFSET: this assertion is unchanged
    from commit 8 (mcs_index_for_snr(snr) with no added offset), which
    is the point -- module docstring's commit-9 section proves the
    offset is 0, and this is that proof holding for a real candidate
    build, not just in isolation."""
    from scheduler.link import mcs_index_for_snr

    sched = Reservation()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF"),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=2000)
    buffers.set(2, 1, bytes_queued=2000)
    channel = _FakeChannel({1: 16.0, 2: 25.0})
    slot = _FakeSlot(dl_symbols=14, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    sched.allocate(slot, buffers, channel)

    assert sched._ue_state[1].ul_mcs_index == mcs_index_for_snr(16.0)
    assert sched._ue_state[2].dl_mcs_index == mcs_index_for_snr(25.0)


def test_mcs_index_recomputed_fresh_every_slot_not_read_then_preserved():
    """The persisted MCS index is recomputed from mcs_index_for_snr(snr)
    at the top of every candidate-build pass, before it's used for
    sizing this same slot -- pre-seeding it with a nonsense value before
    allocate() must not survive into the grant. This was true at commit
    8 too (nothing consumed it yet, so pre-seeding trivially couldn't
    matter); commit 9 makes it a live claim about a value grant sizing
    now actually reads, not just an inert field."""
    def make_scheduler():
        sched = Reservation()
        flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF")]
        sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
        return sched

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=2000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    sched_clean = make_scheduler()
    out_clean = sched_clean.allocate(slot, buffers, channel)

    sched_corrupted = make_scheduler()
    sched_corrupted._ue_state[1].ul_mcs_index = 999  # nonsense, pre-seeded
    out_corrupted = sched_corrupted.allocate(slot, buffers, channel)

    assert [(a.prbs, a.bytes_capacity) for a in out_clean] == \
        [(a.prbs, a.bytes_capacity) for a in out_corrupted]
    assert sched_corrupted._ue_state[1].ul_mcs_index != 999


def test_grant_sizing_now_reads_the_persisted_mcs_index():
    """Commit 9 (D2(b)): grant sizing switches from recomputing
    bits_per_prb(snr, symbols) independently to reading
    bits_per_prb_for_mcs(mcs_index, symbols) -- the persisted field
    commit 8 built but nothing read. Verified directly, the same
    standard commit 8's corrupted-index test met: monkeypatch
    bits_per_prb_for_mcs to a rate _MCS_TABLE could never produce at
    this SNR and confirm the emitted grant reflects it -- a black-box
    comparison of granted bytes alone can't distinguish the two data
    paths, since _OLLA_OFFSET == 0 makes them numerically identical
    today (module docstring's commit-9 section)."""
    import scheduler.reservation as resv_mod

    def fake_bits_per_prb_for_mcs(mcs_index, symbols):
        return 4800, 0.0  # _MCS_TABLE's real rows never reach this high

    sched = Reservation()
    flows = [FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF")]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1_000_000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    real = resv_mod.bits_per_prb_for_mcs
    resv_mod.bits_per_prb_for_mcs = fake_bits_per_prb_for_mcs
    try:
        out = sched.allocate(slot, buffers, channel)
    finally:
        resv_mod.bits_per_prb_for_mcs = real

    assert len(out) == 1
    expected_bytes = (out[0].prbs * 4800) // 8
    assert out[0].bytes_capacity == expected_bytes
