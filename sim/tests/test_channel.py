"""WP6 commits 1-2: ChannelModel's opt-in wiring to sim/pathloss.py
(docs/wp6-plan.md Decision 2) and sim/blockage.py (Decision 3). A UE
without ``position``/``blockage`` set must behave byte-for-byte as before
these commits -- this is the falsifiable-inertness claim scripts/
regression_corpus.py --check exercises across the existing 22-record
corpus (no scenario sets either field yet)."""

import numpy as np
import pytest

from sim.channel import ChannelModel
from sim.config import BlockageConfig, UEConfig


def test_ue_without_position_keeps_authored_mean_snr_db():
    ue = UEConfig(ue_id=1, mean_snr_db=12.5)
    channel = ChannelModel([ue], np.random.default_rng(0))
    assert channel.mean_snr_db[1] == 12.5
    assert channel.get_snr_db(1) == 12.5


def test_ue_with_position_ignores_authored_mean_snr_db():
    ue = UEConfig(
        ue_id=1,
        mean_snr_db=12.5,  # must be ignored once position is set
        position=(10.0, 0.0, 1.5),
        inf_scenario="SL",
    )
    channel = ChannelModel(
        [ue],
        np.random.default_rng(0),
        gnb_position=(0.0, 0.0, 1.5),
        center_freq_ghz=3.5,
        bandwidth_hz=30_000_000,
        los_seed=1,
        shadow_fading_seed=2,
    )
    assert channel.mean_snr_db[1] != 12.5


def test_position_derived_mean_snr_db_is_deterministic_given_seeds():
    def build():
        ue = UEConfig(ue_id=1, position=(10.0, 0.0, 1.5), inf_scenario="SL")
        return ChannelModel(
            [ue],
            np.random.default_rng(0),
            gnb_position=(0.0, 0.0, 1.5),
            center_freq_ghz=3.5,
            bandwidth_hz=30_000_000,
            los_seed=7,
            shadow_fading_seed=9,
        ).mean_snr_db[1]

    assert build() == build()


def test_farther_ue_gets_lower_position_derived_mean_snr_db():
    """Sanity on direction, not a specific spec value: more path loss at
    greater distance should mean lower SNR -- averaged over many shadow-
    fading/LOS draws so a single unlucky draw can't flip the comparison."""
    def mean_snr_over_seeds(distance_m: int) -> float:
        values = []
        for seed in range(30):
            ue = UEConfig(
                ue_id=1, position=(float(distance_m), 0.0, 1.5), inf_scenario="SH"
            )
            channel = ChannelModel(
                [ue],
                np.random.default_rng(0),
                gnb_position=(0.0, 0.0, 8.0),
                center_freq_ghz=3.5,
                bandwidth_hz=30_000_000,
                los_seed=seed,
                shadow_fading_seed=seed + 1000,
            )
            values.append(channel.mean_snr_db[1])
        return sum(values) / len(values)

    near = mean_snr_over_seeds(10)
    far = mean_snr_over_seeds(200)
    assert far < near


def test_los_and_shadow_fading_draws_use_independent_seeds():
    """docs/wp6-plan.md Decision 2: LOS realization and shadow fading are
    two new independent random draws -- changing one seed while holding
    the other fixed should (almost always) change the result, confirming
    they aren't silently sharing one stream. Uses InF-SL at a distance
    where Pr_LOS is comfortably mid-range (~0.37, not near 0 or 1), so a
    changed los_seed has a real chance of flipping the LOS/NLOS draw
    instead of every seed landing in the same all-but-certain outcome."""
    def build(los_seed, sf_seed):
        ue = UEConfig(ue_id=1, position=(45.0, 0.0, 1.5), inf_scenario="SL")
        return ChannelModel(
            [ue],
            np.random.default_rng(0),
            gnb_position=(0.0, 0.0, 1.5),
            center_freq_ghz=3.5,
            bandwidth_hz=30_000_000,
            los_seed=los_seed,
            shadow_fading_seed=sf_seed,
        ).mean_snr_db[1]

    baseline = build(1, 1)
    changed_los = [build(s, 1) for s in range(2, 12)]
    changed_sf = [build(1, s) for s in range(2, 12)]
    assert any(v != baseline for v in changed_los)
    assert any(v != baseline for v in changed_sf)


# -- WP6 commit 2: two-state Markov blockage -----------------------------


def test_ue_without_blockage_is_never_blocked():
    ue = UEConfig(ue_id=1, mean_snr_db=20.0)
    channel = ChannelModel([ue], np.random.default_rng(0))
    for slot in range(50):
        channel.update(slot)
        assert channel.is_blocked(1) is False
    assert channel.get_snr_db(1) != pytest.approx(20.0 - 17.5)


def test_ue_with_blockage_drops_mean_snr_while_blocked():
    """Force the UE into the Blocked state (p_leave_unblocked=1.0 makes it
    block on the very first update) and check the AR(1) process converges
    to a mean genuinely shifted down by blocked_extra_loss_db -- not just
    that is_blocked() reports True. The AR(1) recurrence only approaches
    its mean geometrically (rate ``alpha`` per slot, sim/channel.py's own
    documented form), so this runs enough slots for that to converge
    rather than checking the very first one."""
    ue = UEConfig(
        ue_id=1,
        mean_snr_db=20.0,
        coherence_slots=1,  # alpha = exp(-1) ~= 0.37/slot
        blockage=BlockageConfig(
            mean_unblocked_slots=1, mean_blocked_slots=1_000_000, blocked_extra_loss_db=17.5
        ),
    )
    channel = ChannelModel([ue], np.random.default_rng(0), stationary_std_db=0.0)
    for slot in range(50):  # alpha**50 ~= 0: converged well within float tolerance
        channel.update(slot)
    assert channel.is_blocked(1) is True
    assert channel.get_snr_db(1) == pytest.approx(20.0 - 17.5)


@pytest.mark.parametrize(
    "mean_blocked_slots,mean_unblocked_slots,n_slots",
    [
        # "Short" -- shorter than even the UL HARQ retry cycle (~4ms = 8
        # slots at mu=1, k2_slots=2, harq_round_max=4, sim/driver.py
        # defaults) -- docs/wp6-plan.md sec 4's falsifiability requirement
        # for commit 4: the parameterisation must support this regime just
        # as well as "hundreds of milliseconds", not only the latter.
        (4, 8, 20_000),
        # "Long" -- this module's own default, an order-of-magnitude
        # anchor to p5g-sim-plan.md's "hundreds of milliseconds" (600
        # slots = 300ms at 0.5ms/slot) -- WP6's own acceptance criterion
        # regime.
        (600, 4000, 400_000),
    ],
)
def test_blockage_dwell_matches_configured_mean_at_both_short_and_long_settings(
    mean_blocked_slots, mean_unblocked_slots, n_slots
):
    """Empirical check, per the sign-off's explicit ask: confirm the same
    Markov construction reproduces its configured mean dwell whether that
    mean is short (below a HARQ retry cycle) or long (hundreds-of-ms-
    equivalent) -- nothing here is structurally biased toward one regime.
    Geometric dwell times are high-variance, so this checks the empirical
    mean against a generous (35%) relative tolerance over many cycles,
    not an exact match."""
    ue = UEConfig(
        ue_id=1,
        blockage=BlockageConfig(
            mean_unblocked_slots=mean_unblocked_slots,
            mean_blocked_slots=mean_blocked_slots,
            blocked_extra_loss_db=17.5,
        ),
    )
    channel = ChannelModel([ue], np.random.default_rng(0), blockage_seed=123)
    history = []
    for slot in range(n_slots):
        channel.update(slot)
        history.append(channel.is_blocked(1))

    blocked_runs = []
    unblocked_runs = []
    run_len = 1
    for i in range(1, len(history)):
        if history[i] == history[i - 1]:
            run_len += 1
        else:
            (blocked_runs if history[i - 1] else unblocked_runs).append(run_len)
            run_len = 1
    (blocked_runs if history[-1] else unblocked_runs).append(run_len)

    assert len(blocked_runs) >= 10, "not enough blocked runs to estimate a mean from"
    empirical_blocked_mean = sum(blocked_runs) / len(blocked_runs)
    empirical_unblocked_mean = sum(unblocked_runs) / len(unblocked_runs)
    assert empirical_blocked_mean == pytest.approx(mean_blocked_slots, rel=0.35)
    assert empirical_unblocked_mean == pytest.approx(mean_unblocked_slots, rel=0.35)


def test_blockage_transitions_use_their_own_independent_rng_stream():
    """docs/wp6-plan.md Decision 3 / CLAUDE.md's seed-isolation rule:
    changing blockage_seed alone (holding every other seed fixed) must
    change the blockage trajectory -- confirming it isn't silently
    sharing the AR(1)/CQI/LOS/shadow-fading streams."""
    def blocked_slots(blockage_seed):
        ue = UEConfig(
            ue_id=1,
            blockage=BlockageConfig(
                mean_unblocked_slots=5, mean_blocked_slots=5, blocked_extra_loss_db=17.5
            ),
        )
        channel = ChannelModel([ue], np.random.default_rng(0), blockage_seed=blockage_seed)
        count = 0
        for slot in range(200):
            channel.update(slot)
            count += channel.is_blocked(1)
        return count

    baseline = blocked_slots(1)
    others = [blocked_slots(s) for s in range(2, 8)]
    assert any(v != baseline for v in others)
