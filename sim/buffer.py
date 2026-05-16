from collections import deque
from dataclasses import dataclass


@dataclass
class BufferState:
    bytes_queued: int = 0
    hol_timestamp_s: float = 0.0
    bytes_dropped_pdb: int = 0


class BufferModel:
    """Per-(UE, QFI) fluid byte buffer. Tracks chunk timestamps for HoL accounting."""

    def __init__(self) -> None:
        self._buffers: dict[tuple[int, int], BufferState] = {}
        # Each chunk is [timestamp_s, bytes_remaining]; FIFO via deque.
        self._chunks: dict[tuple[int, int], deque] = {}
        # Monotone lifetime counters (bytes). Used by schedulers that need a
        # windowed view of offered/served load.
        self._arrived_cum: dict[tuple[int, int], int] = {}
        self._delivered_cum: dict[tuple[int, int], int] = {}

    def register(self, ue_id: int, qfi: int) -> None:
        key = (ue_id, qfi)
        self._buffers[key] = BufferState()
        self._chunks[key] = deque()
        self._arrived_cum[key] = 0
        self._delivered_cum[key] = 0

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
        return dropped

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        state = self._buffers[(ue_id, qfi)]
        if state.bytes_queued == 0:
            return 0.0
        return now_s - state.hol_timestamp_s
