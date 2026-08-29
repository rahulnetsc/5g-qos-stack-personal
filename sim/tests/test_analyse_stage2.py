"""Fixtures with known answers for scripts/analyse_stage2.py.

**Written before the stage-2 results were seen.** That timing is the point:
contiguity logic that has never been observed rejecting an isolated winner
is a guess about what it guards, and a fixture written after seeing the real
output is written by someone who already knows the answer they want. These
were built while blind to stage 2's output, on a grid whose correct verdict
is arithmetic rather than judgement.

Same standard as the guard tests elsewhere in this WP: each case is checked
to fail against the wrong behaviour, not merely to pass against the right
one.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import analyse_stage2 as A  # noqa: E402
from regime_sweep import check_contiguity  # noqa: E402

ARMS = ("PF", "Reservation", "TwoTier")


def _cell(winner, metric="M07.met", n_seeds=10, loss=0.2):
    """One cell's rows, with `winner` given the best value on `metric`."""
    rows = []
    for arm in ARMS:
        # M07 is higher_better, so the winner gets the larger value.
        val = 8.0 if arm == winner else 4.0
        for seed in range(n_seeds):
            rows.append({"scheduler": arm, "seed": seed,
                         metric: val, "M02": loss})
    return rows


def test_direction_is_derived_from_the_panel_not_transcribed():
    """The count-from-structure rule applied to signs: a hand-copied
    direction on M01.p98 or M02 inverts a winner and nothing downstream
    catches it."""
    import yaml

    panel = yaml.safe_load(
        open(Path(__file__).resolve().parent.parent.parent
             / "config" / "metric_panel.yml"))
    by_id = {m["id"]: m.get("direction") for m in panel["metrics"]}
    for col, sign in A.DIRECTION.items():
        expected = by_id[col.split(".")[0]]
        assert expected in ("higher_better", "lower_better")
        assert sign == (+1 if expected == "higher_better" else -1), col


def test_winner_respects_a_lower_better_metric():
    """Sign errors are the failure this guards: on M02 (lower_better) the
    arm with the SMALLEST value wins."""
    rows = []
    for arm, val in (("PF", 0.5), ("Reservation", 0.1), ("TwoTier", 0.9)):
        for seed in range(10):
            rows.append({"scheduler": arm, "seed": seed, "M02": val})
    assert A.cell_winner(rows, "M02") == "Reservation"


def test_uninformative_cell_has_no_winner_and_cannot_support_a_neighbour():
    """Rule 2(i): a zero-loss cell carries no information, so it must not
    vote in a contiguity claim."""
    assert A.cell_winner(_cell("PF", loss=0.0), "M07.met") is None


# -- the three cases the contiguity guard exists for ----------------------


def test_case1_clean_contiguous_boundary_is_reported_as_a_boundary():
    """One arm winning across grid-adjacent cells: every such cell has an
    agreeing neighbour, so none is isolated."""
    axes = {"n_ues": [2, 4, 8, 16], "load_mult": [1.0, 2.0]}
    winners = {}
    for n in axes["n_ues"]:
        for lm in axes["load_mult"]:
            winners[(n, lm)] = "PF" if n <= 4 else "TwoTier"
    isolated = check_contiguity(winners, axes)
    assert not any(isolated.values()), (
        "a clean two-region boundary must have no isolated cells")


def test_case2_isolated_winner_is_flagged_and_is_not_a_boundary():
    """One cell disagreeing with every neighbour is noise, not a regime.
    This is the case that matters at 252 cells, where isolated winners
    arise by chance."""
    axes = {"n_ues": [2, 4, 8, 16], "load_mult": [1.0, 2.0]}
    winners = {(n, lm): "PF" for n in axes["n_ues"] for lm in axes["load_mult"]}
    winners[(8, 1.0)] = "TwoTier"          # the lone dissenter
    isolated = check_contiguity(winners, axes)

    assert isolated[(8, 1.0)] is True, "the lone dissenter must be isolated"
    assert sum(1 for v in isolated.values() if v) == 1, (
        "only the dissenter is isolated; its neighbours still agree with "
        "each other")


def test_case2b_a_pair_of_agreeing_cells_is_not_isolated():
    """The discriminating counterpart to case 2: two ADJACENT dissenting
    cells support each other and are not isolated. Without this, a test
    could pass by flagging everything."""
    axes = {"n_ues": [2, 4, 8, 16], "load_mult": [1.0, 2.0]}
    winners = {(n, lm): "PF" for n in axes["n_ues"] for lm in axes["load_mult"]}
    winners[(8, 1.0)] = "TwoTier"
    winners[(8, 2.0)] = "TwoTier"          # adjacent along load_mult
    isolated = check_contiguity(winners, axes)
    assert isolated[(8, 1.0)] is False
    assert isolated[(8, 2.0)] is False


def test_case3_missing_cell_refuses_to_score(monkeypatch, tmp_path, capsys):
    """An incomplete grid must exit non-zero, not score what it has."""
    grid = {"n_ues": [2, 4], "load_mult": [1.0, 2.0]}
    monkeypatch.setattr(A, "STAGE2_GRID", grid)
    rows = []
    for n in grid["n_ues"]:
        for lm in grid["load_mult"]:
            if (n, lm) == (4, 2.0):
                continue                   # the hole
            for r in _cell("PF"):
                rows.append({**r, "n_ues": n, "load_mult": lm})
    missing, bad = A.check_cell_sizes(rows)
    assert missing == 1 and bad == 0


def test_case3b_wrong_sized_cell_refuses_to_score(monkeypatch):
    """A cell with the wrong row count is the empty-selection failure's
    near neighbour -- the one that produced a plausible-looking 0.000
    earlier in this WP. It must be caught before scoring, not after."""
    grid = {"n_ues": [2, 4], "load_mult": [1.0, 2.0]}
    monkeypatch.setattr(A, "STAGE2_GRID", grid)
    rows = []
    for n in grid["n_ues"]:
        for lm in grid["load_mult"]:
            n_seeds = 3 if (n, lm) == (2, 1.0) else 10    # short cell
            for r in _cell("PF", n_seeds=n_seeds):
                rows.append({**r, "n_ues": n, "load_mult": lm})
    missing, bad = A.check_cell_sizes(rows)
    assert missing == 0 and bad == 1


def test_case3c_main_exits_nonzero_on_an_incomplete_grid(monkeypatch, tmp_path):
    """End-to-end: the refusal is wired into main(), not just available as
    a helper somebody might forget to call."""
    import csv as _csv

    grid = {"n_ues": [2, 4], "load_mult": [1.0, 2.0]}
    monkeypatch.setattr(A, "STAGE2_GRID", grid)
    path = tmp_path / "stage2_rows.csv"
    fields = ["n_ues", "load_mult", "scheduler", "seed", "M07.met", "M02",
              "M08.fraction", "M01.p98", "M09.worst"]
    with path.open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for n in grid["n_ues"]:                      # omit (4, 2.0) entirely
            for lm in grid["load_mult"]:
                if (n, lm) == (4, 2.0):
                    continue
                for arm in ARMS:
                    for seed in range(10):
                        w.writerow({"n_ues": n, "load_mult": lm,
                                    "scheduler": arm, "seed": seed,
                                    "M07.met": 8.0, "M02": 0.2,
                                    "M08.fraction": 0.9, "M01.p98": 10.0,
                                    "M09.worst": 0.9})
    monkeypatch.setattr(sys, "argv", ["analyse_stage2.py", str(tmp_path)])
    with pytest.raises(SystemExit):
        A.main()
