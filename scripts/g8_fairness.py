"""G8 / GT-5.1 -- equal robots, equal service, continuously.

THE CLAUSE (`docs/IA_P5G_Factory_Guarantee_Test_Plan.md`, G8 row + GT-5.1),
scored as the FOUR conjuncts it actually is:

  part 1  per-1 s Jain >= 0.9 for every scoreable ROLE
  part 2  zero starvation epochs >= 1 s, over flows that can express one
  part 3  zero telemetry gaps >= 1 s
  part 4  per-window GFBR floor holds

WHY A CONJUNCTION AND NOT JUST JAIN. `Scorecard._m22_starvation_epochs`
records the reason in its own docstring: M09 scores `delivered / arrived`
with a hardcoded **1.0 when `arrived == 0`**, so a flow delivering nothing
reads as PERFECTLY FAIR exactly when it is most starved. Jain alone cannot
fail on the case the guarantee is about. This runner therefore reports the
starvation count beside it AND counts the padded seconds
(`jain_padded_seconds`) so a reader can see how much of a Jain number is
that convention rather than measurement.

WHICH "ROLE". `sim/scenarios/g8.py`'s docstring has the full note; the short
version is that `completion_ts_by_role_s` is a PDU-set message role and G8
means the UE's FLEET role, which only `sim.fleet.build_fleet` knows. The
scenario builder returns that map and this runner joins on
`FlowRecord.ue_id`. M09's own description asks for exactly this -- "pass a
same-role flow subset upstream if that's what the guarantee needs" -- so
part 1 is folded here and M09 is reported only as a pooled comparison.

WHY THE AXIS STARTS AT N=8. Measured while building this: `mixed` at N=4
allocates one UE per role, and a Jain index over one flow is 1.0 by
construction -- the clause could not fail. `assert_g8_is_scoreable` refuses
such a cell and the cell is excluded WHOLE and named, never silently scored.

WHY PART 2 RESTRICTS THE POPULATION, AND WHY M22 IS STILL REPORTED RAW.
M22's panel caveat says it counts DELIVERY silence and therefore over-counts
"a duty-cycled or activation-gated source". Measured on the first smoke run
of this runner: every epoch belonged to such a source -- `ue2_qfi85`, the
emergency-STOP bearer, logged a 2.26 s "starvation" on **two arrivals in the
whole run**, and a 5QI-82 bearer three more on five. A flow that offered
twice cannot have been starved; that is its duty cycle. Part 2 therefore
scores only flows dense enough to express starvation -- see
`MIN_ARRIVAL_DENSITY` for the measured reason a COUNT of arrival-seconds
does not work -- so a 1 s delivery silence is evidence about the SCHEDULER. The
unmodified panel number travels beside it as `m22_epochs_raw`, because
narrowing a pre-registered metric's population inside a runner and then
reporting only the narrowed value is how a guard quietly stops guarding.

PART 4 IS REPORTED TWICE ON PURPOSE, AND THE TOLERANCE IS DERIVED.
G5's part 3 uses `floor >= 1.0`, zero tolerance, on the minimum over
windows. Measured on the 2026-09-16 campaign, over 152 rows at N <= 8 whose
frame delivery is otherwise perfect (p1 AND p2 pass), that clause admits
**22 %** of them; the 1st percentile floor is 0.9796 and the median 0.9961.
A windowed ratio wobbles because frame sizes vary and bytes straddle a
window edge. So the STRICT clause is the verdict (fidelity to the plan) and
`part4_tolerant` reads the same floor at `WINDOW_FLOOR_TOLERANCE`, set at
the observed noise floor of healthy runs -- 0.98 admits 98 % of them while
TwoTier's genuine failure (floor 0.6039) is still caught. Chosen from the
distribution, not to make an arm pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from regime_sweep import (RunLedger, arm_cost, invocation_config,  # noqa: E402
                          paired_seeds, run_cells)
from proto_arms import resolve_arm, split_cg                        # noqa: E402
from sim.driver import run as driver_run                            # noqa: E402
from sim.run_record import RunRecord                                # noqa: E402
from sim.scenarios import deployed_cell as _dcell                   # noqa: E402
from sim.scenarios.g8 import (assert_g8_is_scoreable,               # noqa: E402
                              build_g8_scenario, roles_for)
from sim.scorecard import (Population, Scorecard,                   # noqa: E402
                           _bucket_by_second, _jain)

#: The value every real study in this branch runs with -- not the driver's
#: bare 0 default (CLAUDE.md: `cqi_delay_slots` is load-bearing).
CQI_DELAY_SLOTS = 8

#: GT-5.1's own numbers, cited rather than invented.
JAIN_BOUND = 0.9                 #: "per-1 s Jain >= 0.9 per role"
STARVATION_EPOCH_S = 1.0         #: "zero starvation epochs >= 1 s"
TELEMETRY_GAP_MS = 1000.0        #: "zero windows where ... telemetry gap >= 1 s"

#: ELIGIBILITY FOR PART 2, and it takes TWO conditions because one is not
#: enough. MEASURED, not assumed (PF+CG, mixed, N=8, 20 s horizon):
#:
#:     flow        density  active_s  epochs  longest
#:     ue2_qfi85     0.500       8        3    3.16s   <- 0.2 Hz STOP events
#:     ue5_qfi82     1.000      20        6    1.01s   <- REAL starvation
#:     ue1_qfi85     1.000       1        0       -    <- one event, span 1 s
#:
#: A COUNT of arrival-seconds does not separate these. At a 5 s horizon the
#: STOP bearer had 2 arrival-seconds and was excluded; at 20 s it had 4 and
#: was not -- the count rule re-breaks at every longer horizon, which is this
#: project's own trap of a guard that is itself degenerate. DENSITY -- the
#: fraction of seconds inside the flow's active span in which it offered
#: anything -- is horizon-invariant and cleanly separates 0.500 from 1.000.
#: Density ALONE is not enough either: `ue1_qfi85` scores 1.000 over a single
#: second, so a minimum span is required as well.
#:
#: `ue5_qfi82` stays scored, and SHOULD. A bearer that offered in every one
#: of 20 seconds and went 1.01 s undelivered is starved; part 2 is meant to
#: fail on exactly that, and the point of the rule is to remove the flows
#: that cannot express starvation, never the ones that do.
MIN_ARRIVAL_DENSITY = 0.75
MIN_ACTIVE_SPAN_S = 5.0

#: AND THE THIRD CONDITION, which the first production run forced.
#: `ue5_qfi82` is `periodic_control` at `period_ms = 1000`: it arrives 64 B
#: once per second and was DELIVERED 64 B in that same second, 20 of 20 --
#: no starvation at all. But a 1 Hz source leaves ~1 s of zero-delivery
#: buckets BETWEEN its bursts, so a >= 1 s epoch fires on it by construction.
#: It was the worst flow in 69 of 70 runs of the lightest cell, on every arm,
#: with a longest silence of 1.00-1.01 s -- pinned exactly on the bound.
#:
#: Density cannot catch this (density is 1.0: the flow does offer every
#: second). The discriminator is the source's own INTER-ARRIVAL PERIOD, and
#: it is derived from the arrival series rather than read from config, so it
#: needs no per-scenario knowledge. A flow whose typical gap between
#: arrivals is itself a sizeable fraction of the epoch cannot distinguish
#: "starved" from "idle by design", so it is not scored.
#:
#: This is CLAUDE.md's threshold-on-a-quantised-value rule: the fix is to
#: threshold in the units the MECHANISM works in, never to nudge the operator.
MAX_SOURCE_PERIOD_S = STARVATION_EPOCH_S / 2.0

#: Part 4's second reading. NOT the verdict; RE-DERIVED at this runner's own
#: 20 s horizon after the first production run, because a tolerance carried
#: over from G5's 5 s / 5-window data does not transfer: more windows means a
#: harsher minimum, and here the floor's MAXIMUM at the healthiest cell is
#: 0.9870, so strict `>= 1.0` admits 0 of 630. Measured pass rates, healthy
#: cell (N=8 x1.0) against overloaded (N=12 x1.5):
#:
#:     tol 1.00   healthy   0/70   overloaded 0/70   <- unusable
#:     tol 0.98   healthy  68/70   overloaded 0/70
#:     tol 0.97   healthy  70/70   overloaded 0/70   <- clean separation
#:
#: 0.97 admits every demonstrably-healthy run and rejects every overloaded
#: one. Chosen for that separation, not to make any arm pass.
WINDOW_FLOOR_TOLERANCE = 0.97

#: 20 s. A guarantee about CONTINUOUS service cannot be scored on the 5 s
#: every other builder defaults to: at 5 s a 1 s epoch is a fifth of the run
#: and a 0.2 Hz source contributes one event. Derived through `slots()`,
#: never a slot literal.
HORIZON_MS = 20_000.0

#: Fleet axis. Starts at 8 because N=4 has no role with >= 2 UEs and so
#: cannot fail part 1; see the builder's guard.
UE_AXIS = (8, 12, 16)

#: Promised-load axis. GT-5.1 wants both assets driven ABOVE the contention
#: ceiling or the fairness question is vacuous; G10's admissible fleet on
#: this cell with CG is 8, so x1.5 and x2.0 are genuinely past it.
LOAD_AXIS = (1.0, 1.5, 2.0)


def _telemetry_keys(rec: RunRecord) -> list[str]:
    """UL Delay-class flows -- the heartbeat population part 3 is about.

    Selected by CLASS and recorded in the row, never assumed: an empty
    selection scoring "zero gaps" is this project's most repeated defect, so
    the caller asserts the list is non-empty and the row carries it.
    """
    return sorted(k for k, fr in rec.flows.items()
                  if fr.direction == "UL" and fr.flow_class == "Delay")


def _worst_gap_ms(rec: RunRecord, keys: list[str]) -> tuple[float, int]:
    """Worst inter-completion gap over `keys`, and how many flows were silent.

    A flow with fewer than two completions has no gap to measure and is
    counted as SILENT rather than skipped -- G1's lesson: excluding a flow
    that received nothing turns a failure into a comfortable number.
    """
    worst, silent = 0.0, 0
    for k in keys:
        fr = rec.flows.get(k)
        ts: list[float] = []
        for lst in (getattr(fr, "completion_ts_by_role_s", None) or {}).values():
            ts.extend(lst)
        ts.sort()
        if len(ts) < 2:
            silent += 1
            continue
        for a, b in zip(ts, ts[1:]):
            worst = max(worst, (b - a) * 1000.0)
    return worst, silent


def _scored_starvation(rec: RunRecord) -> dict[str, Any]:
    """Starvation epochs over flows that can actually express one.

    Same arithmetic as `Scorecard._m22_starvation_epochs` -- runs of
    consecutive zero-delivery buckets bounded to a flow's own first..last
    arrival -- restricted to the protected fleet AND to flows offering in at
    least `MIN_ARRIVAL_SECONDS` distinct seconds. Flows dropped by that rule
    are NAMED in the row, so the restriction is auditable rather than a
    silent narrowing.
    """
    scoped = Population.protected_fleet().restrict(rec)
    time_s = scoped.timeseries_time_s or []
    if len(time_s) < 2:
        return {"epochs": None, "worst_flow": None, "longest_s": None,
                "flows_scored": 0, "flows_too_sparse": []}
    dt = time_s[1] - time_s[0]
    need = max(1, int(round(STARVATION_EPOCH_S / dt))) if dt > 0 else 1

    total, longest, worst_flow = 0, 0, None
    scored, sparse = 0, []
    for key, fr in scoped.flows.items():
        arr, dlv = fr.ts_arrived_bytes, fr.ts_delivered_bytes
        if not arr or not dlv:
            continue
        live = [i for i, a in enumerate(arr) if a > 0]
        if not live:
            continue
        arrival_seconds = len({int(time_s[i]) for i in live})
        active_span_s = max(
            1, int(time_s[live[-1]]) - int(time_s[live[0]]) + 1)
        density = arrival_seconds / active_span_s
        # The source's own cadence, read off the series: the median gap
        # between consecutive arrival buckets. A 1 Hz source gives 1.0 s here
        # however dense its per-second offering looks.
        gaps = [live[j + 1] - live[j] for j in range(len(live) - 1)]
        period_s = (sorted(gaps)[len(gaps) // 2] * dt) if gaps else 0.0
        if (active_span_s < MIN_ACTIVE_SPAN_S
                or density < MIN_ARRIVAL_DENSITY
                or period_s > MAX_SOURCE_PERIOD_S):
            sparse.append([key, round(density, 3), active_span_s,
                           round(period_s, 4)])
            continue
        scored += 1
        run_len = 0
        for i in range(live[0], live[-1] + 1):
            if dlv[i] == 0:
                run_len += 1
                continue
            if run_len >= need:
                total += 1
                if run_len > longest:
                    longest, worst_flow = run_len, key
            run_len = 0
        if run_len >= need:
            total += 1
            if run_len > longest:
                longest, worst_flow = run_len, key
    return {"epochs": total, "worst_flow": worst_flow,
            "longest_s": round(longest * dt, 3), "flows_scored": scored,
            "flows_too_sparse": sorted(sparse)}


def _per_role_jain(rec: RunRecord, roles: dict[int, str],
                   min_ues: int = 2) -> tuple[dict[str, float], int, int]:
    """Worst per-second Jain within each role: `{role: min over seconds}`.

    Returns the map, the number of (flow, second) pairs where `arrived == 0`
    and the ratio was padded to 1.0 (M09's convention, kept so the two
    numbers stay comparable), and the number of roles scored.
    """
    # THE PROTECTED FLEET, NOT EVERY FLOW. The first production run scored
    # this over the unscoped record and produced a false headline: at N=8
    # x1.5 the ConfigSched family read Jain 0.7500 while PF read 0.9996, and
    # the worst second's ratios show BOTH zeros were 5QI 9 -- the best-effort
    # filler a QoS-aware scheduler is SUPPOSED to starve. `Population`'s own
    # docstring records exactly this case ("G8's TwoTier FAILs all-flow at
    # Jain 0.8783 and passes protected at 0.9584"). Scoring fairness over a
    # population that includes the sacrificial class penalises the arms doing
    # the right thing.
    rec = Population.protected_fleet().restrict(rec)
    time_s = rec.timeseries_time_s or []
    if len(time_s) < 2:
        return {}, 0, 0
    by_role: dict[str, list] = {}
    for fr in rec.flows.values():
        if fr.ts_delivered_bytes is None or fr.ts_arrived_bytes is None:
            continue
        role = roles.get(fr.ue_id)
        if role is None:
            continue
        by_role.setdefault(role, []).append(fr)

    out: dict[str, float] = {}
    padded = 0
    for role, frs in by_role.items():
        if len({fr.ue_id for fr in frs}) < min_ues:
            continue                      # a one-UE role cannot be unfair
        per_sec: dict[int, list[float]] = {}
        for fr in frs:
            dlv = _bucket_by_second(time_s, fr.ts_delivered_bytes)
            arr = _bucket_by_second(time_s, fr.ts_arrived_bytes)
            for sec, dl in dlv.items():
                delivered = sum(dl)
                arrived = sum(arr.get(sec, []))
                if arrived <= 0:
                    padded += 1
                    ratio = 1.0
                else:
                    ratio = delivered / arrived
                per_sec.setdefault(sec, []).append(ratio)
        js = [j for j in (_jain(v) for v in per_sec.values()) if j is not None]
        if js:
            out[role] = min(js)
    return out, padded, len(out)


def one(arm: str, seed: int, n_ues: int, composition: str,
        committed_mult: float, cap: int, horizon: int) -> dict[str, Any]:
    t0 = time.time()
    sc, roles = build_g8_scenario(composition=composition, n_ues=n_ues,
                                  seed=seed, committed_mult=committed_mult,
                                  horizon_slots=horizon)
    base_arm, cg_cfg = split_cg(arm)        # "PF+CG": the suffix is the label
    s = driver_run(sc, resolve_arm(base_arm), cqi_delay_slots=CQI_DELAY_SLOTS,
                   record_timeseries=True, max_sched_ues=cap,
                   configured_grant=cg_cfg)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows, summary=s,
                                 arm={}, meta={})
    scored = Scorecard().score(rec, population=Population.protected_fleet())

    # --- part 1: per-role per-second Jain
    jain_by_role, padded, n_roles = _per_role_jain(rec, roles)
    worst_role = min(jain_by_role, key=jain_by_role.get) if jain_by_role else None
    jain_worst = jain_by_role.get(worst_role) if worst_role else None

    # --- part 2: starvation, restricted; the raw panel number travels too
    starv = _scored_starvation(rec)
    m22 = (scored.get("M22").value if scored.get("M22") else None) or {}

    # --- part 3: telemetry liveness
    tele_keys = _telemetry_keys(rec)
    tele_gap_ms, tele_silent = _worst_gap_ms(rec, tele_keys)

    # --- part 4: windowed GFBR floor (M23), strict AND tolerant
    m23 = (scored.get("M23").value if scored.get("M23") else None) or {}
    window_floor = m23.get("fraction")

    # M09 for comparison only -- it pools every flow, so it is NOT part 1.
    m09v = (scored.get("M09").value if scored.get("M09") else None) or {}

    return {
        "arm": arm, "seed": seed, "n_ues": n_ues, "composition": composition,
        "committed_mult": committed_mult, "cap": cap,
        "horizon": sc.horizon_slots,

        "jain_by_role": {k: round(v, 6) for k, v in jain_by_role.items()},
        "jain_worst": jain_worst, "jain_worst_role": worst_role,
        "n_roles_scored": n_roles, "jain_padded_seconds": padded,
        "jain_pooled_worst": m09v.get("worst"),
        "jain_pooled_mean": m09v.get("mean"),
        "part1_pass": bool(jain_worst is not None and jain_worst >= JAIN_BOUND),

        "starvation_epochs": starv["epochs"],
        "starvation_worst_flow": starv["worst_flow"],
        "starvation_longest_s": starv["longest_s"],
        "starvation_flows_scored": starv["flows_scored"],
        "starvation_flows_too_sparse": starv["flows_too_sparse"],
        "m22_epochs_raw": m22.get("epochs"),
        "m22_worst_flow_raw": m22.get("worst_flow"),
        "part2_pass": bool(starv["epochs"] == 0),

        "tele_keys": tele_keys, "tele_gap_worst_ms": tele_gap_ms,
        "tele_silent": tele_silent,
        "part3_pass": bool(tele_keys and tele_silent == 0
                           and tele_gap_ms < TELEMETRY_GAP_MS),

        "window_floor": window_floor, "window_floor_flow": m23.get("flow"),
        "part4_pass": bool(window_floor is not None and window_floor >= 1.0),
        "part4_tolerant": bool(window_floor is not None
                               and window_floor >= WINDOW_FLOOR_TOLERANCE),

        "wall_s": round(time.time() - t0, 2),
    }


def _task(t):
    return one(*t)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="G8 / GT-5.1 fleet fairness")
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--compositions", default="mixed")
    ap.add_argument("--n-ues", default=",".join(str(x) for x in UE_AXIS))
    ap.add_argument("--load-axis", default=",".join(str(x) for x in LOAD_AXIS))
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--cap", type=int, default=4, help="M-6 max_sched_ues")
    ap.add_argument("--horizon-ms", type=float, default=HORIZON_MS)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default="sweeps/g8-fairness/g8_fairness.json")
    a = ap.parse_args(argv[1:])

    arms = [s.strip() for s in a.arms.split(",") if s.strip()]
    comps = [s.strip() for s in a.compositions.split(",") if s.strip()]
    ns = [int(s) for s in a.n_ues.split(",") if s.strip()]
    loads = [float(s) for s in a.load_axis.split(",") if s.strip()]
    seeds = paired_seeds(a.seeds, base_seed=a.seed_base)
    horizon = _dcell.slots(a.horizon_ms)

    # EXCLUDE UNSCOREABLE CELLS WHOLE, AND SAY SO. A cell where no role has
    # two UEs cannot fail part 1; scoring it would add a guaranteed pass.
    kept: list[tuple[str, int]] = []
    for comp in comps:
        for n in ns:
            try:
                assert_g8_is_scoreable(roles_for(n, comp))
            except ValueError as exc:
                print(f"  EXCLUDED {comp}:N={n} -- {exc}", flush=True)
                continue
            kept.append((comp, n))
    if not kept:
        raise SystemExit("every requested cell is unscoreable; nothing to run")

    tasks = [(arm, seed, n, comp, mult, a.cap, horizon)
             for (comp, n) in kept for mult in loads
             for arm in arms for seed in seeds]

    out_path = Path(a.out)
    ledger = RunLedger(out_path.with_suffix(".runs.jsonl"),
                       invocation_config(a),
                       ("arm", "seed", "n_ues", "composition",
                        "committed_mult", "cap"))
    done = ledger.done_keys()
    todo = [t for t in tasks if (t[0], t[1], t[2], t[3], t[4], t[5]) not in done]
    print(f"G8 / GT-5.1: {len(tasks)} runs = {len(kept)} cells x {len(loads)} "
          f"loads x {len(arms)} arms x {len(seeds)} seeds; "
          f"{len(tasks) - len(todo)} banked, {len(todo)} to run", flush=True)
    print(f"  horizon {a.horizon_ms:g} ms = {horizon} slots; bounds: Jain >= "
          f"{JAIN_BOUND} per role, 0 starvation epochs >= {STARVATION_EPOCH_S}s "
          f"(flows with arrival density >= {MIN_ARRIVAL_DENSITY} over a span "
          f">= {MIN_ACTIVE_SPAN_S:g}s and source period "
          f"<= {MAX_SOURCE_PERIOD_S:g}s), "
          f"telemetry gap < {TELEMETRY_GAP_MS}ms, window floor >= 1.0 "
          f"(tolerant reading at {WINDOW_FLOOR_TOLERANCE})", flush=True)

    t0 = time.time()
    for i, (_idx, row) in enumerate(run_cells(
            _task, todo, a.workers,
            cost=lambda t: arm_cost(t[0], t[2], 1)), start=1):
        ledger.bank(row)
        if i % 25 == 0 or i == len(todo):
            print(f"    ... {i}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    rows = ledger.banked()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "_clause": "G8 / GT-5.1",
        "_jain_bound": JAIN_BOUND,
        "_starvation_epoch_s": STARVATION_EPOCH_S,
        "_min_arrival_density": MIN_ARRIVAL_DENSITY,
        "_min_active_span_s": MIN_ACTIVE_SPAN_S,
        "_max_source_period_s": MAX_SOURCE_PERIOD_S,
        "_jain_population": "protected_fleet",
        "_telemetry_gap_ms": TELEMETRY_GAP_MS,
        "_window_floor_tolerance": WINDOW_FLOOR_TOLERANCE,
        "_horizon_ms": a.horizon_ms, "_horizon_slots": horizon,
        "_cap": a.cap, "_seeds": a.seeds, "_cells": [list(c) for c in kept],
        "_load_axis": loads, "_n_runs": len(rows),
        "_wall_s": round(time.time() - t0, 1),
        "rows": rows,
    }, indent=1))
    print(f"wrote {out_path}  ({time.time() - t0:.0f}s, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
