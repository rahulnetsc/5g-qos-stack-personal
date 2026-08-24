"""WP6 commit 3: sim/rlf.py sync-loss DETECTION, dormant -- not wired into
driver.py, config.py, or any scheduler (docs/wp6-plan.md Decision 4).
Predicted, before writing this file: scripts/regression_corpus.py --check
stays fully clean -- sim/driver.py is not touched at all this commit, so
there is no code path by which anything here could run during a
driver.run() call, regardless of scenario (the same strongest-form
inertness argument as docs/wp5-plan.md commit 6 / sim/olla.py).

Timer values below (t310_ms=2000, n310=10, n311=1) are the
RlfDetectorConfig defaults, cited from calibration-logs/
twotier_startup_gnb.log:17 -- not chosen for the test."""

import pytest

from sim.rlf import RlfDetectorConfig, RlfDetectorState, SyncState, step, t310_slots

SLOT_DURATION_S = 0.0005  # 0.5ms/slot, numerology mu=1 (this deployment's default)


def _run(state, config, snr_sequence, slot_duration_s=SLOT_DURATION_S, start_slot=0):
    """Feed a sequence of true SNR values through step(), one per slot,
    returning the list of RlfStepResults."""
    results = []
    for i, snr_db in enumerate(snr_sequence):
        results.append(step(state, config, snr_db, start_slot + i, slot_duration_s))
    return results


# -- RlfDetectorConfig validation ----------------------------------------


def test_config_rejects_non_positive_t310():
    with pytest.raises(ValueError):
        RlfDetectorConfig(t310_ms=0.0)


def test_config_rejects_non_positive_n310_or_n311():
    with pytest.raises(ValueError):
        RlfDetectorConfig(n310=0)
    with pytest.raises(ValueError):
        RlfDetectorConfig(n311=0)


# -- t310_slots conversion ------------------------------------------------


def test_t310_slots_matches_2000ms_at_half_ms_slots():
    config = RlfDetectorConfig()  # t310_ms=2000
    assert t310_slots(config, SLOT_DURATION_S) == 4000


def test_t310_slots_floors_to_at_least_one():
    config = RlfDetectorConfig(t310_ms=0.001)
    assert t310_slots(config, SLOT_DURATION_S) >= 1


# -- staying IN_SYNC -------------------------------------------------------


def test_stays_in_sync_when_snr_never_drops():
    config = RlfDetectorConfig()
    state = RlfDetectorState()
    results = _run(state, config, [10.0] * 100)
    assert state.sync_state == SyncState.IN_SYNC
    assert not any(r.rlf_declared_this_slot for r in results)


def test_a_single_good_slot_resets_the_n310_counter_before_arming():
    """n310 counts CONSECUTIVE bad slots -- an interrupting good slot must
    reset the count, not just pause it."""
    config = RlfDetectorConfig(n310=5)
    state = RlfDetectorState()
    # 4 bad, 1 good, 4 bad: never reaches 5 consecutive, never arms.
    _run(state, config, [-10.0] * 4 + [10.0] + [-10.0] * 4)
    assert state.sync_state == SyncState.IN_SYNC
    assert state.consecutive_bad_slots == 4


# -- arming T310 (n310) ----------------------------------------------------


def test_t310_arms_exactly_at_the_nth310_consecutive_bad_slot_not_before():
    config = RlfDetectorConfig(n310=10)
    state = RlfDetectorState()
    _run(state, config, [-10.0] * 9)
    assert state.sync_state == SyncState.IN_SYNC
    step(state, config, -10.0, 9, SLOT_DURATION_S)  # 10th consecutive bad slot
    assert state.sync_state == SyncState.T310_RUNNING
    assert state.t310_elapsed_slots == 0


# -- T310 dwell / RLF declaration ------------------------------------------


def test_rlf_declared_exactly_when_t310_expires_not_before_or_after():
    config = RlfDetectorConfig(n310=1, t310_ms=5.0)  # t310 = 10 slots @ 0.5ms
    state = RlfDetectorState()
    dwell = t310_slots(config, SLOT_DURATION_S)
    assert dwell == 10
    # Arm T310 on slot 0 (n310=1), then stay bad for `dwell` more slots.
    results = _run(state, config, [-10.0] * (1 + dwell))
    assert state.sync_state == SyncState.T310_RUNNING or state.sync_state == SyncState.RLF_DECLARED
    declared_slots = [i for i, r in enumerate(results) if r.rlf_declared_this_slot]
    assert declared_slots == [dwell]  # 0-indexed: arms at slot 0, expires at slot `dwell`
    assert state.sync_state == SyncState.RLF_DECLARED
    assert state.rlf_declared_at_slot == dwell


def test_rlf_declared_at_slot_records_the_actual_slot_index_passed():
    config = RlfDetectorConfig(n310=1, t310_ms=1.0)  # t310 = 2 slots
    state = RlfDetectorState()
    _run(state, config, [-10.0] * 3, start_slot=1000)
    assert state.sync_state == SyncState.RLF_DECLARED
    assert state.rlf_declared_at_slot == 1002


# -- n311 cancellation -------------------------------------------------


def test_a_single_good_slot_cancels_t310_when_n311_is_one():
    config = RlfDetectorConfig(n310=1, n311=1, t310_ms=1000.0)
    state = RlfDetectorState()
    step(state, config, -10.0, 0, SLOT_DURATION_S)  # arms T310
    assert state.sync_state == SyncState.T310_RUNNING
    step(state, config, -10.0, 1, SLOT_DURATION_S)
    assert state.t310_elapsed_slots == 1
    step(state, config, 10.0, 2, SLOT_DURATION_S)  # one in-sync sample
    assert state.sync_state == SyncState.IN_SYNC
    assert state.t310_elapsed_slots == 0
    assert state.consecutive_bad_slots == 0


def test_n311_requires_consecutive_good_slots_not_just_one_when_greater_than_one():
    """Generalized, not hardcoded to n311=1 -- a deployment with n311=3
    should need 3 consecutive in-sync samples, and an interrupting bad
    slot should reset that count."""
    config = RlfDetectorConfig(n310=1, n311=3, t310_ms=1000.0)
    state = RlfDetectorState()
    step(state, config, -10.0, 0, SLOT_DURATION_S)  # arms T310
    step(state, config, 10.0, 1, SLOT_DURATION_S)
    step(state, config, 10.0, 2, SLOT_DURATION_S)
    assert state.sync_state == SyncState.T310_RUNNING  # only 2 of 3 good slots so far
    step(state, config, -10.0, 3, SLOT_DURATION_S)  # interrupts the good-slot streak
    assert state.consecutive_good_slots == 0
    step(state, config, 10.0, 4, SLOT_DURATION_S)
    step(state, config, 10.0, 5, SLOT_DURATION_S)
    step(state, config, 10.0, 6, SLOT_DURATION_S)  # 3 consecutive good slots now
    assert state.sync_state == SyncState.IN_SYNC


# -- terminal RLF_DECLARED state -------------------------------------------


def test_step_is_a_no_op_once_rlf_is_declared():
    config = RlfDetectorConfig(n310=1, t310_ms=1.0)  # t310 = 2 slots
    state = RlfDetectorState()
    _run(state, config, [-10.0] * 3)
    assert state.sync_state == SyncState.RLF_DECLARED
    declared_at = state.rlf_declared_at_slot
    # Further steps, even with a strongly in-sync SNR, must not un-declare.
    for i in range(10):
        result = step(state, config, 30.0, 100 + i, SLOT_DURATION_S)
        assert result.rlf_declared_this_slot is False
    assert state.sync_state == SyncState.RLF_DECLARED
    assert state.rlf_declared_at_slot == declared_at
