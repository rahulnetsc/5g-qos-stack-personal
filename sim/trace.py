"""The grant stream: what was granted, to whom, and what became of it.

WHAT THIS IS FOR, AND WHY IT IS THIS NARROW. `config/metric_panel.yml`'s
own note states the limitation this exists against: the panel and
`record_timeseries` record OUTCOMES PER FLOW and never DECISIONS, so no
number of metrics can answer a "why" question. This is the first
decision-site hook, and it is scoped to exactly one registered question --
the camera's UL loss (`docs/phase2-results.md`), whose three candidate
mechanisms were written down with their discriminating signatures BEFORE any
trace existed.

**IT IS NARROWER THAN THE FACILITY THAT WAS PROPOSED, ON PURPOSE.** The
proposal was a `decision_sink` on the scheduler, called after the ranking
sort, carrying the candidate list. Re-reading the registered map against the
grant site showed that is not what this question needs:

    candidate 1  "UE granted; camera's share of each TB small while
                  siblings take the rest"        -> per-grant split
    candidate 2  "the UE itself granted rarely;
                  its share fine when it is"     -> grant frequency
    candidate 3  "grants issued, bytes not delivered;
                  bytes_harq_lost non-zero"      -> grant outcome

**All three are readable from the grant stream alone.** Candidate 2's
registered signature is about grant RARITY, not about candidate-set
membership -- the candidate set would say WHY a UE was granted rarely, which
is a further question the map does not ask. So the hook lives in
`sim/driver.py` at the grant site, and `scheduler/` is not touched at all --
narrower than the proposed hook, and it sidesteps the `scheduler/` cannot
import `sim/` boundary rather than negotiating it.

**AND IT CANNOT FAIL THE WAY THE PROBES FAILED.** The defect this facility
exists to avoid is a hook bound to `self._ue` where the attribute is
`self._state`, which read zero for the control as well as the treatment and
would have confirmed a hypothesis on no evidence. That failure mode is
*attribute binding by name*. This hook is a direct call at a fixed call
site, so there is no name to get wrong -- and `GrantCollector` raises rather
than reporting zero if it never saw a grant.

Not extended to G5, G8 or G10 until the camera question is answered: the
facility's shape should be settled by a real customer.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional


@dataclasses.dataclass(frozen=True)
class GrantTrace:
    """One grant, at the moment its outcome is known.

    Frozen, and built from values the driver already holds -- nothing here is
    computed for the trace, so attaching a sink cannot change what a run
    does. That is the bit-identity acceptance condition, and it is a
    property of this record's construction rather than a hope about it.
    """

    slot_index: int
    ue_id: int
    direction: str                 # "DL" | "UL"
    prbs: int
    bytes_capacity: int
    cce_cost: int
    #: 0 for a first transmission; >=1 for a retransmission of the same TB.
    #: RETRANSMISSIONS CARRY PRBs (`driver.py`'s `retx_prbs_this_slot`), and
    #: those PRBs are carved out before the scheduler sees the slot -- which
    #: is the whole of candidate 3, so they are traced, not just counted.
    retx_count: int
    #: Did this attempt decode?
    success: bool
    #: UL only: the UE's own LCP split of the granted TB, as
    #: ((qfi, bytes), ...). THIS IS CANDIDATE 1'S CURRENCY -- the camera's
    #: share of each TB against its siblings'. Empty for DL, where a grant
    #: belongs to exactly one flow (`qfi` below carries it).
    split: tuple[tuple[int, int], ...] = ()
    #: DL only: the single flow the grant belongs to. -1 for a UE-level UL
    #: grant, whose composition is in `split`.
    qfi: int = -1


GrantSink = Callable[[GrantTrace], None]


class NoGrantsObserved(RuntimeError):
    """Raised when a collector finishes having seen nothing."""


class GrantCollector:
    """Accumulates a run's grant stream, and REFUSES TO REPORT ZERO.

    THE ONE THAT MATTERS. A probe that silently observes nothing is
    indistinguishable from a mechanism that never fired -- this project has
    six recorded instances of that shape, and the one this hook is a reaction
    to would have confirmed a cold-start hypothesis on a hook that read zero
    for its control too. So `finish()` RAISES if nothing was collected. A
    caller that legitimately expects an empty stream must say so with
    `allow_empty=True`, which is a claim rather than a default.
    """

    def __init__(self, *, allow_empty: bool = False) -> None:
        self.grants: list[GrantTrace] = []
        self._allow_empty = allow_empty
        self._finished = False

    def __call__(self, g: GrantTrace) -> None:
        self.grants.append(g)

    def finish(self) -> list[GrantTrace]:
        self._finished = True
        if not self.grants and not self._allow_empty:
            raise NoGrantsObserved(
                "the grant sink was attached and collected NOTHING. That is a "
                "hook that did not bind, not a run with no grants -- and a "
                "trace reporting zero is indistinguishable from a mechanism "
                "that never fired. Pass allow_empty=True only if an empty "
                "stream is the expected result and you are claiming it.")
        return list(self.grants)


def attach(sink: Optional[GrantSink]) -> Optional[GrantSink]:
    """Identity, kept as the single documented place the driver's guard is
    described: `driver.run` calls the sink only behind `is not None`, so a
    run without one pays one pointer comparison per grant."""
    return sink
