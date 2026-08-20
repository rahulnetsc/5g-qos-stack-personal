from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class FlowMetrics:
    bytes_arrived: int = 0
    bytes_delivered: int = 0
    bytes_dropped: int = 0
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

    def record_arrival(self, ue_id: int, qfi: int, byts: int) -> None:
        self._flow[(ue_id, qfi)].bytes_arrived += byts

    def record_delivery(self, ue_id: int, qfi: int, byts: int) -> None:
        self._flow[(ue_id, qfi)].bytes_delivered += byts

    def record_dropped(self, ue_id: int, qfi: int, byts: int) -> None:
        self._flow[(ue_id, qfi)].bytes_dropped += byts

    def record_hol_delay(self, ue_id: int, qfi: int, delay_s: float) -> None:
        # KNOWN ISSUE (flagged, not fixed here -- see WP0 in README.md, and
        # docs/p5g-sim-plan.md sec 5.4 on landing fidelity changes one at a
        # time): this only appends a sample when delay_s > 0. A message
        # fully drained within the same slot it arrived produces
        # hol_delay_s() == 0.0 and is silently excluded, not recorded as a
        # zero. That means fast, successfully-served messages never
        # contribute a sample, biasing hol_p50/p95/p98/p99 worse than the
        # true delay distribution for lightly-loaded flows -- worst at low
        # load, which is exactly the regime WP4's SR-chain calibration
        # target cares about. Left as-is so scripts/regression_corpus.py's
        # baseline snapshot matches today's published numbers exactly;
        # fixing this is recommended as the *next* isolated change, scored
        # by its own regression diff, not bundled into WP0.
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
        """Record one per-slot snapshot. No-op if record_timeseries is False."""
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
        """Return recorded per-slot data. Empty dict if recording was disabled."""
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

    def summary(self, horizon_s: float, buffers=None) -> dict:
        """``buffers`` is optional so callers that don't need M02's
        "delivered, but later than PDB" component (e.g. tests exercising
        Metrics in isolation) don't have to supply one -- bytes_delivered_
        late_pdb is 0 without it."""
        out = {
            "horizon_s": horizon_s,
            "dl_prb_utilization": self._dl_prbs_used / max(1, self._dl_prbs_total),
            "ul_prb_utilization": self._ul_prbs_used / max(1, self._ul_prbs_total),
            "cce_utilization": self._cce_used / max(1, self._cce_total),
            "flows": {},
        }
        for (ue_id, qfi), m in sorted(self._flow.items()):
            tput_bps = (m.bytes_delivered * 8) / horizon_s if horizon_s > 0 else 0.0
            arr_bps = (m.bytes_arrived * 8) / horizon_s if horizon_s > 0 else 0.0
            late_pdb = buffers.state(ue_id, qfi).bytes_delivered_late_pdb if buffers else 0
            out["flows"][f"ue{ue_id}_qfi{qfi}"] = {
                "bytes_arrived": m.bytes_arrived,
                "bytes_delivered": m.bytes_delivered,
                "bytes_dropped": m.bytes_dropped,
                "bytes_delivered_late_pdb": late_pdb,
                "throughput_bps": round(tput_bps, 1),
                "offered_bps": round(arr_bps, 1),
                "delivery_ratio": round(
                    m.bytes_delivered / max(1, m.bytes_arrived), 4
                ),
                "hol_p50_ms": round(self._percentile(m.hol_delay_samples_s, 0.50) * 1000, 3),
                "hol_p95_ms": round(self._percentile(m.hol_delay_samples_s, 0.95) * 1000, 3),
                # p98 is the 3GPP conformance statistic (TS 23.501 sec
                # 5.7.3.4): while within GFBR, 98% of packets shall not
                # exceed the PDB. Added for WP0's metric panel (M01);
                # p50/p95/p99 above are unchanged from their prior values.
                "hol_p98_ms": round(self._percentile(m.hol_delay_samples_s, 0.98) * 1000, 3),
                "hol_p99_ms": round(self._percentile(m.hol_delay_samples_s, 0.99) * 1000, 3),
            }
        return out
