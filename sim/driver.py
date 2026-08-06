from collections import defaultdict

import numpy as np

from .buffer import BufferModel
from .channel import ChannelModel, bits_per_prb
from .config import ScenarioConfig
from .metrics import Metrics
from .resource import ResourceGrid
from scheduler import Scheduler
from .traffic import TrafficModel


def run(
    scenario: ScenarioConfig,
    scheduler: Scheduler,
    record_timeseries: bool = False,
    ul_bsr_delay_slots: int = 0,
    ul_bsr_loss_rate: float = 0.0,
) -> dict:
    """Run one scenario through one scheduler.

    ``ul_bsr_delay_slots`` models the UE-to-gNB Buffer Status Report round
    trip: for each UL flow, the scheduler sees a view of the buffer that
    lags reality by this many slots. Configured Grants / SPS bypass it.
    Zero (the default) preserves the old zero-latency behaviour; a typical
    realistic value at numerology μ=1 (0.5 ms slot) is 8 slots (~4 ms).

    ``ul_bsr_loss_rate`` (0.0-1.0) is the per-slot per-UL-flow probability
    that a BSR update fails to reach the gNB; on a loss the gNB keeps its
    last successfully reported value. Independent of channel BLER; uses a
    dedicated RNG seeded from ``scenario.seed`` for reproducibility.
    """
    rng = np.random.default_rng(scenario.seed)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    channel = ChannelModel(scenario.ues, rng)
    buffers = BufferModel(
        ul_bsr_delay_slots=ul_bsr_delay_slots,
        ul_bsr_loss_rate=ul_bsr_loss_rate,
        # Derive a distinct seed so BSR-loss draws don't perturb the channel
        # / traffic RNG stream when the loss rate is swept.
        bsr_seed=scenario.seed ^ 0xB5B5B5B5,
    )
    traffic = TrafficModel(scenario.flows, buffers, grid.slot_duration_s, rng)
    metrics = Metrics(record_timeseries=record_timeseries)

    scheduler.configure(scenario.flows, grid.slot_duration_s, grid)

    pdb_by_flow = {(f.ue_id, f.qfi): f.pdb_ms / 1000.0 for f in scenario.flows}
    horizon_s = scenario.horizon_slots * grid.slot_duration_s

    for slot_index in range(scenario.horizon_slots):
        now_s = slot_index * grid.slot_duration_s

        per_flow_arrived: dict[tuple[int, int], int] = defaultdict(int)
        for ue_id, qfi, byts in traffic.generate(slot_index):
            metrics.record_arrival(ue_id, qfi, byts)
            per_flow_arrived[(ue_id, qfi)] += byts

        channel.update(slot_index)

        # Advance the UL BSR-delay pipeline so bytes_reported reflects the
        # buffer as seen `ul_bsr_delay_slots` ago -- what a real gNB would
        # know from BSR. No-op when ul_bsr_delay_slots = 0.
        buffers.snapshot_bsr()

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
            _, bler = bits_per_prb(channel.get_snr_db(alloc.ue_id), symbols=symbols)
            delivered = int(alloc.bytes_capacity * (1.0 - bler))
            buffers.drain(alloc.ue_id, alloc.qfi, delivered)
            metrics.record_delivery(alloc.ue_id, alloc.qfi, delivered)
            metrics.record_prb_use(alloc.direction, alloc.prbs)
            per_flow_delivered[(alloc.ue_id, alloc.qfi)] += delivered
            cce_used_this_slot += alloc.cce_cost
            if alloc.direction == "DL":
                dl_prbs_used_this_slot += alloc.prbs
            else:
                ul_prbs_used_this_slot += alloc.prbs
        metrics.record_cce(cce_used_this_slot, slot_grid.pdcch_cce_budget)

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
    if record_timeseries:
        summary["timeseries"] = metrics.timeseries()
    return summary
