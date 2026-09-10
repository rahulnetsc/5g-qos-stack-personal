"""G3's cell: the properties the experiment depends on, pinned.

Each test here is a thing that would **silently invalidate G3's result rather
than crash it** -- the same standard `sim/tests/test_g1_scenario.py` sets. The
two that matter most are the ones that were already wrong once:

  * telemetry's LCG collided with the camera's the first time the flow list
    was ordered canonically, because the fleet's own LCG pass had already run
    over the partial list. Two data flows on one LCG is a state the deployed
    RRC cannot produce (CLAUDE.md's LCG = DRB ID rule) and nothing would have
    raised;
  * telemetry's prioritised bit rate is the whole of GT-2.1's mechanism, and
    a `flow_class` typo would take it to zero and read as a scheduler result.
"""

from __future__ import annotations

import pytest

from scheduler.flow import FIVE_QI_PDB_MS, LCG_UNASSIGNED
from sim.scenarios.g3 import (
    CAMERA_GFBR_BPS, FLOOR_ARMING_HORIZON_MS, MAX_GAP_BOUND_MS, MFBR_MULTIPLE,
    QFI_CAMERA, QFI_FLOOD_UL, QFI_TELEMETRY, RAN_PDB_MS, SILENCE_ACTIVE_S,
    SILENCE_CYCLES, SILENCE_TAIL_S, SLOT_S, T_LIVE_S, TELEMETRY_BYTES,
    TELEMETRY_GFBR_BPS, TELEMETRY_PERIOD_MS,
    assert_telemetry_instrument_live, build_gt21_scenario,
    build_gt22_scenario, build_gt23_scenario, flood_ue_id,
    instrument_ue_ids, minimum_horizon_slots_gt23, resume_times_s,
    silence_windows, telemetry_flow_keys,
)
from sim.scenarios.schedule_guard import ScheduleTooLongForHorizon


def _tel(sc, ue_id=1):
    hits = [f for f in sc.flows
            if f.ue_id == ue_id and f.qfi == QFI_TELEMETRY
            and f.direction == "UL"]
    assert len(hits) == 1
    return hits[0]


# --- the bounds are DERIVED from the plan's own quantities ----------------

def test_the_two_bounds_are_derived_not_authored():
    assert MAX_GAP_BOUND_MS == pytest.approx(T_LIVE_S * 1000.0 / 4.0)
    # §5's RAN budget split: "RAN budget = PDB - 5 ms", against 5QI 1's own
    # standardised PDB. A literal 95.0 here would drift the moment the PDB
    # table moved.
    assert RAN_PDB_MS == pytest.approx(FIVE_QI_PDB_MS[QFI_TELEMETRY] - 5.0)


def test_the_floor_arming_horizon_is_read_from_the_scheduler_not_restated():
    """GT-2.3's buckets straddle this number, so a copy that drifted would
    silently make the buckets measure the wrong side of it."""
    from scheduler.two_tier import _UL_FLOOR_ALIVE_MS
    assert FLOOR_ARMING_HORIZON_MS == _UL_FLOOR_ALIVE_MS


# --- the instrument ------------------------------------------------------

def test_telemetry_is_a_gbr_bearer_offering_exactly_its_contract():
    """The unique point satisfying §5's "within GFBR" and this repo's own
    offered >= contract invariant at once."""
    sc = build_gt22_scenario(seed=1, n_ues=4)
    f = _tel(sc)
    assert f.flow_class == "GBR"
    offered = (f.traffic_params["bytes_per_period"] * 8
               / (f.traffic_params["period_ms"] / 1000.0))
    assert offered == pytest.approx(f.gfbr_bps)
    assert f.gfbr_bps == pytest.approx(TELEMETRY_GFBR_BPS)


def test_telemetry_carries_an_mfbr_because_the_ul_floor_cannot_arm_without_one():
    """`TwoTier._ul_has_pending_gbr` requires `mfbr_bps > 0`; a zero here
    disables BOTH of two-tier's named UL protections (Tier-1.5's floor and
    FIX-2's GBR PRB reserve) and GT-2.2 exists to validate the first."""
    sc = build_gt22_scenario(seed=1, n_ues=4)
    f = _tel(sc)
    assert f.mfbr_bps == pytest.approx(MFBR_MULTIPLE * TELEMETRY_GFBR_BPS)
    assert f.mfbr_bps > 0.0


def test_telemetry_gets_a_pbr_token_bucket_by_default_and_none_in_the_control():
    on = _tel(build_gt22_scenario(seed=1, n_ues=4))
    off = _tel(build_gt22_scenario(seed=1, n_ues=4, telemetry_gbr=False))
    assert on.effective_pbr_bps() == pytest.approx(TELEMETRY_GFBR_BPS)
    assert off.effective_pbr_bps() == 0.0
    assert off.flow_class == "Delay" and off.gfbr_bps == 0.0


def test_the_pbr_lever_actually_reaches_the_UE_LCP_and_not_only_the_config():
    """GT-2.1's mechanism, asserted through `sim/ue_lcp.py` rather than by
    reading a field -- and the mechanism is EXHAUSTION, not precedence.

    **Telemetry is never outranked.** TS 38.321 5.4.3.1 step 3 serves every
    logical channel in strict decreasing priority order REGARDLESS of Bj, and
    5QI 1's priority (20) beats 5QI 2's (40), so in round 2 telemetry goes
    first. `sim/ue_lcp.py` implements that correctly.

    What starves it is that round 2 never runs. Round 1 serves only channels
    with a positive bucket (`nr_ue_scheduler.c:2543-2553`), and with the
    camera's 4 Mbps bucket against a smaller transport block it absorbs the
    WHOLE block -- so a PBR-less telemetry bearer gets zero out of a grant it
    is the highest-priority channel on. Measured at 24 062 of 24 062 starved
    grants (docs/g3-stress-experiment-2026-09-09.md section 3.2).

    The two assertions below are exactly that pair: the camera always gets
    bytes, and telemetry gets them only when it has a bucket to be reached
    with in round 1.
    """
    from sim.buffer import BufferModel
    from sim.ue_lcp import UeLcp

    tb = 2_000                      # smaller than the camera's bucket
    for gbr, want_telemetry_bytes in ((False, 0), (True, TELEMETRY_BYTES)):
        sc = build_gt22_scenario(seed=1, n_ues=2, telemetry_gbr=gbr)
        ue_flows = [f for f in sc.flows if f.ue_id == 1 and f.direction == "UL"]
        buffers = BufferModel()
        for f in ue_flows:
            buffers.register(f.ue_id, f.qfi, is_ul=True, lcg=f.lcg)
        buffers.enqueue(1, QFI_TELEMETRY, int(TELEMETRY_BYTES), 0.0)
        buffers.enqueue(1, QFI_CAMERA, 100_000, 0.0)
        lcp = UeLcp(ue_flows)
        lcp.refill(0.2)             # fill every bucket to its ceiling
        split = dict(lcp.fill(ue_flows, tb, buffers))
        assert split.get(QFI_TELEMETRY, 0) == want_telemetry_bytes, (
            f"telemetry_gbr={gbr}: split {split} -- GT-2.1's whole mechanism "
            f"is which LCP round telemetry is served from")
        assert split.get(QFI_CAMERA, 0) > 0


def test_the_instrument_is_identical_at_every_point_of_the_load_axis():
    """`committed_mult` must move the load and not the quantity measured."""
    base = _tel(build_gt22_scenario(seed=1, n_ues=6, committed_mult=1.0))
    for cm in (0.5, 2.0, 3.0):
        f = _tel(build_gt22_scenario(seed=1, n_ues=6, committed_mult=cm))
        assert f.traffic_params["bytes_per_period"] == base.traffic_params["bytes_per_period"]
        assert f.traffic_params["period_ms"] == base.traffic_params["period_ms"]
        assert f.gfbr_bps == base.gfbr_bps
    # ... and the fleet's camera DOES move, or the axis is inert.
    cam = {cm: [f.traffic_params["avg_bytes"] for f in
                build_gt22_scenario(seed=1, n_ues=6, committed_mult=cm).flows
                if f.qfi == QFI_CAMERA][0]
           for cm in (0.5, 1.0, 2.0)}
    assert cam[0.5] < cam[1.0] < cam[2.0]


def test_the_scored_population_does_not_grow_with_the_fleet():
    """A worst-of-N order statistic would make the UE axis move the
    statistic as well as the load -- `sim/scorecard.py::Population`'s defect.
    """
    sizes21 = {len(instrument_ue_ids(build_gt21_scenario(seed=1, n_ues=n)))
               for n in (2, 4, 8, 16, 24)}
    sizes22 = {len(instrument_ue_ids(build_gt22_scenario(seed=1, n_ues=n)))
               for n in (2, 4, 8, 16, 24)}
    assert sizes21 == {1}, "GT-2.1 scores Asset A only"
    assert sizes22 == {2}, "GT-2.2 scores A and the flooding asset B"


# --- the bearer layout ---------------------------------------------------

def test_every_robot_has_the_same_bearer_layout_and_telemetry_is_drb_1():
    """THE BUG THIS PINS. `assign_deployed_lcgs` keeps an explicit LCG while
    still spending an ordinal, so appending the instrument to an
    already-assigned fleet list put telemetry and the camera BOTH on LCG 1.
    Two data flows on one LCG is a state the deployed RRC cannot produce.
    """
    for builder in (build_gt21_scenario, build_gt22_scenario):
        for n in (2, 4, 6, 12):
            sc = builder(seed=1, n_ues=n)
            for ue in sc.ues:
                mine = [f for f in sc.flows if f.ue_id == ue.ue_id]
                lcgs = [f.lcg for f in mine]
                assert LCG_UNASSIGNED not in lcgs
                assert len(set(lcgs)) == len(lcgs), (
                    f"{builder.__name__} n={n} ue{ue.ue_id}: LCG collision "
                    f"{[(f.qfi, f.lcg) for f in mine]}")
                tel = [f for f in mine if f.qfi == QFI_TELEMETRY]
                assert tel and tel[0].lcg == 1, (
                    "telemetry is DRB 1 in test plan §2's own bearer order")
                assert all(f.lcg != 0 for f in mine), "LCG 0 is the SRB group"


def test_no_ue_carries_one_5qi_in_both_directions():
    """`FlowRecord.key` has no direction term and `sim/buffer.py::_resolve`
    raises -- defects log #28/#30. The flood shares the filler's 5QI, which
    is why the flooding robot has no filler."""
    for sc in (build_gt21_scenario(seed=1, n_ues=6),
               build_gt22_scenario(seed=1, n_ues=6),
               build_gt23_scenario(seed=1, silence_s=1.0, n_ues=6)):
        seen: dict[tuple[int, int], str] = {}
        for f in sc.flows:
            key = (f.ue_id, f.qfi)
            if key in seen:
                assert seen[key] == f.direction, f"{key} in both directions"
            seen[key] = f.direction
        counts: dict[tuple[int, int], int] = {}
        for f in sc.flows:
            counts[(f.ue_id, f.qfi)] = counts.get((f.ue_id, f.qfi), 0) + 1
        assert max(counts.values()) == 1, "a (ue, qfi) is declared twice"


# --- the three sub-tests differ in the way the plan says ------------------

def test_gt21_isolates_the_intra_ue_mechanism_and_has_no_flood():
    sc = build_gt21_scenario(seed=1, n_ues=6)
    assert flood_ue_id(sc) is None, (
        "a neighbour's flood would confound GT-2.1 with GT-2.2")
    assert_telemetry_instrument_live(sc)


def test_gt21_over_drives_only_asset_As_camera_and_never_its_contract():
    sc = build_gt21_scenario(seed=1, n_ues=4, camera_offer_x_gfbr=2.0)
    cams = {f.ue_id: f for f in sc.flows if f.qfi == QFI_CAMERA}
    assert cams[1].traffic_params["avg_bytes"] == pytest.approx(
        2.0 * cams[2].traffic_params["avg_bytes"])
    for f in cams.values():
        assert f.gfbr_bps == pytest.approx(CAMERA_GFBR_BPS), (
            "over-driving means offering more than the entitlement, not "
            "being entitled to more")
        assert f.mfbr_bps == pytest.approx(MFBR_MULTIPLE * CAMERA_GFBR_BPS)
    # "camera at MFBR" IS offer_x_gfbr == MFBR_MULTIPLE, derived.
    offered = (cams[1].traffic_params["avg_bytes"] * 8
               / (cams[1].traffic_params["period_ms"] / 1000.0))
    assert offered >= cams[1].mfbr_bps


def test_gt22_floods_a_neighbour_that_is_still_a_real_asset():
    sc = build_gt22_scenario(seed=1, n_ues=6)
    fl = flood_ue_id(sc)
    assert fl == 6 and fl != 1
    mine = {f.qfi for f in sc.flows if f.ue_id == fl}
    assert QFI_TELEMETRY in mine and QFI_CAMERA in mine, (
        "GT-2.2's B is 'a real asset, not a pure aggressor', and the clause "
        "scores its telemetry too")
    assert QFI_FLOOD_UL in mine
    assert_telemetry_instrument_live(sc)


def test_gt22_refuses_a_zero_flood_and_a_flood_on_the_instrument():
    with pytest.raises(ValueError):
        build_gt22_scenario(seed=1, n_ues=4, flood_bps=0.0)
    with pytest.raises(ValueError):
        build_gt21_scenario(seed=1, n_ues=1)          # §4's ">= 2 assets"


# --- GT-2.3's schedule ---------------------------------------------------

@pytest.mark.parametrize("silence_s", (1.0, 5.0, 60.0))
def test_the_silence_schedule_is_derived_and_self_consistent(silence_s):
    wins = silence_windows(silence_s)
    resumes = resume_times_s(silence_s)
    assert len(wins) == SILENCE_CYCLES + 1
    assert len(resumes) == SILENCE_CYCLES, (
        "one resume per silence -- GT-2.3's unit of observation")
    for (a, b), nxt in zip(wins, wins[1:]):
        assert b - a == pytest.approx(SILENCE_ACTIVE_S) or b - a == pytest.approx(SILENCE_TAIL_S)
        assert nxt[0] - b == pytest.approx(silence_s), (
            "the gap between windows IS the bucket's silence")
    assert tuple(w[0] for w in wins[1:]) == resumes
    need = minimum_horizon_slots_gt23(silence_s)
    assert need * SLOT_S >= wins[-1][1]


@pytest.mark.parametrize("silence_s", (1.0, 5.0, 60.0))
def test_gt23_refuses_a_horizon_that_drops_resumes(silence_s):
    need = minimum_horizon_slots_gt23(silence_s)
    with pytest.raises(ScheduleTooLongForHorizon):
        build_gt23_scenario(seed=1, silence_s=silence_s, n_ues=4,
                            horizon_slots=need // 2)
    # ... and says so is a claim the caller makes.
    build_gt23_scenario(seed=1, silence_s=silence_s, n_ues=4,
                        horizon_slots=need // 2, allow_partial_schedule=True)


def test_gt23_puts_the_windows_on_asset_A_only_and_floods_throughout():
    sc = build_gt23_scenario(seed=1, silence_s=5.0, n_ues=6)
    for f in sc.flows:
        if f.qfi != QFI_TELEMETRY or f.direction != "UL":
            continue
        wins = f.traffic_params.get("active_windows")
        if f.ue_id == 1:
            assert wins == silence_windows(5.0)
        else:
            assert wins is None, (
                "only Asset A pauses; a neighbour that paused too would make "
                "the cell quieter exactly when re-entry is being measured")
    flood = [f for f in sc.flows if f.qfi == QFI_FLOOD_UL
             and f.direction == "UL" and f.traffic_kind == "poisson"]
    assert flood and "active_windows" not in flood[0].traffic_params, (
        "'bg saturation throughout' -- the worst case for A's re-entry")


def test_the_buckets_straddle_the_floors_arming_horizon():
    """The reason the three buckets are {1, 5, 60} and not three arbitrary
    numbers: below the arming horizon the floor can still rescue a stall,
    above it the raw SR path carries the resume alone."""
    horizon_s = FLOOR_ARMING_HORIZON_MS / 1000.0
    assert 1.0 < horizon_s < 5.0 < 60.0


# --- populations, derived ------------------------------------------------

def test_telemetry_keys_are_derived_from_the_scenario():
    for n in (2, 5, 9):
        sc = build_gt22_scenario(seed=1, n_ues=n)
        assert telemetry_flow_keys(sc) == [f"ue{i}_qfi{QFI_TELEMETRY}"
                                           for i in range(1, n + 1)]


def test_the_live_assertion_catches_a_cell_missing_its_instrument():
    import dataclasses
    sc = build_gt22_scenario(seed=1, n_ues=4)
    stripped = dataclasses.replace(
        sc, flows=[f for f in sc.flows
                   if not (f.ue_id == 1 and f.qfi == QFI_TELEMETRY)])
    with pytest.raises(AssertionError):
        assert_telemetry_instrument_live(stripped)


# --- the mechanism is OBSERVABLE, not merely present ---------------------

def test_the_ul_floor_is_observable_on_this_cell_without_a_scheduler_change():
    """`CLAUDE.md`'s audit lists the UL floor as UNOBSERVABLE -- "OAI's
    counters not ported; activation unknowable". It is observable after all:
    `floor_fire` is tier 1.5 of two-tier's own UL ranking key, so
    `scheduler/rank_trace.py` already records it for every candidate.

    This asserts the cell REACHES the mechanism -- CLAUDE.md's two questions
    at the moment a mechanism lands: who calls it outside a test, and what in
    a run's output would differ if it never fired. The tally's own correctness
    (that a zero means silence and not a mis-bound hook) is pinned separately
    in `sim/tests/test_g3_floor_tally.py`, which counts the fires a second way
    and requires the two to agree.
    """
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[2] / "scripts"))
    from g3_stress import FloorFireTally
    from scheduler.two_tier import TwoTier
    from sim.driver import run as driver_run

    sc = build_gt22_scenario(seed=1, n_ues=4, horizon_slots=8_000)
    sched = TwoTier(min_rb=5)
    tally = FloorFireTally()
    sched.rank_sink = tally
    driver_run(sc, sched, cqi_delay_slots=8, max_sched_ues=4)

    assert tally.arm_declares_floor is True, (
        "two-tier's UL key no longer declares a floor tier")
    assert tally.snapshots > 0, "no UL candidate set was ever ranked"
    assert tally.candidate_slots > 0
    rep = tally.report()
    assert rep["floor_fires"] is not None, (
        "None means 'this arm has no such tier', which two-tier does")


def test_flood_ue_id_is_correct_at_the_campaign_rate_and_FLAGGED_below_it():
    """The published campaign's configuration, plus the flagged latent defect.

    `flood_ue_id` tests `rate_bps >= FLOOD_UL_BPS`, so it is correct at and
    above the default and returns None BELOW it -- which would silently drop
    Asset B from `instrument_ue_ids`. The fix is one comparison and is
    deliberately NOT in this commit (`sim/scenarios/g3.py` sits inside the
    artefact's `code_state` scope, so editing it re-stales every G3 claim). This
    test pins BOTH halves so the defect cannot be forgotten and cannot be
    "fixed" without a test noticing.
    """
    from sim.scenarios.g3 import FLOOD_UL_BPS
    for rate in (FLOOD_UL_BPS, FLOOD_UL_BPS * 2):
        sc = build_gt22_scenario(seed=1, n_ues=5, flood_bps=rate)
        assert flood_ue_id(sc) == 5, rate
        assert instrument_ue_ids(sc) == [1, 5], rate
    # THE FLAGGED BEHAVIOUR, pinned as it stands. When the comparison is fixed
    # to `> BG_UL_BPS` this assertion must be inverted in the same commit.
    small = build_gt22_scenario(seed=1, n_ues=5, flood_bps=FLOOD_UL_BPS / 2)
    assert flood_ue_id(small) is None, (
        "flood_ue_id now finds a below-default flood -- if that is the fix, "
        "invert this assertion and re-stamp the G3 artefact in the same commit")
    assert instrument_ue_ids(small) == [1]


def test_round_2_serves_telemetry_BEFORE_the_camera_even_with_no_bucket():
    """THE LOAD-BEARING FACT OF G3's CORRECTED MECHANISM, pinned.

    TS 38.321 5.4.3.1 step 3: all logical channels are served in strict
    decreasing priority order **regardless of the value of Bj**. So a
    bucket-less telemetry bearer is NOT outranked by the camera -- it wins
    round 2 outright, and the only reason it starves in the campaign is that
    round 1 exhausts the block before round 2 runs.

    This test removes that reason and requires the standard's behaviour: with
    a camera bucket SMALLER than the transport block, round 1 cannot consume
    everything, and telemetry must take the scarce remainder AHEAD of the
    camera. If this ever fails, the corrected mechanism in
    `docs/g3-stress-experiment-2026-09-09.md` section 3.2 is wrong and the
    original "telemetry waits behind the camera" reading would be right.
    """
    from scheduler.flow import FIVE_QI_PRIORITY
    from sim.buffer import BufferModel
    from sim.ue_lcp import UeLcp

    # The ordering the whole argument rests on, derived from the 5QI table.
    assert FIVE_QI_PRIORITY[QFI_TELEMETRY] < FIVE_QI_PRIORITY[QFI_CAMERA]

    # bsd_ms=1 gives the camera a 4 Mbps x 1 ms = 500 B bucket, well under the
    # 700 B block -- so round 1 CANNOT exhaust the grant.
    sc = build_gt22_scenario(seed=1, n_ues=2, telemetry_gbr=False, bsd_ms=1.0)
    ue_flows = [f for f in sc.flows if f.ue_id == 1 and f.direction == "UL"]
    buffers = BufferModel()
    for f in ue_flows:
        buffers.register(f.ue_id, f.qfi, is_ul=True, lcg=f.lcg)
    buffers.enqueue(1, QFI_TELEMETRY, 300, 0.0)
    buffers.enqueue(1, QFI_CAMERA, 100_000, 0.0)
    lcp = UeLcp(ue_flows)
    lcp.refill(1.0)                      # every bucket to its ceiling
    split = dict(lcp.fill(ue_flows, 700, buffers))

    assert split.get(QFI_TELEMETRY, 0) > 0, (
        f"split {split}: a bucket-less telemetry bearer got nothing out of a "
        f"block round 1 could not exhaust -- round 2 is not honouring "
        f"TS 38.321 5.4.3.1 step 3")
    # ... and it took the remainder AHEAD of the camera, which is precedence
    # rather than leftovers: the camera is capped at its 500 B round-1 take.
    assert split.get(QFI_TELEMETRY, 0) == 200
    assert split.get(QFI_CAMERA, 0) == 500
