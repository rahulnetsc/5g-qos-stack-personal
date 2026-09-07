# Step 5 — the stress axes and the two unbuilt scenarios

**2026-09-07. Specification only; nothing built, nothing run.** Consolidates
Part 3's sweep design with this pass's corrections and the user's two axis
corrections, and states what each axis costs and what it would answer.

---

## 1. The two axis corrections, adopted

**(a) `load_mult` is the wrong axis for G1/G3/G5.** `sim/parametric.py:71-104`
scales **only the best-effort 5QI-9 filler**, deliberately — *"load_mult must
not change the quantity being measured"* — and the cell is **already ~1.5×
oversubscribed at ×1.0** (~96 Mbps offered against G12's measured 63.4 Mbps
ceiling; `ul_prb_util` **0.933** on all three arms). Raising it deepens a queue
that is already unbounded.

**The right knob is `committed_mult`** — GT-3.2's own mechanism, which scales
both GBR classes' offered rate **and** their GFBR together. It exists in
`sim/scenarios/g12.py` and would be ported onto the parametric cell.

**(b) G12 needs resolution near the knee, not a higher ramp top.** Measured:
**TwoTier's entire transition (telemetry M02 0.001 → 0.915) is inside the
single ×1.0 → ×1.6 step**; PF's knee is in (1.6, 2.3]; Reservation's in
(2.3, 3.3]; and **all three arms are at 1.000 by ×6.0**, so five of the current
eight ramp points carry no ordering information. **GT-7.3 itself specifies
+10 % steps; the campaign used up to ×2.0.** The axis is **×1.0 → ×2.5 at
0.1**.

## 2. The axis per guarantee

| guarantee | axis | current | reaches separation? | cost @ W=12 |
|---|---|---|---|---|
| **G1 · G3 · G5 · G8** | **`committed_mult` 1.0→2.3 @0.1 × `n_ues` {4,6,8,10,12,16}** — *one grid serves all four*, since `core.json` emits all their statistics from the same run | one point | G5/G8 yes, G1 partly, G3 no | **~14 min** (16-point L-shape, not the 84-point cross) |
| **G1-SD · G8-SD** | `n_ues` {20…50} × **`snr_spread_db` {0,6,12}** | one point, spread 0 | **G1-SD is 3 % from its bound at N=30** — not comfortable, near-boundary | **~8 min** |
| **G10** | `n_ues` **{2,4,5,6,7,8,10,12,14,16}** | {2,4,8,16} | too coarse **and on the wrong side** | free if merged into the core grid's axis 2 |
| **G7 c2** | `offer_x_mfbr` **1.0→3.0**, swept **downward** from 2.1, plus a **lightly loaded** point | one point | inverted — already 0/10 | ~8 min |
| **G7 c1/c3** | **aggressor COUNT** {1,2,4} — a bigger single aggressor cannot break c1 at `ul_prb_util` 0.933 | one point | no | with the above |
| **G12** | **`committed_mult` 1.0→2.5 @0.1** | ×1.0→×8.0, 8 points | overshoots; knee inside one step | ~28 min |
| **G11** | simulated duration | **already at it** (7.2 M slots, ×112-141 margin) | — | **do not re-run** |

**G10's correction, which Part 3 got right and my earlier reading did not:**
both QoS arms already fail at N=8 (Reservation 3/10, TwoTier 6/10), so
**{10, 12} resolves PF only.** The half that matters is **{5, 6, 7}**.

## 3. The four guarantees with no axis

| guarantee | proposed axis | why this one |
|---|---|---|
| **G2** | **simultaneous STOP count {1,2,4,8} × background saturation {none, UL, UL+DL}** | GT-1.2's own words. The DL level needs a DL background flow that no scenario has |
| **G4** | **silence length {1, 5, 10, 60 s} at CONSTANT message size** | the plan contradicts itself ({1,5,60} in the KPI line, {1,10,60} in GT-2.3) — **run both** rather than choosing silently |
| **G6** | **background offered rate {0, 0.5, 1, 2, 4} × direction {UL, DL}** — the one guarantee where `load_mult` IS the right knob, because background pressure *is* the treatment | the paired `bg=False` baseline already exists; the DL half is **P0** and unbuildable today |
| **G9** | **join rate** — `period_slots` {3200…200}, i.e. one join per 1.6 s → 0.1 s — **× `n_neighbours` {7,15}** | the lock-out is measurably a *joining* phenomenon: the attach seed is inert when all UEs start at slot 0 and decisive when they stagger |

## 4. The two unbuilt scenarios, specified

### GT-1.2 + GT-7.2 — G2's real condition

**What the plan requires and what ran:**

| | specified | what ran |
|---|---|---|
| load | *"both assets at full committed profile; cell **saturated both directions** with 5QI-9 (**worst legal case**)"* | nominal, UL-only background |
| trigger | *"scripted master-disconnect → **simultaneous** STOP datagrams to A and B"* | one STOP flow |
| storms (GT-7.2) | *"5 × 300 B bursts within the same 10 ms window on 5QI 1 UL, **50 storms/run**, coincident with the DL STOP pair"* | none |
| statistic | **100 % of STOPs ≤ 100 ms** — a **maximum**, per-trial, ≥ 30 trials/run | p98 |

**This is why G2 reads 10/10 at ×19-27 margin.** The scenario built is not the
scenario specified, and the specified one is the adversarial case — simultaneous
STOPs are precisely when a per-UE argmax scheduler *"is most tempted to
serialise badly"*, in the plan's own words.

**Build:** `sim/fleet.py` gains a simultaneous-STOP trigger and the storm
burst; the runner emits the **maximum** and the full trial distribution.
**The cost is the build, not the sweep** — the sweep itself is ~2.5 min.

### The DL background flow — the hidden dependency of four things

Every 5QI-9 flow in every built scenario is **uplink**. Only **~160-214 slots
per run** carry any DL grant. So:

- **G1's** clause names a downlink command and GT-1.1 requires *"saturating
  5QI-9 DL … an idle DL link measures nothing"* — the link is exactly that.
- **G6's** GT-4.2 half (*"a firmware push to one robot cannot blunt another
  robot's controls"*) is marked **P0** and **cannot be run at all**.
- **G2's** DL saturation level needs it.
- **M-6's DL cap** and **B1's DL trace** both need a contended downlink to
  measure anything.

**And Step 3 found a second, sharper prerequisite for TwoTier specifically:**
its DL coefficient is **0.0 for every candidate** because the only DL flow is
`Delay` class with **GFBR 0**, so Tier-1 assigns it no target. **A DL
background flow alone does not fix that — TwoTier's DL comparator needs a DL
flow with a GBR target to be non-degenerate at all.**

## 5. What this step deliberately does not do

**Nothing is built and nothing is run.** Part 2 established that six rows are
not deployment-representative until **M-6** and **M-9** exist, and both will
move whatever the axes measure. **Sweeping today produces boundaries that would
be retired**, which is the same trap as publishing a number before the clause
that scores it is complete.

**The whole fresh run is ~95 min at W=12 across ~3,900 runs. The cost is the
builds, not the sweeps**, and sweep resolution should not be traded against
wall-clock that is not the constraint.
