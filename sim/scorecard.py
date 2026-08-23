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
        out["M03"] = self._m03_liveness_gap_distribution(record, cfg["t_live_s"])
        out["M04"] = self._m04_survival_time_failures(record, cfg["survival_miss_n"])
        out["M05"] = self._m05_pdu_set_completeness(record)
        out["M06"] = self._m06_frame_age_at_mec(record)
        out["M07"] = self._m07_gbr_contract_count(record, cfg["gbr_contract_fraction"])
        out["M08"] = self._m08_worst_flow_gfbr_fraction(record)
        out["M09"] = self._m09_per_second_jain(record)
        out["M10"] = self._m10_aggregate_throughput(record)
        out["M11"] = self._m11_prb_utilization(record)
        out["M12"] = self._m12_cce_utilization(record)
        # M13 (first_violation_order) is a cross-run metric -- see
        # first_violation_order() below, called by the study/sweep layer.
        out["M14"] = self._m14_communication_service_availability(record)
        out["M15"] = self._m15_command_jitter(record)
        # M16 (ul_dl_shared_bearer_correlation) needs a named flow pair --
        # see correlate_flows() below, not part of the automatic per-run scan.
        out["M17"] = self._m17_frame_freeze_and_effective_fps(record)
        return out

    def _has_true_latency(self, record: RunRecord) -> bool:
        """WP7: True per-message latency is available iff every flow in the
        record was produced by a WP7-aware driver.run() (message_count is
        never None for a flow that exists at all, post-WP7 -- see
        RunRecord.FlowRecord). False for any pre-WP7 record, which keeps
        the head-of-line proxy as the fallback rather than mixing the two
        within one record."""
        flows = list(record.flows.values())
        return bool(flows) and all(fr.message_count is not None for fr in flows)

    def _m01_latency_percentiles(self, record: RunRecord) -> MetricResult:
        if self._has_true_latency(record):
            all_flows = list(record.flows.values())
            # A flow that never fully delivered a single message (chronic
            # stall / total congestion) has message_count == 0 and would
            # otherwise report 0ms -- the LOWEST possible value, silently
            # masking the worst-behaved flow as the best one. Exclude it
            # from the "worst" contest here; M02/bytes_dropped_pdb and M05
            # are what actually score that flow's failure, not this metric.
            delivering = [fr for fr in all_flows if fr.message_count]
            excluded = len(all_flows) - len(delivering)
            worst = {"p50": 0.0, "p95": 0.0, "p98": 0.0, "p99": 0.0, "flow": None}
            for fr in delivering:
                if fr.delay_p99_ms >= worst["p99"]:
                    worst = {
                        "p50": fr.delay_p50_ms, "p95": fr.delay_p95_ms,
                        "p98": fr.delay_p98_ms, "p99": fr.delay_p99_ms, "flow": fr.key,
                    }
            note = (
                "true per-message completion latency (WP7) over fully-delivered "
                "messages only; dropped messages are scored by M02, not blended in here"
            )
            if excluded:
                note += (
                    f"; {excluded}/{len(all_flows)} flow(s) delivered zero complete "
                    "messages this run and are excluded here -- see M02/M05 for their "
                    "violation/completeness rate, not a 0ms latency"
                )
            return MetricResult("M01", "flow_latency_percentiles", worst, "ok", "ms", note)

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

    def _has_role_completions(self, record: RunRecord) -> bool:
        """WP7 commit 4: completion_ts_by_role_s is available iff every flow
        in the record was produced by a commit-4-aware driver.run() (never
        None for a flow that exists at all, post-commit-4 -- an empty dict
        is a real 'no completions', same convention as message_count)."""
        flows = list(record.flows.values())
        return bool(flows) and all(fr.completion_ts_by_role_s is not None for fr in flows)

    def _m03_liveness_gap_distribution(self, record: RunRecord, t_live_s: float) -> MetricResult:
        if not self._has_role_completions(record):
            return MetricResult(
                "M03", "liveness_gap_distribution", None, "pending", "ms",
                "requires WP7 commit 4 (completion_ts_by_role_s); record predates it",
            )
        t_live_quarter, t_live_half = t_live_s / 4.0, t_live_s / 2.0
        worst = None
        worst_gap_ms = -1.0
        excluded: list[str] = []
        for fr in record.flows.values():
            for role, ts_list in fr.completion_ts_by_role_s.items():
                # A role with <2 completions has no inter-arrival gap to
                # measure. Excluding it (not scoring gap=0) matters for the
                # same reason M01 excludes zero-message flows: 0ms/0-gap is
                # the BEST possible value, and a flow in total silence must
                # not win the "worst" contest by looking like the quietest,
                # best-behaved one.
                if len(ts_list) < 2:
                    excluded.append(f"{fr.key}:{role}")
                    continue
                gaps_s = [b - a for a, b in zip(ts_list, ts_list[1:])]
                max_gap_ms = max(gaps_s) * 1000.0
                if max_gap_ms > worst_gap_ms:
                    worst_gap_ms = max_gap_ms
                    worst = {
                        "flow": fr.key,
                        "role": role,
                        "max_gap_ms": max_gap_ms,
                        "gap_count_over_t_live_over_4": sum(1 for g in gaps_s if g > t_live_quarter),
                        "gap_count_over_t_live_over_2": sum(1 for g in gaps_s if g > t_live_half),
                        "gap_count_over_t_live": sum(1 for g in gaps_s if g > t_live_s),
                        # Never quotable without the assumption it was
                        # computed against -- same condition attached to
                        # M14's survival_time_ms (docs/wp7-plan.md Decision
                        # #3). t_live_s itself is README sec8's [OPEN] item,
                        # assumed 2s.
                        "t_live_s": t_live_s,
                    }
        note = (
            "max/count of receiver-side inter-arrival gaps among fully-"
            "delivered messages, grouped by Message.role; computed "
            "generically over any flow's completions -- most diagnostic for "
            "periodic_control/MAVLink-style flows, which no current scenario "
            "uses yet, so today's records exercise the mechanism without yet "
            "testing its intended use case"
        )
        if excluded:
            note += (
                f"; {len(excluded)} flow/role pair(s) had fewer than 2 "
                "completions (no gap definable) and are excluded from the "
                "worst-gap contest rather than scored as gap=0 -- see M01/M02 "
                f"for their delivery failure: {', '.join(excluded)}"
            )
        if worst is None:
            return MetricResult(
                "M03", "liveness_gap_distribution", None, "ok", "ms",
                "no flow/role pair had >=2 completions this run; " + note,
            )
        return MetricResult("M03", "liveness_gap_distribution", worst, "ok", "ms", note)

    def _m14_communication_service_availability(self, record: RunRecord) -> MetricResult:
        """TS 22.104 CSA: fraction of transfer intervals where the message
        arrived within (max latency + survival time). Reuses M03's exact
        gap mechanism (completion_ts_by_role_s's receiver-side inter-arrival
        gaps) against a different threshold -- pdb_ms + survival_time_ms
        per flow, instead of T_live-derived ones -- rather than needing a
        second raw-data field: an "on time" gap and a "within CSA budget"
        gap are the same underlying measurement at a different threshold.

        With survival_time_ms == 0.0 (every flow's dormant default as of
        this commit -- no scenario overrides it), the threshold collapses
        to exactly pdb_ms, so CSA == "fraction of gaps within the flow's own
        PDB" -- NOT a full CSA measurement including the TS 22.104 grace
        period. survival_time_ms is reported alongside every value for
        exactly this reason (docs/wp7-plan.md Decision #3): so a 0.0 result
        is never quoted as if it were a real survival-time-aware figure.
        """
        if not self._has_role_completions(record):
            return MetricResult(
                "M14", "communication_service_availability", None, "pending", "fraction",
                "requires WP7 commit 4 (completion_ts_by_role_s); record predates it",
            )
        worst = None
        worst_fraction = 2.0  # above the valid [0,1] range, so the first candidate always wins
        excluded: list[str] = []
        for fr in record.flows.values():
            budget_s = (fr.pdb_ms + fr.survival_time_ms) / 1000.0
            for role, ts_list in fr.completion_ts_by_role_s.items():
                if len(ts_list) < 2:
                    excluded.append(f"{fr.key}:{role}")
                    continue
                gaps_s = [b - a for a, b in zip(ts_list, ts_list[1:])]
                within = sum(1 for g in gaps_s if g <= budget_s)
                fraction = within / len(gaps_s)
                if fraction < worst_fraction:
                    worst_fraction = fraction
                    worst = {
                        "flow": fr.key,
                        "role": role,
                        "fraction": fraction,
                        "interval_count": len(gaps_s),
                        "survival_time_ms": fr.survival_time_ms,
                    }
        note = (
            "fraction of receiver-side inter-arrival gaps within pdb_ms + "
            "survival_time_ms, grouped by Message.role, worst (min) flow/role "
            "pair; survival_time_ms defaults to 0.0 (docs/wp7-plan.md Decision "
            "#3) -- with every current flow at that default, this collapses "
            "exactly to the fraction of gaps within the flow's own pdb_ms, "
            "not a full CSA measurement including the TS 22.104 grace period"
        )
        if excluded:
            note += (
                f"; {len(excluded)} flow/role pair(s) had fewer than 2 "
                "completions (no interval definable) and are excluded here -- "
                f"see M01/M02 for their delivery failure: {', '.join(excluded)}"
            )
        if worst is None:
            return MetricResult(
                "M14", "communication_service_availability", None, "ok", "fraction",
                "no flow/role pair had >=2 completions this run; " + note,
            )
        return MetricResult("M14", "communication_service_availability", worst, "ok", "fraction", note)

    def _has_frame_data(self, record: RunRecord) -> bool:
        """WP7 commit 6: frame_completions is available iff every flow in
        the record was produced by a commit-6-aware driver.run() (never
        None for a flow that exists at all, post-commit-6 -- total=0 is a
        real "generated no XR frames," same convention as message_count)."""
        flows = list(record.flows.values())
        return bool(flows) and all(fr.frame_completions is not None for fr in flows)

    def _m05_pdu_set_completeness(self, record: RunRecord) -> MetricResult:
        if not self._has_frame_data(record):
            return MetricResult(
                "M05", "pdu_set_completeness", None, "pending", "fraction",
                "requires WP7 commit 6 (FrameLedger / frame_completions); record predates it",
            )
        candidates = []
        for fr in record.flows.values():
            total = fr.frame_completions["total"]
            if total == 0:
                continue  # this flow never used xr_video -- not applicable
            on_time = sum(
                1 for age in fr.frame_completions["complete_ages_ms"] if age <= fr.pdb_ms
            )
            candidates.append((fr.key, on_time / total, total))
        note = (
            "worst (min) per-flow fraction of frames fully delivered within "
            "pdb_ms -- this branch has no separate PDU-Set Delay Budget "
            "concept, so the frame's own PDB doubles as its set delay "
            "budget; a dropped or partial frame counts as failed regardless "
            "of speed, per this metric's own definition"
        )
        if not candidates:
            return MetricResult(
                "M05", "pdu_set_completeness", None, "ok", "fraction",
                "no flow in this run generated any XR frames; " + note,
            )
        worst_key, worst_fraction, worst_total = min(candidates, key=lambda kv: kv[1])
        return MetricResult(
            "M05", "pdu_set_completeness",
            {"flow": worst_key, "fraction": worst_fraction, "frame_count": worst_total},
            "ok", "fraction", note,
        )

    def _m06_frame_age_at_mec(self, record: RunRecord) -> MetricResult:
        if not self._has_frame_data(record):
            return MetricResult(
                "M06", "frame_age_at_mec", None, "pending", "ms",
                "requires WP7 commit 6 (FrameLedger / frame_completions); record predates it",
            )
        candidates = []
        excluded: list[str] = []
        for fr in record.flows.values():
            total = fr.frame_completions["total"]
            if total == 0:
                continue  # this flow never used xr_video -- not applicable
            ages = fr.frame_completions["complete_ages_ms"]
            if not ages:
                # Generated frames but completed none -- age is undefined,
                # not 0ms (0 would look like the BEST-behaved flow). M05
                # scores this failure as 0% completeness; this metric just
                # excludes it, the same shape as M01's zero-message-count
                # exclusion.
                excluded.append(fr.key)
                continue
            candidates.append((fr.key, _percentile(ages, 0.95)))
        note = "p95 age (completion_ts - frame_generation_ts) over fully-delivered frames only, worst flow"
        if excluded:
            note += (
                f"; {len(excluded)} flow(s) generated frames but completed none "
                f"(age undefined) and are excluded here -- see M05 for their "
                f"failure: {', '.join(excluded)}"
            )
        if not candidates:
            return MetricResult("M06", "frame_age_at_mec", None, "ok", "ms",
                                 "no flow completed a single XR frame this run; " + note)
        worst_key, worst_p95 = max(candidates, key=lambda kv: kv[1])
        return MetricResult("M06", "frame_age_at_mec",
                             {"flow": worst_key, "p95_ms": worst_p95}, "ok", "ms", note)

    def _has_frame_gap_data(self, record: RunRecord) -> bool:
        """WP7 commit 7: frame_completions["complete_ts_s"] is present iff
        every flow was produced by a commit-7-aware driver.run(). Checks
        key PRESENCE, not truthiness -- an empty list is a real "no
        complete frames this run," while a MISSING key means the record
        predates commit 7 (frame_completions itself already existed from
        commit 6, so frame_completions is not None alone can't tell the two
        apart -- see _has_frame_data)."""
        flows = list(record.flows.values())
        return bool(flows) and all(
            fr.frame_completions is not None and "complete_ts_s" in fr.frame_completions
            for fr in flows
        )

    def _m17_frame_freeze_and_effective_fps(self, record: RunRecord) -> MetricResult:
        if not self._has_frame_gap_data(record):
            return MetricResult(
                "M17", "frame_freeze_and_effective_fps", None, "pending", "mixed",
                "requires WP7 commit 7 (frame_completions[\"complete_ts_s\"] / "
                "xr_frame_period_ms); record predates it",
            )
        horizon_s = record.system.horizon_s
        candidates = []
        excluded: list[str] = []
        for fr in record.flows.values():
            total = fr.frame_completions["total"]
            if total == 0:
                continue  # this flow never used xr_video -- not applicable
            ts = fr.frame_completions["complete_ts_s"]
            period_ms = fr.xr_frame_period_ms
            if len(ts) < 2 or period_ms is None:
                # Generated frames but too few completed to see a gap at
                # all -- M05 already scores this as a completeness failure;
                # this metric just excludes it, same shape as M06's own
                # zero-completion exclusion.
                excluded.append(fr.key)
                continue
            frame_interval_s = period_ms / 1000.0
            gaps_s = [b - a for a, b in zip(ts, ts[1:])]
            freeze_gaps_s = [g for g in gaps_s if g > 2 * frame_interval_s]
            candidates.append((fr.key, {
                "freeze_count": len(freeze_gaps_s),
                "freeze_total_duration_ms": round(sum(freeze_gaps_s) * 1000.0, 3),
                "freeze_max_duration_ms": round(max(freeze_gaps_s) * 1000.0, 3) if freeze_gaps_s else 0.0,
                "effective_fps": round(len(ts) / horizon_s, 3) if horizon_s > 0 else 0.0,
                "source_fps": round(1000.0 / period_ms, 3),
            }))
        note = (
            "a freeze is a gap between consecutive fully-delivered frames "
            "exceeding 2x the flow's CONFIGURED (nominal) frame interval -- "
            "xr_frame_period_ms, not this simulator's own slot-quantised "
            "actual firing interval, so a freeze reflects the source's real "
            "claimed frame rate rather than an artifact of this simulator's "
            "time discretisation (docs/wp7-plan.md commit 7); worst = most "
            "freeze events, ties broken by total freeze duration"
        )
        if excluded:
            note += (
                f"; {len(excluded)} flow(s) generated frames but had fewer "
                f"than 2 complete ones (no gap definable) and are excluded "
                f"here -- see M05 for their completeness failure: "
                f"{', '.join(excluded)}"
            )
        if not candidates:
            return MetricResult(
                "M17", "frame_freeze_and_effective_fps", None, "ok", "mixed",
                "no flow had enough complete frames to evaluate; " + note,
            )
        worst_key, worst_value = max(
            candidates, key=lambda kv: (kv[1]["freeze_count"], kv[1]["freeze_total_duration_ms"])
        )
        return MetricResult(
            "M17", "frame_freeze_and_effective_fps",
            {"flow": worst_key, **worst_value}, "ok", "mixed", note,
        )

    def _m02_pdb_violation_rate(self, record: RunRecord) -> MetricResult:
        total_arrived = sum(fr.bytes_arrived for fr in record.flows.values())
        total_delivered = sum(fr.bytes_delivered for fr in record.flows.values())
        total_dropped = sum(fr.bytes_dropped_pdb for fr in record.flows.values())
        total_late = sum(fr.bytes_delivered_late_pdb for fr in record.flows.values())
        # Denominator is RESOLVED bytes (delivered + dropped), not
        # bytes_arrived. A byte still queued at horizon end is neither
        # delivered, dropped, nor late -- if it counted toward bytes_arrived
        # without ever being able to land in the numerator, the rate would
        # be systematically optimistic on any run that doesn't fully drain
        # (short horizons, bursty tails). Excluding it is honest about what
        # wasn't resolved rather than silently treating it as fine.
        total_resolved = total_delivered + total_dropped
        rate = ((total_dropped + total_late) / total_resolved) if total_resolved > 0 else 0.0
        note = (
            "expiry-discard + delivered-but-late components, both exact "
            "(WP3: bytes_delivered_late_pdb tags each drained chunk's age "
            "against its flow's PDB at drain time); denominator is resolved "
            "bytes (delivered + dropped), not bytes_arrived -- bytes still "
            "queued and unresolved at horizon end are excluded rather than "
            "counted as fine"
        )
        still_queued = total_arrived - total_resolved
        if total_arrived > 0 and still_queued > 0:
            note += (
                f"; {still_queued}/{total_arrived} bytes "
                f"({still_queued / total_arrived:.1%}) still queued, "
                "unresolved at horizon end, excluded from this run"
            )
        return MetricResult("M02", "pdb_violation_rate", rate, "ok", "fraction", note)

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
        have_true = self._has_true_latency(record)
        worst = None
        worst_jitter = -1.0
        for fr in record.flows.values():
            # Same zero-completions exclusion as M01 -- a stalled flow's
            # jitter is undefined, not 0ms.
            if have_true and not fr.message_count:
                continue
            jitter = (
                fr.delay_p99_ms - fr.delay_p50_ms if have_true
                else fr.delay_p99_ms_proxy - fr.delay_p50_ms_proxy
            )
            if jitter > worst_jitter:
                worst_jitter = jitter
                worst = fr.key
        if worst is None:
            return MetricResult("M15", "command_jitter_p99_p50", None, "proxy", "ms", "no flows")
        status = "ok" if have_true else "proxy"
        note = (
            "true per-message p99-p50 (WP7); flows with zero delivered messages excluded"
            if have_true
            else "inherits M01's head-of-line-age proxy caveat"
        )
        return MetricResult("M15", "command_jitter_p99_p50",
                             {"flow": worst, "jitter_ms": worst_jitter}, status, "ms", note)

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
