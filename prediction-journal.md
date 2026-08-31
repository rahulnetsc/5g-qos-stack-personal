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
