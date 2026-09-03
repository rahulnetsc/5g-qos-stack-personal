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
| 8 | `wp9-plan.md` §24.6, `wp9_part_c.py` | cadence exclusion said `duty ≤ 0.5`; arithmetic says `0.1`, discarding a real breach | TwoTier 503.25 ms, 5/10 vs PF 0/10 | no | `e598470` |
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
