"""G1/G3/G5/G8's fast numbers, on fixed code, with both populations shown.

STUDY LAYER. config/metric_panel.yml is not edited; this reads MetricResults.

WHY BOTH POPULATIONS. Phase 1 found (verified on sweeps/wp9/stage2/
stage2_rows.csv, 7,560 rows) that M01's worst-flow contest is won by the
5QI-9 best-effort filler in 85.4 % of runs and by the 5QI-1 telemetry bearer
in 6 -- while the regime map cites "M01 p98 / M15 across the core plane" as
G1's evidence. G6 already solved this once, with M20's protected-fleet
restriction; nothing else adopted it. So every worst-flow statistic here is
reported TWICE, over all flows and over the protected fleet
(Scorecard.NON_PROTECTED_5QI = {8, 9} excluded), and the pair is the result.

G8 IS A CONJUNCTION and both halves are reported: M09 (per-1s Jain) and M22
(starvation epochs), the latter added in this pass because M09 scores a flow
delivering nothing as perfectly fair whenever its source is idle.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                              # noqa: E402
from regime_sweep import RunLedger, arm_cost, run_cells    # noqa: E402
from sim.driver import run as driver_run                   # noqa: E402
from sim.parametric import sweep_scenario                  # noqa: E402
from sim.run_record import RunRecord                       # noqa: E402
from sim.scorecard import Population, Scorecard             # noqa: E402
from g11_campaign import _arm                              # noqa: E402

SLOT_S = 0.00025
# 16 physical cores on this machine; measured efficiency 77 % at W=16 against
# 45 % at W=32 (docs/wp9-g11-plan.md §1.3). Peak RSS is 214-226 MB per record
# at the N=8 / 20,000-slot base cell, so 16 workers is ~3.6 GB -- memory does
# not bind here, only at N=32 or at soak horizons.
_DEFAULT_WORKERS = 16


def one(arm: str, seed: int, n_ues: int, horizon: int, load_mult: float) -> dict:
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=load_mult)
    t0 = time.time()
    summary = driver_run(sc, _arm(arm), cqi_delay_slots=8,
                         record_timeseries=True)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    # The population is now a required argument on the scoring layer, so
    # this script stopped hand-restricting the record and asks for the two
    # populations by name instead.
    card = Scorecard()
    full = card.score(rec, population=Population.all_flows())
    prot = card.score(rec, population=Population.protected_fleet())

    def val(scored, mid, *path):
        r = scored.get(mid)
        v = r.value if r else None
        for p in path:
            v = (v or {}).get(p) if isinstance(v, dict) else None
        return v

    return {
        "arm": arm, "seed": seed, "n_ues": n_ues, "load_mult": load_mult,
        "sim_s": horizon * SLOT_S, "wall_s": round(time.time() - t0, 1),
        # G1 -- p98 latency and jitter, BOTH populations
        "G1_M01_p98_all": val(full, "M01", "p98"),
        "G1_M01_flow_all": val(full, "M01", "flow"),
        "G1_M01_p98_prot": val(prot, "M01", "p98"),
        "G1_M01_flow_prot": val(prot, "M01", "flow"),
        "G1_M15_all": val(full, "M15", "jitter_ms"),
        "G1_M15_flow_all": val(full, "M15", "flow"),
        "G1_M15_prot": val(prot, "M15", "jitter_ms"),
        # G3 -- liveness gap: M03 is all-flow by design, M20 is the fleet
        "G3_M03_all_ms": val(full, "M03", "max_gap_ms"),
        "G3_M03_flow_all": val(full, "M03", "flow"),
        "G3_M20_prot_ms": val(full, "M20", "max_gap_ms"),
        "G3_M20_flow": val(full, "M20", "flow"),
        "G3_M20_caveats": len((full.get("M20").caveats if full.get("M20") else []) or []),
        # G5 -- PDU-set completeness and frame age
        "G5_M05_all": val(full, "M05", "fraction"),
        "G5_M05_prot": val(prot, "M05", "fraction"),
        "G5_M06_all_ms": val(full, "M06", "p95_ms"),
        # G8 -- BOTH conjuncts
        "G8_M09_worst_all": val(full, "M09", "worst"),
        "G8_M09_worst_prot": val(prot, "M09", "worst"),
        "G8_M22_epochs_all": val(full, "M22", "epochs"),
        "G8_M22_epochs_prot": val(prot, "M22", "epochs"),
        "G8_M22_longest_s": val(full, "M22", "longest_epoch_s"),
        "G8_M22_worst_flow": val(full, "M22", "worst_flow"),
    }


def _task(task: tuple) -> dict:
    """Pool entry point. Top-level and taking one plain tuple, because
    `spawn` has to pickle it (`regime_sweep.run_cells`)."""
    return one(*task)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--n-ues", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=40_000)   # 10 s at mu=2
    ap.add_argument("--load-mult", type=float, default=1.0)
    ap.add_argument("--out", default="sweeps/phase2/core_fast.json")
    ap.add_argument("--workers", type=int, default=_DEFAULT_WORKERS,
                    help="0 or 1 runs serially -- the reference path the "
                         "parallel one is checked byte-for-byte against")
    a = ap.parse_args()

    from regime_sweep import paired_seeds
    seeds = paired_seeds(a.seeds)
    arms = a.arms.split(",")
    # Task order is the serial order (seed-major, then arm) so that placing
    # each result at its own index reproduces the serial `rows` list exactly.
    # Submission order is longest-first inside run_cells; the two are
    # independent because the index travels with the result.
    tasks = [(arm, s, a.n_ues, a.horizon, a.load_mult)
             for s in seeds for arm in arms]

    # BANKED AS EACH RUN COMPLETES, not written once at the end. This runner
    # produced G1/G3/G5/G8 and had the write-at-the-end shape G12 lost a cell
    # to (docs/phase2-results.md). A resume re-enters the banked rows rather
    # than publishing only this invocation's.
    ledger = RunLedger(Path(a.out).with_suffix(".runs.jsonl"),
                       {"n_ues": a.n_ues, "horizon": a.horizon,
                        "load_mult": a.load_mult, "arms": arms},
                       ("arm", "seed"))
    done = ledger.done_keys()
    by_key = {(r["arm"], r["seed"]): r for r in ledger.banked()}
    todo = [(i, t) for i, t in enumerate(tasks) if (t[0], t[1]) not in done]
    if by_key:
        print(f"  {ledger.summary()}; {len(todo)} still to run", flush=True)

    rows: list[dict] = [None] * len(tasks)          # type: ignore[list-item]
    for i, t in enumerate(tasks):
        if (t[0], t[1]) in by_key:
            rows[i] = by_key[(t[0], t[1])]
    idx_map = [i for i, _ in todo]
    for j, row in run_cells(_task, [t for _, t in todo], a.workers,
                            cost=lambda t: arm_cost(t[0], t[2])):
        rows[idx_map[j]] = row
        ledger.bank(row)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"config": vars(a),
                                       "code_state": stamp(), "rows": rows},
                                      indent=1, default=str))

    def fmt(v, p=2):
        return "n/a" if v is None else (f"{v:.{p}f}" if isinstance(v, float) else str(v))

    print(f"\nn_ues={a.n_ues} load={a.load_mult} horizon={a.horizon} "
          f"({a.horizon*SLOT_S:.0f}s sim) seeds={a.seeds}\n")
    print("G1  M01 p98 (ms) and M15 jitter (ms) -- ALL flows vs PROTECTED fleet")
    print(f"  {'arm':<12} {'p98 all':>9} {'winner':>12} {'p98 prot':>9} {'winner':>12} {'M15 all':>9} {'M15 prot':>9}")
    for r in rows:
        print(f"  {r['arm']:<12} {fmt(r['G1_M01_p98_all']):>9} {str(r['G1_M01_flow_all']):>12} "
              f"{fmt(r['G1_M01_p98_prot']):>9} {str(r['G1_M01_flow_prot']):>12} "
              f"{fmt(r['G1_M15_all']):>9} {fmt(r['G1_M15_prot']):>9}")
    print("\nG3  liveness gap (ms) -- M03 all-flow vs M20 protected fleet")
    print(f"  {'arm':<12} {'M03 all':>9} {'winner':>12} {'M20 prot':>9} {'winner':>12} {'caveats':>8}")
    for r in rows:
        print(f"  {r['arm']:<12} {fmt(r['G3_M03_all_ms']):>9} {str(r['G3_M03_flow_all']):>12} "
              f"{fmt(r['G3_M20_prot_ms']):>9} {str(r['G3_M20_flow']):>12} {r['G3_M20_caveats']:>8}")
    print("\nG5  PDU-set completeness (>=0.99) and frame age p95 (<=67 ms)")
    print(f"  {'arm':<12} {'M05 all':>9} {'M05 prot':>9} {'M06 p95':>9}")
    for r in rows:
        print(f"  {r['arm']:<12} {fmt(r['G5_M05_all'],4):>9} {fmt(r['G5_M05_prot'],4):>9} "
              f"{fmt(r['G5_M06_all_ms']):>9}")
    print("\nG8  BOTH conjuncts -- M09 per-1s Jain (>=0.9) AND M22 starvation epochs (==0)")
    print(f"  {'arm':<12} {'Jain all':>9} {'Jain prot':>9} {'epochs all':>11} {'epochs prot':>12} {'longest s':>10} {'worst flow':>12}")
    for r in rows:
        print(f"  {r['arm']:<12} {fmt(r['G8_M09_worst_all'],4):>9} {fmt(r['G8_M09_worst_prot'],4):>9} "
              f"{str(r['G8_M22_epochs_all']):>11} {str(r['G8_M22_epochs_prot']):>12} "
              f"{fmt(r['G8_M22_longest_s']):>10} {str(r['G8_M22_worst_flow']):>12}")
    print(f"\nwall: {sum(r['wall_s'] for r in rows):.0f}s total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
