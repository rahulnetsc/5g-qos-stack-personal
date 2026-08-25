"""Simulator scenario configuration: the radio (carrier, TDD), the UEs, and
the run window.

The per-flow QoS descriptor ``FlowConfig`` belongs to the ``scheduler``
library (it is a scheduler input); it is re-exported here so a scenario has
a single config import surface.
"""

from dataclasses import dataclass, field

from scheduler.flow import FlowConfig

from .join import JoinConfig

__all__ = [
    "TDDConfig",
    "CarrierConfig",
    "BlockageConfig",
    "ScriptedFadeWindow",
    "UEConfig",
    "FlowConfig",
    "ScenarioConfig",
]


@dataclass
class TDDConfig:
    pattern: str = "DSUUU"
    s_slot_split: tuple[int, int, int] = (3, 2, 9)


@dataclass
class CarrierConfig:
    bandwidth_hz: int = 30_000_000
    numerology: int = 1
    overhead_factor: float = 0.85
    # WP6: real deployed centre frequency, not invented -- band 78, gNB
    # startup log's own frequency computation (calibration-logs/
    # twotier_startup_gnb.log: "nrarfcn 621312 => 3319680 KHz"). Only
    # consumed by sim/pathloss.py for a UE that opts into position-derived
    # SNR (UEConfig.position); otherwise unused, same as every other field
    # here for a scenario that doesn't reference it.
    center_freq_ghz: float = 3.31968


@dataclass(frozen=True)
class BlockageConfig:
    """Two-state Markov blockage (docs/wp6-plan.md Decision 3, sim/
    blockage.py). Dwell times in slots, not milliseconds -- matching
    ``k1_slots``/``k2_slots``/``cqi_delay_slots``/``sr_period_slots``'s
    own convention, and numerology-agnostic the same way those are.

    No ground truth (literature or vendored) exists in this repo for
    factory blockage rate/duration -- these defaults are an order-of-
    magnitude anchor to ``p5g-sim-plan.md``'s own "hundreds of
    milliseconds" motivating text (at this deployment's 0.5ms/slot,
    600 slots = 300ms), not a confirmed value. Nothing about the
    mechanism itself restricts ``mean_blocked_slots`` to that regime --
    see ``sim/tests/test_blockage.py`` for the same construction
    exercised at a "short" (shorter-than-a-HARQ-retry-cycle) setting too.
    """

    mean_unblocked_slots: int = 4000
    mean_blocked_slots: int = 600
    blocked_extra_loss_db: float = 17.5  # midpoint of p5g-sim-plan.md's cited 15-20dB


@dataclass(frozen=True)
class ScriptedFadeWindow:
    """A single scripted, deterministic SNR fade window (WP-Join commit 3,
    docs/wp-join-plan.md sec1.5). Unlike ``BlockageConfig`` -- a stochastic
    two-state Markov process, no ground truth for its dwell times -- this
    is a scenario-authored, EXACT depth over an EXACT slot range: GT-6.3's
    join/RLF acceptance tests need a known, repeatable fade that crosses a
    known SNR threshold at a known time, which a stochastic process
    structurally cannot guarantee. ``sim/channel.py::ChannelModel`` forces
    ``snr_db`` deterministically (no AR(1) noise) for every slot in
    ``[start_slot, end_slot)``, and resets it cleanly to the clean mean at
    ``end_slot`` -- both ends of the window are exact, not statistical."""

    start_slot: int
    end_slot: int
    extra_loss_db: float

    def __post_init__(self) -> None:
        if self.start_slot < 0:
            raise ValueError(f"start_slot must be >= 0 (got {self.start_slot})")
        if self.end_slot <= self.start_slot:
            raise ValueError(f"end_slot must be > start_slot (got {self.end_slot} <= {self.start_slot})")
        if self.extra_loss_db < 0.0:
            raise ValueError(f"extra_loss_db must be >= 0 (got {self.extra_loss_db})")


@dataclass
class UEConfig:
    ue_id: int
    mean_snr_db: float = 20.0
    coherence_slots: int = 100
    # WP6 (docs/wp6-plan.md Decision 2): opt-in TR 38.901 InF path loss.
    # None (default) preserves today's behaviour exactly -- mean_snr_db
    # stays the scenario author's own hand-picked value. When set, sim/
    # channel.py derives mean_snr_db from position + inf_scenario instead
    # (sim/pathloss.py), and mean_snr_db above is ignored for this UE.
    position: tuple[float, float, float] | None = None
    inf_scenario: str | None = None  # one of sim.pathloss.INF_SUB_SCENARIOS
    # WP6 (docs/wp6-plan.md Decision 3): opt-in two-state Markov blockage.
    # None (default) preserves today's behaviour exactly. Independent of
    # position/inf_scenario -- composes as a further dB penalty on
    # whichever mean_snr_db is already in effect, hand-authored or
    # path-loss-derived.
    blockage: BlockageConfig | None = None
    # WP-Join commit 3 (docs/wp-join-plan.md sec1.5): opt-in, deterministic
    # scripted SNR fade -- () (default) preserves today's behaviour
    # exactly. Independent of position/blockage; composes as a further,
    # exact dB penalty on whichever mean/blockage-adjusted mean is already
    # in effect while a window is active. Built to make sync loss (sim/
    # rlf.py) reachable at all and its recovery-path timing exact -- see
    # that module and sim/join.py for why blockage's own stochastic
    # process can't serve this role.
    scripted_fade: tuple[ScriptedFadeWindow, ...] = ()
    # WP-Join commit 5 (docs/wp-join-plan.md sec1.3/sec1.4): opt-in
    # join/re-join/RLF-recovery state machine. None (default) preserves
    # today's behaviour exactly -- this UE is never radio-gated, sim/
    # rlf.py::step() runs unconditionally for it (WP-Join commit 2's
    # existing behaviour), and sim/driver.py never constructs a sim/
    # join.py::JoinState for it at all. See sim/join.py's own docstring
    # for what setting this does.
    join: JoinConfig | None = None


@dataclass
class ScenarioConfig:
    name: str
    horizon_slots: int
    carrier: CarrierConfig = field(default_factory=CarrierConfig)
    tdd: TDDConfig = field(default_factory=TDDConfig)
    ues: list[UEConfig] = field(default_factory=list)
    flows: list[FlowConfig] = field(default_factory=list)
    seed: int = 42
    # WP6: gNB position for UEs that opt into position-derived SNR
    # (UEConfig.position). Always present, harmless when unused -- no
    # existing scenario sets any UE's position, so this default is never
    # read by anything today.
    gnb_position: tuple[float, float, float] = (0.0, 0.0, 8.0)
