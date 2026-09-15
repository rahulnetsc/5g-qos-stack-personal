"""Configured grants (sim/configured_grant.py), Build 2 of the pre-scheduler
occupancy. Every test here asks something a run's output could contradict;
the off path's identity is held by `regression_corpus --check`, which is
clean with the flag absent."""
import pytest

from scheduler.two_tier import TwoTier
from sim.configured_grant import (CG_PERIODICITY_N_BY_SCS_KHZ, CgConfig,
                                  ConfiguredGrantModel, cg_periodicities_slots)
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.resource import ResourceGrid
from sim.scenarios.g3 import QFI_CAMERA, QFI_TELEMETRY, build_gt22_scenario
from sim.srb import with_srb
from sim.ul_access import UlAccessModel


def _cell(n_ues=8, horizon=8_000, seed=1097657231):
    return with_srb(build_gt22_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon))


def _run(sc, cg, sink=None):
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    return driver_run(sc, TwoTier(min_rb=5), cqi_delay_slots=8, max_sched_ues=4,
                      random_access=ra, configured_grant=cg, grant_sink=sink)


# --- the transcribed table and the period policy ---------------------------

def test_periodicity_table_is_per_scs_sorted_and_the_mu2_set_is_the_60khz_row():
    for scs, ns in CG_PERIODICITY_N_BY_SCS_KHZ.items():
        assert ns == tuple(sorted(set(ns))), scs
    assert cg_periodicities_slots(2) == CG_PERIODICITY_N_BY_SCS_KHZ[60]
    with pytest.raises(ValueError):
        cg_periodicities_slots(5)


def test_period_is_the_largest_pattern_aligned_value_under_half_the_pdb():
    """mu = 2, DSUUU, PDB 100 ms = 400 slots: cap is 200, the allowed values
    under it are ... 128, 160; 160 is a multiple of 5 and 128 is not."""
    sc = _cell()
    m = ConfiguredGrantModel(sc.flows, ResourceGrid(sc.carrier, sc.tdd), CgConfig())
    st = m._states[(1, QFI_TELEMETRY)]
    assert st.pdb_slots == 400
    assert st.period_slots == 160
    assert st.period_slots % len(sc.tdd.pattern) == 0


def test_eligibility_is_the_contract_not_the_traffic_kind():
    """Telemetry (300 B per 100 ms) qualifies; the 4 Mbps camera (75 kB per
    150 ms) does not; the flood and filler are best-effort and never do."""
    sc = _cell()
    m = ConfiguredGrantModel(sc.flows, ResourceGrid(sc.carrier, sc.tdd), CgConfig())
    qfis = {qfi for _, qfi in m.eligible_flows()}
    assert qfis == {QFI_TELEMETRY}
    assert m._states[(1, QFI_TELEMETRY)].message_bytes == 300


# --- the SR rule (TS 38.321 sec 5.4.4) ------------------------------------

def test_an_active_cg_suppresses_sr_only_for_the_channels_it_may_carry():
    """`UlAccessModel.on_arrivals` reads only `bytes_queued` and
    `bytes_reported` through `buffers.state(ue, qfi)`, so the fixture is a
    two-attribute stand-in: UE 1's telemetry just arrived on an otherwise
    empty UE -- the classic empty -> non-empty SR trigger."""
    sc = _cell(n_ues=2)
    ua = UlAccessModel(sc.flows, 0.00025, sr_period_slots=10, sr_offset_slots=0,
                       slots_per_frame=40)

    class _St:
        def __init__(self, q):
            self.bytes_queued = q
            self.bytes_reported = 0

    class _Buffers:
        def state(self, ue, qfi):
            return _St(300 if (ue, qfi) == (1, QFI_TELEMETRY) else 0)

    arrived = {(1, QFI_TELEMETRY): 300}
    st = ua._state[1]
    ua.on_arrivals(arrived, _Buffers(), cg_covers=lambda ue, qfi: qfi == QFI_TELEMETRY)
    assert not st.pending, "a covered channel's arrival raised an SR"
    # The camera (uncovered) arriving on the same UE DOES raise one: the CG
    # cannot carry it, so for that channel no UL-SCH resource is available.
    ua.on_arrivals({(1, QFI_CAMERA): 1500}, _Buffers(),
                   cg_covers=lambda ue, qfi: qfi == QFI_TELEMETRY)
    assert st.pending, "an uncovered channel's arrival did not raise an SR"
    # ... unless the UE really is empty before it: rebuild with the camera
    # as the only backlog and no CG at all -> the classic trigger fires.
    ua2 = UlAccessModel(sc.flows, 0.00025, sr_period_slots=10, sr_offset_slots=0,
                        slots_per_frame=40)
    ua2.on_arrivals(arrived, _Buffers(), cg_covers=None)
    assert ua2._state[1].pending, "no CG, empty->non-empty arrival, no SR"
    # And with the restriction OFF the CG covers every channel on the UE.
    ua3 = UlAccessModel(sc.flows, 0.00025, sr_period_slots=10, sr_offset_slots=0,
                        slots_per_frame=40)
    ua3.on_arrivals(arrived, _Buffers(), cg_covers=lambda ue, qfi: ue == 1)
    assert not ua3._state[1].pending


# --- run level: reached, on the right slots, and the switch does what it says

def test_cg_is_reached_and_every_occasion_lands_on_an_uplink_slot():
    sc = _cell()
    pat = sc.tdd.pattern
    cg_slots, dyn_slots = [], 0

    def sink(g):
        nonlocal dyn_slots
        if g.direction != "UL" or g.retx_count:
            return
        if g.configured:
            cg_slots.append(g.slot_index)
            assert g.cce_cost == 0, "a CG occasion spent a DCI"
        else:
            dyn_slots += 1
    s = _run(sc, {"lcp_restriction": True}, sink)
    c = s["configured_grant"]
    assert c["eligible_flows"] == 8
    assert c["totals"]["occasions"] > 0 and c["totals"]["used"] > 0
    assert cg_slots, "no CG transmission ever traced"
    assert all(pat[k % len(pat)] in ("U", "S") for k in cg_slots)
    assert c["totals"]["invalid_slot"] == 0
    assert dyn_slots > 0, "dynamic grants vanished -- CG is not meant to replace them"
    assert s["levers"]["configured_grant"]["lcp_restriction"] is True


def test_restriction_switch_decides_which_channels_ride_the_cg():
    sc = _cell()
    carried = {True: set(), False: set()}
    for restricted in (True, False):
        def sink(g, r=restricted):
            if g.configured:
                carried[r].update(q for q, b in g.split if b > 0)
        _run(sc, {"lcp_restriction": restricted}, sink)
    assert carried[True] <= {QFI_TELEMETRY}, carried[True]
    assert QFI_CAMERA in carried[False], "unrestricted CG never carried the camera"


def test_an_empty_occasion_wastes_its_prbs_and_is_counted():
    s = _run(_cell(), {"lcp_restriction": True})
    t = s["configured_grant"]["totals"]
    assert t["skipped_empty"] > 0
    assert t["prb_wasted"] > 0
    assert t["prb_reserved"] >= t["prb_wasted"]
    assert t["occasions"] == (t["used"] + t["skipped_empty"] + t["skipped_harq_pending"]
                              + t["skipped_same_slot"] + t["skipped_cg_busy"])


def test_off_leaves_no_trace_in_the_summary():
    s = _run(_cell(horizon=2_000), None)
    assert "configured_grant" not in s
    assert "configured_grant" not in s.get("levers", {})


# --- Build 2b: more than one CG on a UE -----------------------------------

def _two_cg_cell(n_ues=2, horizon=8_000):
    """G5's robot (telemetry) plus a second small periodic flow on the same
    robot, both first reporting in the same slot -- the case the probe of
    2026-09-15 showed colliding on every robot, every seed."""
    import dataclasses
    from scheduler.flow import LCG_UNASSIGNED, FlowConfig
    from sim.scenarios.g5 import QFI_TELEMETRY as G5_TEL, build_gt31_scenario
    sc = build_gt31_scenario(seed=1, n_ues=n_ues, horizon_slots=horizon)
    qfi = max(f.qfi for f in sc.flows) + 1
    extra = [FlowConfig(ue_id=u, qfi=qfi, direction="UL", flow_class="GBR",
                        gfbr_bps=200 * 8 * 1000 / 50.0, mfbr_bps=2 * 200 * 8 * 1000 / 50.0,
                        pdb_ms=50.0, lcg=LCG_UNASSIGNED, traffic_kind="periodic_control",
                        traffic_params={"period_ms": 50.0, "bytes_per_period": 200})
             for u in sorted({f.ue_id for f in sc.flows if f.qfi == G5_TEL})]
    return with_srb(dataclasses.replace(sc, flows=list(sc.flows) + extra)), G5_TEL, qfi


def test_two_cgs_on_one_ue_never_share_a_slot_and_own_disjoint_harq_processes():
    sc, q_tel, q_mon = _two_cg_cell()
    per_slot: dict[tuple[int, int], int] = {}

    def sink(g):
        if g.configured and not g.retx_count:
            per_slot[(g.slot_index, g.ue_id)] = per_slot.get((g.slot_index, g.ue_id), 0) + 1
    s = _run(sc, {"lcp_restriction": True}, sink)
    c = s["configured_grant"]
    assert c["eligible_flows"] == 4                      # 2 UEs x 2 flows
    assert per_slot and max(per_slot.values()) == 1, "two CG PUSCHs of one UE in one slot"
    assert c["totals"]["phase_deferred"] >= 2, "the second CG was not moved to a free phase"
    assert c["totals"]["phase_collisions"] == 0
    assert c["refused_harq_budget"] == 0
    for ue in (1, 2):
        a = tuple(c["per_flow"][f"ue{ue}_qfi{q_tel}"]["harq_pids"])
        b = tuple(c["per_flow"][f"ue{ue}_qfi{q_mon}"]["harq_pids"])
        assert a and b and not set(a) & set(b), (a, b)


def test_dynamic_grants_stay_off_the_reserved_harq_processes():
    from sim.harq import HarqProcessPool
    pool = HarqProcessPool(ul_capacity=16)
    pool.reserve_ul(1, (14, 15))
    dyn = [pool.allocate(1, "UL", 100, 5) for _ in range(14)]
    assert all(p is not None for p in dyn) and {p.pid for p in dyn} == set(range(14))
    assert pool.allocate(1, "UL", 100, 5) is None            # the dynamic side is exhausted
    assert pool.allocate(1, "UL", 100, 5, pids=(14, 15)).pid == 14
    assert pool.allocate(1, "UL", 100, 5, pids=(14, 15)).pid == 15
    assert pool.allocate(1, "UL", 100, 5, pids=(14, 15)) is None   # cg_busy
    with pytest.raises(ValueError):
        pool.reserve_ul(1, (15, 16))                          # overlap and out of range
    assert pool.allocate(2, "UL", 100, 5).pid == 0             # another UE: nothing reserved


# --- Build 2c: a restricted CG TB masks only its own channel ----------------

def test_restricted_cg_tbs_mask_their_own_channel_only():
    from sim.harq import HarqAwareBufferView, HarqProcessPool
    pool = HarqProcessPool(ul_capacity=16)
    pool.reserve_ul(1, (14, 15))
    p = pool.allocate(1, "UL", 300, 5, pids=(14, 15), cg_qfi=7)
    assert p.pid == 14 and p.cg_qfi == 7
    assert pool.ul_cg_pending(1, 7) and not pool.ul_dynamic_pending(1)
    assert pool.ul_flow_in_flight(1, 7) and not pool.ul_flow_in_flight(1, 9)
    assert pool.is_pending(1, "UL")                          # "any UL TB": unchanged meaning

    class _St:
        def __init__(self):
            self.bytes_queued = 500
            self.bytes_reported = 500

    class _B:
        def state(self, ue, qfi):
            return _St()
    dirs = {(1, 7): "UL", (1, 9): "UL", (2, 7): "UL"}
    view = HarqAwareBufferView(_B(), pool, dirs)
    assert view.state(1, 7).bytes_queued == 0                # the CG's own channel is hidden
    assert view.state(1, 9).bytes_queued == 500              # the UE's other channel is not
    assert view.state(2, 7).bytes_queued == 500
    busy = HarqAwareBufferView(_B(), pool, dirs, ul_busy_this_slot=frozenset({1}))
    assert busy.state(1, 9).bytes_queued == 0                # one PUSCH per slot per UE
    d = pool.allocate(1, "UL", 400, 5, ul_split=[(9, 400)])
    assert d.cg_qfi == -1 and pool.ul_dynamic_pending(1) and pool.ul_flow_in_flight(1, 9)
    assert view.state(1, 9).bytes_queued == 0                # a dynamic TB masks the whole UE
    pool.free(1, "UL", d.pid)
    pool.free(1, "UL", p.pid)
    assert not pool.ul_flow_in_flight(1, 7) and not pool.is_pending(1, "UL")
    assert pool._busy_ul_cg == {(1, 7): 0} and pool._busy_ul_cg_total == {1: 0}


def test_one_uplink_pusch_per_ue_per_slot_with_cg_and_dynamic_grants_mixed():
    """Two CGs per robot plus dynamic grants: never two UL PUSCHs of one UE in
    one slot, and no CG occasion is refused for a TB that carries none of its
    channel's bytes -- the refusals that remain are the same-slot rule."""
    sc, q_tel, q_mon = _two_cg_cell()
    per_slot: dict[tuple[int, int], int] = {}

    def sink(g):
        if g.direction == "UL" and not g.retx_count:
            per_slot[(g.slot_index, g.ue_id)] = per_slot.get((g.slot_index, g.ue_id), 0) + 1
    s = _run(sc, {"lcp_restriction": True}, sink)
    assert per_slot and max(per_slot.values()) == 1
    t = s["configured_grant"]["totals"]
    assert t["used"] > 0 and t["occasions"] == (
        t["used"] + t["skipped_empty"] + t["skipped_harq_pending"]
        + t["skipped_same_slot"] + t["skipped_cg_busy"])
