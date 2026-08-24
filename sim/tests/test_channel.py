"""WP6 commit 1: ChannelModel's opt-in wiring to sim/pathloss.py
(docs/wp6-plan.md Decision 2). A UE without ``position`` set must behave
byte-for-byte as before this commit -- this is the falsifiable-inertness
claim scripts/regression_corpus.py --check exercises across the existing
22-record corpus (no scenario sets ``position`` yet)."""

import numpy as np

from sim.channel import ChannelModel
from sim.config import UEConfig


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
