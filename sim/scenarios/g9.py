"""G9's three join/re-join scenarios (GT-6.1 / 6.2 / 6.3).

`docs/wp9-plan.md` §31. **Scenario construction only** -- every mechanism
these exercise (`sim/join.py`, `sim/rlf.py`, the driver wiring, M18/M19)
was built by WP-Join and is already live on every run. No `sim/` or
`scheduler/` behaviour changes for G9; what did not exist was a scenario
that sets `UEConfig.join` at all (§31.2).

THE SHAPE, from the test plan's GT-6 section: one **Asset B** (the joiner /
recoverer) against **Asset A** -- a loaded neighbour fleet that must be
unaffected throughout. The neighbours are the population G9's fourth clause
is about, and `joiner_ue_id()` exists so an analyser can exclude it rather
than re-deriving which UE it was (§31.6).

THE HANDSHAKE WIRING IS THE TRAP THIS MODULE EXISTS TO CLOSE.
`JoinConfig.handshake_ul_qfi`/`handshake_dl_qfi` must name flows that
actually exist on that UE, direction-correct -- and `JoinConfig` cannot
check it, because it never sees the flow list. Set wrongly (or left None)
the handshake simply never completes and M18 reports
`n_never_completed = 100%` with every latency `None`. A throwaway probe hit
exactly that (§31.3). `validate_handshake_wiring()` below is the guard, and
every builder here calls it before returning.
"""

from __future__ import annotations

from sim.config import (CarrierConfig, FlowConfig, ScenarioConfig,
                        ScriptedFadeWindow, TDDConfig, UEConfig)
from sim.join import JoinConfig, JoinEvent

# QFIs. The handshake pair is distinct from every traffic flow on the
# joiner, per JoinConfig's own contract.
QFI_TELEMETRY = 1
QFI_VIDEO = 2
QFI_COMMAND = 82
QFI_AGGRESSOR = 8      # GT-6's "bg saturation"; in NON_PROTECTED_5QI
QFI_HANDSHAKE_UL = 70
QFI_HANDSHAKE_DL = 71

_BASE_SNR_DB = 20.0
_COHERENCE_SLOTS = 2000


def joiner_ue_id(scenario: ScenarioConfig) -> int:
    """The UE carrying the join schedule -- the one an analyser must EXCLUDE
    from any neighbours statistic (§31.6). Derived from the scenario rather
    than passed alongside it, so the two cannot disagree."""
    joiners = [ue.ue_id for ue in scenario.ues if ue.join is not None]
    if len(joiners) != 1:
        raise ValueError(f"expected exactly one joiner UE, found {joiners}")
    return joiners[0]


def neighbour_ue_ids(scenario: ScenarioConfig) -> list[int]:
    """Every UE except the joiner. The population G9's fourth clause is
    about, named here so no analyser has to reconstruct it."""
    j = joiner_ue_id(scenario)
    return sorted(ue.ue_id for ue in scenario.ues if ue.ue_id != j)


def validate_handshake_wiring(scenario: ScenarioConfig) -> None:
    """Assert every joiner's handshake QFIs name real, direction-correct
    flows on that UE.

    THE DEFECT THIS CATCHES is silent: `JoinConfig` cannot self-validate
    (it never sees the flow list), and a wrong or absent QFI does not raise
    -- it just means the handshake never completes, so M18 reports
    `n_never_completed = 100%` and every latency is `None`. That reads as a
    scheduler result and is a scenario bug.
    """
    for ue in scenario.ues:
        if ue.join is None:
            continue
        for qfi, want_dir, field in (
            (ue.join.handshake_ul_qfi, "UL", "handshake_ul_qfi"),
            (ue.join.handshake_dl_qfi, "DL", "handshake_dl_qfi"),
        ):
            if qfi is None:
                raise ValueError(
                    f"ue {ue.ue_id}: {field} is None, so this UE's handshake "
                    f"can never complete and M18 will report every latency as "
                    f"None (docs/wp9-plan.md §31.3)")
            match = [f for f in scenario.flows
                     if f.ue_id == ue.ue_id and f.qfi == qfi]
            if not match:
                raise ValueError(
                    f"ue {ue.ue_id}: {field}={qfi} names no flow on that UE; "
                    f"sim/join.py does not synthesize flows")
            if match[0].direction != want_dir:
                raise ValueError(
                    f"ue {ue.ue_id}: {field}={qfi} is a {match[0].direction} "
                    f"flow, must be {want_dir}")


def _traffic_flows(ue_id: int, *, video: bool = True) -> list[FlowConfig]:
    """One asset's profile: UL telemetry, UL video, DL command."""
    flows = [
        FlowConfig(ue_id=ue_id, qfi=QFI_TELEMETRY, direction="UL",
                   flow_class="Delay", pdb_ms=100.0,
                   traffic_kind="periodic_control",
                   traffic_params={"period_ms": 100.0, "bytes_per_period": 300}),
        FlowConfig(ue_id=ue_id, qfi=QFI_COMMAND, direction="DL",
                   flow_class="Delay", pdb_ms=100.0,
                   traffic_kind="periodic_control",
                   traffic_params={"period_ms": 50.0, "bytes_per_period": 100}),
    ]
    if video:
        flows.append(FlowConfig(
            ue_id=ue_id, qfi=QFI_VIDEO, direction="UL", flow_class="GBR",
            gfbr_bps=4_000_000.0, pdb_ms=150.0, traffic_kind="xr_video",
            traffic_params={"period_ms": 33.0, "avg_bytes": 16_000,
                            "fragment_bytes": 1500}))
    return flows


def _handshake_flows(ue_id: int) -> list[FlowConfig]:
    """The UL request / DL response pair. Real traffic through the ordinary
    buffer -> scheduler -> HARQ path (JoinConfig's own docstring): sampling
    the round trip would make GT-6.1's under-load criterion a tautology."""
    return [
        FlowConfig(ue_id=ue_id, qfi=QFI_HANDSHAKE_UL, direction="UL",
                   flow_class="Delay", pdb_ms=1000.0,
                   traffic_kind="periodic_control",
                   traffic_params={"period_ms": 1e9, "bytes_per_period": 1}),
        FlowConfig(ue_id=ue_id, qfi=QFI_HANDSHAKE_DL, direction="DL",
                   flow_class="Delay", pdb_ms=1000.0,
                   traffic_kind="periodic_control",
                   traffic_params={"period_ms": 1e9, "bytes_per_period": 1}),
    ]


def _build(name: str, *, n_neighbours: int, join: JoinConfig, seed: int,
           horizon_slots: int, fade: ScriptedFadeWindow | None = None,
           joiner_id: int = 1, bg: bool = True) -> ScenarioConfig:
    flows: list[FlowConfig] = []
    ues: list[UEConfig] = []

    flows += _traffic_flows(joiner_id) + _handshake_flows(joiner_id)
    ue_kwargs = dict(ue_id=joiner_id, mean_snr_db=_BASE_SNR_DB,
                     coherence_slots=_COHERENCE_SLOTS, join=join)
    if fade is not None:
        ue_kwargs["scripted_fade"] = (fade,)
    ues.append(UEConfig(**ue_kwargs))

    for k in range(n_neighbours):
        nid = joiner_id + 1 + k
        flows += _traffic_flows(nid)
        ues.append(UEConfig(ue_id=nid, mean_snr_db=_BASE_SNR_DB,
                            coherence_slots=_COHERENCE_SLOTS))

    if bg:
        # GT-6's own load condition -- "Asset A full profile + bg
        # saturation" (GT-6.1), "against a loaded cell" (GT-6.2). WITHOUT
        # IT THE NEIGHBOURS CLAUSE IS VACUOUS: measured at 22% UL
        # utilisation the neighbours drop and delay nothing, so the
        # neighbours delta is 0.000000 on every arm and every seed -- an
        # arithmetically correct PASS from a statistic with no dynamic
        # range, which J5 could never falsify. 5QI 8 is in
        # Scorecard.NON_PROTECTED_5QI, so the aggressor is excluded from
        # the neighbours statistic automatically.
        flows.append(FlowConfig(
            ue_id=ues[-1].ue_id, qfi=QFI_AGGRESSOR, direction="UL",
            flow_class="PF", pdb_ms=300.0, lcg=6, traffic_kind="poisson",
            traffic_params={"rate_bps": 50_000_000.0}))

    sc = ScenarioConfig(name=name, horizon_slots=horizon_slots,
                        carrier=CarrierConfig(bandwidth_hz=40_000_000,
                                              numerology=2),
                        tdd=TDDConfig(pattern="DSUUU"), ues=ues, flows=flows,
                        seed=seed)
    validate_handshake_wiring(sc)
    return sc


def gt61_warm_rejoin(seed: int = 1, n_neighbours: int = 7,
                     n_cycles: int = 10, horizon_slots: int = 20_000,
                     first_slot: int = 2000, period_slots: int = 1600,
                     bg: bool = True) -> ScenarioConfig:
    """GT-6.1: repeated app restarts on the joiner under neighbour load.

    `n_cycles` restarts because the pass line is a **p95 over cycles**; one
    event gives no percentile. The campaign's 50 cycles come from running
    this across seeds, not from one very long run.
    """
    events = tuple(JoinEvent(slot=first_slot + i * period_slots,
                             kind="app_restart") for i in range(n_cycles))
    join = JoinConfig(events=events, handshake_ul_qfi=QFI_HANDSHAKE_UL,
                      handshake_dl_qfi=QFI_HANDSHAKE_DL)
    return _build(f"g9_gt61_warm_n{n_neighbours}", n_neighbours=n_neighbours,
                  join=join, seed=seed, horizon_slots=horizon_slots, bg=bg)


def gt62_cold_attach(seed: int = 1, n_neighbours: int = 7, n_cycles: int = 5,
                     horizon_slots: int = 20_000, first_slot: int = 2000,
                     off_slots: int = 800, period_slots: int = 3000,
                     bg: bool = True) -> ScenarioConfig:
    """GT-6.2: repeated power-cycles. GT-6.2's own pass line is "10
    consecutive cycles", which is why `JoinConfig.events` is a list.

    **Clause 2's number is NOT independent evidence** (§31.1, regime map's
    G9 row): the attach delay is sampled between this deployment's own
    t300/t301/t311 ceilings and one RACH trace, so a p95 restates the
    configuration. Built anyway, because the *cold path's* effect on
    NEIGHBOURS is a real measurement even when its own latency is not.
    """
    events = []
    for i in range(n_cycles):
        base = first_slot + i * period_slots
        events += [JoinEvent(slot=base, kind="power_off"),
                   JoinEvent(slot=base + off_slots, kind="power_on")]
    join = JoinConfig(events=tuple(events), initial_state="connected",
                      handshake_ul_qfi=QFI_HANDSHAKE_UL,
                      handshake_dl_qfi=QFI_HANDSHAKE_DL)
    return _build(f"g9_gt62_cold_n{n_neighbours}", n_neighbours=n_neighbours,
                  join=join, seed=seed, horizon_slots=horizon_slots, bg=bg)


# sim/rlf.py's RlfDetectorConfig, from the gNB startup banner: t310 = 2000 ms,
# n310 = 10, n311 = 1. The driver constructs RlfDetectorConfig() with these
# defaults, so they -- not JoinConfig.rlf_snr_floor_db -- are what a fade has
# to defeat. At numerology 2 (0.25 ms slots) t310 alone is 8,000 SLOTS.
_T310_MS = 2000.0
_SLOT_MS_MU2 = 0.25
T310_SLOTS_MU2 = int(_T310_MS / _SLOT_MS_MU2)   # 8,000


def gt63_rlf_recovery(seed: int = 1, n_neighbours: int = 7,
                      horizon_slots: int = 30_000, fade_start_slot: int = 4000,
                      fade_slots: int = 12_000, fade_extra_loss_db: float = 35.0,
                      bg: bool = True) -> ScenarioConfig:
    """GT-6.3: a scripted deep fade drives RLF, then recovery.

    RLF is **never scripted as an event** -- it is emergent, driven by
    `sim/rlf.py` observing the real SNR trace (`JoinEvent`'s own docstring).
    So this scenario scripts only the FADE; the join schedule is empty.

    **THE FADE MUST OUTLAST t310, AND THE FIRST VERSION OF THIS BUILDER DID
    NOT.** t310 is 2,000 ms = **8,000 slots** at numerology 2; a 4,000-slot
    fade let the dwell re-arm and **produced ZERO RLF events**, which reads
    as "recovery was instant" rather than as a scenario that never fired.
    Default is now 12,000 slots (1.5x t310), asserted by
    `sim/tests/test_g9_scenarios.py`.

    **Divergence from the test plan, stated:** GT-6.3 specifies a **10 s**
    obstruction. 10 s is 40,000 slots here, which needs a ~60,000-slot
    horizon. The detector only requires t310 to expire, so this uses 3 s --
    enough to declare RLF with margin, at a fifth of the run cost. The
    10 s figure is the hardware's obstruction duration, not a threshold the
    detection depends on.
    """
    join = JoinConfig(events=(), handshake_ul_qfi=QFI_HANDSHAKE_UL,
                      handshake_dl_qfi=QFI_HANDSHAKE_DL)
    # 35 dB of extra loss puts a 20 dB UE at -15 dB, below the DETECTOR's
    # own rlf_snr_floor_db of -5.0 (RlfDetectorConfig, which is what the
    # driver constructs -- NOT JoinConfig's identically-named field). Depth
    # arms t310; DURATION is what expires it, and both are needed.
    fade = ScriptedFadeWindow(start_slot=fade_start_slot,
                              end_slot=fade_start_slot + fade_slots,
                              extra_loss_db=fade_extra_loss_db)
    return _build(f"g9_gt63_rlf_n{n_neighbours}", n_neighbours=n_neighbours,
                  join=join, seed=seed, horizon_slots=horizon_slots, fade=fade,
                  bg=bg)
