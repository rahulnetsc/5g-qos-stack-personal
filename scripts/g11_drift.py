"""C2's instrument: monotone drift in per-window internals.

WP9 G11 commit 7. GT-7.1's second KPI is *"internals stable across the run
-- floor-fire rate, `%min_rb` crumb rate, skip-reason counters show no
monotonic drift (leak detector)"*.

STUDY LAYER. `config/metric_panel.yml` is pre-registered and is not edited
for this; nothing here is a registered metric.

WHAT C2 CAN ACTUALLY COVER, established before anything was built:

  crumb rate         EXISTS -- grants <= 150 bytes are already counted
                     (README §8); per-window it is a rate.
  floor-fire rate    EXISTS and is instrumentable the way
                     `scripts/wp9_sweep.py::_instrumented_two_tier` already
                     does it. Its DYNAMIC RANGE here is unknown: §19.5
                     measured `fires = 0` at scale, but on a workload with
                     NO SCRIPTED SILENCES. GT-7.1 is the first workload that
                     has them, and `floor_rx_lastseen` is the route silences
                     would exercise, so this is measured here rather than
                     inherited.
  skip-reason        DOES NOT EXIST. `grep -rn 'skip_reason|skip_count'`
                     over `sim/` and `scheduler/` returns nothing -- they are
                     a gNB log field (`[P5G-UL-SKIP]`) with no simulator
                     counterpart. NOT SCORED, and C2's verdict says so
                     inline rather than quietly covering two of three.

THE GUARD THAT BINDS. A drift detector that cannot return non-flat on a
drifting input cannot report the leak it exists to find -- so
`sim/tests/test_g11_drift.py` feeds it a synthetic ramp and requires an
interval EXCLUDING zero, and feeds it a flat series and requires one
CONTAINING zero. That pairing is the whole check: either alone passes for
the wrong reason.
"""

from __future__ import annotations

import statistics
from typing import Optional, Sequence

import numpy as np

__all__ = ["TrendResult", "theil_sen_slope", "trend", "drift_verdict"]


class TrendResult(dict):
    """A dict so it streams straight into a tidy row like every other
    study-layer output here."""


def theil_sen_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Median of pairwise slopes. Robust to the one-off spikes a soak's
    internals are full of, which is why this and not least squares."""
    slopes = [(ys[j] - ys[i]) / (xs[j] - xs[i])
              for i in range(len(xs)) for j in range(i + 1, len(xs))
              if xs[j] != xs[i]]
    return statistics.median(slopes) if slopes else 0.0


def trend(values: Sequence[float], n_boot: int = 2000,
          seed: int = 0xD817) -> TrendResult:
    """Slope per window, with a bootstrap CI over window indices.

    Returns `value=None` with a reason when the series CANNOT drift --
    fewer than three windows, or every value identical. A constant series
    is not evidence of stability; it is evidence the counter never moved,
    and reporting 'no drift' for it would be a statement about the
    instrument rather than about the run (CLAUDE.md's dynamic-range rule).
    """
    ys = [float(v) for v in values]
    n = len(ys)
    out = TrendResult(n_windows=n, first=ys[0] if ys else None,
                      last=ys[-1] if ys else None)
    if n < 3:
        out.update(value=None, lo=None, hi=None,
                   reason=f"only {n} window(s); a trend needs >=3")
        return out
    if max(ys) == min(ys):
        out.update(value=None, lo=None, hi=None,
                   reason=f"series is constant at {ys[0]!r} -- NO DYNAMIC "
                          f"RANGE, so 'no drift' would describe the counter, "
                          f"not the run")
        return out

    xs = list(range(n))
    slope = theil_sen_slope(xs, ys)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        idx = sorted(rng.integers(0, n, size=n).tolist())
        bx = [xs[i] for i in idx]
        by = [ys[i] for i in idx]
        if len(set(bx)) > 1:
            boots.append(theil_sen_slope(bx, by))
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else slope
    hi = boots[int(0.975 * len(boots))] if boots else slope
    out.update(value=slope, lo=lo, hi=hi,
               excludes_zero=bool(lo > 0 or hi < 0),
               total_change=ys[-1] - ys[0])
    return out


def drift_verdict(series_by_name: dict[str, Optional[Sequence[float]]]) -> dict:
    """C2, scored PER INTERNAL, never pooled.

    A counter that does not exist and a counter that is flat are DIFFERENT
    answers and are reported as such -- pooling them into "C2 passes" would
    be the decompose failure this project has recorded six times.
    """
    per: dict[str, dict] = {}
    for name, vals in series_by_name.items():
        if vals is None:
            per[name] = {"value": None, "scored": False,
                         "reason": "no such counter exists in sim/ or "
                                   "scheduler/ -- hardware log field only"}
            continue
        t = trend(vals)
        t["scored"] = t.get("value") is not None
        per[name] = t
    scored = [k for k, v in per.items() if v.get("scored")]
    drifting = [k for k in scored if per[k].get("excludes_zero")]
    return {
        "per_internal": per,
        "n_named_by_GT_7_1": len(series_by_name),
        "n_scored": len(scored),
        "n_drifting": len(drifting),
        "drifting": drifting,
        # The qualifier travels with the verdict, inline, the way G11's seed
        # count does -- a reader must not take "C2 passes" as covering all
        # three internals when it covers however many were scoreable.
        "verdict": ("DRIFT" if drifting else "NO DRIFT" if scored else "NOT SCORED"),
        "coverage": f"{len(scored)} of {len(series_by_name)} internals GT-7.1 names",
    }
