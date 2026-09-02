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

| # | document / file | what is wrong | correct value | cited downstream by | verdict? |
|---|---|---|---|---|---|
| 10 | `wp9-g11-plan.md` §4.2 | claims eviction takes per-run retention to **~1 GiB**, restoring 16-wide parallelism | eviction alone leaves **~5.6 GiB/run** at 7.2 M slots; ~49 % of the residual is `sim/metrics.py::FlowMetrics.hol_delay_samples_s`, which neither commit 2 nor commit 3 touches | §7.3's option (c) makespan, ≈2.15 h | no — changes a budget, not a verdict; commit 8's `--time-cell` measures the real cell anyway |
| 11 | `wp9-g11-plan.md` §10 | commit-2 row says `--check` is blind "because eviction is scoring-layer" | the mechanism is in `sim/driver.py` and the corpus stores driver output; **`--check` BINDS** — see the registered-expectation miss below | the commit table's own binding/blind split | no |
| 12 | `sim/metrics.py` | `hol_delay_samples_s` is a `list` of Python floats — ~32 B/sample, ~87 M samples at 7.2 M slots | `array("d")` at 8 B/sample takes the evicted floor ~5.6 → ~2.0 GiB, value-identical (`_percentile` sorts a copy either way) | §7.3's budget | no — its own commit, `--check`-neutral |

**A REGISTERED EXPECTATION MISSED, recorded rather than absorbed.** The
commit table registered *"commit 2: `--check` is BLIND"*. **It is not.** The
commit adds `RunRecord.message_ledger_windowed`, the corpus serialises
`RunRecord`s, and `--check` failed on the first run with
`study3/latency_bound/TwoTier.message_ledger_windowed: MISSING in baseline`.

**The prediction was wrong for the reason the rule it came from exists.** I
applied *"name what the check reads and what the commit touches"* using the
commit's **headline** (ledger eviction, scoring-adjacent) rather than its
**diff** (which reaches `RunRecord`). The intersection test is only sound
against what a commit actually changes, and at registration time that was
not yet known — which is an argument for re-running the test when the diff
exists, not only when the row is written.

**Resolved without re-baselining**: the field is serialised **only when
true**, so a non-windowed record's `to_dict()` is byte-identical to before
and the frozen corpus is untouched (`--check` clean at `--rel-tol 0`).
Re-baselining would have been the wrong move — the change is not *intended*
to move any number.

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
