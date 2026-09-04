"""Profile ONE representative sweep record end-to-end.

Replicates the real per-record path of scripts/wp9_sweep.py's parallel
worker exactly, in this order:

  1. sweep_scenario(N=8, factory mix, 20,000 slots)  -- scenario build
  2. driver.run(record_timeseries=True, cqi_delay_slots=8)
  3. RunRecord.from_summary
  4. _online_rows_for   -- M16 + 12 scoring variations x 2 populations
  5. _strip_timeseries(record.to_dict()) + json.dumps  -- persistence
  6. m13_projection
  7. scorecard.score() x 2 populations  -- the panel row (regime_sweep.sweep)

Phase wall-clock is measured with perf_counter; py-spy samples the whole
process for the intra-phase breakdown. Phase boundaries are also written to
a marker file so the sampled stacks can be attributed to a phase.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve()
REPO = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from sim.parametric import sweep_scenario
from sim.driver import run
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard
from scheduler import load_two_tier

import wp9_sweep as W

ARM = os.environ.get("ARM", "TwoTier")
HORIZON = int(os.environ.get("HORIZON", "20000"))
NUES = int(os.environ.get("NUES", "8"))
SEED = int(os.environ.get("SEED", "1"))

marks: list[tuple[str, float]] = []


def mark(name: str) -> None:
    marks.append((name, time.perf_counter()))


def build_sched():
    if ARM == "TwoTier":
        return load_two_tier(W._TT_CONFIG, min_rb=5)
    if ARM == "PF":
        from sim.baselines.pf import ProportionalFair
        return ProportionalFair(ewma_window_slots=200)
    from scheduler.reservation import Reservation
    return Reservation(min_rb=5)


def main() -> None:
    # Exactly a core-plane cell of stage 1: only (n_ues, load_mult) are
    # axis values; everything else comes from BASE inside _build.
    axis_values = {"n_ues": NUES, "load_mult": 1.0}
    W._HORIZON[0] = HORIZON
    dk = W._driver_kwargs(**axis_values)

    t_all0 = time.perf_counter()
    mark("scenario_build:start")
    sc = W._build(seed=SEED, **axis_values)
    mark("scenario_build:end")

    sched = build_sched()
    mark("driver_run:start")
    summary = run(sc, sched, **dk)
    mark("driver_run:end")

    mark("from_summary:start")
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=ARM, seed=SEED,
        flow_configs=sc.flows, summary=summary, arm=dict(dk),
        meta=dict(axis_values),
    )
    mark("from_summary:end")

    card = Scorecard()
    mark("online_variations:start")
    online = W._online_rows_for(card, rec, axis_values)
    mark("online_variations:end")

    mark("persist:start")
    d = W._strip_timeseries(rec.to_dict())
    blob = json.dumps({"axis_values": axis_values, "record": d})
    out = Path(os.environ.get("RECORD_OUT", "/dev/null"))
    with out.open("w") as fh:
        fh.write(blob + "\n")
    mark("persist:end")

    mark("m13_projection:start")
    m13 = W.m13_projection(rec).to_dict()
    mark("m13_projection:end")

    mark("panel_score:start")
    scores = card.score(rec, population=Population.all_flows())
    scores_prot = card.score(rec, population=Population.protected_fleet())
    mark("panel_score:end")

    t_all1 = time.perf_counter()

    phases = {}
    for i in range(0, len(marks), 2):
        name = marks[i][0].split(":")[0]
        phases[name] = marks[i + 1][1] - marks[i][1]
    total = t_all1 - t_all0
    report = {
        "arm": ARM, "n_ues": NUES, "horizon_slots": HORIZON, "seed": SEED,
        "flows": len(sc.flows),
        "total_s": total,
        "phases_s": phases,
        "phases_pct": {k: 100.0 * v / total for k, v in phases.items()},
        "accounted_pct": 100.0 * sum(phases.values()) / total,
        "n_online_rows": len(online),
        "n_panel_metrics": len(scores),
        "record_bytes": len(blob),
        "m13_bytes": len(json.dumps(m13)),
        "marks": [(n, t - t_all0) for n, t in marks],
    }
    print(json.dumps(report, indent=2))
    dest = os.environ.get("PHASE_OUT")
    if dest:
        Path(dest).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
