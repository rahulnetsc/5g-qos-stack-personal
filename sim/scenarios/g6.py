"""GT-4's isolation cells -- G6's own conditions, built as a TRANSFORMATION.

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` L100 (the G6 catalogue row):

    With saturating 5QI-9 load added (either direction), every G1/G3/G5
    statistic stays within its bound and shifts by <= +20 % relative.

--------------------------------------------------------------------------
WHY THIS IS NOT A FOURTH SCENARIO FAMILY
--------------------------------------------------------------------------

G6 has **no statistic of its own**. It re-scores G1's command latency, G3's
liveness gaps and G5's frame statistics under an added flood, and asks two
independent questions of each: is it still inside its own bound (part A), and
did it shift by more than a fifth (part B).

**Part B is a PAIRED RATIO, so it needs a control** -- and the control cannot be
"a scenario built from the same parameters", because a paired delta is only a
delta if nothing else moved. So this module TRANSFORMS an existing scenario:
same seed, same instrument, same flow objects, with the background removed or a
saturator added. Everything G1, G3 and G5 already defend about their
instruments -- the canonical LCG ordering, offered >= GFBR, the fixed
instrument robot -- is inherited rather than re-decided.

--------------------------------------------------------------------------
THE MEASUREMENT THAT FORCED THE CONTROL TO EXIST
--------------------------------------------------------------------------

**All three guarantees ALREADY carry 5QI-9 traffic**, measured on their own
builders at N = 8:

    G1 GT-1.1   6 flows   poisson, 8 Mbps per UL robot, 50 Mbps DL on the last
    G3 GT-2.2   8 flows   per-UE filler plus the 50 Mbps saturating flood
    G5 GT-3.1   1 flow    the 50 Mbps saturator on Asset B

So *"load added"* has nothing to be added to: **the published artefacts are the
TREATMENT, not the control**, and G6 cannot be scored by differencing them.

**And the existing background is not the same thing in all three.** G1's uplink
filler is an 8 Mbps Poisson source per robot -- offered load, not saturation --
while G3's and G5's are 50 Mbps saturators. Differencing them as if they shared
a condition would compare a saturator against a trickle, which is this
project's own "a measurement carries its configuration" error.

--------------------------------------------------------------------------
THE ONE THING A TRANSFORMATION CAN BREAK, AND THE CHECK FOR IT
--------------------------------------------------------------------------

**LCG = DRB ID, and the simulator's proxy for DRB setup order is position in
the UE's flow list** (`scheduler/flow.py::assign_deployed_lcgs`). So REMOVING a
flow can renumber the ones after it, and a "control" whose instrument sits on a
different logical channel group is not a control at all.

Every builder here happens to order background LAST, so removal renumbers
nothing -- but that is a property of those builders, not of this code, and it
is asserted rather than assumed: `sim/tests/test_g6_scenario.py` compares every
instrument flow's `lcg` across conditions and fails if one moves.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from sim.config import ScenarioConfig
from scheduler.flow import LCG_UNASSIGNED, FlowConfig

__all__ = [
    "BG_5QI", "SATURATOR_BPS", "FIRMWARE_IMAGE_BYTES", "CONDITIONS",
    "without_background", "with_saturator", "with_firmware_push",
    "background_flow_keys", "instrument_is_unchanged",
]

#: The non-protected 5QIs. `sim/scorecard.py::Population.protected_fleet()`
#: excludes exactly these, so "the flood is never scored" is inherited
#: machinery rather than a rule restated here.
BG_5QI = (8, 9)

#: What "saturating" means, matched to G3's own `FLOOD_UL_BPS` so the word
#: means the same thing across guarantees. Large enough that the queue never
#: empties; not so large that an unbounded backlog dominates the run's memory.
SATURATOR_BPS = 50_000_000.0

#: GT-4.2: *"record completion time for a fixed 500 MB image -- clients ask how
#: how long updates take WITH the fleet live"*. A FINITE transfer, not a
#: saturator: it has a completion instant, which is the deliverable.
FIRMWARE_IMAGE_BYTES = 500 * 1024 * 1024

#: The three conditions part B needs. `none` is the CONTROL and is two thirds
#: cheaper to skip and impossible to do without.
CONDITIONS = ("none", "ul", "dl")


def background_flow_keys(scenario: ScenarioConfig) -> list[str]:
    """Every non-protected flow, derived from the scenario rather than listed."""
    return sorted(f"ue{f.ue_id}_qfi{f.qfi}"
                  for f in scenario.flows if f.qfi in BG_5QI)


def _rebuild(scenario: ScenarioConfig, flows: list[FlowConfig],
             name: str) -> ScenarioConfig:
    """Re-resolve LCGs over each UE's FULL list, as G3 and G5 both do.

    The ordinals are cleared first: `assign_deployed_lcgs` keeps an explicit
    LCG while still spending an ordinal, so a second pass over a partially
    resolved list can land two flows on one group. Measured directly while
    building G3's module, and pinned by a test there.
    """
    cleared = [dataclasses.replace(f, lcg=LCG_UNASSIGNED) for f in flows]
    return dataclasses.replace(scenario, flows=cleared, name=name)


def without_background(scenario: ScenarioConfig) -> ScenarioConfig:
    """THE CONTROL: the same cell with every 5QI-8/9 flow removed.

    This is the condition part B differences against, and it does not exist in
    any published artefact -- see the module docstring.
    """
    keep = [f for f in scenario.flows if f.qfi not in BG_5QI]
    if len(keep) == len(scenario.flows):
        raise ValueError(
            f"{scenario.name} has no 5QI-8/9 flow to remove, so this is not a "
            f"control for anything -- G6's whole design rests on the base "
            f"scenarios already carrying background, and one that does not "
            f"would silently make treatment and control identical")
    return _rebuild(scenario, keep, f"{scenario.name}_bgnone")


def with_saturator(scenario: ScenarioConfig, *, direction: str,
                   bps: float = SATURATOR_BPS,
                   ue_id: Optional[int] = None,
                   instrument_ue: int = 1) -> ScenarioConfig:
    """THE TREATMENT: the control, plus one saturating 5QI-9 flow.

    Built from `without_background` rather than from the original, so the
    treatment and the control differ by EXACTLY this flow. Adding a saturator
    on top of the existing filler would make the pair differ by the filler too.

    The saturator rides a NEIGHBOUR, never the instrument robot: G6 is about
    background traffic impairing *the fleet*, and a flood on the instrument's
    own radio is GT-2.1's intra-asset question wearing a different name.
    """
    if direction not in ("UL", "DL"):
        raise ValueError(f"direction must be UL or DL, got {direction!r}")
    base = without_background(scenario)
    ues = sorted({f.ue_id for f in base.flows})
    if ue_id is None:
        # The LAST robot, matching G3's own flood placement.
        ue_id = ues[-1]
    if ue_id == instrument_ue:
        raise ValueError(
            f"the saturator is on ue{ue_id}, the instrument robot -- G6 asks "
            f"whether a NEIGHBOUR's background can impair the fleet, so a "
            f"flood on the instrument measures a different question")
    sat = FlowConfig(
        ue_id=ue_id, qfi=9, direction=direction, flow_class="PF",
        pdb_ms=300.0, lcg=LCG_UNASSIGNED,
        traffic_kind="poisson", traffic_params={"rate_bps": float(bps)},
    )
    # APPENDED, so the instrument's own ordinals are untouched -- see the
    # module docstring's LCG note and the test that pins it.
    return _rebuild(scenario, list(base.flows) + [sat],
                    f"{scenario.name}_bg{direction.lower()}")


def with_firmware_push(scenario: ScenarioConfig, *,
                       image_bytes: int = FIRMWARE_IMAGE_BYTES,
                       ue_id: Optional[int] = None,
                       instrument_ue: int = 1,
                       horizon_s: float) -> ScenarioConfig:
    """GT-4.2's firmware window: a FINITE downlink image, not a saturator.

    *"A firmware push to one robot cannot blunt another robot's controls"*, and
    *"record completion time for a fixed 500 MB image"*. The completion instant
    is the deliverable, so the source must be able to FINISH -- a saturator
    never does, and a saturator's "completion time" would be the horizon by
    construction.

    Modelled as a constant-rate downlink flow sized to deliver the image within
    the horizon if it gets the whole cell, so the measured completion time is
    bounded by contention rather than by the source's own rate. The rate is
    DERIVED from the image and the horizon, never picked.
    """
    if horizon_s <= 0:
        raise ValueError(f"horizon_s must be > 0, got {horizon_s}")
    base = without_background(scenario)
    ues = sorted({f.ue_id for f in base.flows})
    if ue_id is None:
        ue_id = ues[-1]
    if ue_id == instrument_ue:
        raise ValueError(
            f"the firmware push is on ue{ue_id}, the instrument robot -- "
            f"GT-4.2 asks whether a push to ONE robot blunts ANOTHER's "
            f"controls")
    rate_bps = image_bytes * 8.0 / horizon_s
    fw = FlowConfig(
        ue_id=ue_id, qfi=9, direction="DL", flow_class="PF",
        pdb_ms=300.0, lcg=LCG_UNASSIGNED,
        traffic_kind="poisson", traffic_params={"rate_bps": rate_bps},
    )
    return _rebuild(scenario, list(base.flows) + [fw],
                    f"{scenario.name}_fw{image_bytes}")


def instrument_is_unchanged(a: ScenarioConfig, b: ScenarioConfig) -> bool:
    """Is every PROTECTED flow identical between two conditions?

    The property a paired delta rests on. Compares the full FlowConfig,
    `lcg` included, because a control whose instrument sits on a different
    logical channel group is not a control.
    """
    key = lambda sc: sorted(
        (f.ue_id, f.qfi, f.direction, f.flow_class, f.lcg, f.pdb_ms,
         f.gfbr_bps, f.mfbr_bps, f.traffic_kind,
         tuple(sorted((str(k), str(v)) for k, v in f.traffic_params.items())))
        for f in sc.flows if f.qfi not in BG_5QI)
    return key(a) == key(b)
