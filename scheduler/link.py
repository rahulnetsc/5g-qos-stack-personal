"""Link adaptation -- SNR to spectral efficiency / PDCCH aggregation level.

This is the scheduler's radio model: how a UE's channel quality maps to
bits per PRB (an MCS proxy) and to the PDCCH cost of a grant. In an OAI
deployment these would be the real 3GPP MCS and CCE-aggregation tables;
here they are crude staircases, good enough for comparative scheduler work.
"""

# (snr_db_threshold, spectral_efficiency_bps_per_hz, target_BLER)
# Crude staircase derived from a 0.75-of-Shannon curve. Captures the macro
# behaviour (higher SNR -> more bits/RB) without being defensible at the PHY
# level. bits_per_prb() consumes SE as if it were bits/RE (i.e. ignores the
# ~7% CP overhead between b/s/Hz and b/RE); the carrier overhead_factor knob
# dominates that error, so it is fine for comparative work.
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
    """Return (bits_per_PRB_for_given_symbols, expected_BLER) for the MCS
    the scheduler would pick at ``snr_db``. BLER here is the target BLER at
    the picked MCS (uniform 10% in the table), i.e. the *matched* BLER
    assuming the true SNR equals ``snr_db``. When the scheduler's ``snr_db``
    differs from the true SNR at transmission time (CQI staleness), use
    ``bler_for_mcs`` instead to get the mismatch-adjusted BLER."""
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


def mcs_threshold_for_snr(snr_db: float) -> float:
    """Return the SNR threshold of the MCS that ``bits_per_prb`` would pick
    for ``snr_db``. This is the "picked MCS's operating point": at this SNR
    the target BLER (10%) is met; below it, BLER climbs (see bler_for_mcs).
    Returns the lowest threshold - 3 dB when snr_db is below the whole
    table (representing an unusable MCS)."""
    picked = _MCS_TABLE[0][0] - 3.0
    for thresh, _, _ in _MCS_TABLE:
        if snr_db >= thresh:
            picked = thresh
        else:
            break
    return picked


def bler_for_mcs(
    mcs_threshold_db: float, true_snr_db: float, base_bler: float = 0.10
) -> float:
    """BLER for an MCS with operating threshold ``mcs_threshold_db`` when the
    true instantaneous SNR is ``true_snr_db``. If the true SNR is at or above
    the threshold, BLER stays at the (link-adapted) target. Below the
    threshold, BLER doubles per dB of shortfall -- a crude approximation of
    the sharp BLER curves in real 5G, which is what makes an aggressively
    picked MCS expensive when CQI was stale-optimistic."""
    margin = true_snr_db - mcs_threshold_db
    if margin >= 0.0:
        return base_bler
    # Doubles per dB below threshold; capped at 1.0 (total loss).
    return min(1.0, base_bler * (2.0 ** (-margin)))


# PDCCH aggregation level vs SNR (dB). Real 5G uses 1, 2, 4, 8, 16 CCEs;
# each higher AL adds ~3 dB of robustness. The thresholds below are a rough
# approximation tuned so a "factory" UE at 20 dB SNR uses AL=1 (cheap) while
# a cell-edge UE at 0 dB needs AL=8 (expensive).
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
