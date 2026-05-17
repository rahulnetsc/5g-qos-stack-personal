"""Plot per-slot time series for one or two scheduler runs on the same scenario.

Usage:
    python scripts/plot_timeseries.py                       # default: pf vs twotier on sensor
    python scripts/plot_timeseries.py --scenario vision --schedulers pf twotier
    python scripts/plot_timeseries.py --scheduler twotier --out tt.png

Multi-scheduler mode overlays the same metric for each scheduler so you can
see the difference visually. Single-scheduler mode shows more per-flow detail.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
import numpy as np

from sim.driver import run
from sim.scenarios import (
    factory_robots_scenario,
    latency_bound_scenario,
    overload_scenario,
    sensor_dense_scenario,
    smoke_scenario,
    vision_scenario,
)
from sim.schedulers.gradient import GradientScheduler
from sim.schedulers.pf import ProportionalFair
from sim.schedulers.round_robin import RoundRobin
from sim.schedulers.two_tier import TwoTier


SCENARIOS = {
    "smoke": smoke_scenario,
    "overload": overload_scenario,
    "vision": vision_scenario,
    "sensor": sensor_dense_scenario,
    "latency": latency_bound_scenario,
    "factory": factory_robots_scenario,
}

SCHEDULERS = {
    "rr": lambda: RoundRobin(),
    "pf": lambda: ProportionalFair(ewma_window_slots=200),
    "gradient": lambda: GradientScheduler(),
    "twotier": lambda: TwoTier(tier1_period_slots=2000),
}


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x
    kernel = np.ones(window) / window
    # 'same' mode keeps array length; edges are biased downward for first
    # `window` slots, which we accept for plotting purposes.
    return np.convolve(x, kernel, mode="same")


def _plot_per_flow_panel(
    ax, ts_by_sched: dict[str, dict], metric: str, slot_dur_s: float,
    transform=None, title: str = "", ylabel: str = "",
    flow_filter=None, smooth_window: int = 1,
) -> None:
    flows = sorted(next(iter(ts_by_sched.values()))["per_flow"].keys())
    if flow_filter is not None:
        flows = [f for f in flows if flow_filter(f)]

    sched_names = list(ts_by_sched.keys())
    n_sched = len(sched_names)
    cmap = plt.get_cmap("tab10")

    for fi, flow_key in enumerate(flows):
        color = cmap(fi % 10)
        for si, sched_name in enumerate(sched_names):
            ts = ts_by_sched[sched_name]
            t_s = np.array(ts["time_s"])
            y = np.array(ts["per_flow"][flow_key][metric], dtype=float)
            if transform is not None:
                y = transform(y, slot_dur_s)
            if smooth_window > 1:
                y = _rolling_mean(y, smooth_window)
            linestyle = "-" if si == 0 else "--"
            label = (
                flow_key if n_sched == 1
                else f"{flow_key} [{sched_name}]"
            )
            ax.plot(t_s, y, color=color, linestyle=linestyle, linewidth=1.0, label=label)

    ax.set_xlabel("time (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    if len(flows) <= 8:
        ax.legend(fontsize=7, loc="best", ncol=2)


def _plot_system_panel(
    ax, ts_by_sched: dict[str, dict], series_keys: list[str],
    title: str, ylabel: str, smooth_window: int = 50,
    as_utilization: bool = False, total_keys: list[str] | None = None,
) -> None:
    sched_names = list(ts_by_sched.keys())
    cmap = plt.get_cmap("tab10")

    for ki, sk in enumerate(series_keys):
        for si, sched_name in enumerate(sched_names):
            ts = ts_by_sched[sched_name]
            t_s = np.array(ts["time_s"])
            y = np.array(ts["system"][sk], dtype=float)
            if as_utilization and total_keys is not None:
                tot = np.array(ts["system"][total_keys[ki]], dtype=float)
                # avoid div-by-zero
                y = np.where(tot > 0, y / np.maximum(tot, 1), 0.0)
            if smooth_window > 1:
                y = _rolling_mean(y, smooth_window)
            color = cmap(ki % 10)
            linestyle = "-" if si == 0 else "--"
            label = f"{sk} [{sched_name}]" if len(sched_names) > 1 else sk
            ax.plot(t_s, y, color=color, linestyle=linestyle, linewidth=1.0, label=label)
    ax.set_xlabel("time (s)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="best")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS.keys(), default="sensor")
    parser.add_argument(
        "--scheduler",
        choices=SCHEDULERS.keys(),
        help="Single scheduler mode (multi-flow detail).",
    )
    parser.add_argument(
        "--schedulers",
        nargs="+",
        choices=SCHEDULERS.keys(),
        default=["pf", "twotier"],
        help="Two-scheduler comparison mode (overlay).",
    )
    parser.add_argument("--out", default=None, help="Output PNG path. Default: <scenario>_<sched>.png")
    parser.add_argument(
        "--smooth", type=int, default=50,
        help="Rolling-window smoothing for instantaneous metrics (slots).",
    )
    args = parser.parse_args()

    sched_names = [args.scheduler] if args.scheduler else args.schedulers
    scenario_factory = SCENARIOS[args.scenario]

    ts_by_sched: dict[str, dict] = {}
    sched_config_summary = []
    for name in sched_names:
        scenario = scenario_factory()
        sched = SCHEDULERS[name]()
        summary = run(scenario, sched, record_timeseries=True)
        ts_by_sched[name] = summary["timeseries"]
        # Quick aggregate stats for the title
        delivery = np.mean([
            f["delivery_ratio"] for f in summary["flows"].values()
        ])
        sched_config_summary.append(f"{name}: avg delivery {delivery:.1%}")

    slot_dur_s = ts_by_sched[sched_names[0]]["time_s"][1] - ts_by_sched[sched_names[0]]["time_s"][0]

    n_flows = len(next(iter(ts_by_sched.values()))["per_flow"])
    show_per_flow = n_flows <= 8

    fig, axes = plt.subplots(3 if show_per_flow else 2, 2, figsize=(15, 12))
    if not show_per_flow:
        axes = np.array([[axes[0, 0], axes[0, 1]], [axes[1, 0], axes[1, 1]]])

    # Throughput per flow (rolling avg over smoothing window)
    def to_bps(y, slot_dur_s):
        return y * 8.0 / slot_dur_s

    _plot_per_flow_panel(
        axes[0, 0], ts_by_sched, "delivered_bytes", slot_dur_s,
        transform=to_bps,
        title="Per-flow throughput (rolling avg)",
        ylabel="Mbps",
        smooth_window=args.smooth,
    )
    # Convert y-axis from bps to Mbps via tick scaling
    axes[0, 0].yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1e6:.1f}"))

    # HoL delay per flow (no smoothing — we want the spikes)
    _plot_per_flow_panel(
        axes[0, 1], ts_by_sched, "hol_delay_s", slot_dur_s,
        transform=lambda y, _: y * 1000.0,
        title="Per-flow HoL delay (raw)",
        ylabel="ms",
        smooth_window=1,
    )

    if show_per_flow:
        # Buffer occupancy per flow
        _plot_per_flow_panel(
            axes[1, 0], ts_by_sched, "backlog_bytes", slot_dur_s,
            title="Per-flow buffer occupancy",
            ylabel="bytes",
            smooth_window=1,
        )
        # Cumulative dropped per flow
        def cumsum(y, _):
            return np.cumsum(y)
        _plot_per_flow_panel(
            axes[1, 1], ts_by_sched, "dropped_bytes", slot_dur_s,
            transform=cumsum,
            title="Cumulative bytes dropped (PDB expiry)",
            ylabel="bytes",
            smooth_window=1,
        )
        sys_row = 2
    else:
        sys_row = 1

    # PRB utilization
    _plot_system_panel(
        axes[sys_row, 0], ts_by_sched,
        series_keys=["dl_prbs_used", "ul_prbs_used"],
        title=f"PRB utilization (rolling avg, {args.smooth} slots)",
        ylabel="utilization",
        smooth_window=args.smooth,
        as_utilization=True,
        total_keys=["dl_prbs_avail", "ul_prbs_avail"],
    )
    axes[sys_row, 0].set_ylim(0, 1.05)

    # PDCCH (CCE) utilization
    _plot_system_panel(
        axes[sys_row, 1], ts_by_sched,
        series_keys=["cce_used"],
        title=f"PDCCH (CCE) utilization (rolling avg, {args.smooth} slots)",
        ylabel="utilization",
        smooth_window=args.smooth,
        as_utilization=True,
        total_keys=["cce_budget"],
    )
    axes[sys_row, 1].set_ylim(0, 1.05)

    sched_label = "+".join(sched_names)
    fig.suptitle(
        f"Scenario: {args.scenario}    Schedulers: {sched_label}\n"
        + "    ".join(sched_config_summary),
        fontsize=11,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    out = args.out or f"{args.scenario}_{sched_label}.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
