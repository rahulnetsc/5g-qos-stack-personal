"""WP5 -- HARQ core state: N processes per UE per direction, and the
per-attempt combining-gain function.

Pure functions/state -- no simulator (driver.py/buffer.py) imports beyond
``sim.buffer`` (commit 4a, for the buffer-masking view below -- an allowed
``sim`` -> ``sim`` sibling import, not the ``scheduler`` boundary this
module already documents). This module DOES import
``scheduler.link.bler_for_mcs``/``bits_per_prb``/``mcs_threshold_for_snr``
(commit 2/4a) to compose combining gain with them; that's the allowed
dependency direction (``sim`` -> ``scheduler``, already used by
``sim/driver.py``), not the reverse -- ``scheduler/interfaces.py`` states
the package must depend on nothing outside itself, so this composition
lives here, not in ``scheduler/link.py`` (docs/wp5-plan.md Decision 1b).

Commit 1-3 landed this dormant/inert; commit 4a (DL) makes retry and
combining gain load-bearing for the first time. Every citation and
decision here is recorded in full in docs/wp5-plan.md -- this module's
docstrings repeat only what a reader needs to not silently misuse the
numbers.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from scheduler.link import bler_for_mcs, bits_per_prb, mcs_threshold_for_snr

Direction = Literal["DL", "UL"]

# Real OAI's own fallback-when-unconfigured process-pool sizes --
# nr_mac_common.c:2724-2744 (get_nrofHARQ_ProcessesForPDSCH/PUSCH),
# asymmetric by direction: DL defaults to 8, UL to 16, both capped at 16
# pre-Rel17 (docs/wp5-plan.md Decision 2). NOT the same claim as an
# invented default -- these are OAI's own fallback return values when RRC
# doesn't configure nrofHARQ_ProcessesForPDSCH/PUSCH explicitly. Whether
# THIS deployment's RRC overrides them is unconfirmed (README.md sec8).
#
# Commit 4a reinterpretation, recorded so the sweep isn't read against the
# old meaning: this is a ceiling on how many DIFFERENT flows of one UE can
# be simultaneously retrying at once, not a per-flow pipeline depth. A
# flow can only ever have ONE in-flight process at a time (HarqAware-
# BufferView below fully masks a flow's backlog while it has one pending,
# a correctness requirement, not a modeling choice -- see that class) --
# so 8/16 bounds concurrent *retrying flows per UE*, and the "1-2
# processes pending per UE" figure the mined branch's own writeup quotes
# (docs/wp5-plan.md sec1) was reasoned under a different, pipelining-depth
# reading that no longer applies here.
DEFAULT_DL_CAPACITY = 8
DEFAULT_UL_CAPACITY = 16


# ---------------------------------------------------------------------------
# Combining gain
# ---------------------------------------------------------------------------

# Ported from origin/feat/harq-bler-retx:scheduler/link.py (README.md sec3,
# docs/wp5-plan.md Decision 1) -- NOT the reachability-weighted
# effective_SE(delta) formula an earlier design conversation cited; that
# formula does not exist anywhere on that branch and is not built here
# (docs/wp5-plan.md sec0 / Decision 1).
#
# UNSOURCED CONSTANTS: the branch's own harq-bler-retx.md sec11 ("Spec
# grounding") states these dB values are "approximations derived from 3GPP
# NR LDPC link-level simulation results in the literature," with no
# specific curve or paper named -- the same epistemic tier as
# scheduler/link.py's own _MCS_TABLE ("crude staircase... not defensible
# at the PHY level"). Ported anyway (no better numbers exist on disk); see
# README.md sec8 [OPEN].
#
# SATURATION, flagged explicitly: retx_count values beyond the table (>3)
# clamp to the SAME bonus as retx_count=3 via .get()'s fallback (IR only --
# Chase has no such cap) -- ported as-is, not derived. This interacts with
# harq_round_max (a scenario's real retry cap, docs/wp5-plan.md sec2): if
# harq_round_max exceeds 4, every attempt past the third gets an
# identical, unvarying, uncalibrated bonus rather than a value that keeps
# reflecting diminishing returns.
_IR_GAIN_DB: dict[int, float] = {0: 0.0, 1: 4.0, 2: 6.5, 3: 8.0}
_CHASE_GAIN_DB_PER_RETX = 3.0


def combining_gain_db(retx_count: int, mode: str = "ir") -> float:
    """Effective SNR gain (dB) from HARQ combining at the given attempt.

    ``retx_count=0`` is the first (original) attempt -- no combining has
    happened yet, gain is 0.0 in both modes. Composes with
    ``scheduler/link.py::bler_for_mcs`` by adding into its
    ``true_snr_db`` argument (docs/wp5-plan.md Decision 1b) -- this is
    NOT a second BLER curve; ``bler_sigmoid`` (the mined branch's own
    paired curve) is deliberately not ported.

    mode="ir" (Incremental Redundancy, the 5G NR default): gain from
    ``_IR_GAIN_DB``, clamped at retx_count=3's value for any higher count
    -- see this module's SATURATION note above.
    mode="chase" (Chase Combining): linear 3.0 dB per retx, uncapped.
    """
    if mode == "ir":
        return _IR_GAIN_DB.get(retx_count, _IR_GAIN_DB[3])
    return _CHASE_GAIN_DB_PER_RETX * retx_count


def bler_for_mcs_with_combining(
    mcs_threshold_db: float,
    true_snr_db: float,
    retx_count: int = 0,
    mode: str = "ir",
) -> float:
    """``scheduler.link.bler_for_mcs``, with HARQ combining gain composed
    in as an SNR-domain bonus (docs/wp5-plan.md Decision 1b) -- NOT a
    second BLER curve; ``bler_for_mcs`` itself is untouched.

    ``retx_count=0`` (the default) makes this identical to calling
    ``bler_for_mcs`` directly -- ``combining_gain_db(0, ...)`` is 0.0 in
    both modes.

    Flagged (docs/wp5-plan.md Decision 1b, README.md sec8): this composes
    three uncalibrated constructs into one modelled probability --
    ``bler_for_mcs``'s doubles-per-dB slope, the ``combining_gain_db`` IR/
    Chase table, and its own ``base_bler`` default -- each individually
    flagged already, not previously as a composition.
    """
    return bler_for_mcs(mcs_threshold_db, true_snr_db + combining_gain_db(retx_count, mode))


def draw_dl_outcome(
    rng: np.random.Generator,
    true_snr_db: float,
    snr_used_db: float,
    retx_count: int,
    mode: str,
    symbols: int,
) -> bool:
    """One DL attempt's binary HARQ outcome (commit 4a). Mirrors
    ``sim/driver.py``'s existing mismatch-aware-vs-legacy BLER branching
    (``math.isnan(snr_used_db)`` selects the legacy, no-mismatch-modelling
    path used by tests that don't set ``Allocation.snr_used_db``), with
    ``combining_gain_db`` layered on for retries in both branches.

    Real HARQ is a per-transport-block binary decode outcome, not a
    continuous fraction -- there is no such thing as "70% of a TB." This
    is why commit 4a replaces the driver's previous ``delivered =
    bytes_capacity * (1 - bler)`` deterministic discount with a stochastic
    draw for DL: ``rng`` must be an INDEPENDENT stream from the channel/
    traffic RNG (docs/wp5-plan.md commit 4a design discussion), matching
    the existing ``cqi_seed = scenario.seed ^ 0xC9C9C9C9`` precedent in
    ``sim/driver.py`` -- otherwise introducing HARQ would silently
    reshuffle draws for flows that never even retry.

    Returns True (success -- deliver `tb_bytes` in full) or False
    (failure -- retry or abandon, driver.py decides which).
    """
    if math.isnan(snr_used_db):
        _, bler = bits_per_prb(true_snr_db + combining_gain_db(retx_count, mode), symbols=symbols)
    else:
        mcs_thresh = mcs_threshold_for_snr(snr_used_db)
        bler = bler_for_mcs_with_combining(mcs_thresh, true_snr_db, retx_count, mode)
    return rng.random() >= bler


# ---------------------------------------------------------------------------
# HARQ process pool
# ---------------------------------------------------------------------------


@dataclass
class HarqProcess:
    """One HARQ process's state, for one (ue_id, direction).

    ``qfi`` is meaningful only for DL (a DL grant is emitted per flow,
    ``scheduler/interfaces.py::Allocation``); UL grants are per-UE (the UE
    runs its own LCP over the granted TB, TS 38.321 sec5.4.3.1), so a UL
    process's ``qfi`` stays -1, matching ``Allocation.ue_grant``'s own
    "qfi is then meaningless (-1)" convention (UL retry is commit 4b, not
    built here).

    ``prbs``/``cce_cost``/``snr_used_db`` (commit 4a): the ORIGINAL
    grant's PRB count, DCI/CCE cost, and the scheduler's CQI-based MCS
    pick, replayed verbatim for every retry -- a retry never re-derives
    PRB sizing, re-consults the scheduler, or requests a fresh DCI budget
    (docs/wp5-plan.md Decision 4), a stated simplification. A retry still
    needs its own DCI, so ``cce_cost`` is real consumption, not overhead
    left uncounted.
    """

    pid: int
    ue_id: int
    direction: Direction
    busy: bool = False
    qfi: int = -1
    tb_bytes: int = 0
    retx_count: int = 0
    due_slot: int = -1
    prbs: int = 0
    cce_cost: int = 0
    snr_used_db: float = math.nan

    def reset(self) -> None:
        self.busy = False
        self.qfi = -1
        self.tb_bytes = 0
        self.retx_count = 0
        self.due_slot = -1
        self.prbs = 0
        self.cce_cost = 0
        self.snr_used_db = math.nan


class HarqProcessPool:
    """Per-(ue_id, direction) pool of ``HarqProcess``, sized asymmetrically
    by direction (``DEFAULT_DL_CAPACITY``/``DEFAULT_UL_CAPACITY`` above --
    docs/wp5-plan.md Decision 2; see that constant's own comment for the
    commit-4a reinterpretation of what the capacity ceiling now means).

    A UE with every process for a direction busy cannot receive a new TB
    on that direction this slot, full stop, regardless of backlog -- real
    OAI's ``available_dl_harq``/``available_ul_harq`` exhaustion (tracked
    there as ``harq_exhausted``). ``allocate()`` returns ``None`` in that
    case; the caller counts that as a diagnostic, not an error (commit 3's
    ``harq_exhausted_count``/``harq_allocate_calls`` pair in
    ``sim/driver.py``).
    """

    def __init__(
        self,
        dl_capacity: int = DEFAULT_DL_CAPACITY,
        ul_capacity: int = DEFAULT_UL_CAPACITY,
    ) -> None:
        self.dl_capacity = dl_capacity
        self.ul_capacity = ul_capacity
        self._pools: dict[tuple[int, Direction], list[HarqProcess]] = {}

    def _capacity(self, direction: Direction) -> int:
        return self.dl_capacity if direction == "DL" else self.ul_capacity

    def _pool(self, ue_id: int, direction: Direction) -> list[HarqProcess]:
        key = (ue_id, direction)
        pool = self._pools.get(key)
        if pool is None:
            pool = [
                HarqProcess(pid=i, ue_id=ue_id, direction=direction)
                for i in range(self._capacity(direction))
            ]
            self._pools[key] = pool
        return pool

    def allocate(
        self,
        ue_id: int,
        direction: Direction,
        tb_bytes: int,
        due_slot: int,
        qfi: int = -1,
        prbs: int = 0,
        cce_cost: int = 0,
        snr_used_db: float = math.nan,
    ) -> HarqProcess | None:
        """Claim a free process for a new TB. ``None`` if every process
        for this (ue_id, direction) is already busy (harq_exhausted)."""
        for proc in self._pool(ue_id, direction):
            if not proc.busy:
                proc.busy = True
                proc.qfi = qfi
                proc.tb_bytes = tb_bytes
                proc.retx_count = 0
                proc.due_slot = due_slot
                proc.prbs = prbs
                proc.cce_cost = cce_cost
                proc.snr_used_db = snr_used_db
                return proc
        return None

    def free(self, ue_id: int, direction: Direction, pid: int) -> None:
        self.get(ue_id, direction, pid).reset()

    def get(self, ue_id: int, direction: Direction, pid: int) -> HarqProcess:
        for proc in self._pool(ue_id, direction):
            if proc.pid == pid:
                return proc
        raise KeyError(
            f"no HARQ process pid={pid} for (ue_id={ue_id}, direction={direction})"
        )

    def in_flight_bytes(self, ue_id: int, direction: Direction) -> int:
        """Sum of ``tb_bytes`` across busy processes for this (ue_id,
        direction). Diagnostic only -- ``HarqAwareBufferView`` below masks
        by flow eligibility (``is_pending``), not by subtracting this
        sum, per that class's own FIFO-correctness argument."""
        return sum(p.tb_bytes for p in self._pool(ue_id, direction) if p.busy)

    def exhausted(self, ue_id: int, direction: Direction) -> bool:
        """True if every process for this (ue_id, direction) is busy."""
        return all(p.busy for p in self._pool(ue_id, direction))

    def is_pending(self, ue_id: int, direction: Direction, qfi: int = -1) -> bool:
        """True if a specific flow (DL: ``(ue_id, qfi)``; UL: ``ue_id``
        alone, ``qfi`` ignored -- commit 4b) already has an unresolved
        in-flight process. Drives ``HarqAwareBufferView``'s full masking
        and is also checked defensively in ``sim/driver.py`` before a new
        allocation, in case a scheduler ever grants an already-masked flow
        (it shouldn't, but this makes the invariant load-bearing rather
        than merely hoped-for)."""
        pool = self._pool(ue_id, direction)
        if direction == "UL":
            return any(p.busy for p in pool)
        return any(p.busy and p.qfi == qfi for p in pool)

    def due_this_slot(self, slot_index: int) -> list[HarqProcess]:
        """Every busy process across every (ue_id, direction) pool whose
        ``due_slot`` has arrived -- the retries/resolutions ``driver.py``
        must act on this slot, before ``scheduler.allocate()`` runs (their
        PRBs must be carved out of the slot budget first, docs/wp5-plan.md
        Decision 4). Plain linear scan -- fine at this repo's scale (WP7's
        ``docs/wp7-plan.md`` end-of-WP review flagged the same tradeoff
        for ``MessageLedger.completions_for``); revisit if a much larger
        UE count ever makes it a real cost."""
        return [
            proc
            for pool in self._pools.values()
            for proc in pool
            if proc.busy and proc.due_slot == slot_index
        ]


class HarqAwareBufferView:
    """Wraps a ``sim.buffer.BufferModel`` so ``scheduler.allocate()`` sees
    ZERO backlog (``bytes_queued`` and ``bytes_reported``) for any flow
    with an unresolved in-flight HARQ process -- DL only this commit
    (``is_pending`` is queried with ``direction="DL"``).

    This is a CORRECTNESS REQUIREMENT, not caution, and must not be
    "optimised" to a partial mask (e.g. ``bytes_queued - tb_bytes``):
    ``sim/buffer.py``'s ``drain()``/``expire()`` are strictly FIFO by
    BYTE COUNT, not by chunk identity. If a second grant were allowed for
    the same flow while the first is still pending, and it resolved
    (ACKed) before the first, draining its byte count would remove the
    WRONG bytes from the head -- the still-pending, OLDER chunk, not the
    newer one that actually just succeeded. Full masking is what makes
    "at most one in-flight process per flow" (docs/wp5-plan.md commit 4a)
    actually guarantee that the reserved bytes are still exactly at the
    head, unperturbed, whenever resolution finally reads them back out
    with ``buffers.drain(...)``. A partial mask would silently reintroduce
    that corruption the moment a flow accumulates enough new backlog to
    look grantable again while still mid-retry.
    """

    def __init__(self, buffers, pool: HarqProcessPool) -> None:
        self._buffers = buffers
        self._pool = pool

    def state(self, ue_id: int, qfi: int):
        real = self._buffers.state(ue_id, qfi)
        if self._pool.is_pending(ue_id, "DL", qfi):
            masked = copy.copy(real)
            masked.bytes_queued = 0
            masked.bytes_reported = 0
            return masked
        return real

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        return self._buffers.hol_delay_s(ue_id, qfi, now_s)

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        return self._buffers.arrived_cum(ue_id, qfi)

    def delivered_cum(self, ue_id: int, qfi: int) -> int:
        return self._buffers.delivered_cum(ue_id, qfi)

    def dropped_cum(self, ue_id: int, qfi: int) -> int:
        return self._buffers.dropped_cum(ue_id, qfi)


class ReducedSlotView:
    """``SlotView`` wrapper carving this slot's resolved-retransmissions'
    PRBs AND DCI/CCE cost out of the budget ``scheduler.allocate()`` sees
    for new data (docs/wp5-plan.md Decision 4) -- a retry needs its own
    DCI, so CCE budget is reduced too, not just PRBs. Structurally
    satisfies the ``SlotView`` Protocol (``scheduler/interfaces.py``) by
    having the right attributes, no inheritance, no scheduler-side
    changes needed. One combined PRB reduction regardless of DL/UL,
    matching the existing model's single shared ``prb_count`` (it doesn't
    already split DL/UL budgets within a slot beyond symbol availability,
    so this doesn't invent new precision beyond that)."""

    __slots__ = ("_inner", "_retx_prbs", "_retx_cce")

    def __init__(self, inner, retx_prbs: int, retx_cce: int = 0) -> None:
        self._inner = inner
        self._retx_prbs = retx_prbs
        self._retx_cce = retx_cce

    @property
    def slot_index(self) -> int:
        return self._inner.slot_index

    @property
    def dl_symbols(self) -> int:
        return self._inner.dl_symbols

    @property
    def ul_symbols(self) -> int:
        return self._inner.ul_symbols

    @property
    def pdcch_cce_budget(self) -> int:
        return max(0, self._inner.pdcch_cce_budget - self._retx_cce)

    @property
    def prb_count(self) -> int:
        return max(0, self._inner.prb_count - self._retx_prbs)
