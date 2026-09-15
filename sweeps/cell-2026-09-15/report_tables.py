"""Tables for the deployed-cell campaign (docs/deployed-cell-2026-09-15.md):
G3, G5, G7, G10, then G1, G2, G6, G9, G12, G4, from THIS directory's
aligned/ artefacts only. The two 2026-09-14 scripts joined; table shapes
unchanged so the two campaigns read side by side.
Run: uv run python sweeps/cell-2026-09-15/report_tables.py
"""
import json, statistics as st
from collections import defaultdict
from pathlib import Path

D = Path(__file__).parent / "aligned"
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




# ---------------------------------------------------------------- G1
g1 = load("g1.json")
if g1:
    print("## G1 tables\n")
    for cap in (4, 2):
        for part, axis, label in (("A", "n_ues", "fleet axis (committed x1)"),
                                  ("B", "committed_mult", f"load axis (N = {g1['_fixed_n']})")):
            rows = []
            xs = None
            for a in ARMS:
                b = g1.get(f"{part}/cap{cap}/{a}")
                if not b:
                    continue
                by = {p[axis]: p for p in b["points"]}
                xs = sorted(by)
                rows.append([a] + [f"{by[x]['part1_pass']}/{by[x]['part2_pass']}" for x in xs]
                            + [b.get("boundary_both")])
            if rows:
                print(f"**cap {cap}, {label}** — passes of 10 as part 1 (p98 <= 95 ms) / part 2 (zero gaps >= 200 ms); boundary = both parts 10/10\n")
                md(["arm"] + [f"{x:g}" for x in xs] + ["boundary"], rows)
                rows = []
                for a in ARMS:
                    b = g1.get(f"{part}/cap{cap}/{a}")
                    if not b:
                        continue
                    by = {p[axis]: p for p in b["points"]}
                    rows.append([a] + [f"{by[x]['p98_median_ms']:.2f} / {by[x]['p98_worst_ms']:.2f} / {by[x]['worst_gap_ms']:.0f}" for x in xs])
                print(f"**cap {cap}, {label}** — cmd_vel p98 median / p98 worst (ms) / worst command gap (ms)\n")
                md(["arm"] + [f"{x:g}" for x in xs], rows)
    print(f"runs: {g1['_n_runs']}  horizon {g1['_horizon_slots']}  driven robots {g1['_n_driven']}  PDB {g1['_ran_pdb_ms']}  gap bound {g1['_gap_bound_ms']}\n")

# ---------------------------------------------------------------- G2
g2 = load("g2.json")
if g2:
    print("## G2 tables\n")
    c = g2.get("_campaign", {})
    print(f"**campaign:** {c.get('missed')} missed of {c.get('stop_events')} STOP events; miss-rate {c.get('miss_rate', 0):.2e}; 95 % upper bound {c.get('bound_95', 0):.2e} ({c.get('bound_method')})\n")
    rows = defaultdict(lambda: defaultdict(int))
    for r in g2["rows"]:
        rows[(r["arm"], r["cap"])]["missed"] += r["n_missed"]
        rows[(r["arm"], r["cap"])]["events"] += r["n_events"]
        rows[(r["arm"], r["cap"])]["worst"] = max(rows[(r["arm"], r["cap"])]["worst"], r["worst_ms"])
    print("**per arm and cap, whole campaign** — missed / STOP events, worst delivered STOP latency (ms)\n")
    md(["arm", "cap 4 missed/events", "cap 4 worst ms", "cap 2 missed/events", "cap 2 worst ms"],
       [[a, f"{rows[(a,4)]['missed']}/{rows[(a,4)]['events']}", f"{rows[(a,4)]['worst']:.2f}",
         f"{rows[(a,2)]['missed']}/{rows[(a,2)]['events']}", f"{rows[(a,2)]['worst']:.2f}"] for a in ARMS])
    for cap in (4, 2):
        for part, axis, label in (("A", "n_stop", f"simultaneous-STOP axis (N = {g2['_fixed_n']})"),
                                  ("B", "n_ues", f"fleet axis (STOP = {g2['_fixed_stop']})")):
            rows_, xs = [], None
            for a in ARMS:
                b = g2.get(f"{part}/cap{cap}/{a}")
                if not b:
                    continue
                by = {p[axis]: p for p in b["points"]}
                xs = sorted(by)
                rows_.append([a] + [f"{by[x]['missed']}/{by[x]['stop_events']}" for x in xs])
            if rows_:
                print(f"**cap {cap}, {label}** — missed / STOP events\n")
                md(["arm"] + [f"{x:g}" for x in xs], rows_)

# ---------------------------------------------------------------- G6
g6 = load("g6.json")
if g6:
    print("## G6 tables\n")
    dl = g6["deltas"]
    conds = [c for c in ("ul", "dl") if any(d["condition"] == c for d in dl)]
    print("**pass counts over all paired deltas (3 instruments x 3 fleet sizes x 10 seeds x statistics)** — part A (within its own bound) / part B (shift <= +20 % toward harm)\n")
    rows = []
    for a in ARMS:
        row = [a]
        for cnd in conds:
            ds = [d for d in dl if d["arm"] == a and d["condition"] == cnd]
            row.append(f"{sum(d['part_a'] for d in ds)} / {sum(d['part_b'] for d in ds)} of {len(ds)}")
        rows.append(row)
    md(["arm"] + [f"{c.upper()} flood: A / B of n" for c in conds], rows)
    stats = sorted({d["stat"] for d in dl})
    for cnd in conds:
        print(f"**{cnd.upper()} flood — per statistic, part A / part B passes of 30 (3 fleet sizes x 10 seeds)**\n")
        rows = []
        for s in stats:
            row = [s]
            for a in ARMS:
                ds = [d for d in dl if d["arm"] == a and d["condition"] == cnd and d["stat"] == s]
                row.append(f"{sum(d['part_a'] for d in ds)}/{sum(d['part_b'] for d in ds)}" if ds else "-")
            rows.append(row)
        md(["statistic"] + list(ARMS), rows)
    print("**worst absolute telemetry gap under flood, any cell (ms)** — the G6 slide's own headline beside the pass count\n")
    rows = []
    for a in ARMS:
        row = [a]
        for s in ("g3_tele_gap_worst_ms", "g5_tele_gap_worst_ms"):
            vals = [d["value"] for d in dl if d["arm"] == a and d["stat"] == s and d["condition"] != "none"]
            row.append(f"{max(vals):.0f}" if vals else "-")
        rows.append(row)
    md(["arm", "G3 instrument", "G5 instrument"], rows)

# ---------------------------------------------------------------- G9
g9 = load("g9.json")
if g9:
    print("## G9 tables\n")
    keys = [k for k in g9 if "/" in k]
    seedings = sorted({k.split("/")[0] for k in keys})
    cases = sorted({k.split("/")[1] for k in keys}, key=lambda c: ("warm", "cold", "rlf").index(c) if c in ("warm", "cold", "rlf") else 9)
    occ = sorted({k.split("/")[2] for k in keys}, key=lambda s: int(s.split("_")[0][1:]))
    eps = "eps1ms"
    for seeding in seedings:
        for case in cases:
            print(f"**{case} re-join, {seeding}** — pass rate · attach / first-service / stable-cell p50 (s) · neighbours within 1 ms · catastrophic/broken seeds\n")
            rows = []
            for a in ARMS:
                row = [a]
                for o in occ:
                    b = g9.get(f"{seeding}/{case}/{o}/{a}", {}).get(eps)
                    if not b:
                        row.append("-"); continue
                    def f(v):
                        return "-" if v is None else f"{v:.2f}"
                    row.append(f"{b['pass_rate']} · {f(b.get('attach_p50_s'))}/{f(b.get('first_service_p50_s'))}/{f(b.get('stable_cell_p50_s'))} s · {b.get('neighbours_within_eps', '-')} · c{b.get('catastrophic_seeds', 0)}b{b.get('cell_broken_seeds', 0)}")
                rows.append(row)
            md(["arm"] + occ, rows)
    print(f"runs: {g9.get('_n_runs')}  cap {g9.get('_cap')}  axis (N, committed) {g9.get('_axis')}\n")

# ---------------------------------------------------------------- G12
g12 = load("g12.json")
if g12:
    print("## G12 tables\n")
    keys = [k for k in g12 if "/" in k]
    tbs = sorted({k.split("/")[0] for k in keys})
    cells = sorted({k.split("/")[1] for k in keys})
    print(f"ramp {g12.get('_ramp')}; specified first-violation order {g12.get('_specified_order')}\n")
    for tb in tbs:
        for cell in cells:
            print(f"**{cell}, {tb}** — clause 4 (safety telemetry survives) PASS / VIOLATION / PREMISE-FAILS of 10; first-violation orders seen; agreement\n")
            rows = []
            for a in ARMS:
                b = g12.get(f"{tb}/{cell}/{a}")
                if not b:
                    continue
                c4 = b["clause4"]
                rows.append([a, f"{c4.get('PASS', 0)} / {c4.get('VIOLATION', 0)} / {c4.get('PREMISE FAILS', 0)}",
                             str(b.get("orders_seen")), b.get("order_agreement"), b.get("matches_specified")])
            md(["arm", "clause 4", "orders seen", "agreement", "matches spec"], rows)

# ---------------------------------------------------------------- G4
g4 = load("g4.json")
if g4:
    print("## G4 tables\n")
    s = g4["summary"]
    ad = s.get("across_duty", {})
    duties = sorted({d for a in ad.values() for d in a}, key=float)
    print("**across duty levels, per arm** — post-silence p98 (ms) / p98 at duty 1.0 baseline / ratio\n")
    rows = []
    for a in ARMS:
        row = [a]
        for d in duties:
            v = ad.get(a, {}).get(d)
            row.append(f"{v['p98_ms']:.1f} / {v['base_p98_ms']:.1f} / {v['ratio']:.2f}" if v else "-")
        rows.append(row)
    md(["arm"] + [f"duty {d}" for d in duties], rows)
    aa = s.get("across_arms", {})
    print("**across arms at one duty level (confound-free)**\n")
    print(json.dumps(aa, indent=1, default=str)[:2500])
    print()
