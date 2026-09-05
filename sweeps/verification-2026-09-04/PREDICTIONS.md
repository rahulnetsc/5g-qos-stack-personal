# Registered BEFORE reading any n>=10 result — 2026-09-04

**Honest status at the moment of writing:** the G11 n=10 run is **already
launched and still running; its output has not been read**. Everything else
below is registered before the relevant figures were extracted.

**The shape, not the mechanism** (journal form rule 1), and each prediction
says what would count as a miss.

| # | claim | expected | a MISS looks like |
|---|---|---|---|
| **A** | **G11's C1 1.000 pass does NOT survive at n=10** | at least one failing window on at least one arm | C1 stays 1.000 / 0 failing windows on all three arms |
| **B** | G1's bound holds at n=10, h=40k | 0/10 breach on every arm | any arm breaching |
| **C** | G3's bound holds at n=10, h=40k | 0/10 over 500 ms on every arm | any arm breaching |
| **D** | G5's failure reproduces at n=10, h=40k | PF ~0/10; Reservation and TwoTier both fail on multiple seeds | either QoS-aware arm at 0/10 |
| **E** | G8 fails at n=10, h=40k | already read — **not a prediction**, recorded so the scoreboard is not padded with a known result | — |

**Why A is the interesting one.** It is G8's shape exactly: a 1.000 pass at
n=3, never re-measured, on a conjunction of five bounds evaluated per window.
More seeds means more windows and more chances for any conjunct to breach, so
the asymmetry runs one way — a low-n pass is fragile and a low-n *failure*
would not be. **If A misses, that is the more informative outcome**: it would
say the n<=3 exposure is not general, and that G8's reversal was specific to
a starvation counter rather than a property of low-n passes.

**Standing caveat on B–D:** these are re-reads of `core_40k_n10.json`, an
artefact that already exists. They are predictions about what I have not yet
extracted, not about a run that has not happened — weaker than A, and marked
so rather than scored as if blind.


---

# SCORED — 2026-09-05

| # | claim | outcome | result |
|---|---|---|---|
| **A** | G11's C1 pass does **not** survive at n=10 | **MISS** | C1 = **1.000 on all three arms**, 0 failing windows, 0 unscoreable, **10/10 seeds pass on every arm**, over **20 windows** (vs 6 at n=3) |
| B | G1's bound holds at n=10, h=40k | **HIT** | 0/10 breach on every arm |
| C | G3's bound holds at n=10, h=40k | **HIT** | 0/10 over 500 ms on every arm |
| D | G5's failure reproduces | **HIT** | PF 0/10; Reservation **7/10**; TwoTier **4/10** |

**3 hits, 1 miss — and the miss is the one that was worth registering.**

**What A's miss establishes, stated as registered in advance:** *"If A misses
... it would say the n<=3 exposure is not general, and that G8's reversal was
specific to a starvation counter rather than a property of low-n passes."*
That is what happened. **The category search paid for itself once, not
twice** -- it found one real instance (G8) and cleared the other candidate by
measurement rather than by assumption. Clearing a candidate is the cheaper
half of a category search and the half that usually goes unreported.

**Why A was worth predicting anyway.** The asymmetry argued for it: more
seeds means more windows and more chances for any of five conjuncts to
breach, so a low-n pass is fragile in one direction only. That reasoning was
sound and the outcome still went the other way -- which is the difference
between a prediction and a conclusion.

**AND A'S MISS DOES NOT CLEAR G11.** The seed exposure is closed; the
**horizon** exposure is untouched. C1 is measured over 20 windows at
**400,000 slots -- 1.7 minutes** -- against GT-7.1's specified **>=30 minutes
(7,200,000 slots)**. A pass at 1/18th of the specified duration is not the
guarantee's pass, and G11's row says so.

---

# Registered BEFORE reading the real-horizon C1 run — 2026-09-05

**Status at the moment of writing: the run was launched detached and its
output has NOT been read.** No file from it has been opened.

**F — Does C1 still pass with the full schedule present?**

**Predicted: NO — at least one failing window on at least one arm.**

**The shape, and each look's meaning fixed in advance:**

| observed | means |
|---|---|
| 0 failing windows, all arms | **MISS.** C1 passes GT-7.1 as specified — the first real G11 result and a clean one |
| failures clustered in the firmware window (T+600–660 s, windows 10–11) | **HIT, mechanism as named** — the flood is what breaks the conjunction |
| failures scattered across windows with no cluster | **HIT on the verdict, MISS on the mechanism** — something other than the scripted events |
| failures only in the STOP window (T+1200) | HIT, and more interesting than predicted: a 40-byte burst breaking a conjunction is a finding in itself |

**Why FAIL.** Three of the four scripted ingredients have never been in a
scored run. The firmware push is 8 Mbps of DL 5QI-8 for 60 s — a saturating
flood in one window, which is G6's own stressor — and C1 conjoins five bounds
**per window**, so one bad window fails the clause outright. The run also has
**30 windows per seed against 2**, so 900 windows are scored where 20 were: a
per-window failure rate too low to appear at 20 would appear at 900.

**The counter-argument, stated so the prediction is not a one-sided bet.**
5QI 8 is in `NON_PROTECTED_5QI`, so the firmware flow is excluded from the
protected-fleet statistics C1 scores — it is the aggressor, not a victim, and
its effect is indirect capacity theft. That is exactly G6's question, and
G6's answer was that the protected fleet mostly holds. If C1 passes, this is
why.

**AND A NOTE ON MY OWN PRIOR.** Prediction A used the same "more samples,
more chances" asymmetry and MISSED. This one is stronger for a different
reason — the *events* are new, not merely more numerous — but the reasoning
family has already failed once here and that is on the record before the
result is read.

## F — SCORED, 2026-09-05

**MISS.** C1 **passes** at GT-7.1's specified horizon with the full schedule
present: **300 windows per arm (900 total), 0 failing, 0 unscoreable, 10/10
seeds on every arm.**

The schedule fired and is recorded on every run: `teleop_on_windows: 90`,
`waypoint_pauses: 6`, `firmware_windows: 1` (**59,994,505 bytes delivered**),
`stop_bursts: 1` (**40 bytes arrived**).

**The counter-argument I registered is what happened.** 5QI 8 is in
`NON_PROTECTED_5QI`, so the firmware flood is the **aggressor** and is
excluded from the protected-fleet statistics C1 scores. A 60 MB push through
the cell did not move any protected window past its bound on any arm.

### A PATTERN IN MY OWN PREDICTIONS, worth more than either miss

**A and F are the same reasoning and both missed.** Both argued *"more
samples / more events means more chances for a conjunction to break"*:

| | prediction | reasoning | outcome |
|---|---|---|---|
| A | C1 fails at n=10 | 20 windows instead of 6 | **MISS** |
| F | C1 fails at the real horizon | 900 windows instead of 20, and three new stressors | **MISS** |

**The asymmetry argument is sound and keeps being insufficient**, because it
reasons about *opportunity* and not about *mechanism*. C1's conjuncts are
bounds on the protected fleet, and none of the scripted ingredients is a
protected flow: the teleop duty cycle is subtracted as scripted silence, the
waypoint pause likewise, and the firmware flood is a non-protected aggressor.
**Nothing in GT-7.1's schedule is aimed at the statistics GT-7.1 scores.**

That is the thing to have noticed in advance, and it was available in advance
— `NON_PROTECTED_5QI` is a constant, not a measurement. **Twice now, an
opportunity argument has substituted for reading what the statistic actually
ranges over.** Next time the question is *which flows does this bound sum
over, and is the new stressor among them* — the decompose rule, applied to a
prediction instead of to a result.
