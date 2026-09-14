"""G10 admissible fleet: per (arm, N) seeds with every GBR target met
(M07_met == M07_total), median M08; boundary = last N with all seeds passing
before the first failure (the repo's rule)."""
import json, statistics as st
from collections import defaultdict
from pathlib import Path
REPO = Path(r"c:/Users/Smart/Documents/Personal/Rahul R/5g/5g-qos-stack-personal")
SCR = Path(__file__).parent
rows = []
for p in (REPO / "sweeps/g1-stress/g10_remeasure_cap4.json", SCR / "g10_rrage.json"):
    if p.exists():
        rows += json.loads(p.read_text())["rows"]
    else:
        print("missing", p)
cells = defaultdict(list)
for r in rows:
    cells[(r["arm"], r["n_ues"])].append(r)
arms = sorted({a for a, _ in cells}, key=lambda a: (a.startswith("Proto"), a))
ns = sorted({n for _, n in cells})
print(f"{'arm':14s}" + "".join(f"{n:>9d}" for n in ns) + "   boundary")
for a in arms:
    out, boundary, broken = "", None, False
    for n in ns:
        c = cells.get((a, n))
        if not c:
            out += f"{'-':>9}"; continue
        ok = sum(1 for r in c if r["M07_met"] == r["M07_total"])
        out += f"{ok:>4d}/{len(c):<4d}"
        if ok == len(c) and not broken:
            boundary = n
        else:
            broken = True
    print(f"{a:14s}{out}   {boundary}")
print("\nmedian M08 (worst GBR flow delivered/GFBR):")
for a in arms:
    print(f"{a:14s}" + "".join(f"{st.median([r['M08_fraction'] for r in cells[(a, n)]]):>9.3f}" if cells.get((a, n)) else f"{'-':>9}" for n in ns))
print("\nnever-granted UEs (sum over seeds):")
for a in arms:
    print(f"{a:14s}" + "".join(f"{sum(r['n_never_granted'] for r in cells[(a, n)]):>9d}" if cells.get((a, n)) else f"{'-':>9}" for n in ns))
