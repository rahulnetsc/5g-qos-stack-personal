"""Run the smoke and overload scenarios through every scheduler and print
side-by-side comparisons.

Usage:
    python scripts/compare_schedulers.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.config import ScenarioConfig
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


# UL BSR round-trip in slots -- kept consistent with scheduler_study.py.
UL_BSR_DELAY_SLOTS = 8


SCHEDULERS = [
    ("RoundRobin", lambda: RoundRobin()),
    ("ProportionalFair", lambda: ProportionalFair(ewma_window_slots=200)),
    (
        "Gradient",
        lambda: GradientScheduler(
            ewma_window_slots=200,
            gbr_urgency_weight=5.0,
            delay_urgency_weight=4.0,
            delay_exponent=2.0,
        ),
    ),
    (
        "TwoTier",
        lambda: TwoTier(
            tier1_period_slots=2000,
            delay_urgency_weight=4.0,
            delay_exponent=2.0,
        ),
    ),
]


def _print_scenario(scenario: ScenarioConfig) -> None:
    results: dict[str, dict] = {}
    for name, factory in SCHEDULERS:
        results[name] = run(scenario, factory(), ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS)

    sched_names = [n for n, _ in SCHEDULERS]
    flow_keys = sorted(next(iter(results.values()))["flows"].keys())
    metrics_to_show = [
        ("offered_bps", "offered Mbps", lambda v: f"{v / 1e6:.2f}"),
        ("throughput_bps", "delivered Mbps", lambda v: f"{v / 1e6:.2f}"),
        ("delivery_ratio", "delivered/offered", lambda v: f"{v:.1%}"),
        ("hol_p50_ms", "p50 HoL ms", lambda v: f"{v:.1f}"),
        ("hol_p95_ms", "p95 HoL ms", lambda v: f"{v:.1f}"),
        ("hol_p99_ms", "p99 HoL ms", lambda v: f"{v:.1f}"),
    ]
    col_w = max(14, max(len(n) for n in sched_names) + 2)

    print(f"\n{'='*70}")
    print(
        f"Scenario: {scenario.name}, "
        f"horizon = {results[sched_names[0]]['horizon_s']:.2f} s"
    )
    print(f"{'='*70}")
    print(
        "DL PRB utilization: "
        + ", ".join(
            f"{n} {results[n]['dl_prb_utilization']:.1%}" for n in sched_names
        )
    )
    print(
        "UL PRB utilization: "
        + ", ".join(
            f"{n} {results[n]['ul_prb_utilization']:.1%}" for n in sched_names
        )
    )
    print(
        "PDCCH utilization: "
        + ", ".join(
            f"{n} {results[n]['cce_utilization']:.1%}" for n in sched_names
        )
    )

    for fk in flow_keys:
        ue_str, qfi_str = fk.split("_")
        ue_id = int(ue_str[2:])
        qfi = int(qfi_str[3:])
        flow_class = "?"
        for f in scenario.flows:
            if f.ue_id == ue_id and f.qfi == qfi:
                flow_class = f.flow_class
                if f.flow_class == "GBR":
                    flow_class += f" (GFBR={f.gfbr_bps/1e6:.1f} Mbps)"
                elif f.flow_class == "Delay":
                    flow_class += f" (PDB={f.pdb_ms:.0f} ms)"
                break
        print(f"\n--- {fk}  [{flow_class}] ---")
        header = f"{'metric':<22}" + "".join(f"{n:>{col_w}}" for n in sched_names)
        print(header)
        print("-" * len(header))
        for key, label, fmt in metrics_to_show:
            row = f"{label:<22}"
            for name in sched_names:
                val = results[name]["flows"][fk][key]
                row += f"{fmt(val):>{col_w}}"
            print(row)


def main() -> None:
    _print_scenario(smoke_scenario())
    _print_scenario(overload_scenario())
    _print_scenario(vision_scenario())
    _print_scenario(sensor_dense_scenario())
    _print_scenario(factory_robots_scenario())


if __name__ == "__main__":
    main()
