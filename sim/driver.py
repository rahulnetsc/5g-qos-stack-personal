"""Simulation driver -- slot loop, HARQEngine, buffer and metrics wiring.

HARQ additions (feat/harq-bler-retx)
--------------------------------------
``HARQEngine`` sits between the scheduler output and the buffer/metrics layer.
It is transparent to all schedulers: they emit ``Allocation`` objects unchanged;
the engine wraps the slot view (reducing prb_count by carved-out retx PRBs),
inserts retx ``Allocation`` objects ahead of the scheduler's new-TX output, and
evaluates per-TB success/failure using ``bler_sigmoid`` + ``combining_gain_db``.

Buffer semantics with HARQ
---------------------------
Bytes are drained from the buffer on **confirmed ACK only** -- not on first
transmission.  While a TB is in-flight (first TX sent, ACK not yet received),
its bytes remain in the real buffer but are hidden from the scheduler via
``_HARQAwareBufferView``, which subtracts in-flight bytes from ``bytes_queued``.
This ensures:

  1. ``buffers.delivered_cum`` only increments on confirmed ACK, so TwoTier's
     windowed ceiling calculation (which uses ``delivered_cum`` to estimate how
     much has actually been received) remains accurate.

  2. The scheduler never re-schedules in-flight bytes because the aware view
     shows those bytes as unavailable.

  3. On MAX_RETX abandon, the bytes are drained and counted as lost.

Backward compatibility
-----------------------
``run(..., harq=False)`` restores the pre-HARQ flat-BLER path exactly:
deterministic ``delivered = bytes_capacity * (1 - 0.10)`` per allocation,
immediate buffer drain, no retx overhead.  The comparative study uses this
to produce the optimistic baseline.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .buffer import BufferModel
from .channel import ChannelModel, bits_per_prb
from .config import ScenarioConfig
from .metrics import Metrics
from .resource import ResourceGrid
from scheduler import Scheduler
from scheduler.interfaces import Allocation
from scheduler.link import bler_sigmoid, combining_gain_db, bits_per_prb as _lbpp
from .traffic import TrafficModel


# ---------------------------------------------------------------------------
# HARQ process state
# ---------------------------------------------------------------------------

@dataclass
class _HARQEntry:
    """State for one in-flight HARQ process."""
    ue_id: int
    qfi: int
    direction: str
    pid: int
    tb_bytes: int       # original TB size -- retx sends same byte count
    retx_count: int     # attempts so far (1 = first retx pending)
    due_slot: int       # slot index when next retx should fire


class _ReducedSlotView:
    """SlotView wrapper that hides retx-carved PRBs from the scheduler."""

    __slots__ = ("_inner", "_retx_prbs")

    def __init__(self, inner, retx_prbs: int) -> None:
        self._inner = inner
        self._retx_prbs = retx_prbs

    @property
    def slot_index(self) -> int:        return self._inner.slot_index
    @property
    def dl_symbols(self) -> int:        return self._inner.dl_symbols
    @property
    def ul_symbols(self) -> int:        return self._inner.ul_symbols
    @property
    def pdcch_cce_budget(self) -> int:  return self._inner.pdcch_cce_budget
    @property
    def prb_count(self) -> int:
        return max(0, self._inner.prb_count - self._retx_prbs)


@dataclass
class _AdjustedBufferState:
    """BufferStateView with bytes_queued reduced by in-flight bytes."""
    bytes_queued: int


class _HARQAwareBufferView:
    """BufferView wrapper that subtracts in-flight HARQ bytes from bytes_queued.

    Passed to the scheduler instead of the real buffer when HARQ is active.
    This prevents the scheduler from re-scheduling bytes that are already
    in a HARQ process waiting for ACK/retx.  All other methods (arrived_cum,
    delivered_cum, hol_delay_s) delegate to the real buffer unchanged.

    Because bytes are now drained on ACK rather than first TX,
    ``delivered_cum`` only increments when bytes are confirmed received --
    which is exactly what TwoTier's windowed ceiling needs.
    """

    __slots__ = ("_buf", "_engine")

    def __init__(self, buf: BufferModel, engine: "HARQEngine") -> None:
        self._buf = buf
        self._engine = engine

    def state(self, ue_id: int, qfi: int) -> _AdjustedBufferState:
        real = self._buf.state(ue_id, qfi)
        in_flight = self._engine.get_in_flight(ue_id, qfi)
        return _AdjustedBufferState(max(0, real.bytes_queued - in_flight))

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        return self._buf.hol_delay_s(ue_id, qfi, now_s)

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        return self._buf.arrived_cum(ue_id, qfi)

    def delivered_cum(self, ue_id: int, qfi: int) -> int:
        # With HARQ this now reflects only ACK-confirmed bytes, not first-TX
        # drains.  TwoTier's windowed ceiling uses this to estimate delivery.
        return self._buf.delivered_cum(ue_id, qfi)

    def keys(self):
        return self._buf.keys()


# ---------------------------------------------------------------------------
# HARQ engine
# ---------------------------------------------------------------------------

class HARQEngine:
    """HARQ process manager and BLER evaluator.

    One instance per simulation run, shared across all scheduler types.

    Parameters
    ----------
    rng : numpy Generator
        Shared RNG from the simulation run (ensures reproducibility).
    max_retx : int
        Maximum retransmission attempts (excluding the original TX).
        Default 3 matches TS 38.321 §5.4.2 ``maxRetxThreshold``.
    combining_mode : str
        ``"ir"`` (incremental redundancy, 5G NR default) or ``"chase"``.
    harq_rtt : int
        Minimum slots between original TX and first retransmission.
        Default 8 (conservative; correct for FDD μ=1 and most TDD patterns).
    ewma_alpha : float
        EWMA smoothing for the per-UE SNR operating point.
        0.1 → ~10-slot averaging; matches two_tier's internal _snr_avg.
    """

    N_PROCS: int = 16   # 5G NR: 16 HARQ processes per UE per direction

    def __init__(
        self,
        rng: np.random.Generator,
        max_retx: int = 3,
        combining_mode: str = "ir",
        harq_rtt: int = 8,
        ewma_alpha: float = 0.1,
    ) -> None:
        self._rng = rng
        self._max_retx = max_retx
        self._combining_mode = combining_mode
        self._harq_rtt = harq_rtt
        self._ewma_alpha = ewma_alpha

        self._snr_ewma: dict[int, float] = {}
        self._pending: dict[tuple[int, str, int], _HARQEntry] = {}
        self._next_pid: dict[tuple[int, str], int] = defaultdict(int)

        # In-flight bytes per (ue_id, qfi): bytes sent but not yet ACK'd.
        # Drained from buffer only on ACK or MAX_RETX abandon.
        self._in_flight: dict[tuple[int, int], int] = defaultdict(int)

    def configure(self, ues) -> None:
        for ue in ues:
            self._snr_ewma[ue.ue_id] = ue.mean_snr_db

    def update_ewma(self, channel: ChannelModel) -> None:
        a = self._ewma_alpha
        for ue_id in self._snr_ewma:
            snr = channel.get_snr_db(ue_id)
            self._snr_ewma[ue_id] = a * snr + (1.0 - a) * self._snr_ewma[ue_id]

    # ------------------------------------------------------------------
    # In-flight byte tracking
    # ------------------------------------------------------------------

    def mark_in_flight(self, ue_id: int, qfi: int, tb_bytes: int) -> None:
        """Record that tb_bytes are now in a HARQ process, not yet ACK'd."""
        self._in_flight[(ue_id, qfi)] += tb_bytes

    def unmark_in_flight(self, ue_id: int, qfi: int, tb_bytes: int) -> None:
        """Remove tb_bytes from the in-flight count (on ACK or abandon)."""
        key = (ue_id, qfi)
        self._in_flight[key] = max(0, self._in_flight[key] - tb_bytes)

    def get_in_flight(self, ue_id: int, qfi: int) -> int:
        """Return bytes currently in HARQ processes for this flow."""
        return self._in_flight.get((ue_id, qfi), 0)

    # ------------------------------------------------------------------
    # Retx slot management
    # ------------------------------------------------------------------

    def get_retx_allocs(
        self,
        slot_index: int,
        slot_grid,
        channel: ChannelModel,
    ) -> list[Allocation]:
        """Return Allocation(is_retx=True) for every process due this slot."""
        allocs: list[Allocation] = []
        for key, entry in list(self._pending.items()):
            if entry.due_slot > slot_index:
                continue

            if entry.direction == "DL" and slot_grid.dl_symbols == 0:
                entry.due_slot = slot_index + 1
                continue
            if entry.direction == "UL" and slot_grid.ul_symbols == 0:
                entry.due_slot = slot_index + 1
                continue

            symbols = (
                slot_grid.dl_symbols
                if entry.direction == "DL"
                else slot_grid.ul_symbols
            )
            snr_inst = channel.get_snr_db(entry.ue_id)
            gain = combining_gain_db(entry.retx_count, self._combining_mode)
            bits, _ = _lbpp(snr_inst + gain, symbols=symbols)
            prbs = (
                math.ceil(entry.tb_bytes * 8 / bits)
                if bits > 0
                else slot_grid.prb_count
            )

            allocs.append(
                Allocation(
                    ue_id=entry.ue_id,
                    qfi=entry.qfi,
                    direction=entry.direction,
                    prbs=min(prbs, slot_grid.prb_count),
                    bytes_capacity=entry.tb_bytes,
                    cce_cost=0,
                    is_sps=False,
                    harq_pid=entry.pid,
                    is_retx=True,
                    harq_ue_direction=entry.direction,
                )
            )
        return allocs

    # ------------------------------------------------------------------
    # Outcome evaluation
    # ------------------------------------------------------------------

    def process_outcome(
        self,
        alloc: Allocation,
        slot_index: int,
        channel: ChannelModel,
    ) -> tuple[int, bool]:
        """Sample BLER and decide ACK / NACK for one allocation.

        Returns
        -------
        (delivered_bytes, abandoned)
            delivered_bytes > 0, abandoned=False  →  ACK
            delivered_bytes = 0, abandoned=False  →  NACK, retx scheduled
            delivered_bytes = 0, abandoned=True   →  NACK after MAX_RETX
        """
        snr_inst = channel.get_snr_db(alloc.ue_id)
        snr_ewma = self._snr_ewma.get(alloc.ue_id, snr_inst)

        if alloc.is_retx:
            key = (alloc.ue_id, alloc.harq_ue_direction, alloc.harq_pid)
            entry = self._pending.get(key)
            retx_count = entry.retx_count if entry else 1
        else:
            if alloc.harq_pid < 0:
                pid_key = (alloc.ue_id, alloc.direction)
                alloc.harq_pid = self._next_pid[pid_key]
                self._next_pid[pid_key] = (alloc.harq_pid + 1) % self.N_PROCS
                alloc.harq_ue_direction = alloc.direction
            retx_count = 0

        gain = combining_gain_db(retx_count, self._combining_mode)
        delta = (snr_inst + gain) - snr_ewma
        bler = bler_sigmoid(delta)
        success = bool(self._rng.random() > bler)

        if success:
            if alloc.is_retx:
                self._pending.pop(
                    (alloc.ue_id, alloc.harq_ue_direction, alloc.harq_pid), None
                )
            return alloc.bytes_capacity, False

        # --- NACK path ---
        if alloc.is_retx:
            key = (alloc.ue_id, alloc.harq_ue_direction, alloc.harq_pid)
            entry = self._pending.get(key)
            if entry is None:
                return 0, True
            if entry.retx_count >= self._max_retx:
                self._pending.pop(key)
                return 0, True
            entry.retx_count += 1
            entry.due_slot = slot_index + self._harq_rtt
        else:
            pkey = (alloc.ue_id, alloc.direction, alloc.harq_pid)
            self._pending[pkey] = _HARQEntry(
                ue_id=alloc.ue_id,
                qfi=alloc.qfi,
                direction=alloc.direction,
                pid=alloc.harq_pid,
                tb_bytes=alloc.bytes_capacity,
                retx_count=1,
                due_slot=slot_index + self._harq_rtt,
            )
        return 0, False


# ---------------------------------------------------------------------------
# Simulation run loop
# ---------------------------------------------------------------------------

def run(
    scenario: ScenarioConfig,
    scheduler: Scheduler,
    record_timeseries: bool = False,
    harq: bool = False,
    max_retx: int = 3,
    combining_mode: str = "ir",
    harq_rtt: int = 8,
    ewma_alpha: float = 0.1,
) -> dict:
    """Run the scenario and return a summary dict.

    Parameters
    ----------
    harq : bool
        True  → stochastic sigmoid BLER + HARQ retransmissions.
                 Bytes are drained from the buffer on confirmed ACK only.
                 The scheduler receives ``_HARQAwareBufferView`` which hides
                 in-flight bytes, preventing double-scheduling.
        False → legacy deterministic flat-10 % BLER, immediate drain.
                 Identical to the pre-HARQ baseline.  Default.
    """
    rng = np.random.default_rng(scenario.seed)
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    channel = ChannelModel(scenario.ues, rng)
    buffers = BufferModel()
    traffic = TrafficModel(scenario.flows, buffers, grid.slot_duration_s, rng)
    metrics = Metrics(record_timeseries=record_timeseries)
    metrics.set_harq_enabled(harq)

    scheduler.configure(scenario.flows, grid.slot_duration_s, grid)

    engine: HARQEngine | None = None
    buf_view = buffers   # what the scheduler sees; replaced by aware view with HARQ
    if harq:
        engine = HARQEngine(
            rng,
            max_retx=max_retx,
            combining_mode=combining_mode,
            harq_rtt=harq_rtt,
            ewma_alpha=ewma_alpha,
        )
        engine.configure(scenario.ues)
        buf_view = _HARQAwareBufferView(buffers, engine)

    pdb_by_flow = {(f.ue_id, f.qfi): f.pdb_ms / 1000.0 for f in scenario.flows}
    horizon_s = scenario.horizon_slots * grid.slot_duration_s

    for slot_index in range(scenario.horizon_slots):
        now_s = slot_index * grid.slot_duration_s

        # --- Traffic arrival ---
        per_flow_arrived: dict[tuple[int, int], int] = defaultdict(int)
        for ue_id, qfi, byts in traffic.generate(slot_index):
            metrics.record_arrival(ue_id, qfi, byts)
            per_flow_arrived[(ue_id, qfi)] += byts

        # --- Channel update ---
        channel.update(slot_index)
        if engine is not None:
            engine.update_ewma(channel)

        slot_grid = grid.slot_grid(slot_index)
        metrics.record_grid_capacity(
            dl_prbs=slot_grid.prb_count if slot_grid.dl_symbols > 0 else 0,
            ul_prbs=slot_grid.prb_count if slot_grid.ul_symbols > 0 else 0,
        )

        # --- Build allocation list ---
        if engine is not None:
            retx_allocs = engine.get_retx_allocs(slot_index, slot_grid, channel)
            retx_prbs = sum(a.prbs for a in retx_allocs)
            sched_slot = _ReducedSlotView(slot_grid, retx_prbs)
        else:
            retx_allocs = []
            sched_slot = slot_grid

        # Scheduler sees buf_view (aware view with HARQ, real buffer without).
        new_allocs = scheduler.allocate(sched_slot, buf_view, channel)
        all_allocs = retx_allocs + new_allocs

        # --- Process allocations ---
        per_flow_delivered: dict[tuple[int, int], int] = defaultdict(int)
        per_flow_dropped:   dict[tuple[int, int], int] = defaultdict(int)
        cce_used_this_slot = 0
        dl_prbs_used_this_slot = 0
        ul_prbs_used_this_slot = 0

        for alloc in all_allocs:
            if alloc.bytes_capacity <= 0:
                continue

            if engine is not None:
                if not alloc.is_retx:
                    # Mark bytes as in-flight.  Do NOT drain yet -- bytes stay
                    # in buffer until ACK so that delivered_cum stays accurate.
                    engine.mark_in_flight(
                        alloc.ue_id, alloc.qfi, alloc.bytes_capacity
                    )

                delivered, abandoned = engine.process_outcome(
                    alloc, slot_index, channel
                )

                if delivered > 0:
                    # ACK: drain bytes and record confirmed delivery.
                    buffers.drain(alloc.ue_id, alloc.qfi, delivered)
                    engine.unmark_in_flight(alloc.ue_id, alloc.qfi, delivered)
                    metrics.record_delivery(alloc.ue_id, alloc.qfi, delivered)
                    per_flow_delivered[(alloc.ue_id, alloc.qfi)] += delivered
                elif abandoned:
                    # MAX_RETX: bytes will never be delivered -- drain and lose.
                    buffers.drain(alloc.ue_id, alloc.qfi, alloc.bytes_capacity)
                    engine.unmark_in_flight(
                        alloc.ue_id, alloc.qfi, alloc.bytes_capacity
                    )
                    metrics.record_harq_loss(
                        alloc.ue_id, alloc.qfi, alloc.bytes_capacity
                    )
                elif not alloc.is_retx:
                    # First TX NACK: bytes stay in buffer (in-flight), will retx.
                    # Record that these bytes needed retransmission.
                    metrics.record_harq_retx(
                        alloc.ue_id, alloc.qfi, alloc.bytes_capacity
                    )
                # Retx NACK: bytes remain in-flight, already counted at first TX.

            else:
                # Legacy flat-BLER path (harq=False)
                symbols = (
                    slot_grid.dl_symbols
                    if alloc.direction == "DL"
                    else slot_grid.ul_symbols
                )
                _, bler = bits_per_prb(channel.get_snr_db(alloc.ue_id), symbols=symbols)
                delivered = int(alloc.bytes_capacity * (1.0 - bler))
                buffers.drain(alloc.ue_id, alloc.qfi, delivered)
                metrics.record_delivery(alloc.ue_id, alloc.qfi, delivered)
                per_flow_delivered[(alloc.ue_id, alloc.qfi)] += delivered

            metrics.record_prb_use(alloc.direction, alloc.prbs)
            cce_used_this_slot += alloc.cce_cost
            if alloc.direction == "DL":
                dl_prbs_used_this_slot += alloc.prbs
            else:
                ul_prbs_used_this_slot += alloc.prbs

        metrics.record_cce(cce_used_this_slot, slot_grid.pdcch_cce_budget)

        # --- PDB expiry (operates on real buffer) ---
        for ue_id, qfi in buffers.keys():
            pdb_s = pdb_by_flow.get((ue_id, qfi), 1.0)
            dropped = buffers.expire(now_s, pdb_s, ue_id, qfi)
            if dropped > 0:
                metrics.record_dropped(ue_id, qfi, dropped)
                per_flow_dropped[(ue_id, qfi)] = dropped
            metrics.record_hol_delay(
                ue_id, qfi, buffers.hol_delay_s(ue_id, qfi, now_s)
            )

        metrics.snapshot_slot(
            slot_index=slot_index,
            time_s=now_s,
            buffers=buffers,
            slot_grid=slot_grid,
            per_flow_delivered=per_flow_delivered,
            per_flow_arrived=per_flow_arrived,
            per_flow_dropped=per_flow_dropped,
            dl_prbs_used=dl_prbs_used_this_slot,
            ul_prbs_used=ul_prbs_used_this_slot,
            cce_used=cce_used_this_slot,
        )

    summary = metrics.summary(horizon_s)
    if record_timeseries:
        summary["timeseries"] = metrics.timeseries()
    return summary