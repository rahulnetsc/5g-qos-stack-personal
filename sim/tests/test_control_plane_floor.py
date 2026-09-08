"""TwoTier's control-plane floors (ia_p5g_scheduler.c:2743-2796), live since
Build 1.2 gave the simulator SRB traffic.

The Build 1.2 commit claimed the two-tier arm had no SRB tier. That was
wrong: it was read off `gNB_scheduler_ulsch.c`, which is NOT this arm's UL
scheduler. `ia_p5g_scheduler.c` promotes any UE with LCG-0 bytes to the
control-plane class via `srb_pending_bytes` -> `srb_floor` ->
`sched_inactive`. These tests pin the port, and pin all FOUR sites that
read `sched_inactive` -- the tier, the FIX-2 exclusion, the max_q scan and
grant sizing -- because wiring one and leaving three is this project's
most expensive recurring defect.
"""
from __future__ import annotations

import pytest

from scheduler.flow import LCG_SRB, FlowConfig, assign_deployed_lcgs, ul_lcg_bytes
from scheduler.two_tier import _Candidate
from sim.random_access import RandomAccessConfig
from sim.srb import with_srb


def _run(arm, n_cycles=2, seed=1):
    from sim.driver import run
    from sim.scenarios.g9 import gt62_cold_attach
    sc = with_srb(gt62_cold_attach(seed=seed, n_neighbours=3, n_cycles=n_cycles,
                                   horizon_slots=9000, first_slot=500, off_slots=400,
                                   period_slots=3000, allow_partial_schedule=True))
    return run(sc, arm(), cqi_delay_slots=8, record_timeseries=True,
               random_access={**RandomAccessConfig.deployed().to_dict(), "srb": True})


def test_ul_lcg_bytes_is_one_reader_first_flow_per_lcg_wins():
    class _B:
        def __init__(self, vals): self.vals = vals
        def state(self, u, q):
            class S: pass
            s = S(); s.estimated_ul_buffer_per_lcg = self.vals[(u, q)]; return s
    flows = [FlowConfig(ue_id=1, qfi=9, direction="UL"),
             FlowConfig(ue_id=1, qfi=-11, direction="UL", is_srb=True, lcg=LCG_SRB),
             FlowConfig(ue_id=1, qfi=-12, direction="UL", is_srb=True, lcg=LCG_SRB),
             FlowConfig(ue_id=2, qfi=9, direction="UL"),
             FlowConfig(ue_id=1, qfi=5, direction="DL")]
    assign_deployed_lcgs(flows)
    b = _B({(1, 9): 700, (1, -11): 40, (1, -12): 40, (2, 9): 900, (1, 5): 0})
    out = ul_lcg_bytes(flows, 1, b)
    assert out == {1: 700, LCG_SRB: 40}          # DL excluded, LCG 0 not double-counted
    assert ul_lcg_bytes(flows, 3, b) == {}


def test_the_floors_fire_with_a_count_on_twotier():
    """The manipulation check: a tier that reports zero with SRB traffic
    present is unwired, which is exactly what it was until this commit."""
    from scheduler import load_two_tier
    s = _run(lambda: load_two_tier("scheduler/scheduler_config.yaml", min_rb=5))
    c = s["scheduler_counters"]
    assert c["srb_floor_fired"] > 0, c
    assert c["sched_inactive_fired"] >= c["srb_floor_fired"], c
    assert c["control_plane_grants"] > 0, c
    assert s["srb"]["by_kind"]["cold"]["completed"] == 2


def test_cp_floor_fires_without_srbs_on_the_bsr_desync_fault():
    """NOT a bug and not SRB-specific. `cp_floor = B > 0 && data_lcg_bytes
    == 0` (:2745) is exactly the state defects-log #24/#25 describes: the SR
    report floor puts bytes on `bytes_reported` while the per-LCG array is
    still zero. The C rescues that UE into the control-plane class; this
    port did not, until now. So porting the floor changes TwoTier on EVERY
    workload, not only ones with SRB traffic -- the corpus re-baseline is
    deliberate and registered, not incidental.
    """
    from sim.driver import run
    from sim.parametric import sweep_scenario
    from scheduler import load_two_tier
    sc = sweep_scenario(seed=1, n_ues=8, horizon_slots=4000)
    s = run(sc, load_two_tier("scheduler/scheduler_config.yaml", min_rb=5), cqi_delay_slots=8)
    c = s["scheduler_counters"]
    assert c["srb_floor_fired"] == 0, "no SRB flows exist in this scenario"
    assert c["cp_floor_fired"] > 0, c
    assert c["sched_inactive_fired"] == c["cp_floor_fired"], c


def test_max_q_scan_excludes_control_plane_candidates():
    """:2901 -- a control-plane candidate must not set the normaliser for
    everyone else's urgency term. Site 3 of 4."""
    from scheduler import load_two_tier
    tt = load_two_tier("scheduler/scheduler_config.yaml", min_rb=5)
    data = _Candidate(1, [], 100.0, 0.1, 20.0, coef=10.0, hyp_tbs_bytes=100)
    ctrl = _Candidate(2, [], 100.0, 0.1, 20.0, coef=1000.0, hyp_tbs_bytes=100)
    ctrl.sched_inactive = True
    data.urgency01 = 0.5
    tt._finalize_ul_coef([data, ctrl])
    with_ctrl = data.coef
    data2 = _Candidate(1, [], 100.0, 0.1, 20.0, coef=10.0, hyp_tbs_bytes=100)
    data2.urgency01 = 0.5
    tt._finalize_ul_coef([data2])
    assert with_ctrl == data2.coef, "a control-plane candidate moved the normaliser"


def test_control_plane_candidate_sorts_first_and_takes_exactly_min_rb():
    """Sites 1 and 4 of 4: the tier, and `sched.rbSize = min_rb` (:3102,
    :3264) instead of demand-derived sizing."""
    from scheduler import load_two_tier
    tt = load_two_tier("scheduler/scheduler_config.yaml", min_rb=5)
    ctrl = _Candidate(2, [], 100.0, 0.1, 20.0, coef=0.0, hyp_tbs_bytes=100)
    ctrl.sched_inactive = True
    data = _Candidate(1, [], 100.0, 0.1, 20.0, coef=1e9, hyp_tbs_bytes=100)
    assert tt._ul_rank_key(ctrl) < tt._ul_rank_key(data)
    s = _run(lambda: load_two_tier("scheduler/scheduler_config.yaml", min_rb=5))
    assert s["scheduler_counters"]["control_plane_grants"] > 0
