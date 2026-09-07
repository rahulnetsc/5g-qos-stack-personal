"""ONE primary number per guarantee per arm: SUCCESS RATE, severity under it.

    success rate = fraction of RUNS in which the guarantee held, with its
                   denominator (PF 7/10).
    severity     = M02, the fraction of RESOLVED bytes that missed their PDB,
                   median across runs. UNIFORM across every row.

Everything else -- p98, jitter, Jain, CoV -- is DIAGNOSTIC and appears only
when explaining a failure. It is never the verdict.

**AGGREGATION IS ASYMMETRIC.** Seeds and sweep cells ARE aggregated:
environmental variation, and a success rate is the right summary. **Clauses
are NOT** -- G11's five and G9's four ask different questions.

**EVERY THRESHOLD IS QUOTED FROM THE TEST PLAN**, by line, in `SOURCE` below.
A threshold taken from a metric's default or from a scoring script instead is
marked `FROM CODE` and is a finding, not a citation -- the first version of
this file scored G1 against the 100 ms PDB when the test plan states
**p98 <= 95 ms**, and that came from the metric, not the document.

**EVERY PREDICATE MUST BE ABLE TO FAIL.** `--selftest` perturbs each clause's
statistic across its threshold and asserts the verdict flips. A predicate that
cannot fail is not evidence; the first C1 row tested a field that does not
exist and read 10/10 on every arm.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARMS = ("PF", "Reservation", "TwoTier")
SEV_DIR = "sweeps/m6-2026-09-07/plain"   # audit fixes applied, attach OFF
ATT_DIR = "sweeps/m6-2026-09-07/attach"  # the same grid WITH the attach path

#: `--attach` scores the with-attach column. BOTH are reported: the without
#: column is what a COLD-STARTING deployment sees before any UE has been
#: granted, and it is the worst case the fault produces; the with-attach
#: column is the steady state hardware reaches
#: (docs/attach-path-default-registration.md).
USE_ATTACH = False

GUARANTEE = {
    "G1": "Every drive command reaches the robot in time to feel responsive",
    "G2": "A STOP always lands, on every ground robot, fast",
    "G3": "The network never makes a healthy robot look dead",
    "G4": "After a robot goes quiet, its next message still arrives promptly",
    "G5": "Operators and the AI always see fresh, complete video",
    "G6": "Background traffic can never impair the fleet",
    "G7": "One misbehaving robot cannot take down the others",
    "G8": "Robots of equal entitlement get equal service, continuously",
    "G9": "A robot joins (or re-joins) quickly, even on a busy cell",
    "G10": "The cell hosts a stated fleet size with all of the above intact",
    "G11": "The guarantees hold for a whole shift, and reproduce run to run",
    "G12": "Under genuine overload, degradation follows the safety order",
}


def load(rel):
    if USE_ATTACH:
        rel = rel.replace(SEV_DIR, ATT_DIR)
    p = REPO / rel
    return json.loads(p.read_text()) if p.exists() else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


class MissingPopulation(ValueError):
    """A clause without a declared population does not score.

    THE AUDIT'S OWN CONCLUSION, MADE STRUCTURAL. Every defect this scorecard
    has produced -- the C1 vacuity, the G1 threshold, G12's unreachable pass
    branch, G3's background flood, the four-population severity column -- is
    one class: **an aggregate arithmetically correct over the wrong
    population**. The three automated checks (--selftest, --denominators,
    threshold citation) were each added AFTER a defect of that exact shape
    shipped; they are trailing indicators, and the one check that catches this
    class cannot be automated.

    So it is not automated. It is made REQUIRED, as data, at the point of use:
    every clause declares `sums_over` (the rows the predicate ranges over) and
    `claim_about` (the rows the guarantee's clause is about). Scoring raises
    if either is absent, and the report prints both beside the verdict so a
    mismatch is visible without reading the source.

    This does not make the judgement for anyone. It forces the question to be
    answered where the row is written rather than in a document nobody rereads
    -- which is precisely where the audit found the documentation was not
    reaching.
    """


def _require_population(c):
    for f in ("sums_over", "claim_about"):
        if not c.get(f):
            raise MissingPopulation(
                f"{c['g']} '{c['clause']}' declares no {f!r}. Name the rows "
                f"the predicate sums over and the rows the clause is about; "
                f"if they differ, say so in the row rather than in a comment.")


# --- CLAUSES ---------------------------------------------------------------
# stat:   run -> the statistic under test
# ok:     stat -> bool
# sev:    run -> M02 (uniform); None only where the artefact predates it
# source: the TEST PLAN line the threshold comes from
CLAUSES = [
 dict(g="G1", clause="cmd_vel p98 <= 95 ms (parametric)",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G1_M01_p98_prot"], ok=lambda v: v is not None and v <= 95.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M01 worst-flow p98 over the PROTECTED FLEET (5QI 1 and 2)",
      claim_about="the drive-command flow (5QI 1) only. MISMATCH: 4 of 30 "
                  "rows are scored on 5QI 2 video; all 3 failures are on "
                  "5QI 1, so the verdict holds on this data",
      source="test plan L95: 'p98 <= RAN PDB (95 ms of the 100 ms 5QI-1 budget)'"),
 dict(g="G1", clause="p98 <= PDB (15 ms, sensor_dense)",
      art=f"{SEV_DIR}/sensor_dense.json", rows="rows",
      stat=lambda r: r["G1_M01_p98"], ok=lambda v: v is not None and v <= 15.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M01 worst-flow p98, sensor_dense (one 5QI, so all flows ARE "
                "the protected fleet)",
      claim_about="the same set -- no mismatch possible here",
      source="test plan L95 + the workload's own 15 ms PDB"),
 dict(g="G3", clause="max telemetry gap <= 500 ms",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G3_M03_prot_ms"], ok=lambda v: v is not None and v <= 500.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M03 max inter-arrival gap over the PROTECTED FLEET",
      claim_about="telemetry liveness. FIXED 2026-09-07: this row read "
                  "M03 over ALL flows, so a saturating 5QI-9 flood's own "
                  "starvation scored as a telemetry failure -- every breach "
                  "was ue*_qfi9 (wp9-plan.md 24.2, recurring)",
      source="test plan L97: 'Max telemetry inter-arrival gap <= T_live/4 (500 ms)'"),
 dict(g="G5", clause=">= 99 % PDU sets complete within PDB",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G5_M05_prot"], ok=lambda v: v is not None and v >= 0.99,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M05 PDU-set completeness over the PROTECTED FLEET",
      claim_about="the video feed. Same set -- PDU sets exist only on the "
                  "framed video flow",
      source="test plan L99: '>= 99 % of PDU sets complete within PDB'"),
 dict(g="G8", clause="per-1 s Jain >= 0.90 (parametric)",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G8_M09_worst_prot"], ok=lambda v: v is not None and v >= 0.90,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M09 worst per-1 s Jain over the PROTECTED FLEET",
      claim_about="the same set. NOTE: M09's panel status is `proxy`, not "
                  "`ok` -- the metric itself is provisional",
      source="test plan L102: 'Per-1 s Jain >= 0.9 per role across assets'"),
 dict(g="G8", clause="per-1 s Jain >= 0.90 (sensor_dense)",
      art=f"{SEV_DIR}/sensor_dense.json", rows="rows",
      stat=lambda r: r["G8_M09_worst"], ok=lambda v: v is not None and v >= 0.90,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M09 worst per-1 s Jain, sensor_dense (one 5QI)",
      claim_about="the same set; `proxy` caveat as above",
      source="test plan L102"),
 dict(g="G2", clause="STOP p98 <= 100 ms (UL)",
      art=f"{SEV_DIR}/g2_ul_stop.json", rows="rows",
      stat=lambda r: r["UL_stop_p98_ms"], ok=lambda v: v is not None and v <= 100.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="the UL STOP flow's p98",
      claim_about="100 % of STOP EVENTS, i.e. the MAXIMUM. MISMATCH: p98 is "
                  "weaker than the clause and is labelled, not equated",
      source="test plan L96: '100 % of STOP events <= 100 ms'. SUBSTITUTION: "
             "the artefact records p98, not the max, so this is WEAKER than "
             "the stated clause and is labelled rather than silently equated"),
 dict(g="G7", clause="clause 2: aggressor's excess clipped at MFBR",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: (r["B_camera_throughput_bps"] or 0) / max(r["B_camera_mfbr_bps"] or 1, 1),
      # TOLERANCE REMOVED 2026-09-07. The clause says "clipped at MFBR" with
      # NO tolerance; the 1.02 was invented. Swept as G12's tau was:
      # Reservation and TwoTier are INSENSITIVE (ratios ~2.0, 0/10 at every
      # tolerance to 1.5), but PF sits ON the boundary -- 1/10 at <=1.02,
      # 5/10 at 1.05, 10/10 at 1.25. So the invented number was deciding 9 of
      # PF's 10 runs. Scored as written.
      ok=lambda v: v <= 1.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="the AGGRESSOR camera's delivered/MFBR ratio",
      claim_about="the same flow -- the clause is about B's excess",
      source="test plan L101: \"B's excess clipped at MFBR\""),
 dict(g="G7", clause="clause 1: victim's PDU sets >= 99 % complete",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: r["A_camera_m05"], ok=lambda v: v is not None and v >= 0.99,
      sev=lambda r: r.get("M02_prot"),
      sums_over="the VICTIM camera's PDU-set completeness",
      claim_about="\"A's G1/G3/G5 unchanged within epsilon\". MISMATCH: "
                  "epsilon is unspecified, so this row substitutes G5's "
                  "absolute 99 % bound -- a different question, and the only "
                  "row whose threshold is downstream of another clause",
      source="test plan L101 (A's G5 unchanged) + L99's 99 % bound"),
 # --- STEP 1: clause parts that were stated and never scored. Every one
 # is read from an artefact that already carried it
 # (docs/clause-coverage-registration-2026-09-07.md).
 dict(g="G3", clause="part 2: zero gaps >= T_live",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G3_M03_gaps_over_tlive_prot"],
      ok=lambda v: v is not None and v == 0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M03's count of gaps exceeding T_live, PROTECTED FLEET",
      claim_about="the same set",
      source="test plan L97, second part: 'zero gaps >= T_live over the "
             "full campaign' -- stated and never scored until today"),
 dict(g="G3", clause="part 3: p98 <= PDB",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G1_M01_p98_prot"], ok=lambda v: v is not None and v <= 95.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M01 worst-flow p98, PROTECTED FLEET -- NUMERICALLY G1's OWN "
                "STATISTIC, scored under G1's name and not G3's until today",
      claim_about="telemetry's own p98. Same caveat as G1: the worst flow is "
                  "5QI 1 or 2, never the DL command flow",
      source="test plan L97, third part: 'p98 <= PDB'"),
 dict(g="G5", clause="part 2: frame age p95 <= 67 ms",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G5_M06_all_ms"], ok=lambda v: v is not None and v <= 67.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M06 frame age p95 over ALL FLOWS -- this is the only G5 key "
                "with no _prot variant. Harmless in fact (PDU sets exist only "
                "on the framed video flow) but it is an undeclared population",
      claim_about="the video feed",
      source="test plan L99, second part: 'frame age at MEC p95 <= 2 frame "
             "periods (67 ms)'"),
 dict(g="G2", clause="DOWNLINK STOP p98 <= 100 ms",
      art=f"{SEV_DIR}/g2_ul_stop.json", rows="rows",
      stat=lambda r: r["DL_stop_p98_ms"], ok=lambda v: v is not None and v <= 100.0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="the DL STOP flow's p98",
      claim_about="GT-1.2's STOP is a DOWNLINK datagram, so this is the "
                  "clause's own direction. The UL row scores the mirror image. "
                  "SUBSTITUTION unchanged: p98 for a stated MAXIMUM",
      source="test plan L96 + GT-1.2 ('simultaneous STOP datagrams')"),
 dict(g="G7", clause="c1: victim's camera p98 <= PDB",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: (r["A_camera_p98_ms"], r["A_camera_pdb_ms"]),
      ok=lambda v: v[0] is not None and v[0] <= v[1],
      sev=lambda r: r.get("M02_prot"),
      sums_over="the VICTIM camera's p98 against its own PDB",
      claim_about="\"A's G1/G3/G5 unchanged within epsilon\" -- the G1 half. "
                  "epsilon is unspecified, so an absolute bound substitutes",
      source="test plan L101 + GT-4.3"),
 dict(g="G7", clause="c1: victim's telemetry p98 <= PDB",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: (r["A_telemetry_p98_ms"], r["A_telemetry_pdb_ms"]),
      ok=lambda v: v[0] is not None and v[0] <= v[1],
      sev=lambda r: r.get("M02_prot"),
      sums_over="the VICTIM's telemetry p98 against its own PDB",
      claim_about="the same flow", source="test plan L101 + GT-4.3"),
 dict(g="G7", clause="c3: AGGRESSOR's own telemetry p98 <= PDB",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: (r["B_telemetry_p98_ms"], r["B_telemetry_pdb_ms"]),
      ok=lambda v: v[0] is not None and v[0] <= v[1],
      sev=lambda r: r.get("M02_prot"),
      sums_over="the AGGRESSOR's telemetry p98 against its own PDB",
      claim_about="GT-4.3's THIRD part, absent from the guarantee-table line: "
                  "'B's other flows (its own telemetry!) still within SLO -- "
                  "the containment must also hold INSIDE the misbehaving asset'",
      source="GT-4.3 KPI line"),
 dict(g="G8", clause="part 2: zero starvation epochs >= 1 s (parametric)",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G8_M22_epochs_prot"],
      ok=lambda v: v is not None and v == 0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M22's count of starvation epochs, PROTECTED FLEET",
      claim_about="the same set",
      source="test plan L102, second part: 'zero starvation epochs >= 1 s'"),
 dict(g="G8", clause="part 2: zero starvation epochs (sensor_dense)",
      art=f"{SEV_DIR}/sensor_dense.json", rows="rows",
      stat=lambda r: r["G8_M22_epochs"],
      ok=lambda v: v is not None and v == 0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="M22's epoch count, sensor_dense (one 5QI)",
      claim_about="the same set", source="test plan L102, second part"),
 dict(g="G8", clause="part 2b: no UE never granted (sensor_dense)",
      art=f"{SEV_DIR}/sensor_dense.json", rows="rows",
      stat=lambda r: r["n_never_granted"],
      ok=lambda v: v is not None and v == 0,
      sev=lambda r: r.get("M02_prot"),
      sums_over="the count of UEs that received no grant all run",
      claim_about="'zero starvation epochs' in its strongest form -- a UE "
                  "never granted is starved for the whole run",
      source="test plan L102, second part"),
 dict(g="G10", clause="every GBR flow meets contract (per fleet size x seed)",
      art=f"{SEV_DIR}/g10_attach.json", rows="rows",
      stat=lambda r: (r["M07_met"], r["M07_total"]),
      ok=lambda v: v[0] == v[1],
      sev=lambda r: r.get("M02_prot"),
      sums_over="M07 GBR contract count over the PROTECTED FLEET, per "
                "(fleet size, seed)",
      claim_about="\"largest N with G1-G8 all-pass\". MISMATCH: this tests "
                  "the GBR contract only, a narrower question",
      source="test plan L104: 'largest asset count with G1-G8 all-pass'. "
             "SCOPED: this artefact carries the GBR contract only"),
]

NOT_COMPUTABLE = [
 ("G4", "first packet after silence p99 <= 300 ms",
  "the artefact records p98, not p99, and p98 <= p99 -- so substituting it "
  "would be OPTIMISTIC, not conservative. Its rows are also per (duty, ue, "
  "qfi, bucket), not per run", "rerun-2026-09-06/g4.json"),
 ("G6", "every G1/G3/G5 statistic within bound and shifts by <= +20 %",
  "the +20 % is stated, but the clause needs the UNPERTURBED baseline per "
  "statistic and the artefact stores only the perturbed arm's summary",
  "rerun-2026-09-06/g6/"),
 ("G9", "warm p95 <= 1 s; attach <= 15 s; post-RLF <= 10 s",
  "bounds ARE stated (L103), but the artefact stores PER-ARM MEDIANS across "
  "runs (`m18_p95_median`), not per-run values -- so a success rate cannot "
  "be formed without re-running", "rerun-2026-09-06/g9.json"),
 ("G9", "neighbours unaffected", "a paired DELTA with no stated bound; "
  "treatment and instrument cannot be separated", "rerun-2026-09-06/g9.json"),
 ("G11", "C2 drift", "counters never wired; 6 of the C's 9 skip-reasons "
  "cannot exist here", "--"),
 ("G11", "C3 CoV(p98) <= 15 %", "computed ACROSS runs -- one result, not n",
  "rerun-2026-09-06/g11_c345.json"),
 ("G11", "C4 identical PASS/FAIL across repeats",
  "satisfied by construction: every run reports 0 failing windows",
  "rerun-2026-09-06/g11_c345.json"),
 ("G11", "C5 no bimodality", "p98 quantised to the 0.25 ms slot; 3-6 levels "
  "over 10 seeds", "rerun-2026-09-06/g11_c345.json"),
]


#: Rows whose artefact path is FIXED, so `--attach`'s path substitution is a
#: no-op for them. Declaring it is the point: the published table showed G11
#: and G12 identical in both columns, which reads as "the attach path does not
#: affect them" -- when the truth is that NO with-attach run of either exists
#: (neither `g11_campaign.py` nor `g12_campaign.py` takes an attach argument).
#: That is defect #31's symptom -- an artefact byte-identical to the column it
#: should differ from -- read for a third time. A row now says so itself.
_NO_ATTACH_COLUMN = "SINGLE-COLUMN: no with-attach run of this artefact exists"


def _nested():
    """G11 C1 and G12 clause 4 -- their artefacts are nested rather than flat
    rows, and BOTH already carry M02 natively (M02w per window; telemetry_m02
    per ramp point), so severity is the same quantity as every other row."""
    out = []
    c1 = load("sweeps/rerun-2026-09-06/g11_c1_soak.json")
    if c1:
        per = {}
        for arm in ARMS:
            R = [r for r in c1["runs"] if r.get("arm") == arm]
            ok, sev = [], []
            for r in R:
                m = [float(x.get("value", x.get("p50", 0)) or 0)
                     for x in r["rows"] if x["metric"] == "M02w"]
                if m:
                    sev.append(med(m))
                    if max(m) <= 0.02:
                        ok.append(r)
            per[arm] = dict(n=len(R), passes=len(ok), sev=med(sev),
                            sev_fail=None)
        out.append((dict(g="G11", clause="C1: every 60 s window within PDB conformance",
                         column=_NO_ATTACH_COLUMN,
                         sums_over="M02w per 60 s window, subset 'all' -- the "
                                   "ONLY subset the artefact carries",
                         claim_about="'every 60 s window passes', i.e. the "
                                     "guarantees, which bind the protected "
                                     "fleet. MISMATCH: wider population, and "
                                     "scoped to PDB conformance only",
                         source="test plan L105 'every 60 s window passes' + "
                                "L122's 98 % conformance basis -> M02w <= 0.02"),
                    per))
    # --- G6: the clause is a CONJUNCTION and the paired baseline EXISTS.
    # The scorecard declared this not-computable on the grounds that the
    # artefact "stores only the perturbed arm's summary". It does not:
    # stage6_g6_n40.csv holds 3 arms x 40 seeds x bg in {False, True} with the
    # full panel in both populations, and bg=False IS the unperturbed paired
    # baseline the clause requires.
    import csv as _csv
    g6p = REPO / "sweeps/rerun-2026-09-06/g6/stage6_g6_n40.csv"
    if g6p.exists():
        rows6 = list(_csv.DictReader(g6p.open()))
        def _f(r, k):
            v = r.get(k, "")
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        STATS = [("G1 M01 p98 <= 95 ms", "M01.prot.p98", 95.0, "le"),
                 ("G3 max gap <= 500 ms", "M03.prot.max_gap_ms", 500.0, "le"),
                 ("G5 M05 >= 0.99", "M05.prot.fraction", 0.99, "ge")]
        for label, key, bound, sense in STATS:
            per = {}
            for arm in ARMS:
                base = {r["seed"]: _f(r, key) for r in rows6
                        if r.get("scheduler") == arm and r.get("bg") == "False"}
                pert = {r["seed"]: _f(r, key) for r in rows6
                        if r.get("scheduler") == arm and r.get("bg") == "True"}
                seeds = sorted(set(base) & set(pert))
                ok = 0
                for sd in seeds:
                    b, q = base[sd], pert[sd]
                    if b is None or q is None:
                        continue
                    within = (q <= bound) if sense == "le" else (q >= bound)
                    # "shifts by <= +20 % relative", in the DIRECTION OF HARM.
                    # An undefined shift (baseline 0) is counted as failing the
                    # within-bound half only -- Part 3's caveat, kept.
                    if b == 0:
                        shift_ok = True
                    elif sense == "le":
                        shift_ok = (q - b) / abs(b) <= 0.20
                    else:
                        shift_ok = (b - q) / abs(b) <= 0.20
                    ok += bool(within and shift_ok)
                per[arm] = dict(n=len(seeds), passes=ok, sev=None, sev_fail=None)
            out.append((dict(g="G6", clause=f"conjunction: {label} AND shift <= +20 %",
                             column=_NO_ATTACH_COLUMN,
                             sums_over="the PROTECTED-FLEET statistic, paired "
                                       "within seed across bg in {False, True}",
                             claim_about="the same set. NOTE the cell runs under "
                                         "wp9_sweep.BASE, i.e. MFBR 0, a DIFFERENT "
                                         "flag state from core.json's MFBR 8 Mbps",
                             source="test plan L100: 'every G1/G3/G5 statistic "
                                    "stays within its bound AND shifts by "
                                    "<= +20 % relative'"), per))

    c345 = load("sweeps/rerun-2026-09-06/g11_c345.json")
    if c345 and "C3" in c345:
        per = {}
        for arm in ARMS:
            d = c345["C3"].get(arm) or {}
            cov = d.get("cov")
            # ONE value per arm across repeats, not a success rate -- reported
            # as 1/1 or 0/1 so the denominator says so.
            per[arm] = dict(n=1, passes=int(cov is not None and cov <= 0.15),
                            sev=None, sev_fail=None,
                            note=f"CoV = {cov:.4f}" if cov is not None else "no value")
        out.append((dict(g="G11", clause="C3: CoV(p98) <= 15 % across repeats",
                         column=_NO_ATTACH_COLUMN,
                         sums_over="p98 across the 10 repeat runs, per arm",
                         claim_about="the same set. DENOMINATOR IS 1 BY "
                                     "CONSTRUCTION -- a CoV is computed across "
                                     "runs, so there is no per-run verdict",
                         source="test plan L105: 'across repeats, CoV(p98) "
                                "<= 15 %'"), per))

    g12 = load("sweeps/g12-rescore-2026-09-06/g12.json")
    if g12:
        # THE PREDICATE WAS UNSOUND AND REPORTED 0/20 ON EVERY ARM.
        # Clause 4 is a CONJUNCTION -- telemetry starved WHILE a lower class
        # still has throughput -- and the first version tested the second half
        # as `bg_bps > 0`. Measured: bg_bps is NEVER exactly 0 in any of the
        # 480 ramp points, so the pass branch was unreachable and the verdict
        # merged two different things. It is the mirror of the C1 vacuity: a
        # predicate that could not report SUCCESS.
        #
        # Three verdicts now, because the clause has three states:
        #   VIOLATION      telemetry starved while background is meaningfully
        #                  alive -- the thing clause 4 prohibits
        #   PREMISE FAILS  telemetry starved and background also dead -- the
        #                  cell is simply exhausted; clause 4 says nothing
        #   PASS           telemetry never starved
        #
        # `tau` is the floor for "still has throughput", which the test plan
        # does NOT state -- a specification gap, recorded as one. It does not
        # matter where it goes: the arms separate by ~2,800x (PF 8.63 Mbps
        # median at the starved points against Reservation's 3.1 kbps), so
        # every tau from 0.01 to 8 Mbps gives PF 20/20 VIOLATION and
        # Reservation 0/20. Robustness measured, not assumed.
        TAU_BPS = 1.0e6            # 2 % of the background's own 50 Mbps offer
        per = {}
        for arm in ARMS:
            viol = prem = ok = 0
            sev = []
            for cell in g12["cells"].values():
                if arm not in cell:
                    continue
                for sd in cell[arm]["per_seed"]:
                    starved = [p for p in sd["per_point"]
                               if (p.get("telemetry_m02") or 0) >= 0.99]
                    sev.append(max((p.get("telemetry_m02") or 0)
                                   for p in sd["per_point"]))
                    if not starved:
                        ok += 1
                    elif any((p.get("bg_bps") or 0) >= TAU_BPS for p in starved):
                        viol += 1
                    else:
                        prem += 1
            per[arm] = dict(n=viol + prem + ok, passes=ok + prem,
                            sev=med(sev), sev_fail=None,
                            note=f"{viol} violation / {prem} premise-fails / {ok} pass")
        out.append((dict(g="G12", clause="c4: never starve telemetry while a lower class is served",
                         column=_NO_ATTACH_COLUMN,
                         sums_over="telemetry M02 and background throughput, "
                                   "per ramp point",
                         claim_about="the same two flows -- no mismatch",
                         source="test plan L106. FLOOR FOR 'still has throughput' "
                                "IS NOT STATED -- tau=1 Mbps (2 % of the 50 Mbps "
                                "offer); verdict robust for tau in [0.01, 8] Mbps"),
                    per))
    return out


def score():
    out = []
    for c in CLAUSES:
        _require_population(c)          # a row without one does not score
        blob = load(c["art"])
        if blob is None:
            out.append((c, None))
            continue
        rows = blob[c["rows"]]
        per_arm = {}
        for arm in ARMS:
            R = [r for r in rows if r.get("arm") == arm]
            ok = [r for r in R if c["ok"](c["stat"](r))]
            bad = [r for r in R if r not in ok]
            per_arm[arm] = dict(
                n=len(R), passes=len(ok),
                sev=med([c["sev"](r) for r in R]),
                sev_fail=med([c["sev"](r) for r in bad]) if bad else None)
        out.append((c, per_arm))
    return out + _nested()


def selftest() -> int:
    """Every predicate must be able to fail. Perturb the statistic across the
    threshold and assert the verdict flips -- in BOTH directions, so a
    predicate that is always-true and one that is always-false both fail."""
    bad = []
    for c in CLAUSES:
        blob = load(c["art"])
        if blob is None:
            bad.append(f"{c['g']} {c['clause']}: artefact missing"); continue
        rows = blob[c["rows"]]
        vals = [c["stat"](r) for r in rows]
        verdicts = {c["ok"](v) for v in vals}

        # REAL DATA BEATS A SYNTHETIC FLIP. If both verdicts occur in the
        # artefact, the predicate is demonstrably falsifiable and no
        # perturbation is needed -- that is stronger evidence, not weaker.
        # The first version tested only a synthetic flip and flagged seven
        # sound predicates, including three whose data plainly contained
        # both verdicts, because its perturbation assumed an inequality on a
        # scalar and these are equality tests and (value, bound) pairs.
        if len(verdicts) == 2:
            print(f"  OK  {c['g']:4s} {c['clause'][:46]:46s} "
                  f"BOTH verdicts occur in the artefact")
            continue

        # One verdict only: the predicate must still be shown able to produce
        # the other. Candidates are built from the observed shape rather than
        # assuming one.
        def candidates(v):
            if isinstance(v, tuple):
                lo = tuple([0] + list(v[1:]))
                hi = tuple([float("inf")] + list(v[1:]))
                return [lo, hi]
            if isinstance(v, (int, float)):
                return [0, 1, -1e9, 1e9]
            return []

        outs = set()
        for v in vals:
            for cand in candidates(v):
                try:
                    outs.add(c["ok"](cand))
                except Exception:
                    pass
        if outs >= {True, False}:
            only = verdicts.pop()
            print(f"  OK  {c['g']:4s} {c['clause'][:46]:46s} flips both ways; "
                  f"observed: only {only} in this data -- "
                  f"NO DISCRIMINATING POWER on this evidence")
        else:
            bad.append(f"{c['g']} {c['clause']}: predicate cannot flip "
                       f"(observed {verdicts}, synthetic {outs})")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def denominators() -> int:
    """Every denominator stated and checked against what it claims to
    aggregate. G10 (40) and G12 (20) differ from the rest (10) and are the
    ones worth confirming."""
    rc = 0
    for c in CLAUSES:
        blob = load(c["art"])
        if blob is None:
            continue
        rows = blob[c["rows"]]
        for arm in ARMS:
            R = [r for r in rows if r.get("arm") == arm]
            seeds = {r.get("seed") for r in R}
            cells = {(r.get("n_ues"), r.get("load_mult")) for r in R}
            claim = len(seeds) * len(cells)
            flag = "" if claim == len(R) else "  <-- MISMATCH"
            if flag:
                rc = 1
            print(f"  {c['g']:4s} {c['clause'][:40]:40s} {arm:12s} "
                  f"n={len(R):3d} = {len(seeds)} seeds x {len(cells)} cells{flag}")
    return rc


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--denominators", action="store_true")
    ap.add_argument("--attach", action="store_true",
                    help="score the WITH-ATTACH column")
    a = ap.parse_args(argv)
    global USE_ATTACH
    USE_ATTACH = a.attach
    if a.selftest:
        print("PREDICATE FALSIFIABILITY -- can each clause report a failure?")
        return selftest()
    if a.denominators:
        print("DENOMINATORS -- does n equal seeds x cells?")
        return denominators()

    print(f"{'G':4s} {'clause':46s} {'arm':12s} {'success':>9s} "
          f"{'sev(M02)':>10s} {'sev|fail':>9s}")
    print("-" * 96)
    for c, per in score():
        if per is None:
            print(f"{c['g']:4s} {c['clause'][:46]:46s} ARTEFACT MISSING")
            continue
        for arm in ARMS:
            d = per[arm]
            sev = "--" if d["sev"] is None else f"{d['sev']:.5f}"
            sf = "--" if d["sev_fail"] is None else f"{d['sev_fail']:.5f}"
            note = f"   {d['note']}" if d.get("note") else ""
            print(f"{c['g']:4s} {c['clause'][:46]:46s} {arm:12s} "
                  f"{d['passes']:>4d}/{d['n']:<4d} {sev:>10s} {sf:>9s}{note}")
        if c.get("column") and USE_ATTACH:
            print(f"       COLUMN     : {c['column']}")
        print(f"       sums over : {c.get('sums_over')}")
        print(f"       claim about: {c.get('claim_about')}")
        print()
    print("NOT COMPUTABLE:")
    for g, cl, why, art in NOT_COMPUTABLE:
        print(f"  {g:4s} {cl[:44]:44s} {why[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
