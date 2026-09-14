"""Tabulate G3 part-A (fleet axis) per arm from the published artefacts plus
the scratch RR-age run. Pass counts of 10 per N; boundary = last N passing
before first failure (the repo's own rule)."""
import json, sys
from pathlib import Path

REPO = Path(r"c:/Users/Smart/Documents/Personal/Rahul R/5g/5g-qos-stack-personal")
SCR = Path(__file__).parent
SRC = [
    (REPO / "sweeps/g3-stress/g3_stress.json", ("PF", "Reservation", "TwoTier")),
    (REPO / "sweeps/g3-proto/g3_gkpi100.json", ("ProtoGkpi100",)),
    (SCR / "g3_rr.json", ("ProtoGkpiD2", "ProtoRRage", "ProtoRRageD2")),
    (SCR / "g3_age.json", ("ProtoAgeD2", "ProtoAge")),
    (SCR / "g3_age2.json", ("ProtoAgeD2", "ProtoAgeC34D2", "ProtoC34D2")),
    (REPO / "sweeps/g3-proto/g3_kpi_heldout.json", ("TwoTier", "ProtoGkpi100")),
    (SCR / "g3_rr_heldout.json", ("ProtoRRageD2",)),
]
# the same arm name measured under two definitions: label by file
RELABEL = {("g3_age.json", "ProtoAgeD2"): "AgeD2(ue-clk)", ("g3_age.json", "ProtoAge"): "Age(ue-clk)",
           ("g3_kpi_heldout.json", "TwoTier"): "TwoTier(held)",
           ("g3_kpi_heldout.json", "ProtoGkpi100"): "Gkpi100(held)",
           ("g3_rr_heldout.json", "ProtoRRageD2"): "RRageD2(held)"}
blocks = {}
camp = {}
for path, arms in SRC:
    if not path.exists():
        print("missing", path); continue
    d = json.loads(path.read_text())
    for a in arms:
        label = RELABEL.get((path.name, a), a)
        b = d.get(f"A/cap4/{a}")
        if b:
            blocks[label] = b
        c = d.get("part2_campaign_by_arm", {}).get(a)
        if c:
            camp[label] = c

ns = sorted({p["n_ues"] for b in blocks.values() for p in b["points"]})
for part in ("part1_pass", "part1s_pass", "part2_pass", "part3_pass", "all_pass"):
    print(f"\n=== {part} (of 10) ===")
    print(f"{'arm':14s}" + "".join(f"{n:>5d}" for n in ns) + "   boundary")
    for a, b in blocks.items():
        by = {p["n_ues"]: p for p in b["points"]}
        row = "".join(f"{by[n][part]:>5d}" if n in by else "    -" for n in ns)
        bkey = "boundary_" + part.replace("_pass", "")
        print(f"{a:14s}{row}   {b.get(bkey)}")
for stat in ("p98_median_ms", "p98_worst_ms", "gap_worst_ms", "silence_worst_ms", "msgs_short", "prot_ul_mbps_median"):
    print(f"\n=== {stat} ===")
    print(f"{'arm':14s}" + "".join(f"{n:>8d}" for n in ns))
    for a, b in blocks.items():
        by = {p["n_ues"]: p for p in b["points"]}
        def fmt(v):
            return f"{v:>8.1f}" if isinstance(v, float) else f"{v:>8}"
        print(f"{a:14s}" + "".join(fmt(by[n].get(stat)) if n in by else "       -" for n in ns))
print("\n=== campaign silences >= 2 s ===")
for a, c in camp.items():
    print(f"{a:14s} {c['gaps_over_t_live']} of {c['gaps_scored']}  ({c['verdict']})")
