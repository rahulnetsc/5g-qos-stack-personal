# Making the guarantee set internally consistent — registered before running

**2026-09-05.** `docs/verification-2026-09-04.md` currently mixes
post-scaling rows (G1, G3, G5, G8, G10) with pre-scaling ones (G4, G6,
G11 C1, G12). **That is the horizon inconsistency repeating in a different
variable** — a reader cannot tell which numbers are comparable. This closes
it.

## Predictions, fixed before any run

Only TwoTier can move: 838 corpus values moved and **all 838 were TwoTier**.
PF and Reservation do not call `solve_tier1` and were confirmed
bit-identical. **So PF and Reservation results MUST be unchanged in all
three campaigns — that is the control, and movement there is a defect.**

| G | current | prediction | why |
|---|---|---|---|
| **G4** | duty 0.1 separation: TwoTier−PF **+5.86 [+4.50, +7.25]**; duty 0.5/1.0 null | **HOLDS, but the effect SHRINKS** | the gap is a TwoTier-minus-PF difference and only TwoTier moves; scaling improved TwoTier elsewhere, which *narrows* this gap. Interval excludes zero by 4.5 against a half-width ~1.4, so it should survive a few-ms narrowing |
| **G12** | TwoTier `[4,2]` 5/10, `[2,4]` 4/10, one degenerate `[2]`; PF `[4,2]` 10/10 | **MOVES — the one I would bet on** | first-violation *order* is decided by which class breaches first, so it is a threshold-crossing statistic and maximally sensitive to a few-percent shift in TwoTier's targets. Clause 4's telemetry failure is a TwoTier result |
| **G11 C1** | **1.000 on all three arms, 0 of 300 windows failing per arm** | **HOLDS at 1.000** | zero failures with no near-misses; a few-percent change has no path to 300 clean windows becoming unclean |

**I got both of my last two risk calls wrong by reasoning from margin and
ignoring direction** (`docs/tier1-scaling-followup-2026-09-05.md` §1). The
correction is applied here: scaling *improves* TwoTier, so where TwoTier
being better makes a verdict better, I predict it holds; where TwoTier being
better changes an *ordering*, I predict it moves.

## G6 is deliberately NOT re-run

**No verdict is publishable regardless of scaling.** G6 is unscoreable as
written (`docs/verification-2026-09-04.md`), so re-running it produces three
readings on new numbers instead of three readings on old ones — the same
non-result at the cost of an n=40 campaign. Its row says so explicitly
rather than leaving it looking overlooked.

## Deferred, recorded so they are not rediscovered

1. **The configuration-based / direct solver swap (41× direct-HiGHS).**
   **DEFERRED.** The profile settles it: a *free* LP buys **1.60×** on
   TwoTier's driver, so there is no performance case, and
   `_OBJ_SCALE` already took the correctness one. Re-opened in CLAUDE.md
   only to correct the recorded *reason* for the original rejection, not
   because it should be taken.
2. **The Tier-1 reformulation (exact greedy / closed-form water-filling).**
   **DEFERRED**, same reason. The greedy is exact and 15.6× faster, but
   against a 1.60× ceiling that is 0.18 s of 12.2 s, and taking it would
   cost a second deliberate corpus re-baseline plus a tie-break fidelity
   argument that cannot be settled — there is no Tier-1 ground truth in this
   repository. **The correctness gap it would close has already been closed
   by scaling** (98.7 % exact).

**Both are deferred on the same finding: the LP is neither the correctness
problem nor the performance problem any more.**


---

## Results — scored against the registration above

| G | prediction | outcome | scored |
|---|---|---|---|
| **G4** | holds, effect **shrinks** | **HELD.** TwoTier−PF at duty 0.1: **+5.86 → +6.76**, still excluding zero; every other contrast unchanged | **verdict HIT, direction MISS** — the effect *grew* |
| **G12** | **"moves" — the one I would bet on** | **Verdict HELD** (neither promotion clause fires, registered conclusion applies verbatim). **But TwoTier's lean moved in 2 of 6 conditions**: canonical/mixed_n8 TIE → `[2,4]`, perm104 `[2,4]` → `[4,2]` | **AMBIGUOUS — my own fault.** I predicted "moves" without saying *what*. The statistic moved; the verdict did not |
| **G11 C1** | holds at 1.000 | **HELD.** 30/30 runs, 7.2M slots, memory guard never tripped, 0 failed runs. **1.000 on all three arms, 300 windows each, 0 failing** — identical to pre-scaling. PF and Reservation window counts bit-identical | **HIT** |

**CONTROLS HELD IN BOTH COMPLETED CAMPAIGNS.** G4: PF and Reservation rows
**bit-identical**. G12: PF and Reservation leans identical in all six
conditions; only TwoTier moved.

### The lesson from G12's scoring, recorded because it is mine

**"It moves" is not a prediction until it names the level.** A verdict, a
point estimate, and a per-condition lean are three different things, and
G12's *statistic* moved while its *verdict* held. That is the same
level-mismatch this project already records for checks (value / layer /
scope) — applied to a prediction rather than to a guard. **Predict the level,
not just the direction.**

### And a near-miss worth logging

Scoring G4 with my own ad-hoc aggregation of the same artefact gave
**opposite signs** and two spurious "MOVED" verdicts. Using the runner's own
scorer reproduced the published figures exactly (+10.94, +5.86) and showed
everything held. **A re-derived statistic that does not reproduce the
published one means you have built a different instrument, not that the
published one is wrong** — check reproduction before reading a diff. This is
exactly what `verify_claims` exists to enforce, and I did it by hand and got
it wrong first.


### C1's close

**G11 C1 re-run post-scaling: 30/30 runs at 7,200,000 slots, exit 0, memory
guard never tripped, 0 failed runs. 1.000 on all three arms, 900 windows,
0 failing — identical to the pre-scaling soak.** Predicted to hold, and it
held; the margin (0 failures, no near-misses) was never in doubt.

**THE CONSISTENCY DELIVERABLE IS CLOSED.** Every guarantee in
`docs/verification-2026-09-04.md` is now either measured on post-scaling
code (G1, G3, G4, G5, G8, G10, G11 C1, G12) or **explicitly marked
pre-scaling with its reason** (G6 — unscoreable as written, so re-running
buys three contradictory readings on new numbers instead of three on old
ones). The provenance table carries a `code state` column for every row.

### Final prediction score

| prediction | outcome |
|---|---|
| G4 holds, effect shrinks | verdict **HIT**, direction **MISS** (it grew) |
| G12 "moves" | **AMBIGUOUS** — statistic moved, verdict held; I named no level |
| G11 C1 holds at 1.000 | **HIT** |
| PF/Reservation unchanged everywhere | **HIT**, confirmed bit-identical in all three campaigns |

**Two clean hits, one verdict-hit-direction-miss, one ambiguous of my own
making.** The recurring lesson across this session and the last: I keep
predicting *whether* something moves without naming *what* — verdict, point
estimate, or per-condition lean — and the ambiguity is a defect in the
prediction, not in the result.
