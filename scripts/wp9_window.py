"""Windowed metric variants for WP9 stage 5 (`docs/wp9-plan.md` §16.4).

**What this is for.** Stage 5 perturbs a fleet with a duty-cycled lidar
activation that occupies ~40 % of a 5 s run. Every panel metric is a
run-aggregate, so a lidar-on cell's M01/M02/M07/M08 mix two regimes and
must not be quoted (§16.5's exclusion list). What the operator question
actually asks -- "at what fleet size does one lidar activation start
breaking other flows' PDBs?" -- is a question about the *activation
window*, so stage 5 scores four windowed variants alongside the panel.

**What this must not depend on.** Study layer, not panel:
`config/metric_panel.yml` is not edited and these are not registered
metrics. Like `sim/scorecard.py`, this module consumes records and
ledgers only -- it imports no driver and no config, so it can score
anything that produces the same shapes. It is deliberately a pure
function over data it is handed; the sweep runner does the plumbing.

**M01w is a pure restriction of M01; M02w is not a pure restriction of
M02.** M01w reuses `sim.messages.message_latency_percentiles_ms` and M01's
own "exclude flows with zero complete messages" rule, so the only
difference from the panel metric is the sample set. M02w differs in
*accounting* as well as population: panel M02 tags lateness per drained
chunk at drain time (`bytes_delivered_late_pdb`), while M02w counts a
whole message's delivered bytes when `MessageCompletion.late` is set. A
message whose first bytes drained on time and last bytes late is counted
differently by the two. That is why control C3 exists -- M02w is
calibrated against panel M02 at the `full` window before any windowed
number is quoted, and reported as a distinct estimator if the two diverge.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from sim.messages import (FrameLedger, MessageCompletion,
                          message_latency_percentiles_ms)

__all__ = [
    "windowed_flows_from_configs",
    "Window", "WindowedFlow", "DEFAULT_SUBSETS", "LIDAR_QFI", "ESTOP_QFI",
    "TIGHT_PDB_MS", "lidar_windows", "fixed_windows",
    "windowed_flows_from_record", "windowed_metrics",
]

# The UGV lidar bearer. `sim/fleet.py` gives 5QI 4 to exactly one flow in
# exactly one profile, and `build_fleet` omits it entirely unless that UE
# was activated -- so "a 5QI-4 flow that exists" IS "a lidar flow on an
# activated UGV", with no need to re-derive activation here.
LIDAR_QFI = 4
ESTOP_QFI = 85
# §12.2's own threshold for "tight PDB", not a fresh choice.
TIGHT_PDB_MS = 30.0


@dataclass(frozen=True)
class Window:
    """A half-open scoring interval [start_s, end_s)."""
    name: str
    start_s: float
    end_s: float

    def contains(self, t_s: float) -> bool:
        return self.start_s <= t_s < self.end_s

    @property
    def nominal_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class WindowedFlow:
    """Exactly the per-flow inputs the windowed metrics need.

    A flat view rather than a `RunRecord.FlowRecord`, so the metric code
    stays a pure function over data and the record stays an adapter
    concern (`windowed_flows_from_record`).
    """
    key: str
    ue_id: int
    qfi: int
    direction: str
    flow_class: str
    gfbr_bps: float
    pdb_ms: float
    ts_delivered_bytes: Optional[Sequence[int]] = None
    # WP9 G11 commit 6. M09w's per-flow ratio needs the DENOMINATOR too;
    # M05w/M06w need the frames. Added here rather than re-fetched from the
    # record, so the metric functions stay pure over this flat view.
    ts_arrived_bytes: Optional[Sequence[int]] = None
    # The source's own ACTIVE intervals, from FlowConfig.traffic_params.
    # None = "active for the whole run", which is every flow that does not
    # use the activation gate and therefore every pre-G11 caller.
    active_windows: Optional[Sequence[tuple]] = None
    frame_completions: Optional[dict] = None


# The four subsets of §16.4. Predicates rather than precomputed sets so a
# caller can add one without this module knowing about it.
DEFAULT_SUBSETS: dict[str, Callable[[WindowedFlow], bool]] = {
    "non_lidar": lambda f: f.qfi != LIDAR_QFI,
    "tight_pdb": lambda f: f.qfi != LIDAR_QFI and f.pdb_ms <= TIGHT_PDB_MS,
    "estop": lambda f: f.qfi == ESTOP_QFI,
    "lidar_only": lambda f: f.qfi == LIDAR_QFI,
}


def lidar_windows(lidar: Any, horizon_s: float) -> list[Window]:
    """§16.4's five windows, derived from `LidarActivation`'s own fields.

    `during_1` and `during_2` are BOTH computed for every cell regardless
    of how many UEs actually activated -- every cell is scored at all five
    windows so a control pairs with either excursion level at no extra run
    cost. `during_2` is the union window: the second UE starts one
    `stagger_s` later and runs for the same `duration_s`.

    `lidar` may be None (a control cell), in which case the activation
    windows are still emitted at the same coordinates so control and
    excursion rows are directly comparable -- a control's `during_2` is
    exactly the interval in which nothing happened.
    """
    start = 1.5 if lidar is None else float(lidar.start_s)
    duration = 2.0 if lidar is None else float(lidar.duration_s)
    stagger = 0.0 if (lidar is not None and lidar.synchronised) else (
        0.5 if lidar is None else float(lidar.stagger_s))
    d1_end = start + duration
    d2_end = start + stagger + duration
    return [
        Window("pre", 0.0, start),
        Window("during_1", start, d1_end),
        Window("during_2", start, d2_end),
        Window("post", d2_end, horizon_s),
        Window("full", 0.0, horizon_s),
    ]


def windowed_flows_from_record(record: Any) -> list[WindowedFlow]:
    """Adapter: `RunRecord` -> the flat view above. The only place in this
    module that knows a RunRecord's shape."""
    return [
        WindowedFlow(
            key=fr.key, ue_id=fr.ue_id, qfi=fr.qfi, direction=fr.direction,
            flow_class=fr.flow_class, gfbr_bps=fr.gfbr_bps, pdb_ms=fr.pdb_ms,
            ts_delivered_bytes=fr.ts_delivered_bytes,
            ts_arrived_bytes=fr.ts_arrived_bytes,
            frame_completions=fr.frame_completions,
        )
        for fr in record.flows.values()
    ]


def windowed_flows_from_configs(flow_configs: Sequence[Any]) -> list[WindowedFlow]:
    """Adapter: `FlowConfig`s -> the flat view, WITHOUT any timeseries.

    The completion-family metrics (M01w/M02w/M03w/M05w/M06w/M15w) read only
    a flow's identity and contract, never its `ts_*` arrays. Building them
    from the SCENARIO lets a caller score those metrics inside the window
    sink and release the completion batch, instead of retaining every
    window's completions until a RunRecord exists.

    That retention is what this exists to remove: measured at N=4 on the
    real campaign path, holding the batches cost ~348 bytes per completion,
    which at the 7.2 M-slot soak horizon is ~10.6 GB of a ~12.5 GB run --
    i.e. it silently negated the ledger eviction G11 commit 2 added to bound
    exactly this (docs/wp9-defects-log.md #15's "where the memory actually
    goes is not yet established").

    `ts_*` are left None deliberately rather than zero-filled: a metric that
    needs them must fail loudly here, not read an empty run.
    """
    return [
        WindowedFlow(
            key=f"ue{fc.ue_id}_qfi{fc.qfi}", ue_id=fc.ue_id, qfi=fc.qfi,
            direction=fc.direction, flow_class=fc.flow_class,
            gfbr_bps=fc.gfbr_bps, pdb_ms=fc.pdb_ms,
            active_windows=(fc.traffic_params or {}).get("active_windows"),
        )
        for fc in flow_configs
    ]


def fixed_windows(horizon_s: float, width_s: float = 60.0) -> list[Window]:
    """A contiguous partition of the run into fixed-width windows.

    WP9 G11 commit 6: GT-7.1's KPI is "every 60 s window passes", which is a
    PARTITION, unlike `lidar_windows`' five overlapping named intervals.
    The last window is CLIPPED to the horizon rather than extending past it,
    and it is emitted even when short -- M07w/M08w already normalise by
    COVERED duration (samples x dt), so a clipped window is scored on the
    time that actually existed. Dropping it instead would silently shorten
    the run, which is the failure G11's own commit 2 exists to prevent one
    layer down.
    """
    if horizon_s <= 0 or width_s <= 0:
        raise ValueError(f"horizon_s and width_s must be positive, "
                         f"got {horizon_s} and {width_s}")
    out, k = [], 0
    while k * width_s < horizon_s:
        a = k * width_s
        b = min(a + width_s, horizon_s)
        out.append(Window(name=f"w{k:03d}", start_s=a, end_s=b))
        k += 1
    return out


def _flow_key(c: MessageCompletion) -> str:
    return f"ue{c.message.ue_id}_qfi{c.message.qfi}"


def _window_indices(time_s: Optional[Sequence[float]], w: Window) -> list[int]:
    if not time_s:
        return []
    return [i for i, t in enumerate(time_s) if w.contains(t)]


def _sample_dt_s(time_s: Sequence[float]) -> Optional[float]:
    if len(time_s) < 2:
        return None
    return float(time_s[1]) - float(time_s[0])


def _m01w(
    completions: list[MessageCompletion], keys: set[str], w: Window,
) -> dict[str, Any]:
    """Worst flow by p99, over messages GENERATED in the window.

    Selecting on generation time rather than completion time is what makes
    this answer "how did traffic offered during the activation fare?" --
    selecting on completion would credit the window with messages that
    were offered before it and drag the tail across the boundary.
    """
    by_flow: dict[str, list[MessageCompletion]] = {}
    for c in completions:
        k = _flow_key(c)
        if k in keys and w.contains(c.message.generation_ts_s):
            by_flow.setdefault(k, []).append(c)

    stats = {k: message_latency_percentiles_ms(v) for k, v in by_flow.items()}
    # M01's own rule: a flow that fully delivered nothing would report 0 ms
    # -- the LOWEST possible value -- and silently win the "worst" contest.
    delivering = {k: s for k, s in stats.items() if s["count"]}
    excluded = len(stats) - len(delivering)

    row: dict[str, Any] = {
        "window": w.name, "metric": "M01w",
        "n_flows": len(stats), "n_excluded_zero_complete": excluded,
    }
    if not delivering:
        row.update({
            "p50": None, "p95": None, "p98": None, "p99": None, "flow": None,
            "reason": "no flow in this subset completed a message generated "
                      "in this window",
        })
        return row
    worst_key = max(delivering, key=lambda k: delivering[k]["p99"])
    s = delivering[worst_key]
    row.update({
        "p50": s["p50"], "p95": s["p95"], "p98": s["p98"], "p99": s["p99"],
        "flow": worst_key, "n_messages": s["count"],
    })
    return row


def _m02w(
    completions: list[MessageCompletion], keys: set[str], w: Window,
) -> dict[str, Any]:
    """(dropped + delivered-while-late) / (delivered + dropped).

    Denominator is RESOLVED bytes, matching panel M02's own choice -- a
    message still queued at horizon end is neither delivered nor dropped
    and counting it as fine would be systematically optimistic. See this
    module's docstring for why this is NOT a pure restriction of M02, and
    control C3 for the calibration that reports the difference.
    """
    sel = [c for c in completions
           if _flow_key(c) in keys and w.contains(c.message.generation_ts_s)]
    delivered = sum(c.delivered_bytes for c in sel)
    dropped = sum(c.dropped_bytes for c in sel)
    late = sum(c.delivered_bytes for c in sel if c.late)
    resolved = delivered + dropped

    row: dict[str, Any] = {
        "window": w.name, "metric": "M02w",
        "n_completions": len(sel), "resolved_bytes": resolved,
    }
    if resolved <= 0:
        row.update({"value": None,
                    "reason": "no resolved bytes in this window/subset"})
        return row
    row["value"] = (dropped + late) / resolved
    return row


def _m07w_m08w(
    flows: list[WindowedFlow], keys: set[str], w: Window,
    time_s: Optional[Sequence[float]], contract_fraction: float,
) -> list[dict[str, Any]]:
    """In-window GBR delivery against `gfbr_bps * contract_fraction`.

    M07w counts flows meeting contract; M08w is the min fraction -- the
    max-min floor, in-window. Per §0.1's standing rule these are computed
    and reported TOGETHER: a claim built on either one alone is false in
    the same cell.
    """
    base = {"window": w.name}
    idx = _window_indices(time_s, w)
    dt = _sample_dt_s(time_s) if time_s else None
    gbr = [f for f in flows
           if f.key in keys and f.flow_class == "GBR" and f.gfbr_bps > 0]

    if not gbr:
        reason = "no GBR flows in this subset"
    elif not idx or dt is None:
        reason = "no timeseries samples in this window"
    else:
        reason = None

    if reason is not None:
        return [
            {**base, "metric": "M07w", "met": None, "total": len(gbr),
             "reason": reason},
            {**base, "metric": "M08w", "fraction": None, "flow": None,
             "reason": reason},
        ]

    # Covered duration, not the nominal width: a window clipped by the end
    # of the run would otherwise divide by time that was never simulated
    # and understate throughput.
    window_s = len(idx) * dt
    fractions: list[tuple[str, float]] = []
    for f in gbr:
        if f.ts_delivered_bytes is None:
            continue
        delivered = sum(f.ts_delivered_bytes[i] for i in idx
                        if i < len(f.ts_delivered_bytes))
        bps = delivered * 8.0 / window_s
        fractions.append((f.key, bps / f.gfbr_bps))

    if not fractions:
        reason = "GBR flows present but no per-slot delivery series"
        return [
            {**base, "metric": "M07w", "met": None, "total": len(gbr),
             "reason": reason},
            {**base, "metric": "M08w", "fraction": None, "flow": None,
             "reason": reason},
        ]

    met = sum(1 for _, v in fractions if v >= contract_fraction)
    worst_key, worst_val = min(fractions, key=lambda kv: kv[1])
    return [
        {**base, "metric": "M07w", "met": met, "total": len(fractions),
         "window_s": window_s},
        {**base, "metric": "M08w", "fraction": worst_val, "flow": worst_key,
         "window_s": window_s},
    ]


def _inactive_s(a: float, b: float, active: Optional[Sequence[tuple]]) -> float:
    """Seconds of [a, b] during which the SOURCE was scheduled not to send.

    WHY THIS AND NOT A CADENCE PREDICATE. `Scorecard._m03` guards the same
    class of error with "is the flow's own MEDIAN gap already above the
    bound", which correctly catches a uniformly SLOW source -- a 1000 ms
    telemetry period against a 500 ms bound. It cannot catch a DUTY-CYCLED
    one, and that is the only kind GT-7.1 has: the soak's teleop stream sends
    every 50 ms while on and is silent for 8 s of every 20 s, so its median
    gap is 50 ms and its max is 8,050 ms. The median predicate reads it as
    healthy and the max is then scored against G3's 500 ms bound as a
    liveness failure -- in 30 of 30 windows, on all three arms, at the same
    value to one decimal place.

    A liveness gap is "how long was the network silent while the source was
    trying to send", so scripted silence is subtracted from the gap rather
    than the flow being excluded: a flow that is duty-cycled AND genuinely
    starved still reports the starved part.
    """
    if not active:
        return 0.0
    covered = 0.0
    for start, end in active:
        lo = a if start is None else max(a, float(start))
        hi = b if end is None else min(b, float(end))
        if hi > lo:
            covered += hi - lo
    return max(0.0, (b - a) - covered)


def _m03w(completions: list[MessageCompletion], keys: set, w: Window,
          flows_by_key: Optional[dict] = None) -> dict:
    """G3's liveness gap, windowed. SELECTS ON COMPLETION TIME.

    This is the opposite of _m01w/_m02w's deliberate choice, and the reason
    is that a liveness gap is a RECEIVER-SIDE inter-arrival statistic: the
    question is "how long was this window silent", which is about when
    messages ARRIVED, not when they were offered.

    A window with fewer than two completions has no gap at all, so it emits
    None with a reason rather than a 0 -- and the reason names the count,
    because a structurally silent window and a healthy one are otherwise
    indistinguishable (CLAUDE.md's mechanism-fired rule at window scale).
    """
    by_flow: dict[str, list[float]] = {}
    for c in completions:
        if not c.complete:
            continue
        k = _flow_key(c)
        if k in keys and w.contains(c.completion_ts_s):
            by_flow.setdefault(k, []).append(c.completion_ts_s)
    worst_key, worst_gap, worst_median = None, None, None
    thin = 0
    for k, ts in by_flow.items():
        if len(ts) < 2:
            thin += 1
            continue
        ts.sort()
        act = (flows_by_key or {}).get(k)
        act = act.active_windows if act is not None else None
        # SCRIPTED SILENCE IS NOT A LIVENESS GAP. Subtracting it leaves the
        # part of the interval the source was actually trying to send in.
        gaps = [((b - a) - _inactive_s(a, b, act)) * 1000.0
                for a, b in zip(ts, ts[1:])]
        g = max(gaps)
        if worst_gap is None or g > worst_gap:
            worst_key, worst_gap = k, g
            worst_median = statistics.median(gaps)
    row = {"window": w.name, "metric": "M03w", "n_flows": len(by_flow),
           "n_flows_too_thin": thin}
    if worst_gap is None:
        row["value"] = None
        row["flow"] = None
        row["reason"] = (f"no flow had >=2 completions in this window "
                         f"({len(by_flow)} flow(s) present, {thin} too thin)")
    else:
        row["value"] = worst_gap
        row["flow"] = worst_key
        # THE REPORTING FLOW'S OWN CADENCE, carried so a consumer can tell a
        # liveness failure from a source that simply sends slowly -- the same
        # discriminator sim/scorecard.py:334-341 already derives for the
        # un-windowed M03, and the one thing this row was missing.
        #
        # It is not optional realism. GT-7.1's soak scripts a duty-cycled
        # teleop stream (12 s on of every 20 s), so EVERY 60 s window of it
        # contains three 8-second silences by construction. Measured on the
        # real scenario, all three arms report M03w = 8050.0 ms on
        # ue1_qfi82 -- identical to one decimal across three different
        # schedulers, which is the signature of a scripted artefact rather
        # than a scheduling result. Scored against G3's 500 ms bound that is
        # a FAIL in 30 of 30 windows on every arm and every seed.
        #
        # The BOUND is deliberately not applied here. This row stays
        # bound-agnostic (it has no t_live_s) and the caller that owns the
        # bound decides -- scripts/g11_score.py.
        row["median_gap_ms"] = worst_median
    return row


def _m15w(completions: list[MessageCompletion], keys: set, w: Window) -> dict:
    """G1's jitter, windowed: p99 - p50 on the worst flow. Same population
    and same generation-time selection as M01w, so the two are comparable."""
    by_flow: dict[str, list[MessageCompletion]] = {}
    for c in completions:
        k = _flow_key(c)
        if k in keys and w.contains(c.message.generation_ts_s):
            by_flow.setdefault(k, []).append(c)
    worst_key, worst = None, None
    for k, cs in by_flow.items():
        s = message_latency_percentiles_ms(cs)
        if not s["count"]:
            continue
        j = s["p99"] - s["p50"]
        if worst is None or j > worst:
            worst_key, worst = k, j
    row = {"window": w.name, "metric": "M15w", "n_flows": len(by_flow)}
    if worst is None:
        row["value"] = None
        row["flow"] = None
        row["reason"] = "no flow completed a message in this window"
    else:
        row["value"] = worst
        row["flow"] = worst_key
    return row


def _m05w_m06w(completions: list[MessageCompletion], flows_by_key: dict,
               keys: set, w: Window) -> list[dict]:
    """G5's PDU-set completeness and frame age, windowed.

    A DIFFERENT ESTIMATOR FROM PANEL M05, and that must travel with it.
    Panel M05 reads `FlowRecord.frame_completions`, built by the driver over
    the whole run; this regroups the WINDOW's completions by
    `Message.frame_id` via `FrameLedger.group`. A frame straddling a window
    boundary is counted differently by the two -- exactly the M02w-vs-M02
    divergence this module's docstring already flags, and the reason
    control C3 exists. G11 owes M05w the same calibration at the `full`
    window before any windowed number is quoted (docs/wp9-g11-plan.md §10,
    commit 6).
    """
    # Group by FLOW first, then frame. FrameCompletion carries frame_id and
    # timings but NO flow identity (sim/messages.py:170), so grouping the
    # other way round loses which flow a frame belonged to -- and M05 is a
    # WORST-FLOW statistic, so that identity is the whole point.
    per_flow_comps: dict[str, list] = {}
    for c in completions:
        k = _flow_key(c)
        if k in keys and w.contains(c.message.generation_ts_s):
            per_flow_comps.setdefault(k, []).append(c)
    by_flow = {k: FrameLedger.group(cs) for k, cs in per_flow_comps.items()}
    by_flow = {k: fcs for k, fcs in by_flow.items() if fcs}
    frames = [fc for fcs in by_flow.values() for fc in fcs]

    worst_key, worst_frac = None, None
    ages: list[float] = []
    for k, fcs in by_flow.items():
        pdb = flows_by_key[k].pdb_ms if k in flows_by_key else None
        # completion_ts_s is None unless complete (sim/messages.py:181)
        done = [fc for fc in fcs if fc.complete and fc.completion_ts_s is not None]
        if pdb is not None:
            in_pdb = [fc for fc in done
                      if (fc.completion_ts_s - fc.generation_ts_s) * 1000.0 <= pdb]
        else:
            in_pdb = done
        frac = len(in_pdb) / len(fcs) if fcs else None
        if frac is not None and (worst_frac is None or frac < worst_frac):
            worst_key, worst_frac = k, frac
        ages.extend((fc.completion_ts_s - fc.generation_ts_s) * 1000.0
                    for fc in done)

    m05 = {"window": w.name, "metric": "M05w", "n_flows": len(by_flow),
           "n_frames": len(frames)}
    if worst_frac is None:
        m05["value"] = None
        m05["flow"] = None
        m05["reason"] = "no frame-bearing flow generated a frame in this window"
    else:
        m05["value"] = worst_frac
        m05["flow"] = worst_key

    m06 = {"window": w.name, "metric": "M06w", "n_frames_complete": len(ages)}
    if not ages:
        m06["value"] = None
        m06["reason"] = "no frame completed in this window"
    else:
        ages.sort()
        m06["value"] = ages[min(len(ages) - 1, int(len(ages) * 0.95))]
    return [m05, m06]


def _m09w(flows: list[WindowedFlow], keys: set, w: Window,
          time_s: Optional[Sequence[float]]) -> dict:
    """G8's per-second Jain, windowed.

    Reuses the panel's own shape: per-flow delivered/arrived ratio per
    SECOND, then Jain over the flow vector in each second, then the WORST
    second in the window. Bucketing by second (not by window) is what keeps
    it the same statistic panel M09 computes -- a Jain over window totals
    would be a different, much smoother quantity under the same name.
    """
    row = {"window": w.name, "metric": "M09w"}
    idx = _window_indices(time_s, w)
    gbr = [f for f in flows if f.key in keys
           and f.ts_delivered_bytes is not None and f.ts_arrived_bytes is not None]
    if not idx or len(gbr) < 2:
        row["value"] = None
        row["reason"] = (f"{len(gbr)} flow(s) with both series and "
                         f"{len(idx)} sample(s) in window; need >=2 and >=1")
        return row
    per_sec: dict[int, list[float]] = {}
    for f in gbr:
        acc: dict[int, list[int]] = {}
        for i in idx:
            if i >= len(f.ts_delivered_bytes):
                continue
            sec = int(time_s[i])
            d, a = acc.setdefault(sec, [0, 0])
            acc[sec] = [d + f.ts_delivered_bytes[i], a + f.ts_arrived_bytes[i]]
        for sec, (d, a) in acc.items():
            per_sec.setdefault(sec, []).append((d / a) if a > 0 else 1.0)
    jains = []
    for vals in per_sec.values():
        if len(vals) < 2:
            continue
        s1, s2 = sum(vals), sum(v * v for v in vals)
        if s2 > 0:
            jains.append((s1 * s1) / (len(vals) * s2))
    if not jains:
        row["value"] = None
        row["reason"] = "no second in this window had >=2 flows with offered load"
    else:
        row["value"] = min(jains)
        row["mean"] = sum(jains) / len(jains)
        row["seconds"] = len(jains)
    return row


def windowed_metrics(
    completions: list[MessageCompletion],
    flows: list[WindowedFlow],
    time_s: Optional[Sequence[float]],
    windows: Sequence[Window],
    subsets: Optional[dict[str, Callable[[WindowedFlow], bool]]] = None,
    contract_fraction: float = 0.95,
    families: str = "all",
) -> list[dict[str, Any]]:
    """§16.4's four windowed quantities, for every (window, subset) pair.

    Returns tidy long-format rows -- one per (window, subset, metric) --
    so the sweep runner can stream them straight out the way
    `_online_rows_for` already does, with no nested structure to flatten.

    A metric that cannot be computed emits a row with a None value and a
    `reason`, never an omitted row: per the panel's own never-omit rule an
    omitted row is indistinguishable from a forgotten one. Callers must
    not read a None as a zero -- for M01w in particular, 0.0 ms is the
    best possible latency and None means "nothing completed here".

    `contract_fraction` defaults to the panel's own 0.95
    (`config/metric_panel.yml` defaults, M07/M08) rather than a fresh
    choice, so M07w/M08w are comparable to the panel numbers they window.
    """
    if families not in ("all", "completion", "timeseries"):
        raise ValueError(f"families must be all/completion/timeseries, got {families!r}")
    want_comp = families in ("all", "completion")
    want_ts = families in ("all", "timeseries")
    subsets = DEFAULT_SUBSETS if subsets is None else subsets
    flows_by_key = {f.key: f for f in flows}
    # PRE-BUCKET ONCE. Every metric below used to receive the WHOLE
    # completion list and filter inside it, so the cost was
    # n_subsets x n_windows x |completions|. Its only caller paid 4 x 5 over
    # a 5 s run; G11 is 4 x 30 over 1,800 s, which is 240 full scans of a
    # list ~360x longer. Bucketing by window index once makes it one scan.
    by_gen: dict[int, list] = {}
    by_done: dict[int, list] = {}
    for c in completions:
        for bucket, ts in ((by_gen, c.message.generation_ts_s),
                           (by_done, c.completion_ts_s if c.complete else None)):
            if ts is None:
                continue
            for wi, w in enumerate(windows):
                if w.contains(ts):
                    bucket.setdefault(wi, []).append(c)
                    break
    rows: list[dict[str, Any]] = []
    for subset_name, pred in subsets.items():
        keys = {f.key for f in flows if pred(f)}
        for wi, w in enumerate(windows):
            gen = by_gen.get(wi, [])
            done = by_done.get(wi, [])
            # ORDER IS PRESERVED ACROSS BOTH FAMILIES. A caller that scores
            # the two halves separately and concatenates gets the same rows
            # this returns for families="all", just not in the same order --
            # every consumer keys on row["metric"], never on position
            # (scripts/g11_score.py:53).
            emitted = []
            if want_comp:
                emitted += [_m01w(gen, keys, w), _m02w(gen, keys, w)]
            if want_ts:
                emitted += list(_m07w_m08w(flows, keys, w, time_s, contract_fraction))
            if want_comp:
                emitted += [_m03w(done, keys, w, flows_by_key), _m15w(gen, keys, w),
                            *_m05w_m06w(gen, flows_by_key, keys, w)]
            if want_ts:
                emitted += [_m09w(flows, keys, w, time_s)]
            for row in emitted:
                row["subset"] = subset_name
                row["window_start_s"] = w.start_s
                row["window_end_s"] = w.end_s
                rows.append(row)
    return rows
