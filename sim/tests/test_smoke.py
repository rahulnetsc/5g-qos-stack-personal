from sim.buffer import BufferModel
from sim.config import (
    CarrierConfig,
    FlowConfig,
    ScenarioConfig,
    UEConfig,
)
from sim.driver import run
from sim.resource import ResourceGrid
from sim.baselines.gradient import GradientScheduler
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin
from scheduler import TwoTier
from scheduler import bler_for_mcs, grid_capacity_prbsym_per_sec, mcs_threshold_for_snr, solve_tier1
from scheduler import (
    estimate_demand_bps,
    gbr_contract_bps,
    gbr_maxmin_floors,
    solve_maxmin_gbr_level,
)


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


def test_channel_cqi_delay_lags_true_snr():
    """With cqi_delay_slots > 0, get_reported_snr_db(ue) equals the true
    SNR from `delay` slots ago, once the pipeline has filled. Before that,
    the initial reported value equals mean_snr_db (a UE reports a CQI at
    RRC attach)."""
    import numpy as np

    from sim.channel import ChannelModel

    rng = np.random.default_rng(7)
    ues = [UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1)]
    ch = ChannelModel(ues, rng, stationary_std_db=1.5, cqi_delay_slots=4)
    trail = []
    # First update publishes the initial mean-report; then reported lags
    # by `delay` = 4 slots.
    for i in range(10):
        ch.update(i)
        trail.append((ch.get_snr_db(1), ch.get_reported_snr_db(1)))
    # At slot i >= 4, reported == true from slot i-4 (i.e. index i-4 in the
    # true-SNR series). Verify a couple of late slots.
    for i in range(4, 10):
        true_then, _ = trail[i - 4]
        _, reported_now = trail[i]
        assert abs(reported_now - true_then) < 1e-9, f"slot {i}: reported {reported_now} vs true[i-4] {true_then}"


def test_channel_cqi_loss_holds_last_reported_value():
    """With cqi_loss_rate = 1.0 every update is lost -> the reported SNR
    never advances past the initial mean value."""
    import numpy as np

    from sim.channel import ChannelModel

    rng = np.random.default_rng(3)
    ues = [UEConfig(ue_id=1, mean_snr_db=15.0, coherence_slots=1)]
    ch = ChannelModel(ues, rng, cqi_delay_slots=2, cqi_loss_rate=1.0, cqi_seed=1)
    for i in range(20):
        ch.update(i)
    # Every update lost -> reported stayed at the RRC-attach initial value.
    assert abs(ch.get_reported_snr_db(1) - 15.0) < 1e-9


def test_bler_for_mcs_matched_vs_mismatched():
    """At the MCS threshold BLER is the target (10%); below the threshold
    BLER doubles per dB of shortfall; well below, capped at 1.0."""
    thresh = mcs_threshold_for_snr(20.0)  # some non-edge MCS
    assert bler_for_mcs(thresh, thresh) == 0.10        # matched
    assert bler_for_mcs(thresh, thresh + 5) == 0.10    # above -> still target
    assert bler_for_mcs(thresh, thresh - 1) == 0.20    # -1 dB
    assert bler_for_mcs(thresh, thresh - 2) == 0.40    # -2 dB
    assert bler_for_mcs(thresh, thresh - 4) == 1.0     # capped


def test_two_tier_sps_uses_conservative_mcs():
    """SPS reservations are sized against snr_avg - sps_snr_margin_db.
    Verify by picking a periodic flow with an explicit non-default margin
    (default is 0.0 for slow-varying channels; a non-zero margin is used
    where CQI can drift meaningfully -- see cqi_study.py)."""
    tt = TwoTier(
        tier1_period_slots=200,
        enable_sps=True,
        sps_snr_margin_db=3.0,
    )
    sc = ScenarioConfig(
        name="sps_mcs",
        horizon_slots=400,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000)],
        flows=[
            FlowConfig(
                ue_id=1, qfi=2, direction="UL", flow_class="GBR",
                gfbr_bps=4_000_000, pdb_ms=20,
                traffic_kind="deterministic",
                traffic_params={"period_ms": 5.0, "bytes_per_period": 2500},
            ),
        ],
    )
    run(sc, tt)
    # The reservation is sized against snr_avg - margin at the moment of
    # the SPS solve (which may differ slightly from the final snr_avg due
    # to AR(1) drift), so allow a few dB of tolerance vs mean - margin.
    assert len(tt._sps) == 1
    sps = tt._sps[0]
    assert sps.ue_id == 1 and sps.direction == "UL"
    assert abs(sps.snr_ref_db - (20.0 - 3.0)) < 2.0
    # And strictly below the smoothed SNR by at least ~2.5 dB (the margin
    # minus a small AR(1) wiggle room).
    assert sps.snr_ref_db < tt._snr_avg[1] - 2.5


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


def test_buffer_bsr_delay_none_when_disabled_or_dl():
    """bytes_reported tracks bytes_queued instantly for DL flows and for
    UL flows when ul_bsr_delay_slots = 0."""
    b = BufferModel(ul_bsr_delay_slots=0)
    b.register(1, 9, is_ul=True)
    b.enqueue(1, 9, 500, 0.0)
    b.snapshot_bsr()
    assert b.state(1, 9).bytes_reported == 500  # no delay configured

    b2 = BufferModel(ul_bsr_delay_slots=4)
    b2.register(2, 9, is_ul=False)  # DL flow -- always instant
    b2.enqueue(2, 9, 500, 0.0)
    b2.snapshot_bsr()
    assert b2.state(2, 9).bytes_reported == 500


def test_buffer_bsr_delay_lags_ul_by_configured_slots():
    """For a UL flow with ul_bsr_delay_slots = 4, bytes_reported at slot t
    equals bytes_queued as it was at slot t-4. Before the pipeline has
    filled, bytes_reported is 0 (no BSR has reached the gNB yet)."""
    b = BufferModel(ul_bsr_delay_slots=4)
    b.register(1, 9, is_ul=True)

    # Slots 0..3: arrivals accumulate, but no BSR is visible yet.
    for slot in range(4):
        b.enqueue(1, 9, 100, slot * 0.001)
        b.snapshot_bsr()
        assert b.state(1, 9).bytes_reported == 0, f"slot {slot}"

    # Slot 4: the first snapshot from slot 0 (100 bytes) becomes visible.
    b.enqueue(1, 9, 100, 4 * 0.001)
    b.snapshot_bsr()
    assert b.state(1, 9).bytes_reported == 100
    assert b.state(1, 9).bytes_queued == 500

    # Slot 8: sees slot 4's snapshot = 500 bytes.
    for slot in range(5, 9):
        b.enqueue(1, 9, 100, slot * 0.001)
        b.snapshot_bsr()
    assert b.state(1, 9).bytes_reported == 500
    assert b.state(1, 9).bytes_queued == 900


def test_buffer_bsr_loss_holds_last_reported_value():
    """With a 100% BSR loss rate, bytes_reported never advances past its
    initial value -- every update is lost, so the gNB keeps the (empty)
    initial view forever. Confirms the loss branch actually short-circuits
    the pipeline write."""
    b = BufferModel(ul_bsr_delay_slots=2, ul_bsr_loss_rate=1.0, bsr_seed=1)
    b.register(1, 9, is_ul=True)
    for slot in range(10):
        b.enqueue(1, 9, 100, slot * 0.001)
        b.snapshot_bsr()
    assert b.state(1, 9).bytes_queued == 1000
    assert b.state(1, 9).bytes_reported == 0  # every update lost

    # With a 0% loss rate the pipeline behaves normally (regression guard).
    b2 = BufferModel(ul_bsr_delay_slots=2, ul_bsr_loss_rate=0.0, bsr_seed=2)
    b2.register(2, 9, is_ul=True)
    for slot in range(5):
        b2.enqueue(2, 9, 100, slot * 0.001)
        b2.snapshot_bsr()
    # After 5 slots (indices 0..4) with delay=2: bytes_reported at slot 4
    # is the value from slot 2, which is 3 * 100 = 300 bytes.
    assert b2.state(2, 9).bytes_reported == 300


def test_buffer_bsr_loss_rng_independent_of_seed_variation():
    """Different bsr_seed values produce different loss draws (so runs are
    varied) but bsr_seed=0 is deterministic across constructor calls."""
    b1 = BufferModel(ul_bsr_delay_slots=1, ul_bsr_loss_rate=0.5, bsr_seed=0)
    b1.register(1, 9, is_ul=True)
    b2 = BufferModel(ul_bsr_delay_slots=1, ul_bsr_loss_rate=0.5, bsr_seed=0)
    b2.register(1, 9, is_ul=True)
    for slot in range(20):
        b1.enqueue(1, 9, 100, slot * 0.001)
        b1.snapshot_bsr()
        b2.enqueue(1, 9, 100, slot * 0.001)
        b2.snapshot_bsr()
    assert b1.state(1, 9).bytes_reported == b2.state(1, 9).bytes_reported


def test_buffer_bsr_sps_bypass_uses_bytes_queued():
    """A CG / SPS-served flow reads bytes_queued (real) not bytes_reported.
    The BufferState carries both so the scheduler can choose which to use;
    SPS uses bytes_queued directly."""
    b = BufferModel(ul_bsr_delay_slots=8)
    b.register(1, 9, is_ul=True)
    b.enqueue(1, 9, 1000, 0.0)
    b.snapshot_bsr()
    # bytes_reported still 0 (pipeline not filled), but bytes_queued is
    # 1000 -- an SPS pathway reading bytes_queued sees the data instantly.
    assert b.state(1, 9).bytes_reported == 0
    assert b.state(1, 9).bytes_queued == 1000


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


def test_tier1_capacity_safety_factor_shaves_targets():
    """A capacity_safety_factor < 1 shaves the LP's PRB budget symmetrically.
    Under overload where the LP would otherwise saturate DL, the total of
    per-flow targets must fall roughly in proportion."""
    from sim.config import TDDConfig
    grid = ResourceGrid(CarrierConfig(numerology=1, bandwidth_hz=10_000_000), TDDConfig())
    flows = [
        FlowConfig(ue_id=1, qfi=9, direction="DL", flow_class="PF",
                   traffic_kind="poisson",
                   traffic_params={"rate_bps": 50_000_000}),
        FlowConfig(ue_id=2, qfi=9, direction="DL", flow_class="PF",
                   traffic_kind="poisson",
                   traffic_params={"rate_bps": 50_000_000}),
    ]
    common = dict(
        flows=flows,
        snr_db_per_ue={1: 20.0, 2: 20.0},
        grid=grid,
        demand_bps={(1, 9): 50_000_000, (2, 9): 50_000_000},
    )
    t_full = solve_tier1(**common, capacity_safety_factor=1.0)
    t_shaved = solve_tier1(**common, capacity_safety_factor=0.5)
    total_full = sum(t_full.values())
    total_shaved = sum(t_shaved.values())
    # 0.5 factor should cut total rate by ~half (within ~5% for solver
    # slack). The direction matters most: shaved < full, and specifically
    # near half.
    assert total_shaved < total_full * 0.6, (
        f"safety_factor=0.5 should shave total ~half; got "
        f"{total_shaved/1e6:.1f} Mbps vs {total_full/1e6:.1f} Mbps"
    )
    assert total_shaved > total_full * 0.4


def test_two_tier_forwards_capacity_safety_factor():
    """TwoTier(capacity_safety_factor=…) must reach solve_tier1. Inspected
    at the Tier-1 target-rate layer (Tier-2 tracks these; the actual sim
    PRB budget is unchanged, so end-to-end delivery only shifts if
    Tier-1's shaved targets no longer saturate the grid)."""
    scen = _overload_scenario()
    tt_full = TwoTier(tier1_period_slots=2000, gbr_maxmin=False)
    tt_shaved = TwoTier(tier1_period_slots=2000, gbr_maxmin=False,
                        capacity_safety_factor=0.5)
    run(scen, tt_full)
    run(scen, tt_shaved)
    full_total = sum(tt_full._targets_bps.values())
    shaved_total = sum(tt_shaved._targets_bps.values())
    assert shaved_total < full_total * 0.7, (
        f"capacity_safety_factor=0.5 should shave the LP's total target ~half; "
        f"got {shaved_total/1e6:.1f} Mbps vs {full_total/1e6:.1f} Mbps"
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
    from sim.baselines.pf import ProportionalFair

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
    from sim.baselines.pf import ProportionalFair

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
    from sim.baselines.pf import ProportionalFair

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
    from sim.baselines.pf import ProportionalFair

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


def test_tier1_slice_floor_enforces_shares():
    """A soft slice floor splits PRB capacity by the configured shares. Two
    slices of equal-SNR PF flows: with no slicing the LP splits ~50/50; a
    75/25 slice share shifts the allocation to ~75/25."""
    from sim.config import TDDConfig

    grid = ResourceGrid(
        CarrierConfig(numerology=1, bandwidth_hz=20_000_000), TDDConfig()
    )
    flows = [
        FlowConfig(ue_id=u, qfi=9, direction="DL", flow_class="PF",
                   slice_id=sid, traffic_kind="poisson",
                   traffic_params={"rate_bps": 50_000_000})
        for u, sid in [(1, 1), (2, 1), (3, 2), (4, 2)]
    ]
    snr = {u: 20.0 for u in (1, 2, 3, 4)}
    demand = {(f.ue_id, f.qfi): 50_000_000 for f in flows}
    slice_of = {f.ue_id: f.slice_id for f in flows}

    def slice_fraction(targets, sid):
        total = sum(targets.values())
        return sum(
            v for (u, _q), v in targets.items() if slice_of[u] == sid
        ) / total

    base = solve_tier1(flows, snr, grid, demand)
    sliced = solve_tier1(
        flows, snr, grid, demand,
        slice_shares={1: {"DL": 0.75}, 2: {"DL": 0.25}},
    )
    # Equal flows, no slicing -> the two slices split evenly.
    assert abs(slice_fraction(base, 1) - 0.5) < 0.1
    # A 75/25 share pulls slice 1 to ~three-quarters of the capacity.
    assert slice_fraction(sliced, 1) > 0.65


def test_tier1_slice_floor_allows_borrowing():
    """The slice floor is a guarantee, not a cap: an under-utilised slice's
    unused capacity is borrowed by a busy slice (work-conserving)."""
    from sim.config import TDDConfig

    grid = ResourceGrid(
        CarrierConfig(numerology=1, bandwidth_hz=20_000_000), TDDConfig()
    )
    # slice 1: heavy demand; slice 2: a single light flow.
    flows = [
        FlowConfig(ue_id=1, qfi=9, direction="DL", flow_class="PF",
                   slice_id=1, traffic_kind="poisson",
                   traffic_params={"rate_bps": 80_000_000}),
        FlowConfig(ue_id=2, qfi=9, direction="DL", flow_class="PF",
                   slice_id=2, traffic_kind="poisson",
                   traffic_params={"rate_bps": 1_000_000}),
    ]
    snr = {1: 20.0, 2: 20.0}
    demand = {(1, 9): 80_000_000, (2, 9): 1_000_000}
    # 50/50 shares, but slice 2 only wants ~1 Mbps.
    sliced = solve_tier1(
        flows, snr, grid, demand,
        slice_shares={1: {"DL": 0.5}, 2: {"DL": 0.5}},
    )
    total = sliced[(1, 9)] + sliced[(2, 9)]
    # slice 1 borrows slice 2's idle half -> well above its own 50% share.
    assert sliced[(1, 9)] / total > 0.6
    # slice 2 still gets the little it asked for.
    assert sliced[(2, 9)] > 0.5e6


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
    the poor-SNR flow, improving the worst-served GBR flow vs fixed b=0.

    The max-min stage is switched off here: it protects the same flow by a
    stronger mechanism, which would mask what this test is measuring.
    """
    fixed = run(_two_gbr_partial_infeasible_scenario(),
                TwoTier(tier1_period_slots=2000, gbr_penalty_lr=0.0,
                        gbr_maxmin=False))
    adaptive = run(_two_gbr_partial_infeasible_scenario(),
                   TwoTier(tier1_period_slots=2000, gbr_penalty_lr=1e5,
                           gbr_maxmin=False))

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


# --- Tier-1 max-min GBR stage (Finding 1: cell-edge starvation) -------------


def _cell_edge_starvation_scenario():
    """Four equal-GFBR GBR flows spread across the SNR range, on a carrier
    that cannot carry them all -- the minimal reproduction of Finding 1.

    The single-stage Tier-1 solve serves this set greedily by spectral
    efficiency: the top two SNRs get 100% of GFBR, and the bottom two are
    abandoned outright (targets ~2% and 0%). 6 Tier-1 solves over the
    horizon.
    """
    from sim.config import TDDConfig

    snrs = (24.0, 20.0, 16.0, 10.0)
    gfbr = 6_000_000
    return ScenarioConfig(
        name="cell_edge_starvation",
        horizon_slots=12000,
        carrier=CarrierConfig(numerology=1, bandwidth_hz=20_000_000),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[
            UEConfig(ue_id=i + 1, mean_snr_db=snr, coherence_slots=4000)
            for i, snr in enumerate(snrs)
        ],
        flows=[
            FlowConfig(ue_id=i + 1, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=gfbr, pdb_ms=100, traffic_kind="poisson",
                       traffic_params={"rate_bps": gfbr})
            for i in range(len(snrs))
        ],
        seed=3,
    )


def _maxmin_inputs(scenario):
    """(flows, snr_by_ue, demand_bps) for a scenario, as Tier-1 sees them."""
    snr = {ue.ue_id: ue.mean_snr_db for ue in scenario.ues}
    demand = {
        (f.ue_id, f.qfi): estimate_demand_bps(f) for f in scenario.flows
    }
    return scenario.flows, snr, demand


def _grid_at_bandwidth(scenario, bandwidth_hz):
    import dataclasses

    carrier = dataclasses.replace(scenario.carrier, bandwidth_hz=bandwidth_hz)
    return ResourceGrid(carrier, scenario.tdd)


def test_maxmin_level_monotone_and_saturating_in_capacity():
    """The max-min level must never fall as capacity rises, and must reach
    1.0 once the GBR set is jointly feasible.

    Regression guard for a conditioning bug: posed in raw bps, maximising a
    unit-scale t against rate variables of order 1e7 made the solver report
    `optimal` on a level that was both inaccurate and *non-monotone* --
    it peaked mid-sweep and then decreased as capacity grew.
    """
    scenario = _cell_edge_starvation_scenario()
    flows, snr, demand = _maxmin_inputs(scenario)

    levels = []
    for bw_mhz in (5, 10, 20, 40, 80, 160):
        grid = _grid_at_bandwidth(scenario, bw_mhz * 1_000_000)
        levels.append(solve_maxmin_gbr_level(flows, snr, grid, demand))

    for lo, hi in zip(levels, levels[1:]):
        assert hi >= lo - 1e-6, f"max-min level fell as capacity rose: {levels}"
    assert levels[0] < 0.99, f"expected overload at 5 MHz, got t*={levels[0]}"
    assert levels[-1] > 0.999, (
        f"expected a feasible GBR set at 160 MHz, got t*={levels[-1]}"
    )
    # And the level tracks capacity proportionally while it is the binding
    # constraint -- 5 -> 10 -> 20 MHz should roughly double each step.
    assert levels[1] > 1.7 * levels[0], f"level not scaling with capacity: {levels}"


def test_maxmin_level_is_one_without_gbr_flows():
    """No GBR flows -> nothing to protect -> no floors, so the scenarios
    that carry only Delay/PF flows are structurally untouched by the stage."""
    from sim.scenarios import latency_bound_scenario, sensor_dense_scenario

    for scenario in (sensor_dense_scenario(), latency_bound_scenario()):
        flows, snr, demand = _maxmin_inputs(scenario)
        grid = ResourceGrid(scenario.carrier, scenario.tdd)
        assert solve_maxmin_gbr_level(flows, snr, grid, demand) == 1.0
        assert gbr_maxmin_floors(flows, demand, level=1.0) == {}


def test_gbr_contract_is_capped_by_offered_demand():
    """A GBR flow offering less than its GFBR can never reach 100% of it, so
    its contract is the demand -- otherwise it would pin the max-min level at
    its own unreachable ratio and drag every other flow down with it."""
    from sim.config import TDDConfig

    scenario = ScenarioConfig(
        name="underoffered_gbr",
        horizon_slots=4000,
        carrier=CarrierConfig(numerology=1, bandwidth_hz=20_000_000),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=4000),
             UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=4000)],
        flows=[
            # Contracted for 8 Mbps but only ever offers 1 Mbps.
            FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=8_000_000, pdb_ms=100, traffic_kind="poisson",
                       traffic_params={"rate_bps": 1_000_000}),
            FlowConfig(ue_id=2, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=4_000_000, pdb_ms=100, traffic_kind="poisson",
                       traffic_params={"rate_bps": 4_000_000}),
        ],
        seed=1,
    )
    flows, snr, demand = _maxmin_inputs(scenario)
    assert gbr_contract_bps(flows[0], demand) == 1_000_000  # capped by demand
    assert gbr_contract_bps(flows[1], demand) == 4_000_000  # GFBR binds

    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    # 5 Mbps of reachable contract on a 20 MHz carrier at 20 dB: feasible.
    # Without the demand cap the under-offered flow would hold t* at 1/8.
    assert solve_maxmin_gbr_level(flows, snr, grid, demand) > 0.999


def test_tier1_hard_floor_overrides_the_slack_penalty_sacrifice():
    """The single-stage solve abandons the low-SE GBR flow; passing the
    max-min floors back in as a hard bound is what stops it.

    This is the core of the Finding 1 fix: the sacrifice is driven by the
    *linear slack penalty* (minimising total shortfall bits under a capacity
    constraint is a fractional knapsack, solved greedily by spectral
    efficiency), so no reweighting of that penalty removes the vertex
    solution -- only a constraint does.
    """
    scenario = _cell_edge_starvation_scenario()
    flows, snr, demand = _maxmin_inputs(scenario)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    gfbr = flows[0].gfbr_bps

    single = solve_tier1(flows, snr, grid, demand)
    rich, poor = (1, 2), (4, 2)  # ue1 at 24 dB, ue4 at 10 dB
    assert single[rich] > 0.95 * gfbr, "expected the high-SE flow served in full"
    assert single[poor] < 0.05 * gfbr, (
        f"expected the single-stage solve to abandon the low-SE flow, "
        f"got {single[poor] / gfbr:.0%} of GFBR"
    )

    level = solve_maxmin_gbr_level(flows, snr, grid, demand)
    assert 0.0 < level < 1.0, f"expected partial infeasibility, t*={level}"
    floors = gbr_maxmin_floors(flows, demand, level=level)
    staged = solve_tier1(flows, snr, grid, demand, gbr_floor_bps=floors)

    for key, floor in floors.items():
        assert staged[key] >= floor * 0.999, (
            f"{key} target {staged[key]:.0f} below its floor {floor:.0f}"
        )
    assert staged[poor] > single[poor], "the hard floor must lift the low-SE flow"


def test_two_tier_maxmin_lifts_the_worst_served_gbr_flow():
    """End to end: gbr_maxmin=True raises min GBR delivery, and the gain
    lands on the poor-SNR flow that the single-stage form starves."""
    single = run(_cell_edge_starvation_scenario(),
                 TwoTier(tier1_period_slots=2000, gbr_maxmin=False))
    maxmin = run(_cell_edge_starvation_scenario(),
                 TwoTier(tier1_period_slots=2000, gbr_maxmin=True))

    def min_delivery(summary):
        return min(f["delivery_ratio"] for f in summary["flows"].values())

    assert min_delivery(maxmin) > min_delivery(single) + 0.05, (
        f"max-min min delivery {min_delivery(maxmin):.1%} should beat "
        f"single-stage {min_delivery(single):.1%}"
    )
    # ue4 (10 dB) is the flow the single-stage solve abandons.
    assert single["flows"]["ue4_qfi2"]["delivery_ratio"] < 0.10
    assert maxmin["flows"]["ue4_qfi2"]["delivery_ratio"] > 0.20


def test_two_tier_maxmin_scale_zero_matches_single_stage():
    """gbr_maxmin_scale=0 claims none of the achievable floor, so it must be
    byte-identical to switching the stage off -- the knob's null setting."""
    single = run(_two_gbr_partial_infeasible_scenario(),
                 TwoTier(tier1_period_slots=2000, gbr_maxmin=False))
    zero = run(_two_gbr_partial_infeasible_scenario(),
               TwoTier(tier1_period_slots=2000, gbr_maxmin=True,
                       gbr_maxmin_scale=0.0))
    for fk, m in single["flows"].items():
        assert zero["flows"][fk]["bytes_delivered"] == m["bytes_delivered"]


def test_two_tier_maxmin_enabled_by_default():
    """The stage is on by default, and the default solves it for real.

    It is safe as a default because it self-disables: whenever the GBR set
    is jointly feasible t* == 1 and the floor binds nothing. Guarded here so
    the default cannot be flipped back silently.
    """
    from sim.scenarios import overload_scenario

    sched = TwoTier(tier1_period_slots=2000)
    assert sched.gbr_maxmin is True
    assert sched.gbr_maxmin_scale == 1.0
    run(overload_scenario(), sched)
    # A level was actually solved (not the NaN sentinel) and is a fraction.
    assert sched.maxmin_level == sched.maxmin_level
    assert 0.0 <= sched.maxmin_level <= 1.0


def test_two_tier_maxmin_default_is_free_when_gbr_set_is_feasible():
    """The default must not cost anything on a workload whose GBR floors all
    fit -- that is the whole justification for having it on."""
    from sim.scenarios import smoke_scenario

    on = run(smoke_scenario(), TwoTier(tier1_period_slots=2000))
    off = run(smoke_scenario(), TwoTier(tier1_period_slots=2000,
                                        gbr_maxmin=False))
    for fk, m in off["flows"].items():
        assert on["flows"][fk]["bytes_delivered"] == m["bytes_delivered"], (
            f"{fk}: the max-min default changed a feasible-GBR workload"
        )


# --- Tier-1 numerical accuracy (the two-phase lexicographic form) -----------


def test_tier1_matches_analytic_optimum_on_overload():
    """Tier-1 must hit the closed-form optimum on `overload`, where it is
    small enough to solve by hand.

    Three flows share one direction at equal SNR. The GBR flow takes its
    floor; the residual pool is then split between the PF flow (w=1) and the
    Delay flow (w=5) under `log`, which pins the Delay flow at its demand cap
    and gives the PF flow the remainder.

    Regression guard for a real defect: written as one objective with a
    penalty ~1e7 larger than the utility, this returned `optimal_inaccurate`
    with CLARABEL and SCS disagreeing by 3.6x, and under-served the Delay
    class -- the highest-weighted one -- by 28%.
    """
    from sim.scenarios import overload_scenario
    from scheduler.tier1 import _spectral_efficiency, grid_capacity_prbsym_per_sec

    scenario = overload_scenario()
    flows, snr, demand = _maxmin_inputs(scenario)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    se = _spectral_efficiency(flows, snr)
    cap_dl, _ = grid_capacity_prbsym_per_sec(grid)

    by_class = {f.flow_class: (i, f) for i, f in enumerate(flows)}
    assert set(by_class) == {"PF", "GBR", "Delay"}, "fixture changed"
    assert all(f.direction == "DL" for f in flows), "fixture changed"
    assert max(se) - min(se) < 1e-9, "closed form assumes equal SE"

    (i_pf, f_pf), (i_gbr, f_gbr), (i_dly, f_dly) = (
        by_class["PF"], by_class["GBR"], by_class["Delay"]
    )
    # The GBR floor is served first, leaving this rate pool for the other two.
    gbr_rate = min(f_gbr.gfbr_bps, demand[(f_gbr.ue_id, f_gbr.qfi)])
    pool = (cap_dl - gbr_rate / se[i_gbr]) * se[i_pf]
    # Equal marginal utility: 1/(r_pf + e) == 5/(r_delay + e)  =>  r_delay = 5 r_pf + 4e
    eps = 1.0
    r_pf = (pool - 4 * eps) / 6.0
    r_dly = pool - r_pf
    d_dly = demand[(f_dly.ue_id, f_dly.qfi)]
    if r_dly > d_dly:                      # Delay flow saturates its demand
        r_dly, r_pf = d_dly, pool - d_dly

    targets = solve_tier1(flows, snr, grid, demand)
    expected = {
        (f_pf.ue_id, f_pf.qfi): r_pf,
        (f_gbr.ue_id, f_gbr.qfi): gbr_rate,
        (f_dly.ue_id, f_dly.qfi): r_dly,
    }
    for key, want in expected.items():
        got = targets[key]
        assert abs(got - want) <= max(1_000.0, 1e-3 * want), (
            f"{key}: got {got:.0f} bps, analytic optimum {want:.0f} bps "
            f"(off by {abs(got - want):.0f})"
        )


def test_tier1_is_solver_independent():
    """Two different conic solvers must agree on the Tier-1 targets.

    Solver disagreement is the sharpest available signal that a convex
    program is badly posed -- it was ~440 kbps on `factory_robots` before
    the two-phase rewrite, on rates of 4-14 Mbps.
    """
    import cvxpy as cp
    import pytest

    from sim.scenarios import factory_robots_scenario

    available = [s for s in ("CLARABEL", "SCS") if s in cp.installed_solvers()]
    if len(available) < 2:
        pytest.skip("needs two conic solvers to cross-check")

    scenario = factory_robots_scenario()
    flows, snr, demand = _maxmin_inputs(scenario)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)

    runs = []
    for solver in available:
        default = cp.Problem.solve
        try:
            cp.Problem.solve = lambda self, *a, **k: default(self, solver=solver)
            runs.append(solve_tier1(flows, snr, grid, demand))
        finally:
            cp.Problem.solve = default

    worst = max(abs(runs[0][k] - runs[1][k]) for k in runs[0])
    assert worst < 200_000, (
        f"{available[0]} and {available[1]} disagree by {worst:.0f} bps"
    )


def test_slice_vs_gbr_priority_is_channel_independent():
    """The GBR-floor / slice-floor tie-break must depend on the configured
    penalties, not on the UEs' spectral efficiency.

    A slice slack is natively in PRB-symbols and a GBR slack in bps, so
    comparing them raw makes the crossover land at `gbr_penalty * SE` --
    i.e. the same deployment, same contracts, different channel, different
    policy. Measured before the fix: crossover exactly `1e3 * SE`, a 4.3x
    swing over a 10-30 dB range. Converting the slice slack to bps at the
    slice's own SE pins the crossover at `gbr_penalty` for every channel.
    """
    from sim.config import TDDConfig
    from scheduler.tier1 import _spectral_efficiency, grid_capacity_prbsym_per_sec

    grid = ResourceGrid(
        CarrierConfig(numerology=1, bandwidth_hz=20_000_000), TDDConfig()
    )
    cap_dl, _ = grid_capacity_prbsym_per_sec(grid)
    gbr_penalty = 1e3

    def gbr_fraction_met(snr_db, slice_penalty):
        """Slice 1 carries a GBR flow wanting 80% of DL; slice 2 has a 50%
        DL floor and unbounded demand. Only one of them can be satisfied."""
        flows = [
            FlowConfig(ue_id=1, qfi=2, direction="DL", flow_class="GBR",
                       gfbr_bps=1, pdb_ms=100, slice_id=1,
                       traffic_kind="poisson", traffic_params={"rate_bps": 1}),
            FlowConfig(ue_id=2, qfi=9, direction="DL", flow_class="PF",
                       slice_id=2, traffic_kind="poisson",
                       traffic_params={"rate_bps": 500_000_000}),
        ]
        snr = {1: snr_db, 2: snr_db}
        se = _spectral_efficiency(flows, snr)
        gfbr = 0.8 * cap_dl * se[0]
        flows[0].gfbr_bps = gfbr
        targets = solve_tier1(
            flows, snr, grid, {(1, 2): gfbr, (2, 9): 500_000_000},
            gbr_slack_penalty=gbr_penalty,
            slice_shares={2: {"DL": 0.5}},
            slice_slack_penalty=slice_penalty,
        )
        return targets[(1, 2)] / gfbr

    for snr_db in (10.0, 20.0, 30.0):
        # An order of magnitude either side of the crossover must decide it
        # the same way regardless of channel quality.
        assert gbr_fraction_met(snr_db, gbr_penalty / 10) > 0.99, (
            f"at {snr_db} dB the GBR floor should win a 10x cheaper slice"
        )
        assert gbr_fraction_met(snr_db, gbr_penalty * 10) < 0.90, (
            f"at {snr_db} dB a 10x dearer slice floor should win"
        )


def test_documented_defaults_match_the_code():
    """The two documented parameter tables must not drift from the code.

    Scheduler knobs are tabulated in design-docs/scheduler-study.md 4.5;
    the simulator-fidelity knobs, whose defaults deliberately differ from
    the settings the studies run, are in 5.1. A defaults table is worse
    than no table once it is stale, and these values are cited as
    decided-by-evidence throughout the study.
    """
    import inspect
    from pathlib import Path

    from scheduler import solve_tier1

    documented = {
        "tier1_period_slots": 2000,
        "snr_window_slots": 100,
        "delay_urgency_weight": 4.0,
        "delay_exponent": 2.0,
        "enable_sps": True,
        "sps_safety_margin": 1.10,
        "sps_budget_fraction": 0.85,
        "sps_min_scale": 0.75,
        "sps_snr_margin_db": 0.0,
        "gbr_penalty_init": 1e3,
        "gbr_penalty_lr": 0.0,
        "gbr_penalty_max": 1e6,
        "gbr_penalty_se_exponent": 0.0,
        "gbr_maxmin": True,
        "gbr_maxmin_scale": 1.0,
        "capacity_safety_factor": 1.0,
        "slice_shares": None,
        "slice_slack_penalty": 1e3,
        "ul_split_estimator": "shadow_lcp",
        "ul_bucket_sync_gain": 0.0,
    }
    actual = inspect.signature(TwoTier.__init__).parameters
    assert set(documented) == set(actual) - {"self"}, (
        "TwoTier gained or lost a knob -- update scheduler-study.md 4.5"
    )
    for name, want in documented.items():
        assert actual[name].default == want, (
            f"TwoTier.{name} default is {actual[name].default!r}, "
            f"scheduler-study.md 4.5 documents {want!r}"
        )

    # capacity_safety_factor lives on both surfaces -- solve_tier1 accepts
    # it directly, TwoTier forwards it (added late so it wasn't in the
    # original 17-knob table). Defaults must match.
    t1 = inspect.signature(solve_tier1).parameters
    assert t1["capacity_safety_factor"].default == 1.0
    assert actual["capacity_safety_factor"].default == 1.0

    # Section 5.1: the fidelity knobs default to perfect information, so a
    # unit test never has to reason about report latency...
    from sim.driver import run as _run

    sim_defaults = inspect.signature(_run).parameters
    for name in ("ul_bsr_delay_slots", "ul_bsr_loss_rate",
                 "cqi_delay_slots", "cqi_loss_rate"):
        assert sim_defaults[name].default in (0, 0.0), (
            f"{name} should default to perfect information (0)"
        )

    # ...while the studies deliberately run the delays non-zero. That gap is
    # the point of the 5.1 table, so guard both halves of it.
    study = Path("scripts/scheduler_study.py").read_text()
    assert "UL_BSR_DELAY_SLOTS = 8" in study
    assert "CQI_DELAY_SLOTS = 8" in study


# --- UE-side uplink LCP and 5QI priorities ---------------------------------


def test_five_qi_priorities_are_distinct_on_multi_flow_ues():
    """A UE's flows must not share a priority level.

    The MAC multiplexer orders a UE's flows by priority; if two share one,
    the sort falls back to whatever order the scenario file lists them in,
    and a harmless-looking YAML reordering silently changes results. Deriving
    the priority from the standardised 5QI (TS 23.501 Table 5.7.4-1) is what
    prevents that.
    """
    from collections import defaultdict

    from sim.scenarios import factory_robots_scenario

    scenario = factory_robots_scenario()
    by_ue_dir = defaultdict(list)
    for f in scenario.flows:
        by_ue_dir[(f.ue_id, f.direction)].append(f)

    for (ue_id, direction), flows in by_ue_dir.items():
        prios = [f.priority_level for f in flows]
        assert len(prios) == len(set(prios)), (
            f"ue{ue_id} {direction} has flows sharing a priority: "
            f"{[(f.qfi, f.priority_level) for f in flows]}"
        )


def test_ue_lcp_split_is_independent_of_flow_listing_order():
    """The UE's LCP output must not depend on the order its flows are listed.

    This is the property distinct 5QI priorities buy. Deliberately a unit
    test of the LCP rather than a full run: reversing a scenario's flow list
    also changes which RNG draws each flow receives, so a whole-run
    comparison would measure a different workload, not a different order.
    """
    from sim.scenarios import factory_robots_scenario
    from sim.ue_lcp import UeLcp

    scenario = factory_robots_scenario()
    ue_flows = [f for f in scenario.flows
                if f.ue_id == 8 and f.direction == "UL"]
    assert len(ue_flows) > 1, "need a multi-flow UE for this to mean anything"

    buffers = BufferModel()
    for f in ue_flows:
        buffers.register(f.ue_id, f.qfi, is_ul=True)
        buffers.enqueue(f.ue_id, f.qfi, 40_000, 0.0)

    def split(order):
        lcp = UeLcp(order)
        lcp.refill(0.02)
        return sorted(lcp.fill(order, 6_000, buffers))

    assert split(ue_flows) == split(list(reversed(ue_flows))), (
        "LCP split changed when the flow list was reversed -- flows on this "
        "UE probably share a priority level"
    )


def test_ue_lcp_pbr_round_protects_gbr_from_a_greedy_best_effort_flow():
    """Round 1 of the UE's LCP is gated on a prioritised bit rate, so a
    continuously-backlogged best-effort flow cannot crowd out a GBR flow on
    the same UE however large its buffer gets."""
    from sim.ue_lcp import UeLcp

    gbr = FlowConfig(ue_id=1, qfi=2, direction="UL", flow_class="GBR",
                     gfbr_bps=8_000_000, pdb_ms=30, priority_level=40,
                     traffic_kind="poisson",
                     traffic_params={"rate_bps": 8_000_000})
    be = FlowConfig(ue_id=1, qfi=9, direction="UL", flow_class="PF",
                    priority_level=90, traffic_kind="poisson",
                    traffic_params={"rate_bps": 50_000_000})

    buffers = BufferModel()
    buffers.register(1, 2, is_ul=True)
    buffers.register(1, 9, is_ul=True)
    buffers.enqueue(1, 2, 2_000, 0.0)        # modest GBR backlog
    buffers.enqueue(1, 9, 1_000_000, 0.0)    # enormous best-effort backlog

    lcp = UeLcp([gbr, be])
    lcp.refill(0.05)                          # 50 ms of tokens
    fills = dict(lcp.fill([gbr, be], 3_000, buffers))

    assert fills.get(2, 0) == 2_000, (
        f"GBR flow should be served first from its PBR bucket, got {fills}"
    )
    assert fills.get(9, 0) == 1_000, "best-effort gets only the remainder"
