"""WP-Join commit 3: the concrete GT-6.3 fade-duration boundary, per
docs/wp-join-plan.md D6/sec6 flag 2 ("raise with the test-plan owner
separately from this WP's build") -- that flag needed a NUMBER, not just
the qualitative observation that the literal 10s scripted fade outlasts
t310+t311. This module computes and locks down that number.

Composes sim.channel's new scripted fade (commit 3) with sim.rlf::step()
(WP6, unmodified) and sim.join::step() (commit 1, unmodified) directly --
none of these three are wired together in sim/driver.py yet (that is
commit 5's job), but all three are already pure/importable, so the
boundary is characterisable now rather than waiting for that wiring.
"""

import numpy as np
import pytest

from sim.channel import ChannelModel
from sim.config import ScriptedFadeWindow, UEConfig
from sim.join import JoinConfig, JoinPhase, init_join_rng_streams, init_join_state
from sim.join import step as join_step
from sim.rlf import RlfDetectorConfig, RlfDetectorState, t310_slots
from sim.rlf import step as rlf_step

SLOT_DURATION_S = 0.0005  # 0.5ms/slot, numerology mu=1 -- this deployment's default
MEAN_SNR_DB = 20.0  # this deployment's typical corpus baseline (scripts/scheduler_study.py)

# The depth a scenario author needs: mean_snr_db - floor(-5.0) = 25dB to
# cross at all; 30dB gives a clean 5dB margin. General form, so a
# different mean_snr_db needs (mean_snr_db - rlf_snr_floor_db) + margin.
FADE_DEPTH_DB = 30.0

# n310_slots + t310_slots + cell_search_ceiling_slots, all at this
# deployment's defaults (RlfDetectorConfig()/JoinConfig() -- calibration-
# logs/twotier_startup_gnb.log:17). Computed once here, asserted against
# below rather than hand-copied, so this file can't silently drift from
# the modules it's characterising.
_RLF_CONFIG = RlfDetectorConfig()
_JOIN_CONFIG = JoinConfig()
_N310_SLOTS = _RLF_CONFIG.n310
_T310_SLOTS = t310_slots(_RLF_CONFIG, SLOT_DURATION_S)
_CELL_SEARCH_CEILING_SLOTS = round(_JOIN_CONFIG.cell_search_ceiling_ms / (SLOT_DURATION_S * 1000.0))
BOUNDARY_SLOTS = _N310_SLOTS + _T310_SLOTS + _CELL_SEARCH_CEILING_SLOTS


def _run_until_outcome(fade_duration_slots: int, horizon: int = 30_000):
    """Drives sim.channel's scripted fade -> sim.rlf.step() -> sim.join.step()
    for one UE, fade active over [0, fade_duration_slots), and returns
    ("REESTABLISH" | "IDLE" | "NEITHER", rlf_declared_at_slot | None)."""
    ue = UEConfig(
        ue_id=1, mean_snr_db=MEAN_SNR_DB,
        scripted_fade=(ScriptedFadeWindow(start_slot=0, end_slot=fade_duration_slots, extra_loss_db=FADE_DEPTH_DB),),
    )
    channel = ChannelModel([ue], np.random.default_rng(0), stationary_std_db=0.0)
    rlf_state = RlfDetectorState()
    join_state = init_join_state(_JOIN_CONFIG)
    rngs = init_join_rng_streams(1)
    rlf_declared_at = None

    for slot in range(horizon):
        channel.update(slot)
        rres = rlf_step(rlf_state, _RLF_CONFIG, channel.get_snr_db(1), slot, SLOT_DURATION_S)
        if rres.rlf_declared_this_slot:
            rlf_declared_at = slot
        jres = join_step(
            join_state, _JOIN_CONFIG, rngs, slot, SLOT_DURATION_S,
            rlf_declared_this_slot=rres.rlf_declared_this_slot,
            snr_db=channel.get_snr_db(1),
        )
        if jres.phase_changed and join_state.phase in (JoinPhase.REESTABLISH, JoinPhase.APP_HANDSHAKE):
            return "REESTABLISH", rlf_declared_at
        if jres.phase_changed and join_state.phase is JoinPhase.IDLE:
            return "IDLE", rlf_declared_at
    return "NEITHER", rlf_declared_at


def test_fade_depth_30db_crosses_the_rlf_floor_with_margin():
    assert MEAN_SNR_DB - FADE_DEPTH_DB < _RLF_CONFIG.rlf_snr_floor_db - 4.0


def test_boundary_formula_matches_the_deployed_timer_values():
    # calibration-logs/twotier_startup_gnb.log:17: n310=10, t310=2000ms;
    # JoinConfig default cell_search_ceiling_ms=3000ms (t311).
    assert _N310_SLOTS == 10
    assert _T310_SLOTS == 4000
    assert _CELL_SEARCH_CEILING_SLOTS == 6000
    assert BOUNDARY_SLOTS == 10_010  # 5.005s at 0.5ms/slot


def test_fade_duration_at_the_boundary_still_reaches_reestablishment():
    outcome, declared_at = _run_until_outcome(BOUNDARY_SLOTS - 1)  # 10,009 slots = 5.0045s
    assert outcome == "REESTABLISH"
    assert declared_at == _N310_SLOTS - 1 + _T310_SLOTS  # slot 4009


def test_fade_duration_one_slot_past_the_boundary_falls_back_to_idle():
    outcome, declared_at = _run_until_outcome(BOUNDARY_SLOTS)  # 10,010 slots = 5.005s
    assert outcome == "IDLE"
    assert declared_at == _N310_SLOTS - 1 + _T310_SLOTS  # RLF declares at the same instant either way


@pytest.mark.parametrize("fade_duration_slots", [1, 100, 4000])
def test_fades_shorter_than_n310_plus_t310_never_declare_rlf_at_all(fade_duration_slots):
    """A second concrete number, not in the original finding: a fade
    shorter than n310+t310 (=4010 slots=2.005s) never declares RLF at
    all, regardless of depth -- n311=1 (default) cancels T310_RUNNING on
    the very first good slot once the fade ends, before t310's 4000-slot
    dwell can complete. Below this floor, "how deep" and "how long" are
    moot -- the detector never even arms long enough to fire."""
    outcome, declared_at = _run_until_outcome(fade_duration_slots, horizon=5_000)
    assert declared_at is None
    assert outcome == "NEITHER"


@pytest.mark.parametrize("fade_duration_slots", [4200, 5000, 8000])
def test_fades_between_the_two_floors_reach_reestablishment(fade_duration_slots):
    """Sanity check across the middle of the range -- strictly longer than
    n310+t310 (so RLF actually declares) and strictly shorter than the
    boundary (so cell search completes within t311). The boundary test
    above pins the exact crossover; this confirms nothing flips back and
    forth for fades well clear of it on either side."""
    outcome, declared_at = _run_until_outcome(fade_duration_slots)
    assert declared_at == _N310_SLOTS - 1 + _T310_SLOTS  # slot 4009, same for all of these
    assert outcome == "REESTABLISH"
