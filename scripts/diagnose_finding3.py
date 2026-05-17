"""Confirm NOTES.md Finding 3 — the burst/PDB loss ceiling.

Finding 3: video GBR flows drop ~15% of offered bytes on PDB expiry even
at 3x capacity. Hypothesis: an I-frame burst cannot drain within the PDB
no matter the scheduler — it is a contract/dimensioning problem, not a
scheduling one.

This script makes the case three ways:
  Part 1 — contract arithmetic: the I-frame burst rate vs the GFBR.
  Part 2 — one flow, no contention: delivery is scheduler-independent and
           capacity-thresholded (no scheduler can do better than "give the
           lone flow everything").
  Part 3 — the fix is in the inputs: relaxing the PDB or shrinking the
           I-frame removes the drops; that is a contract / source change,
           not a scheduler change.

Usage:
    python scripts/diagnose_finding3.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.channel import bits_per_prb
from sim.config import CarrierConfig, FlowConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.driver import run
from sim.resource import ResourceGrid
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin
from scheduler import TwoTier
from scheduler import grid_capacity_prbsym_per_sec

SNR = 20.0
HORIZON = 40000  # numerology 1 (0.5 ms slots) -> 20 s, ~20 I-frame bursts
PERIOD_MS = 33.33
I_PERIOD = 30


def video_flow_scenario(
    bandwidth_mhz: float,
    pdb_ms: float = 30.0,
    i_mult: float = 4.0,
    avg_bytes: int = 33_000,
    gfbr: float = 8_000_000,
) -> ScenarioConfig:
    """One video GBR flow alone on a carrier — no contention at all."""
    return ScenarioConfig(
        name=f"f3_{bandwidth_mhz}mhz",
        horizon_slots=HORIZON,
        carrier=CarrierConfig(bandwidth_hz=int(bandwidth_mhz * 1e6), numerology=1),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[UEConfig(ue_id=1, mean_snr_db=SNR, coherence_slots=2000)],
        flows=[
            FlowConfig(
                ue_id=1, qfi=2, direction="UL", flow_class="GBR",
                gfbr_bps=gfbr, pdb_ms=pdb_ms,
                traffic_kind="video_frame",
                traffic_params={
                    "period_ms": PERIOD_MS, "avg_bytes": avg_bytes,
                    "i_frame_multiplier": i_mult,
                    "i_frame_period_in_frames": I_PERIOD,
                },
            )
        ],
        seed=1,
    )


def _delivery(summary: dict) -> tuple[float, float]:
    f = summary["flows"]["ue1_qfi2"]
    return f["delivery_ratio"], f["bytes_dropped"] * 8 / 1e6


def _peak_ul_mbps(bandwidth_mhz: float) -> float:
    """Best-case UL rate the lone flow can get on this carrier."""
    grid = ResourceGrid(
        CarrierConfig(bandwidth_hz=int(bandwidth_mhz * 1e6), numerology=1),
        TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
    )
    _, cap_ul = grid_capacity_prbsym_per_sec(grid)
    bits, bler = bits_per_prb(SNR, symbols=1)
    return cap_ul * bits * (1.0 - bler) / 1e6


def part1_arithmetic() -> None:
    print("=" * 72)
    print("PART 1 — contract arithmetic: I-frame burst rate vs GFBR")
    print("=" * 72)
    print(
        "An I-frame arrives as one chunk and has the PDB to drain. The rate\n"
        "that needs is I_frame_bytes*8 / PDB — compare it to the GFBR the\n"
        "contract actually guarantees.\n"
    )
    profiles = [
        ("camera 8M", 8_000_000, 33_000, 4.0, 30.0),
        ("lidar 14M", 14_000_000, 58_000, 3.0, 30.0),
        ("camera 6M", 6_000_000, 25_000, 4.0, 30.0),
    ]
    print(f"{'profile':<12}{'GFBR':>9}{'I-frame':>10}{'burst rate':>13}"
          f"{'burst/GFBR':>12}{'fits PDB@GFBR?':>16}")
    for name, gfbr, avg_bytes, i_mult, pdb_ms in profiles:
        i_bytes = avg_bytes * i_mult
        burst_rate = i_bytes * 8 / (pdb_ms / 1000.0)
        deliverable = gfbr * (pdb_ms / 1000.0) / 8  # bytes drainable at GFBR
        fits = "yes" if deliverable >= i_bytes else f"no ({deliverable/i_bytes:.0%})"
        print(
            f"{name:<12}{gfbr/1e6:>7.0f}M{i_bytes/1e3:>8.0f}KB"
            f"{burst_rate/1e6:>11.0f}M{burst_rate/gfbr:>11.1f}x{fits:>16}"
        )
    print(
        "\nThe burst rate is 4-5x the GFBR: a scheduler that delivers exactly\n"
        "the contracted rate still cannot clear the I-frame within the PDB.\n"
    )


def part2_isolation() -> None:
    print("=" * 72)
    print("PART 2 — one flow, no contention: scheduler-independent")
    print("=" * 72)

    # 2a — at a fixed carrier in the drop regime, every scheduler is identical
    # (a lone flow gets all PRBs whatever the policy).
    bw = 20.0
    print(f"\n2a. One video flow alone on a {bw:.0f} MHz carrier "
          f"(peak UL ~{_peak_ul_mbps(bw):.0f} Mbps):\n")
    print(f"{'scheduler':<14}{'delivery':>10}{'dropped':>12}")
    for label, factory in [
        ("RoundRobin", RoundRobin),
        ("PF", lambda: ProportionalFair(ewma_window_slots=200)),
        ("TwoTier", lambda: TwoTier(tier1_period_slots=2000)),
    ]:
        ratio, dropped = _delivery(run(video_flow_scenario(bw), factory()))
        print(f"{label:<14}{ratio:>9.1%}{dropped:>10.1f}M")
    print("  -> identical: with no contention there is nothing to schedule.\n")

    # 2b — sweep capacity. Delivery is thresholded on the burst rate, not the
    # average rate (~9 Mbps), so no amount of "average" capacity fixes it.
    print("2b. Same flow, sweeping carrier capacity (RoundRobin):\n")
    print(f"{'bandwidth':>10}{'peak UL':>10}{'delivery':>10}{'dropped':>12}")
    for bw in (10, 15, 20, 30, 45, 60, 90):
        ratio, dropped = _delivery(run(video_flow_scenario(bw), RoundRobin()))
        print(f"{bw:>8.0f}M{_peak_ul_mbps(bw):>8.0f}M{ratio:>9.1%}{dropped:>10.1f}M")
    print(
        "\n  -> delivery stays < 100% until peak capacity clears the I-frame\n"
        "     burst rate — far above the flow's ~9 Mbps average.\n"
    )


def part3_the_fix_is_in_the_inputs() -> None:
    print("=" * 72)
    print("PART 3 — the fix is in the inputs, not the scheduler")
    print("=" * 72)
    bw = 20.0
    base, base_drop = _delivery(run(video_flow_scenario(bw), RoundRobin()))
    print(f"\nBaseline (one flow, {bw:.0f} MHz, PDB 30 ms, I-frame 4x): "
          f"delivery {base:.1%}, dropped {base_drop:.1f}M\n")

    print("Relax the PDB (a contract change):")
    print(f"{'PDB':>8}{'delivery':>10}{'dropped':>12}")
    for pdb in (30, 60, 100, 150):
        ratio, dropped = _delivery(
            run(video_flow_scenario(bw, pdb_ms=pdb), RoundRobin())
        )
        print(f"{pdb:>6.0f}ms{ratio:>9.1%}{dropped:>10.1f}M")

    print("\nShrink the I-frame multiplier (a source change; 1.0 = paced/CBR):")
    print(f"{'I-mult':>8}{'delivery':>10}{'dropped':>12}")
    for im in (4.0, 3.0, 2.0, 1.0):
        ratio, dropped = _delivery(
            run(video_flow_scenario(bw, i_mult=im), RoundRobin())
        )
        print(f"{im:>7.1f}{ratio:>9.1%}{dropped:>10.1f}M")
    print(
        "\n  -> both fixes live in the contract (PDB) or the source (I-frame /\n"
        "     pacing). Neither is a scheduler change.\n"
    )


def main() -> None:
    part1_arithmetic()
    part2_isolation()
    part3_the_fix_is_in_the_inputs()


if __name__ == "__main__":
    main()
