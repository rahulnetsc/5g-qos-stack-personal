"""TwoTierProto -- a LABELLED DIVERGENCE from the two-tier port, not a port.

READ THIS FIRST, BECAUSE THE DISTINCTION IS THE POINT.

`scheduler/two_tier.py` is a PORT. Every branch in it carries a
`ia_p5g_scheduler.c` line citation, and that citability is most of what makes
this project's findings about the deployed scheduler credible -- a claim like
*"Tier-1.5's floor cannot arm in the fault it exists for"* is worth something
only because the port reproduces the C rather than improving on it. **Every
guarantee result to date (G1, G2, G3, G9, G10, G12) is measured against that
port**, so it is not touched here and must not be.

**NOTHING IN THIS FILE IS PORTED.** Each edit below is a proposed CHANGE to the
deployed scheduler, motivated by a measurement, and it carries no C citation
because there is no C to cite. A future reader must never mistake one of these
for ground truth. `docs/oai-port-map.md` carries a row saying DIVERGENCE for
exactly that reason.

WHAT IT COSTS FOR COMPARABILITY, stated rather than discovered later:

  * **A Proto result is not comparable with a hardware measurement**, because
    no hardware runs this. It is comparable only with the faithful arm, on the
    same seeds -- which is what makes the within-seed paired design load-bearing
    here rather than merely tidy.
  * **A Proto result cannot settle a question about the product.** If Proto
    fixes something, the finding is *"this change would fix it"*, never
    *"the product does X"*.
  * **It adds a fourth arm to every comparison that includes it**, so a
    guarantee's arm count is no longer three and any "all three arms" phrasing
    has to be re-read.

--------------------------------------------------------------------------
EVERY EDIT IS BEHIND ITS OWN FLAG AND EVERY FLAG DEFAULTS OFF
--------------------------------------------------------------------------

With all flags off this class must be **byte-identical to `TwoTier`**, and that
is asserted rather than assumed: `sim/tests/test_two_tier_proto.py` runs both
over several scenarios and seeds and requires the full driver summary to match.
An arm whose "off" state has drifted cannot attribute anything to its edits.

The edits interact, so they land ONE AT A TIME, each with its own registration,
its own regression run, and its own commit.

--------------------------------------------------------------------------
E1 -- GATE THE FOLLOWER RESERVE
--------------------------------------------------------------------------

**The mechanism being changed.** FIX-2 caps every uplink DATA grant by
reserving `min_rb` PRB for each still-unserved GBR candidate ranked below the
current one (`two_tier.py`, `ia_p5g_scheduler.c:3016-3030,3105-3124`):

    reserve_rb = gbr_below[i] * min_rb
    cap        = max(prbs_left - reserve_rb, min_rb)

It exists to stop one saturating UE taking the whole BWP while a different UE
holds an unmet GBR guarantee -- a real production incident.

**Why it needs a gate.** The subtraction has no feasibility test. On a 55-PRB
carrier with `min_rb = 5`, **eleven qualifying followers exhaust the band**, and
beyond that `prbs_left - reserve_rb` goes negative for every candidate, so the
`max(..., min_rb)` floor pins **every** UE -- including the top-ranked one --
at `min_rb`. Measured on G3's own cell
(`docs/g3-stress-experiment-2026-09-09.md` §3.4): the top-ranked candidate is
clamped on **0 % of slots at N <= 8, 3.8 % at N=12, and 100 % at N=16 and
N=24**, and at N=24 the largest grant in 337 599 is 5 PRB. **The
anti-starvation reserve produces the starvation once the fleet exceeds
`bwp / min_rb`.**

**The edit.** Apply the reserve only when it fits -- when
`prb_count > min_rb * n_followers_need` -- and otherwise fall through to greedy
by rank, which is what the scheduler does when `gbr_below` is all zeros anyway.

**HOW IT IS IMPLEMENTED WITHOUT TOUCHING THE PORT, and why this seam is exact.**
`gbr_below[i]`'s reverse scan counts candidates with
`not sched_inactive and has_gbr and gbr_bytes_slot > 0`, and `gbr_bytes_slot`
has exactly **two** live readers after candidate construction (verified by
grep): that scan, and `B_eff`'s `if c.has_gbr and c.gbr_bytes_slot > 0:
b_eff = max(b_eff, c.gbr_bytes_slot)`. So zeroing `gbr_bytes_slot` removes the
reserve, and folding its value into `ul_total_target_bytes` first leaves `B_eff`
**arithmetically unchanged**:

    b_eff = max(ul_total_target_bytes, ue_backlog, gbr_bytes_slot)      # before
          = max(max(ul_total_target_bytes, gbr_bytes_slot), ue_backlog)  # after

Both are the same maximum over the same three numbers. The transform is applied
in `_finalize_ul_coef`, which runs immediately before the sort -- **after**
`super()` has finalised `coef`, and `gbr_bytes_slot` does not feed `coef`. **So
E1 changes grant SIZING only and cannot change the ranking**, which is asserted
by a rank-stream identity test rather than argued.

**ONE OBSERVABILITY SIDE-EFFECT, stated.** `_emit_rank_snapshot` runs after the
sort, so on a Proto run with E1 active the rank trace's `gbr_bytes_slot` factor
reads the post-transform value (0) and `ul_total_target_bytes` the folded one.
The pre-transform values are kept on the candidate as
`proto_orig_gbr_bytes_slot` so a Proto rank analysis can still report the
faithful quantities.

--------------------------------------------------------------------------
E2 -- TARGET THE RESERVE AT STALE BUFFER REPORTS
--------------------------------------------------------------------------

**The argument.** The reserve exists so that a UE the gNB has stopped serving
still gets a grant, and therefore still sends a buffer-status report. Reserving
band for a follower whose report is **already current** spends PRB on
information the gNB is holding. So the reserve should be aimed at followers
whose report has gone stale, not at every follower with an unmet obligation.

**THE STALENESS THRESHOLD IS DERIVED, AND WHICH DERIVATION IS USED MATTERS.**
Two were available and the choice is forced by an architectural boundary, not
by preference:

  * **The BSR periodicity** is the natural quantity -- a report is stale once a
    period has passed. It is **not reachable**: the periodic-BSR timer lives in
    `sim/bsr.py`, and `scheduler/` must not import `sim/` (that is what keeps
    the scheduler library free of simulator-side state). Reading it would mean
    a real gNB reading a UE-side constant, which no gNB can do.
  * **The tightest PDB among the UE's currently-backlogged logical channels**
    IS reachable, through the port's own `_ul_best_pending_pdb_ms(ue_id,
    buffers)` -- the same helper Tier-1.5's floor uses for its own theta. **A
    report older than the deadline of the tightest flow it describes can no
    longer be relied on for that flow**, which is the property the reserve
    cares about.

So: **stale iff the UE's last uplink grant is older than its own tightest
pending PDB.** Both terms are the scheduler's own; no number is chosen here.

**The age proxy, stated because it is a proxy.** A BSR arrives with a grant, so
the slot of a UE's last uplink grant is when the gNB last had the chance to
refresh that UE's report. It is an upper bound on report freshness rather than
the report's own timestamp, which the gNB does not keep. **A UE never granted at
all has no report and is therefore maximally stale**, which keeps the reserve
pointed at exactly the UE it was built for.

**AND THIS ARM KEEPS ITS OWN RECORD OF THAT, WHICH THE FIRST VERSION DID NOT --
the bug is recorded because the shape recurs.** `TwoTier` has a
`_last_ul_grant_slot` dict that looks exactly right, and E2's first version read
it. **It is populated only inside `if self.anti_hysteresis > 0.0`** (`allocate`,
"bookkeeping for the anti-hysteresis diagnostic only"), and that damper defaults
off -- so the dict was permanently EMPTY, every follower classified as
"never granted", nothing was ever suppressed, and **E2 was a structural no-op
that ran to completion over 90 cells and returned bit-identical results.**

That is CLAUDE.md's unreachable-mechanism class, built fresh: an edit whose
precondition cannot occur because it borrows state maintained under an unrelated
flag. **What caught it was the DECOMPOSED counter** -- `e2_never_granted_kept ==
e2_stale_kept == 757 143 of 757 143` is arithmetically impossible in a cell where
UEs are granted every slot, which is the "does this number factor into the run's
own dimensions" signature. A single `e2_suppressed` total would have read 0 and
been reported as a finding about the mechanism instead of a defect in the edit.

So `TwoTierProto` maintains `_proto_last_ul_grant_slot` itself, unconditionally
while E2 is on, from the allocations `allocate` actually returns.

**Same seam as E1**, so the same exactness argument applies: the reserve
contribution of a *current* follower is removed by folding `gbr_bytes_slot`
into `ul_total_target_bytes` and zeroing it, leaving `B_eff` unchanged and the
ranking untouched.

**E1 AND E2 COMPOSE BUT ARE NOT VALIDATED TOGETHER.** E1 suppresses the whole
reserve when it cannot fit; E2 suppresses the part of it aimed at UEs that do
not need it. Enabling both is a third configuration and is not what either
registration measures.

--------------------------------------------------------------------------
G-DEPTH -- BOUND THE RESERVE'S DEPTH RATHER THAN GATING IT ON/OFF
--------------------------------------------------------------------------

**The measurement this exists to answer.** E1 gates the reserve on feasibility
and moves no boundary; E2 removes it essentially always and moves the boundary
but loses the top of the axis. The pair localises the cost: the reserve is
harmful just BELOW the boundary, where it fits and is applied in full, and
protective above it (`docs/g3-stress-experiment-2026-09-09.md` §18.2).

**So the reserve's DEPTH is the continuous variable, and E1's gate is the
K = floor(prb_count / min_rb) - 1 point on it.** Reserve for at most `K`
followers, chosen BY NEED rather than by rank position, and suppress the rest.

**WHY THE OBVIOUS K IS THE WRONG ONE, measured before this was built.**
`floor(prb_count / min_rb) - 1` is 10 on a 55-PRB carrier at `min_rb = 5`, and
a bound of 10 binds only when the qualifying-follower count exceeds 10 --
**the identical threshold E1 fires at.** `scripts/g3_gate_population_probe.py`
confirms it directly: the "need >= 11" and "need > 10" columns are equal at
every fleet size, and both are **0.0 % at N = 4 through 10**, where G3's
boundary of 7 sits. So the specified K inherits E1's blind spot exactly.

**The harm is continuous in the follower count well before the reserve stops
fitting.** Derived from the probe's modal `need` per fleet size, the top-ranked
candidate's own cap is:

    N = 8   need 6    reserve 25 PRB   leader capped at 30 of 55
    N = 10  need 8    reserve 35 PRB   leader capped at 20 of 55
    N = 12  need 11   reserve 50 PRB   leader capped at  5 of 55

**K is therefore swept rather than fixed**, and `K = None` derives the
specified `floor(prb_count / min_rb) - 1` so that variant is scored too.

--------------------------------------------------------------------------
--------------------------------------------------------------------------
G-PERIODIC -- MAKE THE RESERVE TEMPORAL INSTEAD OF SPATIAL
--------------------------------------------------------------------------

Every other gate here trades in the same dimension: how much band to hold back
from the leader on EVERY slot. This one changes the dimension. **The spatial
reserve is removed entirely, and every P-th slot becomes a RESERVE SLOT on
which followers rank first.** On the other P-1 slots the leader takes the full
band unreserved.

**Why the measured failure fits it.** The failure is a DEPTH failure, not a
frequency one: an urgent flow wins the ranking and receives a block too small
to carry its 300-byte heartbeat. A depth cap of K = 4 still leaves the leader
35 of 55 PRB; a reserve slot leaves it all 55 on non-reserve slots. And the
followers plausibly do better as well -- five PRB every slot is a trickle that
may never assemble a message, whereas the whole band once every P slots is a
grant that carries one.

**HOW P IS DERIVED. It is not picked, and it is not a round number.** The
requirement that fixes it is the one the clause is about: every follower must
get a real grant inside the tightest packet delay budget in the workload.

    pdb_slots = min(f.pdb_ms for every backlogged flow) / slot_ms
    rounds    = ceil(n_followers / slot.max_sched_ues)
    P*        = max(1, floor(pdb_slots / rounds))

`rounds` is there because a reserve slot serves at most `max_sched_ues` UEs, so
covering F followers takes that many reserve slots; P* is what makes one full
cycle fit inside one PDB. **Each input is read live** -- the PDB from the
candidates' own flows, the cap from the slot -- so P adapts to fleet size
instead of encoding one. On this workload the tightest PDB is telemetry's
100 ms, which is 400 slots at 0.25 ms, and at the deployment's cap of 4 that
gives P* = 200 at N = 8, 133 at N = 12, 100 at N = 16 and 66 at N = 24.

**Then swept around it**, by a multiplier on P*, because the derivation fixes
the order of magnitude and not the constant.

**WHAT "FOLLOWERS ONLY" MEANS, precisely, since the term is relative to a
leader and a reserve slot may not have one yet.** On a reserve slot the UL
ranking key's Tier 2 -- the composite coefficient -- is REVERSED, and Tiers 1
and 1.5 are left exactly as they are. So:

  * **the rule is a reordering, not a reference to any previous slot**, which
    is what makes it total. It is well defined on **slot 0** (which is a
    reserve slot, since `0 % P == 0`) with no special case, and if no candidate
    is backlogged there it simply has no effect.
  * **the leader is not excluded, it is placed last** among ordinary data UEs.
    Whether that amounts to "followers only" in practice is MEASURED rather
    than asserted -- `gper_leader_served_on_reserve` counts the times the
    would-be leader still received a grant on a reserve slot.
  * **Tier 1 (`sched_inactive`) and Tier 1.5 (`floor_fire`) are untouched.**
    Demoting a control-plane candidate would break SRB delivery, and demoting a
    fired floor would disable the very rescue Tier 1.5 exists for. This gate
    has no business touching either.
  * **on a fully tied slot it does nothing.** `list.sort` is stable and
    reversing the sign of a tier does not reorder equal values, so candidates
    that tie on `coef` keep declaration order -- which is attach order -- on a
    reserve slot exactly as on any other. The gate only reorders candidates
    that genuinely differ.

--------------------------------------------------------------------------
--------------------------------------------------------------------------
G-PERIODIC-DEADLINE -- SKIP THE RESERVE SLOT WHEN NOTHING NEEDS RESCUING
--------------------------------------------------------------------------

**The one thing G-periodic costs.** At the derived period it takes the 8-14
band to 10/10 and holds the top, and its only regression is at **six robots**,
where part 1 falls 20 -> 18. Six robots is a fleet the faithful arm already
serves perfectly, so a reserve slot there demotes the leader with no starvation
to repay it. This gate fires the reserve slot **only when some follower is
actually near its deadline**.

**THE CONDITION IS DERIVED, from `remaining_pdb`'s own measured structure and
the TDD pattern -- not picked.** `_ul_gbr_and_pdb` already computes
`remaining_pdb = max(0, pdb_ms - age_ms)` per candidate, and its distribution
over a real run is **bimodal**: a spike of 27 822 samples at exactly 0 ms, then
a flat tail of roughly 230 per millisecond bin
(`scripts/g3_gate_population_probe.py`, N = 8).

The line has to separate those two populations, and the TDD pattern says where
it goes. `DSUUU` at 0.25 ms puts the **longest wait to the next uplink slot at
2 slots, 0.50 ms**, so a flow with less than that left cannot be saved by the
next opportunity. That is what "near its PDB" has to mean, and it lands in the
**empty region between the spike and the tail**: 11.35 % of samples sit at or
below 0.50 ms and 11.44 % at or below 1.00 ms, so the operator choice moves the
population by 0.09 points. **A threshold on a quantised value's own level is a
coin flip (CLAUDE.md); this one is deliberately placed where no data sits.**

**`_URG_BARRIER_CAP` is why the port's own rescue does not already do this.**
The composite's urgency term is bounded -- `Phi(u) = u^2 / (1 - min(u, 0.97) +
0.03)` maxes at ~16.7 -- and measured `urgency01` never exceeds **0.40** on
this workload, so the barrier never engages. Urgency reaches the RANKING and
still cannot rescue a starved flow; this gate gives the deadline a decision it
can actually carry.

--------------------------------------------------------------------------
--------------------------------------------------------------------------
G-DENIAL -- ORDER A RESERVE SLOT BY DENIAL TIME, NOT BY THE COMPOSITE
--------------------------------------------------------------------------

**This corrects a claim I made about G-periodic and did not measure.** That
gate's docstring said reversing Tier 2 serves *"the follower that keeps losing
the ordinary ranking"*. Measured, it picks that robot on **2.6-10.3 %** of
reserve slots, and the rank correlation between the implemented order and
longest-denied is **-0.29 at N = 8, -0.19 at N = 12 and +0.39 at N = 24** --
so below the boundary it orders candidates *against* denial time. The
improvement G-periodic produced is real; the reason given for it was not.

**Why the composite cannot express denial time.** `coef` is
`(base_q + urg) * hyp_tbs_bytes`. Denial appears only inside `base_q`, which is
`sum(vq_ul)` over LCGs and is clamped to `min(backlog_bits, 5 * target_window)`
(`two_tier.py`, `_update_vq_ul`) -- so it **saturates**, and past that a robot
denied 50 slots and one denied 500 are indistinguishable. `hyp_tbs_bytes` then
multiplies the whole sum by a channel term that has nothing to do with denial.

**So Tier 2 is replaced rather than negated on a reserve slot**, by the
quantity the slot exists to bound: slots since that UE's last uplink grant. A
UE never granted takes `self._cur_slot - (-1)`, which is the largest age
available by construction, so "never served" sorts first without a sentinel.

**Tiers 1, 1.5 and the tie-break still pass through untouched**, and the
deadline gate still decides WHETHER a slot fires -- this changes only the order
within one that does.

**KNOWN LIMITATION, registered before the run so a weak result is not
misread.** `_proto_last_ul_grant_slot` records the last grant to the **UE**,
not to the starved flow on it. A robot whose camera is being served looks
recently granted while its telemetry starves. If this underperforms, that is
the first thing to check rather than concluding denial time is the wrong
quantity.

--------------------------------------------------------------------------
--------------------------------------------------------------------------
G-KPI -- ORDER A RESERVE SLOT BY CLOSENESS TO A KPI VIOLATION
--------------------------------------------------------------------------

**What it fixes.** G-denial orders by denial time and wins G3's liveness parts
(part-1s boundary 8 -> 12, part 1 at N = 24 9 -> 10) while LOSING the latency
part -- part 3 falls 10 -> 9 at N = 7 and 5 -> 0 at N = 16. Denial time says who
has waited longest; it says nothing about whose data is closest to being late.
This orders by the deadline itself.

**The quantity is already computed by the port.** `_ul_gbr_and_pdb` returns
`remaining_pdb = max(0, pdb_ms - age_ms)` per UE, the same number the deadline
GATE reads. Smallest remaining sorts first, so the UE nearest a violation is
served first.

**AND IT NEEDS A TIE-BREAK, which the measurement forced.** `remaining_pdb` is
**bimodal**: a spike of 27 822 samples at **exactly 0 ms** against a flat tail
of ~230 per ms bin (`scripts/g3_gate_population_probe.py`). So on a reserve slot
a large fraction of candidates are tied at zero -- all already violating -- and
ordering on `remaining_pdb` alone would separate them by declaration order,
which is attach order, i.e. arbitrarily. **The tie-break is denial time**, so
among UEs already past their deadline the longest-denied is served first:

    key element 3 = (remaining_pdb_ms, -slots_since_last_ul_grant)

**This composes G-denial rather than replacing it** -- denial ordering is what
happens inside the tied-at-zero group, which is where G-denial's own gains came
from. `gkpi_tied_at_zero_max` reports how large that group gets, so whether the
tie-break is load-bearing is measured rather than assumed.

**A nested tuple, deliberately, not an arithmetic pack.** The key must stay five
elements wide -- `scheduler/rank_trace.py` raises `UnboundRankTerm` on a width
change, and the campaign attaches a rank sink -- and nesting keeps both
components readable where a scaled sum would hide the composition.

--------------------------------------------------------------------------
--------------------------------------------------------------------------
G-SLACK -- SERVE WHO CAN STILL BE SAVED; THE ALREADY-LATE GO LAST
--------------------------------------------------------------------------

**The defect in G-kpi this corrects.** `remaining_pdb == 0` does not mean *about
to violate*, it means **already violating** -- `_ul_gbr_and_pdb` computes
`max(0, pdb_ms - age_ms)`, so it floors. G-kpi orders ascending and therefore
serves that group FIRST. Under overload that is close to backwards: the packet
is already late, so the slot buys a miss either way, while a robot that could
still have been saved slides into the same state. This is the standard way
earliest-deadline-first degrades once the system is infeasible.

**And the group is large, which is why the treatment matters.** Measured at
**11.4 % of classifications at N = 8 and 12.8 % at N = 12**
(`scripts/g3_gate_population_probe.py`), against a flat tail of ~230 samples per
ms bin. Whatever this arm does with that spike dominates its behaviour.

**So the order is: positive slack first, ascending; already-late last,
longest-denied first among themselves.**

    key element 3 = (1 if remaining <= 0 else 0, remaining, -denial_slots)

`remaining` is already 0 for the late group, so the same three-tuple serves both
branches and the denial tie-break applies inside each.

**WHAT WOULD MAKE THIS ARM A NO-OP, so it is measured rather than assumed.** If
every candidate on a reserve slot is already late, the first element is constant
and the arm collapses to G-denial under a different name -- E2's failure mode.
`gslack_first_has_slack` counts the slots where the first pick still had slack,
and a test refuses the arm if that is never true.

--------------------------------------------------------------------------
--------------------------------------------------------------------------
E3 -- A DEADLINE TERM IN UPLINK GRANT SIZING (not built yet)
--------------------------------------------------------------------------

Registered, not implemented, and **it may be unnecessary**. Today
`prbs_used = min(prbs_left, max_rbSize, prbs_needed)` and nothing
urgency-derived enters. But E3 is **inert behind the ungated reserve**: no
demand can exceed a `max_rbSize` the reserve has already set to `min_rb`. **E1
may therefore make E3 live without E3 being written, and that is measured
before E3 is built.**
"""

from __future__ import annotations

from typing import Any

from .two_tier import TwoTier, _Candidate

__all__ = ["TwoTierProto", "PROTO_FLAGS"]

#: Every flag, with the edit it gates. Named here so a runner can enumerate
#: them rather than restating a list -- and so a flag added without a
#: registration is visible.
PROTO_FLAGS: tuple[str, ...] = (
    "gate_follower_reserve",      # E1
    "stale_bsr_reserve",          # E2
    "depth_bounded_reserve",      # G-depth
    "periodic_reserve",           # G-periodic
    "deadline_gated_periodic",    # G-periodic-deadline
    "denial_ordered_periodic",    # G-denial
    "kpi_ordered_periodic",       # G-kpi
    "slack_ordered_periodic",     # G-slack
    "deadline_sizing",            # E3, not implemented
)


#: Only reached when no candidate declares a usable PDB, which cannot happen
#: on a backlogged slot -- present so the derivation has no implicit default.
_GPER_PDB_FALLBACK_MS = 300


class TwoTierProto(TwoTier):
    """The faithful port plus optional, individually-flagged divergences.

    All flags off == `TwoTier`, asserted by `sim/tests/test_two_tier_proto.py`.
    """

    def __init__(self, *args: Any,
                 gate_follower_reserve: bool = False,
                 stale_bsr_reserve: bool = False,
                 depth_bounded_reserve: bool = False,
                 reserve_depth: int | None = None,
                 periodic_reserve: bool = False,
                 reserve_period_mult: float = 1.0,
                 deadline_gated_periodic: bool = False,
                 denial_ordered_periodic: bool = False,
                 kpi_ordered_periodic: bool = False,
                 slack_ordered_periodic: bool = False,
                 deadline_sizing: bool = False,
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.gate_follower_reserve = bool(gate_follower_reserve)
        self.stale_bsr_reserve = bool(stale_bsr_reserve)
        self.depth_bounded_reserve = bool(depth_bounded_reserve)
        #: G-depth's bound. None derives `floor(prb_count / min_rb) - 1`, the
        #: variant registered in the sweep -- which the population probe shows
        #: binds at the same follower count E1 fires at, so the sweep sets it
        #: explicitly rather than relying on the derived value.
        self.reserve_depth = reserve_depth
        self.periodic_reserve = bool(periodic_reserve)
        #: Multiplier on the DERIVED P*. 1.0 is the derivation itself.
        self.reserve_period_mult = float(reserve_period_mult)
        self.deadline_gated_periodic = bool(deadline_gated_periodic)
        self.denial_ordered_periodic = bool(denial_ordered_periodic)
        self.kpi_ordered_periodic = bool(kpi_ordered_periodic)
        self.slack_ordered_periodic = bool(slack_ordered_periodic)
        n_orderings = sum((self.denial_ordered_periodic,
                           self.kpi_ordered_periodic,
                           self.slack_ordered_periodic))
        if n_orderings > 1:
            raise ValueError(
                f"{n_orderings} reserve-slot orderings enabled at once -- one "
                f"arm's numbers would be reported under another's name.")
        if slack_ordered_periodic and not periodic_reserve:
            raise ValueError(
                "slack_ordered_periodic without periodic_reserve -- it "
                "reorders a reserve slot that would never fire.")
        if kpi_ordered_periodic and not periodic_reserve:
            raise ValueError(
                "kpi_ordered_periodic without periodic_reserve -- it reorders "
                "a reserve slot that would never fire.")
        if denial_ordered_periodic and not periodic_reserve:
            raise ValueError(
                "denial_ordered_periodic without periodic_reserve -- it "
                "reorders a reserve slot that would never fire.")
        if deadline_gated_periodic and not periodic_reserve:
            raise ValueError(
                "deadline_gated_periodic without periodic_reserve -- it gates "
                "a reserve slot that would never fire, so the arm would "
                "report the faithful numbers under a divergence name.")
        self.deadline_sizing = bool(deadline_sizing)
        if reserve_depth is not None and not depth_bounded_reserve:
            raise ValueError(
                "reserve_depth set without depth_bounded_reserve -- a bound "
                "that silently does nothing would be reported as a swept "
                "point that ran.")
        for name in ("deadline_sizing",):
            if getattr(self, name):
                raise NotImplementedError(
                    f"{name} is REGISTERED but not implemented -- see this "
                    f"module's docstring. Enabling a flag whose edit does not "
                    f"exist would report the faithful arm's numbers under the "
                    f"divergence arm's name, which is the worst available "
                    f"failure mode for a comparison.")
        #: Observability, because an edit that cannot be shown to have fired is
        #: indistinguishable from one that is switched off (CLAUDE.md's
        #: unreachable-mechanism rule). Surfaced through the driver as
        #: `summary["scheduler_counters"]` alongside the inherited counters.
        self.counters.update({
            "e1_slots_evaluated": 0,
            "e1_gate_fired": 0,          # slots where the reserve was suppressed
            "e1_candidates_suppressed": 0,
            "e1_max_followers_need": 0,
            "e2_slots_evaluated": 0,
            "e2_current_suppressed": 0,  # followers whose report was fresh
            "e2_stale_kept": 0,          # followers the reserve still protects
            "e2_never_granted_kept": 0,  # ... of which had no report at all
            "gdepth_slots_evaluated": 0,
            "gdepth_slots_bound_binding": 0,   # slots where need exceeded K
            "gdepth_candidates_suppressed": 0,
            "gdepth_max_need": 0,
            "gdepth_depth_cap": -1,            # the K actually used
            "gper_slots_evaluated": 0,
            "gper_reserve_slots": 0,           # ... of which were reserve slots
            "gper_period_last": -1,            # the P most recently derived
            "gper_period_min": -1,
            "gper_period_max": -1,
            "gper_reserve_grants": 0,          # UL grants issued on them
            "gper_reserve_prb": 0,
            "gper_normal_grants": 0,
            "gper_normal_prb": 0,
            "gper_leader_served_on_reserve": 0,
            "gpd_due_slots": 0,          # cadence said fire
            "gpd_fired": 0,              # ... and someone was near a deadline
            "gpd_skipped_nobody_due": 0,  # ... and nobody was
            "gpd_urgent_candidates": 0,
            "gdo_slots_ordered": 0,
            "gdo_agrees_with_coef": 0,     # ... where BOTH rules pick the same UE
            "gdo_never_granted_first": 0,  # ... where the first pick never had one
            "gdo_max_age_slots": 0,
            "gkpi_slots_ordered": 0,
            "gkpi_first_already_violating": 0,   # first pick at remaining 0
            "gkpi_tied_at_zero_max": 0,          # largest tied group seen
            "gkpi_tied_at_zero_total": 0,
            "gkpi_agrees_with_denial": 0,        # same first pick as G-denial
            "gkpi_agrees_with_coef": 0,
            "gslack_slots_ordered": 0,
            "gslack_first_has_slack": 0,   # the first pick could still be saved
            "gslack_all_late_slots": 0,    # ... slots where nobody could
            "gslack_late_total": 0,
            "gslack_agrees_with_kpi": 0,
        })
        #: G-periodic per-slot state, recomputed in `_finalize_ul_coef` (which
        #: runs BEFORE the sort) and read by `_ul_rank_key` (which runs during
        #: it). Cached rather than recomputed per candidate because the sort
        #: calls the key once per candidate and P is a per-slot quantity.
        self._gper_is_reserve = False
        self._gper_leader_ue: int | None = None
        self._gper_cap = 4
        #: Slots since the last reserve slot. A COUNTER, not `slot % P`: P is
        #: derived per slot from the live follower count, so it moves, and a
        #: modulo test against a moving P fires only when a slot index happens
        #: to divide the P in force at that instant. Measured before this was
        #: fixed: at N = 8, P ranged over [50, 1200] and the modulo form fired
        #: on 0 of 6 400 slots -- the cadence was not the derived cadence, and
        #: only the counter check found it.
        self._gper_since_reserve = 0
        #: ue_id -> remaining_pdb_ms, from `_ul_gbr_and_pdb`'s own second
        #: return value. Captured rather than recomputed so the gate reads the
        #: SAME number the ranking was built from.
        self._gpd_remaining: dict[int, float] = {}
        #: ue_id -> tightest pending PDB in ms, captured where `buffers` is in
        #: scope. E2 only; empty otherwise.
        self._proto_pdb_ms: dict[int, int] = {}
        #: ue_id -> slot of that UE's last UPLINK grant. THIS ARM'S OWN, not
        #: `TwoTier._last_ul_grant_slot`, which is only written when the
        #: anti-hysteresis damper is on -- see the module docstring for the
        #: no-op that borrowing it produced.
        self._proto_last_ul_grant_slot: dict[int, int] = {}

    # ------------------------------------------------------------------ E2

    def allocate(self, slot, buffers, channel):
        """The port's own allocation, plus E2's own grant-recency record.

        Additive and after the fact: `super()` decides everything, and this
        only reads the allocations it returned. Guarded by the flag so the
        faithful path keeps doing no extra work.
        """
        if self.periodic_reserve:
            # The cap is a property of the SLOT, and `_finalize_ul_coef` does
            # not receive one -- captured here so P's own derivation reads the
            # real value rather than a default standing in for it.
            self._gper_cap = int(slot.max_sched_ues)
        out = super().allocate(slot, buffers, channel)
        if (self.denial_ordered_periodic or self.kpi_ordered_periodic
                or self.slack_ordered_periodic):
            for a in out:
                if a.direction == "UL":
                    self._proto_last_ul_grant_slot[a.ue_id] = slot.slot_index
        if self.periodic_reserve:
            reserve = self._gper_is_reserve
            for a in out:
                if a.direction != "UL":
                    continue
                if reserve:
                    self.counters["gper_reserve_grants"] += 1
                    self.counters["gper_reserve_prb"] += int(a.prbs)
                    if a.ue_id == self._gper_leader_ue:
                        self.counters["gper_leader_served_on_reserve"] += 1
                else:
                    self.counters["gper_normal_grants"] += 1
                    self.counters["gper_normal_prb"] += int(a.prbs)
        if self.stale_bsr_reserve:
            for a in out:
                if a.direction == "UL":
                    self._proto_last_ul_grant_slot[a.ue_id] = slot.slot_index
        return out

    def _ul_gbr_and_pdb(self, ue_id: int, buffers: Any,
                        slot_index: int) -> tuple:
        """The port's own computation, plus E2's staleness input.

        `super()` first and its result returned unchanged -- this override adds
        a pure READ and nothing else. It exists because `_finalize_ul_coef`,
        where the reserve is gated, does not receive `buffers`, and
        `_ul_best_pending_pdb_ms` needs it. Guarded by the flag so the faithful
        path does not even take the read.
        """
        out = super()._ul_gbr_and_pdb(ue_id, buffers, slot_index)
        if (self.deadline_gated_periodic or self.kpi_ordered_periodic
                or self.slack_ordered_periodic):
            self._gpd_remaining[ue_id] = float(out[1])
        if self.stale_bsr_reserve:
            self._proto_pdb_ms[ue_id] = self._ul_best_pending_pdb_ms(
                ue_id, buffers)
        return out

    def _e2_report_is_stale(self, ue_id: int) -> tuple[bool, bool]:
        """(stale, never_granted) for one UE. See the module docstring."""
        last = self._proto_last_ul_grant_slot.get(ue_id)
        if last is None:
            return True, True           # no grant ever -> no report at all
        pdb_ms = self._proto_pdb_ms.get(ue_id)
        if pdb_ms is None:
            # Not observed this slot: treat as stale rather than fresh. An
            # unknown must not silently earn a UE the "current" disposition,
            # which is the direction that would quietly remove protection.
            return True, False
        age_ms = (self._cur_slot - last) * self.slot_duration_s * 1000.0
        return age_ms > float(pdb_ms), False

    # ------------------------------------------------------------------ E1

    def _finalize_ul_coef(self, candidates: list[_Candidate]) -> None:
        """`TwoTier`'s composite formation, then E1's reserve gate.

        `super()` FIRST and unconditionally: `coef` is finalised by the parent
        exactly as the port computes it, and nothing below touches `coef` or
        any input to it. That ordering is what makes E1 a sizing change rather
        than a ranking change.
        """
        super()._finalize_ul_coef(candidates)
        if self.stale_bsr_reserve:
            self._apply_e2(candidates)
        if self.depth_bounded_reserve:
            self._apply_gdepth(candidates)
        if self.periodic_reserve:
            self._apply_gperiodic(candidates)
        if not self.gate_follower_reserve:
            return

        self.counters["e1_slots_evaluated"] += 1

        # The population FIX-2 reserves for -- the same predicate its own
        # reverse scan uses, so the count cannot disagree with the mechanism
        # it is gating.
        qualifying = [c for c in candidates
                      if not c.sched_inactive and c.has_gbr
                      and c.gbr_bytes_slot > 0]
        need = len(qualifying)
        if need > self.counters["e1_max_followers_need"]:
            self.counters["e1_max_followers_need"] = need
        if need == 0:
            return

        # THE FEASIBILITY TEST THE PORT DOES NOT HAVE. `prb_count` is the
        # slot's whole band; `_grid` is stored by `TwoTier.configure`, so this
        # reads the same number the grant loop's `slot.prb_count` reads rather
        # than a second copy of it.
        if self._grid.prb_count > self.min_rb * need:
            return                      # the reserve fits: stay faithful

        # It does not fit. Suppress it, exactly and only it -- see the module
        # docstring for why folding into `ul_total_target_bytes` leaves B_eff
        # unchanged.
        self.counters["e1_gate_fired"] += 1
        for c in qualifying:
            self._suppress_reserve(c)
            self.counters["e1_candidates_suppressed"] += 1

    def _apply_e2(self, candidates: list[_Candidate]) -> None:
        """Keep the reserve only for followers whose buffer report is stale."""
        self.counters["e2_slots_evaluated"] += 1
        for c in candidates:
            if c.sched_inactive or not c.has_gbr or c.gbr_bytes_slot <= 0:
                continue
            stale, never = self._e2_report_is_stale(c.ue_id)
            if stale:
                self.counters["e2_stale_kept"] += 1
                if never:
                    self.counters["e2_never_granted_kept"] += 1
                continue
            # Report is current: this follower does not need band reserved to
            # make it report. Remove its reserve contribution, B_eff-neutrally.
            self._suppress_reserve(c)
            self.counters["e2_current_suppressed"] += 1

    # -------------------------------------------------------------- G-depth

    def _apply_gdepth(self, candidates: list[_Candidate]) -> None:
        """Keep the reserve for at most K qualifying followers, chosen by need.

        Not a gate: below K nothing is suppressed and the arm is the port, and
        above it exactly `need - K` reserves are dropped. That is what makes it
        continuous where E1 is binary.
        """
        self.counters["gdepth_slots_evaluated"] += 1
        qual = [c for c in candidates
                if not c.sched_inactive and c.has_gbr and c.gbr_bytes_slot > 0]
        need = len(qual)
        if need > self.counters["gdepth_max_need"]:
            self.counters["gdepth_max_need"] = need

        cap = self.reserve_depth
        if cap is None:
            # The registered variant, derived from the band rather than picked:
            # the count at which the reserve stops fitting, less one.
            cap = self._grid.prb_count // self.min_rb - 1
        cap = max(0, cap)
        self.counters["gdepth_depth_cap"] = cap
        if need <= cap:
            return                      # the bound does not bind: stay faithful

        self.counters["gdepth_slots_bound_binding"] += 1
        # BY NEED, not by rank position -- the neediest keep their reserve, and
        # `ue_id` breaks ties so the choice is deterministic rather than
        # dependent on the incoming list order.
        order = sorted(qual, key=lambda c: (-c.gbr_bytes_slot, c.ue_id))
        for c in order[cap:]:
            self._suppress_reserve(c)
            self.counters["gdepth_candidates_suppressed"] += 1

    # ----------------------------------------------------------- G-periodic

    def _ul_rank_key(self, candidate: _Candidate) -> tuple:
        """The port's key, with Tier 2 reversed on a reserve slot.

        Tiers 1 and 1.5 are passed through untouched -- see the module
        docstring for why demoting a control-plane candidate or a fired floor
        is out of this gate's scope.
        """
        key = super()._ul_rank_key(candidate)
        if not (self.periodic_reserve and self._gper_is_reserve):
            return key
        if self.slack_ordered_periodic:
            # G-slack. See the module docstring: the FIRST element separates
            # "can still be saved" from "already late", which is the whole
            # correction to G-kpi.
            return (key[0], key[1], key[2],
                    self._gslack_key(candidate.ue_id), key[4])
        if self.kpi_ordered_periodic:
            # G-kpi. Nearest a KPI violation first, longest-denied among those
            # already violating -- see the module docstring for why the
            # tie-break is not optional here.
            return (key[0], key[1], key[2],
                    (self._gpd_remaining.get(candidate.ue_id, float("inf")),
                     -self._gdo_age(candidate.ue_id)),
                    key[4])
        if self.denial_ordered_periodic:
            # G-denial. REPLACE Tier 2 rather than negate it: `-age` sorts the
            # longest-denied first under the same ascending sort, and the
            # composite is not consulted at all. See the module docstring for
            # why negating `coef` does not express this.
            return (key[0], key[1], key[2],
                    -self._gdo_age(candidate.ue_id), key[4])
        # key[3] is `-coef`; negating it sorts the LOWEST composite first.
        # MEASURED, and it is NOT the longest-denied robot -- see the G-denial
        # section of the module docstring for the correlations. Ties are
        # untouched: equal values stay equal under negation, and `list.sort` is
        # stable, so a fully tied slot is ordered exactly as the port orders it.
        return (key[0], key[1], key[2], -key[3], key[4])

    def _gslack_key(self, ue_id: int) -> tuple[int, float, int]:
        """(already_late, remaining_ms, -denial_slots) for one UE."""
        rem = self._gpd_remaining.get(ue_id, float("inf"))
        return (1 if rem <= 0.0 else 0, rem, -self._gdo_age(ue_id))

    def _gdo_age(self, ue_id: int) -> int:
        """Slots since this UE's last uplink grant.

        A UE never granted gets `_cur_slot - (-1)`, the largest age available,
        so "never served" sorts first without needing a sentinel value.
        """
        return self._cur_slot - self._proto_last_ul_grant_slot.get(ue_id, -1)

    def _apply_gperiodic(self, candidates: list[_Candidate]) -> None:
        """Replace the spatial reserve with a temporal one."""
        self.counters["gper_slots_evaluated"] += 1
        qual = [c for c in candidates
                if not c.sched_inactive and c.has_gbr and c.gbr_bytes_slot > 0]

        # THE SPATIAL RESERVE GOES, on every slot -- the point of the gate is
        # that the leader takes the depth it needs when it is not a reserve
        # slot. Suppressed through the same seam every other edit uses.
        for c in qual:
            self._suppress_reserve(c)

        period = self._gper_period(candidates, len(qual))
        self.counters["gper_period_last"] = period
        lo = self.counters["gper_period_min"]
        self.counters["gper_period_min"] = period if lo < 0 else min(lo, period)
        self.counters["gper_period_max"] = max(
            self.counters["gper_period_max"], period)

        self._gper_since_reserve += 1
        self._gper_is_reserve = self._gper_since_reserve >= period
        self._gper_leader_ue = None
        if not self._gper_is_reserve:
            return
        if self.deadline_gated_periodic:
            self.counters["gpd_due_slots"] += 1
            urgent = sum(
                1 for c in candidates
                if not c.sched_inactive
                and self._gpd_remaining_pdb_ms(c.ue_id) <= self._gpd_near_ms())
            self.counters["gpd_urgent_candidates"] += urgent
            if urgent == 0:
                # Nobody is near a deadline. Do NOT consume the cadence -- the
                # slot is skipped, not spent, so the next genuinely urgent slot
                # is not delayed by a quiet one.
                self._gper_is_reserve = False
                self.counters["gpd_skipped_nobody_due"] += 1
                return
            self.counters["gpd_fired"] += 1
        self._gper_since_reserve = 0
        self.counters["gper_reserve_slots"] += 1
        # Who WOULD have led, recorded before the reordering, so
        # `gper_leader_served_on_reserve` measures whether "followers only"
        # actually holds rather than assuming the reversal achieved it.
        data = [c for c in candidates if not c.sched_inactive]
        if data:
            self._gper_leader_ue = min(
                data, key=lambda c: TwoTier._ul_rank_key(self, c)).ue_id
        if self.slack_ordered_periodic and data:
            self.counters["gslack_slots_ordered"] += 1
            first = min(data, key=lambda c: self._gslack_key(c.ue_id))
            late = sum(1 for c in data
                       if self._gpd_remaining.get(c.ue_id, float("inf")) <= 0.0)
            self.counters["gslack_late_total"] += late
            if late == len(data):
                self.counters["gslack_all_late_slots"] += 1
            if self._gslack_key(first.ue_id)[0] == 0:
                self.counters["gslack_first_has_slack"] += 1
            kpi_first = min(data, key=lambda c: (
                self._gpd_remaining.get(c.ue_id, float("inf")),
                -self._gdo_age(c.ue_id)))
            if first.ue_id == kpi_first.ue_id:
                self.counters["gslack_agrees_with_kpi"] += 1
        if self.kpi_ordered_periodic and data:
            self.counters["gkpi_slots_ordered"] += 1
            rem = {c.ue_id: self._gpd_remaining.get(c.ue_id, float("inf"))
                   for c in data}
            first = min(data, key=lambda c: (rem[c.ue_id],
                                             -self._gdo_age(c.ue_id)))
            tied = sum(1 for c in data if rem[c.ue_id] <= 0.0)
            self.counters["gkpi_tied_at_zero_total"] += tied
            if tied > self.counters["gkpi_tied_at_zero_max"]:
                self.counters["gkpi_tied_at_zero_max"] = tied
            if rem[first.ue_id] <= 0.0:
                self.counters["gkpi_first_already_violating"] += 1
            if first.ue_id == max(data,
                                  key=lambda c: self._gdo_age(c.ue_id)).ue_id:
                self.counters["gkpi_agrees_with_denial"] += 1
            if first.ue_id == min(data, key=lambda c: c.coef).ue_id:
                self.counters["gkpi_agrees_with_coef"] += 1
        if self.denial_ordered_periodic and data:
            # Does the swap actually change who is served first? If the two
            # rules agreed everywhere, this arm would be G-periodic under a
            # different name -- the E2 failure mode, and the counter is here
            # so it cannot pass unnoticed.
            self.counters["gdo_slots_ordered"] += 1
            by_age = max(data, key=lambda c: self._gdo_age(c.ue_id))
            by_coef = min(data, key=lambda c: c.coef)
            if by_age.ue_id == by_coef.ue_id:
                self.counters["gdo_agrees_with_coef"] += 1
            if by_age.ue_id not in self._proto_last_ul_grant_slot:
                self.counters["gdo_never_granted_first"] += 1
            age = self._gdo_age(by_age.ue_id)
            if age > self.counters["gdo_max_age_slots"]:
                self.counters["gdo_max_age_slots"] = age

    def _gpd_near_ms(self) -> float:
        """The longest wait to the next uplink slot, from the TDD pattern.

        DERIVED per grid rather than stored as a constant, so a numerology or
        pattern change moves it instead of silently invalidating it.
        """
        pat = self._grid.pattern
        ul = [i for i, k in enumerate(pat) if k in ("U", "S")]
        if not ul:
            return 0.0
        gap = max((ul[(j + 1) % len(ul)] - ul[j]) % len(pat)
                  for j in range(len(ul)))
        return gap * self.slot_duration_s * 1000.0

    def _gpd_remaining_pdb_ms(self, ue_id: int) -> float:
        """This UE's tightest remaining PDB, captured in `_ul_gbr_and_pdb`."""
        return self._gpd_remaining.get(ue_id, float("inf"))

    def _gper_period(self, candidates: list[_Candidate], n_followers: int) -> int:
        """P*, derived. See the module docstring for the requirement it meets."""
        slot_ms = self.slot_duration_s * 1000.0
        pdb_ms = min(
            (float(f.pdb_ms) for c in candidates for f in c.flows
             if f.pdb_ms and f.pdb_ms > 0),
            default=float(_GPER_PDB_FALLBACK_MS))
        pdb_slots = pdb_ms / slot_ms
        cap = max(1, int(self._gper_cap))
        rounds = max(1, -(-max(1, n_followers) // cap))     # ceil
        p = int(pdb_slots / rounds * self.reserve_period_mult)
        return max(1, p)

    def _suppress_reserve(self, c: _Candidate) -> None:
        """Remove one candidate's FIX-2 reserve contribution, exactly.

        `gbr_bytes_slot` has two live readers: `gbr_below`'s reverse scan and
        `B_eff`'s `max`. Folding the value into `ul_total_target_bytes` before
        zeroing it leaves the second identical and removes the first -- see the
        module docstring's arithmetic. Shared by every edit that suppresses a
        reserve, so they cannot diverge in HOW they suppress -- only in which
        candidates they choose.
        """
        c.proto_orig_gbr_bytes_slot = c.gbr_bytes_slot
        c.ul_total_target_bytes = max(c.ul_total_target_bytes,
                                      c.gbr_bytes_slot)
        c.gbr_bytes_slot = 0
