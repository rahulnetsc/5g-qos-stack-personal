from ..buffer import BufferModel
from ..channel import ChannelModel, bits_per_prb, cce_aggregation_level
from ..config import FlowConfig
from ..resource import SlotGrid
from . import Allocation


class RoundRobin:
    """Cycles through eligible (UE, QFI) flows. One flow per direction per slot."""

    def __init__(self) -> None:
        self._flows: list[FlowConfig] = []
        self._dl_cursor = 0
        self._ul_cursor = 0

    def configure(self, flows, slot_duration_s, grid) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s

    def allocate(
        self, slot: SlotGrid, buffers: BufferModel, channel: ChannelModel
    ) -> list[Allocation]:
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
        eligible = [
            f for f in self._flows
            if f.direction == direction
            and buffers.state(f.ue_id, f.qfi).bytes_queued > 0
        ]
        if not eligible:
            return []

        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        if direction == "DL":
            self._dl_cursor = (self._dl_cursor + 1) % len(eligible)
            chosen = eligible[self._dl_cursor]
        else:
            self._ul_cursor = (self._ul_cursor + 1) % len(eligible)
            chosen = eligible[self._ul_cursor]

        snr = channel.get_snr_db(chosen.ue_id)
        bits_per_rb, _bler = bits_per_prb(snr, symbols=symbols)
        if bits_per_rb <= 0:
            return []

        backlog_bytes = buffers.state(chosen.ue_id, chosen.qfi).bytes_queued
        full_capacity_bytes = (bits_per_rb * slot.prb_count) // 8
        bytes_capacity = min(full_capacity_bytes, backlog_bytes)

        # Right-size PRBs to the smaller of backlog or full grid.
        prbs_used = min(
            slot.prb_count,
            max(1, (bytes_capacity * 8 + bits_per_rb - 1) // bits_per_rb),
        )

        return [
            Allocation(
                ue_id=chosen.ue_id,
                qfi=chosen.qfi,
                direction=direction,
                prbs=prbs_used,
                bytes_capacity=bytes_capacity,
                cce_cost=cce_aggregation_level(snr),
                is_sps=False,
            )
        ]
