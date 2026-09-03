"""G11's first-pass answer: the number per arm, what is most likely wrong
with it, and whether the guarantee is scoreable as written.

`docs/wp9-g11-plan.md` §2 defines five clauses in two currencies. This
scores each SEPARATELY with its own instrument named -- the regime map's
§4.1 clause-by-clause default -- and never pools them into one verdict.

DECOMPOSE BEFORE ATTRIBUTING is applied at the point each aggregate is
COMPUTED, not when it is quoted (the fourth journal form rule, and the
defect `g12_score.py` committed while citing the rule in its docstring).
So: C1's per-window verdict always carries WHICH conjunct failed and WHICH
flow, never a bare boolean.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from g11_drift import drift_verdict

# Each conjunct with its own bound and its own direction. The bounds are the
# test plan's, not fresh choices: G1 100 ms PDB, G3 T_live/4 = 500 ms,
# G5 >=99% complete and p95 frame age <=67 ms, G8 per-second Jain >=0.9.
CONJUNCTS = [
    ("G1", "M01w", "p98", "<=", 100.0),
    ("G3", "M03w", "value", "<=", 500.0),
    ("G5", "M05w", "value", ">=", 0.99),
    ("G5", "M06w", "value", "<=", 67.0),
    ("G8", "M09w", "value", ">=", 0.90),
]


def _ok(v, op, bound):
    if v is None:
        return None                      # not scoreable in this window
    return (v <= bound) if op == "<=" else (v >= bound)


def score(path: Path) -> dict:
    data = json.loads(path.read_text())
    runs = data["runs"]
    # rows -> [arm][seed][window][metric] = row
    idx: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for r in runs:
        for row in r["rows"]:
            idx[row["arm"]][row["seed"]][row["window_index"]][row["metric"]] = row

    # ---- C1: every 60 s window passes G1/G3/G5/G8, per arm ----------------
    c1: dict = {}
    for arm, by_seed in idx.items():
        wins_total = fails = unscoreable = 0
        by_conjunct: dict[str, int] = defaultdict(int)
        offenders: dict[str, int] = defaultdict(int)
        per_seed_pass: dict[int, bool] = {}
        for seed, by_w in by_seed.items():
            seed_ok = True
            for w, mets in by_w.items():
                wins_total += 1
                verdicts = []
                for g, metric, field, op, bound in CONJUNCTS:
                    row = mets.get(metric)
                    v = row.get(field) if row else None
                    o = _ok(v, op, bound)
                    verdicts.append(o)
                    if o is False:
                        by_conjunct[f"{g}/{metric}"] += 1
                        if row and row.get("flow"):
                            offenders[row["flow"]] += 1
                if any(o is False for o in verdicts):
                    fails += 1
                    seed_ok = False
                elif all(o is None for o in verdicts):
                    unscoreable += 1
            per_seed_pass[seed] = seed_ok
        c1[arm] = {
            "windows": wins_total, "failing": fails,
            "unscoreable": unscoreable,
            "pass_rate": (wins_total - fails) / wins_total if wins_total else None,
            "failures_by_conjunct": dict(by_conjunct),
            "distinct_offending_flows": len(offenders),
            "top_offenders": dict(sorted(offenders.items(),
                                         key=lambda kv: -kv[1])[:4]),
            "seeds_all_windows_pass": sum(per_seed_pass.values()),
            "seeds": len(per_seed_pass),
        }

    # ---- C3/C5: CoV of worst-flow p98 across seeds, and the raw vector ----
    c3: dict = {}
    for arm, by_seed in idx.items():
        per_seed_p98 = []
        for seed, by_w in by_seed.items():
            vals = [m["M01w"]["p98"] for m in by_w.values()
                    if m.get("M01w") and m["M01w"].get("p98") is not None]
            if vals:
                per_seed_p98.append(max(vals))       # worst window in the run
        if len(per_seed_p98) >= 2:
            mean = statistics.mean(per_seed_p98)
            sd = statistics.stdev(per_seed_p98)
            c3[arm] = {"n_seeds": len(per_seed_p98),
                       "mean_ms": mean, "sd_ms": sd,
                       "cov": (sd / mean) if mean else None,
                       "vector_ms": sorted(round(v, 2) for v in per_seed_p98)}
        else:
            c3[arm] = {"n_seeds": len(per_seed_p98), "cov": None,
                       "reason": "fewer than 2 seeds scored"}

    # ---- C4: is the per-window verdict vector identical across seeds? -----
    c4: dict = {}
    for arm, by_seed in idx.items():
        vectors = {}
        for seed, by_w in by_seed.items():
            vec = []
            for w in sorted(by_w):
                mets = by_w[w]
                vs = [_ok(mets.get(m, {}).get(f), op, b)
                      for _, m, f, op, b in CONJUNCTS]
                vec.append(False if any(x is False for x in vs) else True)
            vectors[seed] = tuple(vec)
        distinct = len(set(vectors.values()))
        varying = [i for i in range(max((len(v) for v in vectors.values()),
                                        default=0))
                   if len({v[i] for v in vectors.values() if i < len(v)}) > 1]
        allsame = distinct <= 1
        c4[arm] = {
            "distinct_verdict_vectors": distinct,
            "windows_that_vary_across_seeds": len(varying),
            "consistent": allsame,
            # The J5 shape, declared: consistency is only informative if the
            # verdict COULD have differed.
            "scoreable": bool(varying) or not allsame,
            "note": ("NOT SCORED -- every window has the same verdict on every "
                     "seed, so consistency is satisfied by construction"
                     if allsame and not varying else "real cross-seed claim"),
        }

    # ---- C2: drift in internals -------------------------------------------
    c2 = drift_verdict({
        "crumb_rate": None, "floor_fire_rate": None, "skip_reasons": None,
    })
    c2["note"] = ("NOT SCORED. The runner does not collect per-window "
                  "internal counters -- commit 7 built the detector and "
                  "commit 8 did not wire the counters in. A gap in this "
                  "plan's own commit sequence, not a property of the run.")

    return {"C1_window_pass": c1, "C2_drift": c2, "C3_C5_reproducibility": c3,
            "C4_verdict_stability": c4,
            "n_runs": len(runs), "n_expected": data.get("n_expected"),
            "horizon_slots": data.get("horizon_slots"),
            "window_s": data.get("window_s"),
            "memory_guard_tripped": data.get("memory_guard_tripped")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", default=str(
        Path(__file__).resolve().parent.parent / "sweeps" / "wp9" / "g11_campaign.json"))
    a = ap.parse_args()
    out = score(Path(a.campaign))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
