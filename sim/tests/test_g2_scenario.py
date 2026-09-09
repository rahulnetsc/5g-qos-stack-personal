"""GT-1.2's cell, and the one property the whole test is about.

`aperiodic_event` had every other property of a STOP flow and lacked exactly
one: two robots firing in the SAME slot. Measured at the real 0.2 Hz cadence,
17 events landed in 17 distinct slots and no slot ever held two
(`docs/g2-step0-2026-09-09.md`). So simultaneity is what these pin.
"""
from __future__ import annotations

import collections

import numpy as np
import pytest

from sim.buffer import BufferModel
from sim.messages import MessageLedger
from sim.scenarios.g2 import (N_TRIALS, QFI_FLOOD_DL, QFI_FLOOD_UL, QFI_STOP,
                              STOP_BOUND_MS, TDD_PERIOD_SLOTS,
                              assert_stop_instrument_live, build_gt12_scenario,
                              minimum_horizon_slots, stop_flow_keys,
                              trial_slots)
from sim.scenarios.schedule_guard import ScheduleTooLongForHorizon
from sim.traffic import TrafficModel

H = 40_000


def _fire_map(sc):
    """Slot -> how many STOP flows fired in it, from the real generator."""
    buf = BufferModel()
    for f in sc.flows:
        buf.register(f.ue_id, f.qfi, is_ul=(f.direction == "UL"),
                     lcg=f.lcg, direction=f.direction)
    tm = TrafficModel(sc.flows, buf,
                      1.0 / (2 ** sc.carrier.numerology) / 1000.0,
                      np.random.default_rng(sc.seed), MessageLedger())
    per_slot = collections.Counter()
    for slot in range(sc.horizon_slots):
        for _ue, qfi, _b in tm.generate(slot):
            if qfi == QFI_STOP:
                per_slot[slot] += 1
    return per_slot


@pytest.mark.parametrize("n_ues,n_stop", [(4, 2), (8, 2), (8, 4), (8, 8), (16, 4)])
def test_every_stop_fires_in_the_SAME_slot(n_ues, n_stop):
    """THE PROPERTY GT-1.2 EXISTS TO TEST. Not "n STOPs happened" -- n STOPs
    in ONE slot, on every trial, so the test exercises same-slot DL
    contention rather than n independent events that happen to be nearby."""
    sc = build_gt12_scenario(seed=7, n_ues=n_ues, n_stop=n_stop, horizon_slots=H)
    fired = _fire_map(sc)
    assert len(fired) == N_TRIALS, (
        f"{len(fired)} distinct firing slots, expected {N_TRIALS} trials")
    assert set(fired.values()) == {n_stop}, (
        f"trials fired with {sorted(set(fired.values()))} robots, expected "
        f"every trial to stop all {n_stop} simultaneously")
    assert sorted(fired) == list(trial_slots(7))


def test_the_trigger_phase_is_randomised_over_the_tdd_frame():
    """A STOP landing just before a D-slot waits differently from one landing
    just after, so a fixed phase tests one alignment. Over 30 trials every
    within-frame position must be visited."""
    for seed in (1, 7, 12345):
        phases = {s % TDD_PERIOD_SLOTS for s in trial_slots(seed)}
        assert phases == set(range(TDD_PERIOD_SLOTS)), (seed, sorted(phases))
    # and the schedule differs between seeds, or 10 seeds test one schedule
    assert trial_slots(1) != trial_slots(7)


def test_the_schedule_is_deterministic_for_a_seed():
    assert trial_slots(99) == trial_slots(99)


def test_trials_are_spaced_wider_than_the_bound_they_are_scored_against():
    """A trial is scored by looking for a completion after its trigger, so
    two trials closer together than the bound would be indistinguishable."""
    slot_ms = 0.25
    for seed in (1, 7, 12345):
        s = trial_slots(seed)
        gaps_ms = [(b - a) * slot_ms for a, b in zip(s, s[1:])]
        assert min(gaps_ms) > STOP_BOUND_MS, min(gaps_ms)


def test_the_cell_is_saturated_in_BOTH_directions():
    sc = build_gt12_scenario(seed=1, n_ues=8, n_stop=2, horizon_slots=H)
    floods = {(f.qfi, f.direction): f for f in sc.flows
              if f.qfi in (QFI_FLOOD_DL, QFI_FLOOD_UL)}
    assert (QFI_FLOOD_DL, "DL") in floods and (QFI_FLOOD_UL, "UL") in floods
    for f in floods.values():
        assert f.traffic_params["rate_bps"] >= 50_000_000.0
    assert_stop_instrument_live(sc, n_stop=2)


def test_a_horizon_that_cannot_SCORE_the_last_trial_is_refused():
    """The shared guard, and note the derivation: the last trial's 100 ms
    window must close inside the run, not merely its trigger fire."""
    need = minimum_horizon_slots(1)
    build_gt12_scenario(seed=1, n_ues=4, n_stop=1, horizon_slots=need + 1)
    with pytest.raises(ScheduleTooLongForHorizon):
        build_gt12_scenario(seed=1, n_ues=4, n_stop=1, horizon_slots=need - 1)


def test_the_grid_is_triangular():
    with pytest.raises(ValueError):
        build_gt12_scenario(seed=1, n_ues=4, n_stop=5, horizon_slots=H)
    with pytest.raises(ValueError):
        build_gt12_scenario(seed=1, n_ues=4, n_stop=0, horizon_slots=H)


def test_stop_flow_keys_follow_n_stop():
    for n_stop in (1, 2, 4):
        sc = build_gt12_scenario(seed=1, n_ues=8, n_stop=n_stop, horizon_slots=H)
        assert len(stop_flow_keys(sc)) == n_stop
        with pytest.raises(AssertionError):
            assert_stop_instrument_live(sc, n_stop=n_stop + 1)


def test_the_stop_bearer_pdb_is_the_5qi_s_own_unless_asked_otherwise():
    """5 ms is the STANDARDISED PDB and the default; 100 ms is the DIAGNOSTIC
    that asks when a discarded STOP would have arrived. Both are deliberate
    and the scenario must not blur them."""
    faithful = build_gt12_scenario(seed=1, n_ues=8, n_stop=2, horizon_slots=H)
    assert {f.pdb_ms for f in faithful.flows if f.qfi == QFI_STOP} == {5.0}
    lifted = build_gt12_scenario(seed=1, n_ues=8, n_stop=2, horizon_slots=H,
                                 stop_pdb_ms=STOP_BOUND_MS)
    assert {f.pdb_ms for f in lifted.flows if f.qfi == QFI_STOP} == {100.0}
    # and lifting the PDB must change NOTHING else about the cell
    a = [(f.ue_id, f.qfi, f.direction, f.traffic_params)
         for f in faithful.flows if f.qfi != QFI_STOP]
    b = [(f.ue_id, f.qfi, f.direction, f.traffic_params)
         for f in lifted.flows if f.qfi != QFI_STOP]
    assert a == b


def test_committed_mult_scales_the_fleet_and_never_the_stop():
    a = build_gt12_scenario(seed=1, n_ues=8, n_stop=2, horizon_slots=H)
    b = build_gt12_scenario(seed=1, n_ues=8, n_stop=2, horizon_slots=H,
                            committed_mult=2.0)

    def stop(sc):
        return [f for f in sc.flows if f.qfi == QFI_STOP]

    for x, y in zip(stop(a), stop(b)):
        assert x.traffic_params == y.traffic_params
    cam_a = [f for f in a.flows if f.qfi == 2][0]
    cam_b = [f for f in b.flows if f.qfi == 2][0]
    assert cam_b.gfbr_bps == pytest.approx(2 * cam_a.gfbr_bps)
