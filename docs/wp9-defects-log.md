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

---

## #21 — THE NINE DEAD SCRIPTS: TWO FIXED, SEVEN DELETED (2026-09-04)

#20.1 established that nine scripts could not run. Decided per script, because
"fix" and "delete" are not interchangeable here: **seven of them cannot be
repaired without changing what they measure.**

`TwoTier.__init__` stopped accepting `tier1_period_slots` at the Phase 2
rewrite, and `2000` was the STALE value in the first place — it encoded
`ia_p5g_scheduler.h`'s doc-commented 1.0 s against the deployed 0.1 s macro
(CLAUDE.md). So "fixing" one of these means pointing it at a **different
scheduler** from the one whose finding it documents. The repaired script
would produce a new measurement wearing an old name, which is worse than no
script: the finding it records lives in the docs, and a runnable file beside
it invites someone to re-run it and believe the output.

### FIXED (2)

| script | what was wrong | why fix rather than delete |
|---|---|---|
| `plot_timeseries.py` | `TwoTier(tier1_period_slots=2000)` | a plotting utility, not a finding. It has no result to invalidate, and construction is its only stale part — now `load_two_tier(_TT_CONFIG, min_rb=5)`. |
| `g6_fleet_restricted_m03.py` | ran its whole analysis at **import time** — `parse_args()` and the body at module scope (#20.8), so importing it parsed `sys.argv` | it is G6's decisive falsifier and still the right instrument. Wrapped in `main()`. |

### DELETED (7)

`compare_schedulers.py`, `demand_study.py`, `diagnose_finding2.py`,
`diagnose_finding3.py`, `knapsack_diagnostic.py`, `transient_check.py`,
`ul_shadow_study.py`.

Each is a Phase 1-era diagnostic whose finding is recorded in `docs/`, and
each would need a rewrite rather than a repair:

- **`transient_check.py`** also **reimplemented the slot loop** and still
  applied `bytes_capacity * (1 - bler)` as its delivery model — the
  fractional HARQ discount CLAUDE.md forbids reintroducing (#20.2). Its
  question ("is 4,000 slots steady state?") is re-askable with
  `wp9_window.py` on `driver.run` output; the answer it gave was measured on
  a simulator six work packages behind.
- **`ul_shadow_study.py`** studied `_shadow_lcp_split`, which CLAUDE.md names
  as a known modeling error not to extend and which Phase 2 deleted.
- **`demand_study.py`** asked how Tier-1 gets demand without ground truth;
  Phase 2 answered it by porting `_compute_demand_bps` from the C.
- **`diagnose_finding2.py`** passed `enable_sps=False`, a mechanism deleted
  with the SPS path.

**`knapsack_diagnostic.py` is the one deletion with an external cost, and it
is deliberate.** README §8 carries an `[OPEN: PHASE2]` item: `paper/main.tex`'s
knapsack section rests on `solve_tier1` being lexicographic, ground truth has
no such structure, and whether the fixed `IA_P5G_TIER1_GBR_PENALTY` still
produces knapsack-shaped allocations under the single-phase form is **open
and empirically answerable**. That script was the instrument for the OLD
formulation. **Repairing its imports would let it answer the old question
against a scheduler that no longer exists and report it as an answer to the
new one** — so the code goes and the question stays. README's entry is
updated from "no longer runs" (which implies revival) to "removed; the
instrument for the new formulation has to be built".

### THE STRUCTURAL FIX, so the class cannot recur silently

**Every one of these imported cleanly** — a constructor is not called at
import time — so nothing static noticed and nothing dynamic ran them. They
sat dead for a whole phase.

`scripts/parallel_audit.py --check` now also reports **DEAD CALLS**: for
every call to a name imported from `sim`/`scheduler`, it compares the
keyword arguments against the callee's live signature, and flags a
`from <module> import NAME` whose NAME has vanished. Verified to bind by
restoring one deleted script and re-running:

```
_deadcheck_probe.py   TwoTier(..., tier1_period_slots=...) at line 34: no such parameter
_deadcheck_probe.py   TwoTier(..., enable_sps=...) at line 138: no such parameter
```

Import-checking alone would have passed all nine. The signature comparison
is what makes the check able to fail.

### AND TWO DEFECTS FROM #20 FIXED WHILE HERE

- **#20.6, the mean-of-ratios verdict**, in both `g6_fleet_restricted_m03.py`
  and `g6_conjunction_table.py`. `regime_sweep.bootstrap_ci` gained
  `statistic="median"` — **default unchanged and the mean path bit-identical**,
  with the new `statistic` key emitted ONLY on the non-default path, because
  these dicts are serialised straight into committed artefacts and adding a
  field on the default path would change every one of them.

  **THE ESTIMATOR CHANGE MOVES A VERDICT, so it is shown rather than
  substituted.** On the n=40 G6 records, TwoTier's all-flow row reads
  **MEDIAN −0.85 % PASS** where the mean gives **+30.24 % [−0.21, +68.79]
  INCONCLUSIVE**. Both are printed and the row is marked `!= mean:INCONCLUSIVE`
  when they disagree. Silently swapping one answer for another would have
  been the same move as quoting the mean alone, in the other direction — the
  disagreement between the estimators is the finding.
- **#20.7, the sibling that did not get #19's fix.**
  `g6_conjunction_table.py` now takes `--records`, checks existence, and
  names the regenerator, instead of reading a gitignored 251 MB path from a
  module constant.


---

## #22 — A PUBLISHED ROW CONTRADICTED BY ITS OWN SOURCE FILE (2026-09-04)

**Its own class, and not one already in this log.** Every earlier entry is a
wrong *inference* from data, a *stale count*, an *empty selection*, or a
*check that could not fire*. This is none of those: **the data was correct,
on disk, and the row summarising it was never read back against it.**

### The instance

`docs/phase2-results.md`'s G8 row read *"M22 starvation epochs … **0 on all
arms** at the core cell."* Its source, `sweeps/phase2/core_mfbr.json` (n=3):

| seed | arm | M22 all-flow | M22 protected | longest |
|---|---|---|---|---|
| 1826701614 | all three | 0 | 0 | 0.0 s |
| 1367864806 | all three | 0 | 0 | 0.0 s |
| **1097657231** | **Reservation** | **3** | **2** | **10.0 s** |

**One seed of three shows a flow starved for ten seconds against a one-second
bar**, in the file the row was written from.

**Three defects in one row, and they compound:**

1. **A claim contradicted by its source** — "0 on all arms" against 3 epochs.
2. **Two source files presented as one run.** Traced by arithmetic: G8's
   figures reconcile to `core_mfbr.json`, and G1's TwoTier 94.51 ms
   reconciles to `core_fixed.json` — *a different run*, pre-MFBR. The two
   rows sit in one table implying one campaign.
3. **Mixed estimators inside one metric.** *"PF 0.9995 / Reservation 0.9998 /
   TwoTier 0.9654"*: TwoTier's is the 3-seed mean, Reservation's mean is
   **0.9719** — 0.9998 is seed 1 alone. A single-seed value and a mean, side
   by side, unmarked.

**None of it is a code defect.** Re-run at the published configuration on
current code, the published numbers reproduce. The simulator was right and
the row was wrong.

### Why the existing checks could not catch it

`--check` compares `RunRecord`s, not documents. The panel's rules govern how
a metric is *computed*, not how it is *quoted*. `regime_map_rollup.py` checks
one derived sentence against its own table. **Nothing in this project reads a
published figure back against the artefact it claims to summarise** — the
gap is between the JSON and the prose, and every guard sits on one side of
it.

### THE CHECK THAT WOULD CATCH IT — PROPOSED, NOT BUILT

Two parts, and the first is most of the value:

**1. Every quoted figure names its artefact and its n.** A row becomes
`M22 epochs 0/9 (core_mfbr.json, n=3, h=40k)` rather than "0 on all arms".
This is a documentation convention, costs a phrase, and would have made the
mixed sources visible on sight — G1 and G8 citing different files in adjacent
rows is obvious once the files are named. The provenance table now at the top
of `docs/verification-2026-09-04.md` is this part, applied by hand, and it
immediately exposed a second inconsistency nobody intended: G3 and G5 are
read at h=20,000 while G1 and G8 are read at h=40,000.

**2. A script re-derives the row from the artefact it names.** Parse the
citations out of the markdown, load each artefact, recompute the quoted
statistic, and diff. Roughly: a `figure` inline convention the parser can
find, a small registry mapping metric ids to how they are summarised
(median / mean / count-of-seeds), and a `--check` mode that exits non-zero on
a mismatch. **It is the same shape as `regime_map_rollup.py`**, which already
does this for one sentence, generalised to figures — so the pattern is
established and the cost is bounded.

**What it must NOT do**, on this log's own evidence: silently pick an
estimator. If a row says "0.9654" and the artefact's median is 0.9166 and its
mean 0.9654, the checker reports **which** matches rather than accepting the
first that does — a checker that accepts any estimator would have passed this
row unchanged.

**BUILT 2026-09-05** — `scripts/verify_claims.py` + `config/published_claims.yml`,
after the verification pass closed, so the pass's own numbers are not its
only test case.

**Its failing case is kept as a claim, and it demonstrates why the estimator
constraint is the whole design.** The pre-correction G8 row is entry
`G8.M22.PRE_CORRECTION`, and the checker reports:

```
FAIL   G8.M22.PRE_CORRECTION   max=2 quoted=0  (9 values, core_mfbr.json)
       but these DO match the quoted value: median, min
       -- the figure is a different statistic from the one declared
```

**The protected-fleet M22 values across the three seeds are `[0, 0, 2]`.** The
claim *"0 on all arms"* is a claim about the **max**, which is 2 — but the
**median and the min are both 0**. A checker that accepted "some estimator
matches" would have **passed the exact row it was built to catch**. That is
why it reports which estimators match and fails unless the declared one does,
and why `sim/tests/test_verify_claims.py` pins that behaviour rather than
only pinning the pass/fail.

The checker also refuses an empty selection, a missing artefact and an
unknown statistic, and its statistic vocabulary is a small named table rather
than an expression evaluator — a checker that can compute anything can match
anything, and stops being a check.


---

## #23 — SCRIPTED EVENTS PINNED TO ABSOLUTE TIME SILENTLY NO-OP AT A SHORTER HORIZON (2026-09-05)

Found pricing G11's soak: a 3,200,000-slot run aborted on all three arms with
*"the STOP flow `ue2_qfi85` is absent from the record — it generated nothing
at all, so GT-7.1's drill never happened."* The message was true and the run
was fine.

### The three defects, in order of consequence

**1. THE SCENARIO BUILT HAPPILY WITHOUT ITS OWN SCRIPTED EVENTS.** GT-7.1
places the firmware push at T+10 min and the STOP drill at T+20 min, both
absolute because the guarantee states them that way. `build_g11_scenario`
accepted any horizon and simply produced a scenario without whichever events
fell outside it. **Every C1 result to date was produced at 400,000 slots
(100 s), where THREE of the four scripted ingredients are absent** — no
firmware window, no STOP drill, no waypoint pause, only the teleop duty
cycle. Nothing raised, because `assert_schedule_fired` correctly has nothing
to assert about an event the horizon cannot contain.

**Fixed at CONSTRUCTION, not at scoring:** `build_g11_scenario` now refuses a
horizon below `minimum_horizon_slots()` (derived from the schedule, 4,800,080
slots) unless the caller passes `allow_partial_schedule=True`.
`scripted_ingredients_present()` reports which four it actually has. **The
flag is the point, not an escape hatch** — a short run is legitimate, and
passing the flag is the caller saying so. **A drill rescaled to fit a short
run would not be GT-7.1's drill, so rescaling is deliberately not offered.**

**2. AN ASSERTION ABOUT ONE INGREDIENT FIRING ON ANOTHER'S EXPECTATION.**
`assert_schedule_fired` early-returned only when **both** the STOP and
firmware counts were zero, then checked the STOP flow unconditionally. Any
horizon in **[660 s, 1200 s)** — firmware expected, STOP not — aborted on an
event the horizon cannot contain. That is what killed the 3.2 M battery
point. Each ingredient is now gated on its own count.

**3. A SCRIPTED WINDOW THAT STARTS AFTER IT ENDS.** `teleop.windows()`
returns one window past the horizon by construction (`n = h // period + 1`),
so clipping the last OFF interval produced **(812.0, 800.0)**. Benign
downstream and wrong to emit: a partition of the run into quiescent-vs-event
intervals cannot contain an interval outside the run. Inverted windows are
now dropped.

### THE CATEGORY QUESTION — what else is pinned to absolute time

Asked of the whole scenario layer, since the shape is *"a schedule sized for
one horizon, run at another"*.

| scenario | scheduled events | clipped to horizon? |
|---|---|---|
| `g11.py` | firmware T+600 s, STOP T+1200 s | **was not** — fixed above |
| **`g9.py` `gt61_warm_rejoin`** | **10 cycles from slot 2000, period 1600** | **NO** |
| **`g9.py` `gt62_cold_attach`** | **5 cycles from slot 2000, period 3000** | **NO** |
| **`g9.py` `gt63_rlf_recovery`** | **fade from slot 4000, 12000 slots long** | **NO** |
| `g12.py` | none — the ramp is one load per run, no mid-run schedule | n/a |

**Measured:** `gt61_warm_rejoin` at h=8,000 places **6 of its 10 events
beyond the horizon**, and at h=4,000, **8 of 10**. `gt63_rlf_recovery` at
h=4,000 has its entire fade outside the run.

**And `g9_campaign.expected_event_count` does not clip either** — it returns
`sum(1 for e in joiner.join.events if e.kind in kinds)`, all of them, so the
count guard would compare recorded events against a number the horizon cannot
reach. **At G9's designed horizon (20,000) all events fit, so no published G9
result is affected** — the defect is **latent**, and G9's actual abort
(*"2 'warm' events but the scenario schedules 10"*) is a genuine finding at
the correct horizon, not this.

**FIXED AT THE CATEGORY, 2026-09-05.** `sim/scenarios/schedule_guard.py`
holds one `require_horizon()` for every scenario that pins events to
absolute time; g9's three builders and `g9_campaign.expected_event_count`
are wired to it, and `sim/tests/test_schedule_guard.py` **derives the set of
schedule-owning builders from the AST** (`-> ScenarioConfig` + a
`horizon_slots` parameter) and fails when a NEW one does not guard. That
last test is what makes a fifth instance loud instead of silent -- this
answer sat written down here, naming four sites, for eight weeks while the
fix stayed at one.

**And the count guard's failure is the OPPOSITE direction, which is why it
needed its own note.** A scenario whose events fall past the horizon reports
FEWER events than scheduled; `expected_event_count`, unclipped, returned the
FULL scheduled count -- so the guard compared a real count against a number
the horizon could not reach and **refused to score at all**. That is the
safe direction to fail in, and it may well be why G9 aborted rather than
publishing a partial run -- but *"the guard is unsatisfiable"* and *"the arm
is degenerate"* are different diagnoses and the abort message could not tell
them apart.

### The shape worth carrying

**A schedule expressed in absolute time is a claim about the horizon**, and
nothing checked that claim. The guards downstream were all correct: they
asserted what the horizon could contain, which is right, and therefore could
not notice that the horizon could contain almost none of it. **The check has
to be at construction, where the two are compared, not at scoring, where only
one of them is present.**

---

## #24 — THE PER-LCG BSR ARRAY HAS THE SAME COLD-START DEADLOCK THE SCALAR HAD, AND TWO RANKING TIERS READ IT (2026-09-05)

**Logged and parked.** Found while isolating G5's lever
(`docs/g5-lever-2026-09-05.md`); it does not make that answer wrong, so it is
recorded here rather than chased.

### The instance

`scheduler/reservation.py::_ul_gbr_and_pdb` is gated per-LCG on
`estimated_ul_buffer_per_lcg > 0` (`gNB_scheduler_ulsch.c:2230`, ported
faithfully). If no LCG passes that gate, the method returns its seeds —
`has_gbr=False` and `best_remaining_pdb=9999` — and the candidate enters the
sort with **tiers 2 and 3 both at their no-information values**.

Measured on `sweep_scenario(seed=1097657231, n_ues=8, horizon 40,000)`, by
wrapping the real method and calling it:

| ue | candidate evaluations | all per-LCG estimates == 0 | any `bytes_reported` > 0 |
|---|---|---|---|
| 1–5 | ~30,900 | **1 (0.0 %)** | 100 % |
| 6–7 | ~30,950 | 31 (0.1 %) | 100 % |
| **8** | **9,216** | **9,216 (100.0 %)** | **9,216 (100.0 %)** |

**ue8 is eligible on every one of its slots and carries no QoS state on every
one of them.** It is never once `has_gbr=True`, and its `pdb_ms` is never
anything but 9999. Not populated-then-collapsed — **never populated**.

### Why it is its own entry

CLAUDE.md already records that the scalar `estimated_ul_buffer` and the
per-LCG array *legitimately desync between BSRs* — that is faithful to ground
truth and is not the defect. CLAUDE.md also records the cold-start deadlock
for `bytes_reported`, and `sim/ul_access.py` was built to break it: SR on
PUCCH → `sr-ProhibitTimer` → grant → BSR.

**`UlAccessModel` arms the scalar. It does not arm the per-LCG array.** And
two of Reservation's four UL ranking tiers read the array, not the scalar. So
a UE that loses early grants never gets the BSR that would populate the
array, and without the array it ranks below every UE that has one — a
positive-feedback lock-in on a quantity nothing in the SR path re-arms.

This is the *same* deadlock the project already fixed once, one field over,
reached through a different consumer. The fix that closed it for eligibility
does not reach ranking.

### What it would take, and why it is parked

A real fix is a new mechanism (what re-arms the per-LCG array without a
grant?), not a bug fix — its own commit, its own regression diff, under the
one-fidelity-change-per-commit rule. It also needs the ground-truth question
asked first: **does real hardware exhibit this, or does something in the C
that this port omits keep the array warm?** That is an
`oai-branches/`-plus-full-checkout question, not a Python one.

### The shape worth carrying

**A deadlock fixed for one consumer of a field is not fixed for another
consumer of a different field that shares its cause.** The SR path was
verified against UL *throughput* — the symptom `bytes_reported` produces.
Nothing checked the array, because nothing had yet asked which fields the
*ranking* reads. The cheap check is the one this campaign happened to run:
for any field a scheduler reads, ask what writes it and whether that writer
can be reached from a starved state.

---

## #25 — A DESIGNED REMEDY GATED ON THE CONDITION WHOSE ABSENCE DEFINES THE FAULT (2026-09-05)

**In the deployed C, not only in this port.** The follow-up to #24, and the
reason #24 is a product finding rather than a porting question.

### The instance

`ia_p5g_scheduler.c`'s Tier-1.5 UL service-interval floor exists specifically
to rescue a UE whose `estimated_ul_buffer_per_lcg[]` reads 0. Its own comment
(:2119-2135) states the fault and the cure:

> *"A floor-fired UE is in the fault state where BOTH composite inputs are
> gated on `estimated_ul_buffer_per_lcg[] > 0`, which reads 0 by definition
> of the fault… under Tier 2 it would sort dead last… It only needs to land
> ONCE: the resulting BSR… repopulates `estimated_ul_buffer_per_lcg[]`."*

Its arming gate (:2325) is:

```c
if (_fl && sched_ctrl->has_pending_gbr && !_intr) {
```

`has_pending_gbr` is written **only** by `update_ul_qos_priority`
(`gNB_scheduler_ulsch.c:41-70`), inside a loop that `continue`s past every
LCG whose per-LCG estimate is ≤ 0. **So the rescue for "the array reads 0" is
gated on a flag that is false exactly when the array reads 0.**

Measured in the faithful port: the floor is evaluated **32,000 times per UE
per run** and fires **0 times** for the three UEs that receive **0 UL grants
in 40,000 slots**. The one firing observed across two seeds landed on a UE
that already had 19,805 grants.

### Why it is its own entry rather than part of #24

#24 is a **gate** that produces a fault state. This is a **remedy** that
cannot reach it. They have different fixes and, more importantly, different
evidential status: #24 could plausibly have been a port artefact until the C
was read; this one is visible in the C's own source with the C's own comment
explaining what it was supposed to do.

### The shape worth carrying: A FIX THAT REMOVES *SOME* OF THE CIRCULAR INPUTS

The C's v2 comment is the transferable part — it shows the trap being
half-escaped:

> *"v2 … Deficit read for TELEMETRY ONLY … it is NOT an arming input. v1
> armed on (B>0 || deficit>0 || vq>0), all estimate-derived: B==0 defines
> the fault and vq_ul stops updating once the per-LCG estimate reads 0, so
> arming rested entirely on the deficit staying non-zero…"*

**v2 correctly identified that arming must not depend on estimate-derived
state, removed three such inputs, and left a fourth standing in the `if`.**
The author was reasoning about the *body* of the arming logic and did not
re-examine the *guard* around it.

**Mechanically:** when a mechanism exists to escape a degenerate state,
enumerate **every** predicate on the path to it — the guard as well as the
body — and check each against the degenerate state. A partial escape is
indistinguishable from a working one in any test where the state is
constructed rather than reached, which is `sim/tests/`'s own recorded failure
mode (§19's fixture-built precondition).

### Parked, deliberately

Fixing this is a **behaviour change to a ported scheduler against ground
truth** — the port currently reproduces the C exactly, including the dead
gate. Changing it would make this simulator diverge from the deployed system
in the direction of being better, which is the opposite of what this port is
for. The finding is the deliverable; any change belongs in a conversation
with whoever owns `ia_p5g_scheduler.c`.

---

## #26 — `summary` CARRIES LIVE OBJECTS, SO TWO IDENTICAL RUNS COMPARE UNEQUAL (2026-09-05)

**Found because a bit-identity test failed against itself.** Model C's first
acceptance test compared `json.dumps(summary, sort_keys=True, default=str)`
for a run with the feature off against one with it explicitly disabled. It
failed — and so did the same comparison between **two byte-identical calls
with no feature at all**.

`summary` holds `_ue_lcp` and `_message_ledger`, which are live objects.
`default=str` stringifies them via `repr()`, which embeds a memory address.
So the serialised summary differs between runs for reasons that have nothing
to do with the run.

### Why it belongs in this log rather than being fixed in passing

**This is the `default=` serialization-fallback trap CLAUDE.md already
records for `RunLedger.bank()`, one layer over.** There, `default=str`
turned `RunRecord`s into their `repr()` — *"valid JSON, silently wrong"*.
Here it turns object identity into apparent nondeterminism. Same root:
**a serialization fallback converts an unserializable value into a
plausible-looking wrong one.**

The difference is the direction of the failure, and this one is the kinder
of the two. `bank()`'s version produced an artefact that *looked complete*
and had to be caught by kill-and-resume identity. This version fails
**loudly and immediately** — the test could not pass, so it could not
silently check nothing.

### The fix used, and the one not made

The test compares `RunRecord.to_dict()` instead, which is what
`test_grant_trace.py` already did — the correct comparison surface, since
`RunRecord` is what every artefact in this project is built from and
`from_summary` drops these keys anyway.

**Not fixed: `summary` itself.** Removing the live objects would move
whatever else reads them, and this experiment is not the place. But **any
future check that serialises `summary` for equality is broken before it is
written**, and that is the transferable part.

---

## #27 — M07 UNDER A STAGGERED ARRIVAL MEASURES THE STAGGER, NOT THE SCHEDULER (2026-09-05)

**Logged and parked; no result rests on it.** Found scoring outcome A6 of
`docs/attach-path-map.md`.

M07 is the fraction of GBR flows meeting GFBR **over the whole horizon**. Under
a staggered attach, a UE that arrives at slot 3,000 of 20,000 generates no
traffic for 15 % of the window, so its run-average throughput misses GFBR for
a reason that is not a scheduling outcome.

**What identifies it as an artefact rather than a result: PF shows it too, and
worse.** At N=16 under `stagger_seed`, M07 is PF **0.062**, Reservation 0.125,
TwoTier 0.125 — while PF starves nobody in any condition and its M08 is
healthy. A statistic on which the arm with no lock-in performs *worst* is not
measuring the lock-in. The dose-response confirms it: M07 is 1.000 at N=2
(200-slot stagger), 0.500 at N=4, ~0.1 at N=16.

### Why this is worth its own entry

It is the **decompose-before-attributing** rule arriving through a new door.
Every previous instance was an aggregate summed over the wrong *rows*; this
one is summed over the wrong *interval*. The check is the same — name the
window the statistic integrates over and the window the claim is about — and
it had not previously been applied to time.

**Consequence for the campaign:** any M07 comparison across conditions that
change when a flow is active needs pre-attach time excluded, or it compares
arrival schedules. `Scorecard` has no such exclusion today.

---

## #28 — `FlowRecord.key` OMITS DIRECTION, so one UE cannot carry the same 5QI both ways (2026-09-05)

**Found building G2's UL/DL STOP pair.** `FlowRecord.key` is
`flow_key(ue_id, qfi)` (`sim/run_record.py:154`) — **no direction**. So a UE
configured with the same QFI in both directions produces **one** record, and
the other flow vanishes.

**Measured, not inferred:** with a UL 5QI-85 flow added beside the existing DL
5QI-85 one on the same UE, `rec.flows` contained `ue1_qfi85` and `ue2_qfi85`
**as UL only** — the DL flows were absent entirely, and every DL statistic
read `None`. A control that silently disappears is worse than one that fails.

**Why it has not bitten before:** every existing scenario assigns each 5QI to
one direction, which is the `one DRB per QFI` convention CLAUDE.md records.
The collision is only reachable by deliberately pairing directions.

**Worked around, not fixed:** G2's UL STOP uses **5QI 86**, which carries the
**same standardised 5 ms PDB** as 85 in `scheduler/flow.py::FIVE_QI_PDB_MS`,
so the pair stays comparable and the PDB is still derived rather than
authored.

**Not fixed because the fix is not obviously right.** Adding direction to the
key changes every artefact's flow identifiers and every consumer that parses
them. And the model may be correct as-is: a DRB is directional in 5G, so
"the same 5QI both ways on one UE" is arguably two DRBs and should be two
QFIs. **The finding is that the schema enforces that silently rather than
loudly** — a scenario that violates it loses flows with no error.

**Cheap guard if this is taken up:** `RunRecord.from_summary` could assert
that `len(set(flow keys)) == len(flow_configs)`, which would have turned a
silent disappearance into an immediate failure.

---

## #29 — THE POPULATION DEFECT, THIRD INSTANCE, AND THIS TIME IN A DENOMINATOR (2026-09-06)

**The class: a ratio whose denominator includes capacity that cannot
contribute.** Two instances were about rows; this one is about slots, and it
is the same shape.

| instance | the statistic ranged over | what could not contribute |
|---|---|---|
| M03's worst liveness gap | **every flow** | a saturating background aggressor the scheduler starves **by design** |
| M02's PDB-violation rate | **every flow**, byte-weighted | the aggressor's own bytes |
| **#29 — CCE utilisation** | **every slot's budget** | **D-slot budget an uplink-only workload can never spend** |

### The arithmetic

`DSUUU`, per-slot PDCCH budgets **D=48, S=16, U=32** → 160 per period. A
workload with no downlink flows can spend only **S + U = 112**. So **30 % of
the denominator was unreachable and the ceiling was 0.70, not 1.0.**

**Same measured number, opposite conclusion.** `0.6357` against 1.0 reads
*"loaded, not bound"* — which is what `docs/sensor-dense-result-2026-09-05.md`
said. Against 0.70 it reads **90.8 % of achievable**, and the control channel
binds.

### WHY NO GUARD CAUGHT IT, and this bounds what the guards protect

- **`verify_claims`** confirms a figure matches its cited artefact. **It did.**
- **`regression_corpus --check`** compares against a baseline computed the
  same way. **No drift, because the same denominator was on both sides.**
- **`parallel_audit`** and the suite are orthogonal.

**All four passed on a wrong conclusion, because the arithmetic was right and
only the denominator's MEANING was wrong.** No guard asks *is this the right
denominator*, and **none can** — that is a modelling judgement, not a
property of the code.

**What caught it was being pushed to sweep the UE count**, which forced a
re-derivation of the ceiling. **It was not caught by a rule**, and saying so
is the honest bound on what this project's guards are for.

### THE SECOND LESSON, and it may be the more useful one

**2,308 slots were at the per-slot cap, and that was in the data the whole
time.** An aggregate ratio cannot show binding: a channel saturated on 2,308
slots and idle otherwise averages to something comfortable.

> **Binding is a property of the worst slot, not the average one.**

### What was added

1. **`cce_utilization_by_slot_kind`** — D/S/U separately, so the aggregate is
   interpretable without any ceiling arithmetic. On sensor_dense: **D 0.7 %,
   S 81.5 %, U 92.2 %** against an aggregate of 0.637.
2. **`cce_slots_at_cap` / `cce_frac_slots_at_cap`** — the per-slot
   distribution. sensor_dense: **3,254 of 8,000 slots (40.7 %)**; the
   parametric mix: **0 of 8,000**.

**A `cce_achievable_ceiling` field was tried first and abandoned**, because
deriving it from *"slot kinds this run spent anything in"* reads 1.0 — D-slots
carry 524 of 76,800 CCEs (0.7 %) rather than exactly zero, so any usage
threshold for "reachable" is an arbitrary judgement. **The breakdown needs no
such judgement and shows the same thing more directly.**

### The sweep for the same shape elsewhere

**`record_grid_capacity` is ALREADY direction-gated** —
`dl_prbs=slot_grid.prb_count if slot_grid.dl_symbols > 0 else 0` — so
**PRB utilisation does not have the mirrored defect**, in either direction.
CCE was the only unguarded denominator in the metrics layer, and the scoring
layer's ratios (M07's GBR list, M09's qualifying windows, M19's gaps) each
carry an explicit population already.
