from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class FlowMetrics:
    bytes_arrived: int = 0
    bytes_delivered: int = 0
    bytes_dropped: int = 0
    hol_delay_samples_s: list = field(default_factory=list)


class Metrics:
    def __init__(self, record_timeseries: bool = False,
                 timeseries_resolution: str = "slot") -> None:
        self._flow: dict[tuple[int, int], FlowMetrics] = defaultdict(FlowMetrics)
        self._dl_prbs_used = 0
        self._ul_prbs_used = 0
        self._dl_prbs_total = 0
        self._ul_prbs_total = 0
        self._cce_used = 0
        self._cce_total = 0
        self._cce_by_kind: dict[str, tuple[int, int]] = {}
        self._cce_slots = 0
        self._cce_slots_at_cap = 0

        # Per-slot time series (opt-in to keep memory footprint small).
        self.record_ts = record_timeseries
        # WP9 G11 commit 3. "second" folds each series to ONE ENTRY PER
        # SIMULATED SECOND instead of per slot -- 7.2M -> 1,800 at the soak
        # horizon, a 4,000x reduction (docs/wp9-plan.md §37).
        #
        # OPT-IN, DELIBERATELY. Making it the default would rewrite every
        # existing study and the frozen regression corpus, which is exactly
        # what the one-change-per-commit and do-not-recapture rules forbid.
        # Every current caller gets "slot" and is byte-identical.
        #
        # WHAT FOLDS EXACTLY AND WHAT DOES NOT. delivered/arrived/dropped
        # are COUNTS: summing them per second is lossless for every
        # consumer that buckets by second, which is M09 (by definition) and
        # M08w (sums over a window). backlog_bytes and hol_delay_s are
        # LEVELS -- a sum is meaningless and a max/mean would be a
        # DIFFERENT STATISTIC wearing the same field name. They are emitted
        # as None instead, so M04/M19/M21 report pending rather than
        # silently reading a per-second aggregate as a per-slot series.
        if timeseries_resolution not in ("slot", "second"):
            raise ValueError(
                f"timeseries_resolution must be 'slot' or 'second', "
                f"got {timeseries_resolution!r}")
        self.ts_resolution = timeseries_resolution
        self._ts_sec: int | None = None      # second currently accumulating
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

    def record_cce(self, used: int, total: int,
                   slot_kind: str = "?") -> None:
        """Per-slot PDCCH spend and budget.

        `slot_kind` ("D"/"S"/"U") is recorded because **the aggregate ratio
        alone is not interpretable** -- see `docs/wp9-defects-log.md` #29,
        the third instance of the population defect. `_cce_total` sums the
        budget of EVERY slot, but a workload with no downlink flows can
        never spend a D-slot's budget, so its achievable ceiling is below
        1.0. On this repository's `DSUUU` carrier (D=48, S=16, U=32) that
        ceiling is 112/160 = **0.70**, and 0.6357 read as "loaded" against
        1.0 is **90.8 % of achievable** against 0.70.

        Note the asymmetry that made this findable: `record_grid_capacity`
        IS direction-gated (`dl_prbs=... if slot_grid.dl_symbols > 0 else
        0`), so PRB utilisation already has the right denominator. CCE was
        the one that did not.

        The per-slot series is kept too, because **binding is a property of
        the worst slot, not the mean** -- a channel saturated on 2,308 slots
        and idle otherwise averages to something comfortable.
        """
        self._cce_used += used
        self._cce_total += total
        self._cce_by_kind[slot_kind] = (
            self._cce_by_kind.get(slot_kind, (0, 0))[0] + used,
            self._cce_by_kind.get(slot_kind, (0, 0))[1] + total)
        if total > 0:
            self._cce_slots += 1
            if used >= total:
                self._cce_slots_at_cap += 1

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
        dl_avail = slot_grid.prb_count if slot_grid.dl_symbols > 0 else 0
        ul_avail = slot_grid.prb_count if slot_grid.ul_symbols > 0 else 0

        if self.ts_resolution == "second":
            sec = int(time_s)
            if sec != self._ts_sec:
                # open a new second: one entry, then accumulate into it
                self._ts_sec = sec
                self._ts_slot_index.append(slot_index)
                self._ts_time_s.append(float(sec))
                for k in ("dl_prbs_used", "ul_prbs_used", "dl_prbs_avail",
                          "ul_prbs_avail", "cce_used", "cce_budget"):
                    self._ts_system[k].append(0)
                for key in buffers.keys():
                    ts = self._ts_per_flow.setdefault(
                        key, {"delivered_bytes": [], "arrived_bytes": [],
                              "dropped_bytes": []})
                    for k in ("delivered_bytes", "arrived_bytes", "dropped_bytes"):
                        ts[k].append(0)
            for key in buffers.keys():
                ts = self._ts_per_flow.setdefault(
                    key, {"delivered_bytes": [], "arrived_bytes": [],
                          "dropped_bytes": []})
                # a flow first seen mid-second still needs its slot
                for k in ("delivered_bytes", "arrived_bytes", "dropped_bytes"):
                    if len(ts[k]) < len(self._ts_time_s):
                        ts[k].extend([0] * (len(self._ts_time_s) - len(ts[k])))
                ts["delivered_bytes"][-1] += per_flow_delivered.get(key, 0)
                ts["arrived_bytes"][-1] += per_flow_arrived.get(key, 0)
                ts["dropped_bytes"][-1] += per_flow_dropped.get(key, 0)
            self._ts_system["dl_prbs_used"][-1] += dl_prbs_used
            self._ts_system["ul_prbs_used"][-1] += ul_prbs_used
            self._ts_system["dl_prbs_avail"][-1] += dl_avail
            self._ts_system["ul_prbs_avail"][-1] += ul_avail
            self._ts_system["cce_used"][-1] += cce_used
            self._ts_system["cce_budget"][-1] += slot_grid.pdcch_cce_budget
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
        self._ts_system["dl_prbs_avail"].append(dl_avail)
        self._ts_system["ul_prbs_avail"].append(ul_avail)
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
            # PER-SLOT-KIND UTILISATION, which is what makes the aggregate
            # interpretable (#29). A "ceiling" field was tried first and
            # abandoned: deriving it from "kinds this run spent anything in"
            # reads 1.0 here, because D-slots carry 524 of 76,800 CCEs
            # (0.7 %) rather than exactly zero -- so any usage threshold for
            # "reachable" is an arbitrary judgement. The BREAKDOWN needs no
            # such judgement and shows the same thing more directly: on
            # sensor_dense it is D 0.7 %, S 81.5 %, U 92.2 %, against an
            # aggregate of 0.637 that averages an unspendable D budget into
            # a saturated U one.
            "cce_budget_by_slot_kind": {
                k: v[1] for k, v in sorted(self._cce_by_kind.items())},
            "cce_used_by_slot_kind": {
                k: v[0] for k, v in sorted(self._cce_by_kind.items())},
            "cce_utilization_by_slot_kind": {
                k: (v[0] / v[1] if v[1] else 0.0)
                for k, v in sorted(self._cce_by_kind.items())},
            # BINDING IS A PROPERTY OF THE WORST SLOT, NOT THE MEAN (#29).
            "cce_slots_with_budget": self._cce_slots,
            "cce_slots_at_cap": self._cce_slots_at_cap,
            "cce_frac_slots_at_cap": (
                self._cce_slots_at_cap / max(1, self._cce_slots)),
            "flows": {},
        }
        for (ue_id, qfi), m in sorted(self._flow.items()):
            tput_bps = (m.bytes_delivered * 8) / horizon_s if horizon_s > 0 else 0.0
            arr_bps = (m.bytes_arrived * 8) / horizon_s if horizon_s > 0 else 0.0
            late_pdb = buffers.state(ue_id, qfi).bytes_delivered_late_pdb if buffers else 0
            # WP5 (docs/wp5-plan.md commit 4a): read straight from
            # BufferState at summary time, same pattern as late_pdb above
            # -- no separate Metrics.record_*/driver.py call needed.
            harq_lost = buffers.state(ue_id, qfi).bytes_dropped_harq if buffers else 0
            out["flows"][f"ue{ue_id}_qfi{qfi}"] = {
                "bytes_arrived": m.bytes_arrived,
                "bytes_delivered": m.bytes_delivered,
                "bytes_dropped": m.bytes_dropped,
                "bytes_delivered_late_pdb": late_pdb,
                "bytes_harq_lost": harq_lost,
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
