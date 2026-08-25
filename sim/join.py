"""WP-Join commit 1 -- per-UE join/re-join/RLF-recovery state machine and
calibrated delay sampler. Landed DORMANT: not wired into ``sim/driver.py``,
``sim/config.py``, or any scheduler -- the same landing pattern as ``sim/
power.py`` (WP1), ``sim/olla.py`` (WP5 commit 6), and ``sim/rlf.py`` (WP6
commit 3). Pure functions/dataclasses only -- no simulator or scheduler
imports, and in particular **no import of ``sim/rlf.py``**: this module
consumes ``sim/rlf.py``'s contract (``docs/wp6-plan.md`` Decision 4) as a
plain ``bool`` passed into ``step()`` (see below), not as an object it
constructs or holds -- the "consume, don't extend" boundary CLAUDE.md
records is kept at the type-signature level, not just the docstring level.

**WP-Join commit 5** (docs/wp-join-plan.md sec1.4/sec4) wires this module
into ``sim/driver.py`` via ``UEConfig.join`` (opt-in, default ``None``)
and adds ``JoinAwareBufferView`` below -- the radio gate. This module
still imports nothing from ``sim``/``scheduler`` (``JoinAwareBufferView``
duck-types its wrapped view exactly like ``sim/harq.py::
HarqAwareBufferView`` does, needing no import to do it); the FSM/sampler
above this point in the file remains exactly what commit 1 landed,
unmodified.

**WP-Join commit 6** adds the application-layer gate: ``sim/driver.py``
suppresses traffic admission (source gate) while ``JoinState.app_running``
is False, and injects/tracks the real UL/DL handshake ``Message`` pair
(``JoinConfig.handshake_ul_qfi``/``handshake_dl_qfi`` above) once a UE
enters ``JoinPhase.APP_HANDSHAKE``, finally passing ``handshake_complete``
into ``step()`` for real. `sim/join.py` itself is unmodified except for
those four new, all-optional ``JoinConfig`` fields -- the FSM's own
``step()`` logic already handled ``handshake_complete`` correctly since
commit 1; it simply never received ``True`` until now.

**Ground truth, cited exactly** (``docs/wp-join-plan.md`` sec2):
``calibration-logs/twotier_startup_gnb.log:17``'s startup banner --
``t300 400, t301 400, t311 3000, t319 400`` (ms) -- the only line in the
4117-line file mentioning any of these, real deployed values, cited the
same way ``sim/rlf.py`` cites ``t310``/``n310``/``n311`` from the same
line. The one real RACH trace in that file (lines 163-182, a single
uncontended attach, preamble to ``RRC_CONNECTED`` in ~2 frames, ~20ms) is
this module's floor for the merged RACH+RRC-Setup procedure -- one data
point, not a distribution, stated once here rather than left to be
discovered by reading the code.

**``t319`` (RRC Resume, for ``RRC_INACTIVE``) is out of scope** --
transcribed here for completeness, never read by ``step()``:
``T319_MS_NOT_MODELED = 400.0``. None of GT-6.1/6.2/6.3 involves
``RRC_INACTIVE``, and nothing else in this repo models an inactivity timer
that would ever suspend a UE into it (``docs/wp-join-plan.md`` D4).

**The one invented parameter in the whole delay model is ``p_expiry``**
(``JoinConfig.p_expiry``, default 0.01) -- every ``t3xx`` ceiling above is
a real 3GPP *supervision deadline*, not a distribution's mean, so delays
are drawn as ``floor + Exponential(mean_excess)`` where ``mean_excess`` is
solved so a draw exceeds the ceiling with probability ``p_expiry`` --
never truncated: a draw beyond the ceiling is a real timer-expiry event
with its own fallback edge (retry, or fall back to a full attach), exactly
matching what a real UE's supervision timer does (``docs/wp-join-plan.md``
D2/D3). Two procedures have no ground truth for even a floor -- PDU-session
establishment (NAS/5GC, nothing in the calibration banner) and app-restart
delay (the handshake itself carries the measurable part, sec1.7/D8 in the
plan) -- both default to ``0.0`` and are reported alongside any result that
uses them, per the plan's citation discipline, not silently assumed. The
reestablishment floor is *borrowed* from the one RACH trace above, not
measured for reestablishment itself -- no ``RRCReestablishment`` procedure
appears anywhere in the calibration log.

**``JoinConfig.rlf_snr_floor_db``/``reestablish_snr_margin_db`` MUST mirror
the ``RlfDetectorConfig.rlf_snr_floor_db`` used for the SAME UE.** This
module does not import ``sim/rlf.py`` to read it directly (that would
create the exact import coupling the "consume, don't extend" boundary is
meant to avoid) -- keeping the two values in sync across both configs is
the wiring commit's (commit 5) responsibility, not this module's.

**Three independent RNG streams, one per path family** (``docs/wp-join-
plan.md`` D9, CLAUDE.md's seed-isolation rule, matching WP6's ``los_seed``/
``shadow_fading_seed``/``blockage_seed`` precedent): ``cold`` (RACH+RRC
Setup, PDU session), ``reest`` (cell search, reestablishment), ``warm``
(app-restart delay -- reserved; unused while ``app_restart_ceiling_ms ==
app_restart_floor_ms == 0.0`` by default, since a deterministic delay
draws nothing). See ``init_join_rng_streams``.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

T319_MS_NOT_MODELED = 400.0  # calibration-logs/twotier_startup_gnb.log:17 -- RRC Resume, out of scope (D4)

_JOIN_COLD_TAG = 0x434F4C44  # "COLD"
_JOIN_REEST_TAG = 0x52454553  # "REES"
_JOIN_WARM_TAG = 0x4A4F494E  # "JOIN"

_VALID_EVENT_KINDS = ("power_on", "power_off", "app_restart")


class JoinPhase(Enum):
    CONNECTED = "connected"
    APP_RESTART = "app_restart"
    APP_HANDSHAKE = "app_handshake"
    POWERED_OFF = "powered_off"
    IDLE = "idle"
    RRC_ESTABLISH = "rrc_establish"
    PDU_SESSION = "pdu_session"
    CELL_SEARCH = "cell_search"
    REESTABLISH = "reestablish"


# Radio (RRC) is connected in exactly these phases -- docs/wp-join-plan.md
# sec1.6's gate table. In particular RRC_ESTABLISH/PDU_SESSION are NOT
# connected: this simulator doesn't model bearers mid-attach, so the whole
# attach chain is treated as one un-connected span, consistent with there
# being nothing to grant PRBs against until it completes.
_RADIO_CONNECTED_PHASES = frozenset(
    {JoinPhase.CONNECTED, JoinPhase.APP_RESTART, JoinPhase.APP_HANDSHAKE}
)


def rrc_connected(phase: JoinPhase) -> bool:
    """Pure read, no draws, no mutation -- the radio gate (sec1.4/1.8 of
    docs/wp-join-plan.md). Called every slot by the wiring commit (5),
    before ``channel.update()``, independent of ``step()``."""
    return phase in _RADIO_CONNECTED_PHASES


@dataclass(frozen=True)
class JoinEvent:
    """A scripted event on one UE's join schedule. ``power_on``/
    ``power_off`` model GT-6.2's cold-attach cycling (repeated, per
    ``JoinConfig.events`` being a list, not a scalar -- GT-6.2's own "10
    consecutive cycles" pass criterion needs the same UE power-cycled
    repeatedly within one run); ``app_restart`` models GT-6.1's warm
    re-join. RLF (GT-6.3) is never scripted here -- it is emergent, driven
    by ``sim/rlf.py`` observing the real SNR trace (docs/wp-join-plan.md
    sec1.3)."""

    slot: int
    kind: str

    def __post_init__(self) -> None:
        if self.kind not in _VALID_EVENT_KINDS:
            raise ValueError(f"kind must be one of {_VALID_EVENT_KINDS} (got {self.kind!r})")
        if self.slot < 0:
            raise ValueError(f"slot must be >= 0 (got {self.slot})")


@dataclass(frozen=True)
class JoinConfig:
    """Per-UE join/RLF-recovery configuration. ``events``/``initial_state``
    default to today's behaviour exactly (a UE that is always connected,
    never scripted to leave) -- opt-in, matching ``UEConfig.blockage``'s
    own ``None``-default shape (this module doesn't touch ``sim/
    config.py`` at all this commit; the wiring commit adds ``UEConfig.
    join: JoinConfig | None = None``)."""

    initial_state: str = "connected"  # "connected" | "powered_off"
    events: tuple[JoinEvent, ...] = ()

    # RACH + RRC Setup, merged into one sampled state (docs/wp-join-plan.md
    # sec1.7: the one real trace measures the combined procedure
    # end-to-end; splitting it would invent a decomposition the data
    # doesn't support). Ceiling = t300.
    rach_rrc_setup_floor_ms: float = 20.0
    rach_rrc_setup_ceiling_ms: float = 400.0

    # Cell search. No floor beyond the physical SNR-restoration gate
    # below; ceiling = t311.
    cell_search_ceiling_ms: float = 3000.0
    cell_search_good_snr_slots: int = 1  # n311-equivalent consecutive-good-slot gate
    reestablish_snr_margin_db: float = 0.0  # no ground truth for a nonzero margin (D-adjacent to D6)

    # Reestablishment. Floor is a BORROW from the one RACH trace, not a
    # reestablishment-specific measurement -- flagged, not silently reused
    # as if it were. Ceiling = t301.
    reestablish_floor_ms: float = 20.0
    reestablish_ceiling_ms: float = 400.0

    # PDU session establishment (NAS/5GC). No timer anywhere in the
    # calibration banner -- default 0.0, reported alongside any result
    # that uses it, not silently assumed (docs/wp-join-plan.md D4-in-sec1.7).
    pdu_session_floor_ms: float = 0.0
    pdu_session_ceiling_ms: float = 0.0

    # App-restart delay (warm path). No ground truth; the handshake itself
    # (real traffic, commit 6) carries the measurable part of GT-6.1.
    app_restart_floor_ms: float = 0.0
    app_restart_ceiling_ms: float = 0.0

    # The one invented scalar in the whole delay model (D3).
    p_expiry: float = 0.01

    # MUST mirror RlfDetectorConfig.rlf_snr_floor_db for the same UE --
    # see module docstring. Not imported from sim/rlf.py on purpose.
    rlf_snr_floor_db: float = -5.0

    # WP-Join commit 6 (docs/wp-join-plan.md sec1.7/D8): the app handshake
    # is modelled as REAL traffic -- a UL request / DL response Message
    # pair traversing the ordinary buffer -> scheduler -> HARQ path, using
    # WP7's existing message ledger -- not a sampled delay. GT-6.1's own
    # pass line ("handshake round-trip p95 <= 1s UNDER LOAD") is itself a
    # load-dependent measurement; sampling it would make the criterion a
    # tautology. Both qfis MUST already exist in the scenario's own
    # FlowConfig list (pre-registered like every other flow, D1's "fixed
    # roster" -- sim/join.py does not synthesize flows), each direction-
    # correct (UL for handshake_ul_qfi, DL for handshake_dl_qfi) and
    # distinct from every other flow's qfi on this UE. None (default,
    # either) means this UE's handshake never completes -- exactly commit
    # 5's own behaviour, preserved for any scenario that predates this
    # commit's wiring. Payload sizes are deterministic (no ground truth
    # for real byte sizes; drawing them would also risk perturbing the
    # shared traffic rng for no benefit -- sec1.7).
    handshake_ul_qfi: int | None = None
    handshake_dl_qfi: int | None = None
    handshake_request_bytes: int = 64
    handshake_response_bytes: int = 64

    def __post_init__(self) -> None:
        if self.initial_state not in ("connected", "powered_off"):
            raise ValueError(f"initial_state must be 'connected' or 'powered_off' (got {self.initial_state!r})")
        if not 0.0 < self.p_expiry < 1.0:
            raise ValueError(f"p_expiry must be in (0, 1) (got {self.p_expiry})")
        if self.cell_search_good_snr_slots < 1:
            raise ValueError(f"cell_search_good_snr_slots must be >= 1 (got {self.cell_search_good_snr_slots})")
        prev_slot = -1
        for event in self.events:
            if event.slot <= prev_slot:
                raise ValueError("events must be strictly ascending by slot")
            prev_slot = event.slot
        for name in (
            "rach_rrc_setup_floor_ms", "rach_rrc_setup_ceiling_ms",
            "cell_search_ceiling_ms", "reestablish_floor_ms", "reestablish_ceiling_ms",
            "pdu_session_floor_ms", "pdu_session_ceiling_ms",
            "app_restart_floor_ms", "app_restart_ceiling_ms",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0 (got {getattr(self, name)})")
        if (self.handshake_ul_qfi is None) != (self.handshake_dl_qfi is None):
            raise ValueError("handshake_ul_qfi and handshake_dl_qfi must be set together, or neither")
        if self.handshake_ul_qfi is not None and self.handshake_ul_qfi == self.handshake_dl_qfi:
            raise ValueError("handshake_ul_qfi and handshake_dl_qfi must be distinct (one flow per direction)")
        if self.handshake_request_bytes <= 0 or self.handshake_response_bytes <= 0:
            raise ValueError("handshake_request_bytes/handshake_response_bytes must be > 0")


@dataclass
class JoinRngStreams:
    """Three independent generators, one per path family (module
    docstring, D9). Constructed via ``init_join_rng_streams`` so every UE
    gets streams derived from the same scenario seed the rest of the
    simulator uses, XOR-tagged like every other mechanism's seed."""

    cold: np.random.Generator
    reest: np.random.Generator
    warm: np.random.Generator


def init_join_rng_streams(seed: int) -> JoinRngStreams:
    return JoinRngStreams(
        cold=np.random.default_rng(seed ^ _JOIN_COLD_TAG),
        reest=np.random.default_rng(seed ^ _JOIN_REEST_TAG),
        warm=np.random.default_rng(seed ^ _JOIN_WARM_TAG),
    )


@dataclass
class JoinState:
    """Per-UE state. Mutated in place by ``step()``, mirroring ``sim/
    rlf.py``'s ``RlfDetectorState`` / ``sim/olla.py``'s ``OllaState``
    pattern. Constructed via ``init_join_state``, not directly, so a UE
    scripted to start powered off begins in the right phase."""

    phase: JoinPhase = JoinPhase.CONNECTED
    app_running: bool = True
    phase_elapsed_slots: int = 0
    deadline_slots: float = 0.0  # raw sampled completion time; NOT pre-clamped to the ceiling (see step())
    phase_ceiling_slots: int = 0
    good_snr_slots: int = 0  # CELL_SEARCH's SNR-restoration gate only
    next_event_index: int = 0
    active_path: str | None = None  # "warm" | "cold" | "reestablish" -- None while CONNECTED and idle
    trigger_slot: int | None = None
    cycle_index: int = 0
    timer_expiry_counts: dict[str, int] = field(default_factory=dict)


def init_join_state(config: JoinConfig) -> JoinState:
    if config.initial_state == "powered_off":
        return JoinState(phase=JoinPhase.POWERED_OFF, app_running=False)
    return JoinState()


@dataclass(frozen=True)
class JoinStepResult:
    state: JoinState
    phase_changed: bool
    radio_connected_this_slot: bool  # edge; also the signal to construct a fresh RlfDetectorState (sec1.6)
    app_connected_this_slot: bool  # edge
    timer_expired_this_slot: bool
    snr_restored_this_slot: bool  # edge, meaningful only while state.phase is CELL_SEARCH


def _ms_to_slots(ms: float, slot_duration_s: float) -> int:
    return max(0, round(ms / (slot_duration_s * 1000.0)))


def _sample_deadline_slots(
    rng: np.random.Generator, floor_slots: int, ceiling_slots: int, p_expiry: float
) -> float:
    """Returns the RAW sampled completion time in slots -- NOT clamped to
    ``ceiling_slots``. The caller compares this against the ceiling live,
    every step, rather than pre-computing a "will this expire" flag at
    draw time: a phase whose completion also depends on an external,
    time-varying condition (CELL_SEARCH's SNR-restoration gate) can still
    expire even when the draw itself was short, and pre-clamping would
    hide that. ``ceiling_slots <= floor_slots`` is treated as
    deterministic -- returns ``floor_slots`` exactly, consuming no RNG
    draw at all (this is what keeps PDU-session/app-restart's default
    0.0/0.0 configuration from touching ``rng`` -- see module docstring)."""
    if ceiling_slots <= floor_slots:
        return float(floor_slots)
    mean_excess = (ceiling_slots - floor_slots) / (-math.log(p_expiry))
    return floor_slots + rng.exponential(mean_excess)


def step(
    state: JoinState,
    config: JoinConfig,
    rngs: JoinRngStreams,
    slot_index: int,
    slot_duration_s: float,
    rlf_declared_this_slot: bool = False,
    snr_db: float = 0.0,
    handshake_complete: bool = False,
) -> JoinStepResult:
    """One step for one UE. ``rlf_declared_this_slot`` is ``sim/rlf.py``'s
    ``RlfStepResult.rlf_declared_this_slot`` for this UE, passed as a
    plain ``bool`` -- this module never imports or holds an
    ``RlfDetectorState`` itself. ``snr_db`` should be the TRUE
    instantaneous SNR, matching ``sim/rlf.py``'s own convention, and is
    only consulted while ``state.phase is CELL_SEARCH``. ``handshake_
    complete`` reports whether the (real-traffic, commit 6) app-handshake
    message pair has completed this slot -- this module has no notion of
    ``Message``/``MessageLedger`` and never will; it just waits in
    ``APP_HANDSHAKE`` until told.

    Every phase dwells at least one slot: the transition INTO a phase
    resets ``phase_elapsed_slots`` to 0 in the SAME call, and the
    elapsed-vs-deadline/ceiling check that could transition OUT of it only
    runs on a LATER call, after incrementing. This keeps one ``step()``
    call from cascading through multiple phase transitions in a single
    slot."""
    prior_phase = state.phase
    prior_app_running = state.app_running
    prior_rrc_connected = rrc_connected(prior_phase)
    timer_expired_this_slot = False
    snr_restored_this_slot = False

    event_kind = None
    if state.next_event_index < len(config.events):
        candidate = config.events[state.next_event_index]
        if candidate.slot == slot_index:
            event_kind = candidate.kind
            state.next_event_index += 1

    if state.phase is JoinPhase.CONNECTED:
        if event_kind == "power_off":
            state.phase = JoinPhase.POWERED_OFF
            state.app_running = False
        elif event_kind == "app_restart":
            state.phase = JoinPhase.APP_RESTART
            state.app_running = False
            state.active_path = "warm"
            state.trigger_slot = slot_index
            state.phase_elapsed_slots = 0
            state.deadline_slots = _sample_deadline_slots(
                rngs.warm,
                _ms_to_slots(config.app_restart_floor_ms, slot_duration_s),
                _ms_to_slots(config.app_restart_ceiling_ms, slot_duration_s),
                config.p_expiry,
            )
        elif rlf_declared_this_slot:
            state.phase = JoinPhase.CELL_SEARCH
            state.active_path = "reestablish"
            state.trigger_slot = slot_index
            state.phase_elapsed_slots = 0
            state.good_snr_slots = 0
            state.phase_ceiling_slots = _ms_to_slots(config.cell_search_ceiling_ms, slot_duration_s)
            state.deadline_slots = _sample_deadline_slots(
                rngs.reest, 0, state.phase_ceiling_slots, config.p_expiry
            )

    elif state.phase is JoinPhase.POWERED_OFF:
        if event_kind == "power_on":
            state.phase = JoinPhase.RRC_ESTABLISH
            state.active_path = "cold"
            state.trigger_slot = slot_index
            state.phase_elapsed_slots = 0
            state.phase_ceiling_slots = _ms_to_slots(config.rach_rrc_setup_ceiling_ms, slot_duration_s)
            state.deadline_slots = _sample_deadline_slots(
                rngs.cold,
                _ms_to_slots(config.rach_rrc_setup_floor_ms, slot_duration_s),
                state.phase_ceiling_slots,
                config.p_expiry,
            )

    elif state.phase is JoinPhase.APP_RESTART:
        state.phase_elapsed_slots += 1
        if state.phase_elapsed_slots >= state.deadline_slots:
            # No failure edge modeled here -- unlike the RRC timers, there
            # is no real "app restart timed out" concept in the ground
            # truth; the handshake (commit 6) carries the measurable part.
            state.phase = JoinPhase.APP_HANDSHAKE
            state.phase_elapsed_slots = 0

    elif state.phase is JoinPhase.RRC_ESTABLISH:
        state.phase_elapsed_slots += 1
        if state.phase_elapsed_slots >= state.deadline_slots:
            state.phase = JoinPhase.PDU_SESSION
            state.phase_elapsed_slots = 0
            state.phase_ceiling_slots = _ms_to_slots(config.pdu_session_ceiling_ms, slot_duration_s)
            state.deadline_slots = _sample_deadline_slots(
                rngs.cold,
                _ms_to_slots(config.pdu_session_floor_ms, slot_duration_s),
                state.phase_ceiling_slots,
                config.p_expiry,
            )
        elif state.phase_elapsed_slots >= state.phase_ceiling_slots:
            timer_expired_this_slot = True
            state.timer_expiry_counts["rrc_establish"] = state.timer_expiry_counts.get("rrc_establish", 0) + 1
            state.phase_elapsed_slots = 0  # t300 expiry: retry, stay in RRC_ESTABLISH
            state.deadline_slots = _sample_deadline_slots(
                rngs.cold,
                _ms_to_slots(config.rach_rrc_setup_floor_ms, slot_duration_s),
                state.phase_ceiling_slots,
                config.p_expiry,
            )

    elif state.phase is JoinPhase.PDU_SESSION:
        state.phase_elapsed_slots += 1
        if state.phase_elapsed_slots >= state.deadline_slots:
            state.phase = JoinPhase.APP_HANDSHAKE
            state.phase_elapsed_slots = 0
        elif state.phase_elapsed_slots >= state.phase_ceiling_slots:
            # Unreachable at defaults (floor == ceiling == 0.0, so deadline
            # == 0 == ceiling and the `if` above always fires first).
            # Guarded for whoever configures a nonzero ceiling here later
            # -- no real timer governs this in the ground truth either way.
            timer_expired_this_slot = True
            state.timer_expiry_counts["pdu_session"] = state.timer_expiry_counts.get("pdu_session", 0) + 1
            state.phase = JoinPhase.APP_HANDSHAKE
            state.phase_elapsed_slots = 0

    elif state.phase is JoinPhase.CELL_SEARCH:
        if snr_db >= config.rlf_snr_floor_db + config.reestablish_snr_margin_db:
            state.good_snr_slots += 1
        else:
            state.good_snr_slots = 0
        state.phase_elapsed_slots += 1
        snr_restored = state.good_snr_slots >= config.cell_search_good_snr_slots
        snr_restored_this_slot = state.good_snr_slots == config.cell_search_good_snr_slots
        if snr_restored and state.phase_elapsed_slots >= state.deadline_slots:
            state.phase = JoinPhase.REESTABLISH
            state.phase_elapsed_slots = 0
            state.phase_ceiling_slots = _ms_to_slots(config.reestablish_ceiling_ms, slot_duration_s)
            state.deadline_slots = _sample_deadline_slots(
                rngs.reest,
                _ms_to_slots(config.reestablish_floor_ms, slot_duration_s),
                state.phase_ceiling_slots,
                config.p_expiry,
            )
        elif state.phase_elapsed_slots >= state.phase_ceiling_slots:
            # t311 expiry: the search window itself is exhausted, whether
            # or not SNR ever recovered -- fall back to a full attach.
            timer_expired_this_slot = True
            state.timer_expiry_counts["cell_search"] = state.timer_expiry_counts.get("cell_search", 0) + 1
            state.phase = JoinPhase.IDLE
            state.phase_elapsed_slots = 0

    elif state.phase is JoinPhase.REESTABLISH:
        state.phase_elapsed_slots += 1
        if state.phase_elapsed_slots >= state.deadline_slots:
            state.phase = JoinPhase.APP_HANDSHAKE
            state.phase_elapsed_slots = 0
        elif state.phase_elapsed_slots >= state.phase_ceiling_slots:
            timer_expired_this_slot = True
            state.timer_expiry_counts["reestablish"] = state.timer_expiry_counts.get("reestablish", 0) + 1
            state.phase = JoinPhase.IDLE  # t301 expiry: fall back to a full attach
            state.phase_elapsed_slots = 0

    elif state.phase is JoinPhase.IDLE:
        # Single-slot transit (docs/wp-join-plan.md sec1.6): the UE is
        # motivated to reconnect (app_running is left exactly as it was --
        # true for a post-RLF fallback, false only if IDLE were ever
        # reached from a cold path, which the FSM above never does) and
        # immediately begins a fresh attach attempt.
        state.phase = JoinPhase.RRC_ESTABLISH
        state.phase_elapsed_slots = 0
        state.phase_ceiling_slots = _ms_to_slots(config.rach_rrc_setup_ceiling_ms, slot_duration_s)
        state.deadline_slots = _sample_deadline_slots(
            rngs.cold,
            _ms_to_slots(config.rach_rrc_setup_floor_ms, slot_duration_s),
            state.phase_ceiling_slots,
            config.p_expiry,
        )

    elif state.phase is JoinPhase.APP_HANDSHAKE:
        state.phase_elapsed_slots += 1
        if handshake_complete:
            state.phase = JoinPhase.CONNECTED
            state.app_running = True  # idempotent for the reestablish path, where it was already True
            state.cycle_index += 1
            state.active_path = None
            state.trigger_slot = None
            state.phase_elapsed_slots = 0

    radio_connected_this_slot = rrc_connected(state.phase) and not prior_rrc_connected
    app_connected_this_slot = state.app_running and not prior_app_running
    phase_changed = state.phase is not prior_phase

    return JoinStepResult(
        state=state,
        phase_changed=phase_changed,
        radio_connected_this_slot=radio_connected_this_slot,
        app_connected_this_slot=app_connected_this_slot,
        timer_expired_this_slot=timer_expired_this_slot,
        snr_restored_this_slot=snr_restored_this_slot,
    )


class JoinAwareBufferView:
    """WP-Join commit 5: wraps another BufferView (composed OUTERMOST over
    ``sim/harq.py::HarqAwareBufferView`` -- docs/wp-join-plan.md sec1.4)
    so ``scheduler.allocate()`` sees ZERO backlog (``bytes_queued`` AND
    ``bytes_reported``) for any UE currently radio-gated -- i.e. any UE
    with a tracked ``JoinState`` whose ``phase`` is not one of ``rrc_
    connected``'s set. Masked per WHOLE UE, both directions, unlike
    ``HarqAwareBufferView``'s per-flow(DL)/per-UE(UL) split -- RRC
    connectivity is a property of the UE, not of any one flow. Both
    fields matter: ``TwoTier``'s SPS path reads ``bytes_queued`` directly,
    bypassing BSR entirely, so masking only ``bytes_reported`` would leave
    that path open (docs/wp-join-plan.md sec1.4).

    ``hol_delay_s`` and the cumulative arrived/delivered/dropped counters
    are passed through UNMASKED, exactly matching ``HarqAwareBufferView``'s
    own choice -- they are either genuinely-known gNB state (HoL age of
    its own queue) or lifetime accounting later windowing depends on;
    masking them would corrupt post-recovery demand estimates, not just
    this slot's grant.

    A UE with no entry in ``join_states`` (no ``UEConfig.join`` set) is
    never gated -- exactly today's behaviour, unconditionally; this is
    also why ``join_states`` should hold only UEs that opted in, not
    every UE in the scenario with a placeholder ``None``."""

    def __init__(self, inner, join_states: dict[int, JoinState]) -> None:
        self._inner = inner
        self._join_states = join_states

    def state(self, ue_id: int, qfi: int):
        real = self._inner.state(ue_id, qfi)
        join_state = self._join_states.get(ue_id)
        if join_state is not None and not rrc_connected(join_state.phase):
            masked = copy.copy(real)
            masked.bytes_queued = 0
            masked.bytes_reported = 0
            return masked
        return real

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        return self._inner.hol_delay_s(ue_id, qfi, now_s)

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        return self._inner.arrived_cum(ue_id, qfi)

    def delivered_cum(self, ue_id: int, qfi: int) -> int:
        return self._inner.delivered_cum(ue_id, qfi)

    def dropped_cum(self, ue_id: int, qfi: int) -> int:
        return self._inner.dropped_cum(ue_id, qfi)
