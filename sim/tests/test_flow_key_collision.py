"""Defect #28: a UE cannot carry the same 5QI in both directions, and the
schema must say so LOUDLY rather than dropping a flow.

`FlowRecord.key` is `flow_key(ue_id, qfi)` -- no direction. Before this
guard, a scenario that violated the constraint produced one record and the
other flow vanished with no error; it was found only because a G2 control
read `None`.

THE CATEGORY QUESTION WAS ASKED BEFORE FIXING and the answer was zero: no
scenario in the repository puts a (ue, qfi) pair in both directions, so no
published result lost a flow. Fixed anyway -- the absolute-time class was
latent too, right up until someone shortened a horizon.
"""

from __future__ import annotations

import dataclasses

import pytest

from scheduler.flow import FlowConfig
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord


def _summary_for(sc):
    from sim.baselines.pf import ProportionalFair
    from sim.driver import run
    return run(sc, ProportionalFair(ewma_window_slots=200), cqi_delay_slots=8)


def test_a_colliding_scenario_RAISES_instead_of_losing_a_flow():
    sc = sweep_scenario(seed=1, n_ues=2, horizon_slots=500)
    ul = [f for f in sc.flows if f.direction == "UL"][0]
    # the same (ue_id, qfi) in the opposite direction -- the exact shape that
    # silently lost the DL half of G2's STOP pair
    twin = dataclasses.replace(ul, direction="DL")
    sc2 = dataclasses.replace(sc, flows=list(sc.flows) + [twin])
    summary = _summary_for(sc)
    with pytest.raises(ValueError, match="flow key collision"):
        RunRecord.from_summary(scenario_name="x", scheduler_name="PF", seed=1,
                               flow_configs=sc2.flows, summary=summary,
                               arm={}, meta={})


def test_the_message_names_the_colliding_key_and_cites_the_defect():
    sc = sweep_scenario(seed=1, n_ues=2, horizon_slots=500)
    ul = [f for f in sc.flows if f.direction == "UL"][0]
    sc2 = dataclasses.replace(sc, flows=list(sc.flows)
                              + [dataclasses.replace(ul, direction="DL")])
    with pytest.raises(ValueError) as e:
        RunRecord.from_summary(scenario_name="x", scheduler_name="PF", seed=1,
                               flow_configs=sc2.flows,
                               summary=_summary_for(sc), arm={}, meta={})
    msg = str(e.value)
    assert f"ue{ul.ue_id}_qfi{ul.qfi}" in msg
    assert "#28" in msg
    assert "SILENTLY LOST" in msg


def test_every_real_scenario_still_builds_a_record():
    """THE CONTROL. The guard must not fire on anything that exists -- the
    category question said zero collisions, and this pins that."""
    for n in (2, 4, 8):
        sc = sweep_scenario(seed=1, n_ues=n, horizon_slots=500)
        rec = RunRecord.from_summary(
            scenario_name="x", scheduler_name="PF", seed=1,
            flow_configs=sc.flows, summary=_summary_for(sc), arm={}, meta={})
        assert len(rec.flows) == len(sc.flows), (
            "the guard passed but flows were still lost")


def test_the_G2_STOP_PAIR_shape_is_representable_with_distinct_5QI():
    """The worked-around case: 5QI 85 DL beside 5QI 86 UL, both PDB 5 ms."""
    from scheduler.flow import FIVE_QI_PDB_MS
    assert FIVE_QI_PDB_MS[85] == FIVE_QI_PDB_MS[86] == 5.0
    from sim.fleet import build_fleet
    flows, _ = build_fleet(4, "mixed", ul_stop=True)
    keys = {(f.ue_id, f.qfi) for f in flows}
    assert len(keys) == len(flows), "the STOP pair must not collide"
