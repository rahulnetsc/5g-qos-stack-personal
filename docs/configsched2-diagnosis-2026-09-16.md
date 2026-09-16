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

---

## 9. E1 MEASURED, 9 steps rc 0 (`sweeps/cs2-increments/e1/`, against `inc9`)

Scored against the expectations registered in §7.3 **before** the build.

| # | registered | outcome |
|---|---|---|
| 1 | `visit_density_bound` > 0 | **MET** — 616 at N=8, 988 at N=10; the encoding is not inert |
| 2 | track repairs fall | **MET** — `track_dropped_best_effort` 129 → 0 at N=8, others already 0 |
| 3 | `cap_skipped_promised` and `mapped_visit_missed` fall | **PARTLY MET** — total `cap_skipped` 10 369 → 6 431 at N=10 (−38 %) and promised 2 591 → 2 251, but `mapped_visit_missed` rose at N=10 |
| 4 | `prb_exhausted` roughly flat | **NOT MET** — 1 774 → 2 454, pressure moved off DCIs onto PRBs |
| 5 | group C (G5) improves | **MET, strongly** — admissible fleet **6 → 7**, load knee 1.0 → 1.3; gt32 ×1.1 3/0/4 at 137 ms → **10/10/10 at 33 ms**, ×1.2 0/0/2 at 146 ms → **10/10/10 at 38 ms**; gt31 N=7 52 → 29 ms |
| 6 | no regression in A/B/D/E/F | **FAILED** |

**Where it fails, and it is severe.** Group B collapses: G3 `part3_pass`
`10 10 10 10 10 7 0 0 0` → `9 3 2 3 3 1 0 0 0`, **boundary 10 → None**, and
telemetry p98 goes 8.5 → 84.25 ms at N = 2 — the heartbeat is damaged at every
fleet size, not only under load. Group D's clause 1 and 3 follow: A-telemetry
p98 57.8 → 97.8 ms, A-camera p98 46.9 → 106.0 ms, B-telemetry p98 6.0 → 58.2 ms
(clause 2 improves, 1.04x → 0.88x). Group A, E and F are flat to slightly
better (G2 cap-2 missed 291 → 268; G6 UL A/B 217/216 of 220 → 223/226 of 227).

**So E1 is NOT keepable on its own** under the regression contract — the same
judgement D1 got, and for the same reason.

**The registered hypothesis for the G3 collapse** (to be tested, not assumed):
it is the crumb effect §4 named and §8 exists to fix. E1 grants fewer visits
for the same bytes while `_place` still clamps each visit to a cap-th of the
slot, so a 300 B heartbeat is split across visits — exactly the mechanism that
made increment 2 fail (`bytes_per_visit = ceil(r_i / n_i)` halving a message).
If that is right, **E1+E2 should restore G3 while keeping E1's group-C gain.**
If G3 stays broken under E1+E2, the density budget is starving short-period
contracted flows directly and E1 needs importance-ordered shedding instead —
which is the `degrade-by-importance` requirement in
`guarantee-groups-2026-09-16.md` §7 expressed inside the constraint.

---

## 10. E1+E2 MEASURED — the registered hypothesis is REFUTED (`sweeps/cs2-increments/e2/`)

9 steps rc 0, `ConfigSched2X2` against `inc9` (baseline) and against `e1`.

**§9 predicted:** *"If that is right, E1+E2 should restore G3 while keeping E1's
group-C gain. If G3 stays broken under E1+E2, the density budget is starving
short-period contracted flows directly."*

**G3 stays broken.** part-3 `10 10 10 10 10 7 0 0 0` → `9 1 1 2 1 1 0 0 0`,
boundary **10 → None**, telemetry p98 8.5 → 87.25 ms. Against E1 *alone* it is
marginally WORSE (part-3 `9 3 2 3 3 1` → `9 1 1 2 1 1`). **So the crumb
explanation is refuted**, even though E2 does what it was built to do — camera
crumb short-bytes fell 902 kB → 192 kB on the short run, and G5's load ramp is
transformed.

By the registration's own terms the surviving explanation is that **the density
budget starves short-period contracted flows directly**, and the fix is
importance-ordered shedding *inside* the constraint rather than more sizing work.

### 10.1 E2's own scorecard (§8.3), against E1

| # | registered | outcome |
|---|---|---|
| 1 | camera crumbs fall below the ConfigSched2 baseline | **MET** — short-bytes 902 760 → 191 510 at N=10, 618 068 → 44 172 at N=8 |
| 2 | group C improves | **MET in the load ramp, MIXED on the fleet axis** — gt32 ×1.1 3/0/4 at 137 ms → 10/10/10 at 35 ms, ×1.5 0/0/2 → 3/0/10; gt33 15 2/0/0 at 139 ms → 10/9/4 at 37 ms; but gt31 N=8 10/9/4 at 42 ms → 9/4/1 at 68 ms and N=10 1/0/0 → 0/0/0 |
| 3 | the per-slot cap assertion never fires | **MET** — E1's concurrency guarantee holds in the realisation |
| 4 | `granted` does not fall materially | **NOT MET** — `mapped_visits_served` 8 962 → 5 143, `visits_stamped` 15 901 → 12 247 |
| 5 | no regression in A/B/D/E/F | **FAILED** — G3 as above; G7 clause 1 p98 57.8 → 99.0 ms and clause 3 6.0 → 49.2 ms; **G10 admissible 10 → 8**, which E1 alone did NOT cost |

### 10.2 Verdict

**Neither E1 nor E1+E2 is keepable under the regression contract.** Both are
judged exactly as D1 was. What is established, and worth keeping as knowledge
rather than code:

* The binding constraint really is the per-slot DCI cap, and encoding it in the
  outer problem really does move group C — G5's admissible fleet 6 → 7 and its
  load knee 1.0 → 1.3 are the largest group-C gains any increment has produced.
* The cost is group B, and it is not a sizing artefact.
* E2 additionally costs group E (G10 admissible 10 → 8), so the two changes are
  not independent and E2 must not be carried forward on its own.

**Next, registered:** E3 — when the density budget binds, shed in IMPORTANCE
order (best-effort first, then longest-PDB contracted), never uniformly in row
order. That is `guarantee-groups-2026-09-16.md` §7's degrade-by-importance
requirement expressed inside the constraint, and it is the first encoding whose
motivation is a measured starvation rather than a structural argument.

---

## 11. WHY E1 BREAKS GROUP B — measured, and it is not starvation by demand

Traced at the real axis point (gt22, **N = 6**, UL; `W_dir` = 120, cap 4). An
earlier attempt at this ran at N = 2, which is **not on G3's axis**
(`[4, 6, 7, 8, 10, 12, 14, 16, 24]`) and where E1 is provably inert
(`visit_density_bound` = 0, byte-identical counters); that run was discarded.

**The heartbeat gets ONE visit per window on both arms. What changes is its
PERIOD.**

| flow | baseline `ConfigSched2` | E1 `ConfigSched2X1` |
|---|---|---|
| telemetry `qfi1` x2 | **T = 32** (density 0.031) | T = 64 (0.016) |
| telemetry `qfi1` x4 | T = 64 | T = 64 |
| camera `qfi2` x6 | T = 2 (0.5 each) | T = 2 (0.5 each) |
| best-effort `qfi9` | T = 8 each (0.125) | **T = 2 (0.5), 4, 8, 32, none** |
| **total density** | **4.000** | **4.000** |

Both saturate the cap exactly. The difference is **who holds it**: under E1 a
single best-effort `qfi9` flow occupies **density 0.5 — the same share as a
contracted camera** — while every contracted heartbeat sits at T = 64 (~53 ms
between visits against a 100 ms PDB, and a measured p98 of 87–97 ms).

### 11.1 The mechanism, and it is the opposite of what §9 assumed

Telemetry never *asks* for more: its `r_i` is one 300 B message, so
`need = ceil(r_i / per_visit_max)` = 1 visit, and the residual loop gives it
one. Its period is then `_pow2_floor(W_dir // 1)` = 64.

What shortened it on the baseline was **the repair path E1 removed**. The
baseline deliberately overcommits, and `_assign_periods_and_tracks` then
(a) lengthens periods **best-effort first, densest first**, and (b) spends any
spare density **shortening contracted periods, shortest PDB first** — halving
the heartbeat 64 → 32. E1 makes the plan exactly feasible, so there is no
overcommit to repair, **and the repair was the only thing doing
importance-ordered shedding.**

**E1 did not starve the heartbeat by taking its bytes. It deleted the mechanism
that was protecting its deadline.**

---

## 12. Encoding E3 REGISTERED BEFORE BUILDING

**The encoding.** When the density budget binds, allocate in IMPORTANCE order:
every contracted flow first receives enough visits that its period meets its
own deadline bound (`T <= pow2_floor(pdb - margin)`), shortest PDB first; only
the density left over goes to best-effort. Best-effort is shed first, by
construction, instead of by a repair pass that E1 removed.

This is `guarantee-groups-2026-09-16.md` §7 — *critical flows held as far as
capacity allows, non-critical degraded gracefully* — expressed as a constraint
rather than left to emerge. It is the first encoding here motivated by a
measured starvation rather than a structural argument.

**Structure class: TYPE 1.** Still one additive density budget with a
non-decreasing per-flow cost; only the ORDER of claims changes, which is what a
greedy over a polymatroid is already free to choose. Greedy stays exact.

### 12.1 Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | at gt22 N=6, contracted telemetry period returns to **T <= 32**, and no best-effort flow holds density 0.5 | telemetry still at T = 64 — then the period is not set where §11 says it is |
| 2 | G3 part-3 boundary returns to **>= 10** and telemetry p98 back under ~35 ms | no recovery — then the period is not what drives telemetry p98, and §11's mechanism is wrong |
| 3 | E1's group-C gain is RETAINED: G5 admissible fleet 7, load knee >= 1.3 | falling back to 6 / 1.0 — then the group-C gain was bought by the heartbeat and the two cannot be had together |
| 4 | best-effort throughput FALLS (this is the intended trade, not a regression) | it rising — the shed order would not be taking effect |
| 5 | G10 admissible stays 10, G7 clause 1 no worse than baseline | either regressing |

**Expectation 3 is the one that decides whether this whole line of work
survives.** If group C's gain cannot coexist with group B's deadline, then the
per-slot cap is a genuine capacity wall on this cell and the honest answer is
that the camera and the heartbeat are competing for a resource neither
scheduling nor encoding can create.

---

## 13. E3 MEASURED (`sweeps/cs2-increments/e3/`), and the remaining mechanism

9 steps rc 0, `ConfigSched2X3` against `inc9`. Scored against §12.1.

| # | registered | outcome |
|---|---|---|
| 1 | telemetry back to T <= 32, no best-effort at 0.5 | **MET** (checked before the run) |
| 2 | G3 part-3 boundary >= 10, p98 under ~35 ms | **PARTLY** — boundary None → **4**, not 10; p98 still 76–98 ms |
| 3 | group C retained (fleet 7, knee >= 1.3) | **EXCEEDED** — admissible fleet 6 → **8**, knee 1.0 → 1.3 |
| 4 | best-effort throughput falls | met (the intended trade) |
| 5 | G10 admissible stays 10; G7 clause 1 no worse | **SPLIT** — G10 **10 held**; G7 clause 1 p98 57.8 → 96.5 ms, clause 3 6.0 → 53.0 ms, both worse |

### 13.0 The remaining groups, and one expectation FALSIFIED

| group | statistic | baseline `ConfigSched2` | E3 | verdict |
|---|---|---|---|---|
| **A (G2)** | cap-4 missed STOPs | 202/18300 | **186/18300** | win |
| **A (G2)** | cap-2 missed STOPs | 291/18300 | **239/18300** | win |
| **D (G6)** | UL flood part A/B | 217/216 of 220 | **223/222 of 225** | win |
| **D (G6)** | camera window floor | 1/3 | 3/5 | win |
| **F (G9)** | informative cells | 12 of 12 | **12 of 12** | held |
| **E (G12)** | clause 4 | 10/0/0 | 10/0/0 | held |
| **E (G12)** | order agreement | 9/10 | **10/10** | win |
| **E (G12)** | telemetry M02 at ×1.8/×2.0 | 0.025/0.071 | **0.100/0.284** | regression |
| **E (G12)** | background Mbps at ×2.0 | 6.5 | **9.0** | **expectation 4 FALSIFIED** |

**§12.1 expectation 4 said best-effort throughput would FALL** — that was the
intended trade of shedding best-effort first. It ROSE, 6.5 → 9.0 Mbps, and
telemetry's PDB-violation rate rose with it. The reason is that E1 frees DCIs
(`cap_skipped` −38 %), so more traffic of every class gets through; E3 changes
the *order* of claims on density but does not reduce the total carried. The
registered expectation confused "shed best-effort first when the budget binds"
with "carry less best-effort overall", and only the first is what E3 does.

**Group B and E's telemetry regression share one cause**, identified in §13.1
below — the heartbeat's share halved to 150 B — so both should move together
under E4, and if only one moves the explanation is incomplete.

**Group C is now the best any increment has produced** — admissible fleet 8
against the baseline's 6 and E1's 7, with the load ramp transformed (gt32 ×1.1
and ×1.2 at 10/10/10, ×1.3 at 10/6/10) — and **group E is held at 10**, which
E2 could not do. Group B is recovered from "no boundary at all" to 4, and
group D is still regressed.

### 13.1 Why group B is still broken, traced to the line

The §11 mechanism was right and E3 fixed it: the heartbeat's period is back to
T = 32. But the trace shows a SECOND mechanism that importance-ordering
introduced:

| | baseline | E1 | E3 |
|---|---|---|---|
| telemetry `qfi1` | n_visits **1**, bpv **300** | n_visits 1, bpv 300 | n_visits **2**, bpv **150** |

**The 300 B heartbeat is now split across two visits of 150 B.** That is
verbatim the failure this project already measured and recorded as increment 2
(`docs/campaign-cell-2026-09-16-linux.md`): *"two visits per window halve the
heartbeat's visit to 150 B for a 300 B message, so every message is split
across visits 50 ms apart, delivery rate = arrival rate with no slack, and one
missed visit grows the backlog without bound."*

The cause is that `bytes_per_visit = ceil(r_i / n_i)` divides the window's
bytes by the FINAL visit count — and E3 raised that count for a **deadline**
reason, not a byte reason. A visit added to meet a deadline should still be
able to carry a whole message; instead it halved the share.

**This is why E2 does not fix it either**: E2 relaxes the per-slot clamp in
`_place`, but `want` is still bounded by `plan.bytes_per_visit`, which is
already 150 before `_place` is reached.

---

## 14. Encoding E4 REGISTERED BEFORE BUILDING

**The encoding.** Size a visit by the flow's BYTE need, not by a visit count
that a deadline inflated: `bytes_per_visit = ceil(r_i / n_bytes)` where
`n_bytes` is the byte-driven visit count before the deadline floor is applied.
The flow still gets its deadline-driven visits; each one may simply carry a
whole message rather than a fraction of one.

**Structure class: TYPE 1.** Neither the budget nor the feasible region moves —
only the reported share of an already-chosen allocation. Greedy stays exact.

### 14.1 Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | at gt22 N=6, telemetry reads n_visits 2 with **bpv 300** (not 150), period still T = 32 | bpv staying 150 — the divisor is not where §13.1 says it is |
| 2 | G3 part-3 boundary returns to **>= 10** | no recovery — then message splitting is not what is costing group B, and §13.1 is wrong |
| 3 | group C retained: admissible fleet **8**, knee >= 1.3 | falling back — the gain would depend on the splitting |
| 4 | G10 admissible stays 10 | regressing |
| 5 | G7 clause 1 recovers toward baseline as the telemetry share is restored | no movement — then G7's clause 1 has a separate cause (and note it is an UPPER BOUND on harm anyway, having no control run) |

**Expectation 2 decides it.** If G3 recovers to 10 while group C holds at 8,
then E1+E3+E4 is the first increment to move a group without paying for it
elsewhere, and it becomes the candidate. If not, the honest conclusion is that
on this cell the camera and the heartbeat compete for the per-slot DCI cap and
no encoding creates capacity.

---

## 15. X5 (E1+E3+E4) MEASURED — expectation 2 FALSIFIED, and the E-series verdict

9 steps rc 0 (`sweeps/cs2-increments/e5/`), `ConfigSched2X5` against `inc9`.

| # | registered (§14.1) | outcome |
|---|---|---|
| 1 | telemetry bpv 300 not 150, T = 32 | **MET** (checked before the run) |
| 2 | **G3 part-3 boundary returns to >= 10** | **FALSIFIED — boundary 10 → None**, *worse* than E3's 4 |
| 3 | group C retained at fleet 8 | **MET** — admissible **8**, knee 1.3, gt33 ×5 98 → 67 ms, ×15 139 → 99 ms |
| 4 | G10 admissible stays 10 | **MET** — 10 held, M08 at N=10 0.970 → 0.973, N=12 0.781 → 0.811 |
| 5 | G7 clause 1 recovers | **NOT MET** — A telemetry p98 57.8 → 98.0 ms (clause 3 does improve, 6.0 → 42.0; clause 2 1.04 → 0.97) |

**§13.1's mechanism is refuted on its own registered terms.** E4 demonstrably
fixed the message splitting — telemetry reads `bpv 300` at gt22 N=6, confirmed
before the run — and G3 got **worse**, not better. Message splitting was
therefore not what was costing group B.

### 15.1 The E-series trade, all measured on the same seeds

| arm | G3 part-3 boundary | G5 admissible fleet | G5 knee | G10 admissible | G2 cap-4 missed |
|---|---|---|---|---|---|
| `ConfigSched2` (baseline) | **10** | 6 | 1.0 | 10 | 202 |
| E1 (density budget) | None | 7 | 1.3 | 10 | — |
| E1+E2 (plan-share sizing) | None | 7 | 1.3 | **8** | — |
| E1+E3 (importance order) | **4** | **8** | 1.3 | 10 | 186 |
| E1+E3+E4 (byte-sized visits) | None | **8** | 1.3 | 10 | **181** |

**No variant dominates the baseline.** Every encoding that wins the camera
loses the heartbeat, and the three successive attempts to recover group B —
sizing (E2), claim order (E3), share (E4) — each fixed the mechanism it
targeted, verified by trace before the run, and none recovered G3.

### 15.2 What is established, and what is not

**Established.** The per-slot DCI cap is the binding constraint (§1–§2);
encoding it in the outer problem is worth a large, reproducible group-C gain
(admissible fleet 6 → 8, load knee 1.0 → 1.3, the load ramp transformed) and
carries G2, G6, G12 order-agreement and G10's M08 with it.

**Not established, and NOT to be asserted:** that group B's loss is an
irreducible capacity wall. §14.1 offered that as the conclusion if expectation 2
failed, but the evidence does not support it yet — because the BASELINE achieves
G3 p98 8.5 ms with *worse* telemetry periods than any E-variant (two of six
heartbeats at T = 32, four at T = 64, against E3/X5's six at T = 32). A cell
where the loser has better periods and worse latency is not a capacity wall; it
is an unexplained mechanism, and the next step is to find it rather than to add
a fifth encoding against a guess (§8e's own rule).

### 15.3 THE MECHANISM, FOUND — the budget moved the cell from DCI-bound to PRB-bound

§15.2 said the loss was unexplained and must not be called a capacity wall.
Traced at gt22 N=6, it is neither a wall nor anything the three encodings
targeted:

| arm | UL grants issued | `cap_skipped` | `prb_exhausted` | `mapped_visit_missed` | telemetry p98 |
|---|---|---|---|---|---|
| `ConfigSched2` | **11 858** | 2 639 | 2 196 | 1 383 | **8.5–24.0 ms** |
| E1+E3 | 6 154 | **73** | 3 566 | 3 231 | 86.5–99.5 ms |
| E1+E3+E4 | 7 105 | 367 | 3 420 | 2 861 | 78.5–99.0 ms |

**The E-variants issue roughly HALF the uplink grants the baseline does.** The
density budget does exactly what it was built to do — `cap_skipped` collapses
2 639 → 73, a 97 % cut in DCIs lost to the per-slot cap — and the cell simply
moves to the other side of the trade: `prb_exhausted` rises and the total number
of grants nearly halves.

The chain is: a density budget constrains `n_visits`, so `bytes_per_visit =
r_i / n_i` grows, so each grant demands more PRBs, so a slot's PRBs run out
after fewer units. **Fewer, larger visits.** Telemetry's p98 is 8.5 ms → ~90 ms
because the heartbeat is served half as often in absolute terms — not because
of its period (E3 fixed that), not its share (E4 fixed that), and not the cap.

**The warning was in E1's own scorecard and was not heeded.** §9 recorded
expectation 4 as NOT MET: *"prb_exhausted 1 774 → 2 454, pressure moved off
DCIs onto PRBs."* That was the finding, one increment in; E2, E3 and E4 were
each aimed at a downstream symptom instead. **A registered expectation that
fails is information about the mechanism, not an acceptable cost of admission**
— this is the fourth instance in this project of carrying on past a miss.

**What this means for the formulation, and it is not a wall.** The outer problem
optimises against the DCI cap alone; the realisation is bounded by BOTH DCIs and
PRBs. A budget over one resource, tightened until it binds, silently loads the
other. The Rel-16-correct next encoding is therefore a **joint** constraint —
visits AND the PRBs those visits will demand — which is still separable per
direction and still a knapsack, so it stays TYPE 1. That is registered as the
next candidate and is deliberately NOT built here: three encodings in a row were
aimed at guesses downstream of an unheeded measurement, and the rule in §8e says
to diagnose first.

**Standing recommendation until then:** `ConfigSched2` (baseline) remains the
arm of record. The E-series flags stay in the tree, default off, each with its
measured result, exactly as the D1 flag did.

---

## 16. THE PRB MECHANISM, TRACED TO THE LINE (2026-09-16)

§15.3 established that the E-variants issue half the grants. This is why.
gt22 N=6, 3 600 UL slots, from the decision trace:

| | `ConfigSched2` | E1+E3 |
|---|---|---|
| units OFFERED per slot | 5.73 | 5.86 |
| units **GRANTED** per slot | **3.29** | **1.71** |
| PRBs used per slot | 92.85 | 95.92 |
| **PRBs per GRANT** (mean / median) | **28.2 / 26** | **56.1 / 52** |
| bytes per GRANT (median) | 1 443 | 2 100 |
| slots granting **zero** units | 13 | **151** |

**A cap-th of the 106-PRB slot is ~26 PRBs.** The baseline's grants sit exactly
there, so `cap` = 4 of them fit. Under E1 each grant takes ~52 — half a slot —
so only two fit. The same units are offered and the slot is equally saturated;
the cell simply serves half as many.

### 16.1 The defect: the clamp bounds a FLOW, the grant belongs to a UNIT

`per_visit_cap = (prb_count // cap) * se // 8` is applied per flow:

    want = min(reported, plan.bytes_per_visit, per_visit_cap)

but a **UL unit is `(ue_id, -1)` — every uplink flow of a UE shares ONE grant**
(`_place` groups them), and the grant is sized from their SUM:

    target = planned          # sum of `want` over the unit's flows
    prbs_needed = (target * 8 + se - 1) // se

So a UE carrying telemetry + camera + best-effort can legitimately request
**three cap-ths of the slot**, and nothing bounds the total. The baseline hides
this because its per-flow shares are small; E1 enlarges every share, so the sum
doubles and the arithmetic surfaces.

**This is latent in the baseline too**, not an artefact E1 introduced — E1 only
made it bind. It is the same family as the denominator rule in CLAUDE.md: the
quantity being bounded is not the quantity that is spent.

---

## 17. Encoding E5 REGISTERED BEFORE BUILDING

**The encoding.** Bound the **unit's total** request to a cap-th of the slot,
not each flow's share, so that `cap` units fit by construction — which is what
the clamp was always meant to guarantee.

**Structure class: TYPE 1**, and note it is independent of E1: it is a
realisation-side bound restoring the invariant the outer problem already
assumes (`cap` units share a slot). It is therefore measured BOTH standalone on
the baseline (`ConfigSched2X6`) and stacked (`ConfigSched2X7` = E1+E3+E4+E5),
because if it helps standalone it is a fix in its own right and must not be
credited to the density budget.

### 17.1 Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | PRBs per grant returns to ~26 median, units granted per slot to ~3.3 | no movement — then unit aggregation is not what inflates the grant and §16.1 is wrong |
| 2 | on the STACKED arm, G3 part-3 boundary recovers materially toward 10 | no recovery — then grant count is not what costs group B either, and the E-series should be closed for good |
| 3 | the stacked arm retains group C at admissible fleet 8 | falling back to 6 |
| 4 | G10 admissible stays 10 | regressing |
| 5 | on the STANDALONE arm, the baseline does not regress on any group | any regression — then the clamp is load-bearing as written and must not be changed |

**Expectation 5 is the one that protects the arm of record.** `ConfigSched2` is
currently the recommended arm; a change that improves the stack but damages the
baseline is not a fix, and the standalone measurement is what separates them.

---

## 18. X6 = E5 STANDALONE, MEASURED (`sweeps/cs2-increments/e6/`)

9 steps rc 0, `ConfigSched2X6` (unit-total cap on the OTHERWISE UNTOUCHED
baseline) against `inc9`. This is the arm that tests whether E5 is a fix in its
own right, so that it cannot be credited to the density budget.

| # | registered (§17.1) | outcome |
|---|---|---|
| 1 | PRBs/grant ~26, units/slot ~3.3 | **MET** — 25.5 and **3.59**, checked before the run |
| 5 | the baseline does not regress on any group | **NOT MET** — see below |

### 18.1 It is by far the closest any variant has come, and it still trades

**Wins**

| group | statistic | baseline | X6 |
|---|---|---|---|
| C (G5) | admissible fleet | 6 | **7** |
| C (G5) | load knee | 1.0 | 1.1 |
| C (G5) | gt33 ×5 / ×10 / ×15 frame age | 98 / 142 / 139 ms | **31 / 36 / 35 ms** |
| C (G5) | gt32 ×1.1 | 3/0/4 at 137 ms | **9/6/10 at 60 ms** |
| B (G3) | p98 median, first axis point | 8.5 ms | **3.75 ms** |
| B (G3) | short messages at N ≤ 12 | 1,0,0,2,1,0 | **all 0** |
| A (G2) | cap-2 missed STOPs | 291 | **266** |
| D (G6) | UL / DL part A/B | 217/216, 217/212 | **221/219, 223/219** |
| E (G10) | admissible fleet | 10 | **10 held** |
| F (G9) | informative cells | 12 | **12 held** |

**Regressions**

| group | statistic | baseline | X6 |
|---|---|---|---|
| B (G3) | part-3 boundary | **10** | 8 |
| B (G3) | worst silence at N = 14 | 297 ms | 479 ms |
| C (G5) | gt31 N = 8 | 10/9/4 at 42 ms | **6/1/0 at 122 ms** |
| D (G7) | clause 1 A telemetry p98 | 57.8 ms | 75.2 ms |
| E (G12) | telemetry M02 at ×1.8/×2.0, N=6 | 0.025/0.071 | **0.106/0.250** |
| E (G10) | M08 at N = 12 | 0.781 | 0.754 |
| A (G2) | cap-4 missed STOPs | 202 | 210 |

### 18.2 What separates it from the density-budget family

**E5 does not starve throughput the way E1 did.** G7's A-telemetry throughput
holds at **24 000 bps**, exactly the baseline, where every density-budget arm
dropped it to 18 240–18 960. That is the direct signature of the grants-per-slot
fix: the cell serves as many units as before, and more of them than the
baseline (3.59/slot against 3.29).

**So E5 is a real and independent improvement to the realisation** — it restores
an invariant the outer problem already assumes — and it is NOT a clean win:
it buys group C's fleet and G5's whole load ramp with G3's boundary (10 → 8),
one G5 fleet point, and G12's telemetry PDB rate.

**Verdict pending X7.** E5 standalone does not displace `ConfigSched2` as the
arm of record on its own. Whether the stack (E1+E3+E4+E5) does is exactly what
X7 measures: E5 restores the grant count that E1 destroyed, so the stack is the
first variant where the density budget's group-C gain and a working grant rate
coexist.

---

## 19. X7 = E1+E3+E4+E5 MEASURED, and the whole series as one table

9 steps rc 0 (`sweeps/cs2-increments/e7/`) against `inc9`.

| # | registered (§17.1) | outcome |
|---|---|---|
| 1 | PRBs/grant ~26, units/slot ~3.3 | **MET** (25.95 / 3.59, pre-run) |
| 2 | G3 boundary recovers materially toward 10 | **PARTLY** — **6**, the best of any density-budget variant, still short of 10 |
| 3 | group C retained at fleet 8 | **MET** — admissible **8**, knee **1.3** |
| 4 | G10 admissible stays 10 | **MET** — 10 held, M08 essentially identical to baseline |

### 19.1 Every variant, same seeds, same runners

| arm | G3 part-3 boundary | G5 fleet | G5 knee | G10 adm. | G2 cap-4 | G6 UL A/B | G9 |
|---|---|---|---|---|---|---|---|
| `ConfigSched2` (baseline) | **10** | 6 | 1.0 | 10 | 202 | 217/216 of 220 | 12 |
| E1 | None | 7 | 1.3 | 10 | — | — | — |
| E1+E2 | None | 7 | 1.3 | **8** | — | — | — |
| E1+E3 | 4 | **8** | 1.3 | 10 | 186 | 223/222 of 225 | 12 |
| E1+E3+E4 | None | **8** | 1.3 | 10 | 181 | 222/220 of 225 | 12 |
| E5 alone (X6) | 8 | 7 | 1.1 | 10 | 210 | 221/219 of 224 | 12 |
| **E1+E3+E4+E5 (X7)** | **6** | **8** | **1.3** | 10 | **176** | 222/221 of 226 | 12 |

### 19.2 The conclusion: this is a real trade curve, not a failed search

**No variant beats the baseline on group B, and no variant matches X7 on group
C.** The series did not fail to find a dominating point — it established that on
this cell there is not one, and mapped the frontier:

* **`ConfigSched2`** — heartbeat first. G3 boundary **10**, camera fleet 6.
* **X6 (E5 alone)** — the middle. G3 **8**, fleet 7, and the only variant that
  keeps G7's A-telemetry throughput at the baseline's 24 000 bps.
* **X7 (E1+E3+E4+E5)** — camera first. Fleet **8** with the load ramp
  transformed (gt33 ×5/×10/×15 frame age 98/142/139 ms → ~29 ms; gt32 ×1.1 and
  ×1.2 at 10/10/10), G2 cap-4 best of all at **176**, G10 and G9 held — bought
  with G3's boundary at 6.

**Which point is right is a product decision, not a scheduling one**, and it is
exactly the degrade-by-importance question in
`guarantee-groups-2026-09-16.md` §7: if the heartbeat is the safety-bearing
flow, the baseline wins and the camera is under-served by design; if the fleet
must carry 8 cameras, X7 is the arm and the heartbeat needs a CG (which
`docs/results-cg-2026-09-14.md` already shows closes the entire uplink
heartbeat class on every arm).

**That last point is the one to test next** and it is cheap: X7 **+CG**. CG
closed G3's class structurally on every arm measured, and G3 is the only group
X7 gives up. If the combination holds group C at fleet 8 while CG restores the
heartbeat, the trade dissolves — and nothing in the E-series could have shown
that, because every increment was run without CG.

**Until that is measured, `ConfigSched2` remains the arm of record** and every
E flag stays default-off with its result recorded.

---

## 20. G7 CLAUSE 1 RE-MEASURED WITH CONTROLS — the group-D verdicts above are CORRECTED

`sweeps/cs2-increments/g7_controls_2026-09-16.json`, N = 8, 10 seeds, each arm
run twice per seed: over-driven (2.1x MFBR) and its paired no-aggressor control.

| arm | A telemetry p98 | control | **aggressor-attributable** | A camera p98 | control | **attributable** |
|---|---|---|---|---|---|---|
| `ConfigSched2` | 57.8 | 48.8 | **+9.0** | 46.9 | 36.2 | **+10.7** |
| X6 (E5 alone) | 75.2 | 52.0 | **+23.2** | 50.9 | 37.4 | **+13.5** |
| **X7 (E1+E3+E4+E5)** | 97.8 | 97.0 | **+0.8** | 101.7 | 100.7 | **+1.0** |
| `ProtoRRageD2` | 74.0 | 66.2 | +7.8 | 32.8 | 33.9 | **−1.1** |

0 of 10 cells gated on every arm: no arm's victim is pre-broken at N = 8, so
all four rows are scoreable.

### 20.1 What this corrects

**§13, §15 and §19 recorded "G7 clause 1 regressed" for every density-budget
arm. On the containment question G7 actually asks, that is wrong.** X7's raw
97.8 ms is almost entirely its OWN latency under load — the aggressor adds
**+0.8 ms**. Ranked by containment, X7 is the **best** arm measured:

    X7 +0.8  <  ProtoRRageD2 +7.8  <  ConfigSched2 +9.0  <  X6 +23.2

and `ProtoRRageD2`'s camera is **−1.1 ms**, i.e. indistinguishable from no
aggressor at all.

**The corrected group-D readings:**

* **X7: containment is essentially perfect, standalone latency is worse.** Its
  group-D cost is real but it is a *capacity* cost, the same one group B pays,
  not a failure to contain a bad actor.
* **X6: the only arm whose containment genuinely degrades** (+23.2 against the
  baseline's +9.0), despite a better-looking raw number. Raw p98 ranked the two
  arms in exactly the wrong order.

**This is the decompose-before-attributing rule landing on my own results.** A
raw p98 under an aggressor sums two populations — the cell's own load and the
aggressor's marginal harm — and every E-series group-D verdict above quoted the
sum while claiming the second.

### 20.2 What does NOT change

X7's G3 boundary (6 against the baseline's 10) and G12's telemetry M02 are
measured without an aggressor, so no control qualifies them. **The group-B
trade in §19.2 stands exactly as written.** What changes is that group D is no
longer part of X7's cost: the frontier is heartbeat-versus-camera, and G7 is not
on it.

---

## 21. X7 +CG REGISTERED — written while the run is in flight, before any result

**Process note, recorded because it is a lapse against the standing rule.** The
`INC=e8 ARM=ConfigSched2X7+CG` run was launched BEFORE these expectations were
written. Every other increment in this document was registered first. This
section is written while the run is still executing and before any of its output
has been read, which preserves the scoring but not the discipline — noted so the
next one is not launched the same way.

### 21.1 Why this experiment

§19.2's frontier is heartbeat (G3) versus camera (G5), and **G3 is the only
group X7 gives up**. `docs/results-cg-2026-09-14.md` already measured that
restricted configured grants close the **entire uplink heartbeat class on every
arm** — G3 to 10/10 at every fleet size. If that holds under X7's density
budget, the trade dissolves: the camera keeps fleet 8 and the heartbeat is
rescued by a mechanism that is not the scheduler's to spend.

Nothing in the E-series could have shown this, because every increment ran
without CG.

### 21.2 Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | **G3 part-3 boundary recovers to >= 10** | staying at or below 6 — then CG does not rescue the heartbeat under a density budget, and the §19.2 trade is intrinsic to this cell |
| 2 | group C retained: G5 admissible fleet **8**, knee >= 1.3 | falling to 6–7 — CG is sized for the heartbeat and never carries the camera (CLAUDE.md), so a fall would contradict the recorded CG design and needs tracing before anything is claimed |
| 3 | G10 admissible stays 10 | regressing |
| 4 | group A (G1, G2) unchanged within noise | a material move — CG is uplink and G1/G2 are downlink, so a real shift is a cross-direction effect (the `HarqProcessPool.due_this_slot` mechanism) and must be traced, not absorbed |
| 5 | G7 clause 2 no worse | worsening — the SR-suppression failure belongs to unrestricted `+CGu`; this is restricted `+CG` |

### 21.3 THE COMPARISON THIS NEEDS, and why the obvious one is invalid

**X7+CG must NOT be compared against `ConfigSched2` without CG to claim
dominance.** CG improves every arm it is applied to; a like-for-unlike
comparison would credit the scheduler with CG's effect. That is the same
category error as quoting a measurement outside its configuration.

So a dominance claim requires **`ConfigSched2+CG`** as the comparator, and that
run does not exist — the 2026-09-16 campaign's CG artefacts are for
`ConfigSched` (v1), not `ConfigSched2`. It is registered as required before any
"X7+CG is the arm of record" statement, and the two legitimate readings of e8
alone are:

* **X7+CG vs X7** (`e7`) — isolates what CG does for this arm. Valid now.
* **X7+CG vs ConfigSched2+CG** — the dominance question. **Needs the missing run.**

**If expectation 1 holds and X7+CG still leads `ConfigSched2+CG` on group C,
that is the first variant in this entire series to dominate**, and it would
displace the baseline as the arm of record. If expectation 1 fails, the §19.2
recommendation stands unchanged: the frontier is real and the choice is a
product decision.

---

## 22. X7+CG vs X7 MEASURED — CG closes group B, and two costs appear that are NOT yet attributable

9 steps rc 0 (`sweeps/cs2-increments/e8/`). **CG plumbing verified live before
reading any result**: arm label recorded as `ConfigSched2X7+CG`, and 88 of 90
shared G3 cells differ from `e7` — had that been 0, the suffix would have been
inert and the whole experiment void.

Scored against §21.2:

| # | registered | outcome |
|---|---|---|
| 1 | G3 part-3 boundary >= 10 | **MET** — **6 → 24** (top of the axis), part-3 **90/90**, p98 median ~95 → ~22 ms, short messages at N=24 **325 → 0** |
| 2 | group C retained at fleet 8 | **EXCEEDED** — admissible fleet **8 → 24**, knee 1.3 → 1.4; gt31 at N = 12/14/16/24 goes 0/0/0 at ~145 ms → **10/10/3 at ~30 ms** |
| 3 | G10 admissible stays 10 | **FAILED** — **10 → 8**; M07 at N=10 10 → 1; M08 at N=12 0.778 → 0.336 |
| 4 | group A unchanged within noise | **marginal** — G2 cap-4 176 → 191, cap-2 293 → 275; G1 p98 up a little at some N |
| 5 | G7 clause 2 no worse | **FAILED** — 1.02x → **1.08x** |

Also strongly improved: G6 (UL 222/221 of 226 → **243/248 of 249**, worst
telemetry gaps 238 → 199 and 299 → 202), G12 telemetry M02 → **0.000 at every
load**, G12 order agreement 10/10, and G7 **clause 1** (A telemetry p98
97.8 → **48.0 ms**, throughput 20 400 → **24 000 bps**).

### 22.1 What CANNOT be concluded yet, and why

**CG improves every arm it is applied to.** Two of the results above are costs —
G10's admissible fleet 10 → 8, and clause 2's 1.02x → 1.08x — and **nothing here
attributes them to X7 rather than to CG itself.** `docs/results-cg-2026-09-14.md`
already records that CG changes behaviour well outside the heartbeat class
(unrestricted CG breaks G5 on every arm; this run is restricted `+CG`, but the
principle stands).

So the comparison that decides the arm of record is **X7+CG against
`ConfigSched2+CG`**, registered in §21.3 before any of this was read, and that
run (`e9`) is still executing. If `ConfigSched2+CG` shows the same G10 drop,
the cost is CG's and X7+CG dominates; if it holds 10, the cost is X7's.

**No dominance claim is made here.** The valid statement from `e8` alone is:
*for this arm, CG converts group B from its weakest result to a perfect one and
transforms group C, at the price of group E's boundary and a little containment
headroom — with the attribution of that price still open.*

### 22.2 One flag for the next reader

G9's per-cell verdict codes change character under CG: cells that read `P…`/`B…`
on `X7` now include `F…` entries (`Fc1b1`, `Fc2b1`, `Fc1b2`) even though
"informative cells passed of 12" stays **12 of 12** on both arms. The headline
is unchanged and is the scored quantity, but the letter change is a qualitative
difference that has not been traced. **Recorded as unexplained, not as fine** —
the standing rule is that a count holding while its composition moves is exactly
where a partially degenerate result hides.
