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
E2 -- TARGET THE RESERVE AT STALE BUFFER REPORTS (not built yet)
--------------------------------------------------------------------------

Registered, not implemented. The reserve exists to keep buffer reports flowing;
reserving band for a follower whose report is already current spends PRB on
information the gNB holds. The staleness threshold must be DERIVED -- from the
BSR periodicity or from the tightest PDB among the UE's backlogged flows -- and
which one is used has to be stated, not chosen silently.

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
    "stale_bsr_reserve",          # E2, not implemented
    "deadline_sizing",            # E3, not implemented
)


class TwoTierProto(TwoTier):
    """The faithful port plus optional, individually-flagged divergences.

    All flags off == `TwoTier`, asserted by `sim/tests/test_two_tier_proto.py`.
    """

    def __init__(self, *args: Any,
                 gate_follower_reserve: bool = False,
                 stale_bsr_reserve: bool = False,
                 deadline_sizing: bool = False,
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.gate_follower_reserve = bool(gate_follower_reserve)
        self.stale_bsr_reserve = bool(stale_bsr_reserve)
        self.deadline_sizing = bool(deadline_sizing)
        for name in ("stale_bsr_reserve", "deadline_sizing"):
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
        })

    # ------------------------------------------------------------------ E1

    def _finalize_ul_coef(self, candidates: list[_Candidate]) -> None:
        """`TwoTier`'s composite formation, then E1's reserve gate.

        `super()` FIRST and unconditionally: `coef` is finalised by the parent
        exactly as the port computes it, and nothing below touches `coef` or
        any input to it. That ordering is what makes E1 a sizing change rather
        than a ranking change.
        """
        super()._finalize_ul_coef(candidates)
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

    def _suppress_reserve(self, c: _Candidate) -> None:
        """Remove one candidate's FIX-2 reserve contribution, exactly.

        `gbr_bytes_slot` has two live readers: `gbr_below`'s reverse scan and
        `B_eff`'s `max`. Folding the value into `ul_total_target_bytes` before
        zeroing it leaves the second identical and removes the first -- see the
        module docstring's arithmetic. A method rather than inline so E2, when
        it lands, cannot diverge from E1 in how it suppresses.
        """
        c.proto_orig_gbr_bytes_slot = c.gbr_bytes_slot
        c.ul_total_target_bytes = max(c.ul_total_target_bytes,
                                      c.gbr_bytes_slot)
        c.gbr_bytes_slot = 0
