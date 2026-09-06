# Making the attach path the default — a registered DECISION

**Registered 2026-09-06, before the re-run.** This is not a build. The
mechanism exists, is tested, and is off behind a flag. **Making it default
changes every number measured without it**, so it is registered as a decision
with its predictions scored afterwards.

---

## 1. The justification

**Hardware always grants during attach and re-establishment, and those grants
carry BSRs.** This simulator has **no RA procedure**, and Reservation's
`has_srb` — the control-plane tier that would carry msg3 — is **hardcoded
`False`** (`scheduler/reservation.py:23`, and its control-only cap is
described there as "a permanent no-op" for exactly this reason).

So the sim enters a fault state the deployed system does not: a UE with real
backlog, an all-zero `estimated_ul_buffer_per_lcg`, `has_gbr=False` and
`pdb_ms=9999`, which loses every sort and **cannot earn the grant that would
repopulate the array**. Measured at **51.3 %** of a joiner's slots.

**`attach_seed_slots` supplies the effect of an input the deployed system
has.** It does not fix the scheduler — the lock-out mechanism, and Tier-1.5's
dead rescue gate, stay exactly as ported. It removes a *missing input*, not a
*faithful behaviour*.

## 2. This is a DIVERGENCE and the port map must say so

The port reproduces the deployed C. Supplying a BSR that no line of the C
supplies is a **deliberate divergence from the port**, justified by the sim
lacking a procedure the hardware has — **not** by the outcome being nicer.

**Recorded as such in the port map, with the reason and the direction of the
divergence (the sim is missing an input; the flag restores it), so a later
reader cannot mistake it for a ported behaviour.**

## 3. Predictions — every clause in the scorecard, not only the ones expected to improve

Registered before the run. Direction and, where possible, magnitude.

| guarantee | clause | arm | prediction |
|---|---|---|---|
| **G5** fresh complete video | ≥99 % PDU sets | TwoTier | **6/10 → 10/10** (0 failing) |
| | | Reservation | **3/10 → ~9/10** (1/10 marginal) |
| | | PF | 10/10, **unchanged** |
| **G10** stated fleet size | GBR contract met | all | **improves**; the arm spread collapses — previously PF 8 / Res 4 / TT 4 became a **common boundary of 8** |
| **G1** responsive commands | p98 ≤ 95 ms (parametric) | TwoTier | **WORSE or unchanged.** The attach path took M06 failures 14/40 → 40/40; more UEs in contention lengthens the tail |
| | | PF, Reservation | ~unchanged |
| **G1** | p98 ≤ 15 ms (sensor_dense) | all | unchanged — one flow per UE, no lock-out to clear |
| **G3** never look dead | gap ≤ 500 ms | TwoTier | **improves** (8/10 → 9-10/10): a locked-out UE is precisely a UE that looks dead |
| | | PF, Reservation | unchanged at 10/10 |
| **G8** equal service | Jain ≥ 0.90 (parametric) | all | **improves** — a starved UE is the largest possible Jain penalty |
| **G8** | Jain ≥ 0.90 (sensor_dense) | Reservation | **improves from 0/10**; this arm's failure is starvation-shaped |
| **G2** STOP lands | p98 ≤ 100 ms | all | unchanged at 10/10 — already ~2–4 ms |
| **G7** isolation | c1 victim ≥99 % | all | unchanged 10/10 |
| **G7** | c2 clipped at MFBR | all | **unchanged 0-1/10.** MFBR bounds entitlement, not throughput; nothing about attach touches that |
| **G12** safety order | c4 | all | **unchanged.** PF 20 violations, QoS arms 0 — the mechanism is QoS-blindness, not a cold start |
| **severity (M02)** | every row | all | **falls** wherever starvation was the cause; **unchanged** where it was not |

**The one that matters: G1/TwoTier is predicted to get WORSE.** If every
prediction is an improvement the exercise is worthless.

## 4. Falsifier

**If G5/TwoTier does not clear, the mechanism is not the lock-out** and the
consolidation of four observations under one cause is wrong. That would be a
larger finding than the decision.

## 5. What is reported

**Both columns — with-attach and without.** The without column is what a
**cold-starting deployment** sees before any UE has been granted, and it is
not meaningless: it is the worst case the fault produces. The with-attach
column is the steady state hardware reaches.

**Neither column is "the" answer**, and the scorecard will carry both.
