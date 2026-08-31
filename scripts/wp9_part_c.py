"""Part C -- the depth §21.5's pre-registered go/no-go bought.

§21.5 said: buy the grid for an axis iff Part A showed a paired effect whose
CI excludes zero on at least one arm/metric. `duty_cycle` and
`snr_spread_db` qualified; `bg` did not (§22.7). The grid is the axis
crossed with n_ues, plus a load line at the base n_ues -- a CROSS, not a
full factorial, because a full factorial on three axes is what §0.4's cap
existed to prevent.

M03's readings here carry their own cadence caveat automatically
(`sim/scorecard.py`, WP9 Step 4): at duty_cycle <= 0.5 the telemetry
source's configured period approaches or exceeds the T_live/4 bound, so
max_gap_ms measures cadence rather than a liveness failure. The caveat is
derived from each flow's own median gap and travels in the record.

Usage:
    uv run python scripts/wp9_part_c.py [--smoke]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import sweep, write_csv  # noqa: E402
from sim.parametric import sweep_scenario  # noqa: E402
from wp9_sweep import BASE, PersistingRecordSink, _arms, _driver_kwargs  # noqa: E402

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


def _build(seed: int, horizon_slots: int = HORIZON, **axis_values):
    kwargs = {**BASE, **axis_values}
    kwargs.pop("min_rb", None)
    kwargs.pop("horizon_slots", None)
    for k in ("sr_period_slots", "k2_slots"):
        kwargs.pop(k, None)
    return sweep_scenario(seed=seed, horizon_slots=horizon_slots, **kwargs)


def cells(smoke: bool):
    """Emit (axes-dict) per cell. Printed as a count by the runner rather
    than restated in prose -- CLAUDE.md's derive-it rule."""
    out = []
    for axis, spec in CROSS.items():
        for lvl in spec["levels"]:
            for n in spec["n_ues"]:
                out.append({axis: [lvl], "n_ues": [n], "load_mult": [1.0]})
            for load in spec["load_mult"]:
                if load == 1.0:
                    continue          # already covered by the n_ues line
                out.append({axis: [lvl], "n_ues": [BASE["n_ues"]],
                            "load_mult": [load]})
    return out[:2] if smoke else out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--root", default="sweeps/wp9")
    args = ap.parse_args(argv[1:])
    root = Path(args.root)
    grid = cells(args.smoke)
    n_seeds = 2 if args.smoke else N_SEEDS
    horizon = 2000 if args.smoke else HORIZON
    print(f"Part C: {len(grid)} cells x {len(_arms())} arms x {n_seeds} seeds "
          f"= {len(grid) * len(_arms()) * n_seeds} runs")
    suffix = "_SMOKE" if args.smoke else ""
    rows = []
    with PersistingRecordSink(root / f"part_c_records{suffix}.jsonl") as sink:
        for i, axes in enumerate(grid, 1):
            rows += sweep(axes=axes, build_scenario=lambda seed, **kw:
                          _build(seed, horizon_slots=horizon, **kw),
                          schedulers=_arms(), n_seeds=n_seeds,
                          driver_kwargs=_driver_kwargs, record_sink=sink)
            print(f"  cell {i}/{len(grid)} done ({len(rows)} rows)", flush=True)
        print(f"  persisted {sink.n} records")
    write_csv(rows, str(root / f"part_c_rows{suffix}.csv"))
    print(f"wrote {len(rows)} rows -> {root}/part_c_rows{suffix}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
