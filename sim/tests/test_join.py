"""WP-Join commit 1: sim/join.py, dormant -- not wired into driver.py,
config.py, or any scheduler. Predicted, before writing this file:
scripts/regression_corpus.py --check stays fully clean -- sim/driver.py is
not touched at all this commit, so there is no code path by which
anything here could run during a driver.run() call, regardless of
scenario (the strongest-form inertness argument, same as sim/olla.py /
sim/rlf.py -- see docs/wp-join-plan.md sec4.1)."""

import numpy as np
import pytest

from sim.join import (
    JoinConfig,
    JoinEvent,
    JoinPhase,
    JoinState,
    init_join_rng_streams,
    init_join_state,
    rrc_connected,
    step,
)

SLOT_DURATION_S = 0.0005  # 0.5ms/slot, numerology mu=1 (this deployment's default)


def _rngs(seed=1234):
    return init_join_rng_streams(seed)


# -- JoinEvent / JoinConfig validation ------------------------------------


def test_join_event_rejects_invalid_kind():
    with pytest.raises(ValueError):
        JoinEvent(slot=0, kind="reboot")


def test_join_event_rejects_negative_slot():
    with pytest.raises(ValueError):
        JoinEvent(slot=-1, kind="power_on")


def test_join_config_rejects_invalid_initial_state():
    with pytest.raises(ValueError):
        JoinConfig(initial_state="asleep")


def test_join_config_rejects_p_expiry_out_of_range():
    with pytest.raises(ValueError):
        JoinConfig(p_expiry=0.0)
    with pytest.raises(ValueError):
        JoinConfig(p_expiry=1.0)


def test_join_config_rejects_non_ascending_events():
    with pytest.raises(ValueError):
        JoinConfig(events=(JoinEvent(10, "power_off"), JoinEvent(5, "power_on")))
    with pytest.raises(ValueError):
        JoinConfig(events=(JoinEvent(10, "power_off"), JoinEvent(10, "power_on")))


def test_join_config_rejects_negative_delay_fields():
    with pytest.raises(ValueError):
        JoinConfig(rach_rrc_setup_floor_ms=-1.0)


def test_join_config_rejects_non_positive_cell_search_good_snr_slots():
    with pytest.raises(ValueError):
        JoinConfig(cell_search_good_snr_slots=0)


# -- init_join_state -------------------------------------------------------


def test_init_join_state_defaults_to_connected():
    state = init_join_state(JoinConfig())
    assert state.phase is JoinPhase.CONNECTED
    assert state.app_running is True


def test_init_join_state_powered_off():
    state = init_join_state(JoinConfig(initial_state="powered_off"))
    assert state.phase is JoinPhase.POWERED_OFF
    assert state.app_running is False


# -- rrc_connected gate -----------------------------------------------------


def test_rrc_connected_gate_matches_the_documented_phase_set():
    connected = {JoinPhase.CONNECTED, JoinPhase.APP_RESTART, JoinPhase.APP_HANDSHAKE}
    for phase in JoinPhase:
        assert rrc_connected(phase) == (phase in connected)


# -- RNG streams -------------------------------------------------------------


def test_rng_streams_are_independent_and_reproducible():
    a = init_join_rng_streams(42)
    b = init_join_rng_streams(42)
    assert a.cold.random() == b.cold.random()  # same seed -> reproducible
    c = init_join_rng_streams(42)
    draws = {c.cold.random(), c.reest.random(), c.warm.random()}
    assert len(draws) == 3  # three distinct streams, not one shared generator


def test_deterministic_delay_consumes_no_rng_draw_when_ceiling_equals_floor():
    rngs = _rngs()
    state_before = rngs.cold.bit_generator.state
    config = JoinConfig(initial_state="powered_off", pdu_session_floor_ms=0.0, pdu_session_ceiling_ms=0.0)
    state = init_join_state(config)
    step(state, config, rngs, 0, SLOT_DURATION_S)  # POWERED_OFF, no event -> no draw either
    assert rngs.cold.bit_generator.state == state_before


# -- warm path (GT-6.1: app restart, radio never drops) ---------------------


def test_warm_path_never_drops_the_radio_and_reaches_connected():
    config = JoinConfig(events=(JoinEvent(5, "app_restart"),))
    state = init_join_state(config)
    rngs = _rngs()

    radio_edges = 0
    for i in range(6):  # slots 0..5 -- the event fires at slot 5
        r = step(state, config, rngs, i, SLOT_DURATION_S)
        if r.radio_connected_this_slot:
            radio_edges += 1
    assert state.active_path == "warm"
    assert state.trigger_slot == 5
    assert not state.app_running
    assert rrc_connected(state.phase)  # still connected throughout -- APP_RESTART is in the connected set
    assert radio_edges == 0  # radio never dropped, so never re-connects

    slot = 6
    while state.phase is not JoinPhase.APP_HANDSHAKE and slot < 20:
        step(state, config, rngs, slot, SLOT_DURATION_S)
        slot += 1
    assert state.phase is JoinPhase.APP_HANDSHAKE

    r_final = step(state, config, rngs, slot, SLOT_DURATION_S, handshake_complete=True)
    assert state.phase is JoinPhase.CONNECTED
    assert state.app_running is True
    assert state.cycle_index == 1
    assert r_final.app_connected_this_slot
    assert not r_final.radio_connected_this_slot


# -- cold path (GT-6.2: RACH -> RRC Setup -> PDU session -> handshake) ------


def test_cold_path_full_trace_reaches_connected_via_radio_reconnect_edge():
    config = JoinConfig(
        initial_state="powered_off",
        events=(JoinEvent(3, "power_on"),),
        rach_rrc_setup_floor_ms=1.0,
        rach_rrc_setup_ceiling_ms=5.0,
        pdu_session_floor_ms=0.0,
        pdu_session_ceiling_ms=0.0,
    )
    state = init_join_state(config)
    rngs = _rngs()
    assert state.phase is JoinPhase.POWERED_OFF

    for i in range(3):  # slots 0,1,2 -- nothing happens yet
        step(state, config, rngs, i, SLOT_DURATION_S)
    assert state.phase is JoinPhase.POWERED_OFF

    # slot 3: power_on fires -> RRC_ESTABLISH
    step(state, config, rngs, 3, SLOT_DURATION_S)
    assert state.phase is JoinPhase.RRC_ESTABLISH
    assert state.active_path == "cold"
    assert state.trigger_slot == 3

    radio_edges = 0
    slot = 4
    while state.phase is not JoinPhase.APP_HANDSHAKE and slot < 100:
        r = step(state, config, rngs, slot, SLOT_DURATION_S)
        if r.radio_connected_this_slot:
            radio_edges += 1
        slot += 1

    assert state.phase is JoinPhase.APP_HANDSHAKE
    assert radio_edges == 1  # radio_connected_this_slot fires exactly once (PDU_SESSION -> APP_HANDSHAKE)
    assert not state.app_running  # app_running only flips once handshake_complete is observed

    r_final = step(state, config, rngs, slot, SLOT_DURATION_S, handshake_complete=True)
    assert state.phase is JoinPhase.CONNECTED
    assert state.app_running is True
    assert r_final.app_connected_this_slot


def test_rrc_establish_timer_expiry_retries_in_place_and_counts_it():
    # ceiling < floor forces the deterministic (no-draw) branch to exceed
    # the ceiling every single attempt -- a clean, non-random way to
    # exercise the t300-expiry/retry edge without fighting the sampler.
    config = JoinConfig(
        initial_state="powered_off",
        events=(JoinEvent(0, "power_on"),),
        rach_rrc_setup_floor_ms=5.0,
        rach_rrc_setup_ceiling_ms=1.0,
    )
    state = init_join_state(config)
    rngs = _rngs()
    step(state, config, rngs, 0, SLOT_DURATION_S)
    assert state.phase is JoinPhase.RRC_ESTABLISH

    expiries = 0
    for i in range(1, 30):
        r = step(state, config, rngs, i, SLOT_DURATION_S)
        if r.timer_expired_this_slot:
            expiries += 1
    assert expiries >= 2  # retried more than once
    assert state.phase is JoinPhase.RRC_ESTABLISH  # never succeeds -- floor always exceeds ceiling
    assert state.timer_expiry_counts["rrc_establish"] == expiries


# -- reestablish path (GT-6.3: RLF -> cell search -> reestablish) -----------


def test_rlf_edge_enters_cell_search_and_app_running_never_drops():
    config = JoinConfig()
    state = init_join_state(config)
    rngs = _rngs()
    r = step(state, config, rngs, 0, SLOT_DURATION_S, rlf_declared_this_slot=True, snr_db=-20.0)
    assert state.phase is JoinPhase.CELL_SEARCH
    assert state.active_path == "reestablish"
    assert state.trigger_slot == 0
    assert state.app_running is True  # the robot's sensors don't stop -- only the radio dropped
    assert not r.radio_connected_this_slot


def test_cell_search_gates_on_both_snr_restoration_and_sampled_delay():
    config = JoinConfig(
        cell_search_ceiling_ms=100.0,
        cell_search_good_snr_slots=3,
        rlf_snr_floor_db=-5.0,
    )
    state = init_join_state(config)
    rngs = _rngs()
    step(state, config, rngs, 0, SLOT_DURATION_S, rlf_declared_this_slot=True, snr_db=-20.0)
    assert state.phase is JoinPhase.CELL_SEARCH

    # bad SNR: good_snr_slots never accumulates, never restores.
    for i in range(1, 5):
        r = step(state, config, rngs, i, SLOT_DURATION_S, snr_db=-20.0)
        assert not r.snr_restored_this_slot
    assert state.good_snr_slots == 0

    # good SNR, but interrupted just before reaching the threshold -- must reset.
    step(state, config, rngs, 5, SLOT_DURATION_S, snr_db=10.0)
    step(state, config, rngs, 6, SLOT_DURATION_S, snr_db=10.0)
    assert state.good_snr_slots == 2
    step(state, config, rngs, 7, SLOT_DURATION_S, snr_db=-20.0)  # interrupts
    assert state.good_snr_slots == 0

    # now let it actually restore for 3 consecutive slots.
    r1 = step(state, config, rngs, 8, SLOT_DURATION_S, snr_db=10.0)
    r2 = step(state, config, rngs, 9, SLOT_DURATION_S, snr_db=10.0)
    r3 = step(state, config, rngs, 10, SLOT_DURATION_S, snr_db=10.0)
    assert not r1.snr_restored_this_slot
    assert not r2.snr_restored_this_slot
    assert r3.snr_restored_this_slot
    assert state.phase is JoinPhase.REESTABLISH  # both conditions now met -- transitions


def test_cell_search_timer_expiry_falls_back_to_idle_then_rrc_establish():
    config = JoinConfig(cell_search_ceiling_ms=1.0)  # tiny ceiling -- expires almost immediately
    state = init_join_state(config)
    rngs = _rngs()
    step(state, config, rngs, 0, SLOT_DURATION_S, rlf_declared_this_slot=True, snr_db=-20.0)
    assert state.phase is JoinPhase.CELL_SEARCH

    expired_at = None
    for i in range(1, 30):
        r = step(state, config, rngs, i, SLOT_DURATION_S, snr_db=-20.0)  # SNR never restores
        if r.timer_expired_this_slot:
            expired_at = i
            break
    assert expired_at is not None
    assert state.phase is JoinPhase.IDLE
    assert state.timer_expiry_counts["cell_search"] == 1

    # IDLE is a single-slot transit straight into RRC_ESTABLISH.
    step(state, config, rngs, expired_at + 1, SLOT_DURATION_S)
    assert state.phase is JoinPhase.RRC_ESTABLISH
    assert state.app_running is True  # post-RLF fallback keeps the app alive throughout


def test_reestablish_success_reconnects_radio_and_keeps_app_running():
    config = JoinConfig(
        # cell_search_ceiling_ms=0.0 makes the sampled cell-search delay
        # deterministic at 0 slots (floor==ceiling, see _sample_deadline_
        # slots), so the transition to REESTABLISH fires the instant SNR
        # restores -- isolating this test from the exponential draw.
        cell_search_ceiling_ms=0.0,
        cell_search_good_snr_slots=1,
        reestablish_floor_ms=1.0,
        reestablish_ceiling_ms=100.0,
    )
    state = init_join_state(config)
    rngs = _rngs()
    step(state, config, rngs, 0, SLOT_DURATION_S, rlf_declared_this_slot=True, snr_db=-20.0)
    r = step(state, config, rngs, 1, SLOT_DURATION_S, snr_db=10.0)  # SNR restored, 1 slot suffices
    assert state.phase is JoinPhase.REESTABLISH

    radio_edges = []
    for i in range(2, 60):
        result = step(state, config, rngs, i, SLOT_DURATION_S, snr_db=10.0)
        radio_edges.append(result.radio_connected_this_slot)
        if state.phase is JoinPhase.APP_HANDSHAKE:
            break
    assert state.phase is JoinPhase.APP_HANDSHAKE
    assert sum(radio_edges) == 1  # exactly one radio-reconnect edge, at REESTABLISH -> APP_HANDSHAKE
    assert state.app_running is True  # never dropped for this path

    r_final = step(state, config, rngs, 100, SLOT_DURATION_S, handshake_complete=True)
    assert state.phase is JoinPhase.CONNECTED
    assert not r_final.app_connected_this_slot  # app_running was already True -- no edge


def test_reestablish_timer_expiry_falls_back_to_idle():
    config = JoinConfig(
        cell_search_ceiling_ms=0.0,  # deterministic -- see test above
        cell_search_good_snr_slots=1,
        reestablish_ceiling_ms=1.0,
    )
    state = init_join_state(config)
    rngs = _rngs()
    step(state, config, rngs, 0, SLOT_DURATION_S, rlf_declared_this_slot=True, snr_db=-20.0)
    step(state, config, rngs, 1, SLOT_DURATION_S, snr_db=10.0)
    assert state.phase is JoinPhase.REESTABLISH

    for i in range(2, 30):
        r = step(state, config, rngs, i, SLOT_DURATION_S, snr_db=10.0)
        if r.timer_expired_this_slot:
            break
    assert state.phase is JoinPhase.IDLE
    assert state.timer_expiry_counts["reestablish"] == 1


# -- events landing during a phase that doesn't act on them -----------------


def test_event_during_an_unrelated_phase_is_consumed_but_has_no_effect():
    config = JoinConfig(
        events=(JoinEvent(2, "power_on"),),  # POWERED_OFF-only event, but we start CONNECTED
        cell_search_ceiling_ms=100.0,
    )
    state = init_join_state(config)
    rngs = _rngs()
    step(state, config, rngs, 0, SLOT_DURATION_S)
    step(state, config, rngs, 1, SLOT_DURATION_S)
    step(state, config, rngs, 2, SLOT_DURATION_S)  # event consumed, no branch reads it here
    assert state.phase is JoinPhase.CONNECTED
    assert state.next_event_index == 1
