"""G7 / GT-4.3: a misbehaving asset offered at 2x MFBR, and its containment.

**THE SCENARIO IS THE ONLY THING THAT WAS MISSING.** The clipping mechanism
is present and faithful in both arms and both directions -- the C clips at
`ia_p5g_scheduler.c:2663-2665`, `gNB_scheduler_ulsch.c:2248-2250` and
`gNB_scheduler_dlsch.c:397-399`, and the port at `two_tier.py:1581-1585`/
`1748-1752` and `reservation.py:1109-1113`
(`docs/g7-clipping-question-2026-09-05.md`). G7 was previously recorded as
"structurally out, no MFBR enforcement anywhere in sim/", and both halves of
that were wrong.

GT-4.3's criterion is a CONJUNCTION of three clauses, scored separately here
because the interesting outcome is a split:

  1. Asset A entirely within SLO
  2. **Asset B's camera delivered <= MFBR + tolerance**
  3. Asset B's OWN other flows within SLO -- containment must hold INSIDE
     the misbehaving asset, which is the clause easiest to drop

Expectations registered in `docs/next-expectations-2026-09-05.md` BEFORE this
file existed: clause 1 PASS, **clause 2 FAIL**, clause 3 PASS.

**THE AGGRESSOR SCALES `avg_bytes`, NOT `aggressor_multiplier`.** That field
scales an `xr_video` flow's fragments *after* `_gen_xr_video` has already
fragmented the frame to fit `fragment_bytes`, so a scaled fragment can exceed
the configured MTU cap -- a known issue (CLAUDE.md). Scaling the source rate
is what "the encoder is mis-set" actually means.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                  # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells    # noqa: E402
from sim.driver import run as driver_run                      # noqa: E402
from sim.parametric import sweep_scenario                     # noqa: E402
from sim.run_record import RunRecord                          # noqa: E402
from g11_campaign import _arm                                 # noqa: E402

#: The misbehaving asset. UE 2 rather than UE 1 so the aggressor is not also
#: the first-position UE, which would confound the fault with the
#: declaration-order lock-out (docs/g5-mechanism-2026-09-05.md).
ASSET_B = 2
#: The victim, measured for clause 1.
ASSET_A = 1
CAMERA_QFI = 2
TELEMETRY_QFI = 1
#: GT-4.3's "offered >= 2x MFBR". THIS IS A MULTIPLE OF MFBR, and the
#: `avg_bytes` scale needed to reach it is DERIVED from the flow's own
#: gfbr/mfbr rather than restated -- the first version of this script set
#: `avg_bytes *= 2.0` and produced an offered rate of 0.97x MFBR, because
#: the camera natively offers about its GFBR and MFBR is 2x GFBR. It scored
#: clause 2 as a comfortable PASS on a scenario that was not the one GT-4.3
#: specifies.
OFFER_X_MFBR = 2.1   # target; the ACHIEVED rate is asserted >= 2.0 below,
                     # since the camera natively offers slightly under its GFBR
#: "delivered <= MFBR + tolerance". 10 % is this campaign's reading of
#: "tolerance"; the plan does not fix a number, and the verdict is reported
#: against several so the choice is visible rather than load-bearing.
TOLERANCES = (0.05, 0.10, 0.25)


def build(seed: int, n_ues: int, horizon: int, offer_x_mfbr: float,
          load_mult: float = 1.0):
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=load_mult)
    flows = []
    for f in sc.flows:
        if f.ue_id == ASSET_B and f.qfi == CAMERA_QFI and f.direction == "UL":
            p = dict(f.traffic_params)
            # Scale the SOURCE rate. `avg_bytes` is the per-period frame
            # size, so multiplying it is exactly "the encoder bitrate is set
            # too high" -- and it goes through _gen_xr_video's own
            # fragmentation, so no fragment exceeds fragment_bytes.
            #
            # The scale is DERIVED: the flow natively offers ~gfbr_bps, so
            # reaching `offer_x_mfbr` multiples of MFBR needs
            # offer_x_mfbr * mfbr / gfbr. Restating it as a literal is how
            # the first version came out at 0.97x MFBR instead of 2x.
            scale = offer_x_mfbr * (f.mfbr_bps / f.gfbr_bps)
            p["avg_bytes"] = float(p["avg_bytes"]) * scale
            f = dataclasses.replace(f, traffic_params=p)
        flows.append(f)
    return dataclasses.replace(sc, flows=flows)


def one(arm: str, seed: int, n_ues: int, horizon: int, offer: float,
        load_mult: float = 1.0) -> dict:
    sc = build(seed, n_ues, horizon, offer, load_mult)
    t0 = time.time()
    s = driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=s, arm={}, meta={})
    out = {"arm": arm, "seed": seed, "n_ues": n_ues, "horizon": horizon,
           "offer_x_mfbr_target": offer, "load_mult": load_mult,
           "wall_s": round(time.time() - t0, 1)}

    for fr in rec.flows.values():
        if fr.direction != "UL":
            continue
        role = None
        if fr.ue_id == ASSET_B and fr.qfi == CAMERA_QFI:
            role = "B_camera"
        elif fr.ue_id == ASSET_B and fr.qfi == TELEMETRY_QFI:
            role = "B_telemetry"
        elif fr.ue_id == ASSET_A and fr.qfi == CAMERA_QFI:
            role = "A_camera"
        elif fr.ue_id == ASSET_A and fr.qfi == TELEMETRY_QFI:
            role = "A_telemetry"
        if role is None:
            continue
        out[f"{role}_throughput_bps"] = fr.throughput_bps
        out[f"{role}_offered_bps"] = fr.offered_bps
        out[f"{role}_mfbr_bps"] = fr.gfbr_bps * 2.0 if fr.gfbr_bps else 0.0
        out[f"{role}_gfbr_bps"] = fr.gfbr_bps
        out[f"{role}_p98_ms"] = fr.delay_p98_ms
        out[f"{role}_pdb_ms"] = fr.pdb_ms
        if fr.frame_completions["total"]:
            ok = sum(1 for a in fr.frame_completions["complete_ages_ms"]
                     if a <= fr.pdb_ms)
            out[f"{role}_m05"] = ok / fr.frame_completions["total"]
    # utilisation is the discriminating second read registered for clause 2:
    # excess that vanishes as the cell saturates confirms BE-path delivery.
    out["dl_prb_util"] = rec.system.dl_prb_utilization
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
    ap.add_argument("--offer", type=float, default=OFFER_X_MFBR,
                    help="offered rate as a MULTIPLE OF MFBR (GT-4.3: >= 2)")
    ap.add_argument("--out", default="sweeps/postscaling-2026-09-05/g7.json")
    ap.add_argument("--load-mult", type=float, default=1.0,
                    help="background load; the registered second read for "
                         "clause 2 varies this to drive utilisation -> 1.0")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    arms = [x for x in a.arms.split(",") if x]
    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, a.n_ues, a.horizon, a.offer, a.load_mult)
             for arm in arms for s in seeds]
    print(f"{len(tasks)} runs = {len(arms)} arms x {len(seeds)} seeds, "
          f"asset B (ue{ASSET_B}) camera offered at {a.offer}x MFBR")
    rows = [None] * len(tasks)
    for i, (idx, r) in enumerate(run_cells(_task, tasks, a.workers,
                                           cost=lambda t: arm_cost(t[0])), 1):
        rows[idx] = r
        print(f"  [{i}/{len(tasks)}] {r['arm']:<12} seed={r['seed']} "
              f"B_cam={r.get('B_camera_throughput_bps', 0)/1e6:.2f} Mbps "
              f"(MFBR {r.get('B_camera_mfbr_bps', 0)/1e6:.1f})", flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # ASSERT THE SCENARIO IS THE ONE GT-4.3 SPECIFIES, from the achieved
    # offered rate rather than from the knob that was set.
    ach = [r["B_camera_offered_bps"] / r["B_camera_mfbr_bps"] for r in rows
           if r.get("B_camera_mfbr_bps")]
    lo = min(ach) if ach else 0.0
    print(f"achieved offered rate: {lo:.2f}-{max(ach):.2f}x MFBR "
          f"(GT-4.3 requires >= 2.0x)")
    if lo < 2.0:
        raise SystemExit(
            f"the aggressor offered only {lo:.2f}x MFBR -- this is not "
            f"GT-4.3's scenario and must not be scored as it")
    out.write_text(json.dumps({"code_state": stamp(), "asset_b": ASSET_B,
                               "asset_a": ASSET_A,
                               "offer_x_mfbr_target": a.offer,
                               "offer_x_mfbr_achieved_min": lo,
                               "rows": rows}, indent=1, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
