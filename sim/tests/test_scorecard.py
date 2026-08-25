import dataclasses

import pytest

from sim.driver import run
from sim.run_record import FlowRecord, JoinEventRecord, RunRecord, SystemRecord
from sim.scorecard import Scorecard, load_panel
from sim.scenarios import smoke_scenario, factory_robots_scenario
from sim.baselines.pf import ProportionalFair


PANEL_IDS = [m["id"] for m in load_panel()["metrics"]]


def _flow_record(key_suffix: str, *, message_count, delay_p50=0.0, delay_p99=0.0,
                  proxy_p50=0.0, proxy_p99=0.0, **overrides) -> FlowRecord:
    """Minimal FlowRecord for scorecard-logic tests that don't need a real
    driver.run() -- WP7's M01/M15 true-latency edge cases are about
    scorecard.py's own selection logic, not traffic generation."""
    ue_id, qfi = 1, int(key_suffix)
    defaults = dict(
        ue_id=ue_id, qfi=qfi, direction="UL", flow_class="PF",
        gfbr_bps=0.0, pdb_ms=100.0, priority_level=100,
        bytes_arrived=0, bytes_delivered=0, bytes_dropped_pdb=0,
        bytes_delivered_late_pdb=0, throughput_bps=0.0, offered_bps=0.0,
        delivery_ratio=0.0,
        delay_p50_ms_proxy=proxy_p50, delay_p95_ms_proxy=proxy_p50,
        delay_p99_ms_proxy=proxy_p99, delay_p98_ms_proxy=proxy_p99,
        delay_p50_ms=delay_p50, delay_p95_ms=delay_p50,
        delay_p98_ms=delay_p99, delay_p99_ms=delay_p99,
        message_count=message_count,
    )
    defaults.update(overrides)
    return FlowRecord(**defaults)


def _run_record(flows: list[FlowRecord], *, timeseries_time_s=None, join_events=None) -> RunRecord:
    return RunRecord(
        schema_version=1, scenario_name="synthetic", scheduler_name="X", seed=0,
        arm={}, flows={f.key: f for f in flows},
        system=SystemRecord(horizon_s=1.0, dl_prb_utilization=0.0,
                             ul_prb_utilization=0.0, cce_utilization=0.0),
        timeseries_time_s=timeseries_time_s,
        join_events=join_events,
    )


def _record(scenario_fn=smoke_scenario, record_timeseries=False, **run_kwargs):
    sc = scenario_fn()
    summary = run(sc, ProportionalFair(), record_timeseries=record_timeseries, **run_kwargs)
    return RunRecord.from_summary(
        scenario_name=sc.name,
        scheduler_name="PF",
        seed=sc.seed,
        flow_configs=sc.flows,
        summary=summary,
    ), sc


def test_panel_loads_and_has_nineteen_metrics():
    """M18/M19 (WP-Join commit 4, docs/wp-join-plan.md sec5) are the
    panel's first additions since WP0's original 17."""
    panel = load_panel()
    assert len(panel["metrics"]) == 19
    ids = [m["id"] for m in panel["metrics"]]
    assert len(ids) == len(set(ids)), "duplicate metric ids in the panel"


def test_caveats_travel_with_the_value_for_registered_metrics_only():
    """docs/wp5-plan.md Decision 6: a caveat is additive metadata on
    MetricResult, not a status change -- M01/M02/M14/M15 are HARQ-blind
    (registered in config/metric_panel.yml) and must carry that caveat
    regardless of status; every other metric must get an empty list, not
    an omitted attribute (same "never silently omit" discipline as a
    pending row). M19 also carries its own registered caveat since
    WP-Join commit 8 (the hol-delay-vs-continuous-PDB-drops finding)."""
    rec, _ = _record()
    sc = Scorecard()
    results = sc.score(rec)
    for mid in ("M01", "M02", "M14", "M15", "M19"):
        assert results[mid].caveats, f"{mid} should carry its registered caveat"
        assert all(isinstance(c, str) and c for c in results[mid].caveats)
    for mid, res in results.items():
        if mid not in ("M01", "M02", "M14", "M15", "M19"):
            assert res.caveats == []


def test_score_emits_every_scoreable_metric_row():
    rec, _ = _record()
    sc = Scorecard()
    results = sc.score(rec)
    # M13 and M16 need extra args and are called separately -- not part of
    # the automatic per-run scan.
    expected = set(PANEL_IDS) - {"M13", "M16"}
    assert set(results.keys()) == expected
    for mid, res in results.items():
        assert res.status in ("ok", "proxy", "pending")
        if res.status == "pending":
            assert res.value is None
            assert res.note  # a pending row must say why


def test_pending_metrics_are_pending_without_timeseries():
    rec, _ = _record(record_timeseries=False)
    sc = Scorecard()
    results = sc.score(rec)
    for mid in ("M04", "M09"):
        assert results[mid].status == "pending"
        assert results[mid].value is None


def test_proxy_metrics_populate_with_timeseries():
    rec, _ = _record(record_timeseries=True)
    sc = Scorecard()
    results = sc.score(rec)
    assert results["M04"].status == "proxy"
    assert results["M04"].value is not None
    assert results["M09"].status in ("proxy",)
    # per-second Jain needs >=2 flows -- smoke_scenario should have that
    assert results["M09"].value is not None


def test_m07_and_m08_gbr_metrics_are_internally_consistent():
    rec, sc_cfg = _record(scenario_fn=factory_robots_scenario)
    sc = Scorecard()
    results = sc.score(rec)
    gbr_flows = rec.flows_by(flow_class="GBR")
    if not gbr_flows:
        pytest.skip("factory_robots_scenario has no GBR flows in this config")
    m07 = results["M07"].value
    assert m07["total"] == len(gbr_flows)
    assert 0 <= m07["met"] <= m07["total"]
    m08 = results["M08"].value
    assert m08["flow"] in {f.key for f in gbr_flows}
    # worst flow's fraction should be <= every other GBR flow's fraction
    fractions = [f.gfbr_fraction() for f in gbr_flows if f.gfbr_fraction() is not None]
    assert abs(m08["fraction"] - min(fractions)) < 1e-9


def test_m11_and_m12_match_system_record_exactly():
    rec, _ = _record()
    sc = Scorecard()
    results = sc.score(rec)
    assert results["M11"].value == {
        "dl": rec.system.dl_prb_utilization,
        "ul": rec.system.ul_prb_utilization,
    }
    assert results["M12"].value == rec.system.cce_utilization


def test_m02_pdb_violation_rate_matches_hand_computation():
    """Denominator is RESOLVED bytes (delivered + dropped), not
    bytes_arrived -- see test_m02_excludes_bytes_still_queued_at_horizon_end
    for why bytes_arrived would be wrong."""
    rec, _ = _record()
    sc = Scorecard()
    results = sc.score(rec)
    total_delivered = sum(f.bytes_delivered for f in rec.flows.values())
    total_dropped = sum(f.bytes_dropped_pdb for f in rec.flows.values())
    total_late = sum(f.bytes_delivered_late_pdb for f in rec.flows.values())
    total_resolved = total_delivered + total_dropped
    expected = (total_dropped + total_late) / total_resolved if total_resolved else 0.0
    assert abs(results["M02"].value - expected) < 1e-9
    assert results["M02"].status == "ok"


def test_m02_excludes_bytes_still_queued_at_horizon_end():
    """A short horizon relative to offered load leaves most arrived bytes
    still queued (neither delivered, dropped, nor late) when the run ends.
    Those bytes must NOT inflate M02's denominator -- smoke_scenario()
    (used above) drains close to fully and can't catch this; a short
    horizon on a heavily-loaded scenario can. Confirmed empirically: at
    horizon_slots=200 on factory_robots_scenario/PF, ~19% of arrived bytes
    are unresolved, and the bytes_arrived-denominator rate (0.58) differs
    materially from the resolved-bytes rate (0.72)."""
    sc = dataclasses.replace(factory_robots_scenario(), horizon_slots=200)
    summary = run(sc, ProportionalFair())
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=sc.seed,
        flow_configs=sc.flows, summary=summary,
    )
    total_arrived = sum(f.bytes_arrived for f in rec.flows.values())
    total_delivered = sum(f.bytes_delivered for f in rec.flows.values())
    total_dropped = sum(f.bytes_dropped_pdb for f in rec.flows.values())
    total_late = sum(f.bytes_delivered_late_pdb for f in rec.flows.values())
    still_queued = total_arrived - total_delivered - total_dropped

    # Test-setup invariant: this scenario/horizon must actually leave a
    # meaningful chunk unresolved, or this test isn't exercising the bug.
    assert still_queued / total_arrived > 0.1, (
        "test setup invariant broken: expected a substantial unresolved "
        f"fraction, got {still_queued}/{total_arrived}"
    )

    results = Scorecard().score(rec)
    resolved_rate = (total_dropped + total_late) / (total_delivered + total_dropped)
    wrong_rate_against_arrived = (total_dropped + total_late) / total_arrived
    assert abs(results["M02"].value - resolved_rate) < 1e-9
    assert results["M02"].value != pytest.approx(wrong_rate_against_arrived)
    assert "still queued" in results["M02"].note


def test_m01_flips_to_ok_and_uses_true_latency_when_every_flow_has_it():
    rec = _run_record([_flow_record("1", message_count=50, delay_p50=2.0, delay_p99=9.0)])
    res = Scorecard().score(rec)["M01"]
    assert res.status == "ok"
    assert res.value["p99"] == 9.0


def test_m01_falls_back_to_proxy_for_a_pre_wp7_record():
    rec = _run_record([_flow_record("1", message_count=None, proxy_p50=2.0, proxy_p99=9.0)])
    res = Scorecard().score(rec)["M01"]
    assert res.status == "proxy"
    assert res.value["p99"] == 9.0


def test_m01_excludes_a_chronically_stalled_flow_from_worst():
    """A flow that never fully delivered a message (message_count=0) must
    not win the 'worst' contest by reporting a 0ms latency -- that would
    silently rank the most-broken flow as the best one. See scorecard.py's
    _m01_latency_percentiles."""
    stalled = _flow_record("1", message_count=0, delay_p50=0.0, delay_p99=0.0)
    healthy = _flow_record("2", message_count=10, delay_p50=3.0, delay_p99=7.0)
    rec = _run_record([stalled, healthy])
    res = Scorecard().score(rec)["M01"]
    assert res.status == "ok"
    assert res.value["flow"] == healthy.key
    assert res.value["p99"] == 7.0
    assert "excluded" in res.note


def test_m01_notes_when_every_flow_is_stalled():
    stalled = _flow_record("1", message_count=0)
    rec = _run_record([stalled])
    res = Scorecard().score(rec)["M01"]
    assert res.status == "ok"
    assert res.value["flow"] is None
    assert "excluded" in res.note


def test_m15_excludes_a_chronically_stalled_flow_from_worst():
    stalled = _flow_record("1", message_count=0, delay_p50=0.0, delay_p99=0.0)
    healthy = _flow_record("2", message_count=10, delay_p50=1.0, delay_p99=6.0)
    rec = _run_record([stalled, healthy])
    res = Scorecard().score(rec)["M15"]
    assert res.status == "ok"
    assert res.value["flow"] == healthy.key
    assert res.value["jitter_ms"] == pytest.approx(5.0)


def test_m03_is_pending_for_a_pre_wp7_commit4_record():
    """completion_ts_by_role_s defaults to None (via _flow_record's
    defaults, which don't set it) -- the same never-None-post-commit-4
    convention message_count uses for M01."""
    rec = _run_record([_flow_record("1", message_count=10)])
    res = Scorecard().score(rec)["M03"]
    assert res.status == "pending"
    assert res.value is None


def test_m03_computes_max_gap_and_reports_the_t_live_it_used():
    fr = _flow_record("1", message_count=3,
                       completion_ts_by_role_s={"data": [0.0, 1.0, 3.0]})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M03"]  # default t_live_s = 2.0 (panel)
    assert res.status == "ok"
    assert res.value["flow"] == fr.key
    assert res.value["role"] == "data"
    assert res.value["max_gap_ms"] == pytest.approx(2000.0)
    assert res.value["t_live_s"] == pytest.approx(2.0)
    assert res.value["gap_count_over_t_live_over_4"] == 2  # gaps 1.0,2.0 > 0.5
    assert res.value["gap_count_over_t_live_over_2"] == 1  # only 2.0 > 1.0
    assert res.value["gap_count_over_t_live"] == 0         # neither > 2.0


def test_m03_respects_a_t_live_s_override():
    fr = _flow_record("1", message_count=3,
                       completion_ts_by_role_s={"data": [0.0, 1.0, 3.0]})
    rec = _run_record([fr])
    res = Scorecard().score(rec, t_live_s=0.5)["M03"]
    assert res.value["t_live_s"] == pytest.approx(0.5)
    assert res.value["gap_count_over_t_live"] == 2  # both gaps (1.0, 2.0) > 0.5


def test_m03_excludes_a_role_with_fewer_than_two_completions_from_worst():
    """A role that only ever completed once has no inter-arrival gap --
    excluding it (not scoring gap=0) matters for the same reason M01
    excludes zero-message flows: silence must not look like the best case.
    """
    silent = _flow_record("1", message_count=1,
                           completion_ts_by_role_s={"heartbeat": [0.0]})
    noisy = _flow_record("2", message_count=5,
                          completion_ts_by_role_s={"telemetry": [0.0, 0.05, 5.0]})
    rec = _run_record([silent, noisy])
    res = Scorecard().score(rec)["M03"]
    assert res.status == "ok"
    assert res.value["flow"] == noisy.key
    assert res.value["role"] == "telemetry"
    assert "1:heartbeat" in res.note


def test_m03_selects_the_worst_role_within_one_multi_role_flow():
    """MAVLink-style: one flow, several roles -- the worst (largest) gap
    across roles wins, not just the first role seen."""
    fr = _flow_record("1", message_count=6, completion_ts_by_role_s={
        "heartbeat": [0.0, 1.0, 2.0],   # max gap 1.0s
        "telemetry": [0.0, 0.1, 4.0],   # max gap 3.9s
    })
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M03"]
    assert res.value["role"] == "telemetry"
    assert res.value["max_gap_ms"] == pytest.approx(3900.0)


def test_m05_is_pending_for_a_pre_wp7_commit6_record():
    rec = _run_record([_flow_record("1", message_count=10)])  # frame_completions defaults None
    res = Scorecard().score(rec)["M05"]
    assert res.status == "pending"
    assert res.value is None


def test_m06_is_pending_for_a_pre_wp7_commit6_record():
    rec = _run_record([_flow_record("1", message_count=10)])
    res = Scorecard().score(rec)["M06"]
    assert res.status == "pending"
    assert res.value is None


def test_m05_excludes_flows_that_never_used_xr_video():
    non_xr = _flow_record("1", message_count=10, frame_completions={"total": 0, "complete_ages_ms": []})
    xr = _flow_record("2", message_count=10, pdb_ms=50.0,
                       frame_completions={"total": 4, "complete_ages_ms": [10.0, 20.0, 60.0, 70.0]})
    rec = _run_record([non_xr, xr])
    res = Scorecard().score(rec)["M05"]
    assert res.status == "ok"
    assert res.value["flow"] == xr.key
    assert res.value["frame_count"] == 4
    assert res.value["fraction"] == pytest.approx(0.5)  # 2 of 4 ages <= 50ms pdb
    # pdb_ms must travel with the fraction -- it varies per flow, so the
    # number alone doesn't say what it was measured against (found in
    # WP7's end-of-WP review).
    assert res.value["pdb_ms"] == pytest.approx(50.0)


def test_m05_scores_a_dropped_frame_as_failed_even_though_it_is_fast():
    """A partial frame isn't in complete_ages_ms at all -- it must still
    count against the denominator (total), per M05's own 'partial delivery
    counts as failed' definition."""
    fr = _flow_record("1", message_count=10, pdb_ms=1000.0,
                       frame_completions={"total": 3, "complete_ages_ms": [1.0, 2.0]})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M05"]
    assert res.value["fraction"] == pytest.approx(2 / 3)  # 1 of 3 frames never completed


def test_m05_worst_flow_is_the_lowest_completeness_fraction():
    better = _flow_record("1", message_count=10, pdb_ms=100.0,
                           frame_completions={"total": 2, "complete_ages_ms": [10.0, 20.0]})
    worse = _flow_record("2", message_count=10, pdb_ms=100.0,
                          frame_completions={"total": 2, "complete_ages_ms": [10.0]})
    rec = _run_record([better, worse])
    res = Scorecard().score(rec)["M05"]
    assert res.value["flow"] == worse.key
    assert res.value["fraction"] == pytest.approx(0.5)


def test_m06_excludes_a_flow_that_generated_frames_but_completed_none():
    silent = _flow_record("1", message_count=1,
                           frame_completions={"total": 2, "complete_ages_ms": []})
    healthy = _flow_record("2", message_count=10,
                            frame_completions={"total": 3, "complete_ages_ms": [5.0, 6.0, 100.0]})
    rec = _run_record([silent, healthy])
    res = Scorecard().score(rec)["M06"]
    assert res.status == "ok"
    assert res.value["flow"] == healthy.key
    assert silent.key in res.note  # excluded flow is named, not silently dropped


def test_m06_reports_p95_of_the_worst_flow():
    fr = _flow_record("1", message_count=10,
                       frame_completions={"total": 10, "complete_ages_ms": list(range(1, 11))})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M06"]
    assert res.status == "ok"
    assert res.value["flow"] == fr.key
    assert res.value["p95_ms"] == pytest.approx(10)  # k = min(9, int(10*0.95)) = 9 -> s[9] = 10


def test_m17_is_pending_for_a_pre_wp7_commit7_record():
    """frame_completions in the commit-6 shape (no complete_ts_s key) must
    still report pending, not silently treat the missing key as an empty
    gap array -- see _has_frame_gap_data vs _has_frame_data."""
    fr = _flow_record("1", message_count=10,
                       frame_completions={"total": 3, "complete_ages_ms": [1.0, 2.0, 3.0]})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M17"]
    assert res.status == "pending"
    assert res.value is None


def test_m17_excludes_flows_that_never_used_xr_video():
    non_xr = _flow_record("1", message_count=10,
                           frame_completions={"total": 0, "complete_ages_ms": [], "complete_ts_s": []})
    rec = _run_record([non_xr])
    res = Scorecard().score(rec)["M17"]
    assert res.status == "ok"
    assert res.value is None


def test_m17_detects_a_freeze_when_a_gap_exceeds_2x_the_nominal_interval():
    # period_ms=20 -> nominal interval 0.02s, freeze threshold 0.04s.
    fr = _flow_record("1", message_count=10, xr_frame_period_ms=20.0,
                       frame_completions={"total": 4, "complete_ages_ms": [1, 1, 1, 1],
                                          "complete_ts_s": [0.0, 0.02, 0.04, 0.09]})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M17"]
    assert res.status == "ok"
    assert res.value["freeze_count"] == 1  # only the 0.04->0.09 gap (0.05s) exceeds 0.04s
    assert res.value["freeze_total_duration_ms"] == pytest.approx(50.0)
    assert res.value["freeze_max_duration_ms"] == pytest.approx(50.0)


def test_m17_no_freeze_when_all_gaps_are_within_2x_the_nominal_interval():
    fr = _flow_record("1", message_count=10, xr_frame_period_ms=20.0,
                       frame_completions={"total": 3, "complete_ages_ms": [1, 1, 1],
                                          "complete_ts_s": [0.0, 0.02, 0.04]})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M17"]
    assert res.value["freeze_count"] == 0
    assert res.value["freeze_total_duration_ms"] == pytest.approx(0.0)


def test_m17_reports_effective_and_source_fps():
    fr = _flow_record("1", message_count=10, xr_frame_period_ms=20.0,  # source fps = 50
                       frame_completions={"total": 4, "complete_ages_ms": [1, 1, 1, 1],
                                          "complete_ts_s": [0.0, 0.02, 0.04, 0.09]})
    rec = _run_record([fr])  # _run_record's SystemRecord uses horizon_s=1.0
    res = Scorecard().score(rec)["M17"]
    assert res.value["source_fps"] == pytest.approx(50.0)
    assert res.value["effective_fps"] == pytest.approx(4.0)  # 4 complete frames / 1.0s horizon
    # Labelled explicitly rather than left as an inversion of source_fps
    # (found in WP7's end-of-WP review) -- this is what freeze_count was
    # actually measured against.
    assert res.value["xr_frame_period_ms"] == pytest.approx(20.0)


def test_m17_excludes_a_flow_with_fewer_than_two_complete_frames():
    silent = _flow_record("1", message_count=1, xr_frame_period_ms=20.0,
                           frame_completions={"total": 3, "complete_ages_ms": [1],
                                              "complete_ts_s": [0.0]})
    healthy = _flow_record("2", message_count=10, xr_frame_period_ms=20.0,
                            frame_completions={"total": 3, "complete_ages_ms": [1, 1, 1],
                                               "complete_ts_s": [0.0, 0.02, 0.04]})
    rec = _run_record([silent, healthy])
    res = Scorecard().score(rec)["M17"]
    assert res.status == "ok"
    assert res.value["flow"] == healthy.key
    assert silent.key in res.note


def test_m17_worst_flow_has_the_most_freeze_events():
    calm = _flow_record("1", message_count=10, xr_frame_period_ms=20.0,
                         frame_completions={"total": 3, "complete_ages_ms": [1, 1, 1],
                                            "complete_ts_s": [0.0, 0.02, 0.04]})
    freezy = _flow_record("2", message_count=10, xr_frame_period_ms=20.0,
                           frame_completions={"total": 4, "complete_ages_ms": [1, 1, 1, 1],
                                              "complete_ts_s": [0.0, 0.1, 0.2, 0.3]})
    rec = _run_record([calm, freezy])
    res = Scorecard().score(rec)["M17"]
    assert res.value["flow"] == freezy.key
    assert res.value["freeze_count"] == 3


def test_m14_is_pending_for_a_pre_wp7_commit4_record():
    rec = _run_record([_flow_record("1", message_count=10)])  # completion_ts_by_role_s defaults None
    res = Scorecard().score(rec)["M14"]
    assert res.status == "pending"
    assert res.value is None


def test_m14_collapses_to_within_pdb_ms_when_survival_time_is_zero():
    fr = _flow_record("1", message_count=3, pdb_ms=50.0,
                       completion_ts_by_role_s={"data": [0.0, 0.03, 0.1]})
    rec = _run_record([fr])  # survival_time_ms defaults to 0.0
    res = Scorecard().score(rec)["M14"]
    assert res.status == "ok"
    # gaps = [0.03, 0.07]s = [30, 70]ms; budget = 50+0 = 50ms -> only the
    # first gap is within budget.
    assert res.value["fraction"] == pytest.approx(0.5)
    assert res.value["survival_time_ms"] == pytest.approx(0.0)
    # pdb_ms is the other half of the threshold (pdb_ms + survival_time_ms)
    # -- must travel alongside survival_time_ms, not just the latter (found
    # in WP7's end-of-WP review).
    assert res.value["pdb_ms"] == pytest.approx(50.0)


def test_m14_survival_time_extends_the_budget():
    fr = _flow_record("1", message_count=3, pdb_ms=50.0, survival_time_ms=30.0,
                       completion_ts_by_role_s={"data": [0.0, 0.03, 0.1]})
    rec = _run_record([fr])
    res = Scorecard().score(rec)["M14"]
    # same gaps as above, but budget = 50+30 = 80ms -> both gaps qualify now.
    assert res.value["fraction"] == pytest.approx(1.0)
    assert res.value["survival_time_ms"] == pytest.approx(30.0)


def test_m14_excludes_a_role_with_fewer_than_two_completions():
    silent = _flow_record("1", message_count=1, pdb_ms=50.0,
                           completion_ts_by_role_s={"heartbeat": [0.0]})
    healthy = _flow_record("2", message_count=5, pdb_ms=50.0,
                            completion_ts_by_role_s={"telemetry": [0.0, 0.01, 0.02]})
    rec = _run_record([silent, healthy])
    res = Scorecard().score(rec)["M14"]
    assert res.status == "ok"
    assert res.value["flow"] == healthy.key
    assert "1:heartbeat" in res.note


def test_m14_worst_is_the_lowest_fraction_across_flows():
    better = _flow_record("1", message_count=3, pdb_ms=100.0,
                           completion_ts_by_role_s={"data": [0.0, 0.05, 0.1]})
    worse = _flow_record("2", message_count=3, pdb_ms=100.0,
                          completion_ts_by_role_s={"data": [0.0, 0.2, 0.4]})
    rec = _run_record([better, worse])
    res = Scorecard().score(rec)["M14"]
    assert res.value["flow"] == worse.key
    assert res.value["fraction"] == pytest.approx(0.0)  # both gaps (0.2s, 0.2s) exceed 100ms budget


def test_correlate_flows_requires_timeseries():
    rec, sc_cfg = _record(record_timeseries=False)
    sc = Scorecard()
    ul_flow = next(f for f in rec.flows.values() if f.direction == "UL")
    dl_flows = [f for f in rec.flows.values() if f.direction == "DL"]
    other = dl_flows[0] if dl_flows else ul_flow
    res = sc.correlate_flows(rec, (ul_flow.ue_id, ul_flow.qfi), (other.ue_id, other.qfi))
    assert res.status == "pending"


def test_correlate_flows_self_correlation_is_one():
    rec, _ = _record(record_timeseries=True)
    sc = Scorecard()
    f = next(iter(rec.flows.values()))
    res = sc.correlate_flows(rec, (f.ue_id, f.qfi), (f.ue_id, f.qfi))
    assert res.status == "proxy"
    assert res.value["r"] == pytest.approx(1.0, abs=1e-9)


def test_first_violation_order_over_a_load_ramp():
    sc_cfg = factory_robots_scenario()
    gbr_flows = [f for f in sc_cfg.flows if f.flow_class == "GBR"]
    if not gbr_flows:
        pytest.skip("factory_robots_scenario has no GBR flows in this config")
    class_of = {f"ue{f.ue_id}_qfi{f.qfi}": f.qfi for f in gbr_flows}

    records = []
    for mult in (1.0, 2.0, 4.0, 8.0):
        carrier = dataclasses.replace(
            sc_cfg.carrier, bandwidth_hz=int(sc_cfg.carrier.bandwidth_hz / mult)
        )
        shrunk = dataclasses.replace(sc_cfg, carrier=carrier)
        summary = run(shrunk, ProportionalFair())
        records.append(
            RunRecord.from_summary(
                scenario_name=shrunk.name, scheduler_name="PF", seed=shrunk.seed,
                flow_configs=shrunk.flows, summary=summary,
                meta={"load_mult": mult},
            )
        )
    sc = Scorecard()
    res = sc.first_violation_order(records, class_of)
    assert res.status == "ok"
    assert isinstance(res.value["order_5qi"], list)


# -- WP-Join commit 4: M18/M19 (docs/wp-join-plan.md sec5) ------------------


def test_m18_is_pending_when_join_events_predates_wpjoin():
    rec = _run_record([_flow_record("1", message_count=1)])  # join_events=None by default
    res = Scorecard().score(rec)["M18"]
    assert res.status == "pending"
    assert res.value is None
    assert "predates" in res.note


def test_m18_is_pending_when_no_join_events_occurred():
    rec = _run_record([_flow_record("1", message_count=1)], join_events=[])
    res = Scorecard().score(rec)["M18"]
    assert res.status == "pending"
    assert res.value is None


def test_m18_computes_per_path_breakdown_and_counts_never_completed():
    events = [
        JoinEventRecord(
            ue_id=1, path="cold", trigger_slot=0, trigger_ts_s=0.0,
            attached_slot=1000, attached_ts_s=0.5,
            phases={"rrc_establish": 300.0, "pdu_session": 50.0},
            timer_expiries={"rrc_establish": 1},
        ),
        JoinEventRecord(
            ue_id=2, path="reestablish", trigger_slot=2000, trigger_ts_s=1.0,
            rf_restore_slot=2400, rf_restore_ts_s=1.2,
            attached_slot=3000, attached_ts_s=1.5,
        ),
        JoinEventRecord(
            ue_id=3, path="warm", trigger_slot=4000, trigger_ts_s=2.0,
            # never completed -- attached_ts_s stays None
        ),
    ]
    rec = _run_record([_flow_record("1", message_count=1)], join_events=events)
    res = Scorecard().score(rec)["M18"]
    assert res.status == "ok"

    cold = res.value["by_path"]["cold"]
    assert cold["n_events"] == 1
    assert cold["n_never_completed"] == 0
    assert cold["p50_ms"] == pytest.approx(500.0)
    assert cold["phase_p95_ms"] == {"rrc_establish": pytest.approx(300.0), "pdu_session": pytest.approx(50.0)}
    assert cold["timer_expiry_count"] == 1
    assert "rf_restore_to_attached_p95_ms" not in cold

    reest = res.value["by_path"]["reestablish"]
    assert reest["p50_ms"] == pytest.approx(500.0)  # trigger (RLF declared) -> attached
    assert reest["rf_restore_to_attached_p95_ms"] == pytest.approx(300.0)  # RF-restore -> attached

    warm = res.value["by_path"]["warm"]
    assert warm["n_events"] == 1
    assert warm["n_never_completed"] == 1
    assert warm["p50_ms"] is None
    assert warm["max_ms"] is None


def test_m19_is_pending_when_join_events_predates_wpjoin():
    rec = _run_record([_flow_record("1", message_count=1)])
    res = Scorecard().score(rec)["M19"]
    assert res.status == "pending"


def test_m19_is_pending_without_timeseries_even_with_join_events():
    events = [JoinEventRecord(ue_id=1, path="cold", trigger_slot=0, trigger_ts_s=0.0)]
    rec = _run_record([_flow_record("1", message_count=1)], join_events=events)
    res = Scorecard().score(rec)["M19"]
    assert res.status == "pending"
    assert "record_timeseries" in res.note


def test_m19_computes_recovery_time_from_sustained_green_hol_delay():
    time_s = [round(0.1 * i, 3) for i in range(11)]  # 0.0 .. 1.0, 0.1s apart
    # Bad (over PDB) for the first 3 samples, then green for the rest --
    # pdb_ms=50 -> pdb_s=0.05.
    recovering = _flow_record(
        "1", message_count=1, pdb_ms=50.0,
        ts_hol_delay_s=[1.0, 1.0, 1.0] + [0.01] * 8,
    )
    stuck = _flow_record(
        "2", message_count=1, pdb_ms=50.0,
        ts_hol_delay_s=[1.0] * 11,  # never recovers
    )
    stuck = dataclasses.replace(stuck, ue_id=2)
    events = [
        JoinEventRecord(ue_id=1, path="cold", trigger_slot=0, trigger_ts_s=0.0),
        JoinEventRecord(ue_id=2, path="cold", trigger_slot=0, trigger_ts_s=0.0),
    ]
    rec = _run_record([recovering, stuck], timeseries_time_s=time_s, join_events=events)
    res = Scorecard().score(rec, slo_green_dwell_s=0.2)["M19"]
    assert res.status == "proxy"

    cold = res.value["by_path"]["cold"]
    assert cold["n_events"] == 2
    assert cold["n_never_recovered"] == 1  # UE 2 never sustains green for 0.2s
    # UE 1: green_since=0.3s (index 3, first slot at/under pdb_s), and
    # t=0.5s (index 5) is the first point >= 0.2s after that -- so the
    # sustained window is confirmed at t=0.3s, duration = 0.3s = 300ms.
    assert cold["p50_ms"] == pytest.approx(300.0)
