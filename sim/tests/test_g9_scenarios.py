"""G9's three join scenarios (docs/wp9-plan.md §31, commit 2).

The load-bearing test here is `validate_handshake_wiring`. `JoinConfig`
cannot check its own `handshake_ul_qfi`/`handshake_dl_qfi` because it never
sees the flow list, and a wrong or absent QFI does NOT raise -- the
handshake simply never completes, M18 reports `n_never_completed = 100%`
and every latency reads `None`. A throwaway probe hit exactly that (§31.3),
and it reads as a scheduler result rather than a scenario bug.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.config import FlowConfig, UEConfig  # noqa: E402
from sim.join import JoinConfig  # noqa: E402
from sim.scenarios.g9 import (QFI_HANDSHAKE_DL, QFI_HANDSHAKE_UL,  # noqa: E402
                              gt61_warm_rejoin, gt62_cold_attach,
                              gt63_rlf_recovery, joiner_ue_id,
                              neighbour_ue_ids, validate_handshake_wiring)

BUILDERS = (gt61_warm_rejoin, gt62_cold_attach, gt63_rlf_recovery)


@pytest.mark.parametrize("build", BUILDERS)
def test_every_builder_validates_its_own_handshake_wiring(build):
    """Each builder calls the validator before returning, so a scenario
    that would silently produce all-None M18 latencies cannot escape."""
    validate_handshake_wiring(build())


@pytest.mark.parametrize("build", BUILDERS)
def test_exactly_one_joiner_and_the_rest_are_neighbours(build):
    sc = build(n_neighbours=4)
    assert joiner_ue_id(sc) == 1
    assert neighbour_ue_ids(sc) == [2, 3, 4, 5]
    assert len(sc.ues) == 5


@pytest.mark.parametrize("build", BUILDERS)
def test_the_joiner_is_excluded_from_its_own_neighbour_set(build):
    """§31.6: a neighbours statistic that includes the recovering UE is
    measuring the event, not the containment."""
    sc = build()
    assert joiner_ue_id(sc) not in neighbour_ue_ids(sc)


def test_handshake_qfis_are_distinct_from_every_traffic_flow():
    """JoinConfig's own contract: the pair must be distinct from every
    other flow's qfi on that UE."""
    sc = gt61_warm_rejoin()
    j = joiner_ue_id(sc)
    traffic = [f.qfi for f in sc.flows
               if f.ue_id == j and f.qfi not in (QFI_HANDSHAKE_UL, QFI_HANDSHAKE_DL)]
    assert QFI_HANDSHAKE_UL not in traffic
    assert QFI_HANDSHAKE_DL not in traffic


# -- the validator's own failure modes ------------------------------------

def _one_ue(**join_kwargs):
    from sim.config import CarrierConfig, ScenarioConfig, TDDConfig
    flows = [FlowConfig(ue_id=1, qfi=QFI_HANDSHAKE_UL, direction="UL",
                        flow_class="Delay", pdb_ms=100.0),
             FlowConfig(ue_id=1, qfi=QFI_HANDSHAKE_DL, direction="DL",
                        flow_class="Delay", pdb_ms=100.0)]
    return ScenarioConfig(
        name="t", horizon_slots=100, carrier=CarrierConfig(), tdd=TDDConfig(),
        ues=[UEConfig(ue_id=1, join=JoinConfig(**join_kwargs))], flows=flows)


def test_validator_rejects_BOTH_handshake_qfis_unset():
    """THE PROBE'S EXACT DEFECT (§31.3). `JoinConfig.__post_init__` already
    rejects a HALF-set pair ("must be set together, or neither"), so the
    reachable failure is both unset -- which JoinConfig allows BY DESIGN,
    since it is the pre-WP-Join-commit-6 default. Nothing raises, the
    handshake never completes, and M18 reports every latency as None."""
    with pytest.raises(ValueError, match="handshake_ul_qfi is None"):
        validate_handshake_wiring(_one_ue())


def test_joinconfig_itself_rejects_a_half_set_pair():
    """Recorded because it narrows what the validator above is FOR: the
    half-set case is already covered upstream, so the validator's job is
    the both-unset case and the direction/existence checks JoinConfig
    structurally cannot make."""
    with pytest.raises(ValueError, match="must be set together"):
        JoinConfig(handshake_dl_qfi=QFI_HANDSHAKE_DL)


def test_validator_rejects_a_qfi_with_no_matching_flow():
    with pytest.raises(ValueError, match="names no flow"):
        validate_handshake_wiring(_one_ue(handshake_ul_qfi=999,
                                          handshake_dl_qfi=QFI_HANDSHAKE_DL))


def test_validator_rejects_a_direction_mismatch():
    """UL and DL swapped -- both QFIs exist, so only a direction check
    catches it."""
    with pytest.raises(ValueError, match="must be UL"):
        validate_handshake_wiring(_one_ue(handshake_ul_qfi=QFI_HANDSHAKE_DL,
                                          handshake_dl_qfi=QFI_HANDSHAKE_UL))


# -- event schedules ------------------------------------------------------

def test_warm_schedules_one_restart_per_cycle():
    """p95 over cycles needs cycles: one event gives no percentile."""
    sc = gt61_warm_rejoin(n_cycles=10)
    ev = sc.ues[0].join.events
    assert len(ev) == 10
    assert {e.kind for e in ev} == {"app_restart"}


def test_cold_schedules_a_power_cycle_PAIR_per_cycle():
    sc = gt62_cold_attach(n_cycles=5)
    ev = sc.ues[0].join.events
    assert len(ev) == 10, "each cycle is an off/on PAIR"
    assert [e.kind for e in ev[:2]] == ["power_off", "power_on"]


def test_rlf_scenario_scripts_a_FADE_and_no_join_events():
    """RLF is emergent from sim/rlf.py observing the SNR trace, never
    scripted as a JoinEvent (JoinEvent's own docstring)."""
    sc = gt63_rlf_recovery()
    assert sc.ues[0].join.events == ()
    assert len(sc.ues[0].scripted_fade) == 1


def test_rlf_fade_is_deep_enough_to_cross_the_rlf_floor():
    """A shallower fade produces no RLF at all, making GT-6.3 a slow-link
    test rather than a recovery one."""
    sc = gt63_rlf_recovery()
    fade = sc.ues[0].scripted_fade[0]
    faded_snr = sc.ues[0].mean_snr_db - fade.extra_loss_db
    assert faded_snr < sc.ues[0].join.rlf_snr_floor_db, (
        f"faded SNR {faded_snr} must be below rlf_snr_floor_db "
        f"{sc.ues[0].join.rlf_snr_floor_db}")


def test_neighbours_carry_no_join_config():
    for build in BUILDERS:
        sc = build()
        for ue in sc.ues:
            if ue.ue_id != joiner_ue_id(sc):
                assert ue.join is None


def test_rlf_fade_must_outlast_t310_or_no_event_ever_fires():
    """THE DEFECT THIS PINS. t310 is 2,000 ms = 8,000 slots at numerology 2,
    and the driver builds `RlfDetectorConfig()` with that default. The first
    version of `gt63_rlf_recovery` used a 4,000-slot fade -- half the dwell
    -- so t310 re-armed and the scenario produced ZERO RLF events. Zero
    events reads as "recovery was instant", not as "the scenario never
    fired", which is why depth alone is not enough: depth ARMS t310,
    duration EXPIRES it."""
    from sim.scenarios.g9 import T310_SLOTS_MU2
    sc = gt63_rlf_recovery()
    fade = sc.ues[0].scripted_fade[0]
    fade_len = fade.end_slot - fade.start_slot
    assert fade_len > T310_SLOTS_MU2, (
        f"fade is {fade_len} slots, t310 is {T310_SLOTS_MU2} -- RLF cannot "
        f"be declared and the scenario will silently produce no events")
    assert sc.horizon_slots > fade.end_slot, "no room for recovery after the fade"
