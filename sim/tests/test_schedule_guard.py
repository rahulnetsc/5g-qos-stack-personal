"""The absolute-time defect class, guarded at the CATEGORY.

`docs/wp9-defects-log.md` #23: a scenario that places events at fixed slots
and is run at a shorter horizon does not fail -- the events past the end are
consumed and discarded and the run exits 0. The fix was applied to
`g11.py` when it was found there, the category question was asked and
answered in the defects log naming four more sites, and then **the answer was
not acted on for eight weeks because G9 was deferred.**

**SO THIS FILE GUARDS THE CLASS, NOT THE SITES.** The last test derives the
set of scenario builders from the module's own AST -- never from a list
written into prose, which is the drift this project has recorded four times
-- and fails when a NEW builder takes a horizon and never calls the guard.
That is what makes a fifth instance loud instead of silent.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from sim.scenarios import g9
from sim.scenarios.schedule_guard import (
    ScheduleTooLongForHorizon, require_horizon,
)

SCEN_DIR = pathlib.Path(g9.__file__).parent

#: Builders that legitimately have no absolute-time schedule. Each entry is a
#: CLAIM with a reason, the same shape as parallel_audit's ALLOW_SERIAL --
#: "no schedule" is fine, "no schedule silently" is the finding.
NO_SCHEDULE = {
    "g12": "the ramp is one load per run; no mid-run schedule (defects-log #23)",
}


# --- the guard itself ------------------------------------------------------

def test_require_horizon_refuses_a_schedule_that_does_not_fit():
    with pytest.raises(ScheduleTooLongForHorizon) as e:
        require_horizon("demo", last_event_slot=9_000, horizon_slots=4_000)
    assert "9000" in str(e.value) and "4000" in str(e.value)
    assert "#23" in str(e.value), "the message must cite the defect class"


def test_allow_partial_is_a_claim_the_caller_makes():
    require_horizon("demo", 9_000, 4_000, allow_partial=True)   # no raise


def test_a_schedule_that_fits_is_accepted():
    require_horizon("demo", 3_999, 4_000)


# --- the four G9 sites, each at a horizon that used to truncate silently ---

@pytest.mark.parametrize("builder,kwargs,short", [
    (g9.gt61_warm_rejoin, {}, 8_000),      # 6 of 10 events were past the end
    (g9.gt61_warm_rejoin, {}, 4_000),      # 8 of 10
    (g9.gt62_cold_attach, {}, 8_000),
    (g9.gt63_rlf_recovery, {}, 4_000),     # the ENTIRE fade was outside
])
def test_g9_builders_now_REFUSE_a_horizon_that_truncates(builder, kwargs, short):
    with pytest.raises(ScheduleTooLongForHorizon):
        builder(seed=1, horizon_slots=short, **kwargs)


@pytest.mark.parametrize("builder", [
    g9.gt61_warm_rejoin, g9.gt62_cold_attach, g9.gt63_rlf_recovery,
])
def test_g9_builders_still_build_at_their_own_defaults(builder):
    """The defect was LATENT -- everything fits at the designed horizon, so
    no published G9 result is affected and the guard must not change that."""
    assert builder(seed=1) is not None


@pytest.mark.parametrize("builder", [
    g9.gt61_warm_rejoin, g9.gt62_cold_attach, g9.gt63_rlf_recovery,
])
def test_allow_partial_schedule_is_reachable_on_every_g9_builder(builder):
    assert builder(seed=1, horizon_slots=4_000,
                   allow_partial_schedule=True) is not None


# --- THE CLASS CHECK: a NEW site must fail loudly -------------------------

def _builders_taking_a_horizon(path: pathlib.Path) -> list[str]:
    """Every module-level function that BUILDS A SCENARIO and accepts
    `horizon_slots`, from the AST -- so a builder added tomorrow is included
    without anyone remembering to add it here.

    "Builds a scenario" is `-> ScenarioConfig`, not a name pattern. The
    first version of this test used "takes horizon_slots" alone and flagged
    three g11 HELPERS (`scripted_ingredients_present`, `expected_counts`,
    `assert_schedule_fired`) that read a horizon without owning a schedule.
    A guard that fires on things it is not about gets an allow-list, and an
    allow-list is how a category check decays into a site list.
    """
    tree = ast.parse(path.read_text())
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name.startswith("_"):
            continue
        args = [a.arg for a in node.args.args + node.args.kwonlyargs]
        if "horizon_slots" not in args:
            continue
        ret = getattr(node.returns, "id", None) or getattr(node.returns, "attr", None)
        if ret != "ScenarioConfig":
            continue
        out.append(node.name)
    return out


def _calls_a_horizon_guard(path: pathlib.Path, fn_name: str) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    f = sub.func
                    name = getattr(f, "id", None) or getattr(f, "attr", None)
                    if name in ("require_horizon", "minimum_horizon_slots"):
                        return True
    return False


def test_EVERY_scenario_builder_that_takes_a_horizon_guards_its_schedule():
    """THE CATEGORY GUARD. Derived from the AST, never from a list in prose.

    A new scenario builder that takes `horizon_slots` and never calls a
    horizon guard fails here -- which is the whole point: instance five of
    this defect should be caught by a test, not by someone re-reading the
    defects log two months later.
    """
    # ESTABLISH IT COULD HAVE FAILED. A category check that discovers zero
    # builders passes vacuously and would keep passing forever -- the third
    # fault shape in CLAUDE.md's could-have-failed table. So the discovery
    # itself is asserted before the guard is.
    found: list[str] = []
    for path in sorted(SCEN_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "schedule_guard.py":
            continue
        found += [f"{path.name}::{fn}" for fn in _builders_taking_a_horizon(path)]
    assert len(found) >= 4, (
        f"the AST scan found only {found} -- it must discover the known "
        f"schedule-owning builders (g9's three plus g11's) or it is passing "
        f"vacuously")
    for known in ("g9.py::gt61_warm_rejoin", "g9.py::gt62_cold_attach",
                  "g9.py::gt63_rlf_recovery", "g11.py::build_g11_scenario"):
        assert known in found, f"{known} was not discovered by the AST scan"

    unguarded = []
    for path in sorted(SCEN_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "schedule_guard.py":
            continue
        for fn in _builders_taking_a_horizon(path):
            if _calls_a_horizon_guard(path, fn):
                continue
            if path.stem in NO_SCHEDULE:
                continue
            unguarded.append(f"{path.name}::{fn}")
    assert not unguarded, (
        "these scenario builders take a horizon and never call "
        "require_horizon()/minimum_horizon_slots(), so a short horizon would "
        "silently truncate their schedule (docs/wp9-defects-log.md #23): "
        + ", ".join(unguarded)
        + ". Either guard the schedule, or add the module to NO_SCHEDULE "
          "with a reason -- 'no schedule' is fine, 'no schedule silently' is "
          "the finding.")
