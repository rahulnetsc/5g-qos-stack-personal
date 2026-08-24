"""WP5 commit 1: sim/harq.py core state, dormant -- not wired into
driver.py yet (docs/wp5-plan.md). Predicted, before writing this file:
scripts/regression_corpus.py --check stays fully clean, since nothing here
is imported by driver.py or any scenario/scheduler."""

import pytest

from sim.harq import (
    DEFAULT_DL_CAPACITY,
    DEFAULT_UL_CAPACITY,
    HarqProcess,
    HarqProcessPool,
    combining_gain_db,
)


# -- combining_gain_db -------------------------------------------------


def test_ir_gain_matches_the_ported_table_exactly():
    assert combining_gain_db(0, mode="ir") == 0.0
    assert combining_gain_db(1, mode="ir") == 4.0
    assert combining_gain_db(2, mode="ir") == 6.5
    assert combining_gain_db(3, mode="ir") == 8.0


def test_ir_gain_saturates_beyond_retx_3():
    """docs/wp5-plan.md Decision 1: every attempt past the third gets the
    identical, uncalibrated bonus -- ported as-is, not derived."""
    assert combining_gain_db(4, mode="ir") == 8.0
    assert combining_gain_db(10, mode="ir") == 8.0


def test_chase_gain_is_linear_and_uncapped():
    assert combining_gain_db(0, mode="chase") == 0.0
    assert combining_gain_db(1, mode="chase") == 3.0
    assert combining_gain_db(2, mode="chase") == 6.0
    assert combining_gain_db(5, mode="chase") == 15.0


def test_ir_is_the_default_mode():
    assert combining_gain_db(2) == combining_gain_db(2, mode="ir")


# -- HarqProcess ---------------------------------------------------------


def test_harq_process_defaults():
    proc = HarqProcess(pid=0, ue_id=1, direction="DL")
    assert proc.busy is False
    assert proc.qfi == -1
    assert proc.tb_bytes == 0
    assert proc.retx_count == 0
    assert proc.due_slot == -1


def test_harq_process_reset_clears_all_mutable_fields():
    proc = HarqProcess(
        pid=0, ue_id=1, direction="UL", busy=True, qfi=5, tb_bytes=1000,
        retx_count=2, due_slot=42,
    )
    proc.reset()
    assert proc.busy is False
    assert proc.qfi == -1
    assert proc.tb_bytes == 0
    assert proc.retx_count == 0
    assert proc.due_slot == -1


# -- HarqProcessPool ------------------------------------------------------


def test_pool_defaults_are_asymmetric_by_direction():
    """docs/wp5-plan.md Decision 2: real OAI fallback defaults, not one
    shared spec-ceiling value."""
    assert DEFAULT_DL_CAPACITY == 8
    assert DEFAULT_UL_CAPACITY == 16
    pool = HarqProcessPool()
    assert pool.dl_capacity == 8
    assert pool.ul_capacity == 16


def test_allocate_fills_pids_sequentially_then_exhausts():
    pool = HarqProcessPool(dl_capacity=2, ul_capacity=16)
    p0 = pool.allocate(ue_id=1, direction="DL", tb_bytes=500, due_slot=10)
    p1 = pool.allocate(ue_id=1, direction="DL", tb_bytes=500, due_slot=10)
    assert (p0.pid, p1.pid) == (0, 1)
    assert pool.exhausted(ue_id=1, direction="DL") is True
    assert pool.allocate(ue_id=1, direction="DL", tb_bytes=500, due_slot=10) is None


def test_free_makes_a_pid_reusable():
    pool = HarqProcessPool(dl_capacity=1, ul_capacity=16)
    p0 = pool.allocate(ue_id=1, direction="DL", tb_bytes=500, due_slot=10)
    assert pool.allocate(ue_id=1, direction="DL", tb_bytes=500, due_slot=10) is None
    pool.free(ue_id=1, direction="DL", pid=p0.pid)
    p1 = pool.allocate(ue_id=1, direction="DL", tb_bytes=200, due_slot=20)
    assert p1.pid == p0.pid
    assert p1.tb_bytes == 200


def test_different_ue_and_direction_keys_do_not_share_capacity():
    pool = HarqProcessPool(dl_capacity=1, ul_capacity=1)
    a = pool.allocate(ue_id=1, direction="DL", tb_bytes=100, due_slot=1)
    b = pool.allocate(ue_id=2, direction="DL", tb_bytes=100, due_slot=1)
    c = pool.allocate(ue_id=1, direction="UL", tb_bytes=100, due_slot=1)
    assert a is not None and b is not None and c is not None
    assert pool.exhausted(ue_id=1, direction="DL") is True
    assert pool.exhausted(ue_id=1, direction="UL") is True
    assert pool.exhausted(ue_id=2, direction="DL") is True
    # UE 2's UL pool was never touched -- still fully free.
    assert pool.exhausted(ue_id=2, direction="UL") is False


def test_in_flight_bytes_sums_only_busy_processes_for_the_queried_key():
    pool = HarqProcessPool(dl_capacity=4, ul_capacity=16)
    pool.allocate(ue_id=1, direction="DL", tb_bytes=300, due_slot=1)
    p1 = pool.allocate(ue_id=1, direction="DL", tb_bytes=700, due_slot=1)
    pool.allocate(ue_id=1, direction="UL", tb_bytes=9999, due_slot=1)
    assert pool.in_flight_bytes(ue_id=1, direction="DL") == 1000
    pool.free(ue_id=1, direction="DL", pid=p1.pid)
    assert pool.in_flight_bytes(ue_id=1, direction="DL") == 300
    # UL allocation must not leak into the DL sum.
    assert pool.in_flight_bytes(ue_id=2, direction="DL") == 0


def test_get_raises_for_an_unknown_pid():
    pool = HarqProcessPool(dl_capacity=2, ul_capacity=2)
    with pytest.raises(KeyError):
        pool.get(ue_id=1, direction="DL", pid=99)


def test_free_raises_for_an_unknown_pid():
    pool = HarqProcessPool(dl_capacity=2, ul_capacity=2)
    with pytest.raises(KeyError):
        pool.free(ue_id=1, direction="DL", pid=99)
