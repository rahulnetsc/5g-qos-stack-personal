"""Instalment 6 / Group F -- G9 transitions, all arms on +CG footing.

Field names are TAKEN FROM the artefact (dumped and verified 2026-09-17), not
guessed: cells are 'rejoin/case/nUES_cmMULT/arm', each holding eps0.5ms ..
eps5ms, each of those holding outcome / pass_rate / cell_broken_seeds /
catastrophic_seeds / neighbours_within_eps / first_service_p50_s /
stable_cell_p50_s / attach_p50_s / nb_dp98_ci / checks_total / wall_s_total.

Keys are PARSED, never reconstructed -- 'n8_cm1' vs 'n8_cm1.25' formatting has
bitten this campaign before.
"""
import json
import sys
from collections import defaultdict

EPS = "eps1ms"  # headline; disagreement across eps is reported separately


def load(path):
    d = json.load(open(path))
    meta = {k: v for k, v in d.items() if k.startswith("_")}
    cells = {}
    for k, v in d.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        parts = k.split("/")
        if len(parts) != 4:
            continue
        rejoin, case, level, arm = parts
        cells[(rejoin, case, level, arm)] = v
    return meta, cells


def main(path):
    meta, cells = load(path)
    arms, levels, cases, rejoins = [], [], [], []
    for (rj, ca, lv, ar) in cells:
        for seq, val in ((arms, ar), (levels, lv), (cases, ca), (rejoins, rj)):
            if val not in seq:
                seq.append(val)

    axis = meta.get("_axis", [])
    order = {f"n{int(u)}_cm{m:g}": i for i, (u, m) in enumerate(axis)}
    levels.sort(key=lambda l: order.get(l, 99))

    print(f"artefact : {path}")
    print(f"axis     : {axis}")
    print(f"seeds    : {meta.get('_seeds')}   cap: {meta.get('_cap')}   "
          f"runs: {meta.get('_n_runs')}   wall: {meta.get('_wall_s', 0) / 60:.1f} min")
    print(f"arms     : {arms}")
    print(f"cells    : {len(cells)}  (expected {len(arms) * len(levels) * len(cases) * len(rejoins)})")

    # ---- COMPLETIONS FIRST. CLAUDE.md: a count-only assertion passes on an arm
    # ---- that registers every event and completes none of them.
    print("\n" + "=" * 78)
    print("COMPLETION GATE -- did the transition MECHANISM actually finish?")
    print("(srb dialogues started vs completed; an arm that starts 50 and")
    print(" completes 0 reports 'instant recovery' for a UE that never returned)")
    print("=" * 78)
    bad = []
    for arm in arms:
        st = co = stall = 0
        for (rj, ca, lv, ar), v in cells.items():
            if ar != arm:
                continue
            ch = (v.get(EPS) or {}).get("checks_total") or {}
            st += ch.get("srb_dialogues_started", 0)
            co += ch.get("srb_dialogues_completed", 0)
            stall += ch.get("srb_active_at_end", 0)
        rate = co / st if st else float("nan")
        flag = "" if rate > 0.995 else "   <-- INCOMPLETE"
        if rate <= 0.995:
            bad.append(arm)
        print(f"  {arm:<22} started {st:>5}  completed {co:>5}  "
              f"({rate:6.2%})  stalled_at_end {stall:>3}{flag}")

    # ---- VERDICTS
    for case in cases:
        print("\n" + "=" * 78)
        print(f"CASE: {case}")
        print("=" * 78)
        for rj in rejoins:
            print(f"\n  rejoin-seed = {rj}")
            head = "  " + f"{'arm':<22}" + "".join(f"{l:>13}" for l in levels)
            print(head)
            for arm in arms:
                row = f"  {arm:<22}"
                for lv in levels:
                    v = cells.get((rj, case, lv, arm))
                    if not v:
                        row += f"{'--':>13}"
                        continue
                    c = v.get(EPS) or {}
                    out = str(c.get("outcome", "?"))
                    pr = c.get("pass_rate", "")
                    tag = {"PASS": "P", "FAIL": "F", "JOIN FAILURE": "JF",
                           "CELL ALREADY BROKEN": "BROKEN"}.get(out, out[:6])
                    row += f"{tag + ':' + str(pr):>13}"
                print(row)

    # ---- the continuous quantities the clause is actually about
    print("\n" + "=" * 78)
    print("FIRST SERVICE AFTER THE TRANSITION (p50, seconds) -- lower is better")
    print("=" * 78)
    for case in cases:
        print(f"\n  {case}")
        print("  " + f"{'arm':<22}" + "".join(f"{l:>13}" for l in levels))
        for arm in arms:
            row = f"  {arm:<22}"
            for lv in levels:
                vals = [(cells.get((rj, case, lv, arm)) or {}).get(EPS, {}).get("first_service_p50_s")
                        for rj in rejoins]
                vals = [x for x in vals if isinstance(x, (int, float))]
                row += f"{(f'{min(vals):.3f}' if vals else '--'):>13}"
            print(row)

    # ---- eps sensitivity: does the verdict depend on the neighbour epsilon?
    print("\n" + "=" * 78)
    print("EPS SENSITIVITY -- cells whose outcome changes across eps0.5/1/2/5ms")
    print("=" * 78)
    n = 0
    for k, v in sorted(cells.items()):
        outs = {e: (v.get(e) or {}).get("outcome") for e in
                ("eps0.5ms", "eps1ms", "eps2ms", "eps5ms")}
        if len(set(outs.values())) > 1:
            n += 1
            print(f"  {'/'.join(k)}: {outs}")
    print(f"  ({n} of {len(cells)} cells are eps-sensitive)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "sweeps/cs2-increments/g9_groupF_2026-09-17.json")
