"""RunRecord -- the scorecard's input contract (WP0).

``sim.driver.run()`` returns a loosely-typed dict (see ``Metrics.summary``).
That's the right shape for the driver -- it doesn't know about QoS
contracts, guarantees, or scoring. The scorecard needs more: per-flow QoS
metadata (GFBR, PDB, flow class) joined against the delivery stats, plus
enough run/scenario identity that a study can tell two rows apart.

``RunRecord`` is that join, typed and JSON-round-trippable so
``scripts/regression_corpus.py`` can snapshot it and diff a later run
against the snapshot. Building it here, once, means the scorecard (and any
future consumer) never re-derives the flow-key join or re-guesses which
timeseries fields are optional.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from scheduler.flow import FlowConfig

SCHEMA_VERSION = 1


def flow_key(ue_id: int, qfi: int) -> str:
    """The same key convention sim.metrics.Metrics.summary() uses."""
    return f"ue{ue_id}_qfi{qfi}"


@dataclass
class FlowRecord:
    """One flow's QoS contract joined against its measured delivery stats.

    Fields ending ``_proxy`` carry the honesty flag from
    config/metric_panel.yml inline, so a consumer never has to cross-
    reference the panel to know whether a number is exact.
    """

    ue_id: int
    qfi: int
    direction: str  # "DL" or "UL"
    flow_class: str  # "PF" | "GBR" | "Delay"
    gfbr_bps: float
    pdb_ms: float
    priority_level: int

    bytes_arrived: int
    bytes_delivered: int
    bytes_dropped_pdb: int
    # Delivered, but after the flow's own PDB had already passed -- the
    # "delivered, but later than PDB" component of M02 (config/metric_
    # panel.yml). 0 on records predating this field. Distinct from
    # bytes_dropped_pdb (bytes that never reached delivery at all).
    bytes_delivered_late_pdb: int
    throughput_bps: float
    offered_bps: float
    delivery_ratio: float

    # Proxy delay percentiles -- head-of-line age sampled per slot, NOT true
    # per-message completion latency. See config/metric_panel.yml M01.
    delay_p50_ms_proxy: float
    delay_p95_ms_proxy: float
    delay_p99_ms_proxy: float
    delay_p98_ms_proxy: Optional[float] = None  # None on records from before p98 was added

    # True per-message completion-latency percentiles (WP7), over fully-
    # delivered messages only -- sim/messages.py::message_latency_
    # percentiles_ms. None on records from before WP7's message ledger was
    # wired up; scorecard.py falls back to the _proxy fields in that case.
    delay_p50_ms: Optional[float] = None
    delay_p95_ms: Optional[float] = None
    delay_p98_ms: Optional[float] = None
    delay_p99_ms: Optional[float] = None
    # Count of fully-delivered messages the percentiles above were computed
    # over. 0 is a real "no message completed," distinct from None ("this
    # record predates WP7 and was never given true-latency fields at all").
    message_count: Optional[int] = None
    # WP7 M03 (liveness_gap_distribution): completion timestamps of fully-
    # delivered messages, grouped by Message.role. None on records that
    # predate this field; {} is a real "flow generated no completions",
    # distinct from None -- same never-None-post-WP7 convention as
    # message_count. scorecard.py derives gaps and applies its own T_live
    # threshold from these rather than a driver-computed count, since the
    # threshold is a scoring-time choice, not a simulation output.
    completion_ts_by_role_s: Optional[dict[str, list[float]]] = None
    # WP7 M05/M06 (pdu_set_completeness, frame_age_at_mec): {"total": int,
    # "complete_ages_ms": list[float]}, from grouping the same ledger
    # completions by Message.frame_id (sim/messages.py::FrameLedger). total
    # counts every frame this flow generated (xr_video only; 0 for every
    # other kind, real "no frames" -- distinct from None, "predates this
    # field"); complete_ages_ms holds only fully-delivered frames' ages, so
    # M05's denominator (total) and numerator (on-time completions) can
    # both be computed at score time against the flow's own pdb_ms, without
    # this field baking in a threshold.
    frame_completions: Optional[dict[str, Any]] = None
    # WP7 M17 (frame_freeze_and_effective_fps): the flow's configured
    # nominal frame period, copied from FlowConfig.traffic_params
    # ["period_ms"] when traffic_kind=="xr_video", else None -- not
    # derivable from frame_completions alone (total/horizon_s would give
    # this simulator's own slot-quantised firing interval, not the source's
    # actual claimed frame rate; a freeze must be judged against the
    # latter, docs/wp7-plan.md's commit-7 note). None for every non-xr_video
    # flow -- not a "predates this field" marker like the Optional fields
    # above, since a fresh dataclass default can't distinguish those two
    # cases; scorecard.py gates on frame_completions["complete_ts_s"]'s
    # presence instead.
    xr_frame_period_ms: Optional[float] = None
    # WP7 M14 (communication_service_availability): copied from
    # FlowConfig.survival_time_ms (scheduler/flow.py, dormant at 0.0 --
    # docs/wp7-plan.md Decision #3). A plain float like pdb_ms/gfbr_bps,
    # not Optional -- it's a static config value always present once this
    # field exists at all, not a "predates WP7" sentinel; M14's own
    # pending/ok gate reuses M03's completion_ts_by_role_s check instead.
    survival_time_ms: float = 0.0
    # The source's CONFIGURED inter-arrival period, from
    # FlowConfig.traffic_params["period_ms"]. None for a flow whose kind has
    # no period (poisson, xr_video's frame model, aperiodic_event).
    #
    # WHY A RECORD FIELD AND NOT A SCORECARD LOOKUP: sim/scorecard.py is
    # forbidden from importing sim/config.py, and consumes RunRecord only, so
    # a scorer that needs to know whether a source is slow BY DESIGN can only
    # learn it from the record. Without it, M03's cadence caveat had to infer
    # the answer from the MEASURED median -- which cannot tell "configured
    # slow" from "degraded by the network until the median got large", and so
    # suppressed 4 of 44 real duty-0.5 breaches in sweeps/wp9/part_c_rows.csv
    # (observed medians 596/602/551/525 ms against a 200 ms configured
    # period).
    configured_period_ms: Optional[float] = None

    # WP5 commit 4a (docs/wp5-plan.md): bytes abandoned after HARQ
    # max-retx exhaustion -- distinct from bytes_dropped_pdb (PDB-clock
    # discard) and bytes_delivered_late_pdb (delivered, just late). Placed
    # here (defaulted), not among the required fields above, for the same
    # dataclass-field-ordering reason survival_time_ms is here rather than
    # beside pdb_ms -- a later field can't default ahead of an earlier
    # required one. 0 is unambiguous on a pre-4a record (the mechanism
    # didn't exist, so genuinely zero bytes were ever dropped this way) --
    # unlike message_count/etc., no Optional/None "predates this field"
    # sentinel is needed. NOT yet folded into M02 (config/metric_panel.
    # yml) -- see docs/wp5-plan.md commit 4a for that deliberately
    # separate gap.
    bytes_harq_lost: int = 0

    # Populated only when driver.run(..., record_timeseries=True) was used.
    # Per-slot series, aligned to RunRecord.timeseries_time_s.
    ts_backlog_bytes: Optional[list[int]] = None
    ts_hol_delay_s: Optional[list[float]] = None
    ts_delivered_bytes: Optional[list[int]] = None
    ts_arrived_bytes: Optional[list[int]] = None
    ts_dropped_bytes: Optional[list[int]] = None

    @property
    def key(self) -> str:
        return flow_key(self.ue_id, self.qfi)

    def gfbr_fraction(self) -> Optional[float]:
        """delivered / GFBR. None for non-GBR flows (GFBR is meaningless)."""
        if self.flow_class != "GBR" or self.gfbr_bps <= 0:
            return None
        return self.throughput_bps / self.gfbr_bps

    def meets_gbr_contract(self, fraction: float = 0.95) -> Optional[bool]:
        g = self.gfbr_fraction()
        return None if g is None else g >= fraction

    def has_timeseries(self) -> bool:
        return self.ts_hol_delay_s is not None


@dataclass
class JoinEventRecord:
    """One join/re-join/re-establishment event (WP-Join commit 4, docs/
    wp-join-plan.md sec5). Assembled by sim/driver.py from sim/join.py's
    JoinStepResult edges once commit 5/6 wire the mechanism live -- this
    dataclass carries no computation of its own, only raw timestamps/
    counts, the same "thresholding happens in scorecard.py, not here"
    discipline M03/M14 already use for T_live.

    ``rf_restore_*``/``rlf_declared_at_slot`` are only ever set for
    ``path == "reestablish"``; ``attached_*`` is None iff the event never
    completed before the run's horizon (counted, not excluded, by M18/
    M19 -- see config/metric_panel.yml)."""

    ue_id: int
    path: str  # "warm" | "cold" | "reestablish"
    trigger_slot: int
    trigger_ts_s: float
    rf_restore_slot: Optional[int] = None
    rf_restore_ts_s: Optional[float] = None
    attached_slot: Optional[int] = None
    attached_ts_s: Optional[float] = None
    phases: dict[str, float] = field(default_factory=dict)  # phase name -> duration_ms
    timer_expiries: dict[str, int] = field(default_factory=dict)  # phase name -> count
    rlf_declared_at_slot: Optional[int] = None
    handshake_rtt_ms: Optional[float] = None


@dataclass
class SystemRecord:
    horizon_s: float
    dl_prb_utilization: float
    ul_prb_utilization: float
    cce_utilization: float
    # System-level per-slot series, present only with record_timeseries=True.
    ts_dl_prbs_used: Optional[list[int]] = None
    ts_ul_prbs_used: Optional[list[int]] = None
    ts_dl_prbs_avail: Optional[list[int]] = None
    ts_ul_prbs_avail: Optional[list[int]] = None
    ts_cce_used: Optional[list[int]] = None
    ts_cce_budget: Optional[list[int]] = None


@dataclass
class RunRecord:
    """One (scenario, scheduler, seed[, arm]) run, typed and scoreable."""

    schema_version: int
    scenario_name: str
    scheduler_name: str
    seed: int
    arm: dict[str, Any]  # e.g. {"cqi_delay_slots": 8}
    flows: dict[str, FlowRecord]
    system: SystemRecord
    timeseries_time_s: Optional[list[float]] = None
    timeseries_slot_index: Optional[list[int]] = None
    # WP9 G11 commit 2. True when driver.run() drained the message ledger
    # per window. Without this flag a consumer cannot tell None-because-
    # EVICTED from None-because-PRE-WP7, and scorecard.py's M01/M15 would
    # silently fall back to the head-of-line proxy -- a different estimator
    # reported under the same metric id.
    message_ledger_windowed: bool = False
    # WP9 G11 commit 3. "slot" (default) or "second". Under "second" the
    # per-flow COUNT series are per-second sums -- lossless for M09 and
    # M08w, which bucket by second anyway -- and the LEVEL series
    # (backlog_bytes, hol_delay_s) are absent, because a sum of levels is
    # meaningless and a max would be a different statistic under the same
    # name. M04/M19/M21 report pending rather than reading one as the other.
    timeseries_resolution: str = "slot"
    meta: dict[str, Any] = field(default_factory=dict)
    # WP-Join commit 4/5 (docs/wp-join-plan.md sec5): None means "this
    # record was produced by a driver.run() that predates commit 5's
    # wiring" -- from commit 5 onward, EVERY record gets a real list,
    # [] included, regardless of whether the scenario's UEs opt into
    # UEConfig.join (from_summary keys this off "join_events" in summary
    # at all, not off any UE's own config). [] is a real "this run had
    # zero join/RLF events" -- the same never-None-post-landing
    # convention message_count/completion_ts_by_
    # role_s already establish above.
    join_events: Optional[list[JoinEventRecord]] = None

    def has_timeseries(self) -> bool:
        return self.timeseries_time_s is not None

    def flow(self, ue_id: int, qfi: int) -> FlowRecord:
        return self.flows[flow_key(ue_id, qfi)]

    def flows_by(self, **predicates) -> list[FlowRecord]:
        """Filter flows by attribute equality, e.g. flows_by(flow_class='GBR')."""
        out = []
        for fr in self.flows.values():
            if all(getattr(fr, k) == v for k, v in predicates.items()):
                out.append(fr)
        return out

    def to_dict(self) -> dict:
        d = {
            "schema_version": self.schema_version,
            "scenario_name": self.scenario_name,
            "scheduler_name": self.scheduler_name,
            "seed": self.seed,
            "arm": self.arm,
            "flows": {k: asdict(v) for k, v in self.flows.items()},
            "system": asdict(self.system),
            "timeseries_time_s": self.timeseries_time_s,
            "timeseries_slot_index": self.timeseries_slot_index,
            "meta": self.meta,
            "join_events": (
                [asdict(e) for e in self.join_events] if self.join_events is not None else None
            ),
        }
        # WP9 G11 commit 2. Emitted ONLY when true, so a non-windowed
        # record serialises byte-identically to before this commit and the
        # frozen regression corpus is untouched. from_dict defaults to
        # False on absence, so the round trip is total either way.
        if self.message_ledger_windowed:
            d["message_ledger_windowed"] = True
        if self.timeseries_resolution != "slot":
            d["timeseries_resolution"] = self.timeseries_resolution
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RunRecord":
        return cls(
            schema_version=d["schema_version"],
            scenario_name=d["scenario_name"],
            scheduler_name=d["scheduler_name"],
            seed=d["seed"],
            arm=d["arm"],
            flows={k: FlowRecord(**v) for k, v in d["flows"].items()},
            system=SystemRecord(**d["system"]),
            timeseries_time_s=d.get("timeseries_time_s"),
            timeseries_slot_index=d.get("timeseries_slot_index"),
            message_ledger_windowed=bool(d.get("message_ledger_windowed", False)),
            timeseries_resolution=d.get("timeseries_resolution", "slot"),
            meta=d.get("meta", {}),
            join_events=(
                [JoinEventRecord(**e) for e in d["join_events"]]
                if d.get("join_events") is not None else None
            ),
        )

    @classmethod
    def from_summary(
        cls,
        *,
        scenario_name: str,
        scheduler_name: str,
        seed: int,
        flow_configs: list[FlowConfig],
        summary: dict,
        arm: Optional[dict[str, Any]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> "RunRecord":
        """Build a RunRecord from sim.driver.run()'s output dict.

        ``flow_configs`` is ``scenario.flows`` -- the QoS metadata driver.run()
        doesn't carry in its summary. ``summary["_ue_lcp"]`` and
        ``summary["_message_ledger"]`` (WP7) -- both live objects, not
        JSON-serialisable -- are intentionally dropped here; neither is read
        by this method at all.
        """
        meta_by_key = {flow_key(f.ue_id, f.qfi): f for f in flow_configs}
        ts = summary.get("timeseries") or {}
        ts_per_flow = ts.get("per_flow", {})

        flows: dict[str, FlowRecord] = {}
        for fk, m in summary["flows"].items():
            fc = meta_by_key.get(fk)
            if fc is None:
                raise KeyError(
                    f"summary has flow {fk!r} with no matching FlowConfig in "
                    f"flow_configs -- scenario/summary mismatch"
                )
            fts = ts_per_flow.get(fk)
            flows[fk] = FlowRecord(
                ue_id=fc.ue_id,
                qfi=fc.qfi,
                direction=fc.direction,
                flow_class=fc.flow_class,
                gfbr_bps=fc.gfbr_bps,
                pdb_ms=fc.pdb_ms,
                priority_level=fc.priority_level,
                survival_time_ms=fc.survival_time_ms,
                configured_period_ms=(fc.traffic_params or {}).get("period_ms"),
                bytes_arrived=m["bytes_arrived"],
                bytes_delivered=m["bytes_delivered"],
                bytes_dropped_pdb=m["bytes_dropped"],
                bytes_delivered_late_pdb=m.get("bytes_delivered_late_pdb", 0),
                bytes_harq_lost=m.get("bytes_harq_lost", 0),
                throughput_bps=m["throughput_bps"],
                offered_bps=m["offered_bps"],
                delivery_ratio=m["delivery_ratio"],
                delay_p50_ms_proxy=m["hol_p50_ms"],
                delay_p95_ms_proxy=m["hol_p95_ms"],
                delay_p99_ms_proxy=m["hol_p99_ms"],
                delay_p98_ms_proxy=m.get("hol_p98_ms"),
                delay_p50_ms=m.get("delay_p50_ms"),
                delay_p95_ms=m.get("delay_p95_ms"),
                delay_p98_ms=m.get("delay_p98_ms"),
                delay_p99_ms=m.get("delay_p99_ms"),
                message_count=m.get("message_count"),
                completion_ts_by_role_s=m.get("completion_ts_by_role_s"),
                frame_completions=m.get("frame_completions"),
                xr_frame_period_ms=(
                    fc.traffic_params.get("period_ms") if fc.traffic_kind == "xr_video" else None
                ),
                # .get, not [...]: under WP9 G11 commit 3's per-second fold
                # the LEVEL series are absent by design (a sum of levels is
                # meaningless), so a folded record carries only the COUNT
                # series. Absent must read as None, not raise.
                ts_backlog_bytes=fts.get("backlog_bytes") if fts else None,
                ts_hol_delay_s=fts.get("hol_delay_s") if fts else None,
                ts_delivered_bytes=fts.get("delivered_bytes") if fts else None,
                ts_arrived_bytes=fts.get("arrived_bytes") if fts else None,
                ts_dropped_bytes=fts.get("dropped_bytes") if fts else None,
            )

        sysd = ts.get("system", {})
        system = SystemRecord(
            horizon_s=summary["horizon_s"],
            dl_prb_utilization=summary["dl_prb_utilization"],
            ul_prb_utilization=summary["ul_prb_utilization"],
            cce_utilization=summary["cce_utilization"],
            ts_dl_prbs_used=sysd.get("dl_prbs_used"),
            ts_ul_prbs_used=sysd.get("ul_prbs_used"),
            ts_dl_prbs_avail=sysd.get("dl_prbs_avail"),
            ts_ul_prbs_avail=sysd.get("ul_prbs_avail"),
            ts_cce_used=sysd.get("cce_used"),
            ts_cce_budget=sysd.get("cce_budget"),
        )

        return cls(
            schema_version=SCHEMA_VERSION,
            scenario_name=scenario_name,
            scheduler_name=scheduler_name,
            seed=seed,
            arm=dict(arm or {}),
            flows=flows,
            system=system,
            timeseries_time_s=ts.get("time_s"),
            timeseries_slot_index=ts.get("slot_index"),
            message_ledger_windowed=bool(summary.get("_ledger_windowed", False)),
            timeseries_resolution=summary.get("timeseries_resolution", "slot"),
            meta=dict(meta or {}),
            # WP-Join commit 5: "join_events" in summary at all (even an
            # empty list) is the signal a WP-Join-aware driver.run() ran --
            # None here means the summary predates that (no key), which is
            # the same never-None-once-landed convention this method
            # already applies via .get() defaults elsewhere, just phrased
            # as key-presence rather than a None-vs-real-value field
            # because driver.py always sets it to at least [] once landed.
            join_events=(
                [JoinEventRecord(**e) for e in summary["join_events"]]
                if "join_events" in summary else None
            ),
        )
