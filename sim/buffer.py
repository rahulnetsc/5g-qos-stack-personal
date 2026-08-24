from collections import deque
from dataclasses import dataclass

from .messages import Message, MessageCompletion


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
    # WP5 (docs/wp5-plan.md sec1): bytes abandoned after HARQ max-retx
    # exhaustion -- a SECOND, distinct loss path from bytes_dropped_pdb
    # (PDB-clock-driven, via expire()). Removed via discard_harq_loss(),
    # not drain() (never delivered) or expire() (harq_round_max is an
    # attempt-count budget, independent of the PDB clock -- a TB can
    # exhaust its retries before its PDB has technically passed).
    bytes_dropped_harq: int = 0
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

    WP7 message identity (optional, additive): a chunk may carry a
    ``Message`` reference (``enqueue(..., message=...)``). When it does,
    ``drain()``/``expire()`` track that message's completion -- fully
    delivered, or dropped on PDB expiry -- as a side effect and queue a
    ``MessageCompletion`` for ``pop_completions()`` to collect. A chunk
    enqueued without a message (every call site before WP7, and any test
    that doesn't care) behaves exactly as before -- this tracking is purely
    additive and never changes what ``drain()``/``expire()`` return.
    """

    def __init__(self) -> None:
        self._buffers: dict[tuple[int, int], BufferState] = {}
        # Each chunk is [timestamp_s, bytes_remaining, message_or_None];
        # FIFO via deque.
        self._chunks: dict[tuple[int, int], deque] = {}
        # Monotone lifetime counters (bytes). Used by schedulers that need a
        # windowed view of offered/served load.
        self._arrived_cum: dict[tuple[int, int], int] = {}
        self._delivered_cum: dict[tuple[int, int], int] = {}
        # Flows whose bytes_reported is externally driven by BsrModel.
        self._bsr_managed: set[tuple[int, int]] = set()
        # Completed messages not yet collected via pop_completions().
        self._completed: dict[tuple[int, int], list[MessageCompletion]] = {}

    def register(self, ue_id: int, qfi: int, is_ul: bool = False, lcg: int = -1) -> None:
        key = (ue_id, qfi)
        self._buffers[key] = BufferState(lcg=lcg)
        self._chunks[key] = deque()
        self._arrived_cum[key] = 0
        self._delivered_cum[key] = 0
        self._completed[key] = []
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

    def enqueue(
        self,
        ue_id: int,
        qfi: int,
        bytes_count: int,
        timestamp_s: float,
        message: Message | None = None,
    ) -> None:
        if bytes_count <= 0:
            return
        key = (ue_id, qfi)
        state = self._buffers[key]
        chunks = self._chunks[key]
        if state.bytes_queued == 0:
            state.hol_timestamp_s = timestamp_s
        chunks.append([timestamp_s, bytes_count, message])
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
            chunk_late = (now_s - chunk[0]) > pdb_s
            if chunk_late:
                late += take
            chunk[1] -= take
            removed += take
            remaining -= take
            if chunk[2] is not None:
                chunk[2].delivered_bytes += take
            if chunk[1] == 0:
                if chunk[2] is not None:
                    self._completed[key].append(MessageCompletion(
                        message=chunk[2],
                        complete=True,
                        late=chunk_late,
                        completion_ts_s=now_s,
                        delivered_bytes=chunk[2].delivered_bytes,
                        dropped_bytes=0,
                    ))
                chunks.popleft()
        state.bytes_queued -= removed
        state.bytes_delivered_late_pdb += late
        state.hol_timestamp_s = chunks[0][0] if chunks else 0.0
        self._delivered_cum[key] += removed
        if key not in self._bsr_managed:
            state.bytes_reported = state.bytes_queued
        return removed

    def discard_harq_loss(
        self,
        ue_id: int,
        qfi: int,
        bytes_count: int,
        now_s: float = 0.0,
        pdb_s: float = float("inf"),
    ) -> int:
        """Remove up to bytes_count bytes from the head, counted as HARQ
        max-retx loss -- NOT a delivery (unlike drain(), which always
        credits delivered_cum/bytes_reported as successful) and NOT a
        PDB-clock discard (unlike expire(), which only fires once a
        chunk's age exceeds the flow's PDB). WP5 (docs/wp5-plan.md sec1):
        a HARQ process can exhaust harq_round_max independent of whether
        the flow's PDB has technically passed yet -- this is the path
        that removes those bytes. Tags the MessageCompletion the same way
        expire() does (complete=False), since from the message's own
        perspective this IS a drop, just for a different top-level reason
        than PDB expiry -- config/metric_panel.yml's M02 does not yet
        fold bytes_dropped_harq into its own count; see docs/wp5-plan.md
        commit 4a for that gap.

        WP5 end-of-WP review fix: `late` is computed per chunk exactly
        like `drain()` does (`(now_s - chunk[0]) > pdb_s`), not hardcoded
        `True` -- harq_round_max exhaustion is an attempt-count budget,
        independent of the PDB clock, so an abandoned TB is not
        necessarily late in PDB terms yet. `pdb_s` defaults to infinity
        (never late) for a caller that doesn't have or care about it,
        matching `drain()`'s own optional-`pdb_s` convention."""
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
            chunk_late = (now_s - chunk[0]) > pdb_s
            chunk[1] -= take
            removed += take
            remaining -= take
            if chunk[1] == 0:
                if chunk[2] is not None:
                    self._completed[key].append(MessageCompletion(
                        message=chunk[2],
                        complete=False,
                        late=chunk_late,
                        completion_ts_s=now_s,
                        delivered_bytes=chunk[2].delivered_bytes,
                        dropped_bytes=take,
                    ))
                chunks.popleft()
        state.bytes_queued -= removed
        state.bytes_dropped_harq += removed
        state.hol_timestamp_s = chunks[0][0] if chunks else 0.0
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
            chunk = chunks[0]
            dropped += chunk[1]
            if chunk[2] is not None:
                self._completed[key].append(MessageCompletion(
                    message=chunk[2],
                    complete=False,
                    late=True,
                    completion_ts_s=now_s,
                    delivered_bytes=chunk[2].delivered_bytes,
                    dropped_bytes=chunk[1],
                ))
            chunks.popleft()
        state.bytes_dropped_pdb += dropped
        state.bytes_queued -= dropped
        state.hol_timestamp_s = chunks[0][0] if chunks else 0.0
        if key not in self._bsr_managed:
            state.bytes_reported = state.bytes_queued
        return dropped

    def pop_completions(self, ue_id: int, qfi: int) -> list[MessageCompletion]:
        """Return and clear this flow's ``MessageCompletion``s recorded by
        ``drain()``/``expire()`` since the last call. Empty for any chunk
        enqueued without a ``message=`` -- see the class docstring."""
        key = (ue_id, qfi)
        out = self._completed[key]
        self._completed[key] = []
        return out

    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float:
        state = self._buffers[(ue_id, qfi)]
        if state.bytes_queued == 0:
            return 0.0
        return now_s - state.hol_timestamp_s
