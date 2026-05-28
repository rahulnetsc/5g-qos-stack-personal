"""Compare all schedulers with and without HARQ across all scenarios.

Produces a side-by-side table for each scenario showing:
  - flat-BLER (harq=False) -- pre-HARQ baseline
  - HARQ/IR  (harq=True)   -- feature branch with incremental redundancy

Key metrics shown per flow:
  delivery_ratio, harq_retx_ratio, harq_loss_ratio, hol_p95_ms, hol_p99_ms

System metrics:
  DL/UL PRB utilization (retx PRBs are included in HARQ runs)

Usage:
    python scripts/compare_harq.py                 # all scenarios
    python scripts/compare_harq.py --scenario 1    # single scenario by index
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.driver import run
from sim.scenarios import (
    factory_robots_scenario,
    overload_scenario,
    sensor_dense_scenario,
    smoke_scenario,
    vision_scenario,
)
from sim.baselines.gradient import GradientScheduler
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin
from scheduler import TwoTier

SCHEDULERS = [
    ("RoundRobin",       lambda: RoundRobin()),
    ("ProportionalFair", lambda: ProportionalFair(ewma_window_slots=200)),
    ("Gradient",         lambda: GradientScheduler(
        ewma_window_slots=200, gbr_urgency_weight=5.0,
        delay_urgency_weight=4.0, delay_exponent=2.0,
    )),
    ("TwoTier",          lambda: TwoTier(
        tier1_period_slots=2000,
        delay_urgency_weight=4.0, delay_exponent=2.0,
    )),
]

SCENARIOS = [
    ("smoke",         smoke_scenario),
    ("overload",      overload_scenario),
    ("vision",        vision_scenario),
    ("sensor_dense",  sensor_dense_scenario),
    ("factory_robots",factory_robots_scenario),
]

# Per-flow metrics to compare
FLOW_METRICS = [
    ("delivery_ratio",   "delivery ratio",   lambda v: f"{v:.1%}"),
    ("harq_retx_ratio",  "retx ratio",       lambda v: f"{v:.1%}"),
    ("harq_loss_ratio",  "loss ratio",       lambda v: f"{v:.2%}"),
    ("throughput_bps",   "tput Mbps",        lambda v: f"{v/1e6:.2f}"),
    ("hol_p50_ms",       "p50 HoL ms",       lambda v: f"{v:.1f}"),
    ("hol_p95_ms",       "p95 HoL ms",       lambda v: f"{v:.1f}"),
    ("hol_p99_ms",       "p99 HoL ms",       lambda v: f"{v:.1f}"),
]


def _run_both(scenario_fn, scheduler_factory):
    scenario = scenario_fn()
    flat = run(scenario, scheduler_factory(), harq=False)
    scenario = scenario_fn()                 # fresh scenario, same seed
    harq = run(scenario, scheduler_factory(), harq=True)
    return flat, harq


def _print_scenario(scenario_fn, scenario_name):
    print(f"\n{'='*80}")
    print(f"SCENARIO: {scenario_name.upper()}")
    print(f"{'='*80}")

    for sched_name, sched_factory in SCHEDULERS:
        flat, harq_r = _run_both(scenario_fn, sched_factory)

        print(f"\n  [{sched_name}]")
        print(f"  {'':30}  {'flat-BLER':>12}  {'HARQ/IR':>12}  {'delta':>10}")
        print(f"  {'-'*68}")

        # System metrics
        for label, key in [
            ("DL PRB utilization", "dl_prb_utilization"),
            ("UL PRB utilization", "ul_prb_utilization"),
        ]:
            fv = flat[key]
            hv = harq_r[key]
            delta = hv - fv
            sign = "+" if delta >= 0 else ""
            print(f"  {label:<30}  {fv:>11.1%}  {hv:>11.1%}  "
                  f"{sign}{delta:>+9.1%}")

        # Per-flow metrics
        flow_keys = sorted(flat["flows"].keys())
        for fk in flow_keys:
            print(f"\n  flow {fk}:")
            for key, label, fmt in FLOW_METRICS:
                fv = flat["flows"][fk].get(key, 0)
                hv = harq_r["flows"][fk].get(key, 0)
                # delta in percentage points for ratios, raw for others
                if "ratio" in key or key in ("delivery_ratio",):
                    delta_str = f"{(hv - fv):>+9.1%}"
                elif "bps" in key:
                    delta_str = f"{(hv - fv)/1e6:>+9.2f}M"
                else:
                    delta_str = f"{(hv - fv):>+9.2f}"
                print(f"    {label:<28}  {fmt(fv):>12}  {fmt(hv):>12}  "
                      f"{delta_str}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=int, default=None,
                        help="Run only scenario N (0-indexed)")
    args = parser.parse_args()

    scenarios = SCENARIOS
    if args.scenario is not None:
        scenarios = [SCENARIOS[args.scenario]]

    for name, fn in scenarios:
        _print_scenario(fn, name)

    print(f"\n{'='*80}")
    print("HARQ parameters: max_retx=3, mode=IR, harq_rtt=8 slots, ewma_alpha=0.1")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
