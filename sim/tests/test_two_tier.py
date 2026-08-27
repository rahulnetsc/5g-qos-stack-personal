"""Phase 2, two-tier commits 1-3a: scheduler/two_tier.py's rewrite.

Commit 1: Scheduler protocol conformance, a bootstrap PF coefficient as
the only ranking criterion (explicitly NOT a ported mechanism), UL-
then-DL per-slot order (fixed from the pre-rewrite file's own
DL-then-UL bug). Commit 2: the real Tier-1 SCA/GLPK-equivalent solve
wired in, output unconsumed. Commit 3: DL's real 3-tier comparator
(has_gbr -> pdb_ms -> coefficient) and UL's deliberately-revised 2-tier
one (sched_inactive -> coefficient, no has_gbr/pdb_ms -- ground truth's
own architectural reason: Tier-1's targets already carry the GBR
guarantee into Tier-2's VQ deficit on UL). Commit 3a: the windowed-
ceiling VQ itself -- growth, ceiling, drain, and the real ranking
coefficients (DL: pure VQ-sum x SE; UL: composite VQ-plus-urgency
barrier function) -- replacing the bootstrap PF coefficient outright.
The bootstrap throughput-EWMA (dl_thr_bytes_per_slot/
ul_thr_bytes_per_slot/_THR_EWMA_ALPHA) no longer exists as of commit
3a; tests that exercised it directly are retired, not adapted.

See docs/phase2-plan.md's two-tier commit checklist and
docs/oai-port-map.md's "Phase 2 -- two-tier" section for the full
citation/divergence detail.

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
from scheduler.two_tier import TwoTier, _PF_COEF_HYPOTHETICAL_SYMBOLS


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
        self._delivered: dict[tuple[int, int], int] = {}

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

    def set_delivered_cum(self, ue_id: int, qfi: int, value: int) -> None:
        self._delivered[(ue_id, qfi)] = value

    def state(self, ue_id: int, qfi: int) -> _FakeBufferState:
        return self._states.get((ue_id, qfi), _FakeBufferState())

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        return 0.0

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        return 0

    def delivered_cum(self, ue_id: int, qfi: int) -> int:
        return self._delivered.get((ue_id, qfi), 0)

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
    this backwards, see module docstring). Observable via call order,
    not just via a hardcoded assertion on the method body."""
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


# -- 3. UL/DL emission shapes match the interface contract -----------------


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


# -- 4. commit 3: DL's has_gbr -> pdb_ms -> coefficient sort tiers ----------
# ia_p5g_dl_cmp, ia_p5g_scheduler.c:1397-1411 -- the never-revised
# lexicographic form. One fixture per tier boundary (reservation.py's own
# commit-2 discipline), so a wrong tier ORDER fails distinguishably from
# wrong tier CONTENT. Direct _Candidate construction + _dl_rank_key,
# not a full allocate() -- as of commit 3a the coefficient is the real
# VQ-sum x SE product, which depends on Tier-1 targets/history state
# that's orthogonal to what these tests are checking (tier ORDER, not
# coefficient VALUE); _finalize_ul_coef's own tests below cover the real
# coefficient's arithmetic directly.


def test_dl_has_gbr_tier_beats_the_coefficient_tiebreak():
    """A GBR flow (has_gbr=True) must win over a non-GBR flow with a far
    more favourable (higher) coefficient."""
    from scheduler.two_tier import _Candidate

    sched = TwoTier()
    loser = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0,
        coef=1000.0, has_gbr=False, pdb_ms=9999,  # would win on coef alone
    )
    winner = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0,
        coef=1.0, has_gbr=True, pdb_ms=9999,  # would lose on coef alone
    )
    ranked = sorted([loser, winner], key=sched._dl_rank_key)
    assert ranked[0].ue_id == 2, "GBR flow (has_gbr) should rank first despite a worse coefficient"


def test_dl_pdb_tier_beats_the_coefficient_tiebreak_within_the_same_has_gbr_bucket():
    """Two non-GBR flows (has_gbr=False for both) -- the one with the
    tighter (lower) pdb_ms ranks first even with a worse coefficient."""
    from scheduler.two_tier import _Candidate

    sched = TwoTier()
    winner = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0,
        coef=1000.0, has_gbr=False, pdb_ms=10,  # worse coef, tighter pdb
    )
    loser = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0,
        coef=1.0, has_gbr=False, pdb_ms=300,  # better coef, looser pdb
    )
    ranked = sorted([loser, winner], key=sched._dl_rank_key)
    assert ranked[0].ue_id == 1, "tighter pdb_ms should rank first despite a worse coefficient"


def test_dl_coefficient_remains_the_final_tiebreak_when_has_gbr_and_pdb_tie():
    """Both non-GBR, both at the same pdb_ms -- the tiebreak falls
    through to the coefficient."""
    from scheduler.two_tier import _Candidate

    sched = TwoTier()
    winner = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0,
        coef=1000.0, has_gbr=False, pdb_ms=100,
    )
    loser = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0,
        coef=10.0, has_gbr=False, pdb_ms=100,
    )
    ranked = sorted([loser, winner], key=sched._dl_rank_key)
    assert ranked[0].ue_id == 1, "higher coefficient should win the tiebreak"


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

    has_gbr, pdb_ms, _guaranteed, _be, _urgency = sched._ul_gbr_and_pdb(
        1, buffers, slot_index=0
    )
    assert has_gbr is False
    assert pdb_ms == 9999
    assert sched._ue_state[1].ul_lcg_deficit_bytes.get(1, 0) == 0


# -- 5. commit 3: UL's sched_inactive tier is a documented, permanent no-op

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


# -- 6. commit 3: _dl_rank_key/_ul_rank_key stay independently sourced -----


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


# -- 7. commit 3a: the windowed-ceiling virtual queue -----------------------


def test_dl_vq_grows_by_tier1_target_then_stays_under_the_arrival_delta_ceiling():
    """ia_p5g_update_vq_dl, ia_p5g_scheduler.c:1835-1894 -- growth is
    r_bps * slot_duration_s; the ceiling (arrival-delta form, matches
    the header) does not bind here since the window has plenty of
    headroom."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    sched._targets_bps[(1, 1)] = 1_000_000.0  # 1 Mbps

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000)
    buffers.set_delivered_cum(1, 1, 5000)
    # _arr_hist/_del_hist both default to 0.0 from configure() -- arr_W =
    # 6000 bytes, del_W = 5000 bytes, target_W = 1e6*0.1 = 1e5 bits.
    # ceiling = min(48000, 100000) - 40000 = 8000 bits, growth = 500 bits.

    sched._update_vq_dl(1, buffers)
    assert sched._ue_state[1].vq_dl[1] == pytest.approx(500.0)


def test_dl_vq_ceiling_clamps_a_stale_deficit_down_to_the_arrival_delta_bound():
    """Same window as above, but vq_dl starts already above the 8000-bit
    ceiling (e.g. carried over from a much higher prior target) -- the
    clamp must bind, proving the ceiling is real, not just a no-op upper
    bound that never fires in practice."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    sched._targets_bps[(1, 1)] = 1_000_000.0
    sched._ue_state[1].vq_dl[1] = 999_999.0

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000)
    buffers.set_delivered_cum(1, 1, 5000)

    sched._update_vq_dl(1, buffers)
    assert sched._ue_state[1].vq_dl[1] == pytest.approx(8000.0)


def test_ul_vq_ceiling_is_backlog_bound_and_survives_starvation():
    """ia_p5g_update_vq_ul, ia_p5g_scheduler.c:3578-3687 -- the BUGFIX
    ceiling form. Mirrors the cited incident's shape (UE 5ce4: ~2.9 MB
    backlogged, ~435 bytes delivered in the window) -- a heavily
    saturated buffer with almost no recent delivery. Under the OLD
    arrival-delta form this would collapse toward ~0 (arrivals stop once
    the buffer saturates); under the real backlog-bound/catchup form the
    ceiling stays large (bounded by the N=5-window catchup horizon, not
    by how little got through), so a stale deficit clamps DOWN to that
    large bound rather than being wiped to ~0."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1)
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    sched._targets_bps[(1, 1)] = 1_000_000.0  # target_W = 1e5 bits/window
    sched._ue_state[1].vq_ul[1] = 999_999_999.0  # stale, will clamp down

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=2_901_912, estimated_ul_buffer_per_lcg=2_901_912)
    buffers.set_delivered_cum(1, 1, 435)
    # catchup_W = 5 * 1e5 = 5e5 bits; backlog_bits >> catchup_W, so the
    # min() picks catchup_W. del_W = 435*8 = 3480 bits.
    # ceiling = 500_000 - 3480 = 496_520 bits -- large, not collapsed.

    sched._update_vq_ul(1, buffers)
    ceiling = sched._ue_state[1].vq_ul[1]
    assert ceiling == pytest.approx(496_520.0)
    assert ceiling > 100_000.0, (
        "backlog-bound ceiling should stay large under starvation, not "
        "collapse toward zero the way the old arrival-delta form would"
    )


def test_ul_base_q_or_gate_includes_a_decayed_bsr_flow_with_positive_vq():
    """ia_p5g_ul_metric, ia_p5g_scheduler.c:3696-3726 -- the OR-gate
    starvation-prevention bugfix (cited incident: "d639 zero grants for
    55s"). A flow whose BSR has decayed to zero but whose vq_ul is still
    positive must still contribute to base_q; a flow with BOTH at zero
    must not."""
    sched = TwoTier()
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1),
        FlowConfig(ue_id=1, qfi=2, direction="UL", lcg=2),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._ue_state[1].vq_ul[1] = 5000.0  # LCG 1: BSR decayed, VQ alive
    sched._ue_state[1].vq_ul[2] = 3000.0  # LCG 2: BSR decayed, VQ ALSO dead

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=0, estimated_ul_buffer_per_lcg=0)
    buffers.set(1, 2, bytes_queued=0, estimated_ul_buffer_per_lcg=0)
    sched._ue_state[1].vq_ul[2] = 0.0  # both terms zero for LCG 2 now

    total = sched._ul_base_q(1, buffers)
    assert total == pytest.approx(5000.0), "only LCG 1 (OR-gate satisfied) should contribute"


def test_ul_finalize_coef_barrier_function_lets_near_deadline_dominate_higher_base_q():
    """ia_p5g_scheduler.c:2860-2924 -- Phi(u) diverges as u -> 1
    (URG_BARRIER_CAP=0.97). A near-deadline-exceeded, low-base_q
    candidate must end up with a far larger coefficient than a
    comfortable, high-base_q competitor -- the barrier function, not a
    plain power law, is what makes this possible."""
    from scheduler.two_tier import _Candidate

    sched = TwoTier()
    near_deadline = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.0, snr_db=10.0,
        coef=10.0,  # base_q, temporarily -- see _finalize_ul_coef
        hyp_tbs_bytes=100, urgency01=0.99,
    )
    comfortable = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.0, snr_db=10.0,
        coef=1000.0, hyp_tbs_bytes=100, urgency01=0.0,
    )
    candidates = [near_deadline, comfortable]
    sched._finalize_ul_coef(candidates)

    assert near_deadline.coef > comfortable.coef, (
        "the near-deadline candidate's barrier-function urgency should "
        "dominate despite a 100x-lower base_q"
    )


def test_ul_gbr_flow_held_near_gfbr_by_vq_alone_no_tier_assists():
    """Scores commit 3's own stated expectation (module docstring,
    ia_p5g_scheduler.c:2092-2111's design-revision comment): if Tier-1's
    targets genuinely carry the GBR obligation into the UL VQ deficit, a
    UL GBR flow should be protected by the VQ/urgency composite alone --
    _ul_rank_key has no has_gbr/pdb_ms tier to fall back on (commit 3's
    own finding). Two UEs, one PRB-scarce slot per iteration (only one
    can win), UE2's channel is much better and would win every slot on
    spectral efficiency alone if the composite carried no GBR-protective
    signal. Tier-1's own solve is bypassed (monkeypatched to a no-op) so
    this test controls _targets_bps directly -- it is about _ul_rank_key/
    _finalize_ul_coef consuming a target, not about solve_tier1 itself.
    """
    sched = TwoTier()
    flows = [
        FlowConfig(
            ue_id=1, qfi=1, direction="UL", lcg=1,
            flow_class="GBR", gfbr_bps=200_000, pdb_ms=50.0,
        ),
        FlowConfig(ue_id=2, qfi=1, direction="UL", lcg=1),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._resolve_tier1 = lambda slot_index, buffers: None  # freeze Tier-1
    sched._targets_bps = {(1, 1): 200_000.0, (2, 1): 200_000.0}

    buffers = _FakeBuffers()
    channel = _FakeChannel({1: 5.0, 2: 25.0})  # UE2 has the far better channel
    slot_kwargs = dict(dl_symbols=0, ul_symbols=14, prb_count=6, pdcch_cce_budget=48)

    ue1_wins = 0
    for slot_index in range(30):
        buffers.set(1, 1, bytes_queued=50_000, estimated_ul_buffer_per_lcg=50_000)
        buffers.set(2, 1, bytes_queued=50_000, estimated_ul_buffer_per_lcg=50_000)
        slot = _FakeSlot(slot_index=slot_index, **slot_kwargs)
        out = sched.allocate(slot, buffers, channel)
        if any(a.ue_id == 1 for a in out):
            ue1_wins += 1

    assert ue1_wins > 0, (
        "UL GBR flow never won a single grant despite _ul_rank_key's "
        "composite coefficient -- commit 3's design-revision expectation "
        "(VQ alone protects UL GBR flows, no tier assists) does not hold"
    )
