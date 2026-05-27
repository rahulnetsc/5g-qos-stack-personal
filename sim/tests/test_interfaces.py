"""Unit tests for scheduler/interfaces.py -- Allocation HARQ fields.

Run from the project root:
    pytest sim/tests/test_interfaces.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.interfaces import Allocation


class TestAllocationBackwardCompat:
    """Existing construction sites must work unchanged."""

    def test_minimal_construction(self):
        """Original positional fields still work without HARQ fields."""
        a = Allocation(
            ue_id=1, qfi=5, direction="DL",
            prbs=10, bytes_capacity=1000,
        )
        assert a.ue_id == 1
        assert a.bytes_capacity == 1000

    def test_defaults_are_safe(self):
        """New HARQ fields default to sentinel / no-op values."""
        a = Allocation(ue_id=0, qfi=0, direction="DL", prbs=0, bytes_capacity=0)
        assert a.harq_pid == -1
        assert a.is_retx is False
        assert a.harq_ue_direction == ""

    def test_existing_optional_fields_unchanged(self):
        a = Allocation(
            ue_id=2, qfi=1, direction="UL",
            prbs=5, bytes_capacity=500,
            cce_cost=2, is_sps=True,
        )
        assert a.cce_cost == 2
        assert a.is_sps is True


class TestAllocationHARQFields:
    """HARQEngine sets these; schedulers read harq_pid only."""

    def test_new_transmission_fields(self):
        """Scheduler emits a new-tx Allocation with a harq_pid assigned."""
        a = Allocation(
            ue_id=3, qfi=9, direction="DL",
            prbs=20, bytes_capacity=2000,
            harq_pid=4,
            harq_ue_direction="DL",
        )
        assert a.harq_pid == 4
        assert a.is_retx is False          # schedulers never set True
        assert a.harq_ue_direction == "DL"

    def test_retx_allocation_fields(self):
        """HARQEngine constructs retx Allocations with is_retx=True."""
        a = Allocation(
            ue_id=3, qfi=9, direction="DL",
            prbs=20, bytes_capacity=2000,
            harq_pid=4,
            is_retx=True,
            harq_ue_direction="DL",
        )
        assert a.is_retx is True
        assert a.harq_pid == 4

    def test_pending_key_reconstructable(self):
        """The pending-state key (ue_id, harq_ue_direction, harq_pid)
        must be reconstructable from the Allocation alone."""
        a = Allocation(
            ue_id=7, qfi=2, direction="UL",
            prbs=8, bytes_capacity=800,
            harq_pid=11,
            is_retx=True,
            harq_ue_direction="UL",
        )
        key = (a.ue_id, a.harq_ue_direction, a.harq_pid)
        assert key == (7, "UL", 11)

    def test_pid_range(self):
        """harq_pid must accept all valid 5G NR process IDs (0-15)."""
        for pid in range(16):
            a = Allocation(
                ue_id=0, qfi=0, direction="DL",
                prbs=1, bytes_capacity=100,
                harq_pid=pid,
            )
            assert a.harq_pid == pid

    def test_sentinel_pid_not_retx(self):
        """harq_pid=-1 (not tracked) must never be a retx."""
        a = Allocation(
            ue_id=0, qfi=0, direction="DL",
            prbs=0, bytes_capacity=0,
        )
        assert a.harq_pid == -1
        assert a.is_retx is False


if __name__ == "__main__":
    try:
        import pytest, sys
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        print("run: pytest sim/tests/test_interfaces.py -v")
