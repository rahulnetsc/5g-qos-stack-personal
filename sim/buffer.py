from collections import deque
from dataclasses import dataclass


@dataclass
class BufferState:
    bytes_queued: int = 0            # real backlog (drain / fill work off this)
    bytes_reported: int = 0          # BSR-visible view (see BufferModel.snapshot_bsr)
    hol_timestamp_s: float = 0.0
    bytes_dropped_pdb: int = 0


class BufferModel:
    """Per-(UE, QFI) fluid byte buffer. Tracks chunk timestamps for HoL
    accounting.

    Uplink Buffer Status Report (BSR) delay is modelled cheaply. In real
    5G the gNB does not directly see a UE's UL buffer -- it learns the
    size via a delayed (and quantised, and sometimes lost) BSR MAC CE that
    piggybacks on a UL grant that itself was triggered by a Scheduling
    Request on PUCCH. The round-trip is ~4-8 ms for an idle UE. We model
    this as a fixed per-UL-flow delay in slots: ``bytes_reported`` lags
    ``bytes_queued`` by ``ul_bsr_delay_slots``. Dynamic schedulers read
    ``bytes_reported`` (that is what BSR would tell them); SPS / Configured
    Grants read ``bytes_queued`` directly because a CG UE just fills its
    reserved PRBs with whatever it has -- no BSR needed. Downlink flows
    (gNB-side buffer) always have ``bytes_reported == bytes_queued``.

    ``ul_bsr_delay_slots = 0`` disables the pipeline entirely (bytes_reported
    is kept in lock-step with bytes_queued), preserving the previous
    zero-latency behaviour.
    """

    def __init__(self, ul_bsr_delay_slots: int = 0) -> None:
        self._buffers: dict[tuple[int, int], BufferState] = {}
        # Each chunk is [timestamp_s, bytes_remaining]; FIFO via deque.
        self._chunks: dict[tuple[int, int], deque] = {}
        # Monotone lifetime counters (bytes). Used by schedulers that need a
        # windowed view of offered/served load.
        self._arrived_cum: dict[tuple[int, int], int] = {}
        self._delivered_cum: dict[tuple[int, int], int] = {}
        # UL BSR-delay pipeline.
        self._ul_bsr_delay = max(0, int(ul_bsr_delay_slots))
        self._ul_flows: set[tuple[int, int]] = set()
        self._bsr_history: dict[tuple[int, int], deque] = {}

    def register(self, ue_id: int, qfi: int, is_ul: bool = False) -> None:
        key = (ue_id, qfi)
        self._buffers[key] = BufferState()
        self._chunks[key] = deque()
        self._arrived_cum[key] = 0
        self._delivered_cum[key] = 0
        if is_ul and self._ul_bsr_delay > 0:
            self._ul_flows.add(key)
            # maxlen = delay + 1 so hist[0] is the value from `delay` slots ago
            # once the pipeline has filled.
            self._bsr_history[key] = deque(maxlen=self._ul_bsr_delay + 1)

    def arrived_cum(self, ue_id: int, qfi: int) -> int:
        """Cumulative bytes ever enqueued for this flow."""
        return self._arrived_cum[(ue_id, qfi)]

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
        # DL / no-BSR-delay flows: report is exact and instant.
        if key not in self._ul_flows:
            state.bytes_reported = state.bytes_queued

    def drain(self, ue_id: int, qfi: int, bytes_count: int) -> int:
        """Remove up to bytes_count bytes from the head. Returns bytes actually removed."""
        if bytes_count <= 0:
            return 0
        key = (ue_id, qfi)
        state = self._buffers[key]
        chunks = self._chunks[key]
        remaining = bytes_count
        removed = 0
        while remaining > 0 and chunks:
            chunk = chunks[0]
            take = min(remaining, chunk[1])
            chunk[1] -= take
            removed += take
            remaining -= take
            if chunk[1] == 0:
                chunks.popleft()
        state.bytes_queued -= removed
        state.hol_timestamp_s = chunks[0][0] if chunks else 0.0
        self._delivered_cum[key] += removed
        if key not in self._ul_flows:
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
        if key not in self._ul_flows:
            state.bytes_reported = state.bytes_queued
        return dropped

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        state = self._buffers[(ue_id, qfi)]
        if state.bytes_queued == 0:
            return 0.0
        return now_s - state.hol_timestamp_s

    def snapshot_bsr(self) -> None:
        """Advance the UL BSR-delay pipeline by one slot. Call once per
        slot AFTER traffic arrivals are enqueued and drained/expired, but
        BEFORE the scheduler reads state -- so ``bytes_reported`` reflects
        the buffer as seen ``ul_bsr_delay_slots`` ago. No-op if no UL flow
        has a delay configured (bytes_reported is already tracked in
        enqueue/drain/expire for the zero-delay case)."""
        if not self._ul_flows:
            return
        for key in self._ul_flows:
            st = self._buffers[key]
            hist = self._bsr_history[key]
            hist.append(st.bytes_queued)
            # Once the pipeline has filled (len > delay), hist[0] is the value
            # from `delay` slots ago. Before that, nothing has been reported
            # yet -- the scheduler sees an empty buffer, matching the real
            # cold-start behaviour (no BSR has yet reached the gNB).
            if len(hist) > self._ul_bsr_delay:
                st.bytes_reported = hist[0]
