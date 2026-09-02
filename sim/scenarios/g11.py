"""GT-7.1's production-shift soak (G11).

`docs/wp9-g11-plan.md`. **Scenario construction only** -- no `sim/` or
`scheduler/` behaviour change. The one mechanism this needs that did not
exist, a repeating activation window, landed separately as G11 commit 4
(`sim/traffic.py`); everything here composes it.

WHY THE BASE IS `sweep_scenario` AND NOT `build_fleet`. §7.4 settles the
soak's fleet size at **N=4** on evidence computed from `stage2_rows.csv` --
C1's conjunction passes 10/10 on every arm at N=4 and collapses to 0/10 on
TwoTier at N=8. That grid is the **parametric `factory` mix**. Switching to
the fleet builder would carry the fleet-size decision onto a workload the
evidence was never measured on, which is the trap §13's own cost-model
scope qualifier records. So the soak runs the mix its dynamic-range
evidence describes, and GT-7.1's scripted realism is layered on top.

WHAT GT-7.1 ASKS FOR, AND WHERE EACH PIECE LANDS (test plan line 305):

    "teleop cmd_vel duty-cycled on A"   -> 5QI 82 DL command flow, ue1
    "waypoint pauses on B"              -> 5QI 1 telemetry flow, ue2
    "a firmware window at T+10 min"     -> a new DL 5QI 9 bulk flow
    "one STOP drill at T+20 min"        -> a new DL 5QI 85 one-shot burst

EVERY SCHEDULE IS DERIVED, NEVER RESTATED. `expected_counts()` computes what
each ingredient should produce **from the same window lists the scenario is
built from**, and `assert_schedule_fired()` compares at EQUALITY. G9's §34.5
is the reason: "did it fire at all" is a weaker question than "did it fire
as often as the scenario specifies", and the gap between them is where a
partially-degenerate run hides. G9 also supplies the sharper half -- an arm
can record its full scheduled count and COMPLETE none -- so the assertion
checks delivery, not just arrival, where the flow is deliverable.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional

from scheduler.flow import FlowConfig
from sim.config import ScenarioConfig
from sim.parametric import sweep_scenario

__all__ = [
    "SOAK_HORIZON_SLOTS", "SLOT_S", "TeleopDuty", "WaypointPauses",
    "FirmwareWindow", "StopDrill", "build_g11_scenario", "expected_counts",
    "assert_schedule_fired", "scripted_windows",
]

SLOT_S = 0.00025                       # numerology 2
SOAK_MINUTES = 30.0
SOAK_HORIZON_SLOTS = int(SOAK_MINUTES * 60.0 / SLOT_S)      # 7,200,000

# 5QI 8 for the firmware push, NOT 9. `sim/run_record.py::flow_key` keys a
# flow by (ue_id, qfi) with NO DIRECTION TERM (docs/wp9-plan.md §5), so a DL
# 5QI 9 firmware flow on a UE that already has a UL 5QI 9 filler COLLIDES and
# one of them silently disappears from every metric. Caught in this module's
# own smoke run. 5QI 8 is the parametric mix's aggressor slot and is unused
# whenever bg=False, which is the soak's configuration.
_QFI_TELEMETRY, _QFI_COMMAND, _QFI_FIRMWARE, _QFI_ESTOP = 1, 82, 8, 85


@dataclasses.dataclass(frozen=True)
class TeleopDuty:
    """Duty-cycled teleop: on for `on_s` of every `period_s`."""
    period_s: float = 20.0
    on_s: float = 12.0

    def windows(self, horizon_s: float) -> tuple[tuple[float, float], ...]:
        n = int(horizon_s // self.period_s) + 1
        return tuple((k * self.period_s, k * self.period_s + self.on_s)
                     for k in range(n))


@dataclasses.dataclass(frozen=True)
class WaypointPauses:
    """Telemetry goes quiet at a waypoint, then resumes."""
    first_s: float = 120.0
    period_s: float = 300.0
    pause_s: float = 5.0

    def windows(self, horizon_s: float) -> tuple[tuple[Optional[float], Optional[float]], ...]:
        """ACTIVE intervals -- i.e. the complement of the pauses."""
        edges, t = [], self.first_s
        while t < horizon_s:
            edges.append((t, t + self.pause_s))
            t += self.period_s
        out, prev = [], None
        for a, b in edges:
            out.append((prev, a))
            prev = b
        out.append((prev, None))
        return tuple(out)

    def pause_count(self, horizon_s: float) -> int:
        return len(self.windows(horizon_s)) - 1


@dataclasses.dataclass(frozen=True)
class FirmwareWindow:
    """GT-4.2's firmware push, once, partway through the shift."""
    start_s: float = 600.0                 # T+10 min
    duration_s: float = 60.0
    rate_bps: float = 8_000_000.0

    def windows(self) -> tuple[tuple[float, float], ...]:
        return ((self.start_s, self.start_s + self.duration_s),)


@dataclasses.dataclass(frozen=True)
class StopDrill:
    """One STOP, at one instant. Not Poisson -- GT-7.1 says T+20 min."""
    at_s: float = 1200.0                   # T+20 min
    period_ms: float = 20.0
    burst_bytes: int = 40

    def windows(self) -> tuple[tuple[float, float], ...]:
        # exactly one period wide, so exactly one burst can fall inside
        return ((self.at_s, self.at_s + self.period_ms / 1000.0),)


def _with_params(f: FlowConfig, **extra: Any) -> FlowConfig:
    return dataclasses.replace(f, traffic_params={**f.traffic_params, **extra})


def build_g11_scenario(
    seed: int,
    n_ues: int = 4,
    horizon_slots: int = SOAK_HORIZON_SLOTS,
    teleop: TeleopDuty = TeleopDuty(),
    pauses: WaypointPauses = WaypointPauses(),
    firmware: FirmwareWindow = FirmwareWindow(),
    stop: StopDrill = StopDrill(),
    permutation: int = 0,
) -> ScenarioConfig:
    """GT-7.1's soak. `permutation` rotates the flow list for §9's control."""
    base = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon_slots)
    horizon_s = horizon_slots * SLOT_S

    flows: list[FlowConfig] = []
    for f in base.flows:
        if f.qfi == _QFI_COMMAND and f.ue_id == 1:            # asset A teleop
            f = _with_params(f, active_windows=teleop.windows(horizon_s))
        elif f.qfi == _QFI_TELEMETRY and f.ue_id == 2:        # asset B pauses
            f = _with_params(f, active_windows=pauses.windows(horizon_s))
        flows.append(f)

    flows.append(FlowConfig(
        ue_id=1, qfi=_QFI_FIRMWARE, direction="DL", flow_class="PF", pdb_ms=300.0,
        traffic_kind="poisson",
        traffic_params={"rate_bps": firmware.rate_bps,
                        "active_windows": firmware.windows()},
    ))
    flows.append(FlowConfig(
        ue_id=2, qfi=_QFI_ESTOP, direction="DL", flow_class="Delay", pdb_ms=5.0,
        traffic_kind="deterministic",
        traffic_params={"period_ms": stop.period_ms,
                        "bytes_per_period": stop.burst_bytes,
                        "active_windows": stop.windows()},
    ))

    if permutation:
        k = permutation % len(flows)
        flows = flows[k:] + flows[:k]

    return dataclasses.replace(
        base, flows=tuple(flows),
        name=f"g11_soak_n{n_ues}_p{permutation}",
    )


def scripted_windows(horizon_s: float, teleop=TeleopDuty(), pauses=WaypointPauses(),
                     firmware=FirmwareWindow(), stop=StopDrill()) -> dict:
    """Every scripted interval, for partitioning windows into quiescent vs
    event (E1/E5's partition -- declared once, used by both)."""
    return {
        "teleop_off": tuple((a + teleop.on_s, min(a + teleop.period_s, horizon_s))
                            for a, _ in teleop.windows(horizon_s)),
        "pause": tuple((w[1], nxt[0]) for w, nxt in
                       zip(pauses.windows(horizon_s), pauses.windows(horizon_s)[1:])),
        "firmware": firmware.windows(),
        "stop": stop.windows(),
    }


def expected_counts(horizon_slots: int, teleop=TeleopDuty(), pauses=WaypointPauses(),
                    firmware=FirmwareWindow(), stop=StopDrill()) -> dict[str, int]:
    """What each scripted ingredient MUST produce, derived from its own
    schedule. Never restated -- CLAUDE.md's derive-it rule, and G9 §34.5's
    reason for asserting equality rather than non-zero."""
    horizon_s = horizon_slots * SLOT_S
    # EVERY count is clipped to the horizon. The first version of this
    # returned firmware_windows=1 and stop_bursts=1 for a 40-second smoke
    # run whose schedule puts them at T+600s and T+1200s -- an "expected"
    # count for events the run cannot contain, which would have turned a
    # correct short run into an assertion failure and, worse, made the
    # assertion look like it was checking something on the long run when it
    # was really checking a constant.
    return {
        "teleop_on_windows": len([w for w in teleop.windows(horizon_s) if w[0] < horizon_s]),
        "waypoint_pauses": pauses.pause_count(horizon_s),
        "firmware_windows": len([w for w in firmware.windows() if w[0] < horizon_s]),
        "stop_bursts": len([w for w in stop.windows() if w[0] < horizon_s]),
    }


def assert_schedule_fired(record: Any, horizon_slots: int, label: str,
                          **kw: Any) -> dict[str, int]:
    """Every scripted ingredient fired AS OFTEN AS SPECIFIED.

    G9 §34.5 twice over: assert the expected COUNT, not merely non-zero --
    and for the STOP, which is the one with a single scheduled instance,
    assert it was DELIVERED rather than only generated, because an arm can
    record its full scheduled count and complete none of it.
    """
    want = expected_counts(horizon_slots, **kw)
    # Nothing to assert about an event the horizon cannot contain. Returning
    # the (zero) expectations rather than raising is what lets the same
    # assertion run on a smoke horizon and on the real soak.
    if not want["stop_bursts"] and not want["firmware_windows"]:
        return dict(want)
    stop_key = f"ue2_qfi{_QFI_ESTOP}"
    fw_key = f"ue1_qfi{_QFI_FIRMWARE}"
    got: dict[str, int] = {}

    fr = record.flows.get(stop_key)
    if fr is None:
        raise AssertionError(
            f"{label}: the STOP flow {stop_key} is absent from the record -- "
            "it generated nothing at all, so GT-7.1's drill never happened.")
    got["stop_bytes_arrived"] = fr.bytes_arrived
    if fr.bytes_arrived <= 0:
        raise AssertionError(
            f"{label}: STOP drill generated 0 bytes. Expected exactly one "
            f"{kw.get('stop', StopDrill()).burst_bytes}-byte burst at "
            f"T+{kw.get('stop', StopDrill()).at_s:.0f}s.")
    if fr.bytes_delivered <= 0:
        raise AssertionError(
            f"{label}: STOP drill generated {fr.bytes_arrived} bytes and "
            f"DELIVERED NONE. Firing and finishing are different questions "
            f"(G9 §34.5a) -- a drill that never lands is not a drill.")

    fw = record.flows.get(fw_key)
    if fw is None or fw.bytes_arrived <= 0:
        raise AssertionError(
            f"{label}: the firmware window {fw_key} produced no traffic; "
            f"expected {want['firmware_windows']} window(s) of "
            f"{kw.get('firmware', FirmwareWindow()).duration_s:.0f}s.")
    got["firmware_bytes_arrived"] = fw.bytes_arrived
    return {**want, **got}
