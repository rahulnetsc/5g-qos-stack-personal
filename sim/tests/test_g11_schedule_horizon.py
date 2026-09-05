"""GT-7.1's schedule against the horizon it is run at.

THE DEFECT (found pricing G11's soak, 2026-09-05). The firmware push is at
T+10 min and the STOP drill at T+20 min, both ABSOLUTE because GT-7.1 states
them that way. At any shorter horizon the scenario built happily WITHOUT
them, so a run could look like GT-7.1 while missing its scripted events --
and every C1 result so far was produced at 400,000 slots (100 s), where
THREE of the four ingredients are absent.

A second defect beside it: `assert_schedule_fired` early-returned only when
BOTH the STOP and firmware counts were zero, then checked the STOP flow
unconditionally. Any horizon in [660 s, 1200 s) -- firmware expected, STOP
not -- aborted on an event the horizon cannot contain. Measured: the
3,200,000-slot battery run failed on all three arms.
"""

from __future__ import annotations

import pytest

from sim.scenarios.g11 import (SLOT_S, FirmwareWindow, StopDrill,
                               build_g11_scenario, expected_counts,
                               minimum_horizon_slots,
                               scripted_ingredients_present, scripted_windows)


def test_a_horizon_too_short_for_the_schedule_is_REFUSED():
    with pytest.raises(ValueError, match="cannot contain GT-7.1's schedule"):
        build_g11_scenario(seed=1, horizon_slots=400_000)


def test_the_refusal_names_the_minimum_and_the_event():
    with pytest.raises(ValueError) as exc:
        build_g11_scenario(seed=1, horizon_slots=400_000)
    msg = str(exc.value)
    assert "STOP drill" in msg and f"{minimum_horizon_slots():,}" in msg


def test_a_short_run_is_available_but_must_SAY_SO():
    sc = build_g11_scenario(seed=1, horizon_slots=400_000,
                            allow_partial_schedule=True)
    assert sc.flows
    present = scripted_ingredients_present(400_000)
    assert present == {"teleop": True, "pause": False,
                       "firmware": False, "stop": False}


def test_the_full_horizon_contains_every_ingredient():
    assert scripted_ingredients_present(7_200_000) == {
        "teleop": True, "pause": True, "firmware": True, "stop": True}
    build_g11_scenario(seed=1, horizon_slots=7_200_000)      # must not raise


def test_the_minimum_is_derived_from_the_schedule_not_restated():
    """Move the drill and the minimum must move with it."""
    late = StopDrill(at_s=2400.0)
    assert minimum_horizon_slots(stop=late) > minimum_horizon_slots()
    assert minimum_horizon_slots(stop=late) == int(
        (late.at_s + late.period_ms / 1000.0) / SLOT_S + 0.999999)


@pytest.mark.parametrize("horizon", [400_000, 800_000, 3_200_000, 7_200_000])
def test_no_scripted_window_starts_after_it_ends(horizon):
    """The clip produced (812.0, 800.0) at 3.2 M slots -- a window outside
    the run, in a partition of the run."""
    for name, wins in scripted_windows(horizon * SLOT_S).items():
        for a, b in wins:
            if a is None or b is None:
                continue
            assert a < b, f"{name}: window ({a}, {b}) starts after it ends"


def test_no_scripted_window_lies_wholly_outside_the_horizon():
    h_s = 3_200_000 * SLOT_S
    for name, wins in scripted_windows(h_s).items():
        if name in ("firmware", "stop"):
            continue          # absolute by design; expected_counts clips them
        for a, b in wins:
            if a is None or b is None:
                continue
            assert a < h_s, f"{name}: window ({a}, {b}) starts after the run ends"


def test_expected_counts_clips_to_the_horizon():
    at_400k = expected_counts(400_000)
    assert at_400k["firmware_windows"] == 0 and at_400k["stop_bursts"] == 0
    at_full = expected_counts(7_200_000)
    assert at_full["firmware_windows"] == 1 and at_full["stop_bursts"] == 1
