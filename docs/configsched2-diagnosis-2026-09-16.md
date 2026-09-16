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
