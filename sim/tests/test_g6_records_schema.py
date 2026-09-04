"""The persisted G6 record envelope.

WHY THIS EXISTS. `g6_seed_extension.py`'s parallelisation replaced its
`PersistingRecordSink` with an inline sink and dropped the
`{"axis_values": ..., "record": ...}` envelope -- silently, because every
reader unwraps it and none was run in that commit. The serial-vs-parallel
identity check did not catch it: it compares NEW code against NEW code, so it
binds on the axis it was built for (ordering under a pool) and not on the one
that moved (the schema). Found by the verification pass, when
g6_fleet_restricted_m03.py raised KeyError('axis_values') on a fresh file.

The lesson is the one this project keeps relearning at a new level: an
identity check establishes that two paths agree with EACH OTHER, never that
either agrees with what came before.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import g6_seed_extension  # noqa: E402
import wp9_sweep  # noqa: E402


def test_persisted_records_carry_the_axis_values_envelope(tmp_path):
    out = tmp_path / "recs.jsonl"
    rows = g6_seed_extension.collect_rows(n_seeds=1, horizon=800,
                                          records_path=out, workers=1)
    assert rows
    lines = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert lines, "no records were persisted"
    for rec in lines:
        assert set(rec) == {"axis_values", "record"}, (
            f"record envelope changed: {sorted(rec)[:6]}. Every reader of "
            f"these files unwraps 'record' and keys on 'axis_values'.")
        assert "bg" in rec["axis_values"]
        assert "flows" in rec["record"]


def test_the_envelope_matches_PersistingRecordSink(tmp_path):
    """The two writers of this format must not drift apart -- which is
    exactly what happened."""
    # Build the reference through the sim's own path rather than by hand, so
    # the fixture cannot drift from RunRecord's real signature.
    from sim.driver import run
    from sim.parametric import sweep_scenario
    from sim.run_record import RunRecord
    from sim.baselines.pf import ProportionalFair
    sc = sweep_scenario(seed=1, n_ues=2, horizon_slots=800, load_mult=1.0)
    summary = run(sc, ProportionalFair(ewma_window_slots=200))
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="PF",
                                 seed=1, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    out = tmp_path / "sink.jsonl"
    sink = wp9_sweep.PersistingRecordSink(out)
    sink(rec, {"bg": False})
    sink.close()
    ref = json.loads(out.read_text().splitlines()[0])

    out2 = tmp_path / "g6.jsonl"
    g6_seed_extension.collect_rows(n_seeds=1, horizon=800,
                                   records_path=out2, workers=1)
    got = json.loads(out2.read_text().splitlines()[0])
    assert set(ref) == set(got), (
        f"g6_seed_extension writes {sorted(got)} where PersistingRecordSink "
        f"writes {sorted(ref)}")
