"""The activation gate generalised from one window to a list.

WP9 G11 commit 4. GT-7.1 scripts three things the single (active_from_s,
active_until_s) pair cannot express -- a duty-cycled teleop stream, waypoint
pauses, and a one-shot STOP drill -- and all three are "active during any of
these intervals".

THE GUARD THAT BINDS, and this is the one commit in G11 where it does.
Per CLAUDE.md: name what the check reads and what the commit touches.
`regression_corpus.py --check` reads RunRecords; this commit changes
`sim/traffic.py`, which produces them; they INTERSECT. So a clean --check
here is evidence rather than a structural inevitability -- it says the
generalisation did not perturb any existing scenario. The tests below cover
what --check cannot: that the two spellings are equivalent BY CONSTRUCTION,
and that the new shapes do what GT-7.1 needs.
"""

from __future__ import annotations

import numpy as np
import pytest

from scheduler.flow import FlowConfig
from sim.buffer import BufferModel
from sim.traffic import TrafficModel

SLOT_S = 0.00025


def _flow(**params) -> FlowConfig:
    return FlowConfig(
        ue_id=1, qfi=1, direction="UL", flow_class="Delay", pdb_ms=100.0,
        traffic_kind="deterministic",
        traffic_params={"period_ms": 10.0, "bytes_per_period": 100, **params},
    )


def _active_slots(flow: FlowConfig, horizon: int) -> list[int]:
    """Slots at which the flow actually produced an arrival."""
    buffers = BufferModel()
    buffers.register(flow.ue_id, flow.qfi, is_ul=True, lcg=flow.lcg)
    tm = TrafficModel([flow], buffers, SLOT_S, np.random.default_rng(7))
    out = []
    for s in range(horizon):
        before = buffers.state(flow.ue_id, flow.qfi).bytes_queued
        tm.generate(s)
        if buffers.state(flow.ue_id, flow.qfi).bytes_queued > before:
            out.append(s)
    return out


@pytest.mark.parametrize("pair", [
    (None, None), (0.5, None), (None, 1.0), (0.5, 1.5), (0.0, 2.0),
])
def test_a_single_pair_is_exactly_a_one_element_window_list(pair):
    """The equivalence the whole design rests on.

    If these ever diverge, the generalisation stopped being strict and
    --check's cleanliness stops meaning anything.
    """
    af, au = pair
    single = _active_slots(_flow(active_from_s=af, active_until_s=au), 8_000)
    listed = _active_slots(_flow(active_windows=((af, au),)), 8_000)
    assert single == listed, (
        f"single pair {pair} and its one-element list disagree: "
        f"{len(single)} vs {len(listed)} arrivals")


def test_no_activation_keys_means_always_on():
    assert len(_active_slots(_flow(), 4_000)) == 4_000 // 40   # 10 ms period


def test_a_duty_cycle_is_a_repeating_window_list():
    """Teleop cmd_vel duty-cycled: on 0.2 s of every 0.5 s."""
    wins = tuple((k * 0.5, k * 0.5 + 0.2) for k in range(4))
    got = _active_slots(_flow(active_windows=wins), 8_000)      # 2.0 s
    assert got, "no arrivals at all -- the gate closed everything"
    for s in got:
        t = s * SLOT_S
        assert any(f <= t < u for f, u in wins), f"arrival at {t:.4f}s is outside every window"
    # and it really is intermittent, not just narrowed
    assert len(got) < 8_000 // 40


def test_a_waypoint_pause_is_a_gap_between_windows():
    wins = ((0.0, 0.5), (1.5, 2.0))            # silent 0.5-1.5 s
    got = [s * SLOT_S for s in _active_slots(_flow(active_windows=wins), 8_000)]
    assert got, "no arrivals"
    assert not any(0.5 <= t < 1.5 for t in got), "traffic during the pause"
    assert any(t < 0.5 for t in got) and any(t >= 1.5 for t in got), \
        "the flow did not resume after the pause"


def test_a_one_shot_stop_drill_fires_exactly_once():
    """A STOP at an exact time: one window narrow enough for one period."""
    wins = ((1.0, 1.0 + 0.010),)               # one 10 ms period
    got = _active_slots(_flow(active_windows=wins), 8_000)
    assert len(got) == 1, f"expected exactly one burst, got {len(got)}"
    assert got[0] * SLOT_S == pytest.approx(1.0, abs=SLOT_S)


def test_windows_are_half_open_matching_wp9_window_Window_contains():
    """[from, until) -- an arrival exactly at `until` is OUTSIDE."""
    got = [s * SLOT_S for s in _active_slots(
        _flow(active_windows=((0.0, 1.0),)), 8_000)]
    assert max(got) < 1.0
    assert any(t == pytest.approx(0.0, abs=1e-9) for t in got)


def test_an_open_ended_window_is_allowed_in_the_list_form():
    got = [s * SLOT_S for s in _active_slots(
        _flow(active_windows=((1.0, None),)), 8_000)]
    assert min(got) >= 1.0 and max(got) >= 1.9
