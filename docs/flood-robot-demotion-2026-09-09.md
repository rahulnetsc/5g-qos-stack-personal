# The download-carrying robot is the one that does not stop

**2026-09-09.** Found inside G2's campaign, given its own document because it
is **the sharpest scheduler-differentiating result this evaluation has
produced** and because it is a property of the ranking, not of G2.

**One sentence:** on PF and Reservation, a robot that is receiving a large
transfer is systematically demoted at exactly the moment its emergency STOP is
pending, and holds **45–56 % of all missed STOPs**; on TwoTier it is not, and
holds a share indistinguishable from uniform.

**Artefacts:** `sweeps/g2-stress/g2_stress.json` and the controls described
below. **Cited from:** `docs/g2-slide-source.md` §4a,
`docs/GUARANTEE-RESULTS.md`.

---

## 1. The observation

G2's cell stops 12 robots simultaneously; one of them also carries the
saturating 50 Mbps downlink firmware pull. Misses do **not** spread evenly
across the twelve:

| arm | total misses | **the download-carrying robot's share** | uniform would be |
|---|---|---|---|
| **PF** | 68 | **55.9 %** | 8.3 % |
| **Reservation** | 162 | **45.1 %** | 8.3 % |
| TwoTier | 82 | **9.8 %** | 8.3 % |

Its mean STOP latency doubles on the two fairness-ranked arms — **3.99 ms
(PF) and 4.40 ms (Reservation) against ~2.0–2.4 ms for its peers** — while on
TwoTier it is **1.69 ms, the best of the twelve**.

## 2. The control: it follows the DOWNLOAD, not the position

The download robot is also the **last-declared** UE, and TwoTier's downlink
order is 88 % ties broken by declaration order — an entirely different
candidate cause. **The control moves both floods to the FIRST-declared robot
and changes nothing else.**

| floods on | PF: that robot's share | Reservation | TwoTier |
|---|---|---|---|
| robot 12 (last-declared) | **55.9 %** | **45.1 %** | 9.8 % |
| **robot 1 (first-declared)** | **46.7 %** | **45.9 %** | 5.7 % |
| — and robot 12, in that case | **3.3 %** | **2.2 %** | 8.6 % |

**The burden moves with the download.** The previously-worst robot falls to
2–3 %. **Declaration order is refuted as the cause**, and the effect is a
property of carrying the transfer.

## 3. The mechanism, read from each arm's ranking key and confirmed by trace

**Inside the trial windows** — the slots where every robot has a STOP pending,
which are the only slots where the question exists:

| arm | DL candidates | **download robot's rank** | fleet's rank | **demoted by** |
|---|---|---|---|---|
| **PF** | 6.2 | **5.21** | 3.47 | **1.74 places** |
| **Reservation** | 7.2 | **6.05** | 3.51 | **2.54 places** |
| TwoTier | 6.8 | 4.38 | 3.83 | **0.55 places** |

*(rank 0 = served first)*

**Why each arm behaves as it does, from the key each one declares:**

**PF** — `sim/baselines/pf.py`: `metric = bits_per_rb / _r_avg[ue_id]`, key
`(-metric,)`. **A single term, with nothing above it.** `_r_avg` is
incremented by every grant's delivered bits, so a robot that has just received
a large transfer has a high `_r_avg`, a low metric, and sorts last. **The STOP
has no tier to appeal to** — proportional fairness is working exactly as
designed, and the safety packet inherits the penalty because it rides the same
robot. Measured: `-metric` decides **99.7 %** of PF's downlink adjacencies.

**Reservation** — `_DL_TERMS = (has_srb, has_gbr, pdb_ms, -coef, tie_break)`.
**The deadline tier exists and sits above the channel term**, so on paper the
STOP should be rescued. **This measurement is the evidence for
`docs/reservation-edits.md` R4**, where it is diagnosed: the tier ties because
its values are coarse (13 distinct levels across every cell, whole-ms
truncation against a 0.25 ms slot) and saturate at zero (7.9 % → 24.4 % of
candidates as the fleet is stopped together) — **not** because of a sentinel
(9999 never appears) and **not** because the coefficient's range swamps it (a
lexicographic tier cannot be swamped from below). In practice **`-coef` decides 98.4 % of adjacencies
and `pdb_ms` only 0.6 %** — the tiers above `-coef` almost never separate two
candidates, so the throughput/channel term is effectively the whole key. **A
tier that exists but is never reached is not a protection**, which is the
recurring shape this project has already recorded for Tier-1.5's UL floor.

**TwoTier** — `_DL_TERMS = (has_gbr, pdb_ms, -coef, tie_break)`, and
**`pdb_ms` decides 8.1 % of adjacencies — 13× more often than Reservation's.**
The STOP's 5 ms deadline is actually consulted, and the demotion collapses to
0.55 places. **It does not eliminate it** — TwoTier still loses STOPs — but it
removes the concentration.

**And the magnitudes line up with the outcome**: Reservation demotes most
(2.54 places) and misses most (162); TwoTier demotes least (0.55) and shows no
concentration.

## 4. What this means for "is two-tier needed"

**This is the first unconfounded case in this evaluation where a QoS-aware
ranking demonstrably protects a safety packet that a fairness ranking
demotes.**

Three things make it stronger than the arm comparisons that came before it:

1. **It is DOWNLINK.** No BSR, no SR, no grant round-trip — the estimation
   pathology that qualifies most of this project's uplink findings is
   structurally absent. The gNB reads its own RLC buffers.
2. **It is controlled.** Moving the floods to a different robot moves the
   effect, so it is the transfer and not position, declaration order, or which
   UE happens to be last.
3. **It is mechanistic, not statistical.** The ranking key predicts it, and
   the trace confirms the predicted term is the deciding one at the slots that
   matter.

**It does not settle the question.** It is one clause, on one cell, in
simulation, and TwoTier still fails G2 in absolute terms — 82 misses of its
own. **What it settles is a narrower thing: that the QoS ranking is doing real
work that proportional fairness cannot do**, and doing it on the packet where
it matters most.

**It is also the counterweight to this project's own strongest sceptical
result.** `docs/grant-density-mechanism-2026-09-06.md` established that the
headline workload inversion was an intra-UE LCP effect **identical across all
three arms**, with no scheduler change able to reach it. This is the opposite
shape: the arms genuinely differ, the difference is in the ranking key, and it
is visible in the outcome an operator cares about.

## 5. Process notes — I got the mechanism wrong twice on the way

- **First attribution: PF's throughput history demotes it.** Stated with
  confidence before it was measured.
- **Then refuted, by the wrong instrument.** Mean downlink rank over *all*
  slots put the download robot at **0.63 against the fleet's 3.50** — ranked
  first, apparently exonerating the ranking. **That statistic ranges over the
  wrong rows:** the download robot is backlogged in nearly every slot and is
  often the only candidate, so its mean is dominated by slots where nothing
  competes.
- **Re-measured inside the trial windows, the original attribution holds.**
  The demotion is real, and only visible where the question exists.

**The lesson is the project's own decompose-before-attributing rule, committed
while applying it.** Before quoting a rank, a rate or a mean, name the rows it
sums over and the rows the claim is about — **a refutation needs that check as
much as a claim does.**

---

## 6. THE CATEGORY — PF's ranking is the same code everywhere

**`_r_avg` is one EWMA per UE, and CLAUDE.md's own invariant records that it
is SHARED ACROSS DIRECTIONS.** So the precondition is not "a firmware pull" —
it is **any robot that has recently moved a large volume in either
direction**, and every flow on that robot inherits the demotion.

**Enumerated over every builder the flow-key sweep already proves it covers**
(large ≥ 10 Mbps offered, urgent ≤ 20 ms PDB, both on one UE):

**19 of 42 built scenarios contain the coincidence.**

| where | the robot that carries both |
|---|---|
| **`scenario(6)`** — the regression corpus's own | ue10: 10 Mbps 5QI-9 **DL** beside a 5QI-82 **DL** at 10 ms |
| **`scenario(6)`** | ue5–7: 14 Mbps 5QI-2 UL beside 5QI-82 DL at 10 ms |
| **G12's fleet cells** (all four compositions, N=4 and 8) | the last UE: 50 Mbps 5QI-8 **UL** beside 5QI-82/83 at 10 ms |
| **G1's `gt11`** (N=4, 8, 16) | the last UE: 50 Mbps 5QI-9 **DL** beside 5QI-82 **DL** at 10 ms |
| **G2's `gt12`** | the last UE: 50 Mbps DL **and** UL, beside 5QI-82 and the 5QI-85 STOP |

### 6.1 G1 specifically — the driven robot never coincides, BY CONSTRUCTION

**Asked because it is the case that would matter most: if G1's driven robot
were ever the firmware puller, its cmd_vel would inherit the same demotion.**

**It never is.** `sim/scenarios/g1.py::build_gt11_scenario` puts cmd_vel on
robots `1..n_driven` and the firmware pull on robot `n_ues`, and **refuses a
scenario with `n_ues <= n_driven`** — so the two cannot be the same robot at
any parameter value.

**Two things follow, and the second is the uncomfortable one:**

1. **G1's published result is unaffected.** Its scored instrument never sits
   on the download robot.
2. **G1's result is therefore measured in a configuration that structurally
   AVOIDS this effect**, and is optimistic in that specific respect. **A
   deployment that teleoperates the robot which is pulling firmware is outside
   what G1 measured** — and G1's own fleet control loop (5QI 82) *does* sit on
   the download robot, so the shape is present in that cell even though the
   instrument dodges it.

**Stated rather than left for a reader to discover**, and it is a scenario
choice worth revisiting: driving the download robot is a realistic operation
and is currently untested.

### 6.2 What the census does and does not establish

**Does:** the PRECONDITION is widespread — 19 of 42 scenarios, including the
regression corpus's own — and PF's ranking is the same code in all of them.

**Does NOT:** that the effect is material in any of them. **It is measured
only in G2's cell.** Whether a 5QI-82 control loop on a download robot is
actually delayed enough to breach anything is a separate measurement per
guarantee, and none has been run.

**So this is a flagged precondition, not a set of new findings** — the
distinction this project draws between a mechanism existing and a mechanism
being reached, kept on the right side of the line.
