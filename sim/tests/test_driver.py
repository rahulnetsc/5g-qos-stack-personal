"""Unit tests for HARQEngine (sim/driver.py).

Tests the engine in isolation -- no traffic, no buffer, no full simulation loop.
Full end-to-end smoke test is in test_smoke.py (Step 6).

Run from the project root:
    pytest sim/tests/test_driver.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pytest
from scheduler.interfaces import Allocation
from sim.driver import HARQEngine, _ReducedSlotView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine(seed=42, max_retx=3, combining_mode="ir", harq_rtt=8, ewma_alpha=0.1):
    rng = np.random.default_rng(seed)
    engine = HARQEngine(rng, max_retx=max_retx, combining_mode=combining_mode,
                        harq_rtt=harq_rtt, ewma_alpha=ewma_alpha)
    engine._snr_ewma = {1: 20.0, 2: 15.0}
    return engine


def make_alloc(ue_id=1, qfi=5, direction="DL", bytes_capacity=1000,
               is_retx=False, harq_pid=-1):
    return Allocation(
        ue_id=ue_id, qfi=qfi, direction=direction,
        prbs=10, bytes_capacity=bytes_capacity,
        is_retx=is_retx, harq_pid=harq_pid,
        harq_ue_direction=direction if harq_pid >= 0 else "",
    )


class _AlwaysACK:
    """RNG stub: random() always returns 1.0 → success regardless of BLER."""
    def random(self): return 1.0


class _AlwaysNACK:
    """RNG stub: random() always returns 0.0 → failure regardless of BLER."""
    def random(self): return 0.0


class _FakeChannel:
    def __init__(self, snr_db=20.0):
        self._snr = snr_db
    def get_snr_db(self, ue_id): return self._snr


class _FakeSlotGrid:
    slot_index = 0
    dl_symbols = 14
    ul_symbols = 0
    prb_count = 106
    pdcch_cce_budget = 48


def _engine_with_rng(rng_stub, max_retx=3, harq_rtt=8):
    """Build an engine with a stubbed RNG for deterministic outcome control."""
    engine = HARQEngine.__new__(HARQEngine)
    from collections import defaultdict
    engine._rng = rng_stub
    engine._max_retx = max_retx
    engine._combining_mode = "ir"
    engine._harq_rtt = harq_rtt
    engine._ewma_alpha = 0.1
    engine._snr_ewma = {1: 20.0}
    engine._pending = {}
    engine._next_pid = defaultdict(int)
    return engine


# ---------------------------------------------------------------------------
# PID assignment
# ---------------------------------------------------------------------------

class TestPIDAssignment:

    def test_pid_assigned_to_new_alloc(self):
        engine = _engine_with_rng(_AlwaysACK())
        alloc = make_alloc()
        engine.process_outcome(alloc, 0, _FakeChannel())
        assert alloc.harq_pid == 0

    def test_pid_rotates_0_to_15(self):
        engine = _engine_with_rng(_AlwaysACK())
        pids = []
        for _ in range(17):
            alloc = make_alloc()
            engine.process_outcome(alloc, 0, _FakeChannel())
            pids.append(alloc.harq_pid)
        assert pids[:16] == list(range(16))
        assert pids[16] == 0      # wraps back to 0

    def test_dl_ul_pid_counters_independent(self):
        engine = _engine_with_rng(_AlwaysACK())
        dl = make_alloc(direction="DL")
        ul = make_alloc(direction="UL")
        engine.process_outcome(dl, 0, _FakeChannel())
        engine.process_outcome(ul, 0, _FakeChannel())
        assert dl.harq_pid == 0
        assert ul.harq_pid == 0   # separate counter


# ---------------------------------------------------------------------------
# ACK path
# ---------------------------------------------------------------------------

class TestACKPath:

    def test_always_ack_returns_full_bytes(self):
        engine = _engine_with_rng(_AlwaysACK())
        for _ in range(20):
            alloc = make_alloc(bytes_capacity=1000)
            delivered, abandoned = engine.process_outcome(alloc, 0, _FakeChannel())
            assert delivered == 1000
            assert not abandoned

    def test_ack_on_retx_clears_pending(self):
        # NACK first TX
        engine = _engine_with_rng(_AlwaysNACK())
        alloc = make_alloc()
        engine.process_outcome(alloc, slot_index=0, channel=_FakeChannel())
        pid = alloc.harq_pid
        key = (1, "DL", pid)
        assert key in engine._pending

        # ACK on retx
        engine._rng = _AlwaysACK()
        retx = make_alloc(is_retx=True, harq_pid=pid, bytes_capacity=1000)
        delivered, abandoned = engine.process_outcome(retx, slot_index=8,
                                                       channel=_FakeChannel())
        assert delivered == 1000
        assert not abandoned
        assert key not in engine._pending

    def test_ack_direction_field_preserved(self):
        engine = _engine_with_rng(_AlwaysACK())
        alloc = make_alloc(direction="UL")
        engine.process_outcome(alloc, 0, _FakeChannel())
        assert alloc.harq_ue_direction == "UL"


# ---------------------------------------------------------------------------
# NACK path
# ---------------------------------------------------------------------------

class TestNACKPath:

    def test_nack_returns_zero_not_abandoned(self):
        engine = _engine_with_rng(_AlwaysNACK())
        alloc = make_alloc()
        delivered, abandoned = engine.process_outcome(alloc, 0, _FakeChannel())
        assert delivered == 0
        assert not abandoned

    def test_nack_registers_pending_at_rtt(self):
        engine = _engine_with_rng(_AlwaysNACK(), harq_rtt=8)
        alloc = make_alloc()
        engine.process_outcome(alloc, slot_index=0, channel=_FakeChannel())
        pid = alloc.harq_pid
        entry = engine._pending[(1, "DL", pid)]
        assert entry.due_slot == 8
        assert entry.retx_count == 1
        assert entry.tb_bytes == alloc.bytes_capacity

    def test_retx_nack_increments_count_and_requeues(self):
        engine = _engine_with_rng(_AlwaysNACK(), harq_rtt=8)
        alloc = make_alloc()
        engine.process_outcome(alloc, 0, _FakeChannel())
        pid = alloc.harq_pid
        key = (1, "DL", pid)

        retx = make_alloc(is_retx=True, harq_pid=pid)
        engine.process_outcome(retx, slot_index=8, channel=_FakeChannel())

        entry = engine._pending[key]
        assert entry.retx_count == 2
        assert entry.due_slot == 16    # 8 + harq_rtt=8

    def test_max_retx_abandons_and_clears(self):
        engine = _engine_with_rng(_AlwaysNACK(), max_retx=3, harq_rtt=8)
        alloc = make_alloc()
        engine.process_outcome(alloc, 0, _FakeChannel())
        pid = alloc.harq_pid
        key = (1, "DL", pid)

        abandoned = False
        for i in range(1, 10):
            retx = make_alloc(is_retx=True, harq_pid=pid)
            d, ab = engine.process_outcome(retx, 8 * i, _FakeChannel())
            if ab:
                abandoned = True
                break

        assert abandoned
        assert key not in engine._pending

    def test_max_retx_fires_at_correct_count(self):
        """With max_retx=2 the process should be abandoned on the 2nd retx."""
        engine = _engine_with_rng(_AlwaysNACK(), max_retx=2, harq_rtt=8)
        alloc = make_alloc()
        engine.process_outcome(alloc, 0, _FakeChannel())
        pid = alloc.harq_pid

        outcomes = []
        for i in range(1, 5):
            retx = make_alloc(is_retx=True, harq_pid=pid)
            d, ab = engine.process_outcome(retx, 8 * i, _FakeChannel())
            outcomes.append((d, ab))

        # retx 1 → NACK, not abandoned
        assert outcomes[0] == (0, False)
        # retx 2 → abandoned (max_retx=2 reached)
        assert outcomes[1] == (0, True)
        # retx 3, 4 → stale (entry already cleared) → abandoned
        assert all(ab for _, ab in outcomes[2:])


# ---------------------------------------------------------------------------
# get_retx_allocs
# ---------------------------------------------------------------------------

class TestGetRetxAllocs:

    def test_no_pending_no_retx(self):
        engine = _engine_with_rng(_AlwaysACK())
        allocs = engine.get_retx_allocs(0, _FakeSlotGrid(), _FakeChannel())
        assert allocs == []

    def test_due_pending_returns_alloc(self):
        engine = _engine_with_rng(_AlwaysNACK(), harq_rtt=8)
        alloc = make_alloc()
        engine.process_outcome(alloc, slot_index=0, channel=_FakeChannel())

        retx_allocs = engine.get_retx_allocs(
            slot_index=8, slot_grid=_FakeSlotGrid(), channel=_FakeChannel(30.0)
        )
        assert len(retx_allocs) == 1
        assert retx_allocs[0].is_retx
        assert retx_allocs[0].harq_pid == alloc.harq_pid
        assert retx_allocs[0].bytes_capacity == alloc.bytes_capacity

    def test_not_yet_due_not_returned(self):
        engine = _engine_with_rng(_AlwaysNACK(), harq_rtt=8)
        alloc = make_alloc()
        engine.process_outcome(alloc, slot_index=0, channel=_FakeChannel())

        retx_allocs = engine.get_retx_allocs(
            slot_index=5, slot_grid=_FakeSlotGrid(), channel=_FakeChannel()
        )
        assert retx_allocs == []

    def test_wrong_direction_deferred(self):
        """A DL retx should be deferred if the slot has no DL symbols."""
        engine = _engine_with_rng(_AlwaysNACK(), harq_rtt=8)
        alloc = make_alloc(direction="DL")
        engine.process_outcome(alloc, slot_index=0, channel=_FakeChannel())
        pid = alloc.harq_pid

        class ULSlot(_FakeSlotGrid):
            dl_symbols = 0
            ul_symbols = 14

        retx_allocs = engine.get_retx_allocs(
            slot_index=8, slot_grid=ULSlot(), channel=_FakeChannel()
        )
        assert retx_allocs == []
        # Entry should have been deferred by 1 slot
        assert engine._pending[(1, "DL", pid)].due_slot == 9


# ---------------------------------------------------------------------------
# _ReducedSlotView
# ---------------------------------------------------------------------------

class TestReducedSlotView:

    def test_prb_count_reduced(self):
        assert _ReducedSlotView(_FakeSlotGrid(), 10).prb_count == 96

    def test_floored_at_zero(self):
        assert _ReducedSlotView(_FakeSlotGrid(), 200).prb_count == 0

    def test_zero_retx_unchanged(self):
        assert _ReducedSlotView(_FakeSlotGrid(), 0).prb_count == 106

    def test_other_fields_pass_through(self):
        rv = _ReducedSlotView(_FakeSlotGrid(), 10)
        assert rv.slot_index == 0
        assert rv.dl_symbols == 14
        assert rv.pdcch_cce_budget == 48


# ---------------------------------------------------------------------------
# EWMA
# ---------------------------------------------------------------------------

class TestEWMA:

    def test_converges_to_constant_snr(self):
        engine = make_engine(ewma_alpha=0.2)
        engine._snr_ewma = {1: 5.0}

        class ConstCh:
            def get_snr_db(self, uid): return 20.0

        for _ in range(100):
            engine.update_ewma(ConstCh())
        assert engine._snr_ewma[1] > 18.0

    def test_configure_seeds_from_mean(self):
        rng = np.random.default_rng(0)
        engine = HARQEngine(rng)

        class _UE:
            ue_id = 7
            mean_snr_db = 13.5

        engine.configure([_UE()])
        assert engine._snr_ewma[7] == pytest.approx(13.5)


if __name__ == "__main__":
    try:
        import pytest as pt, sys
        sys.exit(pt.main([__file__, "-v"]))
    except ImportError:
        print("run: pytest sim/tests/test_driver.py -v")
