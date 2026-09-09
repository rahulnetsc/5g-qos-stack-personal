"""GT-1.1's cell: the properties the experiment depends on.

Every one of these is a thing that would silently invalidate G1's result
rather than crash it, which is why they are pinned here rather than left to
the runner's own asserts.
"""
from __future__ import annotations

import collections

import pytest

from sim.scenarios.g1 import (CMD_GFBR_BPS, N_DRIVEN, QFI_CMD, QFI_FIRMWARE_DL,
                              assert_cmd_instrument_live, build_gt11_scenario,
                              cmd_flow_keys)


def test_the_instrument_is_a_5qi_1_downlink_gbr_flow():
    """G1's clause names a DOWNLINK command on 5QI 1, and TwoTier's DL
    `has_gbr` tier is dead without a GBR target -- measured, not assumed
    (docs/g1-step0-2026-09-09.md (c))."""
    sc = build_gt11_scenario(seed=1, n_ues=8, horizon_slots=2000)
    cmds = [f for f in sc.flows if f.qfi == QFI_CMD and f.direction == "DL"]
    assert len(cmds) == N_DRIVEN
    for f in cmds:
        assert f.flow_class == "GBR" and f.gfbr_bps == CMD_GFBR_BPS
        assert f.pdb_ms == 100.0, "5QI 1's standardised PDB, derived not authored"
        assert f.priority_level == 20, "5QI 1's standardised priority"
    assert_cmd_instrument_live(sc)


def test_the_downlink_is_actually_loaded():
    """GT-1.1's own text: an idle DL link measures nothing."""
    sc = build_gt11_scenario(seed=1, n_ues=8, horizon_slots=2000)
    pulls = [f for f in sc.flows
             if f.qfi == QFI_FIRMWARE_DL and f.direction == "DL"]
    assert len(pulls) == 1
    assert pulls[0].traffic_params["rate_bps"] >= 50_000_000.0
    with pytest.raises(ValueError):
        build_gt11_scenario(seed=1, n_ues=8, firmware_pull_bps=0.0)


@pytest.mark.parametrize("n_ues", [4, 8, 16])
def test_committed_mult_scales_the_fleet_and_never_the_instrument(n_ues):
    """A robot asked to do more work does not receive more drive commands.
    If the load axis moved the instrument, the quantity G1 measures would
    change along its own axis."""
    a = build_gt11_scenario(seed=1, n_ues=n_ues, horizon_slots=2000)
    b = build_gt11_scenario(seed=1, n_ues=n_ues, horizon_slots=2000,
                            committed_mult=2.0)

    def cmd(sc):
        return [f for f in sc.flows if f.qfi == QFI_CMD and f.direction == "DL"]

    for x, y in zip(cmd(a), cmd(b)):
        assert x.gfbr_bps == y.gfbr_bps
        assert x.traffic_params == y.traffic_params

    def camera(sc):
        return [f for f in sc.flows if f.qfi == 2][0]

    assert camera(b).gfbr_bps == pytest.approx(2 * camera(a).gfbr_bps)
    assert camera(b).traffic_params["avg_bytes"] == pytest.approx(
        2 * camera(a).traffic_params["avg_bytes"])


@pytest.mark.parametrize("n_ues", [4, 8, 16, 24])
def test_the_instrument_population_does_not_grow_with_the_fleet(n_ues):
    """Otherwise "worst cmd_vel p98" is a worst-of-N order statistic and the
    UE axis moves the statistic as well as the load."""
    sc = build_gt11_scenario(seed=1, n_ues=n_ues, horizon_slots=2000)
    assert len(cmd_flow_keys(sc)) == N_DRIVEN


@pytest.mark.parametrize("n_ues,cm", [(4, 1.0), (8, 2.0), (16, 0.5)])
def test_no_ue_carries_one_5qi_in_both_directions(n_ues, cm):
    """Defects log #28/#30: `BufferModel` keys on (ue_id, qfi) with no
    direction. This cell deliberately puts 5QI 1 and 5QI 9 on DOWNLINK while
    the fleet holds both on uplink, so it is exactly that shape."""
    sc = build_gt11_scenario(seed=1, n_ues=n_ues, committed_mult=cm,
                             horizon_slots=2000)
    dup = {k: v for k, v in
           collections.Counter((f.ue_id, f.qfi) for f in sc.flows).items() if v > 1}
    assert not dup, dup


def test_n_ues_must_leave_at_least_one_asset_b():
    for bad in (0, 1, 2):
        with pytest.raises(ValueError):
            build_gt11_scenario(seed=1, n_ues=bad, horizon_slots=2000)


def test_cmd_flow_keys_is_derived_not_restated():
    """A restated set is this project's most-repeated defect; `n_driven` is a
    parameter, so the key list must follow it."""
    sc = build_gt11_scenario(seed=1, n_ues=8, n_driven=3, horizon_slots=2000)
    assert cmd_flow_keys(sc) == ["ue1_qfi1", "ue2_qfi1", "ue3_qfi1"]
    with pytest.raises(AssertionError):
        assert_cmd_instrument_live(sc, n_driven=2)
