# Three specification findings for the test plan's owner

**2026-09-08.** Three clauses of `IA_P5G_Factory_Guarantee_Test_Plan.md`
cannot be scored as written. They are not measurement problems — in each
case the simulator produced the numbers and the *plan* does not say what
verdict they imply. Collected here as one list because they have one
audience and one shape.

**The shape, in each case: the plan states a comparison and omits the
threshold, so the verdict is chosen by whoever scores it.** That is not a
tolerance question; it is an unspecified requirement.

---

## 1. G6 — "background traffic does not disturb the guarantees" names no estimator

**Clause (L100):** the guaranteed statistics must hold *with* background
traffic present, and must not shift by more than a stated amount.

**What is missing:** the plan does not say **which estimator** the shift is
measured on. G6 is currently scored on a mean-of-per-seed-ratios, and this
project has already been bitten once by exactly that choice: the same
statistic read **+136.84 %** as a mean-of-ratios while its median read
**−0.22 %**, with 21 of 40 seeds *improving* (`docs/wp9-plan.md` §25.4).

**What we need:** name the estimator (mean of ratios / ratio of means /
median of per-seed deltas) and the population it is computed over.

## 2. G7 c1 — the isolation tolerance is unspecified

**Clause (GT-4.3 c1):** an aggressor must not disturb the victim.

**What is missing:** "not disturb" has **no ε**. We currently score it as
"victim PDU-set completeness ≥ 99 % and victim p98 ≤ its PDB", which is a
choice we made, not one the plan states.

**What we need:** either the ε, or an explicit statement that the victim's
own per-5QI guarantee *is* the criterion (which is what we assumed).

## 3. G9 — "neighbours unaffected" is not testable as written, and we can show it

**Clause (L103, fourth part):** *"neighbours unaffected throughout"*.

**What is missing:** the ε. And unlike the other two this one is now
**measured**, so the cost of leaving it unstated is visible. Over 540 runs
of the G9 stress experiment (`docs/g9-stress-experiment-2026-09-08.md`
§4.4), the fraction of runs whose worst incumbent p98 moved by no more than
ε:

| ε | runs within |
|---|---|
| **0.5 ms** | 184 / 540 (34 %) |
| **1.0 ms** | 217 / 540 (40 %) |
| **2.0 ms** | 266 / 540 (49 %) |
| **5.0 ms** | 408 / 540 (76 %) |

**At 0.5 ms the clause fails on two runs in three; at 5 ms it passes on
three in four. Nothing about the system changed between those rows — only
the number the plan does not state.** We report every ε rather than pick
one, and no G9 neighbours verdict should be quoted without its ε beside it.

**What we need:** the ε, in whatever unit the plan prefers (absolute ms of
p98, a fraction of PDB, or a fraction of the unloaded baseline). If the
intended answer is "any measurable change fails", say so — that is a
testable statement too, and we would report it as failing nearly everywhere.

---

**Contact:** rahul.r@artpark.in. These three, plus the SRB capture
(`docs/requests/srb-capture-request-2026-09-08.md`) and TS 22.104's
survival-time table (`docs/g9-stress-experiment-2026-09-08.md` §1.2), are
the complete set of external inputs the guarantee evidence base is waiting
on.
