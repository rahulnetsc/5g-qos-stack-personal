# WP9 defects log — found while measuring, corrected in batches

**Working rule (adopted 2026-09-02, mid-G11).** When a defect in an
already-committed result turns up *while doing something else*, **log it
here and keep going.** Corrections are made in a **single pass across
several findings**, not inline at the moment of discovery.

**The boundary, stated as a test rather than a feeling: BATCH findings about
RESULTS; FIX IMMEDIATELY anything that gates the NEXT ACTION.**

- A wrong number in a finished result is read by whoever reads that line.
  It waits for the batch.
- A defect that gates what happens next — a guard an unattended run depends
  on, a prerequisite without which the next commit cannot be verified —
  cannot wait, because the thing it gates happens before the batch does.

**Worked both ways, once each, on the same day.** The aggregate memory guard
(#14) was **not** batched: it was a prerequisite for an unattended
multi-hour run's safety, not a defect in a finished number — and the first
real-horizon run tripped it, which is what "gates the next action" means in
practice. The memory attribution (#15) **stays** batched by the same test:
it gates nothing, the run fits without it, and chasing it would be depth on
a number that does not matter.

**The older phrasing — "anything that would change a VERDICT rather than a
number" — is the same test read from the results side**, and both are kept
because each catches cases the other states less clearly. A wrong number is
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
| 13 | `wp9-g11-plan.md` §7.3 | option (c) prices the campaign at **16 workers**; the measured evicted residual is 2.83 GiB/run at N=4, so 16 would need 45 GiB against 24.2 available | **8 workers**; makespan ≤3.33 h (N=8 costs, N=4 is cheaper), still comfortably overnight | §7.3's ≈2.15 h | no — the campaign still fits, at ~35 % more wall clock |
| **14** | `sweeps/wp9/g11_probes/memwatch.sh`, and commit 8's runner | the watchdog threshold is **PER-PROCESS (22 GiB)**. At 2.83 GiB/run **no single worker ever approaches it**, so it would not fire — while the real failure mode at 16 workers is **aggregate** exhaustion (45 GiB against 24.2) | an **aggregate** threshold across workers, or a per-worker one derived as `budget ÷ workers`; ideally both | commit 8's "live RSS instrumentation with a kill threshold" | no — but it is a **prerequisite for commit 8**, not batchable, since the guard is the thing that makes a 3-hour run safe |
| **16** | `scripts/g11_campaign.py` | commit 7 built C2's drift detector; commit 8 **never wired the per-window internal counters in**, so C2 cannot be scored from this run at all | collect crumb rate and floor-fire rate per window in the runner's sink | C2's verdict in `g11_score.py` | no — but it is a **gap in this plan's own commit sequence**, not a property of the run, and the first-pass answer says so rather than reporting C2 as "no drift" |
| **15** | `wp9-g11-plan.md` §7.3–§7.4, defects-log #10/#13 | per-run memory at the **real** horizon is **~6–9 GB**, not the 2.83 GiB estimated by scaling the N=8 evicted residual to N=4 | **2 workers**, not 8; makespan ~5.7 h for 3 arms × 10 seeds | §7.3's option (c), #13's 8-worker figure | no — the campaign still fits overnight, at ~4× the wall clock |
| ~~12~~ | `sim/metrics.py` | `hol_delay_samples_s` is a `list` of Python floats — ~32 B/sample, ~87 M samples at 7.2 M slots | `array("d")` at 8 B/sample takes the evicted floor ~5.6 → ~2.0 GiB, value-identical (`_percentile` sorts a copy either way) | §7.3's budget | no — its own commit, `--check`-neutral |

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

**COMMIT 3's REGISTERED `--check` PREDICTION: MISS.** Registered *"BINDS
AND MOVES — the `ts_*` arrays shorten on all 20 records"*. **`--check` came
back clean.** The fold is **opt-in** (`timeseries_resolution="slot"` by
default), because making it the default would rewrite every existing study
and the frozen corpus — precisely what the one-change-per-commit and
do-not-recapture rules forbid. No corpus case opts in, so nothing moves.

**The registered outcome→meaning map was ALSO wrong.** It said a clean
`--check` *"would mean the fold is not reaching the serialised record"*. It
means no such thing: clean is the *correct* result for an opt-in change.

**Two misses in two commits, in OPPOSITE directions, from one cause.**
Commit 2 registered *blind* and it **bound** (I reasoned from the commit's
headline, not its diff). Commit 3 registered *binds* and it is **blind** (I
registered before deciding opt-in versus default). **The blind/binds call
depends on a design decision, and registering it before that decision is
made registers a guess about the design, not a prediction about behaviour.**

Unlike a shape prediction about data — which is exactly the thing the
journal's first form rule says *can* be fixed in advance — this one cannot
be, and pretending otherwise produced two confident wrong answers.
**Corrected practice: register the blind/binds call at the moment the design
is settled and before the code is run** — still in advance of the evidence,
which is what the rule is for, but not in advance of the decision it
depends on.

**#15, AND #12 IS REFUTED AS ITS CAUSE.** The real-horizon budget probe
(3 arms × 7,200,000 slots, 3 workers) **tripped the aggregate guard**: pool
total 20,219 MB with the largest worker at **9,249 MB**, killed at 00:57:45.

**The guard did exactly what #14 said it had to.** A per-process 22 GiB
threshold would **not** have fired — 9.2 GB is nowhere near it — while the
machine had 4.0 GB left. The aggregate guard is the only reason this was a
measurement rather than an OOM.

**And the cause is NOT `hol_delay_samples_s`.** Both the scoping pass and
defects-log #12 named it as ~49 % of the residual, which made `array("d")`
look like a lever. Measured directly, by patching the accumulator to retain
nothing: **477 → 422 MiB at h=400,000, i.e. 55 MiB of 477 (12 %)**. So #12
is struck through — it is real but it is worth ~12 %, not 49 %, and it
would not change the worker count. **The 49 % figure came from a run with
`record_timeseries=False` and no eviction; it did not survive the change of
configuration it was quoted about.**

**Where the memory actually goes is not yet established**, and that is
recorded as unknown rather than guessed: `tracemalloc` at end-of-run shows
~0 because the peak is transient and freed by return, so attributing it
needs sampling *during* the run. Not chased — the campaign is runnable at
2 workers and the attribution changes no decision today.

**AND THE WATCHDOG IS THE COULD-HAVE-FAILED SHAPE AGAIN (#14).** The guard
that killed the 7.2 M-slot probe at 21.8 GiB is a **per-process** threshold,
and it worked there because that run was one process. The soak is 8–16
processes of 2.83 GiB each: **no individual worker ever gets near 22 GiB, so
the watchdog cannot fire**, while the machine runs out of memory at ~8
concurrent runs. A guard aimed at the wrong aggregation level is a guard
that cannot fail — the third instance of that shape this week, after J5's
expectation and commit 1's `--check`. Fixed in commit 8, where the runner
lives; **not batched**, because the guard is what makes an unattended
multi-hour run safe.

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
| 8 | `wp9-plan.md` §24.6, `wp9_part_c.py` | cadence exclusion said `duty ≤ 0.5`; arithmetic says `0.1`, discarding a real breach | TwoTier 503.25 ms, 5/10 vs PF 0/10 | no | `e598470` — **and see #18 below: this correction ALSO over-shot** |
| 9 | `wp9-g11-plan.md` §10 | cited `--check` as commit 1's verification; the corpus stores no scorecard output, so it cannot fail | per-commit intersection test, all 12 rows | **yes** — a check cited as evidence of safety | `ac8c5cc` + this pass |

**Nine defects, four of them verdict-changing.** The five that were not
would all have been fine to batch; the four that were are why the exception
exists.

---

## #17 — THE MEMORY BUDGET WAS MEASURED ON A DIFFERENT RUN, AND THE CAUSE IS FIXED (2026-09-03)

**This retracts #10, #13 and #15's figures, and the regime map's, and the
handover's, and `wp9-g11-plan.md` §7.3's.** Not refined — retracted. They
describe a configuration the campaign does not use.

**The provenance.** Every published per-run figure for G11 —
`~48 GiB` / `~24 GiB` (regime map G11 row, `HANDOVER` §5.1,
`wp9-g11-plan.md` §7.3, `wp9-plan.md` §6.3), `2.83 GiB` (#13, CLAUDE.md),
`~6–9 GB` (#15) — traces to `sweeps/wp9/g11_probes/g11_probe_session1.py`.
That probe builds **`sweep_scenario` at N=8** and calls `run(...)` with **no
`window_sink` and no `window_slots`**. The campaign builds
**`build_g11_scenario` at N=4, windowed, with ledger eviction and a
retaining sink**. These are different runs. CLAUDE.md's own
measurement-carries-its-configuration rule, for the fourth time, and the
first three are in the same table.

**#15 is additionally wrong on its own terms.** Its "~6–9 GB" comes from the
largest worker of a 3-arm probe **observed mid-run and then killed** — a
lower bound on a partial run, quoted as a per-run requirement. The one
completed real-horizon measurement is `g11_horizon_battery.time`:
`Maximum resident set size 22,851,440 KB` with `Exit status: 137`, i.e.
**21.8 GiB and SIGKILLed at the 22 GiB threshold** — and that is the N=8
unwindowed probe, not the campaign either.

**Measured on the actual campaign path** (PF, N=4, `record_timeseries=True`,
`timeseries_resolution="second"`, `window_slots=240000`, one mode per
process because `ru_maxrss` is a high-water mark):

| horizon | windows | completions | sink DROPS | sink KEEPS |
|---|---|---|---|---|
| 240,000 | 1 | 1,047,766 | 468.9 MiB | 470.7 MiB |
| 480,000 | 2 | 2,095,774 | 519.8 MiB | 868.0 MiB |

At one window the sink fires once at the end and costs nothing; at two, one
window's completions are held while the next accumulates — **~348 bytes per
retained completion.** The driver side is nearly flat (~212 MiB/M-slot on a
~418 MiB intercept): commit 2's eviction works. **The sink was undoing it.**

**Extrapolated to 7,200,000 slots — stated as an extrapolation, from two
points:** driver ≈ **1.9 GB**, retained completions ≈ **10.6 GB**. So ~85 %
of a run was `run_one`'s `pending` dict.

**FIXED, and the fix is verified row-identical.** `run_one` now scores the
completion-family metrics inside the sink and releases the batch;
`windowed_metrics` grew a `families` selector so there is one code path, not
two spellings. Measured at 480,000 slots: **peak RSS 877.1 → 556.0 MiB, and
18 of 18 rows byte-identical.**

**The operative numbers now, and their configuration, in the same sentence:**
on the campaign path at N=4 with `record_timeseries=True` and the fold at
`"second"`, a 7.2 M-slot run should cost **≈2 GB**, extrapolated from
240k/480k measurements — which takes the affordable worker count within a
22 GB budget from ~1 to ~10. **This has not yet been measured at the real
horizon**, and it is the first thing the next real-horizon probe should
confirm, because it is itself an extrapolation and this row exists because
of one.

**A guard landed with it, and it fired on its first run** — which is the
point of adding it. `run_one` now compares the scenario's flow keys against
the record's, because the two metric families are scored against different
flow lists. It raised immediately on `ue1_qfi8` / `ue2_qfi85`: GT-7.1's
firmware push (T+600 s) and STOP drill (T+1200 s) generate nothing on a
120 s probe, so they never enter `record.flows`. That direction is benign
and the guard is now directional — record-only keys raise, scenario-only
keys are **emitted as `flows_declared_but_silent`**, because "a scripted
flow that generated nothing" is exactly the did-the-mechanism-fire question
and belongs in the artefact rather than in an assertion that stayed quiet.


---

## #18 — THE #8 CORRECTION OVER-SHOT (2026-09-03)

**A closed row reopened, and the reason is a failure class rather than a
detail.** #8 fixed a cadence exclusion that was too broad (`duty ≤ 0.5`,
discarding a real arm difference) by narrowing it to duty 0.1 and asserting
*"at duty 0.5 the period is 200 ms, the caveat does NOT fire"*.

**Measured over the committed `sweeps/wp9/part_c_rows.csv`: it fires on 4 of
44 duty-0.5 breaches**, observed medians 596.63 / 602.25 / 551.25 / 525.00 ms
against that 200 ms configured period.

**The single wrong step: the correction inferred the predicate's STATE from
the CONFIGURATION instead of reading the predicate's INPUT.** The predicate
is `median_gap_ms > T_live/4`; `median_gap_ms` is measured. A flow configured
at 200 ms that the network degrades to a 600 ms median trips it. The
exclusion is a property of each ROW, not of the `duty_cycle` axis.

**What survives:** #8's headline result. TwoTier's 503.25 ms / 5-of-10
against PF's 0-of-10 is real — those rows are not among the four.
**What withdraws:** the blanket claim that duty 0.5 is caveat-free.

**This is triage #22 from the other direction**, and together they are why
G3 cannot be scored honestly yet: the caveat silences real breaches on M03/
M20, the metric G3 binds to.

**Recorded as a new failure class** in `prediction-journal.md` — *an
over-correction is its own class, distinct from a stale claim and a wrong
claim, and it is the hardest to see because it reads as settled.* A stale
claim is suspected by anyone who checks the date; a wrong claim is
contradicted by the code; an over-correction arrives with a correction box
and a citation, so nobody checks it twice.

---

## #19 — THE TRANSFER MANIFEST WAS NEVER CHECKED, AND ALL THREE ITEMS WERE ABSENT (2026-09-04)

**Found by accident.** G6 could not be scored because
`scripts/g6_conjunction_table.py` reads
`sweeps/wp9/stage6_g6_n40_records.jsonl`, which was not present. Checking the
rest of `scripts/transfer_manifest.sh`'s `ITEMS` list showed **all three
missing**: `stage1/records.jsonl`, `stage4/records.jsonl`, and G6's.

**The manifest is not partly unsatisfied — it was entirely unsatisfied**, for
an unknown period, on a repo that has been producing results throughout.

**THE ROOT CAUSE IS THAT VERIFICATION WAS COUPLED TO A TRANSFER.** The script
had a `--verify` mode, but every mode required an ssh host
(`[ -z "$HOST" ] && exit 2`). So the only way to ask *"is the manifest
satisfied?"* was to ask it **of another machine**. The purely local
question — *is what should be here, here?* — had no way to be asked, which is
why nothing asked it.

**A manifest nothing checks is a list of intentions.**

**ROOT CAUSE, AS ITS OWN LINE — the local question had no way to be asked.**
Every mode of the script required an ssh host, so the only question it could
answer was *"does this machine's manifest match THAT machine's?"* The
question that actually matters day to day — **"is the manifest satisfied
HERE?"** — was not expressible, and an inexpressible question does not get
asked.

**This is the same shape as a metric with no red state.** M19 cannot report
a never-delivering flow as failing, so nobody reads M19 and concludes
failure; the manifest could not report itself unsatisfied on one host, so
nobody read it and concluded absence. In both cases the gap is not that the
check was skipped — it is that **the check had no way to produce the answer
that mattered**, so its silence was uninformative and looked like assent.

**The mechanical form:** when adding a verification, ask what OUTCOME it can
report. If it cannot report the failure you care about, it is not a check of
that failure, however often it runs.

**Fixed:** `./scripts/transfer_manifest.sh --local` needs no host, checks
existence **and size** (a zero-byte file passes `-e` and fails every
consumer — the same class as an empty output file being read as evidence
about a process), names the regenerator for each missing item, and **exits
non-zero** so it can gate a campaign.

### What is unreproducible until regenerated

| artefact | what it gates | status |
|---|---|---|
| `stage6_g6_n40_records.jsonl` | **G6's conjunction table** — the only input `g6_conjunction_table.py` reads | **regenerated 2026-09-04** (64.5 MB) by `g6_seed_extension.py` |
| `stage4/records.jsonl` | **C5-style bit-identity against stage 4**, and any re-scoring of the Category-2 fleet grid without re-running it | **still missing** |
| `stage1/records.jsonl` | any re-scoring of the axis-screening gate from records rather than from `stage1_rows.csv` | **still missing** |

**The rows CSVs survive** (`stage1_rows.csv`, `stage2_rows.csv`,
`stage6_g6_n40.csv`, `part_c_rows.csv`), so results already *scored* into
rows remain readable. What is lost is the ability to **re-score from
records** — to ask a new question of an old run without re-running it, which
is the entire reason `record_sink` exists.

**Note the asymmetry, because it decides priority:** stage 4's records gate a
bit-identity check that is a *verification*, so its absence weakens
confidence rather than invalidating a number. G6's gated a *result*, and its
absence made that result unscoreable outright.

---

## #20 — THE `scripts/` READ: NINE SCRIPTS ARE DEAD, AND FOUR GUARDS CANNOT FIRE (2026-09-04)

`docs/phase2-results.md` closed by naming `scripts/` as *"the least-tested
layer, 42 files, 14 of them named in any test"*, and said it had not been
read at all. This is that read.

**Two corrections to that sentence first, both derived rather than
restated.** There are **44** files, and **10** are imported by a test — the
"14 named" counts *mentions*, five of which are docstring references. A
docstring reference is not coverage, so the tested fraction was overstated
by half.

Nothing below changes a published number. Every item is either dead code, a
latent guard, or a defect whose triggering condition has not yet occurred —
and in one case the trigger is G12's own next step.

### 20.1 NINE SCRIPTS CANNOT RUN AT ALL

`TwoTier.__init__` stopped accepting `tier1_period_slots` at the Phase 2
rewrite. Eight scripts still construct it that way and raise `TypeError` on
their first scheduler:

`transient_check.py`, `compare_schedulers.py`, `ul_shadow_study.py`,
`plot_timeseries.py`, `demand_study.py`, `diagnose_finding2.py`
(4 sites, one also passing `enable_sps=False`, deleted with the SPS path),
`diagnose_finding3.py`.

`knapsack_diagnostic.py` fails one step earlier, at **import**:
`estimate_demand_bps` no longer exists in `scheduler/`.

**They import cleanly**, which is why nothing noticed: the constructor is
not called at import time, so every static check and every `python -c
"import x"` passes. Only running them fails.

### 20.2 `transient_check.py` REIMPLEMENTS THE SLOT LOOP, ~6 WPs STALE

Its own docstring says *"Mirror of sim.driver.run"*. It is the **only**
script that does this (swept across all 44). It still contains

    delivered = int(alloc.bytes_capacity * (1.0 - bler))

— the fractional HARQ discount CLAUDE.md forbids reintroducing, and which
WP5 found was *"the dominant driver of the pre-4a/post-4a latency-metric
drift"*. Checked before asserting it: the other nine `(1 - bler)` sites in
the tree are schedulers computing an **expected rate for ranking**, which is
legitimate and is not what the rule governs. This is the only surviving
instance of the forbidden **delivery** model.

It also has no HARQ, no BSR, no UL access chain, no join/RLF, no message
ledger and no CQI delay. **Its conclusion — whether 4,000 slots is steady
state — was measured on a different simulator than the one that produces
results**, and is cited at `docs/phase1-triage.md:65`.

### 20.3 FOUR GUARDS THAT CANNOT FIRE AGAINST THE FAILURE THEY NAME

| where | the guard | why it cannot fire |
|---|---|---|
| `g10_admissible.py` | *"every cell selection asserts its expected size, so an empty or short selection cannot be silently summed"* | the expected size is `n_seeds = max(len(v) for v in by.values())` — **derived from the data it checks**. A uniformly short slice sets its own bar and passes. It catches ragged cells, never uniform shortfall. Verified harmless today: all 18 cells really are 10 rows. |
| `g11_score.py` | C1's `pass_rate` | `unscoreable` windows land in the denominator and not in `fails`, so **a window that could not be judged counts as a passing window**. Verified harmless today: `unscoreable=0` on the real data, so C1 = 1.000 is clean. |
| `g11_score.py` | `n_expected`, `memory_guard_tripped` | both are read from the campaign JSON, placed in the output, and **never compared to anything**. `g9_campaign.py` refuses to score and exits non-zero on a count mismatch; G11's scorer has the same inputs and does not. |
| `g11_score.py` | C3's CoV | emitted at `n_seeds=3` with no marker, though GT-7.4 requires ≥5. Phase 2's table says "not scoreable" — that judgement came from a human reading the plan, not from the scorer, which produces a quotable number below its own bar. |

### 20.4 `wp9_gate.py` SILENTLY OMITS ONE AXIS — CONFIRMED IN THE COMMITTED ARTEFACT

`select_for_stage_2`'s docstring: *"every axis that did not make it is
returned by name and score. **Nothing is silently omitted.**"*

    for v in excursions[len(qualifying[:1]):] if v.axis not in promoted

The slice is taken on the **unsorted** `excursions` list by the *count* of
promoted axes, so it always discards `excursions[0]` — whether or not that
element is the promoted one. Reproduced directly: three excursion axes, the
second qualifying, and the first is reported neither as promoted nor as
dropped.

**Checked against the committed artefacts, and it happened.** Both
`gate_verdict.txt` and `gate_verdict_corrected.txt` list 12 axes, 2 core,
1 promoted excursion — so 9 axes should appear under `dropped:`. Both list
**8**. The missing axis in both is **`min_rb`**, which scored **152.579**,
among the highest non-`inf` scores in the grid.

**Why this one matters beyond the accounting.** `docs/wp9-regime-map.md`
§0.3 records that `min_rb` "separated the arms strongly (score 152.579)" and
that "the cap dropped it from stage 2" — a deliberate budget decision. The
committed record of that decision **does not contain it**, because the code
that writes the record dropped it by an off-by-one. The conclusion is
unaffected; the evidence for it is not what it claims to be.

### 20.5 A FIX APPLIED AT ONE OF FIVE SITES IN ITS OWN FILE

`g12_score.py` already carries a recorded self-violation (§36.6: it cites
the decompose rule in its docstring and pooled a minimum across arms). The
corrective pass searched the file for that shape — the right move — and
**fixed one of five aggregation sites.**

| line | aggregates | keyed on |
|---|---|---|
| 192 (E2) | two-element order counts | **(cell, arm)** — fixed |
| 238 (E3) | telemetry M02, first-degradation point | arm only, **pools cells** |
| 276 (E4) | bg throughput at first GBR breach | **pools cells AND arms** |
| 296 (E5) | full-ramp orders by arm | arm only, **pools cells** |
| 314 (promotion bar) | canonical orders by arm | arm only, **pools cells** |

E2's own comment states the rule and its trigger: keying on arm alone is
*"harmless while the grid has one scoreable cell and **silently wrong the
moment it has two**."* Phase 2 completed exactly one cell, so nothing is
wrong today — **and running the remaining cells is an open thread on G12's
row.** The moment a second cell scores, E3's degradation point, E4's median,
E5's arm comparison and the promotion bar's `arms_differ_canonical` all
become mixtures quoted as single statements, and the last of those is a
published verdict about whether an arm difference is a scheduler property.

E4 is the sharpest: it pools both axes into one median, and the arms are
known to reach first breach at very different loads — TwoTier from nominal
on 9/10 seeds, PF and Reservation from 102 % of ceiling.

**This is the fix-at-the-category rule at the smallest scale it can occur** —
not across guarantees or scripts, but across five loops in one file, during
a review that went looking for exactly that shape.

### 20.6 THE MEAN-OF-RATIOS VERDICT, TWICE

`g6_fleet_restricted_m03.py:120` and `g6_conjunction_table.py:180` both
compute `PASS if ci["hi"] <= 0.20` from the bootstrap CI of the **mean of
ratios**, while printing median and IQR beside it. The reporting rule
(§27.1's *"median and quartiles beside the mean, never the mean alone"*) is
honoured in the **display** and violated in the **verdict** — on the exact
statistic where the mean read **+136.84 %** and the median **−0.22 %**.

`g6_fleet_restricted_m03.py` additionally drops pairs silently
(`if b is None or e is None or b == 0: continue`) with no expected-count
assertion; a base cell with a zero gap is a specific kind of run, so the
survivors are self-selected.

### 20.7 THE SIBLING THAT DID NOT GET THE FIX

Defect #19 fixed `g6_fleet_restricted_m03.py`'s silent default to an
uncommittable 1.8 GB input: `--records` is now required and names both real
sources. **`g6_conjunction_table.py` reads the same class of file from a
hardcoded module constant** —
`RECORDS = "sweeps/wp9/stage6_g6_n40_records.jsonl"`, gitignored, absent
from any clone, no CLI override, no existence check, resolved relative to
the CWD. Swept: it is the only other script with this shape.

### 20.8 SMALLER, RECORDED WITHOUT ELABORATION

- **`g6_fleet_restricted_m03.py` runs its whole analysis at import time** —
  `parse_args()` and the full body at module scope, no `__main__` guard.
  Scanned all 44: the only one with real top-level calls.
- **`g6_conjunction_table.py` leaks a loop variable**: `bs` is read after
  the `for k in pairs` loop to report a status, so it reports the *last
  seed's* status as the arm's, and raises `NameError` if `pairs` is empty.
- **`blackout_frequency.py`** prints `len(hit)/len(sel) if sel else 0` — an
  empty cell reads as a **0.00 % blackout rate**, i.e. as a clean pass. The
  `runs` column exposes it, but the rate is the quotable number.
- **`wp9_gate.py` skips a level with no rows** (`if not cell_rows: continue`)
  and never reports per-axis row counts, so an axis whose cells never ran is
  indistinguishable from one that ran and lost. The gate's own docstring
  says it exists to kill the opposite error — cells selecting **too many**
  rows — and starvation was not covered.
- **Five hand-rolled pools do not pin worker threads**:
  `blackout_frequency.py`, `g10_rerun.py`, `g11_campaign.py`,
  `wp9_sweep.py`, `wp9_part_c.py` predate `regime_sweep.run_cells` and keep
  their own `mp.Pool`. `scripts/parallel_audit.py` reports which mechanism
  each uses, so this is visible rather than hidden — but converting them is
  unfinished work, and CLAUDE.md's claim that `run_cells` carries the four
  lessons "so a new runner cannot lose them" applies to new runners only.

### 20.9 WHAT THE READ COVERED

~20 files read line by line; **all 44 swept mechanically** for nine specific
shapes: slot-loop reimplementation, stale `TwoTier` construction, CSV
boundary coercion, mean-CI verdicts, hardcoded uncommittable inputs,
module-level side effects, thread pinning, empty-selection rates, and
expected-count assertions. The nine dead scripts (20.1) were not read
further — establishing that they cannot run is the more useful fact, and
reading a script that raises on its first scheduler tells you about a
simulator that no longer exists.

**The four stage analysers all coerce at the CSV boundary** (`_coerce` /
`coerce` in `analyse_stage2/3/6`, five sites in `analyse_stage5`), so
defect #1's string/bool fix propagated correctly. That is the one place in
this read where a fix reached every site it needed to.
