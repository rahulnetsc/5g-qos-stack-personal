"""M20 -- the protected-fleet companion to M03 (WP9 Step 2).

THE DEFECT THIS PINS. `Scorecard._m03_liveness_gap_distribution` runs its
worst-gap contest over EVERY flow in the record (sim/scorecard.py:220) and
its docstring/panel note say so: "computed generically over any flow's
completions". That is correct for M03 and must not change -- editing it
would silently re-interpret every historical reading.

But G6 binds it to a question M03's domain does not match: *background
traffic can never impair THE FLEET*. Measured, the aggressor flow's own
starvation won M03's contest on the seeds that produced G6's headline
failure, so the guarantee was scored on the background traffic's own
service (docs/wp9-plan.md §24.2).

So the fix is a SEPARATE statistic with the fleet restriction built in, and
this test asserts exactly the discriminating case: a record where one
non-protected flow blows the maximum while every protected flow is clean.
M03 must still report the aggressor (unchanged semantics); the new
statistic must ignore it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.run_record import RunRecord  # noqa: E402
from sim.scorecard import Scorecard  # noqa: E402


def _flow(ue_id, qfi, gaps_s, flow_class="Delay", direction="UL"):
    """A flow whose completion timestamps produce exactly `gaps_s`.

    `ue_id` is explicit because `FlowRecord.key` is DERIVED from
    (ue_id, qfi) -- the dict key a caller writes is not what the scorecard
    reports, and hardcoding ue_id=1 while keying the dict "ue8_qfi8" makes
    the fixture silently describe a different flow than it names.
    """
    ts, t = [], 0.0
    for g in [0.0] + list(gaps_s):
        t += g
        ts.append(t)
    return {
        "ue_id": ue_id, "qfi": qfi, "direction": direction, "flow_class": flow_class,
        "priority_level": 100, "pdb_ms": 100.0, "gfbr_bps": 0.0,
        "bytes_arrived": 10, "bytes_delivered": 10, "bytes_dropped_pdb": 0,
        "bytes_delivered_late_pdb": 0, "bytes_harq_lost": 0,
        "delivery_ratio": 1.0, "throughput_bps": 1.0, "offered_bps": 1.0,
        "delay_p50_ms": 1.0, "delay_p95_ms": 1.0, "delay_p98_ms": 1.0,
        "delay_p99_ms": 1.0, "delay_p50_ms_proxy": 1.0, "delay_p95_ms_proxy": 1.0,
        "delay_p98_ms_proxy": 1.0, "delay_p99_ms_proxy": 1.0,
        "survival_time_ms": 0.0, "message_count": len(ts),
        "completion_ts_by_role_s": {"data": ts},
    }


def _record(flows):
    return RunRecord.from_dict({
        "schema_version": 1, "scenario_name": "toy", "scheduler_name": "TwoTier",
        "seed": 1, "arm": {}, "meta": {}, "flows": flows,
        "system": {"horizon_s": 10.0, "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0},
        "join_events": [], "timeseries_time_s": None, "timeseries_slot_index": None,
    })


# The discriminating record: fleet telemetry clean at 0.10 s gaps, the
# best-effort aggressor starved to a 2.3 s gap -- the real shape measured on
# seed 1440696407 (§24.2), where fleet flows sat at 0.117-0.352 s and
# ue8_qfi8 at 2.2775 s.
AGGRESSOR_RECORD = _record({
    "ue1_qfi1": _flow(1, 1, [0.10, 0.10, 0.10]),
    "ue2_qfi1": _flow(2, 1, [0.10, 0.11, 0.10]),
    "ue8_qfi8": _flow(8, 8, [0.10, 2.30, 0.10], flow_class="PF"),
})


def test_m03_still_reports_the_aggressor_semantics_unchanged():
    """M03 must NOT change. Its domain is every flow, by definition, and a
    historical reading has to keep meaning what it meant."""
    res = Scorecard().score(AGGRESSOR_RECORD)["M03"]
    assert res.value["flow"] == "ue8_qfi8"
    assert abs(res.value["max_gap_ms"] - 2300.0) < 1e-6


def test_protected_fleet_statistic_ignores_the_aggressor():
    """THE GUARD. Fails against current code: no such statistic exists."""
    res = Scorecard().protected_fleet_liveness_gap(AGGRESSOR_RECORD)
    assert res.value["flow"] in ("ue1_qfi1", "ue2_qfi1"), \
        "the protected-fleet statistic must not score a non-protected flow"
    assert abs(res.value["max_gap_ms"] - 110.0) < 1e-6, \
        "must report the worst PROTECTED gap (0.11 s), not the aggressor's 2.3 s"


def test_protected_fleet_statistic_excludes_best_effort_too():
    """qfi 9 is the per-UE best-effort filler -- fleet-generated, but not a
    protected G1/G3/G5 bearer. §25.2 measured it carrying a further 10-17%
    of the excess after the aggressor is removed."""
    rec = _record({
        "ue1_qfi1": _flow(1, 1, [0.10, 0.10]),
        "ue3_qfi9": _flow(3, 9, [0.10, 1.50], flow_class="PF"),
    })
    res = Scorecard().protected_fleet_liveness_gap(rec)
    assert res.value["flow"] == "ue1_qfi1"
    assert abs(res.value["max_gap_ms"] - 100.0) < 1e-6


def test_robust_summary_reports_median_and_spread_not_a_bare_mean():
    """The estimator half. A mean of ratios over a MAX statistic is not a
    robust summary of them: the real G6 cell had mean +136.84% while the
    median was -0.22% and 21/40 seeds improved (§24.3)."""
    deltas = [-0.02, -0.01, 0.0, 0.01, 0.02, 21.0]   # one extreme, five flat
    summ = Scorecard.robust_delta_summary(deltas)
    assert abs(summ["median"]) <= 0.01, "median must resist the outlier"
    assert summ["mean"] > 3.0, "the mean is reported too, and is not robust"
    assert summ["n"] == 6
    assert summ["p25"] <= summ["median"] <= summ["p75"]
    assert summ["frac_worse"] == 3 / 6


# -- Step 4: the cadence caveat, derived from the record ------------------

def test_m03_flags_cadence_when_the_flow_is_slower_than_the_bound():
    """At duty_cycle 0.1 the telemetry source's configured period is 1000 ms
    against a 500 ms (T_live/4) bound, so every seed 'breaches' with nothing
    failing (docs/wp9-plan.md §24.6). The caveat is derived from the flow's
    OWN median gap, so it fires for any slow flow from any producer."""
    rec = _record({"ue1_qfi1": _flow(1, 1, [1.00, 1.00, 1.05])})
    res = Scorecard().score(rec)["M03"]
    assert res.value["median_gap_ms"] == 1000.0
    assert any("CADENCE, NOT LIVENESS" in c for c in res.caveats), res.caveats


def test_m03_does_not_flag_cadence_for_a_normal_flow():
    rec = _record({"ue1_qfi1": _flow(1, 1, [0.10, 0.10, 0.60])})
    res = Scorecard().score(rec)["M03"]
    assert abs(res.value["max_gap_ms"] - 600.0) < 1e-6, "a real gap above the bound"
    assert res.value["median_gap_ms"] == 100.0
    assert not any("CADENCE" in c for c in res.caveats), \
        "a fast flow with one long gap is a real liveness event, not cadence"


def test_panel_caveats_and_data_caveats_both_travel():
    """The panel loop used to ASSIGN caveats, discarding any a metric method
    had attached from the run's own data."""
    rec = _record({"ue1_qfi1": _flow(1, 1, [1.00, 1.00])})
    results = Scorecard().score(rec)
    assert any("CADENCE" in c for c in results["M03"].caveats)
    assert results["M01"].caveats, "M01's registered panel caveat must survive"
