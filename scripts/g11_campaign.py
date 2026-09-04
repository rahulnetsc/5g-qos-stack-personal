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
from regime_sweep import check_for_orphans, paired_seeds
from wp9_window import (Window, windowed_flows_from_configs,
                        windowed_flows_from_record, windowed_metrics)

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
    # SCORE AND RELEASE, rather than retain. The previous version stored
    # every window's completion batch in a dict for the whole run and scored
    # after it, which silently negated commit 2's ledger eviction: measured
    # on this exact path (PF, N=4, ts="second"), retaining the batches costs
    # ~348 bytes per completion, ~10.6 GB of a ~12.5 GB run at the 7.2 M-slot
    # horizon. Scoring in the sink takes a run to ~2 GB and the affordable
    # worker count from ~1 to ~10.
    #
    # The split is exact, not an approximation: M01w/M02w/M03w/M05w/M06w/M15w
    # read only a flow's identity and contract, which the SCENARIO already
    # has; only M07w/M08w/M09w need the run's per-second arrays. Rows are
    # keyed by row["metric"] downstream, never by position.
    cfg_flows = windowed_flows_from_configs(sc.flows)

    def sink(idx: int, comps: list) -> None:
        if idx >= len(windows):
            return                     # a residual window past the partition
        for row in windowed_metrics(comps, cfg_flows, None, [windows[idx]],
                                    subsets={"all": lambda f: True},
                                    families="completion"):
            row.update(arm=arm, seed=seed, window_index=idx,
                       permutation=permutation)
            rows.append(row)
        comps.clear()                  # the batch is scored; drop it now

    summary = driver_run(
        sc, _arm(arm), cqi_delay_slots=CQI_DELAY_SLOTS,
        record_timeseries=True, timeseries_resolution="second",
        window_slots=int(WINDOW_S / SLOT_S), window_sink=sink)

    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=arm, seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})
    flows = windowed_flows_from_record(rec)

    # THE GUARD THAT MAKES THE SPLIT SAFE. The completion family was scored
    # against flows built from the scenario; the timeseries family is scored
    # against flows built from the record. If those two populations ever
    # disagree, the two halves describe different fleets and the merge is
    # silently wrong -- so compare them rather than assume (CLAUDE.md's
    # decompose-before-attributing rule, applied at the point of the join).
    cfg_keys = {f.key for f in cfg_flows}
    rec_keys = {f.key for f in flows}
    # The asymmetry is DIRECTIONAL and only one direction is an error.
    #
    # scenario-only is EXPECTED and benign: `record.flows` holds only flows
    # that produced traffic, and GT-7.1 scripts two one-shot flows late in
    # the run -- the firmware push at T+600 s and the STOP drill at
    # T+1200 s. On any horizon shorter than those they generate nothing and
    # never enter the record. Harmless here because the completion family
    # filters `if k in keys`, so a key with no completions contributes
    # nothing; a LARGER key set changes no row. (This guard raised on its
    # first run for exactly this case, which is why the direction is spelled
    # out rather than assumed.)
    #
    # record-only is an ERROR: a flow in the record that the scenario does
    # not declare means the two families really are scoring different
    # fleets, and the merge below would be silently wrong.
    if rec_keys - cfg_keys:
        raise AssertionError(
            f"{arm}/seed{seed}: the record carries flows the scenario does "
            f"not declare, so the completion and timeseries metric families "
            f"describe different populations: "
            f"record-only={sorted(rec_keys - cfg_keys)}")
    scenario_only = sorted(cfg_keys - rec_keys)

    for idx, w in enumerate(windows):
        for row in windowed_metrics([], flows, rec.timeseries_time_s, [w],
                                    subsets={"all": lambda f: True},
                                    families="timeseries"):
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
        # Emitted, not just checked: a scripted flow that generated nothing
        # is exactly the "did the mechanism fire at all" question, and it
        # must be visible in the artefact rather than only in an assertion
        # that did not fire.
        "flows_declared_but_silent": scenario_only,
    }


# ------------------------------------------------------- aggregate watchdog

class AggregateMemoryGuard(threading.Thread):
    """Watches TOTAL RSS across the worker pool, not any one process.

    #14: a per-process threshold cannot fire against machine-level
    exhaustion, because no single worker gets near it. Kills the largest
    worker by PID -- `pkill -f` misses multiprocessing SPAWN workers, whose
    argv is the bootstrap.
    """

    def __init__(self, budget_mb: int, log: Path, poll_s: float = 15.0,
                 min_avail_mb: int = 2_000):
        super().__init__(daemon=True)
        self.budget_mb, self.log, self.poll_s = budget_mb, log, poll_s
        self.min_avail_mb = min_avail_mb
        self.stop_flag = threading.Event()
        self.tripped = False
        self.victims: list[int] = []

    # The spawn bootstrap's argv. multiprocessing spawn workers do NOT carry
    # the script name -- which is why `pkill -f g11_campaign` misses them --
    # so this is what identifies one.
    _SPAWN_ARGV = "from multiprocessing.spawn import spawn_main"

    def _workers(self) -> list[tuple[int, int, bool]]:
        """EVERY spawn worker on this machine, not just our own children.

        The first version filtered on `PPid: <me>`, and that is the same
        scope defect as the per-process watchdog it replaced, one level
        out: workers ORPHANED by a previous attempt are reparented to init,
        so they are invisible to a children-only scan while still consuming
        the machine's memory. Measured during the 2026-09-03 audit -- two
        orphans from a killed 2-worker attempt held 13.5 GB and starved the
        live run to 5.9 GB free, with this guard reporting the pool as
        healthy the whole time.

        Returns (pid, rss_mb, is_ours). Foreign workers are counted toward
        the machine total but are never killed -- they may belong to another
        session, and killing another job's work to protect ours is not this
        guard's decision to make.
        """
        me = os.getpid()
        out = []
        for p in Path("/proc").iterdir():
            if not p.name.isdigit():
                continue
            try:
                cmd = (p / "cmdline").read_bytes().decode("utf8", "replace")
                if self._SPAWN_ARGV not in cmd:
                    continue
                stat = (p / "status").read_text()
                rss = [l for l in stat.splitlines() if l.startswith("VmRSS")]
                if not rss:
                    continue
                ours = f"PPid:\t{me}" in stat
                out.append((int(p.name), int(rss[0].split()[1]) // 1024, ours))
            except (OSError, ValueError):
                continue
        return out

    def run(self) -> None:
        while not self.stop_flag.wait(self.poll_s):
            ws = self._workers()
            ours = [(p, m) for p, m, o in ws if o]
            total = sum(m for _, m, _ in ws)          # machine-wide
            mine = sum(m for _, m in ours)
            avail = 0
            try:
                for line in Path("/proc/meminfo").read_text().splitlines():
                    if line.startswith("MemAvailable"):
                        avail = int(line.split()[1]) // 1024
            except OSError:
                pass
            with self.log.open("a") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} workers={len(ours)}"
                         f"(+{len(ws)-len(ours)} foreign) mine_rss={mine}MB "
                         f"total_rss={total}MB avail={avail}MB\n")

            # TWO trip conditions, because an absolute budget is not enough.
            # The first version compared the pool's own total against a fixed
            # number and LOGGED MemAvailable without acting on it, so memory
            # consumed by anything else -- orphans, another session, the
            # desktop -- was invisible to the decision.
            over_budget = mine > self.budget_mb
            starved = 0 < avail < self.min_avail_mb
            if (over_budget or starved) and ours:
                pid, mb = max(ours, key=lambda x: x[1])
                why = ("our pool total %dMB exceeded budget %dMB" % (mine, self.budget_mb)
                       if over_budget else
                       "machine MemAvailable %dMB fell below floor %dMB "
                       "(total spawn RSS %dMB, of which %dMB foreign)"
                       % (avail, self.min_avail_mb, total, total - mine))
                self.tripped = True
                self.victims.append(pid)
                with self.log.open("a") as fh:
                    fh.write(f"{time.strftime('%H:%M:%S')} KILL pid={pid} "
                             f"({mb}MB) -- {why}\n")
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
    done_rows: list[dict] = []
    if done_path.exists() and not a.time_cell:
        for line in done_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                # The horizon and fleet size ARE banked (run_one's return);
                # they were simply absent from the key, so a --smoke run at
                # 400,000 slots displaced a 7,200,000-slot one.
                if (r.get("horizon_slots") != horizon
                        or r.get("n_ues") != a.n_ues):
                    continue
                done.add((r["arm"], r["seed"], r["permutation"]))
                done_rows.append(r)
    todo = [t for t in tasks if (t[0], t[1], t[4]) not in done]
    # BANKED RUNS RE-ENTER THE RESULT. Previously `results` started empty and
    # the artefact was written as `"runs": results`, so a resume published
    # ONLY that invocation's runs -- exit 0, n_runs < n_expected, and
    # g11_score.py scoring whatever survived. With ARMS_LPT longest-first the
    # subset is arm-skewed, so C1/C3/C4 would be computed per arm over a
    # self-selected slice of a within-seed paired design.
    #
    # The horizon/n_ues filter above closes the second half of the same
    # hazard: the key is (arm, seed, permutation), and `--smoke` (400,000
    # slots) shares the production `--out` default, so a smoke record used to
    # displace a real one. Records are now admitted only if their banked
    # horizon and fleet size match this invocation's.
    banked = [r for r in done_rows
              if (r["arm"], r["seed"], r["permutation"]) not in
                 {(t[0], t[1], t[4]) for t in todo}]
    with log.open("a") as fh:
        fh.write(f"resume: {len(done)} run(s) already complete, "
                 f"{len(todo)} to run\n")

    guard = AggregateMemoryGuard(a.budget_mb, mem)
    guard.start()
    t0 = time.time()
    results: list[dict] = list(banked)
    failures: list[dict] = []
    # A KILLED WORKER MUST PRODUCE A RECORDED FAILURE, NOT A GAP.
    # `imap_unordered` never yields a result for a task whose worker was
    # SIGKILLed -- no exception, no retry, and the iterator can block
    # forever. That is the guard's own failure mode being the thing it was
    # built to prevent: a run that neither completes nor reports. So each
    # task is submitted individually and collected with a TIMEOUT, and a
    # task that dies or overruns is written to the log and to a failures
    # list rather than silently vanishing from the denominator.
    #
    # The timeout is derived from the horizon, not guessed: a run is ~1
    # wall-second per 4,000 slots on the slowest arm at N=4, and 4x that
    # plus an hour is generous enough that a healthy run can never trip it.
    per_task_timeout_s = max(1800.0, horizon / 4_000.0 * 4.0 + 3600.0)
    # MEASURED AGAINST TIME SINCE THE LAST COMPLETION, not since campaign
    # start. The previous form compared elapsed-since-t0 against
    # `per_task_timeout_s * len(submitted)`: at the real horizon that is
    # 10,800 s x 30 = ~90 HOURS against a ~5.7 h makespan, so the only escape
    # from the collection loop could not fire inside the run it protects. A
    # worker killed by the guard -- which has already happened once on a
    # real-horizon probe -- left the parent sleeping indefinitely and the
    # campaign JSON never written. The guard's own documented failure mode
    # (docs/wp9-audit-2026-09-03.md Tier-1 #1) was live in its mitigation.
    # Refuse to launch beside an orphaned pool: its workers cannot be
    # found by script name and its memory is charged to this run.
    check_for_orphans()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        submitted = [(task, pool.apply_async(run_one, (task,))) for task in todo]
        with log.open("a") as fh:
            fh.write(f"submitted {len(submitted)} task(s); per-task timeout "
                     f"{per_task_timeout_s/60:.0f} min\n")
        done_n = 0
        remaining = list(submitted)
        last_progress_t = time.time()
        while remaining:
            progressed = False
            for entry in list(remaining):
                task, ar = entry
                if not ar.ready():
                    continue
                remaining.remove(entry)
                progressed = True
                done_n += 1
                arm, seed, _, _, perm = task
                try:
                    res = ar.get(timeout=1)
                except Exception as exc:                     # noqa: BLE001
                    fail = {"arm": arm, "seed": seed, "permutation": perm,
                            "failed": True, "error": f"{type(exc).__name__}: {exc}"}
                    failures.append(fail)
                    with log.open("a") as fh:
                        fh.write(f"  {done_n}/{len(submitted)} FAILED "
                                 f"{arm}/seed{seed}/p{perm}: {fail['error']}\n")
                    continue
                results.append(res)
                with done_path.open("a") as fh:
                    fh.write(json.dumps(res) + "\n")
                with log.open("a") as fh:
                    fh.write(f"  {done_n}/{len(submitted)} {res['arm']}/seed{res['seed']}"
                             f"/p{res['permutation']} wall={res['wall_s']}s "
                             f"rss={res['peak_rss_mb']}MB "
                             f"windows={res['n_windows']} "
                             f"elapsed={(time.time()-t0)/60:.1f}m\n")
            if progressed:
                last_progress_t = time.time()
            if remaining and not progressed:
                if time.time() - last_progress_t > per_task_timeout_s:
                    for task, _ in remaining:
                        arm, seed, _, _, perm = task
                        failures.append({"arm": arm, "seed": seed,
                                         "permutation": perm, "failed": True,
                                         "error": "never returned -- worker "
                                                  "killed, or hung past the "
                                                  f"{per_task_timeout_s/60:.0f} min "
                                                  "no-progress deadline"})
                        with log.open("a") as fh:
                            fh.write(f"  ABANDONED {arm}/seed{seed}/p{perm} "
                                     f"-- no result; guard victims="
                                     f"{guard.victims}\n")
                    break
                time.sleep(5)
        pool.terminate()
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
        "memory_guard_victims": guard.victims,
        "failed_runs": failures,
        "scripted_windows": {k: [list(x) for x in v] for k, v in
                             scripted_windows(horizon * SLOT_S).items()},
        "runs": results,
    }, indent=1))
    with log.open("a") as fh:
        fh.write(f"DONE {len(results)}/{n_real_runs} runs in "
                 f"{(time.time()-t0)/60:.1f} min; guard tripped="
                 f"{guard.tripped}; victims={guard.victims}; "
                 f"failures={len(failures)}\n")
    if len(results) != n_real_runs and not failures:
        failures.append({"arm": None, "seed": None, "permutation": None,
                         "failed": True,
                         "error": f"campaign is SHORT: {len(results)} of "
                                  f"{n_real_runs} runs present. A shortfall "
                                  f"was previously reported at exit 0 and "
                                  f"scored as if complete."})
    if failures:
        # Loud, and non-zero exit: a short campaign must not be scored as a
        # complete one. Per-run resume means re-invoking picks up only the
        # missing runs.
        with log.open("a") as fh:
            fh.write(f"INCOMPLETE: {len(failures)} run(s) failed -- "
                     f"{[(f['arm'], f['seed']) for f in failures]}. "
                     f"Re-invoke to resume; completed runs are banked.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
