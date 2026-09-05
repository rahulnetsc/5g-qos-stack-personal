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


def core_hash() -> str:
    """A stable digest of the simulation core's behaviour-bearing AST."""
    h = hashlib.sha256()
    for p in core_files():
        try:
            tree = _strip_docstrings(ast.parse(p.read_text()))
        except SyntaxError:                      # a file mid-edit
            h.update(b"UNPARSEABLE:" + p.name.encode())
            continue
        h.update(str(p.relative_to(REPO)).encode())
        h.update(ast.dump(tree, annotate_fields=True,
                          include_attributes=False).encode())
    return h.hexdigest()[:16]


def stamp() -> dict:
    """The block a producer embeds in its artefact."""
    return {"sim_core_ast_sha256_16": core_hash(),
            "n_core_files": len(core_files())}


def artefact_state(blob) -> str | None:
    """The stamp inside an artefact, or None if it predates stamping.

    **None must NEVER be treated as matching** -- an unstamped artefact is
    exactly the case this check exists for, and treating unknown as OK is
    the empty-selection failure wearing a new hat.
    """
    if isinstance(blob, dict):
        cs = blob.get("code_state")
        if isinstance(cs, dict):
            return cs.get("sim_core_ast_sha256_16")
    return None
