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
eventual OpenAirInterface (OAI) integration. All quantitative results below
are reproducible with `python scripts/scheduler_study.py` and
`python scripts/compare_schedulers.py`.

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

The adaptive GBR penalty (a dual-ascent refinement of Tier-1) turned out to
be the *wrong shape* for its intended job; that negative result is in §8.4.

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
  share.

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
overload case it was built for.

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
| **UL Buffer Status Report round-trip** as a fixed per-flow delay (8 slots ≈ 4 ms at μ=1); Configured Grants bypass | BSR quantisation and loss not modeled (delay captures the first-order effect) |
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

`factory_robots` as shipped sits in *deep overload* — UL GBR demand is
roughly 2× carrier capacity — so the overload study sweeps the carrier
bandwidth around that point (1.0× … 3.0×) to traverse regimes.

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

### 7.1 Study 1 — overload sweep (`factory_robots`)

Carrier capacity scaled around the as-shipped point (1.0×). A GBR contract
counts as met when delivered throughput ≥ 95% of GFBR.

| Capacity | Scheduler | Total | GBR met | mean GBR | min GBR | worst p99 |
|---|---|---|---|---|---|---|
| **1.0×** (deep overload) | PF | 69.1 M | 0/10 | 37% | 0% | 30 ms |
| | TwoTier | 74.7 M | 0/10 | **51%** | 0% | 30 ms |
| | TwoTier + adaptive | 66.0 M | 0/10 | 43% | 35% | 30 ms |
| **1.5×** | PF | 93.7 M | **4/10** | 55% | 4% | 30 ms |
| | TwoTier | 96.1 M | 0/10 | **68%** | **43%** | 30 ms |
| | TwoTier + adaptive | 93.9 M | 0/10 | 65% | 46% | 30 ms |
| **2.0×** (moderate overload) | PF | 111.1 M | 5/10 | 72% | 32% | 30 ms |
| | TwoTier | 120.2 M | **10/10** | **83%** | **81%** | 30 ms |
| | TwoTier + adaptive | 120.2 M | 10/10 | 83% | 81% | 30 ms |
| **3.0×** (light load) | PF | 124.7 M | 10/10 | 85% | 83% | 30 ms |
| | TwoTier | 125.4 M | 10/10 | 85% | 83% | 30 ms |

The uplink UEs run with an **8-slot (~4 ms) BSR round-trip delay** on the
dynamic scheduler — see §5.1. SPS-served flows bypass it, exactly as they
do in real 5G.

Reading the table:

- **At 2.0× — the clean win, sharpened by BSR.** TwoTier honors **10/10**
  GBR contracts vs PF's 5/10, with a much higher minimum delivery (81% vs
  32%) and +9.1 Mbps total throughput. The gap widened from the BSR-off
  version (8/10 for PF) because dynamic-only PF absorbs the full BSR
  latency while TwoTier's SPS-served flows do not. This is the regime where
  the two-tier scheduler unambiguously earns its complexity.
- **At 1.5× — a distributional win the contract count hides.** TwoTier
  meets *fewer* knife-edge contracts (0/10 vs PF's 4/10) yet delivers a far
  better *distribution*: minimum delivery 43% vs PF's 4%, mean 68% vs 55%.
  PF lets a few good-channel flows run clear of the 95% line while
  abandoning the rest to near-zero; TwoTier equalizes everyone toward their
  target, so most flows cluster in the 40–90% band and none cross the exact
  95% threshold. "Every robot at ≥43%, mean 68%" is operationally better
  than "4 robots at 100%, 6 robots below 30%" — but a 95% threshold metric
  scores it lower. (See §8.1.)
- **At 1.0× and 3.0× — convergence.** In deep overload no scheduler can
  honor the contracts; with ample capacity all converge (10/10). The
  scheduler choice is immaterial at both ends.
- **The adaptive penalty meets 0/10 across every overload row.** §8.4.

### 7.2 Study 2 — PDCCH-limited (`sensor_dense`)

30 dense periodic sensors; the per-slot DCI/CCE budget binds before the data
channel. Delay contract = ≥99% on-time within the 15 ms PDB.

| Scheduler | Total | On-time | mean deliv | min deliv | worst p99 |
|---|---|---|---|---|---|
| RoundRobin | 6.9 M | 0/30 | 72% | 71% | 15.0 ms |
| ProportionalFair | 9.2 M | 1/30 | 95% | 85% | 15.0 ms |
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
| **TwoTier** | **8/8** | **100%** | **10.0 ms** | 14.2 M |

TwoTier meets **8/8** deadlines; PF meets 5/8. PF schedules by
channel-relative throughput with no notion of a deadline, so a healthy
5 Mbps interactive flow is throttled exactly like bulk. TwoTier funds the
interactive set (Delay weight 5 in Tier-1, HoL urgency in Tier-2) and
explicitly squeezes bulk — a *deliberate* ~10 Mbps bulk trade (24.6 → 14.2 M)
to clear every deadline. The danger PF poses here is that its **86% mean
control delivery reads "fine" on a dashboard** while the missing 14% is
aged-out motion-control packets — the safety-relevant ones (§8.3).

### 7.4 Per-flow breakdown (`factory_robots`, 1.0×)

The aggregates above hide *which* flows win and lose. The per-GBR-flow
delivery (fraction of GFBR delivered) at the as-shipped 1.0× operating
point:

| Flow | SNR | GFBR | RR | PF | Gradient | TwoTier |
|---|---|---|---|---|---|---|
| ue1 (video) | 22 dB | 8 M | 77% | 91% | 77% | 87% |
| ue2 (video) | 18 dB | 8 M | 57% | 68% | 66% | 66% |
| ue3 (video) | 20 dB | 8 M | 63% | 74% | 71% | 68% |
| **ue4 (video)** | **16 dB** | 8 M | 51% | 62% | 64% | **0%** ⚠ |
| ue5 (LIDAR) | 24 dB | 14 M | 56% | 67% | 67% | 93% |
| ue6 (LIDAR) | 19 dB | 14 M | 37% | 46% | 55% | 88% |
| **ue7 (LIDAR)** | **14 dB** | 14 M | 23% | 28% | 41% | **0%** ⚠ |
| **ue8 (video + BE)** | 21 dB | 6 M | 3% | 3% | 3% | **86%** |
| **ue9 (video + BE)** | 17 dB | 6 M | 3% | 3% | 3% | **47%** |
| **ue10 (video + TCP)** | 20 dB | 6 M | 89% | 0% | 0% | **86%** |
| Aggregate | | | mean 46% | **mean 44%** | mean 45% | **mean 62%** |

Two opposite effects are visible:

- **TwoTier protects mixed-flow GBR (ue8/9/10): 86/47/86% vs PF's 3/3/0%.**
  These UEs carry a GBR video flow *and* a best-effort flow. Under the
  QoS-blind baselines the MAC multiplexer fills the UE's transport block by
  raw backlog, and a continuously-backlogged best-effort flow wins every
  time — cannibalizing its own UE's GBR flow down to ~3%. TwoTier's
  multiplexer fills by drift-plus-penalty deficit, so the GBR flow (far
  behind its Tier-1 target → large `Q`) is served first. This is a direct,
  clean demonstration of QoS-aware multiplexing.
- **TwoTier still starves the cell edge (ue4 at 16 dB, ue7 at 14 dB → 0%).**
  The Tier-1 `log`-utility objective with *soft* GBR floors finds it cheaper
  to abandon expensive low-SNR flows and fund the rest — the classic
  weighted-`log` pathology. This is **Finding 1** (§8.5), open.

Net at 1.0×: TwoTier carries mean GBR delivery 62% vs PF's 44% and +5.6 Mbps
total — but, being deep overload, still 0/10 *contracts* met either way
(§7.1). The two-tier machinery redistributes the pain; at 1.0× it cannot
remove it.

---

## 8. Interpretation and discussion

### 8.1 The value of QoS-awareness is a hump, not a slope

The intuition "a smarter scheduler is always at least as good" is **false**
for contract satisfaction. Study 1 traces a *hump*:

- **Deep overload (≥2.5×, here 1.0× as-shipped).** GBR demand far exceeds
  capacity. No scheduler can honor the contracts; PF ≈ TwoTier on the
  contract count. A smarter MAC cannot manufacture capacity.
- **Moderate overload (the 1.5–2.0× band).** Capacity is *enough to honor
  the contracts but only if allocated deliberately*. This is where TwoTier
  wins: at 2.0×, 10/10 vs 8/10 contracts; at 1.5×, a much better delivery
  *distribution* (min 47% vs 7%). PF, optimizing the wrong objective, misses
  contracts the cell could have met.
- **Light load (≥3×).** Everyone has slack; all schedulers converge to
  10/10.

The 1.5× row deserves emphasis because it is where the *metric itself*
becomes the discussion. TwoTier there meets fewer 95%-threshold contracts
than PF yet delivers a strictly better outcome by every distributional
measure (higher mean, dramatically higher minimum). A knife-edge threshold
rewards a scheduler that *abandons* some flows so that others clear the bar.
For a factory where every robot matters, "all robots degraded gracefully"
beats "half the robots perfect, half offline" — so the contract *count* is
necessary but not sufficient; report it alongside the minimum.

**Engineering implication.** Dimension cells for the ~1.5–2× peak-overload
band — that is where the two-tier scheduler pays for itself. A cell that
*systematically* runs deeper than ~2.5× overload has a capacity-planning
problem, and the fix is spectrum, cells, or admission control — not a
smarter MAC.

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
by QoS. **This is also why the win widens (Study 1, 2.0×: PF 8/10 → 5/10)
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
It does raise the *minimum* delivery (Study 1, 1.0×: min GBR 0% → 37%). But
it meets **0/10** contracts at 1.0× — *worse* than default TwoTier's 1/10.

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

### 8.5 Finding 1 — cell-edge starvation (open)

The per-flow breakdown (§7.4) shows TwoTier driving the two lowest-SNR GBR
flows (ue4 at 16 dB, ue7 at 14 dB) to 0%. The Tier-1 `log`-utility objective
with soft floors prefers to abandon flows that are *expensive in PRBs per
delivered bit* and fund cheaper ones — a known pathology of weighted-`log`
objectives under infeasibility. The adaptive penalty mitigates the symptom
but, per §8.4, breaks the contract count. The principled fix is a
**lexicographic / max-min stage on GBR satisfaction before the `log`
utility**, or hard floors plus admission control. This is open; it is a
*Tier-1 objective-design* question, not a Tier-2 bug.

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
| GBR contracts at moderate (1.5–2×) overload | **Two-tier** (Tier-1 LP) | PF misses contracts the cell could honor |
| GBR contracts at deep (≥2.5×) overload | **Admission control**, not a scheduler | Genuine infeasibility — satisfy a feasible subset |

The honest bottom line: the two-tier scheduler **is** worth building for the
factory/warehouse target — but the load-bearing features are **Configured
Grants** and a **deadline-aware Tier-2**, and the Tier-1 LP earns its place
specifically in the moderate-overload GBR band. The adaptive GBR penalty
does *not* earn its place. A study that had only reported mean throughput
would have concluded "two-tier ≈ PF, don't bother"; the contract-oriented
metrics are what surface the real, regime-dependent value.

---

## 9. Threats to validity

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
- **UL BSR is modeled as a fixed delay only.** Real BSR is also *quantised*
  (5- or 8-bit table entries, ~10–15% granularity) and *lossy* (SR on PUCCH
  and the BSR MAC CE itself). The delay model captures the first-order
  effect on dynamic UL latency and grant sizing; quantisation and loss
  would each add small further hits to dynamic PF but not to SPS.

---

## 10. Next steps

**Algorithm.**
1. **Finding 1 (cell-edge starvation).** Prototype a lexicographic / max-min
   GBR-satisfaction stage ahead of the `log` utility in Tier-1, and compare
   against hard floors + admission control.
2. **Admission control.** Build the knapsack-on-contracts gate that §8.4
   argues for: when the LP reports a flow pinned at `p_max` and still
   missing, defer/reject rather than fairly under-serve everyone.
3. **Finding 3.** Treat as a contract/source issue: encoder pacing, I-frame
   staggering across cameras, and burst-aware PDB sizing — none of which is
   a scheduler change. Surface `bytes_dropped_pdb` correlated with I-frame
   slots so the dimensioning tool can flag inconsistent contracts.

**Evaluation.**
4. Adopt a 3GPP TBS table extract for absolute-claim credibility.
5. Collect and replay trace-driven factory workloads.
6. Make the longer (60-window) horizon the default for *absolute* figures;
   keep the 4000-slot horizon for fast comparative runs.

**Toward OAI** (the phased plan in [scheduler-design.md §10](scheduler-design.md)).
7. Instrument the OAI MAC with per-flow throughput / HoL / BLER metrics;
   verify against its default PF scheduler.
8. Port Tier-2 (drift-plus-penalty + the MAC multiplexer) into the OAI MAC
   scheduler thread; the `scheduler/` library is already dependency-isolated
   for exactly this.
9. Run Tier-1 as a separate thread/process writing an atomic shared-memory
   snapshot of target rates.
10. Wire SPS/Configured-Grant setup to Tier-1's decisions — per §8.2, the
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
- **Moderate-overload GBR** deployments (~1.5–2× peak): 10/10 contracts vs
  PF's 8/10 at 2×; a far better delivery floor at 1.5×.

The decomposition that delivers this — a slow NUM-style LP (Tier-1) feeding
a fast drift-plus-penalty tracker (Tier-2) — is a synthesis of established
theory (Kelly; Neely; Stolyar) chosen so each piece sits at the timescale it
belongs at, mirroring the O-RAN RIC split. The load-bearing features are
**Configured Grants** and the **deadline-aware Tier-2**; the Tier-1 LP earns
its place in the moderate-overload band specifically; and the adaptive GBR
penalty was explored and *rejected* — equalizing shortfall is the wrong
objective when a contract is a step function, and deep infeasibility is an
admission-control problem, not a scheduling one.

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
