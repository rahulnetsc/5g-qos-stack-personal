"""Phase 2, two-tier commits 1-4b: scheduler/two_tier.py's rewrite.

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

Commit 4: the UL service-interval floor's arm/fire state machine
(delivery-history arming, evidence-based deficit forgiveness, two
independently-capped exponential backoffs) plus a THIRD comparator
tier (floor_fire, between sched_inactive and coef) the design-revision
comment commit 3 quoted ("exactly TWO tiers") turned out not to
describe -- a comment accurate when written, overtaken by a later
change to the code it describes, a new finding category distinct from
this port's four OAI-inherited comment-vs-code mismatches and its one
self-inflicted citation error. Grant-sizing (the GBR-PRB-reserve cap,
the floor's own uncapped-to-bwpSize sizing, the PHR-based PRB ceiling)
was deferred to commit 4a -- commit 4's own grant-sizing change was the
minimum needed for the floor to have any observable effect at all (a
fixed min_rb-sized rescue grant), not that fuller bypass.

Commit 4a: FIX-2 (the GBR-PRB-reserve cap, `gbr_below`) and the floor's
own uncapped-to-max_rbSize sizing, replacing commit 4's fixed min_rb
rescue grant. Confirmed structurally inert on this corpus on TWO
independent grounds -- the floor never fires (commit 4's own confirmed
result) AND mfbr_bps is never configured on any flow in any scenario
in this repo, so gbr_below's own reverse-scan condition never fires
either (the identical fact reservation.py's own already-landed
gbr_bytes_slot found for the same quantity). Both mechanisms ported as
real, fully testable machinery anyway -- this port's standing practice
for confirmed-currently-unreachable mechanisms. PHR-based capping
stays structurally out of scope entirely (not merely deferred), the
same disposition reservation.py's own commit 4a already recorded for
the identical connection point.

Commit 4b: B_eff, the deficit-accumulated UL grant-sizing target,
wired into ordinary (non-floor-fired) DATA sizing. ul_total_target_
bytes -- confirmed to NOT equal guaranteed_bytes+be_bytes despite the
similar shape (the GBR-LCG overflow term be_bytes includes,
ul_total_target_bytes excludes) -- is a real, testable third
accumulator inside _ul_gbr_and_pdb's own loop. This port's own port-map
row 46 said guaranteed_bytes+be_bytes would be "reused directly" for
this consumption -- checked here, not executed unchecked, and found
wrong: this port's SECOND self-inflicted finding, distinct in kind from
_dl_stamp's own stale citation at commit 3a (a wrong citation vs. a
wrong plan). reservation.py's own already-landed _ul_grant_target
confirmed NOT a template either (different baseline formula, and a
has_srb control-only cap two-tier's own C genuinely lacks) -- a third
instance of "a similar-looking mechanism differs structurally," after
FIX-2's own two divergences at commit 4a. D1 (reservation's own sizing
decision -- size PRBs off the target, cap delivered bytes at true
backlog) IS reused directly, the one piece of the "template" that does
transfer.

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
from scheduler.two_tier import TwoTier, _Candidate, _PF_COEF_HYPOTHETICAL_SYMBOLS


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

    has_gbr, pdb_ms, _guaranteed, _be, _urgency, _gbr_bytes_slot, _target = (
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    )
    assert has_gbr is False
    assert pdb_ms == 9999
    assert sched._ue_state[1].ul_lcg_deficit_bytes.get(1, 0) == 0


# -- 5. commit 3: UL's sched_inactive tier is a documented, permanent no-op

def test_ul_sched_inactive_never_fires_ranking_stays_coefficient_only():
    """ia_p5g_ul_cmp's revised Tier-1 form (ia_p5g_scheduler.c:2117-2120):
    sched_inactive is structurally absent here (no do_sched-equivalent
    signal), so this tier position collapses to always-1 (never the
    top) for every candidate -- verified directly on the key, not
    inferred from a ranking outcome that could coincidentally match
    either way. Tier 1.5 (floor_fire, commit 4) also defaults inert
    here since this candidate never fired."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())

    c = _Candidate(ue_id=1, flows=[flow], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=5.0)
    assert sched._ul_rank_key(c) == (1, 1, 0, -5.0)
    c.sched_inactive = True  # never actually set by this scheduler, but
    assert sched._ul_rank_key(c) == (0, 1, 0, -5.0)  # the key itself is real


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


# -- 8. commit 4: the UL service-interval floor -----------------------------
# Fixtures below arm the floor with one _update_ul_floor(...slot_index=0)
# call (delivered_cum != the default floor_rx_lastseen=0 triggers the
# "movement" branch, which arms), then manipulate _UeState's floor_*
# fields directly to isolate one state-transition boundary per test --
# matching this port's own "one fixture per tier/transition boundary"
# discipline, not a single fully-simulated multi-slot run per test.
#
# Shared arithmetic used throughout (slot_duration_s=0.0005 -> slot_ms=0.5):
#   pdb_ms=80.0  ->  theta = max(2, round((80/8)/0.5)) = 20 slots
#   _UL_FLOOR_ALIVE_MS=2000  ->  alive_max = 2000/0.5 = 4000 slots
#   _UL_FLOOR_FRUITLESS_DECAY_MS=500  ->  fr_decay = 500/0.5 = 1000 slots


def _floor_flow(ue_id: int = 1, lcg: int = 1, pdb_ms: float = 80.0) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=1, direction="UL", lcg=lcg,
        flow_class="GBR", gfbr_bps=100_000, mfbr_bps=200_000, pdb_ms=pdb_ms,
    )


def _floor_desynced_buffers(ue_id: int = 1) -> _FakeBuffers:
    """A UE with real backlog (arms has_pending_gbr) but bytes_reported
    == 0 (the B==0 blackout condition the floor exists to catch)."""
    buffers = _FakeBuffers()
    buffers.set(ue_id, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)
    buffers._states[(ue_id, 1)].bytes_reported = 0
    buffers.set_delivered_cum(ue_id, 1, 100)
    return buffers


def test_ul_floor_does_not_arm_or_touch_state_without_has_pending_gbr():
    """gNB_scheduler_ulsch.c:42-71 -- has_pending_gbr false (no LCG with
    both current backlog AND mfbr_bps>0) means the C skips the WHOLE
    block; ported the same way -- no state advances at all, not even
    the delivery-history bookkeeping."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1, flow_class="PF")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    state = sched._ue_state[1]
    state.floor_fruitless = 5  # pre-seeded -- must survive untouched

    fired, sil = sched._update_ul_floor(1, buffers, slot_index=100)
    assert fired is False
    assert sil == 0
    assert state.floor_fruitless == 5
    assert state.floor_alive_slot is None


def test_ul_has_pending_gbr_is_mfbr_keyed_not_gfbr_keyed():
    """gNB_scheduler_ulsch.c:65-66 -- gates on gbr_ul_max (mfbr_bps),
    NOT gbr_ul_guaranteed (gfbr_bps) -- a GBR flow with gfbr_bps>0 but
    mfbr_bps==0 must NOT count, even though it clearly has a GBR
    classification and _ul_gbr_and_pdb's OWN has_gbr would react to it."""
    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", lcg=1,
        flow_class="GBR", gfbr_bps=100_000, mfbr_bps=0.0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)

    assert sched._ul_has_pending_gbr(1, buffers) is False


def test_ul_best_pending_pdb_ms_picks_highest_priority_backlogged_lcg():
    """gNB_scheduler_ulsch.c:42-71 -- the PDB of the HIGHEST-PRIORITY
    currently-backlogged LCG, not literally the lowest PDB value (the
    C struct field's own comment is misleading -- this method's
    docstring corrects it)."""
    sched = TwoTier()
    flows = [
        FlowConfig(
            ue_id=1, qfi=1, direction="UL", lcg=1, priority_level=50,
            pdb_ms=10.0,  # lower PDB, but LOWER priority (higher number)
        ),
        FlowConfig(
            ue_id=1, qfi=2, direction="UL", lcg=2, priority_level=5,
            pdb_ms=90.0,  # higher PDB, but HIGHER priority (lower number)
        ),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100, estimated_ul_buffer_per_lcg=100)
    buffers.set(1, 2, bytes_queued=100, estimated_ul_buffer_per_lcg=100)

    assert sched._ul_best_pending_pdb_ms(1, buffers) == 90


def test_ul_best_pending_pdb_ms_own_fallback_is_100ms_not_300ms():
    """Confirmed a DIFFERENT constant from _PDB_FALLBACK_MS (300ms,
    used by _dl_gbr_and_pdb/_ul_gbr_and_pdb for a different purpose)."""
    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1, pdb_ms=0.0)
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100, estimated_ul_buffer_per_lcg=100)

    assert sched._ul_best_pending_pdb_ms(1, buffers) == 100


def test_ul_floor_fires_after_theta_slots_of_silence_on_a_backlogged_ue():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()

    fired, _ = sched._update_ul_floor(1, buffers, slot_index=0)
    assert fired is False  # first sight only arms

    fired, sil = sched._update_ul_floor(1, buffers, slot_index=20)  # theta=20
    assert fired is True
    assert sil == 20


def test_ul_floor_fruitless_shift_caps_at_16x_not_beyond():
    """FRUITLESS_SHIFT_MAX=4 -- the checklist's "16x cap" and "caps at
    exactly 4" are the same fact (theta_eff = theta << shift, 2**4=16),
    not two disagreeing numbers."""
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_fruitless = 10  # far past the shift cap
    state.floor_fruitless_slot = 0
    state.floor_last_move_slot = 0

    # Capped theta_eff = 20 << 4 = 320. Below it: must not fire even
    # though an UNCAPPED theta<<10 would put the threshold far higher.
    fired, _ = sched._update_ul_floor(1, buffers, slot_index=300)
    assert fired is False

    fired, sil = sched._update_ul_floor(1, buffers, slot_index=320)
    assert fired is True
    assert sil == 320


def test_ul_floor_fruitless_decays_one_step_per_500ms_of_no_further_fires():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_fruitless = 3
    state.floor_fruitless_slot = 0
    state.floor_last_move_slot = 990  # small sil at slot 1000 -- isolates decay from a refire
    state.floor_alive_slot = 0

    fired, _ = sched._update_ul_floor(1, buffers, slot_index=1000)  # exactly one fr_decay period
    assert fired is False
    assert state.floor_fruitless == 2
    assert state.floor_fruitless_slot == 1000


def test_ul_floor_forgiveness_gate_is_exactly_fruitless_max_not_off_by_one():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_fruitless = 2  # one below FRUITLESS_MAX=3
    state.floor_fruitless_slot = 0
    state.floor_last_move_slot = 0
    state.floor_alive_slot = 0
    state.ul_lcg_deficit_bytes[1] = 500

    theta_eff = 20 << 2  # 80
    fired, _ = sched._update_ul_floor(1, buffers, slot_index=theta_eff)
    assert fired is True
    assert state.floor_disarmed is False
    assert state.ul_lcg_deficit_bytes[1] == 500


def test_ul_floor_forgiveness_fires_exactly_at_fruitless_max_and_clears_deficit():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_fruitless = 3  # == FRUITLESS_MAX
    state.floor_fruitless_slot = 0
    state.floor_last_move_slot = 0
    state.floor_alive_slot = 0
    state.ul_lcg_deficit_bytes[1] = 500

    theta_eff = 20 << 3  # shift = min(3, 4) = 3 -> 160
    fired, _ = sched._update_ul_floor(1, buffers, slot_index=theta_eff)
    assert fired is True
    assert state.floor_disarmed is True
    assert state.ul_lcg_deficit_bytes[1] == 0


def test_ul_floor_forgiveness_is_one_time_while_already_disarmed():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_fruitless = 3
    state.floor_disarmed = True  # already disarmed by an earlier fire
    state.floor_fruitless_slot = 0
    state.floor_last_move_slot = 0
    state.floor_alive_slot = 0
    state.ul_lcg_deficit_bytes[1] = 777  # accrued again since the earlier clear

    theta_eff = 20 << 3
    fired, _ = sched._update_ul_floor(1, buffers, slot_index=theta_eff)
    assert fired is True
    assert state.ul_lcg_deficit_bytes[1] == 777  # NOT re-cleared -- guard skips


def test_ul_floor_adq_requires_both_crumb_run_and_elapsed_period():
    """crumb_run>=8 is necessary, not sufficient -- the real gate is
    crumb_run>=8 AND adq_age>=adq_period."""
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)
    buffers._states[(1, 1)].bytes_reported = 1000  # trickle, not blackout: B>0
    buffers.set_delivered_cum(1, 1, 100)
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_crumb_run = 8  # >= ADQ_CRUMB_RUN
    state.floor_last_move_slot = 0
    state.floor_alive_slot = 0
    state.floor_adq_slot = 0

    # adq_period at floor_adq_backoff=0: theta_eff(20) << 0 = 20.
    fired, _ = sched._update_ul_floor(1, buffers, slot_index=10)
    assert fired is False  # crumb_run satisfied, period not yet elapsed

    fired, _ = sched._update_ul_floor(1, buffers, slot_index=20)
    assert fired is True


def test_ul_floor_adq_does_not_fire_below_the_crumb_run_threshold():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)
    buffers._states[(1, 1)].bytes_reported = 1000
    buffers.set_delivered_cum(1, 1, 100)
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_crumb_run = 7  # one below ADQ_CRUMB_RUN
    state.floor_last_move_slot = 0
    state.floor_alive_slot = 0
    state.floor_adq_slot = 0

    fired, _ = sched._update_ul_floor(1, buffers, slot_index=100_000)
    assert fired is False


def test_ul_floor_real_delivery_immediately_resets_fruitless_and_disarm():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    state = sched._ue_state[1]
    state.floor_fruitless = 4
    state.floor_disarmed = True
    state.floor_rx_lastseen = 100

    buffers.set_delivered_cum(1, 1, 250)  # real bytes moved
    fired, sil = sched._update_ul_floor(1, buffers, slot_index=500)
    assert fired is False  # silence resets to 0 on movement, can't fire this call
    assert sil == 0
    assert state.floor_fruitless == 0
    assert state.floor_disarmed is False
    assert state.floor_rx_lastseen == 250


def test_ul_floor_never_armed_ue_does_not_fire_regardless_of_elapsed_slots():
    """A UE whose delivered_cum has ALWAYS been exactly 0 never
    triggers the "movement" branch (0 != 0 is false), so it never arms
    -- a real property of the zero-init comparison, not a Python
    artifact (the C's own zero-initialized floor_rx_lastseen has the
    identical property when _rx is genuinely always 0)."""
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)
    buffers._states[(1, 1)].bytes_reported = 0
    # delivered_cum left at the default 0.

    fired, _ = sched._update_ul_floor(1, buffers, slot_index=10_000)
    assert fired is False
    assert sched._ue_state[1].floor_alive_slot is None


def test_ul_floor_idle_beyond_alive_window_does_not_fire():
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    sched._update_ul_floor(1, buffers, slot_index=0)  # arm

    fired, _ = sched._update_ul_floor(1, buffers, slot_index=4001)  # > ALIVE_MS
    assert fired is False


def test_ul_floor_has_pending_gbr_gate_reads_the_same_estimate_it_exists_to_route_around():
    """Flagged, not resolved (module docstring / README.md sec7): the
    floor's own arming precondition (has_pending_gbr) is gated on
    estimated_ul_buffer_per_lcg > 0 -- the SAME per-LCG estimate the
    floor exists to route around. This test establishes only that the
    PORT follows the C faithfully (has_pending_gbr reads False, so the
    floor never arms) when a UE's only GBR LCG has desynced to 0 -- it
    does NOT establish that real hardware has this gap: a real gNB may
    have a path this simulator cannot produce (another LCG staying
    genuinely backlogged, an SR-triggered BSR refresh landing the same
    slot, timing that keeps the estimate briefly nonzero)."""
    sched = TwoTier()
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    # The desync itself: estimated_ul_buffer_per_lcg reads 0 even though
    # the UE holds real data (bytes_queued > 0, the TRUE backlog).
    buffers.set(1, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=0)
    buffers._states[(1, 1)].bytes_reported = 0

    assert sched._ul_has_pending_gbr(1, buffers) is False
    fired, _ = sched._update_ul_floor(1, buffers, slot_index=100_000)
    assert fired is False


def test_ul_floor_track_crumb_run_increments_on_min_rb_grants_resets_above():
    sched = TwoTier(min_rb=5)
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    state = sched._ue_state[1]

    sched._ul_floor_track_crumb_run(1, prbs_used=5)  # == min_rb
    sched._ul_floor_track_crumb_run(1, prbs_used=3)  # < min_rb
    assert state.floor_crumb_run == 2

    sched._ul_floor_track_crumb_run(1, prbs_used=6)  # > min_rb
    assert state.floor_crumb_run == 0


# -- 9. commit 4: _ul_rank_key's new Tier 1.5 --------------------------------


def test_ul_floor_fire_outranks_ordinary_coefficient_regardless_of_value():
    sched = TwoTier()
    loser = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=1_000_000.0,
    )
    winner = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=0.0,
        floor_fire=True, floor_sil=5,
    )
    ranked = sorted([loser, winner], key=sched._ul_rank_key)
    assert ranked[0].ue_id == 2


def test_ul_floor_fire_ties_break_on_longer_silence_first():
    sched = TwoTier()
    shorter = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=5.0,
        floor_fire=True, floor_sil=50,
    )
    longer = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=5.0,
        floor_fire=True, floor_sil=200,
    )
    ranked = sorted([shorter, longer], key=sched._ul_rank_key)
    assert ranked[0].ue_id == 2


def test_ul_floor_fire_still_ranks_below_sched_inactive():
    sched = TwoTier()
    inactive = _Candidate(
        ue_id=1, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=0.0,
        sched_inactive=True,
    )
    floor_ue = _Candidate(
        ue_id=2, flows=[], bits_per_rb=100, bler=0.1, snr_db=20.0, coef=1000.0,
        floor_fire=True, floor_sil=999,
    )
    ranked = sorted([floor_ue, inactive], key=sched._ul_rank_key)
    assert ranked[0].ue_id == 1


# -- 10. commit 4: the candidacy-rescue pre-pass -----------------------------


def test_ul_floor_candidacy_rescue_only_adds_ues_that_actually_fired():
    """Watch-item from plan approval: the pre-pass must not become a
    periodic wake-up for every GBR-configured UE -- only a UE whose
    floor genuinely fires (armed AND past its own theta/adq_period)
    gets added back to the candidate set. UE 2 here is GBR-configured
    and equally excluded by the bytes_reported>0 pre-filter, but has
    NO delivery history at all (never armed) -- it must stay excluded."""
    sched = TwoTier()
    flows = [_floor_flow(ue_id=1), _floor_flow(ue_id=2)]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    channel = _FakeChannel({1: 20.0, 2: 20.0})

    buffers.set(1, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)
    buffers._states[(1, 1)].bytes_reported = 0
    buffers.set(2, 1, bytes_queued=5000, estimated_ul_buffer_per_lcg=5000)
    buffers._states[(2, 1)].bytes_reported = 0

    # UE 1: pre-armed as if a delivery happened at slot 0 -- silence
    # will have reached theta=20 by the slot this test allocates at.
    state1 = sched._ue_state[1]
    state1.floor_alive_slot = 0
    state1.floor_last_move_slot = 0
    state1.floor_rx_lastseen = 100
    buffers.set_delivered_cum(1, 1, 100)  # matches floor_rx_lastseen -- no fresh movement
    # UE 2: delivered_cum left at 0 == default floor_rx_lastseen -- never arms.

    slot = _FakeSlot(
        slot_index=20, dl_symbols=0, ul_symbols=14, prb_count=6, pdcch_cce_budget=48,
    )
    out = sched.allocate(slot, buffers, channel)

    granted_ues = {a.ue_id for a in out}
    assert 1 in granted_ues, "UE1's floor should have fired and rescued it"
    assert 2 not in granted_ues, "UE2 never armed -- must NOT be rescued just for being GBR-configured"


# -- 11. commit 4a: gbr_bytes_slot -- max, not sum; no max(1,...) floor -----


def test_ul_gbr_bytes_slot_positive_is_max_not_sum_and_has_no_floor_at_one():
    """ia_p5g_scheduler.c:2710-2722 -- confirmed already ported once, in
    reservation.py's own commit 4a: gbr_bytes_slot lacks the max(1,...)
    floor _ul_gbr_and_pdb's own `obligation` applies fifty-ish lines
    earlier in the real C. A tiny gfbr_bps truncates to 0 here even
    though has_gbr (obligation-floored) reads True for the identical
    flow -- a real, precise asymmetry, not a rounding accident."""
    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", lcg=1,
        flow_class="GBR", gfbr_bps=1_000, mfbr_bps=200_000, pdb_ms=100.0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100, estimated_ul_buffer_per_lcg=100)

    has_gbr, _pdb, _guar, _be, _urg, gbr_bytes_slot, _target = (
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    )
    # gfbr_bps=1000 / 8 / slots_per_sec(2000) = 0.0625 -> int() truncates
    # to 0, uncontested by any floor.
    assert gbr_bytes_slot == 0
    assert has_gbr is True, "has_gbr's own max(1,...) floor should still fire here"


def test_ul_gbr_bytes_slot_positive_false_without_mfbr_even_with_real_gfbr():
    """The has_pending_gbr gate is MFBR-keyed (gbr_ul_max), not
    GFBR-keyed -- a real, well-provisioned GBR flow with mfbr_bps == 0
    (this repo's own default, and the value every scenario in this repo
    actually configures) never activates gbr_bytes_slot regardless of
    how large gfbr_bps is."""
    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", lcg=1,
        flow_class="GBR", gfbr_bps=1_000_000, mfbr_bps=0.0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100, estimated_ul_buffer_per_lcg=100)

    _has_gbr, _pdb, _guar, _be, _urg, gbr_bytes_slot, _target = (
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    )
    assert gbr_bytes_slot == 0


# -- 12. commit 4a: FIX-2, the GBR-PRB reserve -------------------------------


def test_fix2_reserve_is_inert_without_a_live_obligation_gbr_ue_ranked_below():
    """gbr_below[i] == 0 when no downstream candidate has both has_gbr
    and gbr_bytes_slot_positive -- confirmed inert in the common case,
    the same disposition this corpus has for every real scenario
    (mfbr_bps never configured, module docstring)."""
    sched = TwoTier(min_rb=5)
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1, flow_class="PF")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000, estimated_ul_buffer_per_lcg=1000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    assert len(out) == 1
    assert out[0].bytes_capacity == 1000, "uncapped by any reserve absent a downstream GBR UE"


def test_fix2_reserve_protects_a_downstream_gbr_ue_from_a_saturating_leader():
    """ia_p5g_scheduler.c:2987-3007's own cited incident, mirrored
    directly: a saturating non-GBR UE ranked ahead of a live-obligation
    GBR UE must not consume the PRBs FIX-2 reserves for that GBR UE."""
    sched = TwoTier(min_rb=5)
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1, flow_class="PF"),
        FlowConfig(
            ue_id=2, qfi=1, direction="UL", lcg=1,
            flow_class="GBR", gfbr_bps=100_000, mfbr_bps=200_000, pdb_ms=100.0,
        ),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._resolve_tier1 = lambda slot_index, buffers: None  # freeze Tier-1
    # UE1 dominates the coefficient (huge VQ growth) so it ranks first
    # despite not being the one FIX-2 exists to protect.
    sched._targets_bps = {(1, 1): 5_000_000.0, (2, 1): 1.0}

    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100_000, estimated_ul_buffer_per_lcg=100_000)
    buffers.set(2, 1, bytes_queued=50, estimated_ul_buffer_per_lcg=50)
    channel = _FakeChannel({1: 20.0, 2: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=10, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)

    by_ue = {a.ue_id for a in out}
    assert by_ue == {1, 2}, f"the GBR UE must still get a grant, got {by_ue}"
    ue1_prbs = sum(a.prbs for a in out if a.ue_id == 1)
    assert ue1_prbs <= 5, (
        f"the saturating leader must be capped by the FIX-2 reserve "
        f"(min_rb=5 for the one live-obligation GBR UE ranked below it), "
        f"got {ue1_prbs} PRBs"
    )


# -- 13. commit 4a: floor-fire sizing now uses max_rbSize, not fixed min_rb -


def test_ul_floor_fire_grant_is_bounded_by_max_rbSize_not_fixed_min_rb():
    """Commit 4a: a fired floor's grant is sized to max_rbSize (the
    whole slot, absent any GBR-PRB reserve), replacing commit 4's own
    fixed min_rb rescue grant."""
    sched = TwoTier(min_rb=5)
    sched.configure([_floor_flow()], slot_duration_s=0.0005, grid=_grid())
    buffers = _floor_desynced_buffers()
    channel = _FakeChannel({1: 20.0})

    state = sched._ue_state[1]
    state.floor_alive_slot = 0
    state.floor_last_move_slot = 0
    state.floor_rx_lastseen = 100  # matches _floor_desynced_buffers's delivered_cum

    slot = _FakeSlot(
        slot_index=20, dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48,
    )  # theta=20 for pdb_ms=80.0
    out = sched.allocate(slot, buffers, channel)

    assert len(out) == 1
    assert out[0].ue_grant is True
    assert out[0].prbs > 5, (
        f"a fired floor's grant should use the whole slot (max_rbSize), "
        f"not be capped at min_rb=5; got {out[0].prbs} PRBs"
    )


def test_ul_floor_fire_grant_also_respects_the_fix2_reserve():
    """ia_p5g_scheduler.c:3114-3117, "FIX-C": floor grants take the
    DATA-class path FIX-2 already protects, so they must also respect
    the reserve -- a fired floor must not consume PRBs reserved for a
    different, still-unserved GBR UE ranked below it."""
    sched = TwoTier(min_rb=5)
    flows = [
        _floor_flow(ue_id=1),
        FlowConfig(
            ue_id=2, qfi=1, direction="UL", lcg=1,
            flow_class="GBR", gfbr_bps=100_000, mfbr_bps=200_000, pdb_ms=100.0,
        ),
    ]
    sched.configure(flows, slot_duration_s=0.0005, grid=_grid())
    sched._resolve_tier1 = lambda slot_index, buffers: None
    sched._targets_bps = {}

    buffers = _floor_desynced_buffers(ue_id=1)
    buffers.set(2, 1, bytes_queued=50, estimated_ul_buffer_per_lcg=50)
    channel = _FakeChannel({1: 20.0, 2: 20.0})

    state1 = sched._ue_state[1]
    state1.floor_alive_slot = 0
    state1.floor_last_move_slot = 0
    state1.floor_rx_lastseen = 100

    slot = _FakeSlot(
        slot_index=20, dl_symbols=0, ul_symbols=14, prb_count=10, pdcch_cce_budget=48,
    )
    out = sched.allocate(slot, buffers, channel)

    ue1_grant = next((a for a in out if a.ue_id == 1), None)
    assert ue1_grant is not None and ue1_grant.ue_grant is True
    assert ue1_grant.prbs <= 5, (
        f"a fired floor's grant must still respect the FIX-2 reserve for "
        f"a downstream live-obligation GBR UE, got {ue1_grant.prbs}"
    )


# -- 14. commit 4b: ul_total_target_bytes vs. guaranteed_bytes+be_bytes -----


def test_ul_total_target_bytes_diverges_from_guaranteed_plus_be_on_gbr_overflow():
    """ia_p5g_scheduler.c:2649-2670 vs. the deficit loop's own
    guaranteed_bytes/be_bytes -- confirmed a real divergence, not a
    rounding artifact: ul_total_target_bytes excludes the GBR-LCG
    overflow term be_bytes includes. This port's own port-map row 46
    said these values would be "reused directly" for this consumption
    -- checked here, not executed unchecked, and found wrong (this
    port's second self-inflicted finding, distinct from _dl_stamp's
    stale citation at commit 3a)."""
    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", lcg=1,
        flow_class="GBR", gfbr_bps=16_000, mfbr_bps=0.0, pdb_ms=100.0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1000, estimated_ul_buffer_per_lcg=1000)

    _has_gbr, _pdb, guaranteed, be, _urg, _gbr_slot, ul_total_target_bytes = (
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    )
    assert guaranteed == 1
    assert be == 999  # the overflow: backlog(1000) - target(1)
    assert ul_total_target_bytes == 1  # target only -- NOT guaranteed+be (1000)
    assert ul_total_target_bytes != guaranteed + be


def test_ul_total_target_bytes_equals_guaranteed_plus_be_without_overflow():
    """The two DO coincide when a GBR flow's backlog never exceeds its
    computed target -- the divergence above is specifically about
    overflow, not a permanent inequality between the two quantities."""
    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", lcg=1,
        flow_class="GBR", gfbr_bps=16_000, mfbr_bps=0.0, pdb_ms=100.0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=1, estimated_ul_buffer_per_lcg=1)

    _has_gbr, _pdb, guaranteed, be, _urg, _gbr_slot, ul_total_target_bytes = (
        sched._ul_gbr_and_pdb(1, buffers, slot_index=0)
    )
    assert be == 0  # no overflow -- backlog(1) <= target(1)
    assert ul_total_target_bytes == guaranteed + be


# -- 15. commit 4b: B_eff sizes PRBs off the target, not raw backlog --------


def test_b_eff_uses_ul_total_target_bytes_when_it_exceeds_reported_backlog():
    """The non-GBR contribution to ul_total_target_bytes is the raw,
    per-LCG estimated_ul_buffer_per_lcg (frozen between BSRs, WP3/WP4's
    own confirmed invariant), not bytes_reported (drained on grant
    regardless of BSR timing) -- so ul_total_target_bytes can exceed
    ue_backlog even for a UE with NO GBR flows at all, sizing MORE PRBs
    than raw-backlog sizing would."""
    from scheduler.link import bits_per_prb

    sched = TwoTier()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", lcg=1, flow_class="PF")
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100, estimated_ul_buffer_per_lcg=5000)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=50, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    assert len(out) == 1
    assert out[0].bytes_capacity == 100  # D1: tbs_bytes capped at true backlog

    bits_per_rb, _bler = bits_per_prb(20.0, symbols=14)
    expected_prbs_for_backlog_alone = -(-(100 * 8) // bits_per_rb)
    expected_prbs_for_target = -(-(5000 * 8) // bits_per_rb)
    assert out[0].prbs > expected_prbs_for_backlog_alone
    assert out[0].prbs == min(50, expected_prbs_for_target)


def test_b_eff_gbr_target_exceeding_backlog_sizes_more_prbs_but_caps_bytes_at_backlog():
    """D1 (reservation.py's own commit-4a decision, reused directly):
    the target sizes PRBs, not delivered bytes. A deficit-carrying GBR
    flow's target can exceed its own true (reported) backlog -- more
    PRBs get granted than raw-backlog sizing would give, but tbs_bytes
    never manufactures bytes beyond what's actually queued."""
    from scheduler.link import bits_per_prb

    sched = TwoTier()
    flow = FlowConfig(
        ue_id=1, qfi=1, direction="UL", lcg=1,
        flow_class="GBR", gfbr_bps=800_000_000, mfbr_bps=0.0, pdb_ms=100.0,
    )
    sched.configure([flow], slot_duration_s=0.0005, grid=_grid())
    buffers = _FakeBuffers()
    buffers.set(1, 1, bytes_queued=100, estimated_ul_buffer_per_lcg=100)
    channel = _FakeChannel({1: 20.0})
    slot = _FakeSlot(dl_symbols=0, ul_symbols=14, prb_count=200, pdcch_cce_budget=48)

    out = sched.allocate(slot, buffers, channel)
    assert len(out) == 1
    assert out[0].bytes_capacity == 100  # never manufactured beyond true backlog

    bits_per_rb, _bler = bits_per_prb(20.0, symbols=14)
    expected_prbs_for_backlog_alone = -(-(100 * 8) // bits_per_rb)
    assert out[0].prbs > expected_prbs_for_backlog_alone, (
        "a deficit-driven target should size more PRBs than raw backlog alone"
    )
