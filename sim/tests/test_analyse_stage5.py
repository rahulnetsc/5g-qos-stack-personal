"""Tests for stage 5's blind-written analyser (docs/wp9-plan.md §16.9).

The analyser exists to enforce a read order and an exclusion that would
otherwise be discipline. Both are pinned here:

  - C1 is a STOP CONDITION, so it must FAIL LOUDLY on a difference and on a
    MISSING cell -- a check that silently passes when it compared nothing is
    worse than no check.
  - §16.5's exclusion must RAISE, not warn.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import pytest

from analyse_stage5 import (
    STAGE4_ONSET_N,
    _norm_csv,
    c5_stage4_identity,
    TransientExclusionError,
    WINDOWED_DIRECTION,
    _as_bool,
    _coerce,
    aggregate_panel,
    c1_null_identity,
    c2_census,
    c4_pre_window,
    contiguity_per_composition,
)
from wp9_sweep import STAGE5_GRID


def _panel_row(comp, n, lu, arm, seed, m02="0.01"):
    return {"composition": comp, "n_ues": n, "lidar_ues": lu,
            "scheduler": arm, "seed": seed, "M02": m02,
            "n_lidar_active": "0", "transient_excluded": False}


def _win_row(metric, window, subset, comp, n, lu, arm, seed, value):
    key = {"M01w": "p99", "M02w": "value", "M07w": "met",
           "M08w": "fraction"}[metric]
    return {"metric": metric, "window": window, "subset": subset,
            "composition": comp, "n_ues": n, "lidar_ues": lu,
            "scheduler": arm, "seed": seed, key: value}


# --- §16.5's exclusion must raise ----------------------------------------

def test_aggregating_an_excluded_column_raises():
    rows = [_panel_row("ugv_heavy", 32, 2, "PF", s) for s in (1, 2)]
    for r in rows:
        r["transient_excluded"] = True
    with pytest.raises(TransientExclusionError) as e:
        aggregate_panel(rows, "M02")
    # The message must point at the alternative, not just refuse.
    assert "M01w" in str(e.value) and "§16.5" in str(e.value)


def test_aggregating_control_cells_is_allowed():
    """Control cells are NOT excluded -- their run-aggregate metrics are
    legitimately interpretable and feed C5."""
    rows = [_panel_row("ugv_heavy", 32, 0, "PF", s, m02=str(v))
            for s, v in ((1, 0.01), (2, 0.03))]
    assert aggregate_panel(rows, "M02") == pytest.approx(0.02)


# --- C1, the stop condition ----------------------------------------------

def test_c1_passes_when_null_cells_are_identical():
    rows = []
    for lu in (0, 1, 2):
        for arm in ("PF", "TwoTier"):
            for seed in (11, 22):
                rows.append(_panel_row("sensor_dense", 4, lu, arm, seed))
                rows.append(_panel_row("sensor_dense", 8, lu, arm, seed))
    ok, notes = c1_null_identity(rows)
    assert ok, notes
    assert "compared 16 paired rows" in notes[0]


def test_c1_fails_on_any_difference():
    rows = []
    for lu in (0, 1, 2):
        for seed in (11, 22):
            rows.append(_panel_row("sensor_dense", 4, lu, "PF", seed))
            rows.append(_panel_row("sensor_dense", 8, lu, "PF", seed))
    # One metric column differs with NO lidar active -- plumbing, by
    # elimination.
    for r in rows:
        if r["lidar_ues"] == 2 and r["n_ues"] == 4 and r["seed"] == 11:
            r["M02"] = "0.02"
    ok, notes = c1_null_identity(rows)
    assert not ok
    assert any("cols differ" in n for n in notes)


def test_c1_fails_when_a_null_cell_is_missing_rather_than_passing_vacuously():
    """A stop condition that compared nothing must not report PASS -- that
    is how an empty selection scores 0.000 and survives."""
    rows = [_panel_row("sensor_dense", 4, 0, "PF", 11)]   # no lidar_ues 1/2
    ok, notes = c1_null_identity(rows)
    assert not ok
    assert any("NO shared rows" in n for n in notes)


# --- C2 -------------------------------------------------------------------

def test_c2_census_matches_the_registered_counts():
    ok, census = c2_census()
    assert ok, census
    assert census == {"total": 48, "control": 16, "excursion": 32,
                      "degenerate": 9, "null": 4}


# --- the serialization boundary ------------------------------------------

def test_axis_values_coerce_back_to_their_declared_types():
    """CLAUDE.md's rule. `lidar_ues` is an int axis; the CSV hands back a
    string, and a string never matches an int level."""
    assert _coerce("lidar_ues", "2", STAGE5_GRID) == 2
    assert _coerce("n_ues", "32", STAGE5_GRID) == 32
    assert _coerce("composition", "ugv_heavy", STAGE5_GRID) == "ugv_heavy"
    assert _coerce("composition", "nope", STAGE5_GRID) is None


def test_transient_excluded_survives_the_csv_boundary_as_a_bool():
    """The exact bug that made a stage-1 cell select zero rows: a bool
    round-trips as the string 'True' and matches nothing."""
    assert _as_bool("True") is True
    assert _as_bool("False") is False
    assert _as_bool(True) is True
    assert _as_bool("") is None


# --- contiguity is per composition, over ordered axes only ---------------

def test_contiguity_never_crosses_the_categorical_composition_axis():
    """§16.1.2: check_contiguity walks each axis by index +/-1, which invents
    adjacency between compositions that have no order."""
    w = []
    # ugv_heavy: one arm wins everywhere -> contiguous, nothing isolated.
    # sensor_dense: the SAME arm wins everywhere too. If contiguity crossed
    # compositions the two would prop each other up; per composition they
    # must be scored independently.
    for comp, winner in (("ugv_heavy", 3.0), ("sensor_dense", 3.0)):
        for n in STAGE5_GRID["n_ues"]:
            for lu in STAGE5_GRID["lidar_ues"]:
                for arm, val in (("PF", winner), ("Reservation", 1.0),
                                 ("TwoTier", 1.0)):
                    w.append(_win_row("M07w", "during_2", "non_lidar",
                                      comp, n, lu, arm, 1, val))
    out = contiguity_per_composition(w, "M07w")
    assert set(out) == set(STAGE5_GRID["composition"])
    assert out["ugv_heavy"]["scored"] == 12
    assert out["ugv_heavy"]["isolated"] == 0
    # Compositions with no rows are scored, not silently merged into another.
    assert out["mixed"]["scored"] == 0


def test_contiguity_flags_an_isolated_winner():
    w = []
    for n in STAGE5_GRID["n_ues"]:
        for lu in STAGE5_GRID["lidar_ues"]:
            iso = (n == 8 and lu == 1)
            for arm in ("PF", "TwoTier"):
                win = "TwoTier" if iso else "PF"
                w.append(_win_row("M07w", "during_2", "non_lidar",
                                  "mixed", n, lu, arm, 1,
                                  3.0 if arm == win else 1.0))
    out = contiguity_per_composition(w, "M07w")
    assert out["mixed"]["isolated"] == 1


# --- C4 names a branch ----------------------------------------------------

def test_c4_reports_identical_when_the_pre_window_matches():
    w = []
    for lu in (0, 2):
        for seed in range(6):
            w.append(_win_row("M02w", "pre", "non_lidar", "ugv_heavy", 32,
                              lu, "PF", seed, 0.01))
            w.append(_win_row("M08w", "pre", "non_lidar", "ugv_heavy", 32,
                              lu, "PF", seed, 0.9))
    assert c4_pre_window(w)["branch"] == "identical"


def test_c4_reports_different_when_provisioning_alone_moves_the_pre_window():
    """The branch that matters: a 12 Mbps GBR contract carrying no traffic
    already changing scheduling makes every contrast a COMPOUND treatment."""
    w = []
    for seed in range(8):
        w.append(_win_row("M02w", "pre", "non_lidar", "ugv_heavy", 32, 0,
                          "PF", seed, 0.010))
        w.append(_win_row("M02w", "pre", "non_lidar", "ugv_heavy", 32, 2,
                          "PF", seed, 0.020 + seed * 1e-5))
    assert c4_pre_window(w)["branch"] == "different"


# --- registered constants -------------------------------------------------

def test_direction_signs_and_stage4_onset_are_the_registered_ones():
    """§15.4's onset table is what E2 is scored against; a silent edit would
    move the goalposts after the fact."""
    assert WINDOWED_DIRECTION == {"M01w": -1, "M02w": -1,
                                 "M07w": +1, "M08w": +1}
    assert STAGE4_ONSET_N == {"sensor_dense": None, "mixed": 32,
                              "drone_heavy": 32, "ugv_heavy": 16}


# --- C5's normalisation, found by the real run ---------------------------

def test_norm_csv_maps_empty_and_none_alike():
    assert _norm_csv("") is None
    assert _norm_csv("None") is None
    assert _norm_csv("0.5") == "0.5"


def test_c5_does_not_flag_a_normalisation_difference_as_a_mismatch(tmp_path):
    """The bug the real run caught: `load_rows` maps ''-> None on the
    stage-5 side, so comparing against RAW stage-4 strings compared the
    normalisation and reported all 480 control rows as differing, with zero
    real differences underneath.

    A control that cries wolf is as useless as one that never fires -- it
    would have been read as "plumbing the lidar axis changed the lidar-off
    path", which is the one conclusion C5 exists to license.
    """
    s4 = tmp_path / "stages4_rows.csv"
    s4.write_text(
        "composition,n_ues,video_tier,scheduler,seed,M02,M04.flow\n"
        "ugv_heavy,8,1.0,PF,7,0.01,\n")
    rows = [{"composition": "ugv_heavy", "n_ues": 8, "lidar_ues": 0,
             "scheduler": "PF", "seed": 7, "M02": "0.01",
             "M04.flow": None,          # load_rows turned '' into None
             "transient_excluded": False}]
    ok, notes = c5_stage4_identity(rows, s4)
    assert ok, notes
    assert "compared 1 control rows" in notes[0]


def test_c5_still_catches_a_real_difference(tmp_path):
    """The fix must not have made C5 unable to fail."""
    s4 = tmp_path / "stages4_rows.csv"
    s4.write_text(
        "composition,n_ues,video_tier,scheduler,seed,M02\n"
        "ugv_heavy,8,1.0,PF,7,0.01\n")
    rows = [{"composition": "ugv_heavy", "n_ues": 8, "lidar_ues": 0,
             "scheduler": "PF", "seed": 7, "M02": "0.02",
             "transient_excluded": False}]
    ok, notes = c5_stage4_identity(rows, s4)
    assert not ok
    assert any("cols differ" in n for n in notes)


# --- E2's post-hoc CI correction ----------------------------------------

def _m07_pair(comp, n, arm, seed, ctrl, on):
    return [_win_row("M07w", "during_2", "non_lidar", comp, n, 0, arm, seed, ctrl),
            _win_row("M07w", "during_2", "non_lidar", comp, n, 2, arm, seed, on)]


def test_registered_e2_fires_on_a_one_seed_difference():
    """Documents the defect rather than hiding it: the pre-registered
    criterion is a bare mean comparison, so a single seed losing a single
    contract declares the composition 'breaking'."""
    from analyse_stage5 import e2_breaking_n
    w = []
    for seed in range(10):
        drop = 1 if seed == 0 else 0        # one seed, one contract
        for arm in ("PF", "Reservation", "TwoTier"):
            w += _m07_pair("ugv_heavy", 4, arm, seed, 3.0, 3.0 - drop)
    assert e2_breaking_n(w)["ugv_heavy"]["breaking_n"] == 4


def test_paired_ci_correction_does_not_fire_on_that_same_noise():
    from analyse_stage5 import e2_breaking_n_paired_ci
    w = []
    for seed in range(10):
        drop = 1 if seed == 0 else 0
        for arm in ("PF", "Reservation", "TwoTier"):
            w += _m07_pair("ugv_heavy", 4, arm, seed, 3.0, 3.0 - drop)
    assert e2_breaking_n_paired_ci(w)["ugv_heavy"]["breaking_n"] is None


def test_paired_ci_correction_still_fires_on_a_real_collapse():
    """The correction must not be merely more conservative -- it has to
    still detect the effect the excursion exists to measure."""
    from analyse_stage5 import e2_breaking_n_paired_ci
    w = []
    for seed in range(10):
        for arm in ("PF", "Reservation", "TwoTier"):
            w += _m07_pair("ugv_heavy", 16, arm, seed, 10.0, 1.0)
    out = e2_breaking_n_paired_ci(w)["ugv_heavy"]
    assert out["breaking_n"] == 16
    assert out["holds"] is True          # 16 <= stage-4 onset 16


def test_both_undefined_is_reported_as_consistent_not_as_a_miss():
    """sensor_dense never separated in stage 4 and never breaks here. That
    is agreement, and `holds=False` alone would read as a failure."""
    from analyse_stage5 import e2_breaking_n_paired_ci
    out = e2_breaking_n_paired_ci([])["sensor_dense"]
    assert out["breaking_n"] is None and out["stage4_onset_n"] is None
    assert out["consistent_both_undefined"] is True
