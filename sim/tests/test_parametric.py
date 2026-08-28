"""Tests for sim/parametric.py -- WP9's sweep-scenario factory
(`docs/wp9-plan.md` build item B4).
"""

import itertools

import pytest

from sim.parametric import MIXES, sweep_scenario


def test_defaults_are_the_base_point():
    """`sweep_scenario(seed=s)` with nothing else IS docs/wp9-plan.md §1's
    base point, so every excursion is one keyword away from it."""
    sc = sweep_scenario(seed=1)
    assert len(sc.ues) == 8
    assert sc.horizon_slots == 20_000
    assert sc.carrier.numerology == 2
    assert sc.tdd.pattern == "DSUUU"
    assert "load1.0" in sc.name


@pytest.mark.parametrize("n_ues,mix,bg,shared_lcg,duty,spread", [
    (n, m, b, s, d, sp)
    for n, m, b, s, d, sp in itertools.product(
        (1, 2, 8), MIXES, (False, True), (False, True), (1.0, 0.1), (0.0, 12.0)
    )
])
def test_no_flow_key_collision_across_axis_combinations(
    n_ues, mix, bg, shared_lcg, duty, spread
):
    """A flow is keyed by (ue_id, qfi) with NO direction term
    (`sim/run_record.py::flow_key`), so two flows of one UE sharing a 5QI
    collide and one silently disappears from every metric.

    This bit once, for real: following the hardware plan's "T2 commands ride
    the T1 bearer in reverse", the DL command flow was given 5QI 1 alongside
    the UL telemetry flow, and a base scenario reported 6 of its 8 flows.
    The `bg` aggressor had the same collision against the per-UE 5QI-9
    filler. Both are fixed by construction (5QI 82 and 5QI 8), and this test
    covers the axis grid rather than the one combination that happened to
    be noticed -- a collision that only appears at, say, video_heavy+bg
    would be just as silent.
    """
    sc = sweep_scenario(
        seed=1, n_ues=n_ues, mix=mix, bg=bg, shared_lcg=shared_lcg,
        duty_cycle=duty, snr_spread_db=spread, horizon_slots=200,
    )
    keys = [(f.ue_id, f.qfi) for f in sc.flows]
    assert len(keys) == len(set(keys)), f"colliding flow keys: {sorted(keys)}"


def test_burstify_holds_mean_rate_constant():
    """H2's duty-cycle axis must not smuggle in a load change, or a
    "burstiness regime" could just be the load axis in disguise."""
    full = sweep_scenario(seed=1, duty_cycle=1.0, horizon_slots=200)
    bursty = sweep_scenario(seed=1, duty_cycle=0.1, horizon_slots=200)

    def rate(sc, qfi, key_bytes):
        f = next(f for f in sc.flows if f.qfi == qfi)
        p = f.traffic_params
        return p[key_bytes] / p["period_ms"]

    assert rate(full, 1, "bytes_per_period") == pytest.approx(
        rate(bursty, 1, "bytes_per_period"))
    assert rate(full, 2, "avg_bytes") == pytest.approx(
        rate(bursty, 2, "avg_bytes"))
    # ...and it really is burstier, not merely unchanged.
    assert (next(f for f in bursty.flows if f.qfi == 1).traffic_params["period_ms"]
            > next(f for f in full.flows if f.qfi == 1).traffic_params["period_ms"])


def test_load_mult_scales_the_filler_not_the_instruments():
    """§1.2: the GBR/Delay flows are INSTRUMENTS held at fixed profile rates
    (their KPIs are what G1/G3/G5 read); load_mult scales the best-effort
    filler only. If load_mult ever moved an instrument, the load axis would
    be changing the quantity being measured."""
    a = sweep_scenario(seed=1, load_mult=1.0, horizon_slots=200)
    b = sweep_scenario(seed=1, load_mult=3.0, horizon_slots=200)
    for qfi in (1, 2, 82):
        fa = next(f for f in a.flows if f.qfi == qfi)
        fb = next(f for f in b.flows if f.qfi == qfi)
        assert fa.traffic_params == fb.traffic_params, f"instrument {qfi} moved"
    ba = next(f for f in a.flows if f.qfi == 9)
    bb = next(f for f in b.flows if f.qfi == 9)
    assert bb.traffic_params["rate_bps"] == pytest.approx(
        3.0 * ba.traffic_params["rate_bps"])


def test_mfbr_multiple_sets_mfbr_only_on_gbr_flows():
    sc = sweep_scenario(seed=1, mfbr_multiple=2.0, horizon_slots=200)
    gbr = [f for f in sc.flows if f.flow_class == "GBR"]
    assert gbr and all(f.mfbr_bps == 2.0 * f.gfbr_bps for f in gbr)
    assert all(f.mfbr_bps == 0.0 for f in sc.flows if f.flow_class != "GBR")


def test_shared_lcg_forces_one_lcg_via_explicit_override():
    """H5 is reached through an explicit per-flow `lcg`, NOT by changing
    FIVE_QI_LCG -- that mapping is invented with nothing to validate it
    (README §8), so WP9 routes around the open item rather than appearing
    to settle it."""
    off = sweep_scenario(seed=1, shared_lcg=False, horizon_slots=200)
    on = sweep_scenario(seed=1, shared_lcg=True, horizon_slots=200)
    ul_off = {f.lcg for f in off.flows if f.direction == "UL" and f.qfi in (1, 2)}
    ul_on = {f.lcg for f in on.flows if f.direction == "UL" and f.qfi in (1, 2)}
    assert len(ul_on) == 1
    assert len(ul_off) > 1


def test_unknown_mix_and_inf_scenario_raise():
    with pytest.raises(ValueError):
        sweep_scenario(seed=1, mix="nope")
    with pytest.raises(ValueError):
        sweep_scenario(seed=1, inf_scenario="XX")


def test_ignores_non_scenario_axis_values():
    """min_rb is arm-config and sr_period_slots/k2_slots are driver kwargs;
    the same axis_values dict is passed to all three consumers."""
    sc = sweep_scenario(seed=1, min_rb=20, sr_period_slots=40, k2_slots=1,
                        horizon_slots=200)
    assert len(sc.ues) == 8
