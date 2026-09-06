"""The burstiness intervention. docs/burstiness-intervention-registration.md.

Manipulation check first (did burstiness actually fall?), outcome second.
Reduces in the worker; the rank/grant streams never leave it.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                   # noqa: E402
from regime_sweep import paired_seeds, run_cells               # noqa: E402
from scheduler.two_tier import TwoTier                         # noqa: E402
from sim.driver import run as driver_run                       # noqa: E402
from sim.parametric import sweep_scenario                      # noqa: E402
from sim.resource import ResourceGrid                          # noqa: E402
from sim.run_record import RunRecord                           # noqa: E402
from sim.scorecard import Population, Scorecard                # noqa: E402
from sim.trace import GrantCollector                           # noqa: E402

ALPHAS = (0.0, 0.25, 0.5, 0.75)
K_SLOTS = 4


def one(task) -> dict:
    alpha, seed, n_ues, horizon = task
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=1.0)
    sched = TwoTier(anti_hysteresis=alpha, anti_hysteresis_slots=K_SLOTS)
    grants = GrantCollector()
    t0 = time.time()
    s = driver_run(sc, sched, cqi_delay_slots=8, record_timeseries=False,
                   grant_sink=grants)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="TwoTier",
                                 seed=seed, flow_configs=sc.flows, summary=s,
                                 arm={}, meta={})
    slot_ms = ResourceGrid(sc.carrier, sc.tdd).slot_duration_s * 1000.0

    # the protected flow that sets M01 p98, and ITS service cadence
    prot = [f for f in rec.flows.values()
            if f.direction == "UL" and f.qfi in (1, 2)]
    worst = max(prot, key=lambda f: (f.delay_p98_ms or 0.0))
    gl = [g for g in grants.finish()
          if g.direction == "UL" and g.ue_id == worst.ue_id]
    last, gaps = None, []
    for g in gl:
        for q, b in (g.split or ()):
            if q == worst.qfi and b > 0:
                if last is not None:
                    gaps.append(g.slot_index - last)
                last = g.slot_index

    def pct(xs, p):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] * slot_ms

    p50, p98 = pct(gaps, .50), pct(gaps, .98)
    card = Scorecard()
    sc_prot = card.score(rec, population=Population.protected_fleet())
    def val(m, f):
        v = sc_prot.get(m)
        v = v.value if v is not None and hasattr(v, "value") else None
        return v.get(f) if isinstance(v, dict) else v
    return {
        "alpha": alpha, "seed": seed, "wall_s": round(time.time() - t0, 1),
        "worst_flow": worst.key, "worst_ue": worst.ue_id,
        # THE MANIPULATION CHECK
        "gap_p50_ms": p50, "gap_p98_ms": p98,
        "burstiness": (p98 / p50) if (p50 and p98) else None,
        "n_services": len(gaps) + 1, "ue_ul_grants": len(gl),
        # THE OUTCOME
        "flow_p98_ms": worst.delay_p98_ms,
        "M01_p98": val("M01", "p98"), "M07_met": val("M07", "met"),
        "M13_worst": val("M13", "worst"),
        "ul_bytes_total": sum(f.bytes_delivered for f in rec.flows.values()
                              if f.direction == "UL"),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--n-ues", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    tasks = [(al, s, a.n_ues, a.horizon)
             for al in ALPHAS for s in paired_seeds(a.seeds)]
    rows = [None] * len(tasks)
    for i, r in run_cells(one, tasks, a.workers, cost=lambda t: 1.0):
        rows[i] = r
        print(f"  a={r['alpha']:<5} seed={r['seed']} burst="
              f"{(r['burstiness'] or 0):8.1f} flow_p98={r['flow_p98_ms']}",
              flush=True)
    Path(a.out).write_text(json.dumps(
        {"code_state": stamp(), "alphas": list(ALPHAS), "k_slots": K_SLOTS,
         "rows": rows}, indent=1))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
