"""The scheduler's I/O contract.

`Allocation` is what the scheduler emits; `Scheduler` is the protocol it
satisfies. The slot / buffer / channel state it reads is described by the
structural views below -- a concrete simulator type (or an OAI adapter)
satisfies a view simply by having the right attributes / methods, with no
inheritance. This keeps the `scheduler` package dependent on nothing
outside itself.
"""

from dataclasses import dataclass
from typing import Protocol

from .flow import FlowConfig


@dataclass
class Allocation:
    """One flow's share of a per-UE grant for a slot. A multi-flow UE grant
    is emitted as several Allocations; the grant's PRB count and DCI cost
    ride on the first."""

    ue_id: int
    qfi: int
    direction: str  # 'DL' or 'UL'
    prbs: int
    bytes_capacity: int
    cce_cost: int = 0
    is_sps: bool = False


class SlotView(Protocol):
    """One slot's resource grid, as the scheduler reads it."""

    slot_index: int
    dl_symbols: int
    ul_symbols: int
    prb_count: int
    pdcch_cce_budget: int


class GridView(Protocol):
    """The TDD resource grid over one pattern cycle."""

    pattern: str
    prb_count: int
    slot_duration_s: float

    def slot_grid(self, slot_index: int) -> SlotView: ...


class BufferStateView(Protocol):
    bytes_queued: int


class BufferView(Protocol):
    """Per-(UE, QFI) buffer status the scheduler reads -- a buffer-status
    report in 5G terms."""

    def state(self, ue_id: int, qfi: int) -> BufferStateView: ...

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float: ...

    def arrived_cum(self, ue_id: int, qfi: int) -> int: ...

    def delivered_cum(self, ue_id: int, qfi: int) -> int: ...


class ChannelView(Protocol):
    """Per-UE channel quality the scheduler reads -- a CQI report in 5G
    terms."""

    def get_snr_db(self, ue_id: int) -> float: ...


class Scheduler(Protocol):
    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: GridView,
    ) -> None: ...

    def allocate(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
    ) -> list[Allocation]: ...
