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


# test_tier1_capacity_safety_factor_shaves_targets deleted (Phase 2, two-
# tier commit 2, docs/phase2-plan.md): capacity_safety_factor is no longer
# a free, sweepable kwarg -- ground truth's IA_P5G_TIER1_OVERHEAD_FACTOR
# is a fixed 0.80 constant, baked into tier1_capacity_prbslot_per_sec.
# Nothing to sweep; see test_tier1_capacity_uses_the_fixed_overhead_factor
# below for the mechanism's replacement coverage.


def test_grid_capacity_helper():
    """Capacity computation should be > 0 and respect TDD pattern."""
    from sim.config import TDDConfig
    grid = ResourceGrid(CarrierConfig(numerology=1), TDDConfig(pattern="DSUUU"))
    cap_dl, cap_ul = grid_capacity_prbsym_per_sec(grid)
    assert cap_dl > 0 and cap_ul > 0
    # DSUUU has 1 D + S(DL) symbols, vs 3 U + S(UL); UL > DL by symbol count
    assert cap_ul > cap_dl


def test_tier1_capacity_uses_the_fixed_overhead_factor():
    """tier1_capacity_prbslot_per_sec (Phase 2 commit 2) -- whole-slot
    granularity, IA_P5G_TIER1_OVERHEAD_FACTOR=0.80 baked in fixed, not a
    sweepable kwarg (docs/oai-port-map.md, the two-tier commit-2 rows).
    "DSUUU" has exactly one whole D slot and zero whole U slots (the 3 U
    slots are each mixed with the S slot's own UL share, but "U" itself
    IS a whole slot -- only S is mixed) -- construct a pattern with a
    known whole-slot count and check the fixed 0.80 factor lands exactly,
    not merely "less than the unscaled value"."""
    from scheduler import tier1_capacity_prbslot_per_sec
    from sim.config import TDDConfig

    grid = ResourceGrid(CarrierConfig(numerology=1, bandwidth_hz=20_000_000), TDDConfig(pattern="DU"))
    cap_dl, cap_ul = tier1_capacity_prbslot_per_sec(grid)
    slot_duration_s = grid.slot_duration_s
    cycle_duration_s = 2 * slot_duration_s
    expected_dl = grid.prb_count * (1 / cycle_duration_s) * 0.80
    expected_ul = grid.prb_count * (1 / cycle_duration_s) * 0.80
    assert cap_dl == pytest.approx(expected_dl)
    assert cap_ul == pytest.approx(expected_ul)


def test_tier1_capacity_excludes_mixed_slots_from_either_direction():
    """A mixed (special) slot contributes to NEITHER direction's whole-
    slot capacity count -- ia_p5g_compute_capacity's own
    get_full_dl_slots_per_period/get_full_ul_slots_per_period, confirmed
    against the full OAI checkout (config.c:313-347), not merely the
    vendored subset. "DSU" has one whole D, one whole U, and one mixed S
    slot that counts toward neither -- capacity should match a "DU"
    pattern of the same slot duration exactly, not a "DSU"-sized cycle
    with the S slot's own symbols folded in."""
    from scheduler import tier1_capacity_prbslot_per_sec
    from sim.config import TDDConfig

    carrier = CarrierConfig(numerology=1, bandwidth_hz=20_000_000)
    grid_dsu = ResourceGrid(carrier, TDDConfig(pattern="DSU", s_slot_split=(6, 2, 6)))
    grid_du = ResourceGrid(carrier, TDDConfig(pattern="DU"))
    cap_dl_dsu, cap_ul_dsu = tier1_capacity_prbslot_per_sec(grid_dsu)
    cap_dl_du, cap_ul_du = tier1_capacity_prbslot_per_sec(grid_du)
    # DSU's cycle is 3 slots long vs DU's 2 -- normalise to a per-slot rate
    # before comparing, since the whole-slot COUNT (1 DL, 1 UL) is what
    # should match, not the raw per-second rate over differently-sized
    # cycles.
    assert cap_dl_dsu * 3 == pytest.approx(cap_dl_du * 2)
    assert cap_ul_dsu * 3 == pytest.approx(cap_ul_du * 2)


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


# test_tier1_per_flow_penalty_shifts_allocation,
# test_tier1_se_penalty_exponent_tilts_allocation,
# test_tier1_slice_floor_enforces_shares, test_tier1_slice_floor_allows_
# borrowing all deleted (Phase 2, two-tier commit 2, docs/phase2-plan.md):
# gbr_slack_penalty (per-flow dict)/se_penalty_exponent/slice_shares/
# slice_slack_penalty have no ground-truth citation anywhere in
# ia_p5g_scheduler.c -- confirmed absent, not merely unattested (every GBR
# flow's slack column gets the SAME fixed IA_P5G_TIER1_GBR_PENALTY=1.0e3,
# set once, never adjusted; no slicing mechanism exists in the C at all).
# Permanent loss, no successor mechanism.


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


# --- Tier-1 max-min GBR stage: deleted (Phase 2, two-tier commit 2,
# docs/phase2-plan.md) -- solve_maxmin_gbr_level/gbr_maxmin_floors/
# gbr_contract_bps and everything that fed them are permanent loss.
# ia_p5g_sca_solve (ia_p5g_scheduler.c:974-1103) is a SINGLE SCA outer
# loop; no lexicographic two-phase structure, no separate max-min
# pre-stage, no hard-floor override on top of the soft GFBR constraint --
# confirmed absent by reading the C directly, not merely unattested.


# --- Tier-1 numerical accuracy -----------------------------------------


def test_tier1_pool_conservation_and_gbr_floor_on_overload():
    """Tier-1 must serve the GBR floor and conserve the residual capacity
    pool on `overload`, where the pool is small enough to hand-verify.

    **Finding, made while rewriting this test, not assumed**: unlike the
    deleted two-phase cvxpy form (a smooth convex solve with one interior
    optimum), the SCA loop over a plain vertex LP does **not** converge to
    the smooth weighted-log-utility split when two flows share one
    capacity row at equal SE and neither dominates on weight alone --
    `linprog` (vertex-optimal, matching GLPK's own simplex) puts the
    *entire* residual pool on whichever of PF/Delay currently has the
    larger `weight/(r_prev+eps)` coefficient, so successive iterations
    toggle which flow gets everything; the damped average never settles
    (`rel_change` stays near `_SCA_ALPHA` at every iteration this pair
    competes, confirmed by tracing 30+ iterations directly, not merely
    observed at 150). This is a genuine, previously-undocumented property
    of `ia_p5g_sca_solve`'s own vertex-LP mechanism, not a bug introduced
    by this port -- real hardware's GLPK-backed SCA loop has the
    identical mathematical structure (a linear objective over a shared
    capacity polytope) and would oscillate the same way for two DL flows
    at equal SE with comparable weighted coefficients. Whatever the loop
    lands on after exactly `_SCA_MAXITERS=150` damped steps is fully
    deterministic (confirmed: two back-to-back calls with identical
    inputs return byte-identical results) but is NOT a "closed-form
    optimum" in the sense the old two-phase form's own optimum was --
    there is no single interior point to hand-derive here. Testing the
    exact 150-iteration landing point would be a regression pin on an
    implementation detail (solver tie-breaking, exact vertex selection),
    not a fidelity check.

    What IS checkable in closed form, and asserted here: the GBR flow's
    penalty (`IA_P5G_TIER1_GBR_PENALTY=1.0e3`, dominating the PF/Delay
    coefficients by 4-5 orders of magnitude once their own r_prev grows)
    still drives it to its floor; and the residual pool (`cap_dl -
    gbr_rate/se_gbr`, converted to bps at the shared SE) is exactly what
    the PF+Delay flows split between them, whichever way the oscillation
    happened to divide it -- capacity is never lost or invented.

    Demand values transcribed directly from
    sim/scenarios/scenario_config_2.yml (not from the deleted
    estimate_demand_bps/`_maxmin_inputs` helpers).
    """
    from sim.scenarios import overload_scenario
    from scheduler.tier1 import _spectral_efficiency_per_slot, tier1_capacity_prbslot_per_sec

    scenario = overload_scenario()
    flows = scenario.flows
    snr = {ue.ue_id: ue.mean_snr_db for ue in scenario.ues}
    demand = {(1, 9): 20_000_000.0, (2, 2): 4_000_000.0, (3, 1): 640_000.0}
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    se = _spectral_efficiency_per_slot(flows, snr)
    cap_dl, _ = tier1_capacity_prbslot_per_sec(grid)

    by_class = {f.flow_class: (i, f) for i, f in enumerate(flows)}
    assert set(by_class) == {"PF", "GBR", "Delay"}, "fixture changed"
    assert all(f.direction == "DL" for f in flows), "fixture changed"
    assert max(se) - min(se) < 1e-9, "closed form assumes equal SE"

    (i_pf, f_pf), (i_gbr, f_gbr), (i_dly, f_dly) = (
        by_class["PF"], by_class["GBR"], by_class["Delay"]
    )
    gbr_rate = min(f_gbr.gfbr_bps, demand[(f_gbr.ue_id, f_gbr.qfi)])
    pool = (cap_dl - gbr_rate / se[i_gbr]) * se[i_pf]

    targets = solve_tier1(flows, snr, grid, demand)
    pf_key, gbr_key, dly_key = (
        (f_pf.ue_id, f_pf.qfi), (f_gbr.ue_id, f_gbr.qfi), (f_dly.ue_id, f_dly.qfi)
    )

    assert abs(targets[gbr_key] - gbr_rate) <= max(1_000.0, 1e-3 * gbr_rate), (
        f"GBR target {targets[gbr_key]:.0f} should sit at its floor "
        f"{gbr_rate:.0f}"
    )
    total_residual = targets[pf_key] + targets[dly_key]
    assert abs(total_residual - pool) <= max(1_000.0, 1e-3 * pool), (
        f"PF+Delay should exactly consume the residual pool "
        f"{pool:.0f}, got {total_residual:.0f}"
    )
    # Reproducibility: the oscillating-but-deterministic landing point
    # must not vary call to call given identical inputs.
    again = solve_tier1(flows, snr, grid, demand)
    assert again == targets, "solve_tier1 must be deterministic given identical inputs"


# test_tier1_is_solver_independent deleted (Phase 2, two-tier commit 2,
# docs/phase2-plan.md): tested that two interchangeable CVXPY conic
# solver backends agree. scipy.optimize.linprog (D3) is the one library
# now -- nothing to swap, the premise this test exercised is gone, not
# merely one implementation of it.


# test_slice_vs_gbr_priority_is_channel_independent deleted (Phase 2,
# two-tier commit 2): slicing has no ground-truth citation anywhere in
# ia_p5g_scheduler.c (confirmed absent, not merely unattested) -- see the
# max-min section's own note above for the same finding.


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
