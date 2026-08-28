"""Parametric sweep-scenario factory (WP9, `docs/wp9-plan.md` build item B4).

What this module is for: turning one WP9 grid cell's axis values into a
`ScenarioConfig`. `scripts/regime_sweep.py::sweep()` takes a
`build_scenario(**axis_values, seed=seed)` callable precisely because how
axes map onto a scenario is scenario-specific; this is WP9's own such
callable.

What it is **not**: a member of `sim/scenarios/`'s registry. That package's
contract is "drop a `scenario_config_<n>.yml` file in the directory and
`scenario(n)` loads it" -- a fixed workload, hand-authored, one file per
scenario, suitable for a regression corpus that must not move. WP9 needs the
opposite: one workload *shape* with continuously varying knobs, constructed
in Python, never captured into the corpus. Keeping it out of that package
keeps `scenario(n)`'s meaning intact.

Every default here is the base point of `docs/wp9-plan.md` §1, so
`sweep_scenario(seed=s)` with no other argument IS the base cell, and every
excursion is one keyword away from it.

Ground-truth honesty: nothing in this module is ported from OAI C -- there is
none for workload shape. The traffic *models* it composes are WP7's
(`sim/traffic.py`), and the QoS mapping follows the hardware plan's own
asset->5QI table (`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` §2), which is
a deployment choice, not a spec.
"""

from __future__ import annotations

from typing import Any, Optional

from .config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
from scheduler.flow import FlowConfig

__all__ = ["sweep_scenario", "MIXES"]

# The base RAN (docs/wp9-plan.md §1): factory_robots' own default radio.
# 55 PRB at mu=2, 0.25ms slots, DSUUU. Fixed for the whole sweep so that
# §1.1's N_crit prediction (min(55/min_rb, 32/4)) is a single number to
# check against, not one that moves per cell.
_BASE_BANDWIDTH_HZ = 40_000_000
_BASE_NUMEROLOGY = 2
_BASE_TDD_PATTERN = "DSUUU"

_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000

# Hardware plan §2's asset->5QI mapping, as far as this simulator models it.
_QFI_TELEMETRY = 1     # T1 telemetry (UL) -- 5QI 1, the liveness instrument
# T2 commands (DL). The hardware plan §1 has T2 riding T1's bearer in the
# reverse direction, and this simulator CANNOT represent that: RunRecord and
# Metrics key a flow by (ue_id, qfi) with no direction term, so a UL and a DL
# flow sharing a 5QI collide and one silently disappears from every metric
# (measured: 8 configured flows, 6 reported). Modelled instead as 5QI 82,
# delay-critical GBR -- the same 5QI factory_robots uses for its own DL
# control loop. Consequence, recorded in docs/wp9-plan.md §5: M16's
# "shared-bearer" correlation is between two 5QIs here, not one bidirectional
# bearer, and G1/G2/G3's shared-bearer half is an approximation to that
# extent. Fixing it properly means adding a direction term to flow keying,
# which touches RunRecord, Metrics, every scenario and the frozen corpus.
_QFI_COMMAND = 82
_QFI_VIDEO = 2         # T3 camera (UL) -- 5QI 2
_QFI_BG = 9            # T6 best-effort (per-UE filler) -- 5QI 9, non-GBR
_QFI_AGGRESSOR = 8     # GT-4.1/4.2's saturating flood -- distinct from the
                       # per-UE filler above for the same keying reason as
                       # _QFI_COMMAND: it lands on a UE that already has a
                       # 5QI-9 flow, so reusing 9 would collide.

MIXES = ("factory", "telemetry_only", "video_heavy")

# Per-UE best-effort UL offered rate at load_mult=1.0.
#
# WHY THE LOAD AXIS RIDES THIS FLOW AND NOT THE INSTRUMENTS.
#
# History, kept because it is why this module is shaped this way: scaling
# the periodic GBR/Delay flows with load_mult was tried first, and produced
# a base point that delivered 3.7 Mbps of 48.5 offered with 95% of the
# carrier's PRBs idle. That was NOT a property of the workload -- it was the
# SR-trigger defect (docs/oai-port-map.md row 79, docs/wp9-plan.md sec8b),
# found by chasing exactly this measurement, and it is fixed.
#
# **The original mechanical justification is therefore obsolete, and is not
# restated here as though it still held.** Re-measured post-fix, the
# instrument flows alone deliver 98.7% of what they offer at ~49% UL
# utilisation on all three arms: nothing collapses, and periodic flows keep
# a cell perfectly well occupied now.
#
# The design survives for two different and more ordinary reasons:
#   1. Methodological. The GBR/Delay flows are what G1/G3/G5 read, so
#      load_mult must not change the quantity being measured. Holding them
#      at fixed profile rates and varying a separate filler is how the
#      hardware campaign separates its own tests -- GT-7.3 ramps aggregate
#      offered load, GT-3.2 steps the GBR rates -- and keeps "load" and
#      "instrument" from being the same knob.
#   2. Arithmetic. At profile rates the instruments offer ~32 Mbps at
#      n_ues=8, against a cell that saturates near 100. They cannot reach
#      overload on their own without being distorted past what they are
#      supposed to represent, and the exclusion rule needs cells that reach
#      real loss.
#
# Calibrated so load_mult=1.0 offers ~96 Mbps UL at n_ues=8, i.e. ~100% of
# cell capacity: loss on all three arms (is_informative passes) and the
# band's widest arm spread (docs/wp9-plan.md sec1.2's re-derivation).
_BE_PER_UE_BPS = 8_000_000.0


def _snr_for(index: int, n_ues: int, spread_db: float) -> float:
    """UE SNRs spread linearly across `spread_db`, centred on the base.

    spread_db=0 gives every UE the base value (the corpus convention and the
    base point). H3 ("two-tier wins as channel quality spreads") needs the
    spread itself to be the axis, and a linear ramp makes "spread" mean one
    unambiguous thing -- the max-minus-min gap in dB -- rather than a
    distribution shape that would be a second, uncontrolled variable.
    """
    if n_ues <= 1 or spread_db <= 0.0:
        return _BASE_SNR_DB
    frac = index / (n_ues - 1)          # 0.0 .. 1.0
    return _BASE_SNR_DB - spread_db / 2.0 + frac * spread_db


def _burstify(period_ms: float, byts: float, duty: float) -> tuple[float, float]:
    """Trade cadence against burst size at CONSTANT mean offered rate.

    H2's axis is burst duty cycle, and the hypothesis ("the windowed ceiling
    accumulates credit across idle periods; reservation is memoryless") is
    about *idleness*, not about load. So duty must not smuggle in a load
    change: at duty d the period stretches by 1/d and the burst grows by
    1/d, leaving bytes/second exactly where it was. duty=1.0 is a no-op.

    Without this the duty axis and the load axis would move the same
    quantity, and a "burstiness regime" found on it could just be the load
    axis in disguise.
    """
    if duty >= 1.0:
        return period_ms, byts
    return period_ms / duty, byts / duty


def sweep_scenario(
    *,
    seed: int,
    n_ues: int = 8,
    load_mult: float = 1.0,
    mix: str = "factory",
    duty_cycle: float = 1.0,
    snr_spread_db: float = 0.0,
    pdb_ms: Optional[float] = None,
    shared_lcg: bool = False,
    mfbr_multiple: float = 0.0,
    bg: bool = False,
    inf_scenario: Optional[str] = None,
    horizon_slots: int = 20_000,
    **_ignored: Any,
) -> ScenarioConfig:
    """One WP9 grid cell as a ScenarioConfig. Defaults ARE the base point.

    `**_ignored` absorbs axis values that are not scenario properties --
    `min_rb` reaches the scheduler through its constructor
    (`regime_sweep.axis_aware`) and `sr_period_slots`/`k2_slots` reach the
    driver through `driver_kwargs` -- so the same `axis_values` dict can be
    passed to all three without the caller having to partition it. Silently
    dropping an unknown key is the deliberate trade: the alternative is
    every axis needing a hand-written split at every call site.

    Args worth stating precisely:
      load_mult      scales OFFERED BYTES, not carrier bandwidth. WP9 excludes
                     capacity scaling as the load axis (docs/wp9-plan.md §3):
                     changing prb_count moves H1's own predicted boundary,
                     which is the quantity the sweep exists to locate.
      duty_cycle     burstiness at constant mean rate -- see _burstify.
      pdb_ms         overrides the DL command flow's PDB only (H4's axis is
                     the PDB-to-Tier-1-period ratio, and the command flow is
                     the one whose deadline that ratio is about).
      shared_lcg     forces this UE's two UL flows onto one LCG via an
                     explicit per-flow `lcg`. Deliberately an override rather
                     than a change to FIVE_QI_LCG, which is an invented
                     mapping with nothing to validate it (README §8,
                     [OPEN: HARDWARE/DECISION]) -- WP9 routes around that
                     open item rather than appearing to settle it, and any
                     H5 result is conditional on this override.
      mfbr_multiple  0.0 = off (the repo-wide status quo). Otherwise every
                     GBR flow gets mfbr_bps = multiple * gfbr_bps, which
                     activates gbr_bytes_slot / gbr_below in BOTH arms at
                     once -- neither arm's captured baseline covers it.
    """
    if mix not in MIXES:
        raise ValueError(f"unknown mix {mix!r}; must be one of {MIXES}")
    if n_ues < 1:
        raise ValueError(f"n_ues must be >= 1, got {n_ues}")
    if inf_scenario is not None:
        from .pathloss import INF_SUB_SCENARIOS
        if inf_scenario not in INF_SUB_SCENARIOS:
            raise ValueError(
                f"unknown InF sub-scenario {inf_scenario!r}; "
                f"must be one of {INF_SUB_SCENARIOS}"
            )

    ues: list[UEConfig] = []
    flows: list[FlowConfig] = []

    for i in range(n_ues):
        ue_id = i + 1
        ue_kwargs: dict[str, Any] = {
            "ue_id": ue_id,
            "mean_snr_db": _snr_for(i, n_ues, snr_spread_db),
            "coherence_slots": _COHERENCE_SLOTS,
        }
        if inf_scenario is not None:
            # A simple expanding ring: distinct distances so path loss has
            # something to differentiate, deterministic so a cell is
            # reproducible from its axis values alone. When set, channel.py
            # derives mean_snr_db from position and ignores the value above
            # -- so snr_spread_db and inf_scenario are mutually exclusive by
            # construction, not by an assertion here.
            radius_m = 5.0 + 5.0 * i
            ue_kwargs["position"] = (radius_m, 0.0, 1.5)
            ue_kwargs["inf_scenario"] = inf_scenario
        ues.append(UEConfig(**ue_kwargs))

        # -- T1 telemetry (UL), the liveness instrument -------------------
        # periodic_control (not `deterministic`) so WP7's message ledger
        # tags each message and M03/M14/M01's true-latency path engages;
        # `deterministic` would leave M03 with nothing to group.
        if mix in ("factory", "telemetry_only"):
            tp_ms, tp_bytes = _burstify(100.0, 300.0, duty_cycle)
            flows.append(FlowConfig(
                ue_id=ue_id, qfi=_QFI_TELEMETRY, direction="UL",
                flow_class="Delay", pdb_ms=100.0,
                lcg=0 if shared_lcg else -1,
                traffic_kind="periodic_control",
                traffic_params={"period_ms": tp_ms, "bytes_per_period": tp_bytes},
            ))

        # -- T3 camera (UL), the GBR/frame instrument ---------------------
        if mix in ("factory", "video_heavy"):
            n_cams = 2 if mix == "video_heavy" else 1
            for cam in range(n_cams):
                # Scale avg_bytes, NOT the produced fragments: CLAUDE.md's
                # own known issue records that scaling an xr_video flow
                # after fragmentation can emit a fragment larger than
                # fragment_bytes, breaking that generator's MTU-cap claim.
                # Scaling the mean frame size is the documented workaround.
                vp_ms, vp_bytes = _burstify(33.0, 16_000.0, duty_cycle)
                gfbr = 4_000_000.0
                flows.append(FlowConfig(
                    ue_id=ue_id, qfi=_QFI_VIDEO + cam, direction="UL",
                    flow_class="GBR", gfbr_bps=gfbr, pdb_ms=150.0,
                    mfbr_bps=mfbr_multiple * gfbr,
                    lcg=0 if shared_lcg else -1,
                    traffic_kind="xr_video",
                    traffic_params={
                        "period_ms": vp_ms, "avg_bytes": vp_bytes,
                        # No default exists for fragment_bytes, deliberately
                        # (sim/traffic.py) -- 1500 is the Ethernet MTU, the
                        # one physically-grounded value available, and it is
                        # stated here rather than inherited silently.
                        "fragment_bytes": 1500,
                    },
                ))

        # -- T2 commands (DL), the responsiveness instrument --------------
        cp_ms, cp_bytes = _burstify(50.0, 100.0, duty_cycle)
        flows.append(FlowConfig(
            ue_id=ue_id, qfi=_QFI_COMMAND, direction="DL",
            flow_class="Delay",
            pdb_ms=100.0 if pdb_ms is None else pdb_ms,
            traffic_kind="periodic_control",
            traffic_params={"period_ms": cp_ms, "bytes_per_period": cp_bytes},
        ))

        # -- T6 best-effort (UL): the LOAD, and the reason the cell is
        # -- occupied at all. See _BE_PER_UE_BPS for why this carries
        # -- load_mult and the instruments above do not.
        flows.append(FlowConfig(
            ue_id=ue_id, qfi=_QFI_BG, direction="UL", flow_class="PF",
            pdb_ms=300.0,
            traffic_kind="poisson",
            traffic_params={"rate_bps": _BE_PER_UE_BPS * load_mult},
        ))

    if bg:
        # GT-4.1/4.2's *aggressor*: a saturating non-GBR UL flood on the
        # last UE, distinct from the per-UE T6 trickle above. One UE, not
        # all, so a shift in the protected statistics is attributable to
        # this flow rather than to every UE having gained one.
        flows.append(FlowConfig(
            ue_id=n_ues, qfi=_QFI_AGGRESSOR, direction="UL", flow_class="PF",
            pdb_ms=300.0, lcg=6,
            traffic_kind="poisson",
            traffic_params={"rate_bps": 50_000_000.0},
        ))

    return ScenarioConfig(
        name=(
            f"wp9_n{n_ues}_load{load_mult}_{mix}"
            f"{'_sharedlcg' if shared_lcg else ''}{'_bg' if bg else ''}"
        ),
        horizon_slots=horizon_slots,
        carrier=CarrierConfig(
            bandwidth_hz=_BASE_BANDWIDTH_HZ, numerology=_BASE_NUMEROLOGY,
        ),
        tdd=TDDConfig(pattern=_BASE_TDD_PATTERN),
        ues=ues,
        flows=flows,
        seed=seed,
    )
