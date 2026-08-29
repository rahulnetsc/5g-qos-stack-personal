"""WP9 stage runner (`docs/wp9-plan.md` §6.3/§6.4, build item B5+B6).

Stage 1 is a **star design**: a dense core plane (N x load) plus
one-axis-at-a-time excursions from the base point. That shape is chosen
deliberately and has a consequence the runner enforces rather than merely
documents -- `regime_sweep.check_contiguity` needs grid-ADJACENT cells, and
excursions structurally cannot supply them, so **a regime-boundary claim
from stage 1 is impossible by construction, not merely discouraged**. Stage
1 selects; stage 2 confirms.

Every run's full RunRecord is persisted (build item B3) so that M13/M16 and
every scoring-parameter variation (§3) can be computed afterwards without
re-running a single cell.

Usage:
    uv run python scripts/wp9_sweep.py --stage 1 --out sweeps/wp9/stage1
    uv run python scripts/wp9_sweep.py --stage 1 --smoke     # tiny grid
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import multiprocessing as mp
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Scorecard
from sim.baselines.pf import ProportionalFair
from scheduler.reservation import Reservation
from scheduler import load_two_tier

from regime_sweep import axis_aware, sweep, write_csv
import wp9_gate

_TT_CONFIG = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")

# docs/wp9-plan.md §1: the base point. Every excursion is one key away.
BASE: dict[str, Any] = {
    "n_ues": 8,
    "load_mult": 1.0,
    "min_rb": 5,
    "mix": "factory",
    "duty_cycle": 1.0,
    "snr_spread_db": 0.0,
    "pdb_ms": None,
    "shared_lcg": False,
    "mfbr_multiple": 0.0,
    "bg": False,
    "inf_scenario": None,
    "sr_period_slots": 10,
    "k2_slots": 2,
}

CORE_PLANE = {
    "n_ues": [2, 4, 8, 16, 24, 32],
    "load_mult": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0],
}

# One-axis-at-a-time excursions (§3). The base level of each is already run
# by the core plane, so only the off-base levels are listed here.
EXCURSIONS: dict[str, list[Any]] = {
    "min_rb": [1, 20],
    "mfbr_multiple": [2.0],
    "duty_cycle": [0.5, 0.1],
    "snr_spread_db": [6.0, 12.0],
    "pdb_ms": [10.0, 1000.0],
    "sr_period_slots": [1, 40],
    "shared_lcg": [True],
    "k2_slots": [1, 4],
    "inf_scenario": ["DL", "DH"],
    "bg": [True],
}

DRIVER_AXES = ("sr_period_slots", "k2_slots")
CQI_DELAY_SLOTS = 8   # pinned, never swept (§3 exclusions)


def _arms() -> dict:
    """The three arms (§4). `min_rb` is an ARM-CONFIG axis, so the two
    schedulers that read it are `axis_aware`; PF does not take it."""
    return {
        "PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": axis_aware(lambda min_rb=5, **_: Reservation(min_rb=min_rb)),
        "TwoTier": axis_aware(lambda min_rb=5, **_: load_two_tier(_TT_CONFIG, min_rb=min_rb)),
    }


def _driver_kwargs(**axis_values):
    dk = {
        "cqi_delay_slots": CQI_DELAY_SLOTS,
        "record_timeseries": True,     # M04/M09/M19 are `pending` without it
    }
    for k in DRIVER_AXES:
        dk[k] = axis_values.get(k, BASE[k])
    return dk


def _build(seed: int, **axis_values):
    kwargs = {**BASE, **axis_values}
    kwargs.pop("min_rb", None)          # arm-config, not a scenario property
    for k in DRIVER_AXES:
        kwargs.pop(k, None)             # driver kwarg, not a scenario property
    return sweep_scenario(seed=seed, horizon_slots=axis_values.get(
        "horizon_slots", _HORIZON[0]), **kwargs)


_HORIZON = [20_000]


# Timeseries fields, stripped before a record is persisted. See _RecordSink.
_TS_FLOW_FIELDS = (
    "ts_backlog_bytes", "ts_hol_delay_s", "ts_delivered_bytes",
    "ts_arrived_bytes", "ts_dropped_bytes",
)
_TS_SYSTEM_FIELDS = (
    "ts_dl_prbs_used", "ts_ul_prbs_used", "ts_dl_prbs_avail",
    "ts_ul_prbs_avail", "ts_cce_used", "ts_cce_budget",
)
# RunRecord's own top-level per-slot arrays. Commit 1a MISSED these: they are
# not under `flows` or `system`, so the strip left two 20,000-element lists on
# every persisted record -- measured at 0.76 MB of each record's 1.087 MB,
# i.e. ~70% of what 1a believed it had already removed.
_TS_RECORD_FIELDS = ("timeseries_time_s", "timeseries_slot_index")

# The scoring-parameter variations (§3), computed ONLINE. Each is free in
# runs but not in bytes -- see _RecordSink's docstring.
_SCORING_VARIATIONS = (
    ("survival_miss_n", (2, 3, 5)),          # M04 -- "report H6 as f(N)"
    ("t_live_s", (1.0, 2.0, 4.0)),           # M03/M14 -- T_live is [OPEN: HARDWARE]
    ("gbr_contract_fraction", (0.90, 0.95, 0.99)),   # M07/M08
    ("slo_green_dwell_s", (0.5, 1.0, 2.0)),  # M19
)


class _RecordSink:
    """Build item B3, with a size fix found by measurement before stage 1 ran.

    The original design persisted every RunRecord whole. Measured, that is
    **1.88 MB per record at horizon 4,000 / N=4, 17.9 MB at 20,000 / N=8 and
    82.7 MB at 20,000 / N=32** -- stage 1's ~1,680 runs would have written
    tens of gigabytes, and a smoke grid of 45 tiny records already produced
    84 MB. The timeseries arrays are essentially all of it.

    So anything needing the per-slot series is computed HERE, while the
    record is in memory, and the persisted record has those arrays stripped:

      - M16 (needs ts_hol_delay_s on both flows of the bearer pair);
      - the four scoring-parameter variations, of which M04 and M19 read the
        timeseries and M03/M14/M07/M08 do not.

    What survives on the stripped record is everything else -- per-flow
    byte/latency aggregates, message and frame ledgers, join events -- so
    M13 (which needs only per-flow GBR data across an ordered load column)
    and any later re-inspection still work without a re-run. That was B3's
    actual purpose; persisting the series as well was not.
    """

    def __init__(self, path: Path, online_path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w")
        # Streamed, not accumulated: ~73 rows per record is ~123k dicts at
        # full scale, held to the end of the run for no reason.
        self._online_fh = online_path.open("w")
        self._sc = Scorecard()
        self.n = 0
        self.n_online = 0

    def __call__(self, record: RunRecord, axis_values: dict) -> None:
        self._online_metrics(record, axis_values)
        self._fh.write(json.dumps({
            "axis_values": axis_values,
            "record": _strip_timeseries(record.to_dict()),
        }) + "\n")
        self.n += 1

    def _online_metrics(self, record: RunRecord, axis_values: dict) -> None:
        # Shared with the parallel worker (_online_rows_for) so both paths
        # compute identically -- the determinism claim depends on it.
        for row in _online_rows_for(self._sc, record, axis_values):
            self._emit(row)

    def _emit(self, row: dict) -> None:
        self._online_fh.write(json.dumps(row) + "\n")
        self.n_online += 1

    def close(self):
        self._fh.close()
        self._online_fh.close()


def _strip_timeseries(d: dict) -> dict:
    """Null the per-slot arrays. Measured at 82.7 MB/record without this, and
    still 1.087 MB/record with commit 1a's incomplete version (which missed
    _TS_RECORD_FIELDS)."""
    for f in _TS_RECORD_FIELDS:
        if f in d:
            d[f] = None
    for fr in d.get("flows", {}).values():
        for f in _TS_FLOW_FIELDS:
            if f in fr:
                fr[f] = None
    sysrec = d.get("system")
    if isinstance(sysrec, dict):
        for f in _TS_SYSTEM_FIELDS:
            if f in sysrec:
                sysrec[f] = None
    return d


def m13_projection(record: RunRecord) -> RunRecord:
    """The ONLY thing worth retaining across a whole stage run.

    THE LEAK THIS EXISTS TO CLOSE. `run_stage_1` used to keep every live
    `RunRecord` in a list so M13 could read them at the end. `_RecordSink`
    strips a *copy* (`record.to_dict()`), so the retained objects still held
    their per-slot arrays -- ~33 MB each, 25 GB across a stage, which
    thrashed the machine into swap and stalled stage 1 at 756 of ~1,680
    records. Commit 1a fixed the persisted size and introduced this in the
    same commit; the in-memory side was never addressed.

    M13 (`Scorecard.first_violation_order`) reads exactly: each record's
    GBR flows, and for each `.key`, `.qfi` and `.meets_gbr_contract()`
    (which needs only `throughput_bps` / `gfbr_bps`). So retain a real
    `RunRecord` -- so no scorecard logic is duplicated or reimplemented --
    carrying only GBR flows with every array and ledger dropped. A few KB
    instead of tens of MB.
    """
    flows = {}
    for key, fr in record.flows.items():
        if fr.flow_class != "GBR":
            continue
        nulls = {f: None for f in _TS_FLOW_FIELDS}
        nulls["completion_ts_by_role_s"] = None
        nulls["frame_completions"] = None
        flows[key] = dataclasses.replace(fr, **nulls)
    system = record.system
    if system is not None:
        system = dataclasses.replace(
            system, **{f: None for f in _TS_SYSTEM_FIELDS})
    return dataclasses.replace(
        record, flows=flows, system=system,
        timeseries_time_s=None, timeseries_slot_index=None, join_events=[],
    )


def _study_layer_metrics(records: list[tuple[dict, RunRecord]]) -> list[dict]:
    """Build item B6: M13 and M16, which `Scorecard.score()` deliberately
    does NOT compute -- M13 is a cross-run load-ramp metric and M16 needs a
    named flow pair. A runner that forgets these silently under-reports two
    guarantees (G12, and the shared-bearer half of G1/G2/G3), which is why
    they are here and not left to the analyst.
    """
    sc = Scorecard()
    rows: list[dict] = []

    # -- M13: per (N, arm), the load column in ascending order -------------
    groups: dict[tuple, list[tuple[float, RunRecord]]] = {}
    for axis_values, rec in records:
        if set(axis_values) - {"n_ues", "load_mult"}:
            continue                     # core-plane cells only
        key = (axis_values.get("n_ues"), rec.scheduler_name, rec.seed)
        groups.setdefault(key, []).append((axis_values.get("load_mult", 0.0), rec))
    for (n_ues, arm, seed), pairs in groups.items():
        pairs.sort(key=lambda p: p[0])
        ordered = [r for _, r in pairs]
        if len(ordered) < 2:
            continue
        class_of = {fr.key: fr.qfi for fr in ordered[0].flows.values()}
        res = sc.first_violation_order(ordered, class_of)
        rows.append({"metric": "M13", "n_ues": n_ues, "scheduler": arm,
                     "seed": seed, "status": res.status, "value": res.value})

    # M16 and the scoring-parameter variations are computed ONLINE by
    # _RecordSink (they need the timeseries, which is stripped before a
    # record is persisted) -- see that class's docstring.

    return rows


def _run_one_cell(task: tuple) -> tuple:
    """Run one grid cell in a worker process and return only compact results.

    Parallelising over CELLS is what makes stage 2 fit its budget at all
    (docs/wp9-plan.md §6.3b): measured serially, stage 1 is ~7.1 h against a
    4 h ceiling and stage 2 ~35-55 h against 24 h.

    **This changes no result.** Cells are independent; within a cell seeds
    and arms stay ordered; `paired_seeds` is drawn up front from a fixed
    base seed; and every run is a pure function of (scenario, seed). The
    worker returns rows, streamed-row payloads and the M13 projection rather
    than writing anything, so the parent stays the single writer.
    """
    axis_values, n_seeds, horizon = task
    _HORIZON[0] = horizon
    online: list[dict] = []
    payload: list[tuple] = []
    sc_card = Scorecard()
    keep_m13 = not (set(axis_values) - {"n_ues", "load_mult"})

    def sink(record, av):
        # Strip and project IMMEDIATELY, never retain the live record.
        #
        # This is the same leak commit 1b fixed in the parent, reintroduced
        # here in 1c and caught in flight: the worker used to append every
        # live RunRecord to a `collected` list and convert only at the end,
        # so it held 30 records x ~33 MB per cell. Measured mid-run at
        # 1.4-2.1 GiB per worker across 12 workers (~20 GiB) with the
        # largest cells (N=24, 32) still queued.
        #
        # 1b's memory test did not catch it because it pinned
        # m13_projection() and the parent's retention, not the worker's --
        # the test was one layer above the bug. test_wp9_sweep_memory.py now
        # covers _run_one_cell directly.
        online.extend(_online_rows_for(sc_card, record, av))
        payload.append((
            dict(av),
            _strip_timeseries(record.to_dict()),
            m13_projection(record).to_dict() if keep_m13 else None,
        ))

    rows = sweep(
        axes={k: [v] for k, v in axis_values.items()},
        build_scenario=_build, schedulers=_arms(), n_seeds=n_seeds,
        driver_kwargs=_driver_kwargs, record_sink=sink,
    )
    return rows, online, payload


def _online_rows_for(sc_card: Scorecard, record: RunRecord,
                     axis_values: dict) -> list[dict]:
    """M16 + the 12 scoring-parameter variations. Extracted from
    _RecordSink so the worker and the serial path compute identically."""
    tag = {**axis_values, "scheduler": record.scheduler_name,
           "seed": record.seed}
    out: list[dict] = []
    try:
        m16 = sc_card.correlate_flows(record, (1, 1), (1, 82))
        out.append({"metric": "M16", **tag,
                    "status": m16.status, "value": m16.value})
    except (KeyError, StopIteration):
        pass
    for name, values in _SCORING_VARIATIONS:
        for v in values:
            scores = sc_card.score(record, **{name: v})
            for mid in ("M03", "M04", "M07", "M08", "M14", "M19"):
                r = scores.get(mid)
                if r is None:
                    continue
                out.append({"metric": mid, "variation": name,
                            "variation_value": v, **tag,
                            "status": r.status, "value": r.value})
    return out


def _cell_tasks(core: dict, excursions: dict, n_seeds: int,
                horizon: int) -> list[tuple]:
    """One task per grid cell: the core plane's full product, then each
    excursion level as its own single-cell task."""
    tasks = []
    names = list(core.keys())
    for combo in itertools.product(*core.values()):
        tasks.append((dict(zip(names, combo)), n_seeds, horizon))
    for axis, levels in excursions.items():
        for level in levels:
            tasks.append(({axis: level}, n_seeds, horizon))
    return tasks


def run_stage_1_parallel(out_dir: Path, n_seeds: int, horizon: int,
                         smoke: bool, workers: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    core = CORE_PLANE if not smoke else {"n_ues": [2, 4], "load_mult": [1.0, 2.0]}
    excursions = EXCURSIONS if not smoke else {"min_rb": [20]}
    tasks = _cell_tasks(core, excursions, n_seeds, horizon)
    print(f"stage 1: {len(tasks)} cells on {workers} workers")

    rows: list[dict] = []
    kept: list[tuple[dict, RunRecord]] = []
    rec_fh = (out_dir / "records.jsonl").open("w")
    onl_fh = (out_dir / "online_rows.jsonl").open("w")
    n_rec = n_onl = 0
    try:
        with mp.get_context("spawn").Pool(workers) as pool:
            for i, (crows, conline, payload) in enumerate(
                    pool.imap_unordered(_run_one_cell, tasks), 1):
                rows.extend(crows)
                for r in conline:
                    onl_fh.write(json.dumps(r) + "\n")
                    n_onl += 1
                for av, recd, m13d in payload:
                    rec_fh.write(json.dumps(
                        {"axis_values": av, "record": recd}) + "\n")
                    n_rec += 1
                    if m13d is not None:
                        kept.append((av, RunRecord.from_dict(m13d)))
                print(f"  cell {i}/{len(tasks)} done ({n_rec} records)", flush=True)
    finally:
        rec_fh.close()
        onl_fh.close()

    write_csv(rows, str(out_dir / "stage1_rows.csv"))
    study_rows = _study_layer_metrics(kept)
    (out_dir / "study_layer_metrics.json").write_text(json.dumps(study_rows, indent=2))
    mb = (out_dir / "records.jsonl").stat().st_size / 1e6
    print(f"  {len(rows)} rows, {n_rec} records ({mb:.1f} MB) -> {out_dir}")
    print(f"  M13 rows: {len(study_rows)}; online rows streamed: {n_onl}")
    _run_gate(rows, core, excursions, out_dir)


def run_stage_1(out_dir: Path, n_seeds: int, horizon: int, smoke: bool) -> None:
    _HORIZON[0] = horizon
    out_dir.mkdir(parents=True, exist_ok=True)
    core = CORE_PLANE if not smoke else {"n_ues": [2, 4], "load_mult": [1.0, 2.0]}
    excursions = EXCURSIONS if not smoke else {"min_rb": [20]}

    sink = _RecordSink(out_dir / "records.jsonl",
                       out_dir / "online_rows.jsonl")
    # Only the M13 projection is retained -- see m13_projection's docstring
    # for the 25 GB leak that made this necessary.
    kept: list[tuple[dict, RunRecord]] = []

    def keeping_sink(rec, axis_values):
        sink(rec, axis_values)
        if not (set(axis_values) - {"n_ues", "load_mult"}):
            kept.append((dict(axis_values), m13_projection(rec)))

    print(f"stage 1: core plane {core}")
    rows = sweep(
        axes=core, build_scenario=_build, schedulers=_arms(),
        n_seeds=n_seeds, driver_kwargs=_driver_kwargs,
        record_sink=keeping_sink,
    )
    for axis, levels in excursions.items():
        print(f"stage 1: excursion {axis}={levels}")
        rows += sweep(
            axes={axis: levels}, build_scenario=_build, schedulers=_arms(),
            n_seeds=n_seeds, driver_kwargs=_driver_kwargs,
            record_sink=keeping_sink,
        )
    sink.close()

    write_csv(rows, str(out_dir / "stage1_rows.csv"))
    study_rows = _study_layer_metrics(kept)
    (out_dir / "study_layer_metrics.json").write_text(json.dumps(study_rows, indent=2))
    mb = (out_dir / "records.jsonl").stat().st_size / 1e6
    print(f"  {len(rows)} rows, {sink.n} records ({mb:.1f} MB) -> {out_dir}")
    print(f"  M13 rows: {len(study_rows)}; online rows streamed: {sink.n_online}")

    _run_gate(rows, core, excursions, out_dir)


def _run_gate(rows, core, excursions, out_dir: Path) -> None:
    """The gate, run as committed code, output recorded verbatim."""
    arm_pairs = [("PF", "Reservation"), ("PF", "TwoTier"),
                 ("Reservation", "TwoTier")]
    verdicts = []
    for axis, levels in {**core, **excursions}.items():
        base_level = BASE.get(axis)
        all_levels = list(levels) + ([base_level] if base_level not in levels else [])
        verdicts.append(wp9_gate.evaluate_axis(rows, axis, all_levels, arm_pairs))
    selection = wp9_gate.select_for_stage_2(verdicts)
    report = wp9_gate.format_verdicts(verdicts, selection)
    (out_dir / "gate_verdict.txt").write_text(report + "\n")
    print("\n" + report)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=int, default=1, choices=(1, 2))
    p.add_argument("--out", default="sweeps/wp9/stage1")
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--horizon", type=int, default=20_000)
    p.add_argument("--workers", type=int, default=12,
                   help="cell-level parallelism; memory-bound, see "
                        "docs/wp9-plan.md §6.3b (0 = serial)")
    p.add_argument("--smoke", action="store_true",
                   help="tiny grid, for exercising the machinery only")
    a = p.parse_args()
    if a.stage != 1:
        raise SystemExit("stage 2 is gated on stage 1's verdict -- not runnable yet")
    if a.workers and a.workers > 1:
        run_stage_1_parallel(Path(a.out), a.seeds, a.horizon, a.smoke, a.workers)
    else:
        run_stage_1(Path(a.out), a.seeds, a.horizon, a.smoke)


if __name__ == "__main__":
    main()
