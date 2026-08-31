"""Step 3 -- G6's conjunction, evaluated over every statistic it binds.

G6 (`docs/IA_P5G_Factory_Guarantee_Test_Plan.md:100`) reads:

  "With saturating 5QI-9 load added (either direction), every G1/G3/G5
   statistic STAYS WITHIN ITS BOUND AND shifts by <= [provisional] +20%
   relative."

Two clauses, and ten statistics -- derived from the panel's own
`guarantees:` fields, never hand-listed. The test as originally implemented
used THREE statistics and checked only the second clause.

Both clauses are evaluated on the PROTECTED FLEET (M20's flow restriction),
because G6 asks whether background traffic impairs THE FLEET and the
unrestricted statistics are won by the background traffic itself.

Usage:
    uv run python scripts/g6_conjunction_table.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import bootstrap_ci  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.scorecard import Scorecard, load_panel  # noqa: E402

ARMS = ("PF", "Reservation", "TwoTier")
BAR = 0.20
RECORDS = "sweeps/wp9/stage6_g6_n40_records.jsonl"

# The scalar each metric contributes, and its bound where the test plan
# states one. A bound of None means the plan states no numeric bound for
# that statistic -- reported as "no stated bound", never invented.
SCALAR = {
    "M01": ("p98", 100.0),         # G1 (:95): cmd_vel p98 <= RAN PDB
    "M02": (None, None),           # a rate; the plan states no absolute bar
    "M03": ("max_gap_ms", 500.0),  # G3 (:97): max telemetry gap <= T_live/4
    "M04": ("worst_consecutive_miss_slots", None),
    "M05": ("fraction", 0.99),     # G5 (:99): >= 99% of PDU sets complete
    "M06": ("p95_ms", 67.0),       # G5 (:99): frame age p95 <= 2 frame periods
    "M15": (None, None),
    "M16": (None, None),           # study-layer: needs a named flow pair
    "M17": (None, None),
    "M19": (None, None),
}

# DIRECTION comes from the panel, never from a hand-written comparison.
# The first version of this script tested `value > bound` for every metric,
# which for the higher-better M05 counted PASSES as failures -- it reported
# "FAIL 37/40 over 0.99" for exactly the 37 seeds that met the >= 99 % bar.
_DIRECTION = {m["id"]: m.get("direction") for m in load_panel()["metrics"]}


def _breaches(value: float, bound: float, mid: str) -> bool:
    d = _DIRECTION.get(mid)
    if d == "lower_better":
        return value > bound
    if d == "higher_better":
        return value < bound
    raise ValueError(f"{mid} has direction {d!r}; a bounded metric needs one")


def g6_bound_statistics() -> list[str]:
    """DERIVED from the panel, never hand-listed -- CLAUDE.md's rule, whose
    fourth instance was a hand-listed set in a test."""
    panel = load_panel()
    return [m["id"] for m in panel["metrics"]
            if {"G1", "G3", "G5"} & set(m.get("guarantees") or [])]


def _scalar(res, key):
    v = res.value
    if v is None:
        return None
    if key is None:
        return float(v) if not isinstance(v, dict) else None
    return None if not isinstance(v, dict) else v.get(key)


def main() -> int:
    ids = g6_bound_statistics()
    print(f"G6 binds {len(ids)} statistics, derived from the panel: {ids}\n")

    base, exc = {}, {}
    with open(RECORDS) as fh:
        for line in fh:
            p = json.loads(line)
            rec = RunRecord.from_dict(p["record"])
            key = (rec.scheduler_name, rec.seed)
            (exc if p["axis_values"].get("bg") is True else base)[key] = rec
    shared = sorted(set(base) & set(exc))
    print(f"paired (arm, seed) pairs: {len(shared)}   "
          f"n_seeds={len(shared) // len(ARMS)} per arm\n")

    # BOTH CLAUSES ARE EVALUATED ON THE PROTECTED FLEET. G6 asks whether
    # background traffic impairs THE FLEET; the unrestricted statistics are
    # won (M03) or dominated (M02) by the background traffic's own service.
    sc = Scorecard()
    excl = Scorecard.NON_PROTECTED_5QI

    def protect(rec: RunRecord) -> RunRecord:
        import dataclasses
        keep = {k: fr for k, fr in rec.flows.items() if fr.qfi not in excl}
        return dataclasses.replace(rec, flows=keep)

    print(f"protected-fleet restriction: excluding 5QIs {sorted(excl)}\n")
    scored = {k: (sc.score(protect(base[k])), sc.score(protect(exc[k])))
              for k in shared}

    hdr = (f"{'metric':<6}{'arm':<13}{'clause 1: within bound':<34}"
           f"{'clause 2: shift <= +20%':<30}")
    print(hdr); print("-" * len(hdr))
    for mid in ids:
        key, bound = SCALAR.get(mid, (None, None))
        for arm in ARMS:
            pairs = [k for k in shared if k[0] == arm]
            b_vals, e_vals, rels = [], [], []
            for k in pairs:
                bs, es = scored[k]
                if mid not in bs or mid not in es:
                    continue
                bv, ev = _scalar(bs[mid], key), _scalar(es[mid], key)
                if bv is None or ev is None:
                    continue
                b_vals.append(bv); e_vals.append(ev)
                if bv:
                    rels.append((ev - bv) / abs(bv))
            if not e_vals:
                st = bs[mid].status if mid in bs else "absent"
                print(f"{mid:<6}{arm:<13}{'NOT EVALUABLE (' + st + ')':<34}"
                      f"{'NOT EVALUABLE':<30}")
                continue
            if bound is None:
                c1 = "no stated bound"
            else:
                over = sum(1 for v in e_vals if _breaches(v, bound, mid))
                word = "over" if _DIRECTION.get(mid) == "lower_better" else "under"
                c1 = (f"{'PASS' if over == 0 else 'FAIL'}  "
                      f"{over}/{len(e_vals)} {word} {bound:g}")
            if not rels:
                c2 = "undefined (zero base)"
            else:
                ci = bootstrap_ci(rels, seed=4242)
                summ = Scorecard.robust_delta_summary(rels)
                verdict = ("PASS" if ci["hi"] <= BAR
                           else "FAIL" if ci["lo"] > BAR else "INCONCLUSIVE")
                c2 = (f"{verdict:<13} med {summ['median']*100:+7.2f}% "
                      f"mean {ci['point']*100:+7.2f}%")
            print(f"{mid:<6}{arm:<13}{c1:<34}{c2:<30}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
