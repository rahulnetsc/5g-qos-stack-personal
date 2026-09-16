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

### 8b.1 First measurement, 2026-09-15 — `sweeps/config-sched-2026-09-15/SCORED.md`

G3 part A on the deployed cell, three paired seeds, against the campaign's
four arms. Registered first (`EXPECTATIONS.md`), scored after: one clean
hit — **Asset A's heartbeat is 100/100 at every fleet size to N = 24 with
p98 31–37 ms at N = 24**, the rank is gone — and one finding the
expectations did not ask for: **the flood robot's own heartbeat loses
half its messages at N = 24** (33–49 of 100, silences to 967 ms; Proto
95/100 on the same seed). The counters locate it: the visit interval
equals the message period and the PDB, a visit is stamped by attribution
whether or not the UE's LCP put the message in the TB, and the flood
robot's camera floor is the one dropped under `floors_unmet` because the
tie-break is `ue_id`. So the three changes the next commit should make,
each one fidelity change: a visit interval of `PDB − period` (or `PDB/2`
undeclared), a BSR-confirmed stamp, and a floor-shortfall rule that is not
declaration order. The prototype is left as measured so that commit has
its before.

## 8c. What the prototype measured about itself, and the v2 formulation (2026-09-16)

### 8c.1 Two bugs, fixed before the campaign (each its own commit)

| | what | measured, G3 part A, seed 1826701614, 10 s, cap 4 |
|---|---|---|
| B1 `65d45ae` | Tier 2 placed past the per-slot UE cap and let `cap_ues_per_slot` trim afterwards; a trimmed grant had already stamped its visit clock | N = 24: 46 of the flood robot's 94 heartbeat stamps and 70 % of all DL stamps were for grants never sent. Fixed: the cap is applied inside placement (`cap_skipped_*` counters). The flood robot's heartbeat then fell 45 → **12** of 100 — the mechanism the phantom stamps hid |
| B2 `f6aa911` | Tier 1 counted the special slot as a full slot in both directions: 1 320 symbol-slots per window against the grid's 1 080 (+22 %) | Fixed: the PRB budget is symbol-weighted, the visit budget stays slot-counted. Flood robot 12 → **97** of 100; `visit_budget_bound` 2 045 → 0. A 22 % change in one budget flipped the outcome — the order has no priority or age term, so the heartbeat's fate depends on how many camera visits happen to be due |

### 8c.2 Why the prototype is not the design §1–§2 describe

Its Tier 1 is the port's LP with the log-utility replaced by floors-then-
max-min and a visit count bolted on; §8a's "the cap becomes linear over a
window, so no Dantzig–Wolfe is needed" is true for the *rate* region and
discarded the configuration idea with it. Against the two reasons for the
pivot: (1) it is greedy and fast but solves no stated problem exactly
(three sequential stages, the visit budget never traded against the PRB
budget, C5 soft); (2) delay enters only as "one visit per PDB", fairness is
equal PRB shares, **frames do not exist** (`bytes_per_visit = r/n` has no
relation to a frame), and **no active set is ever enumerated**. Its one
measured gain — the instrument robot's heartbeat 100/100 where TwoTier
fails — is rank removal, which `ProtoRRageD2` gets from one ordering
change. Also, `_due_key` treats a never-visited flow as due *now*, the
LEAST overdue of the due units, so under load a new or re-joined flow loses
every tie (measured: 10 401 of 12 000 slots "never visited", 13 grants).

### 8c.3 The v2 formulation: lifted variables that make the window constraints sufficient

The deployed cell's numbers fix the shape: at 20 dB a robot's whole-slot
TB is **6 121 B** (11 symbols), a camera frame is **16 500 B** — 2.7 slots
— so a frame is never one visit, and the decisive variable is the trade
between DCIs and PRBs per visit, invisible to a rate. Per direction, per
100 ms window (`W` = 120 UL-carrying slots; 98.2 full-slot equivalents of
PRB-time on `DDSUU`), re-solved every 10 ms:

| variable | meaning | what the dimension buys |
|---|---|---|
| `T_i ∈ {2, 4, 8, …}` | visit period in direction-slots (`n_i = W/T_i`) | the cap becomes a **density** constraint that is sufficient, not only necessary |
| `b_i` | bytes per visit | the DCI-vs-PRB trade, explicit |
| `k_i` | visits per job (frame or message) | frame completion becomes linear; a frame is never split across a deadline |
| `τ_i`, `P_τ` | the track a flow rides, and the track's PRB budget, `Σ_τ P_τ ≤ PRB` | per-slot PRB feasibility by construction |
| `z_i ∈ {0,1}` | floors honoured this window | who loses under overload is a weighted decision, not a tie-break |
| `e_i` | bytes above the floor | the fairness residual |

| # | constraint | meaning |
|---|---|---|
| L1 | `k_i · T_i ≤ PDB_i − T_i` | a job released just after a visit still gets `k_i` visits before its deadline; the `−T_i` is phase slack and drops out with a declared phase (`+CGt`) |
| L2 | `k_i · b_i ≥ F_i` | those visits carry the whole job — M05's rule, structural |
| L3 | `GFBR_i·W/8 ≤ n_i·b_i ≤ MFBR_i·W/8` | the contract per window, both ends (G7's clamp as a constraint) |
| L4 | `Σ_i z_i / T_i ≤ cap` | **the lifted cap.** Harmonic `T_i` ⇒ Kraft's inequality ⇒ `cap` prefix codes ⇒ every flow a residue class on one track, disjoint within a track ⇒ no slot holds more than `cap` flows. The prototype's C3 counted visits and could still bunch 24 due units into one slot; this cannot |
| L5 | `8 b_i / se_i ≤ P_τ(i)` | a visit fits its track in every slot; the special slot's smaller `se` binds for a flow mapped there |
| L6 | `Σ_τ P_τ ≤ PRB` | per-slot PRB feasibility, by construction |
| L7 | `T_i ≤ PDB_i / 2` for a periodic source with PDB ≤ period | the heartbeat (PDB − period = 0): the cadence must beat the period or every message is served at its deadline |

**Objective**, lexicographic: (1) `max Σ_i v_i z_i`, priority-weighted
floors honoured — within a class, dropping the most expensive floors first
maximises the count, which answers the `ue_id` tie-break from the objective;
(2) α-fair over `e_i` on what is left (α = 1 PF, α → ∞ max-min; G8's clause
chooses α).

**Solve, and where it is exact.** Stage 1 is a lexicographic knapsack
over classes: greedy by priority, then by resource cost within a class —
exact for the lexicographic objective. Stage 2 per flow: `T_i` over ≤ 7
powers of two, `k_i = ⌈F_i / b_i⌉` at the track budget — an enumeration of
a handful of points, least density satisfying L1–L3. Stage 3: water-filling
over two resources, exact when one binds (PRB from N ≥ 10 by the counters).
Track packing of harmonic sizes is first-fit-decreasing and exact. No LP.

**Realisability, from the literature rather than recalled:** periodic
visits on one server with periods `T_i` need density `Σ 1/T_i ≤ 1`;
Kawamura proved density ≤ 5/6 always sufficient ([STOC '24](https://dl.acm.org/doi/abs/10.1145/3618260.3649757),
[PNAS 2026](https://www.pnas.org/doi/abs/10.1073/pnas.2530214123), [arXiv](https://arxiv.org/abs/2606.27104));
for harmonic periods density ≤ 1 is sufficient by the Kraft construction
above, and the schedule is a table.

**Checked against the deployed cell, G3:** camera at 20 dB, whole-slot
visits: `k = 3`, 3 frames per window → 9 visits per 120 slots → `T = 8`,
density 1/8, PRB-time 9/98.2 = 0.092 per camera; heartbeat `T = 32` by L7;
fleet DL `T = 16`. Camera floors fit while `0.092·N ≤ 1`: **N = 10, not
11**, before HARQ's ~10 % — the G3 all-parts boundary PF and the Proto arm
measured (10), recovered with no run. Density at N = 10 is 1.56 of a cap of
4: on this cell PRB-time binds, not the cap, and the plan knows it before
placing anything.

**Tier 2 under v2:** a table (slot → per track, the flow whose residue
class contains it); grant = `P_τ` PRBs to that flow's UE (an uplink UE whose
flows share a slot gets one grant sized to their sum; its LCP serves them by
priority — sized for, not predicted); an empty visit's PRBs go to the
residual pool work-conservingly; a displaced visit (retransmission, RA)
slips to the track's next slot and L1's slack absorbs it; **a configured
grant is a pinned map entry** — `+CG` on a heartbeat fixes its track and
phase and removes it from the density Tier 1 allocates. Max gap between
visits is `T_i` exactly. The visit clock, EDF, the "due now" class and every
ordering question of the prototype disappear.

**What it gives up:** harmonic rounding up to 2× density on a badly placed
period (Kawamura's bound says non-harmonic loses 1/6, but its construction
is a search, not a table); tracks fixed within a window; uplink frames
**inferred** from the BSR jump at the declared or estimated period — the
same "conditional on" label as `+CGt`; DL PDU-set marking is Rel-18
core-side.

**Order of work, after the 2026-09-16 campaign's table is complete:** build
as `ConfigSched v2` (a separate labelled arm, the prototype kept as the
"before"), one fidelity change per commit, each probed on G3 N = 10 / 24
and G2 against the campaign's artefacts on the same seeds. Open choice
before building: L7's `PDB/2` against a phase estimate for undeclared
periodic sources — the heartbeat decides it.

## 8d. The time-sharing alternative — and why configuration enumeration collapses into it (2026-09-16)

Asked for: build the recommended outer stage (enumerate configurations,
solve the time-shares by the exact greedy, realise with the Kraft
schedule), and/or the "other time-sharing mechanism" — the Birkhoff–von
Neumann style optimal time-share — to see whether either helps the
deadline-driven failures.

### 8d.1 The check that comes first: enumeration is vacuous here

A *configuration* is a set of flows servable in one slot. Ours must satisfy
two constraints: at most `cap` DCIs, and the PRBs must fit. **Increment 7
sizes every visit at most a cap-th of the slot's PRBs, so `cap` visits
always fit and the PRB constraint never binds within a slot.** What remains
is a pure cardinality constraint, and the feasible set is then *every*
subset of size ≤ cap — the base polytope of a **uniform matroid**.

Every visit-fraction vector `x` with `Σ x_i ≤ cap`, `0 ≤ x_i ≤ 1` is a
convex combination of such subsets. So enumerating configurations and
solving for their time-shares `φ` **cannot reach any rate vector that
choosing `x` directly cannot reach**. The decomposition is not where the
value is; the **realisation** — which slots each flow actually gets — is.

This is why the BvN framing, though structurally correct (an admissible
rate matrix decomposes into configurations held for fractions of time),
buys nothing *as machinery* in our setting. It would stop being vacuous
only if a visit were allowed to exceed a cap-th of a slot, because then
subsets would have to fit in PRBs too and the polytope would no longer be
a uniform matroid. That is a sizing decision we deliberately made the
other way (increment 7, after crumbs at 95 % of grants).

### 8d.2 What is therefore worth building: exact shares, smooth realisation

| | how the visit rate is chosen | how it is realised | max gap | density cost |
|---|---|---|---|---|
| **A — today** | `n_i` from the greedy, then period `T_i` = largest power of two ≤ `W/n_i` | Kraft tracks, residue classes | **exactly `T_i`** | rounding the period DOWN visits more often than needed — up to **2×** the necessary density |
| **B — the alternative** | the exact fraction `x_i = n_i / W` (the greedy is provably exact here: Federgruen–Groenevelt 1986, separable concave over a polymatroid) | a divisor / smoothing schedule — serve whichever flow is furthest behind `x_i · t`; Tijdeman's chairman-assignment bound keeps every flow's cumulative deviation below 1 | `≈ 1/x_i`, bounded deviation, **not** constant | none — the harmonic waste disappears |

**The trade is explicit, and it is the reason to measure rather than
argue.** A is *stronger per flow* (a gap that is exactly `T_i`, by
construction). B is *stronger in aggregate* (no wasted density, so more
flows get a share at all). Our failures at high load are density failures —
`floors_unmet` reads 13 029 at N = 24, and G5's admissible fleet and G10's
behaviour past the boundary are both "who gets a share" questions — which
is why B is worth a run even though it weakens the per-flow guarantee that
made increments 5–9 work.

### 8d.3 Registered before building

- **Density:** `floors_unmet` at N = 24 falls substantially; that is B's
  whole mechanism and if it does not move, B did nothing.
- **Group C (G5):** admissible fleet 6 → 7 or better, load knee ×1.0 →
  ×1.1 or better — the recovered density is exactly what the camera floors
  need.
- **Group E (G10):** admissible 10 held; M08 past the boundary improves on
  increment 9's 0.781 / 0.175.
- **Group B (G3):** part-1s boundary stays 24 and the campaign part 2 stays
  PASS. Worst silences may rise (gaps are no longer constant) but must stay
  at or under the Proto arm's 199–494 ms.
- **Group A (G1, G2) and F (G9):** unchanged within noise.
- **Falsified by:** G3's boundary dropping below 10, or the silences
  exceeding Proto's — either would say the fixed-period guarantee was
  load-bearing and that A's harmonic construction should stay.

Built as a flag on `ConfigSched2` (default off, so the arm stays
byte-identical when unset) under its own arm name, exactly as `D1` was for
the Proto side.

## 9. Open external inputs

None specific to this work. The SRB capture and TS 22.104's survival-time
table are outstanding for the guarantee campaign generally, and the test
plan owes three specification answers — G6's estimator, G7 c1's tolerance,
G9's neighbour ε.
