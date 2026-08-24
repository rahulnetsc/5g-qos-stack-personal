"""TR 38.901 InF (Indoor Factory) path loss and LOS probability.

Source, checked directly rather than reconstructed from memory (CLAUDE.md's
BSR-table rule -- the same standard applies to spec tables in general, not
just 38.321's): ``ATIS.3GPP.38.901.V1610.pdf`` (3GPP TR 38.901 V16.1.0, ATIS
transposition), Table 7.4.1-1 (path loss), Table 7.4.2-1 (LOS probability),
Table 7.2-4 (per-sub-scenario clutter parameters), Table 7.8-7 (calibration-
study example values for clutter density/height/BS height/noise figure) --
see ``docs/wp6-plan.md`` sec 0/2/Decision 6 for the exact page/line
citations this was transcribed from.

The spec defines FIVE InF sub-scenarios, not four: InF-SL, InF-DL, InF-SH,
InF-DH (sparse/dense clutter crossed with low/high BS height), and InF-HH
("high Tx, high Rx" -- both antennas elevated above clutter, independent of
clutter density). InF-HH is structurally different from the other four: its
LOS probability is unconditionally 1.0 (Table 7.4.2-1), so it never reaches
an NLOS path loss formula at all -- Table 7.4.1-1 has no InF-HH NLOS row.
``docs/wp6-plan.md`` sec 0 records that this repo's own docs previously
named the four clutter/height variants plus HH as "SL/DL/SH/HH", omitting
InF-DH -- fixed here and in a new README.md sec 8 item, not silently
inherited.

Depends on nothing outside itself (no ``sim``/``scheduler`` imports),
matching ``scheduler/link.py``'s and ``sim/harq.py``'s own stated design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

INF_SUB_SCENARIOS = ("SL", "DL", "SH", "DH", "HH")

# InF-HH has no clutter-dependent LOS-probability/path-loss branch (always
# LOS) -- these three sub-scenarios plus their two low/high-BS counterparts
# are the only ones that need clutter parameters at all.
_INF_CLUTTER_SUB_SCENARIOS = ("SL", "DL", "SH", "DH")


@dataclass(frozen=True)
class InfClutterParams:
    """Table 7.2-4's per-sub-scenario clutter geometry, at Table 7.8-7's
    calibration-study example values (not a confirmed value for any real
    deployment -- docs/wp6-plan.md Decision 6)."""

    d_clutter_m: float
    r: float  # clutter density ratio (fraction of surface area occupied), 0-1
    h_c_m: float  # effective clutter height


# Table 7.2-4's "Typical clutter size" row (10m sparse / 2m dense) crossed
# with Table 7.8-7's calibration-example clutter density (20% low / 60%
# high) and clutter height (2m low / 6m high). "Low"/"high" clutter density
# maps to the Sparse/Dense letter in the sub-scenario name, not to the BS
# height letter.
_CLUTTER_PARAMS: dict[str, InfClutterParams] = {
    "SL": InfClutterParams(d_clutter_m=10.0, r=0.20, h_c_m=2.0),
    "DL": InfClutterParams(d_clutter_m=2.0, r=0.60, h_c_m=6.0),
    "SH": InfClutterParams(d_clutter_m=10.0, r=0.20, h_c_m=2.0),
    "DH": InfClutterParams(d_clutter_m=2.0, r=0.60, h_c_m=6.0),
}

# Table 7.8-7's calibration-example BS heights, keyed by the height letter.
INF_BS_HEIGHT_M: dict[str, float] = {
    "SL": 1.5,
    "DL": 1.5,
    "SH": 8.0,
    "DH": 8.0,
    # InF-HH: "high Tx, high Rx" -- both ends elevated; no single spec
    # example value given (Table 7.8-7 only calibrates the other four).
    # Reuse the high-BS value as the representative default.
    "HH": 8.0,
}


def _validate_sub_scenario(inf_scenario: str) -> None:
    if inf_scenario not in INF_SUB_SCENARIOS:
        raise ValueError(
            f"unknown InF sub-scenario {inf_scenario!r}; must be one of {INF_SUB_SCENARIOS}"
        )


def inf_los_probability(
    inf_scenario: str, d_2d_m: float, h_bs_m: float, h_ut_m: float
) -> float:
    """TR 38.901 Table 7.4.2-1's InF LOS probability.

    InF-HH: unconditionally 1.0 (both antennas elevated above clutter).
    InF-SL/DL: ``exp(-d_2D / k)``, ``k = -d_clutter / ln(1-r)``.
    InF-SH/DH: same ``k`` scaled by ``(h_BS - h_UT) / (h_c - h_UT)``.

    Raises ValueError if ``r >= 1`` (``ln(1-r)`` singular) or, for SH/DH,
    if ``h_c_m == h_ut_m`` (division by zero in the height-scaling term) --
    loudly wrong beats silently wrong, matching sim/power.py's precedent.
    """
    _validate_sub_scenario(inf_scenario)
    if inf_scenario == "HH":
        return 1.0
    params = _CLUTTER_PARAMS[inf_scenario]
    if params.r >= 1.0:
        raise ValueError(f"clutter density r={params.r} must be < 1")
    k = -params.d_clutter_m / math.log(1.0 - params.r)
    if inf_scenario in ("SH", "DH"):
        height_denom = params.h_c_m - h_ut_m
        if height_denom == 0.0:
            raise ValueError(
                f"h_c_m ({params.h_c_m}) == h_ut_m ({h_ut_m}): "
                "InF-SH/DH's LOS-probability height-scaling term is undefined"
            )
        k *= (h_bs_m - h_ut_m) / height_denom
    return math.exp(-d_2d_m / k)


def inf_path_loss_db(
    inf_scenario: str, d_3d_m: float, f_c_ghz: float, los: bool
) -> tuple[float, float]:
    """TR 38.901 Table 7.4.1-1's InF path loss.

    Returns ``(path_loss_db, shadow_fading_sigma_db)``. ``los=True`` (or
    ``inf_scenario == "HH"``, which is always LOS) uses the common
    ``PL_LOS`` formula shared by every InF sub-scenario; otherwise each
    sub-scenario's own NLOS formula is combined with ``PL_LOS`` via
    ``max()``, per the spec.

    InF-DL's NLOS formula is spec'd as ``max(PL', PL_LOS, PL_InF-SL)`` --
    it also maxes against InF-SL's own NLOS ``PL'`` term, not just the
    shared ``PL_LOS`` (docs/wp6-plan.md sec 2 flags this as easy to drop by
    analogy with the other three rows, which only max against ``PL_LOS``).
    Numerically this is equivalent to computing
    ``max(PL'_DL, max(PL'_SL, PL_LOS))`` since ``PL_LOS`` is already one of
    the three operands either way -- included as a direct three-way max
    here rather than a nested one, for the same result.

    Raises ValueError outside the spec's validated ``1 <= d_3D <= 600 m``
    range (Table 7.4.1-1's own applicability note), rather than silently
    extrapolating a formula the spec doesn't claim holds there.
    """
    _validate_sub_scenario(inf_scenario)
    if not (1.0 <= d_3d_m <= 600.0):
        raise ValueError(
            f"d_3D={d_3d_m}m outside InF's spec-validated range [1, 600]m"
        )
    pl_los = 31.84 + 21.50 * math.log10(d_3d_m) + 19.00 * math.log10(f_c_ghz)
    if los or inf_scenario == "HH":
        return pl_los, 4.3

    log_d3d = math.log10(d_3d_m)
    log_fc = math.log10(f_c_ghz)
    if inf_scenario == "SL":
        pl_prime = 33.00 + 25.5 * log_d3d + 20.0 * log_fc
        return max(pl_prime, pl_los), 5.7
    if inf_scenario == "DL":
        pl_prime = 18.6 + 35.7 * log_d3d + 20.0 * log_fc
        pl_sl_prime = 33.00 + 25.5 * log_d3d + 20.0 * log_fc  # InF-SL's own NLOS PL'
        return max(pl_prime, pl_los, pl_sl_prime), 7.2
    if inf_scenario == "SH":
        pl_prime = 32.4 + 23.0 * log_d3d + 20.0 * log_fc
        return max(pl_prime, pl_los), 5.9
    # inf_scenario == "DH" (only remaining non-HH case; HH returned above)
    pl_prime = 33.63 + 21.9 * log_d3d + 20.0 * log_fc
    return max(pl_prime, pl_los), 4.0
