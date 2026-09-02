"""The five windowed metrics G11's C1 needs, and the 60 s partition.

WP9 G11 commit 6. `--check` is blind here (study layer, no corpus case
builds these), so the binding guards are: the partition really partitions,
each metric agrees with its panel counterpart at the `full` window where
that is meaningful, and each emits None-with-a-reason rather than a
misleading zero when its window is empty.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Scorecard
from wp9_window import (Window, fixed_windows, windowed_flows_from_record,
                        windowed_metrics)

H = 40_000            # 10 s


@pytest.fixture(scope="module")
def run_data():
    sc = sweep_scenario(seed=1, n_ues=4, horizon_slots=H)
    summary = run(sc, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=True)
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=1,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})
    return summary, rec


def _rows(run_data, windows, subsets=None):
    summary, rec = run_data
    return windowed_metrics(
        summary["_message_ledger"].completions(),
        windowed_flows_from_record(rec),
        rec.timeseries_time_s, windows,
        subsets=subsets or {"all": lambda f: True})


def test_fixed_windows_is_a_contiguous_partition_with_a_clipped_tail():
    w = fixed_windows(150.0, 60.0)
    assert [(x.start_s, x.end_s) for x in w] == [(0.0, 60.0), (60.0, 120.0), (120.0, 150.0)]
    assert w[-1].end_s == 150.0, "the tail window must be clipped, not dropped"
    for a, b in zip(w, w[1:]):
        assert a.end_s == b.start_s, "windows must be contiguous"
    assert len(fixed_windows(1800.0, 60.0)) == 30
    with pytest.raises(ValueError):
        fixed_windows(0.0, 60.0)


def test_all_five_new_metrics_emit_a_row_per_window(run_data):
    rows = _rows(run_data, fixed_windows(10.0, 2.0))
    got = {r["metric"] for r in rows}
    for m in ("M03w", "M05w", "M06w", "M09w", "M15w"):
        assert m in got, f"{m} emitted no row at all"
    from collections import Counter
    per = Counter((r["window"], r["metric"]) for r in rows)
    assert set(per.values()) == {1}, "a metric emitted twice for one window"


def test_an_empty_window_emits_None_with_a_reason_never_a_zero(run_data):
    """0.0 is a real value for several of these -- best latency, worst
    completeness. None must be distinguishable from it."""
    far = [Window(name="empty", start_s=9_000.0, end_s=9_060.0)]
    for r in _rows(run_data, far):
        # M01w reports percentiles rather than a single `value`
        vals = ([r[k] for k in ("p50", "p95", "p98", "p99") if k in r]
                or [r.get("value")])
        assert all(v is None for v in vals), \
            f"{r['metric']} invented {vals!r} for an empty window"
        assert r.get("reason"), f"{r['metric']} returned None with no reason"


def test_M09w_over_the_whole_run_tracks_panel_M09(run_data):
    """Same statistic, same bucketing -- one window covering the run should
    land on the panel's worst second."""
    _, rec = run_data
    whole = [Window(name="full", start_s=0.0, end_s=H * 0.00025)]
    m09w = [r for r in _rows(run_data, whole) if r["metric"] == "M09w"][0]
    panel = Scorecard()._m09_per_second_jain(rec).value
    assert m09w["value"] is not None and panel is not None
    assert m09w["value"] == pytest.approx(panel["worst"], abs=1e-9), (
        "M09w over the whole run must equal panel M09's worst second; a "
        "difference means the windowed version is bucketing differently")


def test_M03w_selects_on_COMPLETION_time_not_generation():
    """The opposite of M01w's choice, and deliberate: a liveness gap is a
    receiver-side inter-arrival statistic, so the question is when messages
    ARRIVED, not when they were offered.

    Synthetic and deterministic: two messages generated INSIDE the window
    but completing after it, and two generated before it but completing
    inside. M01w must see the first pair, M03w the second.
    """
    from sim.messages import Message, MessageCompletion
    from wp9_window import WindowedFlow

    def mc(mid, gen, done):
        return MessageCompletion(
            message=Message(id=mid, ue_id=1, qfi=1, size_bytes=100,
                            generation_ts_s=gen),
            complete=True, late=False, completion_ts_s=done,
            delivered_bytes=100, dropped_bytes=0)

    comps = [mc(1, 1.1, 5.0), mc(2, 1.2, 6.0),     # generated in, completed out
             mc(3, 0.1, 1.3), mc(4, 0.2, 1.6)]     # generated out, completed in
    flows = [WindowedFlow(key="ue1_qfi1", ue_id=1, qfi=1, direction="UL",
                          flow_class="Delay", gfbr_bps=0.0, pdb_ms=100.0)]
    w = [Window(name="w", start_s=1.0, end_s=2.0)]
    rows = {r["metric"]: r for r in windowed_metrics(
        comps, flows, None, w, subsets={"all": lambda f: True})}

    assert rows["M01w"]["n_messages"] == 2, "M01w must select on GENERATION time"
    m03 = rows["M03w"]
    assert m03["value"] is not None, "M03w saw no completions in the window"
    assert m03["value"] == pytest.approx(300.0, abs=1e-6), (
        "M03w's gap must be between the two COMPLETIONS inside the window "
        "(1.3 -> 1.6 s = 300 ms); a different value means it selected on "
        "generation time like M01w")


def test_M05w_carries_its_estimator_divergence_in_the_row(run_data):
    """M05w regroups the WINDOW's completions by frame_id; panel M05 reads
    frame_completions built over the whole run. A frame straddling a
    boundary is counted differently -- the M02w-vs-M02 shape. The row must
    carry enough to see that (n_frames), not just a bare fraction."""
    rows = [r for r in _rows(run_data, fixed_windows(10.0, 2.0))
            if r["metric"] == "M05w"]
    assert rows
    assert all("n_frames" in r for r in rows)
    scored = [r for r in rows if r["value"] is not None]
    assert scored, "no window scored M05w at all"
    assert all(0.0 <= r["value"] <= 1.0 for r in scored)


def test_prebucketing_did_not_change_the_existing_metrics(run_data):
    """M01w/M02w/M07w/M08w must be unaffected by commit 6 -- the rewrite
    changed HOW completions reach them, not WHICH ones."""
    summary, rec = run_data
    whole = [Window(name="full", start_s=0.0, end_s=H * 0.00025)]
    m01w = [r for r in _rows(run_data, whole) if r["metric"] == "M01w"][0]
    panel = Scorecard()._m01_latency_percentiles(rec)
    assert m01w["p98"] == pytest.approx(panel.value["p98"]), (
        "M01w over the whole run diverged from panel M01 -- pre-bucketing "
        "changed the population, which it must not")
