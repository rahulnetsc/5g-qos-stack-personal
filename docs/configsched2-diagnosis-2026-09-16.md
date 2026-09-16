# ConfigSched2, diagnosed with the decision trace (2026-09-16)

First use of `ConfigSched2.decision_sink`. Short runs, `gt31` (G5's video
scenario) at N = 6 and N = 10, seed 1097657231, 3 s horizon, cap 4, on the
deployed cell. **This is a diagnosis, not a result** — it says which term binds,
so a constraint can be aimed rather than guessed (`config-scheduler-handoff.md`
§8e).

## 1. What binds is the PER-SLOT UE CAP, not PRBs and not the rate budget

Every UL unit considered, by outcome:

| N | granted | **cap_skipped** | prb_exhausted | mapped_visit_missed |
|---|---|---|---|---|
| 6 | 72 % | **11 %** | 10 % | 7 % |
| 8 | 56 % | **30 %** | 5 % | 9 % |
| 10 | 45 % | **37 %** | 6 % | 12 % |

As load rises `cap_skipped` more than triples while `prb_exhausted` **falls**.
`rate_budget_bound` is 250–300 across the whole run and `visit_budget_bound` is
**0 at every load**. The cell is not short of PRBs; it is short of DCIs.

## 2. The camera's contract wins the rank and buys nothing at the cap

| | camera N=6 | camera N=10 | every other UE, N=10 |
|---|---|---|---|
| granted | 87 % | **55 %** | 44 % |
| cap_skipped | 2 % | **35 %** | 37 % |

At N=6 the camera is protected (2 % cap-skipped). At N=10 it is cap-skipped at
**35 %, statistically the same as the 37 % every other UE suffers.** `_rank`
puts contracted flows first, but the cap is applied in `_place` per DISTINCT UE
*after* the sort (`config_sched2.py:532`) — so ranking first only helps if the
camera is inside the first `cap` units, and under load it often is not.

At N=10, `cap_skipped_leftover` is **8 262** against `cap_skipped_promised`
2 591: most DCIs lost to the cap go to traffic with **no plan claim at all**.

## 3. `visit_budget_bound` NEVER FIRES, and that is the finding

It reads 0 at N = 6, 8 and 10. The mechanism is reachable
(`config_sched2.py:340`) — it simply never binds, because **the plan's visit
budget is a WINDOW TOTAL while the constraint that actually binds is PER-SLOT
CONCURRENCY.** A window-total budget can be perfectly satisfiable while the
per-slot "at most `cap` distinct UEs in this slot" constraint is violated
constantly; they are different constraints, and the outer problem only models
the first.

**This is the exact shape §8e exists for:** the requirement that decides the
outcome is not represented in the optimisation, so the realisation absorbs it
as an after-the-fact skip, with no visibility of what it cost.

## 4. The second lever: the camera crumbs even when it is granted

`crumb_qfi2` is 927 at N=6 and 1 382 at N=10, short by **814 kB and 902 kB**.
A crumb is a grant smaller than the flow's want — by the module's own comment
it "settles nothing". The cause is the sizing term
(`config_sched2.py:549`): `per_visit_cap` is **a cap-th of the slot, always**,
sized for the worst case of `cap` units due simultaneously. When fewer units
are actually due the camera is still held to a quarter slot, and its frame
fragments into crumbs. `floors_unmet` rises 0 → 320 between N=6 and N=10.

## 5. Two encodings to try, classified before building (§8e)

1. **Per-slot concurrency as an outer constraint — expected TYPE 1**
   (separability and the polymatroid region preserved, greedy stays exact).
   The harmonic/Kraft track construction already makes mapped visits land on
   disjoint residue classes; what defeats it is that unplanned and leftover
   units compete for the same DCIs in the realisation (8 262 leftover skips).
   Encoding the cap as a per-slot claim the plan owns — leftover traffic may
   only take a DCI no mapped visit claims in that slot — puts the binding
   constraint where the solver can trade it.
2. **Size to actual contention, not worst-case contention — expected TYPE 2**
   (still a knapsack per direction, but the sizing quantity changes, so the
   ordering derivation must be re-stated). `per_visit_cap` should reflect the
   units actually due in that slot rather than a fixed cap-th.

**Registered before building:** (1) should move `cap_skipped_promised` and
`mapped_visit_missed` down and leave `prb_exhausted` roughly flat; (2) should
move `crumb_qfi2` and `crumb_short_bytes_qfi2` down and `floors_unmet` with
them. If (1) does not move `cap_skipped_promised`, the per-slot claim is not
what is being lost and the diagnosis above is wrong.

## 6. Method note

The first version of this diagnostic reported an EMPTY camera breakdown: it
parsed `camera_flow_key`'s `"ue1_qfi2"` string as a tuple and matched nothing,
printing `{}` — an empty selection wearing a measurement. It was caught by a
`matched == 0` gate that raises instead of reporting, and the numbers above are
from the corrected run (1 893 and 2 291 camera decisions matched).

---

## 7. Encoding E1 REGISTERED BEFORE BUILDING (2026-09-16)

Per the user's standing instruction — build the requirement before running, so
a result never has to be walked back — this section is written **before** the
arm is measured.

### 7.1 The defect, stated precisely

`_resolve_tier1` charges every visit against `visit_budget = cap * s_dir`, a
**window total**. But a flow's visits are realised as a harmonic track of period
`T = _pow2_floor(W_dir // n_i)` (`_assign_periods_and_tracks`), and the
constraint that must hold is the **density** one, `sum(1/T) <= cap`.

Those two budgets are NOT the same, and the gap is the power-of-two rounding:
`_pow2_floor` rounds `T` **down**, which rounds a flow's realised visit rate
**up**, by up to 2x. So a plan can satisfy `sum n_i <= cap * W_dir` and still be
infeasible in density. When that happens `_assign_periods_and_tracks` repairs it
*after the fact* — lengthening periods (`period_over_deadline`), dropping
best-effort tracks (`track_dropped_best_effort`), or leaving a flow unplaced
(`track_unplaced`) — and `plan.n_visits` then disagrees with the track the flow
actually got, while `bytes_per_visit` was already computed from the larger
number.

**That is why `visit_budget_bound` reads 0 at every load while `cap_skipped` is
35–37 %:** the budget being checked is not the constraint that binds.

### 7.2 The encoding

Charge visits against a **density budget of `cap`**, using the same rounded
harmonic cost the realisation will actually pay, at both allocation sites (the
contract floors, and the residual visits). New counter `visit_density_bound`
fires when the density budget refuses visits.

**Structure class: TYPE 1 — separable, greedy stays exact.** The feasible set is
still "each flow picks a visit count, subject to one additive budget"; only the
per-unit cost changes from 1 to `1/T(n_i)`. The cost is a non-decreasing step
function of `n_i`, so the greedy still takes flows in contract order and stops
at the budget. No solver change, no coupling between directions.

### 7.3 Registered expectations, and what falsifies each

| # | expectation | falsified by |
|---|---|---|
| 1 | `visit_density_bound` > 0 at N >= 8 | reading **0** — the encoding would be inert, the same could-not-fail defect as the first G6 floor |
| 2 | `track_dropped_best_effort`, `period_over_deadline`, `track_unplaced` all FALL | any of them rising — the plan would still be overcommitting |
| 3 | `cap_skipped_promised` and `mapped_visit_missed` fall | no movement — then the lost DCIs were never the plan's overcommitment and §1–§3's diagnosis is WRONG |
| 4 | `prb_exhausted` roughly flat | a large rise — the budget would have been re-aimed at the wrong resource |
| 5 | group C (G5) improves: admissible fleet and/or frame age at N=10 | no movement, which would mean the cap was not what bound the camera |
| 6 | groups A/B/D/E/F do not regress (the contract in `guarantee-groups-2026-09-16.md` section 3) | any regression — then it is judged exactly as D1 was, and D1 was rejected for precisely this |

**Expectation 3 is the load-bearing one.** If the DCIs lost to the cap do not
fall, the whole diagnosis in sections 1–3 is refuted and the encoding should be
reverted regardless of what else improves.

### 7.4 Build constraints

Default off, so `ConfigSched2` stays byte-identical when the flag is unset —
verified by digest, as the decision sink was. The tuned arm gets its own name so
the frozen arm keeps meaning what the campaign measured.

---

## 8. Encoding E2 REGISTERED BEFORE BUILDING (2026-09-16)

Written before the arm exists, and before E1's full measurement has returned.

### 8.1 Why E1 makes E2 possible, and why E2 alone would be wrong

`_place` sizes every visit against

    per_visit_cap = (prb_count // cap) * se // 8

— **a cap-th of the slot, always.** The module's own comment says why: four
cameras due in one slot, each sized to a whole slot, take 108 PRBs of a
106-PRB slot and three of them become crumbs. The clamp is a defence against
the plan overcommitting a slot.

**E1 removes the thing it defends against.** Once visits are charged the
density they actually occupy, the plan can no longer map more than `cap` units
onto one slot — that is exactly what `sum(1/T) <= cap` means. So the
worst-case clamp is defending against a state the outer problem now excludes,
and it costs the camera its frame on every visit.

**This ordering is load-bearing: E2 must not be built without E1.** Relaxing
the clamp while the plan can still overcommit is the crumb cascade the comment
records, which the first build measured at 32 992 missed visits.

### 8.2 The encoding

A promised visit carries **its plan share** (`plan.bytes_per_visit`, already
computed by the outer problem against the density budget), bounded only by what
is actually left in the slot and by the flow's own backlog — not re-clamped to
a fixed cap-th. The realisation stops overriding a decision the optimisation
already made.

**Structure class: the outer problem is UNCHANGED.** E2 removes a
realisation-side override, so the greedy's exactness is untouched. It is the
second half of the same idea: the plan decides, the realisation executes.

### 8.3 Registered expectations, and what falsifies each

| # | expectation | falsified by |
|---|---|---|
| 1 | `crumb_qfi2` and `crumb_short_bytes_qfi2` fall **below the ConfigSched2 baseline**, not merely below E1's | no fall — then the clamp was never what fragmented the camera, and §4 of this document is wrong |
| 2 | group C (G5) improves: admissible fleet and/or frame age p95 at N = 10 | no movement — the camera's loss was not sizing |
| 3 | the per-slot cap assertion in `allocate()` never fires | it raising — E1's density bound is not delivering the concurrency guarantee E2 relies on, which would invalidate §8.1 |
| 4 | `prb_exhausted` rises somewhat (visits are larger) but `granted` does not fall | `granted` falling materially — larger visits would be starving later units |
| 5 | groups A/B/D/E/F do not regress | any regression, judged exactly as D1 was |

**Expectation 3 is the structural one.** It is the direct test of whether E1's
outer-problem constraint actually holds in the realisation; if it fires, E2 is
reverted and E1's claim is re-opened.
