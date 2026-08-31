"""G6 at n=40 -- the seed extension registered in `docs/wp9-plan.md` §22.1a.

Part A left TwoTier's G6 cell UNDETERMINED on all three metrics: +74.9%
(M01.p98) and +157.0% (M03.max_gap_ms) against GT-4.1's +20% bar, with
intervals containing zero at n=10. §22.1a decided to buy seeds rather than
cells, and registered the terms BEFORE this ran, because otherwise the
procedure is "sample until the interval excludes zero":

  * n = 40 total, ONE LOOK, no interim analysis and no extension;
  * same three metrics, same three arms, same paired-within-seed design,
    same `g6_verdict` read from the INTERVAL;
  * if still INCONCLUSIVE at n=40 that IS the reported result, and G6's row
    says "undetermined at n=40" rather than being resampled.

WHY ALL 40 SEEDS ARE RE-RUN RATHER THAN SPLICING IN 30 NEW ONES.
`paired_seeds` is prefix-stable (`paired_seeds(40)[:10] == paired_seeds(10)`,
verified), so seeds 0-9 are the ones stage 1 already ran. Re-running them
costs ~10 minutes and buys a REGISTERED CONTROL that nothing else in this
WP has: stage 1's own stored numbers must reproduce on those 10 seeds. A
mismatch would mean the stage-1 CSV and this runner disagree about the
scenario, which invalidates the extension before it is read -- and is
checked FIRST, in that order, for the same reason stage 2 reads contiguity
before effect sizes.

Usage:
    uv run python scripts/g6_seed_extension.py
    uv run python scripts/g6_seed_extension.py --smoke
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyse_stage6 import (ARMS, G6_BAR, G6_METRICS, _stable_seed,  # noqa: E402
                            g6_verdict, impairment_interval, load_rows,
                            paired_deltas)
from regime_sweep import bootstrap_ci, sweep, write_csv  # noqa: E402
from sim.parametric import sweep_scenario  # noqa: E402
from wp9_sweep import (BASE, PersistingRecordSink, _arms,  # noqa: E402
                        _driver_kwargs)

N_SEEDS = 40
HORIZON = 20_000
CONTROL_N = 10          # the seeds stage 1 already ran
CONTROL_TOL = 1e-9      # bit-for-bit: same scenario, same flags, same seed


def run_cells(n_seeds=N_SEEDS, horizon=HORIZON,
              records_path: Path | None = None) -> list[dict[str, Any]]:
    """`records_path` is not optional in spirit. The first version of this
    function passed no `record_sink`, so its n_seeds=40 run kept only the
    scored CSV and the per-flow completion timestamps were gone -- see
    `wp9_sweep.PersistingRecordSink`. Every caller should persist."""
    def build(seed: int, **axis_values):
        kwargs = {**BASE, **axis_values}
        kwargs.pop("min_rb", None)
        for key in ("sr_period_slots", "k2_slots"):
            kwargs.pop(key, None)
        return sweep_scenario(seed=seed, horizon_slots=horizon, **kwargs)

    if records_path is None:
        return sweep(axes={"bg": [False, True]}, build_scenario=build,
                     schedulers=_arms(), n_seeds=n_seeds,
                     driver_kwargs=_driver_kwargs)
    with PersistingRecordSink(records_path) as sink:
        rows = sweep(axes={"bg": [False, True]}, build_scenario=build,
                     schedulers=_arms(), n_seeds=n_seeds,
                     driver_kwargs=_driver_kwargs, record_sink=sink)
        print(f"  persisted {sink.n} records to {records_path}")
    return rows


def control_vs_stage1(rows: list[dict[str, Any]], stage1_csv: Path) -> bool:
    """READ FIRST. The 10 seeds stage 1 already ran must reproduce."""
    print("=" * 78)
    print("CONTROL, read before any effect size: do stage 1's own 10 seeds "
          "reproduce?")
    print("=" * 78)
    if not stage1_csv.exists():
        print(f"  stage-1 CSV absent ({stage1_csv}) -- control CANNOT be run, "
              f"and this is reported as unverified, not as a pass.")
        return False
    old = load_rows(stage1_csv)
    old_bg = {(r["scheduler"], r["seed"]): r
              for r in old if r.get("bg") is True}
    new_bg = {(r["scheduler"], r["seed"]): r
              for r in rows if r.get("bg") is True}
    shared = sorted(set(old_bg) & set(new_bg))
    if not shared:
        print("  NO SHARED (arm, seed) PAIRS -- the control cannot fire, so it "
              "proves nothing. Not a pass.")
        return False
    worst = 0.0
    worst_at = None
    for key in shared:
        for metric in G6_METRICS:
            a, b = old_bg[key].get(metric), new_bg[key].get(metric)
            if a is None or b is None:
                continue
            d = abs(float(a) - float(b))
            if d > worst:
                worst, worst_at = d, (key, metric, a, b)
    ok = worst <= CONTROL_TOL
    print(f"  {len(shared)} shared (arm, seed) pairs, {len(G6_METRICS)} metrics")
    print(f"  worst absolute difference: {worst:.3e}"
          + (f"   at {worst_at[0]} / {worst_at[1]}: "
             f"{worst_at[2]} vs {worst_at[3]}" if worst_at and not ok else ""))
    print(f"  -> {'PASS' if ok else 'FAIL'}"
          + ("" if ok else "  -- the extension is NOT read; the runner and "
                           "stage 1 disagree about the scenario."))
    return ok


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = [r for r in rows if r.get("bg") is False]
    exc = [r for r in rows if r.get("bg") is True]
    n_arms, out = len(ARMS), {"n_seeds": N_SEEDS, "bar": G6_BAR, "arms": {}}
    for cell, label in ((base, "bg=False"), (exc, "bg=True")):
        if len(cell) != n_arms * N_SEEDS:
            raise AssertionError(
                f"cell {label}: {len(cell)} rows, expected {n_arms * N_SEEDS}")
    print("\n" + "=" * 78)
    print(f"G6 at n={N_SEEDS} -- ONE LOOK, as registered in §22.1a")
    print("=" * 78)
    for arm in ARMS:
        print(f"\n  {arm}")
        out["arms"][arm] = {}
        for metric in G6_METRICS:
            deltas = paired_deltas(base, exc, arm, metric, relative=True)
            if not deltas:
                print(f"    {metric:18s}  (no paired samples)")
                continue
            ci = bootstrap_ci(deltas, seed=_stable_seed(arm, metric))
            imp, lo, hi = impairment_interval(metric, ci)
            verdict = g6_verdict(lo, hi)
            dropped = N_SEEDS - len(deltas)
            warn = f"  [{dropped} seed(s) dropped]" if dropped else ""
            print(f"    {metric:18s}  impairment {imp * 100:+8.2f}%  "
                  f"[{lo * 100:+8.2f}, {hi * 100:+8.2f}]%   n={len(deltas):3d}  "
                  f"{verdict}{warn}")
            out["arms"][arm][metric] = {
                "impairment": imp, "lo": lo, "hi": hi, "verdict": verdict,
                "n_paired": len(deltas), "n_dropped": dropped,
            }
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--root", default="sweeps/wp9")
    args = ap.parse_args(argv[1:])
    root = Path(args.root)
    if args.smoke:
        rows = run_cells(n_seeds=2, horizon=2000)
        print(f"smoke: {len(rows)} rows -- machinery only, NOT a result")
        return 0
    rows = run_cells(records_path=root / "stage6_g6_n40_records.jsonl")
    ok = control_vs_stage1(rows, root / "stage1" / "stage1_rows.csv")
    write_csv(rows, str(root / "stage6_g6_n40.csv"))
    summary = report(rows) if ok else {"control": "FAILED -- not read"}
    (root / "stage6_g6_n40.json").write_text(
        json.dumps({"control_passed": ok, "summary": summary},
                   indent=2, default=str))
    print(f"\nwrote {root / 'stage6_g6_n40.csv'} and .json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
