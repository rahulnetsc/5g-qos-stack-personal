"""The camera's UL loss, read against the map registered BEFORE any trace.

`docs/phase2-results.md` registered three candidates and their signatures in
advance. This computes exactly those three and nothing else. THE MAP IS NOT
AMENDED: if none of the three fires, that is the finding.

    candidate 1  PRB lost to other flows on the same UE
                 "UE granted; camera's share of each TB small while
                  siblings take the rest"
    candidate 2  PRB lost to other UEs
                 "the UE itself granted rarely; its share fine when it is"
    candidate 3  capacity lost to retransmissions
                 "grants issued, bytes not delivered; bytes_harq_lost
                  non-zero"
"""
from __future__ import annotations
import json, sys, collections
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))

from sim.driver import run                                   # noqa: E402
from sim.parametric import sweep_scenario                    # noqa: E402
from sim.run_record import RunRecord                         # noqa: E402
from sim.trace import GrantCollector                         # noqa: E402
from scheduler import load_two_tier                          # noqa: E402
import wp9_sweep as W                                        # noqa: E402

FAILING = [161576974, 579362555, 1097657231]     # zero dead flows, miss contract
PASSING = [1826701614, 1367864806]               # controls
CAMERA_QFI = 2


def one(seed: int) -> dict:
    sc = sweep_scenario(seed=seed, n_ues=8, horizon_slots=20000, load_mult=1.0)
    col = GrantCollector()
    summary = run(sc, load_two_tier(W._TT_CONFIG, min_rb=5),
                  cqi_delay_slots=8, record_timeseries=True, grant_sink=col)
    grants = col.finish()
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="TwoTier",
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    # the worst camera flow, by its own GFBR fraction
    cams = [(k, fr) for k, fr in rec.flows.items()
            if fr.qfi == CAMERA_QFI and fr.flow_class == "GBR"]
    worst_key, worst = min(cams, key=lambda kv: kv[1].gfbr_fraction() or 1.0)
    ue = worst.ue_id

    ul = [g for g in grants if g.direction == "UL"]
    first = [g for g in ul if g.retx_count == 0]
    ue_first = [g for g in first if g.ue_id == ue]

    # --- candidate 1: the camera's share of its own UE's TBs ---------------
    shares = []
    for g in ue_first:
        tot = sum(b for _, b in g.split)
        cam = sum(b for q, b in g.split if q == CAMERA_QFI)
        if tot > 0:
            shares.append(cam / tot)
    # --- candidate 2: how often is this UE granted, vs the others ----------
    by_ue = collections.Counter(g.ue_id for g in first)
    others = [n for u, n in by_ue.items() if u != ue]
    # --- candidate 3: retransmissions ------------------------------------
    retx = [g for g in ul if g.retx_count >= 1]
    ue_retx = [g for g in retx if g.ue_id == ue]
    prb_first = sum(g.prbs for g in first)
    prb_retx = sum(g.prbs for g in retx)
    failed_first = [g for g in first if not g.success]

    return {
        "seed": seed, "camera_flow": worst_key, "ue": ue,
        "gfbr_fraction": worst.gfbr_fraction(),
        "bytes_harq_lost": getattr(worst, "bytes_harq_lost", None),
        "c1_share_mean": (sum(shares) / len(shares)) if shares else None,
        "c1_share_min": min(shares) if shares else None,
        "c1_n_grants_with_split": len(shares),
        "c2_ue_grants": by_ue.get(ue, 0),
        "c2_other_ue_grants_mean": (sum(others) / len(others)) if others else None,
        "c2_other_ue_grants_min": min(others) if others else None,
        "c3_retx_prb_fraction": prb_retx / (prb_first + prb_retx) if (prb_first + prb_retx) else 0.0,
        "c3_ue_retx_grants": len(ue_retx),
        "c3_failed_first_grants": len(failed_first),
        "c3_failed_fraction": len(failed_first) / len(first) if first else 0.0,
        "n_ul_first_grants": len(first),
    }


def main() -> int:
    out = {"failing": [one(s) for s in FAILING],
           "passing": [one(s) for s in PASSING]}
    Path(__file__).with_name("result.json").write_text(json.dumps(out, indent=2, default=str))
    hdr = (f"{'seed':>11} {'cam':>12} {'gfbr':>7} | {'c1 share':>18} | "
           f"{'c2 grants':>20} | {'c3 retx/fail':>22}")
    for label in ("failing", "passing"):
        print(f"\n=== {label.upper()} SEEDS ===")
        print(hdr); print("-" * len(hdr))
        for r in out[label]:
            c1 = (f"{r['c1_share_mean']:.3f} min {r['c1_share_min']:.3f}"
                  if r["c1_share_mean"] is not None else "n/a")
            c2 = f"{r['c2_ue_grants']:>5} vs {r['c2_other_ue_grants_mean']:.0f} others"
            c3 = (f"retxPRB {r['c3_retx_prb_fraction']:.3f} "
                  f"fail {r['c3_failed_fraction']:.3f} lost {r['bytes_harq_lost']}")
            print(f"{r['seed']:>11} {r['camera_flow']:>12} {r['gfbr_fraction']:.4f} | "
                  f"{c1:>18} | {c2:>20} | {c3:>22}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
