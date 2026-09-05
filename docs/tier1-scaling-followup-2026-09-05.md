# After the scaling: guarantees re-scored, re-profile, and the solver decision

**2026-09-05.** Follows `0ea02b0` (the scaling) and
`docs/tier1-scaling-decision.md` (the registration).

---

## 1. GUARANTEES RE-SCORED — a diff against `verification-2026-09-04.md`

Run like-for-like: the same campaigns at the same n, once with `_OBJ_SCALE
= 1.0` (by explicit file swap, verified in both directions — monkeypatching
cannot reach `spawn` workers) and once at 1e4.

**Every verdict HELD. Nothing changed category.**

| G | metric | before (K=1) | after (K=1e4) | verdict |
|---|---|---|---|---|
| **G1** | M01 p98 protected ≤ 100 ms | TwoTier **0/10**, med 90.12 | TwoTier **0/10**, med **87.78** | **HELD** — moved *away* from the bound |
| **G3** | M20 liveness gap | TwoTier med 266.2 ms | TwoTier med **257.1 ms** | **HELD** (still inconclusive) |
| **G5** | M05 ≥ 0.99, no attach path | TwoTier **4/10**, med 0.9918 | TwoTier **4/10**, med **0.9934** | **HELD** |
| **G5** | M05, *with* attach path | TwoTier **0/10**, min 0.993174 | TwoTier **0/10**, min **0.993333** | **HELD** |
| **G8** | M09 Jain protected ≥ 0.90 | TwoTier **3/10**, med 0.9916 | TwoTier **3/10**, med 0.9849 | **HELD** |
| **G8** | M22 starvation epochs | TwoTier med 0 | TwoTier med 0 | **HELD** (identical) |
| **G10** | admissible fleet | PF 8 / Res 4 / **TT 4** | PF 8 / Res 4 / **TT 4** | **HELD** |

**THE CONTROL HELD EVERYWHERE, and it is the load-bearing result:** PF and
Reservation are **bit-identical** on every metric in every campaign. Neither
calls `solve_tier1`, so any movement there would have meant the change was
not what it claimed to be.

### Scoring my own predictions — two misses, both mine, both recorded

I registered **G1 and G5 as "AT RISK"** on margin (5.5 % and 0.0032). **Both
held, and both moved *away* from their bounds.** So I predicted two verdict
changes and got **zero**.

| prediction | outcome |
|---|---|
| G1 at risk | **MISS** — held, and improved |
| G5 at risk | **MISS** — held, and improved |
| G3 holds | hit |
| G8 holds | hit |
| G10 TwoTier may move, PF/Res must not | hit (TwoTier held too) |
| PF/Reservation bit-identical everywhere | **hit, and confirmed exactly** |

**What I got wrong and why it matters.** I reasoned from *margin* — how
close a verdict sits to its bound — and ignored *direction*. Correcting a
numerically-degraded optimum should, on average, make the scheduler behave
*better*, and it did: TwoTier's latency, liveness gap and completeness all
improved. A margin argument is symmetric and the underlying change was not.

### Not re-run, and why
**G4, G6, G11 C1, G12.** G4 and G6 need their own campaign runners at n=40,
G11 C1 needs the 4.8 M-slot horizon, and G12's runner covers one cell in
~40 min. None is blocked; all are cost, and this session's budget went to
the profile and the solver decision. **Their published verdicts are
therefore still pre-scaling** and are marked as such in `phase2-results.md`.

### One movement worth parking (no verdict change)
TwoTier at N=16 in the consolidation grid: `n_never_granted` per seed went
**`[1,1,2]` → `[0,1,11]`**. Same verdict (FAIL either way, M08 floored in
both), but one seed's starvation count rose sharply while another fell to
zero. Logged, not chased.

---

## 2. RE-PROFILE — same method, same configuration

`sweep_scenario` N=8, 32 flows, **20,000 slots**, `record_timeseries=True`,
`cqi_delay_slots=8`, full sweep post-processing, seeds 1–3, median of 3 —
the 2026-09-04 configuration, restated because a number quoted outside its
configuration is a different measurement.

| arm | total | driver_run | online_variations | panel_score | persist |
|---|---|---|---|---|---|
| PF | 4.16 s | **84.5 %** | 6.0 % | 4.7 % | 4.4 % |
| Reservation | 5.81 s | **88.5 %** | 4.6 % | 3.4 % | 3.3 % |
| **TwoTier** | **10.72 s** | **93.7 %** | 2.5 % | 1.8 % | 1.8 % |

**Scaling fixes correctness, not speed** — it is the same solver call with a
multiplied vector. The LP share is essentially where it was:

| | TwoTier |
|---|---|
| driver (under LP timing instrumentation) | 12.24 s |
| **LP inside it** | **4.58 s = 37.4 %**, over 6,936 calls |
| `solve_tier1` total (LP + SCA overhead) | 4.81 s = 39.3 %, over 50 solves |

### The ordering after a hypothetical swap — visible without doing the swap

| scenario | TwoTier driver | speedup | LP share after |
|---|---|---|---|
| today | 12.24 s | — | 37.4 % |
| **LP made 41× faster** (direct-HiGHS's measured figure) | **7.77 s** | **1.57×** | 1.4 % |
| **LP made FREE** (the upper bound) | **7.66 s** | **1.60×** | 0 % |

**So the whole LP question is worth at most 1.60×, and 41× captures 98 % of
that.** After the swap TwoTier is still **7.7 s against PF's 3.6 s** — the
next bottleneck is the rest of TwoTier's own driver, not the solver. **Any
further LP optimisation past ~15× is chasing 0.1 s of 12.2 s.**

---

## 3. THE SOLVER DECISION — report only, nothing implemented

856 captured LPs. The exact greedy is the correctness reference.

| | correct `x` | strictly beaten by greedy | ms per LP | stable under column permutation |
|---|---|---|---|---|
| **shipped (K=1)** | **11.3 %** | **57 of 856** | 0.711 | **11.4 %** |
| **scaled (K=1e4)** | **98.7 %** | **0** | 0.698 | **98.8 %** |
| **greedy** | exact by construction | — | **0.0447** | deterministic\* |

\* ties currently resolve by list order; an **explicit** tie-break would be
required — this project has a confirmed declaration-order artefact and would
be adding another otherwise.

**The greedy is 15.6× faster than the solver call.** Direct-HiGHS was
measured at 41×. **That difference is immaterial:** 15.6× puts TwoTier's
driver at 7.95 s and 41× at 7.77 s, against a free-LP floor of 7.66 s. **The
choice must be made on correctness and determinism, not speed.**

### Recommendation: the greedy is the right target, not direct-HiGHS

| | direct-HiGHS | greedy |
|---|---|---|
| correctness | inherits whatever the solver's tolerances do | **exact by construction** |
| speed | 41× (0.18 s better than greedy, of 12.2 s) | 15.6× |
| determinism | a solver's pivot rule | **explicit, if the tie-break is written** |
| dependency | adds `highspy` | **removes the solver from this path entirely** |
| debuggability | a black box at the bottom of a stack trace | 30 lines that can be read |

### What its fidelity argument would have to be

**This is the part that decides it, and it is now much easier to make than
it was:**

1. The greedy computes the **exact optimum of the linearised subproblem** —
   which is what `glp_simplex` is *trying* to compute. It is not a change to
   the model, the SCA, the damping, the cap, or any constant.
2. **The optimum is unique on 98.7 % of solves**, so on those the greedy and
   GLPK *must* agree — a far stronger fidelity claim than the current code
   can make, since the shipped call agrees with the optimum on 11.3 %.
3. On the residual ~1.3 % the optimum is genuinely non-unique and the greedy
   must declare a tie-break. **That is where the fidelity argument has to be
   explicit**, and it cannot be settled against ground truth: there is **no
   Tier-1 output in this repository** (zero `IA-P5G` lines in
   `calibration-logs/`) and no GLPK binding installed. The honest form is
   "declared, documented, and deterministic", not "matches the C".
4. It would move the corpus again, and that would be a **second** deliberate
   re-baseline needing its own registration — the changes are ~1.3 % of
   solves rather than 88.7 %, so the diff should be far smaller than 838
   values. **Predicting its size in advance is the discipline that applies.**

**Not implemented. This is the recommendation and the argument it would
need, not the change.**

---

## 4. `glp_scale_prob` — its own item, and its disposition is "not portable"

The C calls `glp_scale_prob(lp, GLP_SF_GM)` at `ia_p5g_scheduler.c:1053`;
`scheduler/tier1.py` has no corresponding call. Kept out of the scaling
commit deliberately so neither is confounded with the other.

**Finding: there is no distinct change to make.** HiGHS applies its own
matrix scaling by default (`simplex_scale_strategy`) and `scipy.optimize.
linprog` does not expose the knob, so the C's explicit call has **no
separate Python equivalent to port**. It is a difference in what is written
down, not in what is computed.

**And an attempt to add one by hand was inconclusive — reported as
inconclusive rather than as a result.** Applying an explicit geometric-mean
row+column scaling on top of the objective scaling changed the answer on
96.7 % of LPs, but the objective gap between the two points, evaluated on
the *same* unscaled objective, was **6–15 %**. Two optimal points cannot
differ by 15 %, so **the hand transformation is wrong, not the finding.** I
have not debugged it, because the substantive conclusion does not depend on
it.

**What stands:** the matrix spans **2.83 orders** against the objective's
**9.85**, so this was never the dominant term, and the item is closed as
*not portable* rather than *fixed*.

---

## 5. The 41× direct-HiGHS optimisation is RE-OPENED

It was rejected because its answer differed from the shipped one. **Its
answer was the correct one** — `ue9_qfi9` 5,340,428, which the objective
scaling has now independently reproduced and landed. **The recorded reason
for rejecting it is known to be wrong**, and `CLAUDE.md` says so where the
rejection is recorded.

**Re-opened does not mean taken.** §3 recommends the greedy over it, on
correctness and determinism, with the speed difference shown to be worth
0.18 s of 12.2 s. Either way it needs its own plan.
