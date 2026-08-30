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

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from sim.messages import MessageCompletion, message_latency_percentiles_ms

__all__ = [
    "Window", "WindowedFlow", "DEFAULT_SUBSETS", "LIDAR_QFI", "ESTOP_QFI",
    "TIGHT_PDB_MS", "lidar_windows", "windowed_flows_from_record",
    "windowed_metrics",
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
        )
        for fr in record.flows.values()
    ]


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


def windowed_metrics(
    completions: list[MessageCompletion],
    flows: list[WindowedFlow],
    time_s: Optional[Sequence[float]],
    windows: Sequence[Window],
    subsets: Optional[dict[str, Callable[[WindowedFlow], bool]]] = None,
    contract_fraction: float = 0.95,
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
    subsets = DEFAULT_SUBSETS if subsets is None else subsets
    rows: list[dict[str, Any]] = []
    for subset_name, pred in subsets.items():
        keys = {f.key for f in flows if pred(f)}
        for w in windows:
            emitted = [
                _m01w(completions, keys, w),
                _m02w(completions, keys, w),
                *_m07w_m08w(flows, keys, w, time_s, contract_fraction),
            ]
            for row in emitted:
                row["subset"] = subset_name
                row["window_start_s"] = w.start_s
                row["window_end_s"] = w.end_s
                rows.append(row)
    return rows
