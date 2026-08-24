from collections import defaultdict

import numpy as np

from .bsr import BsrModel
from .buffer import BufferModel
from .channel import ChannelModel
from .config import ScenarioConfig
from .harq import HarqAwareBufferView, HarqProcessPool, ReducedSlotView, draw_harq_outcome
from .messages import FrameLedger, MessageLedger, message_latency_percentiles_ms
from .metrics import Metrics
from .resource import ResourceGrid
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
    )
    buffers = BufferModel()
    bsr = BsrModel(scenario.flows, grid.slot_duration_s)
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
    metrics = Metrics(record_timeseries=record_timeseries)
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

    for slot_index in range(scenario.horizon_slots):
        ue_lcp.refill(grid.slot_duration_s)
        now_s = slot_index * grid.slot_duration_s

        per_flow_arrived: dict[tuple[int, int], int] = defaultdict(int)
        for ue_id, qfi, byts in traffic.generate(slot_index):
            metrics.record_arrival(ue_id, qfi, byts)
            per_flow_arrived[(ue_id, qfi)] += byts

        channel.update(slot_index)
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
        masked_buffers = HarqAwareBufferView(buffers, harq_pool, direction_by_flow)

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
                    alloc.ue_id, alloc.bytes_capacity, 0, slot_index, buffers
                )
                ul_access.on_ul_grant(alloc.ue_id)
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
    summary["harq_masked_flow_double_grant_count"] = harq_masked_flow_double_grant_count
    # WP7: true per-message completion latency, replacing the head-of-line
    # proxy for M01/M15 (config/metric_panel.yml). Computed per flow from
    # the message ledger and merged into the same per-flow summary dict the
    # proxy fields already live in -- RunRecord.from_summary picks both up.
    for f in scenario.flows:
        key = f"ue{f.ue_id}_qfi{f.qfi}"
        if key not in summary["flows"]:
            continue  # flow generated no traffic at all this run
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
    if record_timeseries:
        summary["timeseries"] = metrics.timeseries()
    return summary
