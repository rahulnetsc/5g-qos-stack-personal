"""Stage-3 analysis (`docs/wp9-plan.md` §10).

Order is enforced by structure, not discipline:

  1. **Q2's x1.0 null control, as a STOP CONDITION.** `mfbr_multiple=1.0`
     computes `max_burst` to exactly the `obligation*2` floor, so it must be
     a no-op -- BIT-IDENTICAL to x0 on shared seeds. Byte-equal rows, not
     "within tolerance": the paired-seed determinism property (a run is a
     pure function of scenario+seed) makes exact equality the right test.
     If it fails, the max_burst model is wrong and every other Q2 cell is
     uninterpretable, so this exits non-zero rather than reporting.
  2. Contiguity, before any effect size (standing rule).
  3. Effect sizes, as descriptive statistics for §10's stated predictions --
     NOT the stage-1 gate, which is deliberately not applied here.

Usage:
    uv run python scripts/analyse_stage3.py sweeps/wp9/stage3
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from itertools import product
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import check_contiguity  # noqa: E402
import wp9_gate as G  # noqa: E402
from analyse_stage2 import DIRECTION  # noqa: E402  (derived from the panel)
from wp9_sweep import STAGE3_Q1, STAGE3_Q2  # noqa: E402

ARMS = ("PF", "Reservation", "TwoTier")


def load(path: Path, grid: dict) -> list[dict[str, Any]]:
    """Coerce each axis value back to its declared type at the CSV boundary
    (CLAUDE.md's serialization rule)."""
    def coerce(axis, sval):
        for lv in grid[axis]:
            if isinstance(lv, bool):
                if sval == str(lv):
                    return lv
            elif isinstance(lv, (int, float)):
                try:
                    if float(sval) == float(lv):
                        return lv
                except ValueError:
                    pass
            elif sval == str(lv):
                return lv
        return None

    rows = []
    for r in csv.DictReader(open(path)):
        d: dict[str, Any] = {"scheduler": r["scheduler"],
                             "seed": int(float(r["seed"]))}
        for axis in grid:
            v = r.get(axis, "")
            if v not in ("", "None"):
                c = coerce(axis, v)
                if c is not None:
                    d[axis] = c
        for k, v in r.items():
            if k in grid or k in ("scheduler", "seed") or k.endswith(".status"):
                continue
            d[k] = None if v in ("", "None") else v      # keep RAW strings
        rows.append(d)
    return rows


def null_control(rows: list[dict]) -> tuple[bool, list[str]]:
    """STOP CONDITION. x1.0 must be byte-identical to x0 on shared seeds.

    Compares the RAW CSV strings for every non-axis column, so this is exact
    equality of what the run emitted -- no float tolerance, no re-parsing.
    """
    other = [a for a in STAGE3_Q2 if a != "mfbr_multiple"]
    problems: list[str] = []
    compared = 0
    for combo in product(*[STAGE3_Q2[a] for a in other]):
        sel = {a: v for a, v in zip(other, combo)}
        def pick(mult):
            return {(r["scheduler"], r["seed"]): r for r in rows
                    if r.get("mfbr_multiple") == mult
                    and all(r.get(a) == v for a, v in sel.items())}
        a0, a1 = pick(0.0), pick(1.0)
        for key in sorted(set(a0) & set(a1)):
            ra, rb = a0[key], a1[key]
            cols = [c for c in ra
                    if c not in ("mfbr_multiple", "scheduler", "seed")]
            diff = [c for c in cols if ra.get(c) != rb.get(c)]
            compared += 1
            if diff:
                problems.append(
                    f"{sel} {key}: {len(diff)} cols differ, e.g. "
                    + ", ".join(f"{c}={ra.get(c)!r} vs {rb.get(c)!r}"
                                for c in diff[:3]))
    return (not problems), [f"compared {compared} paired rows"] + problems[:10]


def _numeric(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def cell_winner(rows, metric):
    means, losses = {}, {}
    for arm in ARMS:
        vals = [_numeric(r.get(metric)) for r in rows if r["scheduler"] == arm]
        vals = [v for v in vals if v is not None]
        ls = [_numeric(r.get(G.LOSS_COLUMN)) for r in rows if r["scheduler"] == arm]
        ls = [v for v in ls if v is not None]
        if vals:
            means[arm] = st.fmean(vals)
        if ls:
            losses[arm] = st.fmean(ls)
    if len(means) < 2:
        return None
    if losses and max(losses.values()) <= 1e-12:
        return None
    return max(means, key=lambda a: DIRECTION[metric] * means[a])


def q1_boundary(rows) -> None:
    """Where does PF/Reservation separation begin, as a function of min_rb?

    §10's prediction: pinned at N=8 for min_rb <= 6 (PDCCH-bound at 32/4),
    falling above ~7 (7 -> ~7.9, 10 -> ~5.5, 20 -> ~2.75).
    """
    print("CONTIGUITY FIRST (Q1) -- an isolated winner is not a boundary")
    for metric in ("M07.met", "M08.fraction"):
        winners = {}
        for combo in product(*STAGE3_Q1.values()):
            sel = dict(zip(STAGE3_Q1, combo))
            cell = [r for r in rows if all(r.get(a) == v for a, v in sel.items())]
            if not cell:
                continue
            w = cell_winner(cell, metric)
            if w is not None:
                winners[combo] = w
        iso = check_contiguity(winners, STAGE3_Q1)
        n_iso = sum(1 for v in iso.values() if v)
        print(f"  {metric:<14} scored={len(winners):4d} isolated={n_iso:3d} "
              f"({n_iso/max(1,len(winners)):5.1%})")

    print()
    print("Q1 BOUNDARY: lowest N with a qualifying PF-vs-Reservation split")
    print(f"{'min_rb':>7} {'load=1.0':>10} {'load=2.0':>10}   predicted")
    for mr in STAGE3_Q1["min_rb"]:
        pred = min(55.0 / mr, 8.0)
        cols = []
        for lm in STAGE3_Q1["load_mult"]:
            first = None
            for n in STAGE3_Q1["n_ues"]:
                cell = [r for r in rows if r.get("n_ues") == n
                        and r.get("min_rb") == mr and r.get("load_mult") == lm]
                if not cell:
                    continue
                num = [{**r, "M07.met": _numeric(r.get("M07.met")),
                        "M08.fraction": _numeric(r.get("M08.fraction")),
                        "M02": _numeric(r.get("M02"))} for r in cell]
                for m in ("M07.met", "M08.fraction"):
                    res = G.evaluate_cell(num, "n_ues", n, "PF", "Reservation", m)
                    if res and res.qualifies:
                        first = n
                        break
                if first:
                    break
            cols.append(str(first) if first else ">16")
        print(f"{mr:>7} {cols[0]:>10} {cols[1]:>10}   {pred:>6.1f}")


def q2_report(rows, tally_path: Path) -> None:
    print()
    print("Q2 -- mfbr effect on M07.met (mean contracts met), load=1.0")
    print(f"{'N':>4} {'shared':>7} " + "".join(f"{f'x{m}':>22}" for m in STAGE3_Q2["mfbr_multiple"]))
    for n in STAGE3_Q2["n_ues"]:
        for sl in STAGE3_Q2["shared_lcg"]:
            line = f"{n:>4} {str(sl):>7} "
            for mult in STAGE3_Q2["mfbr_multiple"]:
                cell = [r for r in rows if r.get("n_ues") == n
                        and r.get("shared_lcg") is sl
                        and r.get("mfbr_multiple") == mult
                        and r.get("load_mult") == 1.0]
                vals = {a: st.fmean([_numeric(r["M07.met"]) for r in cell
                                     if r["scheduler"] == a
                                     and _numeric(r.get("M07.met")) is not None] or [float("nan")])
                        for a in ARMS}
                line += f"  {vals['PF']:4.1f}/{vals['Reservation']:4.1f}/{vals['TwoTier']:4.1f}   "
            print(line)
    print("  (PF/Reservation/TwoTier)")

    if tally_path.exists():
        tallies = json.loads(tally_path.read_text())
        print()
        print("UL FLOOR -- the two halves, separated for the first time")
        by_mult: dict[Any, list[int]] = {}
        for t in tallies:
            k = t.get("mfbr_multiple")
            g, f = t.get("gate_passes", 0), t.get("fires", 0)
            by_mult.setdefault(k, [0, 0])
            by_mult[k][0] += g
            by_mult[k][1] += f
        for k in sorted(by_mult, key=lambda x: (x is None, x)):
            g, f = by_mult[k]
            print(f"  mfbr x{k}: gate_passes={g:>8}  fires={f:>6}")
        print("  gate_passes>0 with fires==0 CONFIRMS the two-reason dormancy;")
        print("  fires>0 refutes it and corrects README §7 -- see §10.")


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "sweeps/wp9/stage3")
    q2p = root / "q2" / "stage3_q2_rows.csv"
    if q2p.exists():
        q2 = load(q2p, STAGE3_Q2)
        print("=" * 70)
        print("STOP CONDITION FIRST: Q2 mfbr x1.0 null control (bit-identity)")
        print("=" * 70)
        ok, notes = null_control(q2)
        for n in notes:
            print("  " + n)
        if not ok:
            raise SystemExit(
                "NULL CONTROL FAILED -- x1.0 is not bit-identical to x0, so "
                "the max_burst model is wrong and Q2 is uninterpretable. "
                "Refusing to report effect sizes.")
        print("  PASS -- x1.0 is bit-identical to x0; Q2 is interpretable.")
        print()

    q1p = root / "q1" / "stage3_q1_rows.csv"
    if q1p.exists():
        q1_boundary(load(q1p, STAGE3_Q1))
    if q2p.exists():
        q2_report(q2, root / "q2" / "floor_tally.json")


if __name__ == "__main__":
    main()
