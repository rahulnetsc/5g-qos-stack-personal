"""G6's transformation and its delta scoring.

The tests that matter are the ones that could FAIL: that the instrument is
byte-identical between conditions (a paired delta rests on it), that the
+20 % bound is ONE-SIDED, and that a zero baseline is not divided by.
"""
from __future__ import annotations

import pytest

from sim.scenarios.g1 import build_gt11_scenario
from sim.scenarios.g3 import build_gt22_scenario
from sim.scenarios.g5 import build_gt31_scenario
from sim.scenarios.g6 import (BG_5QI, CONDITIONS, SATURATOR_BPS,
                              background_flow_keys, instrument_is_unchanged,
                              with_firmware_push, with_saturator,
                              without_background)

BASES = {
    "g1": lambda n: build_gt11_scenario(seed=1, n_ues=n, horizon_slots=8_000),
    "g3": lambda n: build_gt22_scenario(seed=1, n_ues=n, horizon_slots=8_000),
    "g5": lambda n: build_gt31_scenario(seed=1, n_ues=n, horizon_slots=8_000),
}


# --- the finding the design rests on -------------------------------------

@pytest.mark.parametrize("name", sorted(BASES))
def test_every_base_ALREADY_carries_background_so_the_control_is_new(name):
    """G6's whole design rests on this: "load added" has nothing to be added
    to, so the published artefacts are the TREATMENT and the control does not
    exist in any of them. If a base ever stopped carrying background, the
    control and the treatment would be the same run."""
    sc = BASES[name](8)
    bg = background_flow_keys(sc)
    assert bg, f"{name} carries no 5QI-8/9 flow -- G6's control is not a control"


def test_removing_background_from_a_scenario_that_has_none_RAISES():
    sc = without_background(BASES["g3"](8))
    with pytest.raises(ValueError, match="no 5QI-8/9 flow"):
        without_background(sc)


# --- the property a paired delta rests on --------------------------------

@pytest.mark.parametrize("name", sorted(BASES))
@pytest.mark.parametrize("n", (4, 8, 16))
def test_the_INSTRUMENT_is_identical_across_every_condition(name, n):
    """A paired delta is only a delta if nothing else moved -- and `lcg` is in
    the comparison deliberately. LCG = DRB ID and the simulator's proxy for
    setup order is position in the UE's flow list, so REMOVING a flow can
    renumber the ones after it. A control whose instrument sits on a different
    logical channel group is not a control."""
    base = BASES[name](n)
    ctl = without_background(base)
    ul = with_saturator(base, direction="UL")
    dl = with_saturator(base, direction="DL")
    assert instrument_is_unchanged(ctl, ul), f"{name} n={n}: UL moved it"
    assert instrument_is_unchanged(ctl, dl), f"{name} n={n}: DL moved it"
    assert instrument_is_unchanged(base, ctl), f"{name} n={n}: removal moved it"


@pytest.mark.parametrize("name", sorted(BASES))
def test_treatment_and_control_differ_by_EXACTLY_the_saturator(name):
    """Built from the control rather than the original, so the pair differs by
    one flow -- adding a saturator on top of the existing filler would make
    them differ by the filler too."""
    base = BASES[name](8)
    ctl = without_background(base)
    for d in ("UL", "DL"):
        t = with_saturator(base, direction=d)
        assert len(t.flows) == len(ctl.flows) + 1
        added = [f for f in t.flows if f.qfi in BG_5QI]
        assert len(added) == 1 and added[0].direction == d
        assert added[0].traffic_params["rate_bps"] == SATURATOR_BPS


@pytest.mark.parametrize("name", sorted(BASES))
def test_the_saturator_never_rides_the_INSTRUMENT_robot(name):
    base = BASES[name](8)
    for d in ("UL", "DL"):
        t = with_saturator(base, direction=d)
        assert [f.ue_id for f in t.flows if f.qfi in BG_5QI] != [1]
    with pytest.raises(ValueError, match="instrument robot"):
        with_saturator(base, direction="UL", ue_id=1)


def test_the_firmware_push_is_FINITE_and_its_rate_is_derived():
    """A saturator never finishes, so its "completion time" would be the
    horizon by construction -- and the completion instant is GT-4.2's whole
    deliverable."""
    base = BASES["g1"](8)
    fw = with_firmware_push(base, horizon_s=10.0)
    f = [x for x in fw.flows if x.qfi in BG_5QI][0]
    assert f.direction == "DL"
    assert f.traffic_params["rate_bps"] == pytest.approx(
        500 * 1024 * 1024 * 8.0 / 10.0)
    # halving the horizon doubles the rate -- DERIVED, not picked
    fw2 = with_firmware_push(base, horizon_s=5.0)
    f2 = [x for x in fw2.flows if x.qfi in BG_5QI][0]
    assert f2.traffic_params["rate_bps"] == pytest.approx(
        2 * f.traffic_params["rate_bps"])


# --- the scoring, where the clause is under-specified --------------------

def _delta(stat, value, control, instrument="g5", condition="ul"):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from g6_isolation import score
    base = {"instrument": instrument, "arm": "TwoTier", "n_ues": 7, "seed": 1}
    rows = [{**base, "condition": "none", stat: control},
            {**base, "condition": condition, stat: value}]
    out = [d for d in score(rows)["deltas"] if d["stat"] == stat]
    assert len(out) == 1
    return out[0]


def test_the_shift_bound_is_ONE_SIDED_so_an_IMPROVEMENT_passes():
    """A statistic can improve under added load. Read as |delta| <= 20 %, a run
    that got 30 % BETTER would fail -- which is the wrong answer."""
    # lower_better: halving the gap is an improvement of 50 %
    got = _delta("g3_tele_gap_worst_ms", 50.0, 100.0, instrument="g3")
    assert got["part_b"] is True, "a 50 % improvement was scored as a failure"
    # ... and the same magnitude of HARM fails
    bad = _delta("g3_tele_gap_worst_ms", 150.0, 100.0, instrument="g3")
    assert bad["part_b"] is False


def test_the_bound_is_one_sided_for_higher_better_metrics_TOO():
    """The sign is read from DIRECTION, never hardcoded at the comparison
    site -- a sign restated per metric is how a threshold inverts for one."""
    # higher_better: completeness RISING is an improvement
    good = _delta("g5_cam_complete", 1.0, 0.5)
    assert good["part_b"] is True
    # ... falling by more than a fifth is harm
    bad = _delta("g5_cam_complete", 0.5, 1.0)
    assert bad["part_b"] is False


def test_a_ZERO_baseline_is_never_divided_by():
    """G3's campaign-silence count is legitimately 0 in the control.
    `(x - 0) / 0` is not a 20 % question."""
    same = _delta("g3_tele_over_tlive", 0, 0, instrument="g3")
    assert same["part_b"] is True and same["shift"] == 0
    worse = _delta("g3_tele_over_tlive", 3, 0, instrument="g3")
    assert worse["part_b"] is False, "a breach count rising from 0 must fail"


def test_part_A_and_part_B_are_INDEPENDENT_and_can_disagree():
    """The reason G6 exists: part A is the weaker test, and a statistic can
    stay inside its bound while degrading materially."""
    d = _delta("g3_tele_gap_worst_ms", 400.0, 100.0, instrument="g3")
    assert d["part_a"] is True, "400 ms is inside G3's own 500 ms bound"
    assert d["part_b"] is False, "a 4x rise must fail the shift test"


def test_a_treatment_row_with_no_CONTROL_is_dropped_not_scored():
    """An unpaired treatment has nothing to be a ratio against. Scoring it
    against a default would be the empty-selection failure wearing a ratio."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from g6_isolation import score
    rows = [{"instrument": "g3", "condition": "ul", "arm": "TwoTier",
             "n_ues": 7, "seed": 1, "g3_tele_gap_worst_ms": 400.0}]
    assert score(rows)["deltas"] == []


def test_every_scored_statistic_declares_BOTH_a_direction_and_a_bound():
    """A statistic in one table and not the other would be scored on one part
    and silently skipped on the other."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from g6_isolation import BOUNDS, DIRECTION
    assert set(DIRECTION) == set(BOUNDS)
    assert set(CONDITIONS) == {"none", "ul", "dl"}


def test_the_window_floor_is_the_INSTRUMENTS_not_the_fleets_worst_flow():
    """A worst-of-N statistic where the claim is about a NAMED instrument lets
    the fleet axis move the statistic as well as the load.

    Measured before this was fixed, PF at N=7 with no flood: the instrument
    camera's own floor is 1.0000 and M23's fleet-worst is 0.9901, so part A
    failed on EVERY arm in EVERY condition -- 0 of 30, a criterion nothing
    ever passes.
    """
    import inspect
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import g6_isolation as g6
    src = inspect.getsource(g6._one)
    assert "_instrument_window_floor" in src, (
        "g6 is reading a fleet-wide worst-flow value as the instrument's")
    # the fleet-wide value is still REPORTED, beside it, never as the verdict
    assert "g5_fleet_window_floor" in src
    assert "g5_fleet_window_floor" not in g6.BOUNDS
