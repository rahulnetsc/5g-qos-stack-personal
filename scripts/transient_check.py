"""Long-run transient check: is the standard 4000-slot horizon steady state?

Runs one scenario for many 4000-slot windows (4000 slots = the standard
horizon used everywhere else) and reports a contract metric per window.
If window 1 differs materially from the late windows, the standard horizon
is measuring a transient / a short channel sample-path rather than
steady-state behaviour.

The tracked metric depends on the scenario's contract class:
  - GBR scenarios   -> GBR delivery ratio and throughput.
  - Delay scenarios -> on-time count (flows meeting >=99% delivery within
                       PDB) and the worst per-flow p99 HoL latency.
Total backlog (bytes queued) is reported either way — it makes the
buffer warm-up visible directly.

Usage:
    python scripts/transient_check.py
    python scripts/transient_check.py --scenario sensor_dense --scheduler twotier
    python scripts/transient_check.py --scenario latency_bound --scheduler pf --windows 60
"""

import argparse
import dataclasses
import statistics
import sys
from collections import defaultdict
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
ONTIME_DELIVERY = 0.99  # a Delay flow is "on time" at >= this delivery ratio

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


def run_windowed(scenario, scheduler, window: int = WINDOW_SLOTS) -> tuple:
    """Mirror of sim.driver.run, but instead of recording per-slot data it
    finalises a handful of per-flow aggregates every `window` slots. Only
    the current window's raw HoL samples are held, so it scales to
    arbitrarily long horizons."""
    rng = np.random.default_rng(scenario.seed)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    channel = ChannelModel(scenario.ues, rng)
    buffers = BufferModel()
    traffic = TrafficModel(scenario.flows, buffers, grid.slot_duration_s, rng)
    scheduler.configure(scenario.flows, grid.slot_duration_s, grid)

    pdb_by_flow = {(f.ue_id, f.qfi): f.pdb_ms / 1000.0 for f in scenario.flows}

    windows: list[dict] = []
    arr: dict = defaultdict(int)
    deliv: dict = defaultdict(int)
    hol: dict = defaultdict(list)
    backlog_sum = 0.0
    slots = 0

    for slot_index in range(scenario.horizon_slots):
        now_s = slot_index * grid.slot_duration_s

        for ue_id, qfi, byts in traffic.generate(slot_index):
            arr[(ue_id, qfi)] += byts

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
            deliv[(alloc.ue_id, alloc.qfi)] += delivered

        for ue_id, qfi in buffers.keys():
            pdb_s = pdb_by_flow.get((ue_id, qfi), 1.0)
            buffers.expire(now_s, pdb_s, ue_id, qfi)
            hol[(ue_id, qfi)].append(
                buffers.hol_delay_s(ue_id, qfi, now_s)
            )

        backlog_sum += sum(
            buffers.state(u, q).bytes_queued for u, q in buffers.keys()
        )
        slots += 1

        if slots == window:
            windows.append(
                _finalize(arr, deliv, hol, backlog_sum, slots)
            )
            arr, deliv, hol = defaultdict(int), defaultdict(int), defaultdict(list)
            backlog_sum, slots = 0.0, 0

    if slots > 0:
        windows.append(_finalize(arr, deliv, hol, backlog_sum, slots))
    return windows, grid.slot_duration_s


def _finalize(arr, deliv, hol, backlog_sum, slots) -> dict:
    """Collapse one window's raw accumulators into per-flow stats."""
    per_flow = {}
    for key, samples in hol.items():
        a = arr.get(key, 0)
        d = deliv.get(key, 0)
        per_flow[key] = {
            "deliv_ratio": d / a if a > 0 else 1.0,
            "p99_ms": float(np.percentile(samples, 99) * 1000.0),
            "arr": a,
            "deliv": d,
        }
    return {"per_flow": per_flow, "backlog_kb": backlog_sum / slots / 1024.0}


def _verdict(series: list[float], label: str, unit: str) -> None:
    """Compare window 1 of a per-window series against its steady state."""
    half = len(series) // 2
    ss = series[half:]
    ss_mean = sum(ss) / len(ss)
    ss_std = statistics.pstdev(ss)
    dev = series[0] - ss_mean
    if ss_std < 0.05:
        # Metric is essentially constant across the whole run.
        note = (
            "flat across every window"
            if abs(dev) < 0.05
            else f"window 1 {dev:+.1f}{unit} off an otherwise flat run"
        )
        print(f"  {label}: {ss_mean:.1f}{unit} — {note}")
        return
    n_sigma = abs(dev) / ss_std
    tag = (
        "a warm-up transient, not just noise"
        if n_sigma > 2.0
        else "within per-window noise"
    )
    print(
        f"  {label}: steady state {ss_mean:.1f}{unit} "
        f"(per-window std +/-{ss_std:.1f}); "
        f"window 1 = {series[0]:.1f}{unit} ({dev:+.1f} -> {n_sigma:.1f}x std, {tag})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="factory_robots")
    parser.add_argument("--scheduler", choices=SCHEDULERS, default="twotier")
    parser.add_argument(
        "--windows", type=int, default=60,
        help="Number of 4000-slot windows (default 60).",
    )
    args = parser.parse_args()

    base = SCENARIOS[args.scenario]()
    scenario = dataclasses.replace(
        base, horizon_slots=args.windows * WINDOW_SLOTS
    )
    flow_class = {(f.ue_id, f.qfi): f.flow_class for f in scenario.flows}
    pdb_ms = {(f.ue_id, f.qfi): f.pdb_ms for f in scenario.flows}
    gbr = [k for k, c in flow_class.items() if c == "GBR"]
    delay = [k for k, c in flow_class.items() if c == "Delay"]
    primary = "GBR" if gbr else "Delay"

    windows, slot_s = run_windowed(scenario, SCHEDULERS[args.scheduler]())
    window_s = WINDOW_SLOTS * slot_s

    print(
        f"\nTransient check: {args.scenario} / {args.scheduler}, "
        f"{len(windows)} x {WINDOW_SLOTS}-slot windows "
        f"({len(windows) * window_s:.0f} s total) — tracking {primary} flows\n"
    )

    if primary == "GBR":
        header = f"{'window':>7}{'t (s)':>12}{'GBR deliv':>11}{'GBR Mbps':>10}{'backlog KB':>12}"
        deliv_series, p99_series = [], []
    else:
        header = f"{'window':>7}{'t (s)':>12}{'on-time':>11}{'worst p99':>12}{'backlog KB':>12}"
        ontime_series, p99_series = [], []
    print(header)

    for i, w in enumerate(windows):
        pf = w["per_flow"]
        t0 = i * window_s
        show = i < 10 or i % 5 == 0 or i == len(windows) - 1
        if primary == "GBR":
            tot_a = sum(pf[k]["arr"] for k in gbr)
            tot_d = sum(pf[k]["deliv"] for k in gbr)
            ratio = tot_d / tot_a if tot_a > 0 else 1.0
            mbps = tot_d * 8 / window_s / 1e6
            deliv_series.append(ratio * 100)
            if show:
                print(
                    f"{i + 1:>7}{f'{t0:.0f}-{t0 + window_s:.0f}':>12}"
                    f"{ratio:>10.1%}{mbps:>9.1f}{w['backlog_kb']:>11.0f}"
                )
        else:
            on = sum(
                1 for k in delay
                if pf[k]["deliv_ratio"] >= ONTIME_DELIVERY
                and pf[k]["p99_ms"] <= pdb_ms[k]
            )
            worst = max(pf[k]["p99_ms"] for k in delay)
            ontime_series.append(on)
            p99_series.append(worst)
            if show:
                print(
                    f"{i + 1:>7}{f'{t0:.0f}-{t0 + window_s:.0f}':>12}"
                    f"{f'{on}/{len(delay)}':>11}{f'{worst:.1f}ms':>12}"
                    f"{w['backlog_kb']:>11.0f}"
                )

    print(f"\nWindow 1 is a standard {WINDOW_SLOTS}-slot run. Steady state = "
          f"second half of the run.")
    if primary == "GBR":
        _verdict(deliv_series, "GBR delivery", " pts")
    else:
        _verdict(ontime_series, f"on-time count (/{len(delay)})", "")
        _verdict(p99_series, "worst p99 HoL", " ms")


if __name__ == "__main__":
    main()
