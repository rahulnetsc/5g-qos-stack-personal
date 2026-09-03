# Prediction journal

Predictions registered **before** the investigation that would settle them,
so a diagnosis cannot be scored against a hypothesis written after the
evidence. One entry per question. Scored at the end of the same
investigation, hits and misses both.

---

## P1 — G6's TwoTier M03 failure at 40 seeds (registered 2026-08-31)

**The observation to be explained.** On the `bg` (saturating background
aggressor) excursion at the base point, paired within seed against the
no-`bg` base cell, TwoTier's M03 `max_gap_ms` impairment is **+136.84 %**
with a bootstrap CI of **[+35.23, +267.01]**, entirely above GT-4.1's
+20 % bar. PF (+0.44 %) and Reservation (+1.84 %) pass. M01.p98 moves the
same way on TwoTier (+67.52 %, CI [+14.91, +123.74]) and not on the other
two arms.

**A disambiguation registered up front, because the answer depends on it:
`n=40` is a SEED COUNT, not a fleet size.** The cell is **N=8 UEs, offered
load ×1.0** — the base point. If the intended question was "does G6 hold at
40 UEs", no such cell exists in any run to date and the answer is *unrun*,
not *failed*.

### The prediction — one sentence, falsifiable

**(a) A real scheduler behaviour, not a metric artefact and not a scope
error: TwoTier's UL ranking composite multiplies its priority term by the
candidate's own hypothetical grant size, so a saturating best-effort
aggressor carrying a large backlog outranks the 300-byte periodic telemetry
flow and intermittently starves it, widening the worst liveness gap.**

### What would distinguish (a) from (b) and from (c)

- **Against (c), a max-statistic or metric-definition artefact:** if the
  excess were an artefact of `max_gap_ms` being a *maximum* over the run,
  it would show up in **that statistic alone** and be carried by **one or
  two extreme seeds**, leaving M03's own count-based companion
  (`gap_count_over_t_live`) and M01.p98 flat. The prediction requires the
  opposite: the excess is present across the seed distribution and the
  count-based companion moves too. **M01.p98 already moved (+67.52 %),
  which is weak prior evidence against (c) but is not decisive, because
  both could share a single starvation episode.**
- **Against (b), a guarantee stated at the wrong scope:** scope would mean
  the failing cell lies outside the regime G6 claims. It does not appear
  to — N=8 at load ×1.0 is the base point, and G10's own admissible-fleet
  finding puts N=8 inside the covered range at that load. **(b) becomes the
  answer only if G6's authoritative wording restricts it to a
  load/fleet/traffic-class regime this cell is outside of.**
- **The decisive positive observation for (a):** a code path in
  `scheduler/two_tier.py` where the telemetry flow's UL candidate loses to
  the `bg` flow's candidate *because of* a size-proportional term, plus
  per-seed evidence that the widened gaps coincide with the aggressor being
  served.

### The competing outcome I would have to report

If the mechanism cannot be located in the code path, **the correct result
is "unexplained", recorded as such.** A plausible story invented to close
an unexplained failure is worse than the unexplained failure, and this
project has recorded three corrections that began exactly that way.

**Scored:** see the end of this entry once the investigation completes.

### SCORED — 2026-08-31: **MISS on the branch, HIT on the discriminator**

**The answer is (c), not (a).** `docs/wp9-plan.md` §24.

**The branch was wrong.** I predicted a real scheduler behaviour, with a
named mechanism: the UL composite's size-proportional `hyp_tbs_bytes` term
letting the aggressor outrank the 300-byte telemetry flow. **That is not
what happens.** M03's worst-gap contest scans *every* flow
(`sim/scorecard.py:220`), and on all four seeds carrying the effect the
reported flow is **`ue8_qfi8` — the aggressor itself**. Fleet telemetry
stays inside its 500 ms bound. The mechanism I named was never tested,
because the statistic was never about the telemetry flow.

**The discriminator was right, and it is what found the answer.** I
registered: *"if the excess were a max-statistic artefact it would be
carried by one or two extreme seeds"*. Measured: **median relative delta
−0.22 %, 21 of 40 seeds IMPROVE, and the +136.84 % mean is carried by four
seeds.** That test fired exactly as written and pointed at (c) while my
predicted branch pointed at (a) — the registration earned its keep by
disagreeing with the prediction it was attached to.

**I also under-weighted my own hedge.** I wrote that M01.p98 having moved
was *"weak prior evidence against (c) but not decisive, because both could
share a single starvation episode"*. They did share one — the aggressor's.
The hedge was correct and I should have followed it rather than the branch.

**What the prediction missed entirely**, and neither branch anticipated:
the G6 test was **under-specified**. G6 binds ten G1/G3/G5 statistics
(`config/metric_panel.yml`); the test used three. The omitted **M02** rises
on **40/40 seeds on every arm** (+0.24), which is the real impairment — and
**TwoTier is the least impaired of the three**, so the reported result was
inverted, not merely imprecise. No option in the (a)/(b)/(c) framing covers
"the test measured the wrong set of statistics", and I did not think to
add one.

**Lesson carried forward:** the three-way framing was mine to widen and I
did not. When registering a prediction over a fixed set of branches, add
the branch *"the instrument is measuring something other than what the
question is about"* — in this project that branch has now been the answer
three times (§19.1's trigger, §22.5's single GBR class, and this).

---

## P2 — Does fleet-restricted M03 fall inside G6's +20 % bar? (registered 2026-08-31)

**Registered before running §24.7's falsifier.** Counts carry their noun
throughout: `n_seeds` for paired seeds, `n_ues` for fleet size. The cell is
**n_ues=8, offered load ×1.0**.

**A data constraint recorded up front, not discovered afterwards.**
`scripts/g6_seed_extension.py:62-64` calls `sweep()` with **no
`record_sink`**, so the n_seeds=40 run persisted only the tidy CSV — which
carries M03's *winning* flow and value, never the per-flow completion
timestamps a restricted recomputation needs. **The falsifier is therefore
computable from disk at n_seeds=10** (stage 1's `records.jsonl` holds the
`bg=True` excursion cell and the base-point cell with
`completion_ts_by_role_s` intact), **and at n_seeds=40 only by re-running
those same two cells with a sink.** Whatever comes back is reported at the
`n_seeds` it was actually computed at.

### The prediction — one falsifiable sentence

**Fleet-restricted M03 will NOT fall inside the +20 % bar under the
mean-of-ratios estimator: the excess will drop substantially from
+136.84 % but stay above +20 %, because the aggressor degrades real fleet
flows as well as starving itself — on the one seed already traced
(1440696407) the fleet-only max gap moved 118.75 → 352.25 ms, +197 %,
with no aggressor flow involved.**

**Corollary predicted in the same breath:** the **median** fleet-restricted
relative delta will stay **inside** the bar, so the verdict will depend on
the estimator rather than on the data — which is Step 4's point arriving
early.

### What would show the §24 mechanism is INCOMPLETE rather than WRONG

Three outcomes, distinguished in advance:

- **Excess collapses to ≈ 0 %** → §24's mechanism was **complete**: the
  aggressor's own starvation was the whole effect, (c) stands unqualified.
- **Excess stays near +136 %** → §24's mechanism was **wrong**: excluding
  the aggressor changed nothing, so it was never what drove the statistic.
- **Excess drops a lot but stays above +20 %** → §24's mechanism was
  **INCOMPLETE**: it correctly identified the aggressor as the dominant
  contributor while missing a real, second, fleet-side degradation. **This
  is what I predict**, and it means the honest verdict is neither pure (a)
  nor pure (c) but both, with the split quantified.

### Standing branch — the instrument is measuring something other than the question

Included by standing rule, having been the answer three times in this WP
(§19.1's wrong trigger, §22.5's single GBR class, §24.2's aggressor flow).
**Its live form here:** fleet-restricted M03 is *still a maximum over
n_ues=8 UEs × several flows*, so its relative change is dominated by
whichever single flow happens to spike hardest, and "fleet-restricted"
does not make an extreme-value statistic into a fleet-health statistic.
**The signature to look for:** the restricted excess is again carried by a
handful of seeds with a near-zero median, and the winning flow changes
identity between the paired base and excursion runs — i.e. the statistic is
tracking *which flow spiked*, not *whether the fleet degraded*.

**A second live form:** M03's own definition
(`config/metric_panel.yml:96-99`) says **"telemetry** inter-arrival gaps",
so restricting to "every fleet flow" is already looser than the metric's
own text. Both restrictions are therefore computed — aggressor-excluded and
telemetry-only — because they answer different questions and only the
second matches the definition.

**Scored:** at the end of this entry.

---

## Standing methodology note — a decision rule stated in a prompt is not evidence

Recorded beside P2's standing branch because it is the same shape of error,
one level up: **the standing branch is about the instrument measuring the
wrong thing; this is about the DECISION RULE evaluating it wrongly.**

**The instance.** Step 1's instruction read *"Excess still above +20 % ⇒
verdict returns to (a), a scheduler defect."* That is a **point-estimate
rule**, issued to a project that had, one section earlier, committed itself
in writing to the opposite: `docs/wp9-plan.md` §24.3 reports the interval
and not the point, and `scripts/analyse_stage6.py::g6_verdict` implements
PASS / FAIL / **INCONCLUSIVE** against the interval precisely so a large
point estimate inside a spanning interval cannot be read as a failure.

**Applying the rule literally would have returned (a).** Fleet-restricted
M03's point estimate is **+34.08 %**, above the bar. Its interval is
**[−16.90, +105.67]**, containing both the bar and zero, and its median is
**−2.44 %**, inside the bar. A defect verdict — and then a binding change to
a client-facing guarantee — would have rested on a statistic the data does
not support.

**This is the second time in this thread a prompt encoded an error the
source-side check caught.** The first was the `n=40` framing, which read as
a fleet size when the cell is n_ues=8 at load ×1.0 and 40 is the paired-seed
count (`docs/wp9-plan.md` §24.0); left unchecked it would have produced a
scope finding about a fleet size never run.

**The rule, stated so it generalises:** *a decision rule, a threshold, or a
framing that arrives in a prompt is an input to be checked against the
project's own methodology, exactly like a forward-looking note in this
repo's docs (CLAUDE.md's four kinds).* It is not evidence, and it does not
override a discipline the project has already committed to in code and in
writing. When the two conflict, **say so and apply the project's own rule**,
rather than following the instruction into a result that will not survive
review.

**Why this belongs in the journal rather than in a plan section:** it is a
statement about how predictions get scored, and the failure mode it guards
is scoring a prediction against a rule that was itself wrong.

---

## Standing rule — predict the SHAPE, not the mechanism

A rule about **how to write an expectation**, not about what to expect. It
belongs beside the most-likely-wrong rule for that reason: both govern the
form of a registration rather than its content.

**Predict what the data will LOOK like, and what each possible look would
mean. Do not predict WHY.**

### Why, from the two predictions in this journal

**P1 predicted a mechanism, inferred from an aggregate, and missed.** It
named a specific code path — the UL composite's size-proportional
`hyp_tbs_bytes` term letting an aggressor outrank telemetry — reasoned from
a +136.84 % headline. The mechanism was never even under test: the
statistic belonged to a different flow. **A mechanism prediction is
unscoreable until someone traces the code**, and until then it does nothing
except make one explanation feel likely.

**P2 predicted a shape, with each shape's meaning fixed in advance, and hit
on every clause.** It said the excess would drop substantially and stay
above the bar, that the median would stay inside it, and — the load-bearing
part — it enumerated three outcomes *before* the data arrived: collapse to
zero ⇒ the mechanism was complete; unchanged ⇒ the mechanism was wrong;
drops-but-stays-above ⇒ the mechanism was **incomplete**. When the third
arrived, the interpretation was already fixed and could not be fitted to it.

### What the form buys

1. **It is scoreable on arrival.** No trace needed to know whether it hit.
2. **It cannot be re-fitted afterwards**, because the mapping from outcome
   to meaning was written down before the outcome existed. This is the
   whole guard, and a mechanism prediction has no equivalent.
3. **It still forces the mechanism question — but only when it misses**,
   and then with the search already narrowed by which shape actually turned
   up. P1's miss required a full source trace to explain; P2's hit needed
   none, and a P2-style miss would have arrived with three candidate
   explanations already distinguished.
4. **It survives the instrument being wrong.** A shape prediction about
   medians, spreads and seed counts still scores when the metric turns out
   to measure the wrong thing — which in this WP it has, three times.

### The failure mode it prevents

**A mechanism inferred from an aggregate is a story that fits the summary
statistic, and summary statistics under-determine mechanisms.** P1's story
was consistent with every number then available and still wrong, because
the number was a mean of 40 ratios of a maximum over 8 UEs — a quantity
compatible with many mechanisms and diagnostic of none. **The aggregate was
never going to identify the code path, and no amount of care in reasoning
from it would have helped.**

**Corollary for registration:** if an expectation cannot be scored without
first running a trace, it is written in the wrong form. Rewrite it as a
statement about what the distribution will look like, and attach the
mechanism as the thing the *trace* will settle if the shape misses.

---

## P3 — Are Step 3's clause-1 bound failures PRE-EXISTING? (registered 2026-08-31, before looking)

**Registered before any query, because this question has an obvious desired
answer** — "yes, pre-existing, so G6 is clean and nothing new is owed" —
and that is exactly the shape that gets confirmed rather than tested.

**The observation.** §28.4's clause-1 column (G6's *first* conjunct,
"stays within its bound", never evaluated before Step 3) shows, on the
protected fleet at n_ues=8, load ×1.0, n_seeds=40, **with the aggressor
present**:

| statistic | bound | PF | Reservation | TwoTier |
|---|---|---|---|---|
| M05 pdu_set_completeness | ≥ 0.99 | 3/40 under | 30/40 under | 35/40 under |
| M01 p98 | ≤ 100 ms | 0/40 | 0/40 | 8/40 over |
| M03 max gap | ≤ 500 ms | 0/40 | 0/40 | 2/40 over |
| M06 frame age p95 | ≤ 67 ms | 0/40 | 0/40 | 12/40 over |

**The question:** do these breaches also occur in the **base** cell,
without the aggressor? If yes they are **G1/G3/G5 findings** and G6 is
untouched by them. If no — if the aggressor is what pushes them out of
bound — then **G6 fails its first conjunct** even though it passes its
second, and §28.1's headline needs qualifying.

**Answerable from records already on disk** (`stage6_g6_n40_records.jsonl`
holds both cells), **no new run** — the same shape as the inventory that
found most of Part A already stored.

### The prediction — one falsifiable sentence

**M05's breaches are PRE-EXISTING on all three arms (present in the base
cell at similar rates), while TwoTier's M01/M03/M06 breaches are
PARTIALLY aggressor-driven — present in the base cell but at materially
lower seed counts, so the aggressor widens an existing tail rather than
creating a new failure.**

### What each outcome would mean, fixed in advance

- **All four pre-existing at similar rates** ⇒ clause 1 says nothing about
  G6; the findings are G1/G3/G5 and belong to those guarantees. §28.1's
  headline stands unqualified.
- **Any breach absent from the base cell and present under `bg`** ⇒ **G6
  fails its first conjunct** on that statistic. §28.1's headline becomes
  "passes the *shift* clause on both statistics, fails the *bound* clause
  on N", and the guarantee's verdict is mixed rather than clean.
- **Rates materially higher under `bg` but non-zero in both** ⇒ the
  aggressor widens an existing tail. **This is the messiest outcome and the
  one I expect for TwoTier's three**, and it needs a stated rule for how
  much widening counts, which G6's wording does not supply — a finding
  about the guarantee's specification, not about the scheduler.

### Standing branch — the instrument is measuring something other than the question

Live form here: **three of the four bounds are applied to a scalar the
metric reports for its own WORST flow**, and the worst flow can differ
between the base and `bg` runs — the same winner-churn that made M03's
relative delta untrustworthy (§27.3). A breach count of "8/40" may be
8 different flows. **Before attributing any difference to the aggressor,
check whether the breaching flow's identity is stable across the pair.**

**A second live form:** M05's bound (≥ 0.99) is applied to
`pdu_set_completeness`, which only `xr_video` flows produce. If the
breaching flow is the same video flow in both conditions, "30/40 under" may
be one chronically-incomplete flow rather than thirty failures.

**Scored at the end of this entry.**

### P3 SCORED — 2026-08-31: one clean hit, one miss, and the standing branch again

`docs/wp9-plan.md` §29. Answered from stored records, no new run.

| clause | outcome |
|---|---|
| M05's breaches **pre-existing on all three arms** | **HIT** — base 4/33/35 vs bg 3/30/35 (Δ −1/−3/0) |
| TwoTier's M01/M03/M06 **partially aggressor-driven, at materially lower base counts** | **MISS for M01/M03** (6→8, 1→2, within noise at n_seeds=40), **HIT for M06** (7→12) |
| the messiest outcome would need a widening rule G6 does not supply | **HIT** — M06 is exactly that cell, now recorded as §0.6.3 |
| **standing branch:** "30/40" may be one chronic flow, not thirty failures | **HIT, decisively** |

**The standing branch was the most valuable clause for the second
consecutive prediction, and this time it cost nothing.** Registered before
the data existed; confirmed on arrival — Reservation's 33 breaches come
from **2 distinct flows**, TwoTier's 35 from 4 with one accounting for 30.
It changed how the headline number is read rather than merely annotating
it.

**Contrast with the same insight's three earlier appearances in this item**
(§24.2, §25.4, §28.1): each was discovered *after* a wrong conclusion had
been published, and each cost a correction. **Asked in advance it is free;
asked afterwards it is a retraction.** That asymmetry is the argument for
making it a standing branch on every registration rather than a lesson
recalled when something looks odd — and it is now a mechanical check in
CLAUDE.md ("decompose before attributing"), with the four instances listed.

**What the misses teach about the form.** M01/M03's clause failed because I
predicted a *magnitude* ("materially lower base counts") on a quantity with
no stated resolution — 6 vs 8 breaches at n_seeds=40 is neither clearly
different nor clearly the same, and I had not said in advance what would
count. **A shape prediction still needs its threshold fixed in advance when
the shape is a difference in degree.** The pre-registration rule from the
previous entry is necessary but not sufficient: *predict the shape, and if
the shape is quantitative, name the cut.*

---

### Qualification — a prediction about your OWN forthcoming DESIGN is not a shape prediction

The rule above governs predictions about **data**: say what the data will
look like and fix each look's meaning in advance. That works because the
data exists independently of the person predicting it.

**It does not transfer to a prediction whose answer you are about to
choose.** WP9 G11 registered, for each commit, whether
`regression_corpus.py --check` would move. Two commits, two misses, in
**opposite directions**, from one cause:

| commit | registered | actual | why |
|---|---|---|---|
| 2 (ledger eviction) | `--check` **blind** | it **bound** and failed | reasoned from the commit's *headline* (scoring-adjacent) rather than its *diff*, which reached `RunRecord` |
| 3 (per-second fold) | `--check` **binds and moves** | it was **blind** | registered before deciding **opt-in versus new default**; opt-in was then chosen, and no corpus case opts in |

**Neither miss was about the world being surprising.** Both were about
registering an answer that had not been decided yet. Commit 3's registered
outcome→meaning map was wrong for the same reason — it read a clean
`--check` as *"the fold is not reaching the serialised record"*, when clean
is simply the **correct** result for an opt-in change.

**So: a blind/binds call is registered AFTER the design is settled and
BEFORE the code is run.** That is still in advance of the evidence, which
is the whole point of pre-registration; it is not in advance of the
decision the answer depends on. The test for whether this qualification
applies is one question — **could I change the answer by choosing
differently?** If yes, it is a design commitment, and a design commitment
is recorded, not predicted.

**This narrows the first rule rather than weakening it.** A shape
prediction about data is exactly as binding as it was; what it never
covered was the class of "predictions" the predictor gets to author.

---

## Standing rule — a TWO-LEVEL axis reading can invert

Beside the other two form rules, and it governs the **depth-versus-breadth**
question §21.5's go/no-go rule exists to settle.

**Two levels of an axis tell you a direction, not a shape, and the
direction can reverse at a third point.**

**The concrete instance.** Part A had exactly two off-base levels on
`duty_cycle` (0.5 and 0.1) at one fleet size, and read a monotone story
from them: burstier → worse. Part C ran the same axis across `n_ues` and
found **at n_ues=16, `duty_cycle` 0.5 gives PF 12.8 contracts / 0.922
floor while `duty_cycle` 0.1 gives 0.0 / 0.445** — the burstier setting
destroys contracts outright rather than continuing a trend. **The axis is
not monotone, and a two-point reading could not have shown that.**

**What this changes about registering an expectation.** An axis with two
levels supports *"this axis has an effect"* and does **not** support
*"more of it does more of that"*. Register the first; if the second is
what the claim needs, the axis needs a third level before the claim is
scoreable at all.

**And it sharpens §21.5's rule rather than replacing it.** That rule
decides *whether* to buy depth from a single-cell effect. This says what
the single cell can and cannot licence in the meantime: **breadth
establishes existence, depth establishes shape**, and a plan that reports
shape from breadth is over-reading its own grid. Part A's `duty_cycle`
write-up did exactly that and Part C corrected it.

---

## Standing rule — check the instrument has DYNAMIC RANGE before registering a delta

Third of the form rules, and the one that catches a correctly-written
expectation that still cannot be scored.

**An expectation stated as a delta on a metric that is FLOORED (or capped)
in both conditions cannot be falsified. Before registering any delta
expectation, verify the statistic actually moves in the CONTROL.**

### Why this is a rule about expectations, not about metrics

**J5 was written correctly** — a shape prediction, with each outcome's
meaning named in advance, carrying the most-likely-wrong slot and its trace
obligation. It satisfied every rule above it in this journal. **And it was
unfalsifiable**, because the neighbours' M02 was `0.0` in *both* the join
and the no-join condition: ΔM02 = 0 − 0 = 0 on every arm, every case, every
seed. No possible outcome of the campaign could have contradicted it.

**The check that would have caught it is on the INSTRUMENT, not the
expectation** — which is exactly why it needs its own rule. Reading J5
again, however carefully, would never have revealed it. Running the control
once and asking *"does this number move at all?"* does.

### The mechanical form

Before registering a delta expectation, on the control condition alone:

1. **Is the statistic at a bound?** M02 floored at 0.0, a completeness
   fraction pinned at 1.0, a max capped by construction (M19's HoL, capped
   by `expire()`).
2. **What would have to happen for it to move**, and is that within the
   range the experiment explores? The neighbours sat at p98 15.5 ms against
   a 100 ms PDB — **6× headroom**, so only a catastrophic disturbance could
   register on M02.
3. **If it cannot move, register the delta on a statistic that can** — and
   report both: the guarantee's own currency *and* the instrument with
   range. Δp98 alongside ΔM02, not instead of it.

### The asymmetry, which is the same one the decompose rule records

**Asked beforehand it costs a scenario fix; asked afterwards it is a
retraction.** The floored-metric shape now has three instances:

| | when caught | cost |
|---|---|---|
| §24.2 — M03's max won by the aggressor | after publication | **retraction** |
| §28.1 — M02's rise was the aggressor's own bytes | after publication | **retraction** |
| §33.2 — neighbours' ΔM02 floored at zero | **before any number was quoted** | a scenario fix (added the `bg` load GT-6 already specified) |

**Two retractions, then one cheap fix — and the difference is entirely
when the question was asked**, not how hard it was to answer. Each time the
question is the same: *what does this statistic do in the condition I am
comparing against?*

---

## Standing rule — a rule can be violated by the code that IMPLEMENTS it

Fourth of the form rules, and it is about a failure the other three cannot
reach: not forgetting a rule, but **breaking it inside the tool built to
apply it.**

**The instance.** `scripts/g12_score.py` exists to apply this project's
checks to G12's campaign. Its own docstring names the decompose rule. Its
second version computed E3's "first ramp point at which telemetry degrades"
as a **minimum over every (arm, seed) group** and printed *"first degradation
at ×1.0"*. That is true of **TwoTier only** — PF and Reservation do not
degrade until ×2.3. **An aggregate over one population, quoted as a
statement about another**, which is the decompose rule's exact subject,
committed by the scorer that cites it.

### Why this is not the same as forgetting the rule

**The rule was present, correct, and in scope, and it still did not fire.**
CLAUDE.md's decompose entry is written as a mechanical check — name (a) the
rows the aggregate sums over, (b) the rows the claim is about, (c) whether
they are the same set. Applying it to `min(first_bad)` takes ten seconds and
gives the right answer immediately.

**What failed was the trigger, not the rule.** The check is framed as
something you do *before quoting an aggregate*, and writing a scorer does not
feel like quoting — it feels like plumbing. The aggregate was quoted later,
by the tool, at a point where nobody was reading it as a claim yet.

### The generalisation

**Analysis code is a claim in advance.** Every aggregate a scorer computes is
a sentence somebody will read as a finding, and it is written at the moment
when the discipline that governs findings feels least applicable. So the
checks that apply to a published number apply to the **line of code that will
produce it**, at the time it is written.

**Concretely, for any aggregate inside an analysis tool:** decompose by the
grouping the report will present. If the output is per-arm, the statistic is
per-arm — a `min`/`max`/`mean` that collapses the reporting dimension is a
defect even when the number is arithmetically correct.

### The asymmetry, again, and it is the sharpest instance yet

| | when caught | cost |
|---|---|---|
| §24.2, §28.1 | after publication | **retraction** |
| §33.2 | before any number was quoted | a scenario fix |
| **§36.6** | **before publication, by re-running the tool's own check on its output** | **an edit, and the correct result** |

**What caught it was suspicion of the tool's own output** — "first
degradation at ×1.0" disagreed with a per-seed table read minutes earlier —
not a review of the code. **The scorer had already been read and approved by
its author.** Reading analysis code does not catch this; decomposing its
output does.

---

## P1 — `priority_level` derives from the 5QI table (2026-09-03)

**Registered before running anything.**

**The change.** `scheduler/flow.py`: `priority_level` defaults to
`DERIVE_PRIORITY_FROM_5QI` (-1) and `__post_init__` resolves it via
`priority_for_5qi(qfi)`, exactly as `lcg == -1` and
`pdb_ms == DERIVE_PDB_FROM_5QI` already do.

**`--check` BINDS, and this corrects the framing I was given.** The
instruction registered it as blind *"because the corpus does not call these
builders"* — true of `sim/parametric.py` and `sim/fleet.py`, but the fix is
not in either. It is in `FlowConfig.__post_init__`, which **every** corpus
scenario constructs. Input and change therefore intersect: `--check` would
fail if any corpus flow's priority moved.

**So the intersection test says the check can fail, and that makes a clean
result evidence rather than a structural inevitability** — evidence for the
specific claim that the three published-study scenarios already set
`priority_level` explicitly and are untouched by the derivation.

**Registered prediction.**

1. `regression_corpus.py --check` — **CLEAN**. Falsifier: any moved record.
2. The full suite — **at risk, and I expect some failures.** Any test that
   builds a `FlowConfig` without an explicit `priority_level` and asserts on
   ordering, Tier-1 weights or the UL LCP split now sees a real priority
   where it saw 100. A failure here is the change working, not a regression
   — but each one must be read individually, because a test that was
   *written* against the constant may have been pinning the defect.
3. Builder histograms — non-degenerate on every builder. Falsifier: any
   builder still emitting a single priority level. **This is the binding
   check**, because it is the only one that reads the population the defect
   was in.

**Outcome→meaning, fixed in advance.** Clean `--check` + non-degenerate
histograms = the fix reaches the WP9 builders and leaves the published
studies alone. Clean `--check` + a still-degenerate builder = the fix did not
reach the population it was for. A moved `--check` = a corpus scenario was
relying on the 100 default, which would be a fourth place the defect lived.

### P1 — SCORED

| # | registered | outcome |
|---|---|---|
| 1 | `--check` CLEAN, and it BINDS | **HIT** — `OK -- no drift beyond rel_tol=1e-06`. The corpus scenarios set `priority_level` explicitly, so the derivation leaves them untouched. The check could have failed and did not. |
| 2 | full suite **at risk; some failures expected** | **MISS — 940 passed, 0 failed.** |
| 3 | builder histograms non-degenerate | **HIT** — `sweep_scenario(8)` {19:8, 20:8, 40:8, 90:8}; `g11 N=4` {19:4, 20:4, 21:1, 40:4, 80:1, 90:4}; `build_fleet(8,mixed)` {19:8, 20:2, 21:2, 22:3, 40:5, 90:6}. Previously `{100: n}` in every case. |

**The MISS is the informative one, and it is not a near-miss.** I predicted
"some failures" because three mechanisms read `priority_level` —
`tier1.py::_weight_from_priority`'s Delay threshold, `two_tier.py`'s UL
urgency weight, `ue_lcp.py`'s uplink LCP sort — and the field went from a
constant 100 to a real spread across every builder-made scenario. Zero tests
noticed.

**So the suite does not distinguish those three mechanisms being fed a
constant from being fed real 3GPP priorities.** That is CLAUDE.md's
built-but-unobservable shape arriving from the other direction: not a
mechanism with no caller, but three mechanisms with callers and **no test
whose result depends on their input being meaningful**. It is also why the
defect survived: coverage answers *is this code correct when called*, and
nothing asked *is it called with anything but a constant*.

**Recorded as a gap, not fixed here** — a discriminating test for each of the
three is its own commit, and bundling it would defeat the attribution this
commit exists for.

## P2 — M20's caveat forwarding and M22's addition (2026-09-03)

**`--check` is BLIND to both, and this is the §10-commit-1 shape, so it is
declared rather than discovered.** `regression/baseline_studies_1_3.json`
stores `RunRecord`s — `flows`, `system`, `timeseries_*`, `join_events` — and
**no scorecard output at all**. Both changes are in `sim/scorecard.py`. The
input the check reads and the artefact the change touches do not intersect,
so a clean `--check` here is **zero evidence** and must not be cited as
verification. (This is exactly the trap `docs/wp9-g11-plan.md` §10 fell into
for the M09 hoist, corrected in `ac8c5cc`.)

**What BINDS instead:**

1. `sim/tests/test_scorecard.py`'s caveat test derives the caveat-carrying
   metric set **from the panel** (`{m["id"] for m in load_panel()["metrics"]
   if m.get("caveats")}`), so adding M22's caveat changes that set. If the
   test had hard-listed the ids — as it did until WP9 Step 2 — it would have
   kept passing while checking less than it claimed.
2. `sim/tests/test_m22_starvation.py`'s **pairing** guard: non-zero on a
   starved flow AND zero on a served one, same fixture shape. Either half
   alone passes for a broken metric (count-everything, or count-nothing).
3. The M20 probe: same flow, same value, caveat count 1 → 2.

**Registered: full suite green, `--check` clean and MEANINGLESS.**

## P3 — does the priority fix explain G12's declaration-order confound? (2026-09-03)

**Registered before Phase 2 runs. My first hypothesis is already REFUTED by
a read, and it is recorded because it was the obvious one.**

**Hypothesis (refuted).** `sim/ue_lcp.py:95` sorts a UE's uplink flows by
`priority_level`; on a constant key Python's stable sort preserves input
order, so the intra-TB split was declaration-ordered — proposed as *the*
mechanism behind G12's `[2, 4]` inversion.

**Why it cannot be, checked rather than assumed:** `ue_lcp` orders flows
**within one UE's transport block**, and in `build_fleet(8, "mixed")`
**zero UEs carry both 5QI 2 and 5QI 4 on the uplink**. The two classes G12's
order is about never contend inside a transport block, so this sort never
ranks them against each other. The mechanism is real and it is not this one.

**What the fix DOES change for those two classes, quantified:**

| 5QI | priority | Tier-1 weight | TwoTier UL urgency weight, before → after |
|---|---|---|---|
| 82 | 19 | Delay 5.0 | 0.350 → **0.869** |
| 1 | 20 | Delay 5.0 | 0.350 → **0.861** |
| 2 | 40 | PF 1.0 | 0.350 → **0.715** |
| 4 | 50 | PF 1.0 | 0.350 → **0.642** |
| 9 | 90 | PF 1.0 | 0.350 → 0.350 |

Two separate readings, and they disagree, which is why both are stated:

- **Tier-1 still does not separate 5QI 2 from 5QI 4** — the Delay threshold
  is `p <= 20` and both are above it, so both keep `_PF_WEIGHT`. Whatever
  else changed, this did not.
- **TwoTier's UL urgency now separates them** — 0.715 against 0.642 where
  both were previously clamped to the floor 0.35. That inter-class
  difference **did not exist in any published WP9 number.**

**Registered prediction, falsifiable.** Lower `priority_level` is higher
priority, so 5QI 2 is now favoured over 5QI 4 in TwoTier's UL urgency.
**If that term is what carries the order, G12's Region-2 sequence on TwoTier
should move toward `[4, 2]` — 5QI 4 degrading first — where the canonical
declaration order previously produced `[2, 4]`.**

**Outcome→meaning, fixed in advance.** Order flips to `[4, 2]` = the urgency
weight is a live lever on the ordering and the previous result was measured
with it disabled. Order stays `[2, 4]` = the ordering does not come from
this term, and declaration order remains the standing candidate with one
sub-mechanism (`ue_lcp`) now eliminated. **Order becomes unstable across
seeds = the previous stability was itself an artefact of the constant.**

**This is a prediction about a MEASUREMENT, not a conclusion.** It is
registered here so Phase 2 scores it either way, per the rule that a
prediction exercise only cited when it is right is not one.

## P4 — population becomes a required argument (2026-09-03)

**`--check` is BLIND to the substance and BINDS on a side-effect, and both
halves are declared before running it.**

- `regression/baseline_studies_1_3.json` stores `RunRecord`s and **no
  scorecard output**, and `scripts/regression_corpus.py` never calls
  `Scorecard.score()`. So the corpus cannot see the population logic at all:
  a clean `--check` is **zero evidence** that the restriction is right.
- It does bind on one thing: the change touches `scripts/regime_sweep.py`,
  which the corpus does not use, and `sim/scorecard.py`, which it does not
  call — so a clean result confirms only that nothing leaked into the
  driver/record layer. Worth having, not worth citing as verification.

**What BINDS instead**, and it is the pairing rather than either half:

1. `test_restriction_inverts_g1_and_g8_and_leaves_g3_and_g5_alone` — the
   ASYMMETRY. If restriction moved everything it would be a framing
   preference; it moves the two whose contests the filler was winning and
   leaves the two whose winners were already protected. A future change that
   silently re-broadens the population breaks this.
2. `test_score_refuses_to_compute_without_an_explicit_population` — the API
   guarantee. Verified RED on HEAD behaviourally first, not just by the
   missing import: HEAD accepted `score(rec)`, returned M01 won by
   `ue9_qfi9`, and `MetricResult` had no `population` attribute.
3. `test_population_sensitive_set_matches_what_score_actually_stamps` — one
   constant drives both the restriction and the stamp, so a result cannot
   report a population it was not computed over. That is exactly the failure
   M20 had.

**Registered prediction.** Full suite green after migrating 58 test call
sites to `all_flows()` (the choice that preserves every existing assertion's
meaning); `--check` clean and meaningless.

**Registered consequence, to be scored when Phase 2 re-runs.** Every
worst-flow number in `docs/wp9-regime-map.md` and `docs/wp9-plan.md` was
computed over `all_flows`. The G1 and G8 rows are **known-wrong, not
suspect**. G3, G5, G6 and G10's rows should be **unchanged** — G6 already
restricted via M20, G10's M07/M08 select `flow_class == "GBR"` which excludes
both non-protected 5QIs by construction, and G3/G5's winners were already
protected. **If a re-run moves G10, that prediction is wrong and the
`flow_class` argument was insufficient** — which is the falsifier worth
naming, because it is the one row I am asserting is safe without having
re-measured it.
