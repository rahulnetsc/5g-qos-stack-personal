"""GT-1.1's teleop cell -- G1's own scenario, built because it did not exist.

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` GT-1.1:

    Assets/load: Asset A driven (M1-DL cmd_vel 20 Hz on 5QI 1 DL) **and**
    uplinking camera at nominal; Asset B runs full committed profile UL
    **plus** saturating 5QI-9 DL (firmware pull) so the DL link is genuinely
    loaded -- an idle DL link measures nothing.
    KPIs/pass: cmd_vel one-way p98 <= RAN PDB; p99.9 and max reported; zero
    command gaps >= 200 ms.

WHY A NEW BUILDER RATHER THAN A FLAG ON `sim/parametric.py`. Three of that
module's properties are wrong for GT-1.1 and none of them is a knob:

  * **no workload any guarantee is scored on carries a 5QI-1 DL flow** --
    measured, not assumed: `sim/fleet.py`'s five device profiles,
    `sim/parametric.py`, `sim/scenarios/{g9,g11,g12}.py` and the six YAML
    scenarios put 5QI 1 on UPLINK telemetry. (`scenario_config_2.yml` and
    `_5.yml` do carry a 5QI-1 DL flow, both `Delay` class with GFBR 0 -- so
    neither arms the `has_gbr` tier -- and neither is scored on.)
    `sim/parametric.py`'s own comment records why its DL command flow is
    5QI **82**: a UE cannot carry one 5QI in both directions here (see the
    collision note below), and telemetry already holds 5QI 1;
  * **its DL link is idle** -- the only DL flow is a 120 B / 50 ms control
    loop, so measured DL p98 is 2.75-4.25 ms and every arm passes by 25x.
    That is the condition GT-1.1's own text calls "measures nothing";
  * **its load axis rides a best-effort UL filler**, which cannot load a
    downlink at all.

Adding all three behind a flag would leave `sweep_scenario`'s default
behaviour intact but put GT-1.1's structure inside a builder whose
docstring promises "one workload *shape* with continuously varying knobs".
G9, G11 and G12 each got their own module for the same reason; this is the
fourth, not a new pattern.

THE ONE HARD CONSTRAINT, AND WHERE IT BITES. `FlowRecord.key` is
``ue{N}_qfi{Q}`` with **no direction term**, and `sim/buffer.py::_resolve`
raises rather than guessing when a `(ue, qfi)` is registered in two
directions (defects log #28/#30 -- a DL flow once drained a UL queue). So
one UE cannot hold the same 5QI both ways. Two consequences, both chosen
deliberately and neither hidden:

  1. **A driven robot carries cmd_vel DL on 5QI 1 and therefore no UL 5QI-1
     telemetry.** GT-1.1 gives Asset A exactly "driven ... and uplinking
     camera"; telemetry is Asset B's committed profile. So the split follows
     the test plan's own asset roles rather than working around the
     constraint. The hardware plan §1 has commands riding telemetry's bearer
     in the reverse direction and this simulator cannot represent that --
     `sim/parametric.py` records the same limitation.
  2. **The firmware-pull robot carries the 5QI-9 flood on DL and therefore
     no UL 5QI-9 filler.** The test plan names the DL pull's 5QI by number
     ("saturating 5QI-9 DL"); the UL filler's 5QI is this repo's own choice,
     so the named one wins. Both 8 and 9 are in
     `Scorecard.NON_PROTECTED_5QI`, so neither enters a protected-fleet
     statistic either way.

WHAT `committed_mult` SCALES, AND WHAT IT DOES NOT. It scales the FLEET's
committed load -- every Asset-B GBR/Delay flow's offered bytes and its
contract together, via `sim/workload.py::scale_committed_load`. It does NOT
scale cmd_vel, and that is a physical statement rather than a methodological
one: a robot asked to do more work does not receive more drive commands.
Mechanically the instrument flows are appended AFTER the scaling, so the
quantity G1 measures is fixed at every point of the load axis -- the same
separation `sim/parametric.py` gets by riding load on a filler.

THE INSTRUMENT POPULATION IS FIXED AT `n_driven`, INDEPENDENT OF `n_ues`.
If every robot were driven, "worst cmd_vel p98" would be a worst-of-N order
statistic and the UE axis would move the statistic as well as the load --
the population defect `sim/scorecard.py::Population` exists to prevent. Two
driven robots satisfies the plan's own design principle 1 (">= 2 assets in
every test") and principle 2 ("score the worst asset, never the mean") while
leaving the axis to move load alone.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional

from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.workload import min_bytes_per_period_for_gfbr, scale_committed_load
from scheduler.flow import DERIVE_PDB_FROM_5QI, LCG_UNASSIGNED, FlowConfig

__all__ = [
    "QFI_CMD", "QFI_TELEMETRY", "QFI_CAMERA", "QFI_FLEET_DL", "QFI_BG_UL",
    "QFI_FIRMWARE_DL", "CMD_PERIOD_MS", "CMD_BYTES", "CMD_GFBR_BPS",
    "RAN_PDB_MS", "GAP_BOUND_MS", "FIRMWARE_PULL_BPS", "N_DRIVEN",
    "build_gt11_scenario", "cmd_flow_keys", "assert_cmd_instrument_live",
]

# --- 5QI assignment, each with its source --------------------------------

#: The flow the guarantee is named for. Test plan §2 M1-DL: "20 Hz x 100 B
#: cmd_vel while driving", §3 G1: "5QI-1 budget". 5QI 1 is a GBR 5QI in
#: TS 23.501 Table 5.7.4-1, so the bearer carries a GFBR; PDB (100 ms) and
#: priority (20) are DERIVED from the 5QI table, never authored here.
QFI_CMD = 1
#: Asset B's telemetry, the same 5QI on the other direction -- and the
#: reason a driven robot has none (see the module docstring).
QFI_TELEMETRY = 1
#: Test plan §2 M4 XR, and every other builder in this repo.
QFI_CAMERA = 2
#: Asset B's ordinary DL control loop, so the downlink carries fleet traffic
#: and not only the flood. Same 5QI `sim/parametric.py` and `sim/fleet.py`
#: use for a DL control loop.
QFI_FLEET_DL = 82
#: Asset B's best-effort UL (logs). 5QI 9 in every other builder; kept here.
QFI_BG_UL = 9
#: GT-1.1 names this one by number: "saturating 5QI-9 DL (firmware pull)".
QFI_FIRMWARE_DL = 9

# --- the instrument ------------------------------------------------------

CMD_PERIOD_MS = 50.0        # test plan §2 M1-DL: 20 Hz
CMD_BYTES = 100.0           # test plan §2 M1-DL: 100 B
#: 100 B / 50 ms = 16 kbps. A 5QI-1 bearer is GBR and therefore has a GFBR;
#: provisioned AT the offered rate so the flow starts at contract rather
#: than under it (docs/gbr-offered-shortfall-2026-09-08.md).
CMD_GFBR_BPS = CMD_BYTES * 8.0 * 1000.0 / CMD_PERIOD_MS
#: Operator convention, matching `sim/fleet.py::_MFBR_MULTIPLE` and
#: `sim/parametric.py`'s default: burst to twice the guarantee. AUTHORED --
#: no MFBR ground truth exists in this repo.
CMD_MFBR_MULTIPLE = 2.0

#: The pass bound. Test plan §3 G1 / GT-1.1: "RAN PDB (>= 95 ms of the
#: 100 ms 5QI-1 budget)". A PROPOSED default (marked with the plan's own
#: "range" glyph), to be ratified with the client -- stated here so it is
#: one constant rather than a literal in a runner.
RAN_PDB_MS = 95.0
#: The second pass criterion, GT-1.1: "zero command gaps >= 200 ms".
GAP_BOUND_MS = 200.0

# --- the load ------------------------------------------------------------

#: "saturating". The same figure `sim/parametric.py`'s aggressor and
#: `sim/scenarios/g12.py::BG_OFFERED_BPS` use, so this cell's load is
#: comparable with theirs rather than being a third invented number.
FIRMWARE_PULL_BPS = 50_000_000.0

#: Asset B's per-robot committed profile, from `sim/parametric.py`'s own
#: factory mix so the two workloads' UL halves are the same shape.
TELEMETRY_PERIOD_MS = 100.0
TELEMETRY_BYTES = 300.0
CAMERA_PERIOD_MS = 33.0
CAMERA_GFBR_BPS = 4_000_000.0
CAMERA_FRAGMENT_BYTES = 1500          # Ethernet MTU; stated, not inherited
FLEET_DL_PERIOD_MS = 50.0
FLEET_DL_BYTES = 120.0
BG_UL_BPS = 8_000_000.0               # sim/parametric.py::_BE_PER_UE_BPS

#: How many robots are being driven. FIXED, independent of `n_ues` -- see
#: the module docstring's population note.
N_DRIVEN = 2

_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000
_NUMEROLOGY = 2
_BANDWIDTH_HZ = 40_000_000
_TDD_PATTERN = "DSUUU"


def _camera(ue_id: int) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_CAMERA, direction="UL", flow_class="GBR",
        gfbr_bps=CAMERA_GFBR_BPS, mfbr_bps=CMD_MFBR_MULTIPLE * CAMERA_GFBR_BPS,
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="xr_video",
        traffic_params={
            "period_ms": CAMERA_PERIOD_MS,
            "avg_bytes": float(min_bytes_per_period_for_gfbr(
                CAMERA_GFBR_BPS, CAMERA_PERIOD_MS)),
            "fragment_bytes": CAMERA_FRAGMENT_BYTES,
        },
    )


def build_gt11_scenario(
    *,
    seed: int,
    n_ues: int = 8,
    committed_mult: float = 1.0,
    horizon_slots: int = 40_000,
    n_driven: int = N_DRIVEN,
    firmware_pull_bps: float = FIRMWARE_PULL_BPS,
    snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-1.1's cell at one grid point.

    UE 1..n_driven are Asset A (driven); the rest are Asset B (the fleet).
    The LAST UE additionally carries the saturating 5QI-9 DL firmware pull.
    Requires at least one Asset-B robot, so `n_ues > n_driven`.
    """
    if n_driven < 1:
        raise ValueError(f"n_driven must be >= 1, got {n_driven}")
    if n_ues <= n_driven:
        raise ValueError(
            f"n_ues ({n_ues}) must exceed n_driven ({n_driven}): GT-1.1 needs "
            f"at least one Asset B to load the cell, and the firmware pull "
            f"rides on the last one")
    if firmware_pull_bps <= 0.0:
        raise ValueError(
            f"firmware_pull_bps must be > 0 (got {firmware_pull_bps}) -- "
            f"GT-1.1's own text is that an idle DL link measures nothing")

    ues = [UEConfig(ue_id=i + 1, mean_snr_db=snr_db,
                    coherence_slots=_COHERENCE_SLOTS) for i in range(n_ues)]

    # --- Asset B: the fleet. Scaled by committed_mult below. -------------
    fleet: list[FlowConfig] = []
    for ue_id in range(n_driven + 1, n_ues + 1):
        is_puller = ue_id == n_ues
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
        if not is_puller:
            # The puller's UL 5QI-9 filler is what the DL flood displaces --
            # one (ue, qfi) cannot hold two directions. See the module
            # docstring; the plan names the DL flow's 5QI and not this one.
            fleet.append(FlowConfig(
                ue_id=ue_id, qfi=QFI_BG_UL, direction="UL", flow_class="PF",
                pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
                traffic_kind="poisson", traffic_params={"rate_bps": BG_UL_BPS},
            ))

    # Asset A's camera ("uplinking camera at nominal") is committed traffic
    # and scales with the fleet; its cmd_vel does not.
    for ue_id in range(1, n_driven + 1):
        fleet.append(_camera(ue_id))

    sc = ScenarioConfig(
        name=f"gt11_n{n_ues}_d{n_driven}_cm{committed_mult:g}",
        horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=_BANDWIDTH_HZ, numerology=_NUMEROLOGY),
        tdd=TDDConfig(pattern=_TDD_PATTERN),
        ues=ues, flows=fleet, seed=seed,
    )
    scaled = scale_committed_load(sc, committed_mult)

    # --- the two flows the load axis must NOT touch ----------------------
    tail: list[FlowConfig] = []
    for ue_id in range(1, n_driven + 1):
        tail.append(FlowConfig(
            ue_id=ue_id, qfi=QFI_CMD, direction="DL", flow_class="GBR",
            gfbr_bps=CMD_GFBR_BPS, mfbr_bps=CMD_MFBR_MULTIPLE * CMD_GFBR_BPS,
            pdb_ms=DERIVE_PDB_FROM_5QI,
            traffic_kind="periodic_control",
            traffic_params={"period_ms": CMD_PERIOD_MS,
                            "bytes_per_period": CMD_BYTES},
        ))
    tail.append(FlowConfig(
        ue_id=n_ues, qfi=QFI_FIRMWARE_DL, direction="DL", flow_class="PF",
        pdb_ms=DERIVE_PDB_FROM_5QI,
        traffic_kind="poisson", traffic_params={"rate_bps": firmware_pull_bps},
    ))
    # Rebuilt through ScenarioConfig so __post_init__ re-runs the deployed
    # LCG assignment over each UE's FULL flow list -- appending to
    # `scaled.flows` would leave the instrument unresolved.
    return dataclasses.replace(
        scaled, flows=list(scaled.flows) + tail,
        name=f"{scaled.name}_gt11",
    )


def cmd_flow_keys(scenario: ScenarioConfig) -> list[str]:
    """`FlowRecord.key` for every cmd_vel flow, DERIVED from the scenario.

    The population G1's two pass criteria range over. Never a literal list:
    `n_driven` is a parameter and a restated set is this project's
    most-repeated defect (CLAUDE.md's derive-don't-restate rule)."""
    return [f"ue{f.ue_id}_qfi{f.qfi}" for f in scenario.flows
            if f.qfi == QFI_CMD and f.direction == "DL"]


def assert_cmd_instrument_live(scenario: ScenarioConfig, n_driven: int = N_DRIVEN) -> None:
    """The scenario really carries what GT-1.1 asks for.

    Not a smoke test: `docs/wp9-plan.md` §34.5's standing rule is that a
    mechanism must be shown to FIRE at the expected count, because a
    partially-degenerate cell is not a smaller sample of the same thing.
    This is its construction-time half -- the runner asserts the messages
    were actually generated.
    """
    cmds = [f for f in scenario.flows if f.qfi == QFI_CMD and f.direction == "DL"]
    if len(cmds) != n_driven:
        raise AssertionError(
            f"expected {n_driven} cmd_vel DL flows on 5QI {QFI_CMD}, found "
            f"{len(cmds)} -- the instrument G1 is named for is not in the cell")
    for f in cmds:
        if f.flow_class != "GBR" or f.gfbr_bps <= 0.0:
            raise AssertionError(
                f"{f.ue_id}/{f.qfi} is {f.flow_class} with GFBR {f.gfbr_bps} -- "
                f"5QI 1 is a GBR 5QI, and TwoTier's DL `has_gbr` tier is dead "
                f"without a target (docs/g1-stress-experiment-2026-09-09.md §0)")
    pulls = [f for f in scenario.flows
             if f.qfi == QFI_FIRMWARE_DL and f.direction == "DL"]
    if not pulls:
        raise AssertionError(
            "no saturating DL flow -- GT-1.1's own text is that an idle DL "
            "link measures nothing")
