"""Can PDCCH be made to bind in this branch, and what makes it bind?

The study measured a genuinely PDCCH-bound regime on `sensor_dense`
(TwoTier 30/30 against PF's 2/30 via Configured Grants). This branch's
sensor_dense runs at 44-65 % CCE utilisation -- loaded, not bound. **Two
candidate reasons, and they point at different things:**

  AGGREGATION LEVEL -- the U-slot budget is 32 CCE. At AL 1 a DCI costs 1
    CCE and the budget serves 32 grants; at AL 16 it serves 2. The current
    scenario puts **every UE at exactly 12.0 dB**, which is AL 2 uniformly
    (`cce_aggregation_level`: >=20 -> 1, >=14 -> 2, >=8 -> 4, >=2 -> 8,
    else 16). A cell-edge spread would cost 4-16 CCE per grant.
  GRANT FREQUENCY -- a 5 ms periodic flow does not need a grant every slot,
    so per-slot CCE demand can sit far below the UE count.

**If aggregation level is the answer the binding regime is reachable with
the existing `snr_spread_db` axis rather than more UEs**, which is a
different and more useful conclusion.

Configured Grants are NOT restored and this probe does not need them: the
question is whether the REGIME exists, not whether TwoTier wins in it.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                  # noqa: E402
from sim.config import UEConfig                               # noqa: E402
from sim.driver import run as driver_run                      # noqa: E402
from sim.run_record import RunRecord                          # noqa: E402
from sim.scenarios import sensor_dense_scenario               # noqa: E402
from sim.trace import GrantCollector                          # noqa: E402
from g11_campaign import _arm                                 # noqa: E402


def variant(n_ues: int, snr_db: float, snr_spread_db: float, seed: int,
            horizon: int, period_ms: float | None = None,
            bytes_per_period: int | None = None):
    """sensor_dense's shape at another UE count / SNR spread.

    A VARIANT, not sensor_dense -- `sensor_dense_scenario()` takes no n_ues
    and its UEs are uniform at 12.0 dB. The flow template is copied from its
    own first flow so the workload shape is preserved exactly; only the
    population and the channel change.
    """
    base = sensor_dense_scenario()
    tmpl = base.flows[0]
    ues, flows = [], []
    for i in range(n_ues):
        # deterministic spread across the band, so AL varies without RNG
        off = 0.0 if snr_spread_db == 0 else (
            snr_spread_db * (i / max(1, n_ues - 1) - 0.5) * 2.0)
        ues.append(UEConfig(ue_id=i + 1, mean_snr_db=snr_db + off))
        params = dict(tmpl.traffic_params)
        # THE DECOUPLING LEVER. CCE is charged PER DCI; PRB is charged PER
        # BYTE. Shrinking the payload while raising the rate multiplies DCIs
        # without multiplying bytes -- the only way to raise CCE pressure
        # without raising PRB pressure with it.
        if period_ms is not None:
            params["period_ms"] = float(period_ms)
        if bytes_per_period is not None:
            params["bytes_per_period"] = int(bytes_per_period)
        flows.append(dataclasses.replace(tmpl, ue_id=i + 1,
                                         traffic_params=params))
    return dataclasses.replace(base, ues=ues, flows=flows, seed=seed,
                               horizon_slots=horizon,
                               name=f"sensor_dense_n{n_ues}_spread{snr_spread_db:g}")


def one(arm: str, n_ues: int, snr_db: float, spread: float, seed: int,
        horizon: int, period_ms=None, bytes_per_period=None) -> dict:
    sc = variant(n_ues, snr_db, spread, seed, horizon, period_ms, bytes_per_period)
    grants = GrantCollector()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True,
                   grant_sink=grants)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=s, arm={}, meta={})
    gs = [g for g in grants.finish() if g.direction == "UL" and not g.retx_count]
    al = Counter(g.cce_cost for g in gs)
    per_slot = Counter(g.slot_index for g in gs)
    cce_per_slot = Counter()
    for g in gs:
        cce_per_slot[g.slot_index] += g.cce_cost
    busy = list(per_slot.values())
    cce = list(cce_per_slot.values())
    return {
        "arm": arm, "n_ues": n_ues, "snr_db": snr_db, "spread_db": spread,
        "seed": seed, "horizon": horizon,
        "cce_util": rec.system.cce_utilization,
        "ul_prb_util": rec.system.ul_prb_utilization,
        "ul_grants": len(gs),
        "al_histogram": {str(k): v for k, v in sorted(al.items())},
        "mean_cce_per_dci": (sum(g.cce_cost for g in gs) / len(gs)) if gs else 0,
        "slots_with_a_grant": len(per_slot),
        "grants_per_busy_slot_max": max(busy) if busy else 0,
        "grants_per_busy_slot_mean": statistics.fmean(busy) if busy else 0,
        # THE BINDING TEST: a slot whose CCE spend reaches the U-slot budget
        "cce_per_busy_slot_max": max(cce) if cce else 0,
        "busy_slots_at_or_over_32": sum(1 for c in cce if c >= 32),
        "n_flows_delivering": sum(1 for fr in rec.flows.values()
                                  if fr.bytes_delivered > 0),
        "n_starved": sum(1 for fr in rec.flows.values()
                         if fr.bytes_delivered == 0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="PF")
    ap.add_argument("--n-ues", default="30,45,60,90,120")
    ap.add_argument("--snr", type=float, default=12.0)
    ap.add_argument("--spreads", default="0")
    ap.add_argument("--seed", type=int, default=1826701614)
    ap.add_argument("--horizon", type=int, default=8000)
    ap.add_argument("--period-ms", type=float, default=None)
    ap.add_argument("--bytes", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    print("%-6s %-9s %-9s %-9s %-11s %-10s %-8s %s"%(
        "n_ues","spread","cce_util","ul_prb","mean CCE/DCI","max CCE/slot",
        "slots>=32","AL histogram"))
    for spread in [float(x) for x in a.spreads.split(",")]:
        for n in [int(x) for x in a.n_ues.split(",")]:
            r = one(a.arm, n, a.snr, spread, a.seed, a.horizon,
                    a.period_ms, a.bytes)
            rows.append(r)
            print("%-6d %-9.1f %-9.4f %-9.4f %-11.2f %-10d %-8d %s"%(
                n, spread, r["cce_util"], r["ul_prb_util"],
                r["mean_cce_per_dci"], r["cce_per_busy_slot_max"],
                r["busy_slots_at_or_over_32"], r["al_histogram"]), flush=True)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"code_state": stamp(), "rows": rows},
                                          indent=1, default=str))
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
