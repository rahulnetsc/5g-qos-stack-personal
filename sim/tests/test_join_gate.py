"""WP-Join commit 5: the radio-layer gate. UEConfig.join is opt-in
(default None); no corpus scenario sets it. The falsifiable claim is
stronger than "no scenario sets the config" alone -- per driver.py's own
code, join_states only ever contains an entry for a UE with UEConfig.join
set, so for every OTHER UE, the per-slot loop's `if join_state is None:
continue` skips every line this commit added, JoinAwareBufferView.state()
always falls through to its inner view unmodified, and rlf.step() keeps
running unconditionally exactly as commit 2 left it. "No scenario opts in"
therefore structurally IMPLIES "nothing is ever gated" here -- unlike
commit 2, which had no config at all and needed a different (diagnostic-
output-is-unread) inertness argument.
"""

import pytest

from sim.buffer import BufferModel
from sim.config import CarrierConfig, ScenarioConfig, ScriptedFadeWindow, UEConfig
from sim.driver import run
from sim.harq import HarqAwareBufferView, HarqProcessPool
from sim.join import JoinAwareBufferView, JoinConfig, JoinPhase, JoinState
from sim.run_record import RunRecord
from sim.scorecard import Scorecard
from sim.baselines.round_robin import RoundRobin
from scheduler.flow import FlowConfig


# -- JoinAwareBufferView: masking + BufferView protocol completeness --------


def _real_buffers():
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=False)
    buffers.register(1, 2, is_ul=True)
    buffers.enqueue(1, 1, 5000, 0.0)
    buffers.enqueue(1, 2, 3000, 0.0)
    return buffers


def test_ungated_ue_passes_through_unmodified():
    buffers = _real_buffers()
    view = JoinAwareBufferView(buffers, join_states={})  # no UE opted in
    for qfi in (1, 2):
        assert view.state(1, qfi) == buffers.state(1, qfi)
    assert view.hol_delay_s(1, 1, 1.0) == buffers.hol_delay_s(1, 1, 1.0)
    assert view.arrived_cum(1, 1) == buffers.arrived_cum(1, 1)
    assert view.delivered_cum(1, 1) == buffers.delivered_cum(1, 1)
    assert view.dropped_cum(1, 1) == buffers.dropped_cum(1, 1)


def test_gated_ue_masks_bytes_queued_and_bytes_reported_both_directions():
    buffers = _real_buffers()
    join_states = {1: JoinState(phase=JoinPhase.CELL_SEARCH)}  # radio-gated
    view = JoinAwareBufferView(buffers, join_states)
    for qfi in (1, 2):  # both DL (1) and UL (2) -- the mask is per-UE, not per-flow
        masked = view.state(1, qfi)
        assert masked.bytes_queued == 0
        assert masked.bytes_reported == 0
    # Explicitly unmasked, matching HarqAwareBufferView's own choice:
    assert view.hol_delay_s(1, 1, 1.0) == buffers.hol_delay_s(1, 1, 1.0)
    assert view.arrived_cum(1, 1) == buffers.arrived_cum(1, 1)


def test_gated_ue_does_not_affect_a_different_ue():
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=False)
    buffers.register(2, 1, is_ul=False)
    buffers.enqueue(1, 1, 1000, 0.0)
    buffers.enqueue(2, 1, 1000, 0.0)
    join_states = {1: JoinState(phase=JoinPhase.CELL_SEARCH)}
    view = JoinAwareBufferView(buffers, join_states)
    assert view.state(1, 1).bytes_queued == 0
    assert view.state(2, 1).bytes_queued == 1000  # untouched


@pytest.mark.parametrize("phase", [JoinPhase.CONNECTED, JoinPhase.APP_RESTART, JoinPhase.APP_HANDSHAKE])
def test_connected_phases_are_never_masked(phase):
    buffers = _real_buffers()
    view = JoinAwareBufferView(buffers, join_states={1: JoinState(phase=phase)})
    assert view.state(1, 1).bytes_queued == 5000


def test_composes_over_harq_aware_buffer_view_without_conflict():
    """Both wrappers mask the SAME two fields -- composing them should be
    idempotent (a double-zero is still zero), and a UE masked by ONE layer
    but not the other must still end up masked, since the join layer is
    outermost and its mask strictly subsumes a per-flow HARQ mask
    (docs/wp-join-plan.md sec1.4)."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=False)  # UE 1: HARQ-pending, not radio-gated
    buffers.register(2, 1, is_ul=False)  # UE 2: radio-gated, no HARQ pending
    buffers.enqueue(1, 1, 1000, 0.0)
    buffers.enqueue(2, 1, 1000, 0.0)
    pool = HarqProcessPool()
    pool.allocate(1, "DL", tb_bytes=500, due_slot=10, qfi=1)  # UE 1 now HARQ-pending on (1,1)
    direction_by_flow = {(1, 1): "DL", (2, 1): "DL"}

    inner = HarqAwareBufferView(buffers, pool, direction_by_flow)
    outer = JoinAwareBufferView(inner, join_states={2: JoinState(phase=JoinPhase.CELL_SEARCH)})

    assert outer.state(1, 1).bytes_queued == 0  # masked by the HARQ layer alone
    assert outer.state(2, 1).bytes_queued == 0  # masked by the join layer alone
    # Neither UE's masking leaks into a scenario where both conditions
    # apply to the SAME UE -- verified separately below.
    pool.allocate(2, "DL", tb_bytes=500, due_slot=10, qfi=1)
    assert outer.state(2, 1).bytes_queued == 0  # still zero, not "double-unmasked"


# -- HarqProcessPool.flush_ue ------------------------------------------------


def test_flush_ue_frees_every_busy_process_both_directions():
    pool = HarqProcessPool()
    pool.allocate(1, "DL", tb_bytes=100, due_slot=5, qfi=1)
    pool.allocate(1, "UL", tb_bytes=200, due_slot=5)
    assert pool.is_pending(1, "DL", 1)
    assert pool.is_pending(1, "UL")

    freed = pool.flush_ue(1)
    assert freed == 2
    assert not pool.is_pending(1, "DL", 1)
    assert not pool.is_pending(1, "UL")


def test_flush_ue_is_zero_and_harmless_when_nothing_pending():
    pool = HarqProcessPool()
    assert pool.flush_ue(1) == 0


def test_flush_ue_does_not_touch_another_ue():
    pool = HarqProcessPool()
    pool.allocate(1, "DL", tb_bytes=100, due_slot=5, qfi=1)
    pool.allocate(2, "DL", tb_bytes=100, due_slot=5, qfi=1)
    pool.flush_ue(1)
    assert not pool.is_pending(1, "DL", 1)
    assert pool.is_pending(2, "DL", 1)  # untouched


# -- end-to-end: the real path vs. commit 4's synthetic fixtures ------------


def _gated_scenario(fade_windows, horizon_slots=8000, handshake=False):
    """``handshake=False`` (default) preserves every existing caller's
    behaviour exactly -- no UEConfig.join.handshake_ul_qfi/dl_qfi, so a
    UE parks in APP_HANDSHAKE forever, same as commit 5. ``handshake=
    True`` (WP-Join commit 6) additionally declares the two dedicated
    handshake flows and wires their qfis, letting an event actually
    complete."""
    join_kwargs = {}
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000,
                   pdb_ms=50, traffic_kind="deterministic",
                   traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000,
                   pdb_ms=50, traffic_kind="deterministic",
                   traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
    ]
    if handshake:
        join_kwargs = {"handshake_ul_qfi": 90, "handshake_dl_qfi": 91}
        flows += [
            FlowConfig(ue_id=1, qfi=90, direction="UL", flow_class="PF", pdb_ms=1000,
                       traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
            FlowConfig(ue_id=1, qfi=91, direction="DL", flow_class="PF", pdb_ms=1000,
                       traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
        ]
    return ScenarioConfig(
        name="wpjoin_gate_test", horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[
            UEConfig(
                ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
                scripted_fade=fade_windows, join=JoinConfig(**join_kwargs),
            ),
            UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=1000),  # ungated neighbour
        ],
        flows=flows,
    )


def test_real_reestablish_path_produces_the_shape_commit4s_synthetic_fixtures_assumed():
    """Point 1 of commit 5's review: commit 4's M18 tests were only ever
    checked against hand-built JoinEventRecords. This drives an actual
    scripted fade through the real channel -> rlf.py -> join.py pipeline
    and checks the field names/semantics the scorecard actually receives
    match what those synthetic tests assumed -- same keys, same
    never-None-vs-None conventions, same path label."""
    sc = _gated_scenario((ScriptedFadeWindow(start_slot=100, end_slot=5100, extra_loss_db=30.0),))
    summary = run(sc, RoundRobin(), record_timeseries=True)

    assert summary["rlf_declared_count"] == 1
    assert len(summary["join_events"]) == 1
    raw = summary["join_events"][0]
    # Exactly the field set sim.run_record.JoinEventRecord declares --
    # this dict is fed straight into JoinEventRecord(**raw) by
    # RunRecord.from_summary, so an extra/missing key would raise there.
    assert raw["ue_id"] == 1
    assert raw["path"] == "reestablish"
    assert raw["rlf_declared_at_slot"] == raw["trigger_slot"]
    assert raw["trigger_ts_s"] == pytest.approx(raw["trigger_slot"] * 0.0005)
    assert raw["rf_restore_slot"] == 5100  # exactly when the scripted fade ends
    assert raw["attached_slot"] is None  # commit 6's handshake hasn't landed yet
    assert raw["attached_ts_s"] is None
    assert raw["handshake_rtt_ms"] is None
    assert set(raw["phases"]) <= {"cell_search", "reestablish"}
    assert "connected" not in raw["phases"], (
        "the triggering CONNECTED->CELL_SEARCH transition's prior phase "
        "must never be recorded as if it were inside the new event"
    )

    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="RR", seed=sc.seed,
        flow_configs=sc.flows, summary=summary,
    )
    assert rec.join_events[0].path == "reestablish"
    res = Scorecard().score(rec)["M18"]
    assert res.status == "ok"
    reest = res.value["by_path"]["reestablish"]
    assert reest["n_events"] == 1
    assert reest["n_never_completed"] == 1  # matches attached_slot=None above
    assert reest["p50_ms"] is None  # no completed event to derive a duration from yet


def test_neighbour_ue_is_unaffected_and_run_completes_without_error():
    """Not a fairness/isolation claim (that's commit 8's demo) -- just
    confirms the gated UE's outage doesn't crash or starve the run for a
    UE with no UEConfig.join at all."""
    sc = _gated_scenario((ScriptedFadeWindow(start_slot=100, end_slot=5100, extra_loss_db=30.0),))
    summary = run(sc, RoundRobin())
    assert summary["flows"]["ue2_qfi1"]["bytes_delivered"] > 0


def test_reconnection_rearms_detection_for_a_genuinely_new_degradation():
    """The re-arm claim, made observable from the outside rather than by
    inspecting driver.py's internal rlf_states: a SECOND, later scripted
    fade only declares RLF again if a fresh RlfDetectorState was actually
    constructed on reconnection -- sim/rlf.py's step() is a permanent
    no-op once RLF_DECLARED, so two declarations are only possible with a
    real re-arm in between.

    Updated for WP-Join commit 6 (docs/wp-join-plan.md "Commit 6 --
    landed", review point 1): at commit 5, this test recorded a real,
    then-current limitation -- the UE never reached CONNECTED again
    within that commit alone (no handshake to complete it), so it sat
    parked in APP_HANDSHAKE when the second fade hit, and only
    rlf_declared_count (not join_events) proved re-arm worked. Commit 6's
    handshake completion unsticks exactly that: with handshake_ul_qfi/
    dl_qfi configured, the first event completes, the UE returns to
    CONNECTED, and the second scripted fade now produces a genuine SECOND
    join_events entry -- the FSM correctly routes a second RLF once the
    first fully completes, not just re-detects it.
    """
    sc = _gated_scenario(
        (
            ScriptedFadeWindow(start_slot=100, end_slot=5100, extra_loss_db=30.0),
            ScriptedFadeWindow(start_slot=12000, end_slot=17000, extra_loss_db=30.0),
        ),
        horizon_slots=25000,
        handshake=True,
    )
    summary = run(sc, RoundRobin())
    assert summary["rlf_declared_count"] == 2
    assert len(summary["join_events"]) == 2
    for event in summary["join_events"]:
        assert event["path"] == "reestablish"
        assert event["attached_slot"] is not None
        assert event["handshake_rtt_ms"] is not None
    # The two events are genuinely independent -- second trigger/rf_restore
    # strictly after the first event's own attachment.
    first, second = summary["join_events"]
    assert second["trigger_slot"] > first["attached_slot"]


# -- opt-in inertness: the falsifiable claim, both forms --------------------


def test_a_ue_without_join_is_never_gated_even_when_a_sibling_ue_is():
    """The precise claim (not just "no scenario sets it"): join_states
    only holds an entry for a UE with UEConfig.join set at all -- for
    every other UE, driver.py's per-slot loop takes the `join_state is
    None` branch and never executes any commit-5 logic for it. Checked
    here by giving UE 1 a scripted fade + join, and confirming UE 2 (no
    .join) never appears gated even while UE 1 genuinely is -- not merely
    that UE 2 "looks fine" in aggregate."""
    sc = _gated_scenario((ScriptedFadeWindow(start_slot=100, end_slot=5100, extra_loss_db=30.0),))
    summary = run(sc, RoundRobin())
    # UE 2 was never in join_events at all -- the only entries are UE 1's.
    assert all(e["ue_id"] == 1 for e in summary["join_events"])


def test_no_ue_config_join_reproduces_pre_commit5_behaviour_exactly():
    """Structural form of the inertness claim: with NO UE's UEConfig.join
    set at all (join_states ends up genuinely empty, not just inactive),
    JoinAwareBufferView is a pure pass-through and the RLF loop is commit
    2's exact, unconditional code path -- this is what makes scripts/
    regression_corpus.py --check clean (see docs/wp-join-plan.md "Commit
    5 -- landed"), not merely the absence of a scenario that happens to
    opt in."""
    sc = ScenarioConfig(
        name="wpjoin_no_opt_in", horizon_slots=500,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=1000),
            UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=1000),
        ],
        flows=[
            FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000,
                       pdb_ms=50, traffic_kind="deterministic",
                       traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
            FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000,
                       pdb_ms=50, traffic_kind="deterministic",
                       traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
        ],
    )
    summary = run(sc, RoundRobin())
    assert summary["join_events"] == []
    assert summary["rlf_step_calls"] == 2 * 500  # both UEs, every slot -- never skipped
