"""WP-Join commit 6: the application-layer gate -- traffic-admission
suppression (source gate, warm/cold paths only) and the real UL/DL
handshake Message pair. Opt-in: UEConfig.join stays the only top-level
gate (from commit 5); commit 6 makes what an ALREADY-gated UE experiences
richer (its traffic can now be suppressed, its handshake can now
complete) rather than adding a second independent opt-in surface.
"""

import numpy as np
import pytest

from sim.buffer import BufferModel
from sim.config import CarrierConfig, ScenarioConfig, UEConfig
from sim.driver import run
from sim.join import JoinConfig, JoinEvent
from sim.messages import MessageLedger
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard
from sim.traffic import TrafficModel
from sim.baselines.round_robin import RoundRobin
from scheduler.flow import FlowConfig


# -- TrafficModel.generate()'s suppressed_ues: the source gate -------------


def _model(flows, slot_duration_s=0.0005, seed=0, ledger=None):
    buffers = BufferModel()
    rng = np.random.default_rng(seed)
    return TrafficModel(flows, buffers, slot_duration_s=slot_duration_s, rng=rng, ledger=ledger), buffers


def test_default_no_suppression_reproduces_existing_behaviour():
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", traffic_kind="poisson",
                       traffic_params={"rate_bps": 1_000_000})
    model, buffers = _model([flow])
    arrivals = [model.generate(slot) for slot in range(20)]  # no suppressed_ues arg at all
    assert sum(len(a) for a in arrivals) > 0  # poisson at 1Mbps over 20 slots -- should fire


def test_suppressed_ue_enqueues_nothing():
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", traffic_kind="poisson",
                       traffic_params={"rate_bps": 10_000_000})  # high rate -- fires almost every slot
    model, buffers = _model([flow])
    for slot in range(50):
        arrivals = model.generate(slot, suppressed_ues=frozenset({1}))
        assert arrivals == []
    assert buffers.state(1, 1).bytes_queued == 0


def test_suppression_does_not_perturb_the_shared_rng_draw_order():
    """The generate-then-drop claim, checked directly: an UNSUPPRESSED
    flow's own draw sequence must be identical whether or not ANOTHER
    flow in the same model is suppressed -- suppression only discards a
    result, it never skips the call that consumes rng."""
    flow_a = FlowConfig(ue_id=1, qfi=1, direction="UL", traffic_kind="poisson",
                         traffic_params={"rate_bps": 5_000_000})
    flow_b = FlowConfig(ue_id=2, qfi=1, direction="UL", traffic_kind="poisson",
                         traffic_params={"rate_bps": 5_000_000})

    model_suppressed, buffers_a = _model([flow_a, flow_b], seed=7)
    model_unsuppressed, buffers_b = _model([flow_a, flow_b], seed=7)
    for slot in range(200):
        model_suppressed.generate(slot, suppressed_ues=frozenset({2}))
        model_unsuppressed.generate(slot)

    # UE 1 (never suppressed in either run) must have received EXACTLY
    # the same bytes both times -- if suppression had skipped UE 2's
    # _gen() call instead of discarding its result, UE 1's own draws
    # (interleaved in flow-list order) would have shifted.
    assert buffers_a.state(1, 1).bytes_queued == buffers_b.state(1, 1).bytes_queued
    assert buffers_a.arrived_cum(1, 1) == buffers_b.arrived_cum(1, 1)
    # UE 2 got real backlog in the unsuppressed run, none in the suppressed one.
    assert buffers_a.state(2, 1).bytes_queued == 0
    assert buffers_b.arrived_cum(2, 1) > 0


def test_suppressed_ue_arrival_is_not_counted_by_the_ledger_either():
    ledger = MessageLedger()
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", traffic_kind="poisson",
                       traffic_params={"rate_bps": 10_000_000})
    model, buffers = _model([flow], ledger=ledger)
    for slot in range(30):
        model.generate(slot, suppressed_ues=frozenset({1}))
    assert ledger.completions_for(1, 1) == []


# -- end-to-end: warm path, real handshake, M18/M19 against a real record --


def _warm_scenario(handshake_qfis=(90, 91), trigger_slot=500, horizon_slots=3000):
    join_kwargs = {}
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000,
                   pdb_ms=50, traffic_kind="deterministic",
                   traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
    ]
    if handshake_qfis is not None:
        ul_qfi, dl_qfi = handshake_qfis
        join_kwargs = {"handshake_ul_qfi": ul_qfi, "handshake_dl_qfi": dl_qfi}
        flows += [
            FlowConfig(ue_id=1, qfi=ul_qfi, direction="UL", flow_class="PF", pdb_ms=1000,
                       traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
            FlowConfig(ue_id=1, qfi=dl_qfi, direction="DL", flow_class="PF", pdb_ms=1000,
                       traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
        ]
    sc = ScenarioConfig(
        name="wpjoin_warm_test", horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[
            UEConfig(
                ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
                join=JoinConfig(events=(JoinEvent(slot=trigger_slot, kind="app_restart"),), **join_kwargs),
            ),
        ],
        flows=flows,
    )
    return sc


def test_warm_path_completes_end_to_end_with_a_real_handshake():
    sc = _warm_scenario()
    summary = run(sc, RoundRobin())
    assert len(summary["join_events"]) == 1
    event = summary["join_events"][0]
    assert event["path"] == "warm"
    assert event["trigger_slot"] == 500
    assert event["rf_restore_slot"] is None  # warm never touches the radio at all
    assert event["attached_slot"] is not None
    assert event["handshake_rtt_ms"] is not None
    assert event["handshake_rtt_ms"] > 0.0
    assert "app_restart" in event["phases"]
    assert "app_handshake" in event["phases"]


def test_warm_path_without_handshake_qfis_still_reproduces_commit5_behaviour():
    """handshake_ul_qfi/dl_qfi=None (default) must still leave a UE parked
    in APP_HANDSHAKE forever -- commit 6 must not change behaviour for a
    scenario that opts into join/events but not into the handshake."""
    sc = _warm_scenario(handshake_qfis=None)
    summary = run(sc, RoundRobin())
    assert len(summary["join_events"]) == 1
    assert summary["join_events"][0]["attached_slot"] is None


def test_m18_reports_a_real_completed_warm_path_event_not_just_synthetic_ones():
    """Point 4 of commit 6's review: M18's warm/cold/reestablish breakdown
    checked against synthetic JoinEventRecords in commit 4, and against a
    real (but permanently-incomplete) reestablish event in commit 5. This
    is the first real, FULLY COMPLETED event of any kind -- warm, via
    this commit's handshake wiring."""
    sc = _warm_scenario()
    summary = run(sc, RoundRobin())
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="RR", seed=sc.seed,
        flow_configs=sc.flows, summary=summary,
    )
    res = Scorecard().score(rec, population=Population.all_flows())["M18"]
    assert res.status == "ok"
    warm = res.value["by_path"]["warm"]
    assert warm["n_events"] == 1
    assert warm["n_never_completed"] == 0  # real completion, not synthetic
    assert warm["p50_ms"] is not None
    assert warm["p50_ms"] == warm["p95_ms"] == warm["max_ms"]  # a single event
    assert "reestablish" not in res.value["by_path"]  # no reestablish event this run


def test_m19_promoted_to_proxy_and_computes_on_a_real_completed_event():
    sc = _warm_scenario()
    summary = run(sc, RoundRobin(), record_timeseries=True)
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="RR", seed=sc.seed,
        flow_configs=sc.flows, summary=summary,
    )
    res = Scorecard().score(rec, population=Population.all_flows())["M19"]
    assert res.status == "proxy"  # commit 6's promotion, checked against the actual panel file
    warm = res.value["by_path"]["warm"]
    assert warm["n_events"] == 1
    assert warm["n_never_recovered"] == 0


def test_m19_status_is_proxy_in_the_committed_panel_file():
    from sim.scorecard import load_panel
    m19 = next(m for m in load_panel()["metrics"] if m["id"] == "M19")
    assert m19["status"] == "proxy"


# -- opt-in inertness: both forms, extended to the app-layer gate ----------


def test_a_ue_with_join_but_no_events_or_handshake_is_never_suppressed():
    """Radio-gate-only opt-in (commit 5's own shape, no scripted_fade, no
    events) must never trigger the source gate either -- app_running
    starts and stays True for the whole run with nothing to flip it."""
    sc = ScenarioConfig(
        name="wpjoin_join_no_events", horizon_slots=200,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000, join=JoinConfig())],
        flows=[FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000,
                           pdb_ms=50, traffic_kind="deterministic",
                           traffic_params={"period_ms": 5.0, "bytes_per_period": 500})],
    )
    summary = run(sc, RoundRobin())
    assert summary["flows"]["ue1_qfi1"]["bytes_arrived"] > 0  # never suppressed
    assert summary["join_events"] == []


def test_no_ue_config_join_at_all_reproduces_pre_commit6_behaviour_exactly():
    """Structural form: with join_states empty, suppressed_ues is always
    the empty frozenset (built from join_states.items()), so traffic.
    generate()'s new parameter is passed but has zero effect -- the same
    "provably unreached," not merely "not observed," standard commit 5
    established for the radio gate."""
    sc = ScenarioConfig(
        name="wpjoin_no_join_at_all", horizon_slots=200,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000)],
        flows=[FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000,
                           pdb_ms=50, traffic_kind="deterministic",
                           traffic_params={"period_ms": 5.0, "bytes_per_period": 500})],
    )
    summary = run(sc, RoundRobin())
    assert summary["flows"]["ue1_qfi1"]["bytes_arrived"] > 0
    assert summary["join_events"] == []
