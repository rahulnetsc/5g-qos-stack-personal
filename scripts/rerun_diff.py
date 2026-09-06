"""Consolidated diff: the re-run against the published artefacts.

Pairs rows on their own identity keys and compares every numeric field.
REPRODUCED means byte-equal to 1e-9 on every paired field; anything else is
MOVED and is a finding, since no code these campaigns import has changed.

Reports the pairing itself, not only the deltas: an artefact whose rows do not
pair is not "reproduced", it is unread, and the two look identical in a diff
that only prints differences.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

#: Artefacts that are NOT row-shaped, compared by a deep diff -- but PAIRED
#: ON IDENTITY first. `run_cells` yields in COMPLETION order, so a positional
#: deep diff of a parallel campaign reports every run against a different
#: run's numbers: G11 C1 read as 14,477 differences and was byte-identical.
DEEP = [
    ("G11 C1 soak", "sweeps/postscaling-2026-09-05/g11_c1_soak.json",
     "sweeps/rerun-2026-09-06/g11_c1_soak.json", "runs", ("arm", "seed")),
]

PAIRS = [
    ("G1 G3 G5 G8 (parametric)", "sweeps/phase2/core_scaled.json",
     "sweeps/rerun-2026-09-06/core.json", ("arm", "seed")),
    ("G1 G3 G8 (sensor_dense)", "sweeps/postscaling-2026-09-05/sensor_dense.json",
     "sweeps/rerun-2026-09-06/sensor_dense.json", ("arm", "seed")),
    ("G5 G10 consolidation", "sweeps/phase2/g5_consol_scaled.json",
     "sweeps/rerun-2026-09-06/g5_consol.json", ("arm", "seed", "n_ues")),
    # The published G10 came from `g5_consolidation.py --attach-seed`, NOT
    # from `g10_rerun.py` -- same field names, different grid and a different
    # mechanism. Pairing the wrong producer reads as "no paired rows".
    ("G10 (attach path)", "sweeps/postscaling-2026-09-05/g10_seeded.json",
     "sweeps/rerun-2026-09-06/g10_attach.json", ("arm", "seed", "n_ues")),
    ("G4", "sweeps/postscaling-2026-09-05/g4.json",
     "sweeps/rerun-2026-09-06/g4.json",
     ("duty_cycle", "scheduler", "seed", "ue_id", "qfi", "gap_bucket")),
    ("G7 (load 1.0)", "sweeps/postscaling-2026-09-05/g7.json",
     "sweeps/rerun-2026-09-06/g7.json", ("arm", "seed")),
    ("G7 (load 1.5)", "sweeps/postscaling-2026-09-05/g7_load1.5.json",
     "sweeps/rerun-2026-09-06/g7_load1.5.json", ("arm", "seed")),
    ("G2 UL STOP", "sweeps/postscaling-2026-09-05/g2_ul_stop.json",
     "sweeps/rerun-2026-09-06/g2_ul_stop.json", ("arm", "seed")),
]
TOL = 1e-9


def rows_of(p):
    """Sniffs the CONTENT, never the extension: `g10_rerun.py` writes CSV to a
    path ending `.json`, and trusting the suffix reads it as absent -- which a
    diff that only prints differences would show as silence."""
    txt = Path(p).read_text()
    head = txt.lstrip()[:1]
    if head in "{[":
        b = json.loads(txt)
        r = b.get("rows") if isinstance(b, dict) else b
        return r if isinstance(r, list) else None
    import csv, io
    rows = list(csv.DictReader(io.StringIO(txt)))
    for r in rows:                       # CSV has no types: coerce at the
        for k, v in list(r.items()):     # boundary, against the declared ones
            if v in ("True", "False"):
                r[k] = (v == "True")
                continue
            try:
                r[k] = int(v)
            except (TypeError, ValueError):
                try:
                    r[k] = float(v)
                except (TypeError, ValueError):
                    pass
    return rows or None


def key_of(r, ks):
    return tuple(r.get(k) for k in ks)


def main() -> int:
    worst = 0
    for name, oldp, newp, ks in PAIRS:
        if not Path(newp).exists():
            print(f"{name:26s} PENDING (no artefact yet)"); continue
        o, n = rows_of(oldp), rows_of(newp)
        if o is None or n is None:
            print(f"{name:26s} NOT ROW-SHAPED -- compared separately"); continue
        A = {key_of(r, ks): r for r in o}
        B = {key_of(r, ks): r for r in n}
        common = sorted(set(A) & set(B), key=repr)
        if not common:
            print(f"{name:26s} NO PAIRED ROWS ({len(A)} old, {len(B)} new) "
                  f"-- UNREAD, not reproduced"); worst = max(worst, 2); continue
        moved, checked = [], 0
        for f in A[common[0]]:
            if f in ks or f in ("wall_s",):
                continue
            vals = [(A[c].get(f), B[c].get(f)) for c in common]
            num = [(x, y) for x, y in vals
                   if isinstance(x, (int, float)) and not isinstance(x, bool)
                   and isinstance(y, (int, float)) and not isinstance(y, bool)]
            if not num:
                continue
            checked += 1
            d = max(abs(x - y) for x, y in num)
            if d > TOL:
                moved.append((f, d))
        tag = "REPRODUCED" if not moved else "MOVED"
        if moved:
            worst = max(worst, 1)
        print(f"{name:26s} {tag:11s} {len(common):5d} paired rows, "
              f"{checked:3d} numeric fields"
              + (f", unpaired old/new {len(A)-len(common)}/{len(B)-len(common)}"
                 if len(A) != len(common) or len(B) != len(common) else ""))
        for f, d in moved[:6]:
            print(f"      MOVED {f}: max |delta| {d:.6g}")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
