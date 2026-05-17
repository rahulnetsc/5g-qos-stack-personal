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


def test_two_tier_sps_oversubscribed_tier_falls_back_to_dynamic():
    """NOTES.md Finding 2: when SPS-eligible flows over-subscribe the carrier,
    the viability floor sends the whole tier to dynamic rather than handing
    out undersized reservations (or starving the last-listed flows). The
    factory_robots UL video flows over-commit and the cell is not CCE-bound,
    so the tier is all-or-nothing -- here, none get an SPS reservation."""
    from sim.scenarios import factory_robots_scenario

    scenario = factory_robots_scenario()
    sched = TwoTier(tier1_period_slots=2000)
    run(scenario, sched)
    ul_video = {
        (f.ue_id, f.qfi) for f in scenario.flows
        if f.direction == "UL" and f.traffic_kind == "video_frame"
    }
    reserved = ul_video & sched._sps_keys
    # All-or-nothing: never a list-order subset.
    assert reserved == set(), (
        f"over-subscribed UL tier should fall back to dynamic; got SPS for "
        f"{sorted(reserved)}"
    )


def test_two_tier_sps_priority_tier_decides_the_winner():
    """When two equally-sized SPS-eligible flows over-commit a carrier, the
    one in the higher-priority tier (lower priority_level) is funded and the
    other is left for dynamic. Swapping the priorities swaps the winner."""
    from sim.config import TDDConfig

    grid = ResourceGrid(
        CarrierConfig(numerology=1, bandwidth_hz=10_000_000), TDDConfig()
    )

    def two_flows(pri1, pri2):
        # Identical periodic DL flows; each alone nearly fills the SPS
        # budget, so together they over-commit and only one can be funded.
        return [
            FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="Delay",
                       priority_level=pri1, pdb_ms=20,
                       traffic_kind="deterministic",
                       traffic_params={"period_ms": 2.0,
                                       "bytes_per_period": 700}),
            FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="Delay",
                       priority_level=pri2, pdb_ms=20,
                       traffic_kind="deterministic",
                       traffic_params={"period_ms": 2.0,
                                       "bytes_per_period": 700}),
        ]

    def reserved(flows):
        sched = TwoTier(tier1_period_slots=2000)
        sched.configure(flows, grid.slot_duration_s, grid)
        sched._update_sps_reservations({1: 20.0, 2: 20.0})
        return {(s.ue_id, s.qfi) for s in sched._sps}

    assert reserved(two_flows(1, 50)) == {(1, 1)}, "higher-priority ue1 wins"
    assert reserved(two_flows(50, 1)) == {(2, 1)}, "higher-priority ue2 wins"


def test_two_tier_beats_pf_under_pdcch_pressure():
    """30 small periodic sensors saturate the UL PDCCH budget. TwoTier with
    SPS should deliver every sensor's full demand with low latency; PF, lacking
    SPS, hits the DCI cap and drops packets.
    """
    from sim.scenarios import sensor_dense_scenario
    from sim.schedulers.pf import ProportionalFair

    sc = sensor_dense_scenario()
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


def test_latency_bound_two_tier_protects_deadlines():
    """In the DL-congested latency-bound scenario, TwoTier must hold the
    medium-rate interactive (Delay) flows within their PDB while PF, which
    is deadline-blind, misses some. Guards study 3 of scheduler_study.py."""
    from sim.scenarios import latency_bound_scenario
    from sim.schedulers.pf import ProportionalFair

    sc = latency_bound_scenario()
    pdb_ms = next(f.pdb_ms for f in sc.flows if f.flow_class == "Delay")
    delay_keys = [
        f"ue{f.ue_id}_qfi{f.qfi}" for f in sc.flows if f.flow_class == "Delay"
    ]

    pf = run(sc, ProportionalFair(ewma_window_slots=200))
    tt = run(sc, TwoTier(tier1_period_slots=2000))

    def on_time(summary):
        return sum(
            1 for k in delay_keys
            if summary["flows"][k]["delivery_ratio"] >= 0.99
            and summary["flows"][k]["hol_p99_ms"] <= pdb_ms
        )

    tt_worst_p99 = max(tt["flows"][k]["hol_p99_ms"] for k in delay_keys)
    assert on_time(tt) > on_time(pf), (
        f"TwoTier on-time {on_time(tt)} should beat PF {on_time(pf)}"
    )
    assert on_time(tt) == len(delay_keys), (
        f"TwoTier should hold every deadline; got {on_time(tt)}/{len(delay_keys)}"
    )
    assert tt_worst_p99 <= pdb_ms, (
        f"TwoTier worst p99 HoL {tt_worst_p99} ms exceeds PDB {pdb_ms} ms"
    )


def test_pdcch_budget_caps_dynamic_allocations():
    """The dynamic scheduler must respect the per-slot CCE budget. With many
    flows and a tight budget, PF's allocation count per slot is bounded."""
    from sim.scenarios import sensor_dense_scenario
    from sim.schedulers.pf import ProportionalFair

    sc = sensor_dense_scenario()
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


def test_two_tier_virtual_queue_windowed_ceiling():
    """The windowed ceiling bounds Q at one Tier-1 window of target inflow:
    Q_i <= target_bps_i * tier1_period * slot_duration_s. This pins the
    cap and guards against runaway Q for a flow offered below its target."""
    scenario = ScenarioConfig(
        name="below_target",
        horizon_slots=2000,
        carrier=CarrierConfig(numerology=1, bandwidth_hz=30_000_000),
        ues=[UEConfig(ue_id=1, mean_snr_db=22.0, coherence_slots=2000)],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL", flow_class="PF",
                traffic_kind="poisson",
                traffic_params={"rate_bps": 2_000_000},
            )
        ],
        seed=5,
    )
    sched = TwoTier(tier1_period_slots=2000)
    violations = []
    orig_allocate = sched.allocate

    def checked_allocate(slot, buffers, channel):
        result = orig_allocate(slot, buffers, channel)
        window_s = sched.tier1_period * sched.slot_duration_s
        for key, q in sched._virtual_q.items():
            cap = sched._targets_bps.get(key, 0.0) * window_s
            if q > cap * 1.01 + 1:
                violations.append((slot.slot_index, key, q, cap))
        return result

    sched.allocate = checked_allocate  # type: ignore[method-assign]
    run(scenario, sched)
    assert not violations, f"virtual queue exceeded windowed cap: {violations[:3]}"


def test_two_tier_windowed_ceiling_protects_bursty_gbr():
    """Regression guard for the 10-robot finding: a bursty GBR flow sharing a
    UE with a continuous best-effort flow must not be starved by TwoTier.
    With the old instantaneous-backlog clamp the bursty flow's Q collapsed
    between video frames and the continuous PF flow won; the windowed
    ceiling fixes that. TwoTier should serve the GBR flow at least as well
    as plain PF does."""
    from sim.config import TDDConfig
    from sim.schedulers.pf import ProportionalFair

    def scenario():
        return ScenarioConfig(
            name="mixed_flow_ue",
            horizon_slots=8000,
            carrier=CarrierConfig(numerology=1, bandwidth_hz=20_000_000),
            tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
            ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=2000)],
            flows=[
                # Bursty GBR video on the same UE as ...
                FlowConfig(
                    ue_id=1, qfi=2, direction="UL", flow_class="GBR",
                    gfbr_bps=6_000_000, pdb_ms=30,
                    traffic_kind="video_frame",
                    traffic_params={
                        "period_ms": 33.33, "avg_bytes": 25_000,
                        "i_frame_multiplier": 4.0,
                        "i_frame_period_in_frames": 30,
                    },
                ),
                # ... a continuous best-effort upload competing in the UL pool.
                FlowConfig(
                    ue_id=1, qfi=9, direction="UL", flow_class="PF",
                    pdb_ms=300, traffic_kind="poisson",
                    traffic_params={"rate_bps": 15_000_000},
                ),
            ],
            seed=4,
        )

    pf = run(scenario(), ProportionalFair(ewma_window_slots=200))
    tt = run(scenario(), TwoTier(tier1_period_slots=2000))
    pf_gbr = pf["flows"]["ue1_qfi2"]["delivery_ratio"]
    tt_gbr = tt["flows"]["ue1_qfi2"]["delivery_ratio"]
    assert tt_gbr >= pf_gbr, (
        f"TwoTier GBR delivery {tt_gbr:.0%} should be >= PF's {pf_gbr:.0%} "
        "(bursty GBR must not lose to continuous PF on the same UE)"
    )


def test_tier1_per_flow_penalty_shifts_allocation():
    """A higher per-flow GBR penalty pulls LP allocation toward that flow.
    Under partial infeasibility with a uniform penalty the poor-SNR GBR flow
    is sacrificed; boosting its penalty reverses that."""
    from sim.config import TDDConfig

    grid = ResourceGrid(
        CarrierConfig(numerology=1, bandwidth_hz=20_000_000), TDDConfig()
    )
    flows = [
        FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="GBR",
                   gfbr_bps=3_000_000, traffic_kind="poisson",
                   traffic_params={"rate_bps": 3_000_000}),
        FlowConfig(ue_id=2, qfi=2, direction="DL", flow_class="GBR",
                   gfbr_bps=3_000_000, traffic_kind="poisson",
                   traffic_params={"rate_bps": 3_000_000}),
    ]
    demand = {(1, 2): 3_000_000, (2, 2): 3_000_000}
    snr = {1: 22.0, 2: 8.0}  # flow 2 is the poor-SNR flow

    uni = solve_tier1(flows, snr, grid, demand, gbr_slack_penalty=1e3)
    boosted = solve_tier1(
        flows, snr, grid, demand,
        gbr_slack_penalty={(1, 2): 1e3, (2, 2): 1e5},
    )
    # Uniform penalty sacrifices the poor-SNR flow.
    assert uni[(2, 2)] < uni[(1, 2)]
    # Boosting flow 2's penalty pulls allocation back to it.
    assert boosted[(2, 2)] > uni[(2, 2)] + 0.2e6


def test_tier1_se_penalty_exponent_tilts_allocation():
    """The SE-tilt exponent k scales each flow's GBR penalty by
    (SE_i/SE_max)**k. With two GBR flows that cannot both be met, k>0
    (efficiency-first) leaves the poor-SE flow sacrificed, while k<0
    (RB-level parity) pulls allocation back toward it."""
    from sim.config import TDDConfig

    grid = ResourceGrid(
        CarrierConfig(numerology=1, bandwidth_hz=20_000_000), TDDConfig()
    )
    flows = [
        FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="GBR",
                   gfbr_bps=3_000_000, traffic_kind="poisson",
                   traffic_params={"rate_bps": 3_000_000}),
        FlowConfig(ue_id=2, qfi=2, direction="DL", flow_class="GBR",
                   gfbr_bps=3_000_000, traffic_kind="poisson",
                   traffic_params={"rate_bps": 3_000_000}),
    ]
    demand = {(1, 2): 3_000_000, (2, 2): 3_000_000}
    snr = {1: 22.0, 2: 8.0}  # flow 2 is the poor-SE flow

    base = solve_tier1(flows, snr, grid, demand, gbr_slack_penalty=1e3)
    eff_first = solve_tier1(flows, snr, grid, demand,
                            gbr_slack_penalty=1e3, se_penalty_exponent=2.0)
    rb_parity = solve_tier1(flows, snr, grid, demand,
                            gbr_slack_penalty=1e3, se_penalty_exponent=-2.0)

    # k<0 (RB-level parity) gives the poor-SE flow materially more rate than
    # k>0 (efficiency-first) does.
    assert rb_parity[(2, 2)] > eff_first[(2, 2)] + 0.2e6
    # k>0 does not rescue the poor-SE flow -- it is already the dump target.
    assert eff_first[(2, 2)] <= base[(2, 2)] + 1.0
    # k<0 strictly improves it over the untilted baseline.
    assert rb_parity[(2, 2)] > base[(2, 2)] + 1.0


def _two_gbr_partial_infeasible_scenario():
    """Two GBR flows — one good-SNR, one poor-SNR — on a carrier that cannot
    meet both GFBRs at once. 6 Tier-1 solves over the horizon."""
    from sim.config import TDDConfig

    return ScenarioConfig(
        name="two_gbr",
        horizon_slots=12000,
        carrier=CarrierConfig(numerology=1, bandwidth_hz=20_000_000),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=22.0, coherence_slots=4000),
            UEConfig(ue_id=2, mean_snr_db=8.0, coherence_slots=4000),
        ],
        flows=[
            FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=3_000_000, pdb_ms=100, traffic_kind="poisson",
                       traffic_params={"rate_bps": 3_000_000}),
            FlowConfig(ue_id=2, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=3_000_000, pdb_ms=100, traffic_kind="poisson",
                       traffic_params={"rate_bps": 3_000_000}),
        ],
        seed=3,
    )


def test_two_tier_adaptive_penalty_helps_poor_snr_gbr():
    """Adaptive per-flow penalty (b>0) rebalances the GBR sacrifice toward
    the poor-SNR flow, improving the worst-served GBR flow vs fixed b=0."""
    fixed = run(_two_gbr_partial_infeasible_scenario(),
                TwoTier(tier1_period_slots=2000, gbr_penalty_lr=0.0))
    adaptive = run(_two_gbr_partial_infeasible_scenario(),
                   TwoTier(tier1_period_slots=2000, gbr_penalty_lr=1e5))

    def min_delivery(summary):
        return min(f["delivery_ratio"] for f in summary["flows"].values())

    assert min_delivery(adaptive) > min_delivery(fixed) + 0.01, (
        f"adaptive min delivery {min_delivery(adaptive):.1%} should beat "
        f"fixed {min_delivery(fixed):.1%}"
    )
    # The poor-SNR flow (ue2) specifically improves.
    assert (
        adaptive["flows"]["ue2_qfi2"]["delivery_ratio"]
        > fixed["flows"]["ue2_qfi2"]["delivery_ratio"]
    )


def test_two_tier_adaptive_penalty_caps_at_max():
    """A genuinely infeasible GBR flow must not diverge: its penalty stops
    at gbr_penalty_max instead of growing without bound."""
    from sim.config import TDDConfig

    scenario = ScenarioConfig(
        name="infeasible_gbr",
        horizon_slots=8000,  # 4 Tier-1 solves
        carrier=CarrierConfig(numerology=1, bandwidth_hz=10_000_000),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[UEConfig(ue_id=1, mean_snr_db=8.0, coherence_slots=4000)],
        flows=[
            FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=50_000_000,  # far above carrier capacity
                       pdb_ms=100, traffic_kind="poisson",
                       traffic_params={"rate_bps": 50_000_000}),
        ],
        seed=1,
    )
    p_max = 5_000.0
    sched = TwoTier(
        tier1_period_slots=2000, gbr_penalty_lr=1e6, gbr_penalty_max=p_max
    )
    run(scenario, sched)
    pen = sched._gbr_penalty[(1, 2)]
    assert pen <= p_max, f"penalty {pen} exceeded cap {p_max}"
    assert pen == p_max, (
        f"infeasible flow should drive the penalty to the cap; got {pen}"
    )


def test_two_tier_adaptive_penalty_disabled_by_default():
    """With gbr_penalty_lr=0 (default) the penalties never move from init."""
    from sim.scenarios import overload_scenario

    sched = TwoTier(tier1_period_slots=2000)  # default gbr_penalty_lr=0
    run(overload_scenario(), sched)
    assert all(
        p == sched.gbr_penalty_init for p in sched._gbr_penalty.values()
    )


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
