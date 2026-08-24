"""Simulator scenario configuration: the radio (carrier, TDD), the UEs, and
the run window.

The per-flow QoS descriptor ``FlowConfig`` belongs to the ``scheduler``
library (it is a scheduler input); it is re-exported here so a scenario has
a single config import surface.
"""

from dataclasses import dataclass, field

from scheduler.flow import FlowConfig

__all__ = [
    "TDDConfig",
    "CarrierConfig",
    "BlockageConfig",
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
