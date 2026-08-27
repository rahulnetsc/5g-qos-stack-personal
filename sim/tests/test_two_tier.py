"""Phase 2, two-tier commits 1-3: scheduler/two_tier.py's rewrite.

Commit 1: Scheduler protocol conformance, per-UE throughput EWMA
(blanket decay, not candidacy-gated -- landing the corrected form from
the start rather than reservation's own commit-1-through-10a path), a
bootstrap PF coefficient as the only ranking criterion (explicitly NOT a
ported mechanism -- see scheduler/two_tier.py's module docstring),
UL-then-DL per-slot order (fixed from the pre-rewrite file's own
DL-then-UL bug). Commit 2: the real Tier-1 SCA/GLPK-equivalent solve
wired in, output unconsumed. Commit 3: DL's real 3-tier comparator
(has_gbr -> pdb_ms -> the still-bootstrap coefficient) and UL's
deliberately-revised 2-tier one (sched_inactive -> coefficient, no
has_gbr/pdb_ms -- ground truth's own architectural reason: Tier-1's
targets already carry the GBR guarantee into Tier-2's VQ deficit on UL).
The VQ itself -- what actually replaces the bootstrap coefficient -- is
commit 3a, not yet landed.

See docs/phase2-plan.md's two-tier commit checklist and
docs/oai-port-map.md's "Phase 2 -- two-tier" section (rows 35-48) for the
full citation/divergence detail.

Commit 3's own predicted `--check` outcome, scored in docs/phase2-plan.md:
DL confirmed to move (real, ranking-affecting tiers); UL predicted NOT to
move, which was wrong on 2 of 6 records -- traced directly, not shrugged
off, to sim/harq.py::HarqProcessPool.due_this_slot()'s shared,
insertion-order-dependent iteration (CLAUDE.md's new invariant,
docs/oai-port-map.md row 48) moving UL HARQ outcomes from a DL-only
timing change, with _ul_rank_key and reported SNR confirmed
byte-identical -- a real simulator-infrastructure property, not a bug in
this commit's own tier logic.
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

    def set(
        self, ue_id: int, qfi: int, bytes_queued: int,
        estimated_ul_buffer_per_lcg: int | None = None,
    ) -> None:
        self._states[(ue_id, qfi)] = _FakeBufferState(
            bytes_queued=bytes_queued, bytes_reported=bytes_queued,
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


# -- 6. commit 3: DL's has_gbr -> pdb_ms -> coefficient sort tiers ----------
# ia_p5g_dl_cmp, ia_p5g_scheduler.c:1397-1411 -- the never-revised
# lexicographic form. One fixture per tier boundary (reservation.py's own
# commit-2 discipline), so a wrong tier ORDER fails distinguishably from
# wrong tier CONTENT.


def test_dl_has_gbr_tier_beats_the_coefficient_tiebreak():
    """A GBR flow (real deficit, accumulates unconditionally on the very
    first call -- has_gbr=True) must win the only grant over a non-GBR
    flow with a far more favourable (lower) thr_ue coefficient."""
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF"),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 10.0    # would win on coef alone
    sched._ue_state[2].dl_thr_bytes_per_slot = 1000.0  # would lose on coef alone

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})

    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=82, pdcch_cce_budget=48)
    out = sched.allocate(slot, buffers, channel)

    by_ue = {a.ue_id for a in out}
    assert by_ue == {2}, f"GBR flow (has_gbr) should win despite a worse coefficient; got {by_ue}"


def test_dl_pdb_tier_beats_the_coefficient_tiebreak_within_the_same_has_gbr_bucket():
    """Two non-GBR flows (has_gbr=False for both) -- the one with the
    tighter (lower) pdb_ms wins the only grant even with a worse
    coefficient. Neither has been granted before, so remaining_pdb ==
    pdb_ms exactly (no age truncation to reason about)."""
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF", pdb_ms=10.0),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="PF", pdb_ms=300.0),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].dl_thr_bytes_per_slot = 1000.0  # worse coef
    sched._ue_state[2].dl_thr_bytes_per_slot = 10.0    # better coef

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=6000)
    buffers.set(2, 1, bytes_queued=6000)
    channel = _FakeChannel({1: 20.0, 2: 20.0})

    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=82, pdcch_cce_budget=48)
    out = sched.allocate(slot, buffers, channel)

    by_ue = {a.ue_id for a in out}
    assert by_ue == {1}, f"tighter pdb_ms should win despite a worse coefficient; got {by_ue}"


def test_dl_coefficient_remains_the_final_tiebreak_when_has_gbr_and_pdb_tie():
    """Both non-GBR, both at the default pdb_ms (100.0, never granted
    before -> tied remaining_pdb) -- the tiebreak falls through to the
    bootstrap coefficient, same outcome as the pre-commit-3
    coefficient-only test this one is adjacent to."""
    sched = TwoTier()
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

    slot = _FakeSlot(dl_symbols=14, ul_symbols=0, prb_count=82, pdcch_cce_budget=48)
    out = sched.allocate(slot, buffers, channel)

    by_ue = {a.ue_id for a in out}
    assert by_ue == {1}, f"lower-thr_ue UE1 should win the tiebreak; got {by_ue}"


def test_dl_gbr_deficit_accumulates_unconditionally_even_without_backlog():
    """gNB_scheduler_dlsch.c:381-388 -- deficit accumulation and
    has_unfulfilled_gbr are UNCONDITIONAL for every GBR-configured flow,
    unlike UL's per-LCG-estimate-gated form. Calling _dl_gbr_and_pdb for
    a GBR flow with zero backlog must still report has_gbr=True."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000)
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()  # no backlog registered -- bytes_queued == 0

    has_gbr, pdb_ms, _guaranteed, _be = sched._dl_gbr_and_pdb(1, buffers, slot_index=0)
    assert has_gbr is True
    # bytes_queued == 0 -> best_remaining_pdb stays the C's own 9999
    # sentinel (never updated, since the update is gated on backlog).
    assert pdb_ms == 9999


def test_ul_gbr_deficit_gated_per_lcg_on_the_real_estimate():
    """gNB_scheduler_ulsch.c:2210 -- gated per-LCG on
    estimated_ul_buffer_per_lcg > 0, unlike DL's unconditional form. A
    UL GBR flow with a zero per-LCG estimate must NOT accumulate a
    deficit at all (has_gbr stays False)."""
    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="GBR", gfbr_bps=1_000_000, lcg=1,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=0, estimated_ul_buffer_per_lcg=0)

    has_gbr, pdb_ms, _guaranteed, _be = sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    assert has_gbr is False
    assert pdb_ms == 9999
    assert sched._ue_state[1].ul_lcg_deficit_bytes.get(1, 0) == 0


# -- 7. commit 3: UL's sched_inactive tier is a documented, permanent no-op

def test_ul_sched_inactive_never_fires_ranking_stays_coefficient_only():
    """ia_p5g_ul_cmp's revised form (ia_p5g_scheduler.c:2092-2111):
    sched_inactive is structurally absent here (no do_sched-equivalent
    signal), so _ul_rank_key collapses to (1, -coef) for every
    candidate, every time -- verified directly on the key, not inferred
    from a ranking outcome that could coincidentally match either way."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    from scheduler.two_tier import _Candidate

    c = _Candidate(ue_id=1, flows=[flow], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=5.0)
    assert sched._ul_rank_key(c) == (1, -5.0)
    c.sched_inactive = True  # never actually set by this scheduler, but
    assert sched._ul_rank_key(c) == (0, -5.0)  # the key itself is real


# -- 8. commit 3: _dl_rank_key/_ul_rank_key stay independently sourced -----


def test_dl_and_ul_rank_keys_stay_independently_sourced_not_deduped():
    """Guards against a future refactor collapsing these into one shared
    comparator just because their tuple shapes might look similar --
    DL's real comparator has 3 tiers, UL's revised one has 2, and they
    must stay textually and citationally distinct (same guard shape as
    reservation.py's own test_ul_and_dl_rank_keys_stay_independently_
    sourced_not_deduped)."""
    import inspect

    dl_src = inspect.getsource(TwoTier._dl_rank_key)
    ul_src = inspect.getsource(TwoTier._ul_rank_key)
    assert dl_src != ul_src
    # Check the actual return expressions, not the prose (which explains
    # UL's own has_gbr exclusion by name, a false positive for a bare
    # substring check).
    dl_return = dl_src.rsplit("return", 1)[-1]
    ul_return = ul_src.rsplit("return", 1)[-1]
    assert "candidate.has_gbr" in dl_return and "candidate.has_gbr" not in ul_return
    assert "candidate.sched_inactive" in ul_return and "candidate.sched_inactive" not in dl_return
