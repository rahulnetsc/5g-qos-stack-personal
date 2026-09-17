"""G8 / GT-5.1 -- equal robots, equal service, CONTINUOUSLY.

The guarantee (`docs/IA_P5G_Factory_Guarantee_Test_Plan.md`, G8 row and
GT-5.1): *"Robots of equal entitlement get equal service -- continuously, not
just on average. Per-1 s Jain >= 0.9 per role across assets; zero starvation
epochs >= 1 s."* GT-5.1 adds two conjuncts: *"zero windows where either
asset's telemetry gap >= 1 s; per-window GFBR check on both."*

WHY THIS FILE EXISTS AT ALL. Until now G8 had no scenario and no runner.
`sweeps/g8-fairness/` holds artefacts dated 2026-09-12, but
`git log -S "jain_by_role"` finds no commit: the script that produced them
was never committed and is gone. Those rows also carry `horizon: 40000` as a
literal and predate `sim/scenarios/deployed_cell.py` (2026-09-15, `1f5d105`),
so they describe the OLD numerology-2 `DSUUU` cell. Under CLAUDE.md's
measurement-carries-its-configuration rule they cannot be quoted for the
deployed cell, which is why this is a rebuild and not a re-score.

WHICH "ROLE", BECAUSE THERE ARE TWO AND ONLY ONE IS RIGHT.
`RunRecord`'s `completion_ts_by_role_s` is grouped by `Message.role` -- a
PDU-set role (nine runners read it, all for that purpose). G8's "per role
across assets" is the UE's FLEET role -- ugv / drone / camera / sensor /
actuator -- and the ONLY source of that mapping is `sim.fleet.build_fleet`,
whose second return value is the per-UE role sequence. A runner that joined
on the message role would compute a real number for the wrong population,
so this module hands back the UE-role map beside the scenario rather than
letting anyone reconstruct it.

CONTENTION HAS TO BE REAL OR THE TEST IS VACUOUS. GT-5.1 specifies assets
"offered jointly above the measured ceiling (from GT-3.2) so contention is
real" -- per-second fairness on an idle cell is 1.0 for every scheduler and
separates nothing. `committed_mult` therefore scales each committed flow's
offered load AND its contract together via
`sim.workload.scale_committed_load`; that is the operator-visible axis
(more work promised), and it is deliberately not the best-effort `load_mult`
filler knob.
"""
from __future__ import annotations

from typing import Optional

from sim.config import ScenarioConfig, UEConfig
from sim.fleet import COMPOSITIONS, build_fleet
from sim.workload import scale_committed_load

from . import deployed_cell as _dcell

__all__ = [
    "build_g8_scenario",
    "roles_for",
    "scoreable_roles",
    "assert_g8_is_scoreable",
    "DEFAULT_HORIZON_SLOTS",
]

#: Matched to `sim/scenarios/g12.py`'s values so a G8 cell and a G12 cell at
#: the same N differ in workload only, never in radio.
_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000

#: 5 s, as every other deployed-cell builder. DERIVED from milliseconds
#: through `slots()`, never written as a slot literal -- the whole point of
#: `deployed_cell.py` (a bare `40_000` silently meant "10 s at numerology 2"
#: in every builder before it).
DEFAULT_HORIZON_SLOTS = _dcell.slots(5_000.0)


def roles_for(n_ues: int, composition: str) -> dict[int, str]:
    """`ue_id -> fleet role`, taken from the fleet builder's own allocation.

    Derived, never restated: `build_fleet` allocates roles by largest
    remainder, so the mix is exact at every N. Hardcoding a split here would
    drift from it the moment `COMPOSITIONS` changes -- CLAUDE.md's
    count-in-prose rule applied to a mapping.
    """
    _flows, seq = build_fleet(n_ues, composition)
    return {i + 1: role for i, role in enumerate(seq)}


def scoreable_roles(roles: dict[int, str], min_ues: int = 2) -> list[str]:
    """Roles carrying at least `min_ues` UEs, sorted.

    A Jain index over ONE flow is 1.0 by construction. A role with a single
    UE therefore cannot express unfairness, and including it inflates the
    per-role minimum toward a pass.
    """
    counts: dict[str, int] = {}
    for role in roles.values():
        counts[role] = counts.get(role, 0) + 1
    return sorted(r for r, n in counts.items() if n >= min_ues)


def assert_g8_is_scoreable(roles: dict[int, str], min_ues: int = 2) -> list[str]:
    """Refuse a cell whose per-role Jain could not fail.

    This repo's recurring defect is a check that passes because it could not
    fail -- the M09 hoist's blind `--check`, G12's `SPECIFIED_ORDER` naming a
    5QI that `first_violation_order` can never emit, G9's scripted fade
    shorter than `t310`. G8's per-role Jain has exactly that failure mode: at
    a fleet size where every role holds one UE, every per-role Jain is 1.0
    and the clause reports a perfect pass over a population that cannot
    disagree with itself. Raise instead, and let the runner exclude the cell
    WHOLE and say so.
    """
    ok = scoreable_roles(roles, min_ues)
    if not ok:
        counts = sorted({r: list(roles.values()).count(r) for r in set(roles.values())}.items())
        raise ValueError(
            f"no role has >= {min_ues} UEs, so per-role Jain cannot fail "
            f"(roles: {counts}); raise n_ues or pick a composition that "
            f"concentrates one role")
    return ok


def build_g8_scenario(
    composition: str = "mixed",
    n_ues: int = 8,
    seed: int = 1,
    committed_mult: float = 1.0,
    horizon_slots: Optional[int] = None,
) -> tuple[ScenarioConfig, dict[int, str]]:
    """A symmetric fleet on the deployed cell, plus its `ue_id -> role` map.

    Returns the map rather than the bare scenario because `ScenarioConfig`
    has no role field and `FlowConfig` has none either -- see the module
    docstring on which "role" G8 means.
    """
    if composition not in COMPOSITIONS:
        raise ValueError(
            f"unknown composition {composition!r}; known: {sorted(COMPOSITIONS)}")
    flows, seq = build_fleet(n_ues, composition)
    ues = [UEConfig(ue_id=i + 1, mean_snr_db=_BASE_SNR_DB,
                    coherence_slots=_COHERENCE_SLOTS)
           for i in range(n_ues)]
    scenario = ScenarioConfig(
        name=f"g8_{composition}_n{n_ues}",
        horizon_slots=(DEFAULT_HORIZON_SLOTS if horizon_slots is None
                       else horizon_slots),
        carrier=_dcell.carrier(),
        tdd=_dcell.tdd(),
        ues=ues,
        flows=list(flows),
        seed=seed,
    )
    # Applied AFTER construction so the contract fields resolved in
    # `ScenarioConfig.__post_init__` (LCG = DRB ID, M-5) are scaled with the
    # offered load rather than against it. `scale_committed_load` is the
    # identity at 1.0 and renames the scenario otherwise, so two axis points
    # never share a ledger key.
    scenario = scale_committed_load(scenario, committed_mult)
    return scenario, {i + 1: role for i, role in enumerate(seq)}
