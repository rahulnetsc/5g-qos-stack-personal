"""G12's overload-degradation ramp (GT-7.3).

`docs/wp9-plan.md` §35. **Scenario construction only** -- no `sim/` or
`scheduler/` behaviour change, and, per §35.6 D2, **no `sim/fleet.py`
change either**: `build_fleet`'s existing parameters already express the
whole ramp, and this module verifies that rather than asserting it.

WHAT G12 ASKS, AND WHY M13 IS ENOUGH FOR ONLY HALF OF IT. The guarantee's
four clauses are written in four different currencies (`docs/
IA_P5G_Factory_Guarantee_Test_Plan.md`:106 and GT-7.3):

    5QI 9 "exhausted"  -> throughput; 5QI 9 is non-GBR, no contract exists
    5QI 4 "degrades"   -> GBR contract  <- M13's pair
    5QI 2 "degrades"   -> GBR contract  <- M13's pair
    5QI 1 "intact"     -> liveness gap / PDB, NOT a contract; GT-7.3's own
                          FAIL example is "telemetry GAP grows while bg
                          still moves bytes"

So `Scorecard.first_violation_order` is used UNCHANGED and covers exactly
the middle pair, which is exactly the pair that has a contract. Clauses 1
and 4 are supplied from throughput and from M20/M02 by the analyser. That
is reading the guarantee correctly, not routing around a metric -- see
§35.2, and note §22.5's refusal to widen M13 to the Delay-class flows
stands and is not reopened here.

THE THREE TRAPS THIS MODULE EXISTS TO CLOSE, all measured in §35.4/§35.5:

 1. **A class with no dynamic range reads as a result.** Stage 5's lidar is
    active 2.0 s of a 5.0 s horizon and `throughput_bps` averages over the
    whole run, so its `gfbr_fraction` is capped at `2.0/5.0 = 0.4000` and
    it fails at EVERY load including ramp index 0 -- 0 of 1,110 flow-records
    met contract. `lidar_for_horizon()` below is the fix, and
    `assert_ramp_bottom_clean()` is the guard.
 2. **A GFBR provisioned above what the flow offers can never be met.**
    The test plan's own §2.1 gives telemetry `GFBR 0.5 Mbps` against
    `~24 kbps` offered; scoring 5QI 1 against that reads 0.045 at ramp
    index 0, i.e. telemetry leads every ordering. This module therefore
    leaves 5QI 1 exactly as `sim/fleet.py` declares it -- `flow_class=
    "Delay"`, GFBR 0 -- and clause 4 is a gap statistic.
 3. **Flow DECLARATION ORDER inverts which class violates first.** Measured:
    moving the 5QI 4 flows to the end of `ScenarioConfig.flows`, everything
    else byte-identical, takes 5QI 4 from `2/2` meeting to `0/2` (min
    0.005) at PF x3.0. `permute_flows()` makes that a registered control
    rather than a silent scenario-authoring choice (§35.6 D4). **The
    mechanism is untraced and is not guessed at here.**

WHY THE GUARDS LIVE IN THIS MODULE AND NOT IN `sim/scorecard.py`. They
encode G12's *interpretation* of M13's output -- what counts as a
degenerate ordering for this guarantee. `scorecard.py` is pre-registered
(`config/metric_panel.yml`); teaching it one guarantee's reading of a
metric is the same multiplicity-guard violation as widening the metric.
Same reason `sim/scenarios/g9.py` carries `validate_handshake_wiring`.
"""

from __future__ import annotations

import dataclasses
import random
from typing import Optional

from sim.config import CarrierConfig, FlowConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.fleet import COMPOSITIONS, LIDAR_MAX_CONCURRENT, LidarActivation, build_fleet

__all__ = [
    "QFI_BG", "BG_OFFERED_BPS", "LIDAR_STREAM_BPS", "GBR_CLASSES", "RAMP",
    "GUARANTEE_RAMP_TOP_MULT", "MEASURED_CEILING_BPS",
    "REFERENCE_COMMITTED_BPS",
    "build_g12_scenario", "lidar_for_horizon", "permute_flows",
    "class_of", "gbr_flow_census", "horizon_seconds",
    "assert_cell_is_scoreable", "assert_ramp_bottom_clean",
    "assert_order_non_degenerate", "OrderVerdict",
]

# --- constants, each with its source ------------------------------------

# G12 names 5QI **9** for the best-effort class, by number. `sim/
# parametric.py`'s bg aggressor and `sim/scenarios/g9.py`'s QFI_AGGRESSOR
# are both 5QI **8** and CANNOT be reused: both 8 and 9 are in
# Scorecard.NON_PROTECTED_5QI, so substituting one for the other is
# invisible to every protected-fleet statistic and would never have been
# caught downstream (§35.3).
QFI_BG = 9

# "saturating", per the test plan's §2.1 bg row (GFBR 0 / MFBR 100 Mbps).
# The rate matches `sim/parametric.py`'s existing aggressor so G12's cell
# load is comparable with G6's rather than being a second invented number.
# MFBR is not modelled anywhere in this repo (README §8, G7 is structurally
# out), so the offered rate is the only lever that exists.
BG_OFFERED_BPS = 50_000_000.0

# Test plan §2.1, T4 row: "streaming / lidar (5QI 4) | GFBR 3 Mbps | MFBR
# 6 Mbps | 10 Hz sweeps, bursty, mean 3 Mbps". NOT `sim/fleet.py`'s
# LIDAR_ACTIVE_BPS (12 Mbps), which is that module's duty-cycled activation
# rate for a different test -- see lidar_for_horizon()'s note on §35.6 D3.
LIDAR_STREAM_BPS = 3_000_000.0

# The classes M13 can order on this workload. Derived nowhere else: the
# runner asserts the built scenario actually contains these (§35.8), rather
# than restating a count in prose, which this project has been bitten by
# four times (CLAUDE.md).
GBR_CLASSES = (2, 4)

# The committed-load ramp (§35.6 D1). Multiplies BOTH GBR classes' offered
# rate AND their GFBR together, at fixed fleet -- GT-7.3's "both assets
# nominal; ramp aggregate offered load ... to 145 % of the measured
# ceiling".
#
# NOT `video_tier` alone, which scales only `xr_video` (5QI 2) and would
# bias the very ordering under test toward 5QI 2 failing first. NOT `n_ues`,
# which changes class populations lumpily through `_allocate`'s
# largest-remainder step.
#
# THE TOP LEVEL IS MEASURED, NOT CHOSEN. §35.5 registered a stop condition:
# the grid is not launched until a probe shows 5QI 4 breaching under the
# CANONICAL declaration order. `scripts/g12_ramp_probe.py` ran it (mixed,
# N=8, seed 12345, one seed, canonical order, no permutation) and the stop
# condition did NOT fire -- 5QI 4 breaches on every arm: PF x4.0,
# Reservation x6.0, TwoTier x4.0.
#
# BUT WHERE IT BREACHES IS THE POINT, AND IT IS OUTSIDE THE GUARANTEE'S OWN
# RAMP. GT-7.3 specifies "+10 % steps of the measured ceiling ... to 145 %".
# Measured ceiling at the reference cell (UL delivered when already
# saturated, at the ramp's bottom): 63.4 Mbps, against 28.0 Mbps committed
# at x1.0. So:
#
#     mult   committed   % of ceiling      what breaches (canonical order)
#     x1.0    28.0 Mbps      44 %          nothing, on any arm
#     x1.6    44.8 Mbps      71 %
#     x2.3    64.4 Mbps     102 %
#     x2.7    75.6 Mbps     119 %
#     x3.3    92.4 Mbps     146 %  <- GT-7.3's OWN TOP
#     x4.0   112.0 Mbps     177 %          5QI 4 first breaches (PF, TwoTier)
#     x6.0   168.0 Mbps     265 %          5QI 4 first breaches (Reservation)
#     x8.0   224.0 Mbps     353 %          margin: the probe is ONE seed and
#                                          ONE composition, and Reservation
#                                          breached exactly at the old top
#
# **Within GT-7.3's own ramp, only 5QI 2 breaches on every arm** -- so the
# order there is a ONE-ELEMENT list, which is F4's result recurring for a
# newly measured reason rather than a workload-census one. The ramp
# therefore spans the guarantee's range AND extends past it, and the
# analyser reports the boundary rather than averaging across it.
#
# Extending until a class breaches is the procedure §35.5 registered, not a
# result being bought: if nothing had breached at any level that would have
# been reported as the answer. What must NOT happen is picking the
# declaration order that produces a breach -- see permute_flows().
RAMP: tuple[float, ...] = (1.0, 1.6, 2.3, 2.7, 3.3, 4.0, 6.0, 8.0)

# GT-7.3's own ceiling for the ramp, as a multiplier at the reference cell.
# Named so the analyser can separate "inside the guarantee's ramp" from
# "beyond it" without re-deriving the mapping above -- the two answers are
# different and reporting one as the other would be the error.
GUARANTEE_RAMP_TOP_MULT = 3.3

# The probe's own measurements, recorded so a later reader can check the
# table above rather than trust it.
MEASURED_CEILING_BPS = 63_400_000.0
REFERENCE_COMMITTED_BPS = 28_000_000.0

_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000
_NUMEROLOGY = 2
_BANDWIDTH_HZ = 40_000_000


# --- construction --------------------------------------------------------

def horizon_seconds(horizon_slots: int, numerology: int = _NUMEROLOGY) -> float:
    """Wall-clock horizon. Derived from the same expression
    `sim/resource.py::ResourceGrid` uses (`0.001 / 2**numerology`) rather
    than restated as a literal, so a numerology change cannot silently
    desynchronise the lidar's activation window from the run length."""
    return horizon_slots * (0.001 / (2 ** numerology))


def lidar_for_horizon(horizon_slots: int, committed_mult: float,
                      n_lidar_ues: int = LIDAR_MAX_CONCURRENT,
                      numerology: int = _NUMEROLOGY) -> LidarActivation:
    """A lidar that streams for the WHOLE run, at the test plan's 3 Mbps.

    **This is a different device claim from stage 5's, and deliberately so
    (§35.6 D3).** `sim/fleet.py` argues a duty-cycled lidar must not be
    modelled as "a permanently-downscaled continuous feed" -- an argument
    about stage 5's *transient excursion*, whose whole point was to stress a
    transient. GT-7.3's T4 is "lidar / **second feed**", provisioned as
    "3 Mbps mean, 10 Hz sweeps": a stream, not an event. Both models are in
    the test plan; they belong to different tests. Stated here so a later
    reader does not read it as an oversight.

    `duration_s` is the full horizon rather than a literal: `sim/traffic.py`
    gates on `now_s >= active_until_s`, so a window of exactly `horizon_s`
    covers every slot including the last. `synchronised=True` because a
    stagger would make the two lidars' windows differ in length once they
    are horizon-sized, which is the duty-cycle cap all over again.
    """
    return LidarActivation(
        n_ues=n_lidar_ues,
        start_s=0.0,
        duration_s=horizon_seconds(horizon_slots, numerology),
        rate_bps=LIDAR_STREAM_BPS * committed_mult,
        synchronised=True,
    )


def build_g12_scenario(
    n_ues: int,
    composition: str,
    committed_mult: float,
    seed: int,
    horizon_slots: int = 20_000,
    bg_offered_bps: float = BG_OFFERED_BPS,
    bg_ue_id: Optional[int] = None,
) -> ScenarioConfig:
    """GT-7.3's ramp cell: `sim/fleet.py`'s factory profiles at one point of
    the committed-load ramp, plus one saturating 5QI 9.

    Everything except the bg comes from `build_fleet` unchanged (§35.6 D2):
    `video_tier=committed_mult` scales the `xr_video` flows' `avg_bytes`
    *and* their `gfbr_bps` together, and `lidar_for_horizon` does the same
    for 5QI 4 through `LidarActivation.rate_bps`. So one multiplier moves
    both GBR classes' offered load and both their contracts, which is what
    makes the ramp neutral between the two classes whose order is the
    result.

    5QI 1 is left exactly as the DRONE profile declares it -- `Delay`,
    GFBR 0. Converting it to GBR so M13 could see it is rejected in §35.2
    and measured in §35.4(c): at the test plan's own 0.5 Mbps GFBR against
    ~24 kbps offered it scores 0.045 at ramp index 0 and would lead every
    ordering.
    """
    if composition not in COMPOSITIONS:
        raise ValueError(f"unknown composition {composition!r}")
    if committed_mult <= 0:
        raise ValueError(f"committed_mult must be positive, got {committed_mult}")

    lidar = lidar_for_horizon(horizon_slots, committed_mult)
    flows, _seq = build_fleet(n_ues, composition, lidar=lidar,
                              video_tier=committed_mult)
    flows = list(flows)

    if bg_offered_bps > 0:
        # One UE carries the flood, not all of them -- `sim/parametric.py`'s
        # own reasoning for its aggressor: a shift in the protected
        # statistics is then attributable to this flow rather than to every
        # UE having gained one.
        flows.append(FlowConfig(
            ue_id=n_ues if bg_ue_id is None else bg_ue_id,
            qfi=QFI_BG, direction="UL", flow_class="PF", pdb_ms=300.0, lcg=6,
            traffic_kind="poisson",
            traffic_params={"rate_bps": bg_offered_bps},
        ))

    ues = [UEConfig(ue_id=i + 1, mean_snr_db=_BASE_SNR_DB,
                    coherence_slots=_COHERENCE_SLOTS)
           for i in range(n_ues)]
    return ScenarioConfig(
        name=f"g12_{composition}_n{n_ues}_x{committed_mult}",
        horizon_slots=horizon_slots,
        carrier=CarrierConfig(bandwidth_hz=_BANDWIDTH_HZ,
                              numerology=_NUMEROLOGY),
        tdd=TDDConfig(pattern="DSUUU"),
        ues=ues, flows=flows, seed=seed,
    )


def permute_flows(scenario: ScenarioConfig, perm_seed: int) -> ScenarioConfig:
    """D4's registered control: the same scenario with `flows` reordered.

    **Declaration order is not cosmetic here.** Measured in §35.5, with
    everything else byte-identical: `build_fleet`'s own order leaves 5QI 4
    at `2/2` meeting (min 1.000) at PF x3.0 while 5QI 2 collapses to
    min 0.121; moving the 5QI 4 flows to the end takes 5QI 4 to `0/2`
    (min 0.005). Five random permutations spread 5QI 4 across `1/2`..`2/2`
    at PF x2.0, and two of them drive a TwoTier 5QI 2 bearer to min 0.021
    and min 0.000 where the canonical order gives `5/5` (min 0.953).

    **So an arm-dependent first-violation order is not a scheduler property
    until it survives this.** The mechanism is untraced (§35.5 names three
    candidates from this repo's own recorded behaviour); this function
    measures the effect without asserting a cause.

    Uses `random.Random`, not numpy, and never the scenario's own seed --
    the permutation is an experimental factor, not part of the workload's
    stochastic state, and sharing a stream with the traffic RNG would be
    CLAUDE.md's own "every independent draw needs its own stream" violation.
    """
    flows = list(scenario.flows)
    random.Random(perm_seed).shuffle(flows)
    return dataclasses.replace(scenario, flows=flows)


# --- what an analyser must read off the scenario, not reconstruct --------

def class_of(scenario: ScenarioConfig) -> dict[str, int]:
    """`flow key -> 5QI`, M13's second argument.

    Derived from the built scenario rather than rebuilt by the analyser, for
    the same reason `g9.py::joiner_ue_id` exists: two derivations of one
    fact are one derivation too many, and the analyser's copy is the one
    that silently goes stale.
    """
    return {f"ue{f.ue_id}_qfi{f.qfi}": f.qfi for f in scenario.flows}


def gbr_flow_census(scenario: ScenarioConfig) -> dict[int, int]:
    """`5QI -> number of contracted GBR flows` in this scenario.

    The EXPECTED count for §35.8's assertion, computed from the structure at
    the point of use. c2a9f13 strengthened G9's guard from "did the mechanism
    fire at all" to "did it fire as often as the schedule specifies"; the
    analogue here is that every ramp point must carry the same GBR flow
    population, or the arms are comparing different populations.
    """
    census: dict[int, int] = {}
    for f in scenario.flows:
        if f.flow_class == "GBR" and f.gfbr_bps > 0:
            census[f.qfi] = census.get(f.qfi, 0) + 1
    return census


def assert_cell_is_scoreable(scenario: ScenarioConfig) -> dict[int, int]:
    """A cell with fewer than two GBR classes cannot produce an ordering.

    §35.7 case 1, and it is a real cell property rather than a hypothetical:
    `sensor_dense` allocates 3 % UGVs, so at N=4 and N=8 it has **no UGV at
    all** and therefore no 5QI 4 flow -- exactly the 28-of-48 pattern
    stage 5's own census shows. Such a cell must be EXCLUDED by name, not
    scored to a one-element "order" that reads like a result.
    """
    census = gbr_flow_census(scenario)
    missing = [qi for qi in GBR_CLASSES if census.get(qi, 0) == 0]
    if missing:
        raise ValueError(
            f"{scenario.name}: GBR classes {missing} absent (census "
            f"{census}); M13 orders classes against each other, so this cell "
            f"can only produce a one-element 'order', which is not an "
            f"ordering (docs/wp9-plan.md §35.7 case 1). Exclude the cell."
        )
    return census


@dataclasses.dataclass(frozen=True)
class OrderVerdict:
    """M13's output plus the degeneracy checks §35.7 pre-registered."""
    order_5qi: tuple[int, ...]
    first_fail_at_index: dict[int, int]
    ties: tuple[tuple[int, ...], ...]
    never_failed: tuple[int, ...]
    terminal_fraction: dict[int, float]

    @property
    def is_scoreable(self) -> bool:
        return len(self.order_5qi) >= 2 and not self.ties


def assert_ramp_bottom_clean(first_fail_at_index: dict[int, int],
                             label: str = "") -> None:
    """§35.7 case 2, and it is E1's control -- read FIRST, before any result.

    A class with `first_fail_at_index == 0` was already broken in the
    control condition, so the ramp is measuring PROVISIONING rather than
    load. Both known instances of this are recorded: stage 5's duty-cycled
    lidar (capped at 0.4000, fails at every load) and the test plan's own
    telemetry GFBR (0.045 at index 0). A failure here is a stop condition,
    not a finding about a scheduler.
    """
    at_zero = sorted(qi for qi, idx in first_fail_at_index.items() if idx == 0)
    if at_zero:
        raise AssertionError(
            f"{label}: 5QI {at_zero} already breach contract at ramp index 0. "
            f"The bottom of the ramp is the CONTROL and must be clean "
            f"(docs/wp9-plan.md §35.7 case 2) -- this measures provisioning, "
            f"not overload."
        )


def assert_order_non_degenerate(
    order_5qi: list[int],
    first_fail_at_index: dict[int, int],
    terminal_fraction: dict[int, float],
    label: str = "",
) -> OrderVerdict:
    """Every §35.7 degeneracy, asserted rather than discovered.

    Returns the verdict so a caller reports ties and never-failed classes
    ALONGSIDE the order rather than in place of it -- "never failed" and
    "never present" read identically in a bare `order_5qi`, which is the
    empty-selection signature CLAUDE.md records six times.
    """
    assert_ramp_bottom_clean(first_fail_at_index, label)

    # §35.7 case 5. `first_violation_order` sorts by index and Python's sort
    # is STABLE, so two classes first failing at the same index emit in
    # dict-insertion order -- which is silently the flow-iteration order
    # §35.5 has just shown to be an artefact. A tie is reported as a tie.
    by_index: dict[int, list[int]] = {}
    for qi, idx in first_fail_at_index.items():
        by_index.setdefault(idx, []).append(qi)
    ties = tuple(tuple(sorted(v)) for v in by_index.values() if len(v) > 1)

    # §35.7 case 3: absent from order_5qi is ambiguous between "protected"
    # and "not in the workload", so the terminal fraction travels with it.
    never = tuple(qi for qi in sorted(terminal_fraction)
                  if qi not in first_fail_at_index)

    if len(order_5qi) < 2:
        raise AssertionError(
            f"{label}: order {order_5qi} has fewer than two elements, which "
            f"is not an ordering -- F4's own result recurring (docs/"
            f"wp9-plan.md §35.7 case 1). Classes never failing: {never} with "
            f"terminal gfbr_fraction "
            f"{ {qi: round(terminal_fraction[qi], 4) for qi in never} }."
        )
    return OrderVerdict(
        order_5qi=tuple(order_5qi),
        first_fail_at_index=dict(first_fail_at_index),
        ties=ties, never_failed=never,
        terminal_fraction=dict(terminal_fraction),
    )
