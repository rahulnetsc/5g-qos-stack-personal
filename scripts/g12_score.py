"""Score G12's campaign against §35.9's pre-registered E1-E5.

READING ORDER IS FIXED BY §35.13 AND IS NOT A PRESENTATION CHOICE:

  0. THE PERMUTATION CONTROL'S UNSCOREABLE COUNT, FIRST. §35.13 made the
     control part of the answer rather than a nuisance: a permutation that
     cannot produce a clean ramp bottom cannot contribute an ordering, and
     if a majority of permutations cannot, **that is the finding about
     declaration order** and it lands whether or not any ordering is
     scoreable. Reading it after the orderings would invite treating it as
     a caveat on them instead of as a result.

  1. REGION 1 -- inside GT-7.3's own ramp. The PRIMARY finding, and a
     statement about the test specification, not about any scheduler.

  2. REGION 2 -- beyond 145 %, never printed without the control beside it.

  3. E1-E5, scored.

THE PROMOTION BAR IS APPLIED AS WRITTEN, INCLUDING ITS EDGE. An
arm-dependent order is promoted to a scheduler finding only if it survives
EVERY permutation in the same direction, or a mechanism is traced to
something position-INDEPENDENT. All three candidates §35.5 named are
position-dependent, so tracing to any of them CONFIRMS the artefact. This
script therefore never prints "mechanism found => promoted"; it prints the
survival test and leaves the mechanism clause to a trace it cannot run.

    uv run python scripts/g12_score.py [sweeps/wp9/g12_campaign.json]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import bootstrap_ci  # noqa: E402
from sim.scenarios.g12 import GUARANTEE_RAMP_TOP_MULT  # noqa: E402
from sim.scorecard import Scorecard  # noqa: E402


def _dist(orders: list) -> str:
    c = Counter(tuple(o) for o in orders)
    return "  ".join(f"{list(k)}x{v}" for k, v in c.most_common()) or "(none)"


def _excludes_zero(ci: dict) -> bool:
    return ci["lo"] > 0 or ci["hi"] < 0


# --- 0. the control, read first ------------------------------------------

def report_permutation_control(data: dict) -> dict[str, Any]:
    print("=" * 78)
    print("0. D4 PERMUTATION CONTROL -- read BEFORE any ordering (§35.13)")
    print("=" * 78)
    ctl = data.get("permutation_control")
    if not ctl:
        print("  ABSENT -- no Region-2 claim may be made (§35.13).")
        return {"present": False}

    out: dict[str, Any] = {"present": True, "by_arm": {}}
    for arm, by_perm in ctl.items():
        n_perm = len(by_perm)
        n_bad = sum(1 for v in by_perm.values() if not v["orders"])
        n_runs = sum(len(v["orders"]) + len(v["unscoreable"])
                     for v in by_perm.values())
        n_bad_runs = sum(len(v["unscoreable"]) for v in by_perm.values())
        orders_all = [o for v in by_perm.values() for o in v["orders"]]
        distinct = {tuple(o) for o in orders_all}
        out["by_arm"][arm] = {
            "n_perm": n_perm, "n_perm_fully_unscoreable": n_bad,
            "n_runs": n_runs, "n_unscoreable_runs": n_bad_runs,
            "distinct_orders": [list(d) for d in distinct],
            "orders": orders_all,
        }
        print(f"  {arm:<12} {n_bad_runs}/{n_runs} runs UNSCOREABLE "
              f"(reordering broke the ramp bottom); "
              f"{n_bad}/{n_perm} permutations produced nothing")
        print(f"  {'':<12} orders across permutations: {_dist(orders_all)}")
        if len(distinct) > 1:
            print(f"  {'':<12} ** THE ORDER IS NOT STABLE UNDER REORDERING: "
                  f"{len(distinct)} distinct orders **")

    total_runs = sum(v["n_runs"] for v in out["by_arm"].values())
    total_bad = sum(v["n_unscoreable_runs"] for v in out["by_arm"].values())
    out["majority_unscoreable"] = total_bad * 2 > total_runs
    print(f"\n  ACROSS ARMS: {total_bad}/{total_runs} permuted runs cannot "
          f"produce a clean control.")
    if out["majority_unscoreable"]:
        print("  ** A MAJORITY OF PERMUTED RUNS CANNOT PRODUCE A CLEAN RAMP\n"
              "     BOTTOM. That is the finding about declaration order, and\n"
              "     it stands independently of any ordering below (§35.13). **")
    return out


# --- 1 & 2. the two regions ----------------------------------------------

def report_regions(data: dict) -> dict[str, Any]:
    out: dict[str, Any] = {"region1": {}, "region2": {}}
    print("\n" + "=" * 78)
    print(f"1. REGION 1 -- INSIDE GT-7.3's OWN RAMP (<= x{GUARANTEE_RAMP_TOP_MULT}"
          f", 145 % of ceiling).  THE PRIMARY FINDING")
    print("=" * 78)
    for cell, arms in data["cells"].items():
        for arm, d in arms.items():
            orders = d["in_range_orders"]
            sizes = Counter(len(o) for o in orders)
            out["region1"][f"{cell}/{arm}"] = {
                "orders": orders, "size_counts": dict(sizes)}
            print(f"  {cell:<18} {arm:<12} {_dist(orders)}")
    all_in = [o for a in data["cells"].values() for d in a.values()
              for o in d["in_range_orders"]]
    n_ordering = sum(1 for o in all_in if len(o) >= 2)
    out["region1_summary"] = {"n_groups": len(all_in),
                              "n_with_an_ordering": n_ordering}
    print(f"\n  {n_ordering} of {len(all_in)} (cell, arm, seed) groups produce "
          f"an ORDERING (>= 2 classes) inside the guarantee's own ramp.")
    if n_ordering == 0:
        print("  ** G12's SPECIFIED DEGRADATION ORDER CANNOT BE OBSERVED AT THE\n"
              "     LOAD G12 SPECIFIES. This is a SPECIFICATION finding: the\n"
              "     test as written cannot produce the evidence it asks for.\n"
              "     It is NOT F4's result -- that was one GBR class on disk\n"
              "     with nothing to order, fixed by building a workload (done).\n"
              "     This one is fixed by changing GT-7.3's ramp, or by\n"
              "     accepting G12 is not testable as written. Different\n"
              "     cause, different fix, DIFFERENT OWNER (§35.13). **")

    print("\n" + "=" * 78)
    print("2. REGION 2 -- BEYOND 145 %.  Not printed without the control.")
    print("=" * 78)
    for cell, arms in data["cells"].items():
        for arm, d in arms.items():
            out["region2"][f"{cell}/{arm}"] = {"orders": d["full_orders"]}
            print(f"  {cell:<18} {arm:<12} {_dist(d['full_orders'])}")
    print("\n  QUALIFIER, REGISTERED IN ADVANCE AND TRAVELLING WITH EVERY\n"
          "  NUMBER ABOVE: this ordering is CURRENTLY A PROPERTY OF\n"
          "  DECLARATION ORDER. §35.5 measured the same workload under a\n"
          "  permuted flow list giving the opposite order. On its own it\n"
          "  reads as a scheduler finding and is not established as one.")
    return out


# --- 3. E1-E5 -------------------------------------------------------------

def score_expectations(data: dict, ctl: dict) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []

    # E1 -- scored from the CONTROL PASS's own numbers, not inferred from
    # "the campaign completed". The first launch aborted at ugv_heavy/PF/
    # seed579362555 with 5QI 2 breaching at x1.0, so "it finished" would
    # have been evidence only that contaminated cells had been removed --
    # a completion criterion that improves as more data is discarded.
    cp = data.get("control_pass") or {}
    if not cp:
        rows.append(("E1", "UNSCOREABLE",
                     "no control_pass in the campaign output"))
    else:
        dirty = {k: v for k, v in cp.items() if v["contaminated"]}
        n_bad = sum(len(v["contaminated"]) for v in cp.values())
        n_all = sum(v["n_groups"] for v in cp.values())
        detail = (f"{n_bad}/{n_all} (cell, arm, seed) groups breach at ramp "
                  f"index 0 across {len(cp)} candidate cells; contaminated "
                  f"cells excluded WHOLE: {sorted(dirty)}")
        rows.append(("E1", "HIT" if not dirty else "MISS", detail))

    all_full = [o for a in data["cells"].values() for d in a.values()
                for o in d["full_orders"]]
    n2 = sum(1 for o in all_full if len(o) >= 2)
    per_arm_two = {}
    for cell, arms in data["cells"].items():
        for arm, d in arms.items():
            per_arm_two.setdefault(arm, []).extend(
                len(o) >= 2 for o in d["full_orders"])
    # E2 as REGISTERED reads "a TWO-element list on every arm". Scored at
    # that strength: HIT only if every group gives two elements; PARTIAL if
    # every arm produces some but not all; MISS if any arm produces none.
    # Tightened here, before the data landed -- an `any()` per arm would
    # have been a weaker criterion than the one registered, and loosening a
    # criterion after seeing results is how a prediction exercise stops
    # being one.
    all_groups = all(all(v) for v in per_arm_two.values())
    some_per_arm = all(any(v) for v in per_arm_two.values())
    verdict = "HIT" if all_groups else ("PARTIAL" if some_per_arm else "MISS")
    rows.append(("E2", verdict,
                 f"{n2}/{len(all_full)} full-ramp groups give a two-element "
                 f"order; per-arm two-element counts "
                 f"{ {a: f'{sum(v)}/{len(v)}' for a, v in per_arm_two.items()} }. "
                 f"Note E2 is satisfied only on ramp points BEYOND the "
                 f"guarantee's own range (§35.12)"))

    # E3 -- clause 4, and the instrument choice here is load-bearing.
    #
    # THE FIRST IMPLEMENTATION SCORED THIS ON THE LIVENESS GAP ALONE AND
    # RETURNED "UNSCOREABLE". That was a defect in this scorer, not a null
    # in the data: `telemetry_max_gap_ms` goes **None** from x3.3 upward
    # because the telemetry flow stops completing messages entirely, and a
    # flow with no completions has no gap between completions to measure.
    # The gap is therefore BLIND EXACTLY WHERE THE FAILURE IS TOTAL -- the
    # same shape as M19's registered caveat, where a flow that never
    # delivers anything reads green, and the same shape as §33.3's
    # dynamic-range rule one level over.
    #
    # E3 as REGISTERED says "no liveness-gap OR PDB degradation", so M02 was
    # always half the criterion; the first implementation simply dropped
    # that half. Scoring on M02 restores fidelity to the registration rather
    # than loosening it -- and it moves E3 from UNSCOREABLE to MISS, i.e.
    # against the expectation, which is the honest direction for a
    # post-hoc correction to run.
    # DECOMPOSED BY ARM, because pooling here produced a wrong reading in
    # this scorer's own first run: "first degradation at x1.0" was a min
    # over all groups and was TRUE OF TwoTier ONLY. That is the standing
    # decompose check failing inside the tool built to apply it.
    ramp = data["ramp"]
    in_range_top = max(data["in_range"])
    per_arm: dict[str, dict] = {}
    gap_blind = 0
    for arms in data["cells"].values():
        for arm, d in arms.items():
            a = per_arm.setdefault(arm, {"worst": 0.0, "first": [], "n": 0})
            for s_ in d["per_seed"]:
                a["n"] += 1
                first = None
                for i, p in enumerate(s_["per_point"]):
                    if (p["bg_bps"] or 0) <= 0:
                        continue
                    m = p["telemetry_m02"]
                    if m is not None:
                        a["worst"] = max(a["worst"], m)
                        if m > 0 and first is None:
                            first = i
                    if p["telemetry_max_gap_ms"] is None:
                        gap_blind += 1
                a["first"].append(first)
    worst_overall = max(a["worst"] for a in per_arm.values())
    bits = []
    for arm, a in per_arm.items():
        firsts = [f for f in a["first"] if f is not None]
        earliest = min(firsts) if firsts else None
        bits.append(
            f"{arm}: worst M02 {a['worst']:.3f}, degrades on "
            f"{len(firsts)}/{a['n']} seeds, earliest at x"
            f"{ramp[earliest] if earliest is not None else '-'}"
            + (" (INSIDE the guarantee's ramp)"
               if earliest is not None and ramp[earliest] <= in_range_top
               else ""))
    rows.append(("E3", "MISS" if worst_overall > 0 else "HIT",
                 "5QI 1 IS degraded while 5QI 9 still moves bytes -- "
                 + "; ".join(bits)
                 + f". The gap statistic is BLIND on {gap_blind} ramp points "
                   f"(the flow delivered nothing, so it has no completions to "
                   f"measure between) -- M02 is the instrument with range here"))

    # E4 -- is "5QI 9 exhausted" literally satisfied before a GBR breach?
    bg_at_first_breach = []
    for arms in data["cells"].values():
        for d in arms.values():
            for s in d["per_seed"]:
                ffi = s["full"].get("first_fail_at_index") or {}
                if not ffi:
                    continue
                idx = min(ffi.values())
                if idx < len(s["per_point"]):
                    bg_at_first_breach.append(s["per_point"][idx]["bg_bps"])
    if bg_at_first_breach:
        med = statistics.median(bg_at_first_breach)
        rows.append(("E4", "HIT" if med > 0 else "MISS",
                     f"5QI 9 still carries a median {med/1e6:.3f} Mbps at the "
                     f"first GBR breach (n={len(bg_at_first_breach)}); "
                     f"'exhausted' is not a satisfied precondition"))
    else:
        rows.append(("E4", "UNSCOREABLE", "no group recorded a GBR breach"))

    # E5 -- the most-likely-wrong slot, and the promotion bar applied.
    by_arm_orders: dict[str, set] = {}
    for cell, arms in data["cells"].items():
        for arm, d in arms.items():
            by_arm_orders.setdefault(arm, set()).update(
                tuple(o) for o in d["full_orders"])
    same = len({frozenset(v) for v in by_arm_orders.values()}) == 1
    detail = "; ".join(f"{a}: {sorted(map(list, v))}"
                       for a, v in by_arm_orders.items())
    rows.append(("E5", "HIT" if same else "MISS",
                 f"canonical-order full-ramp orders by arm -- {detail}"))
    return rows


def apply_promotion_bar(data: dict, ctl: dict) -> None:
    """§35.13's bar, applied exactly as registered -- including its edge."""
    print("\n" + "=" * 78)
    print("THE PROMOTION BAR (§35.13), applied as written")
    print("=" * 78)
    by_arm_canon: dict[str, set] = {}
    for arms in data["cells"].values():
        for arm, d in arms.items():
            by_arm_canon.setdefault(arm, set()).update(
                tuple(o) for o in d["full_orders"])
    arms_differ_canonical = len({frozenset(v) for v in by_arm_canon.values()}) > 1
    print(f"  arms differ under the CANONICAL order: {arms_differ_canonical}")

    if not ctl.get("present"):
        print("  control absent -- nothing can be promoted.")
        return
    survives = None
    if arms_differ_canonical:
        perm_arm_orders = {a: {tuple(o) for o in v["orders"]}
                           for a, v in ctl["by_arm"].items()}
        usable = {a: v for a, v in perm_arm_orders.items() if v}
        survives = (len(usable) == len(perm_arm_orders)
                    and len({frozenset(v) for v in usable.values()}) > 1)
        print(f"  the difference survives permutation in the same direction: "
              f"{survives}")

    print("\n  CLAUSE 2 -- a mechanism traced to something POSITION-INDEPENDENT.")
    print("  Not run here, and the edge matters: all three candidates §35.5\n"
          "  named (pf.py's declaration-order tie-break, per-UE LCP iteration\n"
          "  order, HarqProcessPool._pools' insertion order) are POSITION-\n"
          "  DEPENDENT. Tracing the effect to any of them CONFIRMS the\n"
          "  artefact -- it does not promote it. 'We found the mechanism' is\n"
          "  not promotion unless the mechanism is position-independent.")

    if arms_differ_canonical and survives:
        print("\n  => clause 1 FIRES. The arm difference is a candidate "
              "scheduler finding\n     and needs the trace to confirm.")
    else:
        print("\n  => NEITHER CLAUSE FIRES. The registered conclusion applies "
              "verbatim:\n     the Region-2 ordering is NOT ESTABLISHED as a "
              "scheduler property and\n     is CONSISTENT WITH A "
              "DECLARATION-ORDER ARTEFACT. G12's row says that,\n     not an "
              "inversion (§35.13, committed before the numbers existed).")


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else "sweeps/wp9/g12_campaign.json")
    data = json.loads(path.read_text())
    print(f"G12 campaign scoring -- {path}")
    print(f"ramp {data['ramp']}, in-range {data['in_range']}")
    for cell, why in data.get("excluded_cells", []):
        print(f"excluded cell {cell}: {why}")
    print()
    cp = data.get("control_pass") or {}
    if cp:
        print("=" * 78)
        print("E1's CONTROL PASS -- the ramp bottom, per cell")
        print("=" * 78)
        for cell, v in cp.items():
            bad = v["contaminated"]
            print(f"  {cell:<18} {len(bad)}/{v['n_groups']} groups breach at "
                  f"x1.0" + ("  -> EXCLUDED WHOLE" if bad else "  clean"))
            for b in bad[:3]:
                print(f"      {b['arm']}/seed{b['seed']}: 5QI {b['5qi']} "
                      f"worst {b['worst']}")
        print("\n  Cell-level, not seed-level: dropping only the failing seeds\n"
              "  would leave the survivors SELF-SELECTED -- G9's partially-\n"
              "  degenerate-run trap, where the surviving events were the\n"
              "  fastest ones and the arms stopped being comparable.\n")
    ctl = report_permutation_control(data)
    report_regions(data)
    print("\n" + "=" * 78)
    print("3. E1-E5, scored against §35.9")
    print("=" * 78)
    for eid, verdict, detail in score_expectations(data, ctl):
        print(f"  {eid}  {verdict:<12} {detail}")
    apply_promotion_bar(data, ctl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
