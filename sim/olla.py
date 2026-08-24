"""WP5 commit 6 -- OLLA (outer-loop link adaptation) bug #1: the round-count
MCS ratchet in ``get_mcs_from_bler``.

Ported bug-for-bug from ``oai-branches/two-tier/gNB_scheduler_primitives.c``
:785-822, cited verbatim in docs/wp5-plan.md sec2. Pure functions/dataclasses
only -- no simulator or scheduler imports, same discipline as sim/power.py
(WP1), which this module follows as its precedent.

DORMANT: not wired into ``sim/driver.py`` or any scheduler. See
``README.md`` sec8 [OPEN] and ``docs/wp5-plan.md`` Decision 5/commit 6 for
why: real ``get_mcs_from_bler``'s ratcheted MCS reaches exactly one call
site (it directly becomes the grant's MCS before TBS sizing). This
simulator has no persistent per-UE MCS anywhere grant sizing reads, and the
only zero-scheduler-change route to feed one in --
wrapping ``ChannelModel.get_reported_snr_db()`` -- would also feed the
ratcheted value into every OTHER consumer of that same method (PF's
ranking, TwoTier's ``_r_avg``, Tier-1's capacity estimates), none of which
are MCS selection in real hardware. That's not a fidelity trade-off, it's a
different mechanism wearing OLLA's name, with a failure mode no test would
catch and no metric would attribute. Activation belongs in Phase 2's fresh
scheduler rewrite, where MCS selection can live in the right place.
"""

from __future__ import annotations

from dataclasses import dataclass

# Must match scheduler/link.py::_MCS_TABLE's row count exactly (verified
# directly against that table in sim/tests/test_olla.py, not re-derived
# here -- the same "check the vendored/shared source directly" discipline
# sim/bsr.py's own table tests use, rather than importing a private name
# across modules).
MCS_INDEX_COUNT = 12

# gNB_scheduler_primitives.c:785-786.
BLER_UPDATE_FRAME = 10  # frames; an NR frame is a spec-fixed 10ms
                         # regardless of numerology, so this is a 100ms
                         # window, matching the task's "100ms" framing even
                         # though the literal C constant reads 10.
BLER_FILTER = 0.9       # EWMA smoothing factor for bler_stats->bler.


@dataclass
class OllaRoundCounters:
    """Cumulative, monotonically-increasing per-(ue_id, direction) counts --
    mirrors real OAI's ``NR_mac_dir_stats_t.rounds[]``, a lifetime histogram
    of how many TBs have reached each HARQ round. Only round 0 (every NEW
    transmission attempt, regardless of eventual outcome) and round 1
    (every TB's FIRST transition into retry) are needed for ``get_mcs_
    from_bler``'s own ``bler_window`` computation -- round 1 is incremented
    exactly once per TB that ever needed a retry, NOT once per retry
    attempt (a TB that fails rounds 1, 2, and 3 still only increments this
    once, at the round-0-to-round-1 transition)."""

    rounds0: int = 0
    rounds1: int = 0

    def record_new_tx(self) -> None:
        """A new (round-0) transmission attempt happened, regardless of
        its eventual outcome."""
        self.rounds0 += 1

    def record_first_retry(self) -> None:
        """A TB just transitioned from round 0 to round 1 for the first
        time. Call this ONCE per TB, at the moment its first attempt
        fails and a retry is scheduled -- never again for that same TB's
        later rounds."""
        self.rounds1 += 1


@dataclass
class OllaOptions:
    """Mirrors ``NR_bler_options_t`` (gNB_scheduler_primitives.c) -- config
    thresholds, one instance per direction (DL/UL), not per UE."""

    lower: float
    upper: float
    min_mcs: int = 0
    max_mcs: int = MCS_INDEX_COUNT - 1


@dataclass
class OllaState:
    """Per-(ue_id, direction) persistent OLLA state -- mirrors
    ``NR_bler_stats_t``. Seeded via ``init_olla_state``, not this
    constructor directly, so a fresh UE always starts exactly the way real
    OAI's ``init_bler_stats`` does."""

    mcs: int
    bler: float
    last_frame: int = 0
    rounds0_snapshot: int = 0
    rounds1_snapshot: int = 0


def init_olla_state(options: OllaOptions) -> OllaState:
    """Mirrors ``init_bler_stats`` (gNB_scheduler_primitives.c ~2944-2948):
    ``mcs`` starts at ``min_mcs`` -- every UE begins at the floor and can
    only climb back up one step per ``BLER_UPDATE_FRAME`` window, never
    starting anywhere higher. ``bler`` starts at the midpoint of the
    lower/upper thresholds."""
    return OllaState(mcs=options.min_mcs, bler=(options.lower + options.upper) / 2.0)


def update_mcs_from_bler(
    options: OllaOptions,
    counters: OllaRoundCounters,
    state: OllaState,
    max_mcs: int,
    frame: int,
) -> int:
    """Bug-for-bug port of ``get_mcs_from_bler``
    (``gNB_scheduler_primitives.c:787-822``, cited verbatim in
    ``docs/wp5-plan.md`` sec2). Mutates ``state`` in place and returns the
    (possibly unchanged) current MCS index, matching the C function's own
    signature and side effects.

    Bug-for-bug, not simplified in either direction:
    - The ``-1`` branch fires on EITHER ``bler > upper`` OR
      ``num_dl_sched <= 3`` (an ``elif`` in the source -- the two
      conditions are mutually exclusive with the ``+1`` branch within one
      call, never both applied).
    - The ``+1`` branch requires BOTH ``bler < lower`` AND
      ``num_dl_sched > 3``.
    - Consequence: a UE below ~30 tx/sec in the 100ms window
      (``num_dl_sched <= 3``) ratchets monotonically toward ``min_mcs``
      regardless of channel quality, and an idle UE (``num_dl_sched=0``)
      does so unconditionally, every window it stays idle.
    - ``old_mcs = min(state.mcs, max_mcs)`` -- the climb-back after a
      forced drop is strictly ``+1`` per window, never a jump, since the
      ``+1`` branch computes from ``old_mcs``, not from ``min_mcs``.
    - When ``num_dl_sched == 0``, ``bler_window`` is NOT zero -- it falls
      back to the stale ``state.bler`` itself (C: ``num_dl_sched > 0 ?
      ... : bler_stats->bler``), so the EWMA update is a no-op for an
      idle UE; only the ``-1``-on-``num_dl_sched<=3`` branch moves ``mcs``
      in that case, independent of whatever ``bler`` says.
    """
    diff = frame - state.last_frame
    if diff < 0:
        diff += 1024  # frame_t wraps at 1024 (line 794-795)

    max_mcs = min(max_mcs, options.max_mcs)
    old_mcs = min(state.mcs, max_mcs)
    if diff < BLER_UPDATE_FRAME:
        return old_mcs  # no update yet -- window hasn't elapsed

    num_dl_sched = counters.rounds0 - state.rounds0_snapshot
    num_dl_retx = counters.rounds1 - state.rounds1_snapshot
    bler_window = (num_dl_retx / num_dl_sched) if num_dl_sched > 0 else state.bler
    state.bler = BLER_FILTER * state.bler + (1 - BLER_FILTER) * bler_window

    new_mcs = old_mcs
    if state.bler < options.lower and old_mcs < max_mcs and num_dl_sched > 3:
        new_mcs += 1
    elif state.bler > options.upper or num_dl_sched <= 3:
        new_mcs -= 1
    # else: within threshold boundaries, no change.

    new_mcs = max(new_mcs, options.min_mcs)
    state.last_frame = frame
    state.mcs = new_mcs
    state.rounds0_snapshot = counters.rounds0
    state.rounds1_snapshot = counters.rounds1
    return new_mcs
