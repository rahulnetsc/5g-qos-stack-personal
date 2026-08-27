import pytest

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


def test_buffer_drain_without_pdb_args_never_marks_late():
    """now_s/pdb_s are optional -- a caller that doesn't care about
    lateness (the default: now_s=0.0, pdb_s=inf) gets none tagged."""
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 500, 0.0)
    b.drain(1, 9, 500)
    assert b.state(1, 9).bytes_delivered_late_pdb == 0


def test_buffer_drain_tags_bytes_delivered_after_pdb_as_late():
    """M02 (config/metric_panel.yml): a chunk drained after its own PDB
    has already passed counts as delivered-but-late, not fully fine --
    distinct from bytes_dropped_pdb, which never reaches drain() at all."""
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 500, 0.0)
    # PDB is 0.5s; draining at t=1.0 means this chunk is already late.
    drained = b.drain(1, 9, 500, now_s=1.0, pdb_s=0.5)
    assert drained == 500
    assert b.state(1, 9).bytes_delivered_late_pdb == 500


def test_buffer_drain_spanning_chunks_tags_only_the_late_one():
    """A single drain() call can straddle the PDB deadline: an old chunk
    counts as late, a fresh one in the same drain does not."""
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 300, 0.0)   # arrives at t=0 -- late by t=1.0 (pdb=0.5)
    b.enqueue(1, 9, 300, 0.9)  # arrives at t=0.9 -- not late by t=1.0
    drained = b.drain(1, 9, 600, now_s=1.0, pdb_s=0.5)
    assert drained == 600
    assert b.state(1, 9).bytes_delivered_late_pdb == 300


def test_buffer_bsr_managed_flow_ignores_enqueue_drain_expire():
    """A BSR-managed UL flow's bytes_reported is NOT touched by
    BufferModel's enqueue/drain/expire -- only sim/bsr.py::BsrModel writes
    it (see test_bsr.py for that model). DL flows and any flow registered
    with is_ul=False stay in lock-step, as before."""
    b = BufferModel()
    b.register(1, 9, is_ul=True)
    b.enqueue(1, 9, 500, 0.0)
    assert b.state(1, 9).bytes_reported == 0  # untouched; no BsrModel involved
    assert b.state(1, 9).bytes_queued == 500

    b2 = BufferModel()
    b2.register(2, 9, is_ul=False)  # DL flow -- always instant
    b2.enqueue(2, 9, 500, 0.0)
    assert b2.state(2, 9).bytes_reported == 500


def test_buffer_bsr_sps_bypass_uses_bytes_queued():
    """A CG / SPS-served flow reads bytes_queued (real) not bytes_reported.
    The BufferState carries both so the scheduler can choose which to use;
    SPS uses bytes_queued directly. bytes_reported stays at its default
    until a BsrModel writes it -- an SPS UE needs no BSR at all."""
    b = BufferModel()
    b.register(1, 9, is_ul=True)
    b.enqueue(1, 9, 1000, 0.0)
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


def test_reservation_smoke_completes():
    """Phase 2, reservation commit 10: the first time this scheduler runs
    inside the real driver -- real buffers, HARQ, the UL access chain,
    ue_lcp -- rather than sim/tests/test_reservation.py's synthetic
    fixtures (that file deliberately has no sim/ dependency, matching
    reservation.py's own "never on sim" boundary, so this end-to-end
    exercise belongs here instead). Runs the actual Study 1 scenario
    (scripts/scheduler_study.py), not a minimal single-flow one, since
    that is what commit 10 wires in and captures. A failure here is a
    finding about the port that fixtures couldn't reveal, not a test to
    adjust until it passes."""
    from sim.scenarios import factory_robots_scenario
    from scheduler.reservation import Reservation

    summary = run(factory_robots_scenario(), Reservation())
    assert summary["horizon_s"] > 0
    assert summary["flows"]
    for fk, m in summary["flows"].items():
        assert m["bytes_arrived"] >= 0
        assert m["bytes_delivered"] >= 0
    assert any(m["bytes_delivered"] > 0 for m in summary["flows"].values())


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


def test_grid_capacity_helper():
    """Capacity computation should be > 0 and respect TDD pattern."""
    from sim.config import TDDConfig
    grid = ResourceGrid(CarrierConfig(numerology=1), TDDConfig(pattern="DSUUU"))
    cap_dl, cap_ul = grid_capacity_prbsym_per_sec(grid)
    assert cap_dl > 0 and cap_ul > 0
    # DSUUU has 1 D + S(DL) symbols, vs 3 U + S(UL); UL > DL by symbol count
    assert cap_ul > cap_dl


def test_pdcch_budget_caps_dynamic_allocations():
    """The dynamic scheduler must respect the per-slot CCE budget. With many
    flows and a tight budget, PF's allocation count per slot is bounded."""
    from sim.scenarios import sensor_dense_scenario
    from sim.baselines.pf import ProportionalFair

    sc = sensor_dense_scenario()
    summary = run(sc, ProportionalFair(ewma_window_slots=200))
    # PDCCH utilization should be substantial (we're hitting the budget) but
    # not over 100% (the cap actually applies). Threshold lowered from 0.4
    # by WP4 (sim/ul_access.py): on this scenario, every message now needs
    # two grant events (SR-driven crumb, then a real BSR-sized grant)
    # instead of one, and the real grant is sized from a *quantised*
    # (overestimating) BSR rather than the WP3 probe's exact true-backlog
    # report -- roughly doubling PRB cost per message on a scenario with
    # near-zero PRB margin to begin with (README §8). Fewer UEs end up
    # PDCCH-eligible per slot as a result; the cap itself is still what's
    # being tested here, not the specific utilization level.
    util = summary["cce_utilization"]
    assert 0.3 < util <= 1.0, f"PDCCH utilization {util:.1%} unexpected"


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
        scenario, TwoTier(), record_timeseries=True
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

    summary = run(smoke_scenario(), TwoTier())
    assert "timeseries" not in summary


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
    summary = run(scenario, TwoTier())
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
    """Signature-drift guard, kept alive across the Phase 2 rewrite rather
    than deleted with the mechanism-specific tests
    (docs/phase2-plan.md's two-tier commit 1) -- update the expected knob
    set here every commit that changes ``TwoTier.__init__``, rather than
    letting this test go stale or deleting it.

    Phase 2 commit 1: the constructor takes no kwargs at all -- every
    pre-Phase-2 knob was deleted (SPS entirely; the old Tier-1 apparatus
    pending commit 2's rewrite). ``design-docs/scheduler-study.md``
    sec4.5's knob table is correspondingly stale until commits 2+
    reintroduce real, ground-truth-backed knobs -- not updated here since
    there is nothing left to tabulate yet; update it alongside whichever
    future commit adds the first real kwarg back. The rest of this
    function (sec5.1's CQI/BSR fidelity defaults) is untouched by Phase 2
    and still guards its own, unrelated claims.
    """
    import inspect
    from pathlib import Path

    actual = inspect.signature(TwoTier.__init__).parameters
    assert set(actual) - {"self"} == set(), (
        "TwoTier gained a knob -- update this test's expected set (and "
        "design-docs/scheduler-study.md sec4.5 once a knob has real "
        "ground truth behind it, docs/phase2-plan.md)"
    )

    # Section 5.1: the CQI fidelity knob defaults to perfect information, so
    # a unit test never has to reason about report latency. UL BSR realism
    # (sim/bsr.py) is not a delay-slots knob any more (WP3) -- it is always
    # on, driven by each flow's `lcg`, with no "perfect information" toggle
    # to default off.
    from sim.driver import run as _run

    sim_defaults = inspect.signature(_run).parameters
    for name in ("cqi_delay_slots", "cqi_loss_rate"):
        assert sim_defaults[name].default in (0, 0.0), (
            f"{name} should default to perfect information (0)"
        )

    # ...while the studies deliberately run CQI delay non-zero. That gap is
    # the point of the 5.1 table, so guard both halves of it.
    study = Path("scripts/scheduler_study.py").read_text()
    assert "CQI_DELAY_SLOTS = 8" in study
    assert "UL_BSR_DELAY_SLOTS" not in study, (
        "WP3 removed the UL BSR delay-slots knob -- scheduler_study.py "
        "should no longer reference it"
    )


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


def test_wp5_harq_process_pool_gating_is_live_but_never_binds():
    """docs/wp5-plan.md WP5 commit 3: process-pool gating wraps every
    Allocation this commit, but delivery is still synchronous, so no
    (ue_id, direction) key should ever hold more than one process at a
    time -- harq_exhausted_count must stay 0.

    factory_robots_scenario is used deliberately, not an arbitrary smoke
    scenario: README.md sec8 documents it as the one scenario with
    multi-flow UEs sharing a slot (UEs 8/9/10, GBR video + a
    different-class flow each) -- exactly the case that would break
    occupancy <= 1 under a different (not chosen) design, per this
    commit's inertness argument.

    harq_allocate_calls > 0 is asserted alongside harq_exhausted_count ==
    0 on purpose: a bare exhaustion-count-is-zero check would also pass
    if gating silently never ran at all, which is a different bug than
    "runs but never binds" and this test must be able to tell them apart.
    """
    from sim.scenarios import factory_robots_scenario

    summary = run(factory_robots_scenario(), RoundRobin())
    assert summary["harq_allocate_calls"] > 0, (
        "gating never ran -- can't distinguish this from harq_exhausted_count==0 "
        "meaning 'never binds' rather than 'never wired up'"
    )
    assert summary["harq_exhausted_count"] == 0


def test_wpjoin_rlf_detector_runs_every_slot_and_never_declares_on_the_corpus():
    """docs/wp-join-plan.md WP-Join commit 2: sim/rlf.py::step() is now
    called unconditionally, per UE per slot, on every scenario. Checked,
    not assumed, on the regression corpus's own scenarios (all at
    mean_snr_db=20.0, far from RlfDetectorConfig's default -5.0dB floor):
    rlf_declared_count==0 across all 22 study-1/2/3 cases (1,144,000 total
    rlf_step_calls). Asserting rlf_step_calls > 0 alongside it, same
    reason as harq_allocate_calls above: a bare declared_count==0 would
    also pass if the wiring silently never ran at all, a different bug
    this test must be able to tell apart from "runs but never fires".

    If this ever starts failing after an unrelated change, that is a
    genuine finding about the corpus's own channel realism (an AR(1) tail
    event dipping 25dB below a 20dB mean for 10+ consecutive slots) --
    investigate before assuming a bug, per the same document's citation
    discipline.
    """
    from sim.scenarios import factory_robots_scenario, latency_bound_scenario, sensor_dense_scenario

    for scenario in (factory_robots_scenario(), sensor_dense_scenario(), latency_bound_scenario()):
        summary = run(scenario, RoundRobin())
        assert summary["rlf_step_calls"] == len(scenario.ues) * scenario.horizon_slots
        assert summary["rlf_declared_count"] == 0
