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
"""

import math
from collections import deque

import numpy as np

from scheduler.link import bits_per_prb, cce_aggregation_level

from .config import UEConfig
from .pathloss import INF_BS_HEIGHT_M, inf_los_probability, inf_path_loss_db

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
    """
    assert ue.position is not None and ue.inf_scenario is not None
    d_2d_m = _euclidean_distance(
        (ue.position[0], ue.position[1], 0.0), (gnb_position[0], gnb_position[1], 0.0)
    )
    d_3d_m = _euclidean_distance(ue.position, gnb_position)
    h_bs_m = INF_BS_HEIGHT_M[ue.inf_scenario]
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
    ):
        self.rng = rng
        # WP6 (docs/wp6-plan.md Decision 2/3): independent RNG streams for
        # the two new per-link draws this commit adds (LOS/NLOS realization,
        # shadow fading) -- CLAUDE.md's rule that every new independent
        # random draw needs its own seed stream, same precedent as
        # cqi_seed/harq_rng_dl/harq_rng_ul. Unused (never drawn from) for
        # any UE without ``position`` set.
        los_rng = np.random.default_rng(int(los_seed))
        shadow_fading_rng = np.random.default_rng(int(shadow_fading_seed))
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

    def update(self, _slot_index: int) -> None:
        for ue_id, alpha in self.alpha.items():
            mean = self.mean_snr_db[ue_id]
            innovation = self._innovation_scale[ue_id] * self.sigma_db * self.rng.normal()
            self.snr_db[ue_id] = mean + alpha * (self.snr_db[ue_id] - mean) + innovation
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
