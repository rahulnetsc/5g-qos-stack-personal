"""Regenerate stage 1's gate verdict from the committed CSV.

WHY THIS EXISTS. `wp9_gate.select_for_stage_2` silently omitted one axis
from its `dropped` list -- an off-by-one slice, fixed 2026-09-04 -- and both
committed verdicts (`gate_verdict.txt`, `gate_verdict_corrected.txt`) are
missing `min_rb` as a result. The verdict could previously only be produced
as a side effect of `wp9_sweep.py --stage 1`, a ~7 h re-run of 1,770 cells,
so a corrected record was not obtainable at any reasonable cost.

Everything the gate reads is in `stage1_rows.csv`, which IS committed. So
the verdict is regenerable from disk, and this is the script that does it.

TWO THINGS IT DOES NOT DO, deliberately:

  * It does not re-run anything. The rows are stage 1's own output, so the
    regenerated verdict is a re-report of the same decision, not a second
    measurement of it.
  * It does not overwrite the committed verdicts. It writes a new file and
    prints a diff of the axis accounting, because a corrected artefact that
    replaces the flawed one in place destroys the evidence that the flaw
    existed -- which is the same reason `gate_verdict_corrected.txt` sits
    beside `gate_verdict.txt` rather than replacing it.

Usage:
    uv run python scripts/regen_gate_verdict.py
    uv run python scripts/regen_gate_verdict.py --compare sweeps/wp9/stage1/gate_verdict_corrected.txt
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wp9_gate                                        # noqa: E402
from wp9_sweep import CORE_PLANE, EXCURSIONS           # noqa: E402

ROWS = Path("sweeps/wp9/stage1/stage1_rows.csv")
OUT = Path("sweeps/wp9/stage1/gate_verdict_regenerated.txt")


def _coerce(axis: str, raw: str) -> Any:
    """Boundary coercion against the axis's DECLARED levels.

    Defect #1's rule: a value crossing a serialization boundary is coerced
    back to its declared type there, against the levels the grid declares,
    never by guessing from the string. `shared_lcg`'s 'True' is the case
    that cost a whole analysis.
    """
    levels = list(EXCURSIONS.get(axis, [])) + list(CORE_PLANE.get(axis, []))
    for lv in levels:
        if str(lv) == raw:
            return lv
    # A level the grid does not declare is not silently kept as a string.
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    axes = set(EXCURSIONS) | set(CORE_PLANE)
    out: list[dict[str, Any]] = []
    with path.open() as fh:
        for raw in csv.DictReader(fh):
            row: dict[str, Any] = {"scheduler": raw["scheduler"],
                                   "seed": int(float(raw["seed"]))}
            for axis in axes:
                sval = raw.get(axis, "")
                if sval in ("", "None"):
                    continue          # ABSENT, not present-as-None: carries_axis
                c = _coerce(axis, sval)
                if c is not None:
                    row[axis] = c
            for col in wp9_gate.PRIMARY_METRIC_COLUMNS + (wp9_gate.LOSS_COLUMN,):
                v = raw.get(col, "")
                row[col] = None if v in ("", "None") else float(v)
            out.append(row)
    return out


def _axes_in(text: str) -> tuple[set[str], set[str], set[str]]:
    listed = set(re.findall(r"^(?:QUALIFIES|  --     )\s+(\S+)", text, re.M))
    m = re.search(r"promoted to stage 2: \[(.*)\]", text)
    promoted = set(m.group(1).replace("'", "").split(", ")) if m else set()
    dropped = set(re.findall(r"^dropped: (\S+)", text, re.M))
    return listed, promoted, dropped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default=str(ROWS))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--compare", action="append", default=[],
                    help="an existing verdict to check the accounting of")
    a = ap.parse_args(argv[1:])

    rows_path = Path(a.rows)
    if not rows_path.exists():
        raise SystemExit(
            f"{rows_path} is absent. It IS committed -- regenerate it with "
            f"`uv run python scripts/wp9_sweep.py --stage 1` only as a last "
            f"resort (~7 h).")
    rows = load_rows(rows_path)
    print(f"{rows_path}: {len(rows)} rows")

    arm_pairs = [("PF", "Reservation"), ("PF", "TwoTier"),
                 ("Reservation", "TwoTier")]
    verdicts = []
    for axis, levels in {**CORE_PLANE, **EXCURSIONS}.items():
        verdicts.append(wp9_gate.evaluate_axis(rows, axis, list(levels),
                                               arm_pairs))
    # PER-AXIS ROW COUNTS, printed. An axis whose cells never ran scores 0.0
    # and reads identically to one that ran and lost -- the empty-selection
    # shape, which this gate's own docstring addresses only in the opposite
    # direction (cells selecting too MANY rows).
    print("\nrows entering each axis (an axis with 0 did not run, and a "
          "score of 0.000 on it means nothing):")
    for v in verdicts:
        n = sum(1 for r in rows if wp9_gate.carries_axis(r, v.axis))
        print(f"  {v.axis:<18} rows={n:>5}  results={len(v.all_results):>4}  "
              f"score={v.score:8.3f}")

    selection = wp9_gate.select_for_stage_2(verdicts)
    report = wp9_gate.format_verdicts(verdicts, selection)
    Path(a.out).write_text(report + "\n")
    print("\n" + report)
    print(f"\nwrote {a.out}")

    listed = {v.axis for v in verdicts}
    accounted = set(selection["promoted"]) | {d["axis"] for d in selection["dropped"]}
    print(f"\nACCOUNTING: {len(listed)} axes, "
          f"{len(selection['promoted'])} promoted, "
          f"{len(selection['dropped'])} dropped, "
          f"unaccounted {sorted(listed - accounted) or 'none'}")

    for path in a.compare:
        p = Path(path)
        if not p.exists():
            print(f"\n{p}: absent")
            continue
        li, pr, dr = _axes_in(p.read_text())
        missing = sorted(li - pr - dr)
        print(f"\n{p}: {len(li)} axes listed, {len(pr)} promoted, "
              f"{len(dr)} dropped -> UNACCOUNTED {missing or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
