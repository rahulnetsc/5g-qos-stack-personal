"""WP5 commit 6: sim/olla.py, dormant -- not wired into driver.py or any
scheduler (docs/wp5-plan.md commit 6, README.md sec8). Predicted, before
writing this file: scripts/regression_corpus.py --check stays fully clean,
same as WP7 commits 3/5 and WP5 commits 0-2 -- driver.py is untouched this
commit, so this is the 14th such prediction in this lineage, and the
strongest form of it (not just "no scenario references the new field," but
"no runtime code path reaches this module at all")."""

import pytest

from sim.olla import (
    MCS_INDEX_COUNT,
    BLER_UPDATE_FRAME,
    BLER_FILTER,
    OllaOptions,
    OllaRoundCounters,
    OllaState,
    init_olla_state,
    update_mcs_from_bler,
)


def test_mcs_index_count_matches_the_shared_table():
    """MCS_INDEX_COUNT must track scheduler/link.py::_MCS_TABLE's row
    count exactly -- checked directly against that table, not re-derived,
    same discipline sim/bsr.py's own vendored-table tests use."""
    from scheduler.link import _MCS_TABLE

    assert MCS_INDEX_COUNT == len(_MCS_TABLE)


def test_init_olla_state_seeds_at_min_mcs_and_bler_midpoint():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=2, max_mcs=11)
    state = init_olla_state(options)
    assert state.mcs == 2
    assert state.bler == pytest.approx(0.125)
    assert state.last_frame == 0


def test_no_update_before_the_100ms_window_elapses():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = init_olla_state(options)
    counters = OllaRoundCounters(rounds0=100, rounds1=0)  # would justify +1 if it ran
    result = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=5)
    assert result == 0
    # Nothing mutated -- the early return happens before any state write.
    assert state.mcs == 0
    assert state.last_frame == 0
    assert state.rounds0_snapshot == 0


def test_update_fires_exactly_at_the_window_boundary():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = init_olla_state(options)
    counters = OllaRoundCounters(rounds0=10, rounds1=0)
    update_mcs_from_bler(options, counters, state, max_mcs=11, frame=BLER_UPDATE_FRAME)
    assert state.last_frame == BLER_UPDATE_FRAME  # ran, not the early-return path


def test_minus_one_on_high_bler_with_sufficient_activity():
    """Isolates the OR's first disjunct: bler > upper alone, with
    num_dl_sched > 3, so this is NOT the low-activity case."""
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = OllaState(mcs=5, bler=0.5, last_frame=0)
    counters = OllaRoundCounters(rounds0=10, rounds1=8)  # bler_window=0.8, high
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=10)
    expected_bler = BLER_FILTER * 0.5 + (1 - BLER_FILTER) * 0.8
    assert state.bler == pytest.approx(expected_bler)
    assert expected_bler > options.upper  # sanity: this case's own premise
    assert new_mcs == 4
    assert state.mcs == 4


def test_minus_one_on_low_activity_despite_good_bler():
    """The bug: num_dl_sched <= 3 forces -1 even when bler alone would
    have qualified for +1 -- because the +1 branch requires num_dl_sched
    > 3 too, and the -1 elif's OR doesn't care."""
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = OllaState(mcs=5, bler=0.01, last_frame=0)
    counters = OllaRoundCounters(rounds0=2, rounds1=0)  # num_dl_sched=2 <= 3
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=10)
    assert state.bler < options.lower  # bler alone would qualify for +1
    assert new_mcs == 4  # but low activity forces -1 instead


def test_idle_ue_ratchets_down_unconditionally_every_window():
    """num_dl_sched=0: bler_window falls back to the stale bler (EWMA
    becomes a no-op), but -1 still fires from num_dl_sched<=3 alone,
    regardless of how good bler already is."""
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = OllaState(mcs=7, bler=0.01, last_frame=0)  # excellent bler
    counters = OllaRoundCounters(rounds0=0, rounds1=0)  # fully idle
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=10)
    assert state.bler == pytest.approx(0.01)  # EWMA no-op, confirmed exactly
    assert new_mcs == 6  # ratcheted down anyway

    # And it keeps happening every window while idle -- not a one-time dip.
    update_mcs_from_bler(options, counters, state, max_mcs=11, frame=20)
    assert state.mcs == 5


def test_plus_one_requires_both_conditions_not_either():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)

    # (a) good bler AND sufficient activity -> +1.
    state_a = OllaState(mcs=3, bler=0.01, last_frame=0)
    counters_a = OllaRoundCounters(rounds0=10, rounds1=0)
    new_mcs_a = update_mcs_from_bler(options, counters_a, state_a, max_mcs=11, frame=10)
    assert new_mcs_a == 4

    # (b) good bler but INSUFFICIENT activity -> -1, not +1, not a no-op.
    state_b = OllaState(mcs=3, bler=0.01, last_frame=0)
    counters_b = OllaRoundCounters(rounds0=2, rounds1=0)
    new_mcs_b = update_mcs_from_bler(options, counters_b, state_b, max_mcs=11, frame=10)
    assert new_mcs_b == 2

    # (c) sufficient activity but bler within [lower, upper] -> no change.
    state_c = OllaState(mcs=3, bler=0.1, last_frame=0)
    counters_c = OllaRoundCounters(rounds0=10, rounds1=1)  # bler_window=0.1
    new_mcs_c = update_mcs_from_bler(options, counters_c, state_c, max_mcs=11, frame=10)
    assert options.lower <= state_c.bler <= options.upper  # sanity: this case's premise
    assert new_mcs_c == 3


def test_climb_back_is_strictly_plus_one_per_window_never_a_jump():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = OllaState(mcs=0, bler=0.01, last_frame=0)  # already forced to the floor
    counters = OllaRoundCounters(rounds0=0, rounds1=0)
    # Favourable conditions held for three consecutive windows.
    seen = []
    for i in range(1, 4):
        counters.rounds0 += 10  # sufficient activity each window
        new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=10 * i)
        seen.append(new_mcs)
    assert seen == [1, 2, 3]  # one step per window, never more


def test_max_mcs_ceiling_blocks_further_climb():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=3)
    state = OllaState(mcs=3, bler=0.01, last_frame=0)  # already at the ceiling
    counters = OllaRoundCounters(rounds0=0, rounds1=0)
    counters.rounds0 += 10
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=10)
    assert new_mcs == 3  # can't exceed options.max_mcs


def test_min_mcs_floor_blocks_further_drop():
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=2, max_mcs=11)
    state = OllaState(mcs=2, bler=0.01, last_frame=0)  # already at the floor
    counters = OllaRoundCounters(rounds0=0, rounds1=0)  # idle -- would ratchet down
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=10)
    assert new_mcs == 2  # can't go below options.min_mcs


def test_max_mcs_parameter_is_clamped_by_options_max_mcs():
    """Mirrors get_mcs_from_bler's own `max_mcs = min(max_mcs,
    bler_options->max_mcs)` -- the per-call parameter can't override the
    per-direction options ceiling upward."""
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = OllaState(mcs=11, bler=0.01, last_frame=0)
    counters = OllaRoundCounters(rounds0=10, rounds1=0)
    # Pass a much larger per-call max_mcs than options.max_mcs allows.
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=20, frame=10)
    assert new_mcs == 11  # still capped by options.max_mcs, not the param


def test_frame_wraparound_is_handled():
    """frame_t wraps at 1024 (gNB_scheduler_primitives.c:794-795)."""
    options = OllaOptions(lower=0.05, upper=0.2, min_mcs=0, max_mcs=11)
    state = OllaState(mcs=5, bler=0.01, last_frame=1020)
    counters = OllaRoundCounters(rounds0=10, rounds1=0)
    # diff = 6 - 1020 = -1014 -> +1024 = 10 == BLER_UPDATE_FRAME: fires.
    new_mcs = update_mcs_from_bler(options, counters, state, max_mcs=11, frame=6)
    assert state.last_frame == 6  # the update branch ran, not the early return
    assert new_mcs == 6
