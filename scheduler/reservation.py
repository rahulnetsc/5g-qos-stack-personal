"""Reservation 5G QoS scheduler -- built fresh from ``oai-branches/reservation/``.

Phase 2 (``docs/phase2-plan.md``): unlike ``two_tier.py``, no prior Python
exists for this scheduler at all. This module is built up commit by commit,
each one landing a single mechanism from the vendored C source; see
``docs/oai-port-map.md``'s "Phase 2 -- reservation" section for the
file:line correspondence and ``docs/phase2-plan.md`` sec4 for the full
checklist.

This commit (1) builds only: ``Scheduler`` protocol conformance, per-UE
throughput state, and the bare PF coefficient as the only ranking
criterion. Explicitly NOT here yet, each landing in its own later commit:
sort tiers above the coefficient (SRB / liveness / GBR / UL's
sched_inactive-last / PDB -- commit 2), the follower budget that caps a
UE's grant to protect UEs ranked behind it (commit 4), the GBR/best-effort
deficit split and its UL bug-for-bug drain (commit 3/5), the real two-pass
SRB/DRB DL LCP (commit 6, replacing ``_dl_fill``'s placeholder below), and
MCS selection via OLLA (commit 8/9).

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
            candidates.append(_Candidate(ue_id, flows, bits_per_rb, bler, snr, coef))

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
            else:
                state.dl_thr_bytes_per_slot += _THR_EWMA_ALPHA * expected_bytes

            out.extend(
                self._emit_grant(
                    c.ue_id, direction, prbs_used, tbs_bytes, c.flows,
                    buffers, cce_cost, c.snr_db,
                )
            )
        return out

    def _rank_key(self, candidate: _Candidate, direction: str) -> tuple:
        """Commit 1: the PF coefficient (descending) is the only tier.
        Commits 2+ PREPEND tuple elements ahead of this one (SRB,
        liveness, GBR, (UL only) sched_inactive-last, PDB) -- an addition
        to the key, not a restructure of the sort itself.
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
