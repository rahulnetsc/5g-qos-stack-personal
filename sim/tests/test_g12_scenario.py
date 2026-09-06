"""G12's overload-degradation ramp (docs/wp9-plan.md §35, commit 2).

Three of these tests pin things that ALREADY WENT WRONG once and produced a
number that read like a result:

  * `test_lidar_streams_for_the_whole_horizon` pins the fix for stage 5's
    duty-cycled lidar, whose `gfbr_fraction` was capped at
    `duration_s/horizon_s = 0.4` and so breached at every load including
    ramp index 0 -- 0 of 1,110 flow-records met contract (§35.3).
  * `test_bg_is_5qi_9_and_not_the_5qi_8_aggressor` pins the substitution
    that would have been INVISIBLE: `Scorecard.NON_PROTECTED_5QI` contains
    both 8 and 9, so using the existing 5QI 8 aggressor would load the cell
    correctly and silently answer a different guarantee (§35.3).
  * `test_5qi_1_telemetry_stays_delay_class` pins the rejected alternative
    from §35.2, measured in §35.4(c): converting it to GBR at the test
    plan's own 0.5 Mbps GFBR against ~24 kbps offered scores 0.045 at ramp
    index 0, so telemetry would lead every ordering.

The remaining tests pin D1's ramp neutrality (the whole reason the ordering
between 5QI 4 and 5QI 2 means anything) and §35.7's degeneracy guards.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.fleet import LIDAR_ACTIVE_BPS, LIDAR_MAX_CONCURRENT  # noqa: E402
from scheduler.flow import priority_for_5qi
from sim.scenarios.g12 import (BG_OFFERED_BPS, GBR_CLASSES,  # noqa: E402
                               GUARANTEE_RAMP_TOP_MULT,
                               MEASURED_CEILING_BPS, REFERENCE_COMMITTED_BPS,
                               LIDAR_STREAM_BPS, QFI_BG, QFI_BG_UL, RAMP,
                               assert_cell_is_scoreable,
                               assert_order_non_degenerate,
                               assert_ramp_bottom_clean, build_g12_scenario,
                               class_of, gbr_flow_census, horizon_seconds,
                               permute_flows)

HORIZON = 20_000
SEED = 4242


def _flows(scenario, qfi):
    return [f for f in scenario.flows if f.qfi == qfi]


def _build(mult=1.0, n_ues=8, composition="mixed", horizon=HORIZON, **kw):
    return build_g12_scenario(n_ues, composition, mult, SEED, horizon, **kw)


# --- D1: the ramp must be NEUTRAL between the two classes it orders ------

@pytest.mark.parametrize("mult", [1.5, 2.0, 3.0])
def test_ramp_scales_both_gbr_classes_gfbr_together(mult):
    """The ordering between 5QI 4 and 5QI 2 is only meaningful if the ramp
    does not privilege one of them. `video_tier` alone scales `xr_video`
    (5QI 2) and would bias the very result under test, which is why §35.6 D1
    rejects it as the ramp axis."""
    base, ramped = _build(1.0), _build(mult)
    for qfi in GBR_CLASSES:
        b = sorted(f.gfbr_bps for f in _flows(base, qfi))
        r = sorted(f.gfbr_bps for f in _flows(ramped, qfi))
        assert b and len(b) == len(r)
        for got, want in zip(r, b):
            assert got == pytest.approx(want * mult, rel=1e-9)


@pytest.mark.parametrize("mult", [1.5, 3.0])
def test_ramp_scales_offered_load_too_not_only_the_contract(mult):
    """Scaling GFBR without scaling offered load would make the contract
    unmeetable by arithmetic rather than by congestion -- the same defect
    §35.4(c) measures on telemetry, one step removed."""
    base, ramped = _build(1.0), _build(mult)
    for f_b, f_r in zip(_flows(base, 2), _flows(ramped, 2)):
        assert f_r.traffic_params["avg_bytes"] == int(
            f_b.traffic_params["avg_bytes"] * mult)
    for f_b, f_r in zip(_flows(base, 4), _flows(ramped, 4)):
        assert f_r.traffic_params["bytes_per_period"] == pytest.approx(
            f_b.traffic_params["bytes_per_period"] * mult, rel=1e-6)


# --- the stage-5 duty-cycle cap, pinned ---------------------------------

@pytest.mark.parametrize("horizon", [8_000, 20_000, 40_000])
def test_lidar_streams_for_the_whole_horizon(horizon):
    """Stage 5's lidar ran 2.0 s of a 5.0 s horizon, so its throughput --
    averaged over the whole run by `FlowRecord.throughput_bps` -- could not
    exceed 0.4x GFBR and it breached at EVERY load. The window must cover
    the run, and must be DERIVED from `horizon_slots` so a numerology or
    horizon change cannot silently reintroduce the cap."""
    sc = _build(horizon=horizon)
    want_s = horizon_seconds(horizon)
    lidars = _flows(sc, 4)
    assert lidars, "no 5QI 4 flow: G12 has nothing to order"
    for f in lidars:
        assert f.traffic_params["active_from_s"] == 0.0
        assert f.traffic_params["active_until_s"] == pytest.approx(want_s)
        duty = (f.traffic_params["active_until_s"]
                - f.traffic_params["active_from_s"]) / want_s
        assert duty == pytest.approx(1.0), (
            "the duty-cycle cap on gfbr_fraction is back")


def test_lidar_rate_is_the_test_plans_stream_not_fleets_activation():
    """3 Mbps (test plan §2.1's T4 row), not `sim/fleet.py`'s 12 Mbps
    duty-cycled activation rate -- §35.6 D3's two-different-device-claims
    decision, pinned so it cannot be quietly unified."""
    sc = _build(1.0)
    assert LIDAR_STREAM_BPS != LIDAR_ACTIVE_BPS
    for f in _flows(sc, 4):
        assert f.gfbr_bps == pytest.approx(LIDAR_STREAM_BPS)


def test_lidar_max_concurrent_still_binds():
    """A continuous lidar is a different device claim, but the concurrency
    BOUND is unrelated to the duty cycle and still applies -- `sim/fleet.py`
    justifies it from the factory floor's own serialisation."""
    sc = _build(1.0, n_ues=32, composition="ugv_heavy")
    assert len(_flows(sc, 4)) <= LIDAR_MAX_CONCURRENT


# --- the invisible substitution -----------------------------------------

def test_the_bg_class_is_9_and_the_FLOOD_is_8_after_the_collision_fix():
    """G12 names 5QI 9 by number, and the saturating flood now carries 5QI 8.

    **This test used to assert "5QI 8 has no role in G12" and it caught the
    collision fix in the act** -- correctly, because `sim/parametric.py`'s bg
    and `sim/scenarios/g9.py`'s QFI_AGGRESSOR are both 5QI 8 and a mix-up
    would be invisible to every protected-fleet statistic.

    **8 is nonetheless the only available label, and the constraint that
    settles it is `Scorecard.NON_PROTECTED_5QI`.** The flood must be
    non-protected (it has no contract and must not enter a protected-fleet
    statistic) and must keep 5QI 9's 300 ms PDB. Only 8 and 9 satisfy both,
    and 9 is what it is aliasing against -- 5QI 6 has the same 300 ms PDB but
    is NOT in NON_PROTECTED_5QI, so it would score the flood as fleet.

    So the hazard this test was written for is real and is handled by
    construction rather than by avoiding the number: the flood is the ONLY
    5QI-8 flow in a G12 scenario, and the scorer selects the background as a
    POPULATION (`BG_QFIS`), not by a single label.
    """
    sc = _build(1.0)
    assert QFI_BG == 9 and QFI_BG_UL == 8
    bg = [f for f in sc.flows
          if f.traffic_params.get("rate_bps") == BG_OFFERED_BPS]
    assert len(bg) == 1, "expected exactly one saturating background flow"
    assert bg[0].qfi == QFI_BG_UL and bg[0].direction == "UL"
    assert bg[0].flow_class == "PF" and bg[0].gfbr_bps == 0.0
    assert _flows(sc, 8) == bg, "the flood is the only 5QI-8 flow in G12"
    # both background labels must stay outside the protected fleet, or the
    # relabel would quietly move a 50 Mbps flood INTO the fleet statistics
    from sim.scorecard import Scorecard
    assert {QFI_BG, QFI_BG_UL} <= set(Scorecard.NON_PROTECTED_5QI)
    # and the relabel is de-aliasing only: 5QI 9's priority is pinned on
    assert bg[0].priority_level == priority_for_5qi(QFI_BG)


def test_no_ue_carries_one_5qi_in_both_directions():
    """The defect the relabel exists to fix (defects log #30). Kept HERE too,
    beside the scenario, and not only in the repo-wide sweep."""
    import collections
    for comp in ("mixed", "ugv_heavy", "drone_heavy", "sensor_dense"):
        for n in (4, 8):
            sc = _build(1.0, composition=comp, n_ues=n)
            dupes = {k: v for k, v in
                     collections.Counter((f.ue_id, f.qfi)
                                         for f in sc.flows).items() if v > 1}
            assert not dupes, f"{comp} n={n}: {dupes}"


def test_bg_can_be_switched_off_for_a_control():
    sc = _build(1.0, bg_offered_bps=0.0)
    assert not [f for f in sc.flows
                if f.traffic_params.get("rate_bps") == BG_OFFERED_BPS]


# --- the rejected alternative, pinned -----------------------------------

def test_5qi_1_telemetry_stays_delay_class():
    """§35.2's rejected alternative. Converting 5QI 1 to GBR so M13 can see
    it is the same error shape as widening M13 -- changing the input's class
    until the instrument reads it -- and it fails on its own terms: §35.4(c)
    measured 0.045 at ramp index 0 against the test plan's own GFBR."""
    sc = _build(1.0, composition="drone_heavy")
    telemetry = _flows(sc, 1)
    assert telemetry, "drone_heavy must carry 5QI 1"
    for f in telemetry:
        assert f.flow_class == "Delay"
        assert f.gfbr_bps == 0.0


# --- D4: the permutation control must not be a no-op --------------------

def test_permute_flows_reorders_without_changing_the_workload():
    sc = _build(2.0)
    perm = permute_flows(sc, 7)
    key = lambda f: (f.ue_id, f.qfi)  # noqa: E731
    assert sorted(map(key, perm.flows)) == sorted(map(key, sc.flows))
    assert [key(f) for f in perm.flows] != [key(f) for f in sc.flows], (
        "the declaration-order control is a no-op")
    assert gbr_flow_census(perm) == gbr_flow_census(sc)


def test_permute_flows_is_deterministic_in_its_own_seed():
    sc = _build(2.0)
    a, b = permute_flows(sc, 11), permute_flows(sc, 11)
    assert [(f.ue_id, f.qfi) for f in a.flows] == [(f.ue_id, f.qfi)
                                                   for f in b.flows]
    c = permute_flows(sc, 12)
    assert [(f.ue_id, f.qfi) for f in a.flows] != [(f.ue_id, f.qfi)
                                                   for f in c.flows]


# --- §35.8: the population must be constant across the ramp -------------

def test_gbr_census_is_constant_across_the_whole_ramp():
    """c2a9f13's lesson, transferred from events to violations: an arm whose
    ramp points carry different flow populations is not a smaller sample of
    the same thing. Derived from each built scenario, never restated."""
    censuses = {m: gbr_flow_census(_build(m)) for m in RAMP}
    assert len(set(map(lambda d: tuple(sorted(d.items())),
                       censuses.values()))) == 1, censuses
    assert set(censuses[RAMP[0]]) == set(GBR_CLASSES)


def test_class_of_covers_every_flow():
    sc = _build(1.0)
    assert class_of(sc) == {f"ue{f.ue_id}_qfi{f.qfi}": f.qfi
                            for f in sc.flows}


# --- §35.7's degeneracy guards ------------------------------------------

def test_cell_without_a_ugv_is_refused_by_name():
    """`sensor_dense` allocates 3 % UGVs, so at N=4 it has none and carries
    no 5QI 4 flow at all. Such a cell must be excluded, not scored to a
    one-element 'order' that reads like a result (§35.7 case 1)."""
    sc = _build(1.0, n_ues=4, composition="sensor_dense")
    assert not _flows(sc, 4)
    with pytest.raises(ValueError, match="absent"):
        assert_cell_is_scoreable(sc)


def test_scoreable_cell_returns_its_census():
    assert set(assert_cell_is_scoreable(_build(1.0))) >= set(GBR_CLASSES)


def test_ramp_bottom_must_be_clean():
    """E1's control. A class breaching at ramp index 0 means the ramp is
    measuring provisioning, not overload -- both known instances (stage 5's
    lidar, the test plan's telemetry GFBR) are recorded in §35.7 case 2."""
    assert_ramp_bottom_clean({4: 2, 2: 3})
    with pytest.raises(AssertionError, match="ramp index 0"):
        assert_ramp_bottom_clean({4: 0, 2: 3})


def test_one_element_order_raises_and_names_the_unfailed_class():
    with pytest.raises(AssertionError, match="not an ordering"):
        assert_order_non_degenerate([2], {2: 3}, {2: 0.5, 4: 1.0})


def test_a_tie_is_reported_as_a_tie_not_as_an_order():
    """`first_violation_order` sorts by index and Python's sort is STABLE,
    so two classes first failing at the same index emit in dict-insertion
    order -- silently the flow-iteration order §35.5 showed to be an
    artefact."""
    v = assert_order_non_degenerate([4, 2], {4: 2, 2: 2}, {4: 0.3, 2: 0.4})
    assert v.ties == ((2, 4),)
    assert not v.is_scoreable


def test_never_failed_classes_travel_with_the_order():
    """'never failed' and 'never present' read identically in a bare
    `order_5qi` -- the empty-selection signature CLAUDE.md records six
    times. The terminal fraction is what distinguishes them."""
    v = assert_order_non_degenerate([2, 4], {2: 1, 4: 3},
                                    {2: 0.4, 4: 0.2, 9: 0.0})
    assert v.never_failed == (9,)
    assert v.is_scoreable
    assert v.terminal_fraction[9] == 0.0


# --- the ramp's own shape, pinned ---------------------------------------

def test_ramp_is_strictly_ascending():
    """`Scorecard.first_violation_order` documents that `records_by_load`
    "must already be sorted ascending by offered load" -- it assigns
    `first_fail_at` from the ENUMERATION index, so an unsorted ramp silently
    reports the wrong order rather than raising."""
    assert list(RAMP) == sorted(RAMP)
    assert len(set(RAMP)) == len(RAMP)


def test_ramp_spans_the_guarantees_own_top_on_both_sides():
    """GT-7.3 ramps "to 145 % of the measured ceiling". The probe found
    5QI 4 breaching only at 177-265 %, so the ramp must cover the
    guarantee's own range AND extend past it -- and the analyser must be
    able to tell the two apart, which is what GUARANTEE_RAMP_TOP_MULT is
    for. Reporting the beyond-145 % ordering as if it were the guarantee's
    would be the error this constant exists to prevent."""
    assert GUARANTEE_RAMP_TOP_MULT in RAMP
    assert any(m < GUARANTEE_RAMP_TOP_MULT for m in RAMP)
    assert any(m > GUARANTEE_RAMP_TOP_MULT for m in RAMP)
    pct = (100.0 * REFERENCE_COMMITTED_BPS * GUARANTEE_RAMP_TOP_MULT
           / MEASURED_CEILING_BPS)
    assert 140.0 <= pct <= 150.0, (
        f"GUARANTEE_RAMP_TOP_MULT lands at {pct:.0f} % of the measured "
        f"ceiling, not GT-7.3's 145 %")


def test_reference_committed_load_matches_the_built_scenario():
    """REFERENCE_COMMITTED_BPS is a MEASURED number carried in the module so
    the %-of-ceiling table can be checked. It must still equal what the
    builder actually produces at the reference cell, or the table is prose
    that has drifted from the code -- CLAUDE.md's own recurring failure."""
    sc = _build(1.0, n_ues=8, composition="mixed")
    committed = sum(f.gfbr_bps for f in sc.flows
                    if f.flow_class == "GBR" and f.gfbr_bps > 0)
    assert committed == pytest.approx(REFERENCE_COMMITTED_BPS, rel=1e-9)


def test_one_element_order_is_reportable_only_when_explicitly_allowed():
    """Inside GT-7.3's own ramp a one-element order is the FINDING (§35.12),
    so the campaign must report it; everywhere else it means the instrument
    is pinned and must raise. A named parameter rather than a `try` around
    the raise, because a caught assertion and a bypassed one read alike."""
    v = assert_order_non_degenerate([2], {2: 3}, {2: 0.5, 4: 1.0},
                                    allow_one_element=True)
    assert v.order_5qi == (2,)
    assert v.never_failed == (4,)
    assert not v.is_scoreable, (
        "a one-element order must never read as scoreable, however it "
        "was obtained")
    with pytest.raises(AssertionError):
        assert_order_non_degenerate([2], {2: 3}, {2: 0.5, 4: 1.0})


def test_allow_one_element_does_not_disable_the_bottom_of_ramp_check():
    """The two guards are independent: a class breaching at ramp index 0 is
    a stop condition in EVERY region, in-range included."""
    with pytest.raises(AssertionError, match="ramp index 0"):
        assert_order_non_degenerate([2], {2: 0}, {2: 0.5, 4: 1.0},
                                    allow_one_element=True)
