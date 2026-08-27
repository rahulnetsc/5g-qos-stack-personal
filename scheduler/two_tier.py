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

Explicitly NOT here yet, each landing in its own later commit: the
windowed-ceiling virtual queue -- DL matching its own header, UL not
(commit 3), the UL floor's fruitless-shift/ADQ anti-starvation state
machine (commit 4), the real single-pass SRB-exempt DL LCP fill
(commit 5, replacing ``_dl_fill``'s placeholder below), MCS selection via
OLLA (commit 6), and a re-port of ``reset_ue``/``SchedulerContextReset``
against the new field layout (commit 7) -- this class implements no
``reset_ue`` at all until then; ``sim/driver.py`` discovers it via
``getattr(scheduler, "reset_ue", None)``, so its absence simply means
TwoTier is treated like PF (no context reset) in the interim, not an
oversight.

**Commit 2 (this commit) wires the real Tier-1 SCA/GLPK solve
(``scheduler/tier1.py``, rewritten from ``ia_p5g_scheduler.c`` -- see
that module's own docstring for the full ground-truth citation) in, but
its output feeds nothing yet.** ``_rank_key`` stays the commit-1
bootstrap PF coefficient until commit 3 lands the VQ that actually
consumes a Tier-1 target rate. So this commit computes and stores real
``_targets_bps`` every ``tier1_period_slots`` slots, and that's all --
predicted, and confirmed, to move zero `--check` numbers (see
``docs/phase2-plan.md``'s commit-2 entry). ``tier1_period_slots`` is
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
UE's flows in a direction) -- never a per-flow split, and (once the VQ
lands in commit 3) never a per-flow virtual queue on the UL side either,
matching ``docs/phase2-plan.md`` D1's requirement that UL state be
LCG-aggregate, the real gNB's own visibility (``ia_p5g_scheduler.c``'s
``vq_ul[UE][LCG]``, not per-flow).

**The per-UE throughput EWMA and PF coefficient below are a deliberate,
temporary engineering placeholder, not a ported mechanism.** Unlike
``reservation.py``, where this exact formula *is* real ground truth
(final comparator tiebreak, ``gNB_scheduler_{ul,dl}sch.c``), two-tier's
own ground-truth ranking is never PF-coefficient-shaped at any point --
it is VQ-sum-based (DL, commit 3) or VQ-plus-urgency-based (UL, commit 3)
from the start. This placeholder exists only so commit 1 has *some*
ranking rule while VQ doesn't exist yet, structurally mirroring
``reservation.py`` commit 1's own bootstrap shape and reusing its exact
constants (``_PF_COEF_HYPOTHETICAL_SYMBOLS = 10``, EWMA ``alpha = 0.01``)
as an engineering convention, not because two-tier's own
``gNB_scheduler_{ul,dl}sch.c`` has been checked and found to match --
it hasn't been, and this placeholder is deleted in commit 3, so it isn't
going to be. Do not add a C file:line citation for this formula in the
port-map row; record it as "no ground truth -- temporary bootstrap,
removed commit 3" instead, so a future reader doesn't go looking for a
citation that was never claimed.

The one piece of this file that *is* a live-source citation:
``gNB_scheduler.c:246,251`` (confirmed byte-identical across both
branches, ``oai-branches/README.md``) runs ``nr_schedule_ulsch`` before
``nr_schedule_ue_spec`` (DL) unconditionally, every slot -- UL-then-DL.
**The pre-rewrite ``two_tier.py`` had this backwards**: its own
``allocate()`` iterated ``("DL", "UL")``, DL first -- a real, live bug in
the scheduler that produced every existing TwoTier regression record,
not a cosmetic one. Fixed here.
"""

from dataclasses import dataclass

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
# convention _PF_COEF_HYPOTHETICAL_SYMBOLS/_THR_EWMA_ALPHA already use).
_UL_DEMAND_ALPHA = 0.3

# Bootstrap-only constant, borrowed from reservation.py's own PF
# coefficient convention (gNB_scheduler_ulsch.c:2205-2213,
# gNB_scheduler_dlsch.c:814-821 -- reservation's own citation, NOT
# verified against two-tier's own gNB_scheduler_{ul,dl}sch.c, which this
# scheduler's real ranking never uses at all -- see module docstring).
# Deleted along with the rest of this placeholder in commit 3.
_PF_COEF_HYPOTHETICAL_SYMBOLS = 10

# Bootstrap-only constant -- see module docstring. Not a citation to
# two-tier's own C source.
_THR_EWMA_ALPHA = 0.01


@dataclass
class _UeState:
    """Per-UE throughput EWMA, one instance per UE, both directions.

    Bootstrap-only state -- see module docstring. Decayed for every
    connected UE every slot (blanket decay), not gated on this-slot
    candidacy -- reservation's own commit 1 gated this on candidacy and
    found (commit 10a, ``docs/oai-port-map.md`` row 14) that ground
    truth actually decays unconditionally, gated only on a UL-failure/
    DRX signal this simulator's ``Scheduler`` protocol doesn't expose.
    Landing the corrected (blanket) form from the start here rather than
    repeating reservation's now-fixed mistake -- even though, for this
    placeholder, no C citation is being claimed either way.
    """

    dl_thr_bytes_per_slot: float = 0.0
    ul_thr_bytes_per_slot: float = 0.0


@dataclass
class _Candidate:
    ue_id: int
    flows: list[FlowConfig]
    bits_per_rb: int
    bler: float
    snr_db: float
    coef: float


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
        3 (VQ); computed and stored here regardless, so commit 3 doesn't
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
            if f.direction == "DL":
                arr_cum = buffers.delivered_cum(f.ue_id, f.qfi) + st.bytes_queued
                arr_w = arr_cum - self._arr_hist.get(key, 0.0)
                self._arr_hist[key] = arr_cum
                demand[key] = max(0.0, arr_w * 8.0 / elapsed_s)
            else:
                arr_cum = (
                    buffers.delivered_cum(f.ue_id, f.qfi)
                    + st.estimated_ul_buffer_per_lcg
                )
                arr_w = arr_cum - self._arr_hist.get(key, 0.0)
                self._arr_hist[key] = arr_cum
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

        # Blanket per-slot decay -- see _UeState's docstring.
        if direction == "UL":
            for state in self._ue_state.values():
                state.ul_thr_bytes_per_slot *= 1.0 - _THR_EWMA_ALPHA
        else:
            for state in self._ue_state.values():
                state.dl_thr_bytes_per_slot *= 1.0 - _THR_EWMA_ALPHA

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

            # Bootstrap-only coefficient -- see module docstring.
            hyp_bits, _ = bits_per_prb(snr, symbols=_PF_COEF_HYPOTHETICAL_SYMBOLS)
            hyp_tbs_bytes = hyp_bits // 8
            thr = (
                state.ul_thr_bytes_per_slot
                if direction == "UL"
                else state.dl_thr_bytes_per_slot
            )
            coef = hyp_tbs_bytes / max(thr, 1.0)
            candidates.append(_Candidate(ue_id, flows, bits_per_rb, bler, snr, coef))

        if not candidates:
            return []

        candidates.sort(key=self._rank_key)

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

            expected_bytes = tbs_bytes * (1.0 - c.bler)
            state = self._ue_state[c.ue_id]
            if direction == "UL":
                state.ul_thr_bytes_per_slot += _THR_EWMA_ALPHA * expected_bytes
            else:
                state.dl_thr_bytes_per_slot += _THR_EWMA_ALPHA * expected_bytes

            out.extend(
                self._emit_grant(
                    c.ue_id, direction, prbs_used, tbs_bytes, c.flows,
                    buffers, cce_cost, c.snr_db,
                )
            )
        return out

    def _rank_key(self, candidate: _Candidate) -> tuple:
        """Commit 1: the bootstrap PF coefficient (descending) is the
        only tier. Commit 3 replaces this entirely with the real VQ-sum
        (DL) / VQ-plus-urgency (UL) metric -- not an addition to this
        tuple the way reservation's sort tiers prepend onto its own
        coefficient, since two-tier's ground truth never uses this
        coefficient at all (see module docstring).
        """
        return (-candidate.coef,)

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
    ) -> list[Allocation]:
        if direction == "UL":
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
        ``(priority ASC, vq_dl DESC)``, and ``vq_dl`` doesn't exist until
        commit 3. Upgraded in commit 5, mirroring how reservation's own
        commit-1 placeholder was upgraded in its commit 6.
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
