from ..buffer import BufferModel
from ..channel import ChannelModel
from scheduler import Allocation, FlowConfig, bits_per_prb, cce_aggregation_level
from ..resource import SlotGrid
from ._mac import emit_grant


class GradientScheduler:
    """Per-class gradient metric with hardcoded urgency weights, scheduled
    per UE.

    Composite metric per UE:
        metric = base_PF_ue * urgency_multiplier_ue

    where base_PF_ue = r_inst_ue / R_avg_ue and the UE's urgency multiplier
    is the largest class-aware multiplier across its backlogged flows -- the
    UE inherits the urgency of its most urgent flow. Per flow class:
      - PF:    multiplier = 1
      - GBR:   1 + gbr_w * max(0, 1 - R_avg_bps / GFBR)
      - Delay: 1 + delay_w * (HoL / PDB) ^ delay_exp   (clamped to HoL/PDB <= 1)

    Each ranked UE gets one grant (one DCI); the MAC multiplexer fills its
    transport block across the UE's flows. R_avg is an EWMA kept per UE, so
    the GBR rate term compares the UE's smoothed throughput against a flow's
    GFBR -- exact for a single-GBR-flow UE, an approximation otherwise (a
    baseline simplification; the two-tier scheduler tracks per-flow virtual
    queues instead).

    This is a simplification of the pure gradient-sum form (Stolyar /
    Lyapunov drift). With Tier-1 disabled, weights are constants; the
    two-tier system lets Tier-1 set per-flow targets dynamically.
    """

    def __init__(
        self,
        ewma_window_slots: int = 200,
        gbr_urgency_weight: float = 5.0,
        delay_urgency_weight: float = 4.0,
        delay_exponent: float = 2.0,
    ) -> None:
        self.window = max(1, ewma_window_slots)
        self.gbr_w = gbr_urgency_weight
        self.delay_w = delay_urgency_weight
        self.delay_exp = delay_exponent
        self._flows: list[FlowConfig] = []
        # bits per slot, EWMA, per UE
        self._r_avg: dict[int, float] = {}
        self.slot_duration_s = 0.0

    def configure(self, flows, slot_duration_s, grid) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        self._r_avg = {f.ue_id: 1.0 for f in flows}

    def allocate(
        self, slot: SlotGrid, buffers: BufferModel, channel: ChannelModel
    ) -> list[Allocation]:
        decay = 1.0 - 1.0 / self.window
        for k in self._r_avg:
            self._r_avg[k] *= decay

        out: list[Allocation] = []
        if slot.dl_symbols > 0:
            out.extend(self._allocate(slot, buffers, channel, "DL"))
        if slot.ul_symbols > 0:
            out.extend(self._allocate(slot, buffers, channel, "UL"))
        return out

    def _urgency_multiplier(
        self, f: FlowConfig, r_avg_bits_per_slot: float, hol_s: float
    ) -> float:
        cls = f.flow_class
        if cls == "PF":
            return 1.0
        if cls == "GBR":
            if f.gfbr_bps <= 0 or self.slot_duration_s <= 0:
                return 1.0
            r_avg_bps = r_avg_bits_per_slot / self.slot_duration_s
            deficit_ratio = max(0.0, 1.0 - r_avg_bps / f.gfbr_bps)
            return 1.0 + self.gbr_w * deficit_ratio
        if cls == "Delay":
            pdb_s = f.pdb_ms / 1000.0
            if pdb_s <= 0 or hol_s <= 0:
                return 1.0
            urgency = min(1.0, hol_s / pdb_s) ** self.delay_exp
            return 1.0 + self.delay_w * urgency
        return 1.0

    def _allocate(
        self,
        slot: SlotGrid,
        buffers: BufferModel,
        channel: ChannelModel,
        direction: str,
    ) -> list[Allocation]:
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        now_s = slot.slot_index * self.slot_duration_s

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

        # Score each backlogged UE: base PF times its most urgent flow.
        scored: list[tuple[float, int, list[FlowConfig], int, float]] = []
        for ue_id, flows in ue_flows.items():
            snr = channel.get_snr_db(ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue
            r_avg = max(1.0, self._r_avg[ue_id])
            base = bits_per_rb / r_avg
            multiplier = 1.0
            for f in flows:
                hol = buffers.hol_delay_s(f.ue_id, f.qfi, now_s)
                multiplier = max(
                    multiplier, self._urgency_multiplier(f, r_avg, hol)
                )
            scored.append((base * multiplier, ue_id, flows, bits_per_rb, bler))

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
