"""G2: what a UL STOP flow actually measures.

REGISTERED IN `docs/g2-registration.md` BEFORE THIS EXISTED.

G2's row names two blockers: the E-STOP flow is DL while the named failure
mode -- the BSR/SR desync -- is uplink, and TB-size quantisation is unbuilt.

**Both are now better understood and one is dissolved.** §20.1 measured that
TB quantisation would not close G2 (13,214 of 13,214 grants at padding 0,
unchanged), so it stays unbuilt. And
`docs/bsr-desync-result-2026-09-05.md` established that **the desync route
does not latch** -- so G2's named failure mode cannot occur for an
already-served UE, and a UL STOP flow will not exhibit it.

**What the UL flow CAN measure is the SR -> grant -> BSR round-trip against
a 5 ms PDB**, which the app co-design guide puts at "~4-8 ms". That is the
operative cost and it needs no new mechanism.

THE INSTRUMENT IS A PAIR. `sim/fleet.py` now carries a UL 5QI-85 flow beside
the existing DL one: identical 5QI, payload and event rate, opposite
direction, ON THE SAME UE. The DL one pays no SR and no BSR. So the UL-DL
gap isolates the access chain from contention, and the DL flow is the
control -- if it fails too, the cost is contention and the gap says nothing.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                  # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells    # noqa: E402
from sim.config import CarrierConfig, ScenarioConfig, UEConfig  # noqa: E402
from sim.driver import run as driver_run                      # noqa: E402
from sim.fleet import build_fleet                             # noqa: E402
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard                          # noqa: E402
from sim.trace import GrantCollector                          # noqa: E402
from g11_campaign import _arm                                 # noqa: E402

STOP_QFI = {"DL": 85, "UL": 86}   # see sim/fleet.py: same 5 ms PDB, distinct keys
STOP_PDB_MS = 5.0
#: See sim/fleet.py's own comment: the real cadence is 0.2 Hz, which yields
#: ONE event per flow in a 5 s run. Raised for measurability only; payload
#: and PDB unchanged.
DIAG_RATE_HZ = 5.0


def build(seed: int, n_ues: int, horizon: int):
    flows, _seq = build_fleet(n_ues, "mixed", ul_stop=True,
                              stop_rate_hz=DIAG_RATE_HZ)
    ues = [UEConfig(ue_id=i + 1, mean_snr_db=20.0) for i in range(n_ues)]
    return ScenarioConfig(
        name=f"g2_ul_stop_n{n_ues}", seed=seed, horizon_slots=horizon,
        carrier=CarrierConfig(bandwidth_hz=40_000_000, numerology=2),
        ues=ues, flows=flows)


def one(arm: str, seed: int, n_ues: int, horizon: int) -> dict:
    sc = build(seed, n_ues, horizon)
    grants = GrantCollector()
    t0 = time.time()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True,
                   grant_sink=grants)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=s, arm={}, meta={})
    # SEVERITY, uniform across the scorecard: the fraction of RESOLVED
    # bytes that missed their PDB (M02). See phase2_core.py.
    _card = Scorecard()
    _m02a = _card.score(rec, population=Population.all_flows()).get("M02")
    _m02p = _card.score(rec, population=Population.protected_fleet()).get("M02")
    out = {"arm": arm, "seed": seed, "n_ues": n_ues, "horizon": horizon,
           "wall_s": round(time.time() - t0, 1),
           "M02_all": _m02a.value if _m02a else None,
           "M02_prot": _m02p.value if _m02p else None}
    for direction in ("UL", "DL"):
        # DELIVERY IS A PRECONDITION. A flow that delivered nothing reports
        # p98 = 0.0 and would score as inside the budget -- the defect caught
        # in docs/sensor-dense-result-2026-09-05.md, not repeated here.
        fs = [fr for fr in rec.flows.values()
              if fr.qfi == STOP_QFI[direction] and fr.direction == direction
              and fr.bytes_delivered > 0]
        p98 = [fr.delay_p98_ms for fr in fs if fr.delay_p98_ms is not None]
        out[f"{direction}_stop_flows"] = len(fs)
        out[f"{direction}_stop_p98_ms"] = max(p98) if p98 else None
        out[f"{direction}_stop_p50_ms"] = (
            statistics.median([fr.delay_p50_ms for fr in fs
                               if fr.delay_p50_ms is not None]) if fs else None)
        out[f"{direction}_stop_starved"] = sum(
            1 for fr in rec.flows.values()
            if fr.qfi == STOP_QFI[direction] and fr.direction == direction
            and fr.bytes_delivered == 0)
    if out["UL_stop_p98_ms"] is not None and out["DL_stop_p98_ms"] is not None:
        out["ul_minus_dl_ms"] = out["UL_stop_p98_ms"] - out["DL_stop_p98_ms"]
    ever = {g.ue_id for g in grants.finish()
            if g.direction == "UL" and not g.retx_count}
    all_ul = {f.ue_id for f in sc.flows if f.direction == "UL"}
    out["n_never_granted"] = len(all_ul - ever)
    out["ul_prb_util"] = rec.system.ul_prb_utilization
    return out


def _task(t):
    return one(*t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--n-ues", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--out", default="sweeps/postscaling-2026-09-05/g2_ul_stop.json")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    arms = [x for x in a.arms.split(",") if x]
    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, a.n_ues, a.horizon) for arm in arms for s in seeds]
    print(f"{len(tasks)} runs; STOP pair at {DIAG_RATE_HZ} Hz, PDB {STOP_PDB_MS} ms")
    rows = [None] * len(tasks)
    for i, (idx, r) in enumerate(run_cells(_task, tasks, a.workers,
                                           cost=lambda t: arm_cost(t[0])), 1):
        rows[idx] = r
        print(f"  [{i}/{len(tasks)}] {r['arm']:<12} seed={r['seed']} "
              f"UL p98={r['UL_stop_p98_ms']} DL p98={r['DL_stop_p98_ms']}",
              flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_state": stamp(), "stop_pdb_ms": STOP_PDB_MS,
                               "diag_rate_hz": DIAG_RATE_HZ, "rows": rows},
                              indent=1, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
