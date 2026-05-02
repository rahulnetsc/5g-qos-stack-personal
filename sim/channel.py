import numpy as np

from .config import UEConfig


# (snr_db_threshold, spectral_efficiency_bits_per_symbol_per_subcarrier, target_BLER)
# Crude staircase derived from a 0.75-of-Shannon curve. Captures the macro behavior
# (higher SNR -> more bits/RB) without being defensible at the PHY level.
_MCS_TABLE = [
    (-2.0, 0.15, 0.10),
    (1.0, 0.30, 0.10),
    (4.0, 0.60, 0.10),
    (7.0, 1.00, 0.10),
    (10.0, 1.50, 0.10),
    (13.0, 2.00, 0.10),
    (16.0, 2.75, 0.10),
    (19.0, 3.50, 0.10),
    (22.0, 4.50, 0.10),
    (25.0, 5.50, 0.10),
    (28.0, 6.50, 0.10),
    (31.0, 7.50, 0.10),
]


def bits_per_prb(snr_db: float, symbols: int = 14) -> tuple[int, float]:
    """Return (bits_per_PRB_for_given_symbols, expected_BLER)."""
    se = 0.0
    bler = 1.0  # below the lowest MCS, treat as untransmittable
    for thresh, eff, b in _MCS_TABLE:
        if snr_db >= thresh:
            se = eff
            bler = b
        else:
            break
    bits = int(se * 12 * symbols)
    return bits, bler


# PDCCH aggregation level vs SNR (dB). Real 5G uses 1, 2, 4, 8, 16 CCEs;
# each higher AL adds ~3 dB of robustness. The thresholds below are a rough
# approximation tuned so that a "factory" UE at 20 dB SNR uses AL=1 (cheap),
# while a cell-edge UE at 0 dB needs AL=8 (expensive).
def cce_aggregation_level(snr_db: float) -> int:
    """Return PDCCH aggregation level (CCEs per DCI) for the given SNR."""
    if snr_db >= 20:
        return 1
    if snr_db >= 14:
        return 2
    if snr_db >= 8:
        return 4
    if snr_db >= 2:
        return 8
    return 16


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
