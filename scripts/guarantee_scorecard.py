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
SEV_DIR = "sweeps/sev-2026-09-06"          # artefacts carrying uniform M02
ATT_DIR = "sweeps/attach-2026-09-06"       # the same grid WITH the attach path

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
      source="test plan L95: 'p98 <= RAN PDB (95 ms of the 100 ms 5QI-1 budget)'"),
 dict(g="G1", clause="p98 <= PDB (15 ms, sensor_dense)",
      art=f"{SEV_DIR}/sensor_dense.json", rows="rows",
      stat=lambda r: r["G1_M01_p98"], ok=lambda v: v is not None and v <= 15.0,
      sev=lambda r: r.get("M02_all"),
      source="test plan L95 + the workload's own 15 ms PDB"),
 dict(g="G3", clause="max telemetry gap <= 500 ms",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G3_M03_all_ms"], ok=lambda v: v is not None and v <= 500.0,
      sev=lambda r: r.get("M02_all"),
      source="test plan L97: 'Max telemetry inter-arrival gap <= T_live/4 (500 ms)'"),
 dict(g="G5", clause=">= 99 % PDU sets complete within PDB",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G5_M05_prot"], ok=lambda v: v is not None and v >= 0.99,
      sev=lambda r: r.get("M02_prot"),
      source="test plan L99: '>= 99 % of PDU sets complete within PDB'"),
 dict(g="G8", clause="per-1 s Jain >= 0.90 (parametric)",
      art=f"{SEV_DIR}/core.json", rows="rows",
      stat=lambda r: r["G8_M09_worst_prot"], ok=lambda v: v is not None and v >= 0.90,
      sev=lambda r: r.get("M02_prot"),
      source="test plan L102: 'Per-1 s Jain >= 0.9 per role across assets'"),
 dict(g="G8", clause="per-1 s Jain >= 0.90 (sensor_dense)",
      art=f"{SEV_DIR}/sensor_dense.json", rows="rows",
      stat=lambda r: r["G8_M09_worst"], ok=lambda v: v is not None and v >= 0.90,
      sev=lambda r: r.get("M02_all"),
      source="test plan L102"),
 dict(g="G2", clause="STOP p98 <= 100 ms (UL)",
      art=f"{SEV_DIR}/g2_ul_stop.json", rows="rows",
      stat=lambda r: r["UL_stop_p98_ms"], ok=lambda v: v is not None and v <= 100.0,
      sev=lambda r: r.get("M02_all"),
      source="test plan L96: '100 % of STOP events <= 100 ms'. SUBSTITUTION: "
             "the artefact records p98, not the max, so this is WEAKER than "
             "the stated clause and is labelled rather than silently equated"),
 dict(g="G7", clause="clause 2: aggressor's excess clipped at MFBR",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: (r["B_camera_throughput_bps"] or 0) / max(r["B_camera_mfbr_bps"] or 1, 1),
      ok=lambda v: v <= 1.02,
      sev=lambda r: r.get("M02_all"),
      source="test plan L101: \"B's excess clipped at MFBR\""),
 dict(g="G7", clause="clause 1: victim's PDU sets >= 99 % complete",
      art=f"{SEV_DIR}/g7.json", rows="rows",
      stat=lambda r: r["A_camera_m05"], ok=lambda v: v is not None and v >= 0.99,
      sev=lambda r: r.get("M02_prot"),
      source="test plan L101 (A's G5 unchanged) + L99's 99 % bound"),
 dict(g="G10", clause="every GBR flow meets contract (per fleet size x seed)",
      art=f"{SEV_DIR}/g10_attach.json", rows="rows",
      stat=lambda r: (r["M07_met"], r["M07_total"]),
      ok=lambda v: v[0] == v[1],
      sev=lambda r: r.get("M02_prot"),
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
                         source="test plan L105 'every 60 s window passes' + "
                                "L122's 98 % conformance basis -> M02w <= 0.02"),
                    per))
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
                         source="test plan L106. FLOOR FOR 'still has throughput' "
                                "IS NOT STATED -- tau=1 Mbps (2 % of the 50 Mbps "
                                "offer); verdict robust for tau in [0.01, 8] Mbps"),
                    per))
    return out


def score():
    out = []
    for c in CLAUSES:
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
        # observed range, and whether a flip is CONSTRUCTIBLE
        if isinstance(vals[0], tuple):
            # "can it produce a pass" and "can it produce a FAIL" -- the
            # second needs the negation. Getting this wrong flagged G10 as
            # unfalsifiable while its data plainly contained both verdicts,
            # which is the self-test failing its own rule.
            flip_pass = c["ok"]((1, 1)); flip_fail = not c["ok"]((0, 1))
        else:
            lo, hi = min(vals), max(vals)
            flip_pass = c["ok"](lo - 1e9) or c["ok"](hi + 1e9)
            flip_fail = (not c["ok"](lo - 1e9)) or (not c["ok"](hi + 1e9))
        if not (flip_pass and flip_fail):
            bad.append(f"{c['g']} {c['clause']}: predicate cannot flip "
                       f"(observed verdicts {verdicts})")
        else:
            span = ("both" if len(verdicts) == 2 else
                    f"only {verdicts.pop()} in this data")
            print(f"  OK  {c['g']:4s} {c['clause'][:46]:46s} flips both ways; "
                  f"observed: {span}")
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
        print()
    print("NOT COMPUTABLE:")
    for g, cl, why, art in NOT_COMPUTABLE:
        print(f"  {g:4s} {cl[:44]:44s} {why[:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
