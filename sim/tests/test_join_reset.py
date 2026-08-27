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
from sim.config import CarrierConfig, ScenarioConfig, ScriptedFadeWindow, UEConfig
from sim.driver import run
from sim.join import JoinConfig, JoinEvent
from sim.ue_lcp import UeLcp
from sim.ul_access import UlAccessModel
from sim.baselines.gradient import GradientScheduler
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin
from scheduler.flow import FlowConfig


# -- TwoTier.reset_ue: deleted with the Phase 2 rewrite's commit 1 -----------
#
# scheduler/two_tier.py's commit 1 (docs/phase2-plan.md) drops reset_ue
# entirely rather than porting it -- the fields these tests poked
# (_virtual_q, _demand_bps, _gbr_penalty, the UL shadow bucket) no longer
# exist. sim/driver.py discovers reset_ue via getattr(scheduler,
# "reset_ue", None), so its absence just means TwoTier is treated like PF
# (no context reset) in the interim. Restored at two-tier's own commit 7,
# rewritten against the new field layout, not copied back verbatim.


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
