"""G8 / GT-5.1 report. Field names verified against the runner that wrote them.

Reads `scripts/g8_fairness.py`'s artefact and prints the four conjuncts
separately, because a conjunction reported as one number hides which half
failed -- the defect the panel's M08/M09 binding had before M22 existed.
"""
import json
import sys
from collections import defaultdict


def main(path):
    d = json.load(open(path))
    rows = d["rows"]
    arms, ns, loads = [], [], []
    for r in rows:
        for seq, val in ((arms, r["arm"]), (ns, r["n_ues"]),
                         (loads, r["committed_mult"])):
            if val not in seq:
                seq.append(val)
    ns.sort()
    loads.sort()

    print(f"artefact : {path}")
    print(f"clause   : {d['_clause']}   horizon {d['_horizon_ms']:g} ms "
          f"({d['_horizon_slots']} slots), cap {d['_cap']}, {d['_seeds']} seeds")
    print(f"bounds   : Jain >= {d['_jain_bound']} per role; 0 starvation epochs "
          f">= {d['_starvation_epoch_s']}s; telemetry gap < {d['_telemetry_gap_ms']}ms; "
          f"window floor >= 1.0 (tolerant {d['_window_floor_tolerance']})")
    print(f"eligible : arrival density >= {d['_min_arrival_density']} over a span "
          f">= {d['_min_active_span_s']:g}s")
    print(f"cells    : {d['_cells']}   loads {d['_load_axis']}   runs {d['_n_runs']}")

    # ---- the conjunction, one part at a time
    for label, key in (("part 1  per-role 1s Jain >= 0.9", "part1_pass"),
                       ("part 2  zero starvation epochs >= 1s", "part2_pass"),
                       ("part 3  zero telemetry gaps >= 1s", "part3_pass"),
                       ("part 4  per-window GFBR floor (STRICT >= 1.0)", "part4_pass"),
                       ("part 4t per-window GFBR floor (tolerant)", "part4_tolerant")):
        print("\n" + "=" * 78)
        print(label)
        print("=" * 78)
        print("  " + f"{'arm':<22}" + "".join(f"{f'N={n} x{m:g}':>12}"
                                              for n in ns for m in loads))
        for arm in arms:
            line = f"  {arm:<22}"
            for n in ns:
                for m in loads:
                    v = [r for r in rows if r["arm"] == arm and r["n_ues"] == n
                         and r["committed_mult"] == m]
                    line += f"{(f'{sum(1 for r in v if r[key])}/{len(v)}' if v else '--'):>12}"
            print(line)

    # ---- ALL FOUR, which is the guarantee
    print("\n" + "=" * 78)
    print("G8 VERDICT -- all four conjuncts in the same run")
    print("=" * 78)
    print("  " + f"{'arm':<22}" + "".join(f"{f'N={n} x{m:g}':>12}"
                                          for n in ns for m in loads))
    for arm in arms:
        line = f"  {arm:<22}"
        for n in ns:
            for m in loads:
                v = [r for r in rows if r["arm"] == arm and r["n_ues"] == n
                     and r["committed_mult"] == m]
                ok = sum(1 for r in v if r["part1_pass"] and r["part2_pass"]
                         and r["part3_pass"] and r["part4_pass"])
                line += f"{(f'{ok}/{len(v)}' if v else '--'):>12}"
        print(line)

    # ---- what actually drives the failures
    print("\n" + "=" * 78)
    print("WHICH CONJUNCT FAILS, and the worst value behind it")
    print("=" * 78)
    for arm in arms:
        v = [r for r in rows if r["arm"] == arm]
        f1 = sum(1 for r in v if not r["part1_pass"])
        f2 = sum(1 for r in v if not r["part2_pass"])
        f3 = sum(1 for r in v if not r["part3_pass"])
        f4 = sum(1 for r in v if not r["part4_pass"])
        jw = min((r["jain_worst"] for r in v if r["jain_worst"] is not None),
                 default=float("nan"))
        ep = max((r["starvation_epochs"] or 0) for r in v)
        gap = max(r["tele_gap_worst_ms"] for r in v)
        wf = min((r["window_floor"] for r in v if r["window_floor"] is not None),
                 default=float("nan"))
        print(f"  {arm:<22} fails: p1 {f1:>3}  p2 {f2:>3}  p3 {f3:>3}  p4 {f4:>3}"
              f"   of {len(v)}")
        print(f"  {'':<22} worst: jain {jw:.4f}  epochs {ep}  "
              f"gap {gap:.0f}ms  floor {wf:.4f}")

    # ---- the starvation population, so the restriction stays auditable
    print("\n" + "=" * 78)
    print("PART 2 AUDIT -- restricted count vs the raw panel M22")
    print("=" * 78)
    sparse = defaultdict(int)
    for r in rows:
        for entry in (r.get("starvation_flows_too_sparse") or []):
            sparse[entry[0]] += 1
    tot_r = sum(r["starvation_epochs"] or 0 for r in rows)
    tot_m = sum(r["m22_epochs_raw"] or 0 for r in rows)
    print(f"  epochs, restricted population : {tot_r}")
    print(f"  epochs, raw panel M22         : {tot_m}")
    print(f"  excluded as too sparse (flow -> how many runs):")
    for k, n in sorted(sparse.items(), key=lambda kv: -kv[1])[:10]:
        print(f"     {k:<16} {n}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "sweeps/g8-fairness/g8_deployed_2026-09-17.json")
