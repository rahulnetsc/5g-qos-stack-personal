# The Tier-1 LP: analysis

**2026-09-05. Analysis only — nothing built, no default changed.** Every
number below is measured on 6,842 LPs captured from one real run
(`sweep_scenario` seed 1097657231, n=8, 20,000 slots, TwoTier), by wrapping
`scipy.optimize.linprog` where `scheduler/tier1.py` imports it and passing
through, so the run itself is unperturbed.

**The headline is a correction to this project's own recorded finding.**
CLAUDE.md states the Tier-1 LP *"HAS MULTIPLE OPTIMA … same optimal face,
different vertex, chosen by how the solver got there."* **That diagnosis is
wrong.** The optimum is unique on ~98.7 % of solves; what was measured as
degeneracy is a **conditioning failure**, and the shipped solve returns a
strictly suboptimal point on 6.7 % of LPs.

---

## 1. The coefficients — the claim is refuted as stated, and sharper than stated

`c_i = w_i / (r_prev_i + 1)`, `w ∈ {1, 5}` (recovered from the first LP of
each solve, where `r_prev = EPSILON = 1`, so `coef = w/2` exactly — measured
`{0.5, 2.5}`, confirming both weights).

Over 218,944 coefficient values:

| | value |
|---|---|
| min | **1.39737e-07** |
| p01 / median | 2.02e-07 / **2.08e-04** |
| p99 / max | 2.5 / 5.0 |
| GBR penalty | **1000** (constant) |
| **span, min coef → penalty** | **7.16e9 = 9.85 orders** |

**Refuted as stated:** **0 of 218,944** coefficients are at or below HiGHS's
1e-7 default dual feasibility tolerance, and **0 of 6,842 LPs** contain one.
The predicted `c_i ≈ 2.5e-7 at 4 Mbps` is the *minimum* end, not typical —
the median coefficient corresponds to `r_prev ≈ 4.8 kbps`, not 4 Mbps.

**Sharper than stated, and this is the operative fact:** the minimum
coefficient is **1.4 × the tolerance**, and **46.75 % of coefficients are
below 1e-6**. A reduced cost within a factor of ~1.4 of the dual feasibility
tolerance is not distinguishable from zero by the solver's own optimality
test, so the simplex stops on a pivot it cannot see is improving. The
ten-order span is real (9.85 orders min-coef to penalty); it is just not
located where the claim placed it.

---

## 2. The fix that changes nothing — it works, and it moves the corpus

**Instrument: column permutation, not scaled-vs-unscaled.** Scaling `c` by
`K > 0` is argmax-invariant, so any change in `x` is the solver choosing
differently — but comparing scaled against unscaled conflates *"scaling
changed the answer"* with *"the answer was ambiguous"*. Permuting columns is
**also** exactly argmax-invariant and can be applied independently at each
`K`, so the disagreement rate at a given `K` measures that `K`'s ambiguity
and the comparison across `K` is like-for-like.

856 LPs (even subsample), solved as given and with columns permuted:

| K | different vertex | median max\|Δx\| | max rel. objective gap |
|---|---|---|---|
| **1 (shipped)** | **758 / 856 = 88.6 %** | **5.87e6 bps** | 1.07e-08 |
| 1e3 | **15 = 1.8 %** | 9.3e-10 | 2.99e-13 |
| 1e6 | **11 = 1.3 %** | 9.3e-10 | 1.04e-15 |
| 1e9 | — | — | 8.32e-16 |

**Scaling by 1000 removes 98 % of the ambiguity.** Since scaling cannot
change the mathematics, **the ambiguity was numerical, not structural.** The
residual ~1.3 % is genuine non-uniqueness.

### Does it change a delivered result? Yes — and that is the finding

`regression_corpus.py --check` with the objective scaled in-process (nothing
landed):

| K | values moved |
|---|---|
| 1e3 | **838** |
| 1e6 | **838 — byte-identical to K=1e3** |
| 1e9 | 866 (different) |

**K = 1e3 and K = 1e6 produce identical corpora; K = 1e9 does not.** That is
a conditioning *plateau* — a range over which the answer is invariant — and
**the shipped default sits outside it on the low side**, with 1e9 falling
off the high side as the 1e12 penalty acquires its own error.

**And the moved value is one this project has already seen.** CLAUDE.md
records, for the rejected direct-HiGHS optimisation: *"TwoTier `ue9_qfi9`
`throughput_bps` 5,521,232 → 5,340,428."* The scaled objective gives
**5,521,232 → 5,340,428**, exactly. **Three independent argmax-invariant
computations — direct-HiGHS warm, direct-HiGHS cold, and objective scaling —
agree on 5,340,428, while the shipped path alone returns 5,521,232.**

So this is **not** a fix that changes nothing. It is a fix that changes the
answer *to the correct one*, and §3 shows the shipped answer is measurably
suboptimal.

---

## 3. It separates, it is a knapsack, and a greedy beats the shipped solve

### Separability — verified against the C

`ia_p5g_scheduler.c:1027-1038`:

```c
for (int i = 0; i < n; i++) {
    const int cap_row = (flows[i].dir == 0) ? 1 : 2;
    nz++; ia[nz]=cap_row; ja[nz]=i+1; ar[nz]=1.0/flows[i].se;
}
for (int i = 0; i < n; i++) if (flows[i].is_gbr) {
    const int rr = gbr_row_of[i];
    nz++; ia[nz]=rr; ja[nz]=i+1;     ar[nz]=1.0;   /* r_i */
    nz++; ia[nz]=rr; ja[nz]=n+i+1;   ar[nz]=1.0;   /* s_i */
}
```

Each flow contributes **exactly one** nonzero to **exactly one** capacity
row, and each GBR row holds **exactly two** nonzeros, both for the same `i`.
**DL and UL are independent blocks and each GBR row is private to its flow.**
The claim holds exactly.

Minimising `P·s_i` with `s_i ≥ gfbr_i − r_i`, `s_i ≥ 0` gives
`s_i* = max(0, gfbr_i − r_i)`, so the value per unit of **capacity** is
`(c_i + P)·se_i` up to `min(gfbr_i, d_i)` and `c_i·se_i` above — concave,
hence greedy by density is exact for a continuous knapsack.

### The greedy is exact, and the shipped solve is not

856 captured LPs, everything recovered from the model as the solver received
it:

| | result |
|---|---|
| greedy point infeasible | **0 / 856** |
| greedy strictly **worse** than HiGHS | **0 / 856** |
| greedy strictly **better** than HiGHS | **57 / 856 = 6.7 %** |
| max signed relative gap (greedy − HiGHS) | **+1.51e-08** |

**The greedy is never worse, sometimes strictly better, and always
feasible.** So the shipped LP call leaves objective value on the table on
6.7 % of solves — that is beyond vertex selection.

And the discriminator for *which* answer is right, with the greedy as the
exact reference:

| | `x` agrees with the exact greedy |
|---|---|
| **HiGHS at K=1 (shipped)** | **97 / 856 = 11.3 %** |
| HiGHS at K=1e3 | **845 / 856 = 98.7 %** |
| HiGHS at K=1e6 | 845 / 856 = 98.7 % |

**The shipped Tier-1 LP returns the mathematically correct answer on 11.3 %
of its solves.**

---

## 4. The SCA — confirmed, with a sharp threshold and a worse corollary

**The precise argument** (stronger than "every iterate is a vertex" — the
iterates are *damped* and are not vertices). The iteration is
`r_{k+1} = α·v_k + (1−α)·r_k` with `v_k` a vertex of the polytope. A fixed
point requires `r* = α·v* + (1−α)·r*`, i.e. **`r* = v*`**. So the fixed-point
set is exactly the vertices that are their own linearised optimum. **Damping
changes the path, never the fixed points.** If the log-utility optimum is
interior, it is not a fixed point and cannot be reached.

Measured on 20 Tier-1 solves — exact optimum via CVXPY/Clarabel, then the
SCA run to the cap. The polytope has **10 constraint rows**, so a vertex
admits at most 10 strictly-interior components:

| strictly-interior components at the exact optimum | outcome | distance to optimum |
|---|---|---|
| **8** (≤ 10 → can be a vertex) | converged, iter 56 | **18.9 bps** |
| **23** (> 10 → not a vertex) | "converged", iter 56 | **3.1e5 – 3.6e6 bps** |
| **32** (> 10 → not a vertex) | **hit the 150 cap, 13 of 13** | 1.0e6 – 2.9e6 bps |

**The threshold is exact: every solve whose optimum had 32 interior
components hit the cap; every solve with ≤ 23 stopped at iteration 56.** The
claim is confirmed — and it is a property of where the optimum sits, not of
the tolerance.

**The corollary is worse than the claim.** *Converging is not the same as
being right.* **Six of the seven "converged" solves stopped at iteration 56
between 0.3 and 3.6 Mbps from the true optimum**, reporting success. Only
the single case whose optimum could be a vertex landed close (18.9 bps).
**`rel_change < TOL` carries no information about correctness here.**

### The closed form, for the record — not implemented

For `max Σ w_i log(r_i)` subject to `Σ r_i/se_i ≤ C` per direction and
`lo_i ≤ r_i ≤ d_i` (with `lo_i = min(gfbr_i, d_i)` once `P` is large enough
to make the GBR floor effectively hard), the KKT stationarity condition
`w_i/r_i = λ/se_i` gives

> **`r_i(λ) = clamp(w_i·se_i/λ − 1, lo_i, d_i)`**
> **`λ` by a monotone 1-D root find on `g(λ) = Σ r_i(λ)/se_i − C = 0`.**

(The `−1` is this port's `log(r + EPSILON)` with `EPSILON = 1`.) `g` is
non-increasing in `λ`, so the root is unique and bisection is unconditionally
convergent. **Unique, deterministic, O(n log n) per direction, and the two
directions are independent.** Deliberately not implemented.

---

## 5. The fidelity question — and one finding that reframes it

### The C scales the problem. The port does not.

`ia_p5g_scheduler.c:1053`:

```c
glp_scale_prob(lp, GLP_SF_GM);   /* geometric-mean scaling */
```

**`scheduler/tier1.py` has no corresponding call** — it hands raw `c`,
`A_ub`, `b_ub` to `linprog(..., method="highs")`.

**But this is a smaller finding than it first looks, and the honest split
matters:**

| | span | addressed by GM scaling? |
|---|---|---|
| constraint matrix \|a_ij\| | **2.83 orders** (1.47e-3 … 1) | yes — and it is the mild one |
| objective \|c_j\| | **9.85 orders** (1.40e-7 … 1e3) | **no** — GM scaling is a *matrix* treatment |

So the omitted `glp_scale_prob` is a real port omission, but the dominant
conditioning problem is **the objective's 9.85-order span, which is a
property of the model and is therefore present in the C as well.** Do not
report the missing call as the cause.

### Does the port reproduce the C's vertex selection? UNANSWERABLE HERE

**There is no Tier-1 ground truth in this repository.**
`calibration-logs/twotier_startup_gnb.log` contains **zero** `IA-P5G` lines
and zero Tier-1 output; the C's own `IA_P5G_LOG_LIFE` Tier-1 lines
(`ia_p5g_scheduler.c:1115`) were never captured. No GLPK binding is
installed either. **So "check whether the port already fails to reproduce
the C's vertex" cannot be answered by measurement.**

**What can be established, and it is enough to retire the comfort:** the
port's own answer changes under a column permutation on **88.6 %** of
solves — a transformation that changes nothing about the model. An answer
that is not stable under its own presentation cannot be reproducing a
*different solver's* vertex except by coincidence, and 88.6 % is not a
coincidence rate. **"Keep simplex for fidelity" is false comfort: the port
is not reproducing GLPK's vertex selection, it is reproducing HiGHS's
tolerance behaviour on a badly-scaled objective.**

**And the fidelity target is itself path-dependent.** The C's answer is a
damped iterate stopped at 150 on a sequence with no reachable fixed point
(§4), so *the deployed system's own output is not a well-defined function of
its inputs* in any sense that a different solver could reproduce. There is no
"the C's answer" to converge on — only "the C's answer on that build, with
that GLPK, at that pivot order".

### What this licenses

| option | what is known |
|---|---|
| **leave it** | the LP is suboptimal on 6.7 % of solves and returns the exact optimum on 11.3 %; the corpus pins that |
| **scale the objective** | matches the exact optimum on 98.7 %; moves 838 corpus values; the moved answer is independently corroborated by two direct-HiGHS builds; **argmax-invariant, so it cannot be defended against on optimality grounds — only on "the corpus records the shipped behaviour"** |
| **closed form** | unique and deterministic, O(n log n); diverges from the C's damped-iterate behaviour *by construction*, and §4 shows that behaviour is up to 3.6 Mbps from the optimum |

**Item 1 is the only one that could land without a fidelity argument, and
even it is not free** — it moves 838 corpus values. The defensible framing is
not "this changes nothing" but **"this replaces a numerically wrong answer
with the right one, and the corpus must be re-baselined deliberately, with
the reason recorded."** That is a decision, with its own plan.

---

## 6. Consequences for what is already written down

**CLAUDE.md's Tier-1 invariant needs correcting on its central claim.** It
says the LP "HAS MULTIPLE OPTIMA" and calls the 73 % different-`x` rate
"degeneracy: same optimal face, different vertex". Measured: the optimum is
unique on ~98.7 % of solves and the shipped answer is strictly suboptimal on
6.7 %. **The 73 % was a symptom of conditioning, and reading it as
degeneracy led to the wrong conclusion** — that the 41× direct-HiGHS
optimisation was "unavailable at this project's own bar", when its answer
was the correct one and the bar was calibrated against a defect.

**What in that invariant survives:** the SCA cap finding (41 of 50 hitting
`_SCA_MAXITERS`) is confirmed and now explained; the warning that a scipy
upgrade is a scheduler change is *more* true, not less, since the answer is
tolerance-determined; and "do not raise the SCA cap to chase convergence"
still holds — §4 shows convergence would not mean correctness anyway.

## Artefacts

`sweeps/phase2/lp-analysis-2026-09-05/` — `capture.py` (6,842 LPs),
`scaling.py`, `greedy.py`, `sca.py`, `sca_across.py`,
`corpus_under_scaling.py`, and their JSON outputs.
