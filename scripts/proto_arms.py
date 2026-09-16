"""Resolve `TwoTierProto`'s flagged divergence arms by name.

WHY THIS IS NOT IN `g11_campaign._arm`. That function sits inside the stored
`code_state` scope of every published G1/G2/G3/G10/G12 artefact, so adding an
import of `scheduler/two_tier_proto.py` there would stale every claim in
`config/published_claims.yml` for a file those campaigns never ran. A separate
module that the faithful path never imports leaves those scopes untouched.

A name that starts with `Proto` and is not known here RAISES. A typo must not
fall through to the faithful arm and be reported under a divergence's name --
that is the worst failure available to a comparison, because it looks like a
clean null result.
"""
from typing import Any

__all__ = ["resolve_arm", "is_proto", "split_cg", "CG_PRESETS"]

#: "Product + CG" (README section 8): an arm name may carry a configured-
#: grant suffix, and the suffix IS the label -- it travels into every row,
#: block key and ledger key because the arm name does. `+CG` is the
#: restricted UE (`allowedCG-List` honoured), `+CGu` the unrestricted one
#: (the OAI UE today). The driver gets the config; the scheduler gets the
#: base name. Every value inside a preset is `sim/configured_grant.py`'s
#: CHOSEN default, so a preset is a switch, not a tuning.
CG_PRESETS: dict[str, dict[str, Any]] = {
    "+CG": {"lcp_restriction": True},
    "+CGu": {"lcp_restriction": False},
    # Build 2d: restricted, with the CG period and phase taken from the
    # flow's declared traffic pattern (TSCAI / UE traffic info) instead of
    # the PDB rule. Conditional on a core that sends TSCAI -- free5GC and
    # the OAI gNB do not today -- hence its own label.
    "+CGt": {"lcp_restriction": True, "traffic_descriptor": True},
}


def split_cg(name: str) -> tuple[str, "dict[str, Any] | None"]:
    """`"PF+CG"` -> `("PF", {...})`; a name without a suffix -> `(name, None)`.
    An unknown `+` suffix RAISES rather than silently running without CG
    under a name that claims it."""
    if "+" not in name:
        return name, None
    base, _, suffix = name.partition("+")
    key = "+" + suffix
    if key not in CG_PRESETS:
        raise ValueError(f"unknown arm suffix {key!r} in {name!r}; known: {sorted(CG_PRESETS)}")
    return base, dict(CG_PRESETS[key])

_FLAGS: dict[str, dict[str, Any]] = {
    "ProtoOff": {},
    "ProtoE1": {"gate_follower_reserve": True},
    "ProtoE2": {"stale_bsr_reserve": True},
    "ProtoE1E2": {"gate_follower_reserve": True, "stale_bsr_reserve": True},
}


def is_proto(name: str) -> bool:
    return name.startswith("Proto")


def resolve_arm(name: str, min_rb: int = 5):
    """A `TwoTierProto` for `name`, or `g11_campaign._arm(name)` otherwise."""
    if name == "ConfigSched2X1":
        # E1 (2026-09-16): ConfigSched2 with the outer problem charging a
        # visit its real harmonic DENSITY instead of one unit against a
        # window total. Registered HERE rather than in `g11_campaign._arm`
        # for the reason this module exists: that function is inside every
        # published artefact's `code_state` scope.
        from sim.baselines.config_sched2 import ConfigSched2
        return ConfigSched2(min_rb=min_rb, density_budget=True)
    if not is_proto(name):
        from g11_campaign import _arm
        return _arm(name)
    from scheduler.two_tier_proto import TwoTierProto
    if name.startswith("ProtoGslack"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            deadline_gated_periodic=True,
                            slack_ordered_periodic=True,
                            reserve_period_mult=int(name[11:]) / 100.0)
    # G-kpi with a BOUNDED rather than removed spatial reserve: name carries
    # K, e.g. ProtoGkpiD4 keeps the reserve for 4 followers.
    # M1: MFBR enforcement layered on the current candidate.
    if name == "ProtoM1":
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            deadline_gated_periodic=True,
                            kpi_ordered_periodic=True,
                            reserve_depth_under_periodic=2,
                            mfbr_enforced=True)
    if name.startswith("ProtoGkpiD"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            deadline_gated_periodic=True, kpi_ordered_periodic=True,
                            reserve_depth_under_periodic=int(name[10:]), reserve_period_mult=1.0)
    if name.startswith("ProtoGkpi"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            deadline_gated_periodic=True,
                            kpi_ordered_periodic=True,
                            reserve_period_mult=int(name[9:]) / 100.0)
    if name.startswith("ProtoGdenial"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            deadline_gated_periodic=True,
                            denial_ordered_periodic=True,
                            reserve_period_mult=int(name[12:]) / 100.0)
    if name.startswith("ProtoGperD"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            deadline_gated_periodic=True,
                            reserve_period_mult=int(name[10:]) / 100.0)
    if name.startswith("ProtoGper"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            reserve_period_mult=int(name[9:]) / 100.0)
    if name.startswith("ProtoGdepth"):
        tail = name[len("ProtoGdepth"):]
        return TwoTierProto(min_rb=min_rb, depth_bounded_reserve=True,
                            reserve_depth=(None if tail == "" else int(tail)))
    # AGE (fix 1 + 2, 2026-09-14): overdue tier gated on P*, composite
    # otherwise; reserve bounded at K (ProtoAgeD2) or removed (ProtoAge).
    if name in ("ProtoAge", "ProtoAgeD2"):
        return TwoTierProto(min_rb=min_rb, age_gated_ordering=True,
                            reserve_depth_under_periodic=(
                                2 if name.endswith("D2") else None))
    # C3 + C4 (fix 3 + 4): honest deadline clock and contract-only urgency.
    # ProtoC34D2 = the port's own rescue path made honest, reserve bounded by
    # need at K=2 (G-depth); ProtoAgeC34D2 = all of it on top of AGE.
    if name == "ProtoC34D2":
        return TwoTierProto(min_rb=min_rb, clear_gated_stamp=True,
                            urgency_contract_only=True,
                            depth_bounded_reserve=True, reserve_depth=2)
    if name == "ProtoAgeC34D2":
        return TwoTierProto(min_rb=min_rb, age_gated_ordering=True,
                            reserve_depth_under_periodic=2,
                            clear_gated_stamp=True, urgency_contract_only=True)
    # RR-age (probe, 2026-09-13): EVERY slot is a reserve slot (P forced to 1
    # via a zero multiplier), ordered by slots-since-last-UL-grant; Tiers 1 and
    # 1.5 untouched. The spatial reserve is removed (RRage) or kept for K=2
    # followers (RRageD2). Existing flags only -- no new scheduler code.
    if name in ("ProtoRRage", "ProtoRRageD2"):
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            denial_ordered_periodic=True,
                            reserve_period_mult=0.0,
                            reserve_depth_under_periodic=(
                                2 if name.endswith("D2") else None))
    # D1 (2026-09-16, group E): RRageD2 plus a GBR-deficit tie-break BENEATH
    # the age order. The tuned arm is its own name so `ProtoRRageD2` stays
    # frozen as the campaign measured it.
    if name == "ProtoRRageD2X1":
        return TwoTierProto(min_rb=min_rb, periodic_reserve=True,
                            denial_ordered_periodic=True,
                            reserve_period_mult=0.0,
                            reserve_depth_under_periodic=2,
                            deficit_tiebreak=True)
    if name not in _FLAGS:
        raise ValueError(
            f"unknown Proto arm {name!r}; known: {sorted(_FLAGS)} plus the "
            f"ProtoGdepth<K>/ProtoGper<mult>/ProtoGperD<mult> families")
    return TwoTierProto(min_rb=min_rb, **_FLAGS[name])
