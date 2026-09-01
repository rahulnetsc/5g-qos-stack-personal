"""G12's stop-condition probe: fix the ramp's TOP level by measurement.

`docs/wp9-plan.md` §35.5 registered this before any code:

    the grid is not launched until a probe cell shows 5QI 4 breaching under
    the CANONICAL declaration order, and if no feasible load does so, that
    is itself the result and is reported as one rather than fixed by
    adopting whichever permutation cooperates.

Why it is needed. Stage 5's lidar was pinned at "fails" -- capped at
`duration_s/horizon_s = 0.4`, breaching at every load including ramp index
0. Under `build_fleet`'s canonical flow order this workload's lidar looked
pinned the other way, unbroken through x3.0 on all three arms while 5QI 2
collapsed. **A class pinned at "meets" is the same defect mirrored and is
equally fatal to an ordering** -- M13 would emit a one-element list, which
is F4's own result recurring.

This script therefore answers two things, and reports both whatever they
say:

  1. Does 5QI 4 breach anywhere in a feasible ramp, under the CANONICAL
     order? (If not, `RAMP` cannot be set and G12 is unscoreable for a
     stated structural reason.)
  2. Where does the ramp sit relative to GT-7.3's own definition -- "ramp
     aggregate offered load in +10 % steps of the measured ceiling ... to
     145 %"? The committed-load multiplier is not a percentage of ceiling,
     so the mapping is MEASURED here rather than assumed, and a breach that
     only happens far outside 145 % is a different answer from one inside
     it.

Deliberately one seed and one composition: this fixes a grid parameter, it
does not score anything. The campaign is commit 3.

    uv run python scripts/g12_ramp_probe.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scheduler import load_two_tier
from scheduler.reservation import Reservation
from sim import driver
from sim.baselines.pf import ProportionalFair
from sim.scenarios.g12 import (GBR_CLASSES, build_g12_scenario,
                               gbr_flow_census)

_TT_CONFIG = str(Path(__file__).resolve().parents[1] / "scheduler"
                 / "scheduler_config.yaml")

# The panel's own pre-registered contract fraction (config/metric_panel.yml
# `defaults.gbr_contract_fraction`), not a local threshold.
CONTRACT_FRACTION = 0.95
CQI_DELAY_SLOTS = 8          # scripts/scheduler_study.py's pinned value
HORIZON_SLOTS = 20_000

CANDIDATE_MULTS = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)


def _arms() -> dict:
    return {
        "PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": lambda: Reservation(min_rb=5),
        "TwoTier": lambda: load_two_tier(_TT_CONFIG, min_rb=5),
    }


def _measure(scenario, arm_factory) -> dict:
    summary = driver.run(scenario, arm_factory(),
                         cqi_delay_slots=CQI_DELAY_SLOTS)
    cfg = {f"ue{f.ue_id}_qfi{f.qfi}": f for f in scenario.flows}
    by_class: dict[int, list[float]] = {}
    committed_bps = 0.0
    ul_delivered_bps = 0.0
    bg_bps = 0.0
    for key, fm in summary["flows"].items():
        f = cfg[key]
        if f.direction == "UL":
            ul_delivered_bps += fm["throughput_bps"]
        if f.flow_class == "GBR" and f.gfbr_bps > 0:
            committed_bps += f.gfbr_bps
            by_class.setdefault(f.qfi, []).append(
                fm["throughput_bps"] / f.gfbr_bps)
        if f.qfi == 9:
            bg_bps += fm["throughput_bps"]
    return {
        "by_class": by_class, "committed_bps": committed_bps,
        "ul_delivered_bps": ul_delivered_bps, "bg_bps": bg_bps,
        "ul_util": summary["ul_prb_utilization"],
    }


def main(argv: list[str]) -> int:
    n_ues, composition, seed = 8, "mixed", 12345
    scen0 = build_g12_scenario(n_ues, composition, 1.0, seed, HORIZON_SLOTS)
    census = gbr_flow_census(scen0)
    print(f"G12 ramp stop-condition probe -- {composition} N={n_ues} "
          f"seed={seed} horizon={HORIZON_SLOTS}")
    print(f"  GBR flow census (computed from the built scenario): {census}")
    print(f"  contract fraction {CONTRACT_FRACTION} (panel default), "
          f"canonical declaration order, no permutation")
    print()

    # GT-7.3's "% of the measured ceiling" needs a ceiling. Take it as the
    # UL bytes the cell actually delivers when it is already saturated --
    # measured at the ramp's own bottom, not assumed from a link budget.
    ceiling_bps: float | None = None
    first_breach: dict[str, float | None] = {}

    for arm, factory in _arms().items():
        print(f"--- {arm}")
        first_breach[arm] = None
        for m in CANDIDATE_MULTS:
            sc = build_g12_scenario(n_ues, composition, m, seed, HORIZON_SLOTS)
            got = gbr_flow_census(sc)
            if got != census:
                raise AssertionError(
                    f"GBR flow census changed across the ramp: {census} -> "
                    f"{got} at x{m}. Every ramp point must carry the same "
                    f"population or the points are not comparable "
                    f"(docs/wp9-plan.md §35.8).")
            t0 = time.time()
            r = _measure(sc, factory)
            if ceiling_bps is None:
                ceiling_bps = r["ul_delivered_bps"]
            parts = []
            for qi in GBR_CLASSES:
                v = r["by_class"][qi]
                n_ok = sum(x >= CONTRACT_FRACTION for x in v)
                parts.append(f"5QI{qi} {n_ok}/{len(v)} min {min(v):.3f}")
            if (first_breach[arm] is None
                    and min(r["by_class"][4]) < CONTRACT_FRACTION):
                first_breach[arm] = m
            pct = 100.0 * r["committed_bps"] / ceiling_bps if ceiling_bps else 0.0
            print(f"  x{m:<5} committed {r['committed_bps']/1e6:6.1f} Mbps "
                  f"({pct:5.0f}% of ceiling) | " + " | ".join(parts)
                  + f" | 5QI9 {r['bg_bps']/1e6:7.3f} | ul_util "
                    f"{r['ul_util']:.3f} | {time.time()-t0:.1f}s")
        print()

    print("=" * 74)
    print(f"Ceiling (UL delivered at the ramp's own bottom, PF): "
          f"{ceiling_bps/1e6:.1f} Mbps")
    print("First committed-load multiplier at which 5QI 4 breaches "
          f"(contract {CONTRACT_FRACTION}), CANONICAL order:")
    for arm, m in first_breach.items():
        where = f"x{m}" if m is not None else f"NEVER, up to x{CANDIDATE_MULTS[-1]}"
        print(f"  {arm:12s} {where}")
    if any(v is None for v in first_breach.values()):
        print("\n  §35.5's STOP CONDITION FIRES on at least one arm: 5QI 4 is "
              "\n  pinned at 'meets' there, so M13 can only emit a one-element "
              "\n  order for it. That is the result and is reported as one -- "
              "\n  NOT fixed by adopting a permutation that cooperates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
