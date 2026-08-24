"""WP5 -- HARQ core state: N processes per UE per direction, and the
per-attempt combining-gain function.

Pure functions/state -- no simulator (driver.py/buffer.py/etc.) imports.
This module DOES import ``scheduler.link.bler_for_mcs`` (commit 2) to
compose it with ``combining_gain_db``; that's the allowed dependency
direction (``sim`` -> ``scheduler``, already used by ``sim/driver.py``),
not the reverse -- ``scheduler/interfaces.py`` states the package must
depend on nothing outside itself, so the composition lives here, not in
``scheduler/link.py`` (docs/wp5-plan.md Decision 1b).

Not wired into driver.py yet; see docs/wp5-plan.md commit 3+ for when this
becomes live (process-pool gating first, still inert; then commits 4a/4b
make it load-bearing). Every citation and decision here is recorded in
full in docs/wp5-plan.md -- this module's docstrings repeat only what a
reader needs to not silently misuse the numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from scheduler.link import bler_for_mcs

Direction = Literal["DL", "UL"]

# Real OAI's own fallback-when-unconfigured process-pool sizes --
# nr_mac_common.c:2724-2744 (get_nrofHARQ_ProcessesForPDSCH/PUSCH),
# asymmetric by direction: DL defaults to 8, UL to 16, both capped at 16
# pre-Rel17 (docs/wp5-plan.md Decision 2). NOT the same claim as an
# invented default -- these are OAI's own fallback return values when RRC
# doesn't configure nrofHARQ_ProcessesForPDSCH/PUSCH explicitly. Whether
# THIS deployment's RRC overrides them is unconfirmed (README.md sec8).
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
    both modes, so this composition is a no-op until a caller passes a
    positive ``retx_count``. Not called anywhere yet -- driver.py wires it
    in at commits 4a/4b, once a retransmission attempt actually exists to
    have a ``retx_count`` greater than zero.

    Flagged (docs/wp5-plan.md Decision 1b, README.md sec8): this composes
    three uncalibrated constructs into one modelled probability --
    ``bler_for_mcs``'s doubles-per-dB slope, the ``combining_gain_db`` IR/
    Chase table, and its own ``base_bler`` default -- each individually
    flagged already, not previously as a composition.
    """
    return bler_for_mcs(mcs_threshold_db, true_snr_db + combining_gain_db(retx_count, mode))


# ---------------------------------------------------------------------------
# HARQ process pool
# ---------------------------------------------------------------------------


@dataclass
class HarqProcess:
    """One HARQ process's state, for one (ue_id, direction). Dormant
    scaffolding -- not wired to driver.py yet, see module docstring.

    ``qfi`` is meaningful only for DL (a DL grant is emitted per flow,
    ``scheduler/interfaces.py::Allocation``); UL grants are per-UE (the UE
    runs its own LCP over the granted TB, TS 38.321 sec5.4.3.1), so a UL
    process's ``qfi`` stays -1, matching ``Allocation.ue_grant``'s own
    "qfi is then meaningless (-1)" convention.
    """

    pid: int
    ue_id: int
    direction: Direction
    busy: bool = False
    qfi: int = -1
    tb_bytes: int = 0
    retx_count: int = 0
    due_slot: int = -1

    def reset(self) -> None:
        self.busy = False
        self.qfi = -1
        self.tb_bytes = 0
        self.retx_count = 0
        self.due_slot = -1


class HarqProcessPool:
    """Per-(ue_id, direction) pool of ``HarqProcess``, sized asymmetrically
    by direction (``DEFAULT_DL_CAPACITY``/``DEFAULT_UL_CAPACITY`` above --
    docs/wp5-plan.md Decision 2).

    A UE with every process for a direction busy cannot receive a new TB
    on that direction this slot, full stop, regardless of backlog -- real
    OAI's ``available_dl_harq``/``available_ul_harq`` exhaustion (tracked
    there as ``harq_exhausted``). ``allocate()`` returns ``None`` in that
    case; the caller (not yet ``driver.py`` -- see module docstring) is
    responsible for counting that as a diagnostic, not an error.
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
        direction) -- the quantity a future ``driver.py`` wiring would use
        to mask ``BufferView.bytes_queued`` (docs/wp5-plan.md Decision 4's
        ``_HARQAwareBufferView`` precedent). Not consumed by anything yet.
        """
        return sum(p.tb_bytes for p in self._pool(ue_id, direction) if p.busy)

    def exhausted(self, ue_id: int, direction: Direction) -> bool:
        """True if every process for this (ue_id, direction) is busy."""
        return all(p.busy for p in self._pool(ue_id, direction))
