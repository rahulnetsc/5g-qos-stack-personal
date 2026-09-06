# What in these results would embarrass us on a slide

**2026-09-05.** Written at the point the guarantee set became consistent, so
the next step is the deck rather than more measurement. Ordered by how badly
it goes if an audience finds it before we say it.

---

## Tier 1 — would be a retraction on stage

**0. THE BIGGEST ONE, ADDED 2026-09-06: our headline scheduler comparison is
partly not a scheduler result.** *"TwoTier is worst by 3.5x on latency"* — and
G7's *"PF contains the aggressor better than the arms that clamp"* — are
**a UE-side LCP effect that is identical code in all three arms, and no
scheduler change reaches it.** A grant is a transport block for a **UE**; which
of that UE's flows it carries is decided inside the UE by logical-channel
prioritisation, and **the gNB cannot see that split**. An arm chooses only how
often a UE is granted, and measured over 120 runs the more it grants, the
longer its protected flow's deferral tail (ρ = +0.79, p = 2.8e-27). PF
"contains" because it grants **~5.8x less**.

**Why this is Tier 1 rather than a caveat:** the numbers are correct and will
survive scrutiny; **the attribution will not**, and the attribution is exactly
what *"is two-tier needed"* turns on. If an audience works this out before we
say it, every scheduler comparison on the slide is in question at once.
**Say it ourselves, in the same breath as the number.** Full statement:
`docs/grant-density-mechanism-2026-09-06.md`.

**1. "Twelve guarantees" is not twelve.** Updated 2026-09-06: **G12 joined G2
in having no verdict at all** — its published artefact is unsound (a flow was
silently dropped from clause 4's own denominator) and the re-run cannot
reproduce it, so **ten carry a verdict**, one of those is partial (G11: 2
clauses of 5), and G6's is "fails clause 1" rather than a clean result.
**G2 and G12 have none.**
G7 is *structurally* out — there is no MFBR enforcement anywhere in `sim/`,
and clipping is half its pass criterion. Any slide that says "we evaluated
twelve guarantees" invites the one question we cannot answer.
**Say "ten with a verdict, one partial", and name G2 AND G12 and why.**

**2. G11 "passes" is one clause of five.** C1 passed at the specified
horizon — 1.000 on all three arms, 900 windows, 0 failing. **C2–C5 are
unscored.** A slide headline of "G11 PASSES" is quoting 20 % of the
guarantee. **Say "C1 passes; C2–C5 unscored."**

**3. G5's headline reversed, and the reversal is ours.** We published
Reservation **30/40** and TwoTier **34/40** failing PDU-set completeness,
then established the driver was a **cold-start lock-in that this simulator
creates and hardware does not** — under an attach path the same
configuration gives Reservation **1/10 marginal** and TwoTier **0/10**.
**The old numbers must not appear on any slide.** They are in
`phase2-results.md` only inside a row that says they are an artefact.

**4. Every TwoTier number produced before `0ea02b0` came from a solver that
was returning a suboptimal point.** The Tier-1 LP was solved correctly on
**11.3 %** of calls; the rest were vertices chosen by tolerance. Verdicts all
held on re-run — but the honest framing is *"we found it, we fixed it, and
we re-scored everything"*, said by us, first. **If an audience derives it
from the commit log instead, it reads as a correction we buried.**

---

## Tier 2 — would force an awkward qualification

**5. G10's admissible fleet is an UPPER BOUND, not a capacity result.**
PF 8 / Reservation 4 / TwoTier 4 was measured **without an attach path**, and
the lock-out that sets the boundary largely disappears with one. Presenting
it as "how many robots each scheduler supports" is wrong in a way a customer
would act on.

**6. G1's all-flow reading is saturated and must never be shown.** ~300 ms on
every arm, won by the 5QI-9 filler, three arms agreeing to 0.25 ms. Only the
**protected-fleet** reading (PF 24.8 / Reservation 24.4 / TwoTier 87.8 ms
against 100 ms) is meaningful. The saturated version looks like a *finding*
— "all schedulers identical" — and is an instrument artefact.

**7. G12 is one cell, and its ordering result is an artefact.** The
first-violation order was traced to LCP's tie-fallback — declaration order,
no physical referent. **Do not show an ordering as a scheduler property.**

**8. G3 and G6's TwoTier movement is real but INCONCLUSIVE.** G3's interval
is [−2.81, +50.02]. An interval that wide is not a result; presenting the
point estimate (+21.34 %) without it would be the standard chart crime.

---

## Tier 3 — worth pre-empting, small

**9. Aggregation-sensitivity in G4.** The published contrast reproduces
under the runner's own per-seed mean; a different but superficially
reasonable aggregation of the *same* artefact gives **the opposite sign**.
Found while re-running it today. Nothing published is wrong — but if anyone
recomputes from the raw rows they may not match, and we should show the
estimator alongside the number.

**10. The regression baseline was re-captured today.** Deliberate,
registered, with the shape predicted in advance — but "we changed our
reference numbers" needs the one-sentence reason ready.

**11. Reservation has no UL service-interval floor at all**, and TwoTier's
exists but cannot arm in the fault it was built for. This is our strongest
*product* finding — it should be a slide, not a footnote, and it is
independent of every simulator caveat above because it is read from the
deployed C's own source.

---

## What is genuinely strong and should lead

- **The Tier-1.5 dead-gate finding** (#11 above): read from the C, not
  measured here, so no simulator caveat touches it.
- **The cold-start lock-in as one mechanism behind three separate
  observations** — G5, G10's boundary and the UL blackout — with
  `n_never_granted > 0 ⟺ M08 floored`, **0 counterexamples in 144 runs**.
- **G1's protected-fleet separation**: 3.6× between arms, all passing.
- **The process itself**: pre-registered maps, predictions scored including
  the misses, and three defects found by our own checks rather than by a
  reviewer.
