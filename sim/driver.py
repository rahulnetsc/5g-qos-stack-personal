import math
from collections import defaultdict

import numpy as np

from .bsr import BsrModel
from .buffer import BufferModel
from .channel import ChannelModel, bits_per_prb
from .config import ScenarioConfig
from .harq import HarqAwareBufferView, HarqProcessPool, ReducedSlotView, draw_dl_outcome
from .messages import FrameLedger, MessageLedger, message_latency_percentiles_ms
from .metrics import Metrics
from .resource import ResourceGrid
from .ue_lcp import UeLcp
from .ul_access import UlAccessModel
from scheduler import Scheduler, bler_for_mcs, mcs_threshold_for_snr
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
    an ``snr_used_db`` (the SNR the scheduler saw), the driver uses the
    mismatch-BLER curve ``bler_for_mcs`` so an aggressively-picked MCS
    based on stale-optimistic CQI actually costs BLER. Zero preserves the
    old behaviour.

    ``k1_slots``/``k2_slots`` (WP5, docs/wp5-plan.md Decision 3): DL HARQ
    retry gap, in slots (feedback delay + regrant-to-retransmission gap).
    Neither has a single canonical value in real OAI -- k1 is a per-DCI
    selectable {1..8} set, k2 a TDA-row lookup ranging 1-4 slots at this
    deployment's numerology -- so these are swept knobs, not confirmed
    deployed values, same honesty standard as ``sr_period_slots``.
    ``harq_round_max`` (default 4 = 1 original attempt + 3 retries,
    matching ``combining_gain_db``'s table range) is the retry budget
    before a DL TB is abandoned (residual loss, ``bytes_harq_lost``).
    ``harq_combining_mode`` selects ``combining_gain_db``'s IR (default)
    or Chase table. DL only this commit -- UL retry is commit 4b.
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
    # provably inert (delivery was still synchronous). Commit 4a makes DL
    # retry load-bearing: a DL Allocation's outcome is now a stochastic
    # per-TB draw (real HARQ is binary -- there's no "70% of a TB" to
    # retry), and a FAILED attempt keeps its process busy across slots
    # instead of freeing it same-slot. harq_exhausted_count can now
    # genuinely fire (no longer impossible by construction as in commit
    # 3) if a UE has more simultaneously-retrying DL flows than
    # dl_capacity=8 -- rare, but no longer structurally ruled out; see
    # harq_allocate_calls alongside it, same reason commit 3 paired them.
    #
    # harq_rng is an INDEPENDENT stream from `rng` (channel/traffic),
    # matching the existing cqi_seed=scenario.seed^0xC9C9C9C9 precedent a
    # few lines up -- otherwise introducing HARQ would silently reshuffle
    # draws for flows that never even retry.
    harq_pool = HarqProcessPool()
    harq_rng = np.random.default_rng(scenario.seed ^ 0x48415251)
    harq_rtt_dl = k1_slots + k2_slots
    harq_allocate_calls = 0
    harq_exhausted_count = 0
    # Diagnostic only (WP5 commit 4a): should never fire given masking,
    # counted rather than trusted -- see the guard at its increment site.
    harq_masked_flow_double_grant_count = 0

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

        # WP5 commit 4a: resolve DL HARQ processes due this slot BEFORE
        # BSR/scheduler.allocate() -- their PRBs/CCE must be carved out of
        # this slot's budget first (docs/wp5-plan.md Decision 4), and a
        # resolved ACK/exhaustion changes bytes_queued before eligibility
        # is computed. DL only this commit -- due_this_slot() can only
        # return DL entries, since UL never persists across slots yet
        # (commit 3's immediate-free discipline, unchanged for UL below).
        retx_prbs_this_slot = 0
        retx_cce_this_slot = 0
        for proc in harq_pool.due_this_slot(slot_index):
            pdb_s = pdb_by_flow.get((proc.ue_id, proc.qfi), 1.0)
            if buffers.state(proc.ue_id, proc.qfi).bytes_queued < proc.tb_bytes:
                # Preempted: PDB expiry is the ONLY other thing that can
                # touch a masked flow's queue while a process is pending
                # (docs/wp5-plan.md commit 4a's HarqAwareBufferView) -- if
                # it did, it already counted the drop via
                # bytes_dropped_pdb. Free without a second count.
                harq_pool.free(proc.ue_id, proc.direction, proc.pid)
                continue
            retx_prbs_this_slot += proc.prbs
            retx_cce_this_slot += proc.cce_cost
            true_snr = channel.get_snr_db(proc.ue_id)
            success = draw_dl_outcome(
                harq_rng, true_snr, proc.snr_used_db, proc.retx_count,
                harq_combining_mode, symbols=slot_grid.dl_symbols,
            )
            if success:
                buffers.drain(proc.ue_id, proc.qfi, proc.tb_bytes, now_s, pdb_s)
                metrics.record_delivery(proc.ue_id, proc.qfi, proc.tb_bytes)
                per_flow_delivered[(proc.ue_id, proc.qfi)] += proc.tb_bytes
                harq_pool.free(proc.ue_id, proc.direction, proc.pid)
            elif proc.retx_count >= harq_round_max - 1:
                # Exhausted: harq_round_max total attempts (1 original +
                # (harq_round_max-1) retries) all failed -- residual loss,
                # a SECOND, distinct discard path from PDB expiry
                # (sim/buffer.py::discard_harq_loss, docs/wp5-plan.md sec1).
                buffers.discard_harq_loss(proc.ue_id, proc.qfi, proc.tb_bytes, now_s)
                harq_pool.free(proc.ue_id, proc.direction, proc.pid)
            else:
                proc.retx_count += 1
                proc.due_slot = slot_index + harq_rtt_dl
            # PRBs/CCE are consumed by the attempt regardless of outcome --
            # matches the unconditional record_prb_use below for new grants.
            metrics.record_prb_use("DL", proc.prbs)
            cce_used_this_slot += proc.cce_cost
            dl_prbs_used_this_slot += proc.prbs

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
        masked_buffers = HarqAwareBufferView(buffers, harq_pool)

        for alloc in scheduler.allocate(reduced_slot_grid, masked_buffers, channel):
            if alloc.bytes_capacity <= 0:
                continue

            harq_direction = "UL" if alloc.ue_grant else "DL"
            harq_qfi = -1 if alloc.ue_grant else alloc.qfi

            # Defensive guard, counted not just trusted (WP5 commit 4a):
            # masking should already make an already-pending DL flow
            # ineligible; this only fires if some scheduler grants one
            # anyway, which would otherwise double-book the same bytes.
            if harq_direction == "DL" and harq_pool.is_pending(alloc.ue_id, "DL", harq_qfi):
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
                # Uplink: unchanged from commit 3 -- deterministic
                # fractional delivery, immediate drain+free, same slot.
                # UL retry/deferred-drain is commit 4b, not this commit.
                symbols = slot_grid.ul_symbols
                true_snr = channel.get_snr_db(alloc.ue_id)
                if math.isnan(alloc.snr_used_db):
                    _, bler = bits_per_prb(true_snr, symbols=symbols)
                else:
                    mcs_thresh = mcs_threshold_for_snr(alloc.snr_used_db)
                    bler = bler_for_mcs(mcs_thresh, true_snr)
                delivered = int(alloc.bytes_capacity * (1.0 - bler))
                # The scheduler sized the block but the UE chooses the
                # split, so apply the UE's own LCP over its *real*
                # backlog. The scheduler's virtual-queue drain used a
                # BSR-based estimate of this split and will differ.
                ue_delivered_bytes = 0
                for qfi, byts in ue_lcp.fill(
                    ue_flows_by_ue.get(alloc.ue_id, []), delivered, buffers
                ):
                    pdb_s = pdb_by_flow.get((alloc.ue_id, qfi), 1.0)
                    buffers.drain(alloc.ue_id, qfi, byts, now_s, pdb_s)
                    metrics.record_delivery(alloc.ue_id, qfi, byts)
                    per_flow_delivered[(alloc.ue_id, qfi)] += byts
                    ue_delivered_bytes += byts
                # BSR: if pending, assemble/quantise a report from the true
                # post-drain per-LCG backlog; always credit sched_ul_bytes
                # and restart the retx timer -- see
                # sim/bsr.py::BsrModel.on_ul_grant. Fires at GRANT time
                # regardless of eventual HARQ outcome, unchanged by WP5 --
                # real OAI credits sched_ul_bytes on every grant, not on
                # confirmed delivery (docs/wp5-plan.md commit-4b note).
                bsr.on_ul_grant(
                    alloc.ue_id, alloc.bytes_capacity, ue_delivered_bytes, slot_index, buffers
                )
                ul_access.on_ul_grant(alloc.ue_id)
                harq_pool.free(alloc.ue_id, harq_direction, harq_proc.pid)
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
                success = draw_dl_outcome(
                    harq_rng, true_snr, alloc.snr_used_db, retx_count=0,
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
    # WP5 commits 3/4a: diagnostic counters only, deliberately NOT
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
