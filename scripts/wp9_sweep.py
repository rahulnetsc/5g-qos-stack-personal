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
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard
from sim.baselines.pf import ProportionalFair
from scheduler.reservation import Reservation
from scheduler import load_two_tier

from regime_sweep import axis_aware, check_for_orphans, sweep, write_csv
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


class PersistingRecordSink:
    """The minimal `record_sink` every excursion runner should pass to
    `sweep()`. Strips the per-slot arrays and writes one JSONL line per run.

    THE DEFECT THIS EXISTS TO KILL, and it was an instrument defect rather
    than a scheduler one. `scripts/g6_seed_extension.py` called `sweep()`
    with **no record_sink at all**, so its n_seeds=40 run persisted only the
    tidy CSV -- one scored row per run, carrying M03's *winning* flow and
    value and nothing else. When the G6 diagnosis needed per-flow
    `completion_ts_by_role_s` to recompute a flow-restricted statistic, the
    data did not exist, and the falsifier had to fall back to stage 1's
    n_seeds=10 records -- an interval too wide to decide anything.

    **A run that cannot be re-analysed is a run you have to repeat.** The
    scored row answers the question you had when you launched; the record
    answers the question the result gives you. `_RecordSink` above already
    did this for the stage runners; nothing offered it to a one-off
    excursion, which is exactly where it went missing.

    Deliberately NOT `_RecordSink`: that one also computes the 12 online
    scoring variations, which an excursion does not need and which cost
    ~24 % of per-record time (§6.3a). This is the persistence half alone.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w")
        self.n = 0

    def __call__(self, record: RunRecord, axis_values: dict) -> None:
        self._fh.write(json.dumps({
            "axis_values": axis_values,
            "record": _strip_timeseries(record.to_dict()),
        }) + "\n")
        self.n += 1

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> "PersistingRecordSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


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
    # ONE DEFAULT PASS PER POPULATION, then per-variation only the metrics
    # that variation can reach. The rows below are IDENTICAL to what the full
    # 26-pass version emitted -- a metric that does not read the varied
    # parameter has the same value at every level of it, which is the
    # substitution `Scorecard.VARIATION_AFFECTS` licenses and
    # sim/tests/test_scoring_dispatch.py verifies both structurally (from
    # score()'s AST) and empirically (both ways, diffed, every value, both
    # populations).
    #
    # THE COST THIS REMOVES, measured rather than argued
    # (sweeps/phase2/profile-2026-09-04): M09 and M22 are 81 % of a score()
    # call and read no variation parameter, so 24 of the 26 passes computed
    # them for nothing. 2.412 s -> 0.099 s per record, 24.4x, on a record
    # whose driver.run is 3.6-10.1 s.
    base = {
        "all_flows": sc_card.score(record, population=Population.all_flows()),
        "protected_fleet": sc_card.score(
            record, population=Population.protected_fleet()),
    }
    for name, values in _SCORING_VARIATIONS:
        affects = Scorecard.VARIATION_AFFECTS[name]
        for v in values:
            # Both populations, same reason as regime_sweep: one would
            # re-make the choice silently a layer out.
            scores = {**base["all_flows"], **sc_card.score(
                record, population=Population.all_flows(),
                only=affects, **{name: v})}
            scores_prot = {**base["protected_fleet"], **sc_card.score(
                record, population=Population.protected_fleet(),
                only=affects, **{name: v})}
            for mid in ("M03", "M04", "M07", "M08", "M14", "M19"):
                for src, pop_tag in ((scores, "all_flows"),
                                     (scores_prot, "protected_fleet")):
                    r = src.get(mid)
                    if r is None:
                        continue
                    # The population is a COLUMN, not a convention a reader
                    # has to know. An online row that did not carry it was
                    # indistinguishable from one taken over any other subset.
                    out.append({"metric": mid, "variation": name,
                                "variation_value": v, **tag,
                                "population": r.population or pop_tag,
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
        # Refuse to launch beside an orphaned pool: its workers cannot be
        # found by script name and its memory is charged to this run.
        check_for_orphans()
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


# Stage 2 (docs/wp9-plan.md §6.4a): a FULL FACTORIAL over the promoted
# axes, unlike stage 1's star. The factorial is the point -- rule 5 requires
# contiguity, and check_contiguity needs grid-ADJACENT cells, which stage
# 1's one-axis-at-a-time excursions structurally cannot supply.
#
# Both tied-at-inf excursion axes are promoted (§6.4a): the cap was
# RECOMPUTED against §6.3a's measured costs, not relaxed, and at 252 cells /
# ~5.2 h wall it is not binding.
STAGE2_GRID: dict[str, list[Any]] = {
    "n_ues": [2, 4, 8, 16, 24, 32],
    "load_mult": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0],
    "shared_lcg": [False, True],      # base + excursion: H5
    "k2_slots": [1, 2, 4],            # base + excursions
}


def run_stage_2(out_dir: Path, n_seeds: int, horizon: int, smoke: bool,
                workers: int) -> None:
    grid = STAGE2_GRID if not smoke else {
        "n_ues": [2, 4], "load_mult": [1.0, 2.0],
        "shared_lcg": [False, True], "k2_slots": [1, 2],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    names = list(grid.keys())
    tasks = [(dict(zip(names, combo)), n_seeds, horizon)
             for combo in itertools.product(*grid.values())]
    print(f"stage 2: {len(tasks)} cells (full factorial) on {workers} workers")

    rows: list[dict] = []
    rec_fh = (out_dir / "records.jsonl").open("w")
    onl_fh = (out_dir / "online_rows.jsonl").open("w")
    n_rec = n_onl = 0
    try:
        # Refuse to launch beside an orphaned pool: its workers cannot be
        # found by script name and its memory is charged to this run.
        check_for_orphans()
        with mp.get_context("spawn").Pool(workers) as pool:
            for i, (crows, conline, payload) in enumerate(
                    pool.imap_unordered(_run_one_cell, tasks), 1):
                rows.extend(crows)
                for r in conline:
                    onl_fh.write(json.dumps(r) + "\n")
                    n_onl += 1
                for av, recd, _m13 in payload:
                    rec_fh.write(json.dumps(
                        {"axis_values": av, "record": recd}) + "\n")
                    n_rec += 1
                print(f"  cell {i}/{len(tasks)} done ({n_rec} records)", flush=True)
    finally:
        rec_fh.close()
        onl_fh.close()

    write_csv(rows, str(out_dir / "stage2_rows.csv"))
    mb = (out_dir / "records.jsonl").stat().st_size / 1e6
    print(f"  {len(rows)} rows, {n_rec} records ({mb:.1f} MB) -> {out_dir}")
    print("  contiguity is read BEFORE effect sizes -- see analyse_stage2.py")


# ---------------------------------------------------------------- stage 3
# Two TARGETED sub-grids, not a re-run. Both axes were selected by a named
# argument (docs/wp9-regime-map.md §0.2/§0.3), not by a gate score, so the
# stage-1 promotion machinery is deliberately NOT applied here -- see
# docs/wp9-plan.md §10.
STAGE3_Q1: dict[str, list[Any]] = {          # min_rb crossover
    "n_ues": [2, 3, 4, 6, 8, 12, 16],
    "min_rb": [1, 3, 5, 7, 10, 20],
    "load_mult": [1.0, 2.0],
}
STAGE3_Q2: dict[str, list[Any]] = {          # mfbr / H5
    "mfbr_multiple": [0.0, 1.0, 2.0, 4.0],
    "shared_lcg": [False, True],
    "n_ues": [8, 16, 32],
    "load_mult": [1.0, 2.0],
}


def _instrumented_two_tier(min_rb: int, tally: dict):
    """TwoTier with the UL floor's two halves counted separately.

    The floor's dormancy has TWO independent reasons (README §7): it needs
    `mfbr_bps > 0` to ARM, and a BSR/SR-desync fault to FIRE. Every run in
    this project so far failed the first, so "no fires" has never
    distinguished *never armed* from *armed but never fired*. Stage 3 is the
    first run where the arming half can be satisfied, so both counters are
    needed for the result to mean anything.

    `_ul_has_pending_gbr` is the arming gate (it returns early at mfbr=0);
    `_update_ul_floor` returns (fired, silence). Wrapped on the instance so
    no scheduler code changes.
    """
    sched = load_two_tier(_TT_CONFIG, min_rb=min_rb)
    real_gate = sched._ul_has_pending_gbr
    real_floor = sched._update_ul_floor

    def gate(ue_id, buffers):
        ok = real_gate(ue_id, buffers)
        tally["gate_calls"] = tally.get("gate_calls", 0) + 1
        if ok:
            tally["gate_passes"] = tally.get("gate_passes", 0) + 1
        return ok

    def floor(ue_id, buffers, slot_index, *a, **k):
        fired, sil = real_floor(ue_id, buffers, slot_index, *a, **k)
        if fired:
            tally["fires"] = tally.get("fires", 0) + 1
        return fired, sil

    sched._ul_has_pending_gbr = gate
    sched._update_ul_floor = floor
    return sched


def _run_one_cell_s3(task: tuple) -> tuple:
    """Stage-3 worker: same shape as _run_one_cell, plus the floor tally."""
    axis_values, n_seeds, horizon = task
    _HORIZON[0] = horizon
    online: list[dict] = []
    payload: list[tuple] = []
    sc_card = Scorecard()
    tally: dict = {}

    def sink(record, av):
        online.extend(_online_rows_for(sc_card, record, av))
        payload.append((dict(av), _strip_timeseries(record.to_dict()), None))

    arms = {
        "PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": axis_aware(
            lambda min_rb=5, **_: Reservation(min_rb=min_rb)),
        "TwoTier": axis_aware(
            lambda min_rb=5, **_: _instrumented_two_tier(min_rb, tally)),
    }
    rows = sweep(
        axes={k: [v] for k, v in axis_values.items()},
        build_scenario=_build, schedulers=arms, n_seeds=n_seeds,
        driver_kwargs=_driver_kwargs, record_sink=sink,
    )
    return rows, online, payload, {**axis_values, **tally}


# ---------------------------------------------------------------- stage 4
# The Category-2 grid (docs/wp9-plan.md §14). Indexed by what the
# ENVIRONMENT does -- fleet size, composition, load intensity -- not by
# deployment config (Cat 1) or scheduler internals (Cat 3).
STAGE4_GRID: dict[str, list[Any]] = {
    "n_ues": [4, 8, 16, 32],
    "composition": ["drone_heavy", "ugv_heavy", "sensor_dense", "mixed"],
    "video_tier": [0.5, 1.0, 1.5],
}


def _build_fleet_scenario(seed: int, _lidar=None, **axis_values):
    """Stage-4 scenario: a heterogeneous fleet, not the stage-1/2 synthetic
    workload. Load intensity comes from per-device rates (video_tier), NOT
    a synthetic best-effort filler -- the clean break of §6 decision 2.

    `_lidar` is stage 5's only addition (§16, build item B7), and it is a
    parameter here rather than a separate builder precisely so `lidar=None`
    keeps taking the byte-identical path stage 4 ran -- which is what
    control C5 checks against sweeps/wp9/stage4/rows.jsonl. Underscored
    because it is not a grid axis: the axis is the scalar `lidar_ues`.
    """
    from sim.fleet import build_fleet
    from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig

    n = axis_values["n_ues"]
    flows, seq = build_fleet(
        n, axis_values["composition"],
        lidar=_lidar,
        video_tier=axis_values.get("video_tier", 1.0),
    )
    ues = [UEConfig(ue_id=i + 1, mean_snr_db=20.0, coherence_slots=2000)
           for i in range(n)]
    return ScenarioConfig(
        name=f"fleet_{axis_values['composition']}_n{n}",
        horizon_slots=_HORIZON[0],
        carrier=CarrierConfig(bandwidth_hz=40_000_000, numerology=2),
        tdd=TDDConfig(pattern="DSUUU"), ues=ues, flows=flows, seed=seed,
    )


def _run_one_cell_s4(task: tuple) -> tuple:
    axis_values, n_seeds, horizon = task
    _HORIZON[0] = horizon
    online: list[dict] = []
    payload: list[tuple] = []
    sc_card = Scorecard()

    def sink(record, av):
        online.extend(_online_rows_for(sc_card, record, av))
        payload.append((dict(av), _strip_timeseries(record.to_dict()), None))

    rows = sweep(
        axes={k: [v] for k, v in axis_values.items()},
        build_scenario=_build_fleet_scenario, schedulers=_arms(),
        n_seeds=n_seeds, driver_kwargs=_driver_kwargs, record_sink=sink,
    )
    return rows, online, payload, dict(axis_values)


# ---------------------------------------------------------------- stage 5
# The lidar-activation excursion (docs/wp9-plan.md §16). N and composition
# are stage 4's OWN levels so every cell reads against a stage-4
# coordinate; video_tier is held at 1.0 because the excursion is a
# fixed-magnitude perturbation and holding the background constant is what
# isolates it (§16.3).
STAGE5_GRID: dict[str, list[Any]] = {
    "n_ues": [4, 8, 16, 32],
    "composition": ["drone_heavy", "ugv_heavy", "sensor_dense", "mixed"],
    # A JSON SCALAR, not a LidarActivation: cell_id() json-serialises axis
    # values and write_csv needs scalar columns. The runner constructs the
    # dataclass from it.
    "lidar_ues": [0, 1, 2],
}

STAGE5_VIDEO_TIER = 1.0

# Imported rather than restated: wp9_window owns the "which 5QI is the
# lidar" fact, and two copies of it would be one copy too many.
from wp9_window import LIDAR_QFI as _LIDAR_QFI  # noqa: E402

# C2's registered counts (§16.3). Asserted against build_fleet at launch,
# never trusted from here -- this is the expectation, _stage5_cell_census
# is the measurement.
STAGE5_EXPECTED_CENSUS = {
    "total": 48, "control": 16, "excursion": 32, "degenerate": 9, "null": 4,
}


def _build_fleet_scenario_s5(seed: int, **axis_values):
    """Stage-5 scenario: stage 4's fleet plus a duty-cycled lidar activation.

    `lidar_ues=0` MUST take a path byte-identical to stage 4's, because C5
    checks exactly that against sweeps/wp9/stage4/rows.jsonl. It does:
    build_fleet's `lidar=None` branch is stage 4's, and video_tier is
    pinned to the 1.0 stage 4 also ran.
    """
    from sim.fleet import LidarActivation

    n = axis_values["n_ues"]
    lidar_ues = int(axis_values["lidar_ues"])
    lidar = LidarActivation(n_ues=lidar_ues) if lidar_ues > 0 else None
    return _build_fleet_scenario(
        seed, n_ues=n, composition=axis_values["composition"],
        video_tier=STAGE5_VIDEO_TIER, _lidar=lidar,
    )


def _stage5_cell_census(grid: dict) -> dict[str, int]:
    """C2, computed from build_fleet rather than restated in prose.

    CLAUDE.md's rule: a count that describes a structure is derived at the
    point of use or printed by the thing that produces it. The stage-1 grid
    was described as 56 cells while the runner summed 59, and only the
    runner printing its own count surfaced it.
    """
    from sim.fleet import LIDAR_MAX_CONCURRENT, build_fleet

    census = {"total": 0, "control": 0, "excursion": 0,
              "degenerate": 0, "null": 0}
    for n in grid["n_ues"]:
        for comp in grid["composition"]:
            _, seq = build_fleet(n, comp)
            n_ugv = seq.count("ugv")
            for lidar_ues in grid["lidar_ues"]:
                census["total"] += 1
                if lidar_ues == 0:
                    census["control"] += 1
                    continue
                census["excursion"] += 1
                active = min(lidar_ues, LIDAR_MAX_CONCURRENT, n_ugv)
                if active < lidar_ues:
                    census["degenerate"] += 1
                if active == 0:
                    census["null"] += 1
    return census


def _run_one_cell_s5(task: tuple) -> tuple:
    """Stage-4's worker plus the windowed instruments.

    MEMORY: the summary holds `_message_ledger` AND `_ue_lcp`, both live
    objects. The windowed rows are computed here and the summary is
    dropped on return from the sink -- nothing retains it, and nothing
    retains a live RunRecord (CLAUDE.md: a green suite does not prove a
    long run is clean, and 1b's tests stayed green while 1c leaked).
    """
    from sim.fleet import LidarActivation, build_fleet
    from wp9_window import (
        lidar_windows, windowed_flows_from_record, windowed_metrics,
    )

    axis_values, n_seeds, horizon = task
    _HORIZON[0] = horizon
    online: list[dict] = []
    payload: list[tuple] = []
    sc_card = Scorecard()
    lidar_ues = int(axis_values["lidar_ues"])
    lidar = LidarActivation(n_ues=lidar_ues) if lidar_ues > 0 else None

    # COUNTED FROM THE FLOWS build_fleet RETURNED, NOT FROM THE REQUEST
    # (§16.7 B7): `lidar_ues=2` on a composition with one UGV activates
    # one, and that gap IS the degenerate-cell census. Deliberately not
    # counted off the RunRecord -- a record only carries flows that
    # generated traffic, so an activation whose window falls outside a
    # short horizon would read as "not active" when it was provisioned and
    # activated. Deterministic in the axis values, so once per cell.
    cell_flows, _ = build_fleet(
        axis_values["n_ues"], axis_values["composition"],
        lidar=lidar, video_tier=STAGE5_VIDEO_TIER)
    n_active = sum(1 for f in cell_flows if f.qfi == _LIDAR_QFI)
    excluded = n_active > 0

    def run_sink(record, av, summary):
        time_s = record.timeseries_time_s
        horizon_s = (time_s[-1] + (time_s[1] - time_s[0])) if time_s else 0.0
        tag = {**av, "scheduler": record.scheduler_name, "seed": record.seed,
               "n_lidar_active": n_active}
        for row in windowed_metrics(
            summary["_message_ledger"].completions(),
            windowed_flows_from_record(record), time_s,
            lidar_windows(lidar, horizon_s),
        ):
            online.append({**tag, **row})
        # summary goes out of scope here; nothing above holds it.

    def sink(record, av):
        for row in _online_rows_for(sc_card, record, av):
            # §16.5: on a lidar-on cell no run-aggregate panel metric may be
            # quoted. The rows are still WRITTEN in full -- an omitted row is
            # indistinguishable from a forgotten one -- and tagged instead,
            # so the analyser can refuse to aggregate them.
            online.append({**row, "transient_excluded": excluded})
        payload.append((dict(av), _strip_timeseries(record.to_dict()), None))

    rows = sweep(
        axes={k: [v] for k, v in axis_values.items()},
        build_scenario=_build_fleet_scenario_s5, schedulers=_arms(),
        n_seeds=n_seeds, driver_kwargs=_driver_kwargs,
        record_sink=sink, run_sink=run_sink,
    )
    for r in rows:
        r["n_lidar_active"] = n_active
        r["transient_excluded"] = excluded
    return rows, online, payload, dict(axis_values)


def run_stage_5(out_dir: Path, n_seeds: int, horizon: int, workers: int,
                smoke: bool, fresh: bool = False) -> None:
    """Stage 5, reusing stage 3/4's proven resumable loop.

    C2 is asserted BEFORE any cell runs: if the census disagrees with the
    registered counts, `_allocate` or the concurrency cap changed and the
    grid's interpretation is suspect, so aborting beats producing a CSV
    whose degenerate cells are silently a different set.
    """
    grid = {k: (v[:2] if smoke else v) for k, v in STAGE5_GRID.items()}
    census = _stage5_cell_census(grid)
    print(f"stage 5 cell census (from build_fleet): {census}", flush=True)
    if not smoke and census != STAGE5_EXPECTED_CENSUS:
        raise SystemExit(
            f"C2 FAILURE: census {census} != registered "
            f"{STAGE5_EXPECTED_CENSUS} (docs/wp9-plan.md §16.3). The fleet "
            f"allocation or the concurrency cap changed; the grid's "
            f"degenerate cells are not the ones the plan registered.")
    _run_resumable(out_dir, grid, "s5", _run_one_cell_s5, n_seeds, horizon,
                   workers, fresh)


def cell_id(axis_values: dict) -> str:
    """Stable identity for a grid cell.

    Deliberately the SAME identity the analysis uses to select a cell (the
    axis-values mapping), serialised canonically -- not a separate scheme
    that could drift from it and make "already done" mean something
    different from "selected by the analysis".
    """
    return json.dumps({k: axis_values[k] for k in sorted(axis_values)},
                      sort_keys=True)


def _load_completed(rows_path: Path, expected_per_cell: int
                    ) -> tuple[list[dict], set[str]]:
    """Read prior rows; return (rows to keep, ids of COMPLETE cells).

    Two failure modes, deliberately treated DIFFERENTLY:

    - **Partial** (fewer rows than expected) is an ordinary interruption:
      drop the rows and re-run the cell. Appending instead would produce a
      cell of the right size assembled from two different runs' fragments,
      which a naive count check would happily accept.
    - **Oversized** (more rows than expected) should be IMPOSSIBLE -- it
      means something double-wrote -- so it ABORTS rather than being
      silently healed. Healing it would produce a correct final answer
      while hiding the bug that caused it, and the resume path's whole
      purpose is defeated if it can quietly paper over corruption.
    """
    if not rows_path.exists():
        return [], set()
    by_cell: dict[str, list[dict]] = {}
    with rows_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            by_cell.setdefault(rec["cell"], []).append(rec["row"])
    keep: list[dict] = []
    done: set[str] = set()
    partial = 0
    for cid, rws in by_cell.items():
        if len(rws) == expected_per_cell:
            done.add(cid)
            keep.extend(rws)
        elif len(rws) > expected_per_cell:
            raise SystemExit(
                f"RESUME STATE CORRUPT: cell {cid} has {len(rws)} rows, "
                f"expected {expected_per_cell}. An oversized cell means "
                f"something double-wrote; this aborts rather than healing "
                f"it silently. Re-run with --fresh to discard prior output.")
        else:
            partial += 1
    if partial:
        print(f"  resume: dropping {partial} partial cell(s) to re-run")
    return keep, done


def run_stage_4(out_dir: Path, n_seeds: int, horizon: int, workers: int,
                smoke: bool, fresh: bool = False) -> None:
    """Stage 4, resumable, reusing stage 3's proven loop."""
    grid = {k: (v[:2] if smoke else v) for k, v in STAGE4_GRID.items()}
    _run_resumable(out_dir, grid, "s4", _run_one_cell_s4, n_seeds, horizon,
                   workers, fresh)


def run_stage_3(out_dir: Path, grid_name: str, n_seeds: int, horizon: int,
                workers: int, smoke: bool, fresh: bool = False) -> None:
    """Stage 3, resumable.

    WHY RESUMABLE. A long run's cost should be proportional to time LOST,
    not to time ELAPSED. Two runs in this WP have already died mid-flight
    for unrelated reasons -- the OOM/thrash from the retention leak, and a
    laptop restart at cell 35/84 -- and power loss, a full disk or a kernel
    panic would do the same. This is not a reboot mitigation.
    """
    grid = {"q1": STAGE3_Q1, "q2": STAGE3_Q2}[grid_name]
    if smoke:
        grid = {k: v[:2] for k, v in grid.items()}
    _run_resumable(out_dir, grid, grid_name, _run_one_cell_s3, n_seeds,
                   horizon, workers, fresh)


def _run_resumable(out_dir: Path, grid: dict, tag: str, worker, n_seeds: int,
                   horizon: int, workers: int, fresh: bool) -> None:
    """The resumable cell loop, shared by stages 3 and 4.

    Cost is proportional to time LOST, not time ELAPSED: two WP9 runs died
    mid-flight for unrelated reasons (an OOM from the retention leak, a
    laptop restart), and power loss or a full disk would do the same.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    names = list(grid)
    all_tasks = [(dict(zip(names, c)), n_seeds, horizon)
                 for c in itertools.product(*grid.values())]
    expected_per_cell = 3 * n_seeds

    rows_path = out_dir / "rows.jsonl"
    if fresh:
        for f in ("rows.jsonl", "records.jsonl", "online_rows.jsonl"):
            (out_dir / f).unlink(missing_ok=True)
    rows, done = _load_completed(rows_path, expected_per_cell)
    with rows_path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps({"cell": r["__cell"], "row": r}) + "\n")

    tasks = [t for t in all_tasks if cell_id(t[0]) not in done]
    print(f"stage {tag}: {len(all_tasks)} cells, {len(done)} complete, "
          f"{len(tasks)} to run on {workers} workers", flush=True)

    rows_fh = rows_path.open("a")
    rec_fh = (out_dir / "records.jsonl").open("a" if not fresh else "w")
    onl_fh = (out_dir / "online_rows.jsonl").open("a" if not fresh else "w")
    t0 = time.time()
    durations: list[float] = []
    try:
        # Refuse to launch beside an orphaned pool: its workers cannot be
        # found by script name and its memory is charged to this run.
        check_for_orphans()
        with mp.get_context("spawn").Pool(workers) as pool:
            last = time.time()
            for i, (crows, conline, payload, tally) in enumerate(
                    pool.imap_unordered(worker, tasks), 1):
                cid = cell_id({k: v for k, v in tally.items() if k in names})
                for r in crows:
                    r["__cell"] = cid
                    rows.append(r)
                    rows_fh.write(json.dumps({"cell": cid, "row": r}) + "\n")
                rows_fh.flush()
                for r in conline:
                    onl_fh.write(json.dumps(r) + "\n")
                for av, recd, _ in payload:
                    rec_fh.write(json.dumps(
                        {"axis_values": av, "record": recd}) + "\n")
                durations.append(time.time() - last)
                last = time.time()
                # ETA from a ROLLING MEAN of completed cells, not a linear
                # extrapolation from elapsed -- composition makes per-cell
                # cost wildly uneven, and a naive ETA misleads exactly the
                # way N-major ordering did in stage 2. Reported as a RANGE.
                w = durations[-8:]
                lo, hi = min(w), max(w)
                left = len(tasks) - i
                print(f"  cell {i}/{len(tasks)} done | elapsed "
                      f"{(time.time()-t0)/60:.1f}m | eta "
                      f"{left*lo/60:.0f}-{left*hi/60:.0f}m | {tally}",
                      flush=True)
    finally:
        rows_fh.close()
        rec_fh.close()
        onl_fh.close()

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["__cell"]] = counts.get(r["__cell"], 0) + 1
    expected_ids = {cell_id(t[0]) for t in all_tasks}
    missing = expected_ids - set(counts)
    wrong = {c: n for c, n in counts.items() if n != expected_per_cell}
    if missing or wrong or (set(counts) - expected_ids):
        raise SystemExit(
            f"RESUME INTEGRITY FAILURE: {len(missing)} missing, "
            f"{len(wrong)} wrong-sized. Aborting rather than writing a CSV.")

    for r in rows:
        r.pop("__cell", None)
    write_csv(rows, str(out_dir / f"stage{tag}_rows.csv"))
    print(f"  {len(rows)} rows across {len(counts)} cells "
          f"(all exactly {expected_per_cell}) -> {out_dir}", flush=True)


def _run_gate(rows, core, excursions, out_dir: Path) -> None:
    """The gate, run as committed code, output recorded verbatim."""
    arm_pairs = [("PF", "Reservation"), ("PF", "TwoTier"),
                 ("Reservation", "TwoTier")]
    verdicts = []
    for axis, levels in {**core, **excursions}.items():
        # Evaluate an axis on ITS OWN levels only. The base level is not a
        # cell of an excursion axis -- the base point lives in the core
        # plane, and appending it here is what let `pdb_ms`/`inf_scenario`
        # (base None) swallow the whole sweep. Core-plane axes already carry
        # their base value among their levels.
        verdicts.append(wp9_gate.evaluate_axis(rows, axis, list(levels), arm_pairs))
    selection = wp9_gate.select_for_stage_2(verdicts)
    report = wp9_gate.format_verdicts(verdicts, selection)
    (out_dir / "gate_verdict.txt").write_text(report + "\n")
    print("\n" + report)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=int, default=1, choices=(1, 2, 3, 4, 5))
    p.add_argument("--grid", default="q1", choices=("q1", "q2"))
    p.add_argument("--out", default="sweeps/wp9/stage1")
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--horizon", type=int, default=20_000)
    p.add_argument("--workers", type=int, default=12,
                   help="cell-level parallelism; memory-bound, see "
                        "docs/wp9-plan.md §6.3b (0 = serial)")
    p.add_argument("--fresh", action="store_true",
                   help="ignore and truncate prior output (no resume)")
    p.add_argument("--smoke", action="store_true",
                   help="tiny grid, for exercising the machinery only")
    a = p.parse_args()
    if a.stage == 5:
        run_stage_5(Path(a.out), a.seeds, a.horizon, max(1, a.workers),
                    a.smoke, a.fresh)
        return
    if a.stage == 4:
        run_stage_4(Path(a.out), a.seeds, a.horizon, max(1, a.workers),
                    a.smoke, a.fresh)
        return
    if a.stage == 3:
        run_stage_3(Path(a.out), a.grid, a.seeds, a.horizon,
                    max(1, a.workers), a.smoke, a.fresh)
        return
    if a.stage == 2:
        run_stage_2(Path(a.out), a.seeds, a.horizon, a.smoke, max(1, a.workers))
        return
    if a.workers and a.workers > 1:
        run_stage_1_parallel(Path(a.out), a.seeds, a.horizon, a.smoke, a.workers)
    else:
        run_stage_1(Path(a.out), a.seeds, a.horizon, a.smoke)


if __name__ == "__main__":
    main()
