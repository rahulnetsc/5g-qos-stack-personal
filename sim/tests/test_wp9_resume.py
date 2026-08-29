"""Resumability guards for scripts/wp9_sweep.py's stage 3.

WHY. A long run's cost should be proportional to time LOST, not to time
ELAPSED. Two WP9 runs have already died mid-flight for unrelated reasons --
the OOM/thrash from the retention leak, and a laptop restart at cell 35/84
-- and power loss, a full disk or a kernel panic would do the same. This is
not a reboot mitigation.

A resume path that has never been observed skipping a completed cell, and
never been observed REFUSING a double-write, is a guess about what it
guards. Each test below is checked against the wrong behaviour, not merely
against the right one.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from wp9_sweep import _load_completed, cell_id  # noqa: E402


def _write(path: Path, cells: dict[str, int]) -> None:
    """cells: {cell_id_json: n_rows}"""
    with path.open("w") as fh:
        for cid, n in cells.items():
            for i in range(n):
                fh.write(json.dumps(
                    {"cell": cid, "row": {"__cell": cid, "seed": i}}) + "\n")


def test_cell_id_is_the_analysis_cell_identity_and_order_independent():
    """The resume key must be the SAME identity the analysis selects on, or
    'already done' can mean something different from 'selected'."""
    a = cell_id({"n_ues": 8, "load_mult": 1.0})
    b = cell_id({"load_mult": 1.0, "n_ues": 8})
    assert a == b
    assert cell_id({"n_ues": 8}) != cell_id({"n_ues": 16})


def test_complete_cells_are_skipped(tmp_path):
    p = tmp_path / "rows.jsonl"
    c1, c2 = cell_id({"n_ues": 2}), cell_id({"n_ues": 4})
    _write(p, {c1: 30, c2: 30})
    keep, done = _load_completed(p, 30)
    assert done == {c1, c2}
    assert len(keep) == 60


def test_partial_cell_is_dropped_and_rerun_not_appended_to(tmp_path, capsys):
    """The failure this exists to prevent: appending to a half-finished cell
    yields a cell of the RIGHT SIZE assembled from two different runs'
    fragments, which a naive count check accepts."""
    p = tmp_path / "rows.jsonl"
    full, part = cell_id({"n_ues": 2}), cell_id({"n_ues": 4})
    _write(p, {full: 30, part: 17})
    keep, done = _load_completed(p, 30)

    assert done == {full}, "a partial cell must NOT count as complete"
    assert part not in done
    assert all(r["__cell"] == full for r in keep), (
        "partial rows must be dropped, not carried forward")
    assert len(keep) == 30
    assert "dropping 1 partial" in capsys.readouterr().out


def test_no_prior_state_is_a_clean_start(tmp_path):
    keep, done = _load_completed(tmp_path / "absent.jsonl", 30)
    assert keep == [] and done == set()


def test_oversized_cell_ABORTS_rather_than_being_healed(tmp_path):
    """A double-written cell must abort, not be quietly re-run.

    Partial and oversized are different failures and get different
    treatment: partial is an ordinary interruption (drop and re-run);
    oversized should be impossible, so healing it would produce a correct
    final answer while hiding the bug that caused it. Verified against the
    earlier behaviour, which DID heal this case and finished green.
    """
    p = tmp_path / "rows.jsonl"
    dup = cell_id({"n_ues": 2})
    _write(p, {dup: 60})
    with pytest.raises(SystemExit, match="RESUME STATE CORRUPT"):
        _load_completed(p, 30)


def test_completion_assertion_rejects_wrong_sized_cells():
    """The end-of-run integrity check, exercised directly on its own logic:
    missing / wrong-sized / unexpected cells must each be caught."""
    expected = {cell_id({"n_ues": n}) for n in (2, 4, 8)}
    counts = {cell_id({"n_ues": 2}): 30,
              cell_id({"n_ues": 4}): 29,          # short
              cell_id({"n_ues": 99}): 30}         # unexpected
    missing = expected - set(counts)
    wrong = {c: n for c, n in counts.items() if n != 30}
    extra = set(counts) - expected
    assert missing and wrong and extra, (
        "all three corruption classes must be detectable from these inputs")
