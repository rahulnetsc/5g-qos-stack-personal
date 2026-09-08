"""Build 1.2 -- SRBs as flows and the dialogues that ride them (sim/srb.py)."""
from __future__ import annotations

import pytest

from scheduler.flow import LCG_SRB, FlowConfig, assign_deployed_lcgs
from sim.random_access import RandomAccessConfig
from sim.run_record import FlowRecord, RunRecord
from sim.scorecard import Population
from sim.srb import (ATTACH_DIALOGUE, L2_OVERHEAD_BYTES, SRB1_DL_QFI, SRB1_UL_QFI,
                     SrbDialogues, srb_flows, with_srb)


def test_srb_flows_sit_on_lcg0_off_the_drb_ordinals():
    flows = [FlowConfig(ue_id=1, qfi=9, direction="UL"), FlowConfig(ue_id=1, qfi=2, direction="DL")]
    flows += srb_flows(1)
    assign_deployed_lcgs(flows)
    assert [f.lcg for f in flows[:2]] == [1, 2]              # DRB ordinals untouched
    assert all(f.lcg == LCG_SRB and f.is_srb and f.qfi < 0 for f in flows[2:])
    assert len({(f.ue_id, f.qfi) for f in flows[2:]}) == 4   # one queue per direction
    assert {f.priority_level for f in flows[2:]} == {1, 3}
    with pytest.raises(ValueError):
        FlowConfig(ue_id=1, qfi=-1, direction="UL", is_srb=True, lcg=1)


def test_srb_wins_the_tb_over_a_gbr_bearer_with_tokens():
    """The stall the smoke found: with PBR 0 the LCP's first round gives the
    whole TB to a GBR bearer holding tokens and the RRC message never goes.
    PBR infinity is the deployed configuration."""
    from sim.buffer import BufferModel
    from sim.ue_lcp import UeLcp
    flows = [FlowConfig(ue_id=1, qfi=2, direction="UL", flow_class="GBR", gfbr_bps=4e6, pdb_ms=150.0)] + srb_flows(1)
    assign_deployed_lcgs(flows)
    buffers = BufferModel()
    for f in flows:
        buffers.register(f.ue_id, f.qfi, is_ul=True, lcg=f.lcg)
    buffers.enqueue(1, 2, 70_000, 0.0)
    srb_ul = [f for f in flows if f.is_srb and f.direction == "UL" and f.priority_level == 1][0]
    buffers.enqueue(1, srb_ul.qfi, 18, 0.0)
    lcp = UeLcp(flows); lcp.refill(0.1)
    split = dict(lcp.fill([f for f in flows if f.direction == "UL"], 38, buffers))
    assert split.get(srb_ul.qfi) == 18, split


def test_with_srb_is_scenario_level_and_idempotent():
    from sim.scenarios.g9 import gt62_cold_attach
    sc = gt62_cold_attach(seed=1, n_neighbours=2, horizon_slots=4000, first_slot=500,
                          off_slots=400, period_slots=3000, n_cycles=1, allow_partial_schedule=True)
    before = {(f.ue_id, f.qfi): f.lcg for f in sc.flows}
    sc2 = with_srb(sc)
    assert len(sc2.flows) == len(sc.flows) + 4 * len(sc.ues)
    assert {(f.ue_id, f.qfi): f.lcg for f in sc2.flows if not f.is_srb} == before
    assert len(with_srb(sc2).flows) == len(sc2.flows)


def test_dialogue_advances_only_on_full_delivery():
    delivered = {}
    sent = []
    d = SrbDialogues(enqueue=lambda u, q, n, name: sent.append((u, q, n, name)),
                     delivered_cum=lambda u, q: delivered.get((u, q), 0))
    d.start(7, "cold", 0)
    assert sent[0][1] == SRB1_UL_QFI and sent[0][2] == 41 + L2_OVERHEAD_BYTES
    assert d.step(1) == {} and len(sent) == 1
    delivered[(7, SRB1_UL_QFI)] = sent[0][2] - 1                # a fragment is not a delivery
    assert d.step(2) == {} and len(sent) == 1
    delivered[(7, SRB1_UL_QFI)] = sent[0][2]
    assert d.step(3) == {} and len(sent) == 2 and sent[1][1] == SRB1_DL_QFI
    for i in range(1, len(ATTACH_DIALOGUE)):
        u, q, n, _ = sent[-1]
        delivered[(u, q)] = delivered.get((u, q), 0) + n
        done = d.step(10 + i)
    assert done == {7: "cold"} and d.counters["srb_dialogues_completed"] == 1
    assert d.counters["srb_steps_sent"] == len(ATTACH_DIALOGUE) and not d.active(7)


def test_populations_exclude_srb_everywhere():
    from sim.baselines.pf import ProportionalFair
    from sim.driver import run
    sc = with_srb(_gt62(1))
    summary = run(sc, ProportionalFair(), random_access={**RandomAccessConfig.deployed().to_dict(), "srb": True})
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="PF", seed=1,
                                 flow_configs=list(sc.flows), summary=summary)
    assert any(fr.is_srb for fr in rec.flows.values())
    for pop in (Population.all_flows(), Population.protected_fleet()):
        assert not any(fr.is_srb for fr in pop.restrict(rec).flows.values()), pop.name


def _gt62(n_cycles=2):
    from sim.scenarios.g9 import gt62_cold_attach
    return gt62_cold_attach(seed=1, n_neighbours=2, n_cycles=n_cycles, horizon_slots=9000,
                            first_slot=500, off_slots=400, period_slots=3000,
                            allow_partial_schedule=True)


def test_driver_runs_the_attach_dialogue_and_reservation_s_tier_is_live():
    from scheduler.reservation import Reservation
    from sim.driver import run
    sc = with_srb(_gt62(2))
    cfg = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    summary = run(sc, Reservation(min_rb=5), random_access=cfg)
    srb = summary["srb"]
    assert srb["by_kind"]["cold"]["completed"] == 2 and srb["srb_active_at_end"] == 0, srb
    assert srb["srb_steps_sent"] == 2 * len(ATTACH_DIALOGUE)
    assert summary["scheduler_counters"]["has_srb_decisive"] > 0, summary["scheduler_counters"]
    ev = [e for e in summary["join_events"] if e["path"] == "cold"]
    assert all(e["attached_slot"] is not None for e in ev)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="Reservation", seed=1,
                                 flow_configs=list(sc.flows), summary=summary)
    assert rec.srb["srb_dialogues_completed"] == 2 and rec.scheduler_counters["has_srb_decisive"] > 0
    assert sum(fr.bytes_delivered for fr in rec.flows.values() if fr.is_srb) > 0
    assert RunRecord.from_dict(rec.to_dict()).srb == rec.srb


def test_srb_off_builds_nothing_and_ra_without_srb_flows_refuses():
    from sim.baselines.pf import ProportionalFair
    from sim.driver import run
    sc = _gt62(1)
    summary = run(sc, ProportionalFair())
    assert "srb" not in summary and "scheduler_counters" not in summary
    with pytest.raises(ValueError, match="with_srb"):
        run(sc, ProportionalFair(), random_access={**RandomAccessConfig.deployed().to_dict(), "srb": True})
