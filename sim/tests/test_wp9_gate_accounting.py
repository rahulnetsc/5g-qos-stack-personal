"""wp9_gate's axis accounting -- every axis in exactly one list."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from wp9_gate import select_for_stage_2  # noqa: E402


class _V:
    """Minimal stand-in: select_for_stage_2 reads .axis, .qualifies, .score."""
    def __init__(self, axis, qualifies, score):
        self.axis, self.qualifies, self.score, self.best = axis, qualifies, score, None


def test_every_axis_is_promoted_or_dropped():
    """THE BUG THIS PINS. The dropped list was built from a SLICE of the
    unsorted excursions list, indexed by the COUNT of promoted axes -- so it
    discarded excursions[0] whether or not that was the promoted one. Both
    committed stage-1 verdicts lost `min_rb` to it, under a docstring
    reading "Nothing is silently omitted."

    The ordering below is the one that reproduces it: the qualifier is NOT
    first in the list. A test whose qualifier happened to sit at index 0
    would pass against the bug."""
    verdicts = [_V("min_rb", False, 0.0), _V("shared_lcg", True, 9.0),
                _V("bg", False, 0.0)]
    sel = select_for_stage_2(verdicts)
    accounted = set(sel["promoted"]) | {d["axis"] for d in sel["dropped"]}
    assert {v.axis for v in verdicts} <= accounted


def test_accounting_holds_when_the_qualifier_is_first():
    verdicts = [_V("shared_lcg", True, 9.0), _V("min_rb", False, 0.0)]
    sel = select_for_stage_2(verdicts)
    accounted = set(sel["promoted"]) | {d["axis"] for d in sel["dropped"]}
    assert {v.axis for v in verdicts} <= accounted


def test_core_axes_are_always_promoted_and_never_dropped():
    verdicts = [_V("n_ues", True, 1.0), _V("load_mult", True, 1.0),
                _V("min_rb", True, 5.0), _V("bg", True, 2.0)]
    sel = select_for_stage_2(verdicts)
    assert "n_ues" in sel["promoted"] and "load_mult" in sel["promoted"]
    assert "n_ues" not in {d["axis"] for d in sel["dropped"]}
    accounted = set(sel["promoted"]) | {d["axis"] for d in sel["dropped"]}
    assert {v.axis for v in verdicts} <= accounted


def test_a_qualifying_axis_that_is_not_promoted_says_why():
    verdicts = [_V("a", True, 9.0), _V("b", True, 8.0), _V("c", False, 0.0)]
    sel = select_for_stage_2(verdicts)
    reasons = {d["axis"]: d["reason"] for d in sel["dropped"]}
    assert "budget" in reasons["b"]
    assert "did not pass the gate" in reasons["c"]
