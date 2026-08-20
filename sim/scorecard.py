"""Scorecard -- computes config/metric_panel.yml's full panel from a
RunRecord (WP0).

Every metric in the panel gets a row in the output, always -- a metric with
status "pending" appears with value=None and a reason, it is never omitted.
Omitting a not-yet-computable metric would be indistinguishable from
forgetting it, and the whole point of pre-registering the panel (see the
YAML's header) is that its *shape* doesn't drift once sweeps start.

This module intentionally does not import sim.driver or sim.config -- it
consumes only RunRecord, so it can score a record built from any run
(current sim, a future fidelity-uplifted sim, or eventually an OAI log
adapter) without caring how it was produced.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from .run_record import FlowRecord, RunRecord

_DEFAULT_PANEL_PATH = Path(__file__).resolve().parent.parent / "config" / "metric_panel.yml"


@dataclass
class MetricResult:
    id: str
    name: str
    value: Any
    status: str  # "ok" | "proxy" | "pending"
    unit: str
    note: str = ""


def load_panel(path: Path = _DEFAULT_PANEL_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    s = sorted(samples)
    k = min(len(s) - 1, int(len(s) * p))
    return s[k]


def _jain(values: list[float]) -> Optional[float]:
    """Jain's fairness index over a set of values. None if undefined (<2 values,
    or all zero)."""
    n = len(values)
    if n < 2:
        return None
    s1 = sum(values)
    s2 = sum(v * v for v in values)
    if s2 == 0:
        return None
    return (s1 * s1) / (n * s2)


def _pearson(a: list[float], b: list[float]) -> Optional[float]:
    n = len(a)
    if n < 2 or n != len(b):
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((x - mb) ** 2 for x in b)
    if va == 0 or vb == 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def _bucket_by_second(time_s: list[float], values: list[float]) -> dict[int, list[float]]:
    buckets: dict[int, list[float]] = {}
    for t, v in zip(time_s, values):
        buckets.setdefault(int(t), []).append(v)
    return buckets


class Scorecard:
    def __init__(self, panel_path: Path = _DEFAULT_PANEL_PATH) -> None:
        self.panel = load_panel(panel_path)
        self.defaults = self.panel.get("defaults", {})

    # -- single-run metrics --------------------------------------------

    def score(self, record: RunRecord, **overrides) -> dict[str, MetricResult]:
        """Compute every metric in the panel for one RunRecord.

        ``overrides`` may set gbr_contract_fraction / survival_miss_n /
        t_live_s for this call; unset ones fall back to the panel's
        pre-registered defaults.
        """
        cfg = {**self.defaults, **overrides}
        out: dict[str, MetricResult] = {}
        out["M01"] = self._m01_latency_percentiles(record)
        out["M02"] = self._m02_pdb_violation_rate(record)
        out["M03"] = MetricResult(
            "M03", "liveness_gap_distribution", None, "pending", "ms",
            "requires WP7 discrete message model + WP4 uplink access chain",
        )
        out["M04"] = self._m04_survival_time_failures(record, cfg["survival_miss_n"])
        out["M05"] = MetricResult(
            "M05", "pdu_set_completeness", None, "pending", "fraction",
            "requires WP7 XR frame / PDU-set model",
        )
        out["M06"] = MetricResult(
            "M06", "frame_age_at_mec", None, "pending", "ms",
            "requires WP7 XR frame model",
        )
        out["M07"] = self._m07_gbr_contract_count(record, cfg["gbr_contract_fraction"])
        out["M08"] = self._m08_worst_flow_gfbr_fraction(record)
        out["M09"] = self._m09_per_second_jain(record)
        out["M10"] = self._m10_aggregate_throughput(record)
        out["M11"] = self._m11_prb_utilization(record)
        out["M12"] = self._m12_cce_utilization(record)
        # M13 (first_violation_order) is a cross-run metric -- see
        # first_violation_order() below, called by the study/sweep layer.
        out["M14"] = MetricResult(
            "M14", "communication_service_availability", None, "pending", "fraction",
            "requires WP7 discrete message model (same as M03/M04)",
        )
        out["M15"] = self._m15_command_jitter(record)
        # M16 (ul_dl_shared_bearer_correlation) needs a named flow pair --
        # see correlate_flows() below, not part of the automatic per-run scan.
        out["M17"] = MetricResult(
            "M17", "frame_freeze_and_effective_fps", None, "pending", "mixed",
            "requires WP7 XR frame model (same as M05/M06)",
        )
        return out

    def _m01_latency_percentiles(self, record: RunRecord) -> MetricResult:
        worst = {"p50": 0.0, "p95": 0.0, "p98": 0.0, "p99": 0.0, "flow": None}
        have_p98 = True
        for fr in record.flows.values():
            if fr.delay_p98_ms_proxy is None:
                have_p98 = False
            if fr.delay_p99_ms_proxy >= worst["p99"]:
                worst = {
                    "p50": fr.delay_p50_ms_proxy,
                    "p95": fr.delay_p95_ms_proxy,
                    "p98": fr.delay_p98_ms_proxy,
                    "p99": fr.delay_p99_ms_proxy,
                    "flow": fr.key,
                }
        note = "proxy: head-of-line age sampled per slot, not true per-message completion latency"
        if not have_p98:
            note += "; record predates p98 (some flows show p98=None)"
        return MetricResult("M01", "flow_latency_percentiles", worst, "proxy", "ms", note)

    def _m02_pdb_violation_rate(self, record: RunRecord) -> MetricResult:
        total_arrived = sum(fr.bytes_arrived for fr in record.flows.values())
        total_dropped = sum(fr.bytes_dropped_pdb for fr in record.flows.values())
        total_late = sum(fr.bytes_delivered_late_pdb for fr in record.flows.values())
        rate = ((total_dropped + total_late) / total_arrived) if total_arrived > 0 else 0.0
        return MetricResult(
            "M02", "pdb_violation_rate", rate, "ok", "fraction",
            "expiry-discard + delivered-but-late components, both exact "
            "(WP3: bytes_delivered_late_pdb tags each drained chunk's age "
            "against its flow's PDB at drain time)",
        )

    def _m04_survival_time_failures(self, record: RunRecord, survival_n: int) -> MetricResult:
        if not record.has_timeseries():
            return MetricResult(
                "M04", "survival_time_failures", None, "pending", "count",
                "requires record_timeseries=True",
            )
        worst_run = 0
        worst_flow = None
        for fr in record.flows.values():
            if fr.ts_hol_delay_s is None:
                continue
            pdb_s = fr.pdb_ms / 1000.0
            run = 0
            for d in fr.ts_hol_delay_s:
                if d > pdb_s:
                    run += 1
                    if run > worst_run:
                        worst_run = run
                        worst_flow = fr.key
                else:
                    run = 0
        return MetricResult(
            "M04", "survival_time_failures",
            {"worst_consecutive_miss_slots": worst_run, "flow": worst_flow,
             "threshold_n": survival_n, "exceeds_threshold": worst_run >= survival_n},
            "proxy", "count",
            "proxy: consecutive slots with head-of-line delay > PDB, from the "
            "per-slot timeseries -- not a true per-message miss count (WP7)",
        )

    def _m07_gbr_contract_count(self, record: RunRecord, fraction: float) -> MetricResult:
        gbr = record.flows_by(flow_class="GBR")
        if not gbr:
            return MetricResult("M07", "gbr_contract_count", None, "ok", "count",
                                 "no GBR flows in this run")
        met = sum(1 for fr in gbr if fr.meets_gbr_contract(fraction))
        return MetricResult(
            "M07", "gbr_contract_count", {"met": met, "total": len(gbr)}, "ok", "count",
        )

    def _m08_worst_flow_gfbr_fraction(self, record: RunRecord) -> MetricResult:
        gbr = record.flows_by(flow_class="GBR")
        fractions = [(fr.key, fr.gfbr_fraction()) for fr in gbr]
        fractions = [(k, v) for k, v in fractions if v is not None]
        if not fractions:
            return MetricResult("M08", "worst_flow_gfbr_fraction", None, "ok",
                                 "fraction", "no GBR flows in this run")
        worst_key, worst_val = min(fractions, key=lambda kv: kv[1])
        return MetricResult("M08", "worst_flow_gfbr_fraction",
                             {"flow": worst_key, "fraction": worst_val}, "ok", "fraction")

    def _m09_per_second_jain(self, record: RunRecord) -> MetricResult:
        if not record.has_timeseries():
            return MetricResult("M09", "per_second_jain_index", None, "pending",
                                 "index [0,1]", "requires record_timeseries=True")
        flows = [fr for fr in record.flows.values() if fr.ts_delivered_bytes is not None]
        if len(flows) < 2:
            return MetricResult("M09", "per_second_jain_index", None, "proxy",
                                 "index [0,1]", "fewer than 2 flows with timeseries data")
        time_s = record.timeseries_time_s
        per_flow_ratio_by_sec: dict[int, list[float]] = {}
        for fr in flows:
            for sec, delivered_list in _bucket_by_second(time_s, fr.ts_delivered_bytes).items():
                arrived_list = _bucket_by_second(time_s, fr.ts_arrived_bytes)[sec]
                delivered = sum(delivered_list)
                arrived = sum(arrived_list)
                ratio = (delivered / arrived) if arrived > 0 else 1.0
                per_flow_ratio_by_sec.setdefault(sec, []).append(ratio)
        per_sec_jain = [
            j for j in (_jain(v) for v in per_flow_ratio_by_sec.values()) if j is not None
        ]
        if not per_sec_jain:
            return MetricResult("M09", "per_second_jain_index", None, "proxy",
                                 "index [0,1]", "no window had >=2 flows with nonzero offered load")
        return MetricResult(
            "M09", "per_second_jain_index",
            {"worst": min(per_sec_jain), "mean": sum(per_sec_jain) / len(per_sec_jain),
             "windows": len(per_sec_jain)},
            "proxy", "index [0,1]",
            "computed over all flows in the record with timeseries data -- "
            "pass a same-role flow subset upstream if that's what the guarantee needs",
        )

    def _m10_aggregate_throughput(self, record: RunRecord) -> MetricResult:
        total = sum(fr.throughput_bps for fr in record.flows.values())
        return MetricResult("M10", "aggregate_throughput", total, "ok", "bps")

    def _m11_prb_utilization(self, record: RunRecord) -> MetricResult:
        return MetricResult(
            "M11", "prb_utilization",
            {"dl": record.system.dl_prb_utilization, "ul": record.system.ul_prb_utilization},
            "ok", "fraction",
        )

    def _m12_cce_utilization(self, record: RunRecord) -> MetricResult:
        return MetricResult("M12", "pdcch_cce_utilization", record.system.cce_utilization,
                             "ok", "fraction")

    def _m15_command_jitter(self, record: RunRecord) -> MetricResult:
        worst = None
        worst_jitter = -1.0
        for fr in record.flows.values():
            jitter = fr.delay_p99_ms_proxy - fr.delay_p50_ms_proxy
            if jitter > worst_jitter:
                worst_jitter = jitter
                worst = fr.key
        if worst is None:
            return MetricResult("M15", "command_jitter_p99_p50", None, "proxy", "ms", "no flows")
        return MetricResult("M15", "command_jitter_p99_p50",
                             {"flow": worst, "jitter_ms": worst_jitter}, "proxy", "ms",
                             "inherits M01's head-of-line-age proxy caveat")

    # -- metrics that need extra arguments, called explicitly ----------

    def correlate_flows(
        self, record: RunRecord, ue_qfi_a: tuple[int, int], ue_qfi_b: tuple[int, int],
        series: str = "ts_hol_delay_s",
    ) -> MetricResult:
        """M16: correlation between two named flows' per-slot series (e.g.
        the UL and DL halves of a shared telemetry/command bearer)."""
        if not record.has_timeseries():
            return MetricResult("M16", "ul_dl_shared_bearer_correlation", None,
                                 "pending", "Pearson r", "requires record_timeseries=True")
        fa = record.flow(*ue_qfi_a)
        fb = record.flow(*ue_qfi_b)
        sa, sb = getattr(fa, series), getattr(fb, series)
        if sa is None or sb is None:
            return MetricResult("M16", "ul_dl_shared_bearer_correlation", None,
                                 "pending", "Pearson r", f"{series} missing on one of the two flows")
        r = _pearson(sa, sb)
        return MetricResult(
            "M16", "ul_dl_shared_bearer_correlation",
            {"flow_a": fa.key, "flow_b": fb.key, "r": r}, "proxy", "Pearson r",
            f"series={series}; no automatic bearer pairing -- caller-specified flows",
        )

    def first_violation_order(
        self, records_by_load: list[RunRecord], class_of: dict[str, int],
        fraction: Optional[float] = None,
    ) -> MetricResult:
        """M13: over an ascending-load sequence of RunRecords for the SAME
        scenario/scheduler, the order in which 5QI classes first fail their
        GBR contract. ``class_of`` maps flow key -> 5QI. ``records_by_load``
        must already be sorted ascending by offered load.
        """
        fraction = self.defaults["gbr_contract_fraction"] if fraction is None else fraction
        first_fail_at: dict[int, int] = {}
        for load_idx, rec in enumerate(records_by_load):
            for fr in rec.flows_by(flow_class="GBR"):
                qi = class_of.get(fr.key)
                if qi is None or qi in first_fail_at:
                    continue
                met = fr.meets_gbr_contract(fraction)
                if met is False:
                    first_fail_at[qi] = load_idx
        order = sorted(first_fail_at, key=lambda qi: first_fail_at[qi])
        return MetricResult(
            "M13", "first_violation_order", {"order_5qi": order, "first_fail_at_index": first_fail_at},
            "ok", "ordinal (5QI sequence)",
            f"over {len(records_by_load)} load points; 5QI classes never seen "
            f"to fail are absent from order_5qi",
        )
