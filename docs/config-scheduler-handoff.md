# Configuration-based scheduler — handoff

**Status:** designed, not built. Deferred once on measurement, re-opened on
different evidence.
**Disposition if built:** a labelled divergence arm alongside the faithful
port, never a replacement.

---

## 1. What it is

Tier 1 currently emits a **rate vector** — a target bit rate per flow — and
Tiers 2–3 chase it slot by slot. The configuration-based design replaces
that with two levels:

**Tier 1 emits configurations and a slot budget.** A *configuration* is a
choice of which UEs are active plus how the PRB budget splits among them —
a point in rate space. A *schedule* assigns each configuration a share of
the window: "configuration A for 120 of the next 400 slots."

**A new Tier 2 sequences that budget** — decides *which* slots, not how
many.

The composition is Dantzig–Wolfe: enumerate the extreme configurations,
solve a master problem over their convex hull, time-share the result.

---

## 2. Why it is tractable here

**The subproblem is a continuous knapsack.** After the change of variable
`x_i = r_i / se_i`, the constraint set is two disjoint sum bounds plus a
box — a laminar family, hence a polymatroid. Separable concave maximisation
over a polymatroid is solved **exactly** by greedy (Federgruen–Groenevelt,
1986). Verified empirically: over 856 captured LPs the greedy is never
worse than HiGHS and strictly better on 57.

**The column set enumerates.** Eight UEs with a per-slot cap gives 256
subsets, each a microsecond greedy solve. No column generation, no pricing
loop, no convergence question.

**Time-sharing is physically real.** The Tier-1 window is 0.1 s and slots
are 0.25 ms, so a window is **400 slots** and θ = 0.3 means 120 slots. That
is what makes the convex-hull relaxation tight rather than approximate.

**And θ is deterministic, not probabilistic.** It is a budget, not a
distribution to sample from. Randomising would give the same mean with
worse tails on exactly the max-gap statistics the guarantees measure.

---

## 3. Why it was deferred, and why that changed

**Deferred:** the original case rested on PDCCH binding, and M-6's per-slot
UE cap showed it does not. CCE utilisation is 44–65 % on the densest
workload; PRB binds first. The achievability problem the decomposition
solves was theoretical.

**Re-opened on different evidence.** Two measurements since:

**(a) The deadline tier is present and unreached.** Reservation's UL key
has `pdb_ms` above `-coef`, but `-coef` decides **98.4 %** of adjacencies
and `pdb_ms` **0.6 %** — against two-tier's 8.1 %. A lexicographic tier
only fires when its term *separates*; a constraint cannot be outvoted by a
term below it. That is the difference the configuration formulation buys.

**(b) Rank persistence is the measured mechanism behind G3.** At 16 robots
the starved UEs are candidates on **99.9 %** of slots and reach the top
four on **1.2 %** — mean rank 10.90 against the served group's 3.63.
Admission, channel and grant depth were each eliminated by measurement.
They are always in the running and always lose the sort.

**And the winning prototype works for a reason nobody chose.** G-periodic
inverts tier 2 every P slots; it agrees with a longest-denied ordering on
only **2.6–10.3 %** of reserve slots, and the rank correlation *changes
sign* across the fleet axis. So the result is evidence that **any periodic
disruption of a persistent rank order helps** — not that the chosen order
is right. A formulation that decides service explicitly, under a deadline
constraint, is the principled version of what the prototype stumbled into.

---

## 4. The constraint set is the substance

Tier 1 today has **two** constraints: DL PRB and UL PRB. Every mechanism
this project has traced lives in something it cannot express.

| missing | consequence measured |
|---|---|
| no deadline term | urgency reaches UL only via `urgency01` folded into the coefficient; `pdb_ms` is discarded at the UL call site |
| no service-interval term | burstiness is invisible; damping it improved p98 by −16.8 ms, interval excluding zero |
| no per-slot UE cardinality | targets can name more flows than any slot can deliver |
| no model of LCP | a grant to a UE may carry none of the flow it was allocated for |
| no per-LCG or per-bearer-group budget | the reserve operates on UEs, not on obligations |

**What preserves exactness:** laminar or polymatroid constraints stay exact
under greedy. A per-slot UE cardinality is a uniform matroid. Interval and
spacing constraints on *placement* are a scheduling problem with its own
exact algorithms.

**What breaks it:** PDCCH as a *fixed cost per scheduled UE* is an
indicator at `r_i > 0`, so the objective becomes non-concave and no choice
of utility function repairs it. Three routes if it is ever needed — relax
the indicator to `min(1, r_i/ρ)` and round; make it a cardinality
constraint (a uniform matroid, with 8 derived from hardware); or enumerate,
since 256 subsets at a microsecond each is faster than the current simplex.

---

## 5. What it would not fix

**Placement is undetermined by the master problem.** θ fixes how many slots
each configuration gets and says nothing about which. Two schedules with
identical θ can differ by 97.5 ms versus 10 ms on maximum gap — and G3's
max gap, M03 and G8's starvation epochs are all max-gap statistics.

So **the deadline constraints are where the value is, not a refinement**.
Either they enter Tier 1's objective or the split is incomplete, and that
should be settled in the design rather than discovered.

**And LCP is inside the UE.** The gNB cannot see the split; no scheduler
design reaches it. Measured: 24,062 of 24,971 grants where telemetry was
backlogged had round 1 exhaust the block, so round 2 never ran.

---

## 6. Scope of the divergence

**This replaces Tier 2 wholesale**, not incrementally. Every mechanism
traced in this project lives in Tier 2's ranking — the cold-start lock-out,
the flood-robot demotion, the declaration-order tie-break, rank
persistence. None of it survives the change.

**Which is the appeal and the risk.** A slot budget per configuration means
a UE in an active set *receives* its slots with no ranking to lose — so the
lock-out may become structurally impossible. That is testable in an arm
rather than arguable.

**The port stays a port.** `scheduler/two_tier.py` untouched, file:line
citations intact, and a port-map row marked divergence with what it costs
for comparability.

---

## 7. The performance case is dead — do not revive it

Measured, so it does not need re-litigating:

- The whole LP path is **2.6 %** of the workload. A 15.6× solver buys
  ~2.4 %.
- A **free** LP buys 1.60× on a two-tier record; the portable ceiling is
  2.13×.
- Over 5,639 captured solves the objective differs on **zero** at 100×
  scale; the argmax moves on 25 (0.44 %), all ties on the same optimal
  face. **No verdict rests on a suboptimal solve.**

The one performance argument that survives is **deployability**, and it is
unmeasured: Tier-1 runs ~133 SCA iterations inside a 0.1 s window on the
gNB, and nobody has established whether the deployed GLPK solve fits. An
exact O(n log n) greedy cannot miss its window. That is a product question,
not a simulator one.

---

## 8. Before building

**Do not start until the guarantee table is complete.** A redesign measured
against an incomplete baseline cannot be attributed. G4, G5, G6 and G8 are
still unrebuilt.

**Then, in order:**

1. State what each level solves, what structure it preserves, and what
   algorithm solves it exactly.
2. Settle whether deadlines enter Tier 1's objective or Tier 2's
   sequencing — §5 says the split is incomplete without an answer.
3. Decide the placement rule. Minimising maximum gap subject to hitting the
   slot counts is a scheduling problem with known exact algorithms;
   round-robin interleaving is the cheap version.
4. Build as a labelled arm, off by default, byte-identical when off,
   asserted rather than assumed.
5. Register expectations before running, and include the one that matters:
   does the cold-start lock-out become structurally impossible?

**Regression set must include G7 and G5** alongside G1, G2, G9, G10 and
G12 — isolation and video are what the reserve protects, and they are the
predictable exposure of any change to how service is apportioned.

---

## 8a. Addendum 2026-09-14 — what the RRageD2 result changes here

Measured on all ten scoreable guarantees (`docs/results-aligned-2026-09-14.md`):
an uplink Tier 2 that ignores the composite and orders every slot by
slots-since-last-grant, with the reserve bounded to two followers, is
PF-equivalent on G3/G4/G5/G6/G7/G9 and two robots behind PF on G10. Three
consequences for this design:

1. **Tier-1's leverage on UL outcomes is sizing, not ranking.** Its targets
   reach the order only through `vq → coef`, which the winning arm discards.
   A new Tier-1 is worth what the new Tier-2 consumes from it; settle the
   Tier-2 rule first (§8 step 2), and settle it from data: deadlines belong
   in **placement**.
2. **The deadline constraint is only laminar in its weak form.** In rate
   space it is a floor `r_i ≥ bytes_i / PDB_i` — necessary, not sufficient
   (G3: rate met, deadline missed by 300 ms gaps). The strong form is a
   visit-interval bound `n_i ≥ W / T_i`, linear in a **visit count**. So
   Tier-1's variables should be `(r_i, n_i)` per flow under three laminar
   families — PRB per direction in `x_i = r_i/se_i`, visits per direction
   `Σ n_i ≤ cap · W` (the M-6 cap, which *does* bind, becomes linear over a
   window), per-flow boxes from GFBR / PDB / frame period / MFBR / demand —
   plus one per-flow coupling `r_i ≤ n_i · TB_max,i`. Greedy-exact on the
   laminar part; no Dantzig–Wolfe needed once the cap is a visit budget.
   §4's PDCCH indicator is real but does not bind (M-6); it is not the
   case for the machinery.
3. **What Tier-1 can now hold that Tier-2 struggled with:** frame age
   (`n_i ≥ W/T_frame`, bytes per visit ≥ frame), GFBR-per-window, MFBR as a
   budget ceiling (G7, enforceable without touching TB sizing), per-role
   group budgets (laminar if roles partition flows; pairwise ratios are
   not), a common visit floor. What stays in Tier-2: placement (EDF on next
   due visit with `bytes_per_visit` sizing), the intra-UE LCP, HARQ.

Sequencing agreed 2026-09-14: configured grants (Type 2, with the UE-side
`allowedCG-List` restriction as an explicit switch) come **first**, because
they remove the periodic flows from the dynamic path and change what Tier-2
has left to order; this design is written after that measurement.

## 8b. Prototype built 2026-09-15 — `sim/baselines/config_sched.py`, arm `ConfigSched`

Built as the section-8a form while the deployed-cell campaign ran, as a
labelled divergence arm (`ConfigSched`, resolved by `scripts/proto_arms.py`
through `g11_campaign._arm`; `ConfigSched+CG` works like every other arm).
Step 1 of section 8, answered in the module docstring:

- **Tier 1** re-solves every 10 ms over a receding 100 ms window, per
  direction, variables `(r_i, n_i)`: floors `n_i ≥ ceil(W / PDB_i)` (the
  strong, visit-interval deadline) and `r_i ≥ GFBR_i · W` (or the backlog
  for a Delay-class flow); budgets `Σ n_i ≤ cap · S_dir` (the M-6 cap over
  the window's slots of that direction, linear) and `Σ r_i · 8 / se_i ≤
  PRB · S_dir`; a visit at most a cap-th of a slot so `cap` due units share
  one. Floors first in priority order, the residual by max-min fairness
  over demand capped at MFBR · W — greedy, exact on the laminar family.
  Counters: `floors_unmet`, `visit_budget_bound`, `rate_budget_bound`.
- **Tier 2** places: EDF on the next due visit (`last_visit + W / n_i`),
  contracted ahead of best-effort only as a tie-break, an early visit for
  units not yet due when capacity remains, leftover-only for flows with no
  share; sized at `bytes_per_visit`, never below `min_rb`; a grant smaller
  than the visit is a crumb and does not stamp the clock
  (`crumb_not_counted`); `visits_late` and `visits_late_qfi<n>` count a visit
  served more than one interval late.
- **Deliberately absent:** deficit carried across windows, per-role group
  budgets, an MFBR ceiling beyond the demand cap, and any view of the UE's
  LCP split (UL service is attributed to the UE's due flows in planned
  order). Eligibility is the BSR-visible view like every other arm, so the
  SR/BSR cold-start lock-out is configured grants' to fix, not this arm's —
  what it removes is the rank.

Measured on the deployed cell (`sim/tests/test_config_sched.py`): a due
telemetry visit beats a 200 kB best-effort backlog at cap 1 and is not
served again before its interval; at G3 N = 16 no telemetry visit is late
while the camera floors do not all fit (16 × 4 Mbps exceeds this cell's
uplink; `floors_unmet` reports it). Whether that turns into guarantee
results is the campaign's question; nothing here is registered.

## 9. Open external inputs

None specific to this work. The SRB capture and TS 22.104's survival-time
table are outstanding for the guarantee campaign generally, and the test
plan owes three specification answers — G6's estimator, G7 c1's tolerance,
G9's neighbour ε.
