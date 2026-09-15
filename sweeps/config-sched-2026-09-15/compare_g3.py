"""ConfigSched against the deployed-cell campaign's four arms on G3 part A,
paired within seed, and EXPECTATIONS.md scored line by line.

Reads the banked per-run rows (never the summaries), pairs on (n_ues, seed),
and refuses any point whose cell is short. E3's `floors_unmet` half is not
scorable here: scripts/g3_stress.py does not bank scheduler counters, so it
is reported as UNSCORABLE, not as a pass.
Run: uv run python sweeps/config-sched-2026-09-15/compare_g3.py
"""
import json, statistics as st, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
CAMPAIGN = HERE.parent / "cell-2026-09-15" / "aligned" / "g3.runs.jsonl"
PROBE = HERE / "g3_probe.runs.jsonl"
ARMS = ("PF", "Reservation", "TwoTier", "ProtoRRageD2", "ConfigSched")


def rows_of(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def md(header, rows):
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    print()


probe = rows_of(PROBE)
camp = rows_of(CAMPAIGN)
probe = [r for r in probe if r["arm"] == "ConfigSched"]
H = 20_000  # the 10 s cells; the runner also banks one 200 000-slot cell per seed at N = 6
probe = [r for r in probe if r["horizon"] == H]
camp = [r for r in camp if r["horizon"] == H]
seeds = sorted({r["seed"] for r in probe})
ns = sorted({r["n_ues"] for r in probe})
cell = defaultdict(dict)  # (arm, n) -> seed -> row
for r in probe + [c for c in camp if c["seed"] in seeds and c["n_ues"] in ns]:
    if r["kind"] != "gt22" or r["cap"] != 4 or r["committed_mult"] != 1.0 or r["snr_db"] != 20.0 or r["cam_x"] != 1.0:
        continue  # part A of GT-2.2 at nominal load and the scenario SNR, nothing else
    cell[(r["arm"], r["n_ues"])][r["seed"]] = r
for a in ARMS:
    for n in ns:
        got = sorted(cell[(a, n)])
        assert got == seeds, f"{a} N={n}: seeds {got} vs probe {seeds} -- never score a short cell"
k = len(seeds)
print(f"paired seeds {seeds} ({k} per point), fleet axis {ns}\n")

for part, label in (("part1_pass", "part 1 (max gap <= 500 ms)"), ("part1s_pass", "part 1s (longest silence incl. head/tail)"),
                    ("part2_pass", "part 2 (no gap >= 2 s)"), ("part3_pass", "part 3 (p98 <= 95 ms)")):
    print(f"**{label}** -- passes of {k}\n")
    md(["arm"] + [f"N={n}" for n in ns], [[a] + [sum(1 for r in cell[(a, n)].values() if r[part]) for n in ns] for a in ARMS])
for stat, label, fmt in (("p98_worst_ms", "telemetry p98, median over seeds (ms)", "{:.1f}"),
                         ("silence_worst_ms", "worst silence, max over seeds (ms)", "{:.0f}"),
                         ("head_worst_ms", "head silence (first message), max over seeds (ms)", "{:.1f}"),
                         ("msgs_short", "telemetry messages missing, sum over seeds", "{}"),
                         ("prot_ul_mbps", "protected uplink delivered, median (Mbps)", "{:.1f}")):
    agg = max if stat in ("silence_worst_ms", "head_worst_ms") else (sum if stat == "msgs_short" else st.median)
    print(f"**{label}**\n")
    md(["arm"] + [f"N={n}" for n in ns], [[a] + [fmt.format(agg([r[stat] or 0 for r in cell[(a, n)].values()])) for n in ns] for a in ARMS])

print("## Expectations scored\n")
res = []
# E1
fails = [(n, k - sum(1 for r in cell[("ConfigSched", n)].values() if r["part1_pass"])) for n in ns if n <= 16]
fails = [(n, f) for n, f in fails if f]
res.append(("E1 telemetry part 1 passes every seed at N <= 16", "HIT" if not fails else f"MISS {fails}"))
# E2
ratios = []
for n in ns:
    for s in seeds:
        h_c, h_t = cell[("ConfigSched", n)][s]["head_worst_ms"], cell[("TwoTier", n)][s]["head_worst_ms"]
        if h_t:
            ratios.append(h_c / h_t)
med = st.median(ratios)
res.append((f"E2 head silence within 20 % of TwoTier (median ratio {med:.2f}, range {min(ratios):.2f}-{max(ratios):.2f})",
            "HIT" if 0.8 <= med <= 1.2 else "MISS"))
# E3
if 24 in ns:
    p = sum(1 for r in cell[("ConfigSched", 24)].values() if r["part1_pass"])
    res.append((f"E3a telemetry part 1 at N=24 ({p}/{k})", "HIT" if p == k else "MISS"))
res.append(("E3b floors_unmet > 0 at N=24", "UNSCORABLE (runner banks no scheduler counters)"))
# E4
better = []
for n in ns:
    if n < 12:
        continue
    c = sum(1 for r in cell[("ConfigSched", n)].values() if r["part3_pass"])
    others = max(sum(1 for r in cell[(a, n)].values() if r["part3_pass"]) for a in ARMS if a != "ConfigSched")
    if c > 0 and others == 0:
        better.append((n, c))
res.append(("E4 part 3 no better than the others at N >= 12", "HIT" if not better else f"MISS {better}"))
# E5
e5 = []
for n in ns:
    if n > 8:
        continue
    c = st.median(r["prot_ul_mbps"] for r in cell[("ConfigSched", n)].values())
    pf = st.median(r["prot_ul_mbps"] for r in cell[("PF", n)].values())
    tt = st.median(r["prot_ul_mbps"] for r in cell[("TwoTier", n)].values())
    e5.append((n, round(c, 2), round(pf, 2), round(tt, 2), c < pf, abs(c - tt) <= 0.1 * tt))
ok = all(x[4] and x[5] for x in e5)
res.append((f"E5 protected UL (proxy for camera) below PF and within 10 % of TwoTier at N <= 8: {e5}", "HIT" if ok else "MISS"))
md(["expectation", "verdict"], res)
