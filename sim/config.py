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


@dataclass
class UEConfig:
    ue_id: int
    mean_snr_db: float = 20.0
    coherence_slots: int = 100


@dataclass
class ScenarioConfig:
    name: str
    horizon_slots: int
    carrier: CarrierConfig = field(default_factory=CarrierConfig)
    tdd: TDDConfig = field(default_factory=TDDConfig)
    ues: list[UEConfig] = field(default_factory=list)
    flows: list[FlowConfig] = field(default_factory=list)
    seed: int = 42
