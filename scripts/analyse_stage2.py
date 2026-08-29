"""Stage-2 analysis (`docs/wp9-plan.md` §6.4 rule 5, §6.1's D4-1..D4-4).

**Contiguity is read BEFORE effect sizes, and that ordering is enforced by
this script's structure rather than left to discipline.** With 252 cells
there will be isolated winners by chance; rule 5 says a cell whose winner
has no grid-adjacent agreeing neighbour is flagged isolated and **is not a
boundary**. Reading effect sizes first would mean deciding what to believe
and then checking whether it was contiguous, which is the wrong order.

Usage:
    uv run python scripts/analyse_stage2.py sweeps/wp9/stage2
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import check_contiguity  # noqa: E402
import wp9_gate as G  # noqa: E402
from sim.scorecard import load_panel  # noqa: E402
from wp9_sweep import STAGE2_GRID  # noqa: E402

ARMS = ("PF", "Reservation", "TwoTier")

def _load_directions() -> dict[str, int]:
    """Sign per primary metric, READ FROM config/metric_panel.yml, not
    transcribed here.

    CLAUDE.md's count-from-structure rule applies to this exactly: a
    hand-copied sign on M01.p98 or M02 inverts a winner and nothing
    downstream catches it -- the contiguity map would be confidently
    backwards. `direction` is the panel's own pre-registered field, so it is
    the thing to derive from.
    """
    panel = load_panel()
    by_id = {m["id"]: m.get("direction") for m in panel["metrics"]}
    out: dict[str, int] = {}
    for col in G.PRIMARY_METRIC_COLUMNS:
        mid = col.split(".")[0]
        d = by_id.get(mid)
        if d == "higher_better":
            out[col] = +1
        elif d == "lower_better":
            out[col] = -1
        else:
            raise ValueError(
                f"{mid} has direction {d!r} in config/metric_panel.yml; a "
                f"primary gating metric must be directional")
    return out


DIRECTION = _load_directions()


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Read stage-2 rows, coercing each axis value back to its DECLARED type.

    CLAUDE.md's serialization rule, learned the hard way: booleans round-trip
    through CSV as the string 'True' and silently match nothing, which made a
    cell select zero rows and score exactly 0.000. Coerce at the boundary,
    then assert the selection sizes (see `check_cell_sizes`).
    """
    def coerce(axis: str, sval: str):
        for lv in STAGE2_GRID[axis]:
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
        for axis in STAGE2_GRID:
            v = r.get(axis, "")
            if v not in ("", "None"):
                c = coerce(axis, v)
                if c is not None:
                    d[axis] = c
        for k, v in r.items():
            if k in STAGE2_GRID or k in ("scheduler", "seed") or k.endswith(".status"):
                continue
            if v in ("", "None"):
                d[k] = None
                continue
            try:
                d[k] = float(v)
            except ValueError:
                d[k] = v
        rows.append(d)
    return rows


def check_cell_sizes(rows, n_seeds=10) -> tuple[int, int]:
    """Assert every grid cell is present and full BEFORE anything is scored."""
    from itertools import product
    names = list(STAGE2_GRID)
    expected = len(ARMS) * n_seeds
    missing = bad = 0
    for combo in product(*STAGE2_GRID.values()):
        cell = [r for r in rows
                if all(r.get(a) == v for a, v in zip(names, combo))]
        if not cell:
            missing += 1
        elif len(cell) != expected:
            bad += 1
    return missing, bad


def cell_winner(rows, metric: str) -> str | None:
    """Best arm at this cell on `metric`, by mean over seeds, respecting the
    panel's own direction. None if the cell is uninformative (rule 2(i)) --
    an uninformative cell has no winner and cannot support a neighbour."""
    means = {}
    losses = {}
    for arm in ARMS:
        vals = [r[metric] for r in rows
                if r["scheduler"] == arm and isinstance(r.get(metric), float)]
        ls = [r[G.LOSS_COLUMN] for r in rows
              if r["scheduler"] == arm and isinstance(r.get(G.LOSS_COLUMN), float)]
        if vals:
            means[arm] = statistics.fmean(vals)
        if ls:
            losses[arm] = statistics.fmean(ls)
    if len(means) < 2:
        return None
    # is_informative: excluded if every arm is at zero loss.
    if losses and max(losses.values()) <= 1e-12:
        return None
    return max(means, key=lambda a: DIRECTION[metric] * means[a])


def contiguity_report(rows, metric: str) -> dict:
    from itertools import product
    names = list(STAGE2_GRID)
    winners: dict[tuple, str] = {}
    for combo in product(*STAGE2_GRID.values()):
        cell = [r for r in rows
                if all(r.get(a) == v for a, v in zip(names, combo))]
        if not cell:
            continue
        w = cell_winner(cell, metric)
        if w is not None:
            winners[combo] = w
    isolated = check_contiguity(winners, STAGE2_GRID)
    n_iso = sum(1 for v in isolated.values() if v)
    by_arm: dict[str, int] = {}
    for cell, w in winners.items():
        by_arm[w] = by_arm.get(w, 0) + 1
    return {"metric": metric, "n_scored": len(winners), "n_isolated": n_iso,
            "winners_by_arm": by_arm, "isolated": isolated, "winners": winners}


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sweeps/wp9/stage2")
    rows = load_rows(out / "stage2_rows.csv")
    print(f"loaded {len(rows)} rows from {out}")

    missing, bad = check_cell_sizes(rows)
    print(f"cell integrity: {missing} missing, {bad} wrong-sized "
          f"(both must be 0 before anything is scored)")
    if missing or bad:
        raise SystemExit("grid incomplete -- refusing to score")

    print()
    print("=" * 70)
    print("CONTIGUITY FIRST (rule 5) -- an isolated winner is not a boundary")
    print("=" * 70)
    reports = {}
    for metric in G.PRIMARY_METRIC_COLUMNS:
        rep = contiguity_report(rows, metric)
        reports[metric] = rep
        frac = rep["n_isolated"] / max(1, rep["n_scored"])
        print(f"  {metric:<14} scored={rep['n_scored']:4d}  "
              f"isolated={rep['n_isolated']:4d} ({frac:5.1%})  "
              f"winners={rep['winners_by_arm']}")

    (out / "contiguity.json").write_text(json.dumps(
        {m: {k: v for k, v in r.items()
             if k not in ("isolated", "winners")}
         for m, r in reports.items()}, indent=2))
    print(f"\nwrote {out/'contiguity.json'}")


if __name__ == "__main__":
    main()
