"""The CATEGORY question for defect #28, asked properly this time.

`test_flow_key_collision.py`'s docstring records the first answer:

    "THE CATEGORY QUESTION WAS ASKED BEFORE FIXING and the answer was zero:
     no scenario in the repository puts a (ue, qfi) pair in both directions,
     so no published result lost a flow."

**That was wrong, and a published result did lose a flow.**
`build_g12_scenario(composition="drone_heavy", n_ues=8)` puts 5QI 9 on ue8 in
BOTH directions, and the collision is worse than a lost record:
`BufferModel.register()` overwrites, so the two flows shared one queue and DL
grants drained a UL flood (defects log #30).

**Why the first sweep missed it, and what this file does differently.** The
first sweep enumerated the zero-argument scenario functions. `drone_heavy` is
reachable only through a **parameterised** builder, at one composition, at one
fleet size, and only when `bg_offered_bps > 0`. A sweep over nullary builders
cannot see it.

So this file enumerates builders **by reflection** and drives each across a
grid, and — the part that matters — **it asserts its own COVERAGE**. A builder
that is added and not exercised fails the coverage test rather than silently
enlarging the blind spot, which is the failure mode that produced #30.
"""

from __future__ import annotations

import collections
import importlib
import inspect
import pkgutil

import pytest

import sim.scenarios as S
from sim.config import ScenarioConfig


def _builders() -> dict[str, object]:
    """Every function in `sim/scenarios/` that returns a ScenarioConfig."""
    out = {}
    mods = ["sim.scenarios"] + [f"sim.scenarios.{m.name}"
                                for m in pkgutil.iter_modules(S.__path__)]
    for name in mods:
        mod = importlib.import_module(name)
        for fn_name, fn in vars(mod).items():
            if not inspect.isfunction(fn) or fn.__module__ != name:
                continue
            if fn_name.startswith("_"):
                continue
            ann = str(inspect.signature(fn).return_annotation or "")
            if "ScenarioConfig" in ann and fn_name != "permute_flows":
                out[f"{name}.{fn_name}"] = fn
    return out


def _cases():
    """(label, ScenarioConfig) over a grid wide enough to reach the shapes a
    campaign actually builds -- every composition, both fleet sizes G12 uses,
    and the background flood both on and off, since the collision needed all
    three to coincide."""
    from sim.parametric import sweep_scenario
    from sim.scenarios.g11 import build_g11_scenario
    from sim.scenarios.g12 import BG_OFFERED_BPS, COMPOSITIONS, build_g12_scenario
    from sim.scenarios.g9 import (gt61_warm_rejoin, gt62_cold_attach,
                                  gt63_rlf_recovery)

    cases = []
    for sid in range(1, 8):
        try:
            cases.append((f"scenario({sid})", S.scenario(sid)))
        except Exception:
            break
    for n in (2, 4, 8, 10, 16):
        cases.append((f"sweep_scenario(n={n})",
                      sweep_scenario(seed=1, n_ues=n, horizon_slots=2000)))
    for comp in COMPOSITIONS:
        for n in (4, 8):
            for bg in (0.0, BG_OFFERED_BPS):
                cases.append(
                    (f"g12({comp},n={n},bg={bg:g})",
                     build_g12_scenario(composition=comp, n_ues=n, seed=1,
                                        horizon_slots=2000, committed_mult=1.0,
                                        bg_offered_bps=bg)))
    for n in (2, 4):
        # `allow_partial_schedule` because this sweep reads the FLOW LIST, not
        # the scripted schedule -- and the guard is right to refuse a short
        # horizon for anything that scores GT-7.1.
        cases.append((f"g11(n={n})",
                      build_g11_scenario(seed=1, n_ues=n, horizon_slots=2000,
                                         allow_partial_schedule=True)))
    for fn in (gt61_warm_rejoin, gt62_cold_attach, gt63_rlf_recovery):
        cases.append((f"g9.{fn.__name__}",
                      fn(seed=1, n_neighbours=3, horizon_slots=40000)))
    return cases


def _collisions(sc: ScenarioConfig) -> dict:
    c = collections.Counter((f.ue_id, f.qfi) for f in sc.flows)
    return {k: v for k, v in c.items() if v > 1}


@pytest.mark.parametrize("label,sc", _cases(), ids=lambda x: x if isinstance(x, str) else "")
def test_no_scenario_puts_one_5qi_in_both_directions(label, sc):
    coll = _collisions(sc)
    assert not coll, (
        f"{label}: {coll} -- a UE carries the same 5QI in both directions. "
        f"`BufferModel` keys on (ue_id, qfi) with no direction and "
        f"`register()` OVERWRITES, so these flows would SHARE ONE QUEUE, not "
        f"merely collide in the record. Give one of them its own 5QI "
        f"(defects log #28, #30).")


def test_the_sweep_COVERS_every_builder_rather_than_the_easy_ones():
    """The check that would have caught #30 before it shipped.

    The first sweep looked at nullary builders and concluded 'zero'. This
    asserts that every ScenarioConfig-returning builder in `sim/scenarios/`
    is actually exercised above -- so adding one without adding a case fails
    HERE, loudly, instead of quietly widening the blind spot.
    """
    exercised = " ".join(label for label, _ in _cases())
    missing = []
    for full in _builders():
        stem = full.rsplit(".", 1)[1]
        # `scenario()` is the dispatcher the nullary wrappers go through, so
        # covering it by id covers them; name the mapping rather than
        # silently treating absence as coverage.
        if stem in ("smoke_scenario", "overload_scenario", "vision_scenario",
                    "sensor_dense_scenario", "latency_bound_scenario",
                    "factory_robots_scenario"):
            continue                       # reached via scenario(<id>)
        key = {"build_g12_scenario": "g12(", "build_g11_scenario": "g11(",
               "scenario": "scenario("}.get(stem, stem)
        if key not in exercised:
            missing.append(full)
    assert not missing, (
        f"builders with no case in this sweep: {missing}. A sweep that does "
        f"not cover a builder cannot report 'zero collisions' about it -- "
        f"which is exactly how G12's collision survived the first sweep.")


def test_the_grid_reaches_the_shape_that_ACTUALLY_collided():
    """A sweep that cannot construct the known failure proves nothing.

    Before the fix, `drone_heavy` at n=8 with the flood on collided. The grid
    must include that point, or a future regression walks straight past it.
    """
    labels = {label for label, _ in _cases()}
    assert any("drone_heavy" in l and "n=8" in l and "bg=5e+07" in l.replace("bg=50000000", "bg=5e+07")
               or ("drone_heavy" in l and "n=8" in l and not l.endswith("bg=0)"))
               for l in labels), f"the known-colliding point is not in the grid: {sorted(labels)}"
