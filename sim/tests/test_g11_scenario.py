"""GT-7.1's soak scenario, and the expected-count assertions that guard it.

WP9 G11 commit 5. Scenario construction only.

The schedule is COMPRESSED here (firmware at T+10s, STOP at T+20s) so the
mechanism is testable in seconds. The real soak's schedule is the module's
defaults; what these tests pin is that the ingredients fire AS OFTEN AS THE
SCHEDULE SAYS, which is G9 §34.5's lesson and the reason the assertions
compare at equality rather than checking non-zero.
"""

from __future__ import annotations

import pytest

from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.run_record import RunRecord
from sim.scenarios.g11 import (
    SLOT_S, SOAK_HORIZON_SLOTS, FirmwareWindow, StopDrill, TeleopDuty,
    WaypointPauses, assert_schedule_fired, build_g11_scenario,
    expected_counts, scripted_windows,
)

# 40 s, with the whole shift's structure compressed into it
H = 160_000
FAST = dict(teleop=TeleopDuty(period_s=5.0, on_s=3.0),
            pauses=WaypointPauses(first_s=8.0, period_s=12.0, pause_s=2.0),
            firmware=FirmwareWindow(start_s=10.0, duration_s=4.0),
            stop=StopDrill(at_s=20.0))


def _run(seed=1, **kw):
    sc = build_g11_scenario(seed=seed, horizon_slots=H, **{**FAST, **kw})
    summary = run(sc, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=True,
                  timeseries_resolution="second")
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})
    return sc, rec


def test_the_soak_horizon_is_thirty_minutes():
    assert SOAK_HORIZON_SLOTS * SLOT_S == 1800.0
    assert SOAK_HORIZON_SLOTS == 7_200_000


def test_no_two_flows_share_a_ue_qfi_pair():
    """flow_key has NO DIRECTION TERM (wp9-plan §5): a DL and a UL flow on
    the same (ue, 5QI) collide and one silently vanishes from every metric.
    The first version of this scenario put the firmware push on DL 5QI 9,
    which collided with the per-UE UL filler."""
    sc = build_g11_scenario(seed=1, horizon_slots=SOAK_HORIZON_SLOTS)
    keys = [(f.ue_id, f.qfi) for f in sc.flows]
    assert len(keys) == len(set(keys)), \
        f"colliding (ue, qfi) pairs: {[k for k in keys if keys.count(k) > 1]}"


def test_expected_counts_are_clipped_to_the_horizon():
    """An 'expected' count for an event the run cannot contain would turn a
    correct short run into a failure, and would make the assertion look like
    it checked something when it checked a constant."""
    short = expected_counts(160_000, **FAST)
    assert short["firmware_windows"] == 1 and short["stop_bursts"] == 1
    tiny = expected_counts(4_000, **FAST)          # 1.0 s: nothing scheduled yet
    assert tiny["firmware_windows"] == 0 and tiny["stop_bursts"] == 0


def test_every_scripted_ingredient_fires_and_the_stop_is_DELIVERED():
    sc, rec = _run()
    got = assert_schedule_fired(rec, H, "smoke", **FAST)
    assert got["teleop_on_windows"] == 8         # 40 s / 5 s
    assert got["waypoint_pauses"] == 3           # 8, 20, 32 s
    assert got["firmware_windows"] == 1
    assert got["stop_bursts"] == 1
    assert got["stop_bytes_arrived"] == StopDrill().burst_bytes, \
        "the STOP fired more than once -- its window is wider than one period"
    assert got["firmware_bytes_arrived"] > 0


def test_the_stop_drill_is_absent_before_its_instant_and_present_after():
    _, early = _run(stop=StopDrill(at_s=39.9))
    _, late = _run(stop=StopDrill(at_s=5.0))
    k = "ue2_qfi85"
    assert early.flows[k].bytes_arrived == StopDrill().burst_bytes
    assert late.flows[k].bytes_arrived == StopDrill().burst_bytes


def test_a_missing_stop_is_an_assertion_failure_not_a_silent_pass():
    """The guard must be able to fail -- CLAUDE.md's could-have-failed rule
    applied to this module's own assertion."""
    _, rec = _run()
    doomed = type(rec.flows["ue2_qfi85"])
    rec.flows["ue2_qfi85"] = doomed(**{**vars(rec.flows["ue2_qfi85"]),
                                       "bytes_delivered": 0})
    with pytest.raises(AssertionError, match="DELIVERED NONE"):
        assert_schedule_fired(rec, H, "doomed", **FAST)


def test_scripted_windows_partitions_the_run_for_E1_and_E5():
    w = scripted_windows(40.0, **FAST)
    assert set(w) == {"teleop_off", "pause", "firmware", "stop"}
    assert w["firmware"] == ((10.0, 14.0),)
    assert w["stop"] == ((20.0, 20.02),)
    assert len(w["pause"]) == 3


def test_permutation_reorders_without_changing_the_flow_set():
    a = build_g11_scenario(seed=1, horizon_slots=H, permutation=0, **FAST)
    b = build_g11_scenario(seed=1, horizon_slots=H, permutation=5, **FAST)
    key = lambda sc: sorted((f.ue_id, f.qfi, f.direction) for f in sc.flows)
    assert key(a) == key(b)
    assert [ (f.ue_id, f.qfi) for f in a.flows ] != [ (f.ue_id, f.qfi) for f in b.flows ]
