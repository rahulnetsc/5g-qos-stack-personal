from ..buffer import BufferModel
from ..channel import ChannelModel
from scheduler import Allocation, FlowConfig, bits_per_prb, cce_aggregation_level
from ..resource import SlotGrid


class ProportionalFair:
    """Standard PF: M_i = r_inst_i / R_avg_i, multi-UE per slot via greedy fill.

    R_avg is an EWMA over per-slot delivered bits. Decays for all flows every slot
    (whether scheduled or not), and increments for scheduled flows by their expected
    delivery (post-BLER).
    """

    def __init__(self, ewma_window_slots: int = 200) -> None:
        self.window = max(1, ewma_window_slots)
        self._flows: list[FlowConfig] = []
        # Smoothed throughput per (ue, qfi), units: bits per slot.
        self._r_avg: dict[tuple[int, int], float] = {}

    def configure(self, flows, slot_duration_s, grid) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        # Initialize to a small positive value to avoid division-by-zero in the metric.
        self._r_avg = {(f.ue_id, f.qfi): 1.0 for f in flows}

    def allocate(
        self, slot: SlotGrid, buffers: BufferModel, channel: ChannelModel
    ) -> list[Allocation]:
        decay = 1.0 - 1.0 / self.window
        for key in self._r_avg:
            self._r_avg[key] *= decay

        out: list[Allocation] = []
        if slot.dl_symbols > 0:
            out.extend(self._allocate(slot, buffers, channel, "DL"))
        if slot.ul_symbols > 0:
            out.extend(self._allocate(slot, buffers, channel, "UL"))
        return out

    def _allocate(
        self,
        slot: SlotGrid,
        buffers: BufferModel,
        channel: ChannelModel,
        direction: str,
    ) -> list[Allocation]:
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        scored: list[tuple[float, FlowConfig, int, float]] = []
        for f in self._flows:
            if f.direction != direction:
                continue
            if buffers.state(f.ue_id, f.qfi).bytes_queued <= 0:
                continue
            snr = channel.get_snr_db(f.ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue
            r_avg = max(1.0, self._r_avg[(f.ue_id, f.qfi)])
            metric = bits_per_rb / r_avg
            scored.append((metric, f, bits_per_rb, bler))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)

        prbs_left = slot.prb_count
        cce_left = slot.pdcch_cce_budget
        increment = 1.0 / self.window
        out: list[Allocation] = []

        for _metric, f, bits_per_rb, bler in scored:
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(channel.get_snr_db(f.ue_id))
            if cce_left < cce_cost:
                # Try lower-AL flows further down the list; don't break.
                continue
            backlog_bytes = buffers.state(f.ue_id, f.qfi).bytes_queued
            prbs_needed = (backlog_bytes * 8 + bits_per_rb - 1) // bits_per_rb
            prbs_used = min(prbs_left, max(1, prbs_needed))
            bytes_capacity = min(backlog_bytes, (prbs_used * bits_per_rb) // 8)
            if bytes_capacity <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            expected_delivered_bits = bytes_capacity * 8 * (1.0 - bler)
            self._r_avg[(f.ue_id, f.qfi)] += increment * expected_delivered_bits

            out.append(
                Allocation(
                    ue_id=f.ue_id,
                    qfi=f.qfi,
                    direction=direction,
                    prbs=prbs_used,
                    bytes_capacity=bytes_capacity,
                    cce_cost=cce_cost,
                    is_sps=False,
                )
            )
        return out
