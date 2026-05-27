"""The scheduler's I/O contract.

`Allocation` is what the scheduler emits; `Scheduler` is the protocol it
satisfies. The slot / buffer / channel state it reads is described by the
structural views below -- a concrete simulator type (or an OAI adapter)
satisfies a view simply by having the right attributes / methods, with no
inheritance. This keeps the `scheduler` package dependent on nothing
outside itself.

HARQ additions (feat/harq-bler-retx)
-------------------------------------
Three new fields on Allocation support the HARQEngine in driver.py:

    harq_pid          identifies which of the 16 HARQ processes carries
                      this TB, so the engine can match a retx allocation
                      to its pending-state entry.

    is_retx           True when the HARQEngine inserts this allocation as
                      a retransmission.  Schedulers always emit False;
                      only the engine sets True.

    harq_ue_direction  redundant with (ue_id, direction) but carried
                      explicitly so the engine's pending-state key
                      (ue_id, direction, pid) can be reconstructed from
                      the Allocation alone without extra lookups.

Backward compatibility
-----------------------
All three fields default to safe no-op values (-1 / False / ""), so every
existing Allocation construction site continues to work unchanged.  The
driver checks ``is_retx`` to decide whether to drain the buffer; when
False it behaves exactly as before (minus the flat-BLER discount, which
moves into HARQEngine).
"""

from dataclasses import dataclass, field
from typing import Protocol

from .flow import FlowConfig


@dataclass
class Allocation:
    """One flow's share of a per-UE grant for a slot. A multi-flow UE grant
    is emitted as several Allocations; the grant's PRB count and DCI cost
    ride on the first.

    Fields
    ------
    ue_id, qfi, direction, prbs, bytes_capacity, cce_cost, is_sps
        Unchanged from the original contract.

    harq_pid : int
        HARQ process identifier (0-15).  Set by the HARQEngine when it
        creates a retx Allocation, and by the scheduler's emit-grant path
        when it records a new transmission.  Default -1 means "not tracked"
        (pre-HARQ allocations and padding entries).

    is_retx : bool
        True only for Allocations inserted by HARQEngine as retransmissions.
        Schedulers must never set this; it is set exclusively by the engine.
        The driver skips buffer drain for retx allocations and waits for the
        engine's outcome decision instead.

    harq_ue_direction : str
        Copy of ``direction`` carried on the Allocation so the HARQEngine
        can reconstruct the pending-state key ``(ue_id, harq_ue_direction,
        harq_pid)`` from the Allocation alone.  Empty string when harq_pid
        is -1.
    """

    ue_id: int
    qfi: int
    direction: str          # 'DL' or 'UL'
    prbs: int
    bytes_capacity: int
    cce_cost: int = 0
    is_sps: bool = False

    # --- HARQ fields (feat/harq-bler-retx) ---
    harq_pid: int = -1                  # -1 → not HARQ-tracked
    is_retx: bool = False               # True only when HARQEngine inserts retx
    harq_ue_direction: str = ""         # mirrors direction; "" when harq_pid==-1


# ---------------------------------------------------------------------------
# Slot / grid / buffer / channel views (unchanged)
# ---------------------------------------------------------------------------

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