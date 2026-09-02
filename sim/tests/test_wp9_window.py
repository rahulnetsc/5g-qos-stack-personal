"""Tests for WP9 stage 5's windowed instruments (docs/wp9-plan.md §16.4).

The load-bearing one is `test_m01w_equals_panel_m01_over_the_full_run`:
M01w is claimed to be a PURE RESTRICTION of panel M01 -- same formula,
same percentile convention, fewer samples -- and that claim is only worth
anything if it is pinned. M02w is deliberately NOT pinned that way; it
differs in accounting as well as population, which is what control C3
exists to measure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import pytest

from wp9_window import (
    DEFAULT_SUBSETS,
    ESTOP_QFI,
    LIDAR_QFI,
    Window,
    WindowedFlow,
    lidar_windows,
    windowed_flows_from_record,
    windowed_metrics,
)
from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.fleet import LidarActivation
from sim.messages import Message, MessageCompletion
from sim.run_record import RunRecord
from sim.scenarios import smoke_scenario
from sim.scorecard import Scorecard


# --- synthetic fixtures ---------------------------------------------------

def _completion(ue_id, qfi, gen_s, done_s, size=1000, complete=True,
                late=False):
    msg = Message(id=0, ue_id=ue_id, qfi=qfi, size_bytes=size,
                  generation_ts_s=gen_s)
    return MessageCompletion(
        message=msg, complete=complete, late=late, completion_ts_s=done_s,
        delivered_bytes=size if complete else 0,
        dropped_bytes=0 if complete else size,
    )


def _flow(ue_id, qfi, flow_class="GBR", gfbr=1000.0, pdb=20.0, ts=None):
    return WindowedFlow(
        key=f"ue{ue_id}_qfi{qfi}", ue_id=ue_id, qfi=qfi, direction="UL",
        flow_class=flow_class, gfbr_bps=gfbr, pdb_ms=pdb,
        ts_delivered_bytes=ts,
    )


def _rows_by(rows, metric, window, subset):
    return [r for r in rows if r["metric"] == metric
            and r["window"] == window and r["subset"] == subset]


# --- windows are derived, not hardcoded -----------------------------------

def test_lidar_windows_derive_from_the_activation_fields():
    w = {x.name: x for x in lidar_windows(LidarActivation(), horizon_s=5.0)}
    assert (w["pre"].start_s, w["pre"].end_s) == (0.0, 1.5)
    assert (w["during_1"].start_s, w["during_1"].end_s) == (1.5, 3.5)
    assert (w["during_2"].start_s, w["during_2"].end_s) == (1.5, 4.0)
    assert (w["post"].start_s, w["post"].end_s) == (4.0, 5.0)
    assert (w["full"].start_s, w["full"].end_s) == (0.0, 5.0)


def test_lidar_windows_follow_changed_fields_rather_than_constants():
    lid = LidarActivation(start_s=1.0, duration_s=0.5, stagger_s=0.25)
    w = {x.name: x for x in lidar_windows(lid, horizon_s=3.0)}
    assert (w["during_1"].start_s, w["during_1"].end_s) == (1.0, 1.5)
    assert (w["during_2"].start_s, w["during_2"].end_s) == (1.0, 1.75)
    assert w["pre"].end_s == 1.0
    assert w["post"].start_s == 1.75


def test_synchronised_collapses_during_2_onto_during_1():
    lid = LidarActivation(synchronised=True)
    w = {x.name: x for x in lidar_windows(lid, horizon_s=5.0)}
    assert w["during_2"].end_s == w["during_1"].end_s


def test_control_cells_get_the_same_window_coordinates():
    """A control (lidar=None) must be scored at the same intervals or it
    cannot pair with an excursion cell."""
    ctrl = {x.name: (x.start_s, x.end_s) for x in lidar_windows(None, 5.0)}
    exc = {x.name: (x.start_s, x.end_s)
           for x in lidar_windows(LidarActivation(n_ues=2), 5.0)}
    assert ctrl == exc


# --- window selection -----------------------------------------------------

def test_window_is_half_open_at_both_ends():
    w = Window("t", 1.0, 2.0)
    assert w.contains(1.0) is True       # start included
    assert w.contains(1.999) is True
    assert w.contains(2.0) is False      # end excluded
    assert w.contains(0.999) is False


def test_selection_is_on_generation_time_not_completion_time():
    """A message offered before the window but completing inside it does
    NOT belong to the window -- otherwise the window is credited with
    traffic it never received."""
    comps = [_completion(1, 9, gen_s=0.5, done_s=1.5)]
    flows = [_flow(1, 9, flow_class="PF", gfbr=0.0)]
    rows = windowed_metrics(comps, flows, None, [Window("w", 1.0, 2.0)],
                            subsets={"all": lambda f: True})
    m01 = _rows_by(rows, "M01w", "w", "all")[0]
    assert m01["n_flows"] == 0
    assert m01["p99"] is None


def test_empty_window_reports_none_with_a_reason_never_zero():
    """0.0 ms is the BEST possible latency; a forgotten window must not be
    indistinguishable from a perfect one."""
    rows = windowed_metrics([], [_flow(1, 9)], None, [Window("w", 0.0, 1.0)],
                            subsets={"all": lambda f: True})
    m01 = _rows_by(rows, "M01w", "w", "all")[0]
    m02 = _rows_by(rows, "M02w", "w", "all")[0]
    assert m01["p99"] is None and "reason" in m01
    assert m02["value"] is None and "reason" in m02


def test_a_flow_completing_nothing_is_excluded_not_scored_as_zero():
    comps = [
        _completion(1, 9, 0.1, 0.2, size=500),               # delivers
        _completion(2, 9, 0.1, 0.2, size=500, complete=False),  # drops only
    ]
    flows = [_flow(1, 9), _flow(2, 9)]
    rows = windowed_metrics(comps, flows, None, [Window("w", 0.0, 1.0)],
                            subsets={"all": lambda f: True})
    m01 = _rows_by(rows, "M01w", "w", "all")[0]
    assert m01["n_flows"] == 2
    assert m01["n_excluded_zero_complete"] == 1
    assert m01["flow"] == "ue1_qfi9"


# --- subsets --------------------------------------------------------------

def test_default_subsets_select_the_intended_flows():
    flows = [
        _flow(1, LIDAR_QFI, pdb=100.0),
        _flow(1, ESTOP_QFI, pdb=5.0),
        _flow(1, 83, pdb=10.0),
        _flow(2, 9, flow_class="PF", gfbr=0.0, pdb=300.0),
    ]
    picked = {name: {f.key for f in flows if pred(f)}
              for name, pred in DEFAULT_SUBSETS.items()}
    assert picked["lidar_only"] == {f"ue1_qfi{LIDAR_QFI}"}
    assert f"ue1_qfi{LIDAR_QFI}" not in picked["non_lidar"]
    assert picked["estop"] == {f"ue1_qfi{ESTOP_QFI}"}
    # tight_pdb is non-lidar AND <= 30 ms: e-stop (5) and odometry (10),
    # not the 300 ms best-effort flow.
    assert picked["tight_pdb"] == {f"ue1_qfi{ESTOP_QFI}", "ue1_qfi83"}


def test_lidar_flow_is_excluded_from_non_lidar_m02w():
    comps = [
        _completion(1, LIDAR_QFI, 0.1, 0.2, size=1000, complete=False),
        _completion(1, 83, 0.1, 0.2, size=100),
    ]
    flows = [_flow(1, LIDAR_QFI), _flow(1, 83)]
    rows = windowed_metrics(comps, flows, None, [Window("w", 0.0, 1.0)])
    non_lidar = _rows_by(rows, "M02w", "w", "non_lidar")[0]
    lidar_only = _rows_by(rows, "M02w", "w", "lidar_only")[0]
    assert non_lidar["value"] == pytest.approx(0.0)   # the 83 flow was fine
    assert lidar_only["value"] == pytest.approx(1.0)  # the lidar dropped all


# --- M07w / M08w ----------------------------------------------------------

def test_m07w_and_m08w_use_covered_duration_and_the_panel_fraction():
    # 10 slots of 0.1 s; flow delivers 100 bytes in each of slots 5-9.
    time_s = [i * 0.1 for i in range(10)]
    ts = [0] * 5 + [100] * 5
    # In [0.5, 1.0): 5 samples, 500 bytes, 0.5 s -> 8000 bps.
    flows = [_flow(1, 83, gfbr=8000.0, ts=ts)]
    rows = windowed_metrics([], flows, time_s, [Window("w", 0.5, 1.0)],
                            subsets={"all": lambda f: True})
    m07 = _rows_by(rows, "M07w", "w", "all")[0]
    m08 = _rows_by(rows, "M08w", "w", "all")[0]
    assert m07["window_s"] == pytest.approx(0.5)
    assert m08["fraction"] == pytest.approx(1.0)
    assert m07["met"] == 1          # 1.0 >= 0.95
    # Same flow over the empty first half delivers nothing.
    rows2 = windowed_metrics([], flows, time_s, [Window("w", 0.0, 0.5)],
                             subsets={"all": lambda f: True})
    assert _rows_by(rows2, "M08w", "w", "all")[0]["fraction"] == pytest.approx(0.0)
    assert _rows_by(rows2, "M07w", "w", "all")[0]["met"] == 0


def test_m07w_m08w_report_none_when_there_is_no_timeseries():
    rows = windowed_metrics([], [_flow(1, 83, gfbr=1000.0)], None,
                            [Window("w", 0.0, 1.0)],
                            subsets={"all": lambda f: True})
    for metric in ("M07w", "M08w"):
        row = _rows_by(rows, metric, "w", "all")[0]
        assert "reason" in row
        assert row.get("met", row.get("fraction")) is None


def test_m07w_m08w_are_always_emitted_together():
    """§0.1's rule is structural here: neither can be quoted alone if the
    runner cannot emit one without the other."""
    time_s = [i * 0.1 for i in range(10)]
    rows = windowed_metrics([], [_flow(1, 83, gfbr=8000.0, ts=[10] * 10)],
                            time_s, lidar_windows(LidarActivation(), 1.0))
    for subset in DEFAULT_SUBSETS:
        for w in ("pre", "during_1", "during_2", "post", "full"):
            n07 = len(_rows_by(rows, "M07w", w, subset))
            n08 = len(_rows_by(rows, "M08w", w, subset))
            assert n07 == n08 == 1


# --- the pure-restriction claim, against a real run -----------------------

def test_m01w_equals_panel_m01_over_the_full_run():
    """M01w is claimed to be a pure restriction of panel M01. At the full
    window with nothing excluded, "restriction" means "identical" -- so
    this is the claim, pinned."""
    sc = smoke_scenario()
    summary = run(sc, ProportionalFair(), record_timeseries=True)
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=sc.seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={},
    )
    panel = Scorecard().score(rec)["M01"]
    assert panel.status == "ok"

    time_s = rec.timeseries_time_s
    horizon_s = time_s[-1] + (time_s[1] - time_s[0])
    rows = windowed_metrics(
        summary["_message_ledger"].completions(),
        windowed_flows_from_record(rec),
        time_s,
        [Window("full", 0.0, horizon_s)],
        subsets={"all": lambda f: True},
    )
    m01w = _rows_by(rows, "M01w", "full", "all")[0]
    for p in ("p50", "p95", "p98", "p99"):
        assert m01w[p] == pytest.approx(panel.value[p]), p


def test_windowed_metrics_emit_a_row_for_every_window_subset_metric():
    """The panel's never-omit rule, applied to the study layer: an omitted
    row is indistinguishable from a forgotten one."""
    windows = lidar_windows(LidarActivation(), horizon_s=5.0)
    rows = windowed_metrics([], [_flow(1, 83)], None, windows)
    # DERIVED, not restated. This read "* 4" and went stale the moment G11
    # commit 6 added M03w/M05w/M06w/M09w/M15w -- CLAUDE.md's restated-count
    # rule, fourth instance, whose aggravating feature is that a test which
    # restates a count fails in the direction of PASSING when the new thing
    # is absent. What must hold is that the grid is COMPLETE: every
    # (window, subset) pair emits the same metric set, with none missing.
    n_metrics = len({r["metric"] for r in rows})
    assert n_metrics >= 4, "the metric set collapsed"
    assert len(rows) == len(windows) * len(DEFAULT_SUBSETS) * n_metrics
    from collections import Counter
    per_cell = Counter((r["window"], r["subset"]) for r in rows)
    assert set(per_cell.values()) == {n_metrics}, \
        f"some (window, subset) cell is missing metrics: {per_cell}"
    for r in rows:
        assert {"window", "subset", "metric",
                "window_start_s", "window_end_s"} <= set(r)
