"""G12 as a stress experiment: end of shift, everything running hard --
what breaks first, and does the safety telemetry survive?

Registered in `docs/g12-stress-experiment-2026-09-08.md`. Reuses
`g12_campaign.py`'s ramp machinery (`run_ramp`, `order_for`, the three
degeneracy assertions) rather than restating it -- this file adds the
experiment's shape, not new scoring.

WHAT IS DIFFERENT FROM THE OLD G12 RUN, and why:

  * FIXED OCCUPANCY, not a second axis. The ramp is the axis; occupancy is
    chosen once and stated. N=6 is the realistic worst case (G10's
    admissible boundary is PF 6 / Reservation 6 / TwoTier 5, so 6 is where
    the arms separate); N=4 is a comfortable control.

  * THE RAMP SCALES THE WHOLE WORKLOAD, not one aggressor -- everyone busy
    at once, which is G12's question. G7's is the aggressor question and is
    a different experiment.

  * RESOLUTION AT THE KNEE. x1.0-x1.6 in 0.1 steps, coarser outside, because
    that is where the arms separate and a boundary read off a coarse grid is
    what put G10's answer inside an unresolved 2x gap.

  * THE CONTROL IS TIE-BREAK-ONLY (`scheduler/flow.py::tie_break_term`),
    NOT `permute_flows`. Permuting the flow list moves the tie-break AND
    every first-flow-found-wins lookup (`has_gbr`, `pdb_ms`, the LCG-0
    estimate all scan `self._flows`), so an order that shifts under it does
    not say which caused it. Holding the list fixed and re-seeding only the
    tie-break isolates the one thing.

  * A BASELINE GATE, G9's shape, per ramp point -- because a point where the
    cell is already broken cannot answer "what breaks FIRST".
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from g12_campaign import (BG_QFIS, CQI_DELAY_SLOTS, HORIZON_SLOTS,  # noqa: E402
                          QFI_TELEMETRY, _arms, order_for, run_ramp)
from regime_sweep import (arm_cost, invocation_config, paired_seeds,  # noqa: E402
                          RunLedger, run_cells)

#: The ramp. Resolution where the arms separate; the endpoints are the
#: re-based origin (x0.5, the largest origin the deployed cap sustains) and
#: x2.0.
RAMP: tuple[float, ...] = (0.5, 0.75, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0)

#: Occupancy, FIXED and stated. See the module docstring for why 6 and 4.
CELLS: tuple[tuple[str, int], ...] = (("mixed", 6), ("mixed", 4))

#: The specified degradation sequence, from the test plan: sacrifice the
#: background first, then video, and never the telemetry.
SPECIFIED_ORDER: tuple[int, ...] = (9, 4, 2)


#: The floor for "the background still has throughput". THE TEST PLAN DOES
#: NOT STATE ONE -- a specification gap, carried as such. 1 Mbps is 2 % of
#: the background's own 50 Mbps offer, and `guarantee_scorecard.py` measured
#: the verdict robust for tau anywhere in [0.01, 8] Mbps.
TAU_BPS = 1.0e6

#: `telemetry_m02` is a PDB-VIOLATION rate, so HIGH means starved. This is
#: the scorecard's own predicate, not a re-derivation: >= 0.99 of resolved
#: telemetry bytes violated their PDB.
STARVED_M02 = 0.99


def _gate(point: dict[str, Any]) -> str:
    """G9's three outcomes, per ramp point.

    CELL ALREADY BROKEN means the point cannot answer the question, and here
    that has exactly one form: **the background has stopped moving bytes.**
    Clause 4 is "telemetry never starved WHILE LOWER CLASSES STILL MOVE
    BYTES", and the degradation order is about what gets sacrificed first --
    with the background already dead, both are vacuous rather than passed.

    Deliberately NOT a gate: "every GBR class is under contract". At the top
    of the ramp that is the expected end state and is precisely what the
    experiment measures; gating on it would erase the finding. Whether the
    ramp ORIGIN is clean is a different question, asked once per ramp by
    `assert_ramp_bottom_clean` inside `order_for`.
    """
    if (point.get("bg_bps") or 0.0) < TAU_BPS:
        return "CELL ALREADY BROKEN (background below tau)"
    return "SCOREABLE"


def _clause4_verdict(points: list[dict[str, Any]]) -> str:
    """Clause 4 over ONE ramp, exactly as `guarantee_scorecard.py` scores it:

      VIOLATION     telemetry starved at some point while the background is
                    still alive -- the thing clause 4 prohibits;
      PREMISE FAILS telemetry starved and the background also dead -- the
                    cell is exhausted and the clause says nothing;
      PASS          telemetry never starved anywhere on the ramp.
    """
    starved = [p for p in points
               if (p.get("telemetry_m02") or 0.0) >= STARVED_M02]
    if not starved:
        return "PASS"
    if any((p.get("bg_bps") or 0.0) >= TAU_BPS for p in starved):
        return "VIOLATION"
    return "PREMISE FAILS"


def one(task: tuple) -> dict[str, Any]:
    comp, n_ues, arm_name, seed, tb_seed, cap = task
    factory = _arms()[arm_name]

    def armed():
        a = factory()
        a.tie_break_seed = tb_seed          # None = the control is OFF
        return a

    t0 = time.time()
    ramped = run_ramp(comp, n_ues, arm_name, armed, seed, ramp=RAMP,
                      max_sched_ues=cap)
    wall = time.time() - t0

    label = f"{comp}/N={n_ues}/{arm_name}/seed{seed}/tb={tb_seed}/cap{cap}"
    try:
        order = order_for(ramped, RAMP, label, allow_one_element=True)
        order_err = None
    except AssertionError as exc:                 # a degeneracy, not a crash
        order, order_err = None, str(exc)[:300]

    points = []
    for p in ramped["per_point"]:
        points.append({
            "mult": p["mult"], "gate": _gate(p),
            "bg_bps": p["bg_bps"], "telemetry_m02": p.get("telemetry_m02"),
            "telemetry_max_gap_ms": p.get("telemetry_max_gap_ms"),
            "worst_by_class": {str(k): v for k, v in p["worst_by_class"].items()},
        })
    return {"comp": comp, "n_ues": n_ues, "arm": arm_name, "seed": seed,
            "tie_break_seed": tb_seed, "cap": cap, "order": order, "order_error": order_err,
            "clause4": _clause4_verdict(points),
            "points": points, "wall_s": round(wall, 2)}


def _summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda r: r["seed"])
    n = len(rows)
    orders = [tuple(r["order"]["order"]) for r in rows if r["order"]]
    distinct = sorted({o for o in orders})
    per_point = []
    for i, mult in enumerate(RAMP):
        pts = [r["points"][i] for r in rows]
        m02 = [p["telemetry_m02"] for p in pts if p["telemetry_m02"] is not None]
        per_point.append({
            "mult": mult,
            "scoreable_seeds": sum(1 for p in pts if p["gate"] == "SCOREABLE"),
            "broken_seeds": sum(1 for p in pts if p["gate"].startswith("CELL")),
            "starved_seeds": sum(1 for p in pts
                                 if (p["telemetry_m02"] or 0.0) >= STARVED_M02),
            "telemetry_m02_median": statistics.median(m02) if m02 else None,
            "bg_mbps_median": round(statistics.median(
                [p["bg_bps"] for p in pts]) / 1e6, 3),
        })
    c4 = [r["clause4"] for r in rows]
    return {
        "n_seeds": n,
        "clause4": {v: c4.count(v) for v in ("PASS", "VIOLATION", "PREMISE FAILS")},
        "orders_seen": [list(o) for o in distinct],
        "order_agreement": (f"{max((orders.count(o) for o in distinct), default=0)}/{n}"
                            if orders else f"0/{n}"),
        "n_unscoreable_orders": sum(1 for r in rows if not r["order"]),
        "matches_specified": sum(1 for o in orders if list(o) == list(SPECIFIED_ORDER)),
        "per_point": per_point,
        "wall_s_total": round(sum(r["wall_s"] for r in rows), 1),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--cells", default="mixed:6,mixed:4")
    ap.add_argument("--tie-break-seeds", default="none,4243",
                    help="'none' is the control OFF (position decides ties)")
    ap.add_argument("--cap", type=int, default=4,
                    help="M-6 max_sched_ues; 4 is the deployment value, and what the G9 experiment ran at")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default="sweeps/g12-stress/g12_stress.json")
    a = ap.parse_args(argv[1:])

    arms = [x for x in a.arms.split(",") if x]
    cells = [(c.split(":")[0], int(c.split(":")[1])) for c in a.cells.split(",") if c]
    seeds = paired_seeds(a.seeds)
    tbs = [None if x == "none" else int(x) for x in a.tie_break_seeds.split(",") if x]

    tasks = [(comp, n, arm, s, tb, a.cap)
             for tb in tbs for (comp, n) in cells for arm in arms for s in seeds]
    print(f"{len(tasks)} ramp sweeps x {len(RAMP)} points = "
          f"{len(tasks) * len(RAMP)} driver runs "
          f"({len(tbs)} tie-break arms x {len(cells)} cells x {len(arms)} arms "
          f"x {len(seeds)} seeds)", flush=True)

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    ledger = RunLedger(out.with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "ramp": list(RAMP)},
                       ("comp", "n_ues", "arm", "seed", "tie_break_seed", "cap"))
    done = ledger.done_keys()
    rows: list[dict] = list(ledger.banked())
    todo = [t for t in tasks if (t[0], t[1], t[2], t[3], t[4], t[5]) not in done]
    print(f"  {len(rows)} banked, {len(todo)} to run", flush=True)

    t0 = time.time()
    for _i, r in run_cells(one, todo, a.workers, cost=lambda t: arm_cost(t[2])):
        rows.append(r); ledger.bank(r)
        if len(rows) % 10 == 0:
            print(f"    ... {len(rows)}/{len(tasks)} ({time.time()-t0:.0f}s)", flush=True)
    wall = time.time() - t0

    doc: dict[str, Any] = {
        "_ramp": list(RAMP), "_cells": [list(c) for c in cells],
        "_seeds": a.seeds, "_specified_order": list(SPECIFIED_ORDER),
        "_tie_break_seeds": [str(x) for x in tbs],
        "_cap": a.cap,
        "_wall_s": round(wall, 1), "_n_sweeps": len(rows),
        "_n_driver_runs": len(rows) * len(RAMP),
    }
    for tb in tbs:
        for (comp, n) in cells:
            for arm in arms:
                grp = [r for r in rows if r["comp"] == comp and r["n_ues"] == n
                       and r["arm"] == arm and r["tie_break_seed"] == tb]
                if grp:
                    key = f"{'tiebreak-off' if tb is None else f'tiebreak-{tb}'}/{comp}N{n}/{arm}"
                    doc[key] = _summarise(grp)
    out.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nwrote {out}  ({wall:.0f}s, {len(rows)} sweeps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
