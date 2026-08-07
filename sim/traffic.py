from dataclasses import dataclass

import numpy as np

from .buffer import BufferModel
from .config import FlowConfig


@dataclass
class _FlowState:
    cfg: FlowConfig
    # Current offered rate for a rate-adaptive source (bps). None for the
    # open-loop kinds, whose rate is fixed by their traffic params.
    rate_bps: float | None = None
    # Bytes delivered to this flow since the source last adapted.
    delivered_since_adapt: int = 0
    # Bytes offered since the source last adapted.
    offered_since_adapt: int = 0


class TrafficModel:
    def __init__(
        self,
        flows: list[FlowConfig],
        buffers: BufferModel,
        slot_duration_s: float,
        rng: np.random.Generator,
    ) -> None:
        self.flows = [_FlowState(cfg=f) for f in flows]
        self._state_of = {(s.cfg.ue_id, s.cfg.qfi): s for s in self.flows}
        self.buffers = buffers
        self.slot_duration_s = slot_duration_s
        self.rng = rng
        for f in flows:
            buffers.register(f.ue_id, f.qfi, is_ul=(f.direction == "UL"))

    def observe_delivery(self, per_flow_delivered: dict) -> None:
        """Feed delivered bytes back to rate-adaptive sources.

        Called by the driver once per slot. Open-loop sources ignore it; an
        ``adaptive`` source uses it to decide whether to raise or lower its
        offered rate, which is what makes the *demand* a moving target for
        Tier-1 to estimate rather than a constant it can be handed.
        """
        for state in self.flows:
            if state.rate_bps is None:
                continue
            state.delivered_since_adapt += per_flow_delivered.get(
                (state.cfg.ue_id, state.cfg.qfi), 0
            )

    def _adapt(self, state: _FlowState) -> None:
        """One control step of a rate-adaptive source.

        Deliberately generic. The canonical case is a TCP-like congestion
        loop, but the same shape covers an adaptive video encoder backing off
        when the radio cannot carry its bitrate, or a UE-side application
        rate controller. What matters for the scheduler is only that offered
        load *responds to service*, so demand and allocation form a closed
        loop whose period can beat against the Tier-1 window.

        Multiplicative decrease when the link is not carrying what is
        offered, additive increase when it is -- AIMD, the standard shape.
        """
        p = state.cfg.traffic_params
        lo = float(p.get("min_rate_bps", 1e5))
        hi = float(p.get("max_rate_bps", 50e6))
        served_ratio = (
            state.delivered_since_adapt / state.offered_since_adapt
            if state.offered_since_adapt > 0 else 1.0
        )
        if served_ratio < float(p.get("backoff_threshold", 0.95)):
            state.rate_bps *= float(p.get("decrease_factor", 0.7))
        else:
            state.rate_bps += float(p.get("increase_bps", 1e6))
        state.rate_bps = min(hi, max(lo, state.rate_bps))
        state.delivered_since_adapt = 0
        state.offered_since_adapt = 0

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

        if kind == "adaptive":
            state = self._state_of[(cfg.ue_id, cfg.qfi)]
            if state.rate_bps is None:
                state.rate_bps = float(p.get("initial_rate_bps",
                                             p.get("max_rate_bps", 10e6)))
            period_slots = max(
                1, int(p.get("adapt_period_ms", 1000.0) / 1000.0
                       / self.slot_duration_s)
            )
            if slot_index > 0 and slot_index % period_slots == 0:
                self._adapt(state)
            mean_bytes = (state.rate_bps / 8.0) * self.slot_duration_s
            byts = int(self.rng.poisson(mean_bytes))
            state.offered_since_adapt += byts
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
