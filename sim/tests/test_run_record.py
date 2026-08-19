import json

from sim.driver import run
from sim.run_record import RunRecord, flow_key
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
        arm={"ul_bsr_delay_slots": 0},
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
