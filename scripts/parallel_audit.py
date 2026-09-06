"""Which scripts run simulations, and which of those run them in parallel.

DERIVED, NOT RESTATED. The finding that produced this file came from a grep
whose result was written into prose -- "five parallel, twenty-two serial" --
and this project has five recorded instances of a count in prose going stale
the moment the code moved (CLAUDE.md). So the classification is computed from
each file's own AST and printed by the thing that computes it.

WHAT COUNTS AS "RUNS SIMULATIONS". A module that reaches `sim.driver.run`,
`regime_sweep.sweep`, `regime_sweep.run_cells` or `wp9_sweep._run_one_cell`
-- imported by name or via an attribute call. Importing one of those modules
is not enough; an analysis script that imports `regime_sweep` for
`bootstrap_ci` is not a runner and is classified as analysis.

WHAT COUNTS AS PARALLEL. Using `regime_sweep.run_cells`, or driving a pool
directly (`multiprocessing`, `concurrent.futures`). `run_cells` is the
preferred form and the audit says which of the two a runner uses, because a
hand-rolled pool is where the oversubscription and longest-first lessons get
lost again.

Exit code is non-zero if any runner is serial, so this is usable as a check
rather than only as a report -- `--allow` names the ones that are serial
deliberately, each with its reason, so a NEW serial runner fails the check
while a known one does not.

Usage:
    uv run python scripts/parallel_audit.py
    uv run python scripts/parallel_audit.py --check
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
# The repo root, so `import sim` / `import scheduler` resolve when the
# dead-call check imports them. Without it every script reports a
# ModuleNotFoundError -- a check that fires on everything is as useless
# as one that fires on nothing, and louder about it.
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(SCRIPTS))

# A module is a RUNNER if it imports one of these run entry points and
# mentions it anywhere -- referenced, not necessarily called directly, since
# `pool.imap_unordered(_run_one_cell, tasks)` passes it rather than calling
# it and an earlier version of this audit missed wp9_part_c.py for exactly
# that reason.
_RUN_SYMBOLS = {
    ("sim.driver", "run"),
    ("regime_sweep", "sweep"),
    ("regime_sweep", "run_cells"),
    ("wp9_sweep", "_run_one_cell"),
    ("wp9_sweep", "run_stage_1_parallel"),
    # Runners that wrap another runner's entry point rather than the driver.
    ("g12_campaign", "run_ramp"),
    ("g12_campaign", "_task"),
    ("g4_postsilence", "collect_rows"),
    ("g6_seed_extension", "collect_rows"),
    ("phase2_core", "one"),
}
_POOL_MODULES = {"multiprocessing", "concurrent.futures", "concurrent"}

# Serial BY DESIGN, with the reason. Anything not listed here that runs
# simulations serially is a finding, which is the point of the list being
# explicit rather than a heuristic. An entry that does NOT appear in the
# serial set is reported as inert -- an exclusion doing no work today is one
# that hides a real finding tomorrow (scripts/verify_parallel.py makes the
# same argument about its own exclusion list).
ALLOW_SERIAL = {
    "regression_corpus.py": "20 fixed records; the corpus is the reference "
                            "and must stay the simplest possible path",
    "run_smoke.py": "a single smoke run by definition",
    "plot_timeseries.py": "one run, to draw it",
    "tbs_counterfactual.py": "replays one existing run's grants offline",
    "g12_ramp_probe.py": "a stop-condition probe, one arm one seed",
    "cce_bind_probe.py": "a diagnostic sweep, one arm one seed per cell -- the "
                         "question is which RESOURCE binds, which needs no "
                         "seed replication, and each cell prints as it "
                         "completes so ordering is the readable form",
    "bsr_desync_probe.py": "monkeypatches BsrModel._assemble and .broadcast at "
                           "module level to observe per-slot state; under "
                           "`spawn` a worker re-imports the module and would "
                           "run the UNPATCHED code, so a pool would silently "
                           "measure nothing -- the same trap as a module-level "
                           "config cell not reaching workers",
    "cqi_study.py": "PHASE 1 STUDY, superseded -- kept because it still runs",
    "maxmin_study.py": "PHASE 1 STUDY, superseded -- kept because it still runs",
    "f2_duty_cycle_trace.py": "single-run trace, by construction",
    "phase2_g2.py": "G2 is NOT MEASURED (docs/phase2-results.md); this "
                    "probes one configuration",
    "scheduler_study.py": "the published studies 1-3, whose numbers are "
                          "quoted as-is; parallelising it would need its "
                          "own identity check against those numbers",
}


def _imports(tree: ast.Module) -> dict[str, tuple[str, str]]:
    """{local name: (source module, ORIGINAL name)}.

    The original name matters and an earlier version of this file dropped it,
    which is worth keeping as a comment because the bug it caused is the one
    this audit is about. Matching on the module alone made every analyser
    that does `from regime_sweep import bootstrap_ci` look like a runner --
    a check that fires on the wrong thing, which is no better than one that
    cannot fire.
    """
    names: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for al in node.names:
                names[al.asname or al.name.split(".")[0]] = (al.name, al.name)
        elif isinstance(node, ast.ImportFrom):
            for al in node.names:
                names[al.asname or al.name] = (node.module or "", al.name)
    return names


def classify(path: Path) -> dict:
    tree = ast.parse(path.read_text())
    names = _imports(tree)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}

    # `from x import y` / `from x import y as z`
    runs = any(local in used and (mod, orig) in _RUN_SYMBOLS
               for local, (mod, orig) in names.items())

    # MODULE-STYLE IMPORTS, which the from-import check above cannot see:
    # `from sim import driver` + `driver.run(...)`, and
    # `import sim.driver as driver_mod` + `driver_mod.run(...)`. Both are in
    # this repo (g12_ramp_probe.py, bsr_desync_study.py) and both were
    # misfiled as analysis until this was added -- the same shape as the
    # module-only match above, one level out.
    attrs = {(n.value.id, n.attr) for n in ast.walk(tree)
             if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    for local, attr in attrs:
        mod, orig = names.get(local, ("", ""))
        full = f"{mod}.{orig}" if mod and orig != mod else (mod or orig)
        if (full, attr) in _RUN_SYMBOLS:
            runs = True

    parallel_via: list[str] = []
    if names.get("run_cells", ("", ""))[0] == "regime_sweep" \
            and "run_cells" in used:
        parallel_via.append("regime_sweep.run_cells")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in (
                "Pool", "ProcessPoolExecutor"):
            parallel_via.append(node.attr)
    return {"name": path.name, "runs": runs,
            "parallel": sorted(set(parallel_via))}


def dead_calls(path: Path) -> list[str]:
    """Calls whose keyword arguments the callee no longer accepts.

    THE CLASS THIS CATCHES. `TwoTier.__init__` stopped taking
    `tier1_period_slots` at the Phase 2 rewrite, and SEVEN scripts kept
    passing it -- every one of them IMPORTING CLEANLY, because a constructor
    is not called at import time. Nothing static noticed and nothing dynamic
    ran them, so they sat dead for a phase. Import-checking is not enough;
    the signature has to be compared against the call.

    Also flags a `from <project module> import NAME` whose NAME is gone --
    `knapsack_diagnostic.py` failed that way on `estimate_demand_bps`.
    """
    import importlib
    import inspect
    tree = ast.parse(path.read_text())
    names = _imports(tree)
    problems: list[str] = []
    resolved: dict[str, Any] = {}
    for local, (mod, orig) in names.items():
        if not mod.split(".")[0] in ("scheduler", "sim"):
            continue
        try:
            m = importlib.import_module(mod)
        except Exception as exc:                     # noqa: BLE001
            problems.append(f"import {mod}: {type(exc).__name__}: {exc}")
            continue
        if mod == orig:
            # `import sim.driver as driver_mod` binds the MODULE, not an
            # attribute of it. Importing it cleanly is the whole check.
            continue
        if not hasattr(m, orig):
            problems.append(f"{mod}.{orig} no longer exists")
            continue
        resolved[local] = getattr(m, orig)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        fn = resolved.get(node.func.id)
        if fn is None or not (inspect.isclass(fn) or inspect.isfunction(fn)):
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        if any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in sig.parameters.values()):
            continue
        for kw in node.keywords:
            if kw.arg and kw.arg not in sig.parameters:
                problems.append(
                    f"{node.func.id}(..., {kw.arg}=...) at line {node.lineno}: "
                    f"no such parameter")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any runner is serial and not "
                         "listed in ALLOW_SERIAL, or any script is dead")
    a = ap.parse_args(argv[1:])

    rows = [classify(p) for p in sorted(SCRIPTS.glob("*.py"))]
    runners = [r for r in rows if r["runs"]]
    parallel = [r for r in runners if r["parallel"]]
    serial = [r for r in runners if not r["parallel"]]
    analysis = [r for r in rows if not r["runs"]]

    print(f"{len(rows)} python files under scripts/")
    print(f"  {len(runners)} run simulations, {len(analysis)} are analysis "
          f"or reporting only")
    print(f"\nPARALLEL ({len(parallel)}):")
    for r in parallel:
        print(f"  {r['name']:<28} {', '.join(r['parallel'])}")
    print(f"\nSERIAL ({len(serial)}):")
    unexplained = []
    for r in serial:
        why = ALLOW_SERIAL.get(r["name"])
        if why is None:
            unexplained.append(r["name"])
        print(f"  {r['name']:<28} {why or '*** NO RECORDED REASON ***'}")
    print(f"\nANALYSIS / REPORTING ONLY ({len(analysis)}):")
    print("  " + "  ".join(r["name"] for r in analysis))

    print("\nDEAD CALLS (a signature the callee no longer has, or a vanished "
          "import):")
    dead: dict[str, list[str]] = {}
    for path in sorted(SCRIPTS.glob("*.py")):
        if path.name == "parallel_audit.py":
            continue
        probs = dead_calls(path)
        if probs:
            dead[path.name] = probs
            for msg in probs:
                print(f"  {path.name:<28} {msg}")
    if not dead:
        print("  none -- every script's calls match the signatures it calls")

    inert = sorted(set(ALLOW_SERIAL) - {r["name"] for r in serial})
    if inert:
        print(f"\nALLOW_SERIAL entries that are not serial runners "
              f"({len(inert)}): {inert}")
        print("  Each is doing no work -- remove it, or the list stops "
              "describing anything.")
    if unexplained:
        print(f"\n{len(unexplained)} serial runner(s) with no recorded "
              f"reason: {unexplained}")
        print("  Either use regime_sweep.run_cells, or add the file to "
              "ALLOW_SERIAL with the reason it is serial on purpose.")
    if a.check:
        return 1 if (unexplained or dead) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
