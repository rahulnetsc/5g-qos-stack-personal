"""UE uplink Tx power headroom model.

Mirrors OAI's compute_ph_factor() and nr_ue_max_mcs_min_rb()
(gNB_scheduler_ulsch.c). Pure functions only -- no simulator or scheduler
imports.

Sim-only / inert on hardware: the deployed gNB has never received a PHR MAC
CE (ph0 = 0 across every capture), so nothing here is exercised on the
testbed today. Flag any WP1-dependent result as sim-only until PHR
reporting is fixed on the real stack (README.md §4, WP1).

Not wired into any scheduler or sim/driver.py -- Phase 1 makes no scheduler
logic changes (README.md §4). Dormant, unit-tested only.
"""

from __future__ import annotations

import math
from typing import Callable


def _round_half_away_from_zero(x: float) -> int:
    """Mirrors C's roundf(), which rounds half away from zero. Python's
    builtin round() rounds half to even (round(2.5) == 2, round(-2.5) ==
    -2), which disagrees with roundf() at exact .5 boundaries
    (roundf(2.5) == 3, roundf(-2.5) == -3). compute_ph_factor casts
    roundf's result straight to int, so this sim mirrors roundf rather
    than using Python's round()."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def ph_factor(
    mu: int,
    tbs_bits: int,
    rb: int,
    n_layers: int,
    n_symbols: int,
    n_dmrs: int,
    delta_mcs_enabled: bool,
    include_bw: bool = True,
) -> int:
    """Mirrors compute_ph_factor() (gNB_scheduler_ulsch.c ~L208), 38.213
    7.1.1. delta_tf is 0 when delta_mcs isn't configured or the PUSCH spans
    more than one layer (the C source's `deltaMCS != NULL && n_layers == 1`
    guard, inverted).

    include_bw mirrors the C function's own flag rather than being
    collapsed away: of its six call sites, the four that size a grant
    (L592 and the three inside nr_ue_max_mcs_min_rb, L1805/1822/1842) pass
    true; the two phr_txpower_calc telemetry sites (L2534, L2888) pass
    false. Default True matches shrink_to_power_budget's usage below.

    rb <= 0 raises ValueError (n_re and rb << mu would both degenerate to
    log10(0)). tbs_bits <= 0 raises ValueError whenever delta_tf would
    actually be computed (BPRE == 0 -> log10(0)). The C source computes
    log10(0.0) as -inf and then casts that -inf to int, which is undefined
    behavior in C (platform/compiler-dependent, not a deterministic
    hardware behavior to reproduce) -- so this is a deliberate raise, not
    an attempt to mirror that cast.
    """
    if rb <= 0:
        raise ValueError(f"ph_factor: rb must be > 0 (got {rb})")
    delta_tf = 0.0
    if delta_mcs_enabled and n_layers == 1:
        if tbs_bits <= 0:
            raise ValueError(
                f"ph_factor: tbs_bits must be > 0 to compute delta_tf (got {tbs_bits})"
            )
        n_re = (12 * n_symbols - n_dmrs) * rb
        bpre = tbs_bits / n_re
        beta = 1.0
        delta_tf = 10 * math.log10((2 ** (bpre * 1.25) - 1) * beta)
    bw_factor = 10 * math.log10(rb << mu) if include_bw else 0.0
    return _round_half_away_from_zero(delta_tf + bw_factor)


def shrink_to_power_budget(
    mu: int,
    ph_limit: int,
    rb: int,
    min_rb: int,
    mcs: int,
    n_layers: int,
    n_symbols: int,
    n_dmrs: int,
    delta_mcs_enabled: bool,
    tbs_bits_fn: Callable[[int, int], int],
) -> tuple[int, int, bool]:
    """Mirrors nr_ue_max_mcs_min_rb()'s two SEQUENTIAL loops (gNB_scheduler_
    ulsch.c ~L1780), in order: shrink RBs first, down to min_rb; only then
    drop MCS, down to 0. This is not a joint optimum -- reproducing the
    order matters because it's what the deployed scheduler does (a joint or
    MCS-first approach could satisfy the same budget while shrinking rb
    less).

    tbs_bits_fn(rb, mcs) stands in for the C code's nr_compute_tbs() call,
    which needs a full Qm/code-rate MCS table this sim doesn't have; the
    caller supplies whatever TBS model applies.

    If still over budget after both loops, the real function only logs and
    lets the grant proceed over-budget -- there is no refusal path here
    either. Returns (rb, mcs, over_budget) so callers can count these.

    Mirrors nr_ue_max_mcs_min_rb's two AssertFatal preconditions
    (rb >= min_rb, 0 <= mcs <= 28) as ValueError raises. These are real
    precondition violations by the caller, not the "still over budget
    after both loops" outcome the no-refusal note above is about --
    without this check, rb < min_rb at entry would silently skip the RB
    loop entirely (its `rb > min_rb` condition is false from the start)
    and fall straight into MCS reduction, producing a plausible-looking
    result from an input the C treats as fatal.
    """
    if rb < min_rb:
        raise ValueError(f"shrink_to_power_budget: rb ({rb}) < min_rb ({min_rb})")
    if not (0 <= mcs <= 28):
        raise ValueError(f"shrink_to_power_budget: mcs ({mcs}) out of range [0, 28]")

    def tx_power_at(rb_: int, mcs_: int) -> int:
        return ph_factor(
            mu,
            tbs_bits_fn(rb_, mcs_),
            rb_,
            n_layers,
            n_symbols,
            n_dmrs,
            delta_mcs_enabled,
            include_bw=True,
        )

    tx_power = tx_power_at(rb, mcs)

    while ph_limit < tx_power and rb > min_rb:
        rb -= 1
        tx_power = tx_power_at(rb, mcs)

    while ph_limit < tx_power and mcs > 0:
        mcs -= 1
        tx_power = tx_power_at(rb, mcs)

    return rb, mcs, ph_limit < tx_power
