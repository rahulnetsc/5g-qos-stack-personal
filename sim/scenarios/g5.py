"""GT-3's video cells -- G5's own scenarios, built because none existed.

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` L99 (the G5 catalogue row):

    >= 99 % of PDU sets complete within PDB; frame age at MEC p95 <=
    2 frame periods (67 ms); per-feed goodput >= GFBR in every 2 s window.

and its three sub-tests:

    GT-3.1  one camera under contention (lidar + background saturation)
    GT-3.2  the whole committed portfolio, stepped -- the CELL CEILING
    GT-3.3  a cell-edge asset, the containment test

--------------------------------------------------------------------------
WHAT IS DIFFERENT ABOUT THIS FAMILY
--------------------------------------------------------------------------

**The instrument is a GBR video feed, not a heartbeat.** G1/G2 score a
downlink control message and G3 scores an uplink heartbeat's *silence*; G5
scores a stream's *completeness, freshness and rate*, which are three
different statistics over the same flow and can fail independently.

**AND ONE OF THE THREE HAS NO RUN-LEVEL FORM.** Part 3 is *"goodput >= GFBR in
EVERY 2 s window"*. `M08` is `min_f(delivered_f / GFBR_f)` -- a minimum over
flows and a MEAN over time -- so a run-level 0.99 can contain a 2 s window at
0.2 and read as a pass. `M23 windowed_gfbr_floor` was added for this clause
(`config/metric_panel.yml`, appended not redefined) and is the statistic GT-3.2
reads its ceiling off. See `docs/g5-step0-2026-09-10.md` sec 1.1.

--------------------------------------------------------------------------
THE POPULATION, AND WHY IT IS TWO CLASSES
--------------------------------------------------------------------------

GT-3.1's KPI line ends *"A and B telemetry unharmed"*. So this campaign scores
**two flow classes with different bounds**:

  * **parts 1-3** on Asset A's camera -- the instrument;
  * **part 4** on every robot's telemetry -- the collateral check.

A camera that meets its own KPIs by starving the telemetry beside it fails the
guarantee and passes parts 1-3, which is exactly why the fourth part is not
dropped as a detail.

**The load is NOT scored.** The lidar and the 5QI-9 background exist to create
contention; their own starvation is by design. Scoring them would repeat the
defect that produced G3's withdrawn row -- an aggregate over every flow read as
a statement about the protected fleet.

--------------------------------------------------------------------------
THE FRAGMENTATION TRAP IN GT-3.2, avoided by construction
--------------------------------------------------------------------------

GT-3.2 steps offered rates x1.0 -> x1.5. **`FlowConfig.aggressor_multiplier` is
the wrong knob**: `CLAUDE.md`'s own known-issues list records that it scales an
`xr_video` flow's fragments AFTER `sim/traffic.py::_gen_xr_video` has already
fragmented the frame, so a scaled fragment can exceed `fragment_bytes` and
break that generator's MTU-cap claim. This module scales
`traffic_params["avg_bytes"]` BEFORE fragmentation, which is the documented
workaround, and `_camera` takes no multiplier argument at all so the wrong knob
is not reachable from here.

--------------------------------------------------------------------------
OFFERED >= GFBR, derived rather than authored
--------------------------------------------------------------------------

`sim/workload.py::min_bytes_per_period_for_gfbr` sizes the camera's frame so
its offered load is at least its own contract. A flow offering less than it was
promised has an arithmetic ceiling on `gfbr_fraction` below 1.0 that no
scheduler can lift, and every contract-reading metric then measures the traffic
generator instead (`docs/gbr-offered-shortfall-2026-09-08.md`). M23 reads the
contract, so this module cannot inherit that defect.
"""
from __future__ import annotations

import dataclasses
from typing import Optional, Sequence

from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.workload import min_bytes_per_period_for_gfbr, scale_committed_load
from scheduler.flow import DERIVE_PDB_FROM_5QI, LCG_UNASSIGNED, FlowConfig

__all__ = [
    "build_gt31_scenario", "build_gt32_scenario", "build_gt33_scenario",
    "QFI_TELEMETRY", "QFI_CAMERA", "QFI_LIDAR", "QFI_BG_UL", "QFI_FLEET_DL",
    "CAMERA_FPS", "CAMERA_GFBR_BPS", "CAMERA_PDB_MS", "FRAME_AGE_BOUND_MS",
    "PDU_SET_BUDGET_MS", "PDU_SET_COMPLETE_FRACTION", "GFBR_WINDOW_S",
    "LIDAR_GFBR_BPS", "BG_UL_BPS", "LOAD_STEPS",
    "camera_flow_key", "telemetry_flow_keys", "instrument_ue_id",
    "frame_age_bound_ms",
]

# --- the instrument, from test plan sec 2.1's asset -> 5QI table ----------
QFI_TELEMETRY = 1        # T1 telemetry (UL), 5QI 1 -- part 4's population
QFI_CAMERA = 2           # T3 camera (UL), 5QI 2 -- the instrument
QFI_LIDAR = 4            # T4 lidar (UL), 5QI 4 -- load, never scored
QFI_FLEET_DL = 82        # T2 fleet control (DL)
QFI_BG_UL = 9            # T6 best-effort (UL), 5QI 9 -- load, never scored

#: GT-3.1: *"Asset A camera at nominal (M4, 30 fps, 4 Mbps)"*.
CAMERA_FPS = 30.0
CAMERA_GFBR_BPS = 4_000_000.0
CAMERA_PERIOD_MS = 1000.0 / CAMERA_FPS      # 33.33 ms, DERIVED from fps
#: 5QI 2's standardised PDB. GT-3.1 states the set budget as 150 ms directly.
CAMERA_PDB_MS = 150.0
PDU_SET_BUDGET_MS = 150.0
PDU_SET_COMPLETE_FRACTION = 0.99
#: Test plan sec 2.1's own MFBR multiple, as G3 uses.
MFBR_MULTIPLE = 2.0
#: The Ethernet MTU -- the one physically-grounded fragment size available,
#: stated rather than inherited (`sim/traffic.py` has no default, by design).
FRAGMENT_BYTES = 1500

#: Part 3's window, from GT-3.1/GT-3.2's own wording. The scorer reads it from
#: `config/metric_panel.yml::defaults.gfbr_window_s`; this constant exists so a
#: scenario-side assertion can check the two agree rather than drift.
GFBR_WINDOW_S = 2.0

#: The lidar, duty-cycle-free here. `sim/fleet.py` models lidar as an EVENT
#: (LIDAR_ACTIVE_BPS = 12 Mbps, activated per task) because a permanently
#: downscaled continuous feed would misrepresent a large transient as a small
#: steady demand. GT-3.1 wants sustained contention rather than a transient, so
#: this is the LDRP-class active rate offered continuously and labelled as a
#: deliberate departure -- not a re-derivation of that module's own choice.
LIDAR_GFBR_BPS = 12_000_000.0
LIDAR_PERIOD_MS = 10.0
LIDAR_PDB_MS = DERIVE_PDB_FROM_5QI

#: The 5QI-9 background saturation GT-3.1 names. Matches G3's own
#: `FLOOD_UL_BPS`, so "saturating" means the same thing across guarantees --
#: large enough that the queue never empties without being so large that an
#: unbounded backlog dominates the run's memory (G3's campaign came within
#: 1.5 GB of an OOM kill on exactly this flow).
BG_UL_BPS = 50_000_000.0

#: GT-3.2: *"stepped x1.0 -> x1.5 in 0.1 steps"*. DERIVED as a range so the
#: count is computed, never restated (CLAUDE.md's derive-don't-restate rule).
LOAD_STEPS = tuple(round(1.0 + 0.1 * i, 1) for i in range(6))

_BANDWIDTH_HZ = 40_000_000
_NUMEROLOGY = 2
_TDD_PATTERN = "DSUUU"
_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000

#: UE 1 is Asset A, the instrument, exactly as in G3. Fixed rather than
#: worst-of-N: if every robot were the instrument, "worst frame age" would be
#: an order statistic and the fleet axis would move the statistic as well as
#: the load.
_INSTRUMENT_UE = 1


def instrument_ue_id(scenario: ScenarioConfig) -> int:
    """Asset A. A function rather than a bare constant so a caller cannot
    quietly assume a different robot is the instrument."""
    return _INSTRUMENT_UE


def camera_flow_key(scenario: ScenarioConfig) -> str:
    return f"ue{_INSTRUMENT_UE}_qfi{QFI_CAMERA}"


def telemetry_flow_keys(scenario: ScenarioConfig) -> list[str]:
    """Part 4's population: EVERY robot's telemetry, not just Asset A's.

    GT-3.1 says *"A and B telemetry unharmed"*, so the collateral check ranges
    over both assets. Derived from the scenario's own flow list rather than
    from `n_ues`, so a builder change cannot silently shrink it.
    """
    return sorted(
        f"ue{f.ue_id}_qfi{f.qfi}"
        for f in scenario.flows
        if f.qfi == QFI_TELEMETRY and f.direction == "UL"
    )


def frame_age_bound_ms(fps: float = CAMERA_FPS) -> float:
    """Two frame periods. DERIVED from the frame rate, never the sheet's
    rounded 67 ms -- if the camera's fps changes this moves with it."""
    return 2.0 * 1000.0 / fps


FRAME_AGE_BOUND_MS = frame_age_bound_ms()


# --- the flows ------------------------------------------------------------

def _camera(ue_id: int, *, offer_mult: float = 1.0) -> FlowConfig:
    """The instrument. `offer_mult` scales AVG_BYTES, before fragmentation.

    See the module docstring: `aggressor_multiplier` would scale the produced
    fragments instead and break `_gen_xr_video`'s own MTU cap, which is the
    one knob GT-3.2's ramp must not use.
    """
    base = max(
        float(min_bytes_per_period_for_gfbr(CAMERA_GFBR_BPS, CAMERA_PERIOD_MS)),
        1.0,
    )
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_CAMERA, direction="UL", flow_class="GBR",
        gfbr_bps=CAMERA_GFBR_BPS, mfbr_bps=MFBR_MULTIPLE * CAMERA_GFBR_BPS,
        pdb_ms=CAMERA_PDB_MS, lcg=LCG_UNASSIGNED,
        traffic_kind="xr_video",
        traffic_params={
            "period_ms": CAMERA_PERIOD_MS,
            "avg_bytes": base * offer_mult,
            "fragment_bytes": FRAGMENT_BYTES,
        },
    )


def _telemetry(ue_id: int) -> FlowConfig:
    """Part 4's population. GBR, for the reason G3 established: 5QI 1 IS a GBR
    5QI (TS 23.501 Table 5.7.4-1), so a 5QI-1 bearer with no GFBR is an
    infidelity. Offered == GFBR, the unique point satisfying both sec 5's
    "within GFBR" and this repo's offered>=contract invariant."""
    gfbr = 300.0 * 8.0 * 1000.0 / 100.0        # 300 B every 100 ms
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_TELEMETRY, direction="UL", flow_class="GBR",
        gfbr_bps=gfbr, mfbr_bps=MFBR_MULTIPLE * gfbr,
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="periodic_control",
        traffic_params={"period_ms": 100.0, "bytes_per_period": 300},
    )


def _lidar(ue_id: int, *, offer_mult: float = 1.0) -> FlowConfig:
    """Load. Never scored -- see the module docstring."""
    base = max(
        float(min_bytes_per_period_for_gfbr(LIDAR_GFBR_BPS, LIDAR_PERIOD_MS)),
        1.0,
    )
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_LIDAR, direction="UL", flow_class="GBR",
        gfbr_bps=LIDAR_GFBR_BPS, mfbr_bps=MFBR_MULTIPLE * LIDAR_GFBR_BPS,
        pdb_ms=LIDAR_PDB_MS, lcg=LCG_UNASSIGNED,
        traffic_kind="periodic_control",
        traffic_params={"period_ms": LIDAR_PERIOD_MS,
                        "bytes_per_period": int(base * offer_mult)},
    )


def _bg_ul(ue_id: int) -> FlowConfig:
    """The 5QI-9 saturator. Load, never scored."""
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_BG_UL, direction="UL", flow_class="PF",
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="periodic_control",
        traffic_params={"period_ms": 1.0,
                        "bytes_per_period": int(BG_UL_BPS / 8.0 / 1000.0)},
    )


def _fleet_dl(ue_id: int) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_FLEET_DL, direction="DL", flow_class="Delay",
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="periodic_control",
        traffic_params={"period_ms": 50.0, "bytes_per_period": 100},
    )


# --- the cell -------------------------------------------------------------

def _cell(*, seed: int, n_ues: int, horizon_slots: int, name: str,
          camera_offer_mult: float, lidar_ues: Sequence[int],
          bg_ues: Sequence[int], committed_mult: float,
          snr_db: float, edge_ue: Optional[int], edge_snr_db: float,
          ) -> ScenarioConfig:
    """One GT-3 cell. UE 1 is Asset A (the instrument); the rest are Asset B."""
    if n_ues < 2:
        raise ValueError(
            f"n_ues must be >= 2, got {n_ues}: test plan sec 4's first design "
            f"principle is '>= 2 assets in every test'")
    if edge_ue is not None and edge_ue == _INSTRUMENT_UE:
        raise ValueError(
            f"edge_ue={edge_ue} is Asset A, the instrument -- GT-3.3's hard "
            f"criterion is that A is UNCHANGED while B degrades, so the "
            f"degraded robot must be a neighbour's")

    ues = [
        UEConfig(
            ue_id=i + 1,
            mean_snr_db=(edge_snr_db if (edge_ue is not None and i + 1 == edge_ue)
                         else snr_db),
            coherence_slots=_COHERENCE_SLOTS,
        )
        for i in range(n_ues)
    ]

    # The committed fleet, which `committed_mult` scales.
    fleet: list[FlowConfig] = []
    for ue_id in range(1, n_ues + 1):
        fleet.append(_fleet_dl(ue_id))
        if ue_id in lidar_ues:
            fleet.append(_lidar(ue_id))
        if ue_id in bg_ues:
            fleet.append(_bg_ul(ue_id))

    sc = ScenarioConfig(
        name=name, horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=_BANDWIDTH_HZ,
                              numerology=_NUMEROLOGY),
        tdd=TDDConfig(pattern=_TDD_PATTERN),
        ues=ues, flows=fleet, seed=seed,
    )
    scaled = scale_committed_load(sc, committed_mult)

    # THE SCORED FLOWS ARE APPENDED AFTER SCALING, exactly as G3 does, so the
    # quantities G5 measures are identical at every point of a load axis that
    # is meant to vary the LOAD. GT-3.2's ramp scales the camera through its
    # own `camera_offer_mult` instead, which is the offered-rate step the
    # sub-test actually specifies.
    tail: list[FlowConfig] = []
    for ue_id in range(1, n_ues + 1):
        tail.append(_telemetry(ue_id))
        tail.append(_camera(ue_id, offer_mult=camera_offer_mult))

    # ORDERED CANONICALLY BEFORE THE LCG PASS, and the ordinals cleared first.
    # Same reason as G3: LCG = DRB ID, the simulator's proxy for DRB setup
    # order is position in the UE's flow list, and `assign_deployed_lcgs`
    # keeps an explicit LCG while still spending an ordinal -- so a second
    # pass over a partially-resolved list can land two flows on one LCG.
    # Measured directly while building G3's module.
    _rank = {QFI_TELEMETRY: 0, QFI_CAMERA: 1, QFI_LIDAR: 2, QFI_FLEET_DL: 3}
    flows = sorted(
        [dataclasses.replace(f, lcg=LCG_UNASSIGNED)
         for f in list(scaled.flows) + tail],
        key=lambda f: (f.ue_id, _rank.get(f.qfi, 4)))

    return dataclasses.replace(scaled, flows=flows, name=name)


def build_gt31_scenario(
    *, seed: int, n_ues: int = 6, horizon_slots: int = 40_000,
    committed_mult: float = 1.0, snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-3.1 -- one camera's frames under lidar and background contention.

    *"Asset A camera at nominal (M4, 30 fps, 4 Mbps) -- instrument; Asset B
    lidar (M3) + bg UL saturation -- load."*

    The lidar rides Asset B (UE 2) and the background saturation rides every
    robot except the instrument, so Asset A's own uplink carries only its
    committed profile -- otherwise the contention would be intra-UE and this
    would be GT-2.1 with a camera instrument.
    """
    return _cell(
        seed=seed, n_ues=n_ues, horizon_slots=horizon_slots,
        name=f"gt31_n{n_ues}_cm{committed_mult:g}",
        camera_offer_mult=1.0,
        lidar_ues=(2,) if n_ues >= 2 else (),
        # ASSET B ALONE carries the saturator, not every neighbour: GT-3.1
        # names "Asset B lidar + bg UL saturation", one asset. Spreading it
        # over the whole fleet would make the fleet axis vary the offered
        # background load as well as the contention, confounding the two.
        bg_ues=(2,) if n_ues >= 2 else (),
        committed_mult=committed_mult, snr_db=snr_db,
        edge_ue=None, edge_snr_db=snr_db,
    )


def build_gt32_scenario(
    *, seed: int, load_mult: float, n_ues: int = 6,
    horizon_slots: int = 40_000, snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-3.2 -- the committed portfolio, stepped. THE CELL CEILING.

    *"both assets, all committed flows at nominal, then stepped x1.0 -> x1.5
    in 0.1 steps; NO bg."*

    `load_mult` scales BOTH the camera's offered rate and the committed fleet,
    which is what *"all committed flows ... stepped"* means -- stepping only
    the instrument would measure the instrument's own headroom rather than the
    cell's. **No background flow**, by the sub-test's own wording: the ceiling
    is a property of the committed portfolio, and a saturating non-GBR flow
    would make it a property of the aggressor instead.
    """
    if load_mult <= 0.0:
        raise ValueError(f"load_mult must be > 0, got {load_mult}")
    return _cell(
        seed=seed, n_ues=n_ues, horizon_slots=horizon_slots,
        name=f"gt32_n{n_ues}_x{load_mult:g}",
        camera_offer_mult=load_mult,
        lidar_ues=(2,) if n_ues >= 2 else (),
        bg_ues=(),                     # NO bg -- the sub-test says so
        committed_mult=load_mult, snr_db=snr_db,
        edge_ue=None, edge_snr_db=snr_db,
    )


def build_gt33_scenario(
    *, seed: int, edge_snr_db: float, n_ues: int = 6,
    horizon_slots: int = 40_000, committed_mult: float = 1.0,
    snr_db: float = _BASE_SNR_DB, edge_ue: int = 2,
) -> ScenarioConfig:
    """GT-3.3 -- a cell-edge asset, and whether its degradation is contained.

    *"Asset B behind reduced SNR; Asset A nominal. Both full profile."*

    **The hard criterion is containment, not B's own curve**: A's full SLO set
    unchanged within epsilon while B degrades. B's feed satisfaction against
    SNR is a characterisation curve with no fixed pass, so a runner must not
    report a B failure as a G5 failure.
    """
    return _cell(
        seed=seed, n_ues=n_ues, horizon_slots=horizon_slots,
        name=f"gt33_n{n_ues}_edge{edge_snr_db:g}",
        camera_offer_mult=1.0,
        lidar_ues=(2,) if n_ues >= 2 else (),
        bg_ues=(2,) if n_ues >= 2 else (),
        committed_mult=committed_mult, snr_db=snr_db,
        edge_ue=edge_ue, edge_snr_db=edge_snr_db,
    )
