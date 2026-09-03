"""The aggregate memory guard must see workers it did not parent.

WP9 G11. The guard was added because a PER-PROCESS threshold cannot fire
against machine-level exhaustion. The first version then filtered on
`PPid: <me>` -- the same scope defect one level out: workers ORPHANED by a
previous attempt are reparented to init and are invisible to a
children-only scan while still consuming the machine's memory.

Measured on 2026-09-03: two orphans from a killed 2-worker attempt held
13.5 GB and starved the live soak to 5.9 GB free, with the guard reporting
the pool healthy throughout.

THE TEST HAS TO DISTINGUISH NEW FROM OLD, or it is not a guard. It does
that by making the guard's own pid wrong: under the old PPid filter a
foreign pid returns NOTHING, under the cmdline scan it still finds every
spawn worker on the machine and marks them foreign.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from g11_campaign import AggregateMemoryGuard


def _sleep(seconds):          # module-level: spawn needs it picklable
    time.sleep(seconds)


@pytest.fixture()
def one_spawn_worker():
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=_sleep, args=(8,))
    p.start()
    for _ in range(100):                      # wait for it to be visible
        if Path(f"/proc/{p.pid}/cmdline").exists():
            break
        time.sleep(0.05)
    time.sleep(0.5)
    yield p
    p.terminate()
    p.join(timeout=5)


def test_it_finds_a_spawn_worker_at_all(tmp_path, one_spawn_worker):
    g = AggregateMemoryGuard(budget_mb=10**9, log=tmp_path / "m.log")
    pids = {pid for pid, _, _ in g._workers()}
    assert one_spawn_worker.pid in pids, (
        "the guard cannot see a live multiprocessing spawn worker at all")


def test_it_still_sees_workers_it_did_NOT_parent(tmp_path, one_spawn_worker,
                                                 monkeypatch):
    """The orphan case, and the discriminator against the old version.

    With a foreign pid, a PPid-filtered scan returns nothing. The cmdline
    scan must still find the worker and mark it NOT ours.
    """
    import os as _os
    monkeypatch.setattr(_os, "getpid", lambda: 999_999_999)
    g = AggregateMemoryGuard(budget_mb=10**9, log=tmp_path / "m.log")
    found = {pid: ours for pid, _, ours in g._workers()}
    assert one_spawn_worker.pid in found, (
        "an orphaned spawn worker is invisible to the guard -- this is the "
        "13.5 GB failure of 2026-09-03 reproduced")
    assert found[one_spawn_worker.pid] is False, (
        "a worker we did not parent must be reported as foreign, so the "
        "guard counts it toward the machine total but never kills it")


def test_foreign_workers_count_toward_the_total_but_are_never_killed(
        tmp_path, one_spawn_worker, monkeypatch):
    import os as _os
    killed: list[int] = []
    monkeypatch.setattr(_os, "getpid", lambda: 999_999_999)
    monkeypatch.setattr(_os, "kill", lambda pid, sig: killed.append(pid))
    log = tmp_path / "m.log"
    g = AggregateMemoryGuard(budget_mb=0, log=log, poll_s=0.05,
                             min_avail_mb=0)
    g.start()
    time.sleep(0.4)
    g.stop_flag.set()
    g.join(timeout=5)
    text = log.read_text()
    assert "foreign" in text, "the log must separate ours from foreign"
    assert one_spawn_worker.pid not in killed, (
        "the guard killed a process it did not start -- that is another "
        "job's work, and not this guard's decision to make")


def test_a_starved_machine_trips_even_when_our_pool_is_small(tmp_path,
                                                             monkeypatch):
    """The second trip condition. The first version compared only the pool's
    own total against a fixed budget and LOGGED MemAvailable without acting
    on it, so memory consumed by anything else was invisible to the
    decision."""
    import os as _os
    killed: list[int] = []
    monkeypatch.setattr(_os, "kill", lambda pid, sig: killed.append(pid))
    log = tmp_path / "m.log"
    # budget enormous (never over budget), avail floor enormous (always starved)
    g = AggregateMemoryGuard(budget_mb=10**9, log=log, poll_s=0.05,
                             min_avail_mb=10**9)
    g._workers = lambda: [(424242, 10, True)]        # one small worker, ours
    g.start()
    time.sleep(0.3)
    g.stop_flag.set()
    g.join(timeout=5)
    assert g.tripped, "a starved machine did not trip the guard"
    assert 424242 in killed
    assert "MemAvailable" in log.read_text()


def test_the_guard_records_its_victims_for_the_failure_path(tmp_path, monkeypatch):
    """A killed worker must be attributable afterwards -- the campaign's
    failure rows name guard.victims."""
    import os as _os
    monkeypatch.setattr(_os, "kill", lambda pid, sig: None)
    g = AggregateMemoryGuard(budget_mb=0, log=tmp_path / "m.log", poll_s=0.05,
                             min_avail_mb=0)
    g._workers = lambda: [(777, 5000, True)]
    g.start()
    time.sleep(0.3)
    g.stop_flag.set()
    g.join(timeout=5)
    assert g.victims and g.victims[0] == 777
