"""Tests for sim/ul_access.py (WP4): SR -> grant -> BSR -> grant.

Structure mirrors test_bsr.py: small state-machine unit tests first
(trigger, prohibit-timer gating, sr-TransMax exhaustion -> RACH), then an
integration-style re-arm test (bsr.py + ul_access.py together, replacing
the WP3 cold-start probe test this WP retired), then the two acceptance
tests the WP4 plan called for -- see each test's docstring for why two
different scenarios were needed rather than one.
"""

from sim.bsr import BsrModel
from sim.buffer import BufferModel
from sim.driver import run
from sim.ul_access import UlAccessModel
from scheduler.flow import FlowConfig

_SLOT_S = 0.0005  # matches test_bsr.py's representative mu=1 slot duration


def _flow(ue_id, qfi=1, lcg=0):
    return FlowConfig(ue_id=ue_id, qfi=qfi, direction="UL", lcg=lcg)


def test_arrival_on_empty_ue_arms_pending():
    """SR trigger: new data on a UE with no other way to signal it (no
    standing grant, no SR already pending) arms `pending` -- mirrors
    `nr_update_sr`'s trigger condition at UE granularity (module docstring:
    a judgment call, since this sim has no per-LCID SR-DelayTimer or
    configured-grant gate to port)."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    ul = UlAccessModel(flows, _SLOT_S)

    buffers.enqueue(1, 1, 200, 0.0)
    assert ul._state[1].pending is False  # on_arrivals not called yet
    ul.on_arrivals({(1, 1): 200}, buffers)
    assert ul._state[1].pending is True


def test_no_trigger_when_buffer_was_already_nonempty():
    """An arrival that merely adds to an already-nonempty buffer isn't a
    cold start -- there's already a standing grant/BSR path in flight, so
    no fresh SR should arm."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    ul = UlAccessModel(flows, _SLOT_S)

    buffers.enqueue(1, 1, 100, 0.0)
    ul.on_arrivals({(1, 1): 100}, buffers)
    ul._state[1].pending = False  # simulate: already resolved by a grant
    ul._state[1].gnb_sr_flag = False

    # "A standing grant/BSR path in flight" is bytes_reported > 0 -- state
    # this explicitly rather than leaving it at the BufferModel default.
    # WP9: before that fix, this fixture left bytes_reported at 0, which is
    # not the state the docstring describes but the STALL state (backlogged,
    # nothing reportable, no grant possible). The old single-trigger code
    # could not tell the two apart, so the fixture passed for the wrong
    # reason -- CLAUDE.md's own "any new fixture must include a post-grant
    # state" discipline, caught here on an existing one.
    buffers.state(1, 1).bytes_reported = 100
    buffers.enqueue(1, 1, 50, 0.001)  # buffer was 100 > 0 before this arrival
    ul.on_arrivals({(1, 1): 50}, buffers)
    assert ul._state[1].pending is False


def test_trigger_when_backlogged_but_nothing_reportable():
    """The converse of the test above, and the WP9 trigger's unit-level
    guard: same already-nonempty buffer, but bytes_reported == 0, so there
    is NO standing BSR path -- a regular BSR is pending and no UL-SCH
    resource is available (TS 38.321 sec5.4.4). An SR must arm, or the
    flow is starved permanently (docs/wp9-plan.md sec8b).

    Together these two tests pin the distinction the pre-WP9 code could not
    make: "already nonempty" alone is not a reason to stay silent -- what
    matters is whether anything is reportable.
    """
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    ul = UlAccessModel([_flow(1)], _SLOT_S)

    buffers.enqueue(1, 1, 100, 0.0)
    ul.on_arrivals({(1, 1): 100}, buffers)
    ul._state[1].pending = False
    ul._state[1].gnb_sr_flag = False

    buffers.state(1, 1).bytes_reported = 0   # the stall: nothing reportable
    buffers.enqueue(1, 1, 50, 0.001)
    ul.on_arrivals({(1, 1): 50}, buffers)
    assert ul._state[1].pending is True


def test_trigger_when_stalled_even_with_no_arrival_this_slot():
    """The committed fix evaluates the second trigger EVERY slot, not only
    on slots carrying an arrival -- deliberately broader than the worktree
    diagnostic that first demonstrated the defect (docs/wp9-plan.md sec8c).

    The spec conditions the SR on the pending BSR and the absent grant, not
    on new data, so a flow that stalls and then goes quiet must still
    recover. A diagnostic-shaped implementation (new test nested under the
    `arrived <= 0` skip) passes every other test in this file and fails
    this one.
    """
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    ul = UlAccessModel([_flow(1)], _SLOT_S)

    buffers.enqueue(1, 1, 100, 0.0)
    ul.on_arrivals({(1, 1): 100}, buffers)
    ul._state[1].pending = False
    ul._state[1].gnb_sr_flag = False
    buffers.state(1, 1).bytes_reported = 0

    ul.on_arrivals({}, buffers)              # no arrival at all this slot
    assert ul._state[1].pending is True


def test_tick_fires_sr_on_the_next_occasion_and_sets_gnb_flag():
    """Once pending, the next SR occasion (period/offset) transmits: counter
    increments, the prohibit timer arms, and the gNB flag sets -- mirrors
    `trigger_periodic_scheduling_request` + `nr_ue_get_SR`'s success path
    (`nr_ue_procedures.c:2569-2650`)."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    ul = UlAccessModel(flows, _SLOT_S, sr_period_slots=5, sr_offset_slots=3)

    buffers.enqueue(1, 1, 200, 0.0)
    ul.on_arrivals({(1, 1): 200}, buffers)

    for slot in range(3):  # occasions are slots 3, 8, 13, ... -- nothing yet
        ul.tick(slot)
        assert ul.sr_report_floor(1) == 0, slot
    ul.tick(3)  # first occasion
    assert ul._state[1].counter == 1
    assert ul._state[1].prohibit_active is True
    assert ul.sr_report_floor(1) > 0


def test_prohibit_timer_suppresses_a_retransmission():
    """Illustrative case (flag #1, WP4 plan): at the real calibration-log
    deployed value (sr_ProhibitTimer=0) the timer never blocks anything --
    `nr_timer_start`/`nr_timer_is_active` (OAI `common/utils/nr/
    nr_common.c:1414-1436`) show it's a plain flag with no minimum-active
    duration. This test uses an explicit non-zero value (5 ms) to
    demonstrate the mechanism actually works, since the real deployed
    value cannot demonstrate it at all."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    # 5 ms at _SLOT_S=0.0005 -> 10 slots.
    ul = UlAccessModel(flows, _SLOT_S, sr_period_slots=1, sr_prohibit_ms=5.0)

    buffers.enqueue(1, 1, 200, 0.0)
    ul.on_arrivals({(1, 1): 200}, buffers)
    ul.tick(0)
    assert ul._state[1].counter == 1  # first transmission fires immediately

    # Occasion recurs every slot (period=1), but the 10-slot prohibit
    # window blocks every retransmission attempt until it expires.
    for slot in range(1, 10):
        ul.tick(slot)
        assert ul._state[1].counter == 1, slot  # suppressed
    ul.tick(10)
    assert ul._state[1].counter == 2  # prohibit window expired, retries


def test_prohibit_timer_is_a_no_op_at_the_real_deployed_value():
    """Companion to the test above: confirms the real deployed value
    (0 ms, the default) produces no suppression window at all -- the
    illustrative 5 ms case above is what a real deployment configuring a
    nonzero value would look like, not what this branch's calibration
    banner actually configures."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    ul = UlAccessModel(flows, _SLOT_S, sr_period_slots=1)  # sr_prohibit_ms defaults to 0.0

    buffers.enqueue(1, 1, 200, 0.0)
    ul.on_arrivals({(1, 1): 200}, buffers)
    ul.tick(0)
    assert ul._state[1].counter == 1
    ul.on_ul_grant(1)  # clear, so the next occasion can attempt again
    ul._state[1].pending = True  # re-arm without a fresh arrival, for the test
    ul.tick(1)
    assert ul._state[1].counter == 1  # would be suppressed if blocked; it isn't


def test_sr_trans_max_exhaustion_falls_back_to_rach():
    """On exhausting sr-TransMax attempts, the UE cancels the pending SR
    and enters a fixed RACH-recovery delay -- mirrors `nr_ue_get_SR`'s
    final branch (`nr_ue_procedures.c:2655-2660`, calls
    `schedule_RA_after_SR_failure`). Full RACH contention is out of scope
    (README §6); only the timing consequence is modelled."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    ul = UlAccessModel(flows, _SLOT_S, sr_period_slots=1, sr_trans_max=3, rach_recovery_ms=1.0)

    buffers.enqueue(1, 1, 200, 0.0)
    ul.on_arrivals({(1, 1): 200}, buffers)

    slot = 0
    for _ in range(3):
        ul.tick(slot)
        assert ul._state[1].rach_recovery_until is None
        ul._state[1].gnb_sr_flag = False  # simulate: never actually granted
        slot += 1
    # 4th attempt: counter (3) >= trans_max (3) -> exhausted, RACH fallback.
    ul.tick(slot)
    assert ul._state[1].pending is False
    assert ul._state[1].counter == 0
    assert ul._state[1].rach_recovery_until is not None
    assert ul.sr_report_floor(1) == 0  # UL-ineligible during recovery

    recovery_slot = ul._state[1].rach_recovery_until
    for s in range(slot + 1, recovery_slot):
        ul.tick(s)
        assert ul._state[1].pending is False, s
    ul.tick(recovery_slot)
    assert ul._state[1].pending is True  # recovery complete, re-armed


def test_on_ul_grant_clears_sr_state():
    """The gNB clears its SR flag the moment it grants any UL resource
    (`sched_ctrl->SR = false`, `gNB_scheduler_ulsch.c:2694`); the UE
    cancels its own pending/counter/timer state too."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    ul = UlAccessModel(flows, _SLOT_S, sr_period_slots=1)

    buffers.enqueue(1, 1, 200, 0.0)
    ul.on_arrivals({(1, 1): 200}, buffers)
    ul.tick(0)
    assert ul.sr_report_floor(1) > 0

    ul.on_ul_grant(1)
    assert ul.sr_report_floor(1) == 0
    assert ul._state[1].pending is False
    assert ul._state[1].counter == 0
    assert ul._state[1].prohibit_active is False


def test_cold_start_rearms_after_a_flow_drains_and_refills():
    """Integration test replacing test_bsr.py's retired
    test_cold_start_probe_rearms_after_a_flow_drains_to_empty: the real
    SR mechanism (bsr.py + ul_access.py together) must re-arm every time a
    flow's real backlog goes from empty back to non-empty, not just once --
    the exact deadlock WP3 documented and WP4 exists to close (README §8)."""
    buffers = BufferModel()
    buffers.register(1, 1, is_ul=True, lcg=0)
    flows = [_flow(1)]
    bsr = BsrModel(flows, _SLOT_S)
    ul = UlAccessModel(flows, _SLOT_S, sr_period_slots=1)

    def cycle(slot_index, arrived_bytes):
        buffers.enqueue(1, 1, arrived_bytes, slot_index * _SLOT_S)
        bsr.on_arrivals({(1, 1): arrived_bytes}, buffers)
        bsr.tick_timers(slot_index)
        ul.on_arrivals({(1, 1): arrived_bytes}, buffers)
        ul.tick(slot_index)
        bsr.broadcast(buffers, ul)

    # First message: cold start from a genuinely empty buffer.
    cycle(0, 300)
    assert buffers.state(1, 1).bytes_reported > 0  # SR fired immediately (period=1)

    # Simulate the crumb grant landing and draining nothing real yet.
    bsr.on_ul_grant(ue_id=1, tb_size=1, delivered_bytes=0, slot_index=1, buffers=buffers)
    ul.on_ul_grant(1)
    bsr.broadcast(buffers, ul)
    # Real BSR now assembled from the still-300-byte true backlog.
    assert buffers.state(1, 1).bytes_reported == bsr._state[1].estimated_ul_buffer

    # Fully drain via a real grant.
    buffers.drain(1, 1, 300)
    bsr.on_ul_grant(ue_id=1, tb_size=300, delivered_bytes=300, slot_index=2, buffers=buffers)
    ul.on_ul_grant(1)
    bsr.broadcast(buffers, ul)
    assert buffers.state(1, 1).bytes_reported == 0

    # New data arrives with no further grant in flight -- must re-arm, not
    # deadlock at the frozen 0.
    cycle(3, 150)
    assert buffers.state(1, 1).bytes_reported > 0


def test_sr_retires_the_cold_start_deadlock_without_it():
    """WP4's acceptance criterion (CLAUDE.md, carried from WP3): with
    BsrModel's cold-start/re-arm probe fully removed, delivery must not
    collapse to the permanent (~0%) deadlock that removing the probe with
    NO replacement produces on a 30-UE sensor scenario -- confirmed here by
    literally comparing against that no-replacement baseline (`ul_access`
    constructed but never engaged), not just asserting a number that could
    coincidentally look plausible.

    This does NOT assert delivery returns all the way to the probe's own
    ~99% -- investigation during this WP found two compounding costs the
    probe's dishonesty hid: (a) SR structurally requires two grant events
    for a cold-start message (a small triggering grant, then a real one)
    where the probe needed one, and (b) once every grant is sized from a
    real (quantised, overestimating) BSR instead of the probe's exact
    true-backlog report, PRB cost per grant roughly doubles. Raising the
    SR-triggered grant's report floor from an initial 1-byte value to 150
    bytes (matching this branch's own established "crumb" definition,
    README/CLAUDE.md) let most small messages complete in the triggering
    grant itself, recovering most of the gap (WP4: ~50% mean -> ~82% mean)
    -- but a residual tie-breaking pattern in PF's own ranking (unmodified
    per Phase 1's no-scheduler-changes constraint: many simultaneously-
    cold UEs score identically, and Python's stable sort always favours
    the same few on ties) still leaves a handful of UEs starved. See
    docs/oai-port-map.md for the full trace. test_sr_preserves_delivery_on_
    the_branch_s_main_scenario below is the fairer, representative check.

    WP5 commit 4b (docs/wp5-plan.md, README.md sec8): the ~82% WP4 figure
    above is no longer what this test measures and the absolute-delivery
    assertion below is loosened accordingly -- HARQ retry's full masking
    (a FIFO-correctness requirement, not a modelling choice) blocks a
    retrying flow from taking a fresh SR-triggered grant for the whole
    retry cycle, which costs more than failing fast does for this
    scenario's small, one-shot-completion traffic. Measured mean dropped
    to ~47%. The SR MECHANISM itself is unaffected and still verified by
    the other two assertions below (retires the deadlock, ~10x over the
    no-SR case) -- only the absolute-delivery bar is loosened, and only
    because the number it used to check no longer means what this
    docstring used to say it means.
    """
    from sim.scenarios import sensor_dense_scenario
    from sim.baselines.pf import ProportionalFair

    sc = sensor_dense_scenario()

    summary_with_sr = run(sc, ProportionalFair(ewma_window_slots=200))
    delivs_with_sr = [summary_with_sr["flows"][k]["delivery_ratio"] for k in summary_with_sr["flows"]]
    mean_with_sr = sum(delivs_with_sr) / len(delivs_with_sr)

    class _NeverFiresUlAccess(UlAccessModel):
        """Stand-in for "the probe was removed and nothing replaced it" --
        never ticks, so sr_report_floor() always returns 0."""

        def on_arrivals(self, *a, **k):
            return

        def tick(self, *a, **k):
            return

    import sim.driver as driver_module

    real_ul_access_cls = driver_module.UlAccessModel
    driver_module.UlAccessModel = _NeverFiresUlAccess
    try:
        sc2 = sensor_dense_scenario()
        summary_no_replacement = run(sc2, ProportionalFair(ewma_window_slots=200))
    finally:
        driver_module.UlAccessModel = real_ul_access_cls
    delivs_no_replacement = [
        summary_no_replacement["flows"][k]["delivery_ratio"] for k in summary_no_replacement["flows"]
    ]
    mean_no_replacement = sum(delivs_no_replacement) / len(delivs_no_replacement)

    assert mean_no_replacement < 0.01, (
        f"sanity check: no-replacement baseline should be the ~0% deadlock, got {mean_no_replacement:.1%}"
    )
    assert mean_with_sr > 10 * max(mean_no_replacement, 0.001), (
        f"SR mean delivery {mean_with_sr:.1%} should be far above the "
        f"no-replacement deadlock {mean_no_replacement:.1%}"
    )
    # WP5 commit 4b: loosened from 0.6 -- guards against the SR mechanism
    # breaking again (a return to something near the no-replacement
    # deadlock), not against a specific absolute-delivery level. HARQ
    # retry's masking now depresses this to ~47% (measured), a real,
    # documented result (README.md sec8, docs/wp5-plan.md commit 4b), not
    # tuned to hide a regression -- 0.4 sits comfortably below the
    # measured value while still catching the mechanism actually failing.
    assert mean_with_sr > 0.4, f"SR mean delivery {mean_with_sr:.1%} too low"


def test_sr_preserves_delivery_on_the_branch_s_main_scenario():
    """The representative check for "delivery survives the probe's
    removal": on factory_robots_scenario (README's main study scenario,
    already PRB-saturated per its own ul_prb_utilization=1.0 -- capacity-
    bound, not access-chain-bound), SR must not meaningfully change
    delivery relative to the WP3 probe baseline. Compares directly at
    runtime against a stubbed no-SR-mechanism baseline (same technique as
    the sensor-scenario test above) rather than a hardcoded number, so the
    test doesn't rot if scenario parameters change."""
    from sim.scenarios import factory_robots_scenario
    from sim.baselines.pf import ProportionalFair

    sc = factory_robots_scenario()
    summary_with_sr = run(sc, ProportionalFair(ewma_window_slots=200))
    delivs_with_sr = [summary_with_sr["flows"][k]["delivery_ratio"] for k in summary_with_sr["flows"]]
    mean_with_sr = sum(delivs_with_sr) / len(delivs_with_sr)

    class _AlwaysReadyUlAccess(UlAccessModel):
        """Approximates the WP3 probe's behaviour for comparison: reports
        immediately (period 1, no prohibit) rather than exercising SR
        timing -- isolates "does SR itself cost anything on a capacity-
        bound scenario" from period-specific effects (already covered by
        the offered-load study's periodicity sweep)."""

        def __init__(self, flows, slot_duration_s, **kwargs):
            kwargs["sr_period_slots"] = 1
            kwargs["sr_prohibit_ms"] = 0.0
            super().__init__(flows, slot_duration_s, **kwargs)

    import sim.driver as driver_module

    real_ul_access_cls = driver_module.UlAccessModel
    driver_module.UlAccessModel = _AlwaysReadyUlAccess
    try:
        sc2 = factory_robots_scenario()
        summary_fast_sr = run(sc2, ProportionalFair(ewma_window_slots=200))
    finally:
        driver_module.UlAccessModel = real_ul_access_cls
    delivs_fast_sr = [summary_fast_sr["flows"][k]["delivery_ratio"] for k in summary_fast_sr["flows"]]
    mean_fast_sr = sum(delivs_fast_sr) / len(delivs_fast_sr)

    assert abs(mean_with_sr - mean_fast_sr) < 0.05, (
        f"SR ({mean_with_sr:.1%}) vs fast-SR ({mean_fast_sr:.1%}) delivery "
        f"should be close on a capacity-bound scenario -- SR's own timing "
        f"shouldn't matter when PRBs, not access latency, are the limit"
    )
    assert mean_with_sr > 0.6, f"delivery {mean_with_sr:.1%} unexpectedly low for this scenario"


# -- WP9: the never-empties stall -----------------------------------------


def test_sr_rearms_for_a_flow_whose_backlog_never_empties():
    """The deadlock WP9's arm-divergence investigation found
    (docs/wp9-plan.md sec8b), and the reason this module needed a second
    SR trigger.

    `on_arrivals`' empty->non-empty test is the ONLY pre-WP9 trigger, so a
    flow whose backlog never returns to zero can never raise another SR.
    That matters because `bytes_reported` is
    `max(0, estimated_ul_buffer - sched_ul_bytes)`: once `sched_ul_bytes`
    overruns the estimate -- which the crumb-collapse gate is designed to
    allow -- it clamps to 0, and `sched_ul_bytes` resets only inside
    `BsrModel.on_ul_grant`, which needs a grant, which needs
    `bytes_reported > 0`. `BsrModel.pending` re-arms correctly every 5ms
    and cannot help: nothing can consume it.

    TS 38.321 sec5.4.4 triggers an SR on a pending regular BSR with no
    UL-SCH resource available -- exactly the missing valve.

    Traced pre-fix at this configuration: the flow stalls at slot 14 and
    never recovers, backlog growing monotonically to 184,989 bytes by slot
    799 with zero further grants. Asserted on BACKLOG rather than on
    utilisation, so the test states the failure the user would see (a flow
    that stops being served) rather than a threshold that could drift.
    """
    from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
    from sim.baselines.pf import ProportionalFair

    scenario = ScenarioConfig(
        name="wp9_never_empties",
        horizon_slots=800,
        carrier=CarrierConfig(bandwidth_hz=40_000_000, numerology=2),
        tdd=TDDConfig(pattern="DSUUU"),
        ues=[UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=2000)],
        # 20 kB every 20 ms = 8 Mbps offered, on a ~110 Mbps carrier: the
        # cell is nowhere near capacity, so anything but near-full delivery
        # here is the access chain, not contention.
        flows=[FlowConfig(
            ue_id=1, qfi=9, direction="UL", flow_class="PF", pdb_ms=300.0,
            traffic_kind="deterministic",
            traffic_params={"period_ms": 20.0, "bytes_per_period": 20_000},
        )],
        seed=1,
    )
    summary = run(scenario, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8)
    flow = summary["flows"]["ue1_qfi9"]

    # Pre-fix this reads ~0.03; the flow is starved from slot 14 onward.
    assert flow["delivery_ratio"] > 0.5, (
        f"UL flow starved by the SR-trigger gap: delivered "
        f"{flow['bytes_delivered']} of {flow['bytes_arrived']} bytes "
        f"({flow['delivery_ratio']:.3f}) on an uncongested carrier"
    )
