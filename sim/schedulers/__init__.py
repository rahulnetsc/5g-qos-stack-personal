from dataclasses import dataclass
from typing import Protocol

from ..buffer import BufferModel
from ..channel import ChannelModel
from ..config import FlowConfig
from ..resource import ResourceGrid, SlotGrid


# Fallback PDCCH aggregation level when channel SNR is unavailable.
# Schedulers should normally call sim.channel.cce_aggregation_level(snr) to
# pick a per-UE AL. SPS allocations carry cce_cost=0 unconditionally.
DEFAULT_DCI_CCE_COST = 4


@dataclass
class Allocation:
    ue_id: int
    qfi: int
    direction: str  # 'DL' or 'UL'
    prbs: int
    bytes_capacity: int
    cce_cost: int = 0
    is_sps: bool = False


class Scheduler(Protocol):
    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: ResourceGrid,
    ) -> None: ...

    def allocate(
        self,
        slot: SlotGrid,
        buffers: BufferModel,
        channel: ChannelModel,
    ) -> list[Allocation]: ...
