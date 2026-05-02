from dataclasses import dataclass, field
from typing import Literal


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
class FlowConfig:
    ue_id: int
    qfi: int
    direction: Literal["DL", "UL"]
    flow_class: Literal["PF", "GBR", "Delay"] = "PF"
    pdb_ms: float = 100.0
    gfbr_bps: float = 0.0
    traffic_kind: str = "poisson"
    traffic_params: dict = field(default_factory=dict)


@dataclass
class ScenarioConfig:
    name: str
    horizon_slots: int
    carrier: CarrierConfig = field(default_factory=CarrierConfig)
    tdd: TDDConfig = field(default_factory=TDDConfig)
    ues: list[UEConfig] = field(default_factory=list)
    flows: list[FlowConfig] = field(default_factory=list)
    seed: int = 42
