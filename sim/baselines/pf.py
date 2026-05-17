from ..buffer import BufferModel
from ..channel import ChannelModel
from scheduler import Allocation, FlowConfig, bits_per_prb, cce_aggregation_level
from ..resource import SlotGrid
from ._mac import emit_grant


class ProportionalFair:
    """Standard PF, scheduled per UE: M_ue = r_inst_ue / R_avg_ue, multi-UE
    per slot via greedy fill. Each ranked UE gets one grant (one DCI); its
    transport block is filled across the UE's flows by the MAC multiplexer.

    R_avg is an EWMA over per-slot delivered bits, kept per UE. It decays
    for all UEs every slot (whether granted or not), and increments for
    granted UEs by their expected delivery (post-BLER).
    """

    def __init__(self, ewma_window_slots: int = 200) -> None:
        self.window = max(1, ewma_window_slots)
        self._flows: list[FlowConfig] = []
        # Smoothed throughput per UE, units: bits per slot.
        self._r_avg: dict[int, float] = {}

    def configure(self, flows, slot_duration_s, grid) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        # Initialize to a small positive value to avoid division-by-zero.
        self._r_avg = {f.ue_id: 1.0 for f in flows}

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

        # Group this direction's backlogged flows by UE.
        ue_flows: dict[int, list[FlowConfig]] = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            if buffers.state(f.ue_id, f.qfi).bytes_queued <= 0:
                continue
            ue_flows.setdefault(f.ue_id, []).append(f)
        if not ue_flows:
            return []

        # Score each backlogged UE: instantaneous rate over smoothed rate.
        scored: list[tuple[float, int, list[FlowConfig], int, float]] = []
        for ue_id, flows in ue_flows.items():
            snr = channel.get_snr_db(ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue
            r_avg = max(1.0, self._r_avg[ue_id])
            metric = bits_per_rb / r_avg
            scored.append((metric, ue_id, flows, bits_per_rb, bler))

        if not scored:
            return []
        scored.sort(key=lambda x: x[0], reverse=True)

        prbs_left = slot.prb_count
        cce_left = slot.pdcch_cce_budget
        increment = 1.0 / self.window
        out: list[Allocation] = []

        for _metric, ue_id, flows, bits_per_rb, bler in scored:
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(channel.get_snr_db(ue_id))
            if cce_left < cce_cost:
                # Try lower-AL UEs further down the list; don't break.
                continue
            ue_backlog = sum(
                buffers.state(f.ue_id, f.qfi).bytes_queued for f in flows
            )
            prbs_needed = (ue_backlog * 8 + bits_per_rb - 1) // bits_per_rb
            prbs_used = min(prbs_left, max(1, prbs_needed))
            tbs_bytes = min(ue_backlog, (prbs_used * bits_per_rb) // 8)
            if tbs_bytes <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            expected_delivered_bits = tbs_bytes * 8 * (1.0 - bler)
            self._r_avg[ue_id] += increment * expected_delivered_bits

            out.extend(
                emit_grant(
                    ue_id,
                    direction,
                    prbs_used,
                    tbs_bytes,
                    flows,
                    buffers,
                    cce_cost=cce_cost,
                )
            )
        return out
