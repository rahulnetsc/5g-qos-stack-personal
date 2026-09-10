"""The UL floor's fires, counted two independent ways, required to agree.

WHY THIS TEST EXISTS. `scripts/g3_stress.py::FloorFireTally` reads floor fires
out of the rank stream by looking up the `floor_fire` tier in a snapshot's own
`term_names` and testing it against `_FLOOR_FIRED_KEY_VALUE = 0`. Both halves
of that are facts about `scheduler/two_tier.py::_ul_rank_key`, and if either
flipped the tally would report **zero** -- which is exactly the reading that
matters most (CLAUDE.md's audit calls the floor's activation "unknowable", so a
zero would be believed).

So the fires are also counted at the source, by wrapping `_update_ul_floor`,
and the two counts must match. That is the difference between an instrument
and a hopeful one: this test is what makes a zero from the tally mean the
floor did not fire, rather than that the tally did not bind.

It is the same discipline `scheduler/rank_trace.py` states for itself
(`field()` raises rather than defaulting, `finish()` raises on an empty
collection) applied to a consumer of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from scheduler.two_tier import TwoTier                          # noqa: E402
from sim.driver import run as driver_run                        # noqa: E402
from sim.scenarios.g3 import build_gt22_scenario                # noqa: E402

from g3_stress import FloorFireTally, _FLOOR_FIRED_KEY_VALUE, _FLOOR_TERM  # noqa: E402


def _run(arm, sc, tally):
    arm.rank_sink = tally
    return driver_run(sc, arm, cqi_delay_slots=8, max_sched_ues=4)


def test_the_tally_agrees_with_the_state_machine_itself():
    sc = build_gt22_scenario(seed=1, n_ues=4, horizon_slots=8_000)
    sched = TwoTier(min_rb=5)

    direct: list[tuple[int, int]] = []
    real = TwoTier._update_ul_floor

    def spy(self, ue_id, buffers, slot_index):
        fired, sil = real(self, ue_id, buffers, slot_index)
        if fired:
            direct.append((ue_id, slot_index))
        return fired, sil

    TwoTier._update_ul_floor = spy
    try:
        tally = FloorFireTally()
        _run(sched, sc, tally)
    finally:
        TwoTier._update_ul_floor = real

    assert tally.arm_declares_floor is True
    assert tally.snapshots > 0, "the rank sink never bound"
    assert tally.fires == len(direct), (
        f"the rank-stream tally counted {tally.fires} floor fires and the "
        f"state machine itself reported {len(direct)} -- the tier index or "
        f"the fired-key polarity has drifted, and the tally's failure mode "
        f"is a silent ZERO")


def test_the_fired_key_value_and_term_name_are_the_comparators_own():
    """Pins both literals against `_ul_rank_key` directly, so the agreement
    above cannot be a coincidence of a run in which nothing fired."""
    from scheduler.two_tier import _UL_TERMS, _Candidate
    assert _FLOOR_TERM in _UL_TERMS
    idx = _UL_TERMS.index(_FLOOR_TERM)
    sched = TwoTier(min_rb=5)
    kw = dict(flows=[], snr_db=10.0, bits_per_rb=100, bler=0.0, coef=1.0)
    fired = _Candidate(ue_id=1, **kw)
    fired.floor_fire = True
    quiet = _Candidate(ue_id=2, **kw)
    assert sched._ul_rank_key(fired)[idx] == _FLOOR_FIRED_KEY_VALUE
    assert sched._ul_rank_key(quiet)[idx] != _FLOOR_FIRED_KEY_VALUE


def test_an_arm_with_no_floor_tier_reports_None_and_not_zero():
    """PF and Reservation have no such tier -- Reservation has no floor even
    in principle. A structural absence must not read as a measured zero."""
    from sim.baselines.pf import ProportionalFair
    from scheduler.reservation import Reservation

    sc = build_gt22_scenario(seed=1, n_ues=3, horizon_slots=4_000)
    for arm in (ProportionalFair(ewma_window_slots=200), Reservation(min_rb=5)):
        tally = FloorFireTally()
        _run(arm, sc, tally)
        assert tally.snapshots > 0, f"{type(arm).__name__}: sink never bound"
        assert tally.arm_declares_floor is False
        rep = tally.report()
        assert rep["floor_fires"] is None
        assert rep["rank_candidate_slots"] > 0


def test_attaching_the_tally_does_not_change_the_run():
    """The bit-identity condition, checked rather than inherited from
    `rank_trace.py`'s own argument -- `scripts/verify_parallel.py`'s standard
    applied to a hook instead of a pool."""
    sc = build_gt22_scenario(seed=1, n_ues=4, horizon_slots=8_000)
    plain = driver_run(sc, TwoTier(min_rb=5), cqi_delay_slots=8,
                       max_sched_ues=4)
    sched = TwoTier(min_rb=5)
    tally = FloorFireTally()
    hooked = _run(sched, sc, tally)

    def flows_of(summary):
        return {k: (v.get("bytes_delivered"), v.get("bytes_dropped_pdb"),
                    v.get("throughput_bps"))
                for k, v in summary["flows"].items()}

    assert flows_of(plain) == flows_of(hooked)
    assert plain["scheduler_counters"] == hooked["scheduler_counters"]
    assert tally.fires >= 0
