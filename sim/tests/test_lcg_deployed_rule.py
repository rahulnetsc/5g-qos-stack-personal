"""M-5: LCG = DRB ID, the deployed rule (docs/builds-2026-09-08.md §1).

Three things this file pins, each learned by getting the shape wrong before:

- the rule itself, transcribed from the C rather than reasoned about;
- that resolution happens ONCE, at ScenarioConfig, and every consumer that
  indexes a per-LCG array refuses an unresolved flow (a manipulation check:
  the guard demonstrably fires);
- a census over EVERY builder -- coverage inherited from the flow-key
  sweep's own coverage test, not restated here -- that no built scenario
  puts data on LCG 0 or shares an LCG between two data flows.
"""
from __future__ import annotations

import dataclasses
from collections import Counter

import pytest

from scheduler.flow import (
    LCG_MAX_DRB, LCG_SRB, LCG_UNASSIGNED, FlowConfig, assign_deployed_lcgs,
    lcg_for_drb,
)
from sim.config import ScenarioConfig
from sim.tests.test_flow_key_collision_sweep import _cases


def _ul(ue, qfi, **kw):
    return FlowConfig(ue_id=ue, qfi=qfi, direction="UL", **kw)


def test_the_rule_is_the_c_s_rule():
    """rrc_gNB_radio_bearers.c:248-263 (lowest free ID from 1), :498-505 (one
    flow per DRB), nr_radio_config.c:3781-3785 (LCG = DRB ID, cap 7)."""
    flows = [_ul(1, 9), _ul(1, 2), FlowConfig(ue_id=1, qfi=3, direction="DL"),
             _ul(1, 4), _ul(2, 9)]
    assign_deployed_lcgs(flows)
    assert [f.lcg for f in flows] == [1, 2, 3, 4, 1]
    assert lcg_for_drb(7) == 7 and lcg_for_drb(8) == 7 and lcg_for_drb(30) == LCG_MAX_DRB
    with pytest.raises(ValueError):
        lcg_for_drb(0)          # DRB IDs start at 1; 0 is the SRB group


def test_a_bidirectional_flow_is_one_drb():
    flows = [FlowConfig(ue_id=1, qfi=5, direction="DL"), _ul(1, 5), _ul(1, 9)]
    assign_deployed_lcgs(flows)
    assert [f.lcg for f in flows] == [1, 1, 2]


def test_an_explicit_override_wins_but_still_consumes_a_drb():
    """The deployed RRC creates a DRB for every flow whatever the simulator
    labels it, so an override does not shift its neighbours' ordinals."""
    flows = [_ul(1, 1), _ul(1, 2, lcg=1), _ul(1, 9)]
    assign_deployed_lcgs(flows)
    assert [f.lcg for f in flows] == [1, 1, 3]


def test_lcg_zero_is_never_assigned():
    flows = [_ul(1, q) for q in range(1, 12)]
    assign_deployed_lcgs(flows)
    assert LCG_SRB not in {f.lcg for f in flows}
    assert [f.lcg for f in flows] == [1, 2, 3, 4, 5, 6, 7, 7, 7, 7, 7]


def test_resolution_is_idempotent_and_survives_replace_and_permutation():
    """ScenarioConfig is the one resolution point; dataclasses.replace and
    G12's permute_flows re-run __post_init__ on already-resolved flows and
    must not re-derive -- otherwise the permutation control would silently
    become an LCG-assignment control."""
    from sim.scenarios.g12 import build_g12_scenario, permute_flows
    sc = build_g12_scenario(8, "mixed", 1.0, 1, horizon_slots=2000)
    before = {(f.ue_id, f.qfi): f.lcg for f in sc.flows}
    assert LCG_UNASSIGNED not in before.values()
    for seed in (1, 2, 3):
        after = {(f.ue_id, f.qfi): f.lcg for f in permute_flows(sc, seed).flows}
        assert after == before
    assert {(f.ue_id, f.qfi): f.lcg
            for f in dataclasses.replace(sc, seed=99).flows} == before


def test_g11_rotation_control_does_not_move_lcgs():
    from sim.scenarios.g11 import build_g11_scenario
    base = build_g11_scenario(seed=1, n_ues=4, horizon_slots=2000,
                              allow_partial_schedule=True)
    ref = {(f.ue_id, f.qfi): f.lcg for f in base.flows}
    for k in (1, 3, 5, 7):
        rot = build_g11_scenario(seed=1, n_ues=4, horizon_slots=2000,
                                 permutation=k, allow_partial_schedule=True)
        assert {(f.ue_id, f.qfi): f.lcg for f in rot.flows} == ref, k


# --- the guard fires: manipulation check -----------------------------------

def _unassigned():
    return [_ul(1, 9), _ul(2, 9)]


def test_every_lcg_indexing_consumer_refuses_an_unassigned_flow():
    """Python indexes [-1] as [7] without complaint, so the refusal has to be
    explicit -- and it has to be demonstrated, not assumed, in EVERY consumer
    that reads f.lcg (the standing who-else-reads-this-state question)."""
    from scheduler.reservation import Reservation
    from scheduler.two_tier import TwoTier
    from sim.bsr import BsrModel
    from sim.traffic import TrafficModel

    with pytest.raises(ValueError, match="no LCG"):
        BsrModel(_unassigned(), slot_duration_s=0.0005)
    with pytest.raises(ValueError, match="no LCG"):
        Reservation().configure(_unassigned(), slot_duration_s=0.0005, grid=None)
    with pytest.raises(ValueError, match="no LCG"):
        TwoTier().configure(_unassigned(), slot_duration_s=0.0005, grid=None)
    with pytest.raises(ValueError, match="no LCG"):
        TrafficModel(_unassigned(), None, 0.0005, None)


def test_scenarioconfig_is_where_resolution_happens():
    flows = _unassigned()
    assert all(f.lcg == LCG_UNASSIGNED for f in flows)
    sc = ScenarioConfig(name="t", horizon_slots=10, flows=flows)
    assert [f.lcg for f in sc.flows] == [1, 1]


# --- census over every builder ---------------------------------------------

_CASES = _cases()


@pytest.mark.parametrize("label,sc", _CASES, ids=[c[0] for c in _CASES])
def test_no_built_scenario_puts_data_on_lcg0_or_shares_an_lcg(label, sc):
    """Count, not just existence: every flow assigned, per-UE LCG set is
    exactly {lcg_for_drb(1..k)} -- so a saturated or empty selection cannot
    read as a pass."""
    flows = list(sc.flows)
    assert flows, label
    assert sum(f.lcg != LCG_UNASSIGNED for f in flows) == len(flows), label
    assert all(f.lcg != LCG_SRB for f in flows if not f.is_srb), label
    per_ue: dict[int, list[int]] = {}
    for f in flows:
        if not f.is_srb:
            per_ue.setdefault(f.ue_id, []).append(f.lcg)
    for ue, lcgs in per_ue.items():
        n = len({(f.ue_id, f.qfi) for f in flows if f.ue_id == ue and not f.is_srb})
        expected = sorted({lcg_for_drb(k) for k in range(1, n + 1)})
        assert sorted(set(lcgs)) == expected, (label, ue, lcgs)
    ul = Counter((f.ue_id, f.lcg) for f in flows if f.direction == "UL")
    assert max(ul.values(), default=1) == 1, (label, [k for k, v in ul.items() if v > 1])


def test_the_census_COVERS_every_builder():
    """Coverage inherited, not assumed: the census ranges over the same
    _cases() the flow-key sweep proves reaches every builder."""
    from sim.tests import test_flow_key_collision_sweep as sweep
    sweep.test_the_sweep_COVERS_every_builder_rather_than_the_easy_ones()


def test_shared_lcg_override_is_a_divergence_off_the_srb_group():
    from sim.parametric import sweep_scenario
    sc = sweep_scenario(seed=1, shared_lcg=True, horizon_slots=200)
    ul = Counter((f.ue_id, f.lcg) for f in sc.flows if f.direction == "UL")
    assert all(f.lcg != LCG_SRB for f in sc.flows)
    assert any(v == 2 for v in ul.values()), ul
