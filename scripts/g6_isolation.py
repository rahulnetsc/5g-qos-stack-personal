"""G6's campaign -- GT-4.1 and GT-4.2, the isolation delta.

    G6: "With saturating 5QI-9 load added (either direction), every G1/G3/G5
         statistic stays within its bound and shifts by <= +20 % relative."

TWO INDEPENDENT QUESTIONS PER STATISTIC, and they can disagree:

    part A   is it still inside its OWN bound?
    part B   did it shift by more than +20 % IN THE DIRECTION OF HARM?

**This runner emits RAW statistics, never verdicts.** Part A and part B are
computed by `score()` below from the paired rows, because part B is a ratio
against the CONTROL condition and a row cannot know its own control. Keeping
the two apart also means the sign convention can be corrected without re-running
43 M slots.

THREE THINGS THE CLAUSE DOES NOT SAY AND THIS RUNNER HAS TO
(`docs/g6-step0-2026-09-11.md` sec 3):

  * **THE BOUND IS ONE-SIDED.** A statistic can IMPROVE under added load, and
    read as `|delta| <= 20 %` a run that got 30 % better would fail. Harm is
    per-metric and is read from `DIRECTION` below, never hardcoded at the
    comparison site.
  * **A RELATIVE SHIFT IS UNDEFINED ON A ZERO BASELINE.** G3's campaign-silence
    count is legitimately 0 in the control. `(x - 0) / 0` is not a 20 %
    question, so a metric declared `absolute` is scored as "must not rise".
  * **THE CONTROL DOES NOT EXIST IN ANY PUBLISHED ARTEFACT.** All three base
    scenarios already carry 5QI-9 traffic, so the condition axis includes
    `none` and two thirds of the grid is treatment.
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
from sim.scenarios.g1 import build_gt11_scenario, cmd_flow_keys  # noqa: E402
from sim.scenarios.g3 import (build_gt22_scenario,  # noqa: E402
                              telemetry_flow_keys as g3_telemetry_keys)
from sim.scenarios.g5 import (build_gt31_scenario,  # noqa: E402
                              camera_flow_key, frame_age_bound_ms,
                              telemetry_flow_keys as g5_telemetry_keys)
from sim.scenarios.g6 import (CONDITIONS, with_saturator,  # noqa: E402
                              without_background)
from g5_video import _instrument_window_floor  # noqa: E402
from proto_arms import resolve_arm  # noqa: E402

HORIZON_SLOTS = 40_000
SLOT_S = 0.00025
CQI_DELAY_SLOTS = 8
CAP = 4
#: Brackets G10's re-measured boundaries (PF 12 / Res 6 / TwoTier 7) without
#: paying for the full nine-point axis -- G6 pays for a CONDITION axis instead.
UE_AXIS = (4, 7, 12)
SHIFT_BOUND = 0.20

#: Per statistic: (harm direction, comparison). `lower_better` means a RISE is
#: harm; `absolute` means the relative form is undefined because the control
#: can legitimately read zero, so the test is "must not rise".
#: DECLARED HERE, once, rather than at each comparison site -- a sign restated
#: per metric is how a threshold silently inverts for one of them.
DIRECTION: dict[str, tuple[str, str]] = {
    "g1_cmd_p98_ms":        ("lower_better", "relative"),
    "g1_cmd_gaps_over":     ("lower_better", "absolute"),
    "g3_tele_gap_worst_ms": ("lower_better", "relative"),
    "g3_tele_over_tlive":   ("lower_better", "absolute"),
    "g3_tele_silent":       ("lower_better", "absolute"),
    "g5_cam_complete":      ("higher_better", "relative"),
    "g5_cam_age_p95_ms":    ("lower_better", "relative"),
    "g5_cam_window_floor":  ("higher_better", "relative"),
    "g5_tele_gap_worst_ms": ("lower_better", "relative"),
}

#: Each statistic's OWN bound, for part A. Inherited from the guarantee that
#: owns it; `frame_age_bound_ms()` is derived from the camera's frame rate.
BOUNDS: dict[str, tuple[str, float]] = {
    "g1_cmd_p98_ms":        ("<=", 95.0),
    "g1_cmd_gaps_over":     ("<=", 0.0),
    "g3_tele_gap_worst_ms": ("<=", 500.0),
    "g3_tele_over_tlive":   ("<=", 0.0),
    "g3_tele_silent":       ("<=", 0.0),
    "g5_cam_complete":      (">=", 0.99),
    "g5_cam_age_p95_ms":    ("<=", frame_age_bound_ms()),
    "g5_cam_window_floor":  (">=", 1.0),
    "g5_tele_gap_worst_ms": ("<=", 500.0),
}

_TASK_KEYS = ("instrument", "condition", "arm", "n_ues", "seed")


def _base(instrument: str, n_ues: int, seed: int):
    if instrument == "g1":
        return build_gt11_scenario(seed=seed, n_ues=n_ues,
                                   horizon_slots=HORIZON_SLOTS)
    if instrument == "g3":
        return build_gt22_scenario(seed=seed, n_ues=n_ues,
                                   horizon_slots=HORIZON_SLOTS)
    if instrument == "g5":
        return build_gt31_scenario(seed=seed, n_ues=n_ues,
                                   horizon_slots=HORIZON_SLOTS)
    raise ValueError(f"unknown instrument {instrument!r}")


def _condition(sc, condition: str):
    if condition == "none":
        return without_background(sc)
    if condition == "ul":
        return with_saturator(sc, direction="UL")
    if condition == "dl":
        return with_saturator(sc, direction="DL")
    raise ValueError(f"unknown condition {condition!r}")


def _completions(fr) -> list[float]:
    out: list[float] = []
    for ts in (getattr(fr, "completion_ts_by_role_s", None) or {}).values():
        out += list(ts)
    return sorted(out)


def _gap_stats(rec, keys, t_live_ms=2000.0):
    worst, over, silent = 0.0, 0, 0
    for k in keys:
        fr = rec.flows.get(k)
        ts = _completions(fr) if fr is not None else []
        if len(ts) < 2:
            silent += 1
            continue
        gaps = [(b - a) * 1000.0 for a, b in zip(ts, ts[1:])]
        worst = max(worst, max(gaps))
        over += sum(1 for g in gaps if g >= t_live_ms)
    return worst, over, silent


def _one(task: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    sc = _condition(_base(task["instrument"], task["n_ues"], task["seed"]),
                    task["condition"])
    sched = resolve_arm(task["arm"])
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    summ = driver_run(with_srb(sc), sched, cqi_delay_slots=CQI_DELAY_SLOTS,
                      max_sched_ues=CAP, random_access=ra,
                      record_timeseries=(task["instrument"] == "g5"))
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=task["arm"], seed=task["seed"],
        flow_configs=sc.flows, summary=summ, arm={}, meta={})

    row: dict[str, Any] = {**{k: task[k] for k in _TASK_KEYS},
                           "horizon": HORIZON_SLOTS, "cap": CAP}
    inst = task["instrument"]

    if inst == "g1":
        keys = cmd_flow_keys(sc)
        p98 = max((rec.flows[k].delay_p98_ms or 0.0)
                  for k in keys if k in rec.flows)
        worst, _over, _sil = _gap_stats(rec, keys)
        row["g1_cmd_p98_ms"] = p98
        # G1's own bound: a command gap of two command periods (200 ms).
        row["g1_cmd_gaps_over"] = sum(
            1 for k in keys if k in rec.flows
            for a, b in zip(_completions(rec.flows[k]),
                            _completions(rec.flows[k])[1:])
            if (b - a) * 1000.0 >= 200.0)
    elif inst == "g3":
        keys = g3_telemetry_keys(sc)
        worst, over, silent = _gap_stats(rec, keys)
        row["g3_tele_gap_worst_ms"] = worst
        row["g3_tele_over_tlive"] = over
        row["g3_tele_silent"] = silent
    else:
        res = Scorecard().score(rec, population=Population.protected_fleet(),
                                only=["M23"])
        cam = rec.flows.get(camera_flow_key(sc))
        arrived = getattr(cam, "bytes_arrived", 0) or 0
        dropped = getattr(cam, "bytes_dropped_pdb", 0) or 0
        late = getattr(cam, "bytes_delivered_late_pdb", 0) or 0
        row["g5_cam_complete"] = (
            None if arrived <= 0 else max(0.0, 1.0 - (dropped + late) / arrived))
        row["g5_cam_age_p95_ms"] = getattr(cam, "delay_p95_ms", None)
        # THE INSTRUMENT'S OWN FLOOR, not M23's worst-flow pick. M23 reports
        # the worst GBR flow in the protected population, which answers "did
        # ANY feed have a bad window"; G6's claim is about Asset A's camera.
        # Measured before this was fixed, PF at N=7 with no flood: the
        # instrument reads 1.0000 and the fleet's worst reads 0.9901, so the
        # worst-flow form failed part A on EVERY arm in EVERY condition,
        # 0 of 30 -- a criterion nothing ever passes, which is the population
        # defect this project has recorded repeatedly, not a result.
        row["g5_cam_window_floor"] = _instrument_window_floor(
            rec, camera_flow_key(sc))["floor"]
        row["g5_fleet_window_floor"] = (res["M23"].value or {}).get("fraction")
        worst, _o, _s = _gap_stats(rec, g5_telemetry_keys(sc))
        row["g5_tele_gap_worst_ms"] = worst

    row["bg_mbps"] = summ.get("ul_throughput_bps", 0.0) / 1e6
    row["wall_s"] = round(time.time() - t0, 2)
    return row


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Part A and part B, from the paired rows. See the module docstring."""
    by = {tuple(str(r[k]) for k in _TASK_KEYS): r for r in rows}
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["condition"] == "none":
            continue
        ctl_key = (str(r["instrument"]), "none", str(r["arm"]),
                   str(r["n_ues"]), str(r["seed"]))
        ctl = by.get(ctl_key)
        if ctl is None:
            continue
        for stat, (direction, comparison) in DIRECTION.items():
            if stat not in r or r.get(stat) is None:
                continue
            v, c = r[stat], ctl.get(stat)
            if c is None:
                continue
            op, bound = BOUNDS[stat]
            part_a = (v <= bound) if op == "<=" else (v >= bound)
            if comparison == "absolute":
                # The relative form is undefined when the control reads zero,
                # which it legitimately does for a breach COUNT.
                part_b = v <= c
                shift = v - c
            else:
                if c == 0:
                    part_b, shift = (v == 0), None
                else:
                    shift = (v - c) / abs(c)
                    # ONE-SIDED, in the direction of harm.
                    part_b = (shift <= SHIFT_BOUND
                              if direction == "lower_better"
                              else -shift <= SHIFT_BOUND)
            out.append({**{k: r[k] for k in _TASK_KEYS}, "stat": stat,
                        "value": v, "control": c, "shift": shift,
                        "part_a": bool(part_a), "part_b": bool(part_b)})
    return {"deltas": out}


def _tasks(a) -> list[dict[str, Any]]:
    arms = [s.strip() for s in a.arms.split(",") if s.strip()]
    seeds = paired_seeds(a.seeds, base_seed=a.seed_base)
    insts = [s.strip() for s in a.instruments.split(",") if s.strip()]
    conds = [s.strip() for s in a.conditions.split(",") if s.strip()]
    return [{"instrument": i, "condition": c, "arm": arm, "n_ues": n,
             "seed": s}
            for arm in arms for s in seeds for i in insts
            for n in UE_AXIS for c in conds]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier,ProtoGkpiD2")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--instruments", default="g1,g3,g5")
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--workers", type=int,
                    default=max(1, (os.cpu_count() or 2) - 4))
    ap.add_argument("--out", default="sweeps/g6-isolation/g6.json")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    tasks = _tasks(a)
    print(f"G6 isolation: {len(tasks)} runs, "
          f"{len(tasks)*HORIZON_SLOTS/1e6:.1f}M slots")
    print(f"  instruments {a.instruments}  conditions {a.conditions}  "
          f"arms {a.arms}  seeds {a.seeds}  N {list(UE_AXIS)}  cap {CAP}")
    print(f"  part A: each statistic within its own bound; "
          f"part B: shift <= +{SHIFT_BOUND:.0%} IN THE DIRECTION OF HARM, "
          f"absolute for zero-baseline counts")
    if a.dry_run:
        return 0

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ledger = RunLedger(out.with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "horizon": HORIZON_SLOTS,
                        "cap": CAP, "ue_axis": list(UE_AXIS)}, _TASK_KEYS)
    done = ledger.done_keys()
    todo = [t for t in tasks
            if tuple(str(t[k]) for k in _TASK_KEYS) not in done]
    print(f"  {len(done)} banked, {len(todo)} to run")

    check_for_orphans()
    rows = list(ledger.banked())
    t0 = time.time()
    for i, (_, row) in enumerate(run_cells(_one, todo, a.workers), start=1):
        ledger.bank(row)
        rows.append(row)
        if i % 100 == 0 or i == len(todo):
            print(f"    ... {i}/{len(todo)} ({time.time()-t0:.0f}s)",
                  flush=True)

    rows.sort(key=lambda r: tuple(str(r.get(k)) for k in _TASK_KEYS))
    doc = {"code_state": stamp(), "rows": rows, **score(rows),
           "_horizon_slots": HORIZON_SLOTS, "_cap": CAP,
           "_ue_axis": list(UE_AXIS), "_shift_bound": SHIFT_BOUND,
           "_direction": {k: list(v) for k, v in DIRECTION.items()},
           "_bounds": {k: list(v) for k, v in BOUNDS.items()},
           "_seeds": a.seeds, "_seed_base": a.seed_base,
           "_wall_s_this_invocation": round(time.time() - t0, 1),
           "_n_runs": len(rows)}
    out.write_text(json.dumps(doc, indent=1, default=str))
    print(f"\nwrote {out}  ({time.time()-t0:.0f}s, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
