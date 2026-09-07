"""G10's stage-2 slice, re-run with MFBR configured.

WHY A SLICE AND NOT STAGE 2. g10_admissible.py reads load_mult == 1.0 and
BASE_SLICE {k2_slots: 2, shared_lcg: False} only -- 6 fleet sizes x 3 arms x
10 seeds = 180 runs, against stage 2's 7,560. Budgeted from measured per-run
times at the 20,000-slot horizon: ~28 min serial, ~5 min at 6 workers.

THE POINT. G10's admissible-fleet answer (PF 8 / Reservation 4 / TwoTier 4)
was located on a two-tier with BOTH of its named UL protections switched off
-- FIX-2's GBR PRB reserve and the UL service-interval floor, both gated on
has_pending_gbr, which needs mfbr_bps > 0. Configuring MFBR reversed three
other TwoTier bound verdicts. This asks whether it moves the headline.

Emits stage2_rows-compatible columns so g10_admissible.py scores it unchanged.
"""
from __future__ import annotations
import argparse, csv, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim.driver import run as driver_run                     # noqa: E402
from sim.parametric import sweep_scenario                    # noqa: E402
from sim.run_record import RunRecord                         # noqa: E402
from sim.scorecard import Population, Scorecard              # noqa: E402
from g11_campaign import _arm                                # noqa: E402
from regime_sweep import invocation_config, RunLedger, arm_cost, paired_seeds, run_cells  # noqa: E402

N_UES = (2, 4, 8, 16, 24, 32)

def one(task):
    arm, seed, n, horizon = task
    sc = sweep_scenario(seed=seed, n_ues=n, horizon_slots=horizon, load_mult=1.0)
    t = time.time()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm, seed=seed,
                                 flow_configs=sc.flows, summary=s, arm={}, meta={})
    # G10's criterion is over GBR flows, which M07/M08 already select by
    # flow_class -- but the population is stated explicitly rather than
    # defaulted, per the scoring layer's own rule.
    sc_ = Scorecard().score(rec, population=Population.protected_fleet())
    m7, m8 = sc_["M07"].value or {}, sc_["M08"].value or {}
    return {"scheduler": arm, "seed": seed, "n_ues": n, "load_mult": 1.0,
            "shared_lcg": False, "k2_slots": 2,
            "M07.met": m7.get("met"), "M07.total": m7.get("total"),
            "M08.fraction": m8.get("fraction"), "wall_s": round(time.time()-t, 1)}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="sweeps/phase2/g10_rows_mfbr.csv")
    a = ap.parse_args()
    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, n, a.horizon)
             for arm in ("PF", "Reservation", "TwoTier") for n in N_UES for s in seeds]
    # run_cells carries what this script had to learn on its own: the
    # longest-first submission with chunksize=1 (pool.map's default chunking
    # handed one worker every N=32 TwoTier cell and another every N=2 PF one,
    # worker CPU 7:55 against 4:35), plus thread pinning and the pre-launch
    # orphan check. The cost weight moves to regime_sweep.arm_cost.
    print(f"{len(tasks)} runs: 3 arms x {len(N_UES)} fleet sizes x {a.seeds} seeds, "
          f"load 1.0, horizon {a.horizon}", flush=True)
    t0 = time.time()
    # BANKED PER RUN. This produced G10's re-measured admissible fleet and
    # wrote its CSV only at the end -- one kill from losing the grid.
    ledger = RunLedger(Path(a.out).with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "n_ues": list(N_UES)},
                       ("scheduler", "seed", "n_ues"))
    banked = {(r["scheduler"], r["seed"], r["n_ues"]): r
              for r in ledger.banked()}
    todo = [(i, t) for i, t in enumerate(tasks)
            if (t[0], t[1], t[2]) not in banked]
    if banked:
        print(f"  {ledger.summary()}; {len(todo)} still to run", flush=True)
    rows: list = [None] * len(tasks)
    for i, t in enumerate(tasks):
        if (t[0], t[1], t[2]) in banked:
            rows[i] = banked[(t[0], t[1], t[2])]
    idx_map = [i for i, _ in todo]
    for j, row in run_cells(one, [t for _, t in todo], a.workers,
                            cost=lambda t: arm_cost(t[0], t[2])):
        rows[idx_map[j]] = row
        ledger.bank(row)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {a.out} ({len(rows)} rows) in {(time.time()-t0)/60:.1f} min")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
