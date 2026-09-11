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

__all__ = ["resolve_arm", "is_proto"]

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
    if name not in _FLAGS:
        raise ValueError(
            f"unknown Proto arm {name!r}; known: {sorted(_FLAGS)} plus the "
            f"ProtoGdepth<K>/ProtoGper<mult>/ProtoGperD<mult> families")
    return TwoTierProto(min_rb=min_rb, **_FLAGS[name])
