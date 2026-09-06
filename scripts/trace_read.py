"""Reads `traces.json` and answers the three questions it was captured for.

Prints, per cell, the quantity that DISCRIMINATES rather than the whole
stream: for a UL sort the first-difference rule lands on `-coef` almost
always (the terms above it are coarse gates), so the useful signals are (a)
who loses and to whom, (b) whether the loser's UE was granted anyway, and (c)
how often its own 5QI rode along.
"""
from __future__ import annotations
import json, statistics as st, sys
from pathlib import Path


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def show(rows, cell):
    rs = [r for r in rows if r["cell"] == cell]
    if not rs:
        print(f"\n### {cell}: no rows"); return
    print(f"\n### {cell}   (n={len(rs)//3} seeds x 3 arms)")
    ident = {r["bit_identical_hook_off"] for r in rs}
    print(f"    bit-identical with hook off: {ident}")
    for arm in ("PF", "Reservation", "TwoTier"):
        a = [r for r in rs if r["arm"] == arm]
        if not a:
            continue
        tt = {}
        for r in a:
            for k, v in r["rank"]["term_totals"].items():
                tt[k] = tt.get(k, 0) + v
        tot = sum(tt.values()) or 1
        terms = ", ".join(f"{k}={100*v/tot:.1f}%" for k, v in
                          sorted(tt.items(), key=lambda x: -x[1]) if v)
        # Each metric's value is a dict; name the scalar per metric rather
        # than guessing one, so a changed shape fails visibly instead of
        # silently reporting an empty row.
        SCALAR = {"M01": "p98", "M05": "fraction", "M06": "p95_ms",
                  "M09": "worst"}
        m = {}
        for k, field in SCALAR.items():
            vals = []
            for r in a:
                v = r["metrics"].get(k)
                if isinstance(v, dict) and isinstance(v.get(field), (int, float)):
                    vals.append(v[field])
                elif isinstance(v, (int, float)):
                    vals.append(v)
            if vals:
                m[f"{k}.{field}"] = round(med(vals), 3)
                m[f"{k}.n"] = len(vals)
        # deferral: worst UE by "fraction of its grants that carried 5QI 1"
        worst = []
        for r in a:
            for ue, g in r["grants"].items():
                for q, d in g["by_qfi"].items():
                    if d["frac_grants_carrying"] is not None:
                        worst.append((d["frac_grants_carrying"], q,
                                      d["skipped_p98"], g["n_ul_grants"]))
        worst.sort()
        print(f"  {arm:12s} decisive terms: {terms}")
        print(f"  {'':12s} metrics: {m}")
        if worst:
            f, q, sk, ng = worst[0]
            print(f"  {'':12s} most-deferred flow: 5QI {q} carried on "
                  f"{100*f:.2f}% of its UE's {ng} grants, skipped p98={sk}")


def main() -> int:
    p = sys.argv[1] if len(sys.argv) > 1 else "sweeps/rerun-2026-09-06/traces.json"
    b = json.loads(Path(p).read_text())
    print(f"identity checked: {b.get('identity_checked')}  "
          f"failures: {b.get('identity_failures')}")
    rows = b["rows"]
    for cell in ("g7", "attach_control", "attach", "g5_residual"):
        show(rows, cell)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
