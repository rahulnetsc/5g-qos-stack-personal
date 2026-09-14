"""Tables for G1, G2, G6, G9, G12, G4 from THIS directory's artefacts only
(all produced under TDD-aligned HARQ retransmissions). Companion to
report_tables.py. Run:
  uv run python sweeps/g3-proto/rrage-2026-09-14/aligned/report_tables2.py
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
