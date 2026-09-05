"""The candidate stream: who was ranked, in what order, and on which term.

WHAT THIS IS FOR. `sim/trace.py` (the grant stream) answered the camera
question -- *is the UE granted rarely, or granted and short-changed?* -- and
its answer was "granted rarely". THIS module answers the question that one
raised and could not reach: **why does that UE lose the sort?**

Its map is registered in `docs/g5-ranking-map.md` and is CLOSED. Outcomes
L1-L7 (a term that decides) and U1-U4 (the ways the question is unreachable)
were written down before this file existed, so a result that fits none of
them is reported as a RESIDUAL rather than becoming an eighth candidate
after the fact.

WHERE IT LIVES, AND WHY HERE RATHER THAN IN `sim/`. `scheduler/` imports
nothing from `sim/` -- verified, not assumed -- and this hook has to sit
*inside* the ranking, at the sort, in three different arms. So the record
and the sink protocol are defined here, in `scheduler/`, and `sim/` depends
on `scheduler/` as it already does. The grant hook could sidestep this
boundary by living at the driver's grant site; a ranking hook cannot.

**THE FAILURE MODE THIS FILE IS BUILT AGAINST, restated because it is
different from the grant hook's.** The grant hook is a direct call at one
fixed call site: there is no name to bind wrongly. This hook reads terms off
each arm's own candidate object BY NAME, which is exactly the shape of the
defect that motivated the facility -- a probe bound to `self._ue` where the
attribute was `self._state`, reading zero for its control as well as its
treatment and so confirming a hypothesis on no evidence. Hence:

  * `field()` RAISES on a name that does not resolve. There is no
    `getattr(obj, name, default)` anywhere in this module or its call sites,
    because a default is precisely how that defect stays silent.
  * `RankCollector.finish()` RAISES when it collected nothing.
  * A collector will not silently truncate: it raises on overflow, since a
    truncated stream and a short one are indistinguishable afterwards.

**ATTACHING A SINK MUST NOT CHANGE A RUN.** Every value recorded here is one
the arm already computed for its own sort; nothing is derived for the trace.
That is the bit-identity acceptance condition, and it is a property of how
these records are built rather than a hope about them.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Optional


class UnboundRankTerm(RuntimeError):
    """A declared term/factor name does not exist on the candidate object."""


class NoCandidatesObserved(RuntimeError):
    """A collector finished having seen nothing -- i.e. it did not bind."""


class RankStreamOverflow(RuntimeError):
    """A collector hit its retention cap. Raised, never truncated."""


def field(obj: Any, name: str) -> Any:
    """Read `obj.name`, raising if it is absent.

    THE ONE RULE OF THIS MODULE. `getattr` with a default turns a mis-bound
    name into a plausible zero; this project has a recorded instance of
    exactly that, and six more of the same family where a probe observed
    nothing and the nothing was read as a result.
    """
    try:
        return getattr(obj, name)
    except AttributeError as exc:
        raise UnboundRankTerm(
            f"{type(obj).__name__} has no attribute {name!r}. This is a hook "
            f"bound to a name that does not exist -- the defect this module "
            f"exists against. Fix the name; do not default it."
        ) from exc


@dataclasses.dataclass(frozen=True)
class RankEntry:
    """One candidate, at its final position in the sorted order."""

    ue_id: int
    #: The arm's OWN ranking key, exactly as the sort saw it, in
    #: ascending-comparison order. The deciding term between two adjacent
    #: entries is the first index at which their keys differ -- which is what
    #: makes "loses at `floor_fire`" a measurement rather than a reading.
    key: tuple
    #: The qfis of the flows this candidate carries. The arms rank per UE, so
    #: this says whether the video flow was even part of what was ranked.
    qfis: tuple[int, ...]
    #: Diagnostic quantities that are NOT tiers of the key but are factors of
    #: it -- PF's `bits_per_rb` and `_r_avg`, which multiply into one metric
    #: and so cannot be separated by the first-difference rule above. Map
    #: rows L5/L6/L7 are exactly this distinction.
    factors: tuple[tuple[str, float], ...] = ()


@dataclasses.dataclass(frozen=True)
class RankSnapshot:
    """One slot's candidate set for one direction, in final sorted order."""

    slot_index: int
    direction: str
    arm: str
    #: Names for the elements of every entry's `key`, in the same order.
    #: Declared by the arm, so an analysis never has to guess which tier is
    #: which -- and so a key whose width changes is caught rather than
    #: silently re-indexed.
    term_names: tuple[str, ...]
    entries: tuple[RankEntry, ...]

    def __post_init__(self) -> None:
        for e in self.entries:
            if len(e.key) != len(self.term_names):
                raise UnboundRankTerm(
                    f"{self.arm} {self.direction}: key width {len(e.key)} "
                    f"does not match {len(self.term_names)} declared term "
                    f"names {self.term_names}. An analysis indexing this key "
                    f"by position would read the wrong tier.")


RankSink = Callable[[RankSnapshot], None]


def decisive_term(a: RankEntry, b: RankEntry) -> Optional[int]:
    """Index of the first key element on which `a` and `b` differ.

    `None` means the two are TIED on every term, so their relative order came
    from the sort's stability -- i.e. from candidate declaration order, which
    has no physical referent. That is map row U1, and it is an ANSWER: the
    same declaration-order artefact that stopped G12's ordering being
    promoted. It must not be reported as a failed trace.
    """
    for i, (x, y) in enumerate(zip(a.key, b.key)):
        if x != y:
            return i
    return None


class RankCollector:
    """Retains the full stream, with a cap that RAISES rather than truncates.

    For focused runs only. `LossPointTally` is the streaming reducer for
    anything long enough that retention is a memory question -- this project
    has a 25 GB retention leak in its record, twice, so retention here is
    bounded and loud rather than convenient.
    """

    def __init__(self, *, max_snapshots: int = 200_000,
                 allow_empty: bool = False) -> None:
        self.snapshots: list[RankSnapshot] = []
        self._cap = max_snapshots
        self._allow_empty = allow_empty

    def __call__(self, snap: RankSnapshot) -> None:
        if len(self.snapshots) >= self._cap:
            raise RankStreamOverflow(
                f"retention cap {self._cap} reached. Raising rather than "
                f"truncating: a truncated stream is indistinguishable from a "
                f"short one once the run is over. Use LossPointTally, or "
                f"raise the cap deliberately.")
        self.snapshots.append(snap)

    def finish(self) -> list[RankSnapshot]:
        if not self.snapshots and not self._allow_empty:
            raise NoCandidatesObserved(
                "the rank sink was attached and collected NOTHING -- that is a "
                "hook that did not bind, not a run with no candidates. Pass "
                "allow_empty=True only if an empty stream is the expected "
                "result and you are claiming it.")
        return list(self.snapshots)


class LossPointTally:
    """Streaming reducer: for each adjacent pair in the sorted order, which
    term decided it, and who lost.

    Retains O(UEs^2 x terms) rather than O(slots), so it is safe at any
    horizon. This is what reads the map: `losses[(loser, winner)][term]`
    counts how often `loser` was placed behind `winner` BY that term, and
    `ties` counts the U1 case where nothing separated them.
    """

    def __init__(self, direction: str = "UL") -> None:
        self.direction = direction
        self.arm: Optional[str] = None
        self.term_names: tuple[str, ...] = ()
        self.slots_seen = 0
        #: (loser_ue, winner_ue) -> term_index -> count
        self.losses: dict[tuple[int, int], dict[int, int]] = {}
        #: (loser_ue, winner_ue) -> count of fully-tied adjacencies  (U1)
        self.ties: dict[tuple[int, int], int] = {}
        #: ue -> list of ranks it held  (kept as counts, not a list)
        self.rank_hist: dict[int, dict[int, int]] = {}
        #: ue -> number of slots it appeared as a candidate at all  (U2)
        self.present: dict[int, int] = {}
        #: ue -> factor name -> [n, sum, min, max, n_at_or_below_clamp]
        self.factor_stats: dict[int, dict[str, list[float]]] = {}
        self._seen = False

    def __call__(self, snap: RankSnapshot) -> None:
        if snap.direction != self.direction:
            return
        self._seen = True
        self.arm = snap.arm
        self.term_names = snap.term_names
        self.slots_seen += 1
        for rank, e in enumerate(snap.entries):
            self.present[e.ue_id] = self.present.get(e.ue_id, 0) + 1
            h = self.rank_hist.setdefault(e.ue_id, {})
            h[rank] = h.get(rank, 0) + 1
            if e.factors:
                fs = self.factor_stats.setdefault(e.ue_id, {})
                for name, val in e.factors:
                    s = fs.get(name)
                    if s is None:
                        fs[name] = [1.0, val, val, val]
                    else:
                        s[0] += 1.0
                        s[1] += val
                        s[2] = min(s[2], val)
                        s[3] = max(s[3], val)
        for i in range(len(snap.entries) - 1):
            win, lose = snap.entries[i], snap.entries[i + 1]
            pair = (lose.ue_id, win.ue_id)
            t = decisive_term(win, lose)
            if t is None:
                self.ties[pair] = self.ties.get(pair, 0) + 1
            else:
                d = self.losses.setdefault(pair, {})
                d[t] = d.get(t, 0) + 1

    def finish(self, *, allow_empty: bool = False) -> "LossPointTally":
        if not self._seen and not allow_empty:
            raise NoCandidatesObserved(
                f"LossPointTally saw no {self.direction} snapshot. The hook "
                f"did not bind, or this direction never ranked anything.")
        return self

    def term_totals(self) -> dict[str, int]:
        """How often each term was the decisive one, across every adjacency."""
        out = {n: 0 for n in self.term_names}
        for d in self.losses.values():
            for i, c in d.items():
                out[self.term_names[i]] += c
        out["TIED (declaration order)"] = sum(self.ties.values())
        return out

    def losses_for(self, ue_id: int) -> dict[str, int]:
        """How often `ue_id` was placed behind the UE above it, by term."""
        out = {n: 0 for n in self.term_names}
        out["TIED (declaration order)"] = 0
        for (lose, _win), d in self.losses.items():
            if lose != ue_id:
                continue
            for i, c in d.items():
                out[self.term_names[i]] += c
        for (lose, _win), c in self.ties.items():
            if lose == ue_id:
                out["TIED (declaration order)"] += c
        return out

    def mean_rank(self) -> dict[int, float]:
        out = {}
        for ue, h in self.rank_hist.items():
            n = sum(h.values())
            out[ue] = sum(r * c for r, c in h.items()) / n if n else float("nan")
        return out
