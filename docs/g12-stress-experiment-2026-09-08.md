# G12 as a stress experiment — registration and result

**2026-09-08.** *End of shift, everything running hard: what breaks first,
and does the safety telemetry survive?*

Runner `scripts/g12_stress.py`, artefact `sweeps/g12-stress/g12_stress.json`.

---

## 1. STEP 1 — the gate: can a tie produce the `[2,4]` ordering?

I set this gate for myself after the tie-break fidelity investigation
(`docs/tie-break-fidelity-2026-09-08.md`), because the answer decides
whether the tie-break control is load-bearing or merely hygiene.

**The structural fact that reframes the question.** In G12's `mixed`
composition at N=8, **every UE that carries 5QI 4 also carries 5QI 2, and no
UE carries 5QI 4 alone**:

| UEs | carry |
|---|---|
| 1, 2 | **5QI 2 and 5QI 4** (plus 9, 82, 83, 85) |
| 3, 4, 5 | 5QI 2 only |
| 6, 7, 8 | neither |

So the order of 2 against 4 is settled **inside UEs 1 and 2**, by the
intra-UE uplink split — and that orders on `priority_level`, where 5QI 2 is
40 and 5QI 4 is 50. **Different values, so never a tie.** Measured across
the ramp:

| ramp | intra-UE fills with both 2 and 4 present | of those, **2-vs-4 TIED** |
|---|---|---|
| ×0.5 | 4 594 | **0** |
| ×1.0 | 6 769 | **0** |
| ×1.2 | 7 528 | **0** |
| ×1.4 | 7 456 | **0** |
| ×1.6 | 7 669 | **0** |
| ×2.0 | 7 766 | **0** |

**A tie never orders 5QI 2 against 5QI 4 directly. Not once, at any point on
the ramp.**

**But it can move class 4 indirectly**, and that is the honest half of the
answer. An inter-UE tie between a UE that carries class 4 and one that does
not shifts service between them, which can move *when* class 4 starves
relative to class 2:

| ramp | UL ties (adjacent, equal key) | of those, **can move class 4** | 4-bearer vs 2-bearer specifically | cannot separate 2 from 4 |
|---|---|---|---|---|
| ×0.5 | 2 302 | **374 (16.2 %)** | 149 | 1 928 |
| ×1.0 | 609 | **85 (14.0 %)** | 48 | 524 |
| ×1.2 | 659 | **100 (15.2 %)** | 63 | 559 |
| ×1.4 | 724 | **99 (13.7 %)** | 70 | 625 |
| ×1.6 | 856 | **119 (13.9 %)** | 90 | 737 |
| ×2.0 | 1 094 | **136 (12.4 %)** | 124 | 958 |

Per slot that is **7.8 % of UL slots at ×0.5** and **1.8-2.8 % across the
loaded points** (4 800 UL slots per run).

**Verdict on the gate: "sometimes, indirectly" — so the tie-break control is
LOAD-BEARING, not hygiene.** The ordering may not be quoted without it. But
the mechanism is narrower than the permutation control implied: no tie ever
decides 2-against-4 directly; the exposure is entirely through *which UE*
gets served, and it is largest at the ramp origin — which is also the
clean-control point.

## 2. The control, and why it is not `permute_flows`

`scheduler/flow.py::tie_break_term(seed, ue_id)` appends a deterministic
per-UE term as the **last** element of every rank key in both QoS arms.
`seed is None` returns 0 for every UE, so the key — and every existing
result — is unchanged; the corpus confirms it.

- **It isolates the one thing.** The flow list is untouched, so every
  first-flow-found-wins lookup (`has_gbr`, `pdb_ms`, the LCG-0 estimate,
  all of which scan `self._flows`) sees exactly what it saw before. Only the
  order among *already-tied* candidates changes.
- **`permute_flows` cannot say that.** It moves the tie-break and all of
  those lookups at once, so an order that shifts under it does not identify
  the cause. That is why §35.5's permutation result — 5QI 4 going from 2/2
  to 0/2 — could never settle the question.
- **`zlib.crc32`, not `hash()`**: Python's string hash is randomised per
  process, which would make a seeded control unreproducible across pool
  workers.
- `scheduler/rank_trace.py` caught the widened key immediately and required
  the new term to be declared in `_UL_TERMS`/`_DL_TERMS` — the guard working
  as intended.

## 3. The experiment's parameters

| | |
|---|---|
| **question** | end of shift, everything running hard: what breaks first, and does the safety telemetry survive? |
| **axis** | the committed ramp, **×0.5 → ×2.0**, points at 0.5, 0.75, **1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**, 1.8, 2.0 — resolution at the knee, where the arms separate |
| **what the ramp scales** | the **whole committed workload** (every GBR/Delay flow's offered bytes and its contract together), not one aggressor. Everyone busy at once is G12's question; a single aggressor is G7's |
| **occupancy** | **FIXED, not a second axis. N = 6** — G10's admissible boundary is PF 6 / Reservation 6 / TwoTier 5, so 6 is the realistic worst case and where the arms separate. **N = 4** as a comfortable control. **NOTE 2026-09-09: G10's boundary is now PF 12 / Reservation 6 / TwoTier 7** (§7 of this file's own slide source records the correction). N=6 remains the right choice — it is still Reservation's exact boundary and one below TwoTier's — but it is now *comfortable* for PF rather than at its limit |
| **arms** | PF, Reservation, TwoTier |
| **seeds** | 10, paired |
| **horizon** | 20 000 slots, μ=2, DSUUU, 40 MHz |
| **control** | tie-break **off** (position decides) and **on** (seed 4243) — both run in full |
| **clause 4** | telemetry never starved while lower classes still move bytes. `telemetry_m02 ≥ 0.99` = starved; τ = 1 Mbps for "background still moving" |
| **order** | first-violation sequence; the specified sequence is **9 → 4 → 2** |

**Two clauses, scored separately, because they are different questions.**
Clause 4 is a safety property (does the telemetry survive); the order is a
design property (is the sacrifice sequence the specified one).

**The τ gap is the test plan's, and is carried as one:** the plan states
"still has throughput" without a floor. τ = 1 Mbps is 2 % of the
background's own 50 Mbps offer, and the verdict was measured robust for τ
anywhere in [0.01, 8] Mbps.

## 4. The baseline gate — and what it deliberately does NOT gate on

Three outcomes per ramp point, G9's shape. **CELL ALREADY BROKEN has exactly
one form here: the background has stopped moving bytes.** Clause 4 is
"telemetry never starved *while lower classes still move bytes*", and the
degradation order is about what gets sacrificed first — with the background
already dead, both are **vacuous rather than passed**.

**"Every GBR class is under contract" is deliberately NOT a gate.** At the
top of the ramp that is the expected end state and is exactly what the
experiment measures; gating on it would erase the finding. Whether the ramp
*origin* is clean is a different question, asked once per ramp by
`assert_ramp_bottom_clean`.

**A predicate error caught before any number was read:** the first draft
scored clause 4 as `m02 >= 0.99` meaning *healthy*. M02 is a PDB-**violation**
rate, so high means starved — the draft called every point a failure while
the telemetry was in fact perfect. Corrected against
`guarantee_scorecard.py`'s own three-outcome predicate rather than
re-derived.

## 5. The §1 caveat, carried with every ordering result below

The C ties on the same terms we do, from the same input order, and on
**glibc 2.39 its `qsort` resolves those ties the same way — measured**, at
every array size from 2 to 4 096. But `qsort` is **not required to be
stable**, and glibc has changed its algorithm across releases. **So the
deployed product's order at a tie is libc behaviour it inherits, not
something it specifies**, and any ordering result here inherits that
qualification.

---

## 6. STEP 2 — results

**1 320 driver runs per cap** (120 ramp sweeps × 11 points), 10 seeds,
N=6 and N=4, three arms, tie-break control off **and** on. Wall clock
**366 s** at cap 4 and **367 s** at cap 2, 12 workers.

### 6.1 Clause 4 — the safety telemetry survives, everywhere

| cell | arm | PASS / VIOLATION / PREMISE FAILS |
|---|---|---|
| N=6 | PF | **10 / 0 / 0** |
| N=6 | Reservation | **10 / 0 / 0** |
| N=6 | TwoTier | **10 / 0 / 0** |
| N=4 | all three | **10 / 0 / 0** |

**Identical at cap 2 and cap 4, and identical with the tie-break control on
and off.** Across 240 ramp sweeps there is **not one clause-4 violation and
not one vacuous premise** — the background never fell below τ, so the clause
was live at every point and passed at every point.

**But the margin is not the same on every arm, and the carrier decides it.**
Telemetry PDB-violation rate (M02; ≥ 0.99 is starvation) at N=6, median over
10 seeds:

| arm | ×1.6 cap 4 | ×2.0 cap 4 | ×1.6 **cap 2** | ×2.0 **cap 2** |
|---|---|---|---|---|
| PF | 0.000 | 0.000 | 0.000 | 0.000 |
| Reservation | 0.000 | 0.000 | 0.000 | 0.000 |
| **TwoTier** | 0.000 | **0.236** | **0.351** | **0.969** |

**On this 55-PRB carrier (cap 2) TwoTier's telemetry reaches 0.969 — two
points below the starvation threshold — at ×2.0.** At the deployment's cap 4
it reaches 0.236. PF and Reservation are at zero throughout, on both caps.
So clause 4 passes for TwoTier by a margin that the carrier, not the
scheduler, supplies.

### 6.2 The first-violation order — NOT SCOREABLE, and the reason is arithmetic

**The specified sequence 9 → 4 → 2 is observed 0 times out of 10 on every
arm, every cell, both caps.** No arm produced a two-element order at all:
every scoreable sweep returned `[]` (nothing breached) or `[2]`.

**And `[2]` is an artefact of the traffic generator, not a scheduling
result.** The offered load of the 5QI-2 camera flows on UEs 1 and 2 is below
their own contract by construction:

| flow | offered | GFBR | **arithmetic ceiling on `gfbr_fraction`** |
|---|---|---|---|
| ue1/ue2 5QI 2 (`xr_video`) | 3.8788 Mbps | 4.0000 Mbps | **0.9697 — can never meet contract** |
| ue3 5QI 2 | 6.0606 Mbps | 6.0000 Mbps | 1.0101 |
| ue1 5QI 4 (`deterministic`) | 3.0000 Mbps | 3.0000 Mbps | 1.0000 |

Measured, N=6, TwoTier, median over seeds — the worst per-class contract
fraction at **every** ramp point from ×0.5 to ×2.0:

| ramp | ×0.5 | ×1.0 | ×1.4 | ×1.6 | ×2.0 |
|---|---|---|---|---|---|
| **5QI 2** | 0.965 | 0.965 | 0.965 | 0.965 | 0.965 |
| **5QI 4** | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

**5QI 2 is pinned 3.5 % below contract at every point, on every arm,
independent of load and of scheduling; 5QI 4 sits exactly at contract
throughout.** So the class that appears to "breach first" is the only one
that *cannot pass by construction*, and the class the specification says
should be sacrificed before it never breaches at all.

**This is a known, recorded scenario defect, not a new one.**
`sim/parametric.py` states it: *"OFFERED IS BELOW GFBR at every duty …
16 000 B / 33.0 ms = 3.879 Mbps against 4.000 Mbps, ratio 0.9697 — an
arithmetic ceiling of ~0.970 on gfbr_fraction. The same shortfall exists
independently in `sim/fleet.py`'s DRONE and UGV camera flows … Recorded, not
fixed: changing avg_bytes moves the regression corpus."* It reaches G12
through `build_fleet`.

**Consequence, stated plainly: G12's ordering clause cannot be scored on
this scenario, and the previously published TwoTier `[2,4]` was reading this
artefact.** It does not reproduce here at either cap, under either
tie-break. **That row is withdrawn.** Scoring the order needs a scenario
whose GBR flows offer at least their own GFBR — a fix that deliberately
moves the regression corpus and is therefore its own decision, not a
drive-by.

### 6.3 The tie-break control — load-bearing, and it moved exactly one cell

| cell | arm | tie-break OFF | tie-break ON (seed 4243) |
|---|---|---|---|
| N=6 | PF / Reservation / TwoTier | `[[], [2]]`, 9/10 | `[[], [2]]`, 9/10 — **same** |
| N=4 | PF / Reservation | `[[]]`, 10/10 | `[[]]`, 10/10 — **same** |
| **N=4** | **TwoTier** | `[[], [2]]`, 9/10 | **`[[]]`, 10/10 — DIFFERS** |

**One cell of twelve changed**: at N=4 a single TwoTier seed produced a
one-element order with position deciding ties, and none with a seeded
tie-break. Clause 4 is unaffected everywhere.

**So the gate's answer was right in both directions.** Ties never order 2
against 4 directly (§1), so the control could not manufacture a `[2,4]`;
but they do move *which UE* is served, so the control was load-bearing —
and it removed the only ordering signal that survived at N=4. **An ordering
result at this resolution is not separable from the tie-break, which is
another reason §6.2's verdict is "not scoreable" rather than "the order is
`[2]`".**

## 7. What an operator should take from this

1. **The safety telemetry survives the whole shift on every arm** — clause 4
   passes 10/10 across 240 ramp sweeps, at both carrier configurations, with
   no vacuous premises. This is the question that mattered and the answer is
   clean.
2. **TwoTier's margin depends on the carrier, not on its scheduling.** On
   the narrow 55-PRB cell its telemetry violation rate reaches 0.969 at
   twice committed load — just under starvation. On the deployment's wider
   configuration it reaches 0.236. PF and Reservation stay at zero.
3. **"What breaks first" cannot be answered on this workload**, because one
   GBR class is under-offered by 3 % by construction and can never meet its
   contract while the other sits exactly at contract. Any degradation order
   read off this scenario is reading the generator.
4. **The previously published TwoTier `[2,4]` inversion is withdrawn.**

## 8. Run times

| campaign | sweeps | driver runs | wall |
|---|---|---|---|
| Step 1 gate (tie measurement) | — | 6 × 6 000-slot runs | ~90 s |
| G12 stress, **cap 2** | 120 | 1 320 | **367 s** |
| G12 stress, **cap 4** (deployment) | 120 | 1 320 | **366 s** |
| **total** | 240 | 2 640 | **~14 min** |

12 workers, `OMP_NUM_THREADS=1`, on the post-optimisation code.
