from ..buffer import BufferModel
from ..channel import ChannelModel
from scheduler import Allocation, FlowConfig, bits_per_prb, cce_aggregation_level
from ..resource import SlotGrid
from ._mac import emit_grant


class RoundRobin:
    """Cycles through eligible UEs. One UE per direction per slot; that UE
    is granted a single transport block (one DCI), which the MAC
    multiplexer fills across the UE's flows."""

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
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols

        # Group this direction's backlogged flows by UE.
        ue_flows: dict[int, list[FlowConfig]] = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            # Eligibility uses the BSR-visible (bytes_reported) view: the
            # scheduler cannot serve a UL flow it hasn't yet been told
            # about. For DL / no-BSR-delay flows this equals bytes_queued.
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            ue_flows.setdefault(f.ue_id, []).append(f)
        if not ue_flows:
            return []

        eligible = sorted(ue_flows)
        if direction == "DL":
            self._dl_cursor = (self._dl_cursor + 1) % len(eligible)
            chosen = eligible[self._dl_cursor]
        else:
            self._ul_cursor = (self._ul_cursor + 1) % len(eligible)
            chosen = eligible[self._ul_cursor]

        snr = channel.get_snr_db(chosen)
        bits_per_rb, _bler = bits_per_prb(snr, symbols=symbols)
        if bits_per_rb <= 0:
            return []

        flows = ue_flows[chosen]
        # Grant sizing uses the BSR-visible view -- that is what the gNB
        # would base the grant on. The MAC LCP fill (emit_grant) then
        # actually fills the granted TB from real bytes_queued.
        ue_backlog = sum(
            buffers.state(f.ue_id, f.qfi).bytes_reported for f in flows
        )
        # Right-size PRBs to the smaller of BSR-view backlog or full grid.
        prbs_needed = (ue_backlog * 8 + bits_per_rb - 1) // bits_per_rb
        prbs_used = min(slot.prb_count, max(1, prbs_needed))
        tbs_bytes = min(ue_backlog, (prbs_used * bits_per_rb) // 8)
        if tbs_bytes <= 0:
            return []

        return emit_grant(
            chosen,
            direction,
            prbs_used,
            tbs_bytes,
            flows,
            buffers,
            cce_cost=cce_aggregation_level(snr),
        )
