"""WP5 commit 2: scheduler/interfaces.py::Allocation gains harq_pid/is_retx,
both optional and defaulted -- dormant until sim/driver.py wires HARQ in
(docs/wp5-plan.md commit 3+). No existing scheduler constructs these
fields, so every existing call site is unaffected by their addition."""

from scheduler.interfaces import Allocation


def test_harq_fields_default_to_not_harq_tracked():
    alloc = Allocation(ue_id=1, qfi=2, direction="DL", prbs=4, bytes_capacity=1000)
    assert alloc.harq_pid == -1
    assert alloc.is_retx is False


def test_existing_keyword_construction_is_unaffected_by_the_new_fields():
    """Mirrors the construction style every current scheduler actually
    uses (scheduler/two_tier.py, sim/baselines/_mac.py) -- all-keyword,
    omitting harq_pid/is_retx entirely."""
    alloc = Allocation(
        ue_id=1, qfi=-1, direction="UL", prbs=8, bytes_capacity=2000,
        cce_cost=1, is_sps=True, snr_used_db=12.5, ue_grant=True,
    )
    assert alloc.harq_pid == -1
    assert alloc.is_retx is False


def test_harq_fields_can_be_set_explicitly():
    alloc = Allocation(
        ue_id=1, qfi=2, direction="DL", prbs=4, bytes_capacity=1000,
        harq_pid=3, is_retx=True,
    )
    assert alloc.harq_pid == 3
    assert alloc.is_retx is True
