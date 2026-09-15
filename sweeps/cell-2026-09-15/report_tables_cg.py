"""Product + CG tables on the deployed cell: each arm without CG (aligned/),
with restricted CG (+CG) and with the descriptor-driven CG (+CGt,
docs/plan-cg-and-config-scheduler-2026-09-14.md; period and phase from the
declared traffic, `sim/configured_grant.py`). Unrestricted CG (+CGu) is not
re-run: docs/results-cg-2026-09-14.md settled that it breaks G5 on every arm.
Run: uv run python sweeps/cell-2026-09-15/report_tables_cg.py
"""
import json, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
BASE = ROOT / "aligned"
HERE = ROOT / "cg"
ARMS = ("PF", "Reservation", "TwoTier", "ProtoRRageD2")
SUFFIXES = ("", "+CG", "+CGt")


def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def md(header, rows):
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    print()


def cg_totals(rows_or_summary):
    """Aggregate configured_grant totals if the runner kept them (only
    runners that store the driver summary do); else None."""
    return None


# ---------------------------------------------------------------- G3
g3 = {"": load(BASE / "g3.json"), "+CG": load(HERE / "g3_cg.json"), "+CGt": load(HERE / "g3_cgt.json")}
if all(g3.values()):
    print("## G3 — product + CG\n")
    ns = sorted({p["n_ues"] for p in g3[""]["A/cap4/PF"]["points"]})
    for part, label in (("all_pass", "all parts"), ("part3_pass", "part 3 (p98 <= 95 ms)"), ("part1_pass", "part 1 (max gap <= 500 ms)")):
        print(f"**{label} — passes of 10; boundary = last N at 10/10**\n")
        rows = []
        for a in ARMS:
            for sfx in SUFFIXES:
                b = g3[sfx].get(f"A/cap4/{a}{sfx}")
                if not b:
                    continue
                by = {p["n_ues"]: p for p in b["points"]}
                rows.append([a + sfx] + [by[n][part] for n in ns] + [b.get("boundary_" + part.replace("_pass", ""))])
        md(["arm"] + [f"N={n}" for n in ns] + ["boundary"], rows)
    for stat, label, fmt in (("p98_median_ms", "telemetry p98, median (ms)", "{:.1f}"),
                             ("silence_worst_ms", "worst silence (ms)", "{:.0f}"),
                             ("msgs_short", "telemetry messages missing (of 2 000)", "{}"),
                             ("prot_ul_mbps_median", "protected UL delivered (Mbps)", "{:.1f}")):
        print(f"**{label}**\n")
        rows = []
        for a in ARMS:
            for sfx in SUFFIXES:
                b = g3[sfx].get(f"A/cap4/{a}{sfx}")
                if not b:
                    continue
                by = {p["n_ues"]: p for p in b["points"]}
                rows.append([a + sfx] + [fmt.format(by[n][stat]) for n in ns])
        md(["arm"] + [f"N={n}" for n in ns], rows)
    print("**campaign silences >= 2 s**\n")
    rows = []
    for a in ARMS:
        for sfx in SUFFIXES:
            c = g3[sfx].get("part2_campaign_by_arm", {}).get(a + sfx)
            if c:
                rows.append([a + sfx, c["gaps_over_t_live"], c["gaps_scored"], c["verdict"]])
    md(["arm", "gaps >= 2 s", "scored", "verdict"], rows)

# ---------------------------------------------------------------- G5
g5b, g5r, g5u = load(BASE / "g5.json"), load(HERE / "g5_cg.json"), load(HERE / "g5_cgt.json")
if g5b and g5r and g5u:
    print("## G5 — product + CG\n")
    rows_all = g5b["rows"] + g5r["rows"] + g5u["rows"]
    bound = rows_all[0]["age_bound_ms"]
    for kind, axis, label in (("gt31", "n_ues", "GT-3.1 fleet axis"),
                              ("gt32", "load_mult", "GT-3.2 load ceiling (N = 7)"),
                              ("gt33", "snr_db", "GT-3.3 edge SNR (N = 7)")):
        c = defaultdict(list)
        for r in rows_all:
            if r["kind"] == kind:
                c[(r["arm"], r[axis])].append(r)
        xs = sorted({x for _, x in c})
        print(f"**{label} — parts 1/2/3/4 of 10 · frame-age p95 median (ms, bound {bound:.2f})**\n")
        rows = []
        for a in ARMS:
            for sfx in SUFFIXES:
                row = [a + sfx]
                for x in xs:
                    rr = c.get((a + sfx, x))
                    if not rr:
                        row.append("-"); continue
                    ages = [r["cam_age_p95_ms"] for r in rr if r["cam_age_p95_ms"] is not None]
                    row.append("/".join(str(sum(r[k] for r in rr)) for k in ("part1_pass", "part2_pass", "part3_pass", "part4_pass"))
                               + (f" · {st.median(ages):.1f}" if ages else ""))
                rows.append(row)
        md(["arm"] + [f"{x:g}" for x in xs], rows)
        if kind == "gt31":
            print("**admissible fleet (parts 1 and 2 both 10/10)**\n")
            rows = []
            for a in ARMS:
                for sfx in SUFFIXES:
                    last, broken = None, False
                    for x in xs:
                        rr = c.get((a + sfx, x))
                        ok = bool(rr) and len(rr) == 10 and all(r["part1_pass"] and r["part2_pass"] for r in rr)
                        if ok and not broken:
                            last = x
                        else:
                            broken = True
                    rows.append([a + sfx, last])
            md(["arm", "admissible fleet"], rows)

# ---------------------------------------------------------------- G7
g7b, g7c = load(BASE / "g7.json"), load(HERE / "g7.json")
if g7b and g7c:
    print("## G7 — product + CG\n")
    by = defaultdict(list)
    for r in g7b["rows"] + g7c["rows"]:
        by[r["arm"]].append(r)
    arms = [a + s for a in ARMS for s in SUFFIXES if a + s in by]
    def med(a, k):
        return st.median(r[k] for r in by[a])
    spec = [("clause 2 — B camera ÷ MFBR", lambda a: f"{med(a,'B_camera_throughput_bps')/med(a,'B_camera_mfbr_bps'):.2f}×"),
            ("clause 1 — A telemetry bps (of 24 000)", lambda a: f"{med(a,'A_telemetry_throughput_bps'):.0f}"),
            ("clause 1 — A telemetry p98 (ms)", lambda a: f"{med(a,'A_telemetry_p98_ms'):.1f}"),
            ("clause 1 — A camera ÷ GFBR", lambda a: f"{med(a,'A_camera_throughput_bps')/med(a,'A_camera_gfbr_bps'):.3f}"),
            ("clause 1 — A camera p98 (ms)", lambda a: f"{med(a,'A_camera_p98_ms'):.1f}"),
            ("clause 3 — B telemetry bps", lambda a: f"{med(a,'B_telemetry_throughput_bps'):.0f}"),
            ("clause 3 — B telemetry p98 (ms)", lambda a: f"{med(a,'B_telemetry_p98_ms'):.1f}"),
            ("UL PRB utilisation", lambda a: f"{med(a,'ul_prb_util'):.3f}")]
    md(["metric (median of 10)"] + arms, [[lab] + [f(a) for a in arms] for lab, f in spec])

# ---------------------------------------------------------------- G10
g10b, g10c = load(BASE / "g10.json"), load(HERE / "g10.json")
if g10b and g10c:
    print("## G10 — product + CG\n")
    c = defaultdict(list)
    for r in g10b["rows"] + g10c["rows"]:
        c[(r["arm"], r["n_ues"])].append(r)
    ns = sorted({n for _, n in c})
    print("**seeds with every GBR flow >= 95 % of GFBR, of 10; admissible = last N at 10/10**\n")
    rows = []
    for a in ARMS:
        for sfx in SUFFIXES:
            if not any((a + sfx, n) in c for n in ns):
                continue
            boundary, broken, row = None, False, [a + sfx]
            for n in ns:
                rr = c.get((a + sfx, n), [])
                ok = sum(1 for r in rr if r["M07_met"] == r["M07_total"])
                row.append(f"{ok}/{len(rr)}")
                if rr and ok == len(rr) and not broken:
                    boundary = n
                else:
                    broken = True
            rows.append(row + [boundary])
    md(["arm"] + [f"N={n}" for n in ns] + ["admissible"], rows)
    print("**median M08 (worst GBR flow ÷ GFBR)**\n")
    md(["arm"] + [f"N={n}" for n in ns],
       [[a + sfx] + [f"{st.median(r['M08_fraction'] for r in c[(a + sfx, n)]):.3f}" if c.get((a + sfx, n)) else "-" for n in ns]
        for a in ARMS for sfx in SUFFIXES if any((a + sfx, n) in c for n in ns)])
