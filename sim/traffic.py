from dataclasses import dataclass

import numpy as np

from .buffer import BufferModel
from .config import FlowConfig


@dataclass
class _FlowState:
    cfg: FlowConfig


class TrafficModel:
    def __init__(
        self,
        flows: list[FlowConfig],
        buffers: BufferModel,
        slot_duration_s: float,
        rng: np.random.Generator,
    ) -> None:
        self.flows = [_FlowState(cfg=f) for f in flows]
        self.buffers = buffers
        self.slot_duration_s = slot_duration_s
        self.rng = rng
        for f in flows:
            buffers.register(f.ue_id, f.qfi)

    def generate(self, slot_index: int) -> list[tuple[int, int, int]]:
        """Generate arrivals for this slot. Returns list of (ue_id, qfi, bytes)."""
        now_s = slot_index * self.slot_duration_s
        arrivals: list[tuple[int, int, int]] = []
        for state in self.flows:
            cfg = state.cfg
            for ts, byts in self._gen(cfg, slot_index, now_s):
                if byts > 0:
                    self.buffers.enqueue(cfg.ue_id, cfg.qfi, byts, ts)
                    arrivals.append((cfg.ue_id, cfg.qfi, byts))
        return arrivals

    def _gen(
        self, cfg: FlowConfig, slot_index: int, now_s: float
    ) -> list[tuple[float, int]]:
        kind = cfg.traffic_kind
        p = cfg.traffic_params

        if kind == "deterministic":
            period_slots = max(1, int(p["period_ms"] / 1000.0 / self.slot_duration_s))
            if slot_index % period_slots == 0:
                return [(now_s, int(p["bytes_per_period"]))]
            return []

        if kind == "poisson":
            mean_bytes = (p["rate_bps"] / 8.0) * self.slot_duration_s
            byts = int(self.rng.poisson(mean_bytes))
            return [(now_s, byts)] if byts > 0 else []

        if kind == "video_frame":
            period_slots = max(1, int(p.get("period_ms", 16.67) / 1000.0 / self.slot_duration_s))
            slot_offset = int(p.get("slot_offset", 0))
            if (slot_index - slot_offset) % period_slots != 0 or slot_index < slot_offset:
                return []
            frame_idx = (slot_index - slot_offset) // period_slots
            i_period = int(p.get("i_frame_period_in_frames", 60))
            i_phase = int(p.get("i_frame_phase", 0))
            i_mult = float(p.get("i_frame_multiplier", 5.0))
            mult = i_mult if ((frame_idx + i_phase) % i_period == 0) else 1.0
            size = int(p["avg_bytes"] * mult)
            return [(now_s, size)]

        raise ValueError(f"Unknown traffic kind: {kind}")
