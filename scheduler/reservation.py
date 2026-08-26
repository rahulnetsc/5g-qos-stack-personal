"""Reservation 5G QoS scheduler -- built fresh from ``oai-branches/reservation/``.

Phase 2 (``docs/phase2-plan.md``): unlike ``two_tier.py``, no prior Python
exists for this scheduler at all. This module is built up commit by commit,
each one landing a single mechanism from the vendored C source; see
``docs/oai-port-map.md``'s "Phase 2 -- reservation" section for the
file:line correspondence and ``docs/phase2-plan.md`` sec4 for the full
checklist.

Commit 1 built: ``Scheduler`` protocol conformance, per-UE throughput
state, and the bare PF coefficient as the only ranking criterion.

Commit 2 (this commit) adds sort tiers ABOVE the coefficient -- but only
the tiers this simulator can actually source. Ground truth is 5 tiers on
UL (SRB -> liveness -> GBR -> sched_inactive-last -> PDB/coef) and 4 on
DL (SRB -> liveness(TA) -> GBR -> PDB/coef; DL genuinely has no
sched_inactive tier at all, confirmed absent by reading
gNB_scheduler_dlsch.c's UEsched_t struct directly, not merely expressed
differently). Two tiers are current no-ops, for two DIFFERENT reasons,
both recorded as README.md sec8 [OPEN: PHASE2] entries rather than
silently approximated:

- ``has_srb`` (T1, top tier, BOTH directions): hardcoded False. This
  simulator has no SRB/RRC-signaling traffic model at all --
  ``scheduler/flow.py::FlowConfig`` only ever represents a QFI-based DRB,
  and the LCG0-holds-a-GBR-DRB case (FIVE_QI_LCG's QFI 1/3 mapping) is
  exactly what the C's own ``lcg0_is_drb`` check excludes from counting
  as SRB -- so even an "LCG==0" heuristic would be a wrong port, not a
  degraded one. A standing limitation, not a "revisit later" gap.
- ``liveness``/``sched_inactive`` (UL tiers 2/4, DL tier 2): need a
  ``do_sched``-equivalent (UL: SR-or-inactivity trigger for a
  zero-backlog UE) or a TA-pending signal (DL) that the ``Scheduler``
  protocol does not expose today. ``sim/ul_access.py``'s SR-report-floor
  is not a usable proxy -- verified it only fires when
  ``bytes_queued > 0`` (``sim/bsr.py:381-392``), i.e. for real backlog
  the estimate under-reports, not for a genuinely-empty UE. Unblocking
  this is a cross-cutting ``Scheduler``-protocol change affecting every
  scheduler, not a sort-tier-commit-sized change -- its own future
  commit if ever taken up.

Commit 3 (this commit) replaces the coarse GBR proxy with the real thing:
per-LCG (UL) / per-flow (DL) deficit accumulate/cap/target-spread/
overflow-to-BE, verified element-for-element against
``gNB_scheduler_ulsch.c:2251-2278`` / ``gNB_scheduler_dlsch.c:377-409``.
``has_gbr`` now means "this UE has an active unfulfilled deficit," not
"has a GBR flow with any backlog." This does NOT move either
comparator's tier position -- ``_ul_rank_key``/``_dl_rank_key`` are
untouched by this commit; only the *content* feeding their GBR slot
changed. Also fixes a real bug found scoping this commit: commit 2's
``pdb_ms`` used HOL delay as a stand-in for "remaining PDB," but ground
truth's ``ul_best_remaining_pdb_ms``/``dl_best_remaining_pdb_ms`` is
time-since-last-grant, a different quantity -- see
``docs/oai-port-map.md`` rows 18/19 for the full correction note.

What commit 3 deliberately does NOT do: wire ``guaranteed_bytes``/
``be_bytes`` into grant *sizing* (ground truth's own ``ul_target``/
``dl_target``, ``gNB_scheduler_ulsch.c:2496``/``_dlsch.c:1009``) -- grant
sizing stays backlog-based, same as every other scheduler in this repo,
pending a future commit (see ``docs/phase2-plan.md``'s reservation
checklist). Nor does it build the UL-only "silence detection" deficit
reset (``gNB_scheduler_ulsch.c:2286-2296``) or the post-grant deficit
*drain* (the already-known bug-for-bug full-``tb_size``-credit
mechanism, commit 5) -- last-grant-slot *stamping* lands here (needed to
fix the ``pdb_ms`` bug above), but *decrementing* the deficit on a grant
is a different field, cleanly separable, and stays commit 5's job.

Still explicitly deferred to later commits: the follower budget that caps
a UE's grant to protect UEs ranked behind it (commit 4), the deficit
*drain* bug-for-bug (commit 5), the real two-pass SRB/DRB DL LCP
(commit 6, replacing ``_dl_fill``'s placeholder below), and MCS
selection via OLLA (commit 8/9).

Like ``two_tier.py``, this package depends only on stdlib and its own
modules -- never on ``sim``. That boundary is what makes the uplink
intra-TB split a non-issue here: a UL grant is emitted as a single opaque
``ue_grant=True`` Allocation (the same convention ``sim/baselines/_mac.py``
and ``two_tier.py`` already use), and ``sim/ue_lcp.py`` performs the real
per-flow split entirely on the driver side. This scheduler's ranking reads
only UE-aggregate quantities (``bytes_reported`` summed across a UE's
flows in a direction, and a per-UE throughput EWMA) -- never a per-flow
split -- matching the real gNB's own visibility (README.md sec7: UL
virtual-queue state in ``ia_p5g_scheduler.c`` is per-LCG, not per-flow).
"""

from dataclasses import dataclass, field

from .flow import FlowConfig
from .interfaces import Allocation, BufferView, ChannelView, GridView, SlotView
from .link import bits_per_prb, cce_aggregation_level

# gNB_scheduler_ulsch.c:2205-2213, gNB_scheduler_dlsch.c:814-821: the PF
# coefficient's `tbs` is a hypothetical grant at a hardcoded rbSize=1 and a
# fixed 10-symbol duration -- nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, layers)
# -- NOT the slot's real dl_symbols/ul_symbols. The "10" is symbols, not
# slots, despite the C's own inline comment ("hypothetical number of
# slots"): it lines up with nr_compute_tbs's 4th parameter at every other
# call site in this codebase (e.g. sim/power.py's nrOfSymbols), and this
# scheduler has no other notion of "10 slots" anywhere. Verified directly
# against both C files while scoping this commit, not assumed.
_PF_COEF_HYPOTHETICAL_SYMBOLS = 10

# gNB_scheduler_ulsch.c:2083-2087, gNB_scheduler_dlsch.c:750-752:
# thr_ue = (1-a)*thr_ue + a*current_bytes, a=0.01, units bytes (not bits).
_THR_EWMA_ALPHA = 0.01


@dataclass
class _UeState:
    """Per-UE throughput EWMA, one instance per UE, both directions.

    Real hardware's `current_bytes` accumulation site (grant-time vs.
    confirmed-delivery-time) isn't visible in the vendored C -- the
    ``Scheduler`` protocol has no post-grant delivery-confirmation
    callback, so (matching every existing scheduler's identical
    constraint) this is updated at grant time from an *expected*-delivery
    estimate (``tbs_bytes * (1 - bler)``), not a later confirmed outcome.

    Commit 3: GBR deficit + last-grant-slot tracking, keyed by LCG on UL
    (matching ground truth's own per-LCG granularity) and by qfi on DL
    (matching ground truth's own per-LCID granularity) -- see
    docs/phase2-plan.md sec2.2's DL/UL granularity asymmetry. Last-grant-
    slot stamping feeds the "remaining PDB" computation (the commit-2
    pdb_ms fix); deficit *draining* on a grant is commit 5's job, a
    different field the C happens to update in the same code block.
    """

    dl_thr_bytes_per_slot: float = 0.0
    ul_thr_bytes_per_slot: float = 0.0
    ul_lcg_deficit_bytes: dict[int, int] = field(default_factory=dict)
    ul_lcg_last_grant_slot: dict[int, int] = field(default_factory=dict)
    dl_flow_deficit_bytes: dict[int, int] = field(default_factory=dict)
    dl_flow_last_grant_slot: dict[int, int] = field(default_factory=dict)


# Deficit accumulation gating differs between directions -- a real
# asymmetry, not shared code. UL's outer per-LCG loop
# (gNB_scheduler_ulsch.c:2230) gates the WHOLE block -- obligation,
# deficit accumulate/cap, and target -- on
# estimated_ul_buffer_per_lcg > 0: a UL LCG's deficit FREEZES the moment
# its per-LCG estimate reads 0. DL's block (gNB_scheduler_dlsch.c:377-410)
# accumulates the deficit and updates has_unfulfilled_gbr UNCONDITIONALLY
# for every GBR-configured LCID (:381-388) -- only the target/overflow
# sub-step is gated on `bytes_in_buffer > 0` (:391). So a DL GBR flow's
# deficit keeps growing through silence; a UL one does not. Verified by
# reading both exact ranges directly, not assumed from the charter's
# "identical formula" summary (true for the arithmetic; false for when
# it runs).


@dataclass
class _Candidate:
    ue_id: int
    flows: list[FlowConfig]
    bits_per_rb: int
    bler: float
    snr_db: float
    coef: float
    # Sort-tier fields (commit 2). has_srb is a permanent, hardcoded
    # no-op (see module docstring); has_gbr is a coarse placeholder
    # pending commit 3/5's real deficit tracking; pdb_ms is fully real.
    has_srb: bool = False
    has_gbr: bool = False
    pdb_ms: float = float("inf")


class Reservation:
    """Per-slot sort-and-greedily-fill scheduler -- no LP, no virtual
    queue, no floor state machine (those belong to two-tier). Every UE
    candidate for a slot's grant gets a comparator key; ``qsort`` on that
    key (here, Python's ``sorted``) produces the grant order.
    """

    def __init__(self) -> None:
        self._flows: list[FlowConfig] = []
        self._ue_state: dict[int, _UeState] = {}

    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: GridView,
    ) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        self._ue_state = {f.ue_id: _UeState() for f in flows}

    def allocate(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
    ) -> list[Allocation]:
        # gNB_scheduler.c:246,251: nr_schedule_ulsch runs strictly before
        # nr_schedule_ue_spec within a slot -- a hard ordering dependency,
        # not a threading artefact (docs/phase2-plan.md sec2.2). This
        # commit has no cross-direction state, so the order isn't yet
        # independently observable in output, but getting it right now
        # avoids a silent reorder once one exists.
        out: list[Allocation] = []
        if slot.ul_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "UL"))
        if slot.dl_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "DL"))
        return out

    def _allocate_direction(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
        direction: str,
    ) -> list[Allocation]:
        symbols = slot.ul_symbols if direction == "UL" else slot.dl_symbols

        ue_flows: dict[int, list[FlowConfig]] = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            ue_flows.setdefault(f.ue_id, []).append(f)
        if not ue_flows:
            return []

        # gNB_scheduler_ulsch.c:2083-2087 / _dlsch.c:750-752: the
        # throughput EWMA is touched only for UEs being considered as a
        # scheduling candidate this slot (i.e. with pending data) -- NOT
        # a blanket every-UE-every-slot decay the way
        # sim/baselines/pf.py's own _r_avg is. A UE with nothing queued
        # this slot keeps last-known thr_ue untouched, matching the C.
        candidates: list[_Candidate] = []
        for ue_id, flows in ue_flows.items():
            state = self._ue_state[ue_id]
            if direction == "UL":
                state.ul_thr_bytes_per_slot *= 1.0 - _THR_EWMA_ALPHA
            else:
                state.dl_thr_bytes_per_slot *= 1.0 - _THR_EWMA_ALPHA

            snr = channel.get_reported_snr_db(ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue

            # gNB_scheduler_ulsch.c:2205-2213,2301-2302 /
            # _dlsch.c:814-824: coef = hypothetical_1rb_tbs / max(thr, 1.0).
            hyp_bits, _ = bits_per_prb(snr, symbols=_PF_COEF_HYPOTHETICAL_SYMBOLS)
            hyp_tbs_bytes = hyp_bits // 8
            thr = (
                state.ul_thr_bytes_per_slot
                if direction == "UL"
                else state.dl_thr_bytes_per_slot
            )
            coef = hyp_tbs_bytes / max(thr, 1.0)

            # has_srb: hardcoded False -- no SRB/RRC-signaling traffic
            # model exists in this simulator (README.md sec8
            # [OPEN: PHASE2], module docstring above). Not a heuristic;
            # a documented permanent no-op.
            has_srb = False

            # has_gbr / pdb_ms: real GBR deficit accumulate/cap/target-
            # spread/overflow-to-BE (gNB_scheduler_ulsch.c:2251-2278 /
            # _dlsch.c:377-409), replacing commit 2's coarse "any GBR
            # flow has backlog" placeholder -- has_gbr now means "has an
            # active unfulfilled deficit." pdb_ms is now the C's actual
            # "remaining PDB" (time since last grant, not HOL delay --
            # a correction to commit 2, see docs/oai-port-map.md rows
            # 18/19 for the full note on why HOL delay was the wrong
            # proxy for this specific field).
            if direction == "UL":
                has_gbr, pdb_ms, _guaranteed, _be = self._ul_gbr_and_pdb(
                    ue_id, buffers, slot.slot_index
                )
            else:
                has_gbr, pdb_ms, _guaranteed, _be = self._dl_gbr_and_pdb(
                    ue_id, buffers, slot.slot_index
                )

            candidates.append(
                _Candidate(
                    ue_id, flows, bits_per_rb, bler, snr, coef,
                    has_srb=has_srb, has_gbr=has_gbr, pdb_ms=pdb_ms,
                )
            )

        if not candidates:
            return []

        candidates.sort(key=lambda c: self._rank_key(c, direction))

        prbs_left = slot.prb_count
        cce_left = slot.pdcch_cce_budget
        out: list[Allocation] = []
        for c in candidates:
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(c.snr_db)
            if cce_left < cce_cost:
                # Try lower-AL candidates further down the list.
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
                # Last-grant-slot stamping (commit 3, fixes commit 2's
                # pdb_ms proxy) -- NOT the deficit *drain*/decrement,
                # which is a different field and stays commit 5's job
                # (gNB_scheduler_ulsch.c:2761-ish, post_process_ulsch).
                for f in c.flows:
                    state.ul_lcg_last_grant_slot[f.lcg] = slot.slot_index
            else:
                state.dl_thr_bytes_per_slot += _THR_EWMA_ALPHA * expected_bytes
                for f in c.flows:
                    state.dl_flow_last_grant_slot[f.qfi] = slot.slot_index

            out.extend(
                self._emit_grant(
                    c.ue_id, direction, prbs_used, tbs_bytes, c.flows,
                    buffers, cce_cost, c.snr_db,
                )
            )
        return out

    def _ul_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, float, int, int]:
        """UL GBR deficit accumulate/cap/target-spread/overflow-to-BE
        (gNB_scheduler_ulsch.c:2229-2284), plus the remaining-PDB
        computation the same per-LCG loop drives (:2239-2249). Returns
        ``(has_gbr, remaining_pdb_ms, guaranteed_bytes, be_bytes)`` --
        the last two are real (fidelity-checkable), but NOT yet consumed
        by grant sizing (see module docstring / docs/phase2-plan.md).

        Gated per-LCG on ``estimated_ul_buffer_per_lcg > 0`` (:2230) --
        NOT on ``bytes_reported`` (the crumb-collapsed view eligibility
        elsewhere uses) -- matching the C exactly: a UL LCG's deficit
        freezes the moment its per-LCG estimate reads 0, whether or not
        the UE itself is a candidate this slot. Iterates ``self._flows``
        directly (every one of this UE's UL flows), not the pre-filtered
        eligible subset passed into the candidate loop, so a
        currently-crumb-collapsed LCG still gets evaluated here.

        Per-LCG, first-flow-found wins a shared LCG (matching the C's
        own ``lc_config`` linear-scan-then-``break``, :2232-2234,2282) --
        dormant/unexercised today, the same H5 scenario gap
        ``README.md`` sec8 already names for BSR aliasing.
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s

        seen_lcgs: set[int] = set()
        has_gbr = False
        best_remaining_pdb = float("inf")
        guaranteed_bytes = 0
        be_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            lcg_estimate = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if lcg_estimate <= 0:
                continue
            seen_lcgs.add(f.lcg)

            last_grant = state.ul_lcg_last_grant_slot.get(f.lcg)
            if last_grant is None:
                remaining_pdb = f.pdb_ms
            else:
                slots_since = slot_index - last_grant
                remaining_pdb = max(
                    0.0, f.pdb_ms - slots_since * self.slot_duration_s * 1000.0
                )
            best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += lcg_estimate  # non-GBR LCG: entire buffer is BE
                continue

            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.ul_lcg_deficit_bytes.get(f.lcg, 0) + obligation
            window = obligation * (f.pdb_ms * slots_per_sec / 1000.0)
            deficit = min(deficit, window)
            state.ul_lcg_deficit_bytes[f.lcg] = deficit
            if deficit > 0:
                has_gbr = True

            rem_slots = max(1.0, remaining_pdb * slots_per_sec / 1000.0)
            target = max(obligation, (deficit + obligation) / rem_slots)
            max_burst = obligation * 2
            if f.mfbr_bps > 0:
                max_burst = max(max_burst, int((f.mfbr_bps / 8.0) / slots_per_sec) * 2)
            target = min(target, max_burst)

            guaranteed_bytes += int(target)
            overflow = lcg_estimate - target
            if overflow > 0:
                be_bytes += int(overflow)

        return has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes

    def _dl_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, float, int, int]:
        """DL GBR deficit accumulate/cap/target-spread/overflow-to-BE
        (gNB_scheduler_dlsch.c:377-409), plus remaining-PDB (:358-367).
        Returns ``(has_gbr, remaining_pdb_ms, guaranteed_bytes,
        be_bytes)`` -- same not-yet-sizing-consumed caveat as UL's.

        Deficit accumulation and ``has_unfulfilled_gbr`` are UNCONDITIONAL
        for every GBR-configured flow (:381-388) -- unlike UL, this does
        NOT gate on current buffer occupancy, so a DL GBR flow's deficit
        keeps growing through silence. Only the target/overflow sub-step
        gates on ``bytes_queued > 0`` (:391). A real asymmetry, verified
        by reading both exact ranges directly -- see this module's
        top-of-file note.
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s

        has_gbr = False
        best_remaining_pdb = float("inf")
        guaranteed_bytes = 0
        be_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "DL":
                continue
            bytes_queued = buffers.state(f.ue_id, f.qfi).bytes_queued

            last_grant = state.dl_flow_last_grant_slot.get(f.qfi)
            if last_grant is None:
                remaining_pdb = f.pdb_ms
            else:
                slots_since = slot_index - last_grant
                remaining_pdb = max(
                    0.0, f.pdb_ms - slots_since * self.slot_duration_s * 1000.0
                )
            if bytes_queued > 0:
                best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += bytes_queued  # non-GBR: entire buffer is BE
                continue

            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.dl_flow_deficit_bytes.get(f.qfi, 0) + obligation
            window = obligation * (f.pdb_ms * slots_per_sec / 1000.0)
            deficit = min(deficit, window)
            state.dl_flow_deficit_bytes[f.qfi] = deficit
            if deficit > 0:
                has_gbr = True

            if bytes_queued <= 0:
                continue  # accumulation is unconditional; target is not

            rem_slots = max(1.0, remaining_pdb * slots_per_sec / 1000.0)
            target = max(obligation, (deficit + obligation) / rem_slots)
            max_burst = obligation * 2
            if f.mfbr_bps > 0:
                max_burst = max(max_burst, int((f.mfbr_bps / 8.0) / slots_per_sec) * 2)
            target = min(target, max_burst)

            guaranteed_bytes += int(target)
            overflow = bytes_queued - target
            if overflow > 0:
                be_bytes += int(overflow)

        return has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes

    def _rank_key(self, candidate: _Candidate, direction: str) -> tuple:
        """Dispatch to the direction's own comparator. UL and DL are
        genuinely different tier structures in ground truth (5 vs. 4
        tiers) -- see ``_ul_rank_key``/``_dl_rank_key``, kept as two
        independently-sourced methods even where their output currently
        coincides, never merged into one shared function.
        """
        if direction == "UL":
            return self._ul_rank_key(candidate)
        return self._dl_rank_key(candidate)

    def _ul_rank_key(self, c: _Candidate) -> tuple:
        """UL ground truth: 5 tiers, SRB -> liveness -> GBR ->
        sched_inactive-last -> PDB/coef (gNB_scheduler_ulsch.c:2010-2039).

        T1 (has_srb) is a permanent no-op here -- no SRB/RRC traffic
        model exists in this simulator (README.md sec8 [OPEN: PHASE2]).
        T2/T4 (liveness/sched_inactive) are a DEFERRED no-op pending a
        do_sched-equivalent signal (README.md sec8's other new entry).
        Commit 1's own coefficient (-c.coef) remains the tuple's final
        element, unchanged -- this method PREPENDS tiers ahead of it,
        it does not restructure the sort.

        Hedged, not asserted as fact: working through
        gNB_scheduler_ulsch.c's own boolean relationship between T2
        (liveness = sched_inactive && !ul_has_srb, :2339) and T4
        (sched_inactive, :2332) by exhaustive case analysis suggests T4
        may never produce a decisive comparator result in the real C
        either -- whenever sched_inactive=True, either has_srb=True (T1
        already resolves it) or liveness=True (T2 already resolves it
        ahead of T4). This is my own reading of the C, not verified by
        instrumenting it at runtime, and does not change what's ported:
        T4 is implemented exactly as the C runs it (moot today anyway,
        since sched_inactive itself is a deferred no-op).
        """
        return (
            0 if c.has_srb else 1,
            0 if c.has_gbr else 1,
            c.pdb_ms,
            -c.coef,
        )

    def _dl_rank_key(self, c: _Candidate) -> tuple:
        """DL ground truth: 4 tiers, SRB -> liveness(TA) -> GBR ->
        PDB/coef (gNB_scheduler_dlsch.c:692-715). DL's UEsched_t
        (:681-690) has NO sched_inactive field at all -- confirmed
        absent by reading the struct directly, not expressed
        differently -- so there is no T4-equivalent tier on this side,
        ever, regardless of the UL hedge above.

        T1 (has_srb) and T2 (TA-pending liveness) are no-ops for the
        same two reasons as UL's (README.md sec8), independently cited
        here even though this tuple currently comes out the same shape
        as ``_ul_rank_key``'s -- that is a data-availability coincidence
        (both directions happen to have exactly one real tier -- GBR --
        implementable today), not a decision to share a comparator.
        """
        return (
            0 if c.has_srb else 1,
            0 if c.has_gbr else 1,
            c.pdb_ms,
            -c.coef,
        )

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
            # driver side -- see this module's docstring and
            # docs/phase2-plan.md sec3/D1.
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
        real two-pass SRB/DRB LCP (gNB_scheduler_dlsch.c:1394-1463);
        that lands in commit 6. Deliberate, flagged placeholder -- see
        docs/oai-port-map.md row 17.
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
