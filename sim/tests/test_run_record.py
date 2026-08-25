import dataclasses
import json

from sim.driver import run
from sim.run_record import JoinEventRecord, RunRecord, flow_key
from sim.scenarios import smoke_scenario
from sim.baselines.pf import ProportionalFair


def _run_record(record_timeseries=False):
    sc = smoke_scenario()
    summary = run(sc, ProportionalFair(), record_timeseries=record_timeseries)
    return RunRecord.from_summary(
        scenario_name=sc.name,
        scheduler_name="PF",
        seed=sc.seed,
        flow_configs=sc.flows,
        summary=summary,
        arm={"cqi_delay_slots": 0},
    )


def test_from_summary_joins_every_flow():
    rec = _run_record()
    assert len(rec.flows) == len(rec.flows)  # sanity: dict built
    for f in rec.flows.values():
        assert f.key == flow_key(f.ue_id, f.qfi)
    # every flow_config appears exactly once
    keys_from_config = {flow_key(f.ue_id, f.qfi) for f in _scenario_flows()}
    assert set(rec.flows.keys()) == keys_from_config


def _scenario_flows():
    return smoke_scenario().flows


def test_ue_lcp_is_not_carried_into_the_record():
    rec = _run_record()
    assert "_ue_lcp" not in rec.meta
    assert not hasattr(rec, "_ue_lcp")


def test_timeseries_absent_by_default():
    rec = _run_record(record_timeseries=False)
    assert not rec.has_timeseries()
    for f in rec.flows.values():
        assert not f.has_timeseries()


def test_timeseries_present_when_requested():
    rec = _run_record(record_timeseries=True)
    assert rec.has_timeseries()
    for f in rec.flows.values():
        assert f.has_timeseries()
        assert len(f.ts_hol_delay_s) == len(rec.timeseries_time_s)


def test_gfbr_fraction_none_for_non_gbr():
    rec = _run_record()
    non_gbr = [f for f in rec.flows.values() if f.flow_class != "GBR"]
    for f in non_gbr:
        assert f.gfbr_fraction() is None
        assert f.meets_gbr_contract() is None


def test_roundtrip_to_dict_and_back():
    rec = _run_record(record_timeseries=True)
    d = rec.to_dict()
    json.dumps(d)  # must be plain-JSON-serialisable
    rec2 = RunRecord.from_dict(d)
    assert rec2.scenario_name == rec.scenario_name
    assert set(rec2.flows.keys()) == set(rec.flows.keys())
    for k in rec.flows:
        assert rec2.flows[k] == rec.flows[k]
    assert rec2.system == rec.system
    assert rec2.timeseries_time_s == rec.timeseries_time_s


def test_flows_by_filters_correctly():
    rec = _run_record()
    gbr = rec.flows_by(flow_class="GBR")
    assert all(f.flow_class == "GBR" for f in gbr)
    assert len(gbr) + len(rec.flows_by(flow_class="Delay")) + len(
        rec.flows_by(flow_class="PF")
    ) == len(rec.flows)


# -- WP-Join commit 4: join_events (docs/wp-join-plan.md sec5) --------------


def test_join_events_is_a_real_empty_list_from_a_live_wpjoin_commit5_run():
    """Finding, not a fixture to quietly adjust (WP-Join commit 5 review
    point 1): this test originally asserted a real driver.run() produced
    join_events=None, written against the pre-commit-5 driver. Commit 5's
    driver.py now sets summary["join_events"] unconditionally (possibly
    empty) on every run, whether or not any UE opts into UEConfig.join --
    so a live run's own RunRecord is never None any more. None is now
    reserved for a record that lacks the "join_events" key entirely (a
    stored pre-commit-5 baseline, or a hand-built dict/RunRecord that
    omits it) -- see the sibling test below."""
    rec = _run_record()
    assert rec.join_events == []
    d = rec.to_dict()
    assert d["join_events"] == []
    assert RunRecord.from_dict(d).join_events == []


def test_join_events_is_none_only_when_the_key_is_absent_entirely():
    """The pre-commit-5 case: a summary dict (or a stored RunRecord.to_dict()
    snapshot) that never had "join_events" at all -- distinct from a
    live run's real (possibly empty) list above."""
    rec = _run_record()
    d = rec.to_dict()
    del d["join_events"]
    assert RunRecord.from_dict(d).join_events is None


def test_join_events_empty_list_round_trips_as_a_real_empty_list_not_none():
    rec = dataclasses.replace(_run_record(), join_events=[])
    d = rec.to_dict()
    assert d["join_events"] == []  # a real "zero events", distinct from None ("predates WP-Join")
    assert RunRecord.from_dict(d).join_events == []


def test_join_events_roundtrip_to_dict_and_back():
    events = [
        JoinEventRecord(
            ue_id=1, path="reestablish", trigger_slot=100, trigger_ts_s=0.05,
            rf_restore_slot=6100, rf_restore_ts_s=3.05, attached_slot=6500, attached_ts_s=3.25,
            phases={"reestablish": 200.0}, timer_expiries={}, rlf_declared_at_slot=100,
            handshake_rtt_ms=12.5,
        ),
    ]
    rec = dataclasses.replace(_run_record(), join_events=events)
    d = rec.to_dict()
    json.dumps(d)  # must stay plain-JSON-serialisable with the new field
    rec2 = RunRecord.from_dict(d)
    assert rec2.join_events == events
