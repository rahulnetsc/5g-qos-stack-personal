"""Long-run transient check: is the standard 4000-slot horizon steady state?

Runs one scenario for many 4000-slot windows (4000 slots = the standard
horizon used everywhere else) and reports an aggregate metric per window.
If window 1 differs materially from the late windows, the standard horizon
is measuring a transient / a short channel sample-path rather than
steady-state behaviour.

Tracked per window:
  - GBR delivery ratio  (delivered / arrived for GBR flows)
  - GBR throughput      (Mbps)
  - mean total backlog  (bytes queued across all flows, averaged over slots)

Usage:
    python scripts/transient_check.py
    python scripts/transient_check.py --scenario factory_robots --scheduler twotier --windows 60
"""

import argparse
import dataclasses
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from sim.buffer import BufferModel
from sim.channel import ChannelModel, bits_per_prb
from sim.resource import ResourceGrid
from sim import scenarios as scenario_registry
from sim.schedulers.gradient import GradientScheduler
from sim.schedulers.pf import ProportionalFair
from sim.schedulers.round_robin import RoundRobin
from sim.schedulers.two_tier import TwoTier
from sim.traffic import TrafficModel

WINDOW_SLOTS = 4000  # one window = the project's standard run horizon

SCENARIOS = {
    "smoke": scenario_registry.smoke_scenario,
    "overload": scenario_registry.overload_scenario,
    "vision": scenario_registry.vision_scenario,
    "sensor_dense": scenario_registry.sensor_dense_scenario,
    "latency_bound": scenario_registry.latency_bound_scenario,
    "factory_robots": scenario_registry.factory_robots_scenario,
}

SCHEDULERS = {
    "rr": RoundRobin,
    "pf": lambda: ProportionalFair(ewma_window_slots=200),
    "gradient": GradientScheduler,
    "twotier": lambda: TwoTier(tier1_period_slots=2000),
}


def _fresh_window() -> dict:
    return {"gbr_arr": 0, "gbr_deliv": 0, "backlog_sum": 0.0, "slots": 0}


def run_windowed(scenario, scheduler, window: int = WINDOW_SLOTS) -> tuple:
    """Mirror of sim.driver.run, but instead of recording per-slot data it
    accumulates a handful of aggregates per `window` slots. O(num_windows)
    memory, so it scales to arbitrarily long horizons."""
    rng = np.random.default_rng(scenario.seed)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    channel = ChannelModel(scenario.ues, rng)
    buffers = BufferModel()
    traffic = TrafficModel(scenario.flows, buffers, grid.slot_duration_s, rng)
    scheduler.configure(scenario.flows, grid.slot_duration_s, grid)

    pdb_by_flow = {(f.ue_id, f.qfi): f.pdb_ms / 1000.0 for f in scenario.flows}
    gbr_keys = {
        (f.ue_id, f.qfi) for f in scenario.flows if f.flow_class == "GBR"
    }

    windows: list[dict] = []
    cur = _fresh_window()

    for slot_index in range(scenario.horizon_slots):
        now_s = slot_index * grid.slot_duration_s

        for ue_id, qfi, byts in traffic.generate(slot_index):
            if (ue_id, qfi) in gbr_keys:
                cur["gbr_arr"] += byts

        channel.update(slot_index)
        slot_grid = grid.slot_grid(slot_index)

        for alloc in scheduler.allocate(slot_grid, buffers, channel):
            if alloc.bytes_capacity <= 0:
                continue
            symbols = (
                slot_grid.dl_symbols
                if alloc.direction == "DL"
                else slot_grid.ul_symbols
            )
            _, bler = bits_per_prb(
                channel.get_snr_db(alloc.ue_id), symbols=symbols
            )
            delivered = int(alloc.bytes_capacity * (1.0 - bler))
            buffers.drain(alloc.ue_id, alloc.qfi, delivered)
            if (alloc.ue_id, alloc.qfi) in gbr_keys:
                cur["gbr_deliv"] += delivered

        for ue_id, qfi in buffers.keys():
            pdb_s = pdb_by_flow.get((ue_id, qfi), 1.0)
            buffers.expire(now_s, pdb_s, ue_id, qfi)

        cur["backlog_sum"] += sum(
            buffers.state(u, q).bytes_queued for u, q in buffers.keys()
        )
        cur["slots"] += 1

        if cur["slots"] == window:
            windows.append(cur)
            cur = _fresh_window()

    if cur["slots"] > 0:
        windows.append(cur)
    return windows, grid.slot_duration_s


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="factory_robots")
    parser.add_argument("--scheduler", choices=SCHEDULERS, default="twotier")
    parser.add_argument(
        "--windows", type=int, default=60,
        help="Number of 4000-slot windows (default 60 ~= 1 minute at mu=2).",
    )
    args = parser.parse_args()

    base = SCENARIOS[args.scenario]()
    scenario = dataclasses.replace(
        base, horizon_slots=args.windows * WINDOW_SLOTS
    )
    windows, slot_s = run_windowed(scenario, SCHEDULERS[args.scheduler]())
    window_s = WINDOW_SLOTS * slot_s

    rows = []
    for w in windows:
        deliv = w["gbr_deliv"] / max(1, w["gbr_arr"])
        mbps = w["gbr_deliv"] * 8 / (w["slots"] * slot_s) / 1e6
        backlog_kb = w["backlog_sum"] / w["slots"] / 1024
        rows.append((deliv, mbps, backlog_kb))

    print(
        f"\nTransient check: {args.scenario} / {args.scheduler}, "
        f"{len(windows)} x {WINDOW_SLOTS}-slot windows "
        f"({len(windows) * window_s:.0f} s total)\n"
    )
    print(f"{'window':>7}{'t (s)':>12}{'GBR deliv':>11}{'GBR Mbps':>10}{'backlog KB':>12}")
    for i, (deliv, mbps, backlog_kb) in enumerate(rows):
        t0 = i * window_s
        # Print every window for the first 10, then every 5th, plus the last.
        if i < 10 or i % 5 == 0 or i == len(rows) - 1:
            print(
                f"{i + 1:>7}{f'{t0:.0f}-{t0 + window_s:.0f}':>12}"
                f"{deliv:>10.1%}{mbps:>9.1f}{backlog_kb:>11.0f}"
            )

    # Steady state = mean of the second half of the run.
    half = len(rows) // 2
    ss = rows[half:]
    ss_deliv = sum(r[0] for r in ss) / len(ss)
    ss_mbps = sum(r[1] for r in ss) / len(ss)
    ss_backlog = sum(r[2] for r in ss) / len(ss)
    ss_std = statistics.pstdev([r[0] for r in ss])
    print(
        f"\nSteady state (windows {half + 1}-{len(rows)} mean): "
        f"GBR deliv {ss_deliv:.1%}, {ss_mbps:.1f} Mbps, "
        f"backlog {ss_backlog:.0f} KB"
    )
    print(
        f"Per-window noise: steady-state GBR-delivery std = "
        f"+/-{ss_std * 100:.1f} pts — the scatter of one 4000-slot window."
    )
    w1_dev = rows[0][0] - ss_deliv
    n_sigma = abs(w1_dev) / ss_std if ss_std > 0 else 0.0
    verdict = (
        "a warm-up transient, not just noise"
        if n_sigma > 2.0
        else "within per-window noise"
    )
    print(
        f"Window 1 (= a standard 4000-slot run): GBR deliv {rows[0][0]:.1%}, "
        f"{w1_dev * 100:+.1f} pts off steady state ({n_sigma:.1f}x the "
        f"noise std) — {verdict}."
    )


if __name__ == "__main__":
    main()
