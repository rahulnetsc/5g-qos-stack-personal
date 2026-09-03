"""Part C -- the depth §21.5's pre-registered go/no-go bought.

§21.5 said: buy the grid for an axis iff Part A showed a paired effect whose
CI excludes zero on at least one arm/metric. `duty_cycle` and
`snr_spread_db` qualified; `bg` did not (§22.7). The grid is the axis
crossed with n_ues, plus a load line at the base n_ues -- a CROSS, not a
full factorial, because a full factorial on three axes is what §0.4's cap
existed to prevent.

M03's readings here carry their own cadence caveat automatically
(`sim/scorecard.py`, WP9 Step 4): at duty_cycle 0.1 the telemetry source's
configured period is 1000 ms, above the 500 ms T_live/4 bound, so
max_gap_ms measures cadence rather than a liveness failure. The caveat is
derived from each flow's own median gap and travels in the record.

NOT "<= 0.5", which this header used to say: the wider wording discarded a
genuine arm difference (docs/wp9-plan.md §24.6).

BUT THAT CORRECTION ALSO OVER-SHOT, and this is the current statement. It
said "at duty_cycle 0.5 the period is 200 ms, the caveat does NOT fire".
Measured over this script's own output (sweeps/wp9/part_c_rows.csv), the
caveat fires on 4 of 44 duty-0.5 breaches -- observed medians 596/602/551/
525 ms against that configured 200 ms period.

The predicate is `median_gap_ms > T_live/4` and median_gap_ms is MEASURED,
not configured, so a flow the network degrades from 200 ms to a 600 ms
median trips it. THE EXCLUSION IS A PROPERTY OF EACH ROW, NOT OF THE
duty_cycle AXIS, and must be read per row from the M03.median_gap_ms column
this script already emits.

TwoTier's 503.25 ms / 5-of-10 result is unaffected -- those rows are not
among the four. What does not hold is the blanket claim that duty 0.5 is
caveat-free.

Usage:
    uv run python scripts/wp9_part_c.py [--smoke]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json  # noqa: E402
import multiprocessing as mp  # noqa: E402

from regime_sweep import write_csv  # noqa: E402
from wp9_sweep import BASE, _run_one_cell  # noqa: E402

N_SEEDS = 10
HORIZON = 20_000
# The cross (§21.5): each qualifying axis x n_ues at base load, plus a load
# line at base n_ues. Levels are the ones Part A already measured, so the
# base point is shared and every cell is comparable to it.
CROSS = {
    "duty_cycle": {"levels": [0.5, 0.1], "n_ues": [4, 8, 16, 32],
                   "load_mult": [0.75, 1.0, 1.5]},
    "snr_spread_db": {"levels": [6.0, 12.0], "n_ues": [4, 8, 16, 32],
                      "load_mult": [0.75, 1.0, 1.5]},
}


def cells(smoke: bool):
    """One task per cell, in `_run_one_cell`'s own (axis_values, n_seeds,
    horizon) shape. Count is PRINTED by the runner, never restated: §21.7
    budgeted "~10 cells" while the cross §21.5 specifies derives to 24."""
    n_seeds = 2 if smoke else N_SEEDS
    horizon = 2000 if smoke else HORIZON
    out = []
    for axis, spec in CROSS.items():
        for lvl in spec["levels"]:
            for n in spec["n_ues"]:
                out.append(({axis: lvl, "n_ues": n, "load_mult": 1.0},
                            n_seeds, horizon))
            for load in spec["load_mult"]:
                if load == 1.0:
                    continue          # already covered by the n_ues line
                out.append(({axis: lvl, "n_ues": BASE["n_ues"],
                             "load_mult": load}, n_seeds, horizon))
    return out[:2] if smoke else out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--root", default="sweeps/wp9")
    args = ap.parse_args(argv[1:])
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    tasks = cells(args.smoke)
    suffix = "_SMOKE" if args.smoke else ""

    # PARALLEL OVER CELLS, reusing wp9_sweep._run_one_cell rather than a
    # second implementation. §6.3b's reasoning applies unchanged: cells are
    # independent, within a cell seeds and arms stay ordered, paired_seeds
    # is drawn up front from a fixed base seed, and every run is a pure
    # function of (scenario, seed) -- so this changes no result, only the
    # wall time. Serial, this grid is ~5.5 h summed over its actual n_ues
    # mix; the first attempt ran serially and was killed by an OS suspend
    # at cell 3 of 24.
    print(f"Part C: {len(tasks)} cells on {args.workers} workers "
          f"({sum(1 for _ in tasks) * 3 * tasks[0][1]} runs)")
    rows, n_rec = [], 0
    rec_fh = (root / f"part_c_records{suffix}.jsonl").open("w")
    try:
        with mp.get_context("spawn").Pool(args.workers) as pool:
            for i, (crows, _conline, payload) in enumerate(
                    pool.imap_unordered(_run_one_cell, tasks), 1):
                rows.extend(crows)
                for av, recd, _m13 in payload:
                    rec_fh.write(json.dumps(
                        {"axis_values": av, "record": recd}) + "\n")
                    n_rec += 1
                print(f"  cell {i}/{len(tasks)} done ({n_rec} records)",
                      flush=True)
    finally:
        rec_fh.close()
    write_csv(rows, str(root / f"part_c_rows{suffix}.csv"))
    print(f"wrote {len(rows)} rows -> {root}/part_c_rows{suffix}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
