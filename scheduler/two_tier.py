"""Two-tier 5G QoS scheduler -- rewritten from ``oai-branches/two-tier/``.

Phase 2 (``docs/phase2-plan.md``): unlike ``reservation.py``, this is a
rewrite of a scheduler that already had 1148 lines of pre-Phase-2 Python
and was wired into the regression corpus and ~65 test functions across
three files. The pre-rewrite file is preserved at git tag
``phase2-pre-twotier-rewrite`` (``dc1ab6a``) -- commit 8 diffs against it
directly. See ``docs/oai-port-map.md``'s "Phase 2 -- two-tier" section for
the file:line correspondence and ``docs/phase2-plan.md`` sec4 for the
full checklist.

This commit (1) is explicitly **not inert** -- unlike reservation's own
commit 1, this immediately changes the behavior of a scheduler already
exercised by the regression corpus and the wider test suite. It deletes,
outright, two mechanisms confirmed absent from real hardware
(``docs/phase2-plan.md`` sec2.1): SPS/Configured-Grant (``_SPSReservation``,
``_allocate_sps``, ``_is_sps_eligible``, and everything that fed them) and
the UL intra-TB per-flow byte-split estimators (``_shadow_lcp_split``/
``_occupancy_split``/``_estimate_ul_split``) that modeled something the
real gNB structurally cannot observe. It also drops, for now, the entire
old Tier-1 LP apparatus (``_resolve_tier1``, the "measured"/"tracking"
demand estimators, the adaptive dual-ascent GBR penalty, the max-min GBR
pre-stage) -- not because those specific pieces are this commit's job,
but because a VQ-less scheduler (see below) has nothing for a Tier-1
target rate to feed. Two of those Tier-1 pieces do not come back at all:
see ``README.md`` sec7's new bullet -- the adaptive penalty
(``gbr_penalty_lr``) and the max-min pre-stage (``gbr_maxmin``) have no
citation in ``docs/phase2-plan.md`` sec2.1's ground truth (which
describes only a *fixed*-constant soft-slack penalty,
``IA_P5G_TIER1_GBR_PENALTY = 1.0e3``) and were already a documented
negative result (``design-docs/scheduler-study.md`` sec8.4) before this
commit removed them from the live scheduler.

Explicitly NOT here yet, each landing in its own later commit: the UL
floor's fruitless-shift/ADQ anti-starvation state machine (commit 4),
the real single-pass SRB-exempt DL LCP fill (commit 5, replacing
``_dl_fill``'s placeholder below -- see this commit's own note on why
that makes commit 5 a *joint* VQ-correction commit, not a pure LCP one),
MCS selection via OLLA (commit 6), and a re-port of ``reset_ue``/
``SchedulerContextReset`` against the new field layout (commit 7) --
this class implements no ``reset_ue`` at all until then; ``sim/
driver.py`` discovers it via ``getattr(scheduler, "reset_ue", None)``,
so its absence simply means TwoTier is treated like PF (no context
reset) in the interim, not an oversight.

**Commit 3a (this commit) lands the windowed-ceiling virtual queue
itself -- growth, ceiling, drain, and the real ranking coefficients --
finally replacing the bootstrap PF-coefficient placeholder every
ranking decision has used since commit 1.** Commit 3 (``8829e2a``)
landed the GBR-deficit/PDB-remaining sort tiers first, since the VQ is
the *final* tiebreak in both real comparators and a VQ landing under
nothing couldn't have demonstrated its own mechanism.

DL (``ia_p5g_update_vq_dl``, ``ia_p5g_scheduler.c:1835-1894``, re-read
directly this commit): grows by Tier-1's target rate each slot, clamped
to an **arrival-delta** windowed ceiling -- ``min(arr_W, target_W) -
del_W``, where ``arr_W``/``del_W`` are deltas against ``_arr_hist``/
the new ``_del_hist`` snapshots, both frozen once per Tier-1 cycle
inside ``_compute_demand_bps`` (confirmed directly: ``dl_arrived_hist``/
``dl_delivered_hist`` are written only inside the C's Tier-1 demand
block, ``:1264-1265`` -- read-only inside the VQ-update function
itself). This form matches the mechanism's own header intent. LCID < 4
(SRBs) skipped. Ranking coefficient (``ia_p5g_dl_metric``, ``:1896-
1923``): pure ``(Σ vq_dl over backlogged LCIDs) × spectral_eff``,
multiplied *internally*, no urgency folded in -- becomes ``_dl_rank_
key``'s final tiebreak.

UL (``ia_p5g_update_vq_ul``, ``:3578-3687``): grows identically, but
the ceiling is the **backlog-bound/catchup** form -- confirmed again
this commit that the function no longer reads ``ul_arrived_hist``/
``arr_W`` at all. The in-code bugfix comment (``:3608-3654``) explains
why directly: the old arrival-delta form collapsed to ~0 exactly when a
flow was starved hard enough to saturate its buffer (arrivals stop, so
does ``arr_W``) -- "being denied service erases the evidence you were
denied," with a cited incident (UE 5ce4, 2.9 MB backlogged, 435 bytes
delivered in 1 s, ``vq_ul`` read 0.0). The fix bounds by backlog level
instead (``min(backlog, N × target_W) - del_W``, ``N = _VQ_UL_CATCHUP_N
= 5``), which survives starvation. **This is the second of this port's
four documented comment-vs-code instances -- port the code, not the
header.** LCG 0 excluded structurally (no ``FlowConfig`` models SRB
traffic, same convention ``_ul_gbr_and_pdb``/``_ul_stamp`` already use),
``lcid = lcg + 3``.

UL's base ranking term (``ia_p5g_ul_metric``, ``:3696-3726``): ``Σ
vq_ul`` over LCGs gated by an **OR condition** -- include if EITHER
``estimated_ul_buffer_per_lcg > 0`` OR ``vq_ul > 0`` -- a separate,
documented starvation-prevention bugfix (cited incident: "the exact
failure that left d639 with zero grants for 55s"; a BSR-decayed-to-zero
flow during a grant freeze must still be visible via its durable VQ
deficit). Confirmed the function's own ``spectral_eff`` parameter is
read but unused (``(void)spectral_eff``) -- the *caller* forms
``(base_q + urgency) × SE`` and multiplies SE once, unlike DL's
internal multiply. UL's real (and, per commit 3's finding, *sole*)
ranking term is this composite: ``urgency = DELAY_URGENCY_W × Φ(u) ×
norm``, where ``norm = max(base_q across the slot's UL candidates,
1.0)`` and **Φ is a barrier function, not a plain power law** -- ``Φ(u)
= u^DELAY_EXP / (1 - min(u, URG_BARRIER_CAP) + URG_BARRIER_EPS)``,
diverging as ``u → 1``. ``u`` (``ue_worst_urgency01``, ``:2576-2647``)
is the max over active LCGs of ``u_lcg × priority_weight × delta``,
where ``delta = 1.0`` for non-GBR flows and a GBR-deficit-scaled floor
form for GBR ones -- folded into ``_ul_gbr_and_pdb``'s own per-LCG loop
(same ``rem_pdb``/``obligation``/``window`` arithmetic that method
already computed for commit 3) rather than a second duplicate walk,
mirroring the C's own single-pass organization. Constants confirmed by
direct grep: ``IA_P5G_DELAY_URGENCY_W=4.0``, ``_DELAY_EXP=2.0``,
``_URG_PRIO_W_MIN=0.35``, ``_URG_PRIO_MAX=90.0``, ``_URG_BARRIER_
CAP=0.97``, ``_URG_BARRIER_EPS=0.03``, ``_URG_GBR_FLOOR=0.15``. (Note,
not acted on: ``_DELAY_URGENCY_W``/``_DELAY_EXP`` numerically match the
deleted pre-Phase-2 Python's own ``delay_urgency_weight``/
``delay_exponent`` -- magnitude coincidence only; that code's
*structure*, plain power law applied to DL too with no barrier/
priority-weight/GBR-floor terms, was still wrong.)

**``spectral_eff``/``tbs`` is the same hypothetical-TBS quantity for
both directions, and it already existed in this file before this
commit.** Both C call sites (``:1543``, ``:2707``) compute
``nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, l) >> 3`` -- a hypothetical
1-PRB, 10-symbol TBS in bytes at the UE's current MCS. ``_PF_COEF_
HYPOTHETICAL_SYMBOLS = 10`` (commit 1) already computes exactly this
fixed 10-symbol hypothetical, evidently chosen anticipating this reuse
even though commit 1 had no two-tier citation for it at the time.
**Units note, deliberate, not a bug to "fix": ``vq_dl``/``vq_ul`` are
bits, ``hyp_tbs_bytes`` is bytes -- ground truth multiplies them
directly with no conversion. This is an internal ranking score, not a
physical quantity; the mixed units are ported as-is.**

**The bootstrap PF coefficient (``dl_thr_bytes_per_slot``/
``ul_thr_bytes_per_slot``, the per-UE throughput EWMA, and
``_THR_EWMA_ALPHA``) is deleted in this commit, exactly as commit 1's
own docstring already promised** ("Deleted (DL) or replaced (UL) along
with the rest of this placeholder in commit 3a") -- no longer read or
written anywhere in this file.

**A real, self-inflicted finding, distinct in kind from the four
comment-vs-code mismatches inherited from OAI**: ``_dl_stamp``'s own
docstring (landed in commit 3) cited ``gNB_scheduler_dlsch.c:1451-
1460`` as the future VQ-drain hook. Read directly this commit: that
range is unrelated DL-SCH PDU padding-byte fill code, nothing to do
with VQ drain. Corrected to the real citation (``ia_p5g_scheduler.c:
1821`` call site, ``:2002-2035`` the function) -- this project's own
citation, written in commit 3, checked and found wrong in 3a, not
something ported incorrectly from OAI. ``_ul_stamp``'s own citation
(``gNB_scheduler_ulsch.c:2760-2777``) was checked the same way and
found accurate.

DL's drain (``ia_p5g_drain_vq_dl``, ``:2002-2035``): per-LCID,
``(1 - bler)``-discounted, reusing ``_Candidate.bler`` (already computed
per candidate for the pre-existing threshold bookkeeping, now repurposed
here). **Ground truth drains against ``dl_lcid_budget``, populated by
the real LCP fill (``ia_p5g_compute_lcp_budget``, sorted ``(priority
ASC, vq_dl DESC)``, greedy) -- explicitly commit 5's job, not this
one's** (``_dl_fill``'s own docstring already flags this: a placeholder
sorted ``(priority, -bytes_queued)``, "upgraded in commit 5"). **This
commit drains against that placeholder's ``fills`` output instead --
a real behavioral substitution, not a plumbing detail.** The drain
arithmetic itself (the ``(1-bler)`` discount, the per-LCID subtract,
the zero-floor) is faithful; its INPUT (which LCID gets how many of a
TB's bytes) is not yet the real order, so ``vq_dl``'s own trajectory is
not expected to match ground truth until commit 5 lands the real fill.
**Consequence recorded now, not rediscovered at commit 5: commit 5 is a
joint VQ-correction commit, not a pure LCP commit** -- landing the real
fill order will also change which LCID each TB's bytes drain from,
which changes ``vq_dl``, which changes DL ranking downstream, on top of
whatever LCP itself changes about grant composition (also noted in
``docs/phase2-plan.md``'s own commit-5 row).

UL's drain (``ia_p5g_drain_vq_ul``, ``:3728-3769``): proportional split
of the FULL raw ``tb_size`` across active LCGs by BSR-buffer share
(``1/n_active`` fallback when total buffer reads 0), confirmed by
reading the whole function body this commit -- **no BLER discount
anywhere in it**, a genuine DL/UL asymmetry, not an oversight.

**Score commit 3's own stated expectation, tested directly rather than
left as a citation**: if Tier-1's targets genuinely carry the GBR
obligation into the UL VQ deficit, a UL GBR flow should be protected by
the VQ alone with no sort tier assisting it (unlike DL, where
``has_gbr`` protects explicitly) -- see
``test_ul_gbr_flow_held_near_gfbr_by_vq_alone_no_tier_assists`` in the
test file, and this file's own docstring/port-map entry for the
outcome.

``docs/oai-port-map.md``'s port-map rows for this commit carry the full
citation detail for growth/ceiling/drain in both directions and the
composite UL coefficient, plus a dedicated Divergence row for the
DL-drain-against-placeholder substitution above.

**Commit 2 wired the real Tier-1 SCA/GLPK solve
(``scheduler/tier1.py``, rewritten from ``ia_p5g_scheduler.c`` -- see
that module's own docstring for the full ground-truth citation) in,
with its output unconsumed until this commit.** ``_targets_bps`` (real,
computed every ``tier1_period_slots`` slots since commit 2, predicted
and confirmed to move zero `--check` numbers on its own) finally feeds
the VQ growth term above -- this is the first commit where Tier-1's
solve runs genuinely end-to-end. ``tier1_period_slots`` is
derived from ``_TIER1_PERIOD_S = 0.1`` ÷ ``slot_duration_s`` at
``configure()`` time (numerology-robust), not hardcoded, closing the
stale-default finding ``README.md`` §7 already flagged. Demand feeding
the solve is windowed-arrival, DL raw / UL EWMA-smoothed with a
zero-fallback guard -- see ``_resolve_tier1``'s own docstring, which
cites the exact C lines; not an oracle, unlike the deleted pre-Phase-2
default.

Like ``reservation.py``, this package depends only on stdlib and its own
modules -- never on ``sim``. A UL grant is emitted as a single opaque
``ue_grant=True`` Allocation (unchanged from the pre-rewrite file's own
``_emit_grant``); ``sim/ue_lcp.py`` performs the real per-flow split
entirely on the driver side. This scheduler's ranking and grant sizing
read only UE-aggregate quantities (``bytes_reported`` summed across a
UE's flows in a direction) -- never a per-flow split, and never a
per-flow virtual queue on the UL side either (``vq_ul`` is keyed by
LCG, not ``qfi``), matching ``docs/phase2-plan.md`` D1's requirement
that UL state be LCG-aggregate, the real gNB's own visibility
(``ia_p5g_scheduler.c``'s ``vq_ul[UE][LCG]``, not per-flow).

**The bootstrap PF coefficient/throughput-EWMA placeholder that ranked
every UE from commit 1 through commit 3 is gone as of this commit** --
``dl_thr_bytes_per_slot``/``ul_thr_bytes_per_slot``/``_THR_EWMA_ALPHA``
are deleted outright, exactly as commit 1's own docstring already
promised ("Deleted (DL) or replaced (UL)... in commit 3a"). It was
never ground truth at any point it existed (two-tier's own coefficient
is never PF-coefficient-shaped, unlike ``reservation.py``'s, where the
identical formula *is* the real final tiebreak) -- do not add a C
file:line citation for it retroactively in the port-map row; its own
row already records "no ground truth -- temporary bootstrap, removed
commit 3a."

The one piece of this file that *is* a live-source citation:
``gNB_scheduler.c:246,251`` (confirmed byte-identical across both
branches, ``oai-branches/README.md``) runs ``nr_schedule_ulsch`` before
``nr_schedule_ue_spec`` (DL) unconditionally, every slot -- UL-then-DL.
**The pre-rewrite ``two_tier.py`` had this backwards**: its own
``allocate()`` iterated ``("DL", "UL")``, DL first -- a real, live bug in
the scheduler that produced every existing TwoTier regression record,
not a cosmetic one. Fixed here.
"""

from dataclasses import dataclass, field

from .flow import FlowConfig
from .interfaces import Allocation, BufferView, ChannelView, GridView, SlotView
from .link import bits_per_prb, cce_aggregation_level
from .tier1 import solve_tier1

# ia_p5g_scheduler.c:74-76 -- the deployed macro, not ia_p5g_scheduler.h's
# stale "1.0 s default" doc comment (README.md sec7's own stale-default
# finding, now closed here rather than merely documented). Slot count is
# derived from this at configure() time, never hardcoded.
_TIER1_PERIOD_S = 0.1

# ia_p5g_scheduler.c:388 -- UL-only demand EWMA smoothing (see
# scheduler/tier1.py's own citation of the same constant; duplicated here
# rather than imported since it's a two_tier.py-local demand-tracking
# concern, the same "small shared constant, not a cross-module import"
# convention _PF_COEF_HYPOTHETICAL_SYMBOLS already uses).
_UL_DEMAND_ALPHA = 0.3

# GRADUATES to real ground truth as of commit 3a: ia_p5g_scheduler.c:1540
# (DL) and :2681-ish (UL) both compute nr_compute_tbs(Qm, R, 1, 10, 0, 0,
# 0, l) >> 3 -- a hypothetical 1-PRB, 10-symbol TBS in bytes at the UE's
# current MCS -- as the "spectral_eff"/"tbs" argument to
# ia_p5g_dl_metric/ia_p5g_ul_metric. The fixed "10" matches this constant
# exactly. Commit 1 chose it as a bootstrap-only PF-coefficient
# convention borrowed from reservation.py, with no two-tier citation;
# this commit confirms it was -- by coincidence or foresight -- already
# the real value. Used below as _Candidate.hyp_tbs_bytes, the real
# spectral-efficiency factor both directions' ranking coefficients
# multiply by.
_PF_COEF_HYPOTHETICAL_SYMBOLS = 10

# gNB_scheduler_dlsch.c:352/:2216 (two-tier's own files -- confirmed
# byte-identical to reservation's own citation of the same constant at
# the same fallback value, docs/oai-port-map.md rows 18/19). Applies to
# both directions.
_PDB_FALLBACK_MS = 300

# ia_p5g_scheduler.c:3676 -- UL VQ ceiling's catch-up horizon (windows of
# guaranteed bits the virtual queue may accumulate before the backlog/
# ceiling clamp binds), part of the backlog-bound bugfix form (see
# _update_vq_ul's own docstring) -- NOT the arrival-delta form the
# module's own header describes.
_VQ_UL_CATCHUP_N = 5

# ia_p5g_scheduler.c:443-444,478-481,501 -- UL's composite-coefficient
# urgency term (barrier function + priority weight + GBR-deficit floor).
# _DELAY_URGENCY_W/_DELAY_EXP numerically match the deleted pre-Phase-2
# Python's own delay_urgency_weight/delay_exponent (4.0/2.0) -- magnitude
# coincidence only; that code's structure (plain power law, applied to DL
# too, no barrier/priority-weight/GBR-floor terms) was still wrong.
# Ported fresh from this commit's own ground-truth reading, not reused
# from the deleted file.
_DELAY_URGENCY_W = 4.0
_DELAY_EXP = 2.0
_URG_PRIO_W_MIN = 0.35
_URG_PRIO_MAX = 90.0
_URG_BARRIER_CAP = 0.97
_URG_BARRIER_EPS = 0.03
_URG_GBR_FLOOR = 0.15


@dataclass
class _UeState:
    """Per-UE state: commit 3's GBR-deficit/last-grant-slot tracking
    (real ground truth, adapted directly from ``reservation.py``'s own
    ``_UeState``, same field shapes, since the underlying C is confirmed
    byte-identical between branches for this mechanism), plus this
    commit's own virtual queues -- ``vq_dl`` keyed by DL flow ``qfi``
    (≈ LCID), ``vq_ul`` keyed by UL LCG, matching ``ia_p5g_scheduler.c``'s
    own ``vq_dl[UE][LCID]``/``vq_ul[UE][LCG]`` shapes (module docstring's
    D1 note: UL state is LCG-aggregate, never per-flow).
    """

    ul_lcg_deficit_bytes: dict[int, int] = field(default_factory=dict)
    ul_lcg_last_grant_slot: dict[int, int] = field(default_factory=dict)
    dl_flow_deficit_bytes: dict[int, int] = field(default_factory=dict)
    dl_flow_last_grant_slot: dict[int, int] = field(default_factory=dict)
    vq_dl: dict[int, float] = field(default_factory=dict)
    vq_ul: dict[int, float] = field(default_factory=dict)


@dataclass
class _Candidate:
    ue_id: int
    flows: list[FlowConfig]
    bits_per_rb: int
    bler: float
    snr_db: float
    coef: float
    # DL sort tiers (ia_p5g_dl_cmp, ia_p5g_scheduler.c:1397-1411) -- real
    # for DL, computed but unused by ranking for UL (see _ul_rank_key).
    has_gbr: bool = False
    pdb_ms: int = 9999
    # UL's own top tier (ia_p5g_ul_cmp, :2112-2125) -- structurally
    # absent (no do_sched-equivalent signal exists), same disposition
    # reservation.py's own liveness/sched_inactive finding already made.
    # Unused by DL.
    sched_inactive: bool = False
    # Real spectral-efficiency factor both directions' coefficients
    # multiply by -- see module docstring's _PF_COEF_HYPOTHETICAL_SYMBOLS
    # note. Computed once per candidate at build time.
    hyp_tbs_bytes: int = 0
    # UL only (ue_worst_urgency01, ia_p5g_scheduler.c:2576-2647) -- DL
    # leaves this at the default since ia_p5g_dl_metric folds in no
    # urgency term at all.
    urgency01: float = 0.0


class TwoTier:
    """Rewritten in place from the pre-Phase-2 file (tag
    ``phase2-pre-twotier-rewrite``). Commit 1: ``Scheduler`` protocol
    conformance, a per-UE throughput-EWMA bootstrap ranking, no VQ, no
    UL floor, no Tier-1 -- see module docstring for what's deleted and
    what lands in later commits.
    """

    def __init__(self) -> None:
        self._flows: list[FlowConfig] = []
        self._ue_state: dict[int, _UeState] = {}
        self._snr_avg: dict[int, float] = {}
        self._targets_bps: dict[tuple[int, int], float] = {}
        self._arr_hist: dict[tuple[int, int], float] = {}
        self._del_hist: dict[tuple[int, int], float] = {}
        self._ul_demand_smooth: dict[tuple[int, int], float] = {}
        self._last_solve_slot = -(10**9)
        self.tier1_period_slots = 1

    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: GridView,
    ) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        self._grid = grid
        self._ue_state = {f.ue_id: _UeState() for f in flows}
        self._snr_avg = {}
        self._targets_bps = {}
        self._arr_hist = {(f.ue_id, f.qfi): 0.0 for f in flows}
        self._del_hist = {(f.ue_id, f.qfi): 0.0 for f in flows}
        self._ul_demand_smooth = {
            (f.ue_id, f.qfi): 0.0 for f in flows if f.direction == "UL"
        }
        self.tier1_period_slots = max(1, round(_TIER1_PERIOD_S / slot_duration_s))
        self._last_solve_slot = -(10**9)

    def allocate(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
    ) -> list[Allocation]:
        self._update_snr_ewma(channel)
        if slot.slot_index - self._last_solve_slot >= self.tier1_period_slots:
            self._resolve_tier1(slot.slot_index, buffers)
            self._last_solve_slot = slot.slot_index

        # gNB_scheduler.c:246,251 -- UL before DL, unconditionally, every
        # slot. See module docstring: the pre-rewrite file had this
        # backwards (DL-then-UL); fixed here, verified directly against
        # the C rather than inherited from the old Python or the plan
        # doc's own prose.
        out: list[Allocation] = []
        if slot.ul_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "UL"))
        if slot.dl_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "DL"))
        return out

    def _update_snr_ewma(self, channel: ChannelView) -> None:
        """Tier-1's own SNR input -- solve_tier1 needs a per-UE SNR to
        compute spectral efficiency. A plain smoothed CQI-visible read,
        the same convention the pre-rewrite file used for the identical
        purpose (not itself a claim about ground truth's own SNR-smoothing
        specifics for Tier-1, which ia_p5g_scheduler.c does not appear to
        smooth at all before ia_p5g_estimate_se_dl/_ul -- flagged, not
        resolved, since it doesn't change this commit's own predicted-
        zero-movement outcome either way; Tier-1's output is unconsumed
        this commit regardless of exactly how its own inputs are formed)."""
        for f in self._flows:
            cur = channel.get_reported_snr_db(f.ue_id)
            self._snr_avg[f.ue_id] = cur

    def _resolve_tier1(self, slot_index: int, buffers: BufferView) -> None:
        """ia_p5g_tier1_thread's per-cycle body (ia_p5g_scheduler.c:1120-
        1345): build each flow's windowed-arrival demand, call
        solve_tier1, and -- fail-soft, matching the C's own "keep last
        good targets" behavior (scheduler/tier1.py::solve_tier1's own
        docstring) -- only overwrite self._targets_bps when the solve
        actually produced something. Not consumed by ranking until commit
        3a (VQ); computed and stored here regardless, so commit 3a doesn't
        also have to wire the solve itself.
        """
        if slot_index - self._last_solve_slot >= 10**8:
            # First call this run (_last_solve_slot still at its sentinel
            # init) -- no real prior cycle to measure elapsed time against.
            # ia_p5g_scheduler.c:1137-1139's own fallback: use the nominal
            # period, not a wall-clock delta that doesn't exist yet.
            elapsed_s = _TIER1_PERIOD_S
        else:
            elapsed_s = (slot_index - self._last_solve_slot) * self.slot_duration_s
        demand_bps = self._compute_demand_bps(buffers, elapsed_s)
        targets = solve_tier1(self._flows, self._snr_avg, self._grid, demand_bps)
        if targets:
            self._targets_bps = targets

    def _compute_demand_bps(
        self, buffers: BufferView, elapsed_s: float
    ) -> dict[tuple[int, int], float]:
        """Windowed-arrival demand per flow -- ia_p5g_scheduler.c:1238-
        1334. DL: raw arr_W/elapsed, never smoothed (:1256, ":1289-1290
        must NOT be smoothed" -- the RLC buffer is exact and stable). UL:
        the same base quantity, EWMA-smoothed at _UL_DEMAND_ALPHA with a
        raw-value fallback when the smoothed estimate is still zero
        (:1291-1301, first cycle after attach). Ground truth additionally
        caps UL demand at the UE's PHR power headroom (:1303-1313) --
        NOT wired here; sim/power.py stays dormant per this repo's own
        convention (README.md sec4), a flagged gap, not a silent omission.

        Also freezes ``_del_hist`` (delivered-only cumulative, no
        backlog term) alongside the pre-existing ``_arr_hist`` --
        confirmed directly against the C this commit (3a): both
        ``dl_arrived_hist``/``dl_delivered_hist`` (and their UL
        counterparts) are written ONLY inside this same per-Tier-1-cycle
        block (``:1264-1265``, ``:1332-1333``), never inside the VQ
        growth/ceiling functions themselves (``ia_p5g_update_vq_{dl,
        ul}``, which read them but never write them) -- so the VQ
        ceiling's window comparison is against a snapshot frozen at
        Tier-1 cadence, not updated every slot.

        Known, pre-existing simulator limitation, not introduced here:
        multiple flows sharing one UL LCG would each read the identical
        estimated_ul_buffer_per_lcg and get independent (duplicated)
        demand entries -- the same H5-gap shape already documented
        elsewhere in this port (README.md sec8); no current scenario
        triggers it.
        """
        demand: dict[tuple[int, int], float] = {}
        for f in self._flows:
            key = (f.ue_id, f.qfi)
            st = buffers.state(f.ue_id, f.qfi)
            del_cum = buffers.delivered_cum(f.ue_id, f.qfi)
            if f.direction == "DL":
                arr_cum = del_cum + st.bytes_queued
                arr_w = arr_cum - self._arr_hist.get(key, 0.0)
                self._arr_hist[key] = arr_cum
                self._del_hist[key] = del_cum
                demand[key] = max(0.0, arr_w * 8.0 / elapsed_s)
            else:
                arr_cum = del_cum + st.estimated_ul_buffer_per_lcg
                arr_w = arr_cum - self._arr_hist.get(key, 0.0)
                self._arr_hist[key] = arr_cum
                self._del_hist[key] = del_cum
                demand_raw = max(0.0, arr_w * 8.0 / elapsed_s)
                prev_smooth = self._ul_demand_smooth.get(key, 0.0)
                smooth = (
                    _UL_DEMAND_ALPHA * demand_raw
                    + (1.0 - _UL_DEMAND_ALPHA) * prev_smooth
                )
                self._ul_demand_smooth[key] = smooth
                demand[key] = smooth if smooth > 0.0 else demand_raw
        return demand

    def _allocate_direction(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
        direction: str,
    ) -> list[Allocation]:
        symbols = slot.ul_symbols if direction == "UL" else slot.dl_symbols

        # D1 (docs/phase2-plan.md sec3): UE-aggregate only, never a
        # per-flow split. Multiple flows sharing one LCG would each read
        # the identical bytes_reported and be summed here more than
        # once -- a known, currently-untriggered gap (no scenario in
        # this repo shares an LCG across UL flows -- README sec8's H5
        # follow-up), the same shape reservation.py's own ue_backlog sum
        # carries, not fixed here either.
        ue_flows: dict[int, list[FlowConfig]] = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            ue_flows.setdefault(f.ue_id, []).append(f)
        if not ue_flows:
            return []

        candidates: list[_Candidate] = []
        for ue_id, flows in ue_flows.items():
            state = self._ue_state[ue_id]

            snr = channel.get_reported_snr_db(ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue

            # Real spectral-efficiency factor -- see module docstring's
            # _PF_COEF_HYPOTHETICAL_SYMBOLS note (ia_p5g_scheduler.c:1540,
            # :2707).
            hyp_bits, _ = bits_per_prb(snr, symbols=_PF_COEF_HYPOTHETICAL_SYMBOLS)
            hyp_tbs_bytes = hyp_bits // 8

            candidate = _Candidate(
                ue_id, flows, bits_per_rb, bler, snr, coef=0.0,
                hyp_tbs_bytes=hyp_tbs_bytes,
            )
            if direction == "DL":
                self._update_vq_dl(ue_id, buffers)
                has_gbr, pdb_ms, _guaranteed, _be = self._dl_gbr_and_pdb(
                    ue_id, buffers, slot.slot_index
                )
                candidate.has_gbr = has_gbr
                candidate.pdb_ms = pdb_ms
                # ia_p5g_dl_metric, :1896-1923 -- pure product, no
                # urgency, only backlogged LCIDs contribute.
                sum_q = sum(
                    state.vq_dl.get(f.qfi, 0.0)
                    for f in flows
                    if buffers.state(f.ue_id, f.qfi).bytes_queued > 0
                )
                candidate.coef = sum_q * hyp_tbs_bytes
            else:
                self._update_vq_ul(ue_id, buffers)
                # UL's own has_gbr/pdb_ms aren't sort tiers (see module
                # docstring's design-revision finding) -- called for the
                # deficit-tracking + urgency side effect; has_gbr/pdb_ms
                # themselves aren't stored on the candidate since nothing
                # reads them yet.
                _has_gbr, _pdb_ms, _guaranteed, _be, urgency01 = (
                    self._ul_gbr_and_pdb(ue_id, buffers, slot.slot_index)
                )
                candidate.urgency01 = urgency01
                # ia_p5g_ul_metric, :3696-3726 -- base_q only; the
                # urgency term and the SE multiply happen in
                # _finalize_ul_coef below, once max_q across this slot's
                # UL candidates is known. coef temporarily holds base_q
                # until then.
                candidate.coef = self._ul_base_q(ue_id, buffers)
            candidates.append(candidate)

        if not candidates:
            return []

        if direction == "UL":
            self._finalize_ul_coef(candidates)

        rank_key = self._dl_rank_key if direction == "DL" else self._ul_rank_key
        candidates.sort(key=rank_key)

        prbs_left = slot.prb_count
        cce_left = slot.pdcch_cce_budget
        out: list[Allocation] = []
        for c in candidates:
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(c.snr_db)
            if cce_left < cce_cost:
                continue

            ue_backlog = sum(
                buffers.state(f.ue_id, f.qfi).bytes_reported for f in c.flows
            )
            if ue_backlog <= 0:
                continue
            prbs_needed = -(-(ue_backlog * 8) // c.bits_per_rb)  # ceil div
            # No follower budget yet (commit 4) -- unbounded by anything
            # but this slot's own remaining PRBs.
            prbs_used = min(prbs_left, max(1, prbs_needed))
            tbs_bytes = min(ue_backlog, (prbs_used * c.bits_per_rb) // 8)
            if tbs_bytes <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            out.extend(
                self._emit_grant(
                    c.ue_id, direction, prbs_used, tbs_bytes, c.flows,
                    buffers, cce_cost, c.snr_db, slot.slot_index, c.bler,
                )
            )
        return out

    def _finalize_ul_coef(self, candidates: list[_Candidate]) -> None:
        """Second pass of ia_p5g_scheduler.c:2860-2924's composite
        formation -- needs max_q (base_q's max across the slot's whole
        UL candidate set) before any single candidate's coef can be
        finalized, so this can't happen inline during candidate-building
        the way DL's single-pass metric can. Before this runs,
        candidate.coef temporarily holds base_q (this method's own
        input); overwritten here with the real composite. sched_inactive
        is always False (module docstring), so "non-sched_inactive
        candidates" collapses to "all candidates" for the max_q scan.
        """
        norm = max((c.coef for c in candidates), default=0.0)
        norm = max(norm, 1.0)
        for c in candidates:
            base_q = c.coef
            u = c.urgency01
            ub = min(u, _URG_BARRIER_CAP)
            phi = (u**_DELAY_EXP) / (1.0 - ub + _URG_BARRIER_EPS)
            urg = _DELAY_URGENCY_W * phi * norm
            c.coef = (base_q + urg) * c.hyp_tbs_bytes

    def _dl_rank_key(self, candidate: _Candidate) -> tuple:
        """ia_p5g_dl_cmp, ia_p5g_scheduler.c:1397-1411 -- the *original*,
        never-revised lexicographic form: has_gbr (top), then pdb_ms,
        then the coefficient as final tiebreak -- as of commit 3a, the
        real ia_p5g_dl_metric product (module docstring), not the
        bootstrap placeholder. Independently sourced from _ul_rank_key,
        not a shared function -- DL and UL's real comparators have
        genuinely different tier counts (see module docstring's
        design-revision finding), matching reservation.py's own
        precedent of never merging its _ul_rank_key/_dl_rank_key even
        when their shapes coincide.
        """
        return (0 if candidate.has_gbr else 1, candidate.pdb_ms, -candidate.coef)

    def _ul_rank_key(self, candidate: _Candidate) -> tuple:
        """ia_p5g_ul_cmp, ia_p5g_scheduler.c:2112-2125 -- the *revised*
        two-tier form: sched_inactive (top, structurally absent here,
        hardcoded False -- see module docstring), then the composite
        coefficient -- as of commit 3a, the real VQ-plus-urgency
        composite (_finalize_ul_coef), not the bootstrap placeholder.
        Deliberately does NOT include has_gbr/pdb_ms -- ground truth's
        own comment explains why (Tier-1's targets already encode the
        GBR guarantee, so the VQ deficit already carries it; a separate
        tier would double-count it) -- this is the mechanism
        reservation.py's own UL comparator never had a reason to drop,
        since reservation has
        no VQ to carry the guarantee instead.
        """
        return (0 if candidate.sched_inactive else 1, -candidate.coef)

    def _dl_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int, int, int]:
        """DL GBR deficit accumulate/cap/target-spread/overflow-to-BE,
        plus remaining-PDB -- gNB_scheduler_dlsch.c:325-410 (two-tier's
        own file). Confirmed byte-identical, by direct diff, to
        oai-branches/reservation/gNB_scheduler_dlsch.c's own version of
        this same block -- adapted line-for-line from
        reservation.py::_dl_gbr_and_pdb (same int-ms-truncation
        discipline, same 300 ms PDB fallback, same unconditional-deficit-
        accumulation-vs-gated-target asymmetry that method's own
        docstring already documents), not re-derived. Returns
        ``(has_gbr, remaining_pdb_ms, guaranteed_bytes, be_bytes)`` --
        the last two are real (computed, matching the C) but NOT yet
        consumed by anything (grant sizing is a later commit, mirroring
        reservation's own commit-3-then-4a split).
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s
        slot_ms = self.slot_duration_s * 1000.0

        has_gbr = False
        best_remaining_pdb = 9999
        guaranteed_bytes = 0
        be_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "DL":
                continue
            bytes_queued = buffers.state(f.ue_id, f.qfi).bytes_queued

            pdb_ms = int(f.pdb_ms) if f.pdb_ms > 0 else _PDB_FALLBACK_MS

            last_grant = state.dl_flow_last_grant_slot.get(f.qfi)
            if last_grant is None:
                remaining_pdb = pdb_ms
            else:
                age_ms = (slot_index - last_grant) * slot_ms
                remaining_pdb = max(0, pdb_ms - int(age_ms))
            if bytes_queued > 0:
                best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += bytes_queued
                continue

            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.dl_flow_deficit_bytes.get(f.qfi, 0) + obligation
            window = obligation * int(pdb_ms / slot_ms)
            deficit = min(deficit, window)
            state.dl_flow_deficit_bytes[f.qfi] = deficit
            if deficit > 0:
                has_gbr = True

            if bytes_queued <= 0:
                continue  # accumulation is unconditional; target is not

            rem_slots = int(remaining_pdb / slot_ms)
            if rem_slots < 1:
                rem_slots = 1
            target = (deficit + obligation) // rem_slots
            if target < obligation:
                target = obligation
            max_burst = int((f.mfbr_bps / 8.0) / slots_per_sec) * 2
            if max_burst < obligation * 2:
                max_burst = obligation * 2
            if target > max_burst:
                target = max_burst

            guaranteed_bytes += target
            overflow = bytes_queued - target
            if overflow > 0:
                be_bytes += overflow

        return has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes

    def _ul_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int, int, int, float]:
        """UL GBR deficit accumulate/cap/target-spread/overflow-to-BE,
        remaining-PDB, and (as of commit 3a) worst-case priority-weighted
        urgency -- gNB_scheduler_ulsch.c:2196-2280 (two-tier's own file)
        and ia_p5g_scheduler.c's own inlined UL ranking loop (:2570-2674,
        commented "unchanged from original pf_ul()" -- checked, not
        trusted: byte-diffed the deficit/PDB/target arithmetic
        specifically (:2649-2672 vs. gNB_scheduler_ulsch.c:2231-2260) and
        confirmed the claim holds exactly for what it describes. The
        claim's SCOPE is narrower than the block it sits in, though --
        ia_p5g_scheduler.c interleaves genuinely new logic in the same
        loop (the priority-weighted urgency computation this method now
        also folds in, :2576-2647) that the "unchanged" comment does not
        cover; don't over-read "unchanged" as "the whole block is a
        verbatim copy."

        Deficit/PDB arithmetic confirmed byte-identical, by direct diff,
        to oai-branches/reservation/gNB_scheduler_ulsch.c's own version
        -- adapted line-for-line from reservation.py::_ul_gbr_and_pdb
        (same int-ms-truncation discipline, same per-LCG gate on
        estimated_ul_buffer_per_lcg > 0, same first-flow-found-wins-a-
        shared-LCG dedup), not re-derived.

        Urgency (ia_p5g_scheduler.c:2576-2647, new in this commit):
        u_lcg = clamp(1 - remaining_pdb/pdb_ms, 0, 1), computed for
        EVERY active LCG regardless of GBR status -- only the delta term
        below branches on it. priority_weight is a linear ramp from
        _URG_PRIO_W_MIN (low priority) to 1.0 (priority 1), clamped.
        delta = 1.0 for non-GBR flows; for GBR flows,
        _URG_GBR_FLOOR + (1-_URG_GBR_FLOOR) * min(1, deficit/window) --
        reusing the SAME deficit/window this method already computes,
        one pass, matching the C's own single-pass organization rather
        than a second duplicate walk. worst_urgency01 is the max of
        u_lcg * priority_weight * delta over this UE's active LCGs.

        Returns a 5-tuple now: (has_gbr, remaining_pdb_ms,
        guaranteed_bytes, be_bytes, worst_urgency01) -- guaranteed_bytes/
        be_bytes still real but unconsumed (grant sizing is commit 4);
        worst_urgency01 feeds _finalize_ul_coef directly.
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s
        slot_ms = self.slot_duration_s * 1000.0

        seen_lcgs: set[int] = set()
        has_gbr = False
        best_remaining_pdb = 9999
        guaranteed_bytes = 0
        be_bytes = 0
        worst_urgency01 = 0.0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            lcg_estimate = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if lcg_estimate <= 0:
                continue
            seen_lcgs.add(f.lcg)

            pdb_ms = int(f.pdb_ms) if f.pdb_ms > 0 else _PDB_FALLBACK_MS

            last_grant = state.ul_lcg_last_grant_slot.get(f.lcg)
            if last_grant is None:
                remaining_pdb = pdb_ms
            else:
                age_ms = (slot_index - last_grant) * slot_ms
                remaining_pdb = max(0, pdb_ms - int(age_ms))
            best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            u_lcg = max(0.0, min(1.0, 1.0 - remaining_pdb / pdb_ms))
            priority_weight = _URG_PRIO_W_MIN + (1.0 - _URG_PRIO_W_MIN) * (
                1.0 - (f.priority_level - 1) / (_URG_PRIO_MAX - 1)
            )
            priority_weight = max(_URG_PRIO_W_MIN, min(1.0, priority_weight))

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += lcg_estimate
                worst_urgency01 = max(worst_urgency01, u_lcg * priority_weight)
                continue

            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.ul_lcg_deficit_bytes.get(f.lcg, 0) + obligation
            window = obligation * int(pdb_ms / slot_ms)
            deficit = min(deficit, window)
            state.ul_lcg_deficit_bytes[f.lcg] = deficit
            if deficit > 0:
                has_gbr = True

            delta = _URG_GBR_FLOOR + (1.0 - _URG_GBR_FLOOR) * (
                min(1.0, deficit / window) if window > 0 else 0.0
            )
            worst_urgency01 = max(worst_urgency01, u_lcg * priority_weight * delta)

            rem_slots = int(remaining_pdb / slot_ms)
            if rem_slots < 1:
                rem_slots = 1
            target = (deficit + obligation) // rem_slots
            if target < obligation:
                target = obligation
            max_burst = int((f.mfbr_bps / 8.0) / slots_per_sec) * 2
            if max_burst < obligation * 2:
                max_burst = obligation * 2
            if target > max_burst:
                target = max_burst

            guaranteed_bytes += target
            overflow = lcg_estimate - target
            if overflow > 0:
                be_bytes += overflow

        return has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes, worst_urgency01

    def _dl_stamp(
        self, fills: list[tuple[int, int]], ue_id: int, slot_index: int,
    ) -> None:
        """Last-grant-slot stamping only. Needed so _dl_gbr_and_pdb's
        remaining_pdb computation reflects real grant history instead of
        "never granted" every cycle. Gated per filled flow, matching
        reservation.py::_dl_drain_and_stamp's own (found-and-fixed)
        stamp gate -- stamps only flows _dl_fill actually gave bytes to,
        not every flow of a granted UE.
        """
        state = self._ue_state[ue_id]
        for qfi, _byts in fills:
            state.dl_flow_last_grant_slot[qfi] = slot_index

    def _dl_drain(
        self, fills: list[tuple[int, int]], ue_id: int, bler: float,
    ) -> None:
        """ia_p5g_drain_vq_dl, ia_p5g_scheduler.c:2002-2035 -- per-LCID,
        (1-bler)-discounted. See module docstring for the DL-drain-
        against-placeholder caveat: ground truth drains against
        dl_lcid_budget (the real LCP fill, commit 5's job), this commit
        drains against _dl_fill's placeholder split instead -- the
        arithmetic here is faithful, its input is not, until commit 5.
        """
        state = self._ue_state[ue_id]
        delivery_rate = max(0.0, min(1.0, 1.0 - bler))
        for qfi, byts in fills:
            delivered_bits = byts * 8.0 * delivery_rate
            state.vq_dl[qfi] = max(0.0, state.vq_dl.get(qfi, 0.0) - delivered_bits)

    def _ul_stamp(self, ue_id: int, buffers: BufferView, slot_index: int) -> None:
        """Last-grant-slot stamping only. Gated per-active-LCG on
        estimated_ul_buffer_per_lcg > 0, matching reservation.py::
        _ul_drain_and_stamp's own (found-and-fixed) stamp gate --
        iterates self._flows directly, not the candidate's already-
        filtered flow list, so a crumb-gated-to-zero-report LCG with a
        real per-LCG estimate still gets stamped.
        """
        state = self._ue_state[ue_id]
        seen_lcgs: set[int] = set()
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            if buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg <= 0:
                continue
            seen_lcgs.add(f.lcg)
            state.ul_lcg_last_grant_slot[f.lcg] = slot_index

    def _ul_drain(
        self, ue_id: int, buffers: BufferView, tb_size_bytes: int,
    ) -> None:
        """ia_p5g_drain_vq_ul, ia_p5g_scheduler.c:3728-3769 -- proportional
        split of the FULL raw tb_size across active LCGs by BSR-buffer
        share (1/n_active fallback when total buffer reads 0). Confirmed
        by reading the whole function body this commit: NO bler discount
        anywhere in it, unlike DL's drain -- a genuine asymmetry, not an
        oversight. Iterates self._flows directly (same pattern as
        _ul_stamp), not a pre-filtered candidate list.
        """
        state = self._ue_state[ue_id]
        active: dict[int, int] = {}
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in active:
                continue
            buf = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if buf <= 0:
                continue
            active[f.lcg] = buf
        if not active:
            return
        total_buf = sum(active.values())
        grant_bits = tb_size_bytes * 8.0
        for lcg, buf in active.items():
            fraction = (buf / total_buf) if total_buf > 0 else (1.0 / len(active))
            state.vq_ul[lcg] = max(
                0.0, state.vq_ul.get(lcg, 0.0) - grant_bits * fraction
            )

    def _update_vq_dl(self, ue_id: int, buffers: BufferView) -> None:
        """ia_p5g_update_vq_dl, ia_p5g_scheduler.c:1835-1894 -- grow by
        Tier-1's DL target rate this slot, then clamp to the
        ARRIVAL-DELTA windowed ceiling (matches the header; see module
        docstring for the UL case, which does not). Ceiling inputs
        (_arr_hist/_del_hist) are frozen once per Tier-1 cycle inside
        _compute_demand_bps, not updated here -- confirmed directly
        against the C: dl_arrived_hist/dl_delivered_hist are written
        only inside the Tier-1 demand block (:1264-1265), read-only in
        this function. LCID < 4 (SRBs) skipped.
        """
        state = self._ue_state[ue_id]
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "DL":
                continue
            r_bps = self._targets_bps.get((f.ue_id, f.qfi), 0.0)
            vq = state.vq_dl.get(f.qfi, 0.0) + r_bps * self.slot_duration_s

            key = (f.ue_id, f.qfi)
            st = buffers.state(f.ue_id, f.qfi)
            del_cum = buffers.delivered_cum(f.ue_id, f.qfi)
            arr_cum = del_cum + st.bytes_queued
            arr_w_bits = (arr_cum - self._arr_hist.get(key, 0.0)) * 8.0
            del_w_bits = (del_cum - self._del_hist.get(key, 0.0)) * 8.0
            target_w_bits = r_bps * _TIER1_PERIOD_S
            ceiling = max(0.0, min(arr_w_bits, target_w_bits) - del_w_bits)

            state.vq_dl[f.qfi] = max(0.0, min(vq, ceiling))

    def _update_vq_ul(self, ue_id: int, buffers: BufferView) -> None:
        """ia_p5g_update_vq_ul, ia_p5g_scheduler.c:3578-3687 -- grows
        identically to DL, but the ceiling is the BACKLOG-BOUND/CATCHUP
        form (the bugfix, :3608-3654), not arrival-delta -- confirmed
        again this commit: the function no longer reads ul_arrived_hist/
        arr_W at all. See module docstring for the full in-code
        rationale (starvation collapses arrival-delta to ~0 exactly when
        the evidence of starvation is most needed) -- this is the
        second of this port's four documented comment-vs-code instances;
        port the code, not the header. Catch-up horizon is
        _VQ_UL_CATCHUP_N Tier-1 windows. LCG 0 excluded structurally (no
        FlowConfig models SRB traffic, same convention _ul_gbr_and_pdb/
        _ul_stamp already use), lcid = lcg + 3, per-LCG gate on
        estimated_ul_buffer_per_lcg > 0.
        """
        state = self._ue_state[ue_id]
        seen_lcgs: set[int] = set()
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            st = buffers.state(f.ue_id, f.qfi)
            if st.estimated_ul_buffer_per_lcg <= 0:
                continue
            seen_lcgs.add(f.lcg)

            r_bps = self._targets_bps.get((f.ue_id, f.qfi), 0.0)
            vq = state.vq_ul.get(f.lcg, 0.0) + r_bps * self.slot_duration_s

            key = (f.ue_id, f.qfi)
            del_cum = buffers.delivered_cum(f.ue_id, f.qfi)
            del_w_bits = (del_cum - self._del_hist.get(key, 0.0)) * 8.0
            target_w_bits = r_bps * _TIER1_PERIOD_S
            backlog_bits = st.estimated_ul_buffer_per_lcg * 8.0
            catchup_w_bits = _VQ_UL_CATCHUP_N * target_w_bits
            ceiling = max(0.0, min(backlog_bits, catchup_w_bits) - del_w_bits)

            state.vq_ul[f.lcg] = max(0.0, min(vq, ceiling))

    def _ul_base_q(self, ue_id: int, buffers: BufferView) -> float:
        """ia_p5g_ul_metric, ia_p5g_scheduler.c:3696-3726 -- Sigma vq_ul
        over LCGs where EITHER estimated_ul_buffer_per_lcg > 0 OR
        vq_ul > 0 (the OR-gate starvation-prevention bugfix, cited
        incident: "d639 zero grants for 55s"). Iterates self._flows
        directly, not a pre-filtered candidate flow list -- matching
        _ul_stamp/_ul_gbr_and_pdb's own established pattern: a flow
        whose BSR has decayed to zero (and so was excluded from this
        UE's candidate flow list upstream, by the bytes_reported > 0
        pre-filter in _allocate_direction) must still contribute here
        if its vq_ul is still positive. NOTE: that upstream pre-filter
        is itself NOT OR-gate-aware -- a UE with zero bytes_reported on
        EVERY UL flow never becomes a candidate at all regardless of
        vq_ul, so this fix only reaches a UE that has already cleared
        that gate via some other flow. Flagged as a known caveat
        (README.md sec8), not fixed here -- out of this commit's scope.
        """
        state = self._ue_state[ue_id]
        seen_lcgs: set[int] = set()
        total = 0.0
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            seen_lcgs.add(f.lcg)
            buf = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            vq = state.vq_ul.get(f.lcg, 0.0)
            if buf <= 0 and vq <= 0.0:
                continue
            total += vq
        return total

    def _emit_grant(
        self,
        ue_id: int,
        direction: str,
        prbs_used: int,
        tbs_bytes: int,
        ue_flows: list[FlowConfig],
        buffers: BufferView,
        cce_cost: int,
        snr_used_db: float,
        slot_index: int,
        bler: float,
    ) -> list[Allocation]:
        if direction == "UL":
            self._ul_stamp(ue_id, buffers, slot_index)
            self._ul_drain(ue_id, buffers, tbs_bytes)
            # The gNB sizes the block; the UE fills it (TS 38.321
            # sec5.4.3.1). sim/ue_lcp.py performs the real split on the
            # driver side -- unchanged from the pre-rewrite file's own
            # convention, see module docstring and docs/phase2-plan.md
            # sec3/D1.
            return [
                Allocation(
                    ue_id=ue_id, qfi=-1, direction=direction,
                    prbs=prbs_used, bytes_capacity=tbs_bytes,
                    cce_cost=cce_cost, snr_used_db=snr_used_db,
                    ue_grant=True,
                )
            ]

        fills = self._dl_fill(ue_flows, tbs_bytes, buffers)
        self._dl_stamp(fills, ue_id, slot_index)
        self._dl_drain(fills, ue_id, bler)
        out: list[Allocation] = []
        for i, (qfi, byts) in enumerate(fills):
            out.append(
                Allocation(
                    ue_id=ue_id, qfi=qfi, direction=direction,
                    prbs=prbs_used if i == 0 else 0,
                    bytes_capacity=byts,
                    cce_cost=cce_cost if i == 0 else 0,
                    snr_used_db=snr_used_db,
                )
            )
        return out

    def _dl_fill(
        self, ue_flows: list[FlowConfig], tbs_bytes: int, buffers: BufferView
    ) -> list[tuple[int, int]]:
        """Placeholder DL fill -- priority order, then backlog. NOT the
        real single-pass SRB-exempt LCP
        (``ia_p5g_compute_lcp_budget``/``nr_generate_dlsch_pdu``,
        ``docs/phase2-plan.md`` sec2.1) -- that sorts DRBs by
        ``(priority ASC, vq_dl DESC)``. Upgraded in commit 5 (also then
        a joint VQ-correction commit -- see module docstring), mirroring
        how reservation's own commit-1 placeholder was upgraded in its
        commit 6.
        """
        order = sorted(
            ue_flows,
            key=lambda f: (
                f.priority_level,
                -buffers.state(f.ue_id, f.qfi).bytes_queued,
            ),
        )
        fills: list[tuple[int, int]] = []
        remaining = tbs_bytes
        for f in order:
            if remaining <= 0:
                break
            backlog = buffers.state(f.ue_id, f.qfi).bytes_queued
            take = min(backlog, remaining)
            if take > 0:
                fills.append((f.qfi, take))
                remaining -= take
        return fills
