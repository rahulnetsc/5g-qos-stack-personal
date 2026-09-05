"""One guard for every scenario whose schedule is pinned to absolute time.

THE DEFECT CLASS (`docs/wp9-defects-log.md` #23). A scenario that places
events at fixed slots and is then run at a shorter horizon does not fail --
the events past the end are consumed and discarded, the run exits 0, and the
artefact looks complete. Measured: `g9.py::gt61_warm_rejoin` at h=8,000
places **6 of its 10 events beyond the horizon** and at h=4,000, **8 of 10**;
`gt63_rlf_recovery` at h=4,000 has its **entire fade** outside the run.

**THIS MODULE EXISTS BECAUSE THE FIX WAS PREVIOUSLY APPLIED AT ONE SITE.**
`sim/scenarios/g11.py` grew its own `minimum_horizon_slots()` +
`allow_partial_schedule` when the defect was found there, and the category
question was asked and answered in the defects log -- naming four more sites
-- and then not acted on, because G9 was deferred. That is this project's
most expensive recurring shape: fixing at the site of discovery rather than
at the category. So the guard is shared, and
`sim/tests/test_schedule_guard.py` fails when a NEW scenario builder takes a
horizon and does not call it.

The rule it enforces: **a schedule that does not fit its horizon is a
DIFFERENT scenario, not a shorter one.** Refuse construction; do not
silently truncate. `allow_partial=True` is available and is a claim the
caller makes, not a default.
"""

from __future__ import annotations


class ScheduleTooLongForHorizon(ValueError):
    """A scenario's scripted schedule does not fit the requested horizon."""


def require_horizon(scenario: str, last_event_slot: int, horizon_slots: int,
                    *, allow_partial: bool = False,
                    detail: str = "") -> None:
    """Refuse a horizon that cannot contain the whole schedule.

    `last_event_slot` must be DERIVED from the schedule at the call site --
    never restated as a literal, which is the same drift this project has
    recorded four times for counts in prose.
    """
    if allow_partial or horizon_slots > last_event_slot:
        return
    raise ScheduleTooLongForHorizon(
        f"{scenario}: the schedule's last event is at slot {last_event_slot} "
        f"but horizon_slots={horizon_slots}. Events past the horizon are "
        f"consumed and discarded, so the run would exit 0 with an artefact "
        f"that looks complete while measuring a DIFFERENT scenario "
        f"(docs/wp9-defects-log.md #23). "
        f"{detail}"
        f"Raise the horizon to > {last_event_slot}, or pass "
        f"allow_partial=True to claim a partial schedule deliberately.")
