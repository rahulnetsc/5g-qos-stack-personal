"""WP6 commit 1: sim/pathloss.py (TR 38.901 InF path loss + LOS
probability), dormant -- not referenced by any existing scenario yet
(docs/wp6-plan.md). Predicted, before writing this file: scripts/
regression_corpus.py --check stays fully clean, since no existing
UEConfig sets ``position``.

Numeric expectations below are transcribed directly from
ATIS.3GPP.38.901.V1610.pdf (3GPP TR 38.901 V16.1.0) Tables 7.4.1-1,
7.4.2-1, 7.2-4, 7.8-7 -- checked byte-for-byte against the spec text
(docs/wp6-plan.md sec 0/2), not re-derived from a formula written from
memory. If this test ever needs to change to match new code, re-check
against the spec text again, not against what the code currently does.
"""

import math

import pytest

from sim.pathloss import (
    INF_BS_HEIGHT_M,
    INF_SUB_SCENARIOS,
    inf_los_probability,
    inf_path_loss_db,
)


# -- INF_SUB_SCENARIOS: the real five, not the repo's old four ---------


def test_five_sub_scenarios_not_four():
    """docs/wp6-plan.md sec 0: this repo's own docs previously wrote the
    four InF sub-scenarios as SL/DL/SH/HH, omitting InF-DH -- the real
    TR 38.901 Table 7.2-4 set is SL/DL/SH/DH/HH (five members)."""
    assert set(INF_SUB_SCENARIOS) == {"SL", "DL", "SH", "DH", "HH"}


def test_bs_heights_cover_every_sub_scenario():
    assert set(INF_BS_HEIGHT_M) == set(INF_SUB_SCENARIOS)


# -- inf_path_loss_db: LOS formula, common to all five ------------------


def test_los_path_loss_matches_spec_formula_exactly():
    # PL_LOS = 31.84 + 21.50*log10(d3D) + 19.00*log10(fc), sigma=4.3
    d_3d, f_c = 50.0, 3.5
    expected_pl = 31.84 + 21.50 * math.log10(d_3d) + 19.00 * math.log10(f_c)
    for scenario in INF_SUB_SCENARIOS:
        pl_db, sigma = inf_path_loss_db(scenario, d_3d, f_c, los=True)
        assert pl_db == pytest.approx(expected_pl)
        assert sigma == pytest.approx(4.3)


def test_hh_is_always_the_los_formula_even_when_los_is_false():
    """InF-HH has no NLOS row in Table 7.4.1-1 -- both antennas are always
    elevated above clutter, so LOS always holds regardless of the ``los``
    argument."""
    d_3d, f_c = 50.0, 3.5
    expected_pl = 31.84 + 21.50 * math.log10(d_3d) + 19.00 * math.log10(f_c)
    pl_db, sigma = inf_path_loss_db("HH", d_3d, f_c, los=False)
    assert pl_db == pytest.approx(expected_pl)
    assert sigma == pytest.approx(4.3)


# -- inf_path_loss_db: NLOS, per sub-scenario ---------------------------


@pytest.mark.parametrize(
    "scenario,coeff_const,coeff_log_d,sigma",
    [
        ("SL", 33.00, 25.5, 5.7),
        ("SH", 32.4, 23.0, 5.9),
        ("DH", 33.63, 21.9, 4.0),
    ],
)
def test_nlos_formula_matches_spec_for_single_max_scenarios(
    scenario, coeff_const, coeff_log_d, sigma
):
    """SL/SH/DH's NLOS pathloss is max(PL', PL_LOS) -- no third term,
    unlike DL (see below)."""
    d_3d, f_c = 50.0, 3.5
    pl_prime = coeff_const + coeff_log_d * math.log10(d_3d) + 20.0 * math.log10(f_c)
    pl_los = 31.84 + 21.50 * math.log10(d_3d) + 19.00 * math.log10(f_c)
    expected = max(pl_prime, pl_los)
    pl_db, got_sigma = inf_path_loss_db(scenario, d_3d, f_c, los=False)
    assert pl_db == pytest.approx(expected)
    assert got_sigma == pytest.approx(sigma)


def test_dl_nlos_also_maxes_against_inf_sl():
    """docs/wp6-plan.md sec 2: InF-DL's NLOS pathloss is spec'd as
    max(PL', PL_LOS, PL_InF-SL) -- it also maxes against InF-SL's own NLOS
    PL' term, not just PL_LOS. InF-SL's shallower distance slope (25.5 vs
    InF-DL's 35.7) means InF-SL's term is the actual maximum at short
    range, so a three-term max that silently dropped the InF-SL term would
    be caught here."""
    d_3d, f_c = 5.0, 3.5
    pl_prime_dl = 18.6 + 35.7 * math.log10(d_3d) + 20.0 * math.log10(f_c)
    pl_los = 31.84 + 21.50 * math.log10(d_3d) + 19.00 * math.log10(f_c)
    pl_prime_sl = 33.00 + 25.5 * math.log10(d_3d) + 20.0 * math.log10(f_c)
    expected = max(pl_prime_dl, pl_los, pl_prime_sl)
    # Sanity: at this distance, confirm InF-SL's term really is the binding
    # one, so this test can't pass by accident under a two-term max.
    assert pl_prime_sl > pl_prime_dl and pl_prime_sl > pl_los
    pl_db, sigma = inf_path_loss_db("DL", d_3d, f_c, los=False)
    assert pl_db == pytest.approx(expected)
    assert sigma == pytest.approx(7.2)


def test_path_loss_rejects_distance_outside_validated_range():
    with pytest.raises(ValueError):
        inf_path_loss_db("SL", 0.5, 3.5, los=True)
    with pytest.raises(ValueError):
        inf_path_loss_db("SL", 601.0, 3.5, los=True)
    # Boundary values are inclusive per the spec's own "1 <= d3D <= 600m".
    inf_path_loss_db("SL", 1.0, 3.5, los=True)
    inf_path_loss_db("SL", 600.0, 3.5, los=True)


def test_path_loss_rejects_unknown_sub_scenario():
    with pytest.raises(ValueError):
        inf_path_loss_db("XX", 50.0, 3.5, los=True)


# -- inf_los_probability -------------------------------------------------


def test_hh_los_probability_is_always_one():
    assert inf_los_probability("HH", d_2d_m=1.0, h_bs_m=8.0, h_ut_m=1.5) == 1.0
    assert inf_los_probability("HH", d_2d_m=500.0, h_bs_m=8.0, h_ut_m=1.5) == 1.0


def test_low_bs_los_probability_matches_spec_formula():
    """InF-SL/DL: Pr_LOS = exp(-d2D / k), k = -d_clutter/ln(1-r).
    Sparse (SL): d_clutter=10m, r=0.20 (Table 7.2-4/7.8-7)."""
    d_2d = 15.0
    d_clutter, r = 10.0, 0.20
    k = -d_clutter / math.log(1.0 - r)
    expected = math.exp(-d_2d / k)
    got = inf_los_probability("SL", d_2d_m=d_2d, h_bs_m=1.5, h_ut_m=1.5)
    assert got == pytest.approx(expected)


def test_high_bs_los_probability_scales_by_height_ratio():
    """InF-SH/DH: same k, scaled by (h_BS - h_UT) / (h_c - h_UT).
    Sparse (SH): d_clutter=10m, r=0.20, h_c=2m (Table 7.2-4/7.8-7)."""
    d_2d, h_bs, h_ut = 15.0, 8.0, 1.5
    d_clutter, r, h_c = 10.0, 0.20, 2.0
    k = -d_clutter / math.log(1.0 - r) * (h_bs - h_ut) / (h_c - h_ut)
    expected = math.exp(-d_2d / k)
    got = inf_los_probability("SH", d_2d_m=d_2d, h_bs_m=h_bs, h_ut_m=h_ut)
    assert got == pytest.approx(expected)


def test_los_probability_decreases_with_distance():
    """Sanity on the formula shape, not a spec-value check: farther UEs
    are less likely to have a clear line of sight through clutter."""
    near = inf_los_probability("DL", d_2d_m=5.0, h_bs_m=1.5, h_ut_m=1.5)
    far = inf_los_probability("DL", d_2d_m=100.0, h_bs_m=1.5, h_ut_m=1.5)
    assert 0.0 <= far < near <= 1.0


def test_high_bs_los_probability_rejects_degenerate_height_denominator():
    with pytest.raises(ValueError):
        inf_los_probability("SH", d_2d_m=15.0, h_bs_m=8.0, h_ut_m=2.0)  # h_ut == h_c


def test_los_probability_rejects_unknown_sub_scenario():
    with pytest.raises(ValueError):
        inf_los_probability("XX", d_2d_m=15.0, h_bs_m=8.0, h_ut_m=1.5)
