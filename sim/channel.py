"""Simulator channel model: per-UE SNR as a stationary AR(1) process.

Link adaptation (SNR -> bits/PRB, PDCCH aggregation level) belongs to the
``scheduler`` library; ``bits_per_prb`` / ``cce_aggregation_level`` are
re-exported here so simulator code has a single channel import surface.

WP6 (docs/wp6-plan.md Decision 2): a UE with ``UEConfig.position`` set gets
its ``mean_snr_db`` -- the large-scale term the AR(1) process below mean-
reverts to -- derived from TR 38.901 InF path loss (``sim/pathloss.py``)
and a link budget, instead of the scenario author's hand-picked constant.
This is computed once, at construction, per link (static geometry) -- a UE
without ``position`` set (every existing scenario) is completely
unaffected; ``mean_snr_db`` stays exactly the authored value.

WP-Join commit 3 (docs/wp-join-plan.md sec1.5): a UE with ``UEConfig.
scripted_fade`` set gets ``snr_db`` forced deterministically -- no AR(1)
noise -- for every slot inside a configured window, and reset cleanly to
the clean mean the instant a window ends. Needed because blockage's own
stochastic Markov process, and the AR(1) process's own mean-reversion
lag, both make "exactly when does SNR cross a threshold" unanswerable in
closed form -- WP-Join's join/RLF acceptance tests need an exact,
repeatable answer. A UE without ``scripted_fade`` set (every existing
scenario) is completely unaffected.
"""

import math
from collections import deque

import numpy as np

from scheduler.link import bits_per_prb, cce_aggregation_level

from .blockage import step as blockage_step
from .blockage import transition_probability
from .config import ScriptedFadeWindow, UEConfig
from .pathloss import inf_los_probability, inf_path_loss_db

__all__ = ["bits_per_prb", "cce_aggregation_level", "ChannelModel"]

# Link-budget constants for position-derived mean_snr_db (docs/wp6-plan.md
# Decision 6). UE Tx power is a real spec value (3GPP UE power class 3,
# TS 38.101-1); noise figure is TR 38.901 Table 7.8-7's own InF-calibration
# example value (9dB, UT-side; reused symmetrically for both link
# directions -- the spec gives no separate gNB-side figure). Both are
# representative-not-confirmed for this specific deployment, same
# epistemic tier as sr_period_slots -- flagged here, not silently assumed.
_UE_TX_POWER_DBM = 23.0
_NOISE_FIGURE_DB = 9.0
_THERMAL_NOISE_DBM_PER_HZ = -174.0


def _thermal_noise_dbm(bandwidth_hz: float) -> float:
    return _THERMAL_NOISE_DBM_PER_HZ + 10.0 * math.log10(bandwidth_hz)


def _euclidean_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def derive_mean_snr_db(
    ue: UEConfig,
    gnb_position: tuple[float, float, float],
    center_freq_ghz: float,
    los_rng: np.random.Generator,
    shadow_fading_rng: np.random.Generator,
    bandwidth_hz: float,
) -> float:
    """Position + TR 38.901 InF path loss -> mean SNR (dB), for a UE that
    opts in via ``UEConfig.position``/``inf_scenario``.

    LOS/NLOS is a per-link realization (drawn once, not per-slot -- a
    static property of this UE-gNB geometry, distinct from WP6's dynamic
    two-state blockage, docs/wp6-plan.md Decision 3), from its own RNG
    stream (``los_rng``), per CLAUDE.md's rule that every new independent
    random draw needs its own seed stream. Shadow fading (also per-link,
    log-normal, sigma from Table 7.4.1-1) draws from a second independent
    stream (``shadow_fading_rng``) -- two new mechanisms, two new streams.

    ``h_bs_m`` (fed into ``inf_los_probability``'s SH/DH height-scaling
    term) is ``gnb_position[2]`` -- the actual configured height -- not
    ``INF_BS_HEIGHT_M``'s per-sub-scenario calibration constant (end-of-WP
    review finding, docs/wp6-plan.md sec 8): using the table value here
    would silently decouple the height used for LOS probability from the
    height ``d_3d_m`` below actually uses, for any scenario that sets a
    ``gnb_position`` height other than the sub-scenario's own calibration
    default. ``INF_BS_HEIGHT_M`` stays exported as a reference a scenario
    author can use to pick a ``gnb_position`` height consistent with their
    chosen ``inf_scenario`` -- it is advisory only, not consumed here.
    """
    if ue.position is None or ue.inf_scenario is None:
        # Raise, don't assert (end-of-WP review, docs/wp6-plan.md sec 8):
        # `inf_scenario is None` is a real, user-reachable authoring
        # mistake (set position, forgot inf_scenario), not just an
        # internal invariant -- an `assert` is stripped under `python -O`
        # and gives a less actionable message than the other new WP6
        # modules' own ValueError-on-bad-input convention (sim/pathloss.py,
        # sim/blockage.py, sim/rlf.py).
        raise ValueError(
            f"UEConfig(ue_id={ue.ue_id}): position and inf_scenario must "
            f"both be set to opt into TR 38.901 path loss (got "
            f"position={ue.position!r}, inf_scenario={ue.inf_scenario!r})"
        )
    d_2d_m = _euclidean_distance(
        (ue.position[0], ue.position[1], 0.0), (gnb_position[0], gnb_position[1], 0.0)
    )
    d_3d_m = _euclidean_distance(ue.position, gnb_position)
    h_bs_m = gnb_position[2]
    h_ut_m = ue.position[2]
    p_los = inf_los_probability(ue.inf_scenario, d_2d_m, h_bs_m, h_ut_m)
    is_los = bool(los_rng.random() < p_los)
    path_loss_db, shadow_fading_sigma_db = inf_path_loss_db(
        ue.inf_scenario, d_3d_m, center_freq_ghz, is_los
    )
    shadow_fading_db = float(shadow_fading_rng.normal(0.0, shadow_fading_sigma_db))
    return (
        _UE_TX_POWER_DBM
        - path_loss_db
        - shadow_fading_db
        - _NOISE_FIGURE_DB
        - _thermal_noise_dbm(bandwidth_hz)
    )


class ChannelModel:
    """Per-UE SNR (dB) as a stationary AR(1) process around each UE's mean.

    Stationary form: X(t+1) = mean + alpha*(X(t)-mean) + sqrt(1-alpha^2)*sigma*Z.
    Per-step noise is scaled so that the long-run std stays at `stationary_std_db`
    regardless of how close alpha is to 1.

    ``cqi_delay_slots`` models the CQI reporting round-trip: the scheduler-
    visible SNR (``get_reported_snr_db``) lags the true SNR
    (``get_snr_db``) by this many slots. Zero (the default) preserves the
    old zero-latency behaviour. A typical realistic value at numerology
    mu=1 (0.5 ms slot) is 8-16 slots, matching 5G CQI periods of 5-10 ms.

    ``cqi_loss_rate`` (0.0-1.0) is the per-slot per-UE probability that a
    CQI report fails to reach the gNB; on a loss the gNB keeps its last
    successfully reported value. Uses an independent RNG (``cqi_seed``)
    so loss draws don't perturb the channel AR(1) sequence.

    WP6: a UE with ``position`` set (docs/wp6-plan.md Decision 2) has its
    ``mean_snr_db`` derived from TR 38.901 InF path loss instead of using
    ``UEConfig.mean_snr_db`` directly -- see ``derive_mean_snr_db`` above.
    Every other UE (``position is None``, every existing scenario) is
    unaffected; this is opt-in, not a replacement of the existing pipeline.

    WP6 commit 2: a UE with ``blockage`` set (docs/wp6-plan.md Decision 3)
    additionally runs a two-state Markov process (``sim/blockage.py``)
    that subtracts ``blocked_extra_loss_db`` from its large-scale mean
    while Blocked -- independent of ``position``/path loss, composing on
    top of whichever mean is already in effect. Every UE without
    ``blockage`` set (every existing scenario) is unaffected.

    WP-Join commit 3: a UE with ``scripted_fade`` set has ``snr_db``
    forced to an exact, deterministic value for every slot inside a
    configured window -- bypassing the AR(1) recursion entirely while
    active (not merely shifting its mean, the way blockage does): at this
    module's typical ``coherence_slots``, a shifted mean alone would take
    many hundreds to thousands of slots to actually converge, which would
    make a "scripted" fade's real depth-vs-time behaviour unknowable in
    closed form -- exactly the property this mechanism exists to fix.
    Every UE without ``scripted_fade`` set (every existing scenario) is
    unaffected; the underlying AR(1) innovation draw still happens for
    every UE every slot regardless (its result is only discarded, not
    skipped, while a window is active) so a scenario mixing scripted and
    unscripted UEs never has one UE's fade state change the other's draw
    order (CLAUDE.md's RNG-independence rule, applied here without a new
    stream: this mechanism draws nothing of its own at all).
    """

    def __init__(
        self,
        ues: list[UEConfig],
        rng: np.random.Generator,
        stationary_std_db: float = 1.5,
        cqi_delay_slots: int = 0,
        cqi_loss_rate: float = 0.0,
        cqi_seed: int = 0,
        gnb_position: tuple[float, float, float] = (0.0, 0.0, 8.0),
        center_freq_ghz: float = 3.31968,
        bandwidth_hz: float = 30_000_000,
        los_seed: int = 0,
        shadow_fading_seed: int = 0,
        blockage_seed: int = 0,
    ):
        self.rng = rng
        # WP6 (docs/wp6-plan.md Decision 2/3): independent RNG streams for
        # the three new per-UE draws WP6 adds (LOS/NLOS realization,
        # shadow fading, blockage transitions) -- CLAUDE.md's rule that
        # every new independent random draw needs its own seed stream,
        # same precedent as cqi_seed/harq_rng_dl/harq_rng_ul. Each is
        # unused (never drawn from) for a UE that doesn't opt into the
        # corresponding mechanism.
        los_rng = np.random.default_rng(int(los_seed))
        shadow_fading_rng = np.random.default_rng(int(shadow_fading_seed))
        self._blockage_rng = np.random.default_rng(int(blockage_seed))
        self.mean_snr_db: dict[int, float] = {}
        for ue in ues:
            if ue.position is not None:
                self.mean_snr_db[ue.ue_id] = derive_mean_snr_db(
                    ue,
                    gnb_position,
                    center_freq_ghz,
                    los_rng,
                    shadow_fading_rng,
                    bandwidth_hz,
                )
            else:
                self.mean_snr_db[ue.ue_id] = ue.mean_snr_db
        self.snr_db = dict(self.mean_snr_db)
        # Blockage state -- only tracked for UEs that opt in. Starts
        # Unblocked (a deterministic, non-stationary initial condition,
        # matching self.snr_db's own start-at-mean convention above).
        self._blockage_extra_loss_db: dict[int, float] = {}
        self._p_leave_blocked: dict[int, float] = {}
        self._p_leave_unblocked: dict[int, float] = {}
        self._blocked: dict[int, bool] = {}
        for ue in ues:
            if ue.blockage is None:
                continue
            self._blockage_extra_loss_db[ue.ue_id] = ue.blockage.blocked_extra_loss_db
            self._p_leave_blocked[ue.ue_id] = transition_probability(
                ue.blockage.mean_blocked_slots
            )
            self._p_leave_unblocked[ue.ue_id] = transition_probability(
                ue.blockage.mean_unblocked_slots
            )
            self._blocked[ue.ue_id] = False
        # WP-Join commit 3: only tracked for UEs that opt in. No RNG here
        # at all -- the fade is a scenario-authored, deterministic
        # override, not a draw (docs/wp-join-plan.md sec1.5).
        self._scripted_fade: dict[int, tuple[ScriptedFadeWindow, ...]] = {
            ue.ue_id: ue.scripted_fade for ue in ues if ue.scripted_fade
        }
        # alpha so lag-K autocorrelation is ~1/e at K = coherence_slots
        self.alpha = {
            ue.ue_id: float(np.exp(-1.0 / max(ue.coherence_slots, 1))) for ue in ues
        }
        self.sigma_db = stationary_std_db
        # Scale per-step innovation so stationary variance stays at sigma^2.
        self._innovation_scale = {
            ue.ue_id: float(np.sqrt(max(0.0, 1.0 - self.alpha[ue.ue_id] ** 2)))
            for ue in ues
        }
        # CQI reporting pipeline.
        self._cqi_delay = max(0, int(cqi_delay_slots))
        self._cqi_loss_rate = float(min(1.0, max(0.0, cqi_loss_rate)))
        self._cqi_rng = np.random.default_rng(int(cqi_seed))
        # Per-UE rolling snapshot of true SNR (dB) over the last delay+1
        # slots and the last successfully reported value. The reported
        # value starts equal to the mean SNR: real UEs report a CQI at
        # RRC attach before user traffic starts, so the gNB is not
        # cold-started with no CQI at all -- it has a rough initial view.
        self._snr_hist: dict[int, deque] = {}
        self._snr_reported: dict[int, float] = {}
        if self._cqi_delay > 0:
            for ue in ues:
                self._snr_hist[ue.ue_id] = deque(maxlen=self._cqi_delay + 1)
                self._snr_reported[ue.ue_id] = self.mean_snr_db[ue.ue_id]

    def update(self, slot_index: int) -> None:
        # Advance blockage state before computing this slot's effective
        # mean, so a transition drawn this slot affects this slot's SNR --
        # matching the CQI pipeline's own "advance, then read" ordering
        # below. Independent RNG stream (self._blockage_rng), never drawn
        # from for a UE without ``blockage`` set.
        for ue_id in self._blocked:
            draw = float(self._blockage_rng.random())
            self._blocked[ue_id] = blockage_step(
                self._blocked[ue_id],
                self._p_leave_blocked[ue_id],
                self._p_leave_unblocked[ue_id],
                draw,
            )
        for ue_id, alpha in self.alpha.items():
            mean = self.mean_snr_db[ue_id]
            if self._blocked.get(ue_id, False):
                mean -= self._blockage_extra_loss_db[ue_id]
            # The innovation draw always happens, for every UE, regardless
            # of scripted-fade state below -- only its RESULT is discarded
            # while a window is active, never the draw itself (see this
            # class's own docstring on why, and CLAUDE.md's RNG-
            # independence rule).
            innovation = self._innovation_scale[ue_id] * self.sigma_db * self.rng.normal()
            self.snr_db[ue_id] = mean + alpha * (self.snr_db[ue_id] - mean) + innovation
        # WP-Join commit 3: scripted fade overrides the AR(1) result above
        # for any UE with an active window this slot -- deterministic, no
        # noise -- and resets cleanly to the clean mean the instant a
        # window ends (docs/wp-join-plan.md sec1.5: without this reset,
        # the AR(1) recursion's own mean-reversion lag would leave snr_db
        # stuck near the fade value for many hundreds of slots after
        # recovery, defeating the whole point of a "scripted", exact-
        # timing fade). A no-op loop (0 iterations) for every UE without
        # ``scripted_fade`` set.
        for ue_id, windows in self._scripted_fade.items():
            active_loss_db = 0.0
            in_window = False
            just_ended = False
            for window in windows:
                if window.start_slot <= slot_index < window.end_slot:
                    in_window = True
                    active_loss_db += window.extra_loss_db
                elif slot_index == window.end_slot:
                    just_ended = True
            if not (in_window or just_ended):
                continue
            mean = self.mean_snr_db[ue_id]
            if self._blocked.get(ue_id, False):
                mean -= self._blockage_extra_loss_db[ue_id]
            self.snr_db[ue_id] = mean - active_loss_db if in_window else mean
        # Advance the CQI reporting pipeline. Independent of the AR(1)
        # innovation RNG so loss/delay draws don't perturb channel state.
        if self._cqi_delay > 0:
            for ue_id, current in self.snr_db.items():
                hist = self._snr_hist[ue_id]
                hist.append(current)
                if len(hist) <= self._cqi_delay:
                    continue
                if (
                    self._cqi_loss_rate > 0.0
                    and self._cqi_rng.random() < self._cqi_loss_rate
                ):
                    # CQI report lost this slot: gNB keeps last value.
                    continue
                self._snr_reported[ue_id] = hist[0]

    def get_snr_db(self, ue_id: int) -> float:
        """True instantaneous SNR (used at transmission time for BLER)."""
        return self.snr_db[ue_id]

    def get_reported_snr_db(self, ue_id: int) -> float:
        """CQI-visible SNR (used by the scheduler for MCS pick / ranking).
        Equals ``get_snr_db`` when ``cqi_delay_slots = 0``."""
        if self._cqi_delay <= 0:
            return self.snr_db[ue_id]
        return self._snr_reported.get(ue_id, self.mean_snr_db[ue_id])

    def is_blocked(self, ue_id: int) -> bool:
        """Current two-state Markov blockage state (docs/wp6-plan.md
        Decision 3). Always False for a UE without ``blockage`` set."""
        return self._blocked.get(ue_id, False)
