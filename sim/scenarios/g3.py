"""GT-2's liveness cells -- G3's own scenarios, built because none existed.

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` L97 (the G3 catalogue row):

    Max telemetry inter-arrival gap at MEC <= T_live/4 (500 ms); zero gaps
    >= T_live over the full campaign; p98 <= PDB.

and its three sub-tests, each isolating a different mechanism:

    GT-2.1  heartbeat vs the robot's OWN camera (intra-UE LCP preemption)
    GT-2.2  heartbeat vs a NEIGHBOUR's saturating uplink flood (isolation)
    GT-2.3  silence-and-resume, {1 s, 5 s, 60 s}, neighbour flooding

WHY THIS IS THE HARDEST FAMILY IN THE PLAN, IN ONE LINE. G1 and G2 are
downlink, where the gNB reads its own buffers -- no SR, no BSR, no estimate.
G3 is UPLINK, so every mechanism this project has traced is in play at once:
the cold-start lock-out, the BSR desync, `cp_floor`, the never-served fault,
and the Tier-1.5 service-interval floor that exists specifically to rescue
a stalled telemetry bearer. The plan calls the family "existential" for this
scheduler for exactly that reason (test plan GT-2's own preamble).

--------------------------------------------------------------------------
THE ONE CHANGE THAT MAKES THE CELL DIFFERENT FROM EVERY EXISTING WORKLOAD
--------------------------------------------------------------------------

**Telemetry is a GBR bearer here, and everywhere else in this repo it is
not.** `sim/parametric.py`, `sim/fleet.py`'s DRONE profile, `sim/scenarios/
{g1,g2,g9,g11}.py` and the six YAML scenarios all declare 5QI 1 uplink
telemetry as ``flow_class="Delay"`` with ``gfbr_bps=0``. Three consequences
follow, and each one is a reason the clause could not be scored properly
before:

 1. **5QI 1 IS a GBR 5QI** (TS 23.501 Table 5.7.4-1, GBR resource type), so
    a 5QI-1 bearer without a GFBR is an infidelity, not a modelling choice.
    `sim/scenarios/g1.py` already reached the same conclusion independently
    for its downlink cmd_vel bearer.
 2. **G3's third clause part is a GBR-conformance statistic.** Test plan
    §5: *"while the flow stays within GFBR, 98 % of packets shall not exceed
    the PDB"*. On a bearer with no GFBR there is no "within GFBR", so the
    conformance semantics never attached to any G3 number ever published.
 3. **`FlowConfig.effective_pbr_bps()` returns 0 for a Delay flow with no
    GFBR**, so the UE's own logical-channel prioritisation gives telemetry NO
    token bucket and it is skipped in LCP round 1. **TELEMETRY IS NEVER
    OUTRANKED BY THE CAMERA -- IT IS NEVER REACHED.** TS 38.321 5.4.3.1
    step 3 serves every logical channel in strict decreasing priority order
    *regardless of Bj*, and 5QI 1's priority (20) beats 5QI 2's (40), so in
    round 2 telemetry goes FIRST. What starves it is that round 2 never runs:
    the camera's bucket exceeds the transport block, so round 1 consumes the
    whole block and step 3 has nothing left. Measured per grant
    (`docs/g3-stress-experiment-2026-09-09.md` section 3.2), N=6, TwoTier,
    seed 1: of **24 062** grants where telemetry was backlogged and unserved,
    **24 062 -- every one -- had zero bytes remaining after round 1**, and in
    **zero** did round 2 run and skip telemetry. Median camera bucket 20 784 B
    against a median 288 B block.

    **So a PBR moves telemetry INTO round 1, ahead of the camera in the same
    priority order** -- it does not change who outranks whom. Measured: with a
    PBR at the flow's own offered rate, telemetry is served in round 1 on 2 983
    of 3 264 backlogged grants and all six robots deliver 100 of 100. That is
    still GT-2.1's named failure mode and still a UE-configuration lever, as
    that test's own text predicts -- but the root cause is a grant too small
    for the urgent flow, which is the gNB's (section 3.3).

**THE GFBR IS PROVISIONED AT THE OFFERED RATE, AND THAT IS THE ONLY VALUE
THAT SATISFIES BOTH CONSTRAINTS.** Test plan §2.1 proposes GFBR 0.5 Mbps for
the telemetry bearer against ~24 kbps offered. This repo's own invariant
(`sim/tests/test_workload.py::test_no_gbr_flow_offers_below_its_own_contract`,
`docs/gbr-offered-shortfall-2026-09-08.md`) forbids a GBR flow offering below
its contract, because every contract-attainment metric then measures the
traffic generator. §5's conformance semantics need offered <= GFBR; the
invariant needs offered >= GFBR; **offered == GFBR is the unique point that
satisfies both.** And it costs nothing: measured, a PBR at the offered rate
(24 kbps) captures the whole benefit of the plan's 0.5 Mbps (TwoTier p98
51.50 vs 48.25 ms), so the 20x over-provision buys nothing here.

**`telemetry_gbr=False` reproduces the historical configuration** -- Delay
class, GFBR 0, PBR 0 -- so the clause can be scored on both and the
difference reported rather than asserted. It is a control, not an escape
hatch: every G3 number published before 2026-09-09 was measured there.

--------------------------------------------------------------------------
AND THE GFBR -> PBR COUPLING IS THE DEPLOYED DERIVATION, NOT A SIMULATOR
CONVENIENCE -- READ FROM THE C, WITH THE FILES NAMED
--------------------------------------------------------------------------

Files searched: `oai-branches/mac_rrc_dl_handler.c` (the deployed DU's F1AP
bearer-setup handler, already cited in `scheduler/flow.py` for the 5QI PDB
table), `oai-branches/two-tier/nr_ue_scheduler.c` (the UE-side MAC, the file
that would contain the LCP if it existed anywhere -- and it does), and all
four `oai-branches/{two-tier,reservation}/gNB_scheduler_*.c`.

 * **A DRB's uplink `prioritisedBitRate` is derived from its GFBR and from
   nothing else.** `get_bearerconfig_from_drb` (`:294-350`) computes
   `gbr_ul_kbps` from `drb->nr.drb_qos.gbr_qos_flow_information->ul.
   guaranteedFlowBitRate` and passes it to `get_DRB_RLC_BearerConfig`; the
   `[IA-P5G FIX]` comment at `:316-343` states the consumption in as many
   words -- *"This value is consumed solely by get_DRB_RLC_BearerConfig() to
   pick a prioritisedBitRate enum"*.
 * **A non-GBR DRB therefore passes zero.** `gbr_ul_kbps` is initialised to
   `0` at `:296` and only assigned inside the `if (drb->nr.drb_qos.
   gbr_qos_flow_information)` guard. So *"no GFBR -> no PBR"* is the
   deployment's own arithmetic, which is exactly what
   `FlowConfig.effective_pbr_bps()` reproduces.
 * **The UE really does skip a zero-bucket channel in round 1.**
   `nr_ue_scheduler.c:2543-2553`, comment and code: *"selection of logical
   channels with Bj > 0"*, and `Bj` refills at `pbr` (`:1479-1501`). This is
   what `sim/ue_lcp.py` ports.
 * **AND THE FAILURE MODE HAS ALREADY BEEN OBSERVED ON HARDWARE.** The same
   `[IA-P5G FIX]` comment (`:326-335`) records a PBR that outran the cell's
   achievable rate and the consequence: *"the highest-priority LC's bucket
   never empties, so it absorbs every grant in round 1 and the lower-priority
   LCs on the same UE are served only once its buffer runs dry -- observed as
   one flow taking ~85 MB while its two siblings on the same UE got ~10 MB
   and ~4 bytes."* GT-2.1 is a test for a fault the deployment has already
   produced, in the same direction, from the other end of the same knob.
 * **Its own stated precondition for apportionment is met here.** The comment
   continues: *"for the bucket mechanism to apportion rather than starve, the
   SUM of a UE's per-flow PBRs must also stay within that UE's achievable
   rate."* Telemetry 24 kbps + camera 4 Mbps = 4.02 Mbps per robot, well
   inside it -- and inside §2.1's own 7.5 Mbps/asset committed sum.

**WHAT COULD NOT BE ESTABLISHED, stated rather than assumed.**
`get_DRB_RLC_BearerConfig` itself is not in the vendored subset, and the full
OAI checkout `CLAUDE.md` names is ABSENT from this machine (checked). So
which `prioritisedBitRate` enum a `gbr_ul_kbps` of 0 maps to -- `kBps0`, or
the `infinity` value the SRB path uses -- is **not readable here**. Both this
port and the deployment agree that a non-GBR DRB's PBR input is zero; what
the enum does with zero is a gap, and it is the reason `telemetry_pbr_bps`
exists as an explicit override rather than being inferred.

**AND `bsd_ms` HAS NO PROVENANCE AT ALL, in the direction that flatters this
campaign's own finding.** `FlowConfig.bsd_ms` defaults to 100 ms, so the
camera's bucket ceiling is 4 Mbps x 100 ms = 50 kB -- far larger than any
transport block here, which is precisely what lets round 1 absorb a whole TB.
The only bucket duration in the deployed source is the SRB path's
(`mac_rrc_dl_handler.c:227-228`, `bucketSizeDuration_ms5`), **20x smaller**;
the DRB value lives inside the unreadable `get_DRB_RLC_BearerConfig`. A
smaller bucket would let round 2 reach telemetry sooner, so 100 ms biases
TOWARD the starvation this module measures. `bsd_ms` is therefore a builder
parameter and is swept as a control -- see `docs/g3-registration-2026-09-09.md`.

--------------------------------------------------------------------------
WHAT THIS REUSES RATHER THAN REWRITES
--------------------------------------------------------------------------

The committed-profile shape (UL telemetry + UL camera + DL control loop +
per-UE best-effort filler) is `sim/parametric.py`'s factory mix, taken via
`sim/scenarios/g1.py`'s and `g2.py`'s already-established constants, for two
reasons and one of them is load-bearing: **the fleet axis is ranged against
G10's re-measured boundaries (PF 12 / Reservation 6 / TwoTier 7), and those
were measured on `sweep_scenario`'s mix** (`scripts/g10_rerun.py`). A cell
with a different committed portfolio would range the axis against a boundary
measured on a different workload -- the configuration-carrying error this
project has recorded four times.

**No lidar, deliberately, and it is a deviation from §2.1's three-flow
profile.** G1's and G2's cells omit it; adding a third GBR bearer would make
G3's numbers incomparable with theirs AND move the admissible fleet size the
axis is ranged against. Stated rather than silently matched.

`active_windows` (`sim/traffic.py`, WP9 G11 commit 4) is GT-2.3's silence
mechanism -- the same half-open-window gate `sim/scenarios/g11.py` uses for
GT-7.1's waypoint pauses. Nothing new was needed in `sim/`.

--------------------------------------------------------------------------
THE 5QI ALIASING CONSTRAINT, AND HOW IT IS RESOLVED HERE
--------------------------------------------------------------------------

`FlowRecord.key` is ``ue{N}_qfi{Q}`` with NO direction term and
`sim/buffer.py::_resolve` raises rather than guessing when a `(ue, qfi)` is
registered in two directions (defects log #28/#30). Every flow here is
uplink except the DL control loop on 5QI 82, so there is only one collision
risk: **the neighbour's saturating flood and the per-UE best-effort filler
are both 5QI 9.** GT-2.2 names the flood's class by number ("saturating
5QI-9 UL (`bg` role)"), and the filler's 5QI is this repo's own choice, so
the named one wins: **the flooding robot carries the flood on 5QI 9 and no
separate filler.** Identical disposition to `sim/scenarios/g1.py`'s firmware
puller, and both 8 and 9 are in `Scorecard.NON_PROTECTED_5QI`, so no
protected-fleet statistic can see the substitution either way.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Optional, Sequence

from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.scenarios.schedule_guard import require_horizon
from sim.workload import min_bytes_per_period_for_gfbr, scale_committed_load
from scheduler.flow import DERIVE_PDB_FROM_5QI, LCG_UNASSIGNED, FlowConfig

__all__ = [
    "QFI_TELEMETRY", "QFI_CAMERA", "QFI_FLEET_DL", "QFI_BG_UL", "QFI_FLOOD_UL",
    "TELEMETRY_PERIOD_MS", "TELEMETRY_BYTES", "TELEMETRY_GFBR_BPS",
    "T_LIVE_S", "MAX_GAP_BOUND_MS", "RAN_PDB_MS", "SLOT_S",
    "CAMERA_GFBR_BPS", "FLOOD_UL_BPS", "SETTLE_MS",
    "SILENCE_ACTIVE_S", "SILENCE_TAIL_S", "SILENCE_CYCLES",
    "FLOOR_ARMING_HORIZON_MS",
    "build_gt21_scenario", "build_gt22_scenario", "build_gt23_scenario",
    "telemetry_flow_keys", "instrument_ue_ids", "flood_ue_id",
    "silence_windows", "resume_times_s", "minimum_horizon_slots_gt23",
    "assert_telemetry_instrument_live",
]

# --- 5QI assignment, each with its source --------------------------------

#: Test plan §2's asset->5QI table: "T1 telemetry (UL) ... 5QI 1". The flow
#: the whole guarantee is about. PDB (100 ms) and priority (20) are DERIVED
#: from the 5QI table, never authored here.
QFI_TELEMETRY = 1
#: "T3 camera (UL) ... 5QI 2". GT-2.1's aggressor, on the SAME robot.
QFI_CAMERA = 2
#: The DL control loop, so the downlink is not idle. Same 5QI
#: `sim/parametric.py`, `sim/fleet.py`, `g1.py` and `g2.py` all use.
QFI_FLEET_DL = 82
#: The per-UE best-effort uplink filler. 5QI 9 in every builder; kept.
QFI_BG_UL = 9
#: GT-2.2 names it by number: "saturating 5QI-9 UL (`bg` role)". Same value
#: as the filler, which is why the flooding robot has no filler -- see the
#: module docstring's aliasing note.
QFI_FLOOD_UL = 9

# --- the instrument ------------------------------------------------------

#: Test plan §2 M1 CBR: "10 Hz x 300 B (UGV)". Held identical to every other
#: builder's telemetry so latency numbers stay comparable, which is what §2
#: asks for in as many words.
TELEMETRY_PERIOD_MS = 100.0
TELEMETRY_BYTES = 300.0
#: 300 B / 100 ms = 24 kbps. Provisioned AT the offered rate -- the unique
#: value satisfying both §5's "within GFBR" and this repo's own
#: offered >= contract invariant. See the module docstring.
TELEMETRY_GFBR_BPS = TELEMETRY_BYTES * 8.0 * 1000.0 / TELEMETRY_PERIOD_MS
#: Operator convention, matching `sim/fleet.py::_MFBR_MULTIPLE` and
#: `sim/parametric.py`'s default: burst to twice the guarantee. AUTHORED --
#: no MFBR ground truth exists in this repo. It is also the ONLY reason
#: two-tier's Tier-1.5 UL floor and FIX-2 GBR reserve can arm at all
#: (`_ul_has_pending_gbr` needs `mfbr_bps > 0`), so a zero here would
#: silently disable the mechanism GT-2.2 exists to validate.
MFBR_MULTIPLE = 2.0

#: Test plan §3's own footnote: "`T_live` = the MEC's liveness timeout (not
#: stated in the architecture doc -- confirm with the MEC team; assume 2 s)".
#: A PROPOSED default and §9's first open external input, so it is one
#: constant here rather than a literal in a runner.
T_LIVE_S = 2.0
#: Clause part 1: "max telemetry inter-arrival gap at MEC <= T_live/4".
MAX_GAP_BOUND_MS = T_LIVE_S * 1000.0 / 4.0
#: Clause part 3: "p98 <= PDB", against §5's RAN budget split
#: ("RAN budget = PDB - 5 ms"). 5QI 1's standardised PDB is 100 ms, so the
#: RAN share is 95 -- numerically G1's own bound, under a different
#: guarantee's name. Stated so one number never silently carries two
#: verdicts.
RAN_PDB_MS = 95.0

#: Two-tier's UL service-interval floor is ARMED only while the last observed
#: uplink delivery for that UE is within this window
#: (`scheduler/two_tier.py::_UL_FLOOR_ALIVE_MS`, ia_p5g_scheduler.c:2306-2530).
#: GT-2.3's buckets straddle it deliberately: 1 s is inside, 5 s and 60 s are
#: outside, so below it the floor must catch a would-be stall and above it the
#: raw SR path carries it alone. Read from the scheduler rather than restated
#: -- see the assertion in `sim/tests/test_g3_scenario.py`.
FLOOR_ARMING_HORIZON_MS = 2000.0

# --- the load ------------------------------------------------------------

#: `sim/parametric.py`'s own camera: 30 fps, 4 Mbps GBR, 150 ms PDB.
CAMERA_PERIOD_MS = 33.0
CAMERA_GFBR_BPS = 4_000_000.0
CAMERA_FRAGMENT_BYTES = 1500          # Ethernet MTU; stated, not inherited
#: The DL control loop.
FLEET_DL_PERIOD_MS = 50.0
FLEET_DL_BYTES = 120.0
#: `sim/parametric.py::_BE_PER_UE_BPS`.
BG_UL_BPS = 8_000_000.0
#: "saturating". Same figure `g1.py::FIRMWARE_PULL_BPS`,
#: `g2.py::FLOOD_UL_BPS`, `g12.py::BG_OFFERED_BPS` and `sim/parametric.py`'s
#: aggressor use, so this cell's load is comparable with theirs.
FLOOD_UL_BPS = 50_000_000.0

#: Let the unbounded flood queue reach steady state before the first
#: statistic matters. Same reasoning as `g2.py::SETTLE_MS`.
SETTLE_MS = 1000.0

# --- GT-2.3's silence schedule -------------------------------------------

SLOT_S = 0.00025                      # numerology 2, this cell's carrier

#: How long telemetry runs between pauses. 5 s is 50 telemetry messages, so
#: each active window carries its own gap distribution rather than a handful
#: of samples.
SILENCE_ACTIVE_S = 5.0
#: The active tail after the LAST silence, so the final resume is observed
#: with the same amount of run left as every other one.
SILENCE_TAIL_S = 5.0
#: Silences per run. The plan asks 100 cycles/bucket; a run cannot hold 100
#: 60-second pauses, so cycles accumulate across seeds and arms and the
#: achieved count is DERIVED and reported (`scripts/g3_stress.py`), never
#: restated as the plan's number.
#:
#: **ONE, AND THE BINDING CONSTRAINT IS MEMORY RATHER THAN TIME.** Measured
#: 2026-09-09 by killing a launched campaign: at 3 cycles the 60 s bucket is a
#: 800,000-slot run, and 14 such runs in a pool reached **17.0 GB resident with
#: 1.5 GB of machine memory left** and were still climbing at ~60 % through --
#: a projected ~56 GB against 31 GB of RAM. The cost is `sim/messages.py`'s
#: per-message ledger over a 50 Mbps saturating flood: ~2.5 MB of resident set
#: per 1,000 slots per worker, which no per-process guard would flag and
#: `regime_sweep.run_cells` does not watch at all (it carries the pool's other
#: four lessons but not an aggregate memory ceiling -- recorded as a finding in
#: `docs/g3-stress-experiment-2026-09-09.md`).
#:
#: A silence costs its own duration in simulated time, so cycles is the ONLY
#: lever on that. **The buckets are therefore not equally priced** -- 240,000
#: slots per resume at 60 s against 44,000 at 1 s -- and the achieved resume
#: count is 10 per (arm, bucket) against the plan's 100. That shortfall is a
#: run, not an argument.
SILENCE_CYCLES = 1

_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000
_NUMEROLOGY = 2
_BANDWIDTH_HZ = 40_000_000
_TDD_PATTERN = "DSUUU"


# --- flow constructors ---------------------------------------------------

def _telemetry(ue_id: int, *, gbr: bool, pbr_bps: Optional[float],
               bsd_ms: Optional[float] = None,
               active_windows: Optional[Sequence[tuple]] = None) -> FlowConfig:
    """The instrument. See the module docstring for why `gbr` defaults on."""
    params: dict[str, Any] = {"period_ms": TELEMETRY_PERIOD_MS,
                              "bytes_per_period": TELEMETRY_BYTES}
    if active_windows is not None:
        params["active_windows"] = tuple(active_windows)
    if gbr:
        return FlowConfig(
            ue_id=ue_id, qfi=QFI_TELEMETRY, direction="UL", flow_class="GBR",
            gfbr_bps=TELEMETRY_GFBR_BPS,
            mfbr_bps=MFBR_MULTIPLE * TELEMETRY_GFBR_BPS,
            # 0.0 means "use the GFBR" (FlowConfig.effective_pbr_bps), which
            # is what an operator configures; an explicit value overrides it
            # so the PBR can be swept independently of the contract.
            pbr_bps=0.0 if pbr_bps is None else float(pbr_bps),
            **({} if bsd_ms is None else {"bsd_ms": float(bsd_ms)}),
            pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
            traffic_kind="periodic_control", traffic_params=params,
        )
    # The historical configuration, kept as a control: Delay class, no GFBR,
    # and therefore no PBR token bucket at all unless one is passed.
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_TELEMETRY, direction="UL", flow_class="Delay",
        pbr_bps=0.0 if pbr_bps is None else float(pbr_bps),
        **({} if bsd_ms is None else {"bsd_ms": float(bsd_ms)}),
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="periodic_control", traffic_params=params,
    )


def _camera(ue_id: int, offer_x_gfbr: float = 1.0,
            bsd_ms: Optional[float] = None,
            active_windows: Optional[Sequence[tuple]] = None) -> FlowConfig:
    """The UL camera. `offer_x_gfbr` is GT-2.1's over-drive knob: 1.0 offers
    at the contract, 2.0 offers at MFBR ("camera at MFBR, deliberately
    over-driven"). The CONTRACT does not move with it -- over-driving a
    bearer means offering more than it is entitled to, not being entitled to
    more.

    Scales `avg_bytes` rather than the produced fragments: CLAUDE.md's own
    known issue records that scaling an `xr_video` flow after fragmentation
    can emit a fragment larger than `fragment_bytes`, breaking that
    generator's MTU-cap claim.
    """
    if offer_x_gfbr <= 0.0:
        raise ValueError(f"offer_x_gfbr must be > 0, got {offer_x_gfbr}")
    base_bytes = float(min_bytes_per_period_for_gfbr(
        CAMERA_GFBR_BPS, CAMERA_PERIOD_MS))
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_CAMERA, direction="UL", flow_class="GBR",
        gfbr_bps=CAMERA_GFBR_BPS, mfbr_bps=MFBR_MULTIPLE * CAMERA_GFBR_BPS,
        **({} if bsd_ms is None else {"bsd_ms": float(bsd_ms)}),
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="xr_video",
        traffic_params={
            "period_ms": CAMERA_PERIOD_MS,
            "avg_bytes": base_bytes * offer_x_gfbr,
            "fragment_bytes": CAMERA_FRAGMENT_BYTES,
            **({} if active_windows is None
               else {"active_windows": tuple(active_windows)}),
        },
    )


def _fleet_dl(ue_id: int) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_FLEET_DL, direction="DL", flow_class="Delay",
        pdb_ms=DERIVE_PDB_FROM_5QI,
        traffic_kind="periodic_control",
        traffic_params={"period_ms": FLEET_DL_PERIOD_MS,
                        "bytes_per_period": FLEET_DL_BYTES},
    )


def _bg_ul(ue_id: int,
           active_windows: Optional[Sequence[tuple]] = None) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_BG_UL, direction="UL", flow_class="PF",
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="poisson",
        traffic_params={"rate_bps": BG_UL_BPS,
                        **({} if active_windows is None
                           else {"active_windows": tuple(active_windows)})},
    )


def _flood_ul(ue_id: int, rate_bps: float) -> FlowConfig:
    return FlowConfig(
        ue_id=ue_id, qfi=QFI_FLOOD_UL, direction="UL", flow_class="PF",
        pdb_ms=DERIVE_PDB_FROM_5QI, lcg=LCG_UNASSIGNED,
        traffic_kind="poisson", traffic_params={"rate_bps": rate_bps},
    )


# --- GT-2.3's schedule, derived once and consumed everywhere -------------

def silence_windows(
    silence_s: float, *, cycles: int = SILENCE_CYCLES,
    active_s: float = SILENCE_ACTIVE_S, tail_s: float = SILENCE_TAIL_S,
) -> tuple[tuple[float, float], ...]:
    """The telemetry source's ACTIVE intervals for one silence bucket.

    `cycles` active windows of `active_s`, each followed by a `silence_s`
    pause, then a final `tail_s` window so the last resume is observed with
    the same amount of run behind it as every other one. So there are
    `cycles` silences and `cycles` resumes.

    Half-open [from, until), which is `sim/traffic.py`'s own convention.
    """
    if cycles < 1:
        raise ValueError(f"cycles must be >= 1, got {cycles}")
    if silence_s <= 0.0:
        raise ValueError(f"silence_s must be > 0, got {silence_s}")
    step = active_s + silence_s
    wins = [(k * step, k * step + active_s) for k in range(cycles)]
    wins.append((cycles * step, cycles * step + tail_s))
    return tuple(wins)


def resume_times_s(
    silence_s: float, *, cycles: int = SILENCE_CYCLES,
    active_s: float = SILENCE_ACTIVE_S, tail_s: float = SILENCE_TAIL_S,
) -> tuple[float, ...]:
    """The instants telemetry resumes, DERIVED from the same windows.

    The scorer needs these to measure the post-silence gap: the application's
    own pause is not the network's, so the liveness clock starts at resume.
    Derived here rather than recomputed in the runner so the schedule and the
    scoring cannot disagree -- the drift this project has recorded five times
    for restated structure.
    """
    wins = silence_windows(silence_s, cycles=cycles, active_s=active_s,
                           tail_s=tail_s)
    return tuple(w[0] for w in wins[1:])


def minimum_horizon_slots_gt23(
    silence_s: float, *, cycles: int = SILENCE_CYCLES,
    active_s: float = SILENCE_ACTIVE_S, tail_s: float = SILENCE_TAIL_S,
    slot_s: float = SLOT_S,
) -> int:
    """The shortest horizon that contains the whole silence schedule.

    Derived from the windows, never restated. A shorter horizon silently
    drops resumes -- defects log #23, the class
    `sim/scenarios/schedule_guard.py` exists for.
    """
    wins = silence_windows(silence_s, cycles=cycles, active_s=active_s,
                           tail_s=tail_s)
    return int(math.ceil(wins[-1][1] / slot_s))


# --- the cell ------------------------------------------------------------

def _cell(
    *, seed: int, n_ues: int, committed_mult: float, horizon_slots: int,
    name: str,
    telemetry_gbr: bool,
    telemetry_pbr_bps: Optional[float],
    bsd_ms: Optional[float],
    camera_offer_x_gfbr: float,
    over_driven_ue: Optional[int],
    flood_ue: Optional[int],
    flood_bps: float,
    instrument_windows: Optional[Sequence[tuple]],
    pause_whole_ue: bool,
    snr_db: float,
) -> ScenarioConfig:
    """One GT-2 cell. UE 1 is Asset A (the instrument); the rest are Asset B.

    THE INSTRUMENT POPULATION IS FIXED AT UE 1 (plus the flooding robot for
    GT-2.2, whose own telemetry the clause names explicitly). If every robot
    were the instrument, "worst telemetry max gap" would be a worst-of-N
    order statistic and the fleet axis would move the statistic as well as
    the load -- the population defect `sim/scorecard.py::Population` exists
    to prevent, and the one that produced the withdrawn G3 row.
    """
    if n_ues < 2:
        raise ValueError(
            f"n_ues must be >= 2, got {n_ues}: test plan §4's first design "
            f"principle is '>= 2 assets in every test'")
    if flood_ue is not None and flood_ue == 1:
        raise ValueError(
            f"flood_ue={flood_ue} is Asset A, the instrument robot -- GT-2.2 "
            f"is INTER-UE isolation, so the flood must be a neighbour's")

    ues = [UEConfig(ue_id=i + 1, mean_snr_db=snr_db,
                    coherence_slots=_COHERENCE_SLOTS) for i in range(n_ues)]

    # --- the committed fleet, which `committed_mult` scales --------------
    # A pause applied to the WHOLE robot's uplink, not only its telemetry --
    # see `build_gt23_scenario`'s `pause_whole_ue`. The DL control loop is
    # deliberately left running: a robot that stops sending still receives.
    def _pause(ue_id: int) -> Optional[Sequence[tuple]]:
        if instrument_windows is None or ue_id != 1 or not pause_whole_ue:
            return None
        return instrument_windows

    fleet: list[FlowConfig] = []
    for ue_id in range(1, n_ues + 1):
        overdrive = (camera_offer_x_gfbr if ue_id == over_driven_ue else 1.0)
        fleet.append(_camera(ue_id, overdrive, bsd_ms=bsd_ms,
                             active_windows=_pause(ue_id)))
        fleet.append(_fleet_dl(ue_id))
        if ue_id != flood_ue:
            # The flooding robot's filler is displaced by the flood: one
            # (ue, qfi) cannot hold two flows. See the module docstring.
            fleet.append(_bg_ul(ue_id, active_windows=_pause(ue_id)))

    sc = ScenarioConfig(
        name=name, horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=_BANDWIDTH_HZ,
                              numerology=_NUMEROLOGY),
        tdd=TDDConfig(pattern=_TDD_PATTERN),
        ues=ues, flows=fleet, seed=seed,
    )
    scaled = scale_committed_load(sc, committed_mult)

    # --- the flows the load axis must NOT touch --------------------------
    # The instrument is appended AFTER scaling, so the quantity G3 measures
    # is identical at every point of the load axis -- a robot asked to carry
    # more video does not send a different heartbeat. The flood is appended
    # here too: it is already saturating, so scaling it would only change
    # how far past saturation an unbounded queue grows.
    tail: list[FlowConfig] = []
    for ue_id in range(1, n_ues + 1):
        tail.append(_telemetry(
            ue_id, gbr=telemetry_gbr, pbr_bps=telemetry_pbr_bps,
            bsd_ms=bsd_ms,
            active_windows=instrument_windows if ue_id == 1 else None))
    if flood_ue is not None:
        tail.append(_flood_ul(flood_ue, flood_bps))

    # ORDERED CANONICALLY BEFORE THE LCG PASS, and the reason is not
    # cosmetic. LCG = DRB ID and the simulator's proxy for DRB setup order is
    # position within the UE's flow list, so a bare `scaled.flows + tail`
    # gives telemetry the LAST ordinal on most robots and a different one on
    # the flooding robot (whose filler is displaced) -- an asymmetry created
    # by construction order rather than by provisioning. This order is test
    # plan §2's own asset->5QI table: telemetry, camera, DL control,
    # best-effort. Stable within a rank, so declaration order is still what
    # breaks ties.
    #
    # AND THE ORDINALS ARE CLEARED FIRST, which is not optional: building the
    # fleet through `ScenarioConfig` already ran one LCG pass over the
    # PARTIAL list, so the camera holds an explicit LCG 1. `assign_deployed_
    # lcgs` keeps an explicit LCG while still spending an ordinal, so a
    # second pass with telemetry now sorted ahead of the camera hands
    # telemetry ordinal 1 -- and BOTH end up on LCG 1. Measured directly
    # while building this module. Every flow here was authored
    # `LCG_UNASSIGNED`, so clearing restores the authored intent rather than
    # overriding a deliberate choice.
    _rank = {QFI_TELEMETRY: 0, QFI_CAMERA: 1, QFI_FLEET_DL: 2}
    flows = sorted(
        [dataclasses.replace(f, lcg=LCG_UNASSIGNED)
         for f in list(scaled.flows) + tail],
        key=lambda f: (f.ue_id, _rank.get(f.qfi, 3)))

    # Rebuilt through ScenarioConfig so __post_init__ re-runs the deployed
    # LCG assignment over each UE's FULL flow list -- appending to
    # `scaled.flows` would leave the instrument unresolved and every
    # per-LCG array indexer would refuse it.
    return dataclasses.replace(scaled, flows=flows, name=name)


def build_gt21_scenario(
    *, seed: int, n_ues: int = 6, committed_mult: float = 1.0,
    horizon_slots: int = 40_000,
    camera_offer_x_gfbr: float = 2.0,
    telemetry_gbr: bool = True,
    telemetry_pbr_bps: Optional[float] = None,
    bsd_ms: Optional[float] = None,
    snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-2.1 -- the robot's own camera against its own heartbeat.

    *"Asset A telemetry (M1) + camera at MFBR (deliberately over-driven);
    Asset B nominal committed profile (second asset present, collateral
    observed)."*

    `camera_offer_x_gfbr=2.0` IS "at MFBR" (MFBR = 2x GFBR here). No flood:
    GT-2.1 isolates the INTRA-UE mechanism, so adding a neighbour's flood
    would confound it with GT-2.2's.
    """
    return _cell(
        seed=seed, n_ues=n_ues, committed_mult=committed_mult,
        horizon_slots=horizon_slots,
        name=(f"gt21_n{n_ues}_cm{committed_mult:g}"
              f"_cam{camera_offer_x_gfbr:g}"
              f"_tgbr{int(telemetry_gbr)}"),
        telemetry_gbr=telemetry_gbr, telemetry_pbr_bps=telemetry_pbr_bps,
        bsd_ms=bsd_ms,
        camera_offer_x_gfbr=camera_offer_x_gfbr, over_driven_ue=1,
        flood_ue=None, flood_bps=0.0, instrument_windows=None,
        pause_whole_ue=False, snr_db=snr_db,
    )


def build_gt22_scenario(
    *, seed: int, n_ues: int = 6, committed_mult: float = 1.0,
    horizon_slots: int = 40_000,
    flood_bps: float = FLOOD_UL_BPS,
    telemetry_gbr: bool = True,
    telemetry_pbr_bps: Optional[float] = None,
    bsd_ms: Optional[float] = None,
    snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-2.2 -- a neighbour's saturating uplink flood against your heartbeat.

    *"Asset A full committed profile (telemetry is the instrument); Asset B
    saturating 5QI-9 UL (`bg` role) plus its own committed telemetry (so B is
    a real asset, not a pure aggressor)."*

    The flood rides the LAST robot, and that robot keeps its own telemetry and
    camera -- which is what makes it an asset rather than an aggressor, and
    why the clause names *"A **and** B telemetry gap/latency KPIs"*.
    """
    if flood_bps <= 0.0:
        raise ValueError(
            f"flood_bps must be > 0 (got {flood_bps}) -- GT-2.2 IS the "
            f"saturating-neighbour test; without the flood it is GT-2.1 "
            f"with a nominal camera")
    return _cell(
        seed=seed, n_ues=n_ues, committed_mult=committed_mult,
        horizon_slots=horizon_slots,
        name=(f"gt22_n{n_ues}_cm{committed_mult:g}"
              f"_tgbr{int(telemetry_gbr)}"),
        telemetry_gbr=telemetry_gbr, telemetry_pbr_bps=telemetry_pbr_bps,
        bsd_ms=bsd_ms,
        camera_offer_x_gfbr=1.0, over_driven_ue=None,
        flood_ue=n_ues, flood_bps=flood_bps, instrument_windows=None,
        pause_whole_ue=False, snr_db=snr_db,
    )


def build_gt23_scenario(
    *, seed: int, silence_s: float, n_ues: int = 6,
    committed_mult: float = 1.0, horizon_slots: Optional[int] = None,
    cycles: int = SILENCE_CYCLES, active_s: float = SILENCE_ACTIVE_S,
    tail_s: float = SILENCE_TAIL_S,
    flood_bps: float = FLOOD_UL_BPS,
    telemetry_gbr: bool = True,
    telemetry_pbr_bps: Optional[float] = None,
    bsd_ms: Optional[float] = None,
    pause_whole_ue: bool = False,
    allow_partial_schedule: bool = False,
    snr_db: float = _BASE_SNR_DB,
) -> ScenarioConfig:
    """GT-2.3 -- silence and resume, with the neighbour flooding throughout.

    *"Asset A telemetry pauses for {1 s, 5 s, 60 s} then resumes at 10 Hz;
    Asset B full profile + bg saturation throughout (worst case for A's
    re-entry)."*

    `pause_whole_ue` IS THE DIFFERENCE BETWEEN REACHING GT-2.3'S NAMED
    MECHANISM AND NOT REACHING IT, and the default does not reach it.
    GT-2.3 exists for *"the SR-fragility and desync class"* -- the first packet
    after silence has to buy a new grant, which costs a scheduling request on
    PUCCH, its prohibit timer, a grant and a BSR. **A robot whose camera keeps
    running never pays that**: the UE is still receiving uplink grants for
    another logical channel, so the resumed telemetry rides the next one and
    the UE's own LCP splits the transport block. Measured on the campaign's own
    default cell (`docs/g3-stress-experiment-2026-09-09.md` §5): post-silence
    gaps of **0.5-15.7 ms at the 60 s bucket**, below one SR opportunity
    (`sr_period_slots=10` = 2.5 ms), so no SR was involved at all.

    `pause_whole_ue=True` pauses every UPLINK flow on Asset A over the same
    windows, so the robot genuinely has nothing to send and must re-acquire a
    grant from scratch. The DL control loop keeps running, because a robot that
    stops sending still receives commands. **This is the configuration that
    tests what GT-2.3 is written to test**, and it is a strictly harder cell
    rather than a different one.

    `horizon_slots=None` derives the shortest horizon that holds the whole
    schedule. An explicit shorter one is REFUSED unless the caller claims a
    partial schedule: events past the end are consumed and discarded, so the
    run exits 0 having measured a different number of resumes than it says
    (defects log #23).
    """
    need = minimum_horizon_slots_gt23(silence_s, cycles=cycles,
                                      active_s=active_s, tail_s=tail_s)
    if horizon_slots is None:
        horizon_slots = need
    require_horizon(
        f"gt23(silence_s={silence_s:g})", need - 1, horizon_slots,
        allow_partial=allow_partial_schedule,
        detail=(f"{cycles} silences of {silence_s:g} s around "
                f"{active_s:g} s active windows plus a {tail_s:g} s tail. "
                f"A truncated schedule delivers FEWER RESUMES than the "
                f"bucket claims, and a resume is GT-2.3's unit of "
                f"observation. "))
    return _cell(
        seed=seed, n_ues=n_ues, committed_mult=committed_mult,
        horizon_slots=horizon_slots,
        name=(f"gt23_sil{silence_s:g}_n{n_ues}_cm{committed_mult:g}"
              f"_c{cycles}_tgbr{int(telemetry_gbr)}"
              f"{'_ueoff' if pause_whole_ue else ''}"),
        telemetry_gbr=telemetry_gbr, telemetry_pbr_bps=telemetry_pbr_bps,
        bsd_ms=bsd_ms,
        camera_offer_x_gfbr=1.0, over_driven_ue=None,
        flood_ue=n_ues, flood_bps=flood_bps,
        instrument_windows=silence_windows(silence_s, cycles=cycles,
                                           active_s=active_s, tail_s=tail_s),
        pause_whole_ue=pause_whole_ue, snr_db=snr_db,
    )


# --- populations, DERIVED from the scenario ------------------------------

def telemetry_flow_keys(scenario: ScenarioConfig) -> list[str]:
    """`FlowRecord.key` for every telemetry flow. Never a literal list:
    `n_ues` is a parameter, and a restated set is this project's
    most-repeated defect."""
    return [f"ue{f.ue_id}_qfi{f.qfi}" for f in scenario.flows
            if f.qfi == QFI_TELEMETRY and f.direction == "UL"]


def instrument_ue_ids(scenario: ScenarioConfig) -> list[int]:
    """The robots whose telemetry the clause is scored on.

    Asset A (UE 1) always, plus the flooding robot when there is one --
    GT-2.2's pass line names *"A and B telemetry gap/latency KPIs per G3"*,
    and B is the asset carrying the flood.
    """
    out = {1}
    f = flood_ue_id(scenario)
    if f is not None:
        out.add(f)
    return sorted(out)


def flood_ue_id(scenario: ScenarioConfig) -> Optional[int]:
    """The robot carrying the saturating flood, or None (GT-2.1).

    A LATENT DEFECT IS FLAGGED HERE RATHER THAN FIXED, and the reason is
    provenance. The flood and the per-UE best-effort filler share 5QI 9 (the
    plan names the flood's class by number; see the module docstring), so rate
    is the only discriminator -- and this `>= FLOOD_UL_BPS` test returns None
    for any caller passing a SMALLER `flood_bps`, which would then propagate
    into `instrument_ue_ids` and silently drop Asset B from the scored
    population.

    **No published figure is affected**: the campaign runs only the default
    rate, at which the test is correct. The fix is one comparison
    (`> BG_UL_BPS`, i.e. "bigger than a filler") and it was written, tested and
    then REVERTED out of this commit, because `sim/scenarios/g3.py` is inside
    the artefact's own `code_state` scope -- editing it re-stales every G3
    claim and would demand a 20-minute re-run to restore exact provenance for a
    change that cannot alter a single row. **One fidelity change per commit**
    applies to a latent-defect fix as much as to a mechanism, so it gets its
    own commit and its own `--check`.

    Found in this campaign's end-of-work judgment-calls review.
    """
    hits = sorted({f.ue_id for f in scenario.flows
                   if f.qfi == QFI_FLOOD_UL and f.direction == "UL"
                   and f.traffic_kind == "poisson"
                   and f.traffic_params.get("rate_bps", 0.0) >= FLOOD_UL_BPS})
    if not hits:
        return None
    if len(hits) != 1:
        raise ValueError(f"expected one flooding UE, found {hits}")
    return hits[0]


def assert_telemetry_instrument_live(scenario: ScenarioConfig) -> None:
    """The scenario really carries what GT-2 asks for.

    Not a smoke test. `docs/wp9-plan.md` §34.5's standing rule is that a
    mechanism must be shown to fire at the EXPECTED COUNT, because a
    partially-degenerate cell is not a smaller sample of the same thing.
    This is its construction-time half; the runner asserts the messages
    were actually generated and completed.
    """
    tel = [f for f in scenario.flows
           if f.qfi == QFI_TELEMETRY and f.direction == "UL"]
    if len(tel) != len(scenario.ues):
        raise AssertionError(
            f"expected one UL telemetry flow per UE ({len(scenario.ues)}), "
            f"found {len(tel)} -- the instrument G3 is named for is not on "
            f"every robot, so 'the worst asset' is not the worst asset")
    if 1 not in {f.ue_id for f in tel}:
        raise AssertionError("Asset A (UE 1) carries no telemetry flow")
    for f in tel:
        if f.pdb_ms <= 0.0:
            raise AssertionError(
                f"ue{f.ue_id} telemetry has pdb_ms={f.pdb_ms}; clause part 3 "
                f"is scored against the RAN share of it")
    cams = [f for f in scenario.flows
            if f.qfi == QFI_CAMERA and f.direction == "UL"]
    if not cams:
        raise AssertionError(
            "no UL camera -- test plan §4's second design principle needs a "
            "real contender for the uplink, and GT-2.1's mechanism IS the "
            "camera")
