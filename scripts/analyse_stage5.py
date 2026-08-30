"""Stage-5 analysis -- the lidar-activation excursion (`docs/wp9-plan.md` §16).

**Written before the data exists**, like stage 3's (`b862cb4`). An analyser
written after seeing results is an analyser whose thresholds were chosen
knowing which side they would land on; §16.6 pre-registers the controls and
expectations precisely so the scoring is checkable from history.

**The read order is enforced here, not left to discipline** (§16.9):

  1. **C1 -- the null-lidar identity. STOP CONDITION.** `sensor_dense` at
     N=4/8 has zero UGVs, so `lidar_ues` in {1,2} activates nothing and every
     row must be BIT-IDENTICAL to `lidar_ues=0`. A difference with no lidar
     can only come from the axis plumbing, so this exits non-zero and
     NOTHING else is read.
  2. **C2** -- the cell census, recomputed from `build_fleet`.
  3. **C5** -- the 16 control cells against stage 4's own rows.
  4. **C3** -- M02w calibrated against panel M02 at the `full` window,
     reported as a distribution BEFORE any windowed number is quoted.
  5. **C4** -- the pre-window read, whose branch FIXES THE WORDING of E1-E4
     and is therefore named before they are printed.
  6. **Contiguity**, per composition over ordered axes only, before any
     effect size.
  7. **E1-E4**, hits and misses both, M07w and M08w always together.

Usage:
    uv run python scripts/analyse_stage5.py sweeps/wp9/stage5
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from itertools import product
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import bootstrap_ci, check_contiguity  # noqa: E402
from wp9_sweep import (  # noqa: E402
    STAGE5_EXPECTED_CENSUS, STAGE5_GRID, _stage5_cell_census,
)

ARMS = ("PF", "Reservation", "TwoTier")

# Sign convention: +1 = higher is better. M07w counts contracts met and M08w
# is the max-min floor, so both are +1; M01w is latency and M02w a violation
# rate, so both are -1.
WINDOWED_DIRECTION = {"M01w": -1, "M02w": -1, "M07w": +1, "M08w": +1}

# The value key each windowed metric reports under.
WINDOWED_VALUE_KEY = {"M01w": "p99", "M02w": "value",
                      "M07w": "met", "M08w": "fraction"}

# §16.6 C1: the cells where a lidar request activates nothing.
NULL_CELLS = [("sensor_dense", 4), ("sensor_dense", 8)]

# §15.4's onset table, the comparison E2 is scored against. None = never
# separated within stage 4's grid.
STAGE4_ONSET_N = {"sensor_dense": None, "mixed": 32,
                  "drone_heavy": 32, "ugv_heavy": 16}


# --------------------------------------------------------------- loading

def _coerce(axis: str, sval: str, grid: dict) -> Any:
    """Coerce a CSV value back to its DECLARED axis type.

    CLAUDE.md's serialization rule, and it has already cost this WP once:
    booleans round-trip as the string 'True', match nothing, and a cell
    silently selects zero rows -- which scored exactly 0.000 and was only
    catchable because 0.000 is an impossible number rather than a plausible
    one. Do not rely on implausibility; coerce at the boundary.
    """
    for lv in grid[axis]:
        if isinstance(lv, bool):
            if sval == str(lv):
                return lv
        elif isinstance(lv, (int, float)):
            try:
                if float(sval) == float(lv):
                    return lv
            except ValueError:
                pass
        elif sval == str(lv):
            return lv
    return None


def _norm_csv(v: Any) -> Any:
    """Empty / 'None' -> None, the same normalisation `load_rows` applies.

    Both sides of an identity check must pass through this or the check
    compares a normalisation difference and reports a mismatch that is not
    one -- which is exactly what C5 did on its first run: 480 control rows
    flagged on `M04.flow=None vs ''` with zero real differences underneath.
    """
    return None if v in ("", "None") else v


def _as_bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if v in ("True", "true", "1"):
        return True
    if v in ("False", "false", "0"):
        return False
    return None


def load_rows(path: Path, grid: dict = STAGE5_GRID) -> list[dict[str, Any]]:
    """Panel rows. Axis values coerced; every other column kept as the RAW
    string, so C1/C5's identity checks compare what the run actually emitted
    rather than a re-parse of it."""
    rows: list[dict[str, Any]] = []
    for r in csv.DictReader(open(path)):
        d: dict[str, Any] = {"scheduler": r["scheduler"],
                             "seed": int(float(r["seed"]))}
        for axis in grid:
            v = r.get(axis, "")
            if v not in ("", "None"):
                c = _coerce(axis, v, grid)
                if c is not None:
                    d[axis] = c
        d["transient_excluded"] = _as_bool(r.get("transient_excluded"))
        for k, v in r.items():
            if k in grid or k in ("scheduler", "seed", "transient_excluded"):
                continue
            d[k] = None if v in ("", "None") else v
        rows.append(d)
    return rows


def load_windowed(path: Path) -> list[dict[str, Any]]:
    """The windowed rows from `online_rows.jsonl` -- JSON, so the axis values
    are already their declared types and need no coercion."""
    out = []
    for line in open(path):
        r = json.loads(line)
        if str(r.get("metric", "")).endswith("w"):
            out.append(r)
    return out


# ------------------------------------------------- the exclusion, enforced

class TransientExclusionError(RuntimeError):
    """Raised on any attempt to aggregate a run-aggregate panel metric across
    lidar-on cells (§16.5)."""


def aggregate_panel(rows: list[dict], column: str) -> float:
    """Mean of a panel column, refusing transient cells.

    §16.5 is an EXCLUSION LIST, NOT A WARNING: at 5 s a 2 s activation is
    40 % of the run, so a run-aggregate figure from a lidar-on cell mixes two
    regimes. The rows are written in full (an omitted row is
    indistinguishable from a forgotten one) and refused here instead.
    """
    bad = [r for r in rows if r.get("transient_excluded")]
    if bad:
        raise TransientExclusionError(
            f"refusing to aggregate {column!r} across {len(bad)} lidar-on "
            f"cell rows -- run-aggregate panel metrics are not interpretable "
            f"on a transient cell (docs/wp9-plan.md §16.5). Use the windowed "
            f"variants M01w/M02w/M07w/M08w instead.")
    vals = [_numeric(r.get(column)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        raise ValueError(f"no numeric values for {column!r}")
    return st.fmean(vals)


def _numeric(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- C1 .. C5

def c1_null_identity(rows: list[dict]) -> tuple[bool, list[str]]:
    """STOP CONDITION. Zero UGVs means `lidar_ues` in {1,2} activates
    nothing, so the run must be bit-identical to `lidar_ues=0`.

    Compares raw emitted strings for every non-axis column -- exact equality,
    no tolerance. A run is a pure function of scenario+seed, so anything less
    than exact would be hiding a real difference.
    """
    problems: list[str] = []
    compared = 0
    for comp, n in NULL_CELLS:
        def pick(lu):
            return {(r["scheduler"], r["seed"]): r for r in rows
                    if r.get("composition") == comp and r.get("n_ues") == n
                    and r.get("lidar_ues") == lu}
        base = pick(0)
        for lu in (1, 2):
            other = pick(lu)
            shared = sorted(set(base) & set(other))
            if not shared:
                problems.append(
                    f"{comp} N={n} lidar_ues={lu}: NO shared rows to compare "
                    f"-- the cell is missing, not identical")
                continue
            for key in shared:
                ra, rb = base[key], other[key]
                cols = [c for c in ra
                        if c not in ("lidar_ues", "scheduler", "seed")]
                diff = [c for c in cols if ra.get(c) != rb.get(c)]
                compared += 1
                if diff:
                    problems.append(
                        f"{comp} N={n} lidar_ues={lu} {key}: {len(diff)} "
                        f"cols differ, e.g. " + ", ".join(
                            f"{c}={ra.get(c)!r} vs {rb.get(c)!r}"
                            for c in diff[:3]))
    return (not problems), [f"compared {compared} paired rows"] + problems[:10]


def c2_census() -> tuple[bool, dict]:
    census = _stage5_cell_census(STAGE5_GRID)
    return census == STAGE5_EXPECTED_CENSUS, census


def c5_stage4_identity(
    rows: list[dict], stage4_csv: Path,
) -> tuple[bool, list[str]]:
    """The 16 `lidar_ues=0` cells must reproduce stage 4's `video_tier=1.0`
    rows exactly -- same builder, same paired seeds, same driver kwargs.

    Stronger coverage than C1 (16 cells, not 4): a mismatch means plumbing
    the lidar axis changed the lidar-OFF path.
    """
    if not stage4_csv.exists():
        return False, [f"stage-4 rows not found at {stage4_csv}"]
    s4: dict[tuple, dict] = {}
    for r in csv.DictReader(open(stage4_csv)):
        if r.get("video_tier") not in ("1.0", "1"):
            continue
        key = (r["composition"], int(float(r["n_ues"])), r["scheduler"],
               int(float(r["seed"])))
        s4[key] = r

    problems: list[str] = []
    compared = 0
    for r in rows:
        if r.get("lidar_ues") != 0:
            continue
        key = (r.get("composition"), r.get("n_ues"), r["scheduler"], r["seed"])
        ref = s4.get(key)
        if ref is None:
            problems.append(f"{key}: no stage-4 counterpart")
            continue
        # Compare only columns both runs emit: stage 5 adds lidar_ues /
        # n_lidar_active / transient_excluded, stage 4 adds video_tier.
        # `n_ues`/`composition` are part of the join key -- equal by
        # construction -- and load_rows has coerced them to their declared
        # types while `ref` still holds strings, so comparing them would
        # compare int 8 against '8'. Skipped, not coerced: a join key that
        # could differ here would mean the lookup itself was wrong.
        skip = {"lidar_ues", "n_lidar_active", "transient_excluded",
                "video_tier", "scheduler", "seed", "n_ues", "composition"}
        cols = [c for c in r if c not in skip and c in ref]
        # NORMALISE BOTH SIDES: `r` came through load_rows (''-> None) and
        # `ref` is raw csv, so comparing them directly compares the
        # normalisation, not the runs.
        diff = [c for c in cols if r.get(c) != _norm_csv(ref.get(c))]
        compared += 1
        if diff:
            problems.append(
                f"{key}: {len(diff)} cols differ, e.g. " + ", ".join(
                    f"{c}={r.get(c)!r} vs {ref.get(c)!r}" for c in diff[:3]))
    return (not problems), [f"compared {compared} control rows"] + problems[:10]


def _windowed_value(w: list[dict], metric: str, window: str, subset: str,
                    **sel) -> list[float]:
    out = []
    for r in w:
        if r["metric"] != metric or r["window"] != window:
            continue
        if r["subset"] != subset:
            continue
        if any(r.get(k) != v for k, v in sel.items()):
            continue
        v = _numeric(r.get(WINDOWED_VALUE_KEY[metric]))
        if v is not None:
            out.append(v)
    return out


def c3_m02w_calibration(rows: list[dict], w: list[dict]) -> dict:
    """M02w at `full` vs panel M02, over the 16 CONTROL cells only.

    M02w is a restriction PLUS an accounting change: panel M02 tags lateness
    per drained chunk at drain time, M02w counts a whole message's delivered
    bytes when MessageCompletion.late is set. If the two diverge
    systematically, M02w is reported as a distinct estimator with its bias
    stated -- never as "M02 restricted to a window".
    """
    panel = {}
    for r in rows:
        if r.get("lidar_ues") != 0:
            continue
        key = (r.get("composition"), r.get("n_ues"), r["scheduler"], r["seed"])
        v = _numeric(r.get("M02"))
        if v is not None:
            panel[key] = v
    deltas, pairs = [], 0
    for row in w:
        if (row["metric"] != "M02w" or row["window"] != "full"
                or row["subset"] != "non_lidar" or row.get("lidar_ues") != 0):
            continue
        key = (row.get("composition"), row.get("n_ues"), row["scheduler"],
               row["seed"])
        if key in panel:
            v = _numeric(row.get("value"))
            if v is not None:
                deltas.append(v - panel[key])
                pairs += 1
    if not deltas:
        return {"pairs": 0}
    return {"pairs": pairs, "mean_delta": st.fmean(deltas),
            "median_delta": st.median(deltas), "min": min(deltas),
            "max": max(deltas),
            "stdev": st.pstdev(deltas) if len(deltas) > 1 else 0.0}


def c4_pre_window(w: list[dict]) -> dict:
    """The pre-window read. Both branches were named in advance (§16.6), and
    the branch that fires CHANGES WHAT E1-E4 SAY:

    *identical*  -> the contrast measures ACTIVATION.
    *different*  -> the lidar bearer's mere PROVISIONING already changes
                    scheduling, so every contrast measures
                    PROVISIONING + ACTIVATION, a compound treatment, and
                    E1-E4 are restated in that wording. It also triggers the
                    named follow-up: a third level, bearer provisioned but
                    never activated (a LidarActivation whose start_s exceeds
                    the horizon).
    """
    diffs: dict[str, list[float]] = {}
    for metric in ("M02w", "M08w"):
        base = {}
        for r in w:
            if (r["metric"] != metric or r["window"] != "pre"
                    or r["subset"] != "non_lidar"):
                continue
            key = (r.get("composition"), r.get("n_ues"), r["scheduler"],
                   r["seed"])
            v = _numeric(r.get(WINDOWED_VALUE_KEY[metric]))
            if v is None:
                continue
            if r.get("lidar_ues") == 0:
                base[key] = v
            else:
                diffs.setdefault(metric, []).append((key, v))
        paired = [v - base[k] for k, v in diffs.get(metric, []) if k in base]
        diffs[metric] = paired
    out = {}
    for metric, paired in diffs.items():
        if not paired:
            out[metric] = {"n": 0}
            continue
        ci = bootstrap_ci(paired, n_boot=2000, seed=0)
        out[metric] = {"n": len(paired), "mean": st.fmean(paired),
                       "ci_lo": ci["lo"], "ci_hi": ci["hi"],
                       "separated": not (ci["lo"] <= 0.0 <= ci["hi"])}
    out["branch"] = ("different"
                     if any(isinstance(v, dict) and v.get("separated")
                            for v in out.values())
                     else "identical")
    return out


# ------------------------------------------------------- contiguity, E1-E4

def _cell_winner(w: list[dict], metric: str, window: str, subset: str,
                 **sel) -> Optional[str]:
    means = {}
    for arm in ARMS:
        vals = _windowed_value(w, metric, window, subset, scheduler=arm, **sel)
        if vals:
            means[arm] = st.fmean(vals)
    if len(means) < 2:
        return None
    return max(means, key=lambda a: WINDOWED_DIRECTION[metric] * means[a])


def contiguity_per_composition(w: list[dict], metric: str,
                               window: str = "during_2") -> dict:
    """§16.1.2: `check_contiguity` walks each axis by INDEX +/-1, which
    invents adjacency on a categorical axis. `composition` is categorical,
    so contiguity is computed per composition over the ORDERED axes
    (`n_ues`, `lidar_ues`) only -- never across compositions.
    """
    axes = {"n_ues": STAGE5_GRID["n_ues"],
            "lidar_ues": STAGE5_GRID["lidar_ues"]}
    out = {}
    for comp in STAGE5_GRID["composition"]:
        winners: dict[tuple, str] = {}
        for n, lu in product(axes["n_ues"], axes["lidar_ues"]):
            win = _cell_winner(w, metric, window, "non_lidar",
                               composition=comp, n_ues=n, lidar_ues=lu)
            if win is not None:
                winners[(n, lu)] = win
        iso = check_contiguity(winners, axes)
        n_iso = sum(1 for v in iso.values() if v)
        out[comp] = {"scored": len(winners), "isolated": n_iso}
    return out


def e1_detectable(w: list[dict]) -> dict:
    """M02w over non_lidar in `during_2` at ugv_heavy N=32 lidar_ues=2,
    against its PAIRED control, per arm.

    Falsifier: no cell anywhere shows a windowed degradation outside the
    paired CI -- which is a real result bounding the campaign the other way,
    not a failed run.
    """
    out = {}
    for arm in ARMS:
        base = {}
        for r in w:
            if (r["metric"] != "M02w" or r["window"] != "during_2"
                    or r["subset"] != "non_lidar"
                    or r.get("composition") != "ugv_heavy"
                    or r.get("n_ues") != 32 or r["scheduler"] != arm):
                continue
            v = _numeric(r.get("value"))
            if v is None:
                continue
            if r.get("lidar_ues") == 0:
                base[r["seed"]] = v
            elif r.get("lidar_ues") == 2:
                base.setdefault("_on", {})[r["seed"]] = v
        on = base.pop("_on", {})
        paired = [on[s] - base[s] for s in sorted(set(on) & set(base))]
        if not paired:
            out[arm] = {"n": 0}
            continue
        ci = bootstrap_ci(paired, n_boot=2000, seed=0)
        out[arm] = {"n": len(paired), "mean_delta": st.fmean(paired),
                    "ci_lo": ci["lo"], "ci_hi": ci["hi"],
                    "worse_beyond_ci": ci["lo"] > 0.0}
    out["hit"] = any(v.get("worse_beyond_ci") for v in out.values()
                     if isinstance(v, dict))
    return out


def e2_breaking_n(w: list[dict]) -> dict:
    """Breaking N = smallest N at which a non-lidar GBR flow loses an M07w
    contract in-window that it HOLDS in the paired control.

    Scored against §15.4's stage-4 onset. Expectation: breaking N <= onset N
    wherever both are defined. The falsifier -- breaking N > onset N -- would
    mean a transient is EASIER to absorb than steady contention, inverting
    the intuition the excursion is built on. Registered as the expectation
    most likely to be wrong; if it misses it gets a per-slot direct-cause
    trace, not a narrative.
    """
    out = {}
    for comp in STAGE5_GRID["composition"]:
        breaking = None
        for n in STAGE5_GRID["n_ues"]:
            lost = False
            for arm in ARMS:
                ctrl = _windowed_value(w, "M07w", "during_2", "non_lidar",
                                       composition=comp, n_ues=n, lidar_ues=0,
                                       scheduler=arm)
                for lu in (1, 2):
                    on = _windowed_value(w, "M07w", "during_2", "non_lidar",
                                         composition=comp, n_ues=n,
                                         lidar_ues=lu, scheduler=arm)
                    if ctrl and on and st.fmean(on) < st.fmean(ctrl):
                        lost = True
            if lost:
                breaking = n
                break
        onset = STAGE4_ONSET_N[comp]
        out[comp] = {
            "breaking_n": breaking, "stage4_onset_n": onset,
            "holds": (breaking is not None and onset is not None
                      and breaking <= onset),
        }
    return out


def e2_breaking_n_paired_ci(w: list[dict]) -> dict:
    """E2's breaking N under a PAIRED BOOTSTRAP CI -- a POST-HOC CORRECTION
    to the criterion above, added after the first real run, and kept
    separate from it rather than replacing it.

    WHY. `e2_breaking_n` scores a break as `mean(on) < mean(control)` with
    no interval at all. On real data that fires on noise: it declared
    ugv_heavy "breaking" at N=4 on TwoTier going 2.90 -> 2.80 contracts --
    one seed losing one contract -- while the same metric at N=32 collapses
    6.70 -> 1.60. A "breaking N = 4, far below stage 4's onset of 16" is the
    headline that criterion produces, and it is an artifact of the criterion,
    not a property of the fleet.

    E1 was registered WITH a paired bootstrap CI and E2 was not; that
    inconsistency is the defect. This applies E1's own test to E2: a
    composition breaks at the smallest N where some arm's paired per-seed
    delta has a bootstrap CI entirely below zero.

    THE PRE-REGISTERED CRITERION'S OUTPUT IS STILL REPORTED. Replacing a
    registered criterion after seeing which answer it gives is exactly what
    pre-registration exists to prevent, so both are printed and the
    correction is labelled as post-hoc wherever it is quoted.
    """
    out = {}
    for comp in STAGE5_GRID["composition"]:
        breaking, detail = None, {}
        for n in STAGE5_GRID["n_ues"]:
            for arm in ARMS:
                ctrl = {r["seed"]: r["met"] for r in w
                        if r["metric"] == "M07w" and r["window"] == "during_2"
                        and r["subset"] == "non_lidar"
                        and r.get("composition") == comp and r.get("n_ues") == n
                        and r.get("lidar_ues") == 0 and r["scheduler"] == arm
                        and r.get("met") is not None}
                on = {r["seed"]: r["met"] for r in w
                      if r["metric"] == "M07w" and r["window"] == "during_2"
                      and r["subset"] == "non_lidar"
                      and r.get("composition") == comp and r.get("n_ues") == n
                      and r.get("lidar_ues") == 2 and r["scheduler"] == arm
                      and r.get("met") is not None}
                shared = sorted(set(ctrl) & set(on))
                if not shared:
                    continue
                d = [on[k] - ctrl[k] for k in shared]
                ci = bootstrap_ci(d, n_boot=4000, seed=0)
                if ci["hi"] < 0:
                    detail.setdefault(n, {})[arm] = {
                        "mean_delta": st.fmean(d),
                        "ci_lo": ci["lo"], "ci_hi": ci["hi"]}
                    if breaking is None:
                        breaking = n
        onset = STAGE4_ONSET_N[comp]
        out[comp] = {
            "breaking_n": breaking, "stage4_onset_n": onset,
            "holds": (breaking is not None and onset is not None
                      and breaking <= onset),
            "consistent_both_undefined": breaking is None and onset is None,
            "detail": detail,
        }
    return out


def e3_h6_split(w: list[dict], comp: str, n: int) -> dict:
    """Does H6's construction extend from steady overload to a transient?
    Expect the split: one QoS-aware arm holds M07w while PF holds M08w.

    NO PREDICTION IS REGISTERED ABOUT WHICH ARM -- §0.1.1 recorded the
    winner flipping between stage 2 and stage 4, so only the SPLIT is
    predicted. Both metrics are returned together; §0.1's rule is that
    neither may be quoted alone.
    """
    m07 = _cell_winner(w, "M07w", "during_2", "non_lidar",
                       composition=comp, n_ues=n, lidar_ues=2)
    m08 = _cell_winner(w, "M08w", "during_2", "non_lidar",
                       composition=comp, n_ues=n, lidar_ues=2)
    return {"m07w_winner": m07, "m08w_winner": m08,
            "split": (m07 is not None and m08 is not None and m07 != m08)}


def e4_direction_vs_pdb(w: list[dict], comp: str, n: int) -> dict:
    """Weak, and explicitly NOT §15.5's experiment.

    The UGV e-stop has the tightest PDB in the panel (5 ms) but is DL and
    40 bytes at 0.2 Hz; the lidar is UL and 150 KB every 100 ms. Expectation:
    e-stop is not the first flow to break.

    THIS GRID CANNOT TEST §15.5's HYPOTHESIS -- it varies flow count, GBR
    fraction, UL share and tight-PDB density together. §15.5's discriminating
    experiment (identical flow counts and GBR ratios, tight-PDB flows
    co-located vs spread) remains UNRUN, and E4 must not be reported as
    bearing on it.
    """
    out = {}
    for subset in ("estop", "tight_pdb", "non_lidar"):
        deltas = []
        for arm in ARMS:
            ctrl = _windowed_value(w, "M02w", "during_2", subset,
                                   composition=comp, n_ues=n, lidar_ues=0,
                                   scheduler=arm)
            on = _windowed_value(w, "M02w", "during_2", subset,
                                 composition=comp, n_ues=n, lidar_ues=2,
                                 scheduler=arm)
            if ctrl and on:
                deltas.append(st.fmean(on) - st.fmean(ctrl))
        out[subset] = st.fmean(deltas) if deltas else None
    ranked = [k for k, v in sorted(
        ((k, v) for k, v in out.items() if v is not None),
        key=lambda kv: -kv[1])]
    return {"m02w_degradation": out, "worst_first": ranked,
            "estop_broke_first": bool(ranked) and ranked[0] == "estop"}


# ------------------------------------------------------------------ main

def main(out_dir: Path) -> int:
    rows = load_rows(out_dir / "stages5_rows.csv")
    w = load_windowed(out_dir / "online_rows.jsonl")

    print("=" * 72)
    print("C1 -- NULL-LIDAR IDENTITY (STOP CONDITION, read first)")
    ok, notes = c1_null_identity(rows)
    for line in notes:
        print("   ", line)
    if not ok:
        print("\nC1 FAILED. A difference with no lidar can only come from the")
        print("axis plumbing. NOTHING ELSE IS READ until this is explained.")
        return 1
    print("    PASS -- the 4 null cells are bit-identical to their controls")

    print("\nC2 -- CELL CENSUS (recomputed from build_fleet)")
    ok2, census = c2_census()
    print(f"    {census}  expected {STAGE5_EXPECTED_CENSUS}")
    print(f"    {'PASS' if ok2 else 'FAIL'}")

    print("\nC5 -- CONTROLS vs STAGE 4 (bit-identity, 16 cells)")
    ok5, notes5 = c5_stage4_identity(
        rows, out_dir.parent / "stage4" / "stages4_rows.csv")
    for line in notes5:
        print("   ", line)
    print(f"    {'PASS' if ok5 else 'FAIL'}")

    print("\nC3 -- M02w CALIBRATION vs PANEL M02 (`full` window, controls)")
    cal = c3_m02w_calibration(rows, w)
    print(f"    {cal}")
    print("    Read as a DISTRIBUTION: M02w is a restriction PLUS an")
    print("    accounting change, so a systematic delta means it is a")
    print("    distinct estimator, not 'M02 restricted to a window'.")

    print("\nC4 -- PRE-WINDOW READ (names the branch BEFORE E1-E4 are read)")
    c4 = c4_pre_window(w)
    for k, v in c4.items():
        if k != "branch":
            print(f"    {k}: {v}")
    print(f"    BRANCH = {c4['branch'].upper()}")
    if c4["branch"] == "different":
        print("    => every contrast below measures PROVISIONING + ACTIVATION.")
        print("       Restate E1-E4 as 'adding a provisioned-and-activated")
        print("       lidar bearer breaks flows at N=x'. Follow-up needed: a")
        print("       third level, bearer provisioned but never activated.")
    else:
        print("    => the perturbation is localised; E1-E4 read as written.")

    print("\nCONTIGUITY (per composition, over n_ues x lidar_ues ONLY)")
    for metric in ("M07w", "M08w", "M02w"):
        print(f"  {metric}: {contiguity_per_composition(w, metric)}")
    print("    Stage-4 prior: M07 was cleanest, M08 noisier, M02 noisiest.")
    print("    M07w carries the boundary claim; M02w describes it.")

    print("\nE1 -- IS THE ACTIVATION DETECTABLE AT ALL?")
    e1 = e1_detectable(w)
    for k, v in e1.items():
        print(f"    {k}: {v}")
    print(f"    {'HIT' if e1.get('hit') else 'MISS'}")

    print("\nE2 -- BREAKING N vs STAGE-4 ONSET")
    e2 = e2_breaking_n(w)
    for comp, v in e2.items():
        print(f"    {comp:<14} {v}")
    print("    A MISS here is TRACED to a confirmed mechanism (a per-slot")
    print("    trace of the first divergent grant), not absorbed.")

    print("\nE2 (POST-HOC CORRECTION) -- paired bootstrap CI, not a bare mean")
    e2ci = e2_breaking_n_paired_ci(w)
    for comp, v in e2ci.items():
        print(f"    {comp:<14} breaking_n={v['breaking_n']} "
              f"onset={v['stage4_onset_n']} holds={v['holds']} "
              f"both_undefined={v['consistent_both_undefined']}")
    print("    The registered criterion has NO interval and fires on noise")
    print("    (ugv_heavy 'breaks' at N=4 on 2.90 -> 2.80 contracts). Both")
    print("    are printed; the correction is labelled post-hoc wherever")
    print("    it is quoted.")

    print("\nE3 -- H6 SPLIT (M07w and M08w quoted TOGETHER, always)")
    for comp, v in e2.items():
        n = v["breaking_n"]
        if n is not None:
            print(f"    {comp:<14} N={n}: {e3_h6_split(w, comp, n)}")

    print("\nE4 -- DIRECTION vs PDB TIGHTNESS (weak; NOT §15.5's experiment)")
    for comp, v in e2.items():
        n = v["breaking_n"]
        if n is not None:
            print(f"    {comp:<14} N={n}: {e4_direction_vs_pdb(w, comp, n)}")
    print("    §15.5's discriminating experiment remains UNRUN. E4 is")
    print("    suggestive at best and does not bear on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1
                       else "sweeps/wp9/stage5")))
