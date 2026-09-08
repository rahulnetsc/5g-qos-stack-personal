"""G9 as a stress experiment: does a robot joining a BUSY cell start working
correctly and immediately?

Registered in `docs/g9-stress-experiment-2026-09-08.md`. Two sub-experiments,
scored separately and both reported:

  A. TIME TO FIRST SERVICE -- the join itself.
  B. TIME TO A STABLE CELL -- the settling period, incumbents included.

THE AXIS is cell occupancy: UE count and committed load move TOGETHER,
because an operator experiences them as one thing ("the cell is busy"). Its
range is set by G10's re-measured admissible boundary, swept ACROSS it.

THE THRESHOLD is the spec's, not ours. TS 122 261 V17.11.0 sec3.1:

    "the communication service is unavailable if a message is not correctly
     received within a specified time, which is the sum of maximum allowed
     end-to-end latency and survival time"

so a flow is AVAILABLE at time t iff a message of that flow was delivered
within the last (pdb_ms + survival_time_ms). `sim/workload.py` derives
survival_time from the flow's own transfer interval, per TS 122 261's
definition of it; the number of intervals is the CHOSEN part and is swept.

THE BASELINE SANITY GATE runs first and gives three outcomes, all reported:
PASS, JOIN FAILURE, and CELL ALREADY BROKEN -- the last is a result an
operator needs, not a skipped cell.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import (arm_cost, bootstrap_ci, invocation_config,  # noqa: E402
                          paired_seeds, RunLedger, run_cells)
from scheduler import load_two_tier                              # noqa: E402
from scheduler.reservation import Reservation                    # noqa: E402
from sim.baselines.pf import ProportionalFair                    # noqa: E402
from sim.driver import run                                       # noqa: E402
from sim.random_access import RandomAccessConfig                 # noqa: E402
from sim.run_record import RunRecord                             # noqa: E402
from sim.scenarios.g9 import (gt61_warm_rejoin, gt62_cold_attach,  # noqa: E402
                              gt63_rlf_recovery, joiner_ue_id, neighbour_ue_ids)
from sim.scorecard import Population, Scorecard                  # noqa: E402
from sim.srb import with_srb                                     # noqa: E402
from sim.workload import with_survival_times                     # noqa: E402

_TT = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")
CQI_DELAY_SLOTS = 8

#: THE OCCUPANCY AXIS. One knob, two dials: an operator does not experience
#: "six robots" and "1.5x the committed load" as separate facts. Levels are
#: named by TOTAL UEs (joiner + incumbents) so they can be read straight
#: against G10's admissible boundary.
OCCUPANCY = (
    # (total_ues, committed_mult)
    (3, 0.50),
    (4, 0.75),
    (5, 1.00),
    (6, 1.25),
    (7, 1.50),
    (8, 2.00),
)

CASES = {
    "warm": (gt61_warm_rejoin, "warm"),
    "cold": (gt62_cold_attach, "cold"),
    "rlf": (gt63_rlf_recovery, "reestablish"),
}

#: The cold clause keeps the test plan's own bound; warm and post-RLF use the
#: spec rule above. Stated here so a reader need not open the plan.
COLD_ATTACH_BOUND_S = 15.0

#: CHOSEN, and swept: the neighbours criterion has no spec basis at all --
#: the test plan says "neighbours unaffected" without an epsilon.
NEIGHBOUR_EPSILON_MS = (0.5, 1.0, 2.0, 5.0)


def _arms():
    return {"PF": lambda: ProportionalFair(ewma_window_slots=200),
            "Reservation": lambda: Reservation(min_rb=5),
            "TwoTier": lambda: load_two_tier(_TT, min_rb=5)}


def _availability_budget_s(fr) -> float:
    """TS 122 261 sec3.1: max allowed end-to-end latency + survival time."""
    return (fr.pdb_ms + fr.survival_time_ms) / 1000.0


def _unavailable_spans(fr, time_s):
    """Slots at which this flow is UNAVAILABLE by the spec rule: nothing
    delivered within the last (pdb + survival). Returns a boolean list."""
    budget = _availability_budget_s(fr)
    out = []
    last_delivery_s = None
    for i, t in enumerate(time_s):
        if fr.ts_delivered_bytes and i < len(fr.ts_delivered_bytes) and fr.ts_delivered_bytes[i] > 0:
            last_delivery_s = t
        out.append(last_delivery_s is None or (t - last_delivery_s) > budget)
    return out


def _scored_flows(rec, ue_ids):
    """Committed flows only: best-effort filler carries no promise, so its
    availability is not what "the cell is working" means. DERIVED from
    flow_class, and SRBs excluded (signalling, not the fleet's data)."""
    return [fr for fr in rec.flows.values()
            if fr.ue_id in ue_ids and not getattr(fr, "is_srb", False)
            and fr.flow_class in ("GBR", "Delay") and fr.ts_delivered_bytes]


def _cell_broken_pre_join(rec, neighbours, trigger_s, time_s) -> dict:
    """THE BASELINE SANITY GATE. Were the incumbents already failing BEFORE
    the joiner arrived? Measured over the window that ends at the first join
    trigger, skipping a warm-up equal to one availability budget."""
    flows = _scored_flows(rec, set(neighbours))
    if not flows or not time_s:
        return {"broken": None, "reason": "no scoreable incumbent flow"}
    worst = 0.0
    culprit = None
    for fr in flows:
        budget = _availability_budget_s(fr)
        un = _unavailable_spans(fr, time_s)
        idx = [i for i, t in enumerate(time_s) if budget <= t < trigger_s]
        if not idx:
            continue
        frac = sum(1 for i in idx if un[i]) / len(idx)
        if frac > worst:
            worst, culprit = frac, f"ue{fr.ue_id}_qfi{fr.qfi}"
    return {"broken": worst > 0.01, "worst_unavailable_fraction": worst,
            "worst_flow": culprit}


def _time_to_first_service_s(rec, joiner, trigger_s, time_s):
    """SUB-EXPERIMENT A. From the join trigger to the first instant at which
    EVERY committed flow of the joiner is available by the spec rule."""
    flows = _scored_flows(rec, {joiner})
    if not flows:
        return None, "joiner has no scoreable committed flow"
    per_flow = [_unavailable_spans(fr, time_s) for fr in flows]
    for i, t in enumerate(time_s):
        if t < trigger_s:
            continue
        if all(not un[i] for un in per_flow):
            return t - trigger_s, None
    return None, "never available before the horizon"


def _time_to_stable_cell_s(rec, neighbours, trigger_s, time_s):
    """SUB-EXPERIMENT B. From the join trigger to the last instant at which
    ANY incumbent committed flow was unavailable -- the settling period the
    join imposes on the cell, not on the joiner."""
    flows = _scored_flows(rec, set(neighbours))
    if not flows:
        return None, "no scoreable incumbent flow"
    last_bad_s = None
    for fr in flows:
        un = _unavailable_spans(fr, time_s)
        for i, t in enumerate(time_s):
            if t >= trigger_s and un[i]:
                last_bad_s = t if last_bad_s is None else max(last_bad_s, t)
    if last_bad_s is None:
        return 0.0, None
    return last_bad_s - trigger_s, None


def _manipulation_checks(summary, want_path, n_events, label) -> dict:
    """EVERY firing count, asserted BEFORE any number above is read. RA, SRB
    and sched_inactive each get one; a mechanism that reports zero where the
    scenario calls for it is unwired, and its numbers are not results."""
    ra = summary.get("random_access")
    srb = summary.get("srb")
    sc_c = summary.get("scheduler_counters") or {}
    if ra is None or srb is None:
        raise AssertionError(f"{label}: RA/SRB summary missing -- not wired")
    kinds = ra["by_kind"]
    if want_path == "cold" and kinds["cold"]["completed"] != n_events:
        raise AssertionError(f"{label}: {kinds['cold']['completed']} cold RAs "
                             f"for {n_events} scheduled attaches -- {kinds}")
    if want_path == "reestablish" and (kinds["reestablish"]["completed"]
                                       + kinds["cold"]["completed"]) < n_events:
        raise AssertionError(f"{label}: {kinds} RAs for {n_events} RLF events")
    if want_path == "warm" and kinds["cold"]["requested"]:
        raise AssertionError(f"{label}: attach RA on the warm path -- {kinds}")
    if want_path != "warm" and srb["srb_steps_sent"] == 0:
        raise AssertionError(f"{label}: zero SRB dialogue steps on {want_path}")
    if ra["ra_active_at_end"] or srb["srb_active_at_end"]:
        raise AssertionError(f"{label}: RA/SRB still running at the horizon "
                             f"-- a stall, not a sample")
    return {"ra_completed_by_kind": {k: v["completed"] for k, v in kinds.items()},
            "ra_failed": ra["ra_failed"], "ra_latency_p95_ms": ra["ra_latency_ms"]["p95"],
            "srb_steps": srb["srb_steps_sent"],
            "srb_dialogue_p95_ms": srb["srb_dialogue_ms"]["p95"],
            "sched_inactive_fired": sc_c.get("sched_inactive_fired", 0),
            "srb_floor_fired": sc_c.get("srb_floor_fired", 0),
            "cp_floor_fired": sc_c.get("cp_floor_fired", 0),
            "has_srb_decisive": sc_c.get("has_srb_decisive", 0)}


def _build(case, total_ues, committed_mult, seed, intervals, horizon):
    builder, want_path = CASES[case]
    kw = dict(seed=seed, n_neighbours=total_ues - 1, committed_mult=committed_mult)
    if horizon:
        kw["horizon_slots"] = horizon
    sc = builder(**kw)
    return with_survival_times(with_srb(sc), intervals), want_path


def one(task: tuple) -> dict:
    (case, arm, seed, total_ues, committed_mult, rejoin_seed,
     intervals, horizon, cap) = task
    sc, want_path = _build(case, total_ues, committed_mult, seed, intervals, horizon)
    joiner, neighbours = joiner_ue_id(sc), neighbour_ue_ids(sc)
    label = f"{case}/{arm}/n{total_ues}/cm{committed_mult:g}/seed{seed}"
    ra_cfg = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    factory = _arms()[arm]

    t0 = time.time()
    s = run(sc, factory(), cqi_delay_slots=CQI_DELAY_SLOTS, record_timeseries=True,
            rejoin_seed_bsr=rejoin_seed, random_access=ra_cfg, max_sched_ues=cap)
    wall_joiner = time.time() - t0
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm, seed=seed,
                                 flow_configs=sc.flows, summary=s, arm={}, meta={})
    events = [e for e in (rec.join_events or []) if e.path == want_path]
    checks = _manipulation_checks(s, want_path, len(events), label)

    time_s = rec.timeseries_time_s or []
    trigger_s = min((e.trigger_ts_s for e in events), default=None)
    n_never_completed = sum(1 for e in events if e.attached_ts_s is None)

    if trigger_s is None:
        gate = {"broken": None, "reason": "no join event fired"}
        first_service_s = stable_s = None
        first_reason = "no join event fired"
        stable_reason = first_reason
    else:
        gate = _cell_broken_pre_join(rec, neighbours, trigger_s, time_s)
        first_service_s, first_reason = _time_to_first_service_s(rec, joiner, trigger_s, time_s)
        stable_s, stable_reason = _time_to_stable_cell_s(rec, neighbours, trigger_s, time_s)

    # The paired control: same seed, same fleet, NO join schedule -- so the
    # neighbours delta is within-seed, the only form that can attribute.
    ctl_sc = dataclasses.replace(
        sc, ues=[dataclasses.replace(u, join=None, scripted_fade=()) for u in sc.ues],
        name=sc.name + "_control")
    t1 = time.time()
    ctl_s = run(ctl_sc, factory(), cqi_delay_slots=CQI_DELAY_SLOTS, record_timeseries=True,
                rejoin_seed_bsr=rejoin_seed, random_access=ra_cfg, max_sched_ues=cap)
    wall_control = time.time() - t1
    ctl = RunRecord.from_summary(scenario_name=ctl_sc.name, scheduler_name=arm, seed=seed,
                                 flow_configs=ctl_sc.flows, summary=ctl_s, arm={}, meta={})

    def worst_p98(r):
        return max((fr.delay_p98_ms for fr in _scored_flows(r, set(neighbours))), default=0.0)

    return {
        "case": case, "arm": arm, "seed": seed, "total_ues": total_ues,
        "committed_mult": committed_mult, "rejoin_seed": rejoin_seed,
        "n_events": len(events), "n_never_completed": n_never_completed,
        "cell_broken_pre_join": gate,
        "time_to_first_service_s": first_service_s, "first_service_reason": first_reason,
        "time_to_stable_cell_s": stable_s, "stable_reason": stable_reason,
        "attach_s": (statistics.median([(e.attached_ts_s - e.trigger_ts_s)
                                        for e in events if e.attached_ts_s is not None])
                     if any(e.attached_ts_s is not None for e in events) else None),
        "nb_dp98_ms": worst_p98(rec) - worst_p98(ctl),
        "checks": checks,
        "wall_s": round(wall_joiner + wall_control, 2),
    }


def _verdict(rows: list[dict], epsilon_ms: float) -> dict:
    """THE YIELD RULE, applied uniformly: 9 of 10 seeds pass AND no failing
    seed is catastrophic. A seed slightly over a bound is tail variance; a
    seed that never completes is a mechanism, and one is enough to fail."""
    n = len(rows)
    broken = [r for r in rows if (r["cell_broken_pre_join"] or {}).get("broken")]
    catastrophic = [r for r in rows
                    if r["n_never_completed"] > 0 or r["time_to_first_service_s"] is None]
    case = rows[0]["case"]
    if case == "cold":
        passed = [r for r in rows if r["attach_s"] is not None
                  and r["attach_s"] <= COLD_ATTACH_BOUND_S]
    else:
        # warm / post-RLF: the spec rule -- available again, by TS 122 261.
        passed = [r for r in rows if r["time_to_first_service_s"] is not None]
    nb_ok = [r for r in rows if abs(r["nb_dp98_ms"]) <= epsilon_ms]
    if len(broken) > n // 2:
        outcome = "CELL ALREADY BROKEN"
    elif len(passed) >= max(1, int(0.9 * n)) and not catastrophic:
        outcome = "PASS"
    else:
        outcome = "JOIN FAILURE"
    return {
        "outcome": outcome, "n_seeds": n,
        "pass_rate": f"{len(passed)}/{n}",
        "cell_broken_seeds": len(broken),
        "catastrophic_seeds": len(catastrophic),
        "neighbours_within_eps": f"{len(nb_ok)}/{n}",
        "first_service_p50_s": (statistics.median(fs)
                                if (fs := [r["time_to_first_service_s"] for r in rows
                                           if r["time_to_first_service_s"] is not None])
                                else None),
        # 0.0 is a RESULT ("the cell never destabilised"), not a missing
        # value -- `median(...) or None` erased it in the first draft.
        "stable_cell_p50_s": (statistics.median(vals)
                              if (vals := [r["time_to_stable_cell_s"] for r in rows
                                           if r["time_to_stable_cell_s"] is not None])
                              else None),
        "attach_p50_s": (statistics.median([r["attach_s"] for r in rows
                                            if r["attach_s"] is not None])
                         if any(r["attach_s"] is not None for r in rows) else None),
        "nb_dp98_ci": bootstrap_ci([r["nb_dp98_ms"] for r in rows], seed=4243),
        "checks_total": {k: sum(r["checks"].get(k, 0) or 0 for r in rows)
                         for k in ("sched_inactive_fired", "srb_floor_fired",
                                   "cp_floor_fired", "has_srb_decisive",
                                   "srb_steps", "ra_failed")},
        "wall_s_total": round(sum(r["wall_s"] for r in rows), 1),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--cases", default="warm,cold,rlf")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--intervals", type=float, default=1.0,
                    help="survival time in transfer intervals (CHOSEN, swept)")
    ap.add_argument("--horizon", type=int, default=0, help="0 = each builder's own")
    ap.add_argument("--cap", type=int, default=4, help="M-6 max_sched_ues")
    ap.add_argument("--rejoin-seed", default="off,on",
                    help="which columns to run; both are declared in the report")
    ap.add_argument("--occupancy", default="",
                    help="override the axis, as 'ues:mult,ues:mult'")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default="sweeps/g9-stress/g9_stress.json")
    a = ap.parse_args(argv[1:])

    arms = [x for x in a.arms.split(",") if x]
    cases = [x for x in a.cases.split(",") if x]
    seeds = paired_seeds(a.seeds)
    columns = [x == "on" for x in a.rejoin_seed.split(",") if x]
    axis = (tuple((int(p.split(":")[0]), float(p.split(":")[1]))
                  for p in a.occupancy.split(",")) if a.occupancy else OCCUPANCY)

    tasks = [(case, arm, seed, ues, mult, col, a.intervals, a.horizon, a.cap)
             for col in columns for case in cases for (ues, mult) in axis
             for arm in arms for seed in seeds]
    print(f"{len(tasks)} runs = {len(columns)} seed-columns x {len(cases)} cases "
          f"x {len(axis)} occupancy levels x {len(arms)} arms x {len(seeds)} seeds "
          f"(each run also builds its paired control)", flush=True)

    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # The unit key is DERIVED from the row's own fields (RunLedger's
    # key_fields), not hand-listed at the call site -- the defect the ledger
    # key fix of 2026-09-06 was about.
    key_fields = ("case", "arm", "seed", "total_ues", "committed_mult", "rejoin_seed")
    ledger = RunLedger(out_path.with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "occupancy": [list(x) for x in axis]},
                       key_fields)
    done = ledger.done_keys()
    rows: list[dict] = list(ledger.banked())
    todo = [t for t in tasks
            if (t[0], t[1], t[2], t[3], t[4], t[5]) not in done]
    print(f"  {len(rows)} banked, {len(todo)} to run", flush=True)

    t_start = time.time()
    for i, r in run_cells(one, todo, a.workers, cost=lambda t: arm_cost(t[1])):
        rows.append(r)
        ledger.bank(r)
        if len(rows) % 25 == 0:
            print(f"    ... {len(rows)}/{len(tasks)} "
                  f"({time.time() - t_start:.0f}s)", flush=True)
    wall = time.time() - t_start

    doc: dict = {"_axis": [list(x) for x in axis], "_seeds": a.seeds,
                 "_intervals": a.intervals, "_cap": a.cap,
                 "_neighbour_epsilon_ms": list(NEIGHBOUR_EPSILON_MS),
                 "_wall_s": round(wall, 1), "_n_runs": len(rows),
                 "_mean_wall_s_per_run": round(
                     sum(r["wall_s"] for r in rows) / max(1, len(rows)), 2)}
    for col in columns:
        for case in cases:
            for (ues, mult) in axis:
                for arm in arms:
                    group = [r for r in rows
                             if r["case"] == case and r["arm"] == arm
                             and r["total_ues"] == ues and r["rejoin_seed"] == col]
                    if not group:
                        continue
                    key = f"{'seeded' if col else 'unseeded'}/{case}/n{ues}_cm{mult:g}/{arm}"
                    doc[key] = {eps_key: _verdict(group, eps)
                                for eps_key, eps in
                                [(f"eps{e:g}ms", e) for e in NEIGHBOUR_EPSILON_MS]}
    out_path.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nwrote {out_path}  ({wall:.0f}s wall, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
