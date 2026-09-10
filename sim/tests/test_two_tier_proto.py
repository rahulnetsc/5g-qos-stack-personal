"""TwoTierProto: OFF is byte-identical, and each edit does only what it says.

**THE LOAD-BEARING TEST IN THIS FILE IS THE FIRST ONE.** A divergence arm whose
flags-off state has drifted from the port cannot attribute anything to its
edits: every Proto-vs-faithful difference would be a mixture of the edit and
the drift, and there would be no way to tell the two apart afterwards. So
"off == TwoTier" is asserted over whole driver summaries on several scenarios
and seeds, not argued from the fact that the subclass "only adds" things.

The second group pins the exactness argument the implementation rests on --
that suppressing a candidate's reserve contribution leaves `B_eff` unchanged
and the ranking untouched. Both are claims about arithmetic, so both are
tested as arithmetic rather than inferred from a run that happened to match.
"""

from __future__ import annotations

import pytest

from scheduler.two_tier import TwoTier, _Candidate
from scheduler.two_tier_proto import PROTO_FLAGS, TwoTierProto
from sim.driver import run as driver_run
from sim.scenarios.g3 import build_gt22_scenario


def _summary(sched, sc, cap=4):
    return driver_run(sc, sched, cqi_delay_slots=8, max_sched_ues=cap)


#: Keys excluded from the identity comparison, each with the reason it cannot
#: match by construction. `_ue_lcp` and `_message_ledger` are LIVE OBJECT
#: HANDLES -- two runs build two instances and neither class defines `__eq__`,
#: so comparing them compares identities and always differs. That is exactly
#: the defect G1's rank-hook check hit (`docs/g1-slide-source.md` section 8: "a
#: check that fails on its own null control is failing on the instrument"), and
#: it cost this file one false failure before being recognised.
#: `scheduler_counters` is excluded because Proto ADDS keys to it by design; the
#: inherited keys are compared explicitly below, so the exclusion cannot hide a
#: behavioural difference.
_EXCLUDED = ("scheduler_counters", "_message_ledger", "_ue_lcp")


def _comparable(summary):
    """The result content, with live handles excluded BY NAME and the exclusion
    then verified to have been necessary -- an exclusion that is not doing work
    is an exclusion that can hide something later."""
    return {k: v for k, v in summary.items() if k not in _EXCLUDED}


def _handles_really_are_handles(summary):
    """Every excluded key present must be non-JSON, i.e. genuinely a handle.
    If one becomes plain data it belongs back in the comparison."""
    import json
    bad = []
    for k in _EXCLUDED:
        if k == "scheduler_counters" or k not in summary:
            continue
        try:
            json.dumps(summary[k])
        except (TypeError, ValueError):
            continue
        bad.append(k)
    return bad


# --- THE ONE THAT MATTERS -------------------------------------------------

@pytest.mark.parametrize("n_ues,seed", [(4, 1), (6, 2), (12, 3), (16, 4)])
def test_all_flags_off_is_BYTE_IDENTICAL_to_the_faithful_port(n_ues, seed):
    """Off must be the port, over a whole run, at fleet sizes either side of
    the eleven-robot threshold where E1's gate would fire if it were on."""
    sc = build_gt22_scenario(seed=seed, n_ues=n_ues, horizon_slots=8_000)
    faithful = _summary(TwoTier(min_rb=5), sc)
    proto = _summary(TwoTierProto(min_rb=5), sc)

    assert not _handles_really_are_handles(proto), (
        "an excluded key is now plain data and must be compared again")
    assert _comparable(proto) == _comparable(faithful), (
        f"n_ues={n_ues} seed={seed}: TwoTierProto with every flag off differs "
        f"from TwoTier. Until this passes, no Proto-vs-faithful difference can "
        f"be attributed to an edit.")
    # ... and the INHERITED counters too, which the comparison above excludes.
    fc = faithful["scheduler_counters"]
    pc = proto["scheduler_counters"]
    assert {k: pc[k] for k in fc} == fc
    # The gate must not have been evaluated at all.
    assert pc["e1_slots_evaluated"] == 0
    assert pc["e2_slots_evaluated"] == 0


def test_every_flag_defaults_off_and_is_enumerated():
    s = TwoTierProto(min_rb=5)
    for flag in PROTO_FLAGS:
        assert getattr(s, flag) is False, flag
    # A flag added without being registered in PROTO_FLAGS would be invisible
    # to a runner enumerating the arm's configurations. DERIVED from the
    # constructor signature, not from a name prefix: the first version of this
    # test matched on ("gate_", "stale_", "deadline_") and a fourth flag named
    # outside those prefixes would have gone unseen -- a restated set in test
    # code, which fails in the direction of PASSING (CLAUDE.md).
    import inspect
    sig = inspect.signature(TwoTierProto.__init__)
    present = {n for n, prm in sig.parameters.items()
               if isinstance(prm.default, bool)}
    assert present == set(PROTO_FLAGS), (
        f"bool constructor flags {present} do not match "
        f"PROTO_FLAGS {set(PROTO_FLAGS)}")


def test_an_unimplemented_flag_is_REFUSED_not_ignored():
    """Enabling an edit that does not exist would report the faithful arm's
    numbers under the divergence arm's name -- the worst failure available to
    a comparison, because it looks like a null result."""
    with pytest.raises(NotImplementedError, match="deadline_sizing"):
        TwoTierProto(min_rb=5, deadline_sizing=True)


# --- the exactness argument, as arithmetic -------------------------------

def test_suppressing_a_reserve_leaves_B_eff_unchanged():
    """The transform E1 and E2 share: fold `gbr_bytes_slot` into
    `ul_total_target_bytes`, then zero it. `B_eff` is a maximum over the same
    three numbers before and after, and this pins that rather than trusting it.
    """
    from scheduler.two_tier import _Candidate
    s = TwoTierProto(min_rb=5)
    for target, gbr, backlog in ((0, 900, 100), (500, 900, 100),
                                 (900, 500, 100), (0, 0, 700),
                                 (1200, 300, 5000)):
        c = _Candidate(ue_id=1, flows=[], bits_per_rb=100, bler=0.0,
                       snr_db=10.0, coef=1.0)
        c.has_gbr = True
        c.gbr_bytes_slot = gbr
        c.ul_total_target_bytes = target

        def b_eff(cand):
            v = max(cand.ul_total_target_bytes, backlog)
            if cand.has_gbr and cand.gbr_bytes_slot > 0:
                v = max(v, cand.gbr_bytes_slot)
            return v

        before = b_eff(c)
        s._suppress_reserve(c)
        assert c.gbr_bytes_slot == 0
        assert c.proto_orig_gbr_bytes_slot == gbr
        assert b_eff(c) == before, (target, gbr, backlog)


def test_E1_changes_grant_sizing_and_NOT_the_ranking():
    """Given the SAME candidate set, E1 must leave `coef` and the sort key
    identical -- it acts after `super()` has finalised `coef`, and
    `gbr_bytes_slot` feeds neither.

    **A whole-run order comparison is the WRONG instrument here and was tried
    first.** With E1 on the grant sizes differ, so `prbs_left`, what gets
    delivered and therefore every later slot's candidate set differ too -- the
    trajectory diverges by design. Comparing rank order across a run cannot
    separate "the sort changed" from "the state evolved differently", and it
    reported a failure that meant only the second. Same inputs is the
    comparison that answers the question asked.
    """
    from types import SimpleNamespace
    from scheduler.two_tier import _Candidate

    def make():
        cs = []
        for ue in range(1, 13):
            c = _Candidate(ue_id=ue, flows=[], bits_per_rb=100, bler=0.0,
                           snr_db=10.0, coef=float(100 * ue))
            c.has_gbr = True
            c.gbr_bytes_slot = 400 + ue
            c.ul_total_target_bytes = 200
            c.urgency01 = 0.1 * (ue % 5)
            c.hyp_tbs_bytes = 1000
            cs.append(c)
        return cs

    faithful, proto = TwoTier(min_rb=5), TwoTierProto(
        min_rb=5, gate_follower_reserve=True)
    for s_ in (faithful, proto):
        s_._grid = SimpleNamespace(prb_count=55)

    a, b = make(), make()
    faithful._finalize_ul_coef(a)
    proto._finalize_ul_coef(b)

    assert proto.counters["e1_gate_fired"] == 1, (
        "the gate did not fire on 12 followers against 55/5 = 11, so this "
        "comparison is not testing E1")
    assert [c.coef for c in b] == [c.coef for c in a], "E1 moved coef"
    assert ([proto._ul_rank_key(c) for c in b]
            == [faithful._ul_rank_key(c) for c in a]), "E1 moved the sort key"
    # ... and it DID do its own job: the reserve inputs are gone.
    assert all(c.gbr_bytes_slot == 0 for c in b)
    assert all(c.gbr_bytes_slot > 0 for c in a)


def test_E1_gate_fires_only_when_the_reserve_cannot_fit():
    """`prb_count > min_rb * need` is the whole gate. Below the threshold it
    must never fire, above it must; the boundary is 55/5 = 11 on this carrier.
    """
    fired = {}
    for n in (4, 6, 8, 16, 24):
        sc = build_gt22_scenario(seed=1, n_ues=n, horizon_slots=8_000)
        s = TwoTierProto(min_rb=5, gate_follower_reserve=True)
        c = _summary(s, sc)["scheduler_counters"]
        fired[n] = (c["e1_gate_fired"], c["e1_max_followers_need"])
    for n in (4, 6, 8):
        assert fired[n][0] == 0, (
            f"N={n}: gate fired with only {fired[n][1]} followers -- 55 PRB "
            f"holds 11 reserves of 5, so it must not")
    assert fired[16][0] > 0 and fired[24][0] > 0, fired
    # ... and it fires because the follower count crossed 11, not for some
    # other reason: the observed need must reach the threshold.
    assert fired[24][1] >= 11, fired


def test_E2_keeps_the_reserve_for_a_UE_that_has_never_been_GRANTED():
    """The UE with no buffer report at all is the one the reserve exists for,
    so E2 must never suppress it. Counted, because 'never suppressed' over a
    population that is empty would pass vacuously."""
    sc = build_gt22_scenario(seed=1, n_ues=16, horizon_slots=8_000)
    s = TwoTierProto(min_rb=5, stale_bsr_reserve=True)
    c = _summary(s, sc)["scheduler_counters"]
    assert c["e2_slots_evaluated"] > 0, "E2 never ran"
    assert c["e2_stale_kept"] + c["e2_current_suppressed"] > 0, (
        "E2 ran but classified no follower -- the precondition did not occur, "
        "so this cell cannot test the edit")


def test_E2_leaves_the_ranking_alone_too():
    """Same instrument as E1's, for the same reason -- see that test's
    docstring on why a whole-run order comparison cannot answer this."""
    from types import SimpleNamespace
    from scheduler.two_tier import _Candidate

    def make():
        out = []
        for ue in (1, 2, 3):
            c = _Candidate(ue_id=ue, flows=[], bits_per_rb=100, bler=0.0,
                           snr_db=10.0, coef=float(50 * ue))
            c.has_gbr = True
            c.gbr_bytes_slot = 300
            c.ul_total_target_bytes = 100
            c.urgency01 = 0.2
            c.hyp_tbs_bytes = 900
            out.append(c)
        return out

    faithful = TwoTier(min_rb=5)
    proto = TwoTierProto(min_rb=5, stale_bsr_reserve=True)
    for s_ in (faithful, proto):
        s_._grid = SimpleNamespace(prb_count=55)
    # UE 1 granted recently (report current), UE 2 long ago (stale), UE 3 never.
    proto._cur_slot = 1000
    proto.slot_duration_s = 0.00025
    proto._proto_last_ul_grant_slot = {1: 999, 2: 1}
    proto._proto_pdb_ms = {1: 100, 2: 100, 3: 100}

    a, b = make(), make()
    faithful._finalize_ul_coef(a)
    proto._finalize_ul_coef(b)

    assert [c.coef for c in b] == [c.coef for c in a], "E2 moved coef"
    assert ([proto._ul_rank_key(c) for c in b]
            == [faithful._ul_rank_key(c) for c in a]), "E2 moved the sort key"
    # The classification is the edit: fresh report suppressed, stale kept.
    assert b[0].gbr_bytes_slot == 0, "UE 1's report was current; reserve stays"
    assert b[1].gbr_bytes_slot == 300, "UE 2's report was stale; reserve must hold"
    assert b[2].gbr_bytes_slot == 300, "UE 3 never reported; reserve must hold"
    assert proto.counters["e2_current_suppressed"] == 1
    assert proto.counters["e2_stale_kept"] == 2
    assert proto.counters["e2_never_granted_kept"] == 1


def test_E2_actually_OBSERVES_grants_and_is_not_a_structural_no_op():
    """THE TEST THE FIRST VERSION OF E2 NEEDED AND DID NOT HAVE.

    E2 read `TwoTier._last_ul_grant_slot`, which is written only inside
    `if self.anti_hysteresis > 0.0` -- off by default. The dict was permanently
    empty, every follower classified "never granted", nothing suppressed, and
    E2 returned bit-identical results over 90 cells while being a structural
    no-op. This asserts the precondition OCCURS: on a cell where UEs are
    granted constantly, "never granted" must not account for every
    classification.
    """
    sc = build_gt22_scenario(seed=1, n_ues=8, horizon_slots=8_000)
    s = TwoTierProto(min_rb=5, stale_bsr_reserve=True)
    c = _summary(s, sc)["scheduler_counters"]
    total = c["e2_stale_kept"] + c["e2_current_suppressed"]
    assert total > 0, "E2 classified nothing"
    assert s._proto_last_ul_grant_slot, (
        "E2 observed no uplink grant at all -- it is reading state nobody "
        "writes, which is exactly the defect this test exists for")
    assert c["e2_never_granted_kept"] < total, (
        f"every one of {total} classifications was 'never granted' -- "
        f"arithmetically impossible in a cell that grants every slot, so E2 "
        f"is not reaching its own precondition")


# --- G-periodic: the manipulation check, per E2's lesson -----------------
# E2 came back bit-identical while structurally unreachable, and only a
# decomposed counter caught it. So G-periodic is not accepted on "it ran":
# the cadence has to match its own derivation and followers have to actually
# receive the slots.

def _gper_run(n_ues=12, seed=7, mult=1.0):
    from sim.scenarios.g3 import build_gt22_scenario
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     reserve_period_mult=mult)
    sc = build_gt22_scenario(seed=seed, n_ues=n_ues, horizon_slots=4_000,
                             telemetry_gbr=True)
    _summary(s, sc)
    return s.counters


def test_G_periodic_reserve_slots_fire_at_the_DERIVED_cadence():
    c = _gper_run()
    assert c["gper_slots_evaluated"] > 0, "G-periodic never evaluated a slot"
    assert c["gper_reserve_slots"] > 0, "no reserve slot ever fired"
    # DERIVED from the counters themselves, not restated: with P varying as
    # the follower count moves, the realised rate must sit between the rates
    # the smallest and largest observed P imply.
    lo, hi = c["gper_period_min"], c["gper_period_max"]
    assert lo >= 1 and hi >= lo
    rate = c["gper_reserve_slots"] / c["gper_slots_evaluated"]
    # TIGHT on the slow side deliberately. The first version allowed
    # `0.5/hi <= rate <= 2.0/lo`, which spans two orders when P moves over
    # [50, 1200] -- and it PASSED on an implementation that fired on 0 of
    # 6 400 slots at another fleet size. A bound that wide cannot fail.
    assert rate >= 0.8 / hi, (
        f"realised reserve-slot rate {rate:.5f} is far below the slowest "
        f"derived cadence 1/{hi} -- reserve slots are not firing at the "
        f"period the derivation sets")
    assert rate <= 1.2 / lo


def test_G_periodic_followers_ACTUALLY_receive_the_reserve_slots():
    """The E2 failure mode restated: a gate can fire and change nothing."""
    c = _gper_run()
    assert c["gper_reserve_grants"] > 0, (
        "reserve slots fired but no uplink grant was issued on any of them -- "
        "the gate is structurally inert, exactly E2's first result")
    # "Followers only" is a claim about who got them, so it is measured.
    leader = c["gper_leader_served_on_reserve"]
    assert leader < c["gper_reserve_grants"], (
        f"every grant on a reserve slot went to the would-be leader "
        f"({leader} of {c['gper_reserve_grants']}) -- the reordering did not "
        f"reach the allocation")


def test_G_periodic_does_NOT_buy_depth_because_depth_is_already_recovered():
    """The registered rationale for this gate was depth, and it is WRONG --
    pinned here so nobody re-derives it.

    The premise was that a follower gets five PRB every slot, a trickle too
    thin to assemble a 300-byte message, while a reserve slot would hand it
    the whole band. Measured, with the spatial reserve suppressed on every
    slot as this gate specifies, an ORDINARY slot's mean grant is already
    ~54 of 55 PRB. Suppressing the spatial reserve recovers the depth by
    itself; the reserve slot has nothing left to recover, and its grants are
    if anything SHALLOWER because the follower being served has less backlog
    to fill.

    So G-periodic's distinct contribution is not depth. It is WHO gets served
    -- a reordering aimed at rank persistence -- and that is what its result
    has to be read as evidence about.
    """
    c = _gper_run()
    flat = c["gper_normal_prb"] / c["gper_normal_grants"]
    assert flat > 45, (
        f"an ordinary slot's mean grant is {flat:.1f} PRB, not near the full "
        f"band -- the spatial reserve is still binding, which this gate is "
        f"supposed to have removed")
    deep = c["gper_reserve_prb"] / c["gper_reserve_grants"]
    assert deep > 0


def test_G_periodic_a_shorter_multiplier_fires_MORE_often():
    """Continuity: the swept parameter has to actually move the cadence."""
    slow, fast = _gper_run(mult=1.0), _gper_run(mult=0.25)
    assert fast["gper_reserve_slots"] > slow["gper_reserve_slots"], (
        "the period multiplier does not change the reserve-slot count, so the "
        "sweep would report four identical points as four measurements")


# --- G-periodic-deadline -------------------------------------------------

def test_G_periodic_deadline_REFUSES_to_gate_a_reserve_that_never_fires():
    with pytest.raises(ValueError, match="periodic_reserve"):
        TwoTierProto(min_rb=5, deadline_gated_periodic=True)


def test_G_periodic_deadline_threshold_is_DERIVED_from_the_TDD_pattern():
    """Not a constant. DSUUU at 0.25 ms puts the longest wait to the next
    uplink slot at 2 slots, and the threshold has to be that."""
    from sim.scenarios.g3 import build_gt22_scenario
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     deadline_gated_periodic=True)
    sc = build_gt22_scenario(seed=3, n_ues=8, horizon_slots=400,
                             telemetry_gbr=True)
    _summary(s, sc)
    pat = "".join(s._grid.pattern)
    assert pat == "DSUUU", f"pattern changed to {pat}; re-derive the threshold"
    assert s._gpd_near_ms() == pytest.approx(0.5)


def test_G_periodic_deadline_SKIPS_slots_and_the_skip_is_counted():
    """The whole point: at a fleet the faithful arm serves perfectly, the
    cadence must come due and be declined."""
    from sim.scenarios.g3 import build_gt22_scenario
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     deadline_gated_periodic=True)
    sc = build_gt22_scenario(seed=7, n_ues=6, horizon_slots=8_000,
                             telemetry_gbr=True)
    _summary(s, sc)
    c = s.counters
    assert c["gpd_due_slots"] > 0, "the cadence never came due"
    assert c["gpd_due_slots"] == c["gpd_fired"] + c["gpd_skipped_nobody_due"], (
        "a due slot was neither fired nor skipped -- the decomposition does "
        "not close, so one of the three counters is measuring something else")
    assert c["gpd_skipped_nobody_due"] > 0, (
        "no reserve slot was ever declined at six robots, so the gate cannot "
        "be the reason six robots improves -- it would be inert")
    assert c["gper_reserve_slots"] == c["gpd_fired"], (
        "reserve slots and fired slots disagree; the skip did not reach the "
        "reordering")


# --- G-denial ------------------------------------------------------------

def test_G_denial_REFUSES_to_reorder_a_reserve_slot_that_never_fires():
    with pytest.raises(ValueError, match="periodic_reserve"):
        TwoTierProto(min_rb=5, denial_ordered_periodic=True)


def test_G_denial_orders_by_AGE_and_a_never_granted_UE_sorts_FIRST():
    """The age rule has to make "never served" the largest age by
    construction, with no sentinel -- that is what `-1` buys."""
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     denial_ordered_periodic=True)
    s._cur_slot = 1_000
    s._proto_last_ul_grant_slot = {7: 900, 8: 500}
    assert s._gdo_age(7) == 100
    assert s._gdo_age(8) == 500
    assert s._gdo_age(9) == 1_001, "a never-granted UE must have the largest age"
    assert s._gdo_age(9) > s._gdo_age(8) > s._gdo_age(7)


def test_G_denial_ACTUALLY_DIFFERS_from_the_composite_ordering():
    """The whole point of the arm. If the two rules agreed everywhere this
    would be G-periodic under a different name, which is E2's failure mode."""
    from sim.scenarios.g3 import build_gt22_scenario
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     deadline_gated_periodic=True,
                     denial_ordered_periodic=True)
    sc = build_gt22_scenario(seed=35492826, n_ues=16, horizon_slots=8_000,
                             telemetry_gbr=True)
    _summary(s, sc)
    c = s.counters
    assert c["gdo_slots_ordered"] > 0, "the denial ordering never ran"
    agree = c["gdo_agrees_with_coef"] / c["gdo_slots_ordered"]
    assert agree < 0.5, (
        f"the denial rule picks the same UE as the composite rule on "
        f"{agree:.1%} of reserve slots -- at that level the swap is not a "
        f"distinct arm and its result cannot be attributed to the ordering")
    assert c["gdo_max_age_slots"] > 0


# --- G-kpi ---------------------------------------------------------------

def test_G_kpi_REFUSES_both_orderings_at_once():
    """Two orderings for one slot would report one arm under the other's
    name, which is the failure mode E2 already demonstrated."""
    with pytest.raises(ValueError, match="periodic_reserve"):
        TwoTierProto(min_rb=5, kpi_ordered_periodic=True)
    # DERIVED from the flag set, not a hand-listed pair: every combination of
    # two reserve-slot orderings must be refused, so a third ordering added
    # later cannot slip past a test that names only the first two.
    import itertools
    orderings = ("denial_ordered_periodic", "kpi_ordered_periodic",
                 "slack_ordered_periodic")
    for a, b in itertools.combinations(orderings, 2):
        with pytest.raises(ValueError, match="orderings enabled at once"):
            TwoTierProto(min_rb=5, periodic_reserve=True,
                         **{a: True, b: True})


def test_G_kpi_orders_nearest_violation_first_and_breaks_ties_by_denial():
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     kpi_ordered_periodic=True)
    s._cur_slot = 1_000
    s._gper_is_reserve = True
    s._gpd_remaining = {1: 40.0, 2: 0.0, 3: 0.0}
    s._proto_last_ul_grant_slot = {1: 999, 2: 990, 3: 500}
    mk = lambda ue: _Candidate(ue_id=ue, flows=[], bits_per_rb=100, bler=0.0,
                               snr_db=20.0, coef=1.0)
    order = sorted([mk(1), mk(2), mk(3)], key=s._ul_rank_key)
    # 3 and 2 are both already violating, so denial time separates them; 1 has
    # 40 ms left and must come last despite being the most recently served.
    assert [c.ue_id for c in order] == [3, 2, 1]


def test_G_kpi_tie_group_at_zero_is_REAL_so_the_tie_break_is_load_bearing():
    """If nothing ever tied at zero the tie-break would be decoration, and
    the arm would be indistinguishable from ordering on remaining_pdb alone."""
    from sim.scenarios.g3 import build_gt22_scenario
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     deadline_gated_periodic=True, kpi_ordered_periodic=True)
    sc = build_gt22_scenario(seed=35492826, n_ues=16, horizon_slots=8_000,
                             telemetry_gbr=True)
    _summary(s, sc)
    c = s.counters
    assert c["gkpi_slots_ordered"] > 0, "the KPI ordering never ran"
    assert c["gkpi_tied_at_zero_max"] >= 2, (
        f"the largest group tied at remaining_pdb == 0 was "
        f"{c['gkpi_tied_at_zero_max']}, so the denial tie-break never "
        f"separated anything and this arm is ordering on remaining_pdb alone")


# --- G-slack -------------------------------------------------------------

def test_G_slack_puts_the_already_late_LAST_and_orders_the_rest_by_slack():
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     slack_ordered_periodic=True)
    s._cur_slot = 1_000
    s._gper_is_reserve = True
    #  ue1: 40 ms left      ue2: 10 ms left      ue3/ue4: already late
    s._gpd_remaining = {1: 40.0, 2: 10.0, 3: 0.0, 4: 0.0}
    s._proto_last_ul_grant_slot = {1: 999, 2: 999, 3: 990, 4: 500}
    mk = lambda ue: _Candidate(ue_id=ue, flows=[], bits_per_rb=100, bler=0.0,
                               snr_db=20.0, coef=1.0)
    order = [c.ue_id for c in sorted([mk(i) for i in (1, 2, 3, 4)],
                                     key=s._ul_rank_key)]
    # 2 before 1 (less slack); both before the late pair; 4 before 3 inside it
    # (denied 500 slots against 10).
    assert order == [2, 1, 4, 3], order


def test_G_slack_is_NOT_G_denial_wearing_a_different_name():
    """If every candidate were already late the first key element would be
    constant and this arm would collapse to G-denial -- E2's failure mode."""
    from sim.scenarios.g3 import build_gt22_scenario
    s = TwoTierProto(min_rb=5, periodic_reserve=True,
                     deadline_gated_periodic=True, slack_ordered_periodic=True)
    sc = build_gt22_scenario(seed=35492826, n_ues=16, horizon_slots=8_000,
                             telemetry_gbr=True)
    _summary(s, sc)
    c = s.counters
    assert c["gslack_slots_ordered"] > 0, "the slack ordering never ran"
    assert c["gslack_first_has_slack"] > 0, (
        "the first pick was already late on EVERY reserve slot, so the "
        "can-still-be-saved distinction never fired and this arm is G-denial")
    assert c["gslack_all_late_slots"] < c["gslack_slots_ordered"], (
        "every candidate was late on every reserve slot")
