"""G12's overload-degradation campaign (docs/wp9-plan.md §35, commit 3).

Scores E1-E5. **The report is deliberately split into two regions and the
IN-RANGE one is printed first**, because they answer different questions and
the second is currently not a scheduler result at all (§35.13):

  REGION 1 -- inside GT-7.3's own ramp (<= 145 % of the measured ceiling).
      This is the PRIMARY finding. If only one GBR class breaches here, the
      guarantee's specified degradation order cannot be observed at the load
      the guarantee itself specifies -- a statement about the TEST, not
      about any scheduler.

  REGION 2 -- beyond 145 %, reported under its own heading and NEVER without
      the permutation control beside it. §35.5 measured the canonical
      declaration order and a permuted one giving OPPOSITE first-violation
      orders on the same workload, so an ordering read off one flow-list
      order is not yet a property of any scheduler.

Three assertions run before any order is read, and the runner refuses to
report if any fails:

  1. THE CELL IS SCOREABLE (§35.7 case 1). `sensor_dense` allocates 3 %
     UGVs, so at N=4/8 it carries no 5QI 4 flow at all and can only produce
     a one-element "order" that reads like a result. Excluded BY NAME, with
     the exclusion derived from `build_fleet` rather than restated.
  2. THE RAMP'S BOTTOM IS CLEAN (§35.7 case 2, and E1's control). A class
     breaching at ramp index 0 means the ramp measures provisioning, not
     overload -- stage 5's duty-cycled lidar and the test plan's own
     telemetry GFBR are both recorded instances.
  3. THE POPULATION IS CONSTANT ACROSS THE RAMP (§35.8). c2a9f13's lesson
     moved from events to violations: an arm whose ramp points carry
     different GBR flow populations is not a smaller sample of the same
     thing, and comparing it to a full one compares two things.

Usage:
    uv run python scripts/g12_campaign.py [--smoke] [--seeds N] [--time-cell]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import paired_seeds  # noqa: E402
from scheduler import load_two_tier  # noqa: E402
from scheduler.reservation import Reservation  # noqa: E402
from sim.baselines.pf import ProportionalFair  # noqa: E402
from sim.driver import run  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.scenarios.g12 import (GBR_CLASSES, GUARANTEE_RAMP_TOP_MULT,  # noqa: E402
                               QFI_BG, RAMP, assert_cell_is_scoreable,
                               assert_order_non_degenerate,
                               assert_ramp_bottom_clean, build_g12_scenario,
                               class_of, gbr_flow_census, permute_flows)
from sim.scorecard import Scorecard  # noqa: E402

_TT = str(Path(__file__).resolve().parent.parent / "scheduler"
          / "scheduler_config.yaml")
CQI_DELAY_SLOTS = 8
HORIZON_SLOTS = 20_000
QFI_TELEMETRY = 1                     # G12's clause 4, "never 5QI 1"

# Candidate cells. Which of these are actually SCOREABLE is derived from
# build_fleet at launch (`scoreable_cells`), never listed here -- the
# count-in-prose rule this project has been bitten by four times.
CANDIDATE_COMPOSITIONS = ("mixed", "ugv_heavy", "drone_heavy", "sensor_dense")
CANDIDATE_N_UES = (8,)

# D4's control. Four permutations at the reference cell: enough to say
# whether the order is stable under reordering, not enough to characterise
# a distribution over permutations -- and the write-up must not claim the
# latter (§35.13).
PERMUTATION_SEEDS = (101, 102, 103, 104)
REFERENCE_CELL = ("mixed", 8)


def _arms() -> dict:
    return {
        "PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": lambda: Reservation(min_rb=5),
        "TwoTier": lambda: load_two_tier(_TT, min_rb=5),
    }


# --- cell selection, derived ---------------------------------------------

def scoreable_cells() -> tuple[list[tuple[str, int]], list[tuple[tuple, str]]]:
    """Which candidate cells can produce an ordering at all.

    Computed by BUILDING each cell and asking `assert_cell_is_scoreable`,
    so the exclusion list cannot drift from `sim/fleet.py`'s allocation.
    Returns (kept, excluded_with_reason) and the caller prints both --
    an exclusion that is not printed is indistinguishable from a cell
    nobody thought of.
    """
    kept, excluded = [], []
    for comp in CANDIDATE_COMPOSITIONS:
        for n in CANDIDATE_N_UES:
            sc = build_g12_scenario(n, comp, 1.0, 0, HORIZON_SLOTS)
            try:
                assert_cell_is_scoreable(sc)
            except ValueError as exc:
                excluded.append(((comp, n), str(exc).split(";")[0]))
            else:
                kept.append((comp, n))
    return kept, excluded


# --- one ramp ------------------------------------------------------------

def _project(rec: RunRecord) -> RunRecord:
    """Keep only what M13 reads. CLAUDE.md's 25 GB retention lesson: a ramp
    holds 8 records at once and each is ~18 MB with timeseries, so nothing
    whole is retained past scoring."""
    keep = {k: dataclasses.replace(v, ts_backlog_bytes=None,
                                   ts_hol_delay_s=None,
                                   ts_delivered_bytes=None,
                                   ts_arrived_bytes=None,
                                   ts_dropped_bytes=None,
                                   completion_ts_by_role_s=None,
                                   frame_completions=None)
            for k, v in rec.flows.items() if v.flow_class == "GBR"}
    return dataclasses.replace(rec, flows=keep, timeseries_time_s=None,
                               timeseries_slot_index=None)


def _restricted(rec: RunRecord, qfis: set[int]) -> Optional[RunRecord]:
    """A sub-record over named 5QIs only.

    THE DECOMPOSE RULE, MADE MECHANICAL. M02 byte-weights over every flow
    and M20's max runs over every flow it keeps, so quoting either as a
    statement about telemetry requires the sum to actually be over
    telemetry. §28.1 and §24.2 are two published retractions from not doing
    this."""
    keep = {k: v for k, v in rec.flows.items() if v.qfi in qfis}
    return dataclasses.replace(rec, flows=keep) if keep else None


def run_ramp(comp: str, n_ues: int, arm_name: str, arm_factory, seed: int,
             ramp: tuple[float, ...] = RAMP,
             perm_seed: Optional[int] = None) -> dict[str, Any]:
    """One (cell, arm, seed) swept across the whole ramp.

    `perm_seed` applies the SAME permutation at every ramp point -- a
    permutation that varied along the ramp would not be a controlled
    reordering, it would be noise.
    """
    sc_card = Scorecard()
    census: Optional[dict[int, int]] = None
    projected: list[RunRecord] = []
    per_point: list[dict[str, Any]] = []
    class_map: dict[str, int] = {}

    for mult in ramp:
        sc = build_g12_scenario(n_ues, comp, mult, seed, HORIZON_SLOTS)
        if perm_seed is not None:
            sc = permute_flows(sc, perm_seed)
        got = gbr_flow_census(sc)
        if census is None:
            census = got
        elif got != census:
            raise AssertionError(
                f"{comp}/N={n_ues}/{arm_name}/seed {seed}: GBR flow census "
                f"changed across the ramp, {census} -> {got} at x{mult}. The "
                f"ramp points are not comparable (§35.8).")
        class_map.update(class_of(sc))
        summary = run(sc, arm_factory(), cqi_delay_slots=CQI_DELAY_SLOTS,
                      record_timeseries=True)
        rec = RunRecord.from_summary(
            scenario_name=sc.name, scheduler_name=arm_name, seed=seed,
            flow_configs=sc.flows, summary=summary, arm={},
            meta={"composition": comp, "n_ues": n_ues, "committed_mult": mult})

        # Clause 1: 5QI 9 has no contract, so "exhausted" is a throughput
        # statement and nothing else can carry it.
        bg_bps = sum(fr.throughput_bps for fr in rec.flows.values()
                     if fr.qfi == QFI_BG)
        # Clause 4: GT-7.3's own FAIL example is "telemetry GAP grows while
        # bg still moves bytes", so the instrument is a gap, not a contract.
        tele = _restricted(rec, {QFI_TELEMETRY})
        tele_gap_ms = tele_m02 = None
        if tele is not None:
            gap = sc_card.protected_fleet_liveness_gap(
                tele, non_protected_5qi=frozenset())
            tele_gap_ms = (gap.value or {}).get("max_gap_ms")
            tele_m02 = sc_card._m02_pdb_violation_rate(tele).value
        per_point.append({
            "mult": mult, "bg_bps": bg_bps,
            "telemetry_max_gap_ms": tele_gap_ms, "telemetry_m02": tele_m02,
            "worst_by_class": {
                qi: min((fr.gfbr_fraction() or 0.0)
                        for fr in rec.flows.values()
                        if fr.qfi == qi and fr.flow_class == "GBR")
                for qi in GBR_CLASSES},
        })
        projected.append(_project(rec))
        del rec, summary

    if len(projected) != len(ramp):
        raise AssertionError(
            f"{comp}/{arm_name}/seed {seed}: {len(projected)} ramp points, "
            f"expected {len(ramp)} (§35.8).")
    return {"records": projected, "per_point": per_point,
            "class_map": class_map, "census": census}


def order_for(ramped: dict[str, Any], ramp: tuple[float, ...], label: str,
              allow_one_element: bool) -> dict[str, Any]:
    """M13 over one ramp, plus §35.7's degeneracy classification."""
    sc_card = Scorecard()
    n = len(ramp)
    res = sc_card.first_violation_order(ramped["records"][:n],
                                        ramped["class_map"])
    order = res.value["order_5qi"]
    first_fail = res.value["first_fail_at_index"]
    assert_ramp_bottom_clean(first_fail, label)
    terminal = ramped["per_point"][n - 1]["worst_by_class"]
    verdict = assert_order_non_degenerate(
        order, first_fail, terminal, label,
        allow_one_element=allow_one_element)
    return {"order": list(verdict.order_5qi),
            "first_fail_at_index": verdict.first_fail_at_index,
            "ties": [list(t) for t in verdict.ties],
            "never_failed": list(verdict.never_failed),
            "terminal_fraction": {k: round(v, 4)
                                  for k, v in verdict.terminal_fraction.items()},
            "is_scoreable": verdict.is_scoreable}


def order_for_permutation(ramped: dict[str, Any], ramp: tuple[float, ...],
                          label: str, allow_one_element: bool) -> dict[str, Any]:
    """`order_for` for the D4 control, where a FAILED GUARD IS THE
    MEASUREMENT rather than a reason to stop.

    In the main grid a dirty ramp bottom is E1's stop condition: the
    workload is mis-provisioned and nothing computed from it is
    interpretable. In the permutation arm the same failure says something
    else and something worth having -- **that reordering the flow list
    alone breaks a bearer in the CONTROL condition**, at x1.0, before any
    overload. The smoke run hit exactly this on TwoTier.

    So the permutation is recorded UNSCOREABLE with its reason and the
    campaign continues, and the count of unscoreable permutations is
    reported beside the orders. It is a separate function rather than a
    flag on `order_for` for the same reason `allow_one_element` is a named
    parameter: a swallowed assertion and an honoured one must not look
    alike to a later reader.
    """
    try:
        return order_for(ramped, ramp, label, allow_one_element)
    except AssertionError as exc:
        return {"unscoreable": str(exc).split(".")[0], "order": None}


# --- reporting -----------------------------------------------------------

def _order_distribution(orders: list[list[int]]) -> list[tuple[tuple, int]]:
    return Counter(tuple(o) for o in orders).most_common()


def _fmt_dist(orders: list[list[int]]) -> str:
    return "  ".join(f"{list(o)}x{c}" for o, c in _order_distribution(orders))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--perm-seeds", type=int, default=5)
    ap.add_argument("--time-cell", action="store_true",
                    help="time ONE cell end-to-end with real post-processing "
                         "and stop -- §6.3a's rule, before the full grid")
    ap.add_argument("--out", default="sweeps/wp9/g12_campaign.json")
    args = ap.parse_args(argv[1:])

    n_seeds = 2 if args.smoke else args.seeds
    ramp = RAMP[:3] if args.smoke else RAMP
    in_range = tuple(m for m in ramp if m <= GUARANTEE_RAMP_TOP_MULT)
    has_out_of_range = len(ramp) > len(in_range)
    seeds = paired_seeds(n_seeds)
    arms = _arms()

    kept, excluded = scoreable_cells()
    # Kept BEFORE the forcing below, so --time-cell extrapolates against the
    # real grid rather than against the one cell it was told to run. The
    # first version of this message reported "22 min for the grid" from a
    # kept list of length 1 -- a count restated from a mutated variable,
    # which is the same drift this project has recorded four times.
    n_real_cells = len(kept)
    if args.smoke or args.time_cell:
        kept = [REFERENCE_CELL]
    print(f"G12 campaign -- ramp {list(ramp)} ({len(ramp)} points), "
          f"in-range <= x{GUARANTEE_RAMP_TOP_MULT}: {list(in_range)}")
    if not has_out_of_range:
        print("  NOTE: this ramp has no out-of-range points, so REGION 2 "
              "is not reported at all.")
    print(f"  scoreable cells ({len(kept)}): {kept}")
    for cell, why in excluded:
        print(f"  EXCLUDED {cell}: {why}")
    print(f"  {len(arms)} arms x {n_seeds} seeds; "
          f"{len(kept) * len(arms) * n_seeds * len(ramp)} runs", flush=True)

    if args.time_cell:
        t0 = time.time()
        comp, n = REFERENCE_CELL
        for arm_name, factory in arms.items():
            run_ramp(comp, n, arm_name, factory, seeds[0], ramp)
        dt = time.time() - t0
        n_perm_runs = (len(arms) * len(PERMUTATION_SEEDS) * args.perm_seeds
                       * len(ramp))
        per_run = dt / (len(arms) * len(ramp))
        print(f"\n§6.3a TIMED CELL (real post-processing, "
              f"record_timeseries=True): {dt:.0f}s for "
              f"{len(arms)} arms x 1 seed x {len(ramp)} points "
              f"= {per_run:.1f}s/run")
        print(f"  main grid : {dt * n_seeds / 60:.0f} min/cell x "
              f"{n_real_cells} scoreable cells = "
              f"{dt * n_seeds * n_real_cells / 60:.0f} min serial")
        print(f"  D4 control: {n_perm_runs} runs = "
              f"{n_perm_runs * per_run / 60:.0f} min serial")
        print(f"  TOTAL     : "
              f"{(dt * n_seeds * n_real_cells + n_perm_runs * per_run) / 60:.0f}"
              f" min serial")
        return 0

    out: dict[str, Any] = {"ramp": list(ramp), "in_range": list(in_range),
                           "excluded_cells": [[list(c), w] for c, w in excluded],
                           "cells": {}}

    for comp, n in kept:
        key = f"{comp}_n{n}"
        out["cells"][key] = {}
        print(f"\n{'=' * 78}\n{key}\n{'=' * 78}", flush=True)
        for arm_name, factory in arms.items():
            in_orders, full_orders, per_seed = [], [], []
            for seed in seeds:
                r = run_ramp(comp, n, arm_name, factory, seed, ramp)
                label = f"{key}/{arm_name}/seed{seed}"
                # IN-RANGE FIRST, and a one-element order here is the
                # FINDING (§35.12), not a defect -- see the module docstring.
                iv = order_for(r, in_range, label + "/in-range",
                               allow_one_element=True)
                # A one-element FULL-ramp order is a defect (the class is
                # pinned) ONLY when the ramp actually extends past the
                # guarantee's top. When it does not -- --smoke, or any ramp
                # trimmed to <= 145 % -- the "full" region IS the in-range
                # region and the same finding logic applies. Derived from
                # the ramp rather than hardcoded per mode.
                fv = order_for(r, ramp, label + "/full",
                               allow_one_element=not has_out_of_range)
                in_orders.append(iv["order"])
                full_orders.append(fv["order"])
                per_seed.append({"seed": seed, "in_range": iv, "full": fv,
                                 "per_point": r["per_point"]})
                print(f"    ... {label}  in-range {iv['order']}  "
                      f"full {fv['order']}", flush=True)
            out["cells"][key][arm_name] = {
                "in_range_orders": in_orders, "full_orders": full_orders,
                "per_seed": per_seed}
            print(f"  {arm_name:<12} IN-RANGE {_fmt_dist(in_orders)}   |   "
                  f"FULL {_fmt_dist(full_orders)}", flush=True)

    # D4's control, at the reference cell only.
    comp, n = REFERENCE_CELL
    if (comp, n) in kept:
        print(f"\n{'=' * 78}\nD4 permutation control -- {comp} N={n}\n"
              f"{'=' * 78}", flush=True)
        out["permutation_control"] = {}
        perm_seeds = paired_seeds(args.perm_seeds)
        for arm_name, factory in arms.items():
            by_perm = {}
            for p in PERMUTATION_SEEDS:
                orders, unscoreable = [], []
                for seed in perm_seeds:
                    r = run_ramp(comp, n, arm_name, factory, seed, ramp,
                                 perm_seed=p)
                    v = order_for_permutation(
                        r, ramp, f"perm{p}/{arm_name}/seed{seed}",
                        allow_one_element=not has_out_of_range)
                    if v["order"] is None:
                        unscoreable.append(v["unscoreable"])
                    else:
                        orders.append(v["order"])
                by_perm[str(p)] = {"orders": orders,
                                   "unscoreable": unscoreable}
                note = (f"  [{len(unscoreable)}/{len(perm_seeds)} UNSCOREABLE: "
                        f"reordering broke the control]" if unscoreable else "")
                print(f"  {arm_name:<12} perm {p}: "
                      f"{_fmt_dist(orders) or '(none scoreable)'}{note}",
                      flush=True)
            out["permutation_control"][arm_name] = by_perm

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
