"""Tabulate G5 (video) per arm from the published artefacts plus scratch runs.
Aggregated from rows: GT-3.1 fleet axis passes of 10 per part, median frame
age p95; GT-3.2 load ceiling; GT-3.3 edge."""
import json, statistics as st
from collections import defaultdict
from pathlib import Path

REPO = Path(r"c:/Users/Smart/Documents/Personal/Rahul R/5g/5g-qos-stack-personal")
SCR = Path(__file__).parent
SRC = [REPO / "sweeps/g5-video/g5_video.json",
       REPO / "sweeps/g5-video/g5_protoD2C.json",
       SCR / "g5_rrage.json"]
rows = []
for p in SRC:
    if p.exists():
        rows += json.loads(p.read_text())["rows"]
    else:
        print("missing", p)

def table(kind, axis, label):
    cells = defaultdict(list)
    for r in rows:
        if r["kind"] == kind:
            cells[(r["arm"], r[axis])].append(r)
    arms = sorted({a for a, _ in cells}, key=lambda a: (a.startswith("Proto"), a))
    xs = sorted({x for _, x in cells})
    print(f"\n=== {label}: passes of 10 (p1/p2/p3/p4) ===")
    print(f"{'arm':14s}" + "".join(f"{str(x):>14}" for x in xs))
    for a in arms:
        out = ""
        for x in xs:
            c = cells.get((a, x))
            if not c:
                out += f"{'-':>14}"; continue
            out += f"{sum(r['part1_pass'] for r in c):>3}/{sum(r['part2_pass'] for r in c)}/{sum(r['part3_pass'] for r in c)}/{sum(r['part4_pass'] for r in c):<4}  "
        print(f"{a:14s}{out}")
    print(f"--- median frame age p95 (ms; bound {rows[0]['age_bound_ms']:.2f}) / median completeness ---")
    for a in arms:
        out = ""
        for x in xs:
            c = cells.get((a, x))
            if not c:
                out += f"{'-':>14}"; continue
            ages = [r["cam_age_p95_ms"] for r in c if r["cam_age_p95_ms"] is not None]
            comp = [r["cam_complete_frac"] for r in c if r["cam_complete_frac"] is not None]
            out += f"{(st.median(ages) if ages else float('nan')):>7.1f}/{(st.median(comp) if comp else float('nan')):.3f} "
        print(f"{a:14s}{out}")
    return cells, arms, xs

cells, arms, xs = table("gt31", "n_ues", "GT-3.1 fleet axis")
print("\n--- admissible fleet (parts 1-2, last N with 10/10 before first failure) ---")
for a in arms:
    last = None
    for x in xs:
        c = cells.get((a, x))
        if not c: continue
        ok = all(r["part1_pass"] and r["part2_pass"] for r in c) and len(c) == 10
        if ok: last = x
        else: break
    print(f"{a:14s} {last}")
table("gt32", "load_mult", "GT-3.2 load ceiling")
table("gt33", "snr_db", "GT-3.3 cell edge")
