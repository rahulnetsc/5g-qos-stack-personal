"""Link adaptation -- SNR to spectral efficiency / PDCCH aggregation level.

This is the scheduler's radio model: how a UE's channel quality maps to
bits per PRB (an MCS proxy) and to the PDCCH cost of a grant. In an OAI
deployment these would be the real 3GPP MCS and CCE-aggregation tables;
here they are crude staircases, good enough for comparative scheduler work.

HARQ additions (feat/harq-bler-retx)
-------------------------------------
bler_sigmoid()     -- SNR-adaptive BLER replacing the flat 10% in the MCS table.
combining_gain_db() -- effective SNR gain from HARQ combining at each retx attempt.

The two functions work together in the HARQEngine (driver.py):

    delta_snr = snr_inst - snr_ewma          # AR(1) fluctuation around EWMA
    gain      = combining_gain_db(retx_count, mode)
    bler      = bler_sigmoid(delta_snr + gain)
    success   = random() > bler

At nominal SNR (delta=0, retx=0) BLER=0.10 matching the MCS table target.
Each retx attempt shifts the effective SNR upward by combining_gain_db(),
driving BLER rapidly toward zero (IR: BLER<0.001 by the second attempt at
nominal SNR).
"""

import math

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
    """Return (bits_per_PRB_for_given_symbols, expected_BLER).

    expected_BLER is the MCS-table nominal value (0.10 for all rows here).
    In the HARQ feature branch this is used only for MCS selection (TBS
    sizing). The actual per-slot BLER outcome is determined by bler_sigmoid().
    """
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


# ---------------------------------------------------------------------------
# HARQ physical-layer model
# ---------------------------------------------------------------------------

def bler_sigmoid(delta_snr_db: float, steepness: float = 1.5) -> float:
    """BLER as a function of instantaneous SNR deviation from the EWMA.

    ``delta_snr_db = snr_inst - snr_ewma``

    The EWMA is the link adaptation operating point -- the SNR the MCS was
    chosen for.  The AR(1) process drives snr_inst above and below that point
    each slot.

    Shape
    -----
    * delta = 0   → BLER = 0.10  (nominal 10 % at the operating point)
    * delta = +3  → BLER ≈ 0.002 (channel better than expected, rare errors)
    * delta = +6  → BLER ≈ 0.000 (very good fade realisation)
    * delta = -3  → BLER ≈ 0.198 (channel worse, approaching 20 % ceiling)
    * delta = -6  → BLER = 0.200 (deep fade, maximum modelled BLER)

    The 20 % ceiling reflects that sustained deep fades cause the EWMA to
    adapt and the MCS to step down within O(100 ms); the model does not
    need to represent BLER > 20 % because real link adaptation prevents it.

    Parameters
    ----------
    delta_snr_db : float
        Instantaneous SNR minus EWMA SNR, in dB.  Positive = better than
        expected.  Pass ``delta_snr_db + combining_gain_db(retx_count)``
        for retransmissions.
    steepness : float
        Controls the cliff width.  1.5 gives a ~4 dB cliff (BLER 10 %→0 %),
        consistent with 5G NR LDPC link-level curves.

    Returns
    -------
    float
        BLER in [0.0, 0.2].
    """
    return 0.2 / (1.0 + math.exp(steepness * delta_snr_db))


# Incremental-redundancy gain per retx attempt (dB).
# Each entry is the *cumulative* effective SNR gain after that many
# retransmissions relative to the first attempt.
# Values are approximate fits to 3GPP NR LDPC link-level simulation results.
# retx=0 is the first (original) transmission -- no combining has occurred.
_IR_GAIN_DB: dict[int, float] = {
    0: 0.0,   # first attempt: no prior combining
    1: 4.0,   # first retx: ~4 dB gain (new parity bits double information)
    2: 6.5,   # second retx: diminishing returns
    3: 8.0,   # third retx (MAX_RETX): near full codeword received
}

_CHASE_GAIN_DB_PER_RETX = 3.0   # each retx doubles received energy → +3 dB


def combining_gain_db(retx_count: int, mode: str = "ir") -> float:
    """Effective SNR gain (dB) from HARQ combining at the given attempt.

    Parameters
    ----------
    retx_count : int
        Number of retransmissions so far.  0 = first (original) attempt,
        1 = first retransmission, up to MAX_RETX (typically 3).
    mode : str
        ``"ir"``    -- Incremental Redundancy (different RV each retx).
                       Higher gain early, saturates after 4 attempts.
                       This is the 5G NR LDPC default (RV0→RV2→RV3→RV1).
        ``"chase"`` -- Chase Combining (same RV=0 resent each time).
                       Linear +3 dB per retx (energy accumulation only).

    Returns
    -------
    float
        SNR gain in dB to add to delta_snr_db before calling bler_sigmoid().
    """
    if mode == "ir":
        return _IR_GAIN_DB.get(retx_count, _IR_GAIN_DB[3])
    # chase combining: linear 3 dB per retx
    return _CHASE_GAIN_DB_PER_RETX * retx_count


# ---------------------------------------------------------------------------
# PDCCH cost model (unchanged)
# ---------------------------------------------------------------------------

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
