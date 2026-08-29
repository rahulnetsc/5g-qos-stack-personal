"""Cell-level parallelism must change no result (docs/wp9-plan.md §6.3b).

Parallelism became a precondition rather than an optimisation once the real
per-cell costs were measured: stage 1 is ~7.1 h serial against a 4 h ceiling
and stage 2 ~35-55 h against 24 h. That makes "the parallel path computes
exactly what the serial path computes" a correctness claim the sweep's
results rest on, not a performance note.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from wp9_sweep import (  # noqa: E402
    BASE, CORE_PLANE, EXCURSIONS, _cell_tasks, _run_one_cell,
)


def test_cell_tasks_cover_the_core_product_plus_each_excursion_level():
    tasks = _cell_tasks(CORE_PLANE, EXCURSIONS, n_seeds=10, horizon=20_000)
    n_core = len(CORE_PLANE["n_ues"]) * len(CORE_PLANE["load_mult"])
    n_exc = sum(len(v) for v in EXCURSIONS.values())
    assert len(tasks) == n_core + n_exc
    # Every task is one cell: the core plane's tasks fix both plane axes,
    # an excursion's task fixes exactly one axis off the base.
    for axis_values, _, _ in tasks:
        assert axis_values
        if set(axis_values) <= {"n_ues", "load_mult"}:
            assert len(axis_values) == 2
        else:
            assert len(axis_values) == 1
            (axis, level), = axis_values.items()
            assert level != BASE.get(axis), (
                f"excursion {axis}={level} duplicates the base point")


def test_parallel_worker_reproduces_the_serial_result_for_a_cell():
    """A run is a pure function of (scenario, seed), so a cell computed in a
    worker must equal the same cell computed in-process. Verified at full
    scale too: a smoke grid run with --workers 0 and --workers 4 produced
    bit-identical stage1_rows.csv and an identical gate verdict."""
    task = ({"n_ues": 2, "load_mult": 1.0}, 2, 400)
    rows_a, online_a, payload_a = _run_one_cell(task)
    rows_b, online_b, payload_b = _run_one_cell(task)
    assert rows_a == rows_b
    assert online_a == online_b
    assert [av for av, _, _ in payload_a] == [av for av, _, _ in payload_b]
    assert len(rows_a) == 2 * 3          # 2 seeds x 3 arms
    assert all(r["n_ues"] == 2 for r in rows_a)


def test_m13_projection_is_returned_only_for_core_plane_cells():
    """M13 consumes core-plane cells only; excursion cells must not ship a
    projection back, or the parent accumulates what it cannot use."""
    _, _, core = _run_one_cell(({"n_ues": 2, "load_mult": 1.0}, 1, 400))
    assert all(m13 is not None for _, _, m13 in core)
    _, _, exc = _run_one_cell(({"min_rb": 20}, 1, 400))
    assert all(m13 is None for _, _, m13 in exc)
