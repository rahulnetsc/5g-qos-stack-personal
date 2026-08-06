# A Two-Tier QoS-Aware Scheduler for Private 5G — A Study

**Audience.** An engineer or researcher joining this project. This document
is the *scientific rationale* — it explains **why** the scheduler is shaped
the way it is, **what** the alternatives are, and **what the evidence says**
about when the design earns its complexity. It is deliberately not a
how-to: for the architecture see [scheduler-design.md](scheduler-design.md),
for the evaluation harness see [simulator-design.md](simulator-design.md),
and for the running lab notebook see [NOTES.md](../NOTES.md).

**Status.** The scheduler is implemented and validated in simulation and
extracted into a standalone [`scheduler/`](../scheduler/) library for an
eventual OpenAirInterface (OAI) integration. Every quantitative result below
is reproducible:

| section | script |
|---|---|
| §7.1–7.3 (Studies 1–3) | `python scripts/scheduler_study.py` |
| §7.4 (per-flow breakdown) | `python scripts/compare_schedulers.py` |
| §7.5 (BSR sensitivity) | `python scripts/bsr_study.py` |
| §7.6 (CQI staleness, SPS margin) | `python scripts/cqi_study.py` |
| §7.7 (max-min GBR stage) | `python scripts/maxmin_study.py` |

Absolute figures predate the 2026-08-06 Tier-1 reformulation in older
[NOTES.md](../NOTES.md) entries — see §9.

---

## Table of contents

1. [Problem statement and design goals](#1-problem-statement-and-design-goals)
2. [State of the art](#2-state-of-the-art)
3. [The proposed solution](#3-the-proposed-solution)
4. [Mathematical formulation](#4-mathematical-formulation)
5. [The simulation framework](#5-the-simulation-framework)
6. [Scenarios and schedulers compared](#6-scenarios-and-schedulers-compared)
7. [Comparative results](#7-comparative-results)
8. [Interpretation and discussion](#8-interpretation-and-discussion)
9. [Threats to validity](#9-threats-to-validity)
10. [Next steps](#10-next-steps)
11. [Conclusions](#11-conclusions)
12. [References](#12-references)

---

## 1. Problem statement and design goals

### 1.1 The deployment

The target is a **private 5G network for a factory / warehouse**: a single
cell (initially), operator-controlled QoS policy, and a workload that is
*heterogeneous in its quality-of-service requirements* in a way that public
mobile-broadband traffic is not. Three flow archetypes coexist on the same
carrier:

| Archetype | Example | QoS shape |
|---|---|---|
| **Guaranteed-bitrate (GBR)** | Uplink machine-vision / LIDAR from mobile robots | Sustained rate floor (GFBR); periodic with large I-frame bursts |
| **Delay-critical** | Motion-control commands, teleoperation, safety interlocks | Small payloads, hard packet delay budget (PDB) of 1–30 ms |
| **Best-effort (PF)** | Firmware updates, log/telemetry uploads, dashboards | Elastic, bursty, no contract |

The defining difficulty is that these classes do not merely want *more*
throughput — they want *different things*, and a single scalar "fairness"
objective cannot express that. A best-effort flow wants its share of
leftover capacity; a GBR flow wants a specific rate or nothing useful at
all; a delay flow wants its bytes *before a deadline*, after which they are
worthless. A scheduler that maximizes aggregate throughput will quietly
sacrifice the contracts that matter.

### 1.2 Design goals

1. **Honor per-flow QoS contracts** — deliver each GBR flow its GFBR and
   each delay flow its packets within PDB — *whenever the cell has the
   capacity to do so*.
2. **Maximize aggregate utility** for best-effort flows with the residual
   capacity.
3. **Deterministic latency** for periodic high-rate flows (cameras) via
   Configured Grants, and graceful handling of their bursts.
4. **Symbol-accurate capacity accounting**, including the TDD special slot
   and the PDCCH control channel — the control channel is a real and often
   *binding* bottleneck.
5. **A clean, testable integration boundary** so the strategic logic can be
   developed and validated independently of the per-slot, PHY-facing code,
   and lifted into OAI with minimal change.

### 1.3 The scientific question

Complexity is not free: a two-tier scheduler means an LP solver, a control
loop, and a non-trivial port into a real-time MAC. So the question this
study exists to answer is **not** "is the two-tier scheduler clever?" but:

> *In which deployment regimes does QoS-aware scheduling change outcomes a
> user actually feels — and in which is it indistinguishable from a plain
> proportional-fair scheduler and therefore pure overhead?*

The answer (Section 8) is regime-dependent and, in places, counter to the
intuition that "smarter scheduler ⇒ better." That nuance is the point of
running the study before committing to the OAI work.

---

## 2. State of the art

Cellular packet scheduling is a mature field. This section places the
proposed design on that map and explains what the OAI gNB does today.

### 2.1 Channel-opportunistic schedulers

The workhorses of cellular MAC scheduling rank UEs by a metric derived from
their *instantaneous* channel quality:

- **Round Robin (RR)** — equal airtime, channel-blind. Fair in time, but
  wastes capacity by serving UEs in deep fades.
- **Max C/I (maximum rate)** — always serve the best channel. Maximizes
  cell throughput, starves cell-edge UEs.
- **Proportional Fair (PF)** — serve the UE with the highest ratio of
  instantaneous achievable rate to its own smoothed average rate,
  `r_inst(t) / R_avg(t)` (Jalali et al. 2000; the fixed point maximizes
  `Σ log R_i`, the proportional-fair allocation of Kelly et al. 1998). PF is
  the de-facto default in LTE and NR because it balances throughput against
  time-fairness with a single knob (the averaging window).

The structural limitation, shared by all three: **none has any notion of a
rate contract or a deadline.** PF equalizes *weighted throughput*; it cannot
be told "this flow needs exactly 8 Mbps" or "this packet dies in 10 ms." A
GBR or delay flow is scheduled exactly like a best-effort flow with a
fortunate channel.

### 2.2 QoS- and deadline-aware single-tier schedulers

A large literature adds QoS awareness by *modifying the PF metric* with an
urgency term (surveyed in Capozzi et al. 2013):

- **M-LWDF** (Modified Largest Weighted Delay First; Andrews et al. 2001) —
  multiplies the PF metric by head-of-line delay and a per-flow weight.
- **EXP/PF** and the **Exp-rule** (Shakkottai & Stolyar 2002) — an
  exponential urgency term that sharply prioritizes the flow whose delay is
  worst relative to the others.
- **Log-rule** (Sadiq et al.) — a logarithmic delay term, throughput-optimal
  with good delay-tail behavior.

These work well for delay, but they share a subtler defect for *rate*
contracts. A **multiplicative urgency metric saturates**: a metric of the
form `(r_inst/R_avg) · (1 + w·deficit)` has an equilibrium that equalizes a
*weighted* `1/R_avg` across flows — it cannot drive delivered rate to an
*arbitrary, unequal* set of targets, no matter how large `w` is. (We
re-derived this the hard way; see §4.4 and the design note in
[scheduler-design.md §5](scheduler-design.md).) This is the core reason the
proposed Tier-2 is *not* a tuned PF variant.

### 2.3 Optimization-based radio resource management

A separate thread treats allocation as a mathematical program:

- **Network Utility Maximization (NUM)** (Kelly, Maulloo & Tan 1998) — cast
  rate allocation as `maximize Σ U_i(r_i)` subject to capacity constraints.
  With `U_i = log`, the optimum is proportional fairness; other `U_i`
  encode other fairness/priority policies. NUM gives a principled,
  declarative way to state *what* the allocation should be.

The limitation: NUM produces a *rate vector*, but a wireless scheduler
cannot set rates directly — it picks *which UE to serve this slot* over a
stochastic channel. NUM is the right tool for the strategic question and
the wrong tool for the per-slot question.

### 2.4 Lyapunov drift-plus-penalty and gradient scheduling

The bridge from "a rate target" to "a per-slot serve decision" is
**Lyapunov stochastic network optimization**:

- **MaxWeight / backpressure** (Tassiulas & Ephremides 1992) —
  throughput-optimal scheduling by serving the largest queue × rate.
- **Drift-plus-penalty** (Neely 2010) — attach a *virtual queue* to each
  constraint; greedily minimizing the queue drift each slot provably drives
  the long-run average to satisfy the constraint. A virtual queue that
  fills at a *target rate* and drains at the *delivered rate* turns "hit
  this rate" into a per-slot greedy rule.
- **Greedy primal-dual / gradient scheduling** (Stolyar 2005) — the same
  idea derived as a primal-dual algorithm for utility maximization subject
  to stability.

This is exactly the tool the single-tier QoS schedulers of §2.2 lack: a
virtual queue does **not** saturate — it integrates the rate error without
bound, so the delivered rate converges to the target.

### 2.5 RAN slicing and hierarchical schedulers

Network slicing — giving a tenant or traffic class a guaranteed share of
the air interface — is typically built as a **two-level** scheme: a slow
*slice-level* allocator partitions resources, a fast *flow-level* scheduler
runs within each slice. **NVS** (Kokku et al. 2012) is the canonical
example. **O-RAN** institutionalizes the same timescale split
architecturally: a **non-RT RIC** (≥1 s, policy / rApps) and a **near-RT
RIC** (10 ms–1 s, xApps) sit above the real-time MAC scheduler.

The lesson the proposed design borrows: **separate timescales.** A heavy,
declarative optimization belongs at the slow tier; only a cheap, reactive
rule belongs on the per-slot path.

### 2.6 The OpenAirInterface default gNB scheduler

OAI is the target platform, so its current scheduler is the concrete
baseline to beat. As of recent OAI 5G releases, the gNB MAC scheduler
(`openair2/LAYER2/NR_MAC_gNB/`):

- Runs a **proportional-fair preprocessor** for both downlink and uplink.
  Each UE gets a coefficient ≈ (estimated TBS at its current MCS) / (sliding
  average delivered throughput); UEs are sorted by coefficient and PRBs are
  assigned greedily. This is textbook PF, per UE.
- Multiplexes a UE's logical channels into its grant with the **standard
  3GPP Logical Channel Prioritization (LCP)** procedure (TS 38.321): strict
  logical-channel priority with prioritized-bit-rate (`Bj`) token buckets.
- Differentiates QoS only through the **5QI → logical-channel
  priority/PBR** mapping and a per-LC priority bias in the preprocessor.

What OAI's scheduler does **not** have: any strategic tier that reasons
about GFBR rate contracts or PDB deadlines across flows; any optimization
(LP) layer; any QoS-driven use of Configured Grants. Configured-Grant /
SPS support exists in the codebase but is RRC-static — it is not *driven*
by a QoS optimizer. (Exact function names should be verified against the
OAI tree in use; see [scheduler-design.md §10](scheduler-design.md).)

In the language of this study, **OAI's default scheduler is precisely the
`ProportionalFair` baseline** of Section 6 — a solid, channel-opportunistic,
contract-blind PF scheduler with standard LCP multiplexing. The proposed
two-tier scheduler is designed to *wrap*, not replace, that machinery: the
LCP multiplexer stays, the per-slot opportunism stays, and a strategic tier
plus a deadline-aware tactical metric are added.

### 2.7 Positioning

The proposed scheduler is **not a new algorithm** — it is a deliberate
*composition* of three well-founded pieces, chosen for the timescale each
belongs at:

| Piece | Borrowed from | Timescale |
|---|---|---|
| Strategic rate allocation via an LP | NUM (Kelly; §2.3) | ~1 s (Tier-1) |
| Per-slot rate tracking via virtual queues | Drift-plus-penalty (Neely, Stolyar; §2.4) | per slot (Tier-2) |
| Slow/fast timescale separation | RAN slicing, O-RAN RIC split (§2.5) | architecture |

The contribution of this project is the *engineering synthesis* for a
private-5G factory workload, the symbol- and PDCCH-accurate accounting, and
— most importantly — the **empirical characterization of when the
composition is worth its complexity** (Sections 7–8).

---

## 3. The proposed solution

### 3.1 Architecture

```
            ┌────────────────────────────────────────────────┐
            │  Tier-1  — Strategic (CVXPY LP, ~1 s cadence)   │
            │                                                 │
   buffer   │   maximize  Σ wᵢ·log(rᵢ)  −  penalties          │
   state ──▶│   s.t. capacity, GBR floors, slice floors       │──┐
   CQI/SNR  │                                                 │  │ per-flow
   GFBR     │   also: SPS reservations, slice-aware shares    │  │ target
            └────────────────────────────────────────────────┘  │ rates rᵢ
                                                                 │
            ┌────────────────────────────────────────────────┐  │
            │  Tier-2  — Tactical (drift-plus-penalty, /slot) │◀─┘
            │                                                 │
            │   virtual queue  Qᵢ += rᵢ·Δt − deliveredᵢ       │
            │   rank UEs by  (Σ Qᵢ)·SEᵤ                       │──▶ Allocations
            │   one DCI / UE; MAC LCP fills the transport block│   (PRBs, TBS)
            └────────────────────────────────────────────────┘
```

**Tier-1 (strategic).** Every ~1 s — or on a UE/flow join/leave — solve a
small convex program (NUM, §2.3) over the *flows*: given buffer occupancy,
per-UE channel quality, GFBR contracts, and slice shares, produce a
**per-flow target rate** `rᵢ`. Tier-1 also decides which periodic flows get
a Configured Grant and how big. The LP runs off the per-slot critical path.

**Tier-2 (tactical).** Every slot, track those targets with
drift-plus-penalty (§2.4). Each flow has a virtual queue that fills at its
Tier-1 target rate and drains at its delivered rate; the per-slot rule
greedily serves the UEs whose flows are most behind, weighted by channel
quality.

**The interface** between them is a single load-bearing object — the vector
of per-flow target rates — plus the SPS configuration. Tier-2 needs no
"weights": the queue dynamics generate the right priority automatically.
This is the same atomic-snapshot, fail-safe-on-staleness pattern as the
O-RAN RIC interface.

### 3.2 Why two tiers — the scientific rationale

The decomposition is not an arbitrary modularization; it is forced by the
structure of the problem.

- **Strategic allocation is a NUM problem and wants an optimizer.** "Give
  every GBR flow its GFBR if feasible, otherwise degrade gracefully, and
  split the rest by proportional fairness" is a sentence about a *constrained
  optimum over all flows at once*. An LP states it declaratively and solves
  it exactly. But an LP cannot run every 125 µs, and it assumes you can set
  rates — which you cannot.
- **Per-slot allocation is a stochastic-control problem and wants a cheap
  reactive rule.** You do not set rates; you pick a UE to serve over a
  random channel. Drift-plus-penalty is the theory that makes a greedy
  per-slot pick provably converge to a *given* long-run rate vector — with
  no per-slot optimization and no tuning constant.
- **They compose cleanly because the coupling is one-directional and
  slow.** Tier-1 outputs rates; Tier-2 consumes them; nothing on the
  per-slot path waits on the LP. If the LP overruns, Tier-2 keeps the last
  solution — graceful, not fragile.

A single tier cannot do both jobs. A pure LP is too slow and rate-naive
about the channel. A pure per-slot heuristic (the §2.2 schedulers)
saturates and cannot enforce unequal rate targets. The two-tier split is
the *minimal* structure that gets a declarative contract specification onto
a real-time MAC.

### 3.3 The load-bearing features

A central, non-obvious finding of this study (Section 8) is that *the two
tiers are not equally important*. The features that change user-visible
outcomes are:

1. **Configured Grants / SPS** — periodic flows get a standing allocation
   and consume **zero PDCCH** per slot. This is a *structural capability*
   PF-class schedulers lack entirely.
2. **A deadline-aware Tier-2 metric** — head-of-line delay folded into the
   virtual queue, so a flow near its PDB preempts bulk traffic.
3. **The Tier-1 LP** — earns its place specifically in the
   *moderate-overload* GBR regime.
4. **A max-min GBR floor ahead of the Tier-1 utility solve** — without it
   the utility objective is a shortfall-minimising knapsack that abandons
   the lowest-spectral-efficiency GBR flows outright (§8.5). It ships on by
   default because it self-disables wherever the GBR set is feasible, so it
   costs nothing except in genuine GBR overload — where it deliberately
   trades aggregate throughput for the worst-served flow.

Two Tier-1 refinements turned out *not* to be load-bearing, and both
negative results are worth as much as the positive ones: the adaptive GBR
penalty is the wrong shape for its intended job (§8.4), and the
spectral-efficiency tilt `k` only relocates the starvation it was meant to
cure (§8.5). Neither could have worked, for a structural reason given in
§8.5.

---

## 4. Mathematical formulation

Notation: flows indexed `i = 1…N`; flow `i` has class `c(i) ∈ {PF, GBR,
Delay}`, direction `d(i) ∈ {DL, UL}`, slice `σ(i)`, offered demand `Dᵢ`
(bps), and — if GBR — a guaranteed floor `Gᵢ` (GFBR, bps). `SEᵢ` is the
spectral efficiency of flow `i`'s UE: bits per PRB-symbol at its current
SNR and the target BLER. `C_d` is the PRB-symbol capacity per second in
direction `d`, derived from the TDD pattern, carrier bandwidth, and a fixed
overhead factor.

### 4.1 Tier-1 — the strategic LP

Decision variables: target rates `rᵢ ≥ 0` (bps); GBR shortfall slacks
`sᵢ ≥ 0`; per-(slice, direction) slacks `sₛₗᵢ𝒸ₑ ≥ 0`.

```
maximize    Σᵢ  w_c(i) · log(rᵢ + ε)              (utility)
          −  Σᵢ  pᵢ · sᵢ                          (GBR-shortfall penalty)
          −  p_slice · Σ  s_slice                 (slice-shortfall penalty)

subject to
  (capacity)     Σ_{i: d(i)=d}  rᵢ / SEᵢ  ≤  C_d                  ∀ d
  (GBR floor)    rᵢ + sᵢ  ≥  Gᵢ                                   ∀ i: c(i)=GBR
  (demand cap)   rᵢ  ≤  Dᵢ                                        ∀ i
  (slice floor)  Σ_{i∈(σ,d)} rᵢ/SEᵢ  +  s_slice(σ,d)
                     ≥  min( φ(σ,d)·C_d ,  demand(σ,d) )          ∀ (σ,d)
  (sign)         rᵢ, sᵢ, s_slice  ≥  0
```

- **Utility.** `log` makes the unconstrained optimum proportional-fair
  (Kelly et al. 1998). Per-class weights are `w_Delay = 5`,
  `w_PF = w_GBR = 1`: delay flows are typically low-rate, so a higher weight
  ensures the LP funds them well; GBR flows are protected by their floor
  constraint instead, so they need no weight boost. `ε = 1` keeps `log`
  finite at `rᵢ = 0`.
- **Capacity** is expressed in *PRB-seconds*: `rᵢ/SEᵢ` is the resource a
  flow's target rate consumes, and the sum cannot exceed what the direction
  offers. This is where symbol-accurate accounting enters — `C_d` counts the
  TDD special-slot symbols.
- **GBR floor is soft.** Writing `rᵢ + sᵢ ≥ Gᵢ` with a large penalty `pᵢ`
  (default `10³`) makes the floor effectively *hard whenever the flow is
  feasible* — the penalty dominates the `log` utility — yet keeps the LP
  feasible under *any* overload: the slack simply absorbs the shortfall and
  carries the cost. A hard constraint would make the program infeasible the
  moment GBR demand exceeds capacity, which is exactly when you still need
  an answer.
- **Slice floor** has the *same soft shape*: a guaranteed share `φ(σ,d)` of
  capacity, but capped at the slice's own demand (an idle slice holds
  nothing) and soft (so slice and GBR floors can both be stated without
  risking infeasibility). The capacity constraint above makes it
  **work-conserving** — a busy slice freely borrows an idle slice's unused
  share. Its slack is weighed in **bps** — PRB-symbols times the slice's
  demand-weighted SE — so `p_slice` and `pᵢ` are quoted in one currency.
  Compared raw the crossover between them sits at `pᵢ · SEᵢ`, making the
  slice-vs-GBR priority a function of the channel rather than of policy.

The program is a small convex problem (log objective, linear constraints);
CVXPY solves the study scenarios in well under 100 ms.

**Adaptive GBR penalty (optional, dual ascent).** Under genuine
infeasibility, a *uniform* penalty `pᵢ` has a bias: minimizing total bps of
slack is cheapest by sacrificing *poor-SNR* GBR flows (their slack costs the
most capacity per bit). Dual-subgradient ascent removes the bias by
escalating the penalty on whichever flow is *actually* missing:

```
pᵢ(k+1)  =  min( p_max ,  pᵢ(k)  +  b · sᵢ(k) / Gᵢ )
```

The normalized shortfall `sᵢ/Gᵢ ∈ [0,1]` makes the learning rate `b`
scale-free; `b = 0` recovers the fixed penalty. **This refinement is
disabled by default** — §8.4 shows why it is the wrong shape for the deep-
overload case it was built for, and §8.5 shows why *no* choice of `pᵢ` can
be the right one.

**Max-min GBR stage (optional, two-stage).** Because the penalty term
outweighs the utility by ~7 orders of magnitude (§8.5), the program above is
effectively an LP under overload, and its optimum is a *vertex*: GBR flows
are served in full or abandoned outright. Removing that requires a
constraint rather than a weight, so Tier-1 can run a max-min satisfaction
stage first:

```
stage A:   max t   s.t.  rᵢ ≥ t·Ĝᵢ  ∀ i: c(i)=GBR;  capacity; demand; slice floors;  0 ≤ t ≤ 1
stage B:   the program above, plus the hard floor  rᵢ ≥ scale · t* · Ĝᵢ
```

where `Ĝᵢ = min(Gᵢ, Dᵢ)` is the flow's *reachable* contract — the demand cap
prevents an under-offered GBR flow from pinning `t*` at its own unreachable
ratio. `t*` is the largest fraction of contract that every GBR flow can hold
simultaneously; `t* = 1` means the set is jointly feasible and the floor is
non-binding, so the stage is self-disabling wherever the single-stage solve
is already right. Stage B is feasible by construction and keeps the soft
GFBR constraint, so the utility still closes the gap from floor to full GFBR
where that is cheap. `scale ∈ [0,1]` trades guarantee against throughput.
Results in §7.7. **Enabled by default**, which is safe because the stage
self-disables: whenever the GBR set is jointly feasible `t* = 1` and the
floor binds nothing.

Both stages are posed in **normalized units** (rates as a fraction of the
largest contract, capacity usage as a fraction of each direction's budget).
In raw bps — a unit-scale `t` against 1e7-scale rates — CVXPY returned
`optimal` on a `t*` that was non-monotone in capacity, which is impossible
for a max-min level. A relevant caution for anyone reimplementing this.

### 4.2 Tier-2 — drift-plus-penalty rate tracking

Each flow carries a **virtual queue** `Qᵢ` (a control accumulator measured
in bits, *not* a buffer of real data). With slot duration `Δ` and Tier-1
target `rᵢ`, every slot:

```
(1) grow      Qᵢ  ←  Qᵢ  +  rᵢ · Δ
(2) clamp     Qᵢ  ←  min( Qᵢ ,  ceilᵢ )
(3) serve     (see §4.3)
(4) drain     Qᵢ  ←  max( 0 ,  Qᵢ − deliveredᵢ )
```

`Qᵢ` grows when the flow falls behind its target and shrinks when it gets
ahead; a non-saturating integrator, which is exactly why it can enforce an
*arbitrary* target where the multiplicative metric of §2.2 cannot.

**The windowed ceiling** (step 2) is the subtle part. `Qᵢ` is clamped to the
bits the flow *legitimately should have* delivered over the last Tier-1
window `W` but did not:

```
ceilᵢ  =  max( 0 ,  min( rᵢ·W ,  Aᵢᵂ )  −  Dᵢᵂ )
```

where `Aᵢᵂ`, `Dᵢᵂ` are bits *arrived* and *delivered* over the trailing
window. A flow cannot be owed more than its target (`rᵢ·W`) nor more than
what actually arrived (`Aᵢᵂ`). Using a *windowed arrival count* — not the
instantaneous backlog — is essential: a bursty video flow's RLC buffer
momentarily empties between frames, and clamping `Qᵢ` to that near-zero
backlog would erase its legitimate rate-tracking debt and let continuous
flows starve bursty GBR ones. (This was a real regression; see the
2026-05-16 entry in [NOTES.md](../NOTES.md).)

### 4.3 Per-UE grants and the MAC multiplexer

The 5G MAC grants resources **per UE**, not per flow: one DCI, one transport
block per UE per slot. Tier-2 mirrors this.

**Delay urgency.** For a Delay-class flow, a head-of-line urgency bonus is
folded into its queue before ranking:

```
Q̃ᵢ  =  Qᵢ  +  w_delay · ( HoLᵢ / PDBᵢ )^κ · max_j Qⱼ
```

The bonus is scaled by the **system-wide maximum** `Qⱼ`, not the flow's own
small target — otherwise a low-rate control flow (tiny `Qᵢ`) could never
out-compete a bulk flow. This lets a deadline-pressed flow preempt anything
as its HoL approaches PDB. (`w_delay = 4`, `κ = 2`.)

**UE ranking.** Each UE is scored by the summed deficit of its backlogged
flows, weighted by channel quality:

```
M_u  =  ( Σ_{i ∈ u, backlogged}  Q̃ᵢ )  ·  SE_u
```

The rule is simultaneously **opportunistic** (good channel → high `SE_u`)
and **rate-tracking** (flow behind target → high `Q̃ᵢ`). UEs are served in
`M_u` order, greedily, subject to the PRB and PDCCH/CCE budgets; each served
UE costs **one DCI**.

**The MAC LCP multiplexer.** A granted UE's transport block is filled across
*its* flows by a logical-channel-prioritization rule: sort the UE's flows by
`(priority_level, −Q̃ᵢ)` — standard 5QI priority first, then "most behind
target" — and fill each flow's share from its backlog. This is the same
multiplexer the baselines use (there the tiebreak is plain backlog, since
the baselines carry no virtual queues), so all schedulers are strictly
comparable on DCI cost.

### 4.4 Why not a tuned PF metric — the saturation argument

The first design iteration used a multiplicative urgency metric,
`(r_inst/R_avg)·(1 + w·max(0, 1 − R_avg/target))`. It does not work, and the
reason is structural, not a tuning failure. At equilibrium such a metric
equalizes the *weighted* quantity `(1+w·deficit)/R_avg` across competing
flows — it drives the system to a *proportional-fair-like* fixed point, not
to a point where each `R_avg` equals its own `target`. As `w → ∞` the
GBR flow is prioritized hard, but the delivered rate still does not *land
on* the target; it just lands somewhere higher. A virtual queue, by
contrast, integrates the rate error `(target − delivered)` without bound, so
the only steady state is `delivered = target`. This is why Tier-2 is
drift-plus-penalty and not "PF with a bigger GBR knob."

---

## 5. The simulation framework

The design is validated in a purpose-built discrete-event simulator
([simulator-design.md](simulator-design.md)) *before* the expensive OAI
integration. Its job is to answer **comparative** questions ("does the
two-tier scheduler beat PF on this workload, and by how much?"), not
absolute ones ("what is the true throughput of a 30 MHz carrier?").

### 5.1 Fidelity discipline

The simulator is deliberately *not* a PHY-layer simulator. The principle:
**model, to good accuracy, every resource the scheduler competes for; model
nothing else.**

| Modeled carefully | Approximated / omitted |
|---|---|
| Slot-by-slot PRB grid, including the TDD **special slot** | No LDPC, no I/Q, no actual modulation |
| **PDCCH/CCE budget** per slot, with variable DCI aggregation level | HARQ as a fixed delay + BLER discount, not a full state machine |
| **UL Buffer Status Report round-trip** as a fixed per-flow delay (8 slots ≈ 4 ms at μ=1) + Bernoulli loss; Configured Grants bypass | BSR quantisation not modelled (delay + loss capture the first-order effect) |
| **DL/UL CQI report round-trip** as a per-UE delay + Bernoulli loss; scheduler reads `get_reported_snr_db`, driver applies mismatch-BLER (`bler_for_mcs`) at the true SNR against the picked MCS; SPS uses a semi-static conservative MCS (`sps_snr_margin_db`) | CQI quantisation is implicit in the SNR→MCS staircase; direction-agnostic (see §7.6 for the effect on our scenarios — small) |
| Per-UE SNR as an AR(1) process → MCS → bits/PRB | RLC as a fluid byte buffer, no per-packet segmentation |
| BLER as a discount on delivered bits | Single-stream only — no MU-MIMO |
| Per-flow buffers with HoL timestamps and PDB expiry | Single cell — no mobility, no inter-cell interference |

The discipline cuts both ways. The PDCCH budget is modeled *because the
control channel is a genuine bottleneck* — and §7.2 shows that omitting it
would have led to the wrong conclusion that Configured Grants are
unnecessary. The UL BSR delay is modeled for the same reason: dynamic UL
scheduling in real 5G carries a ~4–8 ms SR/BSR/grant/data round-trip that
Configured Grants sidestep entirely, and omitting it *understates* the
value of SPS. (Ignoring BSR was the sim's largest fidelity gap; it surfaced
during the parallel OAI-integration workstream and is closed here — see
[NOTES.md](../NOTES.md).) Conversely, PHY detail is omitted because it does
not change *which scheduler wins*.

### 5.2 The harness

Each slot the driver: generates traffic arrivals → updates per-UE channel →
presents the slot's resource grid → calls `scheduler.allocate()` → applies
transmissions (BLER-discounted) → drains buffers → expires PDB-violating
bytes → records metrics. The scheduler interface is a small structural
contract (`configure` / `allocate`), so the same `scheduler/` library code
is exercised here and is intended to lift into OAI unchanged.

The scheduler library is **dependency-isolated**: [`scheduler/`](../scheduler/)
imports only `cvxpy`/`numpy`, never `sim/`. The simulator depends on the
library, not the reverse — the correct direction for an eventual port.

### 5.3 Validation of the simulator itself

44 unit and scenario tests cover every scheduler, SPS accounting, the PDCCH
cap, the penalty knobs, deadline protection, and every scenario YAML. Two
results give cross-confidence: single-flow-per-UE scenarios are
*byte-identical* under per-UE and per-flow scheduling (the per-UE refactor
is provably behavior-preserving where it should be); and a 60-window
(~60 s) transient check confirms the comparative findings are steady-state,
not warm-up artifacts (the absolute GBR-delivery figures read ~5 points low
on a single 4000-slot run, but the *scheduler-vs-scheduler gap* is stable —
see the 2026-05-17 transient entry in [NOTES.md](../NOTES.md)).

---

## 6. Scenarios and schedulers compared

### 6.1 Scenarios

Workloads are YAML, factored into a radio config (`ran_config_*.yml`), a run
window (`simulation_config.yml`), and a workload (`scenario_config_*.yml`),
so one workload can be run on different radios. Six scenarios exist; this
study uses three, each chosen to isolate a different bottleneck:

| Scenario | Workload | Bottleneck under test |
|---|---|---|
| **`factory_robots`** | 10 mobile robots, 24 flows: UL camera/LIDAR (GBR), DL motion-control (Delay), some best-effort and a TCP flow. SNR spread 14–24 dB. Uplink-heavy. | **Data-channel overload** + GBR contract enforcement; the project's main study. |
| **`sensor_dense`** | 30 small periodic UL sensors (control-loop telemetry), 15 ms PDB. | **PDCCH/CCE budget** — the control channel binds before the data channel. |
| **`latency_bound`** | 8 interactive 5 Mbps streams, 12 ms PDB, sharing a saturated downlink with 80 Mbps of bulk best-effort. | **Deadline awareness** under contention with elastic bulk. |

`factory_robots` as shipped sits in *deep overload* — total UL demand is
roughly 2× carrier capacity — so the load-sweep study varies the offered
load around that point (§7.1). In sim terms this is done by scaling the
carrier bandwidth (an equivalent knob); the tables express the sweep as
load × the as-shipped operating point, matching how an operator sees the
axis in a real deployment where capacity is fixed by spectrum.

### 6.2 Schedulers compared

| Scheduler | What it is | Role |
|---|---|---|
| **RoundRobin** | Channel-blind, equal airtime, per UE. | Sanity floor. |
| **ProportionalFair** | `r_inst/R_avg` per UE, EWMA-smoothed. | **The OAI default** (§2.6) — the baseline to beat. |
| **Gradient** | PF metric × hardcoded per-class urgency multipliers (GBR-deficit, Delay-HoL). | A "class-aware but no Tier-1, and saturating" baseline (§2.2). |
| **TwoTier** | The proposed design: Tier-1 LP + Tier-2 drift-plus-penalty + SPS. | The design under test. |

All four schedule **per UE** — one DCI per UE, transport block filled by the
MAC LCP multiplexer (§4.3) — so the comparison is strictly apples-to-apples
on PDCCH cost. The contrast between PF/Gradient and TwoTier is therefore a
clean measurement of *QoS-awareness*, not of grant granularity.

### 6.3 Metrics — and why contract-oriented

A GBR flow's contract is its **GFBR**; a Delay flow's is **on-time delivery
within PDB**. The study reports, as headline numbers, **the count of flows
that meet their contract** and the **p99 head-of-line delay** — not mean
delivery ratio. The reason is empirical: mean delivery ratio *hid every
finding in this study*. A scheduler can post a healthy-looking 86% mean
while the missing 14% is entirely one starved safety-critical flow. The
count-of-contracts-met and the latency tail are the numbers a deployment
owner actually feels. Mean throughput and total cell throughput are
reported too, but as context, not as the verdict.

---

## 7. Comparative results

All numbers below are reproducible with `python scripts/scheduler_study.py`
(Studies 1–3) and the per-flow breakdown with
`python scripts/compare_schedulers.py`. Horizon is the project-standard
4000 slots; see §9 on the ~5-point warm-up bias on *absolute* figures.

### 7.1 Study 1 — offered-load sweep (`factory_robots`)

Offered load scaled around the as-shipped operating point (1.0×), holding
carrier capacity fixed — the deployment view: spectrum is fixed by
allocation, the load is what the operator sees vary (and controls via
admission). The as-shipped point is deep overload for this cell: no
scheduler honours the contracts there. A GBR contract counts as met when
delivered throughput ≥ 95% of GFBR.

*Implementation note: the sim scales carrier capacity (the equivalent
operation — larger capacity for the same demand is the same load ratio
as smaller demand for the same capacity). The numbers below are
`1 / capacity_multiplier`, i.e., load relative to the as-shipped point.*

`TwoTier` is the shipped default, which includes the max-min GBR stage
(§4.1). `−maxmin` pins that stage off to show what it buys; `+adaptive`
builds on the same single-stage baseline so the §8.4 negative result stays
a like-for-like comparison.

| Load | Scheduler | Total | GBR met | mean GBR | min GBR | worst p99 |
|---|---|---|---|---|---|---|
| **1.0×** (as-shipped, deep overload) | PF | **69.3 M** | 0/10 | 37% | 0% | 30 ms |
| | **TwoTier** | 66.7 M | 0/10 | **44%** | **40%** | 30 ms |
| | TwoTier −maxmin | 74.2 M | 0/10 | 53% | 0% | 30 ms |
| | TwoTier −maxmin +adaptive | 68.7 M | 0/10 | 44% | 34% | 30 ms |
| **0.67×** | PF | 93.9 M | **4/10** | 55% | 4% | 30 ms |
| | **TwoTier** | 94.1 M | 0/10 | **65%** | **60%** | 30 ms |
| | TwoTier −maxmin | 95.8 M | 0/10 | 68% | 43% | 30 ms |
| | TwoTier −maxmin +adaptive | 94.6 M | 0/10 | 65% | 33% | 30 ms |
| **0.50×** (moderate overload) | PF | 111.2 M | 5/10 | 72% | 31% | 30 ms |
| | **TwoTier** | 120.1 M | **10/10** | **82%** | **78%** | 30 ms |
| | TwoTier −maxmin | 120.1 M | 10/10 | 82% | 78% | 30 ms |
| **0.33×** (light load) | PF | 124.7 M | 10/10 | 85% | 83% | 30 ms |
| | TwoTier | 125.4 M | 10/10 | 85% | 83% | 30 ms |

**Note the 1.0× total-throughput row: PF carries 69.3 M against TwoTier's
66.7 M.** In deep overload the default deliberately gives up ~4% of cell
throughput, and it buys a worst-served-flow floor of 40% where PF and the
single-stage form both leave a flow at 0%. That is the max-min trade, taken
on purpose (§7.7). At 0.50× and above the stage is non-binding and costs
nothing at all.

The uplink UEs run with an **8-slot (~4 ms) BSR round-trip delay** on the
dynamic scheduler — see §5.1. SPS-served flows bypass it, exactly as they
do in real 5G.

Reading the table:

- **At 0.50× load — the clean win, sharpened by BSR.** TwoTier honors
  **10/10** GBR contracts vs PF's 5/10, with a much higher minimum
  delivery (78% vs 31%) and +8.9 Mbps total throughput. The gap widened
  from the BSR-off version (8/10 for PF) because dynamic-only PF absorbs
  the full BSR latency while TwoTier's SPS-served flows do not. This is
  the regime where the two-tier scheduler unambiguously earns its
  complexity.
- **At 0.67× load — a distributional win the contract count hides.**
  TwoTier meets *fewer* knife-edge contracts (0/10 vs PF's 4/10) yet
  delivers a far better *distribution*: minimum delivery **60%** vs PF's 4%,
  mean 65% vs 55%. PF lets a few good-channel flows run clear of the 95%
  line while abandoning the rest to near-zero; TwoTier holds everyone near
  their target, so the flows cluster tightly and none crosses the exact 95%
  threshold. "Every robot at ≥60%, mean 65%" is operationally better than
  "4 robots at 100%, 6 robots below 30%" — but a 95% threshold metric scores
  it lower. (See §8.1.)
- **At 1.0× — convergence on contracts only.** No scheduler honours a
  contract here (0/10 everywhere), and in that sense the choice is
  immaterial. Distributionally it is not: TwoTier holds its worst flow at
  40% of contract where PF leaves one at 0%, and pays 2.6 Mbps of total
  throughput for it. What converges at deep overload is the *contract
  count*, not the outcome.
- **At 0.33× — real convergence.** Everyone has slack and all schedulers
  reach 10/10. The scheduler choice is genuinely immaterial.
- **The adaptive penalty meets 0/10 in both overloaded rows** (1.0× and
  0.67×), and is strictly dominated by the max-min default on minimum
  delivery at both. §8.4, §7.7.

### 7.2 Study 2 — PDCCH-limited (`sensor_dense`)

30 dense periodic sensors; the per-slot DCI/CCE budget binds before the data
channel. Delay contract = ≥99% on-time within the 15 ms PDB.

| Scheduler | Total | On-time | mean deliv | min deliv | worst p99 |
|---|---|---|---|---|---|
| RoundRobin | 6.9 M | 0/30 | 72% | 71% | 15.0 ms |
| ProportionalFair | 9.2 M | 2/30 | 95% | 85% | 15.0 ms |
| **TwoTier** | **9.6 M** | **30/30** | **100%** | **100%** | **5.0 ms** |

A decisive, structural separation: TwoTier meets **30/30** contracts at a
5 ms tail; PF meets **1/30** at the 15 ms PDB ceiling. The mechanism is
Configured Grants — each periodic flow gets a standing allocation that
costs **zero PDCCH per slot** *and* **needs no BSR round-trip** (see §5.1).
PF is doubly-throttled here: it must issue a DCI *and* wait for a BSR, and
both budgets bind. PF-class schedulers have no equivalent mechanism to
bypass either. (The 30/30 result is permanent, not a transient — it holds
in every one of 60 consecutive windows; see the transient check in
[NOTES.md](../NOTES.md).)

### 7.3 Study 3 — latency-bound (`latency_bound`)

8 interactive 5 Mbps streams, 12 ms PDB, sharing a saturated downlink with
80 Mbps of bulk best-effort. Delay contract = ≥99% of packets on-time.

| Scheduler | ctrl on-time | ctrl mean | ctrl worst p99 | bulk DL |
|---|---|---|---|---|
| RoundRobin | 3/8 | 84% | 12.0 ms | 22.8 M |
| ProportionalFair | 5/8 | 86% | 12.0 ms | 24.6 M |
| **TwoTier** | **8/8** | **100%** | **10.5 ms** | 15.2 M |

TwoTier meets **8/8** deadlines; PF meets 5/8. PF schedules by
channel-relative throughput with no notion of a deadline, so a healthy
5 Mbps interactive flow is throttled exactly like bulk. TwoTier funds the
interactive set (Delay weight 5 in Tier-1, HoL urgency in Tier-2) and
explicitly squeezes bulk — a *deliberate* ~10 Mbps bulk trade (24.6 → 14.2 M)
to clear every deadline. The danger PF poses here is that its **86% mean
control delivery reads "fine" on a dashboard** while the missing 14% is
aged-out motion-control packets — the safety-relevant ones (§8.3).

### 7.4 Per-flow breakdown (`factory_robots`, 1.0× load — as shipped)

The aggregates above hide *which* flows win and lose. The per-GBR-flow
delivery at the as-shipped 1.0× load operating point:

*Metric note: this table is **delivered ÷ GFBR** — throughput against the
contract. The `mean GBR` / `min GBR` columns in §7.1 and §7.7 are instead
**delivered ÷ arrived**, the flow's own delivery ratio. Offered load runs
~9% above GFBR for these video profiles, so the same run reads a few points
lower as a delivery ratio: the flat TwoTier column below spans 50–56% of
GFBR, and 40–48% as a delivery ratio in §7.7. Both are correct; they answer
different questions.*

| Flow | SNR | GFBR | RR | PF | Gradient | TwoTier |
|---|---|---|---|---|---|---|
| ue1 (video) | 22 dB | 8 M | 77% | 91% | 77% | 56% |
| ue2 (video) | 18 dB | 8 M | 57% | 68% | 66% | 54% |
| ue3 (video) | 20 dB | 8 M | 63% | 74% | 71% | 53% |
| **ue4 (video)** | **16 dB** | 8 M | 51% | 62% | 64% | **50%** |
| ue5 (LIDAR) | 24 dB | 14 M | 56% | 67% | 67% | 56% |
| ue6 (LIDAR) | 19 dB | 14 M | 37% | 46% | 55% | 55% |
| **ue7 (LIDAR)** | **14 dB** | 14 M | 23% | 28% | 41% | **53%** |
| **ue8 (video + BE)** | 21 dB | 6 M | 3% | 3% | 3% | **53%** |
| **ue9 (video + BE)** | 17 dB | 6 M | 3% | 3% | 3% | **50%** |
| **ue10 (video + TCP)** | 20 dB | 6 M | 89% | 0% | 0% | **53%** |
| Aggregate | | | mean 46% | **mean 44%** | mean 45% | **mean 53%** |

The shape of the TwoTier column is the whole point: **every GBR flow lands
between 50% and 53–56%**, a 6-point spread across a 10 dB SNR range, against
PF's 0–91%. That flatness is the max-min floor (§4.1, §7.7), which now ships
on by default. Three effects are visible:

- **TwoTier protects mixed-flow GBR (ue8/9/10): 53/50/53% vs PF's 3/3/0%.**
  These UEs carry a GBR video flow *and* a best-effort flow. Under the
  QoS-blind baselines the MAC multiplexer fills the UE's transport block by
  raw backlog, and a continuously-backlogged best-effort flow wins every
  time — cannibalizing its own UE's GBR flow down to ~3%. TwoTier's
  multiplexer fills by drift-plus-penalty deficit, so the GBR flow (far
  behind its Tier-1 target → large `Q`) is served first. This is a direct,
  clean demonstration of QoS-aware multiplexing.
- **The cell edge is held up, not abandoned: ue7 (14 dB) at 53% and ue4
  (16 dB) at 50%, against PF's 28% and 62%.** With the max-min stage
  switched off these two land at exactly **0%** — Tier-1's soft GBR floors
  make it cheaper to abandon expensive low-SE flows and fund the rest, and
  two flows at a clean zero is the fractional-knapsack vertex showing
  through (§8.5). The hard floor is what removes it.
- **The bill is paid by the high-SNR flows.** ue1 (22 dB) goes 91% under PF
  to 56%, ue5 (24 dB) 67% to 56%. Deliberate: at deep overload the cell
  cannot serve everyone, and the choice is *whose* contract to break.

This was **Finding 1** (§8.5) — caused by the slack penalty rather than the
`log` utility, and fixed by the max-min stage (§7.7).

Net at 1.0× load: TwoTier carries mean GBR delivery 53% vs PF's 44%, and a
worst-served flow at 50% against PF's 0% — for 2.6 Mbps *less* total. Being
deep overload, still 0/10 *contracts* met either way (§7.1). The two-tier
machinery redistributes the pain; at 1.0× load it cannot remove it, and the
default now chooses to spread it rather than concentrate it.

### 7.5 BSR sensitivity — delay and loss sweeps

The 8-slot BSR delay used above is one point on a spectrum. To confirm
the direction of the effect and check that the story is not tuned to that
point, [scripts/bsr_study.py](../scripts/bsr_study.py) sweeps delay ∈
{0, 2, 4, 8, 16} slots at loss = 0, then sweeps loss ∈ {0, 5, 10, 20 %}
at delay = 8, on the two scenarios where BSR bites: `factory_robots` at
0.50× load (moderate-overload UL GBR — the §7.1 sweet spot) and
`sensor_dense` (PDCCH-and-BSR-bound).

**Delay sweep, factory_robots @ 0.50× load (loss = 0).**

| Delay | PF met | TT met | PF min | TT min | PF total | TT total |
|---|---|---|---|---|---|---|
| 0 slots (0 ms) | 8/10 | 10/10 | 66% | 80% | 119.3 M | 120.1 M |
| 2 slots (0.5 ms) | 8/10 | 10/10 | 56% | 79% | 117.2 M | 119.7 M |
| 4 slots (1.0 ms) | 8/10 | 10/10 | 45% | 78% | 115.2 M | 119.5 M |
| **8 slots (2.0 ms)** | **5/10** | **9/10** | **32%** | **77%** | 111.1 M | 119.2 M |
| 16 slots (4.0 ms) | 5/10 | 8/10 | 30% | 77% | 107.0 M | 118.9 M |

The picture is monotone. PF's minimum delivery slides from 66% at zero
delay to 30% at 16 slots — a **factor-of-two hit** on the worst-served
flow — and its contract count breaks between 4 and 8 slots (8/10 → 5/10).
Cell throughput slips ~10% (119 → 107 M). TwoTier degrades far more
gently: its minimum delivery moves only 80% → 77%, throughput barely at
all (120.1 → 118.9 M, ~1%), and its contract count slips 10/10 → 8/10
only once delay reaches 8–16 slots — where its remaining
dynamic-scheduled (non-SPS) flows start absorbing the delay too. So the
SPS bypass is not total *immunity* at the contract level, but the
degradation is roughly a third of PF's on contracts and an order of
magnitude smaller on throughput. The gap widens roughly linearly with
delay — no cliff, no saturation.

**Loss sweep, factory_robots @ 0.50× load (delay = 8 slots).**

| Loss | PF met | TT met | PF min | TT min |
|---|---|---|---|---|
| 0% | 5/10 | 9/10 | 32% | 77% |
| 5% | 5/10 | 9/10 | 32% | 78% |
| 10% | 5/10 | 9/10 | 33% | 77% |
| 20% | 5/10 | 9/10 | 33% | 78% |

Loss barely moves the needle — a somewhat counter-intuitive result worth
understanding. Factory UEs carry continuous video traffic, so their
buffers are almost always non-empty. Losing an individual BSR update
therefore rarely changes the *eligibility* bit (the UE is known to have
data either way), and only slightly restales the *sizing* (`bytes_reported`
is already stale by 8 slots; losing this slot's update makes it a few
slots more stale). The 5-slot rescheduled BSR grants a fresh view soon
enough. For a workload with more frequent empty-to-non-empty transitions
(sparse traffic, bursty control), loss would matter more.

**sensor_dense — the SPS-invariance test.**

| Delay / Loss | PF on-time | TT on-time | PF worst p99 | TT worst p99 |
|---|---|---|---|---|
| delay 0–16 slots (loss 0) | 1–2 / 30 | **30 / 30** (all) | 15 ms | **5 ms** (all) |
| loss 0–20% (delay 8) | 1–2 / 30 | **30 / 30** (all) | 15 ms | **5 ms** (all) |

TwoTier holds **30/30 on-time at 5 ms p99 across every (delay, loss)
point**. This is the clean structural claim: Configured Grants are
insensitive to BSR delay and loss because they *use no BSR*. PF stays
broken at 1–2/30 throughout — the 15 ms PDB ceiling binds regardless of
BSR condition, because PF has no mechanism to bypass either the DCI cost
or the BSR round-trip.

**Take-away.** Modelling BSR does not change *which scheduler wins* on
any scenario — but it changes *by how much*, and it puts a concrete
number on the SPS story: SPS-served flows are *invariant* to BSR delay
and loss, while dynamic PF's minimum-served flow scales roughly linearly
with delay. In a real deployment where BSR degrades under stress
(imperfect PUCCH, marginal SR reception), the operational value of
Configured Grants is exactly *how much* PF's floor drops that TwoTier's
does not.

### 7.6 CQI staleness and SPS conservative MCS

BSR is the *uplink* side of "the scheduler sees stale state." The *downlink*
side is **CQI**: the gNB does not know the true per-UE SNR, only the last
CQI report the UE sent, which is quantised and reported on a period. Our
sim models this via [`ChannelModel.get_reported_snr_db`](../sim/channel.py):
scheduler-side calls read the delayed view; the driver still computes BLER
against the true SNR at transmission via a mismatch-BLER curve
([`bler_for_mcs`](../scheduler/link.py)) — so a MCS picked from stale-
optimistic CQI actually costs BLER when the true SNR has dropped below the
picked MCS's threshold.

The paired mechanism is **SPS's conservative MCS**: real 5G SPS grants use
a semi-static MCS chosen at reservation time from `snr_avg − sps_snr_margin_db`,
a safety margin against channel drift. Larger reservations (lower MCS)
trade spectral efficiency for BLER robustness — worth paying for on
channels that actually drift meaningfully.

[`scripts/cqi_study.py`](../scripts/cqi_study.py) sweeps both.

**CQI delay sweep, factory @ 0.50× load, sps_snr_margin = 0.**

| CQI delay | PF met | TT met | PF min GBR | TT min GBR |
|---|---|---|---|---|
| 0 slots (static channel) | 5/10 | 9/10 | 32% | 77% |
| 8 slots (static channel) | 5/10 | 10/10 | 31% | 78% |
| 32 slots (static channel) | 5/10 | 10/10 | 31% | 78% |
| 0 slots (mobile, coh 30 sl) | 5/10 | 10/10 | 38% | 78% |
| 8 slots (mobile) | 5/10 | 9/10 | 37% | 77% |

| 32 slots (mobile) | 5/10 | 9/10 | 31% | 75% |

The takeaway is **negative** and instructive: CQI staleness barely moves
either scheduler in our current scenarios. Even at 32 slots (16 ms) with a
short-coherence "mobile" channel (30-slot coherence, roughly a moving robot),
PF's min GBR drops only from 38% to 31% and TwoTier's from 78% to 75%. The reason is that our AR(1) channel
model with `stationary_std_db = 1.5` produces per-slot SNR innovations that
are small compared to the ~3 dB spacing between MCS thresholds — so even a
stale CQI usually still picks the right MCS. **CQI staleness would matter
more on a channel with either faster fading amplitude, shorter coherence,
or both** — a highly-mobile deployment, not a factory.

**SPS margin sweep, factory @ 0.50× load, CQI delay = 8.**

| SPS margin | TT met (static) | TT total (static) | TT met (mobile) | TT total (mobile) |
|---|---|---|---|---|
| 0.0 dB | 10/10 | 120.1 M | 9/10 | 121.4 M |
| 1.0 dB | 7/10 | 119.0 M | 4/10 | 117.2 M |
| 2.0 dB | 3/10 | 112.5 M | 2/10 | 113.6 M |
| 3.0 dB | 0/10 | 114.7 M | 0/10 | 114.9 M |
| 5.0 dB | 0/10 | 114.7 M | 0/10 | 114.9 M |

The tradeoff is **stark and one-directional in these scenarios**: the
margin costs efficiency from the first dB (larger reservations at a lower
MCS per PRB), contract count falling 10/10 → 7/10 → 3/10 over 0–2 dB on
the static channel, and margins ≥ 3 dB blow past the SPS-viability floor
(`sps_min_scale = 0.75`) — SPS then drops entirely to dynamic and contract
count collapses to 0/10. The mobile channel does not rescue the tradeoff,
and in fact degrades faster: at coherence 30 slots the BLER protection
from a larger margin is still smaller than the reservation-size cost.

**Combined take-away.** Gaps 1 and 2 were modelled specifically to close
"the scheduler is given perfect knowledge of channel state" — the DL twin
of the BSR gap. The result is **honest but modest**: in our slow-varying
industrial channel, CQI staleness costs little, and the SPS conservative
MCS is either neutral (margin = 0) or harmful (any margin ≥ 1 dB). This
matches physical intuition: SPS's semi-static MCS is a mobility-hedge
feature, and a static factory is exactly where the hedge does not need
paying for. The relevant *design* implication is that `sps_snr_margin_db`
should be set from the deployment's channel-volatility budget — 0 dB for a
warehouse / fixed AGV routes, non-zero (and swept experimentally) as
mobility rises. **None of Study 1–3's conclusions change.**

### 7.7 The max-min GBR stage — closing Finding 1

`factory_robots`, same contract metrics and report settings as §7.1.
`+maxmin` is the shipped default (`gbr_maxmin=True, gbr_maxmin_scale=1.0`);
the plain `TwoTier` rows pin it off. Reproduce with
`python scripts/maxmin_study.py`.

| load | scheduler | total | GBR met | mean GBR | **min GBR** | ue4 (16 dB) | ue7 (14 dB) |
|---|---|---|---|---|---|---|---|
| 1.00× | TwoTier −maxmin | 74.2M | 0/10 | 53% | **0%** | 16% | 0% |
| 1.00× | −maxmin +adaptive | 68.7M | 0/10 | 44% | 34% | 47% | 36% |
| 1.00× | **default (+maxmin)** | 66.7M | 0/10 | 44% | **40%** | 40% | 46% |
| 0.67× | TwoTier −maxmin | 95.8M | 0/10 | 68% | 43% | 63% | 43% |
| 0.67× | −maxmin +adaptive | 94.6M | 0/10 | 65% | 33% | 33% | 68% |
| 0.67× | **default (+maxmin)** | 94.1M | 0/10 | 65% | **60%** | 61% | 69% |
| 0.50× | either | 120.1M | 10/10 | 82% | 78% | 78% | 84% |
| 0.33× | either | 125.4M | 10/10 | 85% | 83% | 83% | 86% |

- **It lifts the floor it was built to lift.** min GBR 0% → 40% at 1.00× and
  43% → 60% at 0.67×; ue7 (the 14 dB flow the single-stage solve zeroes)
  goes 0% → 46%. At 1.00× the whole GBR set collapses into a **40–48% band**
  (delivery ratio; 50–56% of GFBR — see the metric note in §7.4) against a
  single-stage spread of 0–80%.
- **It is free where the cell is not in GBR overload.** At 0.50× and 0.33×,
  `t* = 1.00`, the floor is non-binding, and every figure is identical to
  default TwoTier. Contrast the adaptive penalty, which had no such
  self-disabling property.
- **It dominates the adaptive penalty** — better min GBR at both loads, same
  mean, and at 0.67× the adaptive penalty is actively *worse than doing
  nothing* (min 43% → 33%) where max-min improves things.
- DL Delay flows stay 10/10 on time throughout: a hard UL GBR floor does not
  crowd out the deadline class. Studies 2 and 3 are structurally untouched —
  neither scenario has a GBR flow, so stage A imposes no floor at all.

The `scale` knob traces a smooth cost curve at 1.00× (`t* = 0.59`): min GBR
0 / 8 / 17 / 28 / 40% for scale 0 / 0.25 / 0.5 / 0.75 / 1.0, against total
74.2 / 73.7 / 72.7 / 71.9 / 66.7 Mbps. The first 28 points of floor cost 3.1%
of throughput; the last 12 cost a further 7%.

**What it does not change: the contract count**, at any load. That limit is
structural and is discussed in §8.5.

**Why it ships on.** The deciding property is the second bullet: the stage
is *self-disabling*. Wherever the GBR set is jointly feasible `t* = 1`, the
floor binds nothing, and the result is bit-identical to leaving it off — so
the default costs exactly nothing in every regime except genuine GBR
overload. In that regime what it costs is aggregate throughput (−4% at 1.0×
load, and PF then carries more total than TwoTier does), and what it buys is
a worst-served flow at 40% of contract instead of 0%. A cell-edge robot
whose video is switched off entirely is a deployment failure in a way that a
uniformly degraded fleet is not; that is the judgement encoded in the
default. `gbr_maxmin_scale` dials it back for deployments that would rather
have the throughput, and `gbr_maxmin=False` restores the single-stage form
exactly.

---

## 8. Interpretation and discussion

### 8.1 The value of QoS-awareness is a hump, not a slope

The intuition "a smarter scheduler is always at least as good" is **false**
for contract satisfaction. Study 1 traces a *hump*:

- **Deep overload (1.0× shipped load — the as-shipped operating point).**
  GBR demand far exceeds capacity — the shipped load is deeply overloaded
  for this cell. No scheduler can honor the contracts; PF ≈ TwoTier on the
  contract count. A smarter MAC cannot manufacture capacity. What the
  scheduler still decides here is *how the shortfall is distributed*, and
  the two answers are genuinely different: TwoTier holds every flow near
  50% of contract, PF leaves one at 0% and carries 2.6 Mbps more total.
- **Moderate overload (0.50–0.67× shipped load).** Capacity is *enough to
  honor the contracts but only if allocated deliberately*. This is where
  TwoTier wins: at 0.50× load, 10/10 vs 5/10 contracts; at 0.67× load, a
  much better delivery *distribution* (min 60% vs 4%). PF, optimizing the
  wrong objective, misses contracts the cell could have met.
- **Light load (0.33× shipped).** Everyone has slack; all schedulers
  converge to 10/10.

The 0.67× row deserves emphasis because it is where the *metric itself*
becomes the discussion. TwoTier there meets fewer 95%-threshold contracts
than PF yet delivers a strictly better outcome by every distributional
measure (higher mean, dramatically higher minimum). A knife-edge threshold
rewards a scheduler that *abandons* some flows so that others clear the bar.
For a factory where every robot matters, "all robots degraded gracefully"
beats "half the robots perfect, half offline" — so the contract *count* is
necessary but not sufficient; report it alongside the minimum.

This is not only a reporting caveat: it is the choice the shipped default
now makes. The max-min stage (§7.7) is exactly a commitment to "degraded
gracefully" over "some perfect, some offline", and it is why at 1.0× load
TwoTier gives up total throughput to PF. A deployment that genuinely
prefers the other answer — where a robot at 50% of its video rate is as
useless as one at 0%, so concentration is correct — should set
`gbr_maxmin=False` and read §8.5's contract-count discussion.

**Engineering implication.** In real deployments *capacity is fixed by
spectrum*, so the corresponding operator lever is **admission control**:
keep peak offered load in the moderate-overload band (≈ half the
shipped-baseline load here) — that is where the two-tier scheduler pays
for itself. A cell that *systematically* runs at ≳2.5× its own capacity
(absolute demand-to-capacity ratio) has a capacity-planning problem, and
the fix is spectrum, cells, or admission control — not a smarter MAC.

### 8.2 Configured Grants are a structural capability, not tuning

Study 2's 30/30-vs-1/30 result is the **largest single effect** in the
study, and it does not come from the LP or the drift-plus-penalty metric —
it comes from SPS. A periodic flow on a Configured Grant costs **zero
PDCCH** per slot *and* **needs no BSR round-trip** (the standing grant is
pre-negotiated). In a deployment where the DCI/CCE budget binds before the
data channel, and every dynamic UL grant carries an extra ~4 ms BSR latency
on top, that is the difference between meeting every deadline and meeting
almost none. PF-class schedulers — including OAI's default — *cannot* close
this gap by tuning, because they have no configured-grant mechanism driven
by QoS. **This is also why the win widens (Study 1, 0.50× load: PF 8/10 → 5/10)
when BSR delay is modeled:** dynamic PF absorbs the round-trip; TwoTier's
SPS-served flows do not.

This finding also validates the simulator's fidelity discipline (§5.1):
**before** the PDCCH budget and the BSR delay were modeled, SPS made no
measurable difference and looked like dead weight. The bottlenecks SPS
exists to relieve are the *control channel* and the *BSR round-trip* —
model only the data channel and you conclude, wrongly, that Configured
Grants are unnecessary. The BSR gap surfaced during the parallel OAI
integration workstream, not in the sim — a nice illustration of why the
integration is a distinct validation of what the sim tells us.

**Engineering implication.** Any deployment with dense periodic
small-payload traffic — sensors, PLCs, AGV telemetry — *requires*
Configured Grants. CG support belongs firmly in OAI scope; it is the
highest-leverage feature in this whole design.

### 8.3 Deadline-blindness is silent

Study 3's hazard is not that PF misses deadlines — it is that PF misses them
*quietly*. PF's 86% mean control delivery is a number that passes a
dashboard review. The missing 14% is not spread thinly; it is aged-out
packets concentrated on the flows PF happened to deprioritize — and in a
teleoperation or motion-control loop, a late command is a safety event, not
a quality-of-experience blemish. A scheduler with no model of a deadline
cannot distinguish "delivered late" from "delivered," and so cannot report
the failure either.

**Engineering implication.** Deployments mixing medium-rate latency-critical
flows (teleoperation, AR, motion-control video) with bulk traffic *require*
a deadline-aware scheduler — and monitoring that reports the latency tail
and the on-time count, never just mean delivery.

### 8.4 A negative result: the adaptive penalty is the wrong shape

The adaptive GBR penalty (§4.1, dual ascent) was built to fix cell-edge
starvation by escalating the penalty on whichever flow is actually missing.
It does raise the *minimum* delivery (Study 1, 1.0× load: min GBR 0% → 35%).
But it meets **0/10** contracts across every overloaded row in the sweep.

The reason is a clean piece of theory. Dual ascent drives the system toward
**equal normalized shortfall** — proportional fairness *among the GBR
flows*. But a GBR contract is a **step function**: 94% of GFBR is worth
exactly as much as 0%. Equalizing shortfall parks every flow *just below*
its floor, so none clears it. Proportional fairness is the wrong objective
when the payoff is a step.

**Engineering implication.** Genuine infeasibility is an **admission-control**
problem, not a penalty-tuning problem: defer or drop some flows and *fully*
satisfy a feasible subset — a knapsack on contracts, not a fair division of
shortfall. The adaptive penalty's legitimate role is narrow — fairness-of-
shortfall *reporting* — so it ships **disabled by default** (`gbr_penalty_lr
= 0`). A flow pinned at `p_max` and still missing is precisely the signal
admission control should act on. The spectral-efficiency tilt knob `k`
(§4.1, [scheduler-design.md](scheduler-design.md)) was explored for the same
problem and also rejected: `k < 0` rescues the cell edge but only by
*relocating* starvation to the next-worst tier. Neither static knob can lift
the worst-case floor.

### 8.5 Finding 1 — cell-edge starvation: the penalty, not the utility

The per-flow breakdown (§7.4) shows TwoTier driving the two lowest-SNR GBR
flows (ue4 at 16 dB, ue7 at 14 dB) to 0%. Earlier revisions of this document
attributed that to the `log` utility — "a known pathology of weighted-`log`
objectives under infeasibility." **That was wrong**, and it is why two
successive fixes (§8.4, and the SE-tilt knob `k`) both failed.

Measured on `factory_robots` at 1.0× load, the two objective terms are
`Σ w·log(r+ε) = 709` and `Σ p·s = 2.4e10` — a ratio of **3.4e7**. The utility
is a tie-break and nothing more. What Tier-1 actually solves is

```
minimize  Σᵢ (Gᵢ − rᵢ)      subject to   Σᵢ rᵢ / SEᵢ  ≤  C
```

— minimize total shortfall *bits* under a PRB budget. That is a **fractional
knapsack**, whose optimum is greedy in spectral efficiency, and the solved
targets are exactly that staircase: 100% for the two highest-SE flows, 100%
for the next four, 53–56% for the boundary tier, and **0%** for the single
lowest-SE flow. It orders by SE, not SNR — ue2 (18 dB) and ue4 (16 dB) share
an MCS step and get the identical 56%.

Two controls confirm it. Sweeping `p` over six decades (`1` … `1e6`) leaves
the targets *identical* — the solution is fixed by the knapsack structure,
not the penalty magnitude. And at `p = 1e-6`, with the utility alone driving,
the allocation is 44–56% and **rises as SE falls**: ue7, the starved flow,
gets the highest ratio of all. The `log` utility is the term that *protects*
cell-edge flows; the slack penalty is the term that starves them.

**Why every penalty-shaped fix was doomed.** Once the penalty dominates, the
program is effectively an LP, so its optimum is a **vertex**: bang-bang,
served in full or abandoned. Reweighting `p` selects a different vertex and
nothing more. `k < 0` sets `pᵢ ∝ 1/SEᵢ`, equalizing the knapsack's value
density and merely permuting the victims — precisely the observed "relocates
starvation." Dual ascent promotes the missing flow and demotes another.
Removing the abandonment requires changing the **feasible region**: a
constraint, not a weight.

**The fix, and its limit.** The max-min stage of §4.1 supplies that
constraint, and §7.7 measures it: min GBR delivery 0% → 40% at 1.00× load,
43% → 60% at 0.67×, at zero cost where the GBR set is jointly feasible. It
**ships on by default** — see §7.7 for why that is safe and what it costs
where it binds. Finding 1 is **closed as a scheduler issue**.

What max-min cannot do is raise the **contract count** — and this is not a
shortcoming of the implementation but a genuine conflict of objectives. A
GBR contract is a step function, so parking ten flows at a uniform 59% of
GFBR satisfies none of them; the same wall §8.4 hit. Note that at 0.67× load
PF meets 4/10 contracts to TwoTier's 0/10 *precisely because* PF
concentrates — serving a few fully and abandoning the rest is the answer a
contract-count metric rewards. So Tier-1 can serve one objective at a time:

| objective | mechanism | right when |
|---|---|---|
| maximize the worst-served flow | `gbr_maxmin` | partial delivery has value — video that degrades gracefully, telemetry |
| maximize flows meeting GFBR | knapsack over contracts | partial delivery is worthless — a control loop at 59% of rate is a failed control loop |

The second is a contract-*selection* decision — admission control — and is
deliberately outside the scheduler's scope. Tier-1 now hands that gate a
clean signal for free: `t* < 1` is the infeasibility detector, and `t*`
quantifies how far off the GBR set is *before* any flow has been starved to
reveal it.

### 8.6 Finding 3 — the burst/PDB ceiling is a contract-dimensioning problem

Across the whole overload sweep, even at 3× capacity, the worst-case p99 HoL
pins at the 30 ms PDB and delivery plateaus near ~85%. Tripling spectrum
does not close it — so it is not a capacity problem, and three independent
checks confirm it is not a scheduler problem either: a single video flow
*alone* on a carrier (nothing to schedule) drops the same bytes under RR,
PF, and TwoTier alike.

The cause is the **contract itself**. A video flow's I-frame arrives as one
chunk 3–4× the average frame size; to drain it within the PDB needs an
*instantaneous* rate 3–4× the GFBR. A "GFBR + tight PDB" contract written
for a bursty source is *internally inconsistent* — the average-rate floor
and the burst-vs-deadline requirement contradict each other, before any
scheduler is involved. The levers are all on the input side: dimension for
the *burst* rate, relax the PDB to fit the burst, pace the encoder (cap
I-frame inflation), or admission-shape. This is a **system-design finding**,
and an important one: a GFBR rate contract does not certify burst or latency
integrity, and a deployment that writes one for video will see ~15% frame-
tail loss it cannot schedule away.

### 8.7 What the study says to build

| Deployment characteristic | Recommended scheduler | Why |
|---|---|---|
| Uniformly best-effort, or chronically deep-overloaded | **PF** (OAI default) | Two-tier adds no contract PF can't ≈match — pure overhead |
| Dense periodic sensors / PLCs | **Two-tier with SPS** (mandatory) | PDCCH-bound; PF structurally cannot do configured grants |
| Medium-rate latency-critical + bulk mix | **Two-tier** (deadline-aware Tier-2) | PF is deadline-blind, and misses silently |
| GBR flows whose **aggregate GFBR demand is ≈ 1.0–2× cell capacity** (moderate overload) | **Two-tier** (Tier-1 LP) | The demand is *nearly* feasible — a QoS-aware LP honours the contracts PF misses by chasing throughput instead |
| GBR flows whose **aggregate GFBR demand is ≳ 2.5× cell capacity** (deep overload) | **Admission control**, not a scheduler | Genuine infeasibility — no scheduler can satisfy an over-subscribed contract set; satisfy a feasible subset instead |

The honest bottom line: the two-tier scheduler **is** worth building for the
factory/warehouse target — but the load-bearing features are **Configured
Grants** and a **deadline-aware Tier-2**, and the Tier-1 LP earns its place
specifically in the moderate-overload GBR band. The adaptive GBR penalty
does *not* earn its place. A study that had only reported mean throughput
would have concluded "two-tier ≈ PF, don't bother"; the contract-oriented
metrics are what surface the real, regime-dependent value.

---

## 9. Threats to validity

- **Absolute figures predate 2026-08-06 in older write-ups.** Tier-1 was
  reformulated on that date after its single-objective form was found to
  return solver-inaccurate targets (§4.1). Every study here has been
  re-measured against the corrected solve and no conclusion changed, but
  absolute numbers quoted in [NOTES.md](../NOTES.md) entries dated before
  then carry an unknown few-percent solver error on top of the warm-up and
  channel scatter below.
- **Simulator, not silicon.** Results are comparative and architecture-level
  (§5.1). They establish *which scheduler wins and roughly by how much*;
  they do not predict absolute throughput or microsecond-accurate latency.
  The OAI integration is what validates real-time feasibility and UE
  interop.
- **Warm-up bias on absolute figures.** A single 4000-slot run reads GBR
  delivery ~5 points low versus steady state, with ±~2 point per-window
  scatter (channel coherence is 2000 slots). The *scheduler-vs-scheduler
  gap* is stable across 60 windows, so the comparative claims hold; absolute
  percentages should be read as soft. (2026-05-17 transient entry,
  [NOTES.md](../NOTES.md).)
- **Spectral efficiency is a fitted staircase**, not a 3GPP TBS table
  extract — fine for comparative work, would need the real table for
  absolute claims (open item, [simulator-design.md §13](simulator-design.md)).
- **Scenario coverage.** Three scenarios isolate three bottlenecks cleanly,
  but they are synthetic. Trace-driven workloads from real factory
  measurements are not yet available and would strengthen the external
  validity of §8.7.
- **UL DCI is amortized** into the U-slot CCE budget rather than charged to
  the earlier D-slot that carries the real UL grant — a reasonable
  approximation, worth revisiting if PDCCH-edge UL scenarios become central.
- **BSR is modelled as delay + Bernoulli loss; CQI as delay + Bernoulli
  loss with MCS-mismatch BLER.** Both capture the first-order effects
  (§7.5, §7.6). Not modelled: BSR *quantisation* (5- or 8-bit table
  entries, ~10–15% granularity) and CQI *quantisation* beyond the implicit
  SNR→MCS staircase. Each would add small further hits to dynamic scheduling
  but not to SPS. Also not modelled: **UL k2 grant-to-transmission timing**
  (~4 slots added on top of BSR for dynamic UL) — would widen SPS's win on
  Studies 1 & 2 slightly, direction-consistent (see NOTES.md gap audit).

---

## 10. Next steps

**Algorithm.**
1. ~~**Finding 1 (cell-edge starvation).**~~ **Done** (2026-08-06) — the
   max-min GBR stage of §4.1, measured in §7.7, **on by default** since the
   same date. The default question is settled: the stage self-disables
   wherever the GBR set is feasible, so it is free everywhere except genuine
   GBR overload, and there the aggregate throughput it gives up (−4% at 1.0×
   load) buys a worst-served flow at 40% of contract rather than 0%.
2. **Admission control.** Build the knapsack-on-contracts gate that §8.4 and
   §8.5 argue for: max-min raises the delivery *floor* but cannot raise the
   *contract count*, because a contract is a step function. Tier-1's `t*`
   is the trigger and the sizing signal. Out of scope for the scheduler
   itself.
3. ~~**Rescale the Tier-1 utility program.**~~ **Done** (2026-08-06), and
   the earlier reading that "nothing here is currently corrupted" was
   wrong. The single-objective form was returning materially inaccurate
   targets — on `overload`, two solvers disagreed by 3.6× and the Delay
   class was under-served by 28% against the analytic optimum. Rescaling
   alone did not fix it (a term *ratio* is a property of the model, not the
   units); the fix was to state the lexicographic order as two phases
   (§4.1). All studies were re-measured; no conclusion changed. The
   follow-on item of the same shape — `slice_slack_penalty` being compared
   against the GBR penalty in different units — was measured and fixed the
   same day; it had made the slice-vs-GBR priority a function of SNR.
4. **Finding 3.** Treat as a contract/source issue: encoder pacing, I-frame
   staggering across cameras, and burst-aware PDB sizing — none of which is
   a scheduler change. Surface `bytes_dropped_pdb` correlated with I-frame
   slots so the dimensioning tool can flag inconsistent contracts.

**Evaluation.**
5. Adopt a 3GPP TBS table extract for absolute-claim credibility.
6. Collect and replay trace-driven factory workloads.
7. Make the longer (60-window) horizon the default for *absolute* figures;
   keep the 4000-slot horizon for fast comparative runs.

**Toward OAI** (the phased plan in [scheduler-design.md §10](scheduler-design.md)).
8. Instrument the OAI MAC with per-flow throughput / HoL / BLER metrics;
   verify against its default PF scheduler.
9. Port Tier-2 (drift-plus-penalty + the MAC multiplexer) into the OAI MAC
   scheduler thread; the `scheduler/` library is already dependency-isolated
   for exactly this.
10. Run Tier-1 as a separate thread/process writing an atomic shared-memory
   snapshot of target rates.
11. Wire SPS/Configured-Grant setup to Tier-1's decisions — per §8.2, the
    highest-leverage feature, so prioritize it.

---

## 11. Conclusions

This study set out to decide whether a QoS-aware two-tier scheduler is worth
building for a private-5G factory deployment, or whether a plain
proportional-fair scheduler — what OpenAirInterface ships today — is good
enough.

The answer is **conditional, and the conditions are now characterized.**
QoS-aware scheduling is *not* a uniform improvement: in deep overload and
under light load it is indistinguishable from PF, and a study reporting only
mean throughput would have concluded it is not worth the complexity. But
contract-oriented metrics reveal three regimes where it changes outcomes a
user feels — and feels sharply:

- **PDCCH-limited** dense-sensor deployments: 30/30 deadlines met vs PF's
  1/30, via Configured Grants — a capability PF *structurally lacks*.
- **Latency-bound** mixed deployments: 8/8 deadlines vs PF's 5/8, and PF's
  misses are *silent* — invisible to mean-delivery monitoring.
- **Moderate-overload GBR** deployments (roughly half the shipped-baseline
  load, where admission control has clipped the peak): 10/10 contracts vs
  PF's 5/10 at 0.50× shipped load; a far better delivery floor at 0.67×.

The decomposition that delivers this — a slow NUM-style LP (Tier-1) feeding
a fast drift-plus-penalty tracker (Tier-2) — is a synthesis of established
theory (Kelly; Neely; Stolyar) chosen so each piece sits at the timescale it
belongs at, mirroring the O-RAN RIC split. The load-bearing features are
**Configured Grants** and the **deadline-aware Tier-2**; the Tier-1 LP earns
its place in the moderate-overload band specifically; and the adaptive GBR
penalty was explored and *rejected* — equalizing shortfall is the wrong
objective when a contract is a step function, and deep infeasibility is an
admission-control problem, not a scheduling one.

A late result sharpened that last point. Cell-edge starvation under overload
(§8.5) turned out to be driven not by the `log` utility, as two rounds of
attempted fixes had assumed, but by the GBR slack penalty, which outweighs
the utility by seven orders of magnitude and so reduces Tier-1 to a
shortfall-minimizing knapsack — solved greedily by spectral efficiency, with
the lowest-SE flow abandoned outright. Since that solution is a *vertex*, no
reweighting of a linear penalty could ever have removed it; only a
constraint could. The two-stage max-min form (§4.1, §7.7) supplies one and
**now ships on by default**: it takes the worst-served GBR flow from 0% to
40% of its contract, and costs nothing at all wherever the GBR set is
jointly feasible, which is what makes it defensible as a default. Where it
does bind — genuine GBR overload — it gives up ~4% of cell throughput, and
at the as-shipped load PF consequently carries more total traffic than
TwoTier does. That is the trade stated plainly: a fleet degraded evenly to
~53% of contract, against one where two cell-edge robots are switched off so
the rest can run faster. It still cannot raise the count of contracts
*met* — that remains a knapsack over contracts, which is to say admission
control, and not the scheduler's decision to make.

For the factory/warehouse target, the two-tier scheduler is worth building —
and this study says precisely which parts, for which deployments, and why.

---

## 12. References

**Foundational theory**

- F. P. Kelly, A. K. Maulloo, D. K. H. Tan, "Rate control for communication
  networks: shadow prices, proportional fairness and stability,"
  *J. Operational Research Society*, 1998. — Network Utility Maximization;
  the `log`-utility basis of Tier-1.
- L. Tassiulas, A. Ephremides, "Stability properties of constrained
  queueing systems and scheduling policies for maximum throughput in
  multihop radio networks," *IEEE Trans. Automatic Control*, 1992. —
  MaxWeight / throughput-optimal scheduling.
- M. J. Neely, *Stochastic Network Optimization with Application to
  Communication and Queueing Systems*, Morgan & Claypool, 2010. —
  drift-plus-penalty; the basis of Tier-2's virtual queues.
- A. L. Stolyar, "Maximizing queueing network utility subject to stability:
  greedy primal-dual algorithm," *Queueing Systems*, 2005. — gradient
  scheduling as primal-dual utility maximization.

**Channel-opportunistic and QoS-aware scheduling**

- A. Jalali, R. Padovani, R. Pankaj, "Data throughput of CDMA-HDR: a high
  efficiency-high data rate personal communication wireless system,"
  *IEEE VTC*, 2000. — proportional fair in cellular.
- M. Andrews et al., "Providing quality of service over a shared wireless
  link," *IEEE Communications Magazine*, 2001. — M-LWDF.
- S. Shakkottai, A. L. Stolyar, "Scheduling for multiple flows sharing a
  time-varying channel: the exponential rule," 2002. — Exp-rule / EXP-PF.
- F. Capozzi et al., "Downlink packet scheduling in LTE cellular networks:
  key design issues and a survey," *IEEE Communications Surveys & Tutorials*,
  2013. — survey of QoS-aware single-tier schedulers.

**RAN slicing and architecture**

- R. Kokku et al., "NVS: a substrate for virtualizing wireless resources in
  cellular networks," *IEEE/ACM Trans. Networking*, 2012. — two-level
  slice/flow scheduling.
- O-RAN Alliance, *O-RAN Architecture Description* — non-RT and near-RT RIC;
  the timescale-separation pattern.

**Standards**

- 3GPP TS 23.501 — 5G system architecture and QoS framework (5QI, QFI, PDB,
  GFBR).
- 3GPP TS 38.300 — NR overall description.
- 3GPP TS 38.214 — NR physical layer procedures for data (MCS, TBS).
- 3GPP TS 38.321 — NR MAC (Logical Channel Prioritization, HARQ, SPS /
  Configured Grants).
- 3GPP TS 38.331 — NR RRC (SPS / Configured Grant configuration).

**Platform**

- OpenAirInterface 5G —
  [https://gitlab.eurecom.fr/oai/openairinterface5g](https://gitlab.eurecom.fr/oai/openairinterface5g).
  Target gNB; its default PF scheduler is the `ProportionalFair` baseline of
  this study.

**Project documents**

- [scheduler-design.md](scheduler-design.md) — scheduler architecture and
  the OAI integration plan.
- [simulator-design.md](simulator-design.md) — the evaluation simulator.
- [NOTES.md](../NOTES.md) — dated lab notebook: every finding, regression,
  and decision behind the results above.
