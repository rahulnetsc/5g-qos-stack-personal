"""WP6 commit 3 -- sync-loss (radio link failure, RLF) DETECTION only.

Per docs/wp6-plan.md Decision 4 (sign-off given): this module owns
detecting sync loss -- t310 arming (n310-gated), t310 dwell, and n311-gated
cancellation -- because that state machine is a function of instantaneous
channel quality alone and doesn't need a join/attach procedure to define.
Everything about what happens AFTER RLF is declared (cell search,
RRCReestablishmentRequest timing under t311, or a fresh attach under
t300/t301/t319) is WP-Join's, not this module's -- WP-Join consumes this
module's output (see the bottom of this docstring), it does not extend
this state machine.

**Timer constants are real, measured, deployed values, not representative
defaults** -- ``calibration-logs/twotier_startup_gnb.log:17``'s startup
banner: ``t310 2000, n310 10, ..., n311 1`` (ms/counts). Cited directly,
the same way ``sim/pathloss.py`` cites TR 38.901's tables, not chosen the
way ``sr_period_slots``/``k1_slots`` are. The one exception:
``rlf_snr_floor_db`` has no ground truth anywhere in this repo -- no
calibration log gives an SNR/RSRP threshold for out-of-sync detection
(that's normally an internal PHY implementation choice, not an RRC-visible
config value). Default anchored to ``scheduler/link.py``'s own "no viable
MCS" floor (``_MCS_TABLE[0][0] - 3.0`` = -5.0 dB) -- reusing a boundary
this codebase already treats as physically meaningful, flagged exactly
like ``sr_period_slots``, not a second invented number.

**n310 belongs on the detection side, not just t310/n311 -- corrected
here from an earlier draft of Decision 4 that named only the latter two.**
n310 gates when t310 itself starts counting (arms), which is squarely a
channel-quality-driven trigger condition, the same species of thing as
t310's dwell and n311's cancel -- there is no reading of "detection" that
excludes the condition that starts the detector's own timer.

**Approximation, stated once here rather than left to be discovered by
reading the code:** real 3GPP counts n310 CONSECUTIVE out-of-sync
INDICATIONS, where the indication-sampling period is UE-implementation-
defined and not given anywhere in this repo's calibration data. This
module counts n310 consecutive SLOTS below ``rlf_snr_floor_db`` instead --
one slot standing in for one indication. At this deployment's 0.5ms/slot
(mu=1), n310=10 slots is 5ms, almost certainly faster than any real UE's
indication cadence -- a modelling approximation of the counting
STRUCTURE, not a claim that the timing is realistic at that grain. n311
is modelled with the same one-slot-per-indication approximation,
generalized (not hardcoded to "1") so a different deployment's n311 would
be handled correctly if one is ever found.

**What WP-Join consumes (the seam between the two work packages,
decided now rather than left for WP-Join to guess):**

- ``RlfDetectorState.sync_state`` -- the current level (IN_SYNC /
  T310_RUNNING / RLF_DECLARED), for any code that wants to check "is this
  UE currently failed" at an arbitrary point.
- ``RlfStepResult.rlf_declared_this_slot`` -- an edge-triggered event, true
  for exactly the one slot RLF transitions from T310_RUNNING to
  RLF_DECLARED. WP-Join should react to this event to start its own
  reattach procedure exactly once, not poll the level state and re-derive
  the edge itself.
- ``RlfDetectorState.rlf_declared_at_slot`` -- the slot index RLF was
  declared, for any timing/metrics use.

This module never un-declares RLF once reached -- ``step()`` is a no-op
once ``sync_state == RLF_DECLARED``. Re-arming detection after a real
reattach is WP-Join's responsibility (constructing a fresh
``RlfDetectorState``, or a reset method WP-Join adds when it needs one),
not something this module invents without a consumer.

Landed DORMANT (this commit): not yet wired into ``sim/driver.py``,
``sim/config.py``, or any scheduler -- the state-transition analogue of
``sim/power.py`` (WP1) and ``sim/olla.py`` (WP5 commit 6)'s dormant
landing. **WP-Join commit 2 (docs/wp-join-plan.md) wires ``step()`` into
``sim/driver.py``'s slot loop, unconditionally, per UE per slot** -- this
module's own code is unmodified since (still pure functions/dataclasses,
no simulator or scheduler imports); only its caller changed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SyncState(Enum):
    IN_SYNC = "in_sync"
    T310_RUNNING = "t310_running"
    RLF_DECLARED = "rlf_declared"


@dataclass(frozen=True)
class RlfDetectorConfig:
    """calibration-logs/twotier_startup_gnb.log:17: ``t310 2000 ... n310
    10 ... n311 1`` -- real deployed values, not chosen. ``rlf_snr_floor_
    db`` has no such source (see module docstring)."""

    rlf_snr_floor_db: float = -5.0
    t310_ms: float = 2000.0
    n310: int = 10
    n311: int = 1

    def __post_init__(self) -> None:
        if self.t310_ms <= 0:
            raise ValueError(f"t310_ms must be > 0 (got {self.t310_ms})")
        if self.n310 < 1:
            raise ValueError(f"n310 must be >= 1 (got {self.n310})")
        if self.n311 < 1:
            raise ValueError(f"n311 must be >= 1 (got {self.n311})")


@dataclass
class RlfDetectorState:
    """Per-UE detection state. Mutated in place by ``step()``, mirroring
    ``sim/olla.py``'s ``OllaState`` pattern -- a real per-UE RRC state
    machine is genuinely mutated in place, not recomputed from scratch."""

    sync_state: SyncState = SyncState.IN_SYNC
    consecutive_bad_slots: int = 0  # counts toward n310 arming T310
    consecutive_good_slots: int = 0  # counts toward n311 cancelling T310
    t310_elapsed_slots: int = 0  # counts while T310_RUNNING
    rlf_declared_at_slot: int | None = None


@dataclass(frozen=True)
class RlfStepResult:
    state: RlfDetectorState
    rlf_declared_this_slot: bool


def t310_slots(config: RlfDetectorConfig, slot_duration_s: float) -> int:
    """t310's dwell duration, converted from the cited millisecond value
    to this deployment's slot count. Kept as a millisecond value in
    ``RlfDetectorConfig`` (matching the units the calibration log itself
    states it in), converted here rather than baked into the config as a
    numerology-specific slot count -- unlike ``BlockageConfig``'s
    ``mean_blocked_slots`` (docs/wp6-plan.md Decision 3), which has no
    real ms value to be faithful to in the first place."""
    return max(1, round(config.t310_ms / (slot_duration_s * 1000.0)))


def step(
    state: RlfDetectorState,
    config: RlfDetectorConfig,
    snr_db: float,
    slot_index: int,
    slot_duration_s: float,
) -> RlfStepResult:
    """One detection step for one UE. ``snr_db`` should be the TRUE
    instantaneous SNR (``ChannelModel.get_snr_db``, matching HARQ's own
    use of true, not CQI-delayed, SNR for outcome-relevant decisions) --
    sync loss is a physical link property, not something the gNB's
    delayed CQI view should gate.

    No-op (returns the state unchanged, ``rlf_declared_this_slot=False``)
    once ``state.sync_state == SyncState.RLF_DECLARED`` -- see module
    docstring."""
    if state.sync_state == SyncState.RLF_DECLARED:
        return RlfStepResult(state, rlf_declared_this_slot=False)

    is_bad = snr_db < config.rlf_snr_floor_db

    if state.sync_state == SyncState.IN_SYNC:
        if is_bad:
            state.consecutive_bad_slots += 1
            state.consecutive_good_slots = 0
            if state.consecutive_bad_slots >= config.n310:
                state.sync_state = SyncState.T310_RUNNING
                state.t310_elapsed_slots = 0
                state.consecutive_good_slots = 0
        else:
            state.consecutive_bad_slots = 0
        return RlfStepResult(state, rlf_declared_this_slot=False)

    # state.sync_state == SyncState.T310_RUNNING
    if is_bad:
        state.consecutive_good_slots = 0
        state.t310_elapsed_slots += 1
        if state.t310_elapsed_slots >= t310_slots(config, slot_duration_s):
            state.sync_state = SyncState.RLF_DECLARED
            state.rlf_declared_at_slot = slot_index
            return RlfStepResult(state, rlf_declared_this_slot=True)
        return RlfStepResult(state, rlf_declared_this_slot=False)

    state.consecutive_good_slots += 1
    if state.consecutive_good_slots >= config.n311:
        state.sync_state = SyncState.IN_SYNC
        state.consecutive_bad_slots = 0
        state.consecutive_good_slots = 0
        state.t310_elapsed_slots = 0
    return RlfStepResult(state, rlf_declared_this_slot=False)
