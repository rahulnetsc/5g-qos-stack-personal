import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import pytest

from regime_sweep import (
    aggregate,
    bootstrap_ci,
    check_contiguity,
    paired_seeds,
    regime_selection_excluded,
    sweep,
    write_csv,
)
from sim.scenarios import smoke_scenario
from sim.messages import MessageLedger
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin


def _build_scenario(seed, capacity_mult):
    sc = smoke_scenario()
    carrier = dataclasses.replace(
        sc.carrier, bandwidth_hz=int(sc.carrier.bandwidth_hz * capacity_mult)
    )
    return dataclasses.replace(sc, carrier=carrier, seed=seed)


def test_paired_seeds_deterministic_and_shared_across_arms():
    a = paired_seeds(5, base_seed=1)
    b = paired_seeds(5, base_seed=1)
    assert a == b
    assert len(set(a)) == 5  # no accidental collisions at this size


def test_sweep_produces_expected_row_count():
    rows = sweep(
        axes={"capacity_mult": [0.5, 1.0]},
        build_scenario=_build_scenario,
        schedulers={"PF": ProportionalFair, "RR": RoundRobin},
        n_seeds=2,
    )
    # 2 axis values x 2 seeds x 2 schedulers
    assert len(rows) == 2 * 2 * 2
    for row in rows:
        assert row["capacity_mult"] in (0.5, 1.0)
        assert row["scheduler"] in ("PF", "RR")
        assert "M10" in row  # aggregate_throughput, always ok
        assert "M07.status" in row


def test_sweep_pairs_seeds_across_schedulers_within_a_cell():
    rows = sweep(
        axes={"capacity_mult": [1.0]},
        build_scenario=_build_scenario,
        schedulers={"PF": ProportionalFair, "RR": RoundRobin},
        n_seeds=3,
    )
    pf_seeds = sorted(r["seed"] for r in rows if r["scheduler"] == "PF")
    rr_seeds = sorted(r["seed"] for r in rows if r["scheduler"] == "RR")
    assert pf_seeds == rr_seeds


def test_run_sink_receives_the_live_ledger_the_record_cannot_carry():
    """B8's whole reason to exist (docs/wp9-plan.md §16.2): the message
    ledger is a live object RunRecord.from_summary drops, so a windowed
    metric is underivable from what record_sink sees."""
    seen = []

    def run_sink(record, axis_values, summary):
        seen.append((record, axis_values, summary))

    sweep(
        axes={"capacity_mult": [1.0]},
        build_scenario=_build_scenario,
        schedulers={"PF": ProportionalFair},
        n_seeds=2,
        run_sink=run_sink,
    )
    assert len(seen) == 2
    for record, axis_values, summary in seen:
        assert axis_values == {"capacity_mult": 1.0}
        ledger = summary["_message_ledger"]
        assert isinstance(ledger, MessageLedger)
        # The point of the sink: per-message generation timestamps, which a
        # window can select on. The record carries only whole-run
        # percentiles derived from these.
        for c in ledger.completions():
            assert isinstance(c.message.generation_ts_s, float)
        assert "_message_ledger" not in record.to_dict()


def test_run_sink_runs_before_record_sink():
    """Ordering is deliberate -- a record sink strips/projects/persists the
    record, and must not be able to change what the run sink observed."""
    order = []
    sweep(
        axes={"capacity_mult": [1.0]},
        build_scenario=_build_scenario,
        schedulers={"PF": ProportionalFair},
        n_seeds=1,
        run_sink=lambda rec, av, summary: order.append("run"),
        record_sink=lambda rec, av: order.append("record"),
    )
    assert order == ["run", "record"]


def test_run_sink_is_optional_and_record_sink_keeps_its_arity():
    """Purely additive: a pre-B8 caller passing only a two-argument
    record_sink must be untouched -- the reason this is a second parameter
    rather than a widened record_sink."""
    seen = []
    rows = sweep(
        axes={"capacity_mult": [1.0]},
        build_scenario=_build_scenario,
        schedulers={"PF": ProportionalFair},
        n_seeds=2,
        record_sink=lambda rec, av: seen.append((rec, av)),
    )
    assert len(seen) == 2
    assert len(rows) == 2


def test_write_csv_roundtrips(tmp_path):
    rows = sweep(
        axes={"capacity_mult": [1.0]},
        build_scenario=_build_scenario,
        schedulers={"PF": ProportionalFair},
        n_seeds=2,
    )
    out = tmp_path / "sweep.csv"
    write_csv(rows, str(out))
    assert out.exists()
    import csv as csv_mod
    with open(out) as f:
        read_rows = list(csv_mod.DictReader(f))
    assert len(read_rows) == len(rows)


def test_bootstrap_ci_contains_the_point_estimate():
    ci = bootstrap_ci([1.0, 2.0, 3.0, 4.0, 5.0], n_boot=500, seed=0)
    assert ci["lo"] <= ci["point"] <= ci["hi"]
    assert ci["n"] == 5


def test_bootstrap_ci_empty_input():
    ci = bootstrap_ci([], n_boot=100)
    assert ci["n"] == 0


def test_aggregate_groups_and_drops_non_numeric():
    rows = [
        {"cell": "a", "scheduler": "PF", "M10": 100.0},
        {"cell": "a", "scheduler": "PF", "M10": 120.0},
        {"cell": "a", "scheduler": "PF", "M10": None},  # pending metric, must be dropped not zeroed
        {"cell": "b", "scheduler": "PF", "M10": 50.0},
    ]
    agg = aggregate(rows, group_keys=["cell", "scheduler"], value_key="M10", n_boot=200)
    by_cell = {a["cell"]: a for a in agg}
    assert by_cell["a"]["n"] == 2
    assert by_cell["a"]["n_dropped_non_numeric"] == 1
    assert by_cell["a"]["point"] == pytest.approx(110.0)
    assert by_cell["b"]["point"] == pytest.approx(50.0)


def test_check_contiguity_flags_isolated_winner():
    axes = {"n": [1, 2, 3, 4, 5]}
    # TwoTier wins only at n=3, surrounded by PF on both sides -> isolated.
    winners = {(1,): "PF", (2,): "PF", (3,): "TwoTier", (4,): "PF", (5,): "PF"}
    isolated = check_contiguity(winners, axes)
    assert isolated[(3,)] is True
    assert isolated[(1,)] is False  # PF at (1,) agrees with PF at (2,)


def test_check_contiguity_accepts_a_contiguous_boundary():
    axes = {"n": [1, 2, 3, 4, 5]}
    # TwoTier wins at n>=3 -- a genuine contiguous boundary.
    winners = {(1,): "PF", (2,): "PF", (3,): "TwoTier", (4,): "TwoTier", (5,): "TwoTier"}
    isolated = check_contiguity(winners, axes)
    assert isolated[(3,)] is False  # agrees with (4,)
    assert isolated[(4,)] is False  # agrees with (3,) and (5,)
    assert isolated[(1,)] is False  # agrees with (2,)


def test_check_contiguity_2d():
    axes = {"n": [1, 2, 3], "load": [0.5, 1.0]}
    winners = {
        (1, 0.5): "PF", (2, 0.5): "PF", (3, 0.5): "PF",
        (1, 1.0): "PF", (2, 1.0): "TwoTier", (3, 1.0): "PF",
    }
    isolated = check_contiguity(winners, axes)
    # (2, 1.0) neighbours: (1,1.0)=PF, (3,1.0)=PF, (2,0.5)=PF -- none agree.
    assert isolated[(2, 1.0)] is True


def test_regime_selection_excluded_both_zero():
    assert regime_selection_excluded(0.0, 0.0) is True
    assert regime_selection_excluded(0.0, 0.01) is False
    assert regime_selection_excluded(0.02, 0.01) is False
    assert regime_selection_excluded(None, 0.0) is False
