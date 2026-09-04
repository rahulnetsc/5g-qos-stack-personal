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
import argparse, csv, multiprocessing as mp, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim.driver import run as driver_run                     # noqa: E402
from sim.parametric import sweep_scenario                    # noqa: E402
from sim.run_record import RunRecord                         # noqa: E402
from sim.scorecard import Population, Scorecard              # noqa: E402
from g11_campaign import _arm                                # noqa: E402
from regime_sweep import check_for_orphans, paired_seeds     # noqa: E402

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
    # LONGEST-PROCESSING-TIME FIRST, and chunksize=1 below. Measured cost
    # rises with n_ues and with arm (TwoTier ~2.5x PF at equal N), and
    # pool.map's DEFAULT chunking hands each worker a CONTIGUOUS block of a
    # cost-ordered list -- so one worker got the N=32 TwoTier cells and
    # another the N=2 PF ones. Measured spread on the first run: worker CPU
    # 7:55 down to 4:35, a 1.7x imbalance that made an 8.0 min run out of a
    # ~5 min serial-sum/workers estimate.
    _COST = {"PF": 1.0, "Reservation": 1.4, "TwoTier": 2.5}
    tasks.sort(key=lambda t: -(_COST[t[0]] * t[2]))
    print(f"{len(tasks)} runs: 3 arms x {len(N_UES)} fleet sizes x {a.seeds} seeds, "
          f"load 1.0, horizon {a.horizon}", flush=True)
    t0 = time.time()
    # Refuse to launch beside an orphaned pool: its workers cannot be
    # found by script name and its memory is charged to this run.
    check_for_orphans()
    with mp.get_context("spawn").Pool(a.workers) as pool:
        rows = pool.map(one, tasks, chunksize=1)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"wrote {a.out} ({len(rows)} rows) in {(time.time()-t0)/60:.1f} min")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
