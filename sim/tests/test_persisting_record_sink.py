"""`wp9_sweep.PersistingRecordSink` -- the instrument fix from WP9 §25.

THE DEFECT PINNED HERE was an absence, not a wrong value:
`scripts/g6_seed_extension.py` called `sweep()` with no `record_sink`, so a
40-minute run kept only its scored CSV and the per-flow
`completion_ts_by_role_s` was gone. The falsifier that needed them had to
fall back to a 4x smaller sample and could not decide anything.

So the assertion is about what SURVIVES a run, not about a computed number:
the per-slot arrays must be stripped (they are what made records unaffordable
to keep) while the message/frame ledgers must NOT be.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from wp9_sweep import PersistingRecordSink, _TS_FLOW_FIELDS, _TS_RECORD_FIELDS  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402


def _record() -> RunRecord:
    """A record shaped like a real one: per-slot arrays AND a ledger."""
    return RunRecord.from_dict({
        "schema_version": 1, "scenario_name": "toy", "scheduler_name": "PF",
        "seed": 7, "arm": {}, "meta": {},
        "timeseries_time_s": [0.0, 0.5, 1.0],
        "timeseries_slot_index": [0, 1, 2],
        "system": {"horizon_s": 1.0, "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0,
                   "ts_dl_prbs_used": [1, 2, 3]},
        "flows": {"ue1_qfi1": {
            "ue_id": 1, "qfi": 1, "direction": "UL", "flow_class": "Delay",
            "priority_level": 100, "pdb_ms": 100.0, "gfbr_bps": 0.0,
            "bytes_arrived": 10, "bytes_delivered": 10, "bytes_dropped_pdb": 0,
            "bytes_delivered_late_pdb": 0, "bytes_harq_lost": 0,
            "delivery_ratio": 1.0, "throughput_bps": 1.0, "offered_bps": 1.0,
            "delay_p50_ms": 1.0, "delay_p95_ms": 1.0, "delay_p98_ms": 1.0,
            "delay_p99_ms": 1.0, "survival_time_ms": 0.0, "message_count": 3,
            "delay_p50_ms_proxy": 1.0, "delay_p95_ms_proxy": 1.0,
            "delay_p98_ms_proxy": 1.0, "delay_p99_ms_proxy": 1.0,
            "ts_backlog_bytes": [1, 2, 3], "ts_hol_delay_s": [0.1, 0.2, 0.3],
            "completion_ts_by_role_s": {"data": [0.1, 0.6, 1.1]},
            "frame_completions": {"total": 1},
        }},
        "join_events": [],
    })


def test_ledger_survives_persistence_which_is_the_whole_point(tmp_path):
    """The per-flow completion timestamps are what a later re-analysis needs.
    Losing them is what forced a 40-minute run to be repeated."""
    path = tmp_path / "records.jsonl"
    with PersistingRecordSink(path) as sink:
        sink(_record(), {"bg": True})
        assert sink.n == 1
    payload = json.loads(path.read_text().strip())
    flow = payload["record"]["flows"]["ue1_qfi1"]
    assert flow["completion_ts_by_role_s"] == {"data": [0.1, 0.6, 1.1]}, \
        "completion_ts_by_role_s must survive -- a restricted M03 needs it"
    assert flow["frame_completions"] == {"total": 1}
    assert payload["axis_values"] == {"bg": True}


def test_per_slot_arrays_are_stripped(tmp_path):
    """The arrays are why whole records were unaffordable to keep; stripping
    them is what makes persistence cheap enough to be the default."""
    path = tmp_path / "records.jsonl"
    with PersistingRecordSink(path) as sink:
        sink(_record(), {})
    d = json.loads(path.read_text().strip())["record"]
    for field in _TS_RECORD_FIELDS:
        assert d[field] is None, f"{field} should be stripped"
    for field in _TS_FLOW_FIELDS:
        if field in d["flows"]["ue1_qfi1"]:
            assert d["flows"]["ue1_qfi1"][field] is None, f"{field} should be stripped"
    assert d["system"]["ts_dl_prbs_used"] is None


def test_sink_does_not_mutate_the_live_record(tmp_path):
    """`sweep()` scores the record AFTER calling record_sink, so a sink that
    mutated it would silently change every scored row."""
    rec = _record()
    with PersistingRecordSink(tmp_path / "r.jsonl") as sink:
        sink(rec, {})
    assert rec.timeseries_time_s == [0.0, 0.5, 1.0]
    assert rec.flows["ue1_qfi1"].ts_hol_delay_s == [0.1, 0.2, 0.3]
    assert rec.flows["ue1_qfi1"].completion_ts_by_role_s == {"data": [0.1, 0.6, 1.1]}
