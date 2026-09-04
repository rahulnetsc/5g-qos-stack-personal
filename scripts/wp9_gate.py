"""WP9's stage-1 -> stage-2 go/no-go rule, as code (`docs/wp9-plan.md` §6.4,
build item B5).

**Why this is a module and not a paragraph.** Stage 1 is exploratory and
stage 2 is confirmatory, and the only thing keeping that distinction honest
is that the promotion rule cannot be re-cut after the results are visible.
So the rule is committed *before* stage 1 runs, with tests, and running it is
a single call whose output is recorded verbatim. A sixth primary metric, a
relaxed threshold, or an extended axis list would have to appear as a diff
against this file in its own commit -- which is the point.

The rule, restated exactly as pre-registered:

  1. Five primary metrics, declared in advance: M07, M08, M01(p98), M02, M09.
     All 19 panel metrics are still scored and written for every run; these
     five only gate promotion.
  2. An axis qualifies if, at >= one level, on >= one primary metric, all of:
       (i)   the cell passes is_informative (not zero-loss on both arms);
       (ii)  paired within-seed effect size |mean d| / sd(d) >= 1.0;
       (iii) bootstrap_ci(d)'s 95% interval excludes 0.
  3. At most three axes carry into stage 2 (the core plane's N x load, plus
     at most one excursion axis). Dropped axes are recorded by name and
     score, never silently omitted.
  4. No claim is made from stage 1 -- selection only.
  5. Stage 2 requires contiguity (`regime_sweep.check_contiguity`), which
     stage 1's one-axis-at-a-time excursions structurally cannot supply.
  6. Stage 2 must confirm on the same primary metric that selected the axis.
  7. Zero qualifying axes is the reported negative result. The rule is not
     re-cut to manufacture a qualifier.

This module implements 1-3 and 6's bookkeeping. 4, 5 and 7 are properties of
how the result is *used*, enforced by `scripts/wp9_sweep.py` and by the
write-up, not computable here.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

from regime_sweep import bootstrap_ci, regime_selection_excluded

# The five primary metrics, as the flattened column names `regime_sweep.
# sweep()` actually emits (a dict-valued MetricResult is flattened to
# "<id>.<field>"; a scalar one stays bare). Declared as columns rather than
# metric ids so there is no run-time ambiguity about which field of a
# multi-field metric gates promotion.
PRIMARY_METRIC_COLUMNS: tuple[str, ...] = (
    "M07.met",        # GBR contracts met            -> G10
    "M08.fraction",   # worst-flow GFBR fraction     -> G8/G10
    "M01.p98",        # worst-flow p98 latency       -> G1
    "M02",            # PDB violation rate           -> G1/G5/G12
    "M09.worst",      # worst per-second Jain window -> G8
)

# The loss column the is_informative gate reads. M02 by definition
# (`docs/wp9-plan.md` §6.2).
LOSS_COLUMN = "M02"

EFFECT_SIZE_THRESHOLD = 1.0
MAX_AXES_INTO_STAGE_2 = 3
# The core plane always carries into stage 2; only ONE excursion axis may
# join it, so the factorial stays inside the 24h ceiling.
CORE_PLANE_AXES: tuple[str, ...] = ("n_ues", "load_mult")


@dataclass
class PairResult:
    """One (cell, metric, arm-pair) evaluation."""
    axis: str
    level: Any
    metric: str
    arm_a: str
    arm_b: str
    n_seeds: int
    mean_delta: float
    sd_delta: float
    effect_size: float
    ci_lo: float
    ci_hi: float
    informative: bool

    @property
    def ci_excludes_zero(self) -> bool:
        return (self.ci_lo > 0.0) or (self.ci_hi < 0.0)

    @property
    def qualifies(self) -> bool:
        return (
            self.informative
            and self.effect_size >= EFFECT_SIZE_THRESHOLD
            and self.ci_excludes_zero
        )


@dataclass
class AxisVerdict:
    axis: str
    qualifies: bool
    best: Optional[PairResult] = None
    all_results: list[PairResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Ranking key for rule 3: the largest qualifying effect size, or the
        largest observed one if nothing qualified (so a near-miss is still
        reported with a number rather than a bare 'no')."""
        if self.best is not None:
            return self.best.effect_size
        if not self.all_results:
            return 0.0
        return max(r.effect_size for r in self.all_results)


def _effect_size(deltas: list[float]) -> tuple[float, float, float]:
    """(mean, sd, |mean|/sd) over paired within-seed differences.

    sd is the sample standard deviation (n-1). A zero-variance set of
    non-zero deltas is a perfectly consistent difference, so it returns
    +inf rather than raising -- the alternative (dropping the cell) would
    silently discard the strongest possible evidence.
    """
    if len(deltas) < 2:
        return (float("nan"), float("nan"), 0.0)
    mean = statistics.fmean(deltas)
    sd = statistics.stdev(deltas)
    if sd == 0.0:
        return (mean, 0.0, float("inf") if mean != 0.0 else 0.0)
    return (mean, sd, abs(mean) / sd)


def _numeric(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def evaluate_cell(
    rows: list[dict[str, Any]],
    axis: str,
    level: Any,
    arm_a: str,
    arm_b: str,
    metric: str,
) -> Optional[PairResult]:
    """Evaluate one (axis level, arm pair, metric) against the gate.

    `rows` are `regime_sweep.sweep()` output already filtered to the cell.
    Seeds are paired: a seed contributes a delta only if BOTH arms produced
    a numeric value for it, so an arm whose metric went `pending` at one seed
    drops that seed rather than being compared against a missing value.
    """
    by_seed_a = {r["seed"]: r for r in rows if r["scheduler"] == arm_a}
    by_seed_b = {r["seed"]: r for r in rows if r["scheduler"] == arm_b}
    deltas: list[float] = []
    loss_a: list[float] = []
    loss_b: list[float] = []
    for seed in sorted(set(by_seed_a) & set(by_seed_b)):
        va = _numeric(by_seed_a[seed].get(metric))
        vb = _numeric(by_seed_b[seed].get(metric))
        if va is None or vb is None:
            continue
        deltas.append(va - vb)
        la = _numeric(by_seed_a[seed].get(LOSS_COLUMN))
        lb = _numeric(by_seed_b[seed].get(LOSS_COLUMN))
        if la is not None:
            loss_a.append(la)
        if lb is not None:
            loss_b.append(lb)
    if len(deltas) < 2:
        return None

    mean, sd, es = _effect_size(deltas)
    ci = bootstrap_ci(deltas)
    # is_informative is evaluated on the cell's MEAN loss per arm: a cell is
    # excluded only if both arms are at zero loss across the whole cell, not
    # if one seed happened to be.
    informative = not regime_selection_excluded(
        statistics.fmean(loss_a) if loss_a else None,
        statistics.fmean(loss_b) if loss_b else None,
    )
    return PairResult(
        axis=axis, level=level, metric=metric, arm_a=arm_a, arm_b=arm_b,
        n_seeds=len(deltas), mean_delta=mean, sd_delta=sd, effect_size=es,
        ci_lo=ci["lo"], ci_hi=ci["hi"], informative=informative,
    )


def carries_axis(row: dict[str, Any], axis: str) -> bool:
    """Whether this row's cell actually varies `axis`.

    `sweep()` writes only the axes its own cell varied, so a row from a
    different cell simply has no key for `axis` -- or, once round-tripped
    through CSV, an empty string. Membership therefore has to be tested
    explicitly.

    THE BUG THIS EXISTS TO KILL: `evaluate_axis` used to select cells with
    `r.get(axis) == level`, which conflates "this axis at its base level"
    with "this row does not carry this axis at all" whenever the base level
    is None. `pdb_ms` and `inf_scenario` both have a None base, so their
    cells selected **1,710 of stage 1's 1,770 rows, including all 1,260
    core-plane rows** -- and `pdb_ms` was promoted into stage 2 on that
    basis, over axes that had qualified legitimately.
    """
    v = row.get(axis, None)
    return v is not None and v != ""


def evaluate_axis(
    rows: list[dict[str, Any]],
    axis: str,
    levels: list[Any],
    arm_pairs: list[tuple[str, str]],
    metrics: tuple[str, ...] = PRIMARY_METRIC_COLUMNS,
) -> AxisVerdict:
    """Rule 2: the axis qualifies if ANY (level, metric, arm-pair) does.

    A row belongs to this axis's cell at `level` only if it CARRIES the
    axis (see carries_axis) and matches the level -- never by value
    equality alone.
    """
    results: list[PairResult] = []
    for level in levels:
        cell_rows = [r for r in rows
                     if carries_axis(r, axis) and r.get(axis) == level]
        if not cell_rows:
            continue
        for arm_a, arm_b in arm_pairs:
            for metric in metrics:
                res = evaluate_cell(cell_rows, axis, level, arm_a, arm_b, metric)
                if res is not None:
                    results.append(res)
    qualifying = [r for r in results if r.qualifies]
    best = max(qualifying, key=lambda r: r.effect_size) if qualifying else None
    return AxisVerdict(
        axis=axis, qualifies=best is not None, best=best, all_results=results,
    )


def select_for_stage_2(verdicts: list[AxisVerdict]) -> dict[str, Any]:
    """Rule 3, and rule 7's honesty requirement.

    The core plane always carries. Among the qualifying *excursion* axes, at
    most one joins it -- ranked by effect size -- and every axis that did not
    make it is returned by name and score. Nothing is silently omitted, and
    the function has no argument that could relax the threshold.
    """
    core = [v for v in verdicts if v.axis in CORE_PLANE_AXES]
    excursions = [v for v in verdicts if v.axis not in CORE_PLANE_AXES]
    qualifying = sorted(
        [v for v in excursions if v.qualifies], key=lambda v: -v.score
    )
    promoted = [v.axis for v in core] + [v.axis for v in qualifying[:1]]
    # EVERY excursion that is not promoted, with no slice. The slice that
    # used to stand here -- `excursions[len(qualifying[:1]):]` -- was taken on
    # the UNSORTED list by the COUNT of promoted axes, so it discarded
    # `excursions[0]` whether or not that element was the promoted one. The
    # `not in promoted` filter below is what does the actual exclusion, and
    # it is sufficient on its own.
    #
    # IT HAPPENED, in both committed verdicts. `gate_verdict.txt` and
    # `gate_verdict_corrected.txt` each list 8 dropped axes where the
    # accounting requires 9, and the missing one in both is `min_rb` --
    # score 152.579, among the highest non-`inf` in the grid, and the axis
    # `docs/wp9-regime-map.md` §0.3 records as dropped by the stage-2 cap.
    # The decision was real; the committed record of it was not complete.
    dropped = [
        {"axis": v.axis, "qualifies": v.qualifies, "score": v.score,
         "reason": ("not promoted: only one excursion axis fits the stage-2 "
                    "budget" if v.qualifies else "did not pass the gate")}
        for v in excursions if v.axis not in promoted
    ]
    # THE ACCOUNTING, ASSERTED RATHER THAN DESCRIBED. The docstring's claim
    # that nothing is silently omitted is now a check that fails loudly if it
    # stops being true -- which is the only form of that claim worth making.
    accounted = set(promoted[:MAX_AXES_INTO_STAGE_2]) | {d["axis"] for d in dropped}
    missing = [v.axis for v in verdicts if v.axis not in accounted]
    if missing:
        raise AssertionError(
            f"axes neither promoted nor dropped: {missing}. Every axis must "
            f"appear in exactly one of the two lists, or the verdict is not "
            f"a record of the decision it claims to be.")
    return {
        "promoted": promoted[:MAX_AXES_INTO_STAGE_2],
        "qualifying_excursions": [
            {"axis": v.axis, "score": v.score,
             "metric": v.best.metric if v.best else None,
             "level": v.best.level if v.best else None,
             "arms": f"{v.best.arm_a}-{v.best.arm_b}" if v.best else None}
            for v in qualifying
        ],
        "dropped": dropped,
        "zero_qualified": len(qualifying) == 0,
    }


def format_verdicts(verdicts: list[AxisVerdict], selection: dict) -> str:
    """The verbatim record. Printed and committed as-is."""
    out = ["WP9 stage-1 gate -- verdicts (rule as committed, pre-stage-1)", ""]
    for v in sorted(verdicts, key=lambda v: -v.score):
        mark = "QUALIFIES" if v.qualifies else "  --     "
        out.append(f"{mark}  {v.axis:<18} score={v.score:8.3f}")
        if v.best is not None:
            b = v.best
            out.append(
                f"            best: {b.metric} at {b.axis}={b.level} "
                f"({b.arm_a} vs {b.arm_b}) mean_d={b.mean_delta:.4g} "
                f"sd={b.sd_delta:.4g} es={b.effect_size:.3f} "
                f"CI=[{b.ci_lo:.4g}, {b.ci_hi:.4g}] n={b.n_seeds}"
            )
    out.append("")
    out.append(f"promoted to stage 2: {selection['promoted']}")
    if selection["zero_qualified"]:
        out.append(
            "ZERO excursion axes qualified. Per rule 7 this is D4-4's "
            "negative result and is reported as the finding -- the rule is "
            "NOT re-cut to manufacture a qualifier."
        )
    for d in selection["dropped"]:
        out.append(f"dropped: {d['axis']:<18} score={d['score']:8.3f}  {d['reason']}")
    return "\n".join(out)
