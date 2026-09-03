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

import dataclasses
import math
import statistics
from dataclasses import dataclass, field
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
    # Pre-registered, panel-authored limitations that travel with the value
    # regardless of status -- e.g. "ok" (exact, from real data) but computed
    # under a simulator mechanism that's itself still a simplification (see
    # config/metric_panel.yml's own `caveats:` field, docs/wp5-plan.md
    # Decision 6). Populated by Scorecard.score() from the panel, not by
    # each metric's own method -- see that method's docstring.
    caveats: list[str] = field(default_factory=list)


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
        # id -> its pre-registered caveats list (empty for most metrics).
        # Read once here, not per-score-call, since the panel file itself
        # doesn't change within a process lifetime.
        self._caveats_by_id: dict[str, list[str]] = {
            m["id"]: list(m.get("caveats", [])) for m in self.panel["metrics"]
        }

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
        # M20 is auto-scored rather than left a study-layer call like
        # M13/M16. It needs no extra argument (its exclusion set has a
        # documented default) and the record_sink defect this WP just
        # fixed is the argument for it: a statistic absent from the
        # scored row is one a later question cannot be re-asked of
        # without re-running. The excluded 5QIs travel INSIDE the
        # value, never as a bare number -- same convention as M03/M14
        # reporting the t_live_s they were computed against.
        out["M20"] = self.protected_fleet_liveness_gap(record, cfg["t_live_s"])
        # M21 auto-scored beside M19 for the same reason M20 is beside
        # M03: the pair must be readable together, and a statistic
        # absent from the scored row is one a later question cannot be
        # re-asked of without a re-run.
        out["M21"] = self.slo_recovery_time_by_delivery(record)
        # M22 auto-scored beside M09 for the reason M20 sits beside M03:
        # it is the OTHER half of a conjunction the panel binds to one
        # guarantee, and a conjunction scored on one conjunct is the
        # failure this panel exists to prevent.
        out["M22"] = self._m22_starvation_epochs(record)
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
        out["M18"] = self._m18_rejoin_interruption_time(record)
        out["M19"] = self._m19_slo_recovery_time(record, cfg["slo_green_dwell_s"])
        # Attach the panel's own pre-registered caveats here, uniformly,
        # rather than in each _mNN method -- a caveat is a property of the
        # metric's definition (config/metric_panel.yml), not of any one
        # run's data, so it shouldn't be up to each method to remember.
        for metric_id, result in out.items():
            # EXTEND, never overwrite. A metric method may attach a caveat
            # derived from THIS run's data (M03's cadence caveat), and the
            # panel's registered caveats are a property of the metric's
            # definition -- both must travel. Assigning here used to discard
            # the former silently.
            result.caveats = (list(self._caveats_by_id.get(metric_id, []))
                              + list(result.caveats or []))
        return out

    _FOLDED_REASON = (
        "timeseries recorded at per-SECOND resolution (WP9 G11 commit 3): "
        "this metric needs per-SLOT levels (hol delay / backlog), which a "
        "per-second fold does not carry. Reported pending rather than "
        "reading a per-second aggregate as a per-slot series."
    )

    _WINDOWED_REASON = (
        "message ledger drained per window (WP9 G11 commit 2): run-level "
        "message aggregates are not reconstructible from window summaries "
        "-- score per window. Reported pending rather than falling back to "
        "the head-of-line proxy, which would be a DIFFERENT ESTIMATOR under "
        "the same metric id."
    )

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
        # The eviction case must NOT fall through to the proxy below: a
        # windowed record has message_count=None on every flow, which
        # _has_true_latency reads as "pre-WP7" and answers with the
        # head-of-line proxy -- silently swapping estimators. Pending is the
        # honest answer, and the panel's own rule is that a pending metric
        # emits a row with a reason rather than being omitted.
        if record.message_ledger_windowed:
            return MetricResult("M01", "flow_latency_percentiles", None,
                                "pending", "ms", self._WINDOWED_REASON)
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
                        # The flow's OWN cadence, carried so a reader can
                        # tell a liveness failure from a slow flow. A
                        # duty-cycled source whose configured period already
                        # exceeds the bound makes max_gap_ms report the
                        # cadence, not a failure -- see the caveat below,
                        # which is derived from THIS number rather than from
                        # any scenario axis, so it fires for any slow flow
                        # from any producer.
                        "median_gap_ms": statistics.median(gaps_s) * 1000.0,
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
        # THE CADENCE CAVEAT, attached to the value at score time rather than
        # written in prose afterwards. If the winning flow's own MEDIAN gap
        # already exceeds the bound, max_gap_ms is reporting how often the
        # application sends, not whether the network kept up -- e.g. a
        # duty-cycled telemetry source at duty 0.1 has a 1000 ms configured
        # period against a 500 ms (T_live/4) bound, so every seed "breaches"
        # with nothing failing. Derived from the flow's own data, so it
        # applies to any slow flow from any producer, not just to a WP9 axis.
        result = MetricResult(
            "M03", "liveness_gap_distribution", worst, "ok", "ms", note)
        if worst["median_gap_ms"] > t_live_quarter * 1000.0:
            result.caveats = [
                f"CADENCE, NOT LIVENESS: the reporting flow's own median "
                f"inter-arrival gap is {worst['median_gap_ms']:.0f} ms, already "
                f"above the T_live/4 bound of {t_live_quarter * 1000.0:.0f} ms "
                f"(t_live_s={t_live_s}). max_gap_ms here measures the source's "
                f"cadence, not a liveness failure -- do not score it against "
                f"that bound."
            ]
        return result

    # 5QIs that are NOT protected fleet bearers: the GT-4.1/4.2 saturating
    # aggressor and the per-UE best-effort filler (sim/parametric.py:63-64).
    # Named by 5QI rather than by flow_class because "not protected" is a
    # QoS-profile fact, not a scheduler-visible one -- a GBR video flow and
    # a best-effort flood can share flow_class in other scenarios.
    NON_PROTECTED_5QI: frozenset = frozenset({8, 9})

    def protected_fleet_liveness_gap(
        self, record: RunRecord, t_live_s: Optional[float] = None,
        non_protected_5qi: Optional[frozenset] = None,
    ) -> MetricResult:
        """M03's contest restricted to PROTECTED FLEET bearers.

        WHY THIS IS A SEPARATE STATISTIC AND NOT AN EDIT TO M03. M03's domain
        is deliberately every flow -- its panel note says "computed
        generically over any flow's completions" -- and changing it would
        silently re-interpret every historical reading. What is wrong is not
        M03; it is the BINDING of G6 to M03, because G6 asks whether
        background traffic impairs *the fleet* and M03's maximum can be won
        by the background traffic itself.

        Measured: on the four seeds that produced G6's headline failure the
        winning flow was the aggressor (`docs/wp9-plan.md` §24.2), so the
        guarantee was scored on the aggressor's own starvation -- and since a
        QoS-aware scheduler starves a non-GBR flood *by design*, the better an
        arm contained it, the worse its G6 score. The causal direction was
        inverted.

        Returns the same value shape as M03 so a consumer can swap them.
        """
        t_live_s = self.defaults["t_live_s"] if t_live_s is None else t_live_s
        excluded_5qi = (self.NON_PROTECTED_5QI if non_protected_5qi is None
                        else non_protected_5qi)
        keep = {k: fr for k, fr in record.flows.items()
                if fr.qfi not in excluded_5qi}
        if not keep:
            return MetricResult(
                "M20", "protected_fleet_liveness_gap", None, "ok", "ms",
                f"no protected flow in this record (excluded 5QIs: "
                f"{sorted(excluded_5qi)})")
        sub = dataclasses.replace(record, flows=keep)
        res = self._m03_liveness_gap_distribution(sub, t_live_s)
        value = res.value
        if isinstance(value, dict):
            value = {**value, "excluded_5qi": sorted(excluded_5qi)}
        out = MetricResult(
            "M20", "protected_fleet_liveness_gap", value, res.status, "ms",
            f"M03's contest over PROTECTED bearers only, excluding 5QIs "
            f"{sorted(excluded_5qi)}; {res.note}")
        # CARRY M03'S RUN-DERIVED CAVEATS. This delegates to _m03 and then
        # built a fresh MetricResult from value/status/note only, silently
        # dropping `res.caveats` -- so when the winning PROTECTED flow's own
        # median gap already exceeded the bound, M03 said "CADENCE, NOT
        # LIVENESS: do not score it against that bound" and M20 said nothing.
        #
        # That is the exact loss score() at :156-163 exists to prevent, on
        # the one metric G6's verdict binds to. Verified by probe: one 5QI-1
        # flow at a 1000 ms cadence, no aggressor -- identical value, and
        # only M03 carried the caveat.
        #
        # Panel caveats are NOT added here; score() prepends those for every
        # metric uniformly, and doing it in both places would duplicate them.
        out.caveats = list(res.caveats or [])
        return out

    @staticmethod
    def robust_delta_summary(deltas: list[float]) -> dict:
        """A summary for a per-seed delta distribution on a MAX-type
        statistic, where the mean of ratios is not a robust estimator.

        The G6 cell that motivated this had **mean +136.84 %** while its
        **median was -0.22 % and 21 of 40 seeds IMPROVED** -- the mean was
        carried by four seeds. Reporting the mean alone said the guarantee
        failed; reporting the median alone said it was untouched. Both are
        returned, plus the quartiles, the count, and the fraction of seeds
        that actually got worse, so a reader can see the disagreement instead
        of inheriting whichever estimator was chosen.
        """
        n = len(deltas)
        if n == 0:
            return {"n": 0, "mean": float("nan"), "median": float("nan"),
                    "p25": float("nan"), "p75": float("nan"),
                    "frac_worse": float("nan")}
        ordered = sorted(deltas)

        def _q(frac: float) -> float:
            return ordered[min(n - 1, int(n * frac))]

        return {
            "n": n,
            "mean": sum(deltas) / n,
            "median": statistics.median(deltas),
            "p25": _q(0.25),
            "p75": _q(0.75),
            "frac_worse": sum(1 for d in deltas if d > 0) / n,
        }

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
                        # Both halves of the threshold, not just the newly-
                        # added one -- pdb_ms varies per flow, so "fraction"
                        # alone is meaningless without it too. Found in
                        # WP7's end-of-WP review: Decision #3 asked only for
                        # survival_time_ms, but a fraction is just as
                        # unquotable without knowing which pdb_ms it was
                        # measured against.
                        "pdb_ms": fr.pdb_ms,
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
            candidates.append((fr.key, on_time / total, total, fr.pdb_ms))
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
        worst_key, worst_fraction, worst_total, worst_pdb_ms = min(candidates, key=lambda kv: kv[1])
        return MetricResult(
            "M05", "pdu_set_completeness",
            # pdb_ms travels with the value -- found in WP7's end-of-WP
            # review: pdb_ms varies per flow, so "fraction" alone doesn't
            # say what it was measured against, the same class of gap
            # Decision #3 exists to prevent for M14's survival_time_ms.
            {"flow": worst_key, "fraction": worst_fraction, "frame_count": worst_total,
             "pdb_ms": worst_pdb_ms},
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
                # Technically recoverable from source_fps (1000/source_fps),
                # but labelled explicitly rather than left as an inversion
                # the reader has to do -- found in WP7's end-of-WP review,
                # same class of gap as M05/M14's missing pdb_ms: this is the
                # threshold freeze_count was actually measured against.
                "xr_frame_period_ms": period_ms,
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
        if record.timeseries_resolution != "slot":
            return MetricResult("M04", "survival_time_failures", None,
                                "pending", "count", self._FOLDED_REASON)
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
            # Both series are bucketed ONCE per flow. The arrived bucketing
            # used to sit inside the per-second loop below, which re-scanned
            # the whole arrived array once per second and discarded all but
            # one bucket each time -- O(flows x seconds x slots), i.e.
            # QUADRATIC in horizon. Measured on one record: 0.215 s at 20,000
            # slots, 3.627 s at 80,000, 17.792 s at 160,000, and the sweep
            # evaluates M09 13 times per record. Extrapolated to a 30-minute
            # soak (7.2M slots) that is 10-31 h PER EVALUATION depending on
            # which growth exponent you fit, against 43 s-5.1 min hoisted.
            # G11 is not runnable without this (docs/wp9-plan.md §37,
            # docs/wp9-g11-plan.md §4.1).
            #
            # The VALUE is unchanged and that is asserted, not assumed:
            # sim/tests/test_m09_hoist.py checks bit-identity against a
            # reference implementation of the original nesting, and a
            # SCALING test pins the complexity class -- an output test
            # cannot catch a re-introduced quadratic.
            delivered_by_sec = _bucket_by_second(time_s, fr.ts_delivered_bytes)
            arrived_by_sec = _bucket_by_second(time_s, fr.ts_arrived_bytes)
            for sec, delivered_list in delivered_by_sec.items():
                arrived_list = arrived_by_sec[sec]
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

    def _m22_starvation_epochs(
        self, record: RunRecord, min_epoch_s: float = 1.0,
    ) -> MetricResult:
        """G8's SECOND conjunct, which had no instrument at all.

        G8 is a conjunction -- "per-1 s Jain >= 0.9 per role across assets;
        AND zero starvation epochs >= 1 s". M08 and M09 were the only metrics
        bound to it and neither can express the second half. M09 in
        particular scores `delivered / arrived` with a hardcoded 1.0 when
        `arrived == 0`, so a flow delivering nothing reads as PERFECTLY FAIR
        exactly when it is most starved.

        DELIVERY silence, bounded to the flow's OWN active interval. A run of
        consecutive seconds with zero delivered bytes counts only between
        that flow's first and last arrival, so a flow that has not started
        yet, or has finished, is never charged for the silence. Backlog is
        deliberately not consulted: the per-second fold drops the LEVEL
        series, and a metric that needed them could not be scored on the
        configuration G11 runs (config/metric_panel.yml's M22 caveat).
        """
        if not record.timeseries_time_s:
            return MetricResult(
                "M22", "starvation_epochs", None, "pending", "count",
                "requires driver.run(..., record_timeseries=True)")
        time_s = record.timeseries_time_s
        dt = (time_s[1] - time_s[0]) if len(time_s) > 1 else 1.0
        need = max(1, int(round(min_epoch_s / dt))) if dt > 0 else 1
        total, worst_flow, longest = 0, None, 0
        scored = 0
        for fr in record.flows.values():
            arr, dlv = fr.ts_arrived_bytes, fr.ts_delivered_bytes
            if not arr or not dlv:
                continue
            live = [i for i, a in enumerate(arr) if a > 0]
            if not live:
                continue          # never offered anything: not starvation
            scored += 1
            lo, hi = live[0], live[-1]
            run_len = 0
            for i in range(lo, hi + 1):
                if dlv[i] == 0:
                    run_len += 1
                    continue
                if run_len >= need:
                    total += 1
                    if run_len > longest:
                        longest, worst_flow = run_len, fr.key
                run_len = 0
            if run_len >= need:
                total += 1
                if run_len > longest:
                    longest, worst_flow = run_len, fr.key
        if not scored:
            return MetricResult(
                "M22", "starvation_epochs", None, "ok", "count",
                "no flow had any arrival in the timeseries; nothing to score")
        return MetricResult(
            "M22", "starvation_epochs",
            {"epochs": total, "worst_flow": worst_flow,
             "longest_epoch_s": longest * dt, "min_epoch_s": min_epoch_s,
             "flows_scored": scored},
            "ok", "count",
            f"runs of >= {min_epoch_s}s with zero delivered bytes, per flow, "
            f"bounded to each flow's own first..last arrival; "
            f"{scored}/{len(record.flows)} flow(s) had any arrival",
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
        if record.message_ledger_windowed:
            return MetricResult("M15", "command_jitter_p99_p50", None,
                                "pending", "ms", self._WINDOWED_REASON)
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

    def _m18_rejoin_interruption_time(self, record: RunRecord) -> MetricResult:
        """WP-Join commit 4 (config/metric_panel.yml). Every record today
        has join_events is None (predates WP-Join) or [] (no scenario yet
        populates it) -- this always reports pending until commit 5 wires
        a real UEConfig.join scenario, but the computation itself is
        written now (not deferred) so commits 5/6 need touch nothing here,
        only config/metric_panel.yml's status field (docs/wp-join-plan.md
        sec4's own commit/file mapping)."""
        if record.join_events is None:
            return MetricResult(
                "M18", "rejoin_interruption_time", None, "pending", "ms",
                "requires WP-Join (RunRecord.join_events); record predates it",
            )
        if not record.join_events:
            return MetricResult(
                "M18", "rejoin_interruption_time", None, "pending", "ms",
                "no join/re-join/re-establishment events occurred this run",
            )
        by_path: dict[str, Any] = {}
        for path in ("warm", "cold", "reestablish"):
            events = [e for e in record.join_events if e.path == path]
            if not events:
                continue
            completed = [e for e in events if e.attached_ts_s is not None]
            n_never_completed = len(events) - len(completed)
            durations_ms = [(e.attached_ts_s - e.trigger_ts_s) * 1000.0 for e in completed]
            phase_samples: dict[str, list[float]] = {}
            for e in completed:
                for phase_name, dur_ms in e.phases.items():
                    phase_samples.setdefault(phase_name, []).append(dur_ms)
            entry: dict[str, Any] = {
                "n_events": len(events),
                "n_never_completed": n_never_completed,
                "p50_ms": _percentile(durations_ms, 0.50) if durations_ms else None,
                "p95_ms": _percentile(durations_ms, 0.95) if durations_ms else None,
                "max_ms": max(durations_ms) if durations_ms else None,
                "phase_p95_ms": {k: _percentile(v, 0.95) for k, v in phase_samples.items()},
                "timer_expiry_count": sum(sum(e.timer_expiries.values()) for e in events),
            }
            if path == "reestablish":
                # GT-6.3's own pass line is measured from RF-restore, not
                # from RLF declaration (config/metric_panel.yml's own
                # definition) -- reported alongside, never in place of,
                # the trigger-to-attach figure above.
                rf_durations_ms = [
                    (e.attached_ts_s - e.rf_restore_ts_s) * 1000.0
                    for e in completed if e.rf_restore_ts_s is not None
                ]
                entry["rf_restore_to_attached_p95_ms"] = (
                    _percentile(rf_durations_ms, 0.95) if rf_durations_ms else None
                )
            by_path[path] = entry
        return MetricResult(
            "M18", "rejoin_interruption_time", {"by_path": by_path}, "ok", "ms",
            "computed directly from RunRecord.join_events' timestamps; events "
            "that never completed before the run's horizon are counted "
            "(n_never_completed), not excluded",
        )

    def _m19_slo_recovery_time(self, record: RunRecord, slo_green_dwell_s: float) -> MetricResult:
        if record.timeseries_resolution != "slot":
            return MetricResult("M19", "slo_recovery_time", None,
                                "pending", "ms", self._FOLDED_REASON)
        """WP-Join commit 4. Same always-pending-today shape as M18 above
        -- see that method's docstring."""
        if record.join_events is None:
            return MetricResult(
                "M19", "slo_recovery_time", None, "pending", "ms",
                "requires WP-Join (RunRecord.join_events); record predates it",
            )
        if not record.join_events:
            return MetricResult(
                "M19", "slo_recovery_time", None, "pending", "ms",
                "no join/re-join/re-establishment events occurred this run",
            )
        if not record.has_timeseries():
            return MetricResult(
                "M19", "slo_recovery_time", None, "pending", "ms",
                "requires record_timeseries=True; record has none",
            )
        time_s = record.timeseries_time_s
        by_path: dict[str, Any] = {}
        for path in ("warm", "cold", "reestablish"):
            events = [e for e in record.join_events if e.path == path]
            if not events:
                continue
            durations_ms = []
            n_never_recovered = 0
            for e in events:
                start_ts_s = (
                    e.rf_restore_ts_s if path == "reestablish" and e.rf_restore_ts_s is not None
                    else e.trigger_ts_s
                )
                ue_flows = [
                    fr for fr in record.flows.values()
                    if fr.ue_id == e.ue_id and fr.ts_hol_delay_s is not None
                ]
                recovered_ts_s = self._first_sustained_green(
                    time_s, ue_flows, start_ts_s, slo_green_dwell_s
                )
                if recovered_ts_s is None:
                    n_never_recovered += 1
                    continue
                durations_ms.append((recovered_ts_s - start_ts_s) * 1000.0)
            by_path[path] = {
                "n_events": len(events),
                "n_never_recovered": n_never_recovered,
                "p50_ms": _percentile(durations_ms, 0.50) if durations_ms else None,
                "p95_ms": _percentile(durations_ms, 0.95) if durations_ms else None,
                "max_ms": max(durations_ms) if durations_ms else None,
                "slo_green_dwell_s": slo_green_dwell_s,
            }
        return MetricResult(
            "M19", "slo_recovery_time", {"by_path": by_path}, "proxy", "ms",
            "proxy: 'green' is judged from head-of-line delay against each "
            "flow's own pdb_ms only, not a full GFBR contract check -- an "
            "exact per-message SLO evaluation reusing WP7's message ledger "
            "is a follow-on commit, not this one; events never green before "
            "the run ends are counted (n_never_recovered), not excluded",
        )

    def slo_recovery_time_by_delivery(
        self, record: RunRecord, window_s: float = 1.0,
        violation_ceiling: float = 0.01,
    ) -> MetricResult:
        """M21 -- M19's companion, judging "green" by DELIVERY rather than by
        head-of-line age.

        WHY THIS EXISTS AND WHY M19 IS NOT EDITED. M19's green test is
        `hol_delay <= pdb_ms` on every flow, and `sim/buffer.py::expire()`
        pops any chunk older than the PDB **every slot** -- so head-of-line
        age is capped at `pdb_s` BY CONSTRUCTION and `hol > pdb_ms` is never
        true. Measured on G9's own scenarios: **0 of 20,000 and 0 of 30,000
        slots** exceed PDB on any flow, with max HoL exactly `pdb_ms`, while
        the recovering UE drops **1,396,203 bytes** of video. M19 reads green
        throughout a total outage.

        So M19's registered caveat understates it: the metric does not merely
        *risk* reading a never-delivering flow as green, it **cannot report
        red at all**. That is not fixable by scenario design -- no amount of
        breaking the UE makes `hol` exceed a bound `expire()` enforces.

        **M19 is left exactly as it is** (editing a pre-registered metric is
        what `config/metric_panel.yml`'s guard forbids, and every historical
        M19 reading must keep meaning what it meant). This is an ADDITION,
        the same disposition Step 2 used for M03/M20.

        "Green" here is a window in which the UE's flows drop or deliver-late
        no more than `violation_ceiling` of their arriving bytes -- the
        M02-style test M19's own caveat names as the true fix.
        """
        if record.timeseries_resolution != "slot":
            return MetricResult("M21", "slo_recovery_time_by_delivery", None,
                                "pending", "ms", self._FOLDED_REASON)
        if record.join_events is None:
            return MetricResult("M21", "slo_recovery_time_by_delivery", None,
                                "pending", "ms",
                                "requires WP-Join (RunRecord.join_events)")
        if not record.join_events:
            return MetricResult("M21", "slo_recovery_time_by_delivery", None,
                                "pending", "ms",
                                "no join/re-join/re-establishment events this run")
        if not record.has_timeseries():
            return MetricResult("M21", "slo_recovery_time_by_delivery", None,
                                "pending", "ms", "requires record_timeseries=True")

        time_s = record.timeseries_time_s
        by_path: dict[str, Any] = {}
        for path in ("warm", "cold", "reestablish"):
            events = [e for e in record.join_events if e.path == path]
            if not events:
                continue
            durations_ms, n_never = [], 0
            for e in events:
                start = (e.rf_restore_ts_s
                         if path == "reestablish" and e.rf_restore_ts_s is not None
                         else e.trigger_ts_s)
                flows = [fr for fr in record.flows.values()
                         if fr.ue_id == e.ue_id
                         and fr.ts_arrived_bytes is not None
                         and fr.ts_dropped_bytes is not None]
                ts = self._first_sustained_delivering(
                    time_s, flows, start, window_s, violation_ceiling)
                if ts is None:
                    n_never += 1
                else:
                    durations_ms.append((ts - start) * 1000.0)
            by_path[path] = {
                "n_events": len(events), "n_never_recovered": n_never,
                "p50_ms": _percentile(durations_ms, 0.50) if durations_ms else None,
                "p95_ms": _percentile(durations_ms, 0.95) if durations_ms else None,
                "max_ms": max(durations_ms) if durations_ms else None,
                "window_s": window_s, "violation_ceiling": violation_ceiling,
            }
        return MetricResult(
            "M21", "slo_recovery_time_by_delivery", {"by_path": by_path},
            "ok", "ms",
            f"green = a {window_s}s window in which the UE's flows drop or "
            f"deliver-late <= {violation_ceiling:.0%} of arriving bytes; "
            f"companion to M19, which cannot report red because expire() "
            f"caps head-of-line age at pdb_ms")

    def _first_sustained_delivering(
        self, time_s: list[float], ue_flows: list[FlowRecord], start_ts_s: float,
        window_s: float, ceiling: float,
    ) -> Optional[float]:
        """First timestamp >= start_ts_s from which every flow keeps its
        dropped-byte fraction at or below `ceiling` for `window_s`."""
        if not ue_flows or not time_s:
            return None
        n = len(time_s)
        dt = (time_s[1] - time_s[0]) if n > 1 else 0.0
        if dt <= 0:
            return None
        need = max(1, int(round(window_s / dt)))
        # A WINDOWED ratio, not a per-slot one. The first version compared
        # bytes dropped in slot i against bytes that ARRIVED in slot i --
        # but a chunk is dropped `pdb_ms` AFTER it arrived (expire()), so
        # those are different bytes and the ratio was near-meaningless. It
        # returned 0.25 ms on a UE that had just lost 1.4 MB. Summing both
        # over the same window removes the offset and matches M02's own
        # byte-weighted form, which is what M19's caveat names as the fix.
        for start_i, ts in enumerate(time_s):
            if ts < start_ts_s:
                continue
            end_i = start_i + need
            if end_i > len(time_s):
                return None           # not enough run left to confirm a window
            ok = True
            for fr in ue_flows:
                arr = sum(fr.ts_arrived_bytes[start_i:end_i])
                drp = sum(fr.ts_dropped_bytes[start_i:end_i])
                if arr <= 0:
                    continue          # nothing offered in the window
                if drp / arr > ceiling:
                    ok = False
                    break
            if ok:
                return ts
        return None

    def _first_sustained_green(
        self, time_s: list[float], ue_flows: list[FlowRecord], start_ts_s: float, dwell_s: float,
    ) -> Optional[float]:
        """First timestamp >= start_ts_s at which every one of ue_flows'
        head-of-line delays has stayed within its own pdb_ms for at least
        dwell_s continuously. None if that never happens before the run
        ends, or if the UE has no flow with timeseries data at all."""
        if not ue_flows:
            return None
        start_idx = next((i for i, t in enumerate(time_s) if t >= start_ts_s), None)
        if start_idx is None:
            return None
        green_since: Optional[float] = None
        for i in range(start_idx, len(time_s)):
            t = time_s[i]
            all_green = all(
                i < len(fr.ts_hol_delay_s) and fr.ts_hol_delay_s[i] <= fr.pdb_ms / 1000.0
                for fr in ue_flows
            )
            if all_green:
                if green_since is None:
                    green_since = t
                elif t - green_since >= dwell_s:
                    return green_since
            else:
                green_since = None
        return None

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
