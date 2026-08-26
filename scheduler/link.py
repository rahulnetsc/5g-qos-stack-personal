"""Link adaptation -- SNR to spectral efficiency / PDCCH aggregation level.

This is the scheduler's radio model: how a UE's channel quality maps to
bits per PRB (an MCS proxy) and to the PDCCH cost of a grant. In an OAI
deployment these would be the real 3GPP MCS and CCE-aggregation tables;
here they are crude staircases, good enough for comparative scheduler work.
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


def _mcs_index_for_snr(snr_db: float) -> int | None:
    """Return the index into ``_MCS_TABLE`` the scheduler would pick at
    ``snr_db``, walking the staircase from the bottom. None if ``snr_db``
    is below the lowest threshold (no viable MCS).

    The one staircase-walk implementation -- ``_mcs_row_for_snr`` and
    the public ``mcs_index_for_snr`` (Phase 2 D2(a), a persistent
    per-UE MCS index) both derive from this rather than each walking
    ``_MCS_TABLE`` a second, independent time. Two functions
    independently walking one table is how they drift.
    """
    idx = None
    for i, entry in enumerate(_MCS_TABLE):
        if snr_db >= entry[0]:
            idx = i
        else:
            break
    return idx


def _mcs_row_for_snr(snr_db: float) -> tuple[float, float, float] | None:
    """Return the (threshold, se, bler) row of _MCS_TABLE the scheduler
    would pick at ``snr_db`` -- see ``_mcs_index_for_snr`` for the walk.
    None if ``snr_db`` is below the lowest threshold (no viable MCS)."""
    idx = _mcs_index_for_snr(snr_db)
    return None if idx is None else _MCS_TABLE[idx]


def mcs_index_for_snr(snr_db: float) -> int:
    """Public: the MCS index (0-based position in ``_MCS_TABLE``) the
    scheduler would pick at ``snr_db`` -- for a persistent per-UE MCS
    index (Phase 2 D2(a), ``scheduler/reservation.py``'s commit-8
    section; ``sim/olla.py``'s ``MCS_INDEX_COUNT=12`` already matches
    this table's size, built against it from the start).

    Returns ``0`` (the floor), not ``None``, when ``snr_db`` is below
    the lowest threshold -- matching ``sim/olla.py::init_olla_state``'s
    own floor-at-``min_mcs`` convention. A persisted per-UE MCS index
    must always be a concrete, assignable int; unlike ``bits_per_prb``
    (where zero bits/PRB is itself a valid "untransmittable" answer) or
    ``snr_to_prb_floor`` (which deliberately raises), there is no
    "index -1" that would mean anything to a consumer of this value.
    """
    idx = _mcs_index_for_snr(snr_db)
    return 0 if idx is None else idx


def bits_per_prb(snr_db: float, symbols: int = 14) -> tuple[int, float]:
    """Return (bits_per_PRB_for_given_symbols, expected_BLER) for the MCS
    the scheduler would pick at ``snr_db``. BLER here is the target BLER at
    the picked MCS (uniform 10% in the table), i.e. the *matched* BLER
    assuming the true SNR equals ``snr_db``. When the scheduler's ``snr_db``
    differs from the true SNR at transmission time (CQI staleness), use
    ``bler_for_mcs`` instead to get the mismatch-adjusted BLER."""
    row = _mcs_row_for_snr(snr_db)
    if row is None:
        return 0, 1.0  # below the lowest MCS, treat as untransmittable
    _, se, bler = row
    return int(se * 12 * symbols), bler


def bits_per_prb_for_mcs(mcs_index: int, symbols: int = 14) -> tuple[int, float]:
    """Return (bits_per_PRB_for_given_symbols, expected_BLER) for an
    EXPLICIT MCS index into ``_MCS_TABLE``, bypassing the SNR walk --
    the Phase 2 D2(b) counterpart of ``bits_per_prb``, for a caller that
    already holds a persistent per-UE MCS index (``mcs_index_for_snr``,
    ``reservation.py``'s ``_UeState.ul_mcs_index``/``dl_mcs_index``)
    rather than an instantaneous SNR reading. Ground truth
    (``gNB_scheduler_dlsch.c:812-824``/``_ulsch.c:2203-2213``) always
    derives ``Qm``/``R`` from ``selected_mcs`` this way, never re-picks
    an MCS from SNR at the sizing step.

    ``mcs_index`` is clamped into ``[0, len(_MCS_TABLE) - 1]`` -- a
    persisted index is always in range by construction today, but a
    caller composing this from a not-yet-live OLLA offset (Phase 2 D2(b))
    should not be able to index out of bounds if that changes.

    Unlike ``bits_per_prb``, there is no "below the lowest threshold"
    case here -- every row index is a valid, transmittable MCS by
    definition; that untransmittable-SNR cutoff only exists in the
    SNR-to-row walk (``_mcs_row_for_snr`` returning ``None``), not in
    the table itself.
    """
    idx = max(0, min(len(_MCS_TABLE) - 1, mcs_index))
    _, se, bler = _MCS_TABLE[idx]
    return int(se * 12 * symbols), bler


def mcs_threshold_for_snr(snr_db: float) -> float:
    """Return the SNR threshold of the MCS that ``bits_per_prb`` would pick
    for ``snr_db``. This is the "picked MCS's operating point": at this SNR
    the target BLER (10%) is met; below it, BLER climbs (see bler_for_mcs).
    Returns the lowest threshold - 3 dB when snr_db is below the whole
    table (representing an unusable MCS)."""
    row = _mcs_row_for_snr(snr_db)
    if row is None:
        return _MCS_TABLE[0][0] - 3.0
    return row[0]


def snr_to_prb_floor(snr_db: float, payload_bytes: int, symbols: int = 14) -> int:
    """Sim-only PRB floor: the minimum PRBs needed to carry one MAC PDU of
    ``payload_bytes`` at the MCS ``bits_per_prb`` would pick for ``snr_db``.

    This is NOT OAI's min_rb -- that is ``nrmac->min_grant_prb``, a static
    gNB config constant unrelated to SNR or payload size
    (gNB_scheduler_ulsch.c:2055). This is a distinct, sim-only floor: how
    few PRBs a UE's payload could ever fit into at its current channel
    quality.

    Raises ValueError below the lowest MCS threshold. This deliberately
    diverges from bits_per_prb, which returns (0, 1.0) in that regime:
    bits_per_prb is reporting a rate, where zero bits/PRB is a valid
    answer, but for a PRB floor "zero PRBs suffice" would be a wrong
    answer, not a degenerate one.
    """
    bits_per_rb, _ = bits_per_prb(snr_db, symbols)
    if bits_per_rb <= 0:
        raise ValueError(f"no viable MCS at snr_db={snr_db}")
    payload_bits = payload_bytes * 8
    return math.ceil(payload_bits / bits_per_rb)


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
