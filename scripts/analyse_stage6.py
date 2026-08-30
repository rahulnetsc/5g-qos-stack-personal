"""Stage-6 Part A — the unrun guarantees, from records already on disk.

`docs/wp9-plan.md` §21.3. G6, H2, H3 and G12 are all computable from
`sweeps/wp9/stage{1,4}/` with ZERO new runs: the `bg`, `duty_cycle` and
`snr_spread_db` excursion cells were run in stage 1 and carry the identical
seed set as the base cell, so every comparison here is WITHIN-SEED PAIRED.
What is missing on those axes is depth (one cell, at the base point), not
the axis -- see §21.5's go/no-go for whether depth gets bought.

WHAT THIS SCRIPT REFUSES TO DO. Stage 1's excursion rows carry the EMPTY
STRING for every axis they do not vary: `bg` is '' on 1,740 of 1,770 rows,
`duty_cycle` and `snr_spread_db` on 1,710. **1,710 is exactly the row count
behind the None-base contamination bug recorded in CLAUDE.md**, where a
cell selected every core-plane row and an axis was promoted into stage 2 on
that basis. So membership is tested with `wp9_gate.carries_axis` (never by
value equality), levels are coerced back to their declared types at the CSV
boundary, and cell size AND seed-set equality are asserted before anything
is scored. A cell that selects 0 or 1,710 rows raises.

Usage:
    uv run python scripts/analyse_stage6.py sweeps/wp9
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import bootstrap_ci  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.scorecard import Scorecard  # noqa: E402
from wp9_gate import carries_axis  # noqa: E402
from wp9_sweep import BASE, EXCURSIONS  # noqa: E402

ARMS = ("PF", "Reservation", "TwoTier")
N_SEEDS = 10
CELL_SIZE = len(ARMS) * N_SEEDS

# G6's statistic is GT-4.1's own: a RELATIVE delta with a +20% bar, on the
# guarantee-facing metrics §5(a) names for it. Sign is the panel's:
# M01.p98 and M03.max_gap_ms are lower-better, M05.fraction higher-better.
G6_METRICS = ("M01.p98", "M03.max_gap_ms", "M05.fraction")
G6_BAR = 0.20

# H2/H3 are arm-separation questions, so they read the arm-separating pair
# the whole WP has used -- §0.1's rule applies and BOTH are always reported.
H_METRICS = ("M07.met", "M08.fraction")


def _coerce(axis: str, sval: str) -> Optional[Any]:
    """CSV round-trips every level to a string; coerce back against the
    axis's OWN declared levels (`wp9_sweep.EXCURSIONS`/`BASE`), not by
    guessing from the text. The `'True'`-vs-`True` failure this prevents is
    already recorded in CLAUDE.md -- it scored a cell at exactly 0.000."""
    declared = list(EXCURSIONS.get(axis, []))
    if axis in BASE and BASE[axis] is not None:
        declared.append(BASE[axis])
    for level in declared:
        if isinstance(level, bool):
            if sval == str(level):
                return level
        elif isinstance(level, (int, float)):
            try:
                if float(sval) == float(level):
                    return level
            except ValueError:
                pass
        elif sval == str(level):
            return level
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Load a stage CSV, coercing axis levels at the boundary and leaving a
    blank axis ABSENT rather than present-as-empty, so `carries_axis` can
    tell "did not vary this axis" from "varied it to its base level"."""
    axes = set(EXCURSIONS) | set(BASE) | {"n_ues", "load_mult"}
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(open(path)):
        row: dict[str, Any] = {"scheduler": raw["scheduler"],
                               "seed": int(float(raw["seed"]))}
        for axis in axes:
            sval = raw.get(axis, "")
            if sval in ("", "None"):
                continue
            coerced = _coerce(axis, sval)
            if coerced is not None:
                row[axis] = coerced
        for key, sval in raw.items():
            if key in axes or key in ("scheduler", "seed") or key.endswith(".status"):
                continue
            if sval in ("", "None"):
                row[key] = None
                continue
            try:
                row[key] = float(sval)
            except ValueError:
                row[key] = sval
        rows.append(row)
    return rows


def base_cell(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The core-plane cell every excursion is measured against: the base
    point (§1). An excursion row carries ONLY its own axis, so the base
    comparison has to come from the core plane, not from 'the rows where
    this axis is absent' -- which is all 1,710 of them."""
    cell = [r for r in rows
            if r.get("n_ues") == BASE["n_ues"]
            and r.get("load_mult") == BASE["load_mult"]
            and not any(carries_axis(r, a) for a in EXCURSIONS)]
    _assert_cell(cell, "base point (n_ues=8, load_mult=1.0)")
    return cell


def excursion_cell(rows: list[dict[str, Any]], axis: str, level: Any) -> list[dict[str, Any]]:
    cell = [r for r in rows if carries_axis(r, axis) and r.get(axis) == level]
    _assert_cell(cell, f"{axis}={level!r}")
    return cell


def _assert_cell(cell: list[dict[str, Any]], label: str) -> None:
    """§21.3's third rule. An empty selection and a 1,710-row selection are
    the two failure signatures this project has actually produced, and both
    score plausibly rather than erroring on their own."""
    if len(cell) != CELL_SIZE:
        raise AssertionError(
            f"cell {label}: selected {len(cell)} rows, expected "
            f"{CELL_SIZE} ({len(ARMS)} arms x {N_SEEDS} seeds). "
            f"0 means the level never matched (coercion); a number in the "
            f"thousands means the axis-membership test leaked.")
    by_arm: dict[str, set[int]] = {}
    for row in cell:
        by_arm.setdefault(row["scheduler"], set()).add(row["seed"])
    if set(by_arm) != set(ARMS):
        raise AssertionError(f"cell {label}: arms {sorted(by_arm)} != {sorted(ARMS)}")
    for arm, seeds in by_arm.items():
        if len(seeds) != N_SEEDS:
            raise AssertionError(f"cell {label}/{arm}: {len(seeds)} seeds, expected {N_SEEDS}")


def paired_deltas(
    base: list[dict[str, Any]], exc: list[dict[str, Any]], arm: str, metric: str,
    relative: bool,
) -> list[float]:
    """Per-seed delta for one arm. Paired within seed -- NOT a difference of
    means -- which is the whole reason the excursion cells were run on the
    same seed set as the base. Asserts the two seed sets are EQUAL, not
    merely the same size (§21.3)."""
    b = {r["seed"]: r.get(metric) for r in base if r["scheduler"] == arm}
    e = {r["seed"]: r.get(metric) for r in exc if r["scheduler"] == arm}
    if set(b) != set(e):
        raise AssertionError(
            f"{arm}/{metric}: seed sets differ, so no paired comparison exists "
            f"(base-only {sorted(set(b) - set(e))}, exc-only {sorted(set(e) - set(b))})")
    out: list[float] = []
    for seed in sorted(b):
        bv, ev = b[seed], e[seed]
        if bv is None or ev is None:
            continue
        if relative:
            if bv == 0:
                continue          # a relative delta off a zero base is undefined
            out.append((ev - bv) / abs(bv))
        else:
            out.append(ev - bv)
    return out


def _fmt_ci(ci: dict[str, float], pct: bool = False) -> str:
    scale, unit = (100.0, "%") if pct else (1.0, "")
    return (f"{ci['point'] * scale:+8.3f}{unit}  "
            f"[{ci['lo'] * scale:+8.3f}, {ci['hi'] * scale:+8.3f}]{unit}  n={ci['n']}")


def _excludes_zero(ci: dict[str, float]) -> bool:
    return ci["lo"] > 0.0 or ci["hi"] < 0.0


def impairment_interval(metric: str, ci: dict[str, float]) -> tuple[float, float, float]:
    """Turn a signed delta interval into an IMPAIRMENT interval.

    Direction is the panel's: M01.p98 and M03.max_gap_ms are lower-better so
    a positive delta impairs; M05.fraction is higher-better so a negative
    delta impairs. The whole interval is flipped, not just the point --
    flipping the point alone leaves the bounds the wrong way round, which
    would silently invert every verdict on that metric.
    """
    if metric == "M05.fraction":
        return -ci["point"], -ci["hi"], -ci["lo"]
    return ci["point"], ci["lo"], ci["hi"]


def g6_verdict(lo: float, hi: float, bar: float = G6_BAR) -> str:
    """GT-4.1's bar, tested against the INTERVAL rather than the point.

    A point estimate of +74.9% impairment with a CI of [-22%, +205%] is not
    a failed guarantee, it is an undetermined one; reporting FAIL there would
    be reading a number this data does not support. FAIL requires the whole
    interval above the bar, PASS the whole interval at or below it.
    """
    if hi <= bar:
        return "PASS"
    if lo > bar:
        return "FAIL"
    return "INCONCLUSIVE"


# -- G6 ---------------------------------------------------------------------

def report_g6(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """GT-4.1's delta statistic: does background traffic impair the fleet by
    more than +20% relative, on the guarantee-facing metrics?"""
    print("\n" + "=" * 78)
    print("G6 -- background traffic never impairs the fleet (GT-4.1's own bar: "
          f"<= +{G6_BAR:.0%} relative)")
    print("=" * 78)
    base = base_cell(rows)
    exc = excursion_cell(rows, "bg", True)
    print("\n  NOTE: a RELATIVE delta is undefined off a zero base, so seeds\n"
          "  whose base value is 0 are dropped -- and for M05.fraction those\n"
          "  are exactly the seeds where the base run was ALREADY failing\n"
          "  completely. The drop is therefore not random: it biases M05's\n"
          "  delta OPTIMISTIC. Dropped counts are printed per cell.")
    out: dict[str, Any] = {"bar": G6_BAR, "arms": {}}
    for arm in ARMS:
        out["arms"][arm] = {}
        print(f"\n  {arm}")
        for metric in G6_METRICS:
            deltas = paired_deltas(base, exc, arm, metric, relative=True)
            if not deltas:
                print(f"    {metric:18s}  (no paired samples)")
                out["arms"][arm][metric] = None
                continue
            ci = bootstrap_ci(deltas, seed=hash((arm, metric)) & 0xFFFF)
            # "Impairment" is direction-aware: for a lower-better metric a
            # POSITIVE relative delta is worse; for M05.fraction (higher-
            # better) it is a NEGATIVE delta that impairs. Flip the whole
            # interval, not just the point -- flipping the point alone would
            # leave the bounds the wrong way round.
            imp, lo, hi = impairment_interval(metric, ci)
            verdict = g6_verdict(lo, hi)
            dropped = N_SEEDS - len(deltas)
            warn = f"  [{dropped} seed(s) dropped]" if dropped else ""
            print(f"    {metric:18s}  {_fmt_ci(ci, pct=True)}   impairment "
                  f"{imp * 100:+7.2f}%  [{lo * 100:+7.2f}, {hi * 100:+7.2f}]%   "
                  f"{verdict}{warn}")
            out["arms"][arm][metric] = {
                "ci": ci, "impairment": imp, "impairment_lo": lo,
                "impairment_hi": hi, "verdict": verdict,
                "n_paired": len(deltas), "n_dropped": dropped,
                "ci_excludes_zero": _excludes_zero(ci),
            }
    return out


# -- H2 / H3 ----------------------------------------------------------------

def report_axis(rows: list[dict[str, Any]], axis: str, label: str) -> dict[str, Any]:
    """H2 (`duty_cycle`) / H3 (`snr_spread_db`): a paired per-arm delta at
    each level. §0.1's rule applies -- M07 and M08 are always reported
    together, never one alone."""
    print("\n" + "=" * 78)
    print(f"{label} -- axis `{axis}` vs the base point, paired within seed")
    print("=" * 78)
    base = base_cell(rows)
    out: dict[str, Any] = {"axis": axis, "levels": {}}
    for level in EXCURSIONS[axis]:
        exc = excursion_cell(rows, axis, level)
        print(f"\n  {axis} = {level!r}")
        out["levels"][str(level)] = {}
        for arm in ARMS:
            cells = []
            for metric in H_METRICS:
                deltas = paired_deltas(base, exc, arm, metric, relative=False)
                ci = bootstrap_ci(deltas, seed=hash((axis, level, arm, metric)) & 0xFFFF)
                cells.append((metric, ci))
                out["levels"][str(level)].setdefault(arm, {})[metric] = {
                    "ci": ci, "excludes_zero": _excludes_zero(ci),
                }
            flags = "".join("*" if _excludes_zero(ci) else " " for _, ci in cells)
            print(f"    {arm:12s} " + "   ".join(
                f"{m}: {_fmt_ci(ci)}" for m, ci in cells) + f"   {flags}")
    print("\n  (* = bootstrap CI excludes zero for that arm/metric)")
    return out


# -- G12 --------------------------------------------------------------------

def _stream_records(path: Path) -> Iterator[tuple[dict[str, Any], RunRecord]]:
    """Stream, projecting each record down to its GBR flows immediately.

    CLAUDE.md's own 25 GB retention lesson applies directly: stage 1's
    records.jsonl is 1.4 GB on disk and inflates far beyond that as objects,
    so nothing whole is retained. M13 reads only `.key`, `.qfi`,
    `.flow_class` and `meets_gbr_contract()` (throughput_bps / gfbr_bps).
    """
    with path.open() as fh:
        for line in fh:
            payload = json.loads(line)
            rec_d = payload["record"]
            rec_d["flows"] = {
                k: v for k, v in rec_d["flows"].items() if v.get("flow_class") == "GBR"
            }
            for fr in rec_d["flows"].values():
                for field in ("ts_backlog_bytes", "ts_hol_delay_s", "ts_delivered_bytes",
                              "ts_arrived_bytes", "ts_dropped_bytes",
                              "completion_ts_by_role_s", "frame_completions"):
                    fr[field] = None
            yield payload["axis_values"], RunRecord.from_dict(rec_d)


def report_g12(stage_dir: Path, ramp_axis: str, group_axes: tuple[str, ...],
               label: str) -> dict[str, Any]:
    """M13: over an ascending-load column, the ORDER in which 5QI classes
    first fail their GBR contract.

    `ramp_axis` differs per stage and is NOT assumed: stage 1 ramps
    `load_mult`, stage 4 ramps `video_tier`. Passing the wrong one selects
    nothing and every group silently disappears -- which is how the first
    version of this function reported "distinct orderings: 0" from an empty
    selection, the exact failure signature CLAUDE.md records twice.
    """
    print("\n" + "=" * 78)
    print(f"G12 -- first-violation order (M13), {label}  [ramp: {ramp_axis}]")
    print("=" * 78)
    path = stage_dir / "records.jsonl"
    if not path.exists():
        print(f"  (no records.jsonl in {stage_dir})")
        return {"status": "absent"}
    by_group: dict[tuple, list[tuple[float, RunRecord]]] = {}
    class_of: dict[str, int] = {}
    gbr_5qis: set[int] = set()
    n_records = 0
    for axis_values, rec in _stream_records(path):
        n_records += 1
        ramp = axis_values.get(ramp_axis)
        if ramp is None:
            continue                    # excursion rows are not a load ramp
        key = tuple(axis_values.get(a) for a in group_axes) + (rec.scheduler_name,)
        by_group.setdefault(key, []).append((float(ramp), rec))
        for fr in rec.flows.values():
            class_of[fr.key] = fr.qfi
            gbr_5qis.add(fr.qfi)
    if not by_group:
        raise AssertionError(
            f"G12/{label}: ramp axis {ramp_axis!r} matched NO record out of "
            f"{n_records}. An empty selection scores as a plausible-looking "
            f"zero; check the stage's own axis names before reading anything.")

    # THE STRUCTURAL CHECK, and it is the actual G12 result on this corpus.
    # M13 orders 5QI CLASSES against each other, so it needs at least two GBR
    # classes to have anything to order. `_stream_records` keeps only
    # flow_class == "GBR", which is what `first_violation_order` itself reads.
    print(f"  GBR 5QI classes present across {n_records} records: "
          f"{sorted(gbr_5qis)}")
    if len(gbr_5qis) < 2:
        print(f"  STRUCTURALLY UNINFORMATIVE: M13 orders 5QI classes against\n"
              f"  each other and this workload has exactly {len(gbr_5qis)}\n"
              f"  GBR class. Every group's 'order' is a one-element list, which\n"
              f"  is not an ordering. Note the delay-critical classes here\n"
              f"  (5QI 1/82/83/85) are flow_class='Delay', which M13 does not\n"
              f"  read -- widening it to them would be redefining a\n"
              f"  pre-registered metric, which config/metric_panel.yml's own\n"
              f"  rule forbids. G12 needs a workload with >=2 GBR classes.")
        return {"status": "structurally_uninformative",
                "gbr_5qis": sorted(gbr_5qis), "n_groups": len(by_group),
                "n_records": n_records}

    sc = Scorecard()
    orders_by_group: dict[str, list[int]] = {}
    for key in sorted(by_group, key=lambda k: tuple(str(x) for x in k)):
        seq = sorted(by_group[key], key=lambda pair: pair[0])
        res = sc.first_violation_order([r for _ramp, r in seq], class_of)
        order = res.value["order_5qi"]
        orders_by_group[" / ".join(str(x) for x in key)] = order
        print(f"  {' / '.join(str(x) for x in key):32s} -> 5QI order {order}")
    distinct = {tuple(v) for v in orders_by_group.values()}
    print(f"\n  distinct orderings across {len(orders_by_group)} groups: {len(distinct)}")
    for order in sorted(distinct, key=str):
        holders = [k for k, v in orders_by_group.items() if tuple(v) == order]
        print(f"    {list(order)}  <- {len(holders)} group(s)")
    return {"status": "ok", "orders": orders_by_group,
            "n_distinct": len(distinct), "gbr_5qis": sorted(gbr_5qis)}


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("sweeps/wp9")
    rows = load_rows(root / "stage1" / "stage1_rows.csv")
    print(f"loaded {len(rows)} stage-1 rows from {root}")
    results = {
        "g6": report_g6(rows),
        "h2": report_axis(rows, "duty_cycle", "H2 (two-tier wins as traffic becomes bursty)"),
        "h3": report_axis(rows, "snr_spread_db", "H3 (two-tier wins as the channel spreads)"),
        "g12_stage1": report_g12(root / "stage1", "load_mult", ("n_ues",),
                                 "stage 1, per fleet size"),
        "g12_stage4": report_g12(root / "stage4", "video_tier", ("composition",),
                                 "stage 4, per fleet composition"),
    }
    out_path = root / "stage6_partA.json"
    out_path.write_text(json.dumps(results, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
