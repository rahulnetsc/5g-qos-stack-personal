"""G4 -- prompt resume after silence (`docs/wp9-plan.md` §21.4, §23).

WHY THIS NEEDS A RUN when G6/H2/H3 did not. G4's statistic is M01 over the
POST-SILENCE message subset. `RunRecord` carries only a flow-wide
percentile, and the stored ledger field `completion_ts_by_role_s` carries
completion timestamps with no arrival times -- so a stored record can say
which message follows a silence but not how long it waited. The live
`MessageCompletion` has both (`message.generation_ts_s` and
`completion_ts_s`), and `sim/driver.py` exposes the ledger as
`summary["_message_ledger"]` for exactly this. `regime_sweep.sweep()` calls
`run_sink(record, axis_values, summary)` with the LIVE summary before any
sink strips anything, so this is a study-layer read: no panel change, no
M20, no `sim/` or `scheduler/` change.

REJECTED: reconstructing arrival times from the traffic config. Under
`_burstify` a periodic flow's arrival grid is deterministic, so it looks
recoverable -- but it holds only for `periodic_control`, not for the
`poisson` and fragmented `xr_video` flows in the same fleet, and it would
make the headline number an inference about the generator rather than a
measurement.

NO SILENCE THRESHOLD IS PICKED. Messages are bucketed by the generation gap
that PRECEDED them, and latency is reported per bucket. A fragmented flow
(xr_video) then shows two clusters -- in-burst fragments at ~0 gap and the
first fragment of each burst at ~the burst period -- and an unfragmented
flow shows one. Choosing a "this counts as silence" threshold would be
choosing where the answer comes from.

THE SIZE CONFOUND, STATED RATHER THAN ENGINEERED AROUND. `_burstify` holds
mean rate constant by stretching the period AND growing the burst by the
same 1/duty. So a duty-0.1 burst carries 10x the bytes, and its completion
latency grows with size even under instant access. Two comparisons are
therefore reported:
  * ACROSS DUTY, within an arm -- carries the confound. A size-proportional
    baseline is exactly 1/duty by construction, and it is printed beside
    the measured ratio so the excess over it is readable.
  * ACROSS ARMS, at one duty level -- confound-free, since every arm sees
    the identical message sizes. This is the scheduler-differentiating half.

Usage:
    uv run python scripts/g4_postsilence.py            # the real cells
    uv run python scripts/g4_postsilence.py --smoke    # machinery only
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import (arm_cost, bootstrap_ci,  # noqa: E402
                          paired_seeds, run_cells, sweep)
from sim.parametric import sweep_scenario  # noqa: E402
from wp9_sweep import BASE, _arms, _driver_kwargs  # noqa: E402

# Log-spaced gap buckets, in ms. Chosen from the workload's own cadences
# (33/50/100 ms base periods, stretched to 330/500/1000 ms at duty 0.1),
# not tuned to the answer.
GAP_BUCKETS_MS = (0.0, 1.0, 10.0, 100.0, 1000.0, float("inf"))
DUTY_LEVELS = (1.0, 0.5, 0.1)
N_SEEDS = 10
HORIZON = 20_000
# 16 physical cores; 77 % measured efficiency at W=16 (wp9-g11-plan §1.3).
_DEFAULT_WORKERS = 16
# Set per worker from the task -- `sweep()`'s builder takes only
# (seed, **axis_values) and horizon is neither. Same pattern as
# wp9_sweep._HORIZON.
_HORIZON = [HORIZON]


def _bucket_of(gap_ms: float) -> str:
    for lo, hi in zip(GAP_BUCKETS_MS, GAP_BUCKETS_MS[1:]):
        if lo <= gap_ms < hi:
            return f"[{lo:g},{hi:g})" if hi != float("inf") else f"[{lo:g},inf)"
    return "unbucketed"


def _p(values: list[float], frac: float) -> float:
    """Same percentile-index convention as `sim.metrics.Metrics._percentile`
    and `messages.message_latency_percentiles_ms`, so a number here is
    comparable to a panel number rather than differing by a formula."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * frac))]


def postsilence_rows(summary: dict, axis_values: dict, arm: str, seed: int
                     ) -> list[dict[str, Any]]:
    """The whole G4 read, from the live ledger. Reduces immediately -- the
    ledger itself is never retained (CLAUDE.md's 25 GB retention lesson)."""
    ledger = summary.get("_message_ledger")
    if ledger is None:
        return []
    by_flow: dict[tuple[int, int], list] = defaultdict(list)
    for comp in ledger.completions():
        by_flow[(comp.message.ue_id, comp.message.qfi)].append(comp)

    rows: list[dict[str, Any]] = []
    for (ue_id, qfi), comps in by_flow.items():
        comps.sort(key=lambda c: c.message.generation_ts_s)
        per_bucket: dict[str, list[float]] = defaultdict(list)
        sizes: dict[str, list[int]] = defaultdict(list)
        prev_ts: float | None = None
        for comp in comps:
            gen = comp.message.generation_ts_s
            # THE FIRST MESSAGE OF A FLOW IS EXCLUDED, not bucketed at gap 0.
            # It has no preceding gap at all, and calling that "followed a
            # zero-length silence" is a false claim about the one quantity
            # this instrument exists to measure. It matters: for the
            # low-cadence flows (qfi 1, 82) the first messages were the
            # ENTIRE [0,1) bucket (n=80 = 8 UEs x 10 seeds), so that cell
            # read as an in-burst measurement and was nothing of the kind.
            if prev_ts is None:
                prev_ts = gen
                continue
            gap_ms = (gen - prev_ts) * 1000.0
            prev_ts = gen
            if not comp.complete:
                continue          # a dropped message has no delivery latency
            bucket = _bucket_of(gap_ms)
            per_bucket[bucket].append((comp.completion_ts_s - gen) * 1000.0)
            sizes[bucket].append(comp.message.size_bytes)
        for bucket, lat in per_bucket.items():
            rows.append({
                **axis_values, "scheduler": arm, "seed": seed,
                "ue_id": ue_id, "qfi": qfi, "gap_bucket": bucket,
                "n": len(lat), "p50_ms": _p(lat, 0.50), "p98_ms": _p(lat, 0.98),
                "mean_size_bytes": statistics.mean(sizes[bucket]),
            })
    return rows


def _build(seed: int, **axis_values):
    """Module level so `spawn` can pickle the `sweep()` call using it."""
    kwargs = {**BASE, **axis_values}
    kwargs.pop("min_rb", None)
    for key in ("sr_period_slots", "k2_slots"):
        kwargs.pop(key, None)
    return sweep_scenario(seed=seed, horizon_slots=_HORIZON[0], **kwargs)


def _task(task: tuple) -> list[dict[str, Any]]:
    """One (duty, seed) cell: three arms, in `sweep()`'s own order.

    THE LEDGER NEVER CROSSES THE PROCESS BOUNDARY, and could not: it holds
    live `MessageCompletion` objects and is the single largest thing in a
    run. `postsilence_rows` already reduces it in the sink -- the same
    reduction the serial path did -- so what comes back is the same handful
    of per-(flow, gap-bucket) rows.
    """
    duty, seed, horizon = task
    _HORIZON[0] = horizon
    collected: list[dict[str, Any]] = []

    def sink(record, axis_values, summary):
        collected.extend(postsilence_rows(
            summary, axis_values, record.scheduler_name, record.seed))

    sweep(axes={"duty_cycle": [duty]}, build_scenario=_build,
          schedulers=_arms(), seeds=[seed], driver_kwargs=_driver_kwargs,
          run_sink=sink)
    return collected


def collect_rows(duty_levels=DUTY_LEVELS, n_seeds=N_SEEDS, horizon=HORIZON,
                 workers: int = _DEFAULT_WORKERS) -> list[dict[str, Any]]:
    seeds = paired_seeds(n_seeds)
    # Serial order is duty-major then seed then arm; placing each task's rows
    # at its own index reproduces it regardless of completion order.
    tasks = [(duty, seed, horizon)
             for duty in duty_levels for seed in seeds]
    per_task: list[list | None] = [None] * len(tasks)
    for i, rows in run_cells(_task, tasks, workers,
                             cost=lambda t: arm_cost("TwoTier", BASE["n_ues"])):
        per_task[i] = rows
    return [r for rows in per_task for r in rows]


def _cell(rows, duty, arm, bucket):
    return [r for r in rows if r["duty_cycle"] == duty
            and r["scheduler"] == arm and r["gap_bucket"] == bucket]


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    arms = sorted({r["scheduler"] for r in rows})
    buckets = [b for b in
               [f"[{lo:g},{hi:g})" if hi != float("inf") else f"[{lo:g},inf)"
                for lo, hi in zip(GAP_BUCKETS_MS, GAP_BUCKETS_MS[1:])]
               if any(r["gap_bucket"] == b for r in rows)]

    print("\n" + "=" * 78)
    print("G4 -- latency vs the SILENCE THAT PRECEDED the message (p98 ms)")
    print("=" * 78)
    print("  No silence threshold is chosen; the gap axis IS the answer.\n")
    header = f"  {'duty':>5} {'arm':<12}" + "".join(f"{b:>18}" for b in buckets)
    for duty in sorted({r["duty_cycle"] for r in rows}, reverse=True):
        print(header if duty == max(r["duty_cycle"] for r in rows) else "")
        for arm in arms:
            cells = []
            for bucket in buckets:
                sel = _cell(rows, duty, arm, bucket)
                if not sel:
                    cells.append(f"{'-':>18}")
                    continue
                p98 = statistics.mean([r["p98_ms"] for r in sel])
                size = statistics.mean([r["mean_size_bytes"] for r in sel])
                cells.append(f"{p98:>10.2f}/{size:>6.0f}B")
            print(f"  {duty:>5} {arm:<12}" + "".join(cells))
    print("\n  cells are  p98_ms / mean message size.  '-' = no message in "
          "that gap bucket.")

    out: dict[str, Any] = {"across_duty": {}, "across_arms": {}}

    print("\n" + "-" * 78)
    print("ACROSS DUTY, within an arm -- CARRIES THE SIZE CONFOUND")
    print("-" * 78)
    print("  `_burstify` grows the burst by exactly 1/duty at constant mean\n"
          "  rate, so a size-proportional latency baseline IS 1/duty. The\n"
          "  excess over that baseline is the part access delay could explain.")
    for arm in arms:
        base_sel = [r for r in rows if r["duty_cycle"] == 1.0 and r["scheduler"] == arm]
        if not base_sel:
            continue
        base_p98 = statistics.mean([r["p98_ms"] for r in base_sel])
        for duty in sorted({r["duty_cycle"] for r in rows}):
            if duty == 1.0:
                continue
            sel = [r for r in rows if r["duty_cycle"] == duty and r["scheduler"] == arm]
            if not sel:
                continue
            p98 = statistics.mean([r["p98_ms"] for r in sel])
            ratio = p98 / base_p98 if base_p98 else float("nan")
            baseline = 1.0 / duty
            print(f"  {arm:<12} duty {duty:<5} p98 {p98:8.2f} ms vs "
                  f"{base_p98:8.2f} at duty 1.0  ->  x{ratio:6.2f}   "
                  f"size baseline x{baseline:.1f}   excess x{ratio / baseline:5.2f}")
            out["across_duty"].setdefault(arm, {})[str(duty)] = {
                "p98_ms": p98, "base_p98_ms": base_p98, "ratio": ratio,
                "size_baseline": baseline, "excess_over_size": ratio / baseline,
            }

    print("\n" + "-" * 78)
    print("ACROSS ARMS at one duty level -- CONFOUND-FREE (identical sizes)")
    print("-" * 78)
    for duty in sorted({r["duty_cycle"] for r in rows}):
        print(f"\n  duty_cycle = {duty}")
        per_arm = {}
        for arm in arms:
            sel = [r for r in rows if r["duty_cycle"] == duty and r["scheduler"] == arm]
            by_seed: dict[int, list[float]] = defaultdict(list)
            for r in sel:
                by_seed[r["seed"]].append(r["p98_ms"])
            per_arm[arm] = {s: statistics.mean(v) for s, v in by_seed.items()}
            ci = bootstrap_ci(list(per_arm[arm].values()), seed=7)
            print(f"    {arm:<12} p98 {ci['point']:8.2f} ms  "
                  f"[{ci['lo']:8.2f}, {ci['hi']:8.2f}]  n={ci['n']}")
        base_arm = "PF"
        for arm in arms:
            if arm == base_arm or base_arm not in per_arm:
                continue
            shared = sorted(set(per_arm[arm]) & set(per_arm[base_arm]))
            deltas = [per_arm[arm][s] - per_arm[base_arm][s] for s in shared]
            if not deltas:
                continue
            ci = bootstrap_ci(deltas, seed=11)
            flag = "*" if (ci["lo"] > 0 or ci["hi"] < 0) else " "
            print(f"      {arm} - {base_arm}: {ci['point']:+8.2f} ms "
                  f"[{ci['lo']:+8.2f}, {ci['hi']:+8.2f}] {flag}")
            out["across_arms"].setdefault(str(duty), {})[f"{arm}-{base_arm}"] = ci
    print("\n  (* = paired bootstrap CI excludes zero)")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="tiny grid, machinery only -- NOT a result")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=_DEFAULT_WORKERS,
                    help="0 or 1 runs serially -- the reference path "
                         "scripts/verify_parallel.py checks against")
    args = ap.parse_args(argv[1:])

    # SMOKE AND REAL MUST NOT SHARE A PATH. They did, and it cost a real
    # confusion: a real run killed mid-flight by a session teardown left the
    # earlier smoke run's JSON sitting at the result path, with the right
    # name and a plausible size, looking authoritative. Same family as
    # CLAUDE.md's "an empty or unchanging output file is evidence about the
    # FILE, not the process" -- here a POPULATED file was evidence about a
    # different run. Two defences, both cheap: a distinct filename, and
    # provenance stamped inside the file so a reader who only has the JSON
    # can still tell which run produced it.
    if args.smoke:
        cfg = {"duty_levels": (1.0, 0.1), "n_seeds": 2, "horizon": 2000}
        default_out = "sweeps/wp9/stage6_g4_SMOKE.json"
    else:
        cfg = {"duty_levels": DUTY_LEVELS, "n_seeds": N_SEEDS, "horizon": HORIZON}
        default_out = "sweeps/wp9/stage6_g4.json"
    rows = collect_rows(**cfg, workers=args.workers)
    if not rows:
        raise AssertionError(
            "no post-silence rows produced -- the ledger was empty or the "
            "run_sink never fired; an empty result must not report as a null")
    summary = report(rows)
    out = Path(args.out) if args.out else Path(default_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "provenance": {
            "smoke": bool(args.smoke),
            "duty_levels": list(cfg["duty_levels"]),
            "n_seeds": cfg["n_seeds"],
            "horizon_slots": cfg["horizon"],
            "note": ("MACHINERY SMOKE TEST -- NOT A RESULT" if args.smoke
                     else "real grid"),
        },
        "rows": rows, "summary": summary}, indent=2, default=str))
    if args.smoke:
        print("\n  *** SMOKE RUN -- machinery only, NOT a result ***")
    print(f"\nwrote {out}  ({len(rows)} flow-bucket rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
