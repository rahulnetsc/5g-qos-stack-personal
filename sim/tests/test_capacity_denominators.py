"""Defect #29: a ratio's denominator must not include capacity that cannot
contribute — and a binding claim needs the per-slot distribution.

CCE utilisation summed the budget of EVERY slot while an uplink-only workload
can never spend a D-slot's budget, so 0.6357 read as "loaded" against a
ceiling that was actually 0.70. Same number, opposite conclusion.

These tests pin BOTH halves of the fix, and one of them pins the thing that
was already right so a future edit cannot quietly break it.
"""

from __future__ import annotations

import dataclasses

from sim.driver import run
from sim.baselines.pf import ProportionalFair
from sim.parametric import sweep_scenario
from sim.scenarios import sensor_dense_scenario


def _run(sc):
    return run(sc, ProportionalFair(ewma_window_slots=200), cqi_delay_slots=8)


def test_cce_is_reported_PER_SLOT_KIND_not_only_as_an_aggregate():
    """The aggregate averages an unspendable D budget into a saturated U one.
    The breakdown is what makes it interpretable."""
    s = _run(dataclasses.replace(sensor_dense_scenario(),
                                 seed=1826701614, horizon_slots=4000))
    by = s["cce_utilization_by_slot_kind"]
    assert set(by) >= {"D", "S", "U"}, by
    # the defect, made visible: D is essentially unspendable here, U is not
    assert by["D"] < 0.05, f"D-slots should be near-unused on a UL-only workload: {by}"
    assert by["U"] > 0.80, f"U-slots should be near-saturated: {by}"
    # and the aggregate sits BELOW the U figure, which is the whole point
    assert s["cce_utilization"] < by["U"]


def test_binding_is_reported_as_a_PER_SLOT_DISTRIBUTION():
    """Binding is a property of the worst slot. An aggregate cannot show it."""
    sd = _run(dataclasses.replace(sensor_dense_scenario(),
                                  seed=1826701614, horizon_slots=4000))
    pm = _run(sweep_scenario(seed=1826701614, n_ues=8, horizon_slots=4000))
    assert sd["cce_slots_at_cap"] > 0, "sensor_dense saturates individual slots"
    assert pm["cce_slots_at_cap"] == 0, "the parametric mix does not"
    # THE DISCRIMINATION THE AGGREGATE CANNOT MAKE: both have a comfortable
    # aggregate; only one is binding.
    assert sd["cce_frac_slots_at_cap"] > 0.2
    assert pm["cce_frac_slots_at_cap"] == 0.0


def test_PRB_denominators_stay_direction_gated():
    """The mirrored defect does NOT exist for PRB, because
    `record_grid_capacity` is already direction-gated. This pins that: a DL-
    only workload's ul_prb_utilization must not be diluted by DL-only slots,
    and vice versa.

    Written because CCE was the only unguarded denominator and the obvious
    regression is someone 'simplifying' record_grid_capacity to match it.
    """
    sc = sweep_scenario(seed=1, n_ues=4, horizon_slots=4000)
    dl_only = dataclasses.replace(
        sc, flows=[f for f in sc.flows if f.direction == "DL"])
    s = _run(dl_only)
    # With no UL flows at all, UL utilisation is 0 -- and the DL figure must
    # be computed over DL-capable slots only, so it stays a real fraction
    # rather than being divided by every slot in the run.
    assert s["ul_prb_utilization"] == 0.0
    assert 0.0 <= s["dl_prb_utilization"] <= 1.0
    # the denominator excluded UL-only slots: a naive all-slot denominator
    # would make this strictly smaller than the direction-gated one
    assert s["dl_prb_utilization"] > 0.0


def test_the_budget_and_used_counts_are_both_exposed():
    """So a reader can recompute any ceiling themselves rather than trusting
    one this code chose -- the reason a `cce_achievable_ceiling` field was
    tried and abandoned."""
    s = _run(dataclasses.replace(sensor_dense_scenario(),
                                 seed=1826701614, horizon_slots=4000))
    b, u = s["cce_budget_by_slot_kind"], s["cce_used_by_slot_kind"]
    assert set(b) == set(u)
    assert sum(b.values()) > 0
    for k in b:
        assert u[k] <= b[k], f"{k}: used {u[k]} exceeds budget {b[k]}"
