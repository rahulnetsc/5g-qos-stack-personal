# Guarantee results — the current answer for each

**2026-09-09.** One row per guarantee, **current only**. Where a figure was
withdrawn this says so and points at what replaced it; it does not reproduce
the withdrawn number.

**This supersedes `docs/GUARANTEE-TABLE-2026-09-07.md` as the place to read a
verdict.** That file is kept: it holds the 90-row clause-part scoring and the
supersession trail, and several of its rows are struck through in place.

---

## The two carrier caveats — stated once, governing every row

**M-6 is the deployed per-slot UE cap**, `min(prb_count // 24, 8)`, ported
from `gNB_scheduler_dlsch.c:1019-1023`. **The formula is faithful; the value
depends on the carrier, and this repo's carrier is not the deployment's.**

| | PRB | cap |
|---|---|---|
| this repo's parametric cell (40 MHz, μ=2) | 55 | **2** |
| the deployment (N_RB 106, μ=1) | 106 | **4** |

1. **cap 2 is this carrier's faithful derivation.**
2. **cap 4 is the deployment's value on half its bandwidth.**
3. **Neither is the deployment's system.** Both are run; **cap 4 is the number
   to quote**, and for **G2 the cap is not a detail — it is the dominant
   term.**

---

## The guarantees that have been rebuilt as stress experiments

Five so far. Each has a slide source, a Step-0 record of what had to be
corrected first, and a full record.

| G | question | current answer | slide source |
|---|---|---|---|
| **G1** | driving a robot feels immediate while the fleet works | **PASSES both criteria, 0 breaches of 960 runs.** Worst p98 **9.00 ms** against 95 (10.6× inside); worst command gap **103 ms** against 200 (1.9× inside); p99.9 **4.50 ms**. The QoS arms are **flat in fleet size**, PF degrades mildly. **TwoTier is the best arm, not the worst** | `docs/g1-slide-source.md` |
| **G2** | the master disconnects — does every robot stop in time | **FAILS its clause. 513 misses in 109 800 STOP trials → miss-rate ≤ 5.0 × 10⁻³ at 95 %.** Nothing is late — every delivered STOP arrived under **5.25 ms**, median 0.75 — **things are missing.** The axis that decides is how many robots stop AT ONCE, not load or fleet size | `docs/g2-slide-source.md` |
| **G9** | does a robot joining a busy cell start working immediately | **warm re-join free on every arm; cold attach ~100 ms, post-RLF ~1.1 s on PF/Reservation, flat across a 4× load range. TwoTier fails at 5–6 UEs** — half the cold attaches and **all** post-RLF recoveries never complete | `docs/g9-slide-source.md` |
| **G12** | what breaks first under overload, and does safety telemetry survive | **clause 4 PASSES 10/10 on every arm**, both caps, both tie-break settings. **The first-violation order is NOT SCOREABLE** — nothing breaks in the range swept, so the ramp must extend past ×2.0 | `docs/g12-slide-source.md` |
| **G3** | can the network make a healthy robot look dead | **FAILS on both QoS arms, PASSES on PF.** Campaign-wide, **36 telemetry silences of ≥ 2 s in 115 872** — PF **0 of 40 854**, Reservation 10, TwoTier 26. **The QoS arms' liveness boundary is exactly G10's contract boundary, 6 and 7**, while PF's is ≥ 24 | `docs/g3-slide-source.md` |

**All five withdrew a published figure**, and in four of the five the reason
was that **the statistic could not express the clause's own failure**:

| G | what was withdrawn | why |
|---|---|---|
| G1 | *"TwoTier 87.78 ms vs 100"* and *"teleop feels sticky on 7 shifts in 10"* | M01 is a worst-flow maximum landing on **uplink** on 9 runs of 9, against a **downlink** guarantee |
| G2 | *"PASS 10/10 at ×19 margin"* | **p98 substituted for a maximum**, on a bearer that discards at 5 ms against a 100 ms bound — the check could not have failed |
| G9 | the four join rows | run with a sim-only lever **on and undeclared**, on artefacts predating M-9 and M-6 |
| G12 | the `[2,4]` first-violation order | the 5QI-2 camera was pinned 3.5 % below its own contract, so the class that appeared to break first was the only one that **could not pass by construction** |
| G3 | *"max gap ≤ 500 ms: PF 10/10, Res 10/10, TwoTier 4/10"* | scored over **all flows**, so a saturating flood's own starvation counted as a telemetry failure; the correction to 10/10 was on pre-rebuild code, and **the telemetry bearer had no GFBR**, so two of the three criteria had no meaning |

---

## G2 — the safety-critical row, in full

**The clause: "100 % of STOP events ≤ 100 ms across all trials; demonstrated
miss-rate bound per §5.3."** The statistic is a **maximum** over assets and
trials, and the answer is a **rate with a confidence**, not a pass/fail.

| | |
|---|---|
| **demonstrated bound** | **miss-rate ≤ 5.0 × 10⁻³ at 95 %** (513 of 109 800; Clopper–Pearson, since the rule of three is the zero-miss case) |
| delivered STOP latency | p50 **0.75 ms**, p99 4.75, **max 5.25** |
| **what decides** | **how many robots stop AT ONCE** |
| what barely matters | fleet size, offered load, within-frame trigger phase |

**Boundary — the largest simultaneous-STOP count that loses nothing:**

| | PF | Reservation | TwoTier |
|---|---|---|---|
| **cap 4** (deployment's) | **4** | **1** · non-monotone | **4** |
| **cap 2** (this carrier) | **1** | **none — fails at 1** | **2** |

**Withdrawn: the previous "PASS 10/10 at ×19 margin".** It substituted a
**percentile for a maximum** on a bearer that discards at 5 ms against a
100 ms bound — **the check could not have failed**, and Reservation was
discarding 87 of 1 607 STOPs while reading a clean pass.

---

## G3 — the liveness row, in full

**The clause: "Max telemetry inter-arrival gap at MEC ≤ 500 ms; zero gaps ≥
T_live over the full campaign; p98 ≤ PDB."** Three parts. Part 2 is
**campaign-wide**, so one silence anywhere fails it.

| | PF | Reservation | TwoTier |
|---|---|---|---|
| **part 2, campaign-wide** | **PASS** — 0 of 40 854 | **FAIL** — 10 of 36 514 | **FAIL** — 26 of 38 504 |
| **fleet boundary (all parts)** | **≥ 24** | **6** | **7** |
| telemetry lost over the fleet axis | **3 of 18 000** | 4 310 | 2 351 |
| protected uplink at N=24 | **67.06 Mbps** | 23.87 | 24.20 |

**AND THE QOS ARMS' LIVENESS BOUNDARY IS G10's CONTRACT BOUNDARY, EXACTLY** —
6 and 7, the same two numbers — while PF's liveness boundary is at least 24
against its own contract boundary of 12. One mechanism reads out through both
criteria: a UE running out of uplink service.

**GT-2.3 (silence and resume) PASSES everywhere**, all three buckets, both
configurations, 180 runs, no resume failing to complete. The largest
post-silence gap anywhere is **134.25 ms**, 3.7× inside the bound.

**The UL service-interval floor FIRES — first measurement in this project.**
1 fire at N=4 rising to 744 at N=24 on TwoTier; `None` (no such tier) on PF and
Reservation. **It arms, fires, rises with load, and TwoTier fails anyway.**

**Two instrument defects were corrected first, and the second was in the new
instrument.** The telemetry bearer had no GFBR and therefore no prioritised bit
rate, which made the p98 criterion's GBR-conformance semantics inapplicable and
starved telemetry in the UE's own LCP — **not by outranking it**, which the
standard forbids, but by letting the camera exhaust the transport block in the
bucket-gated first round so the priority-ordered second round never ran
(24 062 of 24 062 starved grants). The root cause is a grant too small for the
urgent flow, and what makes it small is **FIX-2's own anti-monopolisation
reserve**: it withholds `min_rb` per still-unserved GBR follower, so on a 55-PRB
band eleven followers exhaust it and **above sixteen robots every grant in the
run is 5 PRB — including the top-ranked UE's, on 100 % of slots.** At sixteen
robots 97 % of grants to a robot with a pending heartbeat cannot carry it whole.
Nothing sizes an uplink grant by urgency in either code base, but that term
would be **inert**: it could not exceed a budget the reserve has already set. Then the replacement statistic — an
inter-arrival maximum — was found unable to see a robot that goes dark and stays
dark: **19 flow-runs silent for up to 9.5 s while the scored maximum read
114–342 ms.** Both statistics are now published.

---

## G10 — the fleet size everything else is ranged against

**PF 12 / Reservation 6 / TwoTier 7**, cap 4, RA + SRB, 10 seeds per point,
`n_ues ∈ {2,4,5,6,7,8,10,12,16}`. Re-measured 2026-09-09 and reproducing the
2026-09-08 figure cell for cell; **no arm is non-monotone**.
`sweeps/g1-stress/g10_remeasure_cap4.json`.

**Withdrawn twice before reaching this**: `8 / 4 / 4` (a 2× gap in the sweep
left every boundary unresolved) and `6 / 6 / 5` (measured while the camera
offered below its own GFBR, so the **camera's contract** rather than the
cell's capacity bound the boundary). Reservation's 6 never moved, which is the
confirmation — it was capacity-bound and therefore real.

---

## The guarantees not yet rebuilt

Their rows are **pre-GBR-fix** and are flagged as such in
`docs/gbr-offered-shortfall-2026-09-08.md` §4.5. Read them as stale numbers on
a workload whose camera offered load changed by 0.6–3.1 %.

| G | last verdict | why it is stale, and what it would take |
|---|---|---|
| **G4** | **not scoreable** — three independently fatal reasons: the artefact records p98 not p99; the axis is duty cycle, not silence length; and the gap buckets cannot resolve 1 s from 60 s | needs its own scenario, like G1's and G2's |
| **G5** | ≥ 99 % PDU sets: PF 10/10, **Res 1/10, TwoTier 0/10** | pre-fix; the attach path recovers Reservation to 10/10 |
| **G6** | 24/40, 25/40, 20/40 | pre-fix, **and the DL half (GT-4.2, marked P0) has never run** — no DL background flow existed until G1 built one |
| **G7** | fails clause 2; both QoS arms deliver 2.0–2.1× MFBR | pre-fix; the finding itself is a product one and survives |
| **G8** | Jain ≥ 0.90: PF 10/10, **Res 2/10, TwoTier 0/10** (cap 4: 7/10, 5/10) | pre-fix |
| **G11** | C1 and C3 PASS over 7.2 M slots; C2/C4/C5 not scoreable | C4 is **satisfied by construction** and cannot fail; C2 needs counters that have no C counterpart |

---

## The findings that are the product's, not the port's

Each is read from the deployed C and merely reproduced here. **No simulator
caveat touches any of them.** Full text: `docs/hardware-findings.md`.

1. **Tier-1.5's UL floor cannot arm in the fault it exists for** — its gate
   reads state set only inside the loop that skips the fault's own condition.
   **0 firings in 32,000 evaluations per starved UE.**
2. **Reservation has no floor at all** — the same fault, no remedy even in
   principle.
3. **MFBR bounds entitlement, not throughput** — 2.0–2.1× MFBR delivered on
   both QoS arms.
4. **The cold-start lock-out** — one mechanism behind four separate
   observations.
5. **NEW, from G2 — a SCHEDULER RANKING finding, and the sharpest
   arm-differentiating result in this evaluation.** **The robot receiving a
   large download is the robot that does not stop.** It holds **55.9 % of
   PF's missed STOPs and 45.1 % of Reservation's**, against **9.8 % on
   TwoTier** and 8.3 % if uniform; controlled by moving the download, at which
   point the burden moves with it. The mechanism is each arm's downlink key:
   PF ranks on `bits_per_rb / _r_avg` with **nothing above it**, Reservation
   has a deadline tier that **`-coef` pre-empts on 98.4 % of adjacencies**,
   and TwoTier's `pdb_ms` **decides 8.1 %, 13× more often**. **This is the
   first unconfounded case where a QoS ranking protects a safety packet that a
   fairness ranking demotes — and it is DOWNLINK, so no uplink estimation
   pathology is involved.** It does not settle "is two-tier needed"; it is the
   strongest evidence on that side so far.
   `docs/flood-robot-demotion-2026-09-09.md`.

6. **From G2: the emergency-stop bearer's own PDB is 20× tighter than
   the guarantee written on it, and it wins.** 5QI 85's standardised PDB is
   **5 ms**; G2's clause bound is **100 ms**; a STOP older than its PDB is
   discarded. **With the discard lifted to the clause's own bound, ZERO STOPs
   are lost in 5 760 events and the worst arrives at 12.25 ms** — 8× inside
   the guarantee. So the lost STOPs are not lost to congestion; they are
   thrown away by their own bearer while the network would have delivered
   them in time. **A specification finding, not a defect**: the PDB is
   TS 23.501's and the discard is what a delay-critical GBR bearer does.
