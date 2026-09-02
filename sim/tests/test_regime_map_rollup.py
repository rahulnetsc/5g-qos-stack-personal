"""The §2.1 roll-up must agree with the rows it claims to be derived from.

CLAUDE.md's restated-count rule, guarded. This is the fifth instance of
that rule in the project and the only one that asserted its own immunity:
the sentence read "Counts derived from the rows above, not carried
separately" while carrying "3 unrun-but-buildable (G9, G11, G12)" against
rows that said G9 and G12 were run.

The rule's own fourth-instance lesson applies to this file: a test that
RESTATES the expected counts would fail in the direction of passing, so
this test restates nothing -- it re-derives from the document and compares.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import regime_map_rollup as R


def test_rollup_sentence_matches_the_rows_it_is_derived_from():
    assert R.main.__module__  # import smoke
    argv = sys.argv
    try:
        sys.argv = ["regime_map_rollup.py", "--check"]
        assert R.main() == 0, (
            "docs/wp9-regime-map.md §2.1's roll-up disagrees with its own rows -- "
            "run `uv run python scripts/regime_map_rollup.py` and paste the sentence"
        )
    finally:
        sys.argv = argv


def test_every_guarantee_row_buckets_exactly_once():
    rows = R.parse_rows(R.MAP_PATH.read_text())
    by, _ = R.rollup(rows)
    assert sum(len(v) for v in by.values()) == len(rows)
    ids = [g for v in by.values() for g in v]
    assert len(ids) == len(set(ids)), "a guarantee was bucketed twice"


def test_an_unrecognised_status_is_a_hard_error_not_a_silent_drop():
    """The failure mode this whole file exists to prevent: a status nobody
    anticipated quietly vanishing from the count."""
    import pytest
    with pytest.raises(SystemExit):
        R.bucket("some status nobody anticipated")
