"""The candidate stream, and its acceptance conditions.

`docs/g5-ranking-map.md` §4 registered these BEFORE the hook was built, and
one of them is strengthened relative to the grant hook's, for a stated
reason: the grant hook is a direct call at a fixed call site, so there is no
name to bind wrongly, while THIS hook reads each arm's ranking terms off its
own candidate object BY NAME. That is exactly the shape of the defect the
whole facility reacts to -- a probe bound to `self._ue` where the attribute
was `self._state`, which read zero for its control as well as its treatment.

  1. BIT-IDENTITY -- a run with a sink attached produces a byte-identical
     RunRecord to one without.
  2. FAILS LOUDLY -- a collector that saw nothing RAISES; a name that does
     not resolve RAISES; a retention cap RAISES rather than truncating.
  3. IT DOES NOT UNDER-COLLECT -- the condition added for this hook. A hook
     that binds but sees only some of the candidates would pass every test
     above while quietly answering a different question. Checked against an
     INDEPENDENT instrument: every UE granted on a slot must appear in that
     slot's ranking for the same slot and direction.
"""

from __future__ import annotations

import json

import pytest

from scheduler.rank_trace import (
    LossPointTally, NoCandidatesObserved, RankCollector, RankEntry,
    RankSnapshot, RankStreamOverflow, UnboundRankTerm, decisive_term, field,
)
from scheduler.reservation import Reservation
from scheduler.two_tier import TwoTier
from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.trace import GrantCollector

ARMS = {
    "PF": lambda: ProportionalFair(ewma_window_slots=200),
    "Reservation": lambda: Reservation(min_rb=5),
    "TwoTier": lambda: TwoTier(min_rb=5),
}


def _scenario(h=3000, n=4):
    return sweep_scenario(seed=1, n_ues=n, horizon_slots=h, load_mult=1.0)


def _rec(summary, sc, arm):
    return RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                  seed=1, flow_configs=sc.flows,
                                  summary=summary, arm={}, meta={})


def _traced(arm, h=3000, n=4):
    sched = ARMS[arm]()
    col = RankCollector()
    sched.rank_sink = col
    sc = _scenario(h, n)
    summary = run(sc, sched, cqi_delay_slots=8, record_timeseries=True)
    return sc, summary, col.finish()


# --- 1. BIT-IDENTITY -------------------------------------------------------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_attaching_a_rank_sink_changes_NOTHING_about_the_run(arm):
    sc = _scenario()
    plain = run(sc, ARMS[arm](), cqi_delay_slots=8, record_timeseries=True)
    sc2, traced, snaps = _traced(arm)
    assert snaps, "the sink saw nothing; the identity check would be vacuous"
    a = json.dumps(_rec(plain, sc, arm).to_dict(), sort_keys=True, default=str)
    b = json.dumps(_rec(traced, sc2, arm).to_dict(), sort_keys=True, default=str)
    assert a == b, f"attaching the rank sink moved {arm}'s run"


# --- 2. FAILS LOUDLY -------------------------------------------------------

def test_a_collector_that_saw_nothing_RAISES():
    with pytest.raises(NoCandidatesObserved):
        RankCollector().finish()
    assert RankCollector(allow_empty=True).finish() == []


def test_a_tally_that_saw_nothing_RAISES():
    with pytest.raises(NoCandidatesObserved):
        LossPointTally("UL").finish()


def test_a_name_that_does_not_resolve_RAISES_rather_than_defaulting():
    """THE ONE THAT MATTERS. `getattr(obj, name, default)` is how a mis-bound
    probe returns a plausible zero instead of an error."""
    class C:
        coef = 1.0
    assert field(C(), "coef") == 1.0
    with pytest.raises(UnboundRankTerm):
        field(C(), "coeff")


def test_the_retention_cap_RAISES_rather_than_truncating():
    col = RankCollector(max_snapshots=2)
    s = RankSnapshot(0, "UL", "PF", ("-metric",),
                     (RankEntry(0, (-1.0,), (2,)),))
    col(s); col(s)
    with pytest.raises(RankStreamOverflow):
        col(s)


def test_a_key_narrower_than_its_declared_terms_RAISES():
    """A key whose width drifts from its term names would be re-indexed
    silently, attributing a loss to the wrong tier."""
    with pytest.raises(UnboundRankTerm):
        RankSnapshot(0, "UL", "TwoTier", ("a", "b", "c", "d"),
                     (RankEntry(0, (1, 2), (2,)),))


# --- the declared factor names must ALL resolve on a REAL candidate --------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_every_declared_factor_name_resolves_on_a_real_candidate(arm):
    """The construction-time binding assertion, as a test. If a factor name
    were wrong, `field` would raise inside the run -- so reaching a non-empty
    stream at all IS the assertion, and this pins the recorded names so a
    silent rename cannot shrink what is collected."""
    _sc, _s, snaps = _traced(arm)
    ul = [s for s in snaps if s.direction == "UL"]
    assert ul, f"{arm} produced no UL ranking at all"
    names = {n for e in ul[0].entries for n, _v in e.factors}
    assert names, f"{arm} recorded no factors"
    for s in ul:
        for e in s.entries:
            assert {n for n, _ in e.factors} == names, \
                f"{arm}'s recorded factor set is not stable across slots"


# --- 3. IT DOES NOT UNDER-COLLECT -----------------------------------------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_every_GRANTED_ue_appears_in_that_slot_s_ranking(arm):
    """The under-collection guard, checked against an INDEPENDENT instrument.

    A hook that binds but collects only some candidates passes every other
    condition here while answering a different question. The grant stream
    (`sim/trace.py`) is built at a different call site by different code, so
    a UE it records as granted on slot S in direction D is an oracle: it MUST
    have been in the candidate set the sort produced for (S, D).
    """
    sched = ARMS[arm]()
    ranks, grants = RankCollector(), GrantCollector()
    sched.rank_sink = ranks
    sc = _scenario()
    run(sc, sched, cqi_delay_slots=8, record_timeseries=True,
        grant_sink=grants)
    snaps, gr = ranks.finish(), grants.finish()

    ranked: dict[tuple[int, str], set[int]] = {}
    for s in snaps:
        ranked.setdefault((s.slot_index, s.direction), set()).update(
            e.ue_id for e in s.entries)

    checked = 0
    for g in gr:
        if g.retx_count:      # a retransmission bypasses the sort by design
            continue
        seen = ranked.get((g.slot_index, g.direction))
        assert seen is not None, \
            f"{arm}: granted UE {g.ue_id} on slot {g.slot_index} " \
            f"{g.direction} but NO ranking was recorded for that slot"
        assert g.ue_id in seen, \
            f"{arm}: granted UE {g.ue_id} on slot {g.slot_index} " \
            f"{g.direction} is absent from that slot's candidate set -- the " \
            f"hook binds but under-collects"
        checked += 1
    assert checked > 0, "no first-transmission grants to check against"


@pytest.mark.parametrize("arm", sorted(ARMS))
def test_a_ue_appears_at_most_once_per_snapshot(arm):
    _sc, _s, snaps = _traced(arm)
    for s in snaps:
        ids = [e.ue_id for e in s.entries]
        assert len(ids) == len(set(ids)), f"{arm} ranked a UE twice"


# --- the reading itself ----------------------------------------------------

def test_decisive_term_names_the_first_differing_tier():
    a = RankEntry(0, (0, 1, 0, -5.0), ())
    b = RankEntry(1, (0, 1, 0, -3.0), ())
    assert decisive_term(a, b) == 3
    c = RankEntry(2, (0, 0, 0, -3.0), ())
    assert decisive_term(a, c) == 1


def test_a_FULL_TIE_reports_None_and_that_is_map_row_U1():
    """A tie is a MEASUREMENT -- the declaration-order artefact, the same
    finding that stopped G12's ordering being promoted. It must not read as
    a failed trace, so it gets its own return value rather than a fallback."""
    a = RankEntry(0, (0, 1, 0, -5.0), ())
    b = RankEntry(1, (0, 1, 0, -5.0), ())
    assert decisive_term(a, b) is None
    t = LossPointTally("UL")
    t(RankSnapshot(0, "UL", "TwoTier", ("w", "x", "y", "z"), (a, b)))
    t.finish()
    assert t.ties[(1, 0)] == 1
    assert t.term_totals()["TIED (declaration order)"] == 1
