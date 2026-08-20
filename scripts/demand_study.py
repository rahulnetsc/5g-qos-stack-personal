"""Tier-1 has to *estimate* demand. What does that cost, and when does it oscillate?

Our simulator has always handed Tier-1 the exact offered rate of every flow,
read from the traffic generator's own parameters. No gNB has that. It must
infer demand from what it observes -- for uplink, from BSR-reported buffer
occupancy -- and the estimate is lagged, noisy, and (the interesting part) can
be *coupled to its own output*.

That coupling is the failure the OAI deployment hit: offered load that
responds to service forms a closed loop with the scheduler, and when the
source's response period is near the Tier-1 window the loop oscillates. They
measured ~40% uplink throughput loss and fixed it with an EWMA slower than
the oscillation. A TCP sender is the obvious case, but the same shape covers
an adaptive video encoder or a UE-side rate controller -- anything whose
offered load responds to what it got.

This script builds a scenario with rate-adaptive uplink sources and sweeps:
  1. oracle vs measured demand  -- what perfect knowledge was worth.
  2. EWMA alpha                 -- how much smoothing the loop needs.
  3. adapt period vs Tier-1 window -- where the resonance actually is.

Usage:
    python scripts/demand_study.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import TwoTier
from sim.config import (
    CarrierConfig,
    FlowConfig,
    ScenarioConfig,
    TDDConfig,
    UEConfig,
)
from sim.driver import run

TIER1_PERIOD_SLOTS = 2000


def adaptive_scenario(adapt_period_ms: float = 1000.0, n_ue: int = 6):
    """Uplink-heavy cell where every source adapts its rate to what it gets.

    Sized so the cell is genuinely contended -- the sources must back off,
    which is what closes the loop. Without contention an adaptive source just
    climbs to its ceiling and sits there.
    """
    return ScenarioConfig(
        name="adaptive_ul",
        horizon_slots=24000,
        carrier=CarrierConfig(numerology=1, bandwidth_hz=20_000_000),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[
            UEConfig(ue_id=i + 1, mean_snr_db=18.0 + 2.0 * (i % 4),
                     coherence_slots=2000)
            for i in range(n_ue)
        ],
        flows=[
            FlowConfig(
                ue_id=i + 1, qfi=9, direction="UL", flow_class="PF",
                pdb_ms=300, priority_level=90,
                traffic_kind="adaptive",
                traffic_params={
                    "initial_rate_bps": 8e6,
                    "min_rate_bps": 0.5e6,
                    "max_rate_bps": 30e6,
                    "increase_bps": 2e6,
                    "decrease_factor": 0.7,
                    "backoff_threshold": 0.95,
                    "adapt_period_ms": adapt_period_ms,
                },
            )
            for i in range(n_ue)
        ],
        seed=11,
    )


def _tt(**kw):
    return TwoTier(tier1_period_slots=TIER1_PERIOD_SLOTS, **kw)


def total_mbps(summary) -> float:
    return sum(f["throughput_bps"] for f in summary["flows"].values()) / 1e6


def fairness(summary) -> float:
    """Jain's fairness index over delivered throughput."""
    x = [f["throughput_bps"] for f in summary["flows"].values()]
    n = len(x)
    s = sum(x)
    sq = sum(v * v for v in x)
    return (s * s) / (n * sq) if sq > 0 else 1.0


def _hr(t):
    print(f"\n{'=' * 72}\n{t}\n{'=' * 72}")


def main() -> None:
    tier1_ms = TIER1_PERIOD_SLOTS * 0.5  # mu=1 -> 0.5 ms/slot

    _hr("PART 1 -- What was perfect demand knowledge worth?")
    print(f"Adaptive UL sources, adapt period = Tier-1 window = {tier1_ms:.0f} ms\n")
    sc = adaptive_scenario(adapt_period_ms=tier1_ms)
    print(f"{'demand':<12}{'alpha':>7}{'total':>10}{'fairness':>11}")
    for est, alpha in (("oracle", 0.0), ("measured", 1.0), ("measured", 0.5),
                       ("measured", 0.3), ("measured", 0.1)):
        s = run(sc, _tt(demand_estimator=est, demand_ewma_alpha=alpha))
        label = est if est == "oracle" else "measured"
        a = "-" if est == "oracle" else f"{alpha:.1f}"
        print(f"{label:<12}{a:>7}{total_mbps(s):>9.1f}M{fairness(s):>11.2f}")
    print("\nalpha=1.0 is no smoothing (raw window estimate);")
    print("lower alpha smooths over more Tier-1 windows.")

    _hr("PART 2 -- Where is the resonance?")
    print("Sweeping the source's adapt period against a fixed "
          f"{tier1_ms:.0f} ms Tier-1 window.\n")
    print(f"{'adapt period':>14}{'ratio':>8}{'oracle':>10}"
          f"{'measured raw':>14}{'measured a=0.3':>16}")
    for adapt_ms in (250.0, 500.0, 1000.0, 2000.0, 4000.0):
        sc = adaptive_scenario(adapt_period_ms=adapt_ms)
        o = total_mbps(run(sc, _tt(demand_estimator="oracle")))
        raw = total_mbps(run(sc, _tt(demand_estimator="measured",
                                     demand_ewma_alpha=1.0)))
        sm = total_mbps(run(sc, _tt(demand_estimator="measured",
                                    demand_ewma_alpha=0.3)))
        print(f"{adapt_ms:>12.0f}ms{adapt_ms / tier1_ms:>8.2f}"
              f"{o:>9.1f}M{raw:>13.1f}M{sm:>15.1f}M")


if __name__ == "__main__":
    main()
