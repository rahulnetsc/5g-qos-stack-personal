"""Regression corpus -- snapshot studies 1-3's RunRecords, and diff a later
run against the snapshot (WP0).

This is the harness every subsequent fidelity work package (WP1, WP3, WP4,
WP5, WP6, WP7, WP-Join) re-runs after landing, per the one-change-at-a-time
discipline in docs/p5g-sim-plan.md sec 5.4: capture once now (before any
fidelity work lands), then after each WP, run --check and look at exactly
what moved and by how much. A metric that was supposed to change status
(see config/metric_panel.yml) but didn't is itself a finding.

Deliberately reuses scripts/scheduler_study.py's own scenario/scheduler/
run-kwarg choices (same UL_BSR_DELAY_SLOTS, CQI_DELAY_SLOTS, same TwoTier
config) rather than re-declaring them, so this corpus can never silently
drift out of sync with what studies 1-3 actually measure.

Usage:
    uv run python scripts/regression_corpus.py --capture
    uv run python scripts/regression_corpus.py --check
    uv run python scripts/regression_corpus.py --check --rel-tol 1e-6
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.config import ScenarioConfig
from sim.driver import run
from sim.run_record import RunRecord
from sim.baselines.round_robin import RoundRobin

import scheduler_study as ss  # scripts/scheduler_study.py

DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent.parent / "regression" / "baseline_studies_1_3.json"


def _cases() -> list[dict[str, Any]]:
    """Every (study, case_label, scenario, scheduler) combination studies
    1-3 actually run, in scheduler_study.py's own terms."""
    cases: list[dict[str, Any]] = []

    # Study 1 -- overload sweep: 4 capacity multipliers x 4 scheduler variants.
    base = ss.factory_robots_scenario()
    study1_scheds: list[tuple[str, Callable]] = [
        ("PF", ss._pf),
        ("TwoTier", lambda: ss._tt()),
        ("TwoTier-nomaxmin", lambda: ss._tt(gbr_maxmin=False)),
        ("TwoTier-adaptive", lambda: ss._tt(gbr_maxmin=False, gbr_penalty_lr=1e5)),
    ]
    for mult in (1.0, 1.5, 2.0, 3.0):
        sc = ss._scale_capacity(base, mult)
        for sched_name, factory in study1_scheds:
            cases.append({
                "study": 1, "case": f"overload_mult{mult}", "scenario": sc,
                "scheduler_name": sched_name, "scheduler_factory": factory,
            })

    # Study 2 -- PDCCH-limited (sensor_dense).
    sc2 = ss.sensor_dense_scenario()
    for sched_name, factory in [("RoundRobin", RoundRobin), ("PF", ss._pf), ("TwoTier", ss._tt)]:
        cases.append({
            "study": 2, "case": "pdcch_limited", "scenario": sc2,
            "scheduler_name": sched_name, "scheduler_factory": factory,
        })

    # Study 3 -- latency-bound.
    sc3 = ss.latency_bound_scenario()
    for sched_name, factory in [("RoundRobin", RoundRobin), ("PF", ss._pf), ("TwoTier", ss._tt)]:
        cases.append({
            "study": 3, "case": "latency_bound", "scenario": sc3,
            "scheduler_name": sched_name, "scheduler_factory": factory,
        })

    return cases


def _record_id(case: dict[str, Any]) -> str:
    return f"study{case['study']}/{case['case']}/{case['scheduler_name']}"


def collect_records() -> dict[str, dict]:
    """Run every case, return {record_id: RunRecord.to_dict()}."""
    out: dict[str, dict] = {}
    for case in _cases():
        sc: ScenarioConfig = case["scenario"]
        summary = run(
            sc, case["scheduler_factory"](),
            ul_bsr_delay_slots=ss.UL_BSR_DELAY_SLOTS,
            cqi_delay_slots=ss.CQI_DELAY_SLOTS,
        )
        rec = RunRecord.from_summary(
            scenario_name=sc.name,
            scheduler_name=case["scheduler_name"],
            seed=sc.seed,
            flow_configs=sc.flows,
            summary=summary,
            arm={
                "ul_bsr_delay_slots": ss.UL_BSR_DELAY_SLOTS,
                "cqi_delay_slots": ss.CQI_DELAY_SLOTS,
            },
            meta={"study": case["study"], "case": case["case"]},
        )
        out[_record_id(case)] = rec.to_dict()
    return out


def capture(path: Path = DEFAULT_BASELINE_PATH) -> None:
    records = collect_records()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"records": records}, f, indent=2, sort_keys=True)
    print(f"Captured {len(records)} records to {path}")


# -- diffing -------------------------------------------------------------

def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _diff_value(path: str, a: Any, b: Any, rel_tol: float, abs_tol: float, out: list[str]) -> None:
    if _is_number(a) and _is_number(b):
        if abs(a - b) > max(abs_tol, rel_tol * max(abs(a), abs(b))):
            out.append(f"{path}: {a} -> {b} (delta {b - a:+.6g})")
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: MISSING in baseline -> {b.get(k)!r}")
            elif k not in b:
                out.append(f"{path}.{k}: {a.get(k)!r} -> MISSING in new run")
            else:
                _diff_value(f"{path}.{k}", a[k], b[k], rel_tol, abs_tol, out)
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} -> {len(b)}")
            return
        for i, (av, bv) in enumerate(zip(a, b)):
            _diff_value(f"{path}[{i}]", av, bv, rel_tol, abs_tol, out)
        return
    if a != b:
        out.append(f"{path}: {a!r} -> {b!r}")


def check(
    path: Path = DEFAULT_BASELINE_PATH, rel_tol: float = 1e-6, abs_tol: float = 1e-9,
) -> list[str]:
    """Re-run every case and diff against the snapshot at ``path``.
    Returns the list of mismatch descriptions (empty == clean)."""
    if not path.exists():
        raise FileNotFoundError(
            f"No baseline at {path} -- run with --capture first."
        )
    with open(path) as f:
        baseline = json.load(f)["records"]
    current = collect_records()

    mismatches: list[str] = []
    for record_id in sorted(set(baseline) | set(current)):
        if record_id not in baseline:
            mismatches.append(f"{record_id}: new case, not in baseline")
            continue
        if record_id not in current:
            mismatches.append(f"{record_id}: present in baseline, missing from current run")
            continue
        _diff_value(record_id, baseline[record_id], current[record_id], rel_tol, abs_tol, mismatches)
    return mismatches


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--capture", action="store_true", help="write a new baseline snapshot")
    p.add_argument("--check", action="store_true", help="diff current numbers against the snapshot")
    p.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    p.add_argument("--rel-tol", type=float, default=1e-6)
    p.add_argument("--abs-tol", type=float, default=1e-9)
    args = p.parse_args()

    if not args.capture and not args.check:
        p.error("pass --capture or --check")

    if args.capture:
        capture(args.baseline)

    if args.check:
        mismatches = check(args.baseline, args.rel_tol, args.abs_tol)
        if not mismatches:
            print(f"OK -- no drift beyond rel_tol={args.rel_tol}, abs_tol={args.abs_tol}")
        else:
            print(f"{len(mismatches)} mismatch(es):")
            for m in mismatches:
                print(f"  {m}")
            sys.exit(1)


if __name__ == "__main__":
    main()
