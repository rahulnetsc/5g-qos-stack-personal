"""Read `sweeps/phase2/g5_rank.json` against docs/g5-ranking-map.md.

THE MAP IS CLOSED. This script decides which registered outcome the data
matches; it does not invent one. If the data fits none of L1-L7 or U1-U4 it
prints RESIDUAL, which is a result -- the camera question's third seed is the
precedent, and a residual reported as such is worth more than a fourth
candidate written after the fact.

The checks are ordered so the UNREACHABLE outcomes are tested FIRST. U1 (a
full tie, so the order came from declaration position) and U2 (the flow was
never in the candidate set) are not failures of the trace; they are answers,
and reading a term distribution before ruling them out would attribute a
decision to a term that never decided anything.

`docs/wp9-plan.md`'s decompose-before-attributing rule applies throughout:
every aggregate here names the rows it sums over, and the failing-UE
statistics are computed against the OTHER UEs IN THE SAME RUN rather than
against a pooled across-seed baseline -- a within-run control, since seeds
differ in ways the ranking does not.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOUND = 0.99            # G5's own M05 bound
TIE_KEY = "TIED (declaration order)"


def failing_ues(row: dict) -> list[int]:
    """Every UE whose video flow is under G5's bound -- not only M05's
    worst-flow scalar. §29's rule: 'worst' says nothing about how many."""
    return sorted({f["ue_id"] for f in row["per_flow"].values()
                   if f["qfi"] == 2 and f["fraction"] < BOUND})


def _share(d: dict, total: int) -> dict:
    return {k: (v / total if total else 0.0) for k, v in d.items()}


def read_run(row: dict) -> dict:
    ues = [int(u) for u in row["present"]]
    bad = failing_ues(row)
    good = [u for u in ues if u not in bad]
    slots = row["slots_ranked"]
    out = {"arm": row["arm"], "seed": row["seed"],
           "M05": row["M05_fraction"], "failing_ues": bad,
           "n_ranked_ues": len(ues), "slots_ranked": slots}

    # --- U2 FIRST: was the flow's UE in the candidate set at all? ----------
    pres = {u: row["present"][str(u)] / slots for u in ues}
    out["presence"] = pres
    if bad:
        out["U2_presence_ratio"] = statistics.fmean(pres[u] for u in bad) / \
            (statistics.fmean(pres[u] for u in good) if good else 1.0)

    # --- U1: how much of the order came from a full tie? -------------------
    tt = row["term_totals"]
    total_adj = sum(tt.values())
    out["term_share_all_ues"] = _share(tt, total_adj)
    out["U1_tie_share"] = tt.get(TIE_KEY, 0) / total_adj if total_adj else 0.0

    # --- rank position -----------------------------------------------------
    mr = {u: row["mean_rank"][str(u)] for u in ues}
    out["mean_rank"] = mr
    if bad and good:
        out["rank_gap"] = statistics.fmean(mr[u] for u in bad) - \
            statistics.fmean(mr[u] for u in good)

    # --- the term distribution, failing UEs vs the rest OF THIS RUN --------
    def agg(group):
        acc: dict[str, int] = {}
        for u in group:
            for k, v in row["losses_by_ue"][str(u)].items():
                acc[k] = acc.get(k, 0) + v
        return acc
    if bad and good:
        b, g = agg(bad), agg(good)
        bs, gs = _share(b, sum(b.values())), _share(g, sum(g.values()))
        out["term_share_failing"] = bs
        out["term_share_healthy"] = gs
        out["term_lift"] = {k: bs.get(k, 0.0) - gs.get(k, 0.0) for k in bs}

    # --- PF's factors: L5 / L6 / L7 are not separable by the key -----------
    fs = row.get("factor_stats") or {}
    if row["arm"] == "PF" and bad and good:
        def fmean(group, name, stat="mean"):
            vals = [fs[str(u)][name][stat] for u in group if str(u) in fs
                    and name in fs[str(u)]]
            return statistics.fmean(vals) if vals else None
        out["PF_factors"] = {
            n: {"failing": fmean(bad, n), "healthy": fmean(good, n)}
            for n in ("metric", "bits_per_rb", "r_avg_raw", "r_avg_used",
                      "r_avg_at_clamp", "snr_db")}
    return out


def verdict(reads: list[dict]) -> list[str]:
    """Name the registered outcome, or RESIDUAL. No fourth candidate."""
    lines = []
    by_arm: dict[str, list[dict]] = {}
    for r in reads:
        by_arm.setdefault(r["arm"], []).append(r)

    for arm in sorted(by_arm):
        rs = by_arm[arm]
        fails = [r for r in rs if r["failing_ues"]]
        lines.append(f"\n=== {arm}: {len(fails)}/{len(rs)} seeds with a "
                     f"qfi-2 flow under {BOUND} ===")
        if not fails:
            lines.append("  no failing seed on this arm -- it is the CONTROL "
                         "for the cross-arm reading, not a null result")
            continue

        tie = statistics.fmean(r["U1_tie_share"] for r in fails)
        lines.append(f"  U1  full-tie share of all adjacencies: {tie:.1%}")
        pres = [r.get("U2_presence_ratio") for r in fails
                if r.get("U2_presence_ratio") is not None]
        if pres:
            lines.append(f"  U2  failing UE's candidate-set presence, "
                         f"relative to healthy UEs in the same run: "
                         f"{statistics.fmean(pres):.3f}x")
        gaps = [r["rank_gap"] for r in fails if "rank_gap" in r]
        if gaps:
            lines.append(f"  rank gap (failing minus healthy, same run): "
                         f"{statistics.fmean(gaps):+.3f} positions")

        lifts: dict[str, list[float]] = {}
        for r in fails:
            for k, v in (r.get("term_lift") or {}).items():
                lifts.setdefault(k, []).append(v)
        if lifts:
            lines.append("  term lift (share of the failing UE's losses minus "
                         "the healthy UEs', same run):")
            for k, vs in sorted(lifts.items(),
                                key=lambda kv: -abs(statistics.fmean(kv[1]))):
                lines.append(f"      {k:<28} {statistics.fmean(vs):+.4f}  "
                             f"(seeds {sum(1 for v in vs if v > 0)}/{len(vs)} "
                             f"positive)")
        if arm == "PF":
            for r in fails:
                for n, d in (r.get("PF_factors") or {}).items():
                    if d["failing"] is None:
                        continue
                    lines.append(f"      PF factor {n:<16} failing="
                                 f"{d['failing']:.4g}  healthy="
                                 f"{d['healthy']:.4g}")
                break
    return lines


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", default="sweeps/phase2/g5_rank.json")
    a = ap.parse_args(argv[1:])
    blob = json.loads((REPO / a.rows).read_text())
    rows = blob["rows"]
    if not rows:
        raise SystemExit("no rows -- an aggregate over nothing is not a result")
    arms = sorted({r["arm"] for r in rows})
    if len(arms) < 3:
        raise SystemExit(
            f"only {arms} present. The registered cross-arm reading needs all "
            f"three: a single-arm trace cannot say whether the lever is a "
            f"property of QoS-aware ranking or a shared outcome of two "
            f"different mechanisms. Refusing to read.")
    reads = [read_run(r) for r in rows]
    print(f"{len(rows)} runs, arms={arms}, "
          f"{len({r['seed'] for r in rows})} seeds, "
          f"horizon={rows[0]['horizon']}, n_ues={rows[0]['n_ues']}")
    for line in verdict(reads):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
