"""ConfigSched (the 2026-09-16 campaign) against ConfigSched2 (one increment),
per guarantee, on the statistics each section of docs/results-cell-2026-09-15.md
decides by. Both artefact sets were produced by the same runners on the same
seeds, so every line is a within-seed comparison of one code change.

Run: uv run python sweeps/cs2-increments/compare.py sweeps/cs2-increments/inc1 [--before DIR] [--arm ConfigSched2]
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
INC = Path(args[0])
BEFORE = Path(sys.argv[sys.argv.index("--before") + 1]) if "--before" in sys.argv else Path("sweeps/cell-2026-09-16-linux")
# `--arm-before` is needed whenever BEFORE is another INCREMENT rather than the
# campaign: an increment's artefacts hold only `ConfigSched2`, so the default
# `ConfigSched` finds nothing and every section raises a KeyError that a
# caller's grep can hide (it did, 2026-09-16). Defaults to the campaign's arm.
ARM_B = sys.argv[sys.argv.index("--arm-before") + 1] if "--arm-before" in sys.argv else "ConfigSched"
ARM_A = sys.argv[sys.argv.index("--arm") + 1] if "--arm" in sys.argv else "ConfigSched2"


def load(root, name):
    p = root / "aligned" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def line(label, before, after):
    flag = "" if before == after else "   <- moved"
    print(f"  {label:44s} {str(before):>26s} | {str(after):<26s}{flag}")


def section(title):
    print(f"\n== {title}   ({ARM_B} campaign | {ARM_A} increment)")


# ---------------------------------------------------------------- G3
b, a = load(BEFORE, "g3.json"), load(INC, "g3.json")
if b and a:
    section("G3 -- passes of 10 per N, boundaries, campaign part 2")
    pb, pa = b[f"A/cap4/{ARM_B}"], a[f"A/cap4/{ARM_A}"]
    nb = {p["n_ues"]: p for p in pb["points"]}; na = {p["n_ues"]: p for p in pa["points"]}
    for part in ("part1_pass", "part1s_pass", "part2_pass", "part3_pass", "all_pass"):
        line(part, " ".join(str(nb[n][part]) for n in sorted(nb)), " ".join(str(na[n][part]) for n in sorted(na)))
        line(f"  boundary_{part.replace('_pass', '')}", pb.get("boundary_" + part.replace("_pass", "")), pa.get("boundary_" + part.replace("_pass", "")))
    for stat in ("p98_median_ms", "silence_worst_ms", "msgs_short"):
        line(stat, " ".join(f"{nb[n][stat]:g}" for n in sorted(nb)), " ".join(f"{na[n][stat]:g}" for n in sorted(na)))
    cb, ca = b["part2_campaign_by_arm"][ARM_B], a["part2_campaign_by_arm"][ARM_A]
    line("campaign gaps>=2s / scored", f"{cb['gaps_over_t_live']}/{cb['gaps_scored']} {cb['verdict']}", f"{ca['gaps_over_t_live']}/{ca['gaps_scored']} {ca['verdict']}")

# ---------------------------------------------------------------- G5
b, a = load(BEFORE, "g5.json"), load(INC, "g5.json")
if b and a:
    section("G5 -- parts 1/2/3/4 of 10 and frame age per axis point; admissible fleet; load knee")
    def cells(rows, arm):
        c = defaultdict(list)
        for r in rows:
            if r["arm"] == arm:
                c[(r["kind"], r.get("n_ues") if r["kind"] == "gt31" else r.get("load_mult") if r["kind"] == "gt32" else r.get("snr_db"))].append(r)
        return c
    cb, ca = cells(b["rows"], ARM_B), cells(a["rows"], ARM_A)
    def fmt(rr):
        if not rr: return "-"
        ages = [r["cam_age_p95_ms"] for r in rr if r["cam_age_p95_ms"] is not None]
        return "/".join(str(sum(r[k] for r in rr)) for k in ("part1_pass", "part2_pass", "part3_pass", "part4_pass")) + (f" {st.median(ages):.0f}ms" if ages else "")
    for kind in ("gt31", "gt32", "gt33"):
        xs = sorted({x for k, x in cb if k == kind})
        for x in xs:
            line(f"{kind} {x:g}", fmt(cb.get((kind, x))), fmt(ca.get((kind, x))))
    def admissible(c):
        last, broken = None, False
        for x in sorted({x for k, x in c if k == "gt31"}):
            rr = c.get(("gt31", x))
            ok = bool(rr) and len(rr) == 10 and all(r["part1_pass"] and r["part2_pass"] for r in rr)
            if ok and not broken: last = x
            else: broken = True
        return last
    def knee(c):
        for x in sorted({x for k, x in c if k == "gt32"}):
            rr = c.get(("gt32", x))
            if not (rr and all(r["part1_pass"] and r["part2_pass"] for r in rr)): return x
        return "none"
    line("admissible fleet", admissible(cb), admissible(ca))
    line("load knee", knee(cb), knee(ca))

# ---------------------------------------------------------------- G7
b, a = load(BEFORE, "g7.json"), load(INC, "g7.json")
if b and a:
    section("G7 -- medians of 10 seeds")
    rb = [r for r in (b["rows"] if isinstance(b, dict) else b) if r["arm"] == ARM_B]
    ra = [r for r in (a["rows"] if isinstance(a, dict) else a) if r["arm"] == ARM_A]
    def med(rows, k): return st.median(r[k] for r in rows)
    line("clause 2  B camera / MFBR", f"{med(rb,'B_camera_throughput_bps')/med(rb,'B_camera_mfbr_bps'):.2f}x", f"{med(ra,'B_camera_throughput_bps')/med(ra,'B_camera_mfbr_bps'):.2f}x")
    for k, lab in (("A_telemetry_throughput_bps", "clause 1  A telemetry bps"), ("A_telemetry_p98_ms", "clause 1  A telemetry p98 ms"),
                   ("A_camera_p98_ms", "clause 1  A camera p98 ms"), ("B_telemetry_p98_ms", "clause 3  B telemetry p98 ms"), ("ul_prb_util", "UL PRB util")):
        line(lab, f"{med(rb,k):.1f}", f"{med(ra,k):.1f}")

# ---------------------------------------------------------------- G10
b, a = load(BEFORE, "g10.json"), load(INC, "g10.json")
if b and a:
    section("G10 -- seeds with every GBR flow >= 95 % (of 10) per N; admissible; worst-flow/GFBR")
    def cells(rows, arm):
        c = defaultdict(list)
        for r in rows:
            if r["arm"] == arm: c[r["n_ues"]].append(r)
        return c
    cb, ca = cells(b["rows"], ARM_B), cells(a["rows"], ARM_A)
    def m07(c): return " ".join(str(sum(1 for r in c[n] if r["M07_met"] == r["M07_total"])) for n in sorted(c))
    def adm(c):
        last, broken = None, False
        for n in sorted(c):
            ok = all(r["M07_met"] == r["M07_total"] for r in c[n])
            if ok and not broken: last = n
            else: broken = True
        return last
    line("M07 seeds per N " + str(sorted(cb)), m07(cb), m07(ca))
    line("admissible fleet", adm(cb), adm(ca))
    line("M08 median per N", " ".join(f"{st.median(r['M08_fraction'] for r in cb[n]):.3f}" for n in sorted(cb)), " ".join(f"{st.median(r['M08_fraction'] for r in ca[n]):.3f}" for n in sorted(ca)))

# ---------------------------------------------------------------- G1
b, a = load(BEFORE, "g1.json"), load(INC, "g1.json")
if b and a:
    section("G1 -- boundary and cmd_vel p98 median per N (fleet axis) at cap 4 / cap 2")
    for cap in (4, 2):
        pb, pa = b[f"A/cap{cap}/{ARM_B}"], a[f"A/cap{cap}/{ARM_A}"]
        nb = {p["n_ues"]: p for p in pb["points"]}; na = {p["n_ues"]: p for p in pa["points"]}
        line(f"cap {cap} boundary (both parts)", pb.get("boundary_both"), pa.get("boundary_both"))
        line(f"cap {cap} p98 median per N", " ".join(f"{nb[n]['p98_median_ms']:g}" for n in sorted(nb)), " ".join(f"{na[n]['p98_median_ms']:g}" for n in sorted(na)))
        line(f"cap {cap} worst gap per N", " ".join(f"{nb[n]['worst_gap_ms']:g}" for n in sorted(nb)), " ".join(f"{na[n]['worst_gap_ms']:g}" for n in sorted(na)))

# ---------------------------------------------------------------- G2
b, a = load(BEFORE, "g2.json"), load(INC, "g2.json")
if b and a:
    section("G2 -- missed / STOP events, whole campaign per cap; STOP axis and fleet axis at cap 2")
    def tot(d, arm):
        out = defaultdict(lambda: [0, 0])
        for r in d["rows"]:
            if r["arm"] == arm:
                out[r["cap"]][0] += r["n_missed"]; out[r["cap"]][1] += r["n_events"]
        return out
    tb, ta = tot(b, ARM_B), tot(a, ARM_A)
    for cap in (4, 2):
        line(f"cap {cap} missed/events", f"{tb[cap][0]}/{tb[cap][1]}", f"{ta[cap][0]}/{ta[cap][1]}")
    for part, axis in (("A", "n_stop"), ("B", "n_ues")):
        pb, pa = b[f"{part}/cap2/{ARM_B}"], a[f"{part}/cap2/{ARM_A}"]
        xb = {p[axis]: p for p in pb["points"]}; xa = {p[axis]: p for p in pa["points"]}
        line(f"cap 2 {axis} missed", " ".join(f"{xb[x]['missed']}" for x in sorted(xb)), " ".join(f"{xa[x]['missed']}" for x in sorted(xa)))

# ---------------------------------------------------------------- G6
b, a = load(BEFORE, "g6.json"), load(INC, "g6.json")
if b and a:
    section("G6 -- part A / part B of 270 per flood direction; worst telemetry gap")
    for cnd in ("ul", "dl"):
        # SCORED ONLY: a delta whose CONTROL already failed its own bound is not evidence about isolation (g6_isolation.py, 2026-09-16), so it is excluded here and the denominator says so. Summing part_a over gated cells
        # counted an arm's pre-existing capacity failure as isolation harm.
        db = [d for d in b["deltas"] if d["arm"] == ARM_B and d["condition"] == cnd and d.get("scored", True)]
        da = [d for d in a["deltas"] if d["arm"] == ARM_A and d["condition"] == cnd and d.get("scored", True)]
        line(f"{cnd.upper()} flood A/B", f"{sum(d['part_a'] for d in db)}/{sum(d['part_b'] for d in db)} of {len(db)}", f"{sum(d['part_a'] for d in da)}/{sum(d['part_b'] for d in da)} of {len(da)}")
    for s in ("g5_cam_window_floor", "g3_tele_gap_worst_ms"):
        db = [d for d in b["deltas"] if d["arm"] == ARM_B and d["condition"] == "ul" and d["stat"] == s and d.get("scored", True)]
        da = [d for d in a["deltas"] if d["arm"] == ARM_A and d["condition"] == "ul" and d["stat"] == s and d.get("scored", True)]
        line(f"UL {s} A/B of 30", f"{sum(d['part_a'] for d in db)}/{sum(d['part_b'] for d in db)}", f"{sum(d['part_a'] for d in da)}/{sum(d['part_b'] for d in da)}")
    for s in ("g3_tele_gap_worst_ms", "g5_tele_gap_worst_ms"):
        vb = max((d["value"] for d in b["deltas"] if d["arm"] == ARM_B and d["stat"] == s and d["condition"] != "none"), default=None)
        va = max((d["value"] for d in a["deltas"] if d["arm"] == ARM_A and d["stat"] == s and d["condition"] != "none"), default=None)
        line(f"worst {s}", f"{vb:.0f}" if vb else "-", f"{va:.0f}" if va else "-")

# ---------------------------------------------------------------- G9
b, a = load(BEFORE, "g9.json"), load(INC, "g9.json")
if b and a:
    section("G9 -- faithful column: verdict per informative cell; first-service p50 at (5) and (6)")
    keys = [k for k in b if "/" in k]
    occ = sorted({k.split("/")[2] for k in keys}, key=lambda s: int(s.split("_")[0][1:]))
    short = {"PASS": "P", "JOIN FAILURE": "F", "CELL ALREADY BROKEN": "B"}
    for case in ("warm", "cold", "rlf"):
        def row(d, arm):
            out = []
            for o in occ:
                e = d.get(f"unseeded/{case}/{o}/{arm}", {}).get("eps1ms", {})
                fs = e.get("first_service_p50_s")
                out.append(f"{short.get(e.get('outcome'), '?')}c{e.get('catastrophic_seeds', '-')}b{e.get('cell_broken_seeds', '-')}:{'-' if fs is None else f'{fs:.2f}'}")
            return " ".join(out)
        line(f"{case}", row(b, ARM_B), row(a, ARM_A))
    def passed(d, arm):
        return sum(1 for case in ("warm", "cold", "rlf") for o in occ[:4]
                   if d.get(f"unseeded/{case}/{o}/{arm}", {}).get("eps1ms", {}).get("outcome") == "PASS")
    line("informative cells passed of 12", passed(b, ARM_B), passed(a, ARM_A))

# ---------------------------------------------------------------- G12
b, a = load(BEFORE, "g12.json"), load(INC, "g12.json")
if b and a:
    section("G12 -- N = 6 tie-break off: clause 4, orders, telemetry PDB-violation at x1.0/1.4/1.8/2.0, bg Mbps at x2.0")
    for cell in ("tiebreak-off/mixedN6", "tiebreak-off/mixedN4"):
        cb, ca = b[f"{cell}/{ARM_B}"], a[f"{cell}/{ARM_A}"]
        line(f"{cell} clause4 P/V/PF", f"{cb['clause4'].get('PASS',0)}/{cb['clause4'].get('VIOLATION',0)}/{cb['clause4'].get('PREMISE FAILS',0)}", f"{ca['clause4'].get('PASS',0)}/{ca['clause4'].get('VIOLATION',0)}/{ca['clause4'].get('PREMISE FAILS',0)}")
        line(f"{cell} orders / agreement", f"{cb['orders_seen']} {cb['order_agreement']}", f"{ca['orders_seen']} {ca['order_agreement']}")
        pb = {p["mult"]: p for p in cb["per_point"]}; pa = {p["mult"]: p for p in ca["per_point"]}
        line(f"{cell} telemetry M02", "/".join(f"{pb[m]['telemetry_m02_median']:.3f}" for m in (1.0, 1.4, 1.8, 2.0)), "/".join(f"{pa[m]['telemetry_m02_median']:.3f}" for m in (1.0, 1.4, 1.8, 2.0)))
        line(f"{cell} bg Mbps at x2.0", f"{pb[2.0]['bg_mbps_median']:.1f}", f"{pa[2.0]['bg_mbps_median']:.1f}")
