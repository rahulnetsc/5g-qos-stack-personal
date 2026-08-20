import math
from collections import defaultdict

import numpy as np

from .bsr import BsrModel
from .buffer import BufferModel
from .channel import ChannelModel, bits_per_prb
from .config import ScenarioConfig
from .metrics import Metrics
from .resource import ResourceGrid
from .ue_lcp import UeLcp
from scheduler import Scheduler, bler_for_mcs, mcs_threshold_for_snr
from .traffic import TrafficModel


def run(
    scenario: ScenarioConfig,
    scheduler: Scheduler,
    record_timeseries: bool = False,
    cqi_delay_slots: int = 0,
    cqi_loss_rate: float = 0.0,
) -> dict:
    """Run one scenario through one scheduler.

    Uplink Buffer Status Reports are modelled by ``sim/bsr.py::BsrModel``:
    per-LCG, quantised, riding on a UL grant. Configured Grants (SPS)
    bypass BSR entirely (they read ``bytes_queued`` directly).

    ``cqi_delay_slots`` / ``cqi_loss_rate`` model the UE-to-gNB Channel
    Quality Indicator report on the *downlink* -- ChannelModel exposes a
    delayed ``get_reported_snr_db(ue)`` view that the scheduler consumes
    for MCS picks and grant sizing, while the driver keeps computing BLER
    against the *true* SNR at transmission time. When an Allocation carries
    an ``snr_used_db`` (the SNR the scheduler saw), the driver uses the
    mismatch-BLER curve ``bler_for_mcs`` so an aggressively-picked MCS
    based on stale-optimistic CQI actually costs BLER. Zero preserves the
    old behaviour.
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
    traffic = TrafficModel(scenario.flows, buffers, grid.slot_duration_s, rng)
    metrics = Metrics(record_timeseries=record_timeseries)

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

        # Regular-BSR trigger (arrivals) and periodic/retx timer expiry --
        # both just set `pending`; order between them doesn't matter, only
        # that both run before broadcast()/scheduler.allocate().
        bsr.on_arrivals(per_flow_arrived, buffers)
        bsr.tick_timers(slot_index)

        # Recompute every UL flow's gNB-visible bytes_reported from the
        # current BsrModel state (B = estimated_ul_buffer - sched_ul_bytes,
        # capped per-LCG) -- must run before the scheduler reads state.
        bsr.broadcast(buffers)

        slot_grid = grid.slot_grid(slot_index)
        metrics.record_grid_capacity(
            dl_prbs=slot_grid.prb_count if slot_grid.dl_symbols > 0 else 0,
            ul_prbs=slot_grid.prb_count if slot_grid.ul_symbols > 0 else 0,
        )

        per_flow_delivered: dict[tuple[int, int], int] = defaultdict(int)
        cce_used_this_slot = 0
        dl_prbs_used_this_slot = 0
        ul_prbs_used_this_slot = 0
        for alloc in scheduler.allocate(slot_grid, buffers, channel):
            if alloc.bytes_capacity <= 0:
                continue
            symbols = (
                slot_grid.dl_symbols if alloc.direction == "DL" else slot_grid.ul_symbols
            )
            true_snr = channel.get_snr_db(alloc.ue_id)
            if math.isnan(alloc.snr_used_db):
                # Legacy path (no MCS-mismatch modelling) -- used by tests
                # that don't set snr_used_db. BLER is the *matched* BLER
                # at the true SNR, as if the scheduler had perfect CQI.
                _, bler = bits_per_prb(true_snr, symbols=symbols)
            else:
                # Mismatch-aware path. The scheduler picked an MCS from
                # ``alloc.snr_used_db`` (its CQI view); the actual BLER is
                # for that MCS at the *true* SNR. If true_snr fell below the
                # picked MCS's threshold since the CQI report was taken, BLER
                # climbs sharply -- the cost of stale-optimistic CQI, and
                # what SPS's conservative MCS margin (see TwoTier) buys
                # protection against.
                mcs_thresh = mcs_threshold_for_snr(alloc.snr_used_db)
                bler = bler_for_mcs(mcs_thresh, true_snr)
            delivered = int(alloc.bytes_capacity * (1.0 - bler))
            if alloc.ue_grant:
                # Uplink: the scheduler sized the block but the UE chooses
                # the split, so apply the UE's own LCP over its *real*
                # backlog. The scheduler's virtual-queue drain used a
                # BSR-based estimate of this split and will differ.
                ue_delivered_bytes = 0
                for qfi, byts in ue_lcp.fill(
                    ue_flows_by_ue.get(alloc.ue_id, []), delivered, buffers
                ):
                    buffers.drain(alloc.ue_id, qfi, byts)
                    metrics.record_delivery(alloc.ue_id, qfi, byts)
                    per_flow_delivered[(alloc.ue_id, qfi)] += byts
                    ue_delivered_bytes += byts
                # BSR: if pending, assemble/quantise a report from the true
                # post-drain per-LCG backlog; always credit sched_ul_bytes
                # and restart the retx timer -- see
                # sim/bsr.py::BsrModel.on_ul_grant.
                bsr.on_ul_grant(
                    alloc.ue_id, alloc.bytes_capacity, ue_delivered_bytes, slot_index, buffers
                )
            else:
                buffers.drain(alloc.ue_id, alloc.qfi, delivered)
                metrics.record_delivery(alloc.ue_id, alloc.qfi, delivered)
                per_flow_delivered[(alloc.ue_id, alloc.qfi)] += delivered
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

    summary = metrics.summary(horizon_s)
    # Diagnostic handle on the UE model, so a study can compare the gNB's
    # shadow token buckets against the UE's real ones. Not part of the
    # metrics contract -- see scripts/ul_shadow_study.py.
    summary["_ue_lcp"] = ue_lcp
    if record_timeseries:
        summary["timeseries"] = metrics.timeseries()
    return summary
