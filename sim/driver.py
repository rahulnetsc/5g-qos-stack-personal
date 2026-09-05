from collections import defaultdict
from typing import Callable, Optional

import numpy as np

from .bsr import BsrModel
from .buffer import BufferModel
from .channel import ChannelModel
from .config import ScenarioConfig
from .harq import HarqAwareBufferView, HarqProcessPool, ReducedSlotView, draw_harq_outcome
from .join import JoinAwareBufferView, JoinPhase, init_join_rng_streams, init_join_state, rrc_connected
from .join import step as join_step
from .messages import FrameLedger, Message, MessageLedger, message_latency_percentiles_ms
from .metrics import Metrics
from .resource import ResourceGrid
from .rlf import RlfDetectorConfig, RlfDetectorState
from .rlf import step as rlf_step
from .trace import GrantSink, GrantTrace
from .ue_lcp import UeLcp
from .ul_access import UlAccessModel
from scheduler import Scheduler
from .traffic import TrafficModel


def run(
    scenario: ScenarioConfig,
    scheduler: Scheduler,
    record_timeseries: bool = False,
    cqi_delay_slots: int = 0,
    cqi_loss_rate: float = 0.0,
    sr_period_slots: int = 10,
    sr_offset_slots: int = 0,
    k1_slots: int = 4,
    k2_slots: int = 2,
    harq_round_max: int = 4,
    harq_combining_mode: str = "ir",
    truncated_bsr: str = "off",
    window_slots: Optional[int] = None,
    window_sink: Optional[Callable[[int, list], None]] = None,
    timeseries_resolution: str = "slot",
    grant_sink: Optional[GrantSink] = None,
    attach_seed_slots: Optional[dict[int, int]] = None,
    rejoin_seed_bsr: bool = False,
) -> dict:
    """Run one scenario through one scheduler.

    Uplink Buffer Status Reports are modelled by ``sim/bsr.py::BsrModel``:
    per-LCG, quantised, riding on a UL grant. Configured Grants (SPS)
    bypass BSR entirely (they read ``bytes_queued`` directly). The uplink
    access chain (SR -> grant -> BSR -> grant, ``sim/ul_access.py``) is
    what makes a flow with no BSR evidence and real backlog reportable at
    all -- see that module's docstring. ``sr_period_slots`` /
    ``sr_offset_slots`` have no ground truth (README §8); exposed here so
    a study can sweep them rather than fixing a silent default.

    ``cqi_delay_slots`` / ``cqi_loss_rate`` model the UE-to-gNB Channel
    Quality Indicator report on the *downlink* -- ChannelModel exposes a
    delayed ``get_reported_snr_db(ue)`` view that the scheduler consumes
    for MCS picks and grant sizing, while the driver keeps computing BLER
    against the *true* SNR at transmission time. When an Allocation carries
    an ``snr_used_db`` (the SNR the scheduler saw), ``sim/harq.py::
    draw_harq_outcome`` uses the mismatch-BLER curve so an aggressively-
    picked MCS based on stale-optimistic CQI actually costs BLER. Zero
    preserves the old behaviour.

    ``k1_slots``/``k2_slots`` (WP5, docs/wp5-plan.md Decision 3): DL HARQ
    retry gap, in slots (feedback delay + regrant-to-retransmission gap).
    Neither has a single canonical value in real OAI -- k1 is a per-DCI
    selectable {1..8} set, k2 a TDA-row lookup ranging 1-4 slots at this
    deployment's numerology -- so these are swept knobs, not confirmed
    deployed values, same honesty standard as ``sr_period_slots``.
    ``harq_round_max`` (default 4 = 1 original attempt + 3 retries,
    matching ``combining_gain_db``'s table range) is the retry budget
    before a TB is abandoned (residual loss, ``bytes_harq_lost``).
    ``harq_combining_mode`` selects ``combining_gain_db``'s IR (default)
    or Chase table. DL's retry gap is ``k1_slots + k2_slots`` (feedback
    delay + regrant gap); UL's is ``k2_slots`` alone (commit 4b -- the
    gNB already knows the decode outcome the instant it finishes
    decoding, no separate feedback-transit delay to model on that side).
    """
    rng = np.random.default_rng(scenario.seed)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    channel = ChannelModel(
        scenario.ues,
        rng,
        cqi_delay_slots=cqi_delay_slots,
        cqi_loss_rate=cqi_loss_rate,
        # Independent seed so CQI-loss draws don't perturb the AR(1) stream.
        cqi_seed=scenario.seed ^ 0xC9C9C9C9,
        gnb_position=scenario.gnb_position,
        center_freq_ghz=scenario.carrier.center_freq_ghz,
        bandwidth_hz=scenario.carrier.bandwidth_hz,
        # WP6 (docs/wp6-plan.md Decision 2/3): independent seeds for the
        # per-link LOS-realization and shadow-fading draws, same precedent
        # as cqi_seed/harq_rng_dl/harq_rng_ul. Only drawn from for a UE
        # with ``position`` set -- every existing scenario is unaffected.
        los_seed=scenario.seed ^ 0x105105,
        shadow_fading_seed=scenario.seed ^ 0x5FADE5,
        # WP6 commit 2 (docs/wp6-plan.md Decision 3): a fourth independent
        # stream for two-state Markov blockage transitions, only drawn
        # from for a UE with ``blockage`` set.
        blockage_seed=scenario.seed ^ 0x424C4F4B,  # ASCII "BLOK"
    )
    buffers = BufferModel()
    # `truncated_bsr` is exposed here for the same reason sr_period_slots
    # is -- so a study can select it rather than a silent default deciding
    # it. Defaults "off", which is the pre-§18 behaviour the frozen corpus
    # was captured under (docs/wp9-plan.md §18.4).
    bsr = BsrModel(scenario.flows, grid.slot_duration_s,
                   truncated_bsr=truncated_bsr)
    # MODEL C bookkeeping: which UEs have had their attach seed written.
    # A set rather than a counter so the seed is exactly-once per UE by
    # construction, and so the count is derivable for the assertion the
    # map requires (fired == number of UL UEs, not merely non-zero).
    _attach_seeded: set[int] = set()
    #: MODEL C AT THE JOIN EDGES (docs/rejoin-seed-and-desync-registration.md).
    #: Counted per edge kind so "it fired" is distinguishable from "it was
    #: configured", and so the warm path -- which never reaches the RADIO
    #: edge -- cannot be silently unserved by a change aimed at the wrong one.
    _rejoin_seeded = {"app": 0, "radio": 0, "armed": 0}
    #: UEs whose join edge has fired but which had no backlog AT the edge.
    #: The seed ARMS at the edge and FIRES at the first slot the UE actually
    #: has something to report -- the same shape Model C uses at attach, and
    #: for the same reason: an app that has just restarted has not generated
    #: traffic yet, so seeding AT the edge writes zeros and does nothing.
    #: Measured before this was fixed: 7 edges, 7 refusals, 0 seeds.
    _rejoin_pending: dict[int, str] = {}
    ul_access = UlAccessModel(
        scenario.flows,
        grid.slot_duration_s,
        sr_period_slots=sr_period_slots,
        sr_offset_slots=sr_offset_slots,
    )
    # WP7: message identity is purely a scoring-side overlay -- BSR/
    # scheduler code above never reads it. Collected below at the existing
    # drain()/expire() call sites; not yet consumed by Metrics/RunRecord/
    # scorecard (that lands in a later WP7 commit).
    message_ledger = MessageLedger()
    traffic = TrafficModel(
        scenario.flows, buffers, grid.slot_duration_s, rng, ledger=message_ledger
    )
    metrics = Metrics(record_timeseries=record_timeseries,
                      timeseries_resolution=timeseries_resolution)
    # WP5 (docs/wp5-plan.md). Commit 3 landed process-pool gating,
    # provably inert (delivery was still synchronous). Commit 4a made DL
    # retry load-bearing; commit 4b extends it to UL. An Allocation's
    # outcome is a stochastic per-TB draw (real HARQ is binary -- there's
    # no "70% of a TB" to retry), and a FAILED attempt keeps its process
    # busy across slots instead of freeing it same-slot. harq_exhausted_
    # count can genuinely fire (no longer impossible by construction as
    # in commit 3) if a UE has more simultaneously-retrying flows on one
    # direction than that direction's pool capacity -- rare, but no
    # longer structurally ruled out; see harq_allocate_calls alongside
    # it, same reason commit 3 paired them.
    #
    # harq_rng_dl/harq_rng_ul are INDEPENDENT streams from `rng` (channel/
    # traffic) AND from each other, matching the existing cqi_seed=
    # scenario.seed^0xC9C9C9C9 precedent a few lines up -- otherwise
    # introducing HARQ would silently reshuffle draws for flows that
    # never even retry. Commit 4b found this the hard way: sharing ONE
    # harq_rng stream between DL and UL draws (as an earlier version of
    # this commit did) meant adding UL draws shifted the interleaving
    # order of DL draws too, perturbing DL flows' numbers in scenarios
    # with UL traffic even though nothing about DL's own mechanism
    # changed -- confirmed via regression_corpus.py --check showing
    # drift on pure-DL flow keys that 4a's own diff never touched. Two
    # independent streams, not one shared HARQ stream, for the same
    # reason DL/UL are separate directions in every other HARQ structure
    # in this module.
    harq_pool = HarqProcessPool()
    harq_rng_dl = np.random.default_rng(scenario.seed ^ 0x48415251)
    harq_rng_ul = np.random.default_rng(scenario.seed ^ 0x48415251 ^ 0xFFFFFFFF)
    harq_rtt_dl = k1_slots + k2_slots
    # UL's retry gap is k2_slots alone (docs/wp5-plan.md Decision 3,
    # commit 4b docstring above) -- the gNB learns a UL decode outcome
    # immediately (no PUCCH-feedback-style transit delay the way DL's k1
    # models), so only the grant-to-PUSCH gap applies to a retry.
    harq_rtt_ul = k2_slots
    harq_allocate_calls = 0
    harq_exhausted_count = 0
    # Diagnostic only (WP5 commit 4a/4b): should never fire given masking,
    # counted rather than trusted -- see the guard at its increment site.
    harq_masked_flow_double_grant_count = 0
    # WP5 commit 4b: HarqAwareBufferView needs each flow's direction to
    # decide DL-per-flow vs UL-per-UE masking (BufferState itself carries
    # no direction field to read this from).
    direction_by_flow = {(f.ue_id, f.qfi): f.direction for f in scenario.flows}

    scheduler.configure(scenario.flows, grid.slot_duration_s, grid)

    # The UE side of uplink scheduling: the gNB grants a transport block and
    # the UE fills it by its own LCP. Modelled here, not in the scheduler
    # library, because no gNB can do it (TS 38.321 sec 5.4.3.1).
    ue_lcp = UeLcp(scenario.flows)
    ue_flows_by_ue: dict[int, list] = defaultdict(list)
    for _f in scenario.flows:
        if _f.direction == "UL":
            ue_flows_by_ue[_f.ue_id].append(_f)

    pdb_by_flow = {(f.ue_id, f.qfi): f.pdb_ms / 1000.0 for f in scenario.flows}
    horizon_s = scenario.horizon_slots * grid.slot_duration_s

    # WP-Join commit 2 (docs/wp-join-plan.md sec4): sim/rlf.py's detector
    # runs unconditionally for every UE -- sync-loss DETECTION is a
    # property of every real UE, not an opt-in feature; it's the
    # CONSEQUENCES (WP-Join commit 5's gate) that stay opt-in. No new
    # UEConfig field -- one RlfDetectorConfig (its own cited defaults,
    # calibration-logs/twotier_startup_gnb.log:17), one RlfDetectorState
    # per UE, built fresh this run() call like every other per-UE model
    # above (harq_pool/bsr/ul_access). Nothing reads the result yet --
    # rlf_step_calls/rlf_declared_count are diagnostic-only, same idiom as
    # harq_allocate_calls below, and deliberately not threaded into
    # RunRecord.
    rlf_config = RlfDetectorConfig()
    rlf_states: dict[int, RlfDetectorState] = {ue.ue_id: RlfDetectorState() for ue in scenario.ues}
    rlf_step_calls = 0
    rlf_declared_count = 0

    # WP-Join commit 5 (docs/wp-join-plan.md sec1.3/sec1.4/sec1.6): the
    # radio gate. join_states holds a JoinState ONLY for UEs that opt in
    # via UEConfig.join -- a UE without it is never gated, and rlf.step()
    # keeps running for it exactly as commit 2 left it, unconditionally.
    # One shared set of RNG streams for the whole scenario (D9), matching
    # harq_rng_dl/harq_rng_ul's own per-run, not per-UE, construction.
    join_rngs = init_join_rng_streams(scenario.seed)
    join_states = {ue.ue_id: init_join_state(ue.join) for ue in scenario.ues if ue.join is not None}
    join_configs = {ue.ue_id: ue.join for ue in scenario.ues if ue.join is not None}
    # Per-UE pointer to the JoinEventRecord-shaped dict currently being
    # assembled (plain dicts, not sim.run_record.JoinEventRecord instances
    # -- driver.py stays free of any sim.run_record import, matching the
    # rest of this module's own summary-dict convention; sim/run_record.py
    # ::RunRecord.from_summary does the typed construction, same division
    # of labor as every other summary["flows"][...] field). None means no
    # event is currently in progress for that UE.
    join_active_event: dict[int, dict] = {}
    join_events: list[dict] = []
    # WP-Join commit 6 (docs/wp-join-plan.md sec1.7/D8): the app handshake
    # -- real traffic, a UL request / DL response Message pair, tracked
    # per UE while in progress. join_handshake_complete_this_slot is
    # consumed (popped) by THIS slot's join.step() call but only ever set
    # at the end of a PREVIOUS slot once that slot's own deliveries are
    # known -- the same one-slot lag sec1.8 already accepts for the
    # source gate, for the same reason (delivery outcome isn't known
    # until after scheduler.allocate() runs, which is after join.step()).
    join_handshake_state: dict[int, str] = {}  # "awaiting_ul" | "awaiting_dl"
    join_handshake_ul_sent_ts_s: dict[int, float] = {}
    join_handshake_complete_this_slot: dict[int, bool] = {}
    # WP-Join commit 7 (docs/wp-join-plan.md sec1.9): True iff THIS
    # cycle's path ever passed through JoinPhase.IDLE -- the only way a
    # "reestablish"-triggered cycle ends up needing a FULL reset instead
    # of "mac": t311/t301 expiry falls back to a full re-attach (real
    # hardware retains no context either), even though JoinState.
    # active_path never changes from "reestablish" for this cycle. Reset
    # to False at each new event's own trigger, not just at IDLE entry --
    # a stale True from a PRIOR cycle must never leak into this one's
    # scope decision.
    join_used_idle_fallback: dict[int, bool] = {}

    for slot_index in range(scenario.horizon_slots):
        ue_lcp.refill(grid.slot_duration_s)
        now_s = slot_index * grid.slot_duration_s

        # WP-Join commit 6: the source gate. A UE whose app is off/
        # restarting (warm/cold paths only -- see JoinState.app_running)
        # has its traffic admission suppressed this slot; reestablish
        # never appears here since app_running stays True throughout
        # that path. Read from LAST slot's join_states (join.step() for
        # THIS slot hasn't run yet -- it happens after channel.update()
        # below), the same lag the radio gate already accepts.
        suppressed_ues = frozenset(
            ue_id for ue_id, js in join_states.items() if not js.app_running
        )
        per_flow_arrived: dict[tuple[int, int], int] = defaultdict(int)
        for ue_id, qfi, byts in traffic.generate(slot_index, suppressed_ues=suppressed_ues):
            metrics.record_arrival(ue_id, qfi, byts)
            per_flow_arrived[(ue_id, qfi)] += byts

        channel.update(slot_index)
        # RLF detection reads the TRUE instantaneous SNR (sim/rlf.py's own
        # convention, matching HARQ's), so it must run after channel.
        # update() -- and before the HARQ resolution block below, which is
        # where WP-Join commit 5's gate will eventually need to act on a
        # declared RLF before that slot's retransmissions are serviced
        # (docs/wp-join-plan.md sec1.8). Placed here now so commit 5 can
        # wire its consequence in without moving this call site.
        for ue in scenario.ues:
            join_state = join_states.get(ue.ue_id)
            # WP-Join commit 5: sec1.6's gate table -- detection is
            # meaningless with no serving cell, so a radio-gated UE's
            # rlf.step() is skipped entirely (its RlfDetectorState just
            # sits frozen at whatever it was), not merely ignored after
            # the fact. A UE without join_state (no UEConfig.join set)
            # is always considered connected -- commit 2's exact,
            # unconditional behaviour, unchanged.
            was_connected = join_state is None or rrc_connected(join_state.phase)
            rlf_declared_this_slot = False
            if was_connected:
                rlf_step_calls += 1
                rlf_result = rlf_step(
                    rlf_states[ue.ue_id], rlf_config, channel.get_snr_db(ue.ue_id),
                    slot_index, grid.slot_duration_s,
                )
                rlf_declared_this_slot = rlf_result.rlf_declared_this_slot
                if rlf_declared_this_slot:
                    rlf_declared_count += 1

            if join_state is None:
                continue

            prior_phase = join_state.phase
            prior_phase_elapsed = join_state.phase_elapsed_slots
            prior_active_path = join_state.active_path
            jres = join_step(
                join_state, join_configs[ue.ue_id], join_rngs, slot_index, grid.slot_duration_s,
                rlf_declared_this_slot=rlf_declared_this_slot,
                snr_db=channel.get_snr_db(ue.ue_id),
                # WP-Join commit 6: real signal, set at the end of a
                # PREVIOUS slot once that slot's own DL handshake-response
                # delivery was confirmed (see the handshake-progression
                # block after scheduler.allocate() below) -- popped so it
                # only ever fires the one slot it's meant for.
                handshake_complete=join_handshake_complete_this_slot.pop(ue.ue_id, False),
            )
            if was_connected and not rrc_connected(join_state.phase):
                # Just entered a radio-gated state this slot -- flush
                # pending HARQ before it can keep consuming retx PRBs/CCE
                # through the outage (sec1.4/sec2b).
                harq_pool.flush_ue(ue.ue_id)
            # MODEL C AT THE JOIN EDGES -- off unless `rejoin_seed_bsr`.
            #
            # WHY BOTH EDGES, and this is the whole point of the change:
            # `radio_connected_this_slot` does NOT fire on the warm path
            # (the driver's own comment below says so -- the radio never
            # drops for an app restart), and the warm path is the one G9's
            # count guard fails on. Seeding only at the radio edge would
            # have produced a change that provably could not affect the
            # clause it was built for.
            #
            # The warm path reaches the same fault by a different door: the
            # app stops, backlog drains, a BSR fires with no active LCG, and
            # `_assemble` memsets `estimated_ul_buffer_per_lcg` and returns
            # early on fmt=="none" -- leaving it all zero while the app
            # restarts and real backlog returns.
            #
            # THIS IS A MECHANISM CHANGE, NOT A SCENARIO TREATMENT, because
            # the trigger is an internal FSM edge rather than a
            # caller-supplied schedule. Its justification is the one Model C
            # already rests on: real hardware grants during attach and
            # re-establishment (RACH msg3, then RRC signalling on SRB) and
            # those grants carry BSRs. This simulator has no RA procedure
            # and no SRB traffic (`has_srb` is hardcoded False), so a
            # re-attaching UE never receives a grant hardware would always
            # give it. The seed supplies the EFFECT of an input the deployed
            # system has and the sim lacks; it changes no scheduler, no
            # ranking and no ported constant.
            if rejoin_seed_bsr and (jres.app_connected_this_slot
                                    or jres.radio_connected_this_slot):
                _rejoin_pending[ue.ue_id] = (
                    "app" if jres.app_connected_this_slot else "radio")
                _rejoin_seeded["armed"] += 1

            if jres.radio_connected_this_slot:
                # Re-arm: a fresh RlfDetectorState, constructed exactly
                # here, at the instant rrc_connected flips true (sec1.6) --
                # sim/rlf.py itself never un-declares RLF or resets on its
                # own; this is WP-Join's job, done with the tools sim/
                # rlf.py's own docstring names, not an extension of it.
                rlf_states[ue.ue_id] = RlfDetectorState()

                # WP-Join commit 7 (sec1.9): fresh per-UE MAC/BSR/SR/LCP
                # state on every reconnection, cold or reestablished --
                # both restart the UL access chain. Scope for the
                # SCHEDULER's own fairness ledger differs: "mac" (true
                # reestablishment, context retained) leaves it alone;
                # "full" (cold attach, or a reestablishment that itself
                # fell back through IDLE) clears it. A path never
                # touching JoinPhase.IDLE this cycle is the true-
                # reestablish case; active_path=="cold" or having
                # touched IDLE is "full" -- warm never reaches here at
                # all (radio never drops).
                bsr.reset_ue(ue.ue_id, slot_index)
                ul_access.reset_ue(ue.ue_id)
                ue_lcp.reset_ue(ue.ue_id)
                scheduler_reset_ue = getattr(scheduler, "reset_ue", None)
                if scheduler_reset_ue is not None:
                    scope = (
                        "full"
                        if join_state.active_path == "cold" or join_used_idle_fallback.get(ue.ue_id, False)
                        else "mac"
                    )
                    scheduler_reset_ue(ue.ue_id, scope, buffers)

            # Event-log assembly (M18/M19, config/metric_panel.yml).
            # Ordering matters: look up the event that was ALREADY active
            # going into this call (before any new one this same call
            # might create) -- otherwise a brand-new event immediately
            # "absorbs" its own triggering transition's prior phase
            # (CONNECTED, the idle/waiting state, not a procedure phase)
            # as if it were a segment inside itself. Found and fixed
            # exactly this way while verifying the real path against
            # commit 4's synthetic-fixture assumptions (docs/wp-join-
            # plan.md "Commit 5 -- landed", review point 1).
            active_event = join_active_event.get(ue.ue_id)
            if active_event is not None:
                if jres.snr_restored_this_slot and active_event["rf_restore_slot"] is None:
                    active_event["rf_restore_slot"] = slot_index
                    active_event["rf_restore_ts_s"] = slot_index * grid.slot_duration_s
                # A "segment" of time in prior_phase ends here on EITHER a
                # phase change (success) OR a timer-expiry retry that
                # stays in the SAME phase (RRC_ESTABLISH's own retry never
                # changes state.phase -- checking phase_changed alone
                # would silently drop that segment's duration and its
                # expiry count).
                if jres.phase_changed or jres.timer_expired_this_slot:
                    phase_name = prior_phase.value
                    duration_ms = (prior_phase_elapsed + 1) * grid.slot_duration_s * 1000.0
                    active_event["phases"][phase_name] = (
                        active_event["phases"].get(phase_name, 0.0) + duration_ms
                    )
                    if jres.timer_expired_this_slot:
                        active_event["timer_expiries"][phase_name] = (
                            active_event["timer_expiries"].get(phase_name, 0) + 1
                        )
                if jres.phase_changed and join_state.phase is JoinPhase.APP_HANDSHAKE:
                    # WP-Join commit 6: the app handshake, injected as
                    # REAL traffic (sec1.7/D8) -- a UL request Message
                    # traversing the ordinary buffer/scheduler/HARQ path,
                    # not a sampled delay. jcfg.handshake_ul_qfi is None
                    # (default) reproduces commit 5's exact behaviour --
                    # the UE waits here forever, same as before this
                    # commit landed for any scenario that doesn't opt in.
                    jcfg = join_configs[ue.ue_id]
                    if jcfg.handshake_ul_qfi is not None:
                        handshake_msg = Message(
                            id=message_ledger.new_id(), ue_id=ue.ue_id, qfi=jcfg.handshake_ul_qfi,
                            size_bytes=jcfg.handshake_request_bytes, generation_ts_s=now_s,
                            role="handshake",
                        )
                        buffers.enqueue(
                            ue.ue_id, jcfg.handshake_ul_qfi, jcfg.handshake_request_bytes,
                            now_s, message=handshake_msg,
                        )
                        # Must also count as an "arrival" for THIS slot's
                        # bsr.on_arrivals() call (below, later in this same
                        # slot) to ever see it -- a UL flow's bytes_queued
                        # alone does nothing; every scheduler's eligibility
                        # gate reads bytes_reported, which only BsrModel
                        # sets, only on an arrival event (CLAUDE.md's
                        # standing UL-backlog invariant). DL needs no such
                        # step -- the gNB's own queue view IS bytes_queued.
                        # BOTH ACCOUNTS, not one. The ordinary traffic path
                        # (:254-255) increments metrics.record_arrival AND
                        # per_flow_arrived; this site incremented only the
                        # latter, so the handshake's bytes were DELIVERED and
                        # counted while never being ARRIVED and counted.
                        # Measured before the fix on gt61_warm_rejoin: both
                        # handshake flows read arrived=1, delivered=641,
                        # delivery_ratio 641.00, against 1.00 or below for
                        # every other flow in the run -- so any byte-weighted
                        # statistic over the joiner was unsound, which is the
                        # population G9 exists to measure.
                        metrics.record_arrival(ue.ue_id, jcfg.handshake_ul_qfi,
                                               jcfg.handshake_request_bytes)
                        per_flow_arrived[(ue.ue_id, jcfg.handshake_ul_qfi)] += jcfg.handshake_request_bytes
                        join_handshake_state[ue.ue_id] = "awaiting_ul"
                        join_handshake_ul_sent_ts_s[ue.ue_id] = now_s
                if jres.phase_changed and join_state.phase is JoinPhase.IDLE:
                    # WP-Join commit 7: this cycle fell back to a full
                    # re-attach (t311/t301 expired) -- active_path stays
                    # "reestablish" throughout, so this is the only
                    # record of it, consulted at the radio_connected_
                    # this_slot point above to pick reset_ue's scope.
                    join_used_idle_fallback[ue.ue_id] = True
                if jres.phase_changed and join_state.phase is JoinPhase.CONNECTED:
                    active_event["attached_slot"] = slot_index
                    active_event["attached_ts_s"] = slot_index * grid.slot_duration_s
                    join_active_event[ue.ue_id] = None

            if join_state.active_path is not None and prior_active_path is None:
                join_used_idle_fallback[ue.ue_id] = False
                new_event = {
                    "ue_id": ue.ue_id, "path": join_state.active_path,
                    "trigger_slot": join_state.trigger_slot,
                    "trigger_ts_s": join_state.trigger_slot * grid.slot_duration_s,
                    "rf_restore_slot": None, "rf_restore_ts_s": None,
                    "attached_slot": None, "attached_ts_s": None,
                    "phases": {}, "timer_expiries": {},
                    "rlf_declared_at_slot": (
                        join_state.trigger_slot if join_state.active_path == "reestablish" else None
                    ),
                    "handshake_rtt_ms": None,
                }
                join_active_event[ue.ue_id] = new_event
                join_events.append(new_event)
        # Moved ahead of BSR (WP5 commit 4a): the HARQ resolution step
        # below needs slot_grid.dl_symbols before scheduler.allocate()
        # runs; slot_grid itself never depended on BSR/traffic state.
        slot_grid = grid.slot_grid(slot_index)

        per_flow_delivered: dict[tuple[int, int], int] = defaultdict(int)
        cce_used_this_slot = 0
        dl_prbs_used_this_slot = 0
        ul_prbs_used_this_slot = 0

        # WP5 commit 4a/4b: resolve HARQ processes (DL per-flow, UL
        # per-UE-with-a-stored-split) due this slot BEFORE BSR/scheduler.
        # allocate() -- their PRBs/CCE must be carved out of this slot's
        # budget first (docs/wp5-plan.md Decision 4), and a resolved ACK/
        # exhaustion changes bytes_queued before eligibility is computed.
        retx_prbs_this_slot = 0
        retx_cce_this_slot = 0
        for proc in harq_pool.due_this_slot(slot_index):
            if proc.direction == "DL":
                pdb_s = pdb_by_flow.get((proc.ue_id, proc.qfi), 1.0)
                if buffers.state(proc.ue_id, proc.qfi).bytes_queued < proc.tb_bytes:
                    # Preempted: PDB expiry is the ONLY other thing that
                    # can touch a masked flow's queue while a process is
                    # pending (HarqAwareBufferView) -- if it did, it
                    # already counted the drop via bytes_dropped_pdb.
                    # Free without a second count.
                    harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                    continue
                retx_prbs_this_slot += proc.prbs
                retx_cce_this_slot += proc.cce_cost
                true_snr = channel.get_snr_db(proc.ue_id)
                success = draw_harq_outcome(
                    harq_rng_dl, true_snr, proc.snr_used_db, proc.retx_count,
                    harq_combining_mode, symbols=slot_grid.dl_symbols,
                )
                # RETRANSMISSIONS CARRY PRBs, carved out of the slot before
                # the scheduler sees it -- that is the whole of the camera
                # question's candidate 3, so they are traced, not counted.
                if grant_sink is not None:
                    grant_sink(GrantTrace(
                        slot_index=slot_index, ue_id=proc.ue_id,
                        direction=proc.direction, prbs=proc.prbs,
                        bytes_capacity=proc.tb_bytes, cce_cost=proc.cce_cost,
                        retx_count=proc.retx_count + 1, success=success,
                        split=tuple(getattr(proc, "ul_split", None) or ()),
                        qfi=proc.qfi))
                if success:
                    buffers.drain(proc.ue_id, proc.qfi, proc.tb_bytes, now_s, pdb_s)
                    metrics.record_delivery(proc.ue_id, proc.qfi, proc.tb_bytes)
                    per_flow_delivered[(proc.ue_id, proc.qfi)] += proc.tb_bytes
                    harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                elif proc.retx_count >= harq_round_max - 1:
                    # Exhausted: harq_round_max total attempts (1 original
                    # + (harq_round_max-1) retries) all failed -- residual
                    # loss, a SECOND, distinct discard path from PDB
                    # expiry (sim/buffer.py::discard_harq_loss).
                    buffers.discard_harq_loss(proc.ue_id, proc.qfi, proc.tb_bytes, now_s, pdb_s)
                    harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                else:
                    proc.retx_count += 1
                    proc.due_slot = slot_index + harq_rtt_dl
                # PRBs/CCE are consumed by the attempt regardless of
                # outcome -- matches the unconditional record_prb_use
                # below for new grants.
                metrics.record_prb_use("DL", proc.prbs)
                cce_used_this_slot += proc.cce_cost
                dl_prbs_used_this_slot += proc.prbs
            else:
                # UL (commit 4b): proc.ul_split is the UE's own LCP
                # decision from grant time, replayed verbatim -- never
                # re-split at resolution (docs/wp5-plan.md commit 4b,
                # HarqProcess.ul_split docstring). Preemption is checked
                # PER FLOW in the split, since each has its own buffer/
                # PDB and can be preempted independently of the others.
                remaining_split = [
                    (qfi, byts) for qfi, byts in proc.ul_split
                    if buffers.state(proc.ue_id, qfi).bytes_queued >= byts
                ]
                if not remaining_split:
                    # Every flow in the split was preempted by PDB expiry
                    # -- nothing left to retry, no transmission happens.
                    harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                    continue
                retx_prbs_this_slot += proc.prbs
                retx_cce_this_slot += proc.cce_cost
                true_snr = channel.get_snr_db(proc.ue_id)
                success = draw_harq_outcome(
                    harq_rng_ul, true_snr, proc.snr_used_db, proc.retx_count,
                    harq_combining_mode, symbols=slot_grid.ul_symbols,
                )
                # RETRANSMISSIONS CARRY PRBs, carved out of the slot before
                # the scheduler sees it -- that is the whole of the camera
                # question's candidate 3, so they are traced, not counted.
                if grant_sink is not None:
                    grant_sink(GrantTrace(
                        slot_index=slot_index, ue_id=proc.ue_id,
                        direction=proc.direction, prbs=proc.prbs,
                        bytes_capacity=proc.tb_bytes, cce_cost=proc.cce_cost,
                        retx_count=proc.retx_count + 1, success=success,
                        split=tuple(getattr(proc, "ul_split", None) or ()),
                        qfi=proc.qfi))
                if success:
                    for qfi, byts in remaining_split:
                        pdb_s = pdb_by_flow.get((proc.ue_id, qfi), 1.0)
                        buffers.drain(proc.ue_id, qfi, byts, now_s, pdb_s)
                        metrics.record_delivery(proc.ue_id, qfi, byts)
                        per_flow_delivered[(proc.ue_id, qfi)] += byts
                    # WP5 end-of-WP review fix: this retry's confirmed-
                    # receipt event, decrementing estimated_ul_buffer only
                    # NOW -- it was never called for this TB at its
                    # original (failed) grant time (see the main alloc
                    # loop's now-delivered_bytes=0 on_ul_grant call).
                    bsr.on_ul_confirmed_receipt(
                        proc.ue_id, sum(byts for _, byts in remaining_split)
                    )
                    harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                elif proc.retx_count >= harq_round_max - 1:
                    for qfi, byts in remaining_split:
                        pdb_s = pdb_by_flow.get((proc.ue_id, qfi), 1.0)
                        buffers.discard_harq_loss(proc.ue_id, qfi, byts, now_s, pdb_s)
                    harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                else:
                    proc.retx_count += 1
                    proc.due_slot = slot_index + harq_rtt_ul
                metrics.record_prb_use("UL", proc.prbs)
                cce_used_this_slot += proc.cce_cost
                ul_prbs_used_this_slot += proc.prbs

        # Regular-BSR trigger (arrivals) and periodic/retx timer expiry --
        # both just set `pending`; order between them doesn't matter, only
        # that both run before broadcast()/scheduler.allocate(). SR shares
        # the same arrivals event (on_arrivals) and needs its own per-slot
        # occasion/timer tick before broadcast() asks it for a report.
        bsr.on_arrivals(per_flow_arrived, buffers)
        bsr.tick_timers(slot_index)
        ul_access.on_arrivals(per_flow_arrived, buffers)
        ul_access.tick(slot_index)

        # MODEL C AT THE JOIN EDGES: fire any armed re-join seed for a UE
        # that now has backlog. Armed at the edge (above), fired here --
        # `seed_attach_bsr` refuses an empty buffer rather than writing
        # zeros, and an app that has just restarted has not produced traffic
        # yet, so firing AT the edge is a guaranteed no-op.
        if _rejoin_pending:
            for _ue in list(_rejoin_pending):
                if bsr.seed_attach_bsr(_ue, buffers):
                    _rejoin_seeded[_rejoin_pending.pop(_ue)] += 1

        # MODEL C's attach seed (`docs/attach-path-map.md`), OFF unless
        # `attach_seed_slots` is passed. Fires once per UE, at the first
        # slot at or after its attach slot where it actually has UL
        # backlog -- not at the attach slot unconditionally, because a seed
        # written against an empty buffer is a silent no-op that would look
        # exactly like the treatment failing. Placed immediately before
        # broadcast() so the same slot's bytes_reported already reflects it.
        if attach_seed_slots is not None:
            for _ue, _at in attach_seed_slots.items():
                if slot_index < _at or _ue in _attach_seeded:
                    continue
                if bsr.seed_attach_bsr(_ue, buffers):
                    _attach_seeded.add(_ue)

        # Recompute every UL flow's gNB-visible bytes_reported from the
        # current BsrModel state (B = estimated_ul_buffer - sched_ul_bytes,
        # capped per-LCG) -- must run before the scheduler reads state.
        bsr.broadcast(buffers, ul_access)

        # Ceiling reporting (M11's denominator) uses the REAL, unreduced
        # slot_grid -- retransmissions are a utilization concern, not a
        # reduction of physical capacity.
        metrics.record_grid_capacity(
            dl_prbs=slot_grid.prb_count if slot_grid.dl_symbols > 0 else 0,
            ul_prbs=slot_grid.prb_count if slot_grid.ul_symbols > 0 else 0,
        )

        # WP5 commit 4a (Decision 4): new-data allocation sees a
        # PRB/CCE-reduced slot and a buffer view masking any flow with a
        # pending HARQ process -- zero scheduler-side changes, both
        # wrappers only need the right attributes (structural typing,
        # scheduler/interfaces.py).
        reduced_slot_grid = ReducedSlotView(slot_grid, retx_prbs_this_slot, retx_cce_this_slot)
        # WP-Join commit 5: JoinAwareBufferView composed OUTERMOST over
        # HarqAwareBufferView (docs/wp-join-plan.md sec1.4) -- a radio-
        # gated UE's mask strictly subsumes a per-flow HARQ-pending mask,
        # so nesting order doesn't affect correctness, only which
        # docstring a future reader meets first. A no-op wrapper (join_
        # states is empty) for every scenario with no UEConfig.join set.
        masked_buffers = JoinAwareBufferView(
            HarqAwareBufferView(buffers, harq_pool, direction_by_flow), join_states
        )

        for alloc in scheduler.allocate(reduced_slot_grid, masked_buffers, channel):
            if alloc.bytes_capacity <= 0:
                continue

            harq_direction = "UL" if alloc.ue_grant else "DL"
            harq_qfi = -1 if alloc.ue_grant else alloc.qfi

            # Defensive guard, counted not just trusted (WP5 commit 4a/
            # 4b): masking should already make an already-pending flow
            # ineligible (DL per-flow, UL per-UE); this only fires if some
            # scheduler grants one anyway, which would otherwise
            # double-book the same bytes (README.md sec8's SPS finding).
            if harq_pool.is_pending(alloc.ue_id, harq_direction, harq_qfi):
                harq_masked_flow_double_grant_count += 1
                continue

            harq_allocate_calls += 1
            harq_proc = harq_pool.allocate(
                alloc.ue_id, harq_direction, alloc.bytes_capacity, slot_index,
                qfi=harq_qfi, prbs=alloc.prbs, cce_cost=alloc.cce_cost,
                snr_used_db=alloc.snr_used_db,
            )
            if harq_proc is None:
                # Reachable in principle now (unlike commit 3): the pool
                # is shared across a UE's flows, and masking only makes
                # ONE flow ineligible at a time, not the whole pool.
                # Counted, not enforced -- this grant simply can't be
                # tracked or delivered; see harq_allocate_calls alongside
                # it to tell "binding" from "never wired up".
                harq_exhausted_count += 1
                continue
            alloc.harq_pid = harq_proc.pid

            if alloc.ue_grant:
                # Uplink: WP5 commit 4b. Same binary-outcome reasoning as
                # DL (commit 4a) -- there is no "70% of a TB" to retry.
                # The UE's own LCP decides the split AT TRANSMISSION TIME
                # regardless of eventual outcome (a real UE fills the
                # whole granted TB before it knows whether decode will
                # succeed -- TS 38.321 sec5.4.3.1) and that decision is
                # never redone at resolution time (HarqProcess.ul_split
                # docstring). This also fixes a pre-4b fidelity bug: LCP
                # used to be fed the BLER-discounted `delivered` amount
                # instead of the full bytes_capacity, under-filling the TB
                # relative to real UE behaviour and double-counting BLER.
                symbols = slot_grid.ul_symbols
                true_snr = channel.get_snr_db(alloc.ue_id)
                success = draw_harq_outcome(
                    harq_rng_ul, true_snr, alloc.snr_used_db, retx_count=0,
                    mode=harq_combining_mode, symbols=symbols,
                )
                ue_split = ue_lcp.fill(
                    ue_flows_by_ue.get(alloc.ue_id, []), alloc.bytes_capacity, buffers
                )
                # BSR: if pending, assemble/quantise a report from the true
                # current per-LCG backlog; always credit sched_ul_bytes and
                # restart the retx timer -- see sim/bsr.py::BsrModel.
                # on_ul_grant. Fires at GRANT time regardless of eventual
                # HARQ outcome (matches real OAI: sched_ul_bytes credits
                # every grant). delivered_bytes=0 here on purpose (WP5
                # end-of-WP review fix): the SDU-receipt decrement of
                # estimated_ul_buffer must wait for CONFIRMED delivery --
                # see on_ul_confirmed_receipt below, called only once
                # success is known, not unconditionally at grant time.
                ue_filled_bytes = sum(byts for _, byts in ue_split)
                bsr.on_ul_grant(
                    alloc.ue_id, alloc.bytes_capacity, 0, slot_index, buffers,
                    # Occupancy, for truncated-BSR format selection
                    # (docs/wp9-plan.md §18). Read only when the model's
                    # `truncated_bsr` is not "off"; passing it is inert
                    # otherwise, which is what keeps the corpus frozen.
                    filled_bytes=ue_filled_bytes,
                )
                ul_access.on_ul_grant(alloc.ue_id)
                # THE GRANT STREAM (sim/trace.py). One pointer comparison
                # when no sink is attached; every value below is one the
                # driver already holds, so attaching a sink cannot change
                # what the run does.
                if grant_sink is not None:
                    grant_sink(GrantTrace(
                        slot_index=slot_index, ue_id=alloc.ue_id,
                        direction="UL", prbs=alloc.prbs,
                        bytes_capacity=alloc.bytes_capacity,
                        cce_cost=alloc.cce_cost, retx_count=0,
                        success=success, split=tuple(ue_split)))
                if success:
                    for qfi, byts in ue_split:
                        pdb_s = pdb_by_flow.get((alloc.ue_id, qfi), 1.0)
                        buffers.drain(alloc.ue_id, qfi, byts, now_s, pdb_s)
                        metrics.record_delivery(alloc.ue_id, qfi, byts)
                        per_flow_delivered[(alloc.ue_id, qfi)] += byts
                    bsr.on_ul_confirmed_receipt(alloc.ue_id, ue_filled_bytes)
                    harq_pool.free(alloc.ue_id, harq_direction, harq_proc.pid)
                else:
                    harq_proc.retx_count = 1
                    harq_proc.due_slot = slot_index + harq_rtt_ul
                    harq_proc.ul_split = ue_split
                    # Stays busy -- resolved by a later slot's
                    # due_this_slot() pass, above, at the top of this loop.
            else:
                # Downlink: WP5 commit 4a. Real HARQ is a per-TB binary
                # decode outcome, not a continuous fraction -- there is no
                # "70% of a TB." A success drains NOW, at the same slot a
                # pre-4a success would have (the k1 feedback delay is when
                # the *gNB* learns the outcome, not when the *receiver*
                # has the data) -- so a first-try success is identical in
                # timing to before. Only a failure persists the process
                # for a retry harq_rtt_dl slots later.
                symbols = slot_grid.dl_symbols
                true_snr = channel.get_snr_db(alloc.ue_id)
                success = draw_harq_outcome(
                    harq_rng_dl, true_snr, alloc.snr_used_db, retx_count=0,
                    mode=harq_combining_mode, symbols=symbols,
                )
                if grant_sink is not None:
                    grant_sink(GrantTrace(
                        slot_index=slot_index, ue_id=alloc.ue_id,
                        direction="DL", prbs=alloc.prbs,
                        bytes_capacity=alloc.bytes_capacity,
                        cce_cost=alloc.cce_cost, retx_count=0,
                        success=success, qfi=alloc.qfi))
                if success:
                    pdb_s = pdb_by_flow.get((alloc.ue_id, alloc.qfi), 1.0)
                    buffers.drain(alloc.ue_id, alloc.qfi, alloc.bytes_capacity, now_s, pdb_s)
                    metrics.record_delivery(alloc.ue_id, alloc.qfi, alloc.bytes_capacity)
                    per_flow_delivered[(alloc.ue_id, alloc.qfi)] += alloc.bytes_capacity
                    harq_pool.free(alloc.ue_id, harq_direction, harq_proc.pid)
                else:
                    harq_proc.retx_count = 1
                    harq_proc.due_slot = slot_index + harq_rtt_dl
                    # Stays busy -- resolved by a later slot's
                    # due_this_slot() pass, above, at the top of this loop.

            # PRBs/CCE are consumed by the attempt regardless of whether
            # it succeeded -- unchanged from pre-4a (which already applied
            # this unconditionally, independent of the bler outcome).
            metrics.record_prb_use(alloc.direction, alloc.prbs)
            cce_used_this_slot += alloc.cce_cost
            if alloc.direction == "DL":
                dl_prbs_used_this_slot += alloc.prbs
            else:
                ul_prbs_used_this_slot += alloc.prbs
        metrics.record_cce(cce_used_this_slot, slot_grid.pdcch_cce_budget)
        # Close the loop for rate-adaptive sources: their offered load
        # responds to what they actually got.
        traffic.observe_delivery(per_flow_delivered)

        # WP-Join commit 6: handshake progression. Must run here, AFTER
        # this slot's deliveries are fully known (scheduler.allocate()
        # already ran) -- checked via per_flow_delivered, already
        # computed this slot at zero extra cost, on the assumption a
        # small (deterministic-size) handshake message delivers whole in
        # the one slot any of its bytes deliver at all (true for any
        # grant sized above a few dozen bytes). Setting join_handshake_
        # complete_this_slot here means it's consumed by join.step() on
        # the NEXT slot, not this one -- the same one-slot lag as the
        # source gate, for the same reason (sec1.8).
        for hs_ue_id, hs_state in list(join_handshake_state.items()):
            hs_cfg = join_configs[hs_ue_id]
            if hs_state == "awaiting_ul" and per_flow_delivered.get((hs_ue_id, hs_cfg.handshake_ul_qfi), 0) > 0:
                response_msg = Message(
                    id=message_ledger.new_id(), ue_id=hs_ue_id, qfi=hs_cfg.handshake_dl_qfi,
                    size_bytes=hs_cfg.handshake_response_bytes, generation_ts_s=now_s,
                    role="handshake",
                )
                buffers.enqueue(
                    hs_ue_id, hs_cfg.handshake_dl_qfi, hs_cfg.handshake_response_bytes,
                    now_s, message=response_msg,
                )
                # The DL response reached NEITHER account. Both are credited
                # here, after the enqueue, so the flow's arrived bytes match
                # what was actually offered to it.
                #
                # per_flow_arrived is still live at this point in the slot --
                # it is read by the per-slot timeseries recorder below
                # (:763). It is NOT read by bsr.on_arrivals (:539), which
                # already ran, and that is correct rather than a lag: BSR is
                # an uplink mechanism and this is a downlink flow.
                metrics.record_arrival(hs_ue_id, hs_cfg.handshake_dl_qfi,
                                       hs_cfg.handshake_response_bytes)
                per_flow_arrived[(hs_ue_id, hs_cfg.handshake_dl_qfi)] += hs_cfg.handshake_response_bytes
                join_handshake_state[hs_ue_id] = "awaiting_dl"
            elif hs_state == "awaiting_dl" and per_flow_delivered.get((hs_ue_id, hs_cfg.handshake_dl_qfi), 0) > 0:
                active_event = join_active_event.get(hs_ue_id)
                if active_event is not None:
                    active_event["handshake_rtt_ms"] = (
                        (now_s - join_handshake_ul_sent_ts_s[hs_ue_id]) * 1000.0
                    )
                join_handshake_complete_this_slot[hs_ue_id] = True
                del join_handshake_state[hs_ue_id]

        per_flow_dropped: dict[tuple[int, int], int] = defaultdict(int)
        for ue_id, qfi in buffers.keys():
            pdb_s = pdb_by_flow.get((ue_id, qfi), 1.0)
            dropped = buffers.expire(now_s, pdb_s, ue_id, qfi)
            if dropped > 0:
                metrics.record_dropped(ue_id, qfi, dropped)
                per_flow_dropped[(ue_id, qfi)] = dropped
            metrics.record_hol_delay(
                ue_id, qfi, buffers.hol_delay_s(ue_id, qfi, now_s)
            )
            for completion in buffers.pop_completions(ue_id, qfi):
                message_ledger.record(completion)

        # WP9 G11 commit 2 -- windowed eviction. Hand each window's
        # completions to the consumer and let them go, so a 30-minute soak
        # retains one window rather than the whole run (docs/wp9-plan.md
        # §37). Boundary is END-OF-WINDOW: slot_index+1 so the window
        # [0, window_slots) closes at slot_index == window_slots-1.
        if window_sink is not None and window_slots:
            if (slot_index + 1) % window_slots == 0:
                window_sink((slot_index + 1) // window_slots - 1,
                            message_ledger.drain())

        metrics.snapshot_slot(
            slot_index=slot_index,
            time_s=now_s,
            buffers=buffers,
            slot_grid=slot_grid,
            per_flow_delivered=per_flow_delivered,
            per_flow_arrived=per_flow_arrived,
            per_flow_dropped=per_flow_dropped,
            dl_prbs_used=dl_prbs_used_this_slot,
            ul_prbs_used=ul_prbs_used_this_slot,
            cce_used=cce_used_this_slot,
        )

    summary = metrics.summary(horizon_s, buffers)
    # WP5 commits 3/4a/4b: diagnostic counters only, deliberately NOT
    # threaded into RunRecord (RunRecord.from_summary only reads keys it
    # names explicitly -- same idiom as the _ue_lcp/_message_ledger
    # handles below), so regression_corpus.py --check (which snapshots
    # RunRecord.to_dict() only) can't see these. harq_allocate_calls > 0
    # is what distinguishes "gating is live and never binds" from "gating
    # isn't running" -- see sim/tests/test_smoke.py. bytes_harq_lost
    # (per-flow, below in the flows loop) is a real metric field and DOES
    # reach RunRecord -- these three are driver-level wiring diagnostics,
    # a different thing.
    summary["harq_allocate_calls"] = harq_allocate_calls
    summary["harq_exhausted_count"] = harq_exhausted_count
    # MODEL C: emitted ONLY when the attach path is on, so an absent key
    # means "not configured" and a present 0 means "configured and never
    # fired" -- two states this project has repeatedly conflated. Keeping
    # it out of the default summary is also what keeps an off run's summary
    # byte-identical to a pre-Model-C one.
    if rejoin_seed_bsr:
        summary["rejoin_seeds_app"] = _rejoin_seeded["app"]
        summary["rejoin_seeds_radio"] = _rejoin_seeded["radio"]
        summary["rejoin_seeds_armed"] = _rejoin_seeded["armed"]
        summary["rejoin_seeds_still_pending"] = len(_rejoin_pending)
    if attach_seed_slots is not None:
        summary["attach_seeds_fired"] = len(_attach_seeded)
        summary["attach_seeds_expected"] = len(attach_seed_slots)
        summary["attach_seeded_ues"] = sorted(_attach_seeded)
    summary["harq_masked_flow_double_grant_count"] = harq_masked_flow_double_grant_count
    # WP-Join commit 2: same diagnostic-only idiom as the three counters
    # above -- rlf_step_calls confirms the wiring actually ran every slot
    # for every UE (distinguishing "never declares because it's dormant"
    # from "never declares because it's genuinely never triggered");
    # rlf_declared_count is asserted, not assumed, in sim/tests/
    # test_smoke.py (docs/wp-join-plan.md sec4.1 point 4).
    summary["rlf_step_calls"] = rlf_step_calls
    summary["rlf_declared_count"] = rlf_declared_count
    # WP-Join commit 5: always present (possibly empty) from this commit
    # onward, regardless of whether any UE opted into UEConfig.join --
    # this is the signal sim/run_record.py::RunRecord.from_summary uses to
    # tell "predates WP-Join" (key absent, join_events=None) apart from
    # "WP-Join-aware driver, zero events this run" (key present, []),
    # config/metric_panel.yml's own None-vs-[] convention for M18/M19.
    summary["join_events"] = join_events
    # WP7: true per-message completion latency, replacing the head-of-line
    # proxy for M01/M15 (config/metric_panel.yml). Computed per flow from
    # the message ledger and merged into the same per-flow summary dict the
    # proxy fields already live in -- RunRecord.from_summary picks both up.
    windowed_ledger = window_sink is not None and bool(window_slots)
    if windowed_ledger and scenario.horizon_slots % window_slots:
        # THE RESIDUAL WINDOW. Without this, a horizon that is not an exact
        # multiple of window_slots silently loses its last partial window --
        # the consumer would score one window fewer than the run contains
        # and have no way to notice. Emitted only when there IS a residual,
        # so the window count is exactly ceil(horizon / window_slots) and a
        # consumer can assert it against the schedule.
        window_sink(scenario.horizon_slots // window_slots,
                    message_ledger.drain())
    for f in scenario.flows:
        key = f"ue{f.ue_id}_qfi{f.qfi}"
        if key not in summary["flows"]:
            continue  # flow generated no traffic at all this run
        # WP9 G11 commit 2. If a window sink drained the ledger, everything
        # below would be computed over the LAST PARTIAL WINDOW only, and
        # would look like a whole-run number. Percentiles are not
        # associative, so they cannot be reassembled from per-window
        # summaries either -- there is no honest run-level value to emit.
        # Emit None and a reason, per config/metric_panel.yml's rule that a
        # pending metric emits a row rather than being omitted; the windowed
        # consumer holds the real numbers, per window.
        if windowed_ledger:
            fl = summary["flows"][key]
            for fld in ("delay_p50_ms", "delay_p95_ms", "delay_p98_ms",
                        "delay_p99_ms", "message_count"):
                fl[fld] = None
            fl["completion_ts_by_role_s"] = None
            fl["frame_completions"] = None
            fl["message_stats_unavailable_reason"] = (
                "ledger drained per window (window_slots set); run-level "
                "message aggregates are not reconstructible from window "
                "summaries -- score per window instead"
            )
            continue
        completions = message_ledger.completions_for(f.ue_id, f.qfi)
        stats = message_latency_percentiles_ms(completions)
        summary["flows"][key]["delay_p50_ms"] = round(stats["p50"], 3)
        summary["flows"][key]["delay_p95_ms"] = round(stats["p95"], 3)
        summary["flows"][key]["delay_p98_ms"] = round(stats["p98"], 3)
        summary["flows"][key]["delay_p99_ms"] = round(stats["p99"], 3)
        summary["flows"][key]["message_count"] = stats["count"]
        # WP7 commit 4 (M03 liveness_gap_distribution): completion
        # timestamps of fully-delivered messages, grouped by Message.role --
        # a gap distribution needs the actual timestamps, not an aggregate
        # percentile. Dropped messages never arrived at the receiver at all;
        # M02 scores those, not this. T_live thresholding happens in
        # scorecard.py, not here -- this is raw material only.
        by_role: dict[str, list[float]] = {}
        for c in completions:
            if c.complete:
                by_role.setdefault(c.message.role, []).append(c.completion_ts_s)
        for ts_list in by_role.values():
            ts_list.sort()
        summary["flows"][key]["completion_ts_by_role_s"] = by_role
        # WP7 commit 6 (M05 pdu_set_completeness, M06 frame_age_at_mec):
        # group the same completions by frame_id (FrameLedger) rather than
        # refetching from the ledger. total counts every frame this flow
        # generated (xr_video only; 0 for every other kind); complete_ages_ms
        # is the completion age of only the fully-delivered ones -- an
        # incomplete frame has no single arrival instant to report, and
        # M05 (not this) is what scores its failure.
        frames = FrameLedger.group(completions)
        complete_ages_ms = [
            round((fc.completion_ts_s - fc.generation_ts_s) * 1000.0, 3)
            for fc in frames if fc.complete
        ]
        # WP7 commit 7 (M17 frame_freeze_and_effective_fps): the absolute
        # completion timestamps of the same complete frames, sorted -- ages
        # alone can't reconstruct inter-arrival gaps between frames (two
        # frames' ages don't encode the time between their arrivals).
        complete_ts_s = sorted(fc.completion_ts_s for fc in frames if fc.complete)
        summary["flows"][key]["frame_completions"] = {
            "total": len(frames), "complete_ages_ms": complete_ages_ms,
            "complete_ts_s": complete_ts_s,
        }
    # Diagnostic handle on the UE model, so a study can compare the gNB's
    # shadow token buckets against the UE's real ones. Not part of the
    # metrics contract -- see scripts/ul_shadow_study.py.
    summary["_ue_lcp"] = ue_lcp
    # WP7: diagnostic handle, same idiom as _ue_lcp -- not part of the
    # metrics contract. Lets a study inspect raw per-message completions
    # beyond the percentiles already merged into summary["flows"] above.
    summary["_message_ledger"] = message_ledger
    # Tells a consumer the ledger is a TAIL, not the run. Without this a
    # caller cannot distinguish "no messages completed" from "the ones that
    # did were already handed to the window sink".
    summary["_ledger_windowed"] = windowed_ledger
    summary["timeseries_resolution"] = timeseries_resolution
    if record_timeseries:
        summary["timeseries"] = metrics.timeseries()
    return summary
