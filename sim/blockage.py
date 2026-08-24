"""Two-state Markov blockage (docs/wp6-plan.md Decision 3): a transient
obstruction (forklift, robot arm) modelled as a per-UE {Unblocked,
Blocked} process, independent of TR 38.901 path loss (sim/pathloss.py) --
it composes as a further additive dB penalty on whatever large-scale mean
is already in effect, hand-authored or path-loss-derived.

Per-slot transition probabilities are the standard two-state
(Gilbert-Elliott-style) construction: a geometric-dwell approximation of
an exponential sojourn time, ``p_leave = 1 / mean_dwell_slots``, clamped
to 1.0 when the configured mean dwell is at or below one slot. Expressed
in slots, not milliseconds, matching every other timing knob in this
codebase (``k1_slots``/``k2_slots``/``cqi_delay_slots``/``sr_period_
slots``) -- numerology-agnostic the same way those are, and it lets
``mean_blocked_slots`` be swept across the full range from "far shorter
than a HARQ retry cycle" to "hundreds of milliseconds" (WP6's own
acceptance criterion, ``p5g-sim-plan.md`` sec 9) without the module itself
biasing toward either regime.

**No literature source for factory blockage duration exists anywhere in
this repo.** ``p5g-sim-plan.md``'s "a forklift or robot arm crossing the
path -- a 15-20 dB drop lasting hundreds of milliseconds" is this
project's own qualitative motivating description, not a measured
distribution -- external or internal. The default ``mean_blocked_slots``
below is an order-of-magnitude anchor to that description, same epistemic
tier as ``sr_period_slots``/``k1_slots``, not a transcribed value like
``sim/pathloss.py``'s TR 38.901 constants. Nothing about the mechanism
restricts it to that regime -- see ``sim/tests/test_blockage.py``'s
empirical check at both a "long" (hundreds-of-ms-equivalent) and a
"short" (shorter than a HARQ retry cycle) configuration.

Depends on nothing outside itself (no ``sim``/``scheduler`` imports),
matching ``sim/pathloss.py``'s and ``sim/harq.py``'s stated design.
"""

from __future__ import annotations


def transition_probability(mean_dwell_slots: float) -> float:
    """Per-slot probability of leaving the current state, geometric
    approximation of an exponential sojourn with mean ``mean_dwell_slots``.
    Clamped to 1.0 when ``mean_dwell_slots <= 1`` (leaves every slot) --
    the discrete process's own natural floor, not an error case."""
    if mean_dwell_slots <= 0:
        raise ValueError(f"mean_dwell_slots must be > 0 (got {mean_dwell_slots})")
    return min(1.0, 1.0 / mean_dwell_slots)


def step(blocked: bool, p_leave_blocked: float, p_leave_unblocked: float, draw: float) -> bool:
    """One Markov step. ``draw`` is a uniform[0,1) sample from the
    caller's own RNG stream -- this module doesn't own an RNG object
    itself, matching ``sim/pathloss.py``'s pure-function design; the
    caller (``sim/channel.py``) is responsible for using an independent
    stream per docs/wp6-plan.md Decision 3 / CLAUDE.md's seed-isolation
    rule."""
    p_leave = p_leave_blocked if blocked else p_leave_unblocked
    return (not blocked) if draw < p_leave else blocked
