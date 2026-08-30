"""Memory-retention guards for scripts/wp9_sweep.py.

WHY THIS FILE EXISTS. Stage 1 was launched, ran to 756 of ~1,680 records,
reached 25 GB RSS with 32 GiB of swap in use, and stalled -- the machine was
thrashing, not computing. Cause: `run_stage_1` retained every live
`RunRecord` so M13 could read them at the end, while `_RecordSink` stripped
only a serialised *copy*. Each retained record still carried its per-slot
arrays, ~33 MB each.

Without a test that pins retention, the leak returns the first time someone
adds a field to the aggregation -- which is exactly how it arrived.
"""

import sys
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from wp9_sweep import (  # noqa: E402
    _SCORING_VARIATIONS,
    _TS_FLOW_FIELDS,
    _TS_RECORD_FIELDS,
    _TS_SYSTEM_FIELDS,
    _strip_timeseries,
    m13_projection,
)
from sim.parametric import sweep_scenario  # noqa: E402
from sim.driver import run  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.baselines.pf import ProportionalFair  # noqa: E402


def _record(n_ues=4, horizon=2000, seed=1):
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon)
    summary = run(sc, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=True)
    return RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def test_m13_projection_drops_every_per_slot_array():
    """Structural, not size-based: a new timeseries field added to
    RunRecord/FlowRecord must not silently start being retained. This is the
    assertion that survives someone extending the aggregation."""
    rec = _record()
    proj = m13_projection(rec)

    assert proj.timeseries_time_s is None
    assert proj.timeseries_slot_index is None
    assert not proj.has_timeseries()
    for fr in proj.flows.values():
        assert not fr.has_timeseries()
        for f in _TS_FLOW_FIELDS:
            assert getattr(fr, f) is None, f
        assert fr.completion_ts_by_role_s is None
        assert fr.frame_completions is None
    if proj.system is not None:
        for f in _TS_SYSTEM_FIELDS:
            assert getattr(proj.system, f) is None, f


def test_m13_projection_keeps_what_m13_actually_reads():
    """The projection must stay a real RunRecord that
    Scorecard.first_violation_order can consume -- the point of projecting
    rather than hand-rolling a summary is that no scorecard logic is
    duplicated."""
    from sim.scorecard import Scorecard

    recs = [m13_projection(_record(seed=s)) for s in (1, 2)]
    gbr = [fr for fr in recs[0].flows_by(flow_class="GBR")]
    assert gbr, "projection dropped the GBR flows M13 needs"
    assert all(fr.gfbr_fraction() is not None for fr in gbr)

    class_of = {fr.key: fr.qfi for fr in recs[0].flows.values()}
    res = Scorecard().first_violation_order(recs, class_of)
    assert res.status == "ok"


def test_strip_timeseries_covers_the_top_level_arrays():
    """Commit 1a missed `timeseries_time_s`/`timeseries_slot_index` -- they
    are RunRecord fields, under neither `flows` nor `system` -- leaving two
    20,000-element lists on every persisted record (0.76 MB of 1.087 MB)."""
    d = _strip_timeseries(_record().to_dict())
    for f in _TS_RECORD_FIELDS:
        assert d[f] is None, f
    for fr in d["flows"].values():
        for f in _TS_FLOW_FIELDS:
            assert fr[f] is None, f


def test_retention_does_not_grow_with_the_number_of_records():
    """The leak guard proper, with BOTH assertions.

    Per-cell growth alone is not sufficient: a runner that allocated 20 GB
    on the first cell and nothing after would pass a growth-only check while
    being just as unusable. So this pins the marginal cost AND the absolute
    ceiling.
    """
    tracemalloc.start()
    try:
        kept = []
        base = tracemalloc.get_traced_memory()[0]
        for seed in range(2):
            kept.append(m13_projection(_record(seed=seed)))
        after_2 = tracemalloc.get_traced_memory()[0]
        for seed in range(2, 6):
            kept.append(m13_projection(_record(seed=seed)))
        after_6 = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    per_record = (after_6 - after_2) / 4 / 1e6
    absolute = (after_6 - base) / 1e6

    # An unstripped record is ~2 MB even at this tiny horizon (and ~33 MB at
    # the real one), so 0.5 MB/record separates cleanly from the leak while
    # leaving room for the projection's real content.
    assert per_record < 0.5, (
        f"retention grows {per_record:.3f} MB per record -- the projection is "
        f"holding per-slot data again")
    assert absolute < 5.0, (
        f"absolute retention {absolute:.2f} MB for 6 records -- growth per "
        f"record is bounded but the baseline is not")


def test_scoring_variations_are_the_four_pre_registered_ones():
    """These drive 12 extra Scorecard.score() calls per record -- the cost
    §8's original budget omitted entirely. Pinned so the count cannot drift
    silently and invalidate the re-derived timing."""
    assert tuple(name for name, _ in _SCORING_VARIATIONS) == (
        "survival_miss_n", "t_live_s", "gbr_contract_fraction",
        "slo_green_dwell_s",
    )
    assert sum(len(v) for _, v in _SCORING_VARIATIONS) == 12


def test_worker_does_not_retain_records_across_a_cell():
    """The leak commit 1c reintroduced inside the parallel worker, caught
    mid-run: `_run_one_cell` accumulated every live RunRecord for a cell and
    converted only at the end, holding 30 x ~33 MB per worker -- measured at
    1.4-2.1 GiB per worker across 12 workers before it was killed.

    1b's tests missed it because they pinned `m13_projection` and the
    PARENT's retention -- one layer above the bug. This one exercises the
    worker itself, which is the layer that actually runs the sweep.
    """
    import tracemalloc
    from wp9_sweep import _run_one_cell

    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        _run_one_cell(({"n_ues": 4, "load_mult": 1.0}, 2, 1000))
        after_2 = tracemalloc.get_traced_memory()[0]
        _run_one_cell(({"n_ues": 4, "load_mult": 1.0}, 6, 1000))
        after_6 = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    # Tripling the seeds must not triple retention: the worker returns
    # stripped payload, so cost scales with payload size, not record size.
    growth = (after_6 - after_2) / 1e6
    absolute = (after_6 - base) / 1e6
    assert growth < 5.0, (
        f"worker retention grew {growth:.2f} MB when seeds went 2 -> 6; it is "
        f"holding live records again")
    assert absolute < 20.0, f"worker absolute retention {absolute:.2f} MB"


def test_stage5_worker_does_not_retain_the_summary():
    """Stage 5's worker is handed the RAW driver summary via `run_sink` --
    which holds `_message_ledger` AND `_ue_lcp`, both live objects the
    stripped payload never carried before. That is a NEW retention surface,
    on the layer that actually runs the sweep.

    This is the test the CLAUDE.md invariant asks for: commit 1b's guards
    stayed green while 1c reintroduced the identical leak one layer down,
    because they pinned the helper and not the pipeline. So pin the
    pipeline.
    """
    import tracemalloc
    from wp9_sweep import _run_one_cell_s5

    cell = {"n_ues": 4, "composition": "ugv_heavy", "lidar_ues": 2}
    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        _run_one_cell_s5((dict(cell), 2, 1000))
        after_2 = tracemalloc.get_traced_memory()[0]
        _run_one_cell_s5((dict(cell), 6, 1000))
        after_6 = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()

    growth = (after_6 - after_2) / 1e6
    absolute = (after_6 - base) / 1e6
    assert growth < 5.0, (
        f"stage-5 worker retention grew {growth:.2f} MB when seeds went "
        f"2 -> 6; it is holding summaries or live records")
    assert absolute < 20.0, (
        f"stage-5 worker absolute retention {absolute:.2f} MB")


def test_stage5_worker_emits_windowed_rows_and_the_exclusion_tag():
    """The worker must actually produce §16.4's windowed rows (the run_sink
    path) and tag every run-aggregate row on a lidar-on cell as excluded
    (§16.5) -- rows written in full, never omitted, but marked so the
    analyser can refuse to aggregate them."""
    from wp9_sweep import _run_one_cell_s5

    rows, online, payload, tally = _run_one_cell_s5(
        ({"n_ues": 4, "composition": "ugv_heavy", "lidar_ues": 2}, 1, 1000))

    assert all(r["n_lidar_active"] == 2 for r in rows)
    assert all(r["transient_excluded"] is True for r in rows)

    windowed = [r for r in online if r.get("metric", "").endswith("w")]
    assert windowed, "run_sink produced no windowed rows"
    assert {r["window"] for r in windowed} == {
        "pre", "during_1", "during_2", "post", "full"}
    assert {r["subset"] for r in windowed} == {
        "non_lidar", "tight_pdb", "estop", "lidar_only"}
    # M07w and M08w are never emitted apart (§0.1's rule, made structural).
    assert (sum(1 for r in windowed if r["metric"] == "M07w")
            == sum(1 for r in windowed if r["metric"] == "M08w"))


def test_stage5_census_matches_the_registered_counts():
    """C2 (docs/wp9-plan.md §16.3), computed from build_fleet rather than
    restated -- CLAUDE.md's rule after the stage-1 grid was documented as 56
    cells while the runner summed 59."""
    from wp9_sweep import (
        STAGE5_EXPECTED_CENSUS, STAGE5_GRID, _stage5_cell_census,
    )
    assert _stage5_cell_census(STAGE5_GRID) == STAGE5_EXPECTED_CENSUS


def test_stage5_control_path_is_byte_identical_to_stage_4():
    """C5's precondition. `lidar_ues=0` must build exactly the scenario
    stage 4 built at video_tier=1.0, or the control is not a control."""
    from wp9_sweep import _build_fleet_scenario, _build_fleet_scenario_s5

    for comp in ("ugv_heavy", "sensor_dense"):
        s4 = _build_fleet_scenario(7, n_ues=8, composition=comp,
                                   video_tier=1.0)
        s5 = _build_fleet_scenario_s5(7, n_ues=8, composition=comp,
                                      lidar_ues=0)
        assert s5 == s4, comp
