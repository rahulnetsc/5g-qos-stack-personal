# WP9 defects log — found while measuring, corrected in batches

**Working rule (adopted 2026-09-02, mid-G11).** When a defect in an
already-committed result turns up *while doing something else*, **log it
here and keep going.** Corrections are made in a **single pass across
several findings**, not inline at the moment of discovery.

**The one exception, and it should be rare: anything that would change a
VERDICT rather than a number is fixed immediately.** A wrong number is
read by whoever reads that line; a wrong verdict propagates into what the
campaign does next.

**Why.** Measured, not assumed: five of the six defects found while
building the client deck were corrected in one efficient pass, and the
expensive part was **switching between measuring and correcting**, not the
corrections themselves. Batching also lets a later finding re-scope an
earlier one before either is written — the G6 protected-fleet mislabel and
the G6 headline overclaim were the same passage and would have been two
edits and two commits if taken as they arrived.

## How to log one

One row. If it needs more than a row, it is probably a verdict change.

| # | document / file | what is wrong | correct value | cited downstream by | verdict? |
|---|---|---|---|---|---|

- **cited downstream by** is the column that decides batch order — a defect
  nothing cites can wait indefinitely; one cited by the regime map's own
  rows blocks anything that quotes them.
- **verdict?** is `no` unless fixing it changes what someone would *do*.
  `yes` means fix now, and say so in the batch note.

---

## OPEN

*(none — the batch below was cleared by the deck-corrections pass)*

---

## CLOSED

| # | document / file | what was wrong | correct value | verdict? | commit |
|---|---|---|---|---|---|
| 1 | `wp9-regime-map.md` §2.1 | roll-up said "3 unrun (G9, G11, G12)" while its own G9/G12 rows said *run* — under a sentence claiming the counts were derived | 2 run, 1 unrun; now emitted by `scripts/regime_map_rollup.py` | no | `da84845` |
| 2 | `wp9-plan.md` §28.1, regime map G6 row | protected-fleet M02 quoted the **aggressor-excluded** row (`no qfi 8`), one population short of `NON_PROTECTED_5QI = {8,9}` | +0.0000 / −0.0104 / −0.0270 | no | `1cc4dbc` |
| 3 | same passage | headline claimed a pass on "both statistics"; M20 on TwoTier is INCONCLUSIVE with an interval excluding zero | +29.35 % [+4.81, +56.18] | **yes** — changes G6's stated coverage | `1cc4dbc` |
| 4 | `wp9-plan.md` §36.3, regime map G12 rows | registered ordering wording **hardened** from "not established as X" to "IS a property of declaration order" | §35.13's registered sentence, verbatim | **yes** — promotes a non-establishment to a causal claim | `38248f9` |
| 5 | `sim/fleet.py`, `sim/parametric.py`, `g12.py` | camera flows provisioned below their own GFBR, undisclosed | 3.879 vs 4.000 Mbps, ceiling ~0.970 | no | `38248f9` |
| 6 | regime map G10 rows | "admissible N 8 / 16" was the arm-**separation** boundary, mislabelled, and not per-arm | PF 8, Reservation 4, TwoTier 4 | **yes** — changes the headline deliverable | `9ce9787` |
| 7 | `wp9-plan.md` §34.4/§34.5, `CLAUDE.md`, `g9_campaign.py` | overlap mechanism refuted; cold count was events *recorded*, not attaches *completed* | 0 of 50 completed on TwoTier | **yes** — changes the operational instruction | `e9f7f65` |
| 8 | `wp9-plan.md` §24.6, `wp9_part_c.py` | cadence exclusion said `duty ≤ 0.5`; arithmetic says `0.1`, discarding a real breach | TwoTier 503.25 ms, 5/10 vs PF 0/10 | no | `e598470` |
| 9 | `wp9-g11-plan.md` §10 | cited `--check` as commit 1's verification; the corpus stores no scorecard output, so it cannot fail | per-commit intersection test, all 12 rows | **yes** — a check cited as evidence of safety | `ac8c5cc` + this pass |

**Nine defects, four of them verdict-changing.** The five that were not
would all have been fine to batch; the four that were are why the exception
exists.
