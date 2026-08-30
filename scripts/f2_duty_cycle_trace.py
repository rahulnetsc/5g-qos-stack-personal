"""F2's direct-cause trace: WHY does TwoTier win under duty-cycling, and is
stage 5's transient the same phenomenon? (`docs/wp9-plan.md` §22.4)

F2 predicted H2 would NOT hold in its registered direction. It does. §21.6
registered a standing obligation for exactly that case: a miss on this
stage's most-likely-wrong expectation gets a direct-cause trace BEFORE the
write-up, not more reading -- because in this WP that slot has twice
carried the more interesting finding (stage 4's E2 produced §15.5, stage
5's E2 produced the flat transient boundary).

RESULT. The advantage is TwoTier GAINING, not PF losing, and the two
regimes are driven by DIFFERENT TERMS OF THE SAME FORMULA in opposite
directions -- so stage 5's transient and a duty-cycled steady state are not
the same phenomenon. Numbers in §22.4.

F2 predicted H2 would not hold in its registered direction. It does. Per
docs/wp9-plan.md §21.6's standing obligation, a miss on the registered
most-likely-wrong expectation gets a direct-cause trace before write-up.

Two candidate mechanisms inside TwoTier's UL composite
(`_finalize_ul_coef`: coef = (base_q + urg) * hyp_tbs_bytes):
  base_q -- from vq_ul, a virtual queue that INTEGRATES while starved;
  urg    -- a delay barrier on urgency01, which needs live backlog to grow.
Only base_q can accumulate across an IDLE period (no backlog, no delay).

And for PF: _r_avg is an EWMA with ewma_window_slots=200 (50 ms at 0.25 ms
slots) against silences of 330-1000 ms at duty 0.1 -- 6-20 window lengths,
so it decays to the floor and stops discriminating between UEs.
"""
from __future__ import annotations
import sys, collections, statistics
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))

from sim.driver import run
from sim.parametric import sweep_scenario
from sim.baselines.pf import ProportionalFair
from scheduler import load_two_tier

TT_CONFIG = str(REPO / "scheduler" / "scheduler_config.yaml")
HORIZON = 8000


def trace_twotier(duty: float, seed: int = 12345):
    sched = load_two_tier(TT_CONFIG, min_rb=5)
    rec = {"base_q": [], "urg": [], "n_cand": []}
    orig = sched._finalize_ul_coef

    def hooked(candidates):
        pre = [c.coef for c in candidates]          # base_q, before overwrite
        orig(candidates)
        for c, base_q in zip(candidates, pre):
            tbs = max(1, c.hyp_tbs_bytes)
            urg_total = c.coef / tbs - base_q       # recover urg exactly
            rec["base_q"].append(base_q)
            rec["urg"].append(urg_total)
        rec["n_cand"].append(len(candidates))

    sched._finalize_ul_coef = hooked
    sc = sweep_scenario(seed=seed, n_ues=8, load_mult=1.0, mix="factory",
                        duty_cycle=duty, horizon_slots=HORIZON)
    run(sc, sched, cqi_delay_slots=8)
    return rec


def trace_pf(duty: float, seed: int = 12345):
    sched = ProportionalFair(ewma_window_slots=200)
    samples = []
    orig = sched.allocate

    def hooked(slot, buffers, channel):
        out = orig(slot, buffers, channel)
        vals = [v for v in sched._r_avg.values()]
        if len(vals) >= 2:
            samples.append((max(vals), min(vals), statistics.mean(vals)))
        return out

    sched.allocate = hooked
    sc = sweep_scenario(seed=seed, n_ues=8, load_mult=1.0, mix="factory",
                        duty_cycle=duty, horizon_slots=HORIZON)
    run(sc, sched, cqi_delay_slots=8)
    return samples


def summarise(name, vals):
    if not vals:
        print(f"    {name}: none"); return
    q = statistics.quantiles(vals, n=100) if len(vals) > 99 else None
    print(f"    {name:10s} n={len(vals):7d}  mean={statistics.mean(vals):12.3f}  "
          f"median={statistics.median(vals):12.3f}  "
          f"p99={q[98] if q else float('nan'):14.3f}  max={max(vals):14.3f}")


def trace_twotier_scenario(sc, label, seed=12345):
    """Same hook, arbitrary scenario -- so stage 5's lidar activation can be
    measured with the identical instrument rather than argued about."""
    sched = load_two_tier(TT_CONFIG, min_rb=5)
    rec = {"base_q": [], "urg": []}
    orig = sched._finalize_ul_coef

    def hooked(candidates):
        pre = [c.coef for c in candidates]
        orig(candidates)
        for c, base_q in zip(candidates, pre):
            tbs = max(1, c.hyp_tbs_bytes)
            rec["base_q"].append(base_q)
            rec["urg"].append(c.coef / tbs - base_q)

    sched._finalize_ul_coef = hooked
    run(sc, sched, cqi_delay_slots=8)
    return rec


def stage5_scenarios():
    """Stage 5's own builder, reused -- not a re-implementation."""
    sys.path.insert(0, str(REPO / "scripts"))
    import wp9_sweep as W
    control = W._build_fleet_scenario_s5(
        seed=12345, n_ues=16, composition="ugv_heavy", lidar_ues=0)
    active = W._build_fleet_scenario_s5(
        seed=12345, n_ues=16, composition="ugv_heavy", lidar_ues=2)
    return control, active


if __name__ == "__main__":
    print("=" * 74)
    print("TwoTier UL composite: which term carries the advantage?")
    print("=" * 74)
    for duty in (1.0, 0.1):
        r = trace_twotier(duty)
        print(f"\n  duty_cycle = {duty}   ({len(r['n_cand'])} UL selection passes)")
        summarise("base_q", r["base_q"])
        summarise("urg", r["urg"])
        bq, ug = r["base_q"], r["urg"]
        share = [b / (b + u) for b, u in zip(bq, ug) if (b + u) > 0]
        if share:
            print(f"    base_q share of (base_q+urg): mean {statistics.mean(share):.4f}")

    print("\n" + "=" * 74)
    print("PF _r_avg spread: can it still tell UEs apart?")
    print("=" * 74)
    for duty in (1.0, 0.1):
        s = trace_pf(duty)
        if not s:
            print(f"  duty_cycle = {duty}: no samples"); continue
        ratios = [(mx / mn) if mn > 0 else float("inf") for mx, mn, _ in s]
        finite = [r for r in ratios if r != float("inf")]
        floored = sum(1 for _mx, mn, _m in s if mn <= 1.0)
        print(f"\n  duty_cycle = {duty}   ({len(s)} slots with >=2 UEs tracked)")
        print(f"    max/min r_avg ratio: median "
              f"{statistics.median(finite) if finite else float('nan'):10.3f}   "
              f"infinite (min==0) on {len(ratios) - len(finite)} slots")
        print(f"    slots with min(r_avg) <= 1.0 (EWMA at the floor): "
              f"{floored}/{len(s)} ({100.0*floored/len(s):.1f}%)")

    print("\n" + "=" * 74)
    print("STAGE 5's TRANSIENT: can the same mechanism operate there?")
    print("=" * 74)
    print("  The duty-cycle mechanism needs RECURRING IDLE PERIODS for vq_ul")
    print("  to integrate across. A lidar activation is a one-off step to a")
    print("  permanently higher load. If base_q's median stays at the")
    print("  duty=1.0 value, the two are NOT the same phenomenon.")
    try:
        control, active = stage5_scenarios()
    except Exception as exc:
        print(f"  (could not build stage-5 scenarios: {exc})")
    else:
        for sc, label in ((control, "ugv_heavy N=16, lidar_ues=0 (control)"),
                          (active, "ugv_heavy N=16, lidar_ues=2 (activated)")):
            r = trace_twotier_scenario(sc, label)
            print(f"\n  {label}")
            summarise("base_q", r["base_q"])
            summarise("urg", r["urg"])
            bq, ug = r["base_q"], r["urg"]
            share = [b / (b + u) for b, u in zip(bq, ug) if (b + u) > 0]
            if share:
                print(f"    base_q share of (base_q+urg): mean {statistics.mean(share):.4f}")
