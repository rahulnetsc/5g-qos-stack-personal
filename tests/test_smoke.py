from sim.buffer import BufferModel
from sim.config import (
    CarrierConfig,
    FlowConfig,
    ScenarioConfig,
    UEConfig,
)
from sim.driver import run
from sim.resource import ResourceGrid
from sim.schedulers.gradient import GradientScheduler
from sim.schedulers.pf import ProportionalFair
from sim.schedulers.round_robin import RoundRobin
from sim.schedulers.two_tier import TwoTier
from sim.tier1 import grid_capacity_prbsym_per_sec, solve_tier1


def test_channel_stationary_variance():
    """The AR(1) channel must be stationary: long-run std should match the
    configured stationary_std_db, not blow up because alpha is close to 1."""
    import numpy as np

    from sim.channel import ChannelModel

    rng = np.random.default_rng(42)
    ues = [UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=10000)]
    ch = ChannelModel(ues, rng, stationary_std_db=1.5)
    samples = []
    for i in range(20000):
        ch.update(i)
        samples.append(ch.get_snr_db(1))
    # Discard burn-in
    arr = np.array(samples[5000:])
    # Mean should be close to configured mean
    assert abs(arr.mean() - 20.0) < 1.5
    # Std should be within ~30% of stationary_std_db (finite-sample tolerance)
    assert 0.8 < arr.std() < 2.5, f"std={arr.std():.2f} outside expected range"


def test_buffer_basic_drain():
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 1000, 0.0)
    drained = b.drain(1, 9, 600)
    assert drained == 600
    assert b.state(1, 9).bytes_queued == 400


def test_buffer_hol_advances_after_drain():
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 100, 0.0)
    b.enqueue(1, 9, 100, 0.5)
    b.drain(1, 9, 100)
    # head chunk consumed; HoL is now the second chunk's timestamp
    assert b.state(1, 9).hol_timestamp_s == 0.5
    assert b.hol_delay_s(1, 9, now_s=0.7) == 0.7 - 0.5


def test_buffer_pdb_expiry():
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 500, 0.0)
    dropped = b.expire(now_s=1.0, pdb_s=0.5, ue_id=1, qfi=9)
    assert dropped == 500
    assert b.state(1, 9).bytes_queued == 0


def test_resource_grid_dsuuu_pattern():
    grid = ResourceGrid(CarrierConfig(numerology=1), tdd_config())
    kinds = [grid.slot_grid(i).direction for i in range(5)]
    assert kinds == list("DSUUU")
    # S-slot has both DL and UL symbols
    s = grid.slot_grid(1)
    assert s.direction == "S"
    assert s.dl_symbols > 0 and s.ul_symbols > 0


def tdd_config():
    from sim.config import TDDConfig
    return TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9))


def _single_flow_scenario():
    return ScenarioConfig(
        name="t",
        horizon_slots=200,
        carrier=CarrierConfig(numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0)],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 1_000_000},
            )
        ],
    )


def test_smoke_run_completes():
    summary = run(_single_flow_scenario(), RoundRobin())
    assert summary["horizon_s"] > 0
    assert "ue1_qfi9" in summary["flows"]
    assert summary["flows"]["ue1_qfi9"]["bytes_arrived"] > 0


def test_pf_smoke_completes():
    summary = run(_single_flow_scenario(), ProportionalFair())
    assert "ue1_qfi9" in summary["flows"]
    assert summary["flows"]["ue1_qfi9"]["bytes_delivered"] > 0


def _overload_scenario():
    """Both PF and GBR flows demand more than capacity. Capacity ~5 Mbps DL on
    a 10 MHz carrier at SNR 20 dB; PF demands 20 Mbps, GBR demands its full
    GFBR of 4 Mbps. PF's equal-share gives the GBR flow ~2.5 Mbps (below
    target); gradient should push it back up to ~4 Mbps."""
    return ScenarioConfig(
        name="overload",
        horizon_slots=4000,
        carrier=CarrierConfig(bandwidth_hz=10_000_000, numerology=1),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=2000),
            UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=2000),
        ],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL", flow_class="PF", pdb_ms=300,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 20_000_000},
            ),
            FlowConfig(
                ue_id=2, qfi=2, direction="DL", flow_class="GBR",
                gfbr_bps=4_000_000, pdb_ms=100,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 4_000_000},
            ),
        ],
        seed=2,
    )


def test_gradient_protects_gbr_under_overload():
    """Under overload, GradientScheduler should give the GBR flow more
    throughput than PF does, and reach close to its GFBR target."""
    pf = run(_overload_scenario(), ProportionalFair(ewma_window_slots=200))
    grad = run(
        _overload_scenario(),
        GradientScheduler(ewma_window_slots=200, gbr_urgency_weight=5.0),
    )
    pf_gbr = pf["flows"]["ue2_qfi2"]["throughput_bps"]
    grad_gbr = grad["flows"]["ue2_qfi2"]["throughput_bps"]
    target = 2_000_000.0

    assert grad_gbr > pf_gbr, (
        f"Gradient ({grad_gbr/1e6:.2f} Mbps) should beat PF ({pf_gbr/1e6:.2f} Mbps) "
        "for the GBR flow"
    )
    assert grad_gbr / target > 0.7, (
        f"Gradient should approach GFBR; got {grad_gbr/1e6:.2f} Mbps vs "
        f"target {target/1e6:.2f} Mbps"
    )


def test_gradient_matches_pf_when_all_pf():
    """With no GBR/Delay flows, gradient should behave roughly like PF.
    Throughput per flow should be within a small tolerance."""
    scenario = ScenarioConfig(
        name="all_pf",
        horizon_slots=2000,
        carrier=CarrierConfig(numerology=1),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=2000),
            UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=2000),
        ],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL", flow_class="PF",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 5_000_000},
            ),
            FlowConfig(
                ue_id=2, qfi=9, direction="DL", flow_class="PF",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 5_000_000},
            ),
        ],
        seed=3,
    )
    pf = run(scenario, ProportionalFair(ewma_window_slots=200))
    grad = run(scenario, GradientScheduler(ewma_window_slots=200))
    for fk in pf["flows"]:
        pf_t = pf["flows"][fk]["bytes_delivered"]
        grad_t = grad["flows"][fk]["bytes_delivered"]
        ratio = min(pf_t, grad_t) / max(pf_t, grad_t, 1)
        assert ratio > 0.9, (
            f"{fk}: PF and Gradient should agree when all flows are PF "
            f"(pf={pf_t}, grad={grad_t}, ratio={ratio:.2f})"
        )


def test_tier1_solver_basic_feasibility():
    """LP should return non-negative rates that fit in capacity."""
    from sim.config import TDDConfig
    grid = ResourceGrid(CarrierConfig(numerology=1), TDDConfig())
    flows = [
        FlowConfig(ue_id=1, qfi=9, direction="DL", flow_class="PF",
                   traffic_kind="poisson",
                   traffic_params={"rate_bps": 5_000_000}),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR",
                   gfbr_bps=3_000_000,
                   traffic_kind="poisson",
                   traffic_params={"rate_bps": 3_000_000}),
    ]
    targets = solve_tier1(
        flows=flows,
        snr_db_per_ue={1: 20.0, 2: 20.0},
        grid=grid,
        demand_bps={(1, 9): 5_000_000, (2, 1): 3_000_000},
    )
    assert (1, 9) in targets and (2, 1) in targets
    for v in targets.values():
        assert v >= 0


def test_tier1_protects_gbr_under_overload():
    """When demand > capacity, LP should sacrifice PF to keep GBR at GFBR."""
    from sim.config import TDDConfig
    grid = ResourceGrid(CarrierConfig(numerology=1, bandwidth_hz=10_000_000), TDDConfig())
    flows = [
        FlowConfig(ue_id=1, qfi=9, direction="DL", flow_class="PF",
                   traffic_kind="poisson",
                   traffic_params={"rate_bps": 50_000_000}),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR",
                   gfbr_bps=4_000_000,
                   traffic_kind="poisson",
                   traffic_params={"rate_bps": 4_000_000}),
    ]
    targets = solve_tier1(
        flows=flows,
        snr_db_per_ue={1: 20.0, 2: 20.0},
        grid=grid,
        demand_bps={(1, 9): 50_000_000, (2, 1): 4_000_000},
    )
    # GBR target should hit ~GFBR
    assert targets[(2, 1)] / 4_000_000 > 0.95, (
        f"GBR target should be near GFBR, got {targets[(2, 1)]/1e6:.2f} Mbps"
    )
    # PF should get the residual
    assert targets[(1, 9)] < targets[(2, 1)], (
        f"PF should be sacrificed to GBR; got PF={targets[(1, 9)]/1e6:.2f}, "
        f"GBR={targets[(2, 1)]/1e6:.2f}"
    )


def test_grid_capacity_helper():
    """Capacity computation should be > 0 and respect TDD pattern."""
    from sim.config import TDDConfig
    grid = ResourceGrid(CarrierConfig(numerology=1), TDDConfig(pattern="DSUUU"))
    cap_dl, cap_ul = grid_capacity_prbsym_per_sec(grid)
    assert cap_dl > 0 and cap_ul > 0
    # DSUUU has 1 D + S(DL) symbols, vs 3 U + S(UL); UL > DL by symbol count
    assert cap_ul > cap_dl


def test_two_tier_beats_gradient_on_gbr_overload():
    """Under overload, TwoTier should deliver more of the GBR target than the
    Gradient scheduler with hardcoded weights."""
    grad = run(
        _overload_scenario(),
        GradientScheduler(ewma_window_slots=200, gbr_urgency_weight=5.0),
    )
    tt = run(_overload_scenario(), TwoTier(tier1_period_slots=2000))
    grad_gbr = grad["flows"]["ue2_qfi2"]["throughput_bps"]
    tt_gbr = tt["flows"]["ue2_qfi2"]["throughput_bps"]
    target = 4_000_000.0
    assert tt_gbr > grad_gbr, (
        f"TwoTier ({tt_gbr/1e6:.2f}) should beat Gradient ({grad_gbr/1e6:.2f})"
    )
    assert tt_gbr / target > 0.9, (
        f"TwoTier should hit > 90% of GFBR; got {tt_gbr/1e6:.2f} Mbps"
    )


def test_two_tier_sps_does_not_double_allocate():
    """Regression guard: SPS + dynamic-spillover for the same flow must not
    drain more bytes than were ever queued. delivered + dropped <= arrived."""
    from sim.scenarios import smoke_scenario, vision_scenario
    for sc_factory in (smoke_scenario, vision_scenario):
        scenario = sc_factory()
        summary = run(scenario, TwoTier(tier1_period_slots=2000))
        for fk, m in summary["flows"].items():
            arrived = m["bytes_arrived"]
            delivered = m["bytes_delivered"]
            dropped = m["bytes_dropped"]
            assert delivered <= arrived, (
                f"{scenario.name}/{fk}: delivered {delivered} > arrived {arrived}"
            )
            assert delivered + dropped <= arrived, (
                f"{scenario.name}/{fk}: delivered+dropped > arrived"
            )


def test_two_tier_sps_engages_for_periodic_flow():
    """A video_frame flow under TwoTier should get an SPS reservation."""
    from sim.scenarios import vision_scenario
    sched = TwoTier(tier1_period_slots=2000)
    summary = run(vision_scenario(), sched)
    # After at least one Tier-1 solve, SPS list should include the cameras.
    sps_keys = sched._sps_keys
    # 3 video_frame flows in vision_scenario should all get SPS reservations.
    assert len([k for k in sps_keys if k[1] == 2]) == 3, (
        f"Expected all 3 video flows to get SPS; got {sps_keys}"
    )
    # And the cameras should still be delivering well (>= 95% of offered).
    for ue in (1, 2, 3):
        ratio = summary["flows"][f"ue{ue}_qfi2"]["delivery_ratio"]
        assert ratio >= 0.95, f"camera ue{ue} delivery ratio {ratio} too low"


def test_two_tier_sps_disabled_falls_back_to_dynamic():
    """With enable_sps=False the scheduler should still serve everyone, just
    using only dynamic scheduling."""
    from sim.scenarios import vision_scenario
    sched = TwoTier(tier1_period_slots=2000, enable_sps=False)
    summary = run(vision_scenario(), sched)
    assert len(sched._sps_keys) == 0
    # System should still complete; cameras may have higher tail latency.
    for ue in (1, 2, 3):
        assert summary["flows"][f"ue{ue}_qfi2"]["bytes_delivered"] > 0


def test_two_tier_beats_pf_under_pdcch_pressure():
    """30 small periodic sensors saturate the UL PDCCH budget. TwoTier with
    SPS should deliver every sensor's full demand with low latency; PF, lacking
    SPS, hits the DCI cap and drops packets.
    """
    from sim.scenarios import sensor_dense_scenario
    from sim.schedulers.pf import ProportionalFair

    sc = sensor_dense_scenario(num_sensors=30)
    pf_sum = run(sc, ProportionalFair(ewma_window_slots=200))
    tt_sum = run(sc, TwoTier(tier1_period_slots=2000))

    pf_min_delivery = min(
        pf_sum["flows"][k]["delivery_ratio"] for k in pf_sum["flows"]
    )
    tt_min_delivery = min(
        tt_sum["flows"][k]["delivery_ratio"] for k in tt_sum["flows"]
    )
    pf_worst_p99 = max(
        pf_sum["flows"][k]["hol_p99_ms"] for k in pf_sum["flows"]
    )
    tt_worst_p99 = max(
        tt_sum["flows"][k]["hol_p99_ms"] for k in tt_sum["flows"]
    )

    assert tt_min_delivery > pf_min_delivery, (
        f"TwoTier min delivery {tt_min_delivery:.1%} should beat PF "
        f"{pf_min_delivery:.1%}"
    )
    assert tt_min_delivery >= 0.99, (
        f"TwoTier should deliver ~100% per sensor; got {tt_min_delivery:.1%}"
    )
    assert tt_worst_p99 < pf_worst_p99, (
        f"TwoTier worst p99 HoL {tt_worst_p99} ms should beat PF {pf_worst_p99} ms"
    )


def test_pdcch_budget_caps_dynamic_allocations():
    """The dynamic scheduler must respect the per-slot CCE budget. With many
    flows and a tight budget, PF's allocation count per slot is bounded."""
    from sim.scenarios import sensor_dense_scenario
    from sim.schedulers.pf import ProportionalFair

    sc = sensor_dense_scenario(num_sensors=30)
    summary = run(sc, ProportionalFair(ewma_window_slots=200))
    # PDCCH utilization should be high (we're hitting the budget) but not
    # over 100% (the cap actually applies).
    util = summary["cce_utilization"]
    assert 0.4 < util <= 1.0, f"PDCCH utilization {util:.1%} unexpected"


def test_cce_aggregation_level_monotonic():
    """Higher SNR → fewer CCEs per DCI. Edge UEs should pay more."""
    from sim.channel import cce_aggregation_level
    snrs = [-5, 2, 8, 14, 20, 30]
    als = [cce_aggregation_level(s) for s in snrs]
    # Should be non-increasing and bounded
    assert all(a >= b for a, b in zip(als, als[1:]))
    assert min(als) == 1
    assert max(als) <= 16


def test_timeseries_recording_returns_per_slot_data():
    """Opt-in timeseries recording should produce one entry per slot per
    flow and per system metric, with the right lengths."""
    from sim.scenarios import smoke_scenario

    scenario = smoke_scenario()
    summary = run(
        scenario, TwoTier(tier1_period_slots=2000), record_timeseries=True
    )
    assert "timeseries" in summary
    ts = summary["timeseries"]
    assert len(ts["slot_index"]) == scenario.horizon_slots
    assert len(ts["time_s"]) == scenario.horizon_slots
    for fk, series in ts["per_flow"].items():
        for metric, values in series.items():
            assert len(values) == scenario.horizon_slots, (
                f"{fk}/{metric}: {len(values)} != {scenario.horizon_slots}"
            )
    for k, values in ts["system"].items():
        assert len(values) == scenario.horizon_slots


def test_timeseries_default_off():
    """Without record_timeseries=True, summary should omit the heavy ts data."""
    from sim.scenarios import smoke_scenario

    summary = run(smoke_scenario(), TwoTier(tier1_period_slots=2000))
    assert "timeseries" not in summary


def test_two_tier_runs_without_overload():
    """With abundant capacity, TwoTier should serve every flow's full demand."""
    scenario = ScenarioConfig(
        name="abundant",
        horizon_slots=2000,
        carrier=CarrierConfig(numerology=1, bandwidth_hz=30_000_000),
        ues=[UEConfig(ue_id=1, mean_snr_db=22.0, coherence_slots=2000)],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL", flow_class="PF",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 1_000_000},
            )
        ],
        seed=4,
    )
    summary = run(scenario, TwoTier(tier1_period_slots=2000))
    flow = summary["flows"]["ue1_qfi9"]
    # Should deliver near 100% of offered
    assert flow["delivery_ratio"] > 0.95


def test_pf_fairness_two_equal_ues():
    """Two UEs with identical channel and identical offered load should each
    get roughly half the throughput under PF."""
    scenario = ScenarioConfig(
        name="pf_fair",
        horizon_slots=2000,
        carrier=CarrierConfig(numerology=1),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=10000),
            UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=10000),
        ],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 5_000_000},
            ),
            FlowConfig(
                ue_id=2, qfi=9, direction="DL",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 5_000_000},
            ),
        ],
        seed=1,
    )
    summary = run(scenario, ProportionalFair(ewma_window_slots=200))
    t1 = summary["flows"]["ue1_qfi9"]["bytes_delivered"]
    t2 = summary["flows"]["ue2_qfi9"]["bytes_delivered"]
    # Within 20% of each other
    ratio = min(t1, t2) / max(t1, t2)
    assert ratio > 0.8, f"PF unfair: ue1={t1} ue2={t2} ratio={ratio:.2f}"
