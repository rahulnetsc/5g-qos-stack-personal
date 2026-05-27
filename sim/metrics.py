"""Simulation metrics -- arrival, delivery, HARQ, HoL delay, PRB utilisation.

HARQ additions (feat/harq-bler-retx)
--------------------------------------
Two new per-flow counters:

    bytes_harq_retx  -- bytes that required at least one retransmission
                        (first TX NACK'd; the bytes were eventually delivered
                        or abandoned on a later attempt).
    bytes_harq_lost  -- bytes abandoned after MAX_RETX failures.
                        These were drained from the buffer on first TX but
                        never confirmed as received.

New summary keys per flow:
    harq_retx_bytes   raw count
    harq_loss_bytes   raw count
    harq_retx_ratio   bytes_harq_retx / bytes_arrived  (retx pressure)
    harq_loss_ratio   bytes_harq_lost  / bytes_arrived  (unrecoverable loss)

New system-level summary key:
    harq_enabled      bool -- True when the HARQEngine was active this run.
"""

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class FlowMetrics:
    bytes_arrived: int = 0
    bytes_delivered: int = 0
    bytes_dropped: int = 0
    # HARQ counters (feat/harq-bler-retx)
    bytes_harq_retx: int = 0   # bytes that needed ≥1 retransmission
    bytes_harq_lost: int = 0   # bytes abandoned after MAX_RETX
    hol_delay_samples_s: list = field(default_factory=list)


class Metrics:
    def __init__(self, record_timeseries: bool = False) -> None:
        self._flow: dict[tuple[int, int], FlowMetrics] = defaultdict(FlowMetrics)
        self._dl_prbs_used = 0
        self._ul_prbs_used = 0
        self._dl_prbs_total = 0
        self._ul_prbs_total = 0
        self._cce_used = 0
        self._cce_total = 0
        self._harq_enabled: bool = False   # set by run() when HARQEngine active

        # Per-slot time series (opt-in to keep memory footprint small).
        self.record_ts = record_timeseries
        self._ts_slot_index: list[int] = []
        self._ts_time_s: list[float] = []
        self._ts_per_flow: dict[tuple[int, int], dict[str, list]] = {}
        self._ts_system: dict[str, list] = {
            "dl_prbs_used": [],
            "ul_prbs_used": [],
            "dl_prbs_avail": [],
            "ul_prbs_avail": [],
            "cce_used": [],
            "cce_budget": [],
        }

    # ------------------------------------------------------------------
    # Existing record methods (unchanged)
    # ------------------------------------------------------------------

    def record_arrival(self, ue_id: int, qfi: int, byts: int) -> None:
        self._flow[(ue_id, qfi)].bytes_arrived += byts

    def record_delivery(self, ue_id: int, qfi: int, byts: int) -> None:
        self._flow[(ue_id, qfi)].bytes_delivered += byts

    def record_dropped(self, ue_id: int, qfi: int, byts: int) -> None:
        self._flow[(ue_id, qfi)].bytes_dropped += byts

    def record_hol_delay(self, ue_id: int, qfi: int, delay_s: float) -> None:
        if delay_s > 0:
            self._flow[(ue_id, qfi)].hol_delay_samples_s.append(delay_s)

    def record_grid_capacity(self, dl_prbs: int, ul_prbs: int) -> None:
        self._dl_prbs_total += dl_prbs
        self._ul_prbs_total += ul_prbs

    def record_prb_use(self, direction: str, prbs: int) -> None:
        if direction == "DL":
            self._dl_prbs_used += prbs
        else:
            self._ul_prbs_used += prbs

    def record_cce(self, used: int, total: int) -> None:
        self._cce_used += used
        self._cce_total += total

    # ------------------------------------------------------------------
    # HARQ record methods (feat/harq-bler-retx)
    # ------------------------------------------------------------------

    def set_harq_enabled(self, enabled: bool) -> None:
        """Called once by run() so the summary can report harq_enabled."""
        self._harq_enabled = enabled

    def record_harq_retx(self, ue_id: int, qfi: int, byts: int) -> None:
        """Record bytes that are being retransmitted (first TX NACK'd)."""
        self._flow[(ue_id, qfi)].bytes_harq_retx += byts

    def record_harq_loss(self, ue_id: int, qfi: int, byts: int) -> None:
        """Record bytes abandoned after MAX_RETX failures."""
        self._flow[(ue_id, qfi)].bytes_harq_lost += byts

    # ------------------------------------------------------------------
    # Snapshot (unchanged)
    # ------------------------------------------------------------------

    def snapshot_slot(
        self,
        *,
        slot_index: int,
        time_s: float,
        buffers,
        slot_grid,
        per_flow_delivered: dict[tuple[int, int], int],
        per_flow_arrived: dict[tuple[int, int], int],
        per_flow_dropped: dict[tuple[int, int], int],
        dl_prbs_used: int,
        ul_prbs_used: int,
        cce_used: int,
    ) -> None:
        if not self.record_ts:
            return
        self._ts_slot_index.append(slot_index)
        self._ts_time_s.append(time_s)
        for key in buffers.keys():
            ts = self._ts_per_flow.setdefault(
                key,
                {
                    "backlog_bytes": [],
                    "hol_delay_s": [],
                    "delivered_bytes": [],
                    "arrived_bytes": [],
                    "dropped_bytes": [],
                },
            )
            ts["backlog_bytes"].append(buffers.state(*key).bytes_queued)
            ts["hol_delay_s"].append(buffers.hol_delay_s(*key, time_s))
            ts["delivered_bytes"].append(per_flow_delivered.get(key, 0))
            ts["arrived_bytes"].append(per_flow_arrived.get(key, 0))
            ts["dropped_bytes"].append(per_flow_dropped.get(key, 0))
        self._ts_system["dl_prbs_used"].append(dl_prbs_used)
        self._ts_system["ul_prbs_used"].append(ul_prbs_used)
        self._ts_system["dl_prbs_avail"].append(
            slot_grid.prb_count if slot_grid.dl_symbols > 0 else 0
        )
        self._ts_system["ul_prbs_avail"].append(
            slot_grid.prb_count if slot_grid.ul_symbols > 0 else 0
        )
        self._ts_system["cce_used"].append(cce_used)
        self._ts_system["cce_budget"].append(slot_grid.pdcch_cce_budget)

    def timeseries(self) -> dict:
        if not self.record_ts:
            return {}
        return {
            "slot_index": list(self._ts_slot_index),
            "time_s": list(self._ts_time_s),
            "per_flow": {
                f"ue{ue}_qfi{qfi}": dict(series)
                for (ue, qfi), series in self._ts_per_flow.items()
            },
            "system": dict(self._ts_system),
        }

    @staticmethod
    def _percentile(samples: list[float], p: float) -> float:
        if not samples:
            return 0.0
        s = sorted(samples)
        k = min(len(s) - 1, int(len(s) * p))
        return s[k]

    def summary(self, horizon_s: float) -> dict:
        out = {
            "horizon_s": horizon_s,
            "harq_enabled": self._harq_enabled,
            "dl_prb_utilization": self._dl_prbs_used / max(1, self._dl_prbs_total),
            "ul_prb_utilization": self._ul_prbs_used / max(1, self._ul_prbs_total),
            "cce_utilization": self._cce_used / max(1, self._cce_total),
            "flows": {},
        }
        for (ue_id, qfi), m in sorted(self._flow.items()):
            tput_bps = (m.bytes_delivered * 8) / horizon_s if horizon_s > 0 else 0.0
            arr_bps  = (m.bytes_arrived  * 8) / horizon_s if horizon_s > 0 else 0.0
            arrived  = max(1, m.bytes_arrived)
            out["flows"][f"ue{ue_id}_qfi{qfi}"] = {
                "bytes_arrived":    m.bytes_arrived,
                "bytes_delivered":  m.bytes_delivered,
                "bytes_dropped":    m.bytes_dropped,
                "harq_retx_bytes":  m.bytes_harq_retx,
                "harq_loss_bytes":  m.bytes_harq_lost,
                "throughput_bps":   round(tput_bps, 1),
                "offered_bps":      round(arr_bps, 1),
                "delivery_ratio":   round(m.bytes_delivered / arrived, 4),
                "harq_retx_ratio":  round(m.bytes_harq_retx / arrived, 4),
                "harq_loss_ratio":  round(m.bytes_harq_lost  / arrived, 4),
                "hol_p50_ms":  round(
                    self._percentile(m.hol_delay_samples_s, 0.50) * 1000, 3),
                "hol_p95_ms":  round(
                    self._percentile(m.hol_delay_samples_s, 0.95) * 1000, 3),
                "hol_p99_ms":  round(
                    self._percentile(m.hol_delay_samples_s, 0.99) * 1000, 3),
            }
        return out
