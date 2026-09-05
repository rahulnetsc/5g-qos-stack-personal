# Landing the Tier-1 objective scaling — the re-baseline as a decision

**Registered 2026-09-05 BEFORE the capture and before any guarantee is
re-run.** `docs/tier1-lp-analysis-2026-09-05.md` is the evidence; this is the
decision and the predictions it will be scored against.

**The framing, and it is the commit message: this replaces a numerically
wrong answer with the right one, deliberately. Not "this changes nothing."**

---

## 1. Why this is defensible, in one place

1. **The instability is pure numerics.** Column permutation is exactly
   argmax-invariant, and vertex disagreement under it falls **88.6 % → 1.8 %**
   when the objective is scaled. Scaling cannot change the mathematics, so
   what it removed was never mathematics.
2. **The greedy is exact by construction** — the problem separates by
   direction into a continuous knapsack with a concave two-piece value
   (verified against `ia_p5g_scheduler.c:1027-1038`). Measured: **never worse
   than the shipped solve, strictly better on 57 of 856, always feasible.**
   The shipped call leaves objective value on the table on 6.7 % of solves.
3. **Three independent argmax-invariant computations agree.** Direct-HiGHS
   warm, direct-HiGHS cold, and objective scaling all give `ue9_qfi9`
   `throughput_bps` **5,340,428**; only the shipped path returns 5,521,232.
4. **The choice of K is a plateau interior, not a fitted value.** At LP level
   agreement with the exact greedy is 98.8 % flat from K=1e3 to K=1e12; at
   corpus level K=1e3 and K=1e6 give **byte-identical** corpora. §2 maps the
   corpus-level plateau edges and picks the geometric interior.

**What this is NOT.** It is not a speedup — the LP stays 43.5 % of TwoTier's
driver. It is not the missing `glp_scale_prob` (that is a *matrix* treatment,
2.83 orders, and lands separately and after). It is not free — 838 corpus
values move.

---

## 2. K, and why that K

| K | agrees with exact greedy | stable under permutation |
|---|---|---|
| 1 (shipped) | 10.3 % | 10.7 % |
| 1e1 | 72.2 % | 66.6 % |
| 1e2 | 95.6 % | 93.5 % |
| **1e3 … 1e12** | **98.8 – 99.5 %** | **98.8 – 99.5 %** |

The corpus-level plateau is narrower than the LP-level one (small LP
differences compound over a run), so the corpus map decides. **K is chosen as
the geometric interior of the corpus-identical band**, recorded in §6 with
the neighbours that agree and the ones that do not. A value at a plateau
edge would be a fitted constant; one in the interior is not.

---

## 3. What is ALREADY MEASURED vs what is PREDICTED

Stated separately, because I have already run the corpus under scaling and
it would be dishonest to present its shape as a prediction.

**Already measured — this is an ACCEPTANCE CONDITION, not a forecast. The
capture must reproduce it exactly or it is not taken:**

- **838 values move.**
- **All 838 are TwoTier.** PF and Reservation are byte-identical.
- Four records only: `study1/overload_mult{1.0,1.5,2.0}` and
  `study3/latency_bound` — the records where Tier-1 re-solves.
- 827 `flows` fields, 11 `system` fields.

**The control that makes this shape meaningful:** PF and Reservation do not
call `solve_tier1` at all. **If either moves, a boundary was crossed and the
change is not what it claims to be** — that is a stop condition, not a
detail.

---

## 4. THE PREDICTIONS — guarantee verdicts, genuinely unknown

Magnitude of the change on TwoTier: a few percent (the worked example is
−3.3 % on one flow's throughput). So the prediction is driven by **margin**,
not by direction.

**Hard control, all guarantees:** *PF and Reservation verdicts must be
UNCHANGED everywhere.* Neither arm touches Tier-1. Any movement is a defect.

| G | current verdict | prediction | why |
|---|---|---|---|
| **G1** | TwoTier M01 p98 **94.51 ms** vs 100 ms bound | **AT RISK — the one I would bet on moving** | only **5.5 % margin**, and the change is of that order |
| **G3** | TwoTier M20 +21.34 % [−2.81, +50.02] INCONCLUSIVE | **holds** — still inconclusive | the interval is 53 points wide; a few percent cannot resolve it |
| **G4** | duty 0.1 separation, TwoTier−PF +5.86 [+4.50, +7.25] | **holds** | interval excludes zero by 4.5; duty 0.5/1.0 stay null |
| **G5** | TwoTier **0/10** under attach path, min M05 **0.9932** | **AT RISK** | margin above the 0.99 bound is **0.0032** — thinner than G1's |
| **G6** | TwoTier worse; M02 clause 2 FAIL | **holds (still fails)**, counts move | already failing; a few percent will not restore it |
| **G8** | both conjuncts fail on both QoS arms at n=10 | **holds (still fails)** | failure is large, not marginal |
| **G10** | PF 8 / Reservation 4 / **TwoTier 4** | **TwoTier's number may move; PF and Reservation MUST NOT** | admissibility is a threshold on TwoTier's own targets |
| **G11 C1** | 300 windows/arm, **0 failing** | **holds** | zero failures with no near-misses recorded |
| **G12** | TwoTier `[4,2]` 5/10, `[2,4]` 4/10, one degenerate `[2]` | **TwoTier's counts move; PF's `[4,2]` 10/10 MUST NOT** | first-violation order is order-sensitive by construction |

**Scored honestly afterwards, misses recorded as prominently as hits** —
this project's own rule, and WP4's prediction exercise is the precedent for
what happens when only the hits get cited.

---

## 5. The capture discipline

Same as the M03 schema re-baseline:

1. The `--check` diff must have **exactly the shape in §3**. Different shape
   → do not capture, investigate.
2. `--capture` is run with the justification **already written here**, and
   the commit message states which numbers moved and why.
3. The full suite must pass **before** the capture, so a suite failure
   cannot hide inside a re-baseline.

---

## 6. Results

**K = 1e4.** The corpus-level plateau is **exactly [1e3, 1e6]** — four
decades byte-identical — differing at 1e2 (849 values) and at 1e7 (864),
1e8 (836) and 1e9 (866). 1e4 is in the interior; 1e3, 1e5 and 1e6 all give
the identical corpus, so **the specific decade is not load-bearing**, which
is the whole point of choosing a plateau interior rather than fitting.

**The capture discipline was met in order:** suite **1063 passed** first,
then the `--check` diff was verified against §3 and matched **exactly** —
838 values, all TwoTier, four records, 827 `flows` / 11 `system`, and
byte-identical to the pre-registered K=1e4 diff. **PF and Reservation did
not move**, which is the control that says no boundary was crossed. Only
then was `--capture` run.
