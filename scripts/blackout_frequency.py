"""How often does a UE's uplink go completely dark for a whole run?

FOUND IN PHASE 2. On Reservation, seed 1097657231, N=8, UE8's three UPLINK
flows delivered ZERO bytes against full arrivals for the entire 10 s run --
5QI 1 telemetry (30,000 B), 5QI 2 video (4,822,750 B, 0 of 299 frames) and
the 5QI 9 filler -- while its DL 5QI 82 command flow was unaffected. M09's
per-second Jain scored that run 0.9161 on the protected fleet: a PASS.

WHY FREQUENCY FIRST. It is pre-existing (reproduces with priorities forced
flat), so every Reservation number this project has published was measured on
a scheduler that can do this. Whether that matters depends entirely on
whether it is 1-in-3 or 1-in-100, and three seeds cannot tell those apart.

DETECTOR. A flow with bytes_arrived > 0 and bytes_delivered == 0 over the
whole run. Deliberately cruder than M22's epoch count: this is the
unambiguous end of the scale, so a hit needs no interpretation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.driver import run as driver_run            # noqa: E402
from sim.parametric import sweep_scenario           # noqa: E402
from sim.run_record import RunRecord                # noqa: E402
from g11_campaign import _arm                       # noqa: E402
from regime_sweep import (RunLedger, invocation_config, arm_cost,  # noqa: E402
                          paired_seeds, run_cells)


def one(task):
    arm, seed, n_ues, horizon, load, mfbr = task
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=load, mfbr_multiple=mfbr)
    summary = driver_run(sc, _arm(arm), cqi_delay_slots=8,
                         record_timeseries=False)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    dead = []
    for k, fr in rec.flows.items():
        if fr.bytes_arrived > 0 and fr.bytes_delivered == 0:
            dead.append({"flow": k, "qfi": fr.qfi, "direction": fr.direction,
                         "arrived": fr.bytes_arrived})
    dead_ues = sorted({int(d["flow"].split("_")[0][2:]) for d in dead})
    return {"arm": arm, "seed": seed, "n_ues": n_ues, "load_mult": load,
            "mfbr_multiple": mfbr,
            "horizon": horizon, "n_dead_flows": len(dead),
            "dead_ues": dead_ues, "dead": dead}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--n-ues", default="4,8,16")
    ap.add_argument("--horizon", type=int, default=40_000)
    ap.add_argument("--load", default="1.0")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--mfbr-multiple", type=float, default=0.0)
    ap.add_argument("--out", default="sweeps/phase2/blackout_frequency.json")
    a = ap.parse_args()

    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, n, a.horizon, load, a.mfbr_multiple)
             for arm in a.arms.split(",")
             for n in [int(x) for x in a.n_ues.split(",")]
             for load in [float(x) for x in a.load.split(",")]
             for s in seeds]
    print(f"{len(tasks)} runs: {a.arms} x N={a.n_ues} x load={a.load} "
          f"x {a.seeds} seeds, horizon {a.horizon}, mfbr_multiple={a.mfbr_multiple}", flush=True)

    # BANKED PER RUN, and submitted longest-first by run_cells, which also
    # pins worker threads and refuses to launch beside an orphaned pool.
    # This wrote its JSON only at the end -- one kill from losing the grid.
    ledger = RunLedger(Path(a.out).with_suffix(".runs.jsonl"),
                       invocation_config(a),
                       ("arm", "seed", "n_ues", "load_mult"))
    banked = {(r["arm"], r["seed"], r["n_ues"], r["load_mult"]): r
              for r in ledger.banked()}

    def _k(t):
        return (t[0], t[1], t[2], t[4])

    todo = [(i, t) for i, t in enumerate(tasks) if _k(t) not in banked]
    if banked:
        print(f"  {ledger.summary()}; {len(todo)} still to run", flush=True)
    rows: list = [None] * len(tasks)
    for i, t in enumerate(tasks):
        if _k(t) in banked:
            rows[i] = banked[_k(t)]
    idx_map = [i for i, _ in todo]
    for j, row in run_cells(one, [t for _, t in todo], a.workers,
                            cost=lambda t: arm_cost(t[0], t[2])):
        rows[idx_map[j]] = row
        ledger.bank(row)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"config": vars(a), "rows": rows},
                                      indent=1))

    print(f"\n{'arm':<12} {'N':>3} {'runs':>5} {'runs w/ a dead flow':>20} "
          f"{'rate':>7} {'dead UEs seen':>14}")
    for arm in a.arms.split(","):
        for n in [int(x) for x in a.n_ues.split(",")]:
            sel = [r for r in rows if r["arm"] == arm and r["n_ues"] == n]
            hit = [r for r in sel if r["n_dead_flows"] > 0]
            ues = sorted({u for r in hit for u in r["dead_ues"]})
            print(f"{arm:<12} {n:>3} {len(sel):>5} {len(hit):>20} "
                  f"{len(hit)/len(sel) if sel else 0:>7.2%} {str(ues):>14}")

    print("\nDIRECTION of dead flows (DL vs UL) -- the access-chain question:")
    from collections import Counter
    c = Counter((d["direction"], d["qfi"]) for r in rows for d in r["dead"])
    for (direction, qfi), k in sorted(c.items()):
        print(f"  {direction}  5QI {qfi:>3}  {k} dead-flow instances")
    if not c:
        print("  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
