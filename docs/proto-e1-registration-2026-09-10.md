# TwoTierProto E1 — registered before the run

**2026-09-10.** E1 gates FIX-2's GBR follower reserve on feasibility. Written
before any Proto number existed; scored in
`docs/proto-e1-result-2026-09-10.md`.

Baseline: suite **1442 passed** (1431 + 11 new), `regression_corpus --check`
clean, `verify_claims --check` 30/0, core AST `0d0c91022ec842cd` before the arm
was added.

---

## 1. The arm, and what it costs

`scheduler/two_tier_proto.py::TwoTierProto` — **a labelled DIVERGENCE, not a
port.** `scheduler/two_tier.py` is untouched, because its `ia_p5g_scheduler.c`
citations are most of what makes this project's findings about the deployed
scheduler credible, and every guarantee result to date is measured against it.

**Off is byte-identical to `TwoTier`, asserted not assumed** —
`sim/tests/test_two_tier_proto.py` compares whole driver summaries at N = 4, 6,
12 and 16, either side of the threshold E1's gate turns on. An arm whose off
state had drifted could not attribute anything to its edits.

**Comparability cost, stated up front:** a Proto number is comparable only with
the faithful arm on the same seeds, never with a hardware measurement, and it
can never support a claim about what the product *does* — only about what a
change *would do*.

## 2. E1, precisely

FIX-2 caps each uplink DATA grant by reserving `min_rb` for every still-unserved
GBR candidate ranked below the current one:

```
reserve_rb = gbr_below[i] * min_rb
cap        = max(prbs_left - reserve_rb, min_rb)
```

**There is no feasibility test.** On 55 PRB with `min_rb = 5`, eleven qualifying
followers exhaust the band; beyond that the subtraction is negative for every
candidate and the floor pins everyone at `min_rb`. **E1 applies the reserve only
when `prb_count > min_rb * n_followers_need`, and otherwise falls through to
greedy by rank.**

**The seam is exact and the port is not touched.** `gbr_bytes_slot` has exactly
two live readers — `gbr_below`'s scan and `B_eff`'s `max`. Folding it into
`ul_total_target_bytes` and zeroing it removes the first and leaves the second
arithmetically identical, and it happens after `super()` has finalised `coef`.
**So E1 is a sizing change that cannot move the ranking**, pinned by a
same-inputs test on `coef` and `_ul_rank_key`.

## 3. WHAT I EXPECT TO MOVE, and by what mechanism

**On G3, at large fleets.** The measured cause of the small grant is the reserve
(`docs/g3-stress-experiment-2026-09-09.md` §3.4): the top-ranked candidate is
clamped on 100 % of slots at N = 16 and 24, and at N = 24 the largest grant in
337 599 is 5 PRB. Removing an infeasible reserve should let the leader take what
it needs, so telemetry delivery at N = 16 and 24 should rise and the longest
observable silence should fall.

**Nowhere else, and that is a prediction not a hope.** The gate fires only when
`n_followers_need >= 11`; below that E1 is a no-op by construction, and
`test_E1_gate_fires_only_when_the_reserve_cannot_fit` pins zero firings at
N = 4, 6 and 8. So G1, G2, G9, G10 and G12 at their published fleet sizes should
be **bit-identical to the faithful arm** unless their cells cross eleven
qualifying followers.

## 4. THE PREDICTION PUT TO ME, registered so it is scored

> *"The reserve is NOT the boundary mechanism. The arms fail at 6 and 7 robots,
> below the eleven-robot threshold where the clamp saturates, and at eight
> robots telemetry is already 89 of 100 while the floor fires on only 10 % of
> grants. So E1 may improve large-fleet behaviour and leave G3's boundary
> exactly where it is."*

**I expect this to hold, and it is the more valuable outcome.** The arithmetic
already says the gate cannot fire below eleven followers, and TwoTier's G3
boundary is **7**. So:

| | prediction |
|---|---|
| **P-E1-a** | **G3's part-1 boundary is UNCHANGED at 7 on the Proto arm.** Falsifier: any boundary above 7 |
| **P-E1-b** | **N = 16 and N = 24 improve materially** — telemetry shortfall down, longest silence down. Falsifier: no improvement at either, which would mean the clamp was not costing anything even when total |
| **P-E1-c** | **N ≤ 8 is bit-identical to faithful**, because the gate cannot fire. Falsifier: any difference at all |
| **P-E1-d** | **Part 2 (campaign-wide silences ≥ 2 s) improves but does not reach zero**, because most of the 26 TwoTier silences are at fleet sizes at or below the boundary. Falsifier: zero, or no change |

**If P-E1-a holds, the finding is what SETS the boundary, and nobody has named
it.** That is worth more than the improvement, because a fix aimed at the
boundary cannot be designed until the mechanism is identified — and this
campaign will have eliminated the most plausible candidate.

## 5. What is deliberately NOT run

**G1, G2, G9, G10 and G12 are not run yet.** Per the revised scope: G3 first,
one edit at a time, and the regression set only on an edit that improves G3.
**A change that does not help its own target does not need proving safe
elsewhere** — and P-E1-c predicts those cells are bit-identical anyway, which is
cheaper to check by construction than by campaign.

**E3 (a deadline term in grant sizing) is NOT built.** It is inert behind the
ungated reserve, so **E1 may make it live without it being written**. Whether it
does is measured from E1's own artefact — the question is whether, with the
reserve gated, `prbs_needed` rather than `max_rbSize` becomes the binding term.

## 6. The grid

| | |
|---|---|
| pass | GT-2.2 fleet axis, `n_ues ∈ {4,6,7,8,10,12,14,16,24}` |
| arm | `ProtoE1` only — the faithful column is already published |
| cap | 4, the deployment's value |
| seeds | 10, the same paired seeds as the published campaign |
| horizon | 40 000 slots, unchanged |
| runs | **90** |
| artefact | `sweeps/g3-proto/g3_proto_e1.json` |

Compared against `sweeps/g3-stress/g3_stress.json`'s TwoTier column, **same
seeds, same scenario builder, same scoring code** — the runner is
`scripts/g3_stress.py` with only the arm resolution extended, so the comparison
is within-seed and paired.
