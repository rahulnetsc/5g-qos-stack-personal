"""The pre-launch orphan check.

WHY THE PROCESS IS REAL AND NOT MOCKED. The thing under test is whether a
detector finds processes that every name-based search misses, and a mock
would be built from the same assumption the detector is. So the test SPAWNS
a genuine orphan -- a pool whose parent exits without terminating it -- and
then asserts both halves: that the detector sees it, and that `pgrep -f`
does not.

Measured while writing this, and it changed the implementation: the orphans
reparented to `systemd --user` (PPID 2261), NOT to PID 1. A `ppid == 1` test
would have missed all three, so the check tests the PARENT'S IDENTITY rather
than its pid.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from regime_sweep import (OrphanedPoolError, check_for_orphans,  # noqa: E402
                          find_orphaned_pool_processes,
                          find_pool_processes, run_cells)

_ORPHAN_SRC = textwrap.dedent('''
    import multiprocessing as mp, time, os
    def w(x):
        time.sleep(600)
        return x
    if __name__ == "__main__":
        pool = mp.get_context("spawn").Pool(2)
        pool.map_async(w, [1, 2])
        time.sleep(3)
        os._exit(0)          # parent dies WITHOUT terminating the pool
''')


@pytest.fixture
def orphans(tmp_path):
    if not Path("/proc").is_dir():
        pytest.skip("orphan detection reads /proc")
    before = {p.pid for p in find_pool_processes()}
    script = tmp_path / "mk_orphan_fixture.py"
    script.write_text(_ORPHAN_SRC)
    # DEVNULL, NOT capture_output. The parent exits with os._exit(0) but the
    # orphaned children inherit the pipe's write end, so subprocess.run waits
    # for EOF that never arrives while they live -- the first version of this
    # fixture hung for the full 60 s timeout on every test. An orphan holding
    # its parent's pipe open is the same family as the buffered-stdout trap
    # CLAUDE.md records: the observation channel blocks on the thing being
    # observed.
    subprocess.run([sys.executable, str(script)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=60)
    for _ in range(40):
        made = [p for p in find_orphaned_pool_processes() if p.pid not in before]
        if made:
            break
        time.sleep(0.25)
    yield made
    # Kill by PID. This fixture cannot use pkill -f for the reason it exists
    # to demonstrate, and a test that leaked orphans would poison every later
    # test in the session -- which the first version did.
    for p in made:
        try:
            os.kill(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for _ in range(20):
        if not [q for q in find_orphaned_pool_processes()
                if q.pid in {p.pid for p in made}]:
            break
        time.sleep(0.1)


def test_an_orphan_is_found(orphans):
    assert orphans, "no orphan was created; the fixture cannot test anything"
    assert any(p.kind == "spawn" for p in orphans)


def test_the_orphan_is_invisible_to_a_name_search(orphans):
    """THE POINT OF THE WHOLE MECHANISM. A spawn worker's argv is the
    bootstrap, so a search for the script that launched it returns nothing --
    which is why a cleanup or liveness check that greps by name reports clean
    while the workers are alive."""
    assert orphans
    found = subprocess.run(["pgrep", "-f", "mk_orphan_fixture"],
                           capture_output=True, text=True).stdout.split()
    orphan_pids = {str(p.pid) for p in orphans}
    assert not (orphan_pids & set(found)), (
        f"pgrep -f found an orphan ({orphan_pids & set(found)}); the premise "
        f"of this check is that it cannot")


def test_check_refuses_and_names_the_pids(orphans):
    assert orphans
    with pytest.raises(OrphanedPoolError) as exc:
        check_for_orphans()
    msg = str(exc.value)
    for p in orphans:
        assert str(p.pid) in msg, f"pid {p.pid} not named in the refusal"
    assert "kill " in msg, "the refusal must give the kill command"


def test_run_cells_refuses_to_launch(orphans):
    assert orphans
    with pytest.raises(OrphanedPoolError):
        list(run_cells(_square, [1, 2, 3], 2))


def test_allow_downgrades_to_a_warning(orphans, capsys):
    """The guard cannot judge whether an orphan belongs to another user's
    job, so the override exists -- but it must still say what it saw."""
    assert orphans
    got = check_for_orphans(allow=True)
    assert got
    assert "WARNING" in capsys.readouterr().out


def test_clean_machine_returns_empty_and_allows_launch():
    """The other half: with no orphans the check is silent and a pool runs.
    Without this the suite could pass by never being able to launch."""
    if find_orphaned_pool_processes():
        pytest.skip("this machine already has orphans; cannot test the clean path")
    assert check_for_orphans() == []
    out = [None] * 3
    for i, r in run_cells(_square, [1, 2, 3], 2):
        out[i] = r
    assert out == [1, 4, 9]


def _square(t):
    return t * t
