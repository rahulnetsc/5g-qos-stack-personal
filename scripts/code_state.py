"""The hash of the code that produces a run's numbers, for staleness checks.

WHY THIS EXISTS (`docs/verify-claims-staleness-proposal.md`).
`scripts/verify_claims.py` re-derives a published figure from an **artefact
on disk**. Landing `_OBJ_SCALE` (`0ea02b0`) changed **code** and rewrote no
artefact, so all nine claims kept passing while
`G1.M01.n10.twotier.median = 90.125` had become stale against post-scaling
code's 87.78. Decomposed the way this project decomposes any check: it reads
artefacts, the change touched code, **they do not intersect**, so the pass
was structurally guaranteed. This module supplies the missing intersection.

**IT HASHES THE AST, NOT THE BYTES, AND STRIPS DOCSTRINGS.** Both are
deliberate choices made BEFORE the check ever fired, not adjustments made
after it proved noisy:

  * bytes would flag reformatting and comment edits, which cannot change a
    number;
  * `ast.dump` keeps docstrings (they are `Expr(Constant(str))` nodes), and
    this repository edits docstrings constantly, so they are removed
    explicitly.

**A change to a CONSTANT still moves the hash, which is exactly the
sensitivity wanted** -- `_OBJ_SCALE = 1e4` is a constant change and is the
case that motivated all of this.

**IF THIS TURNS OUT NOISY, THAT IS A FINDING TO REPORT, NOT A THING TO
TUNE.** A check tuned until it stops firing is a shape this project has
recorded four times. The two exclusions above are the only ones; adding a
third needs its own argument in writing.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: The producing path: everything whose behaviour determines a run's numbers.
#: Tests are excluded because they cannot change a result; `scripts/` is
#: excluded because a runner's own identity is recorded separately (a runner
#: chooses WHICH cells to run, not what a cell computes).
CORE_DIRS = ("sim", "scheduler")


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    return tree


def core_files() -> list[Path]:
    out: list[Path] = []
    for d in CORE_DIRS:
        for p in sorted((REPO / d).rglob("*.py")):
            if "tests" in p.parts or p.name.startswith("."):
                continue
            out.append(p)
    return sorted(out)


def _hash_files(files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in files:
        try:
            tree = _strip_docstrings(ast.parse(p.read_text()))
        except SyntaxError:                      # a file mid-edit
            h.update(b"UNPARSEABLE:" + p.name.encode())
            continue
        h.update(str(p.relative_to(REPO)).encode())
        h.update(ast.dump(tree, annotate_fields=True,
                          include_attributes=False).encode())
    return h.hexdigest()[:16]


def core_hash() -> str:
    """A stable digest of the whole simulation core's behaviour-bearing AST."""
    return _hash_files(core_files())


def _reachable_from(entry_modules: tuple[str, ...]) -> list[Path]:
    """The core files an entry point can actually reach, by walking imports.

    THE NARROWING, and it has a measured case rather than a guessed one.
    `core_hash()` covers all 45 core files, so ANY edit to `sim/` or
    `scheduler/` invalidates every artefact. Measured over one session: five
    firings, **zero false alarms** -- every one followed a real edit -- at
    roughly ten minutes of re-running each. The cost is real and the guard is
    right; what it is not is PRECISE.

    So a producer may stamp the transitive closure of its own imports
    instead. A campaign that never touches `sim/join.py` is not invalidated
    by a change to it.

    **STATIC, and deliberately so.** It resolves `import`/`from` statements
    from the AST rather than inspecting `sys.modules`, because the dynamic
    set depends on what ran and would differ between a smoke run and a real
    one -- a hash that changes with the invocation is worse than one that is
    too broad.

    **FAILS TOWARD THE BROAD HASH.** An unresolvable import, a syntax error,
    or an entry module outside `sim/`/`scheduler/` returns the full core set.
    A narrowing that silently under-covers is the exact defect this whole
    mechanism exists to catch, so it may only ever err wide.
    """
    by_name = {}
    for p in core_files():
        rel = p.relative_to(REPO)
        by_name[".".join(rel.with_suffix("").parts)] = p
    # A producer reaches most of the core THROUGH `scripts/` helpers, not
    # directly: `phase2_core.py` imports `g11_campaign._arm`, and that is the
    # only route by which `sim/baselines/pf.py` and `sim/fleet.py` enter the
    # run at all. Stopping the walk at a non-core file therefore dropped both
    # from the scope of two campaigns that run a PF arm and build a fleet --
    # measured, 30 files with neither. So the walk TRAVERSES `scripts/` while
    # still hashing only core files.
    via = {q.stem: q for q in sorted((REPO / "scripts").glob("*.py"))}
    seen: set[str] = set()
    queue = [m for m in entry_modules]
    entries = set(entry_modules)
    while queue:
        mod = queue.pop()
        if mod in seen:
            continue
        seen.add(mod)
        path = by_name.get(mod) or by_name.get(mod + ".__init__")
        if path is None:
            path = via.get(mod)                 # traversed, never hashed
        if path is None:
            # A SYMBOL, not a module: `from sim.driver import run` queues
            # both, and the base carries the file. Resolving the base here is
            # what keeps that from counting as an unresolved entry below.
            base = mod.rsplit(".", 1)[0] if "." in mod else None
            if base and (base in by_name or base in via):
                queue.append(base)
                continue
            if mod in entries and mod.split(".")[0] in {"sim", "scheduler"}:
                return core_files()             # fail wide: named, unreachable
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            return core_files()                 # fail wide
        pkg = mod.rsplit(".", 1)[0] if "." in mod else mod
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                queue += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:                  # relative import
                    base = f"{pkg}.{base}" if base else pkg
                queue.append(base)
                queue += [f"{base}.{a.name}" for a in node.names]
    out = sorted({by_name[m] for m in seen if m in by_name}
                 | {by_name[m + ".__init__"] for m in seen
                    if m + ".__init__" in by_name})
    return out or core_files()


def scoped_hash(entry_modules: tuple[str, ...]) -> tuple[str, int]:
    files = _reachable_from(entry_modules)
    return _hash_files(files), len(files)


def _caller_scope() -> tuple[str, ...]:
    """The core modules the CALLING PRODUCER imports, derived from its own
    source rather than restated by hand.

    A hand-written module list per producer is the restated-count defect
    (CLAUDE.md): it drifts the moment the producer's imports change, and it
    drifts SILENTLY toward under-covering. So the scope is read from the
    caller's file.

    It matters that this is the producer and not `sim.driver`: measured,
    `sim.driver` alone reaches 27 of 45 core files but NOT `sim/baselines/
    pf.py`, `sim/scorecard.py` or `sim/fleet.py` -- all of which a campaign
    imports itself and all of which change its numbers.
    """
    import inspect
    for fr in inspect.stack()[1:]:
        f = Path(fr.filename).resolve()
        if f.parent == Path(__file__).resolve().parent and f.name != Path(__file__).name:
            try:
                tree = ast.parse(f.read_text())
            except SyntaxError:
                return ()
            mods: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods += [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                    mods += [f"{node.module}.{a.name}" for a in node.names]
            # `scripts/` helpers are included as ENTRY POINTS even though
            # they are never hashed: `_arm` and `run_cells` are how a producer
            # reaches `sim/baselines/pf.py` and `sim/fleet.py`, and a scope
            # built from the `sim.*` imports alone silently omitted both.
            local = {q.stem for q in (REPO / "scripts").glob("*.py")}
            return tuple(m for m in mods
                         if m.split(".")[0] in ("sim", "scheduler")
                         or m.split(".")[0] in local)
    return ()


def stamp(entry_modules: tuple[str, ...] | None = None) -> dict:
    """The block a producer embeds in its artefact.

    Pass `entry_modules` (e.g. `("sim.driver", "scheduler.two_tier")`) to
    stamp only what those reach; omit it for the full core set. **Both are
    recorded**, so a reader can tell which was used and a narrow stamp can
    never be mistaken for a broad one.
    """
    d = {"sim_core_ast_sha256_16": core_hash(),
         "n_core_files": len(core_files())}
    if entry_modules is None:
        entry_modules = _caller_scope() or None
    if entry_modules:
        h, n = scoped_hash(tuple(entry_modules))
        d["scope"] = list(entry_modules)
        d["scoped_ast_sha256_16"] = h
        d["n_scoped_files"] = n
    return d


def expected_for(blob) -> tuple[str, str]:
    """(hash to compare against, how it was scoped) for an artefact.

    An artefact carrying a `scope` is compared against the SAME scope
    recomputed at HEAD -- so an edit to a module the producer never imports
    does not invalidate it, while an edit to one it does still fires. Both
    directions are pinned in `sim/tests/test_code_state.py`.

    An artefact with no scope falls back to the whole core, which is the
    conservative direction.
    """
    if isinstance(blob, dict):
        cs = blob.get("code_state") or {}
        scope = cs.get("scope")
        if scope:
            return scoped_hash(tuple(scope))[0], f"scope={len(scope)} entries"
    return core_hash(), "whole core"


def artefact_state(blob) -> str | None:
    """The stamp inside an artefact, or None if it predates stamping.

    **None must NEVER be treated as matching** -- an unstamped artefact is
    exactly the case this check exists for, and treating unknown as OK is
    the empty-selection failure wearing a new hat.
    """
    if isinstance(blob, dict):
        cs = blob.get("code_state")
        if isinstance(cs, dict):
            # prefer the scoped stamp when the producer recorded one
            return (cs.get("scoped_ast_sha256_16")
                    or cs.get("sim_core_ast_sha256_16"))
    return None
