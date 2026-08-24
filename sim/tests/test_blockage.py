"""WP6 commit 2: sim/blockage.py's pure two-state Markov functions."""

import pytest

from sim.blockage import step, transition_probability


# -- transition_probability -----------------------------------------------


def test_transition_probability_is_inverse_of_mean_dwell():
    assert transition_probability(4.0) == pytest.approx(0.25)
    assert transition_probability(600.0) == pytest.approx(1.0 / 600.0)


def test_transition_probability_clamps_at_one_for_short_dwell():
    """docs/wp6-plan.md sec 4 / Decision 3: a mean dwell at or below one
    slot isn't an error -- it's the discrete process's own floor (leaves
    every slot)."""
    assert transition_probability(1.0) == 1.0
    assert transition_probability(0.3) == 1.0


def test_transition_probability_rejects_non_positive_dwell():
    with pytest.raises(ValueError):
        transition_probability(0.0)
    with pytest.raises(ValueError):
        transition_probability(-5.0)


# -- step -------------------------------------------------------------


def test_step_leaves_state_when_draw_below_leave_probability():
    assert step(blocked=False, p_leave_blocked=0.1, p_leave_unblocked=0.5, draw=0.3) is True
    assert step(blocked=True, p_leave_blocked=0.5, p_leave_unblocked=0.1, draw=0.3) is False


def test_step_stays_when_draw_at_or_above_leave_probability():
    assert step(blocked=False, p_leave_blocked=0.1, p_leave_unblocked=0.5, draw=0.5) is False
    assert step(blocked=True, p_leave_blocked=0.5, p_leave_unblocked=0.1, draw=0.5) is True


def test_step_uses_the_probability_matching_current_state_not_the_other_one():
    """A high p_leave_blocked must not affect an Unblocked UE, and vice
    versa -- each state reads its own leave probability."""
    # Unblocked, p_leave_unblocked=0.0 (never leaves) regardless of a high
    # p_leave_blocked.
    assert step(blocked=False, p_leave_blocked=0.99, p_leave_unblocked=0.0, draw=0.01) is False
    # Blocked, p_leave_blocked=0.0 (never leaves) regardless of a high
    # p_leave_unblocked.
    assert step(blocked=True, p_leave_blocked=0.0, p_leave_unblocked=0.99, draw=0.01) is True
