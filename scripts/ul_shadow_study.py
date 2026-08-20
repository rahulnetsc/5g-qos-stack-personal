"""Does the gNB's shadow token bucket stay in sync with the UE's real one?

The gNB cannot observe the uplink transport-block split -- the LCP runs in
the UE (TS 38.321 sec 5.4.3.1) -- so the uplink virtual-queue drain rests on
an estimate. `ul_split_estimator="shadow_lcp"` predicts the split by running
the UE's own algorithm against a shadow copy of its PBR token buckets, which
the gNB can do because it configured those PBRs over RRC.

The open question that motivates this script: **the shadow copy is debited
from the gNB's view of backlog (delayed, lossy, and in real 5G aggregated per
logical channel group), while the real bucket is debited from the UE's exact
view. So they drift.** Three things are measured here:

  1. How far apart the two copies actually get.
  2. Whether the drift is bounded, or accumulates without limit.
  3. Whether a closed-loop nudge from BSR residuals (`ul_bucket_sync_gain`)
     reduces it, and whether that changes delivered outcomes at all.

Usage:
    python scripts/ul_shadow_study.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import TwoTier
from sim.driver import run
from sim.scenarios import factory_robots_scenario
from sim.ue_lcp import UeLcp

CQI_DELAY_SLOTS = 8


def _tt(**kw):
    return TwoTier(tier1_period_slots=2000, delay_urgency_weight=4.0,
                   delay_exponent=2.0, **kw)


def divergence(sched: TwoTier, ue_lcp: UeLcp) -> dict:
    """Compare the gNB's shadow buckets against the UE's real ones.

    Reported as a fraction of each bucket's capacity, so flows with very
    different PBRs are comparable.
    """
    rows = []
    for key, shadow in sched._ul_shadow_bucket.items():
        real = ue_lcp._buckets.get(key)
        if real is None or shadow[1] <= 0:
            continue
        cap = shadow[1]
        rows.append((key, abs(shadow[0] - real.tokens) / cap,
                     shadow[0] / cap, real.tokens / cap))
    if not rows:
        return {"n": 0}
    errs = [r[1] for r in rows]
    return {
        "n": len(rows),
        "mean_err": sum(errs) / len(errs),
        "max_err": max(errs),
        "rows": rows,
    }


def profile(summary, scenario) -> dict:
    meta = {f"ue{f.ue_id}_qfi{f.qfi}": (f.flow_class, f.gfbr_bps)
            for f in scenario.flows}
    gbr = [(m, meta[fk][1]) for fk, m in summary["flows"].items()
           if meta[fk][0] == "GBR"]
    return {
        "mean_gbr": sum(m["throughput_bps"] / g for m, g in gbr) / len(gbr),
        "min_gbr": min(m["throughput_bps"] / g for m, g in gbr),
        "total_mbps": sum(f["throughput_bps"]
                          for f in summary["flows"].values()) / 1e6,
    }


def main() -> None:
    sc = factory_robots_scenario()

    print("factory_robots, uplink-heavy, 10 robots (3 with a second UL flow).")
    print("Bucket error is |gNB shadow - UE real| as a fraction of capacity.\n")
    print(f"{'estimator':<14}{'sync gain':>10}{'mean err':>10}{'max err':>9}"
          f"{'mean GBR':>10}{'min GBR':>9}{'total':>9}")

    configs = [
        ("occupancy",  0.0),
        ("shadow_lcp", 0.0),
        ("shadow_lcp", 0.01),
        ("shadow_lcp", 0.05),
        ("shadow_lcp", 0.20),
    ]
    for est, gain in configs:
        sched = _tt(ul_split_estimator=est, ul_bucket_sync_gain=gain)
        summary = run(sc, sched, cqi_delay_slots=CQI_DELAY_SLOTS)
        p = profile(summary, sc)
        ue_lcp = summary.get("_ue_lcp")
        d = divergence(sched, ue_lcp) if ue_lcp is not None else {"n": 0}
        if d["n"]:
            print(f"{est:<14}{gain:>10.2f}{d['mean_err']:>10.1%}"
                  f"{d['max_err']:>9.1%}{p['mean_gbr']:>10.0%}"
                  f"{p['min_gbr']:>9.0%}{p['total_mbps']:>8.1f}M")
        else:
            print(f"{est:<14}{gain:>10.2f}{'n/a':>10}{'n/a':>9}"
                  f"{p['mean_gbr']:>10.0%}{p['min_gbr']:>9.0%}"
                  f"{p['total_mbps']:>8.1f}M")

    print("\nOccupancy uses no bucket at all, so its error column is n/a --")
    print("it is the baseline for the delivered-outcome columns.")


if __name__ == "__main__":
    main()
