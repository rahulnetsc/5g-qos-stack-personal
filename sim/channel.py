"""Simulator channel model: per-UE SNR as a stationary AR(1) process.

Link adaptation (SNR -> bits/PRB, PDCCH aggregation level) belongs to the
``scheduler`` library; ``bits_per_prb`` / ``cce_aggregation_level`` are
re-exported here so simulator code has a single channel import surface.
"""

from collections import deque

import numpy as np

from scheduler.link import bits_per_prb, cce_aggregation_level

from .config import UEConfig

__all__ = ["bits_per_prb", "cce_aggregation_level", "ChannelModel"]


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
    """

    def __init__(
        self,
        ues: list[UEConfig],
        rng: np.random.Generator,
        stationary_std_db: float = 1.5,
        cqi_delay_slots: int = 0,
        cqi_loss_rate: float = 0.0,
        cqi_seed: int = 0,
    ):
        self.rng = rng
        self.snr_db = {ue.ue_id: ue.mean_snr_db for ue in ues}
        self.mean_snr_db = {ue.ue_id: ue.mean_snr_db for ue in ues}
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
                self._snr_reported[ue.ue_id] = ue.mean_snr_db

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
