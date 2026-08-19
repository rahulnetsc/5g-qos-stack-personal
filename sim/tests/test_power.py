"""Tests for sim/power.py (WP1) and scheduler/link.py::snr_to_prb_floor.

Everything here is dormant, sim-only machinery (README.md §4, WP1) -- these
tests exercise the pure functions directly, not through any scheduler.
"""

import math

import pytest

from sim.power import _round_half_away_from_zero, ph_factor, shrink_to_power_budget
from scheduler import bits_per_prb, snr_to_prb_floor


# --- ph_factor ---------------------------------------------------------


def test_ph_factor_delta_tf_zero_when_delta_mcs_disabled():
    """With delta_mcs_enabled=False, tx_power is bw_factor alone."""
    tx = ph_factor(
        mu=1, tbs_bits=5000, rb=20, n_layers=1, n_symbols=14, n_dmrs=12,
        delta_mcs_enabled=False,
    )
    assert tx == round(10 * math.log10(20 << 1))


def test_ph_factor_delta_tf_zero_when_multi_layer():
    """delta_tf is 0 when n_layers != 1, even with delta_mcs_enabled=True
    (mirrors the C source's `deltaMCS != NULL && n_layers == 1` guard)."""
    tx = ph_factor(
        mu=1, tbs_bits=5000, rb=20, n_layers=2, n_symbols=14, n_dmrs=12,
        delta_mcs_enabled=True,
    )
    assert tx == round(10 * math.log10(20 << 1))


def test_ph_factor_bw_factor_monotonic_in_rb_and_mu():
    """With delta_tf forced to 0, tx_power == bw_factor, which must rise
    with more RBs and with higher numerology (rb << mu)."""
    kwargs = dict(tbs_bits=1, n_layers=1, n_symbols=14, n_dmrs=0,
                  delta_mcs_enabled=False)
    rb_series = [ph_factor(mu=0, rb=rb, **kwargs) for rb in (2, 5, 10, 20, 50)]
    assert all(a <= b for a, b in zip(rb_series, rb_series[1:]))
    assert rb_series[0] < rb_series[-1]

    mu_series = [ph_factor(mu=mu, rb=10, **kwargs) for mu in (0, 1, 2, 3)]
    assert all(a <= b for a, b in zip(mu_series, mu_series[1:]))
    assert mu_series[0] < mu_series[-1]


def test_ph_factor_include_bw_false_drops_bandwidth_term():
    """include_bw=False (the phr_txpower_calc telemetry sites, L2534/2888)
    returns delta_tf alone -- verified against the 38.213 7.1.1 formula
    computed independently here, not by re-calling ph_factor."""
    mu, tbs_bits, rb, n_symbols, n_dmrs = 1, 1000, 10, 14, 0
    n_re = (12 * n_symbols - n_dmrs) * rb
    bpre = tbs_bits / n_re
    expected_delta_tf = round(10 * math.log10((2 ** (bpre * 1.25) - 1) * 1.0))

    tx = ph_factor(
        mu=mu, tbs_bits=tbs_bits, rb=rb, n_layers=1, n_symbols=n_symbols,
        n_dmrs=n_dmrs, delta_mcs_enabled=True, include_bw=False,
    )
    assert tx == expected_delta_tf
    # Sanity: with include_bw=True the same call must differ (bw term
    # actually gets added back in).
    tx_with_bw = ph_factor(
        mu=mu, tbs_bits=tbs_bits, rb=rb, n_layers=1, n_symbols=n_symbols,
        n_dmrs=n_dmrs, delta_mcs_enabled=True, include_bw=True,
    )
    assert tx_with_bw != tx


def test_round_half_away_from_zero_at_exact_half():
    """Python's round() rounds half to even; roundf() rounds half away
    from zero. These disagree at exact .5 boundaries -- verify the sim
    matches roundf(), not round()."""
    assert round(2.5) == 2  # builtin: half-to-even, for contrast
    assert _round_half_away_from_zero(2.5) == 3
    assert _round_half_away_from_zero(-2.5) == -3
    assert _round_half_away_from_zero(0.5) == 1
    assert _round_half_away_from_zero(-0.5) == -1
    # Non-boundary values still round the ordinary way.
    assert _round_half_away_from_zero(2.4) == 2
    assert _round_half_away_from_zero(2.6) == 3


def test_ph_factor_raises_on_nonpositive_rb():
    """rb <= 0 degenerates n_re and rb << mu to log10(0); raise instead of
    mirroring the C's log10(0.0) == -inf cast to int, which is undefined
    behavior in C, not a deterministic hardware behavior."""
    with pytest.raises(ValueError):
        ph_factor(
            mu=0, tbs_bits=1000, rb=0, n_layers=1, n_symbols=14, n_dmrs=0,
            delta_mcs_enabled=True,
        )
    with pytest.raises(ValueError):
        ph_factor(
            mu=0, tbs_bits=1000, rb=-1, n_layers=1, n_symbols=14, n_dmrs=0,
            delta_mcs_enabled=False,
        )


def test_ph_factor_raises_on_nonpositive_tbs_bits_when_delta_tf_active():
    """tbs_bits <= 0 only matters when delta_tf is actually computed
    (delta_mcs_enabled and n_layers == 1); it's a no-op input otherwise."""
    with pytest.raises(ValueError):
        ph_factor(
            mu=0, tbs_bits=0, rb=10, n_layers=1, n_symbols=14, n_dmrs=0,
            delta_mcs_enabled=True,
        )
    # tbs_bits=0 is harmless when delta_tf isn't computed at all.
    tx = ph_factor(
        mu=0, tbs_bits=0, rb=10, n_layers=1, n_symbols=14, n_dmrs=0,
        delta_mcs_enabled=False,
    )
    assert tx == _round_half_away_from_zero(10 * math.log10(10))


# --- shrink_to_power_budget ---------------------------------------------

_SE_BY_MCS = {0: 1.0, 1: 2.0, 2: 3.0}


def _make_tbs_bits_fn(n_symbols, n_dmrs):
    """A synthetic TBS model where BPRE = se_by_mcs[mcs] regardless of rb
    (n_re cancels out): tbs_bits(rb, mcs) = se_by_mcs[mcs] * n_re(rb).
    This makes delta_tf depend only on mcs and bw_factor only on rb, so the
    two loops' individual effects are separable and independently
    checkable via direct ph_factor calls -- which is what the loop-order
    test below relies on."""

    def tbs_bits_fn(rb, mcs):
        n_re = (12 * n_symbols - n_dmrs) * rb
        return int(_SE_BY_MCS[mcs] * n_re)

    return tbs_bits_fn


def test_shrink_to_power_budget_runs_loops_in_documented_order():
    """RB is shrunk to min_rb BEFORE MCS is ever touched, even when a
    single MCS step-down at the *original* rb would already have met the
    budget. A joint (or MCS-first) optimizer would prefer that cheaper
    alternative -- it keeps all 10 RBs instead of losing 5. The two-loop
    algorithm does not consider it: it drains rb to min_rb first, and only
    then would fall back to MCS. Mirrors nr_ue_max_mcs_min_rb's structure,
    not a joint optimum."""
    n_symbols, n_dmrs = 14, 0
    tbs_bits_fn = _make_tbs_bits_fn(n_symbols, n_dmrs)
    mu, rb, min_rb, mcs = 0, 10, 5, 2
    ph_limit = 18

    # Confirm the road not taken: dropping MCS by one step alone, at the
    # starting rb, already satisfies ph_limit.
    tx_mcs_only = ph_factor(
        mu, tbs_bits_fn(rb, mcs - 1), rb, n_layers=1, n_symbols=n_symbols,
        n_dmrs=n_dmrs, delta_mcs_enabled=True,
    )
    assert tx_mcs_only <= ph_limit, (
        "test setup invariant broken: MCS-only step should already satisfy "
        f"the budget (got tx_power={tx_mcs_only}, ph_limit={ph_limit})"
    )

    rb_out, mcs_out, over_budget = shrink_to_power_budget(
        mu=mu, ph_limit=ph_limit, rb=rb, min_rb=min_rb, mcs=mcs,
        n_layers=1, n_symbols=n_symbols, n_dmrs=n_dmrs,
        delta_mcs_enabled=True, tbs_bits_fn=tbs_bits_fn,
    )

    # RB was drained all the way to min_rb; MCS was never touched.
    assert rb_out == min_rb
    assert mcs_out == mcs
    assert over_budget is False


def test_shrink_to_power_budget_over_budget_after_both_loops_no_refusal():
    """If both loops exhaust (rb == min_rb, mcs == 0) and the grant is
    still over budget, the function returns normally with over_budget=True
    -- it must not raise or refuse, matching nr_ue_max_mcs_min_rb, which
    only logs and lets the grant proceed over-budget."""
    n_symbols, n_dmrs = 14, 0
    tbs_bits_fn = _make_tbs_bits_fn(n_symbols, n_dmrs)

    rb_out, mcs_out, over_budget = shrink_to_power_budget(
        mu=0, ph_limit=0, rb=10, min_rb=5, mcs=2,
        n_layers=1, n_symbols=n_symbols, n_dmrs=n_dmrs,
        delta_mcs_enabled=True, tbs_bits_fn=tbs_bits_fn,
    )

    assert rb_out == 5
    assert mcs_out == 0
    assert over_budget is True


def test_shrink_to_power_budget_raises_when_rb_below_min_rb():
    """Mirrors nr_ue_max_mcs_min_rb's AssertFatal(*Rb >= minRb, ...).
    Without this check, rb < min_rb would silently skip the RB loop (its
    `rb > min_rb` condition is false from the start) and fall straight
    into MCS reduction -- a plausible-looking result from an input the C
    treats as fatal."""
    tbs_bits_fn = _make_tbs_bits_fn(n_symbols=14, n_dmrs=0)
    with pytest.raises(ValueError):
        shrink_to_power_budget(
            mu=0, ph_limit=18, rb=4, min_rb=5, mcs=2,
            n_layers=1, n_symbols=14, n_dmrs=0,
            delta_mcs_enabled=True, tbs_bits_fn=tbs_bits_fn,
        )


def test_shrink_to_power_budget_raises_when_mcs_out_of_range():
    """Mirrors nr_ue_max_mcs_min_rb's AssertFatal(*mcs >= 0 && *mcs <= 28, ...)."""
    tbs_bits_fn = _make_tbs_bits_fn(n_symbols=14, n_dmrs=0)
    for bad_mcs in (-1, 29):
        with pytest.raises(ValueError):
            shrink_to_power_budget(
                mu=0, ph_limit=18, rb=10, min_rb=5, mcs=bad_mcs,
                n_layers=1, n_symbols=14, n_dmrs=0,
                delta_mcs_enabled=True, tbs_bits_fn=tbs_bits_fn,
            )


# --- snr_to_prb_floor ----------------------------------------------------


def test_snr_to_prb_floor_monotonically_rises_as_snr_falls():
    snrs_high_to_low = [28.0, 19.0, 10.0, 1.0]
    floors = [snr_to_prb_floor(snr, payload_bytes=500) for snr in snrs_high_to_low]
    assert all(a <= b for a, b in zip(floors, floors[1:]))
    assert floors[0] < floors[-1]


def test_snr_to_prb_floor_matches_bits_per_prb_directly():
    snr_db, payload_bytes, symbols = 20.0, 100, 14
    bits_per_rb, _ = bits_per_prb(snr_db, symbols)
    expected = math.ceil(payload_bytes * 8 / bits_per_rb)
    assert snr_to_prb_floor(snr_db, payload_bytes, symbols) == expected


def test_snr_to_prb_floor_raises_below_lowest_mcs():
    with pytest.raises(ValueError):
        snr_to_prb_floor(-10.0, payload_bytes=100)
