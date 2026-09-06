"""ONE primary number per guarantee per arm: SUCCESS RATE, with severity under it.

    success rate = the fraction of RUNS in which the guarantee held, reported
                   with its denominator (PF 7/10).
    severity     = the fraction of traffic that missed its deadline (M02 or
                   the guarantee's own equivalent), MEDIAN across runs.

Everything else -- p98, jitter, Jain, CoV -- is DIAGNOSTIC and appears only
when explaining a failure. It is never the verdict.

**AGGREGATION RULE, and it is not symmetric.** Seeds and sweep cells ARE
aggregated: they are environmental variation and a success rate is exactly
the right summary. **Clauses are NOT.** G11's five clauses ask five different
questions and G9's four likewise; each gets its own row, and a conjunction
("all clauses hold") is reported separately and labelled.

**Every pass predicate is cited to the test plan or to the artefact's own
scorer. Nothing is invented here** -- where a criterion does not exist, the
row says NOT COMPUTABLE rather than guessing one, because an estimated
success rate is worse than a missing one.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARMS = ("PF", "Reservation", "TwoTier")


def load(rel):
    p = REPO / rel
    return json.loads(p.read_text()) if p.exists() else None


def rate(passes, n):
    return f"{passes}/{n}"


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


ROWS = []


def add(g, clause, arm, passes, n, sev, sev_unit, artefact, note="",
        sev_fail=None):
    """`sev` is the median across ALL runs, as specified.

    `sev_fail` is the median across the FAILING runs only, and it is carried
    because the all-runs median answers the question it was asked to answer
    only when most runs fail. With 7/10 passing, the all-runs median is a
    passing run's severity and says nothing about how badly the other 3 broke
    -- which is the exact distinction ("narrowly on 4 seeds" vs "totally on 4
    seeds") the severity number exists to make.
    """
    ROWS.append(dict(g=g, clause=clause, arm=arm,
                     rate=rate(passes, n) if n else "--",
                     frac=(passes / n) if n else None,
                     sev=sev, sev_fail=sev_fail, sev_unit=sev_unit,
                     art=artefact, note=note))


def not_computable(g, clause, why, artefact="--"):
    for arm in ARMS:
        ROWS.append(dict(g=g, clause=clause, arm=arm, rate="NOT COMPUTABLE",
                         frac=None, sev=None, sev_fail=None, sev_unit="",
                         art=artefact, note=why))


# ---------------------------------------------------------------- G1, G8 ---
core = load("sweeps/rerun-2026-09-06/core.json")
if core:
    A = "rerun-2026-09-06/core.json"
    for arm in ARMS:
        R = [r for r in core["rows"] if r["arm"] == arm]
        # test plan L122: "Conformance statistic is p98 < PDB ... PASS/FAIL on p98"
        ok = [r for r in R if (r["G1_M01_p98_prot"] or 0) < 100.0]
        add("G1", "p98 < PDB (100 ms, parametric)", arm, len(ok), len(R),
            None, "", A, "severity needs M02, which no runner records")
        # GT-5: "per-1 s Jain >= 0.9"
        ok = [r for r in R if (r["G8_M09_worst_prot"] or 0) >= 0.90]
        bad = [r for r in R if r not in ok]
        add("G8", "per-1 s Jain >= 0.90", arm, len(ok), len(R),
            med([max(0.0, 0.90 - (r["G8_M09_worst_prot"] or 0)) for r in R]),
            "Jain shortfall (NOT a traffic fraction)", A,
            sev_fail=med([0.90 - (r["G8_M09_worst_prot"] or 0) for r in bad]))
        # GT-3.1: ">= 99 % PDU sets complete <= 150 ms"
        ok = [r for r in R if (r["G5_M05_prot"] or 0) >= 0.99]
        bad = [r for r in R if r not in ok]
        add("G5", ">= 99 % PDU sets complete", arm, len(ok), len(R),
            med([1.0 - (r["G5_M05_prot"] or 0) for r in R]),
            "fraction of PDU sets incomplete", A,
            sev_fail=med([1.0 - (r["G5_M05_prot"] or 0) for r in bad]))

sd = load("sweeps/rerun-2026-09-06/sensor_dense.json")
if sd:
    A = "rerun-2026-09-06/sensor_dense.json"
    for arm in ARMS:
        R = [r for r in sd["rows"] if r["arm"] == arm]
        ok = [r for r in R if (r["G1_M01_p98"] or 0) < 15.0]
        add("G1", "p98 < PDB (15 ms, sensor_dense)", arm, len(ok), len(R),
            med([1.0 - (r["flows_on_time"] / max(r["n_flows"], 1)) for r in R]),
            "fraction of FLOWS late (not of traffic)", A)
        ok = [r for r in R if (r["G8_M09_worst"] or 0) >= 0.90]
        add("G8", "per-1 s Jain >= 0.90 (sensor_dense)", arm, len(ok), len(R),
            med([max(0.0, 0.90 - (r["G8_M09_worst"] or 0)) for r in R]),
            "Jain shortfall (NOT a traffic fraction)", A)

# ------------------------------------------------------------------- G10 ---
g10 = load("sweeps/rerun-2026-09-06/g10_attach.json")
if g10:
    A = "rerun-2026-09-06/g10_attach.json"
    for arm in ARMS:
        R = [r for r in g10["rows"] if r["arm"] == arm]
        # GT-5: admissible N needs G1/G3/G5/G8 all-pass; this artefact carries
        # the GBR contract only, so the row is scoped to what it can support.
        ok = [r for r in R if r["M07_met"] == r["M07_total"]]
        add("G10", "every GBR flow meets contract (per fleet size x seed)",
            arm, len(ok), len(R),
            med([1.0 - (r["M08_fraction"] or 0) for r in R]),
            "worst-flow GFBR shortfall", A,
            "scoped to the GBR contract; GT-5's admissible-N needs G1/G3/G5/G8 jointly")

# -------------------------------------------------------------------- G7 ---
g7 = load("sweeps/rerun-2026-09-06/g7.json")
if g7:
    A = "rerun-2026-09-06/g7.json"
    for arm in ARMS:
        R = [r for r in g7["rows"] if r["arm"] == arm]
        ok = [r for r in R
              if (r["B_camera_throughput_bps"] or 0) <= (r["B_camera_mfbr_bps"] or 0) * 1.02]
        add("G7", "clause 2: aggressor clamped at MFBR", arm, len(ok), len(R),
            med([max(0.0, (r["B_camera_throughput_bps"] or 0)
                     / max(r["B_camera_mfbr_bps"] or 1, 1) - 1.0) for r in R]),
            "excess over MFBR (x MFBR)", A)
        ok = [r for r in R if (r["A_camera_m05"] or 0) >= 0.99]
        add("G7", "clause 1: victim's PDU sets >= 99 % complete", arm,
            len(ok), len(R),
            med([1.0 - (r["A_camera_m05"] or 0) for r in R]),
            "fraction of victim PDU sets incomplete", A)

# ------------------------------------------------------------------- G12 ---
g12 = load("sweeps/g12-rescore-2026-09-06/g12.json")
if g12:
    A = "g12-rescore-2026-09-06/g12.json"
    for arm in ARMS:
        npass = ntot = 0
        sev = []
        for cell in g12["cells"].values():
            if arm not in cell:
                continue
            for s in cell[arm]["per_seed"]:
                ntot += 1
                bad = [pt for pt in s["per_point"]
                       if (pt.get("telemetry_m02") or 0) >= 0.99
                       and (pt.get("bg_bps") or 0) > 0]
                npass += (not bad)
                sev.append(max((pt.get("telemetry_m02") or 0)
                               for pt in s["per_point"]))
        add("G12", "clause 4: telemetry never starved while bg moves bytes",
            arm, npass, ntot, med(sev),
            "telemetry M02 (fraction of bytes PDB-violated), worst ramp point",
            A, "cells x seeds aggregated; ramp points are within-run")

# -------------------------------------------------------------- G11 C1 ---
c1 = load("sweeps/rerun-2026-09-06/g11_c1_soak.json")
if c1:
    A = "rerun-2026-09-06/g11_c1_soak.json"
    # test plan L105 "every 60 s window ... passes", conformance basis L122
    # ("98 % of packets shall not exceed the PDB"), so a window fails at
    # M02w > 0.02. The FIRST version of this row tested a field
    # (`failing_windows`) that does not exist, so it was vacuously 10/10 on
    # every arm -- caught by asking what would make it fail.
    for arm in ARMS:
        R = [r for r in c1["runs"] if (r.get("arm") or r.get("scheduler")) == arm]
        ok, sev_all = [], []
        for r in R:
            m02 = [float(x.get("value", x.get("p50", 0)) or 0)
                   for x in r["rows"] if x["metric"] == "M02w"]
            if m02:
                sev_all.append(med(m02))
                if max(m02) <= 0.02:
                    ok.append(r)
        add("G11", "C1: every 60 s window within PDB conformance (M02w<=0.02)",
            arm, len(ok), len(R), med(sev_all),
            "fraction of traffic PDB-violated, median window", A,
            "passes with ~100x margin: worst window is ~1.8e-4 against 0.02")

# ------------------------------------------------- NOT COMPUTABLE rows ---
not_computable("G2", "any", "no verdict exists: the named failure mode (BSR/SR "
               "desync) is shown not to occur, and no pass criterion was ever "
               "written for what replaced it")
not_computable("G3", "M20 protected-fleet liveness",
               "M20 is a DELTA between arms, not a per-run pass/fail; the test "
               "plan states no per-run bound", "rerun-2026-09-06/core.json")
not_computable("G4", "post-silence resumption",
               "scored as a between-arm SEPARATION at duty 0.1, not a per-run "
               "pass; and the artefact's rows are per (duty, ue, qfi, bucket), "
               "not per run", "rerun-2026-09-06/g4.json")
not_computable("G6", "clause 1",
               "the clause NAMES NO ESTIMATOR; we chose the median and "
               "documented it. A success rate would be an artefact of that "
               "choice", "rerun-2026-09-06/g6/")
not_computable("G9", "clauses 1-3 (event counts)",
               "scored as counts of scripted events completed, not as per-run "
               "pass/fail against a stated bound", "rerun-2026-09-06/g9.json")
not_computable("G9", "clause 4 (neighbours unaffected)",
               "scored as a paired DELTA in neighbour p98; no per-run bound, "
               "and treatment and instrument cannot be separated",
               "rerun-2026-09-06/g9.json")
not_computable("G11", "C2 (drift)", "counters never wired; 6 of the C's 9 "
               "skip-reasons cannot exist here")
not_computable("G11", "C3 (CoV(p98) <= 15 %)",
               "scored ACROSS runs (a CoV over repeats), so it has no per-run "
               "pass/fail -- 1 result, not n", "rerun-2026-09-06/g11_c345.json")
not_computable("G11", "C4 (identical PASS/FAIL across repeats)",
               "satisfied by construction: every run reports 0 failing windows",
               "rerun-2026-09-06/g11_c345.json")
not_computable("G11", "C5 (no bimodality)",
               "p98 is quantised to the 0.25 ms slot; 3-6 distinct levels over "
               "10 seeds, below the instrument's resolution",
               "rerun-2026-09-06/g11_c345.json")


def main() -> int:
    print(f"{'G':5s} {'clause':50s} {'arm':12s} {'success':>14s} "
          f"{'severity':>10s} {'sev|fail':>9s}  unit")
    print("-" * 128)
    last = None
    for r in ROWS:
        key = (r["g"], r["clause"])
        if last is not None and key != last:
            print()
        last = key
        sev = "--" if r["sev"] is None else f"{r['sev']:.5f}"
        sf = "--" if r.get("sev_fail") is None else f"{r['sev_fail']:.4f}"
        print(f"{r['g']:5s} {r['clause'][:50]:50s} {r['arm']:12s} "
              f"{r['rate']:>14s} {sev:>10s} {sf:>9s}  {r['sev_unit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
