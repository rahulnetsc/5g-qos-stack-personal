"""Stage-6 Part A analyser (`docs/wp9-plan.md` §21.3).

The failure modes pinned here are not hypothetical -- each has already cost
this project a wrong result:

  * a CSV level that never coerces back to its declared type, so its cell
    selects ZERO rows and scores a plausible 0.000 (CLAUDE.md);
  * an axis-membership test that treats a blank column as a level, so an
    excursion cell selects the 1,710 core-plane rows and an axis is promoted
    on that basis (CLAUDE.md, `wp9_gate.carries_axis`);
  * an empty selection printing a summary instead of raising (this stage's
    own first draft reported "distinct orderings: 0" from zero groups).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import analyse_stage6 as A  # noqa: E402
from wp9_sweep import BASE  # noqa: E402


# -- coercion at the boundary ---------------------------------------------

def test_bool_level_coerces_back_from_its_csv_string():
    """`bg`'s levels are bools; CSV gives 'True'. The string never equals the
    bool, so without coercion the cell selects nothing and scores 0.000."""
    assert A._coerce("bg", "True") is True
    assert "True" != True  # noqa: E712 -- the point of the test


def test_numeric_levels_coerce_and_unknown_levels_do_not():
    assert A._coerce("duty_cycle", "0.5") == 0.5
    assert A._coerce("snr_spread_db", "12.0") == 12.0
    assert A._coerce("duty_cycle", "0.7") is None, "an undeclared level must not coerce"
    assert A._coerce("duty_cycle", "banana") is None


def test_base_level_is_coercible_too():
    """The base level is a legitimate level on the core plane rows."""
    assert A._coerce("duty_cycle", str(BASE["duty_cycle"])) == BASE["duty_cycle"]


# -- axis membership -------------------------------------------------------

def _row(scheduler, seed, **axes):
    row = {"scheduler": scheduler, "seed": seed}
    row.update(axes)
    return row


def _full_cell(**axes):
    return [_row(arm, seed, **axes)
            for arm in A.ARMS for seed in range(A.N_SEEDS)]


def test_blank_axis_is_absent_not_a_level(tmp_path):
    """A row that did not vary `bg` must not be selectable as `bg`'s cell.

    This is the 1,710-row contamination in miniature."""
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text(
        "scheduler,seed,bg,duty_cycle,n_ues,load_mult,M01.p98\n"
        "PF,1,,,8,1.0,10.0\n"
        "PF,2,True,,,,11.0\n"
    )
    rows = A.load_rows(csv_path)
    assert "bg" not in rows[0], "a blank axis must be ABSENT, not present-as-''"
    assert rows[1]["bg"] is True
    from wp9_gate import carries_axis
    assert not carries_axis(rows[0], "bg")
    assert carries_axis(rows[1], "bg")


def test_base_cell_excludes_every_excursion_row():
    """The base cell is core-plane-only: a row carrying ANY excursion axis is
    a different cell even when its n_ues/load_mult match the base point."""
    rows = _full_cell(n_ues=BASE["n_ues"], load_mult=BASE["load_mult"])
    rows += _full_cell(n_ues=BASE["n_ues"], load_mult=BASE["load_mult"], bg=True)
    assert len(A.base_cell(rows)) == A.CELL_SIZE


# -- cell-size and seed-set assertions ------------------------------------

def test_wrong_cell_size_raises_rather_than_scoring():
    with pytest.raises(AssertionError, match="selected 2 rows"):
        A._assert_cell([_row("PF", 1), _row("PF", 2)], "toy")


def test_empty_cell_raises():
    with pytest.raises(AssertionError, match="selected 0 rows"):
        A._assert_cell([], "toy")


def test_contaminated_cell_raises():
    """1,710 rows is the real signature; any oversize selection must raise."""
    with pytest.raises(AssertionError, match="selected 60 rows"):
        A._assert_cell(_full_cell() + _full_cell(), "toy")


def test_missing_arm_raises():
    cell = [_row(arm, seed) for arm in ("PF", "Reservation") for seed in range(15)]
    with pytest.raises(AssertionError, match="arms"):
        A._assert_cell(cell, "toy")


def test_paired_deltas_require_equal_seed_sets_not_equal_sizes():
    """The whole point of the paired design is the SAME seeds; two disjoint
    sets of ten would otherwise silently become a difference of means."""
    base = [_row("PF", s, **{"M07.met": 1.0}) for s in range(10)]
    exc = [_row("PF", s + 100, **{"M07.met": 2.0}) for s in range(10)]
    with pytest.raises(AssertionError, match="seed sets differ"):
        A.paired_deltas(base, exc, "PF", "M07.met", relative=False)


def test_paired_deltas_are_within_seed():
    base = [_row("PF", s, **{"M07.met": float(s)}) for s in range(10)]
    exc = [_row("PF", s, **{"M07.met": float(s) + 2.0}) for s in range(10)]
    assert A.paired_deltas(base, exc, "PF", "M07.met", relative=False) == [2.0] * 10


def test_relative_delta_drops_zero_base_rather_than_dividing():
    base = [_row("PF", 0, **{"M05.fraction": 0.0}),
            _row("PF", 1, **{"M05.fraction": 2.0})]
    exc = [_row("PF", 0, **{"M05.fraction": 1.0}),
           _row("PF", 1, **{"M05.fraction": 3.0})]
    assert A.paired_deltas(base, exc, "PF", "M05.fraction", relative=True) == [0.5]


# -- the G6 verdict --------------------------------------------------------

def test_g6_verdict_reads_the_interval_not_the_point():
    """A point estimate far above the bar with an interval spanning it is
    UNDETERMINED, not a failed guarantee. The real TwoTier M01.p98 cell is
    +74.9% with CI [-24%, +211%]."""
    assert A.g6_verdict(-0.24, 2.11) == "INCONCLUSIVE"
    assert A.g6_verdict(0.25, 0.40) == "FAIL"
    assert A.g6_verdict(-0.05, 0.05) == "PASS"


def test_g6_verdict_bar_is_inclusive():
    assert A.g6_verdict(0.0, A.G6_BAR) == "PASS"
    assert A.g6_verdict(A.G6_BAR + 1e-9, A.G6_BAR + 1.0) == "FAIL"


def test_impairment_interval_flips_the_whole_interval_for_higher_better():
    """Flipping only the point would leave lo/hi the wrong way round and
    silently invert every M05 verdict."""
    ci = {"point": -0.10, "lo": -0.30, "hi": 0.05}
    imp, lo, hi = A.impairment_interval("M05.fraction", ci)
    assert (imp, lo, hi) == (0.10, -0.05, 0.30)
    assert lo <= hi
    assert A.impairment_interval("M01.p98", ci) == (-0.10, -0.30, 0.05)


# -- G12's structural precondition ----------------------------------------

def test_g12_raises_when_the_ramp_axis_matches_nothing(tmp_path):
    """Stage 4 ramps `video_tier`, not `load_mult`. Passing the wrong axis
    selected zero groups and printed 'distinct orderings: 0' -- a plausible
    number from an empty selection, which is the signature this project has
    recorded twice."""
    import json
    rec = {
        "schema_version": 1, "scenario_name": "toy", "scheduler_name": "PF",
        "seed": 1, "arm": {}, "meta": {}, "flows": {},
        "system": {"horizon_s": 1.0, "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0},
        "join_events": [], "timeseries_slot_index": None, "timeseries_time_s": None,
    }
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps({"axis_values": {"video_tier": 1.0}, "record": rec}) + "\n")
    with pytest.raises(AssertionError, match="matched NO record"):
        A.report_g12(tmp_path, "load_mult", ("n_ues",), "toy")
