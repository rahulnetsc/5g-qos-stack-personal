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
    "deadline_sizing",            # E3, not implemented
)


class TwoTierProto(TwoTier):
    """The faithful port plus optional, individually-flagged divergences.

    All flags off == `TwoTier`, asserted by `sim/tests/test_two_tier_proto.py`.
    """

    def __init__(self, *args: Any,
                 gate_follower_reserve: bool = False,
                 stale_bsr_reserve: bool = False,
                 depth_bounded_reserve: bool = False,
                 reserve_depth: int | None = None,
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
        })
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
        out = super().allocate(slot, buffers, channel)
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
