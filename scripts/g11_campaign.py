"""G11's production-shift soak (GT-7.1 + GT-7.4), run and scored per window.

`docs/wp9-g11-plan.md`. Orchestration only -- the scenario is
`sim/scenarios/g11.py`, the windowed metrics are `scripts/wp9_window.py`,
the drift statistic is `scripts/g11_drift.py`.

FOUR THINGS THIS RUNNER DOES DIFFERENTLY FROM `wp9_sweep.py::_run_resumable`,
each for a reason measured rather than assumed:

1. ONE RUN IS ONE CHECKPOINT. `_run_resumable`'s unit is a CELL -- 3 arms x
   n_seeds runs, returned only when all of them finish. For G11 that is the
   whole campaign in a single checkpoint, and a crash at hour 3 would lose
   everything. Here a completed run is written and never re-run.

2. HORIZON IS AN EXPLICIT PARAMETER, not the `_HORIZON` module global. A
   worker that forgets to set that global silently runs at 20,000 slots --
   a 360x-too-short soak that completes normally and looks like a result.

3. THE MEMORY GUARD IS AGGREGATE, not per-process. The watchdog that killed
   the earlier 7.2M-slot probe at 21.8 GiB was a PER-PROCESS threshold, and
   it worked there because that run was one process. The soak is W workers
   of ~2.8 GiB each: no individual worker approaches 22 GiB while the
   machine exhausts at ~8 concurrent runs, so a per-process guard CANNOT
   FIRE against the failure mode that actually threatens this run
   (docs/wp9-defects-log.md #14). This one watches total RSS across the
   pool and kills by PID.

4. LONGEST-PROCESSING-TIME ORDER. 30 long jobs, not thousands of short
   ones, so the makespan is bounded by the longest run: TwoTier first.

Usage:
    uv run python scripts/g11_campaign.py --time-cell        # budget probe
    uv run python scripts/g11_campaign.py --smoke            # short horizon
    uv run python scripts/g11_campaign.py --seeds 10 --workers 8
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import resource
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler import load_two_tier
from scheduler.reservation import Reservation
from sim.baselines.pf import ProportionalFair
from sim.driver import run as driver_run
from sim.run_record import RunRecord
from sim.scenarios.g11 import (SLOT_S, SOAK_HORIZON_SLOTS,
                               assert_schedule_fired, build_g11_scenario,
                               expected_counts, scripted_windows)
from regime_sweep import paired_seeds
from wp9_window import Window, windowed_flows_from_record, windowed_metrics

_TT = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")
CQI_DELAY_SLOTS = 8
WINDOW_S = 60.0
OUT = Path(__file__).resolve().parent.parent / "sweeps" / "wp9"

# LPT order: slowest arm first, so the pool's makespan is not bounded by a
# long job starting last. Measured ordering, not assumed (§7.1).
ARMS_LPT = ("TwoTier", "Reservation", "PF")


def _arm(name: str):
    if name == "PF":
        return ProportionalFair(ewma_window_slots=200)
    if name == "Reservation":
        return Reservation(min_rb=5)
    return load_two_tier(_TT, min_rb=5)


# ---------------------------------------------------------------- one run

def run_one(task: tuple) -> dict:
    arm, seed, horizon, n_ues, permutation = task
    t0 = time.time()
    sc = build_g11_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                            permutation=permutation)
    horizon_s = horizon * SLOT_S
    windows = [Window(name=f"w{k:03d}", start_s=k * WINDOW_S,
                      end_s=min((k + 1) * WINDOW_S, horizon_s))
               for k in range(int((horizon_s + WINDOW_S - 1) // WINDOW_S))]

    rows: list[dict] = []
    pending: dict[int, list] = {}

    def sink(idx: int, comps: list) -> None:
        pending[idx] = comps           # scored after the run, with the flows

    summary = driver_run(
        sc, _arm(arm), cqi_delay_slots=CQI_DELAY_SLOTS,
        record_timeseries=True, timeseries_resolution="second",
        window_slots=int(WINDOW_S / SLOT_S), window_sink=sink)

    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=arm, seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})
    flows = windowed_flows_from_record(rec)

    for idx, w in enumerate(windows):
        for row in windowed_metrics(pending.get(idx, []), flows,
                                    rec.timeseries_time_s, [w],
                                    subsets={"all": lambda f: True}):
            row.update(arm=arm, seed=seed, window_index=idx,
                       permutation=permutation)
            rows.append(row)

    sched = assert_schedule_fired(rec, horizon, f"{arm}/seed{seed}")
    return {
        "arm": arm, "seed": seed, "permutation": permutation,
        "n_ues": n_ues, "horizon_slots": horizon,
        "wall_s": round(time.time() - t0, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "n_windows": len(windows), "schedule": sched, "rows": rows,
    }


# ------------------------------------------------------- aggregate watchdog

class AggregateMemoryGuard(threading.Thread):
    """Watches TOTAL RSS across the worker pool, not any one process.

    #14: a per-process threshold cannot fire against machine-level
    exhaustion, because no single worker gets near it. Kills the largest
    worker by PID -- `pkill -f` misses multiprocessing SPAWN workers, whose
    argv is the bootstrap.
    """

    def __init__(self, budget_mb: int, log: Path, poll_s: float = 15.0):
        super().__init__(daemon=True)
        self.budget_mb, self.log, self.poll_s = budget_mb, log, poll_s
        self.stop_flag = threading.Event()
        self.tripped = False

    def _workers(self) -> list[tuple[int, int]]:
        me = os.getpid()
        out = []
        for p in Path("/proc").iterdir():
            if not p.name.isdigit():
                continue
            try:
                stat = (p / "status").read_text()
                if f"PPid:\t{me}" not in stat:
                    continue
                rss = [l for l in stat.splitlines() if l.startswith("VmRSS")]
                if rss:
                    out.append((int(p.name), int(rss[0].split()[1]) // 1024))
            except (OSError, ValueError):
                continue
        return out

    def run(self) -> None:
        while not self.stop_flag.wait(self.poll_s):
            ws = self._workers()
            total = sum(m for _, m in ws)
            avail = 0
            try:
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemAvailable"):
                        avail = int(line.split()[1]) // 1024
            except OSError:
                pass
            with self.log.open("a") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} workers={len(ws)} "
                         f"total_rss={total}MB avail={avail}MB\n")
            if total > self.budget_mb and ws:
                pid, mb = max(ws, key=lambda x: x[1])
                self.tripped = True
                with self.log.open("a") as fh:
                    fh.write(f"{time.strftime('%H:%M:%S')} KILL pid={pid} "
                             f"({mb}MB) -- pool total {total}MB exceeded "
                             f"budget {self.budget_mb}MB\n")
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass


# ------------------------------------------------------------------ driver

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--n-ues", type=int, default=4)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=SOAK_HORIZON_SLOTS)
    ap.add_argument("--budget-mb", type=int, default=20_000)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--time-cell", action="store_true",
                    help="time ONE run per arm and extrapolate the grid")
    ap.add_argument("--permutations", type=int, default=0,
                    help="extra TwoTier permutations for §9's control")
    ap.add_argument("--out", default=str(OUT / "g11_campaign.json"))
    a = ap.parse_args()

    horizon = 400_000 if a.smoke else a.horizon
    seeds = paired_seeds(a.seeds)

    tasks = [(arm, s, horizon, a.n_ues, 0) for arm in ARMS_LPT for s in seeds]
    for p in range(1, a.permutations + 1):
        tasks += [("TwoTier", s, horizon, a.n_ues, p) for s in seeds]

    # BUDGET IS DERIVED FROM THE FULL POPULATION, BEFORE any mode flag
    # narrows it -- g12_campaign.py:352's n_real_cells lesson, where the
    # extrapolation was taken after a truncation and reported 22 min for a
    # 64 min grid.
    n_real_runs = len(tasks)
    if a.time_cell:
        tasks = [t for t in tasks if t[1] == seeds[0]][:len(ARMS_LPT)]

    log = Path(str(a.out).replace(".json", ".log"))
    mem = Path(str(a.out).replace(".json", ".mem.log"))
    log.write_text(f"g11 campaign: {n_real_runs} runs "
                   f"({len(ARMS_LPT)} arms x {a.seeds} seeds"
                   f"{f' + {a.permutations} permutations' if a.permutations else ''}), "
                   f"N={a.n_ues}, horizon={horizon} "
                   f"({horizon * SLOT_S / 60:.1f} min), {a.workers} workers\n"
                   f"expected per run: {expected_counts(horizon)}\n")

    done_path = Path(str(a.out).replace(".json", ".runs.jsonl"))
    done: set[tuple] = set()
    if done_path.exists() and not a.time_cell:
        for line in done_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["arm"], r["seed"], r["permutation"]))
    todo = [t for t in tasks if (t[0], t[1], t[4]) not in done]
    with log.open("a") as fh:
        fh.write(f"resume: {len(done)} run(s) already complete, "
                 f"{len(todo)} to run\n")

    guard = AggregateMemoryGuard(a.budget_mb, mem)
    guard.start()
    t0 = time.time()
    results: list[dict] = []
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(run_one, todo), 1):
            results.append(res)
            with done_path.open("a") as fh:
                fh.write(json.dumps(res) + "\n")
            with log.open("a") as fh:
                fh.write(f"  {i}/{len(todo)} {res['arm']}/seed{res['seed']}"
                         f"/p{res['permutation']} wall={res['wall_s']}s "
                         f"rss={res['peak_rss_mb']}MB "
                         f"windows={res['n_windows']} "
                         f"elapsed={(time.time()-t0)/60:.1f}m\n")
    guard.stop_flag.set()

    if a.time_cell:
        per = {r["arm"]: r["wall_s"] for r in results}
        total_cpu = sum(per.get(arm, 0.0) for arm, *_ in tasks for _ in [0]) * 0
        total_cpu = sum(per.get(t[0], 0.0) for t in
                        [(arm, s, 0, 0, p) for arm in ARMS_LPT for s in seeds
                         for p in [0]])
        total_cpu += sum(per.get("TwoTier", 0.0) * a.seeds
                         for _ in range(a.permutations))
        with log.open("a") as fh:
            fh.write(f"\nTIMED CELL, extrapolated over the FULL "
                     f"{n_real_runs}-run population (not the timed subset):\n")
            for arm, w in per.items():
                fh.write(f"  {arm:<12} {w/60:6.1f} min/run\n")
            fh.write(f"  total CPU {total_cpu/3600:6.2f} h; at {a.workers} "
                     f"workers and 87.6% measured efficiency the LPT makespan "
                     f"is >= {total_cpu/3600/a.workers/0.876:.2f} h\n")
        print(Path(log).read_text())
        return 0

    Path(a.out).write_text(json.dumps({
        "n_runs": len(results), "n_expected": n_real_runs,
        "n_ues": a.n_ues, "horizon_slots": horizon,
        "window_s": WINDOW_S, "seeds": seeds,
        "memory_guard_tripped": guard.tripped,
        "scripted_windows": {k: [list(x) for x in v] for k, v in
                             scripted_windows(horizon * SLOT_S).items()},
        "runs": results,
    }, indent=1))
    with log.open("a") as fh:
        fh.write(f"DONE {len(results)}/{n_real_runs} runs in "
                 f"{(time.time()-t0)/60:.1f} min; guard tripped="
                 f"{guard.tripped}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
