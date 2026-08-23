"""WP7 commit 3: periodic_control/condition_monitor (deterministic +
clipped-Gaussian jitter, optional multi-role streams) and aperiodic_event/
machine_vision (Poisson-triggered burst). Exercises sim.traffic.TrafficModel
directly, same style as test_messages.py.
"""

import numpy as np

from sim.buffer import BufferModel
from sim.config import FlowConfig
from sim.messages import MessageLedger
from sim.traffic import TrafficModel, _clipped_gaussian_jitter_ms


def _model(flow: FlowConfig, slot_duration_s: float = 0.0005, seed: int = 0,
           ledger: MessageLedger | None = None) -> TrafficModel:
    buffers = BufferModel()
    rng = np.random.default_rng(seed)
    return TrafficModel([flow], buffers, slot_duration_s=slot_duration_s,
                         rng=rng, ledger=ledger)


def test_periodic_control_fires_on_period_boundaries_with_role_data():
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="periodic_control",
                       traffic_params={"period_ms": 1.0, "bytes_per_period": 30})
    model = _model(flow, slot_duration_s=0.0005)
    period_slots = int(1.0 / 1000.0 / 0.0005)  # 2
    fired = [model._gen(flow, i, i * 0.0005) for i in range(6)]
    assert [bool(f) for f in fired] == [True, False, True, False, True, False]
    ts, byts, role = fired[0][0]
    assert byts == 30
    assert role == "data"


def test_periodic_control_without_jitter_params_is_deterministic():
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="periodic_control",
                       traffic_params={"period_ms": 1.0, "bytes_per_period": 30})
    model = _model(flow)
    ts, byts, role = model._gen(flow, 0, 0.0)[0]
    assert ts == 0.0  # no jitter configured -> sigma defaults to 0.0


def test_condition_monitor_is_mechanically_identical_to_periodic_control():
    params = {"period_ms": 2.0, "bytes_per_period": 20}
    a = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="periodic_control",
                    traffic_params=params)
    b = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="condition_monitor",
                    traffic_params=params)
    model_a = _model(a, seed=7)
    model_b = _model(b, seed=7)
    for i in range(8):
        assert model_a._gen(a, i, i * 0.0005) == model_b._gen(b, i, i * 0.0005)


def test_machine_vision_is_mechanically_identical_to_aperiodic_event():
    params = {"rate_hz": 50.0, "burst_bytes": 5000}
    a = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="aperiodic_event",
                    traffic_params=params)
    b = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="machine_vision",
                    traffic_params=params)
    model_a = _model(a, seed=3)
    model_b = _model(b, seed=3)
    for i in range(20):
        assert model_a._gen(a, i, i * 0.0005) == model_b._gen(b, i, i * 0.0005)


def test_multi_role_streams_tag_each_sub_streams_role_independently():
    """MAVLink-style: a 1Hz heartbeat multiplexed with a faster telemetry
    stream on one flow/port (README sec6)."""
    flow = FlowConfig(
        ue_id=1, qfi=9, direction="UL", traffic_kind="periodic_control",
        traffic_params={"streams": [
            {"role": "heartbeat", "period_ms": 4.0, "bytes": 20},
            {"role": "telemetry", "period_ms": 1.0, "bytes": 40},
        ]},
    )
    model = _model(flow, slot_duration_s=0.0005)
    roles_at_slot0 = {r for _, _, r in model._gen(flow, 0, 0.0)}
    assert roles_at_slot0 == {"heartbeat", "telemetry"}
    # telemetry period = 2 slots, heartbeat period = 8 slots -- at slot 2,
    # only telemetry should fire.
    roles_at_slot2 = {r for _, _, r in model._gen(flow, 2, 2 * 0.0005)}
    assert roles_at_slot2 == {"telemetry"}


def test_multi_role_streams_absent_falls_back_to_single_rate_role_data():
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="periodic_control",
                       traffic_params={"period_ms": 1.0, "bytes_per_period": 30})
    model = _model(flow, slot_duration_s=0.0005)
    arrivals = model._gen(flow, 0, 0.0)
    assert len(arrivals) == 1
    assert arrivals[0][2] == "data"


def test_aperiodic_event_never_fires_at_zero_rate():
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="aperiodic_event",
                       traffic_params={"rate_hz": 0.0, "burst_bytes": 1000})
    model = _model(flow, slot_duration_s=0.0005)
    for i in range(50):
        assert model._gen(flow, i, i * 0.0005) == []


def test_aperiodic_event_always_fires_when_trigger_prob_is_one():
    # rate_hz * slot_duration_s = 1.0 exactly -> rng.random() < 1.0 always.
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="aperiodic_event",
                       traffic_params={"rate_hz": 2000.0, "burst_bytes": 1000})
    model = _model(flow, slot_duration_s=0.0005)
    for i in range(20):
        arrivals = model._gen(flow, i, i * 0.0005)
        assert arrivals == [(i * 0.0005, 1000, "data")]


def test_clipped_gaussian_jitter_never_exceeds_clip_bound():
    rng = np.random.default_rng(0)
    samples = [_clipped_gaussian_jitter_ms(rng, sigma_ms=10.0, clip_ms=4.0)
               for _ in range(2000)]
    assert all(-4.0 <= s <= 4.0 for s in samples)
    assert any(s != 0.0 for s in samples)  # sigma>0 actually perturbs


def test_clipped_gaussian_jitter_is_zero_when_sigma_is_zero():
    rng = np.random.default_rng(0)
    assert all(_clipped_gaussian_jitter_ms(rng, sigma_ms=0.0, clip_ms=4.0) == 0.0
               for _ in range(10))


def test_periodic_control_jitter_default_clip_is_twice_sigma():
    """No jitter_clip_ms given -> defaults to 2x sigma, extending XR's own
    sigma~2ms/clip~4ms ratio (docs/wp7-plan.md Decision #1 area) rather than
    inventing an unrelated one."""
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="periodic_control",
                       traffic_params={"period_ms": 1.0, "bytes_per_period": 30,
                                       "jitter_sigma_ms": 100.0})
    model = _model(flow, slot_duration_s=0.0005, seed=1)
    ts_values = [model._gen(flow, 0, 0.0)[0][0] for _ in range(500)]
    # clip should be 2*100=200ms -> jitter in seconds within [-0.2, 0.2],
    # ts = max(0.0, 0.0 + jitter) so effectively [0.0, 0.2].
    assert all(0.0 <= ts <= 0.2 for ts in ts_values)


def test_existing_kinds_tag_role_data_and_are_otherwise_unaffected():
    """The _gen() tuple-shape change (ts, bytes) -> (ts, bytes, role) touches
    every existing kind's return statement mechanically; this pins that the
    values themselves (not just role) are unchanged from pre-WP7 shape."""
    det = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="deterministic",
                      traffic_params={"period_ms": 1.0, "bytes_per_period": 100})
    model = _model(det, slot_duration_s=0.0005)
    ts, byts, role = model._gen(det, 0, 0.0)[0]
    assert (ts, byts, role) == (0.0, 100, "data")
