from collections import deque
from dataclasses import dataclass


@dataclass
class BufferState:
    bytes_queued: int = 0            # real backlog (drain / fill work off this)
    bytes_reported: int = 0          # BSR-visible view -- see sim/bsr.py
    hol_timestamp_s: float = 0.0
    bytes_dropped_pdb: int = 0
    # Bytes drained after their PDB had already passed -- delivered, but too
    # late to matter (config/metric_panel.yml M02's "delivered, but later
    # than PDB" component). Distinct from bytes_dropped_pdb, which never
    # reaches drain() at all -- expire() removes those first.
    bytes_delivered_late_pdb: int = 0
    lcg: int = -1                    # this flow's logical channel group (-1 = DL / n/a)
    estimated_ul_buffer_per_lcg: int = 0  # gNB's raw per-LCG estimate, uncapped by
                                           # sched_ul_bytes (bytes_reported is capped)


class BufferModel:
    """Per-(UE, QFI) fluid byte buffer. Tracks chunk timestamps for HoL
    accounting.

    Uplink Buffer Status Report (BSR) realism -- quantisation, per-LCG
    aggregation, short-BSR aliasing, and the sched_ul_bytes collapse-to-
    crumb gate -- lives in ``sim/bsr.py::BsrModel``, not here. This class
    is purely the true-backlog store: ``bytes_queued`` is exact and
    instant. For a BSR-managed UL flow (registered with ``is_ul=True``),
    ``bytes_reported`` is written only by ``BsrModel.broadcast()`` -- this
    class does not touch it. For DL flows and any flow not BSR-managed,
    ``bytes_reported`` stays in lock-step with ``bytes_queued`` here, same
    as before (no BSR needed: the gNB IS the DL buffer).
    """

    def __init__(self) -> None:
        self._buffers: dict[tuple[int, int], BufferState] = {}
        # Each chunk is [timestamp_s, bytes_remaining]; FIFO via deque.
        self._chunks: dict[tuple[int, int], deque] = {}
        # Monotone lifetime counters (bytes). Used by schedulers that need a
        # windowed view of offered/served load.
        self._arrived_cum: dict[tuple[int, int], int] = {}
        self._delivered_cum: dict[tuple[int, int], int] = {}
        # Flows whose bytes_reported is externally driven by BsrModel.
        self._bsr_managed: set[tuple[int, int]] = set()

    def register(self, ue_id: int, qfi: int, is_ul: bool = False, lcg: int = -1) -> None:
        key = (ue_id, qfi)
        self._buffers[key] = BufferState(lcg=lcg)
        self._chunks[key] = deque()
        self._arrived_cum[key] = 0
        self._delivered_cum[key] = 0
        if is_ul:
            self._bsr_managed.add(key)

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        """Cumulative bytes ever enqueued for this flow."""
        return self._arrived_cum[(ue_id, qfi)]

    def dropped_cum(self, ue_id: int, qfi: int) -> int:
        """Cumulative bytes discarded on PDB expiry for this flow."""
        return self.state(ue_id, qfi).bytes_dropped_pdb

    def delivered_cum(self, ue_id: int, qfi: int) -> int:
        """Cumulative bytes ever drained (delivered) for this flow.

        Excludes PDB-expired bytes — those leave via expire(), not drain().
        """
        return self._delivered_cum[(ue_id, qfi)]

    def keys(self) -> list[tuple[int, int]]:
        return list(self._buffers.keys())

    def state(self, ue_id: int, qfi: int) -> BufferState:
        return self._buffers[(ue_id, qfi)]

    def enqueue(self, ue_id: int, qfi: int, bytes_count: int, timestamp_s: float) -> None:
        if bytes_count <= 0:
            return
        key = (ue_id, qfi)
        state = self._buffers[key]
        chunks = self._chunks[key]
        if state.bytes_queued == 0:
            state.hol_timestamp_s = timestamp_s
        chunks.append([timestamp_s, bytes_count])
        state.bytes_queued += bytes_count
        self._arrived_cum[key] += bytes_count
        # DL / non-BSR-managed flows: report is exact and instant.
        if key not in self._bsr_managed:
            state.bytes_reported = state.bytes_queued

    def drain(
        self,
        ue_id: int,
        qfi: int,
        bytes_count: int,
        now_s: float = 0.0,
        pdb_s: float = float("inf"),
    ) -> int:
        """Remove up to bytes_count bytes from the head. Returns bytes actually removed.

        ``now_s``/``pdb_s`` are optional: a caller that doesn't care whether
        delivery was late can omit them (nothing is ever "late" against an
        infinite PDB). When given, each removed chunk's age at removal is
        checked against the flow's PDB -- bytes from a chunk already older
        than ``pdb_s`` count toward ``bytes_delivered_late_pdb`` (M02's
        "delivered, but later than PDB" component). A drain spanning
        several chunks can straddle the deadline: some of the removed
        bytes late, some not.
        """
        if bytes_count <= 0:
            return 0
        key = (ue_id, qfi)
        state = self._buffers[key]
        chunks = self._chunks[key]
        remaining = bytes_count
        removed = 0
        late = 0
        while remaining > 0 and chunks:
            chunk = chunks[0]
            take = min(remaining, chunk[1])
            if (now_s - chunk[0]) > pdb_s:
                late += take
            chunk[1] -= take
            removed += take
            remaining -= take
            if chunk[1] == 0:
                chunks.popleft()
        state.bytes_queued -= removed
        state.bytes_delivered_late_pdb += late
        state.hol_timestamp_s = chunks[0][0] if chunks else 0.0
        self._delivered_cum[key] += removed
        if key not in self._bsr_managed:
            state.bytes_reported = state.bytes_queued
        return removed

    def expire(self, now_s: float, pdb_s: float, ue_id: int, qfi: int) -> int:
        """Drop bytes whose age exceeds the per-flow PDB. Returns bytes dropped."""
        key = (ue_id, qfi)
        state = self._buffers[key]
        chunks = self._chunks[key]
        dropped = 0
        while chunks and (now_s - chunks[0][0]) > pdb_s:
            dropped += chunks[0][1]
            chunks.popleft()
        state.bytes_dropped_pdb += dropped
        state.bytes_queued -= dropped
        state.hol_timestamp_s = chunks[0][0] if chunks else 0.0
        if key not in self._bsr_managed:
            state.bytes_reported = state.bytes_queued
        return dropped

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        state = self._buffers[(ue_id, qfi)]
        if state.bytes_queued == 0:
            return 0.0
        return now_s - state.hol_timestamp_s
