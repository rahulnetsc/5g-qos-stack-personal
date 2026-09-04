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
