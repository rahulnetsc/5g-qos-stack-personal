"""G5's campaign -- GT-3.1, GT-3.2 and GT-3.3, scored on their own clause.

    G5: ">= 99 % of PDU sets complete within PDB; frame age at MEC p95 <=
        2 frame periods (67 ms); per-feed goodput >= GFBR in every 2 s window."
    GT-3.1 adds: "and A and B telemetry unharmed."

FOUR PARTS, scored separately and never pooled -- see
`docs/g5-step0-2026-09-10.md` sec 1:

    part 1  M05  PDU sets complete    >= 99 % within 150 ms
    part 2  M06  frame age p95        <= 2 frame periods (DERIVED from fps)
    part 3  M23  windowed GFBR floor  >= 1.0 in EVERY 2 s window
    part 4  --   telemetry unharmed   the collateral population

**PART 3 IS WHY M23 EXISTS.** `M08` is a minimum over flows and a MEAN over
time, so a run-level 0.99 can contain a 2 s window at 0.2 and read as a pass.
Both are reported here, side by side, because the whole registered prediction
P-G5-a is that they disagree -- and a metric that agreed everywhere would not
have been worth adding.

**PART 3 IS ALSO CAMPAIGN-WIDE.** A run holds only five 2 s windows at the
standard horizon, so the verdict is an AND over every window in the campaign,
the same form as G3's part 2. A per-run pass rate is reported too, and labelled
as the weaker statistic it is.

**THE LOAD IS NEVER SCORED.** The lidar and the 5QI-9 background create
contention; a QoS-aware scheduler is supposed to starve the latter. Scoring
them would repeat the defect that produced G3's withdrawn row. `Population.
protected_fleet()` excludes 5QI 8/9 and the lidar is excluded by flow key here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from regime_sweep import (RunLedger, check_for_orphans,  # noqa: E402
                          invocation_config, paired_seeds, run_cells)
from code_state import stamp  # noqa: E402
from sim.driver import run as driver_run  # noqa: E402
from sim.random_access import RandomAccessConfig  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.scorecard import Population, Scorecard  # noqa: E402
from sim.srb import with_srb  # noqa: E402
from sim.scenarios.g5 import (  # noqa: E402
    CAMERA_FPS, GFBR_WINDOW_S, LOAD_STEPS, PDU_SET_COMPLETE_FRACTION,
    QFI_CAMERA, QFI_LIDAR, QFI_TELEMETRY, build_gt31_scenario,
    build_gt32_scenario, build_gt33_scenario, camera_flow_key,
    frame_age_bound_ms, telemetry_flow_keys)
from proto_arms import resolve_arm  # noqa: E402

HORIZON_SLOTS = 40_000
CQI_DELAY_SLOTS = 8
CAP = 4
#: Ranges across G10's RE-MEASURED boundaries (PF 12 / Res 6 / TwoTier 7), so
#: the axis brackets every arm's own limit rather than a round number.
UE_AXIS = (4, 6, 7, 8, 10, 12, 14, 16, 24)
SNR_AXIS = (20.0, 15.0, 10.0, 5.0, 0.0, -3.0, -6.0)
#: The fleet size the load and SNR passes hold. DERIVED from G10's TwoTier
#: boundary rather than chosen: sub-experiments that are not about fleet size
#: should sit at the size the deployment is certified for.
FIXED_N = 7

#: G3's own telemetry bounds, reused unchanged for part 4 so "unharmed" means
#: the same thing across two guarantees rather than being re-derived here.
TELEMETRY_MAX_GAP_MS = 500.0
TELEMETRY_T_LIVE_MS = 2000.0

_TASK_KEYS = ("kind", "arm", "n_ues", "seed", "load_mult", "snr_db")


def _scenario(task: dict[str, Any]):
    kind = task["kind"]
    if kind == "gt31":
        return build_gt31_scenario(
            seed=task["seed"], n_ues=task["n_ues"],
            horizon_slots=HORIZON_SLOTS)
    if kind == "gt32":
        return build_gt32_scenario(
            seed=task["seed"], load_mult=task["load_mult"],
            n_ues=task["n_ues"], horizon_slots=HORIZON_SLOTS)
    if kind == "gt33":
        return build_gt33_scenario(
            seed=task["seed"], edge_snr_db=task["snr_db"],
            n_ues=task["n_ues"], horizon_slots=HORIZON_SLOTS)
    raise ValueError(f"unknown kind {kind!r}")


def _completions(fr) -> list[float]:
    """Every fully-delivered message's completion timestamp, seconds, sorted.

    Roles are POOLED rather than one picked by name: picking would silently
    drop a sub-stream if one were ever added. Same accessor G3 uses, so
    "telemetry unharmed" is measured the same way in both guarantees.
    """
    out: list[float] = []
    for ts in (fr.completion_ts_by_role_s or {}).values():
        out += list(ts)
    return sorted(out)


def _gaps_ms(completions_s: list[float]) -> list[float]:
    return [(b - a) * 1000.0 for a, b in zip(completions_s, completions_s[1:])]


def _one(task: dict[str, Any]) -> dict[str, Any]:
    """One cell. Returns a PROJECTION -- never a RunRecord.

    The parent retains nothing live: `run_cells`' own rule, and the 25 GB
    retention stall it exists to prevent was reintroduced once inside the
    worker after being fixed in the parent.
    """
    t0 = time.time()
    sc = _scenario(task)
    sched = resolve_arm(task["arm"])
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    summ = driver_run(with_srb(sc), sched, cqi_delay_slots=CQI_DELAY_SLOTS,
                      max_sched_ues=CAP, random_access=ra,
                      record_timeseries=True)
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=task["arm"], seed=task["seed"],
        flow_configs=sc.flows, summary=summ, arm={}, meta={})

    res = Scorecard().score(rec, population=Population.protected_fleet(),
                            only=["M05", "M06", "M08", "M17", "M23"])
    cam_key = camera_flow_key(sc)
    cam = rec.flows.get(cam_key)

    # --- parts 1-3, on the INSTRUMENT camera alone ----------------------
    # M05/M06/M23 report the WORST flow in the population, which is not the
    # same question as "did Asset A's camera meet its bound" -- the fleet axis
    # would otherwise move the statistic as well as the load. Both are kept:
    # the instrument's own value decides the part, the worst-flow value is
    # reported beside it.
    def _flow_stat(fr, name):
        return None if fr is None else getattr(fr, name, None)

    m05 = res["M05"].value or {}
    m06 = res["M06"].value or {}
    m08 = res["M08"].value or {}
    m23 = res["M23"].value or {}
    m17 = res["M17"].value or {}

    age_bound = frame_age_bound_ms(CAMERA_FPS)
    cam_p95 = _flow_stat(cam, "delay_p95_ms")
    cam_msgs = _flow_stat(cam, "message_count")

    # Part 1: instrument-side completeness. Derived from the camera's own
    # frames rather than from M05's worst-flow pick.
    arrived = _flow_stat(cam, "bytes_arrived") or 0
    dropped = _flow_stat(cam, "bytes_dropped_pdb") or 0
    late = _flow_stat(cam, "bytes_delivered_late_pdb") or 0
    complete_frac = (
        None if arrived <= 0 else max(0.0, 1.0 - (dropped + late) / arrived))

    # Part 3: the instrument's own worst window, recomputed here because M23
    # reports the worst flow in the population, not the named instrument.
    inst_window = _instrument_window_floor(rec, cam_key)

    # --- part 4, the COLLATERAL population -------------------------------
    tele_keys = telemetry_flow_keys(sc)
    tele_gap_worst = 0.0
    tele_over_tlive = 0
    tele_silent = 0
    for k in tele_keys:
        fr = rec.flows.get(k)
        ts = _completions(fr) if fr is not None else []
        if len(ts) < 2:
            tele_silent += 1
            continue
        gaps = _gaps_ms(ts)
        tele_gap_worst = max(tele_gap_worst, max(gaps))
        tele_over_tlive += sum(1 for g in gaps if g >= TELEMETRY_T_LIVE_MS)

    row = {
        **{k: task.get(k) for k in _TASK_KEYS},
        "horizon": HORIZON_SLOTS, "cap": CAP,
        # part 1
        "cam_complete_frac": complete_frac,
        "part1_pass": bool(complete_frac is not None
                           and complete_frac >= PDU_SET_COMPLETE_FRACTION),
        "m05_worst_flow": m05.get("flow"), "m05_worst": m05.get("fraction"),
        # part 2
        "cam_age_p95_ms": cam_p95, "age_bound_ms": age_bound,
        "part2_pass": bool(cam_p95 is not None and cam_p95 <= age_bound),
        "m06_worst_flow": m06.get("flow"), "m06_worst_p95": m06.get("p95_ms"),
        # part 3 -- BOTH statistics, so P-G5-a is scoreable
        "cam_window_floor": inst_window["floor"],
        "cam_window_offered_floor": inst_window.get("offered_floor"),
        "cam_window_n": inst_window["n_windows"],
        "part3_pass": bool(inst_window["floor"] is not None
                           and inst_window["floor"] >= 1.0),
        "m23_worst_flow": m23.get("flow"), "m23_worst": m23.get("fraction"),
        "m08_worst_flow": m08.get("flow"), "m08_worst": m08.get("fraction"),
        "m08_would_pass": bool(m08.get("fraction") is not None
                               and m08.get("fraction") >= 1.0),
        # part 4
        "tele_gap_worst_ms": tele_gap_worst,
        "tele_n_over_tlive": tele_over_tlive,
        "tele_silent": tele_silent,
        "part4_pass": bool(tele_silent == 0
                           and tele_gap_worst <= TELEMETRY_MAX_GAP_MS
                           and tele_over_tlive == 0),
        # context
        "cam_msgs": cam_msgs,
        "cam_gfbr_fraction": (cam.gfbr_fraction() if cam else None),
        "freeze_count": m17.get("freeze_count"),
        "effective_fps": m17.get("effective_fps"),
        "ul_mbps": summ.get("ul_throughput_bps", 0.0) / 1e6,
        "wall_s": round(time.time() - t0, 2),
    }
    return row


def _instrument_window_floor(rec: RunRecord, key: str) -> dict[str, Any]:
    """M23's statistic, for ONE named flow.

    M23 reports the worst flow in the population, which answers "did any feed
    have a bad window". The clause part is about Asset A's camera, so it is
    recomputed here for that flow alone -- same arithmetic, same discarded
    trailing partial window, different population of one.
    """
    fr = rec.flows.get(key)
    if fr is None or not rec.has_timeseries() or fr.ts_delivered_bytes is None:
        return {"floor": None, "n_windows": 0}
    time_s = rec.timeseries_time_s or []
    if len(time_s) < 2 or fr.gfbr_bps <= 0:
        return {"floor": None, "n_windows": 0}
    step = time_s[1] - time_s[0]
    per = max(1, int(round(GFBR_WINDOW_S / step)))
    n_full = len(time_s) // per
    if n_full < 1:
        return {"floor": None, "n_windows": 0}
    need = fr.gfbr_bps * GFBR_WINDOW_S / 8.0
    floor, off_floor = None, None
    for w in range(n_full):
        lo, hi = w * per, (w + 1) * per
        got = sum(fr.ts_delivered_bytes[lo:hi])
        # CAPPED AT OFFERED, for the reason in Scorecard._m23's docstring: the
        # network owes what it was handed, up to the contract. Uncapped, a run
        # that delivered every offered byte still scores a shortfall in about
        # half its windows, because the video source's frame size varies.
        offered = (sum(fr.ts_arrived_bytes[lo:hi])
                   if fr.ts_arrived_bytes is not None else need)
        owed = min(offered, need)
        frac = 1.0 if owed <= 0 else got / owed
        floor = frac if floor is None else min(floor, frac)
        of = offered / need
        off_floor = of if off_floor is None else min(off_floor, of)
    return {"floor": floor, "n_windows": n_full, "offered_floor": off_floor}


def _tasks(a) -> list[dict[str, Any]]:
    arms = [s.strip() for s in a.arms.split(",") if s.strip()]
    seeds = paired_seeds(a.seeds, base_seed=a.seed_base)
    parts = [p.strip() for p in a.parts.split(",") if p.strip()]
    out: list[dict[str, Any]] = []
    for arm in arms:
        for s in seeds:
            if "A" in parts:
                for n in UE_AXIS:
                    out.append({"kind": "gt31", "arm": arm, "n_ues": n,
                                "seed": s, "load_mult": 1.0, "snr_db": 20.0})
            if "B" in parts:
                for x in LOAD_STEPS:
                    out.append({"kind": "gt32", "arm": arm, "n_ues": FIXED_N,
                                "seed": s, "load_mult": x, "snr_db": 20.0})
            if "C" in parts:
                for db in SNR_AXIS:
                    out.append({"kind": "gt33", "arm": arm, "n_ues": FIXED_N,
                                "seed": s, "load_mult": 1.0, "snr_db": db})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-base", type=int, default=0,
                    help="disjoint seed set for held-out validation; 0 is "
                         "the published sample")
    ap.add_argument("--parts", default="A,B,C",
                    help="A=GT-3.1 fleet, B=GT-3.2 ceiling, C=GT-3.3 edge")
    ap.add_argument("--workers", type=int,
                    default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--out", default="sweeps/g5-video/g5_video.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tasks = _tasks(a)
    slots = len(tasks) * HORIZON_SLOTS
    print(f"G5 video: {len(tasks)} driver runs, {slots/1e6:.1f}M slots")
    print(f"  parts {a.parts}  arms {a.arms}  seeds {a.seeds} "
          f"(base {a.seed_base})  cap {CAP}  fixed N={FIXED_N}")
    print(f"  bounds: PDU sets >= {PDU_SET_COMPLETE_FRACTION:.0%} within "
          f"150 ms; frame age p95 <= {frame_age_bound_ms(CAMERA_FPS):.2f} ms "
          f"(2 frame periods at {CAMERA_FPS:g} fps); goodput >= GFBR in EVERY "
          f"{GFBR_WINDOW_S:g} s window")
    if a.dry_run:
        return 0

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ledger = RunLedger(
        out.with_suffix(".runs.jsonl"),
        {**invocation_config(a), "horizon": HORIZON_SLOTS, "cap": CAP,
         "fixed_n": FIXED_N, "ue_axis": list(UE_AXIS),
         "snr_axis": list(SNR_AXIS), "load_steps": list(LOAD_STEPS)},
        _TASK_KEYS)
    done = ledger.done_keys()
    todo = [t for t in tasks
            if tuple(str(t[k]) for k in _TASK_KEYS) not in done]
    print(f"  {len(done)} banked, {len(todo)} to run")

    check_for_orphans()
    rows = [r for r in ledger.banked()]
    t0 = time.time()
    for i, (_, row) in enumerate(run_cells(_one, todo, a.workers), start=1):
        ledger.bank(row)
        rows.append(row)
        if i % 50 == 0 or i == len(todo):
            print(f"    ... {i}/{len(todo)} ({time.time()-t0:.0f}s)",
                  flush=True)

    # SORTED BY TASK KEY, never completion order: an artefact whose row order
    # depends on --workers is not comparable with a serial reference, and
    # verify_parallel caught exactly that on G3's runner.
    rows.sort(key=lambda r: tuple(str(r.get(k)) for k in _TASK_KEYS))
    doc = {
        "code_state": stamp(),
        "rows": rows,
        "_horizon_slots": HORIZON_SLOTS, "_cap": CAP, "_fixed_n": FIXED_N,
        "_ue_axis": list(UE_AXIS), "_snr_axis": list(SNR_AXIS),
        "_load_steps": list(LOAD_STEPS), "_seeds": a.seeds,
        "_seed_base": a.seed_base,
        "_gfbr_window_s": GFBR_WINDOW_S,
        "_age_bound_ms": frame_age_bound_ms(CAMERA_FPS),
        "_pdu_set_fraction": PDU_SET_COMPLETE_FRACTION,
        "_wall_s_this_invocation": round(time.time() - t0, 1),
        "_ran_this_invocation": len(todo),
        "_n_runs": len(rows),
    }
    out.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\nwrote {out}  ({time.time()-t0:.0f}s, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
