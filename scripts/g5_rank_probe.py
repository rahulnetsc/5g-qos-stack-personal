"""G5's lever: the candidate-set trace, read against a CLOSED map.

`docs/g5-ranking-map.md` was registered before `scheduler/rank_trace.py`
existed. Outcomes L1-L7 (a ranking term decides) and U1-U4 (the question is
unreachable, and how) were written down in advance, so a result fitting none
of them is reported as a RESIDUAL rather than becoming an eighth candidate
after the fact. This script produces the numbers; it does not name the
outcome, and it must not be edited to make one fit.

THE CONFIGURATION IS G5's OWN, not a convenient smaller one -- n_ues=8,
horizon 40,000 slots, load_mult 1.0, cqi_delay_slots=8, record_timeseries
on: exactly what `scripts/phase2_core.py` measures G5 with. A measurement
carries its configuration, and a ranking trace taken in a different one
would be a statement about a different system.

ALL THREE ARMS, ALWAYS. The registered cross-arm reading is the part worth
protecting: if the lever is the SAME term on both QoS-aware arms it is a
property of QoS-aware ranking; if it DIFFERS per arm, then
"concentrate-vs-spread" names a shared OUTCOME produced by two mechanisms --
a description rather than a cause. A single-arm trace cannot stand in for
that, so `--arms` defaults to all three and the reading is refused below if
any is missing.

UL ONLY, and that is a property of the workload rather than a limit of the
trace: no DL flow on the parametric mix carries PDU-set structure
(`sim/traffic.py` assigns `frame_id` only in `_gen_xr_video`, and the mix's
only DL flow is qfi 82 `periodic_control`), so M05/M06 cannot see DL at all.
G5 as measured is a UL-only guarantee on this workload.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from attach_path_experiment import _stagger, STAGGER_SLOTS  # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells   # noqa: E402
from scheduler.rank_trace import LossPointTally              # noqa: E402
from sim.driver import run as driver_run                     # noqa: E402
from sim.parametric import sweep_scenario                    # noqa: E402
from sim.run_record import RunRecord                         # noqa: E402
from sim.scorecard import Population, Scorecard              # noqa: E402
from g11_campaign import _arm                                # noqa: E402

VIDEO_QFI = 2
DEFAULT_WORKERS = 16


def one(arm: str, seed: int, n_ues: int, horizon: int, load_mult: float,
        attach: bool = False) -> dict:
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=load_mult)
    # MODEL C at G5's OWN configuration -- the re-score has to be on
    # M05, the metric G5 is actually scored on, not on the M07/M08
    # proxy the consolidation uses. A check must intersect the claim.
    seed_slots = None
    if attach:
        sc, seed_slots = _stagger(sc, STAGGER_SLOTS)
    sched = _arm(arm)
    tally = LossPointTally("UL")
    # The hook is OPT-IN per instance. A scheduler built without it is the
    # object every other runner in this repo uses, unchanged.
    sched.rank_sink = tally
    t0 = time.time()
    summary = driver_run(sc, sched, cqi_delay_slots=8, record_timeseries=True,
                         attach_seed_slots=seed_slots)
    if seed_slots is not None and \
            summary["attach_seeds_fired"] != summary["attach_seeds_expected"]:
        raise SystemExit("attach seed fired %s of %s -- refusing to score"
                         % (summary["attach_seeds_fired"],
                            summary["attach_seeds_expected"]))
    tally.finish()          # RAISES if the hook saw nothing -- see rank_trace
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    card = Scorecard()
    full = card.score(rec, population=Population.all_flows())
    m05 = full.get("M05")
    m05v = m05.value if m05 else None

    # PER-FLOW completeness, not only M05's worst-flow scalar. `docs/
    # wp9-plan.md` §29's rule: a worst-flow statistic says nothing about how
    # many flows are affected, and "one chronically-broken flow" and "every
    # flow slightly broken" are the same number in it.
    per_flow = {}
    for fr in rec.flows.values():
        total = fr.frame_completions["total"]
        if not total:
            continue
        ok = sum(1 for a in fr.frame_completions["complete_ages_ms"]
                 if a <= fr.pdb_ms)
        per_flow[fr.key] = {"fraction": ok / total, "frames": total,
                            "ue_id": fr.ue_id, "qfi": fr.qfi}

    ranks = tally.mean_rank()
    return {
        "arm": arm, "seed": seed, "n_ues": n_ues, "horizon": horizon,
        "load_mult": load_mult, "wall_s": round(time.time() - t0, 1),
        "attach": attach, "seeds_fired": summary.get("attach_seeds_fired"),
        "M05_fraction": (m05v or {}).get("fraction"),
        "M05_flow": (m05v or {}).get("flow"),
        "per_flow": per_flow,
        "term_names": list(tally.term_names),
        "slots_ranked": tally.slots_seen,
        "present": {str(k): v for k, v in tally.present.items()},
        "mean_rank": {str(k): v for k, v in ranks.items()},
        "rank_hist": {str(k): {str(r): c for r, c in h.items()}
                      for k, h in tally.rank_hist.items()},
        "term_totals": tally.term_totals(),
        "losses_by_ue": {str(u): tally.losses_for(u) for u in tally.present},
        "factor_stats": {
            str(u): {n: {"n": s[0], "mean": s[1] / s[0], "min": s[2],
                         "max": s[3]}
                     for n, s in fs.items()}
            for u, fs in tally.factor_stats.items()},
    }


def _task(t: tuple) -> dict:
    return one(*t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--n-ues", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=40_000)
    ap.add_argument("--load-mult", type=float, default=1.0)
    ap.add_argument("--out", default="sweeps/phase2/g5_rank.json")
    ap.add_argument("--attach", action="store_true",
                    help="MODEL C: staggered arrival + attach BSR seed")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    a = ap.parse_args()

    arms = [x for x in a.arms.split(",") if x]
    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, a.n_ues, a.horizon, a.load_mult, a.attach)
             for arm in arms for s in seeds]
    # Derived, never restated -- the count is computed from the population
    # BEFORE any flag narrows it (`docs/wp9-plan.md`'s --time-cell defect).
    print(f"{len(tasks)} runs = {len(arms)} arms x {len(seeds)} seeds "
          f"@ n={a.n_ues}, horizon={a.horizon}, load={a.load_mult}")

    rows: list[dict] = [None] * len(tasks)          # type: ignore[list-item]
    done = 0
    for idx, r in run_cells(_task, tasks, a.workers,
                            cost=lambda t: arm_cost(t[0])):
        rows[idx] = r
        done += 1
        print(f"  [{done}/{len(tasks)}] {r['arm']:<12} seed={r['seed']} "
              f"M05={r['M05_fraction']:.4f} ({r['wall_s']}s)", flush=True)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows}, indent=1, default=str))
    print(f"\nwrote {out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
