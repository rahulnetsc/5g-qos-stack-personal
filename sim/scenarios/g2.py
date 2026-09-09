"""GT-1.2's emergency-stop cell -- G2's own scenario, built because the one
thing GT-1.2 exists to test has never happened here.

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` GT-1.2:

    Functional view: the disconnect-safety path (master drop => STOP to all
    ground assets) is the single highest-consequence packet in the system.
    Two assets receive STOP **simultaneously**, so this also exercises
    same-slot DL contention for the two highest-priority packets in the cell.
    Assets/load: both assets at full committed profile; cell saturated both
    directions with 5QI-9 (worst legal case). Trigger: scripted
    master-disconnect -> simultaneous STOP datagrams to A and B.
    Procedure: 30 trials/run, >= 10 runs, randomised trigger phase within the
    frame.
    KPIs/pass: 100 % of STOPs <= 100 ms one-way at both assets in every
    trial; per-trial worst asset recorded.

THREE THINGS DID NOT EXIST, all measured rather than assumed
(`docs/g2-step0-2026-09-09.md`):

  * **SIMULTANEITY.** The only STOP flow in the repo is `sim/fleet.py`'s
    UGV 5QI-85 `aperiodic_event`, which draws an independent per-slot
    Bernoulli per flow. At its real 0.2 Hz cadence, **17 STOP events landed
    in 17 distinct slots and no slot ever held two.** The same-slot DL
    contention GT-1.2 is written to exercise has never occurred. Fixed by
    `sim/traffic.py`'s `scripted_burst`, whose trigger list is SHARED, so
    simultaneity is structural rather than lucky.
  * **THE SATURATED CELL.** GT-1.2 says "saturated both directions with
    5QI-9, the worst legal case". No scenario in the repo saturates the
    downlink except `sim/scenarios/g1.py` (built 2026-09-09), and none
    saturates both. Both floods are here.
  * **TRIALS.** GT-1.2 counts trials, not seconds. `aperiodic_event` yields
    a Poisson count that varies per run; a scripted list makes the trial
    count `len(trigger_slots)` -- derived, assertable, and impossible to
    truncate silently (defects-log #23).

WHAT THIS REUSES RATHER THAN REWRITES. `sim/scenarios/g1.py` built GT-1.1's
saturating 5QI-9 DL firmware pull and the fixed-instrument-population
discipline; both are taken directly, and the committed profile is the same
shape so G1's and G2's cells differ only in what GT-1.2 adds. The 5QI
de-aliasing rule is `sim/scenarios/g12.py`'s (`QFI_BG` DL vs `QFI_BG_UL`),
for the same `(ue, qfi)`-keying reason.

THE 5 ms / 100 ms SPLIT, AND WHY THE SCENARIO CARRIES BOTH. 5QI 85's
STANDARDISED PDB is **5 ms**; G2's clause bound is **100 ms**. Those are
different quantities and `sim/buffer.py::expire()` enforces the first:
a STOP older than its PDB is DISCARDED and recorded `complete=False`, so it
never reaches a latency percentile at all. Measured: the largest DELIVERED
STOP latency across every arm and load is **5.25 ms** -- one slot past the
PDB -- while Reservation silently discarded **87 of 1 607**. So a clause
scored as a latency percentile against 100 ms **cannot fail**, and the real
misses are drops. `stop_pdb_ms` therefore exists: at `DERIVE_PDB_FROM_5QI`
(the default) the cell is faithful and a late STOP is a drop; set to 100.0
it is the DIAGNOSTIC that asks *when would that STOP have arrived had the
bearer not thrown it away* -- a question the faithful configuration cannot
answer and an operator needs answered.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Sequence

import numpy as np

from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.scenarios.schedule_guard import require_horizon
from sim.workload import min_bytes_per_period_for_gfbr, scale_committed_load
from scheduler.flow import DERIVE_PDB_FROM_5QI, LCG_UNASSIGNED, FlowConfig

__all__ = [
    "QFI_STOP", "QFI_TELEMETRY", "QFI_CAMERA", "QFI_FLEET_DL",
    "QFI_FLOOD_DL", "QFI_FLOOD_UL", "STOP_BYTES", "STOP_BOUND_MS",
    "N_TRIALS", "TRIAL_SPACING_MS", "SETTLE_MS", "FLOOD_DL_BPS", "FLOOD_UL_BPS",
    "TDD_PERIOD_SLOTS", "trial_slots", "minimum_horizon_slots",
    "build_gt12_scenario",
    "stop_flow_keys", "assert_stop_instrument_live",
]

# --- 5QI assignment, each with its source --------------------------------

#: `sim/fleet.py`'s UGV E-STOP: "tiniest payload, tightest PDB in the panel
#: (5 ms)". Standardised PDB 5 ms and priority 21 (TS 23.501), both DERIVED.
QFI_STOP = 85
#: The committed profile, same shapes as `sim/scenarios/g1.py`.
QFI_TELEMETRY = 1
QFI_CAMERA = 2
QFI_FLEET_DL = 82
#: GT-1.2 names the saturating class by number: "5QI-9, the worst legal case".
QFI_FLOOD_DL = 9
#: The uplink half of "saturated both directions". 5QI **8**, not 9, for the
#: same reason `sim/scenarios/g12.py::QFI_BG_UL` is 8: one UE cannot carry a
#: 5QI in both directions (`sim/buffer.py::_resolve` raises, defects-log
#: #28/#30). Both 8 and 9 are in `Scorecard.NON_PROTECTED_5QI`, so the
#: substitution is invisible to every protected-fleet statistic.
QFI_FLOOD_UL = 8

# --- the instrument ------------------------------------------------------

#: `sim/fleet.py`'s own E-STOP payload.
STOP_BYTES = 40
#: G2's clause bound, test plan L96 and GT-1.2: "100 % of STOPs <= 100 ms
#: one-way". A PROPOSED default (the plan marks it with its own glyph).
#: NOT the bearer's PDB -- see the module docstring's 5/100 note.
STOP_BOUND_MS = 100.0
#: GT-1.2: "30 trials/run".
N_TRIALS = 30
#: Spacing between trials. Chosen, and the constraint is stated: it must
#: exceed `STOP_BOUND_MS` by enough that a trial's outcome cannot be confused
#: with its neighbour's, since a trial is scored by looking for a completion
#: in the window after its trigger. 250 ms is 2.5x the bound.
TRIAL_SPACING_MS = 250.0
#: Let the cell reach steady state before the first disconnect. The floods
#: are unbounded queues; triggering into an empty cell would measure a
#: transient rather than "worst-case load".
SETTLE_MS = 1000.0
#: The DSUUU period. A STOP landing just before a D-slot waits differently
#: from one landing just after, so the trigger phase is randomised over
#: exactly this -- GT-1.2's "randomised trigger phase within the frame".
TDD_PERIOD_SLOTS = 5

# --- the load ------------------------------------------------------------

#: "saturating", the same figure `sim/scenarios/g1.py::FIRMWARE_PULL_BPS`,
#: `sim/scenarios/g12.py::BG_OFFERED_BPS` and `sim/parametric.py`'s aggressor
#: all use, so this cell's load is comparable with theirs.
FLOOD_DL_BPS = 50_000_000.0
FLOOD_UL_BPS = 50_000_000.0

TELEMETRY_PERIOD_MS = 100.0
TELEMETRY_BYTES = 300.0
CAMERA_PERIOD_MS = 33.0
CAMERA_GFBR_BPS = 4_000_000.0
CAMERA_FRAGMENT_BYTES = 1500
FLEET_DL_PERIOD_MS = 50.0
FLEET_DL_BYTES = 120.0
_MFBR_MULTIPLE = 2.0

_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000
_NUMEROLOGY = 2
_BANDWIDTH_HZ = 40_000_000
_TDD_PATTERN = "DSUUU"


def trial_slots(
    seed: int,
    n_trials: int = N_TRIALS,
    spacing_ms: float = TRIAL_SPACING_MS,
    settle_ms: float = SETTLE_MS,
    numerology: int = _NUMEROLOGY,
) -> tuple[int, ...]:
    """The scripted master-disconnect instants, with randomised phase.

    Trial `k` fires at `settle + k*spacing + phase_k`, where `phase_k` is
    drawn uniformly over the TDD period. So trials stay evenly spaced and
    ordered -- which is what makes a completion attributable to its own
    trial -- while the WITHIN-FRAME ALIGNMENT varies, which is the thing
    GT-1.2 asks to be randomised and the thing that actually changes how
    long a STOP waits for a D-slot.

    Its own RNG stream, XOR'd off the scenario seed per CLAUDE.md's
    independent-seed rule: the trigger schedule must not consume draws that
    would shift channel or traffic realisations.
    """
    slot_ms = 1.0 / (2 ** numerology)
    rng = np.random.default_rng(int(seed) ^ 0x570F0FF)
    base = int(round(settle_ms / slot_ms))
    step = int(round(spacing_ms / slot_ms))
    phases = rng.integers(0, TDD_PERIOD_SLOTS, size=n_trials)
    return tuple(int(base + k * step + int(phases[k])) for k in range(n_trials))


def minimum_horizon_slots(seed: int, n_trials: int = N_TRIALS) -> int:
    """The shortest horizon that can SCORE this trial schedule.

    DERIVED from the schedule, never restated: the last disconnect's own
    100 ms scoring window has to close inside the run, or that trial fired
    without being answerable -- which is defects-log #23 with the truncation
    moved from the event to its measurement.
    """
    slot_ms = 1.0 / (2 ** _NUMEROLOGY)
    return trial_slots(seed, n_trials=n_trials)[-1] + int(
        round(STOP_BOUND_MS / slot_ms)) + 1


def _camera(ue_id: int) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_CAMERA, direction="UL", flow_class="GBR",
        gfbr_bps=CAMERA_GFBR_BPS, mfbr_bps=_MFBR_MULTIPLE * CAMERA_GFBR_BPS,
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="xr_video",
        traffic_params={
            "period_ms": CAMERA_PERIOD_MS,
            "avg_bytes": float(min_bytes_per_period_for_gfbr(
                CAMERA_GFBR_BPS, CAMERA_PERIOD_MS)),
            "fragment_bytes": CAMERA_FRAGMENT_BYTES,
        },
    )


def build_gt12_scenario(
    *,
    seed: int,
    n_ues: int = 8,
    n_stop: int = 2,
    committed_mult: float = 1.0,
    horizon_slots: int = 40_000,
    n_trials: int = N_TRIALS,
    stop_pdb_ms: float = DERIVE_PDB_FROM_5QI,
    flood_dl_bps: float = FLOOD_DL_BPS,
    flood_ul_bps: float = FLOOD_UL_BPS,
    snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-1.2's cell at one grid point.

    `n_stop` robots receive the STOP, **all in the same slot**, on each of
    `n_trials` scripted trials. GT-1.2's own number is 2; the guarantee's own
    wording is *"on every ground robot"*, so `n_stop` is an axis and 2 is its
    minimum interesting value, not its maximum.
    """
    if n_stop < 1:
        raise ValueError(f"n_stop must be >= 1, got {n_stop}")
    if n_stop > n_ues:
        raise ValueError(
            f"n_stop ({n_stop}) exceeds n_ues ({n_ues}): the grid is "
            f"triangular -- a cell cannot STOP more robots than it carries")
    if n_ues < 1:
        raise ValueError(f"n_ues must be >= 1, got {n_ues}")

    slots = trial_slots(seed, n_trials=n_trials)
    # THE SHARED guard, not a private one. A trial whose 100 ms scoring
    # window runs past the horizon is not a shorter experiment, it is an
    # unscoreable trial -- and `last_event_slot` is the END of that window,
    # DERIVED, because a trigger that fires one slot before the horizon has
    # fired without being answerable.
    require_horizon(
        "GT-1.2", last_event_slot=minimum_horizon_slots(seed, n_trials) - 1,
        horizon_slots=horizon_slots,
        detail=(f"The last of {n_trials} scripted disconnects fires at slot "
                f"{slots[-1]} and its {STOP_BOUND_MS:g} ms window closes "
                f"after it. "))

    ues = [UEConfig(ue_id=i + 1, mean_snr_db=snr_db,
                    coherence_slots=_COHERENCE_SLOTS) for i in range(n_ues)]

    # --- the committed profile, on every robot. Scaled below. ------------
    fleet: list[FlowConfig] = []
    for ue_id in range(1, n_ues + 1):
        fleet.append(FlowConfig(
            ue_id=ue_id, qfi=QFI_TELEMETRY, direction="UL", flow_class="Delay",
            pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
            traffic_kind="periodic_control",
            traffic_params={"period_ms": TELEMETRY_PERIOD_MS,
                            "bytes_per_period": TELEMETRY_BYTES},
        ))
        fleet.append(_camera(ue_id))
        fleet.append(FlowConfig(
            ue_id=ue_id, qfi=QFI_FLEET_DL, direction="DL", flow_class="Delay",
            pdb_ms=DERIVE_PDB_FROM_5QI,
            traffic_kind="periodic_control",
            traffic_params={"period_ms": FLEET_DL_PERIOD_MS,
                            "bytes_per_period": FLEET_DL_BYTES},
        ))

    sc = ScenarioConfig(
        name=(f"gt12_n{n_ues}_stop{n_stop}_t{n_trials}"
              f"_cm{committed_mult:g}"),
        horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=_BANDWIDTH_HZ, numerology=_NUMEROLOGY),
        tdd=TDDConfig(pattern=_TDD_PATTERN),
        ues=ues, flows=fleet, seed=seed,
    )
    scaled = scale_committed_load(sc, committed_mult)

    # --- what the load axis must NOT touch -------------------------------
    tail: list[FlowConfig] = []
    for ue_id in range(1, n_stop + 1):
        tail.append(FlowConfig(
            ue_id=ue_id, qfi=QFI_STOP, direction="DL", flow_class="Delay",
            pdb_ms=stop_pdb_ms,
            traffic_kind="scripted_burst",
            traffic_params={"trigger_slots": slots, "burst_bytes": STOP_BYTES},
        ))
    # "saturated both directions with 5QI-9, the worst legal case". The
    # floods ride the LAST UE, which therefore carries no committed 5QI-9 of
    # its own -- there is none in this profile, so unlike G1 nothing is
    # displaced. One UE rather than all, so a shift in the STOP statistics is
    # attributable to the flood rather than to every robot having gained one.
    tail.append(FlowConfig(
        ue_id=n_ues, qfi=QFI_FLOOD_DL, direction="DL", flow_class="PF",
        pdb_ms=DERIVE_PDB_FROM_5QI, traffic_kind="poisson",
        traffic_params={"rate_bps": flood_dl_bps}))
    tail.append(FlowConfig(
        ue_id=n_ues, qfi=QFI_FLOOD_UL, direction="UL", flow_class="PF",
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="poisson", traffic_params={"rate_bps": flood_ul_bps}))

    return dataclasses.replace(
        scaled, flows=list(scaled.flows) + tail, name=f"{scaled.name}_gt12")


def stop_flow_keys(scenario: ScenarioConfig) -> list[str]:
    """`FlowRecord.key` for every STOP flow, DERIVED from the scenario.

    The population G2's clause ranges over. `n_stop` is an axis, so a
    restated list would drift the moment it moved -- CLAUDE.md's
    derive-don't-restate rule."""
    return [f"ue{f.ue_id}_qfi{f.qfi}" for f in scenario.flows
            if f.qfi == QFI_STOP and f.direction == "DL"]


def assert_stop_instrument_live(
    scenario: ScenarioConfig, n_stop: int, n_trials: int = N_TRIALS
) -> None:
    """The cell really carries what GT-1.2 asks for, and SIMULTANEOUSLY.

    The count assertion is `docs/wp9-plan.md` §34.5's standing rule -- a
    partially-degenerate run is not a smaller sample of the same thing. The
    SHARED-SCHEDULE assertion is the one specific to G2: it is the property
    the whole test is about, and the property `aperiodic_event` silently
    lacked.
    """
    stops = [f for f in scenario.flows
             if f.qfi == QFI_STOP and f.direction == "DL"]
    if len(stops) != n_stop:
        raise AssertionError(
            f"expected {n_stop} STOP flows on 5QI {QFI_STOP}, found "
            f"{len(stops)} -- the instrument G2 is named for is not in the cell")
    schedules = {tuple(f.traffic_params["trigger_slots"]) for f in stops}
    if len(schedules) != 1:
        raise AssertionError(
            f"{len(schedules)} distinct STOP schedules -- GT-1.2's whole "
            f"mechanism is that every ground robot is stopped in the SAME "
            f"slot, and these are not simultaneous")
    only = next(iter(schedules))
    if len(only) != n_trials:
        raise AssertionError(
            f"{len(only)} trigger slots, expected {n_trials} trials")
    if len(set(only)) != len(only):
        raise AssertionError("duplicate trigger slots -- two trials would "
                             "share one instant and be indistinguishable")
    floods = {(f.qfi, f.direction) for f in scenario.flows
              if f.qfi in (QFI_FLOOD_DL, QFI_FLOOD_UL)}
    if {(QFI_FLOOD_DL, "DL"), (QFI_FLOOD_UL, "UL")} - floods:
        raise AssertionError(
            "GT-1.2 requires the cell saturated in BOTH directions; found "
            f"only {sorted(floods)}")
