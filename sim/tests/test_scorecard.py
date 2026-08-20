import dataclasses

import pytest

from sim.driver import run
from sim.run_record import RunRecord
from sim.scorecard import Scorecard, load_panel
from sim.scenarios import smoke_scenario, factory_robots_scenario
from sim.baselines.pf import ProportionalFair


PANEL_IDS = [m["id"] for m in load_panel()["metrics"]]


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


def test_panel_loads_and_has_seventeen_metrics():
    panel = load_panel()
    assert len(panel["metrics"]) == 17
    ids = [m["id"] for m in panel["metrics"]]
    assert len(ids) == len(set(ids)), "duplicate metric ids in the panel"


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
    rec, _ = _record()
    sc = Scorecard()
    results = sc.score(rec)
    total_arrived = sum(f.bytes_arrived for f in rec.flows.values())
    total_dropped = sum(f.bytes_dropped_pdb for f in rec.flows.values())
    total_late = sum(f.bytes_delivered_late_pdb for f in rec.flows.values())
    expected = (total_dropped + total_late) / total_arrived if total_arrived else 0.0
    assert abs(results["M02"].value - expected) < 1e-9
    assert results["M02"].status == "ok"


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
