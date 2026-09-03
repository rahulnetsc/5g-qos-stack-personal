"""G2's fast number: is the STOP guarantee reachable at all, and what is it?

G2 (IA_P5G_Factory_Guarantee_Test_Plan.md:96): "100 % of STOP events <= 100 ms
across all trials."

AND THE FLOW ALREADY EXISTS. sim/fleet.py:179 declares a 5QI 85 DL Delay
E-STOP on `aperiodic_event` at rate_hz 0.2, burst 40 B -- present in 3 of the
4 compositions (mixed 2, ugv_heavy 4, drone_heavy 1, sensor_dense 0). So it
has been in every stage-4, stage-5 and G12 run. What is missing is that
NOTHING SCORES IT: no metric in config/metric_panel.yml reads 5QI 85, so the
trials were generated and never counted.

THE REAL BLOCKER IS THE TRIAL COUNT, and it is arithmetic. At 0.2 Hz a cell
of 8,000 slots (2 s at mu=2) yields 0.2 * 2 * n_ues events -- under one per
run at the sweep's own horizon. "100 % of STOP events <= 100 ms across all
trials" over a denominator near zero is the empty-selection shape wearing a
guarantee, which is why this needs a long horizon or a raised rate, and why
the default below is 50 s rather than the sweep's 2 s.

THE RECORD SAID THIS WAS STRUCTURALLY UNREACHABLE. docs/wp9-regime-map.md's
G2 row: "Needs an event-triggered STOP flow and trial accumulation; no WP9
cell models it ... the reason is now STRUCTURAL, not scenario coverage."

The mechanism EXISTS. sim/traffic.py::_gen_poisson_triggered_burst is a
per-slot Bernoulli-thinned Poisson EVENT trigger -- its own docstring says
"applied here to *event* triggering instead of byte counts" -- parameterised
by rate_hz and burst_bytes. It has ZERO non-test callers: no scenario, sweep
or YAML sets traffic_kind="aperiodic_event". So G2 was blocked on
nobody having wired up a flow, not on the model's structure.

WHAT THIS SCRIPT DOES AND DOES NOT ESTABLISH. It measures the MEASUREMENT
half: do STOP events accumulate as trials, and what fraction land within the
bound. It does NOT establish that the simulator can produce a LATE stop --
that is the BSR/SR desync question (wp9-plan §19.5, §20.1) and is a separate
claim. A 100 % pass here is only informative if a miss was reachable, so the
run reports the observed maximum beside the bound rather than a bare verdict.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler.flow import FlowConfig                      # noqa: E402
from sim.driver import run as driver_run                   # noqa: E402
from sim.parametric import sweep_scenario                  # noqa: E402
from sim.run_record import RunRecord                       # noqa: E402
from g11_campaign import _arm                              # noqa: E402

# 5QI 85 is the standardised delay-critical class the test plan's STOP maps
# to; priority_for_5qi(85) = 21 and pdb_for_5qi is applied by __post_init__.
QFI_STOP = 85
STOP_BOUND_MS = 100.0            # test plan line 96, G2's own bound
SLOT_S = 0.00025                 # numerology 2


def build(seed: int, n_ues: int, horizon: int, rate_hz: float,
          burst_bytes: int, load_mult: float) -> object:
    """The sweep base cell plus ONE event-triggered STOP flow per UE."""
    base = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                          load_mult=load_mult)
    stops = [
        FlowConfig(ue_id=ue, qfi=QFI_STOP, direction="DL", flow_class="Delay",
                   traffic_kind="aperiodic_event",
                   traffic_params={"rate_hz": rate_hz,
                                   "burst_bytes": burst_bytes})
        for ue in range(1, n_ues + 1)
    ]
    return dataclasses.replace(base, flows=tuple(list(base.flows) + stops),
                               name=f"g2_stop_n{n_ues}_L{load_mult}")


def one(arm: str, seed: int, n_ues: int, horizon: int, rate_hz: float,
        burst_bytes: int, load_mult: float) -> dict:
    sc = build(seed, n_ues, horizon, rate_hz, burst_bytes, load_mult)
    t0 = time.time()
    summary = driver_run(sc, _arm(arm), cqi_delay_slots=8,
                         record_timeseries=False)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    lat: list[float] = []
    arrived = delivered = 0
    for fr in rec.flows.values():
        if fr.qfi != QFI_STOP:
            continue
        arrived += fr.bytes_arrived
        delivered += fr.bytes_delivered
        for role_ts in (fr.completion_ts_by_role_s or {}).values():
            pass
    # Per-message latency comes from the WP7 ledger, which the record exposes
    # as per-flow true percentiles; the raw per-message list is what G2 needs,
    # so pull it from the ledger directly.
    ledger = summary.get("_message_ledger")
    trials, late = [], []
    if ledger is not None:
        for comp in ledger.completions():
            if comp.message.qfi != QFI_STOP:
                continue
            if not comp.complete:
                late.append(None)      # never delivered: a miss by definition
                continue
            ms = (comp.completion_ts_s - comp.message.generation_ts_s) * 1000.0
            trials.append(ms)
    n_miss = sum(1 for t in trials if t > STOP_BOUND_MS) + len(late)
    n_total = len(trials) + len(late)
    return {
        "arm": arm, "seed": seed, "n_ues": n_ues, "load_mult": load_mult,
        "horizon_slots": horizon, "sim_s": horizon * SLOT_S,
        "wall_s": round(time.time() - t0, 1),
        "stop_bytes_arrived": arrived, "stop_bytes_delivered": delivered,
        "trials": n_total, "delivered_trials": len(trials),
        "never_delivered": len(late),
        "misses_over_bound": n_miss,
        "pass_fraction": (n_total - n_miss) / n_total if n_total else None,
        "p50_ms": statistics.median(trials) if trials else None,
        "max_ms": max(trials) if trials else None,
        "bound_ms": STOP_BOUND_MS,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n-ues", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=200_000)  # 50 s at mu=2
    ap.add_argument("--rate-hz", type=float, default=0.2)   # sim/fleet.py:180, the E-STOP's own rate
    ap.add_argument("--burst-bytes", type=int, default=40)
    ap.add_argument("--load-mult", type=float, default=1.0)
    ap.add_argument("--out", default="sweeps/phase2/g2_fast.json")
    a = ap.parse_args()

    rows = [one(arm, a.seed, a.n_ues, a.horizon, a.rate_hz, a.burst_bytes,
                a.load_mult) for arm in a.arms.split(",")]
    # EXPECTED TRIAL COUNT, DERIVED FROM THE SCHEDULE, not restated: a
    # Bernoulli-thinned Poisson at rate_hz over horizon*slot_s seconds, per
    # UE. If the observed count is far off this, the mechanism did not fire
    # as specified and no pass fraction below is meaningful.
    expected = a.rate_hz * (a.horizon * SLOT_S) * a.n_ues
    out = {"expected_trials_per_run": expected, "rows": rows,
           "config": vars(a)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str))
    print(f"expected trials/run (derived): {expected:.0f}\n")
    print(f"{'arm':<12} {'trials':>7} {'undel':>6} {'miss':>5} "
          f"{'pass':>7} {'p50 ms':>8} {'max ms':>8} {'wall':>6}")
    for r in rows:
        pf = "n/a" if r["pass_fraction"] is None else f"{r['pass_fraction']:.4f}"
        p50 = "n/a" if r["p50_ms"] is None else f"{r['p50_ms']:.2f}"
        mx = "n/a" if r["max_ms"] is None else f"{r['max_ms']:.2f}"
        print(f"{r['arm']:<12} {r['trials']:>7} {r['never_delivered']:>6} "
              f"{r['misses_over_bound']:>5} {pf:>7} {p50:>8} {mx:>8} "
              f"{r['wall_s']:>5.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
