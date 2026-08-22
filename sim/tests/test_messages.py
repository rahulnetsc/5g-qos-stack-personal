"""WP7 commit 1: message-ledger plumbing is additive and provably inert
unless a caller opts in (passes ``message=`` / a ``MessageLedger``).

These tests exercise ``sim.buffer.BufferModel``'s completion tracking and
``sim.traffic.TrafficModel``'s optional message tagging directly -- the
scenario/driver-level "does this move any existing number" question is
answered by the full suite + ``scripts/regression_corpus.py --check``,
not by a unit test.
"""

import numpy as np
import pytest

from sim.buffer import BufferModel
from sim.config import FlowConfig
from sim.messages import Message, MessageLedger
from sim.traffic import TrafficModel


def _msg(ledger: MessageLedger, ue_id: int, qfi: int, size_bytes: int, ts: float) -> Message:
    return Message(
        id=ledger.new_id(), ue_id=ue_id, qfi=qfi, size_bytes=size_bytes, generation_ts_s=ts
    )


def test_enqueue_without_message_records_no_completions():
    b = BufferModel()
    b.register(1, 9)
    b.enqueue(1, 9, 500, 0.0)  # no message= -- pre-WP7 call shape
    b.drain(1, 9, 500, now_s=0.1, pdb_s=1.0)
    assert b.pop_completions(1, 9) == []


def test_full_drain_in_one_call_records_on_time_completion():
    b = BufferModel()
    b.register(1, 9)
    ledger = MessageLedger()
    msg = _msg(ledger, 1, 9, 500, 0.0)
    b.enqueue(1, 9, 500, 0.0, message=msg)
    b.drain(1, 9, 500, now_s=0.1, pdb_s=1.0)
    completions = b.pop_completions(1, 9)
    assert len(completions) == 1
    c = completions[0]
    assert c.message is msg
    assert c.complete is True
    assert c.late is False
    assert c.delivered_bytes == 500
    assert c.dropped_bytes == 0
    assert c.completion_ts_s == 0.1


def test_drain_spanning_multiple_calls_completes_once_on_the_final_call():
    b = BufferModel()
    b.register(1, 9)
    ledger = MessageLedger()
    msg = _msg(ledger, 1, 9, 1000, 0.0)
    b.enqueue(1, 9, 1000, 0.0, message=msg)
    b.drain(1, 9, 400, now_s=0.05, pdb_s=1.0)
    assert b.pop_completions(1, 9) == []  # not yet fully drained
    b.drain(1, 9, 600, now_s=0.1, pdb_s=1.0)
    completions = b.pop_completions(1, 9)
    assert len(completions) == 1
    assert completions[0].delivered_bytes == 1000  # accumulated across both calls


def test_late_drain_marks_completion_late_but_still_complete():
    b = BufferModel()
    b.register(1, 9)
    ledger = MessageLedger()
    msg = _msg(ledger, 1, 9, 300, 0.0)
    b.enqueue(1, 9, 300, 0.0, message=msg)
    b.drain(1, 9, 300, now_s=1.0, pdb_s=0.5)  # age at drain = 1.0 > pdb 0.5
    c = b.pop_completions(1, 9)[0]
    assert c.complete is True
    assert c.late is True


def test_expire_records_a_failed_completion_with_zero_delivered():
    b = BufferModel()
    b.register(1, 9)
    ledger = MessageLedger()
    msg = _msg(ledger, 1, 9, 200, 0.0)
    b.enqueue(1, 9, 200, 0.0, message=msg)
    dropped = b.expire(now_s=1.0, pdb_s=0.5, ue_id=1, qfi=9)
    assert dropped == 200
    c = b.pop_completions(1, 9)[0]
    assert c.complete is False
    assert c.late is True
    assert c.delivered_bytes == 0
    assert c.dropped_bytes == 200


def test_partial_drain_then_expire_records_the_partial_delivery():
    """A message partly drained, then the remainder expires -- the PDU-set
    'partial delivery counts as failed' case (README §6 / M05)."""
    b = BufferModel()
    b.register(1, 9)
    ledger = MessageLedger()
    msg = _msg(ledger, 1, 9, 1000, 0.0)
    b.enqueue(1, 9, 1000, 0.0, message=msg)
    b.drain(1, 9, 300, now_s=0.1, pdb_s=0.5)
    assert b.pop_completions(1, 9) == []
    dropped = b.expire(now_s=1.0, pdb_s=0.5, ue_id=1, qfi=9)
    assert dropped == 700
    c = b.pop_completions(1, 9)[0]
    assert c.complete is False
    assert c.delivered_bytes == 300
    assert c.dropped_bytes == 700


def test_pop_completions_clears_the_list():
    b = BufferModel()
    b.register(1, 9)
    ledger = MessageLedger()
    msg = _msg(ledger, 1, 9, 100, 0.0)
    b.enqueue(1, 9, 100, 0.0, message=msg)
    b.drain(1, 9, 100, now_s=0.1, pdb_s=1.0)
    assert len(b.pop_completions(1, 9)) == 1
    assert b.pop_completions(1, 9) == []


def test_ledger_issues_unique_ascending_ids():
    ledger = MessageLedger()
    ids = [ledger.new_id() for _ in range(5)]
    assert ids == sorted(set(ids))
    assert len(set(ids)) == 5


def test_traffic_model_without_ledger_enqueues_untagged_chunks():
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="deterministic",
                       traffic_params={"period_ms": 10.0, "bytes_per_period": 100})
    buffers = BufferModel()
    rng = np.random.default_rng(0)
    traffic = TrafficModel([flow], buffers, slot_duration_s=0.0005, rng=rng)
    traffic.generate(0)
    buffers.drain(1, 9, 100, now_s=0.0005, pdb_s=1.0)
    assert buffers.pop_completions(1, 9) == []


def test_traffic_model_with_ledger_tags_each_arrival_with_a_message():
    flow = FlowConfig(ue_id=1, qfi=9, direction="UL", traffic_kind="deterministic",
                       traffic_params={"period_ms": 10.0, "bytes_per_period": 100})
    buffers = BufferModel()
    rng = np.random.default_rng(0)
    ledger = MessageLedger()
    traffic = TrafficModel([flow], buffers, slot_duration_s=0.0005, rng=rng, ledger=ledger)
    traffic.generate(0)
    buffers.drain(1, 9, 100, now_s=0.0005, pdb_s=1.0)
    for c in buffers.pop_completions(1, 9):
        ledger.record(c)
    completions = ledger.completions_for(1, 9)
    assert len(completions) == 1
    assert completions[0].message.size_bytes == 100
    assert completions[0].message.generation_ts_s == 0.0
