"""Admissible fleet size, per arm — G10's pre-registered per-seed all-pass read.

WHY THIS IS A SCRIPT AND NOT A SENTENCE. CLAUDE.md: "any count that
describes a structure must be computed from that structure at the point of
use, never restated in prose". The number this emits had never been
computed -- `docs/wp9-regime-map.md`'s G10 row carried "admissible N
bounded by 8 at load >= 1.0 and by 16 below it", which is stage 2's
ARM-SEPARATION boundary (§8d D4-3) wearing the admissible-N label. They are
different quantities and they disagree per arm.

THE CRITERION, stated because G1-G8 maps onto several metrics.
`docs/wp9-plan.md` §5(a) registers G10's sim read as "M07, M08 all-pass at
5/5 seeds -> admissible N"; the test plan's own G10 row is "largest asset
count with G1-G8 all-pass in 5/5 runs". Per `config/metric_panel.yml`, M07
counts GBR flows delivering >= gbr_contract_fraction of GFBR and M08 is the
min of that fraction over GBR flows. So:

    per-seed pass  :=  M07.met == M07.total  AND  M08.fraction >= 0.95
    admissible N   :=  largest N passing on EVERY seed, contiguous from the
                       smallest N tested

Two guards, both from this project's own scars:
  * `shared_lcg` is coerced from the CSV's 'True'/'False' back to bool at
    the parse boundary -- WP9 stage 1 lost a whole analysis to exactly that
    string/bool mismatch selecting zero rows.
  * every cell selection asserts its expected size before anything is
    scored, so an empty or short selection cannot be silently summed.

    uv run python scripts/g10_admissible.py
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

ROWS = Path(__file__).resolve().parent.parent / "sweeps" / "wp9" / "stage2" / "stage2_rows.csv"

# The base slice, so the answer is one grid and not a mixture
# (scripts/wp9_sweep.py::BASE).
BASE_SLICE = {"k2_slots": 2, "shared_lcg": False}
LOAD = 1.0
CONTRACT = 0.95


def _bool(s: str) -> bool:
    if s in ("True", "true", "1"):
        return True
    if s in ("False", "false", "0"):
        return False
    raise ValueError(f"not a boolean literal: {s!r}")


def load_rows(path: Path = ROWS) -> list[dict]:
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["n_ues"] = int(r["n_ues"])
        r["seed"] = int(r["seed"])
        r["load_mult"] = float(r["load_mult"])
        r["k2_slots"] = int(r["k2_slots"])
        r["shared_lcg"] = _bool(r["shared_lcg"])          # the coercion guard
    return rows


def _f(r: dict, k: str) -> float | None:
    v = r.get(k, "")
    return float(v) if v not in ("", None) else None


def seed_passes(r: dict) -> bool:
    met, total, frac = _f(r, "M07.met"), _f(r, "M07.total"), _f(r, "M08.fraction")
    if met is None or total is None or frac is None:
        return False
    return met == total and frac >= CONTRACT


def admissible(rows: list[dict], load: float = LOAD) -> tuple[dict, dict]:
    sel = [r for r in rows
           if r["load_mult"] == load
           and all(r[k] == v for k, v in BASE_SLICE.items())]
    by = defaultdict(list)
    for r in sel:
        by[(r["scheduler"], r["n_ues"])].append(r)

    arms = sorted({a for a, _ in by})
    sizes = sorted({n for _, n in by})
    n_seeds = max(len(v) for v in by.values())

    table: dict = {}
    for arm in arms:
        for n in sizes:
            cell = by[(arm, n)]
            # the cell-size guard: never score a short or empty selection
            assert len(cell) == n_seeds, (
                f"cell ({arm}, n_ues={n}) has {len(cell)} rows, expected {n_seeds}")
            table[(arm, n)] = sum(1 for r in cell if seed_passes(r))

    adm = {}
    for arm in arms:
        best = None
        for n in sizes:                      # contiguous from the smallest N
            if table[(arm, n)] == n_seeds:
                best = n
            else:
                break
        adm[arm] = best
    return table, {"arms": arms, "sizes": sizes, "n_seeds": n_seeds,
                   "admissible": adm, "n_rows_scored": len(sel)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", type=float, default=LOAD)
    a = ap.parse_args()

    rows = load_rows()
    table, meta = admissible(rows, a.load)
    arms, sizes, n_seeds = meta["arms"], meta["sizes"], meta["n_seeds"]

    print(f"stage2_rows.csv: {len(rows)} rows; scored slice "
          f"load_mult={a.load}, {BASE_SLICE} -> {meta['n_rows_scored']} rows, "
          f"{n_seeds} seeds/cell")
    print(f"criterion: M07.met == M07.total AND M08.fraction >= {CONTRACT}\n")
    hdr = "arm".ljust(12) + "".join(f"{('N=%d' % n):>10}" for n in sizes) + "   admissible"
    print(hdr); print("-" * len(hdr))
    for arm in arms:
        cells = "".join(f"{('%d/%d' % (table[(arm,n)], n_seeds)):>10}" for n in sizes)
        adm = meta["admissible"][arm]
        print(f"{arm:<12}{cells}   {adm if adm is not None else 'none'}")

    print("\nadmissible N (largest fleet passing on EVERY seed):")
    for arm in arms:
        print(f"  {arm:<12} {meta['admissible'][arm]}")

    # The pair, always together: §0.1's standing rule is that a single-metric
    # claim about who wins at high N is false by construction, so M07 and M08
    # are printed side by side and never one alone.
    print("\nmean M07 contracts met  /  mean M08 worst-flow floor "
          "(§0.1: quote BOTH, always)")
    sel = [r for r in rows if r["load_mult"] == a.load
           and all(r[k] == v for k, v in BASE_SLICE.items())]
    by = defaultdict(list)
    for r in sel:
        by[(r["scheduler"], r["n_ues"])].append(r)
    hdr2 = "arm".ljust(12) + "".join(f"{('N=%d' % n):>18}" for n in sizes)
    print(hdr2); print("-" * len(hdr2))
    means = {}
    for arm in arms:
        cells = ""
        for n in sizes:
            c = by[(arm, n)]
            m07 = sum(_f(r, "M07.met") or 0.0 for r in c) / len(c)
            m08 = sum(_f(r, "M08.fraction") or 0.0 for r in c) / len(c)
            means[(arm, n)] = (m07, m08)
            cells += f"{('%.1f / %.3f' % (m07, m08)):>18}"
        print(f"{arm:<12}{cells}")

    print("\nrank per metric (1 = best); ties shown as '=' ")
    for n in sizes:
        def rank(idx):
            vals = sorted({round(means[(a2, n)][idx], 6) for a2 in arms}, reverse=True)
            return {a2: vals.index(round(means[(a2, n)][idx], 6)) + 1 for a2 in arms}
        r7, r8 = rank(0), rank(1)
        parts = []
        for a2 in arms:
            tie7 = sum(1 for b in arms if r7[b] == r7[a2]) > 1
            tie8 = sum(1 for b in arms if r8[b] == r8[a2]) > 1
            parts.append(f"{a2}: M07 {r7[a2]}{'=' if tie7 else ' '} M08 {r8[a2]}{'=' if tie8 else ' '}")
        print(f"  N={n:<3} " + " | ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
