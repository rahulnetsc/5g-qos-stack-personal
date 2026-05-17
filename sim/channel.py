"""Simulator channel model: per-UE SNR as a stationary AR(1) process.

Link adaptation (SNR -> bits/PRB, PDCCH aggregation level) belongs to the
``scheduler`` library; ``bits_per_prb`` / ``cce_aggregation_level`` are
re-exported here so simulator code has a single channel import surface.
"""

import numpy as np

from scheduler.link import bits_per_prb, cce_aggregation_level

from .config import UEConfig

__all__ = ["bits_per_prb", "cce_aggregation_level", "ChannelModel"]


class ChannelModel:
    """Per-UE SNR (dB) as a stationary AR(1) process around each UE's mean.

    Stationary form: X(t+1) = mean + alpha*(X(t)-mean) + sqrt(1-alpha^2)*sigma*Z.
    Per-step noise is scaled so that the long-run std stays at `stationary_std_db`
    regardless of how close alpha is to 1.
    """

    def __init__(
        self,
        ues: list[UEConfig],
        rng: np.random.Generator,
        stationary_std_db: float = 1.5,
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

    def update(self, _slot_index: int) -> None:
        for ue_id, alpha in self.alpha.items():
            mean = self.mean_snr_db[ue_id]
            innovation = self._innovation_scale[ue_id] * self.sigma_db * self.rng.normal()
            self.snr_db[ue_id] = mean + alpha * (self.snr_db[ue_id] - mean) + innovation

    def get_snr_db(self, ue_id: int) -> float:
        return self.snr_db[ue_id]
