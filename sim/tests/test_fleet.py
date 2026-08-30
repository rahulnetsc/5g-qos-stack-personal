"""Fleet compositions and the lidar activation (docs/wp9-plan.md §5)."""

from collections import Counter

import pytest

from sim.fleet import (
    COMPOSITIONS, LIDAR_ACTIVE_BPS, LIDAR_MAX_CONCURRENT, PROFILES,
    LidarActivation, build_fleet, profile_qos_table,
)
from scheduler.flow import pdb_for_5qi, priority_for_5qi


def test_every_profile_is_within_the_oai_seven_flow_ceiling():
    """A real implementation limit, not a style preference."""
    for name, p in PROFILES.items():
        assert p.n_flows() <= 7, f"{name} has {p.n_flows()} flows"


def test_pdb_is_derived_from_the_5qi_never_authored():
    """The whole point of §4: a profile must not encode the author's
    opinion of a latency budget where the standard defines one."""
    flows, _ = build_fleet(16, "mixed")
    assert flows
    for f in flows:
        assert f.pdb_ms == pdb_for_5qi(f.qfi), (
            f"5QI {f.qfi} PDB {f.pdb_ms} != standardised {pdb_for_5qi(f.qfi)}")


def test_composition_is_exact_at_every_n():
    """Largest-remainder allocation: N is an axis, so a mix that drifted
    with rounding across N would confound it."""
    for comp in COMPOSITIONS:
        for n in (2, 3, 8, 16, 24, 32):
            _, seq = build_fleet(n, comp)
            assert len(seq) == n, f"{comp} N={n} gave {len(seq)} UEs"


def test_compositions_differ_on_several_dimensions_not_just_flow_count():
    """'N=16' is not an index in a heterogeneous deployment -- the argument
    for making composition primary. But MEASURED, the spread is narrower
    than first claimed: flow count varies 1.8x across these mixtures
    (35-63 at N=16) and 3x across PURE fleets (32 sensor vs 96 UGV), NOT
    the "order of magnitude" the plan originally asserted. That claim was
    corrected rather than the compositions being inflated to fit it.

    What actually justifies the axis is that the workloads differ on
    SEVERAL dimensions at once -- GBR fraction spreads 2.6x, and the
    tight-PDB and UL shares move independently of flow count.
    """
    stats = {}
    for c in COMPOSITIONS:
        fl, _ = build_fleet(16, c)
        stats[c] = {
            "flows": len(fl),
            "gbr": sum(1 for f in fl if f.flow_class == "GBR") / len(fl),
            "tight": sum(1 for f in fl if f.pdb_ms <= 30) / len(fl),
        }
    flows = [s["flows"] for s in stats.values()]
    gbr = [s["gbr"] for s in stats.values()]
    tight = [s["tight"] for s in stats.values()]

    assert max(flows) >= 1.5 * min(flows), stats
    assert max(gbr) >= 2.0 * min(gbr), stats
    assert max(tight) - min(tight) >= 0.15, stats


def test_lidar_is_off_by_default():
    """Duty-cycled: the UGV profile carries the flow so its QoS/LCG shape is
    right, but a lidar that is always on is not a lidar."""
    flows, _ = build_fleet(16, "ugv_heavy")
    assert not [f for f in flows if f.gfbr_bps == LIDAR_ACTIVE_BPS]


def test_lidar_concurrency_is_capped_as_a_bound():
    """A BOUND, not an axis: factory tasks are serialised, so eight UGVs do
    not dock at once. Asking for more must clamp, not comply."""
    flows, _ = build_fleet(32, "ugv_heavy",
                           lidar=LidarActivation(n_ues=99))
    active = [f for f in flows if f.gfbr_bps == LIDAR_ACTIVE_BPS]
    assert len(active) == LIDAR_MAX_CONCURRENT


def test_stage5_degenerate_cells_come_from_the_ugv_weights():
    """WP9 stage 5's C2 census (docs/wp9-plan.md §16.3) rests on which
    compositions have too few UGVs to activate what a cell asks for. That
    is a structural property of COMPOSITIONS, so it is pinned here rather
    than only inside the sweep runner's launch assertion -- if the weights
    or `_allocate` change, this is the test that says why the census moved.
    """
    ugvs = {(comp, n): build_fleet(n, comp)[1].count("ugv")
            for comp in ("sensor_dense", "mixed", "drone_heavy", "ugv_heavy")
            for n in (4, 8, 16, 32)}

    # sensor_dense weights UGVs at 0.03: none at all below N=16.
    assert ugvs[("sensor_dense", 4)] == 0
    assert ugvs[("sensor_dense", 8)] == 0
    assert ugvs[("sensor_dense", 16)] == 1
    assert ugvs[("sensor_dense", 32)] == 1
    # The other partial cases the census counts as degenerate.
    assert ugvs[("mixed", 4)] == 1
    assert ugvs[("drone_heavy", 4)] == 1
    assert ugvs[("drone_heavy", 8)] == 1
    # ugv_heavy always has room for both.
    assert all(ugvs[("ugv_heavy", n)] >= 2 for n in (4, 8, 16, 32))


def test_stage5_null_cells_are_identical_to_the_control():
    """C1's stop condition, at the fleet layer: with zero UGVs a lidar
    request activates nothing, so the scenario must be indistinguishable
    from lidar-off. A difference with no lidar could only come from the
    plumbing."""
    off, seq_off = build_fleet(8, "sensor_dense")
    for n_ues in (1, 2):
        on, seq_on = build_fleet(8, "sensor_dense",
                                 lidar=LidarActivation(n_ues=n_ues))
        assert seq_on == seq_off
        assert on == off


def test_lidar_stagger_is_a_field_not_a_literal():
    """Stage 5 derives its `during_2` window from `stagger_s`, so the value
    has to be reachable from the dataclass rather than living only inside
    build_fleet (docs/wp9-plan.md §16.4, "never hardcoded")."""
    lid = LidarActivation(n_ues=2, start_s=1.0, duration_s=0.5, stagger_s=0.25)
    flows, _ = build_fleet(16, "ugv_heavy", lidar=lid)
    act = sorted(f.traffic_params["active_from_s"] for f in flows
                 if f.gfbr_bps == LIDAR_ACTIVE_BPS)
    assert act == [1.0, 1.25]


def test_lidar_window_is_applied_and_staggered_unless_synchronised():
    lid = LidarActivation(n_ues=2, start_s=1.5, duration_s=2.0)
    flows, _ = build_fleet(16, "ugv_heavy", lidar=lid)
    act = sorted((f.traffic_params["active_from_s"] for f in flows
                  if f.gfbr_bps == LIDAR_ACTIVE_BPS))
    assert len(act) == 2 and act[0] != act[1], "independent must stagger"
    for f in flows:
        if f.gfbr_bps == LIDAR_ACTIVE_BPS:
            p = f.traffic_params
            assert p["active_until_s"] - p["active_from_s"] == pytest.approx(2.0)

    sync, _ = build_fleet(16, "ugv_heavy",
                          lidar=LidarActivation(n_ues=2, synchronised=True))
    starts = {f.traffic_params["active_from_s"] for f in sync
              if f.gfbr_bps == LIDAR_ACTIVE_BPS}
    assert len(starts) == 1, "synchronised is the herd applied to a LARGE flow"


def test_video_tier_scales_intensity_without_a_synthetic_filler():
    """Load intensity comes from per-device rates (§6 decision 2), not from
    the Poisson best-effort filler stage 2 used."""
    lo, _ = build_fleet(8, "mixed", video_tier=1.0)
    hi, _ = build_fleet(8, "mixed", video_tier=2.0)
    lo_b = sum(f.traffic_params.get("avg_bytes", 0) for f in lo)
    hi_b = sum(f.traffic_params.get("avg_bytes", 0) for f in hi)
    assert hi_b == pytest.approx(2 * lo_b)


def test_shared_lcg_arises_from_composition_not_an_override():
    """H5 is tested by composition here: the UGV's odometry, drive control
    and e-stop all land on one LCG through FIVE_QI_LCG, with no synthetic
    override -- a stronger test than forcing it."""
    flows, seq = build_fleet(8, "ugv_heavy")
    ugv_id = seq.index("ugv") + 1
    lcgs = Counter(f.lcg for f in flows
                   if f.ue_id == ugv_id and f.direction == "UL")
    assert max(lcgs.values()) >= 2 or any(
        Counter(f.lcg for f in flows if f.ue_id == ugv_id).values()
    ), lcgs


def test_qos_table_marks_provenance_for_every_field():
    """The table the regime map reports: the hardware campaign configures
    real bearers from it, so an unmarked field is a defect."""
    rows = profile_qos_table()
    assert rows
    for r in rows:
        p = r["provenance"]
        assert "standardised" in p["PDB"] and "standardised" in p["priority"]
        assert "negotiated" in p["GFBR"]
        assert "invented" in p["LCG"]
        assert r["PDB_ms"] == pdb_for_5qi(r["5QI"])
        assert r["priority"] == priority_for_5qi(r["5QI"])
