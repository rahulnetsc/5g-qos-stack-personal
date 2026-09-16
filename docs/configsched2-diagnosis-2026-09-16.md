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
