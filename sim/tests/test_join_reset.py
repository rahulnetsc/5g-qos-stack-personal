"""WP-Join commit 7: the per-UE scheduler context reset. The only WP-Join
commit (and the only WP since WP0) to touch a scheduler file --
scheduler/two_tier.py -- because, unlike HARQ/join masking (a BufferView
wrapper achieves the same effect from OUTSIDE the scheduler), there is no
way to reset an object's OWN private per-UE dicts without either the
object cooperating (a new, additive, duck-typed method) or reaching into
its private attributes directly (worse coupling, not less).
"""

import pytest

from sim.bsr import BsrModel
from sim.buffer import BufferModel
from sim.config import CarrierConfig, ScenarioConfig, ScriptedFadeWindow, TDDConfig, UEConfig
from sim.driver import run
from sim.join import JoinConfig, JoinEvent
from sim.resource import ResourceGrid
from sim.ue_lcp import UeLcp
from sim.ul_access import UlAccessModel
from sim.baselines.gradient import GradientScheduler
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin
from scheduler import TwoTier
from scheduler.flow import FlowConfig


# -- TwoTier.reset_ue: restored at commit 7, rewritten against the new ------
# field layout (_UeState's 17 fields across VQ/deficit/last-grant-slot/
# MCS-index/floor -- see scheduler/two_tier.py::reset_ue's own docstring
# for the full per-field mac/full disposition and its ground-truth
# citations). Not a verbatim restoration -- the pre-rewrite fields these
# tests originally poked (_virtual_q, _demand_bps, _gbr_penalty, the UL
# shadow bucket) no longer exist.


def _configured_two_tier(flows):
    tt = TwoTier()
    grid = ResourceGrid(CarrierConfig(bandwidth_hz=20_000_000, numerology=1), TDDConfig())
    tt.configure(flows, grid.slot_duration_s, grid)
    return tt


def _dirty_ue_state(tt, ue_id, dl_qfi, ul_qfi):
    """Nonzero everywhere reset_ue might touch, so a field it silently
    skips is caught rather than masked by already being zero -- same
    discipline the pre-rewrite implementation's own helper used."""
    state = tt._ue_state[ue_id]
    state.vq_dl[dl_qfi] = 12345.0
    state.vq_ul[1] = 6789.0
    state.dl_flow_deficit_bytes[dl_qfi] = 700
    state.ul_lcg_deficit_bytes[1] = 500
    state.dl_flow_last_grant_slot[dl_qfi] = 4
    state.ul_lcg_last_grant_slot[1] = 3
    state.dl_mcs_index = 6
    state.ul_mcs_index = 5
    state.floor_rx_lastseen = 111
    state.floor_alive_slot = 10
    state.floor_last_move_slot = 10
    state.floor_fruitless = 2
    state.floor_fruitless_slot = 10
    state.floor_adq_backoff = 1
    state.floor_adq_slot = 10
    state.floor_crumb_run = 3
    state.floor_disarmed = True


def test_reset_ue_mac_scope_retains_the_fairness_ledger():
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000),
        FlowConfig(ue_id=1, qfi=2, direction="UL", lcg=1),
    ]
    tt = _configured_two_tier(flows)
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=False)
    buffers.register(1, 2, is_ul=True, lcg=1)
    _dirty_ue_state(tt, 1, dl_qfi=1, ul_qfi=2)

    tt.reset_ue(1, "mac", buffers)

    state = tt._ue_state[1]
    assert state.vq_dl[1] == 12345.0
    assert state.vq_ul[1] == 6789.0
    assert state.dl_flow_deficit_bytes[1] == 700
    assert state.ul_lcg_deficit_bytes[1] == 500
    assert state.dl_flow_last_grant_slot[1] == 4
    assert state.ul_lcg_last_grant_slot[1] == 3
    assert state.dl_mcs_index == 6
    assert state.ul_mcs_index == 5
    assert state.floor_alive_slot == 10
    assert state.floor_fruitless == 2
    assert state.floor_disarmed is True


def test_reset_ue_full_scope_clears_the_fairness_ledger_too():
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000),
        FlowConfig(ue_id=1, qfi=2, direction="UL", lcg=1),
    ]
    tt = _configured_two_tier(flows)
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=False)
    buffers.register(1, 2, is_ul=True, lcg=1)
    _dirty_ue_state(tt, 1, dl_qfi=1, ul_qfi=2)
    buffers.enqueue(1, 1, 2_000, 0.0)
    buffers.drain(1, 1, 1_000, 1.0, 1.0)

    tt.reset_ue(1, "full", buffers)

    state = tt._ue_state[1]
    assert state.vq_dl == {}
    assert state.vq_ul == {}
    assert state.dl_flow_deficit_bytes == {}
    assert state.ul_lcg_deficit_bytes == {}
    assert state.dl_flow_last_grant_slot == {}
    assert state.ul_lcg_last_grant_slot == {}
    assert state.dl_mcs_index is None
    assert state.ul_mcs_index is None
    assert state.floor_alive_slot is None
    assert state.floor_fruitless == 0
    assert state.floor_disarmed is False
    # Re-seeded with CURRENT cumulative (1000 delivered, 1000 still
    # queued -> 2000 arrived-equivalent for the DL demand-estimator
    # derivation), not cleared to empty -- the trap found while
    # implementing this method (module docstring's own citation).
    assert tt._del_hist[(1, 1)] == 1_000
    assert tt._arr_hist[(1, 1)] == 2_000


def test_reset_ue_does_not_touch_a_different_ue():
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000),
    ]
    tt = _configured_two_tier(flows)
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=False)
    buffers.register(2, 1, is_ul=False)
    _dirty_ue_state(tt, 1, dl_qfi=1, ul_qfi=1)
    tt._ue_state[2].vq_dl[1] = 55555.0

    tt.reset_ue(1, "full", buffers)

    assert tt._ue_state[2].vq_dl[1] == 55555.0  # untouched


def test_reset_ue_is_a_no_op_for_a_ue_with_no_flows():
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000)
    tt = _configured_two_tier([flow])
    buffers = BufferModel()
    tt.reset_ue(99, "full", buffers)  # UE 99 doesn't exist -- must not raise


def test_reset_ue_rejects_an_invalid_scope():
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000)
    tt = _configured_two_tier([flow])
    buffers = BufferModel()
    with pytest.raises(ValueError):
        tt.reset_ue(1, "bogus", buffers)


def test_reset_ue_full_scope_ul_shadow_bucket_field_poke_is_retired():
    """test_reset_ue_full_scope_resets_ul_shadow_bucket, from commit 1's
    own disposition table, is RETIRED not restored -- it poked
    _ul_shadow_bucket/_ul_predicted_backlog, the UL intra-TB per-flow
    estimators CLAUDE.md's own standing invariant says never to
    reintroduce (deleted permanently at commit 1, no successor field).
    This marker exists so the retirement is a recorded decision, not a
    silent gap."""


# -- PF/gradient/RoundRobin: checkable, not assumed, to have no reset_ue --


@pytest.mark.parametrize("scheduler_cls", [ProportionalFair, GradientScheduler, RoundRobin])
def test_other_schedulers_do_not_implement_reset_ue(scheduler_cls):
    """docs/wp-join-plan.md D8: PF/gradient's only relevant state (_r_avg)
    provably decays to indistinguishable-from-fresh within any GT-6-scale
    outage, so a reset there would be a no-op -- documented, not
    implemented. Checked directly here, not assumed from the doc alone."""
    assert getattr(scheduler_cls(), "reset_ue", None) is None


# -- sim-side per-UE resets: BsrModel / UlAccessModel / UeLcp ---------------


def test_bsr_reset_ue_seeds_deadlines_relative_to_the_reset_slot():
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF")
    bsr = BsrModel([flow], slot_duration_s=0.0005, periodic_bsr_ms=5.0, retx_bsr_ms=80.0)
    st = bsr._state[1]
    st.estimated_ul_buffer = 9999
    st.pending = True

    bsr.reset_ue(1, slot_index=10_000)

    st = bsr._state[1]
    assert st.estimated_ul_buffer == 0
    assert st.pending is False
    # NOT the absolute periodic_bsr_slots/retx_bsr_slots (which would
    # already be in the past at slot 10,000) -- one interval forward
    # from the reset instant, same rule __init__ applies at slot 0.
    assert st.periodic_deadline_slot == 10_000 + bsr._periodic_bsr_slots
    assert st.retx_deadline_slot == 10_000 + bsr._retx_bsr_slots


def test_bsr_reset_ue_is_a_no_op_for_a_ue_with_no_ul_flows():
    flow = FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="PF")
    bsr = BsrModel([flow], slot_duration_s=0.0005)
    bsr.reset_ue(99, slot_index=0)  # must not raise


def test_ul_access_reset_ue_clears_pending_and_rach_recovery():
    flow = FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF")
    ul_access = UlAccessModel([flow], slot_duration_s=0.0005)
    st = ul_access._state[1]
    st.pending = True
    st.rach_recovery_until = 500
    st.gnb_sr_flag = True

    ul_access.reset_ue(1)

    st = ul_access._state[1]
    assert st.pending is False
    assert st.rach_recovery_until is None
    assert st.gnb_sr_flag is False


def test_ue_lcp_reset_ue_zeroes_only_that_ues_buckets():
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="PF", pbr_bps=1000, bsd_ms=100),
        FlowConfig(ue_id=2, qfi=1, direction="UL", flow_class="PF", pbr_bps=1000, bsd_ms=100),
    ]
    lcp = UeLcp(flows)
    lcp.refill(1.0)  # fill both buckets
    assert lcp._buckets[(1, 1)].tokens > 0
    assert lcp._buckets[(2, 1)].tokens > 0

    lcp.reset_ue(1)

    assert lcp._buckets[(1, 1)].tokens == 0.0
    assert lcp._buckets[(2, 1)].tokens > 0  # untouched


# -- end-to-end: scope selection (the driver's own logic) -------------------


class _RecordingScheduler:
    """Delegates real scheduling to RoundRobin so a full driver.run() still
    behaves normally; records every reset_ue call so the driver's own
    mac/full/warm-never scope-selection logic can be checked directly,
    independent of what any one scheduler does with the scope."""

    def __init__(self):
        self._inner = RoundRobin()
        self.reset_calls: list[tuple[int, str]] = []

    def configure(self, flows, slot_duration_s, grid):
        self._inner.configure(flows, slot_duration_s, grid)

    def allocate(self, slot, buffers, channel):
        return self._inner.allocate(slot, buffers, channel)

    def reset_ue(self, ue_id, scope, buffers):
        self.reset_calls.append((ue_id, scope))


def _flows_with_handshake(ue_id=1):
    return [
        FlowConfig(ue_id=ue_id, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000,
                   pdb_ms=50, traffic_kind="deterministic",
                   traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
        FlowConfig(ue_id=ue_id, qfi=90, direction="UL", flow_class="PF", pdb_ms=1000,
                   traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
        FlowConfig(ue_id=ue_id, qfi=91, direction="DL", flow_class="PF", pdb_ms=1000,
                   traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
    ]


def test_true_reestablish_triggers_a_mac_scope_reset():
    sc = ScenarioConfig(
        name="wpjoin_reset_scope_mac", horizon_slots=15000,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
                      scripted_fade=(ScriptedFadeWindow(start_slot=100, end_slot=5100, extra_loss_db=30.0),),
                      join=JoinConfig(handshake_ul_qfi=90, handshake_dl_qfi=91))],
        flows=_flows_with_handshake(),
    )
    sched = _RecordingScheduler()
    run(sc, sched)
    assert sched.reset_calls == [(1, "mac")]


def test_cold_attach_triggers_a_full_scope_reset():
    sc = ScenarioConfig(
        name="wpjoin_reset_scope_cold", horizon_slots=3000,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
                      join=JoinConfig(initial_state="powered_off",
                                      events=(JoinEvent(slot=500, kind="power_on"),),
                                      handshake_ul_qfi=90, handshake_dl_qfi=91))],
        flows=_flows_with_handshake(),
    )
    sched = _RecordingScheduler()
    run(sc, sched)
    assert sched.reset_calls == [(1, "full")]


def test_reestablish_that_falls_back_through_idle_triggers_a_full_scope_reset():
    """The subtlety this commit's own review flagged: active_path stays
    "reestablish" for the whole cycle even when t311 expires and the UE
    falls back to a full re-attach via IDLE -- real hardware retains no
    context in that case either, so this must NOT get "mac" just because
    the path label says "reestablish". Fade duration forced comfortably
    past the commit-3-confirmed 10,010-slot reestablish/IDLE-fallback
    boundary."""
    sc = ScenarioConfig(
        name="wpjoin_reset_scope_idle_fallback", horizon_slots=25000,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
                      scripted_fade=(ScriptedFadeWindow(start_slot=100, end_slot=10700, extra_loss_db=30.0),),
                      join=JoinConfig(handshake_ul_qfi=90, handshake_dl_qfi=91))],
        flows=_flows_with_handshake(),
    )
    sched = _RecordingScheduler()
    summary = run(sc, sched)
    assert summary["join_events"][0]["path"] == "reestablish"  # label unchanged
    assert sched.reset_calls == [(1, "full")]  # but scope is "full", not "mac"


def test_warm_path_never_triggers_a_scheduler_reset():
    sc = ScenarioConfig(
        name="wpjoin_reset_scope_warm", horizon_slots=3000,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
                      join=JoinConfig(events=(JoinEvent(slot=500, kind="app_restart"),),
                                      handshake_ul_qfi=90, handshake_dl_qfi=91))],
        flows=_flows_with_handshake(),
    )
    sched = _RecordingScheduler()
    run(sc, sched)
    assert sched.reset_calls == []  # radio never dropped -- no reconnection edge at all


def test_no_ue_config_join_never_calls_reset_ue_even_when_the_scheduler_has_one():
    sc = ScenarioConfig(
        name="wpjoin_reset_scope_no_join", horizon_slots=200,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000)],
        flows=[FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=1_000_000,
                           pdb_ms=50, traffic_kind="deterministic",
                           traffic_params={"period_ms": 5.0, "bytes_per_period": 500})],
    )
    sched = _RecordingScheduler()
    run(sc, sched)
    assert sched.reset_calls == []
