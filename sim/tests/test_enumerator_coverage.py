"""STANDING RULE: any sweep that reports zero must assert what it reached.

The class, stated once (`docs/defects-status-2026-09-06.md` §3): **an
enumerator that defines its domain by something it cannot itself construct.**
It reports "zero" over the set it CAN reach, and the reader hears "zero" over
the set they care about.

**It has cost two wrong answers on the same question.** The flow-key sweep
enumerated NULLARY builders twice and concluded "no scenario puts a (ue, qfi)
pair in both directions" -- while `build_g12_scenario`, a PARAMETERISED
builder, did exactly that at four grid points, and a published result was
computed on a shared queue because of it (defects log #28, #30).

This file makes coverage-assertion a REQUIREMENT rather than a property of
the two enumerators that happen to have been fixed. Each entry names the
enumerator, the set it is read as covering, and the mechanism by which it
declares what it actually reached. **Adding an enumerator without a coverage
mechanism fails here.**
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

#: enumerator -> (file, what a reader takes "zero" to mean, coverage mechanism)
ENUMERATORS = {
    "flow-key collision sweep": (
        "sim/tests/test_flow_key_collision_sweep.py",
        "no scenario in the repo collides",
        "test_the_sweep_COVERS_every_builder_rather_than_the_easy_ones"),
    "published-figure coverage": (
        "scripts/figure_coverage.py",
        "our published figures are verified",
        "SCANNED"),
    "parallel audit": (
        "scripts/parallel_audit.py",
        "no runner ships serial",
        "ALLOW_SERIAL"),
    "code-state scope": (
        "scripts/code_state.py",
        "an artefact matches current code",
        "n_scoped_files"),
    "regression corpus": (
        "scripts/regression_corpus.py",
        "the simulator has not drifted",
        "_cases"),
}


@pytest.mark.parametrize("name", sorted(ENUMERATORS))
def test_every_enumerator_declares_what_it_reached(name):
    path, _read_as, mechanism = ENUMERATORS[name]
    p = REPO / path
    assert p.exists(), f"{name}: {path} is gone -- update this registry"
    src = p.read_text()
    assert mechanism in src, (
        f"{name} ({path}) has no coverage mechanism named {mechanism!r}. "
        f"A sweep that reports zero without saying what it reached is the "
        f"shape that produced defects #28 and #30 -- twice, on the same "
        f"question.")


def test_the_registry_itself_is_not_the_blind_spot():
    """The registry is an enumerator too, so it needs the same discipline.

    The criterion is STRUCTURAL, not a docstring keyword: does the script
    enumerate something it did not itself define -- i.e. does it WALK THE
    REPO (`glob`, `rglob`, `iterdir`, `walk`, `pkgutil`)?

    That is the line between the two kinds. A **campaign runner** sweeps a
    grid it declares in its own source; its domain IS its definition, so
    there is no gap between what it reaches and what it claims. An
    **enumerator** makes a claim about a set the repository defines -- every
    scenario, every script, every published figure -- and can therefore
    reach less than it claims. Only the second kind can produce a "zero"
    that means something narrower than the reader thinks.

    A docstring keyword was tried first and flagged 22 campaign runners,
    which is the same over-match in the opposite direction.
    """
    EXEMPT = {
        "verify_claims.py": "the enumerator being INVERTED by figure_coverage.py; "
                            "its own domain (registered claims) is the defect",
        "regime_map_rollup.py": "derives counts from one document it names",
        "verify_parallel.py": "compares two runs, enumerates nothing",
        "trace_read.py": "reads one artefact named on the command line",
        "rerun_diff.py": "compares a named pair list, and reports PAIRING",
        # These two glob for PROCESSES and LEDGER FILES, not for a set they
        # make a claim about: check_for_orphans scans /proc, and the ledger
        # reader globs its own bank. Neither reports a "zero" about the
        # repository, which is the shape this registry guards.
        "g11_campaign.py": "globs its own resume ledger, not a repo-defined set",
        "regime_sweep.py": "globs /proc for orphaned workers; the domain is "
                           "live processes, and check_for_orphans reports the "
                           "PIDs it found rather than a bare zero",
    }
    listed = {pathlib.Path(v[0]).name for v in ENUMERATORS.values()}
    missing = []
    for p in sorted((REPO / "scripts").glob("*.py")):
        if p.name in listed or p.name in EXEMPT:
            continue
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        walks = any(
            isinstance(n, ast.Attribute)
            and n.attr in ("glob", "rglob", "iterdir", "walk", "iter_modules")
            for n in ast.walk(tree))
        if walks:
            missing.append(p.name)
    assert not missing, (
        f"scripts advertising a sweep but absent from the registry: {missing}. "
        f"Add them with their coverage mechanism, or exempt with a reason.")
