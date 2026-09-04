"""g12_score decomposes by (cell, arm) at every aggregation site.

WHY A SYNTHETIC TWO-CELL FIXTURE IS THE RIGHT SHAPE HERE, and why it is not
the fixture-built-precondition failure CLAUDE.md records. That failure is
constructing the precondition you are testing FOR and then being unable to
ask whether it ever occurs. Here the precondition -- a campaign with two
scoreable cells -- is the thing whose HANDLING is under test, and it is
known not to have occurred yet: Phase 2 completed one cell and running the
rest is an open thread on G12's row. So the fixture is the only way to test
the code path before the run that exercises it, and the run that exercises
it is the one whose output would otherwise be wrong.

THE DEFECT THESE PIN. `docs/wp9-defects-log.md` #20.5: the file's own review
found the pooling shape (§36.6 -- "first degradation at x1.0", true of
TwoTier only) and fixed ONE of five aggregation sites. E3, E4, E5 and the
promotion bar all still pooled across cells, and E4 pooled arms as well.
Measured on the real single-cell campaign, E4's pooled median was 2.563 Mbps
-- EXACTLY TwoTier's value, with PF at 12.480 and Reservation at 0.345, a
36x spread. The pooled figure landed on one arm and read as the grid's,
which is the original defect's signature reproduced.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import g12_score  # noqa: E402


def _seed(bg_bps, first_fail_idx, order, m02_by_point):
    return {
        "seed": 1,
        "full": {"order": order, "first_fail_at_index": {2: first_fail_idx}},
        "in_range": {"order": order},
        "per_point": [
            {"mult": 1.0 + i, "bg_bps": bg_bps,
             "telemetry_m02": m02, "telemetry_max_gap_ms": 10.0,
             "worst_by_class": {2: 0.99, 4: 0.99}}
            for i, m02 in enumerate(m02_by_point)
        ],
    }


def _campaign() -> dict:
    """Two cells whose arms disagree, chosen so any pooled statistic differs
    from every per-group one."""
    return {
        "ramp": [1.0, 2.0, 3.0],
        "in_range": [1.0, 2.0],
        "excluded_cells": [],
        "control_pass": {"cell_a": {"n_groups": 2, "contaminated": []},
                         "cell_b": {"n_groups": 2, "contaminated": []}},
        "cells": {
            "cell_a": {
                "PF": {"in_range_orders": [[4, 2]], "full_orders": [[4, 2]],
                       "per_seed": [_seed(100e6, 0, [4, 2], [0.0, 0.0, 0.5])]},
                "TwoTier": {"in_range_orders": [[4, 2]], "full_orders": [[4, 2]],
                            "per_seed": [_seed(1e6, 0, [4, 2], [0.4, 0.5, 0.6])]},
            },
            "cell_b": {
                "PF": {"in_range_orders": [[2, 4]], "full_orders": [[2, 4]],
                       "per_seed": [_seed(50e6, 0, [2, 4], [0.0, 0.0, 0.0])]},
                "TwoTier": {"in_range_orders": [[2, 4]], "full_orders": [[2, 4]],
                            "per_seed": [_seed(2e6, 0, [2, 4], [0.0, 0.0, 0.0])]},
            },
        },
    }


def _row(rows, eid):
    return next(r for r in rows if r[0] == eid)


def test_e4_reports_every_cell_and_arm_separately():
    """The pooled median landed on one arm's value on the real campaign.
    Every group must appear by name."""
    rows = g12_score.score_expectations(_campaign(), {"present": False})
    _, _, detail = _row(rows, "E4")
    for group in ("cell_a/PF", "cell_a/TwoTier", "cell_b/PF", "cell_b/TwoTier"):
        assert group in detail, f"E4 does not name {group}: {detail}"


def test_e4_misses_if_any_single_group_is_at_zero():
    """A pooled median can sit above zero while one group is at it. The
    verdict must be the conjunction over groups, not a statement about the
    middle of the pool."""
    camp = _campaign()
    camp["cells"]["cell_b"]["TwoTier"]["per_seed"] = [
        _seed(0.0, 0, [2, 4], [0.0, 0.0, 0.0])]
    rows = g12_score.score_expectations(camp, {"present": False})
    verdict, detail = _row(rows, "E4")[1], _row(rows, "E4")[2]
    assert verdict == "MISS", f"one group at zero bg must not pass: {detail}"


def test_e3_names_the_cell_as_well_as_the_arm():
    rows = g12_score.score_expectations(_campaign(), {"present": False})
    _, _, detail = _row(rows, "E3")
    assert "cell_a/TwoTier" in detail and "cell_b/PF" in detail, detail


def test_e5_compares_arms_WITHIN_a_cell():
    """Naming check: the detail must attribute orders to a cell."""
    rows = g12_score.score_expectations(_campaign(), {"present": False})
    _, _, detail = _row(rows, "E5")
    assert "cell_a" in detail and "cell_b" in detail, detail


def test_e5_verdict_INVERTS_when_cells_are_pooled():
    """THE DISCRIMINATING CASE, and the reason it needs its own fixture.

    The naming check above fails against the pooled implementation, but it
    fails on FORMATTING -- a pooled version that merely printed cell names
    would satisfy it. This one separates the verdicts.

    Both cells have their arms DISAGREEING, but in opposite directions:
    cell_a is PF [4,2] / TwoTier [2,4], cell_b is PF [2,4] / TwoTier [4,2].
    Per cell the answer is MISS twice. Pooled across cells, each arm's SET
    becomes {(4,2),(2,4)} -- identical -- and the verdict flips to HIT, i.e.
    "the arms agree", which is true of neither cell. A pooled statistic here
    does not merely blur the answer; it returns the opposite one.
    """
    camp = _campaign()
    camp["cells"]["cell_a"]["PF"]["full_orders"] = [[4, 2]]
    camp["cells"]["cell_a"]["TwoTier"]["full_orders"] = [[2, 4]]
    camp["cells"]["cell_b"]["PF"]["full_orders"] = [[2, 4]]
    camp["cells"]["cell_b"]["TwoTier"]["full_orders"] = [[4, 2]]
    rows = g12_score.score_expectations(camp, {"present": False})
    verdict, detail = _row(rows, "E5")[1], _row(rows, "E5")[2]
    assert verdict == "MISS", (
        "the arms differ in BOTH cells, so E5 is a MISS. A HIT here means "
        f"the cells were pooled before the arms were compared: {detail}")


def test_promotion_bar_reports_per_cell(capsys):
    """The bar's output decides whether an arm difference is promoted to a
    scheduler finding. A grid-wide boolean over pooled cells is the last
    place a mixture should be quoted as one statement."""
    camp = _campaign()
    # Make the arms differ in cell_a only.
    camp["cells"]["cell_a"]["TwoTier"]["full_orders"] = [[2, 4]]
    g12_score.apply_promotion_bar(camp, {"present": False})
    out = capsys.readouterr().out
    assert "cell_a: arms differ under the CANONICAL order: True" in out
    assert "cell_b: arms differ under the CANONICAL order: False" in out
    assert "THE CELLS DISAGREE" in out, (
        "when cells disagree the bar must say so, or 'arms differ' reads as "
        "a grid-wide property")
