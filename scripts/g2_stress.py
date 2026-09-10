"""G2 as a stress experiment: the master disconnects and every ground robot
must stop. Does the STOP reach all of them in time, even when the cell is
busy?

Registered in `docs/g2-step0-2026-09-09.md`; predictions in
`docs/g2-registration-2026-09-09.md`; result in
`docs/g2-stress-experiment-2026-09-09.md`.

WHAT IS DIFFERENT FROM EVERY EARLIER G2 ROW:

  * **THE STATISTIC IS A MAXIMUM, NOT A PERCENTILE.** The clause is "100 % of
    STOPs <= 100 ms", so a p98 over trials tolerates 2 % of robots not
    stopping. `docs/scorecard-audit-2026-09-07.md` row 7 flagged the
    substitution; this discards it.

  * **A MISS IS NON-DELIVERY, NOT LATE DELIVERY.** 5QI 85's PDB is 5 ms and
    `sim/buffer.py::expire()` discards past it, so no delivered STOP can
    approach the 100 ms bound -- measured max 5.25 ms across every arm. The
    failures are DROPS, and Reservation dropped 87 of 1 607 while its p98 read
    a clean pass. Scored here as: a trial is a miss for a robot iff no
    completion lands in its 100 ms window.

  * **THE ANSWER IS A RATE WITH A CONFIDENCE** (test plan Sec 5.3), not
    pass/fail: zero misses in n trials gives miss-rate <= 3/n at 95 %, and
    with misses observed a Clopper-Pearson upper limit -- the rule of three
    is only its k=0 case and is not stretched past it.

  * **TRIALS ARE SIMULTANEOUS AND PHASE-RANDOMISED.** Every stopped robot
    fires in the SAME slot, on 30 scripted trials whose within-frame
    alignment varies -- the property `aperiodic_event` silently lacked.

  * **NO BASELINE GATE, DELIBERATELY.** G9 gated on a pre-join window so a
    slow join could be told from an already-broken cell. G2's clause reads
    "even at worst-case load", so a STOP that misses under saturation is
    precisely what the guarantee asks about, not a capacity condition to be
    excluded. Gating here would erase the finding.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                     # noqa: E402
from regime_sweep import (arm_cost, invocation_config, paired_seeds,  # noqa: E402
                          RunLedger, run_cells)
from sim.driver import run as driver_run                          # noqa: E402
from sim.random_access import RandomAccessConfig                  # noqa: E402
from sim.run_record import RunRecord                              # noqa: E402
from sim.scenarios.g2 import (N_TRIALS, QFI_STOP, STOP_BOUND_MS,   # noqa: E402
                              assert_stop_instrument_live,
                              build_gt12_scenario, stop_flow_keys,
                              trial_slots)
from sim.srb import with_srb                                      # noqa: E402
from scheduler.flow import DERIVE_PDB_FROM_5QI                    # noqa: E402
from g11_campaign import _arm                                     # noqa: E402
from proto_arms import resolve_arm                              # noqa: E402

CQI_DELAY_SLOTS = 8
#: Set by the schedule, not chosen: 30 trials 250 ms apart after a 1 s settle
#: put the last scoring window's close at ~33.4 k slots.
#: `sim/scenarios/g2.py::minimum_horizon_slots` derives it and the scenario
#: refuses a horizon that cannot score the last trial.
HORIZON_SLOTS = 40_000

#: Sub-experiment A: how many robots the disconnect stops, at once.
#: GT-1.2's own number is 2. The guarantee's wording is "on every ground
#: robot", so 2 is the minimum interesting case and the fleet is the maximum.
STOP_AXIS: tuple[int, ...] = (1, 2, 4, 8)
#: Sub-experiment B's fleet axis, bracketing G10's re-measured boundaries
#: (PF 12 / Reservation 6 / TwoTier 7).
UE_AXIS: tuple[int, ...] = (4, 6, 7, 8, 12, 16)
#: Sub-experiment B's ambient-pressure axis.
LOAD_AXIS: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0)


def _clopper_pearson_upper(k: int, n: int, conf: float = 0.95) -> float:
    """Upper limit on the miss rate at `conf`, exact (Clopper-Pearson).

    Test plan Sec 5.3 gives the rule of three, `eps <= 3/n`, WHICH HOLDS ONLY
    FOR k = 0 -- it is that case of this. Stretching 3/n past zero observed
    misses would state a bound the data does not support, so the k > 0 case
    gets the real thing. Uses the Beta quantile identity rather than a search;
    `scipy` is already a dependency.
    """
    if n <= 0:
        return float("nan")
    if k >= n:
        return 1.0
    from scipy.stats import beta
    return float(beta.ppf(conf, k + 1, n - k))


def _rule_of_three(n: int) -> float:
    """Sec 5.3's own form, for the zero-miss case it is stated for."""
    return 3.0 / n if n > 0 else float("nan")


def one(task: tuple) -> dict[str, Any]:
    n_ues, n_stop, cm, arm_name, seed, cap, lifted = task
    stop_pdb = STOP_BOUND_MS if lifted else DERIVE_PDB_FROM_5QI
    sc = build_gt12_scenario(seed=seed, n_ues=n_ues, n_stop=n_stop,
                             committed_mult=cm, horizon_slots=HORIZON_SLOTS,
                             stop_pdb_ms=stop_pdb)
    assert_stop_instrument_live(sc, n_stop=n_stop)
    keys = stop_flow_keys(sc)
    slots = trial_slots(seed)
    slot_s = 1.0 / (2 ** sc.carrier.numerology) / 1000.0
    sc = with_srb(sc)

    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    t0 = time.time()
    summ = driver_run(sc, resolve_arm(arm_name), cqi_delay_slots=CQI_DELAY_SLOTS,
                      max_sched_ues=cap, random_access=ra)
    wall = time.time() - t0
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm_name,
                                 seed=seed, flow_configs=sc.flows, summary=summ,
                                 arm={"cqi_delay_slots": CQI_DELAY_SLOTS,
                                      "max_sched_ues": cap}, meta={})

    # --- per trial, per robot: did the STOP arrive within the bound? -----
    bound_s = STOP_BOUND_MS / 1000.0
    arrivals: dict[str, list[float]] = {}
    for k in keys:
        ts: list[float] = []
        for lst in (rec.flows[k].completion_ts_by_role_s or {}).values():
            ts += list(lst)
        arrivals[k] = sorted(ts)

    per_trial = []
    for t_idx, t_slot in enumerate(slots):
        t_s = t_slot * slot_s
        worst_ms: Optional[float] = None
        missed_here = 0
        for k in keys:
            # Trials are spaced 250 ms apart and the bound is 100 ms, so at
            # most one completion can fall in a trial's window -- asserted by
            # the scenario's own spacing test, not assumed here.
            hit = [x for x in arrivals[k] if t_s <= x <= t_s + bound_s]
            if not hit:
                missed_here += 1
                continue
            lat = (hit[0] - t_s) * 1000.0
            worst_ms = lat if worst_ms is None else max(worst_ms, lat)
        per_trial.append({
            "trial": t_idx, "slot": t_slot, "phase": t_slot % 5,
            # GT-1.2: "per-trial worst asset recorded"
            "worst_ms": worst_ms, "missed": missed_here,
        })

    n_events = len(slots) * len(keys)
    n_missed = sum(p["missed"] for p in per_trial)
    delivered = [p["worst_ms"] for p in per_trial if p["worst_ms"] is not None]
    dropped_b = sum(rec.flows[k].bytes_dropped_pdb for k in keys)

    dl = sum(fr.throughput_bps for fr in rec.flows.values() if fr.direction == "DL")
    ul = sum(fr.throughput_bps for fr in rec.flows.values() if fr.direction == "UL")

    return {
        "n_ues": n_ues, "n_stop": n_stop, "committed_mult": cm,
        "arm": arm_name, "seed": seed, "cap": cap, "lifted_pdb": lifted,
        "wall_s": round(wall, 2),
        # THE CLAUSE: 100 % of STOPs within the bound, every trial, every robot
        "n_events": n_events, "n_missed": n_missed,
        "all_stopped": n_missed == 0,
        "worst_ms": max(delivered) if delivered else None,
        "median_worst_ms": statistics.median(delivered) if delivered else None,
        "stop_bytes_dropped": dropped_b,
        "per_trial": per_trial,
        "dl_mbps": round(dl / 1e6, 3), "ul_mbps": round(ul / 1e6, 3),
    }


def _summarise(rows: list[dict[str, Any]], axis_key: str, axis: tuple) -> dict:
    n_seeds = max((sum(1 for r in rows if r[axis_key] == a) for a in axis),
                  default=0)
    per_point = []
    for a in axis:
        cell = [r for r in rows if r[axis_key] == a]
        if not cell:
            continue
        assert len(cell) == n_seeds, (
            f"axis point {axis_key}={a} has {len(cell)} rows, expected "
            f"{n_seeds} -- never score a short or empty selection")
        ev = sum(r["n_events"] for r in cell)
        ms = sum(r["n_missed"] for r in cell)
        w = [r["worst_ms"] for r in cell if r["worst_ms"] is not None]
        per_point.append({
            axis_key: a, "n_seeds": len(cell),
            "seeds_all_stopped": sum(1 for r in cell if r["all_stopped"]),
            "stop_events": ev, "missed": ms,
            "miss_rate": ms / ev if ev else None,
            # Sec 5.3: the rule of three is the k=0 case; say which applies.
            "bound_95": (_rule_of_three(ev) if ms == 0
                         else _clopper_pearson_upper(ms, ev)),
            "bound_method": "rule of three (3/n)" if ms == 0
                            else "Clopper-Pearson upper",
            "worst_ms": max(w) if w else None,
            "median_worst_ms": round(statistics.median(w), 3) if w else None,
            "dl_mbps_median": round(statistics.median(
                [r["dl_mbps"] for r in cell]), 3),
            "ul_mbps_median": round(statistics.median(
                [r["ul_mbps"] for r in cell]), 3),
            "wall_s_total": round(sum(r["wall_s"] for r in cell), 1),
        })

    def boundary() -> Optional[Any]:
        best = None
        for p in per_point:
            if p["missed"] == 0:
                best = p[axis_key]
            else:
                break
        return best

    ev = sum(r["n_events"] for r in rows)
    ms = sum(r["n_missed"] for r in rows)
    return {
        "axis": axis_key, "points": per_point,
        "boundary_all_stopped": boundary(),
        "stop_events_total": ev, "missed_total": ms,
        "miss_rate": ms / ev if ev else None,
        "bound_95": _rule_of_three(ev) if ms == 0 else _clopper_pearson_upper(ms, ev),
        "bound_method": "rule of three (3/n)" if ms == 0 else "Clopper-Pearson upper",
        "wall_s_total": round(sum(r["wall_s"] for r in rows), 1),
        "n_runs": len(rows),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--caps", default="4,2")
    ap.add_argument("--stop-axis", default=",".join(str(x) for x in STOP_AXIS))
    ap.add_argument("--ue-axis", default=",".join(str(x) for x in UE_AXIS))
    ap.add_argument("--load-axis", default=",".join(str(x) for x in LOAD_AXIS))
    ap.add_argument("--fixed-n", type=int, required=True,
                    help="sub-experiment A's fleet size, DERIVED from G10")
    ap.add_argument("--fixed-stop", type=int, default=2,
                    help="sub-experiment B's STOP count; 2 is GT-1.2's own")
    ap.add_argument("--lifted-pdb", action="store_true",
                    help="DIAGNOSTIC: raise the STOP bearer's PDB to the "
                         "clause's 100 ms, so a STOP the faithful cell "
                         "discards is delivered and its latency measurable")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default="sweeps/g2-stress/g2_stress.json")
    a = ap.parse_args(argv[1:])

    arms = [x for x in a.arms.split(",") if x]
    caps = [int(x) for x in a.caps.split(",") if x]
    stop_axis = tuple(int(x) for x in a.stop_axis.split(",") if x)
    ue_axis = tuple(int(x) for x in a.ue_axis.split(",") if x)
    load_axis = tuple(float(x) for x in a.load_axis.split(",") if x)
    seeds = paired_seeds(a.seeds)

    tasks: list[tuple] = []
    for cap in caps:
        for arm in arms:
            for s in seeds:
                for ns in stop_axis:            # A: same-slot contention
                    if ns > a.fixed_n:
                        continue                # the grid is triangular
                    tasks.append((a.fixed_n, ns, 1.0, arm, s, cap, a.lifted_pdb))
                for n in ue_axis:               # B: ambient pressure
                    if a.fixed_stop > n:
                        continue
                    for cm in load_axis:
                        tasks.append((n, a.fixed_stop, cm, arm, s, cap,
                                      a.lifted_pdb))
    tasks = list(dict.fromkeys(tasks))

    print(f"G2 stress: {len(tasks)} driver runs x {N_TRIALS} trials\n"
          f"  A  1 clause part x {len(stop_axis)} STOP counts x {len(arms)} arms "
          f"x {len(seeds)} seeds x {len(caps)} caps x {N_TRIALS} trials "
          f"(N={a.fixed_n})\n"
          f"  B  1 clause part x {len(ue_axis)} fleet sizes x {len(load_axis)} "
          f"loads x {len(arms)} arms x {len(seeds)} seeds x {len(caps)} caps "
          f"x {N_TRIALS} trials (STOP={a.fixed_stop})\n"
          f"  horizon {HORIZON_SLOTS}, bound {STOP_BOUND_MS:g} ms, "
          f"STOP bearer PDB {'100 ms (LIFTED DIAGNOSTIC)' if a.lifted_pdb else '5 ms (faithful)'}",
          flush=True)

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    ledger = RunLedger(out.with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "horizon": HORIZON_SLOTS,
                        "n_trials": N_TRIALS},
                       ("n_ues", "n_stop", "committed_mult", "arm", "seed",
                        "cap", "lifted_pdb"))
    done = ledger.done_keys()
    rows: list[dict] = list(ledger.banked())
    todo = [t for t in tasks if (t[0], t[1], t[2], t[3], t[4], t[5], t[6]) not in done]
    print(f"  {len(rows)} banked, {len(todo)} to run", flush=True)

    t0 = time.time()
    for _i, r in run_cells(one, todo, a.workers,
                           cost=lambda t: arm_cost(t[3]) * t[0]):
        rows.append(r); ledger.bank(r)
        if len(rows) % 25 == 0:
            print(f"    ... {len(rows)}/{len(tasks)} ({time.time()-t0:.0f}s)",
                  flush=True)
    wall = time.time() - t0

    _FIG = ("n_ues", "n_stop", "committed_mult", "arm", "seed", "cap",
            "lifted_pdb", "n_events", "n_missed", "all_stopped", "worst_ms",
            "median_worst_ms", "stop_bytes_dropped", "dl_mbps", "ul_mbps",
            "wall_s")
    doc: dict[str, Any] = {
        "code_state": stamp(),
        "rows": [{k: r[k] for k in _FIG} for r in rows],
        "_horizon_slots": HORIZON_SLOTS, "_n_trials": N_TRIALS,
        "_stop_bound_ms": STOP_BOUND_MS, "_lifted_pdb": a.lifted_pdb,
        "_stop_axis": list(stop_axis), "_ue_axis": list(ue_axis),
        "_load_axis": list(load_axis), "_fixed_n": a.fixed_n,
        "_fixed_stop": a.fixed_stop, "_caps": caps, "_seeds": a.seeds,
        "_wall_s_this_invocation": round(wall, 1),
        "_ran_this_invocation": len(todo),
        "_cpu_s_total": round(sum(r["wall_s"] for r in rows), 1),
        "_n_runs": len(rows),
    }
    ev = sum(r["n_events"] for r in rows)
    ms = sum(r["n_missed"] for r in rows)
    doc["_campaign"] = {
        "stop_events": ev, "missed": ms,
        "miss_rate": ms / ev if ev else None,
        "bound_95": _rule_of_three(ev) if ms == 0 else _clopper_pearson_upper(ms, ev),
        "bound_method": "rule of three (3/n)" if ms == 0 else "Clopper-Pearson upper",
    }
    for cap in caps:
        for arm in arms:
            base = [r for r in rows if r["cap"] == cap and r["arm"] == arm]
            aa = [r for r in base if r["n_ues"] == a.fixed_n
                  and r["committed_mult"] == 1.0]
            bb = [r for r in base if r["n_stop"] == a.fixed_stop]
            if aa:
                doc[f"A/cap{cap}/{arm}"] = _summarise(
                    aa, "n_stop", tuple(x for x in stop_axis if x <= a.fixed_n))
            if bb:
                doc[f"B/cap{cap}/{arm}"] = _summarise(bb, "n_ues", ue_axis)
    out.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nwrote {out}  ({wall:.0f}s, {len(rows)} runs, "
          f"{ev} STOP events, {ms} missed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
