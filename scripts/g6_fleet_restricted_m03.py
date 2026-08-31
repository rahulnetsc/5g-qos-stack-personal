"""§24.7's decisive falsifier: does FLEET-RESTRICTED M03 still exceed +20 %?

Read-only. Recomputes M03's own worst-gap contest (sim/scorecard.py:220-235)
over four flow subsets, paired within seed against the base cell, from
records stage 1 already wrote. Changes no metric and no semantics -- it
evaluates what a restricted statistic WOULD have said.

Four subsets, because they answer different questions:
  ALL flows            -- M03 exactly as implemented today.
  aggressor excluded   -- drops qfi 8 only (sim/parametric.py:64), the flow
                          that exists solely when bg=True.
  no best-effort       -- also drops qfi 9 (sim/parametric.py:63), the per-UE
                          best-effort filler.
  TELEMETRY only       -- qfi 1 alone (sim/parametric.py:49), which is what
                          M03's own definition says it measures
                          (config/metric_panel.yml:96-99, "telemetry
                          inter-arrival gaps").

Counts carry their noun: n_seeds is paired seeds, n_ues is fleet size. The
cell is n_ues=8 at offered load x1.0.

Usage:
    uv run python scripts/g6_fleet_restricted_m03.py
"""
from __future__ import annotations
import json, statistics, sys, collections
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
from regime_sweep import bootstrap_ci

AGGRESSOR_QFI = 8      # sim/parametric.py:64  _QFI_AGGRESSOR
BE_FILLER_QFI = 9      # sim/parametric.py:63  _QFI_BG
TELEMETRY_QFI = 1      # sim/parametric.py:49  _QFI_TELEMETRY
ARMS = ("PF", "Reservation", "TwoTier")
EXC_AXES = ("bg","duty_cycle","snr_spread_db","min_rb","pdb_ms",
            "sr_period_slots","k2_slots","shared_lcg","mfbr_multiple","inf_scenario")

def max_gap_ms(rec_flows, keep):
    """M03's own contest (sim/scorecard.py:220-235) over a flow subset."""
    worst, who = -1.0, None
    for key, fr in rec_flows.items():
        if not keep(fr):
            continue
        for role, ts in (fr.get("completion_ts_by_role_s") or {}).items():
            if ts is None or len(ts) < 2:
                continue
            g = max(b - a for a, b in zip(ts, ts[1:])) * 1000.0
            if g > worst:
                worst, who = g, f"{key}:{role}"
    return (None, None) if who is None else (worst, who)

def load(path):
    base, exc = {}, {}
    with open(path) as fh:
        for line in fh:
            p = json.loads(line); av = p["axis_values"]; rec = p["record"]
            is_bg = av.get("bg") is True
            if set(av) == {"bg"}:
                # the n_seeds=40 extension: its only axis IS bg, so the
                # base cell is bg=False rather than a core-plane row.
                is_base = av.get("bg") is False
            else:
                is_base = (av.get("n_ues") == 8 and av.get("load_mult") == 1.0
                           and not any(a in av and av[a] is not None for a in EXC_AXES))
            if not (is_bg or is_base):
                continue
            key = (rec["scheduler_name"], rec["seed"])
            (exc if is_bg else base)[key] = rec["flows"]
    return base, exc

VARIANTS = {
    "ALL flows (M03 as implemented)":  lambda fr: True,
    "fleet = aggressor excluded":      lambda fr: fr["qfi"] != AGGRESSOR_QFI,
    "fleet, no best-effort":           lambda fr: fr["qfi"] not in (AGGRESSOR_QFI, BE_FILLER_QFI),
    "TELEMETRY only (M03's own text)": lambda fr: fr["qfi"] == TELEMETRY_QFI,
}

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--records", default="sweeps/wp9/stage1/records.jsonl")
_args = _ap.parse_args()
base, exc = load(REPO / _args.records)
print(f"records: {_args.records}")
print(f"base-cell runs: {len(base)}   bg-cell runs: {len(exc)}")
shared = sorted(set(base) & set(exc), key=lambda k: (k[0], k[1]))
print(f"paired (arm, seed) pairs available: {len(shared)}\n")

for label, keep in VARIANTS.items():
    print("=" * 78); print(label); print("=" * 78)
    for arm in ARMS:
        pairs = [k for k in shared if k[0] == arm]
        rels, flips = [], 0
        for k in pairs:
            b, bw = max_gap_ms(base[k], keep)
            e, ew = max_gap_ms(exc[k], keep)
            if b is None or e is None or b == 0:
                continue
            rels.append((e - b) / b)
            if bw.split(":")[0] != ew.split(":")[0]:
                flips += 1
        if not rels:
            print(f"  {arm}: no pairs"); continue
        ci = bootstrap_ci(rels, seed=4242)
        q = statistics.quantiles(rels, n=4) if len(rels) >= 4 else [float('nan')]*3
        verdict = "PASS" if ci["hi"] <= 0.20 else ("FAIL" if ci["lo"] > 0.20 else "INCONCLUSIVE")
        print(f"  {arm:<12} n_seeds={len(rels):2d}  MEAN {ci['point']*100:+8.2f}% "
              f"[{ci['lo']*100:+8.2f},{ci['hi']*100:+8.2f}]  {verdict:<12} | "
              f"MEDIAN {statistics.median(rels)*100:+7.2f}%  IQR "
              f"[{q[0]*100:+7.2f},{q[2]*100:+7.2f}]  worse {sum(1 for r in rels if r>0)}/{len(rels)}"
              f"  winner-flow changed identity on {flips}/{len(rels)}")
    print()
