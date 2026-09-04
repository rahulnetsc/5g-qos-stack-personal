"""`Scorecard.score(only=...)` and the mapping it rests on.

WHY THIS FILE EXISTS AT ALL. `docs/wp9-g11-plan.md` §4.1 observed that 12 of
the 13 scoring passes per record discard M09 entirely, and flagged the
premise underneath -- that M09's value does not depend on any variation
parameter -- as *"an argument about existing code, not a measurement"*,
subject to CLAUDE.md's third-kind rule. It named the discharge explicitly:
the commit that acts on it verifies by RUNNING BOTH WAYS AND DIFFING rather
than porting the claim on the strength of it being written down.

So this file does two independent things, because either alone is weaker
than it looks:

  * `test_variation_affects_matches_the_source` DERIVES the mapping from
    `score()`'s own AST and requires the constant to equal it. This is the
    structural half: it answers "which metrics READ this parameter", which
    no amount of running can establish, since a metric can read a parameter
    and happen not to move on the record in front of you.
  * `test_dispatched_pass_equals_full_pass_*` runs a REAL record both ways at
    every registered variation value and requires bit-identity. This is the
    empirical half: it answers "does the substitution actually reproduce the
    full pass", which the AST cannot establish, since a metric could reach a
    parameter through a path the source scan does not model.

A test that only did the second could pass on a record where the omitted
metric is constant for unrelated reasons -- the fixture-built-precondition
failure CLAUDE.md records. A test that only did the first would be checking
that a comment matches a line of code.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard, load_panel
from sim.baselines.pf import ProportionalFair

# The variation grid the sweep actually runs (scripts/wp9_sweep.py's
# _SCORING_VARIATIONS). Restated here rather than imported because
# sim/ must not import from scripts/ -- and pinned by
# test_variation_grid_is_the_one_the_sweep_runs below, which does the import
# from the test side where it is allowed.
VARIATIONS = {
    "survival_miss_n": (2, 3, 5),
    "t_live_s": (1.0, 2.0, 4.0),
    "gbr_contract_fraction": (0.90, 0.95, 0.99),
    "slo_green_dwell_s": (0.5, 1.0, 2.0),
}


def _cfg_reads_by_metric() -> dict[str, set[str]]:
    """Parse `Scorecard.score` and return {metric id: cfg keys its assignment
    reads}. Structural, so it cannot go stale the way a comment can."""
    src = textwrap.dedent(inspect.getsource(Scorecard.score))
    tree = ast.parse(src)
    reads: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not (isinstance(tgt, ast.Subscript)
                and isinstance(tgt.value, ast.Name) and tgt.value.id == "out"
                and isinstance(tgt.slice, ast.Constant)):
            continue
        keys = {
            sub.slice.value
            for sub in ast.walk(node.value)
            if isinstance(sub, ast.Subscript)
            and isinstance(sub.value, ast.Name) and sub.value.id == "cfg"
            and isinstance(sub.slice, ast.Constant)
        }
        reads[tgt.slice.value] = keys
    return reads


@pytest.fixture(scope="module")
def record() -> RunRecord:
    """A real record, not a fixture-built one. The precondition under test is
    that omitted metrics are genuinely unaffected, and a hand-made record can
    satisfy that by being too simple to distinguish anything."""
    sc = sweep_scenario(seed=1, n_ues=4, horizon_slots=4000, load_mult=1.0)
    summary = run(sc, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=True)
    return RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=1,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def test_variation_affects_matches_the_source():
    """THE STRUCTURAL HALF. Derived from score()'s AST, not from memory."""
    reads = _cfg_reads_by_metric()
    derived: dict[str, set[str]] = {}
    for metric_id, keys in reads.items():
        for key in keys:
            derived.setdefault(key, set()).add(metric_id)
    declared = {k: set(v) for k, v in Scorecard.VARIATION_AFFECTS.items()}
    assert derived == declared, (
        f"VARIATION_AFFECTS disagrees with score()'s body.\n"
        f"  derived from source: {derived}\n"
        f"  declared:            {declared}")


def test_every_variation_parameter_is_registered():
    """A parameter the sweep varies but the mapping does not know about would
    be dispatched as affecting NOTHING -- the omission fails silently and in
    the direction of passing, so it is asserted rather than assumed."""
    assert set(VARIATIONS) == set(Scorecard.VARIATION_AFFECTS)


def test_variation_grid_is_the_one_the_sweep_runs():
    """The grid above is restated from scripts/wp9_sweep.py, and a restated
    thing needs a check against the thing it restates (CLAUDE.md)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import wp9_sweep
    assert dict(wp9_sweep._SCORING_VARIATIONS) == VARIATIONS


@pytest.mark.parametrize("param", sorted(VARIATIONS))
def test_dispatched_pass_equals_full_pass(record, param):
    """THE EMPIRICAL HALF, run both ways and diffed, at every registered value
    and on both populations.

    The dispatched form is what the sweep does: compute the affected metrics
    under the varied parameter, and take every other metric from a single
    default pass. If `VARIATION_AFFECTS` under-claims for `param`, some
    metric will differ here.
    """
    card = Scorecard()
    affected = Scorecard.VARIATION_AFFECTS[param]
    for population in (Population.all_flows(), Population.protected_fleet()):
        base = card.score(record, population=population)
        for value in VARIATIONS[param]:
            full = card.score(record, population=population, **{param: value})
            part = card.score(record, population=population,
                              only=affected, **{param: value})
            assert set(part) == set(affected)
            merged = {**base, **part}
            assert set(merged) == set(full)
            for mid in full:
                assert merged[mid].value == full[mid].value, (
                    f"{param}={value}, population={population.name}: {mid} "
                    f"differs between the dispatched and full pass -- "
                    f"VARIATION_AFFECTS[{param!r}] does not contain it")
                assert merged[mid].status == full[mid].status


def test_unrequested_metric_is_absent_not_none(record):
    """A metric that was not computed must raise a KeyError on access, never
    read as a legitimate None. `config/metric_panel.yml`'s own rule is that a
    pending metric emits a row with value=None and a reason, so a
    None-because-not-computed would be indistinguishable from a real pending
    result -- the omitted-vs-forgotten confusion the panel exists to prevent."""
    part = Scorecard().score(record, population=Population.all_flows(),
                             only={"M07"})
    assert set(part) == {"M07"}
    with pytest.raises(KeyError):
        part["M09"]


def test_only_none_still_scores_the_whole_panel(record):
    """The default path is unchanged -- every existing caller passes no
    `only` and must keep getting every metric."""
    full = Scorecard().score(record, population=Population.all_flows())
    # DERIVED from the panel, not restated. M13 is a cross-run metric and M16
    # needs a named flow pair, so neither is part of the automatic per-run
    # scan -- score()'s own comments say so at the point they are skipped.
    expected = {m["id"] for m in load_panel()["metrics"]} - {"M13", "M16"}
    assert set(full) == expected
    assert "M09" in full and "M22" in full


def test_sweep_online_rows_are_unchanged_by_the_dispatch(record):
    """THE CALL SITE, both ways, diffed -- not just the primitive.

    The tests above establish that a dispatched pass reproduces a full one.
    This one establishes that `wp9_sweep._online_rows_for`, which is what
    actually writes `online_rows.jsonl`, emits the SAME ROWS as the 26-pass
    version it replaces -- reference implementation inline below, so the
    comparison does not depend on git history being available.

    CLAUDE.md's guard-test rule is why both exist: a test proves the helper
    you fixed stays fixed; it does not prove the pipeline that calls it is
    clean. Here the pipeline is one function, so it can be pinned directly.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import wp9_sweep

    axis_values = {"n_ues": 4, "load_mult": 1.0}
    card = Scorecard()
    got = wp9_sweep._online_rows_for(card, record, axis_values)

    # The pre-dispatch implementation, verbatim in shape: a full score() per
    # population per variation value, 24 passes plus M16.
    tag = {**axis_values, "scheduler": record.scheduler_name,
           "seed": record.seed}
    want = []
    ref = Scorecard()
    try:
        m16 = ref.correlate_flows(record, (1, 1), (1, 82))
        want.append({"metric": "M16", **tag,
                     "status": m16.status, "value": m16.value})
    except (KeyError, StopIteration):
        pass
    for name, values in wp9_sweep._SCORING_VARIATIONS:
        for v in values:
            scores = ref.score(record, population=Population.all_flows(),
                               **{name: v})
            scores_prot = ref.score(
                record, population=Population.protected_fleet(), **{name: v})
            for mid in ("M03", "M04", "M07", "M08", "M14", "M19"):
                for src, pop_tag in ((scores, "all_flows"),
                                     (scores_prot, "protected_fleet")):
                    r = src.get(mid)
                    if r is None:
                        continue
                    want.append({"metric": mid, "variation": name,
                                 "variation_value": v, **tag,
                                 "population": r.population or pop_tag,
                                 "status": r.status, "value": r.value})

    assert len(got) == len(want)
    assert got == want


def test_the_variation_sweep_cannot_move_m08_or_m14(record):
    """A FINDING, pinned so it cannot be rediscovered as a surprise.

    `_online_rows_for` harvests six metric ids across twelve variations, but
    only four of them read any variation parameter. M08 and M14 read none:
    M08 is a bare worst-flow minimum and M14's threshold is
    `pdb_ms + survival_time_ms`, which its own docstring says is used
    "instead of T_live-derived ones". So every M08 and M14 row in
    `online_rows.jsonl` is the same number twelve times over, and
    `docs/wp9-regime-map.md`'s G3 row -- "M03/M14 at t_live_s in {1,2,4},
    reported as a function of it" -- is true of M03 and not of M14.

    This is not caused by the dispatch and is not fixed by it; the dispatch
    is what made it visible, and the test is here so the next reader meets it
    as a recorded property rather than as an anomaly in a results table.
    """
    card = Scorecard()
    for mid in ("M08", "M14"):
        assert not any(mid in affected
                       for affected in Scorecard.VARIATION_AFFECTS.values())
    seen = {}
    for value in VARIATIONS["t_live_s"]:
        r = card.score(record, population=Population.protected_fleet(),
                       t_live_s=value)
        seen[value] = (r["M14"].value, r["M03"].value)
    m14_values = {repr(v[0]) for v in seen.values()}
    m03_values = {repr(v[1]) for v in seen.values()}
    assert len(m14_values) == 1, "M14 moved with t_live_s -- the finding above is stale"
    assert len(m03_values) > 1, (
        "M03 did NOT move with t_live_s on this record, so this test cannot "
        "distinguish 'M14 is unaffected' from 'nothing moves here' -- the "
        "dynamic-range check the journal's third form rule requires")
