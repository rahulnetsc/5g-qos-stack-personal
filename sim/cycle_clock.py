"""Shared production-line clock for correlated bursts across flows (WP7
commit 9, docs/p5g-sim-plan.md sec9's "thundering herd" mechanism -- "the
plan's own assessment is that the production-line thundering herd is
plausibly the most discriminating factory feature and is entirely absent
today").

Flows tagged with the same FlowConfig.sync_group share one phase reference
-- slot 0, matching every other periodic kind's own convention
(deterministic, periodic_control, video_frame, xr_video all anchor to the
run's start). A sync_group is about relative synchrony BETWEEN its
members, not the absolute phase of the whole run, so there is no reason to
randomise the group's own anchor. Each member then fires
phase_offset_ms after that shared tick, jittered by phase_jitter_ms --
reusing sim/traffic.py's _clipped_gaussian_jitter_ms, not a second jitter
mechanism.

No ground truth: sync_group membership and phase_offset_ms are scenario-
authoring choices (which robots share a production cycle, and how far
apart their responses land), not something oai-branches/ or any spec pins
down -- p5g-sim-plan.md sec9 only says "flows in a sync_group arrive in
phase," not by how much members may legitimately differ. This module
supplies the mechanism; a scenario decides the numbers. No shared mutable
state is needed (every member computes its own offset independently
against the fixed slot-0 anchor), so this is a pure function, not a
stateful clock object, despite the "clock" name inherited from the
original plan doc's file-naming.
"""


def phase_offset_slots(phase_offset_ms: float, slot_duration_s: float) -> int:
    """Convert a flow's configured phase offset (ms, relative to its
    sync_group's shared slot-0 anchor) into whole slots -- same truncating
    convention every other period_ms-to-slots conversion in sim/traffic.py
    uses."""
    return int(phase_offset_ms / 1000.0 / slot_duration_s)
