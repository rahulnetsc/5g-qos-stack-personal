"""G11's C3, C4 and C5 -- three DIFFERENT statistics on one artefact.

Pure scoring. No runs: everything reads
`sweeps/postscaling-2026-09-05/g11_c1_soak.json` (10 seeds, 7.2M slots,
30/30 runs, 30 windows each).

**THEY ARE SCORED SEPARATELY BECAUSE THEY ASK DIFFERENT QUESTIONS**, and
`prediction-journal.md`'s form rule 4 exists because "G11's clauses will
pass" is not a scoreable claim.

    C3  CoV(p98) <= 15 % per instrument flow, across fresh seeds
    C4  identical PASS/FAIL verdicts across repeats
    C5  bimodality that a CoV cannot see

**C5 IS NOT FOLDED INTO C3 AND CANNOT BE.** A coefficient of variation is
identical for a tight unimodal spread and for two tight clusters equidistant
from the mean -- C3's instrument is structurally blind to exactly the
structure C5 exists to find (`docs/wp9-g11-plan.md` §2.1).

**C4 CARRIES A CAVEAT THAT TRAVELS WITH ITS RESULT.** Every run in this
artefact reports 0 failing windows, so the verdict vector is constant BY
CONSTRUCTION and C4 cannot fail here. A verdict that could not have been
otherwise is not evidence. The caveat is emitted with the number, not left
in a planning document.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT = "sweeps/postscaling-2026-09-05/g11_c1_soak.json"
COV_BOUND = 0.15

C4_CAVEAT = (
    "SATISFIED BY CONSTRUCTION -- every run in this artefact reports 0 "
    "failing windows, so the verdict vector is constant and C4 could not "
    "have come out otherwise. A verdict that could not have been otherwise "
    "is not evidence; this is not an independent result."
)


def per_seed_p98(runs, arm) -> dict[int, float]:
    """The run-level instrument statistic: worst-window p98 of M01w.

    Worst-window, not mean-window: C1's own verdict is per window, so the
    quantity a repeat should reproduce is the run's worst window, not its
    average.
    """
    out = {}
    for r in runs:
        if r["arm"] != arm:
            continue
        p98s = [x["p98"] for x in r["rows"]
                if x["metric"] == "M01w" and x.get("p98") is not None]
        if p98s:
            out[r["seed"]] = max(p98s)
    return out


def c3(runs, arms) -> dict:
    out = {}
    for arm in arms:
        v = list(per_seed_p98(runs, arm).values())
        mean = statistics.fmean(v)
        sd = statistics.stdev(v) if len(v) > 1 else 0.0
        cov = sd / mean if mean else float("nan")
        out[arm] = {"n": len(v), "mean_ms": mean, "sd_ms": sd, "cov": cov,
                    "pass": cov <= COV_BOUND}
    return out


def c4(runs, arms) -> dict:
    out = {}
    for arm in arms:
        verdicts = {}
        for r in runs:
            if r["arm"] != arm:
                continue
            # a run PASSES C1 if no window failed; the campaign records
            # failing windows per run
            fails = r.get("n_failing")
            if fails is None:
                fails = sum(1 for x in r["rows"] if x.get("failing"))
            verdicts[r["seed"]] = (fails == 0)
        vals = set(verdicts.values())
        out[arm] = {"n": len(verdicts), "verdicts": sorted(set(verdicts.values())),
                    "identical": len(vals) == 1, "all_pass": vals == {True},
                    "pass": len(vals) == 1,
                    "caveat": C4_CAVEAT if vals == {True} else None}
    return out


def c5(runs, arms) -> dict:
    """Bimodality in the per-seed p98 VECTOR -- not a summary of it.

    The test is a 1-D two-means split: sort the vector, try every split
    point, take the one minimising within-cluster variance, and compare the
    gap between cluster means to the pooled within-cluster spread. A
    separation of >= 2 pooled SDs with >= 2 points a side is reported as
    bimodal. Deliberately simple and deliberately reported WITH the vector,
    so a reader can see the structure rather than trust the label.
    """
    out = {}
    for arm in arms:
        d = per_seed_p98(runs, arm)
        v = sorted(d.values())
        best = None
        for i in range(2, len(v) - 1):
            lo, hi = v[:i], v[i:]
            wv = ((len(lo) - 1) * (statistics.stdev(lo) ** 2 if len(lo) > 1 else 0)
                  + (len(hi) - 1) * (statistics.stdev(hi) ** 2 if len(hi) > 1 else 0))
            if best is None or wv < best[0]:
                best = (wv, i, lo, hi)
        if best is None:
            out[arm] = {"n": len(v), "bimodal": False, "reason": "n too small"}
            continue
        _wv, i, lo, hi = best
        pooled = ((statistics.pstdev(lo) ** 2 * len(lo)
                   + statistics.pstdev(hi) ** 2 * len(hi)) / len(v)) ** 0.5
        gap = statistics.fmean(hi) - statistics.fmean(lo)
        sep = gap / pooled if pooled > 0 else float("inf")

        # --- VALIDITY GUARD, not a threshold tweak -----------------------
        # p98 of a latency measured in slots is QUANTISED to the slot
        # duration, and these vectors hold 4-8 distinct levels across 10
        # seeds. When values repeat exactly, within-cluster variance
        # collapses toward zero and `gap / pooled_sd` reads as large for ANY
        # split -- so the statistic measures the quantisation, not the
        # distribution. The first version of this scorer had no such guard
        # and reported BIMODAL on all three arms INCLUDING PF, which is
        # exactly the falsifier registered in
        # docs/next-expectations-2026-09-05.md.
        #
        # The rule: a separation-in-SDs claim requires the pooled SD to
        # exceed the measurement quantum. Below that the answer is NOT
        # SCOREABLE -- which is a result, not a failure to compute one.
        levels = sorted({round(x, 6) for x in v})
        gaps = [round(b_ - a_, 6) for a_, b_ in zip(levels, levels[1:])]
        quantum = min([g for g in gaps if g > 1e-9], default=0.0)
        scoreable = pooled >= quantum > 0 and len(levels) >= 6
        out[arm] = {"n": len(v), "vector_ms": [round(x, 3) for x in v],
                    "n_distinct_levels": len(levels), "quantum_ms": quantum,
                    "split_at": i, "gap_ms": gap, "pooled_sd_ms": pooled,
                    "separation_sds": sep,
                    "scoreable": scoreable,
                    "bimodal": (scoreable and sep >= 2.0
                                and min(len(lo), len(hi)) >= 2),
                    "not_scoreable_reason": None if scoreable else (
                        f"the p98 vector holds only {len(levels)} distinct "
                        f"levels on a {quantum:.3f} ms quantum, and the "
                        f"pooled within-cluster SD ({pooled:.3f} ms) is "
                        f"below it -- a separation-in-SDs statistic measures "
                        f"the quantisation here, not the distribution"),
                    "seeds_low": sorted(k for k, x in d.items() if x in lo),
                    "seeds_high": sorted(k for k, x in d.items() if x in hi)}
    return out


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artefact", default=DEFAULT)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args(argv[1:])
    blob = json.loads((REPO / a.artefact).read_text())
    runs = blob["runs"]
    arms = sorted({r["arm"] for r in runs})
    print(f"G11 C3/C4/C5 -- {a.artefact}")
    print(f"  {blob['n_runs']}/{blob['n_expected']} runs, n_ues={blob['n_ues']}, "
          f"horizon={blob['horizon_slots']}, window={blob['window_s']}s, "
          f"{len(blob['seeds'])} seeds\n")

    r3, r4, r5 = c3(runs, arms), c4(runs, arms), c5(runs, arms)

    print(f"C3 -- CoV(worst-window p98) <= {COV_BOUND:.0%}, across fresh seeds")
    for arm in arms:
        d = r3[arm]
        print(f"   {arm:<12} n={d['n']:<3} mean={d['mean_ms']:7.3f} ms  "
              f"sd={d['sd_ms']:7.3f}  CoV={d['cov']:.4f}  "
              f"{'PASS' if d['pass'] else 'FAIL'}")

    print(f"\nC4 -- identical PASS/FAIL verdicts across repeats")
    for arm in arms:
        d = r4[arm]
        print(f"   {arm:<12} n={d['n']:<3} verdicts={d['verdicts']}  "
              f"{'PASS' if d['pass'] else 'FAIL'}")
        if d["caveat"]:
            print(f"      ** {d['caveat']}")

    print(f"\nC5 -- bimodality in the per-seed p98 VECTOR (C3 is blind to this)")
    for arm in arms:
        d = r5[arm]
        if "vector_ms" not in d:
            print(f"   {arm:<12} {d['reason']}")
            continue
        print(f"   {arm:<12} vector={d['vector_ms']}")
        print(f"   {'':<12} {d['n_distinct_levels']} distinct levels on a "
              f"{d['quantum_ms']:.3f} ms quantum; best split at {d['split_at']}, "
              f"gap={d['gap_ms']:.3f} ms, pooled sd={d['pooled_sd_ms']:.3f}, "
              f"separation={d['separation_sds']:.2f} sd")
        if not d["scoreable"]:
            print(f"   {'':<12} -> NOT SCOREABLE: {d['not_scoreable_reason']}")
        else:
            print(f"   {'':<12} -> {'BIMODAL' if d['bimodal'] else 'unimodal'}")
        if d["bimodal"]:
            print(f"   {'':<12} low seeds={d['seeds_low']}")
            print(f"   {'':<12} high seeds={d['seeds_high']}")

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(
            {"artefact": a.artefact, "C3": r3, "C4": r4, "C5": r5,
             "C4_caveat": C4_CAVEAT}, indent=1))
        print(f"\nwrote {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
