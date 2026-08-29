"""Tests for scripts/wp9_gate.py -- WP9's stage-1 -> stage-2 promotion rule
(`docs/wp9-plan.md` §6.4).

These exist because the rule's whole value is that it was committed before
stage 1 ran and cannot be re-cut afterwards. An untested rule could be
"corrected" during analysis and nobody would know; a tested one cannot be
changed without the diff and the failing test both being visible.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from wp9_gate import (  # noqa: E402
    CORE_PLANE_AXES,
    EFFECT_SIZE_THRESHOLD,
    PRIMARY_METRIC_COLUMNS,
    AxisVerdict,
    evaluate_axis,
    evaluate_cell,
    select_for_stage_2,
)


def _rows(axis, level, arm_values, loss=0.2):
    """arm_values: {arm: [per-seed metric values]}. Loss is nonzero by
    default so is_informative passes unless a test says otherwise."""
    rows = []
    for arm, vals in arm_values.items():
        for seed, v in enumerate(vals):
            rows.append({
                axis: level, "scheduler": arm, "seed": seed,
                "M07.met": v, "M02": loss,
            })
    return rows


def test_consistent_separation_qualifies():
    """A clean, consistent difference passes all three conditions."""
    rows = _rows("n_ues", 8, {"PF": [8, 8, 8, 8, 8, 8, 8, 8, 8, 8],
                              "TwoTier": [5, 5, 6, 5, 5, 6, 5, 5, 5, 6]})
    res = evaluate_cell(rows, "n_ues", 8, "PF", "TwoTier", "M07.met")
    assert res is not None
    assert res.n_seeds == 10
    assert res.informative
    assert res.effect_size >= EFFECT_SIZE_THRESHOLD
    assert res.ci_excludes_zero
    assert res.qualifies


def test_noise_does_not_qualify():
    """Same mean difference of ~0 with real spread must not pass -- this is
    the case the effect-size threshold exists to reject."""
    rows = _rows("n_ues", 8, {"PF": [8, 5, 7, 6, 8, 5, 7, 6, 8, 5],
                              "TwoTier": [5, 8, 6, 7, 5, 8, 6, 7, 5, 8]})
    res = evaluate_cell(rows, "n_ues", 8, "PF", "TwoTier", "M07.met")
    assert res is not None
    assert not res.qualifies


def test_zero_loss_cell_is_excluded_even_with_a_large_effect():
    """is_informative is checked BEFORE the effect size, per §6.2: a cell
    with zero loss on both arms carries no information about which
    scheduler is better, however cleanly the arms differ there."""
    rows = _rows("load_mult", 0.25,
                 {"PF": [8] * 10, "TwoTier": [4] * 10}, loss=0.0)
    res = evaluate_cell(rows, "load_mult", 0.25, "PF", "TwoTier", "M07.met")
    assert res is not None
    assert res.effect_size == float("inf")   # perfectly consistent...
    assert not res.informative               # ...but uninformative
    assert not res.qualifies


def test_zero_variance_nonzero_mean_is_infinite_effect_not_a_crash():
    """A perfectly consistent difference is the strongest evidence
    available, not a divide-by-zero to drop."""
    rows = _rows("n_ues", 8, {"PF": [8] * 10, "TwoTier": [5] * 10})
    res = evaluate_cell(rows, "n_ues", 8, "PF", "TwoTier", "M07.met")
    assert res.effect_size == float("inf")
    assert res.qualifies


def test_seeds_are_paired_and_unmatched_seeds_are_dropped():
    """A seed contributes only if BOTH arms produced a numeric value, so a
    `pending` metric on one arm drops that seed rather than being compared
    against a missing value."""
    rows = _rows("n_ues", 8, {"PF": [8] * 10, "TwoTier": [5] * 10})
    for r in rows:
        if r["scheduler"] == "TwoTier" and r["seed"] in (0, 1, 2):
            r["M07.met"] = None
    res = evaluate_cell(rows, "n_ues", 8, "PF", "TwoTier", "M07.met")
    assert res.n_seeds == 7


def test_too_few_paired_seeds_returns_none():
    rows = _rows("n_ues", 8, {"PF": [8], "TwoTier": [5]})
    assert evaluate_cell(rows, "n_ues", 8, "PF", "TwoTier", "M07.met") is None


def test_axis_qualifies_if_any_level_does():
    """Rule 2 is an OR over levels, metrics and arm pairs."""
    rows = _rows("min_rb", 1, {"PF": [8] * 10, "TwoTier": [8] * 10})
    rows += _rows("min_rb", 20, {"PF": [8] * 10, "TwoTier": [4] * 10})
    v = evaluate_axis(rows, "min_rb", [1, 20], [("PF", "TwoTier")])
    assert v.qualifies
    assert v.best.level == 20


def test_axis_with_no_separation_anywhere_does_not_qualify():
    rows = _rows("min_rb", 1, {"PF": [8] * 10, "TwoTier": [8] * 10})
    rows += _rows("min_rb", 20, {"PF": [8] * 10, "TwoTier": [8] * 10})
    v = evaluate_axis(rows, "min_rb", [1, 20], [("PF", "TwoTier")])
    assert not v.qualifies
    assert v.best is None


def test_core_plane_always_promoted_and_only_one_excursion_joins_it():
    """Rule 3: the stage-2 budget fits the core plane plus ONE excursion."""
    verdicts = [
        AxisVerdict(axis="n_ues", qualifies=True),
        AxisVerdict(axis="load_mult", qualifies=True),
    ]
    strong = evaluate_axis(
        _rows("min_rb", 20, {"PF": [8] * 10, "TwoTier": [4] * 10}),
        "min_rb", [20], [("PF", "TwoTier")])
    weak = evaluate_axis(
        _rows("k2_slots", 1, {"PF": [8, 8, 7, 8, 8, 7, 8, 8, 8, 7],
                              "TwoTier": [7, 8, 8, 7, 8, 8, 7, 8, 7, 8]}),
        "k2_slots", [1], [("PF", "TwoTier")])
    sel = select_for_stage_2(verdicts + [strong, weak])
    assert set(CORE_PLANE_AXES).issubset(set(sel["promoted"]))
    assert "min_rb" in sel["promoted"]
    assert len(sel["promoted"]) <= 3
    assert "k2_slots" not in sel["promoted"]
    # Rule 3's honesty requirement: dropped axes are named WITH a score.
    assert any(d["axis"] == "k2_slots" for d in sel["dropped"])


def test_zero_qualifying_excursions_is_reported_not_worked_around():
    """Rule 7. The function must report the negative result, not lower the
    bar to find a qualifier -- there is deliberately no parameter that
    could."""
    verdicts = [
        AxisVerdict(axis="n_ues", qualifies=True),
        AxisVerdict(axis="load_mult", qualifies=True),
        evaluate_axis(
            _rows("min_rb", 1, {"PF": [8] * 10, "TwoTier": [8] * 10}),
            "min_rb", [1], [("PF", "TwoTier")]),
    ]
    sel = select_for_stage_2(verdicts)
    assert sel["zero_qualified"]
    assert sel["promoted"] == list(CORE_PLANE_AXES)


def test_primary_metric_set_is_exactly_the_five_pre_registered():
    """A guard on the pre-registration itself: adding a sixth primary metric
    mid-analysis is the specific failure §6.4 exists to prevent, so it must
    fail a test rather than pass silently."""
    assert PRIMARY_METRIC_COLUMNS == (
        "M07.met", "M08.fraction", "M01.p98", "M02", "M09.worst",
    )
    assert EFFECT_SIZE_THRESHOLD == 1.0


# -- cell selection: the defect that promoted a contaminated axis ---------


def _synthetic_sweep_rows(n_seeds=10):
    """Rows shaped exactly as `regime_sweep.sweep()` emits them: each row
    carries ONLY the axes its own cell varied. Synthesised rather than read
    from a sweep artefact so the test does not depend on one existing."""
    from wp9_sweep import CORE_PLANE, EXCURSIONS

    rows = []
    arms = ("PF", "Reservation", "TwoTier")
    for n in CORE_PLANE["n_ues"]:
        for lm in CORE_PLANE["load_mult"]:
            for arm in arms:
                for seed in range(n_seeds):
                    rows.append({"n_ues": n, "load_mult": lm,
                                 "scheduler": arm, "seed": seed,
                                 "M07.met": 1.0, "M02": 0.1})
    for axis, levels in EXCURSIONS.items():
        for level in levels:
            for arm in arms:
                for seed in range(n_seeds):
                    rows.append({axis: level, "scheduler": arm, "seed": seed,
                                 "M07.met": 1.0, "M02": 0.1})
    return rows


def test_no_excursion_cell_can_select_core_plane_rows():
    """The invariant. `pdb_ms` and `inf_scenario` have a None base level, and
    the old selection (`r.get(axis) == level`) could not tell "this axis at
    its base" from "this row does not carry this axis" -- so their cells
    selected 1,710 of stage 1's 1,770 rows, all 1,260 core-plane rows
    included, and `pdb_ms` was promoted into a 3-hour stage 2 on that basis.

    Checked for EVERY excursion axis, not just the two that were caught, so
    it generalises to any future axis with a None/False-ish base.
    """
    from wp9_gate import carries_axis
    from wp9_sweep import CORE_PLANE, EXCURSIONS

    rows = _synthetic_sweep_rows()
    n_arms, n_seeds = 3, 10
    for axis, levels in EXCURSIONS.items():
        for level in levels:
            cell = [r for r in rows
                    if carries_axis(r, axis) and r.get(axis) == level]
            assert len(cell) == n_arms * n_seeds, (
                f"{axis}={level} selected {len(cell)} rows, expected 30")
            core = [r for r in cell if any(k in r for k in CORE_PLANE)]
            assert not core, (
                f"{axis}={level} selected {len(core)} CORE-PLANE rows")


def test_carries_axis_distinguishes_absent_from_base_valued():
    from wp9_gate import carries_axis

    assert not carries_axis({"n_ues": 8}, "pdb_ms")        # absent
    assert not carries_axis({"pdb_ms": ""}, "pdb_ms")      # CSV round-trip
    assert not carries_axis({"pdb_ms": None}, "pdb_ms")    # explicit None
    assert carries_axis({"pdb_ms": 10.0}, "pdb_ms")        # real level
    assert carries_axis({"shared_lcg": False}, "shared_lcg")  # falsy but real
