# Closing `verify_claims`' blind spot — proposal, not built

**2026-09-05.** `verify_claims --check` passed all 9 claims immediately
after `0ea02b0`, while `G1.M01.n10.twotier.median = 90.125` had become stale:
post-scaling code gives **87.78**. The checker was working exactly as
designed and told us nothing.

## The shape

**It confirms a figure matches its cited artefact. It cannot see that the
artefact predates the code that would produce it now.** Decomposed the way
this project decomposes any check:

| | |
|---|---|
| what the check reads | **artefacts on disk** |
| what `0ea02b0` touched | **`scheduler/tier1.py`** |
| do they intersect? | **no** |

So the pass was structurally guaranteed — the third fault shape from
CLAUDE.md's could-have-failed table: *the check passes and could NOT have
failed, so you learn nothing and believe you learned something.*

**And it is the same shape as `stage6_partA.json`: fixing the generator does
not fix what it already wrote.** A repaired producer leaves every artefact it
produced earlier untouched and still cited.

## The fix

**Record the code state alongside each artefact, and fail when a cited
artefact's state does not match HEAD unless the claim is marked historical.**

1. **Producers stamp what produced them.** Every campaign runner writes, into
   its own output, a `code_state` block: the git commit, whether the tree was
   dirty, and — because a commit is too coarse — a **content hash of the
   producing path**: the files whose behaviour the artefact depends on
   (`sim/`, `scheduler/`, plus the runner). A commit-only stamp would flag
   every doc-only commit as stale, which is the fastest way to get a check
   ignored.
2. **`published_claims.yml` gains nothing new to maintain by hand.** The
   existing `code_state:` field stops being documentation and becomes an
   enum: `current` (default — must match HEAD's hash) or
   `historical: <reason>` (deliberately pinned to an old artefact, e.g. the
   kept `G8.M22.PRE_CORRECTION` failing case, which must NOT be re-derived
   against current code).
3. **`verify_claims` gains one check**: recompute the producing-path hash at
   HEAD, compare to the artefact's stamp, and **fail a `current` claim whose
   artefact was produced by different code** — reporting *which* files
   differ, so the message says "re-run this campaign" rather than "something
   changed".
4. **Artefacts predating the stamp** report `code_state: unknown` and fail a
   `current` claim, with a one-line remedy: re-run, or mark the claim
   historical with a reason. **Unknown must not be treated as matching** —
   that is the empty-selection failure wearing a new hat.

## What it costs, and the one risk

- **Cost:** one helper (hash the producing path), one line in each runner's
  output block, and ~30 lines in `verify_claims`.
- **The risk, named:** a hash over `sim/` + `scheduler/` flags a comment-only
  edit as staleness, the check gets noisy, and noisy checks get bypassed.
  **Mitigation: hash the AST, not the bytes** — `ast.dump` of each module,
  which is already the technique `parallel_audit.py` uses to avoid deriving
  its answer from a grep. A docstring or comment change then does not trip
  it; a constant change does. That is the right sensitivity: `_OBJ_SCALE =
  1e4` is exactly a constant change.

## What it would have caught

`G1.M01.n10.twotier.median`, `G3.M20.n10.breaches`, `G5.M05.n10.reservation`,
`G8.M09.n10.twotier` and `G8.M22.n10.reservation` — **five of the nine
claims**, all citing `core_40k_n10.json`, produced before `_OBJ_SCALE`. Today
that took a hand-built provenance column and a person remembering to add it.
**A green check should have been impossible.**
