"""Tables for docs/results-aligned-2026-09-14.md, from THIS directory's
artefacts only (all produced under TDD-aligned HARQ retransmissions).
Run: uv run python sweeps/g3-proto/rrage-2026-09-14/aligned/report_tables.py
"""
import json, statistics as st
from collections import defaultdict
from pathlib import Path

D = Path(__file__).parent
ARMS = ("PF", "Reservation", "TwoTier", "ProtoRRageD2")


def load(name):
    p = D / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def md(header, rows):
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    print()


# ---------------------------------------------------------------- G3
g3 = load("g3.json")
if g3:
    print("## G3 tables\n")
    ns = None
    for part, label in (("part1_pass", "part 1 (max gap <= 500 ms)"),
                        ("part1s_pass", "part 1s (longest silence <= 500 ms)"),
                        ("part2_pass", "part 2 (no gap >= 2 s in run)"),
                        ("part3_pass", "part 3 (p98 <= 95 ms)"),
                        ("all_pass", "all parts")):
        rows = []
        for a in ARMS:
            b = g3.get(f"A/cap4/{a}")
            if not b:
                continue
            by = {p["n_ues"]: p for p in b["points"]}
            ns = sorted(by)
            rows.append([a] + [by[n][part] for n in ns] +
                        [b.get("boundary_" + part.replace("_pass", ""))])
        print(f"**{label}** — passes of 10 per fleet size, boundary = last N at 10/10 before the first failure\n")
        md(["arm"] + [f"N={n}" for n in ns] + ["boundary"], rows)
    for stat, label, fmt in (("p98_median_ms", "telemetry p98, median over seeds (ms)", "{:.1f}"),
                             ("silence_worst_ms", "worst silence in any seed (ms)", "{:.0f}"),
                             ("msgs_short", "telemetry messages missing, sum over seeds (of 2 000)", "{}"),
                             ("prot_ul_mbps_median", "protected uplink delivered, median (Mbps)", "{:.1f}")):
        rows = []
        for a in ARMS:
            b = g3.get(f"A/cap4/{a}")
            if not b:
                continue
            by = {p["n_ues"]: p for p in b["points"]}
            rows.append([a] + [fmt.format(by[n][stat]) for n in ns])
        print(f"**{label}**\n")
        md(["arm"] + [f"N={n}" for n in ns], rows)
    print("**campaign-wide silences >= 2 s (clause part 2 as written)**\n")
    md(["arm", "gaps >= 2 s", "gaps scored", "verdict"],
       [[a, c["gaps_over_t_live"], c["gaps_scored"], c["verdict"]]
        for a, c in g3["part2_campaign_by_arm"].items()])

# ---------------------------------------------------------------- G5
g5 = load("g5.json")
if g5:
    print("## G5 tables\n")
    rows_all = g5["rows"]
    bound = rows_all[0]["age_bound_ms"]

    def cells_for(kind, axis):
        c = defaultdict(list)
        for r in rows_all:
            if r["kind"] == kind:
                c[(r["arm"], r[axis])].append(r)
        return c

    for kind, axis, label in (("gt31", "n_ues", "GT-3.1 fleet axis (N robots)"),
                              ("gt32", "load_mult", "GT-3.2 committed-portfolio load multiplier (N = 7)"),
                              ("gt33", "snr_db", "GT-3.3 Asset B SNR (dB), N = 7")):
        c = cells_for(kind, axis)
        xs = sorted({x for _, x in c})
        print(f"**{label}** — passes of 10 as part 1 / 2 / 3 / 4\n")
        rows = []
        for a in ARMS:
            row = [a]
            for x in xs:
                rr = c.get((a, x))
                row.append("/".join(str(sum(r[k] for r in rr)) for k in
                                    ("part1_pass", "part2_pass", "part3_pass", "part4_pass")) if rr else "-")
            rows.append(row)
        md(["arm"] + [f"{x:g}" for x in xs], rows)
        print(f"**{label}** — median frame-age p95 (ms; bound {bound:.2f}) / median PDU-set completeness\n")
        rows = []
        for a in ARMS:
            row = [a]
            for x in xs:
                rr = c.get((a, x))
                if not rr:
                    row.append("-"); continue
                ages = [r["cam_age_p95_ms"] for r in rr if r["cam_age_p95_ms"] is not None]
                comp = [r["cam_complete_frac"] for r in rr if r["cam_complete_frac"] is not None]
                row.append(f"{st.median(ages):.1f} / {st.median(comp):.3f}" if ages and comp else "-")
            rows.append(row)
        md(["arm"] + [f"{x:g}" for x in xs], rows)
        if kind == "gt31":
            print("**admissible fleet (parts 1 and 2 both 10/10, last N before the first failure)**\n")
            rows = []
            for a in ARMS:
                last, broken = None, False
                for x in xs:
                    rr = c.get((a, x))
                    ok = bool(rr) and len(rr) == 10 and all(r["part1_pass"] and r["part2_pass"] for r in rr)
                    if ok and not broken:
                        last = x
                    else:
                        broken = True
                rows.append([a, last])
            md(["arm", "admissible fleet"], rows)

# ---------------------------------------------------------------- G7
g7 = load("g7.json")
if g7:
    print("## G7 table\n")
    rows_all = g7["rows"] if isinstance(g7, dict) else g7
    by = defaultdict(list)
    for r in rows_all:
        by[r["arm"]].append(r)
    def med(a, k):
        return st.median(r[k] for r in by[a])
    spec = [("clause 2 — B camera delivered ÷ MFBR", lambda a: f"{med(a,'B_camera_throughput_bps')/med(a,'B_camera_mfbr_bps'):.2f}×"),
            ("clause 1 — A telemetry delivered (bps, contract 24 000)", lambda a: f"{med(a,'A_telemetry_throughput_bps'):.0f}"),
            ("clause 1 — A telemetry p98 (ms, PDB 100)", lambda a: f"{med(a,'A_telemetry_p98_ms'):.1f}"),
            ("clause 1 — A camera ÷ GFBR", lambda a: f"{med(a,'A_camera_throughput_bps')/med(a,'A_camera_gfbr_bps'):.3f}"),
            ("clause 1 — A camera p98 (ms, PDB 150)", lambda a: f"{med(a,'A_camera_p98_ms'):.1f}"),
            ("clause 3 — B telemetry delivered (bps)", lambda a: f"{med(a,'B_telemetry_throughput_bps'):.0f}"),
            ("clause 3 — B telemetry p98 (ms)", lambda a: f"{med(a,'B_telemetry_p98_ms'):.1f}"),
            ("uplink PRB utilisation", lambda a: f"{med(a,'ul_prb_util'):.3f}")]
    md(["metric (median of 10 seeds)"] + list(ARMS), [[lab] + [f(a) for a in ARMS] for lab, f in spec])
    print(f"offered: {st.median(r['B_camera_offered_bps'] for r in rows_all)/8e6:.2f}× MFBR achieved\n")

# ---------------------------------------------------------------- G10
g10 = load("g10.json")
if g10:
    print("## G10 tables\n")
    c = defaultdict(list)
    for r in g10["rows"]:
        c[(r["arm"], r["n_ues"])].append(r)
    ns = sorted({n for _, n in c})
    rows = []
    for a in ARMS:
        boundary, broken, row = None, False, [a]
        for n in ns:
            rr = c.get((a, n), [])
            ok = sum(1 for r in rr if r["M07_met"] == r["M07_total"])
            row.append(f"{ok}/{len(rr)}")
            if rr and ok == len(rr) and not broken:
                boundary = n
            else:
                broken = True
        rows.append(row + [boundary])
    print("**seeds with EVERY GBR flow >= 95 % of GFBR (M07), of 10; admissible fleet = last N at 10/10**\n")
    md(["arm"] + [f"N={n}" for n in ns] + ["admissible"], rows)
    print("**median worst-GBR-flow delivered ÷ GFBR (M08)**\n")
    md(["arm"] + [f"N={n}" for n in ns],
       [[a] + [f"{st.median(r['M08_fraction'] for r in c[(a, n)]):.3f}" if c.get((a, n)) else "-" for n in ns] for a in ARMS])
    print("**UEs never granted, sum over seeds**\n")
    md(["arm"] + [f"N={n}" for n in ns],
       [[a] + [sum(r["n_never_granted"] for r in c[(a, n)]) if c.get((a, n)) else "-" for n in ns] for a in ARMS])
