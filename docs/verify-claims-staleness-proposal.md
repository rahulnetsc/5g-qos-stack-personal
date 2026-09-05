# Closing `verify_claims`' blind spot — **BUILT 2026-09-05**

> **LANDED.** `scripts/code_state.py` + the staleness check in
> `scripts/verify_claims.py`, with `sim/tests/test_code_state.py`. The
> proposal below is kept as written; §7 records what the noisy landing found
> and how the nine claims were triaged.

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


---

## 7. What the noisy landing found, and the claim-by-claim triage

**Landed noisy on purpose.** On first run **8 of 9 claims FAILED** as
`UNSTAMPED` — the blind spot becoming visible. A quiet landing would have
meant the check could not see what it was built for.

**The hash behaved as designed, and was tested in both directions before any
triage** — a docstring edit to `scheduler/tier1.py` left it unchanged, and
flipping `_OBJ_SCALE = 1.0e4 → 1.0e5` moved it. **It is not noisy, so there
was nothing to report under the stop-and-report rule.**

### The triage — one decision per claim, not a rule that guesses

| claim | disposition | why |
|---|---|---|
| `G8.M22.PRE_CORRECTION` | **historical** | the kept pre-correction demonstration failure. Re-running it would destroy the demonstration, which *is* the claim |
| `G8.M22.n10.reservation` | **re-run** | repointed to the stamped `core_scaled.json`; value unchanged (7) |
| `G8.M09.n10.twotier` | **re-run** | repointed; value unchanged (3) |
| **`G1.M01.n10.twotier.median`** | **re-run, AND THE VALUE MOVED** | **90.125 → 87.7845.** This is the figure the whole check was built for — it re-derived cleanly from its old artefact for a full day after the code that produced it changed |
| `G1.M01.n10.breaches` | **re-run** | repointed; value unchanged (0) |
| `G3.M20.n10.breaches` | **re-run** | repointed; value unchanged (0) |
| `G5.M05.n10.reservation` | **re-run** | repointed; value unchanged (7) |
| `G10.admissible.PF` | **re-run** | repointed to `g5_consol_scaled.json`. **The `n` check then caught a second thing**: the artefact was 3 seeds against a published n=10 claim, so it was re-run at n=10 rather than the claim being lowered to fit — lowering it would have weakened a published figure to match an artefact, which is the wrong direction and the shape of this project's own n≤3 exposure |
| **`G11.C1.soak.runs`** | **REMOVED** | `min(n_windows) == 30` restates **arithmetic** — 7.2M slots × 0.25 ms ÷ 60 s *is* 30, on any arm under any scheduler — and the checker had already flagged it as not estimator-discriminating. A figure nobody needs does not justify regenerating an artefact. C1's real figure (0 failing windows of 900) gets a claim the next time the 72-minute soak runs for a reason of its own |

**Result: 8 claims, all passing for the right reason** — seven stamped
against HEAD, one explicitly historical.

### One thing the landing changed that was not predicted

`sim/tests/test_verify_claims.py`'s own fixture cites the pre-correction
artefact and **started failing on staleness rather than on the estimator
behaviour it tests.** Fixed by marking the fixture `historical` — and a
**converse test was added** asserting the same fixture *without* that marking
fails as `UNSTAMPED`, so the exemption is a deliberate use rather than a
default that quietly disables the check.

### The limitation to state

**Only JSON artefacts can carry a stamp.** A `.csv` or `.jsonl` artefact has
nowhere to put one, so a `current` claim citing either fails permanently.
`test_code_state.py` asserts this explicitly rather than leaving it to be
discovered: a non-JSON artefact under a `current` claim is a test failure
naming the claim. Both such claims were repointed or removed in the triage;
a future one needs a sidecar, and that is not built.

---

## 8. The first real cost of the guard, observed the same day

**Adding `rejoin_seed_bsr` to `sim/driver.py` — a new parameter defaulting
to `False`, verified bit-identical when off — invalidated every stamped
artefact and failed two tests.**

**That is the guard working to specification, not noise.** Its question is
*"was this artefact produced by the current code?"*, and the answer was
genuinely no. The remedy is the designed one: re-run. Cost this time was
~10 minutes for `core_scaled.json` and `g5_consol_scaled.json`.

**It was NOT tuned, and the tempting tune is named here so the next person
recognises it:** one could exclude parameters that default to their previous
behaviour, or hash only "reachable" code. **Both would convert the guard
from "was this produced by current code" into "was this produced by code I
judge equivalent", and that judgement is exactly what the guard exists to
replace.** A check tuned until it stops firing is a shape this project has
recorded four times.

**The real cost, stated plainly so it can be traded off deliberately:** any
change to `sim/` or `scheduler/` invalidates every artefact, so a project
that touches those often will re-run often. **The finer-grained alternative
— hashing only the modules an artefact's producer actually imports — is a
real option and is not built.** It would reduce false alarms and would also
be substantially harder to get right, since the dependency set is dynamic.
**Recorded as an option with its trade-off, not adopted.**
