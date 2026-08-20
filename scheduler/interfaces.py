"""The scheduler's I/O contract.

`Allocation` is what the scheduler emits; `Scheduler` is the protocol it
satisfies. The slot / buffer / channel state it reads is described by the
structural views below -- a concrete simulator type (or an OAI adapter)
satisfies a view simply by having the right attributes / methods, with no
inheritance. This keeps the `scheduler` package dependent on nothing
outside itself.
"""

import math
from dataclasses import dataclass
from typing import Protocol

from .flow import FlowConfig


@dataclass
class Allocation:
    """One flow's share of a per-UE grant for a slot. A multi-flow UE grant
    is emitted as several Allocations; the grant's PRB count and DCI cost
    ride on the first.

    ``snr_used_db`` is the SNR view the scheduler used to pick the MCS for
    this grant -- reported (CQI-lagged) SNR for a dynamic grant, or the
    conservative SPS-configured SNR for an SPS grant. The driver uses it to
    compute a mismatch-aware BLER against the true SNR at transmission
    time: when the true SNR falls below the picked MCS's threshold, BLER
    climbs. Leaving it NaN (the default) falls back to the legacy behaviour
    (BLER derived from bits_per_prb at true SNR), used by tests that don't
    care about MCS mismatch.
    """

    ue_id: int
    qfi: int
    direction: str  # 'DL' or 'UL'
    prbs: int
    bytes_capacity: int
    cce_cost: int = 0
    is_sps: bool = False
    snr_used_db: float = math.nan
    # True for an *uplink* grant, where the scheduler sizes the transport
    # block but does not choose how the UE fills it: the UE runs its own
    # logical-channel prioritisation (TS 38.321 sec 5.4.3.1). ``qfi`` is then
    # meaningless (-1) and ``bytes_capacity`` is the whole block; the host
    # splits it across the UE's flows. Downlink grants keep ue_grant=False
    # and are emitted per flow, because there the gNB really does choose.
    ue_grant: bool = False


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
    # Actual queued bytes (gNB's exact view). For a UE-side (uplink) buffer
    # in real 5G the gNB only learns this via a quantised, event-triggered
    # BSR (see sim/bsr.py); ``bytes_reported`` below is the *scheduling-
    # visible* view. For downlink (gNB-side buffer) bytes_reported ==
    # bytes_queued always -- no BSR needed, the gNB IS the DL buffer.
    #
    # Dynamic scheduling decisions (eligibility, UE ranking, grant sizing)
    # should read ``bytes_reported``. Once a UE has a grant, the MAC
    # multiplexer fills the transport block with ``bytes_queued`` (real
    # data) -- BSR only affects the *decision*, not the fill. SPS /
    # Configured Grants read ``bytes_queued`` directly (they need no BSR).
    bytes_queued: int
    bytes_reported: int
    # This flow's logical channel group (0-7; -1 for DL / not BSR-managed).
    # A real BSR is per-LCG, not per-flow -- every UL flow sharing an LCG
    # sees the identical estimated_ul_buffer_per_lcg, because that is all
    # the gNB actually knows past that point (see README §4/§7).
    lcg: int
    # The gNB's raw per-LCG BSR estimate for this flow's lcg -- frozen
    # since the last BSR (not drained by grants, per README §7's WP3
    # finding), and NOT capped by the sched_ul_bytes gate the way
    # bytes_reported is. Use this to reason about the per-LCG estimate
    # itself, distinct from the UE-wide collapse-to-crumb view.
    estimated_ul_buffer_per_lcg: int


class BufferView(Protocol):
    """Per-(UE, QFI) buffer status the scheduler reads -- a buffer-status
    report in 5G terms. See BufferStateView for the bytes_queued vs
    bytes_reported split (real vs BSR-visible)."""

    def state(self, ue_id: int, qfi: int) -> BufferStateView: ...

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float: ...

    def arrived_cum(self, ue_id: int, qfi: int) -> int: ...

    def delivered_cum(self, ue_id: int, qfi: int) -> int: ...

    # Cumulative bytes discarded on PDB expiry. A demand estimate built from
    # delivered + backlog alone silently omits these, so a starved flow whose
    # data ages out looks like it stopped asking -- see
    # TwoTier._update_demand_estimate. A real gNB knows its own RLC discards.
    def dropped_cum(self, ue_id: int, qfi: int) -> int: ...


class ChannelView(Protocol):
    """Per-UE channel quality the scheduler reads -- a CQI report in 5G
    terms.

    ``get_snr_db`` returns the *true* instantaneous SNR (used by the driver
    at transmission time to compute actual BLER).
    ``get_reported_snr_db`` returns the *CQI-visible* SNR the scheduler is
    entitled to see: it lags the true SNR by ``cqi_delay_slots`` for
    UEs the host has enabled CQI delay for (real 5G: CQI is measured, then
    reported on PUCCH with a period + processing delay). Dynamic
    scheduling decisions read the reported view; SPS reservations pick a
    conservative MCS at reservation time from the smoothed reported view.
    """

    def get_snr_db(self, ue_id: int) -> float: ...

    def get_reported_snr_db(self, ue_id: int) -> float: ...


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
