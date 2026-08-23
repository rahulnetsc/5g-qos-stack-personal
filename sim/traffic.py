from dataclasses import dataclass

import numpy as np

from .buffer import BufferModel
from .config import FlowConfig
from .messages import Message, MessageLedger


def _clipped_gaussian_jitter_ms(
    rng: np.random.Generator, sigma_ms: float, clip_ms: float
) -> float:
    """Zero-mean Gaussian jitter, clamped (not resampled) to ``+/-clip_ms``.

    This is the shape ``docs/p5g-sim-plan.md`` sec9 specifies for the XR video
    generator's arrival jitter (sigma~2ms, clipped to +/-4ms) -- "truncated
    Gaussian... clipped to X" describes clamping, not rejection sampling.
    Shared with ``periodic_control``/``condition_monitor`` (WP7 commit 3)
    rather than inventing a second jitter distribution for control traffic:
    nothing on disk says control-traffic jitter differs in kind from video's,
    only that no sigma/clip value is specified for it. ``sigma_ms=0`` always
    returns 0.0 (deterministic), which is every existing flow's behaviour.
    """
    if sigma_ms <= 0.0:
        return 0.0
    return float(np.clip(rng.normal(0.0, sigma_ms), -clip_ms, clip_ms))


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
        ledger: MessageLedger | None = None,
    ) -> None:
        self.flows = [_FlowState(cfg=f) for f in flows]
        self._state_of = {(s.cfg.ue_id, s.cfg.qfi): s for s in self.flows}
        self.buffers = buffers
        self.slot_duration_s = slot_duration_s
        self.rng = rng
        # Optional (WP7): tags each enqueued chunk with message identity so
        # sim/messages.py can track true per-message completion. None keeps
        # pre-WP7 behaviour exactly -- every existing caller that doesn't
        # pass a ledger is unaffected.
        self.ledger = ledger
        for f in flows:
            buffers.register(f.ue_id, f.qfi, is_ul=(f.direction == "UL"), lcg=f.lcg)

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
            for ts, byts, role in self._gen(cfg, slot_index, now_s):
                if byts > 0:
                    message = None
                    if self.ledger is not None:
                        message = Message(
                            id=self.ledger.new_id(),
                            ue_id=cfg.ue_id,
                            qfi=cfg.qfi,
                            size_bytes=byts,
                            generation_ts_s=ts,
                            role=role,
                        )
                    self.buffers.enqueue(cfg.ue_id, cfg.qfi, byts, ts, message=message)
                    arrivals.append((cfg.ue_id, cfg.qfi, byts))
        return arrivals

    def _gen(
        self, cfg: FlowConfig, slot_index: int, now_s: float
    ) -> list[tuple[float, int, str]]:
        kind = cfg.traffic_kind
        p = cfg.traffic_params

        if kind == "deterministic":
            period_slots = max(1, int(p["period_ms"] / 1000.0 / self.slot_duration_s))
            if slot_index % period_slots == 0:
                return [(now_s, int(p["bytes_per_period"]), "data")]
            return []

        if kind == "poisson":
            mean_bytes = (p["rate_bps"] / 8.0) * self.slot_duration_s
            byts = int(self.rng.poisson(mean_bytes))
            return [(now_s, byts, "data")] if byts > 0 else []

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
            return [(now_s, byts, "data")] if byts > 0 else []

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
            return [(now_s, size, "data")]

        if kind in ("periodic_control", "condition_monitor"):
            # Mechanically identical for both kind names -- the plan doc's
            # traffic-class table (docs/p5g-sim-plan.md sec9) distinguishes
            # them as scenario-authoring concepts (a single command/control
            # flow vs. many low-rate sensors), not as distinct generation
            # mechanisms, and nothing on disk suggests they should generate
            # differently. See docs/wp7-plan.md commit 3.
            return self._gen_periodic_control(cfg, slot_index, now_s)

        if kind in ("aperiodic_event", "machine_vision"):
            # Same reasoning as above: both are a Poisson-triggered single
            # burst (docs/p5g-sim-plan.md sec9's own language -- "triggered
            # burst" -- doesn't name a second triggering mechanism for
            # machine_vision), differing only in configured burst size
            # (tight-PDB small burst vs. large burst).
            return self._gen_poisson_triggered_burst(cfg, slot_index, now_s)

        raise ValueError(f"Unknown traffic kind: {kind}")

    def _gen_periodic_control(
        self, cfg: FlowConfig, slot_index: int, now_s: float
    ) -> list[tuple[float, int, str]]:
        """Deterministic period +/- clipped-Gaussian jitter, per (sub-)stream.

        ``traffic_params["streams"]`` (optional): a list of independently-
        ticking sub-streams sharing this flow's one port, each its own
        ``role``, ``period_ms``, ``bytes``, and optional ``jitter_sigma_ms``/
        ``jitter_clip_ms`` -- this is what lets one UAV telemetry flow model
        MAVLink's 1Hz HEARTBEAT multiplexed with 4-10Hz other streams
        (README sec6), tagging ``Message.role`` per sub-stream so M03 can
        select just one role's messages out of the shared flow. Absent
        ``streams``, falls back to the single-rate top-level params with
        ``role="data"`` -- every pre-WP7 use of this kind (there are none
        yet) and every scenario not opting into multi-role behaves exactly
        the same either way.
        """
        p = cfg.traffic_params
        streams = p.get("streams")
        if streams is None:
            streams = [{
                "role": "data",
                "period_ms": p["period_ms"],
                "bytes": p["bytes_per_period"],
                "jitter_sigma_ms": p.get("jitter_sigma_ms", 0.0),
                "jitter_clip_ms": p.get("jitter_clip_ms"),
            }]

        arrivals: list[tuple[float, int, str]] = []
        for stream in streams:
            period_ms = float(stream["period_ms"])
            period_slots = max(1, int(period_ms / 1000.0 / self.slot_duration_s))
            if slot_index % period_slots != 0:
                continue
            sigma_ms = float(stream.get("jitter_sigma_ms", 0.0))
            clip_ms = stream.get("jitter_clip_ms")
            clip_ms = float(clip_ms) if clip_ms is not None else 2.0 * sigma_ms
            jitter_s = _clipped_gaussian_jitter_ms(self.rng, sigma_ms, clip_ms) / 1000.0
            ts = max(0.0, now_s + jitter_s)
            role = str(stream.get("role", "data"))
            arrivals.append((ts, int(stream["bytes"]), role))
        return arrivals

    def _gen_poisson_triggered_burst(
        self, cfg: FlowConfig, slot_index: int, now_s: float
    ) -> list[tuple[float, int, str]]:
        """A single burst, triggered by a per-slot Bernoulli-thinned Poisson
        process -- the same per-slot-probability approximation the existing
        ``poisson`` kind already uses for its continuous arrivals, applied
        here to *event* triggering instead of byte counts. ``rate_hz`` sets
        the trigger rate; ``burst_bytes`` the (fixed) size of each triggered
        burst. No jitter -- an event's own trigger time already varies.
        """
        p = cfg.traffic_params
        trigger_prob = float(p["rate_hz"]) * self.slot_duration_s
        if self.rng.random() >= trigger_prob:
            return []
        return [(now_s, int(p["burst_bytes"]), "data")]
