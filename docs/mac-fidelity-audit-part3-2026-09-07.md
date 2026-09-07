# Part 3 — the sweep specification for the fresh run

**2026-09-07.** Third of four. Companion to
`docs/mac-fidelity-audit-2026-09-07.md` (Part 1, **M-1 … M-13**),
`docs/mac-fidelity-audit-part2-2026-09-07.md` (Part 2), and
`docs/system-audit-2026-09-07.md` (**P3-1 … P3-3**, inherited below, not
repeated).

**Nothing was run and nothing was built.** Every number below is either read
from an existing artefact or derived from one. **The sweep itself must not run
yet:** Part 2 established that six rows are not deployment-representative until
**M-6** (the deployed 4-UE-per-slot cap) and **M-9** (the deployed 100 ms UL
anti-starvation rescue) exist, so a sweep run today produces results that would
be retired. **This part designs the sweep for code that does not exist yet.**

**One standing caveat on every cost figure below, stated once.** All timings are
measured on the **current** code (`docs/guarantee-scorecard-2026-09-07.md` §6,
12 workers, measured 10.4× speedup from serial). M-6 and M-9 change what the
scheduler evaluates per slot. **Every cost here is therefore a lower bound in a
configuration that will not exist when the sweep runs** — CLAUDE.md's
measurement-carries-its-configuration rule, applied to my own numbers.

---

## Four corrections to the axis reading before any spec

### C-1 — **`load_mult` is the WRONG load axis for G1/G3/G5, and the cell is already oversubscribed at ×1.0**

`sim/parametric.py:71-104` is explicit: `load_mult` scales **only the
best-effort 5QI-9 filler**, deliberately — *"load_mult must not change the
quantity being measured"*. And it is calibrated so that **×1.0 already offers
~96 Mbps UL at N=8**, against G12's own measured deliverable ceiling of
**63.4 Mbps**. Measured confirmation: `ul_prb_util` is **0.933 on all three
arms** in the g7 cell.

**So the cell is ~1.5× oversubscribed at `load_mult = 1.0`, and raising it adds
offered bytes to a flow that is already receiving residual only.** Above 1.0 it
deepens a queue that is already unbounded; it does not increase pressure on the
protected flows.

**The correct load axis for G1/G3/G5 is the COMMITTED load** — GT-3.2's own
words, *"step all GBR offered rates up together until the first flow's 2 s-window
GFBR check fails; that knee is the certified ceiling"*. That mechanism already
exists as `sim/scenarios/g12.py`'s `committed_mult`, which multiplies both GBR
classes' offered rate **and** their GFBR together. **The G12 ramp mechanism is
the right axis for G1/G3/G5, not just for G12.**

**This corrects P3-2's *"G1: offered load × fleet size, 4 load points"*** —
right in shape, wrong in which knob.

### C-2 — **ONE grid answers four guarantees; the cost estimate should be per GRID, not per guarantee**

`core.json` carries `G1_M01_*`, `G3_M03_*`, `G5_M05_*`/`G5_M06_*`,
`G8_M09_*`/`G8_M22_*` from the **same run**. So a single (committed_mult ×
n_ues) grid on the parametric cell produces **G1, G3, G5 and G8 simultaneously**.
Costing them separately would quadruple the estimate. The same holds for
`sensor_dense.json` (G1 `sensor_dense` + G8 `sensor_dense`).

### C-3 — **G10's boundary for the QoS arms is BELOW 8, not between 8 and 16 — P3-1's proposed {10, 12} resolves PF only**

Measured, per fleet size, seeds inside the point (`g10_attach.json`, plain
column):

| arm | N=2 | N=4 | **N=8** | N=16 | boundary lies in |
|---|---|---|---|---|---|
| PF | 10/10 | 10/10 | **10/10** | 0/10 | **(8, 16)** |
| Reservation | 10/10 | 10/10 | **3/10** | 0/10 | **(4, 8)** |
| TwoTier | 10/10 | 10/10 | **6/10** | 0/10 | **(4, 8)** |

P3-1 proposed **N ∈ {10, 12}**. That resolves PF's boundary and **cannot touch
the QoS arms' — both already fail at 8.** The sweep needs **{5, 6, 7}** as well.

**And the artefact already says why**: `n_never_granted` at N=8 is a median of
**1.0** on Reservation (max 2) and **0** on PF; at N=16, TwoTier's max is
**11 of 16 UEs never granted**. The boundary is the lock-out, and the lock-out
is what **M-9** is.

### C-4 — **G6 IS computable from the existing artefact, and it FAILS. The scorecard's stated reason for declaring it not-computable is wrong.**

The scorecard says *"the artefact stores only the perturbed arm's summary"*.
It does not. `sweeps/rerun-2026-09-06/g6/stage6_g6_n40.csv` holds **240 rows =
3 arms × 40 seeds × `bg ∈ {False, True}`**, carrying the **full metric panel**
in both `_all` and `.prot` populations. **`bg=False` is the unperturbed paired
baseline the clause requires.**

Scored here for the first time — the clause is a **conjunction** (*within its
bound* **and** *shifts ≤ +20 % relative*), paired per (arm, seed):

| statistic | PF | Reservation | TwoTier |
|---|---|---|---|
| **G1** `M01.prot.p98` ≤ 95 ms | within 40/40 · shift 26/40 · **BOTH 26/40** | 40/40 · 37/40 · **37/40** | 28/40 · 28/40 · **24/40** |
| **G3** `M03.prot.max_gap_ms` ≤ 500 ms | 40/40 · 36/40 · **36/40** | 40/40 · 38/40 · **38/40** | 38/40 · 32/40 · **32/40** |
| **G5** `M05.prot.fraction` ≥ 0.99 | 37/40 · 40/40 · **37/40** | **10/40** · 7/40 · **7/40** | **6/40** · 6/40 · **4/40** |

Worst relative shifts: G1 **+505 %** (TwoTier), **+222 %** (PF); G3 **+386 %**
(TwoTier). **The median shift is small (−0.5 % to +4.5 %) and the tail is
enormous** — which is exactly the mean-of-ratios trap CLAUDE.md's
decompose-before-attributing rule names, so both are reported.

**Two honest caveats, and the second matters.** (i) G5's relative shift is
`+inf` on most Reservation/TwoTier seeds because the **baseline itself is 0** —
the cold-start lock-out kills video with **no background at all**, so "shift"
is undefined, not infinite; those rows are unmeasurable for the +20 % half and
are counted as failures only on the within-bound half. (ii) The G6 cell runs
under **`wp9_sweep.BASE`**: `n_ues=8`, **`mfbr_multiple = 0.0`**, `bg` boolean —
**a different flag state from `core.json`, which carries MFBR 8 Mbps.** So G6
and G1/G3/G5 are not measured on the same configuration. That extends Part 2's
finding #9 with a specific mechanism.

**Consequence for this part: G6 does not need a run to get a first number. It
needs a run to get a DL background flow**, which no scenario has (Part 2), and
GT-4.2 — the DL half — is marked **P0**.

---

## How far is each passing row from its boundary?

Measured from `sweeps/fixed-2026-09-07/plain/*` — the **worst seed** in each
cell, never the median, because the boundary is a property of the worst run.
`×` is the multiple the statistic would have to move by to reach the bound.
**This is a distance in the STATISTIC, not in the axis** — labelled as an
estimate of axis distance only where the relationship is roughly linear.

| row | bound | PF worst | Res worst | TT worst | verdict |
|---|---|---|---|---|---|
| **G2 UL STOP p98** | ≤ 100 ms | 5.25 (**×19.0**) | 5.25 (**×19.0**) | 5.25 (**×19.0**) | **entirely inside the comfortable zone** |
| **G2 DL STOP p98** | ≤ 100 ms | 3.75 (**×26.7**) | 4.75 (×21.1) | 3.75 (×26.7) | **comfortable** |
| **G11 C1** worst 60 s window | M02w ≤ 0.02 | 0.00018 (**×112**) | 0.00014 (**×141**) | 0.00017 (**×121**) | **comfortable — and not to be re-run** |
| **G1 `sensor_dense` p98** | ≤ 15 ms | **14.5 (×1.03)** | **14.5 (×1.03)** | 11.5 (×1.30) | **NOT comfortable — 3 % from failing** |
| **G7 c1** victim PDU sets | ≥ 0.99 | 1.000 (0 % of budget) | **0.9934 (66 % of the 1 % budget)** | 1.000 (0 %) | **NOT comfortable on Reservation** |
| G3 max gap | ≤ 500 ms | 198.5 (×2.52) | 200 (×2.50) | **319.2 (×1.57)** | TwoTier is the close one |
| G5 frame age p95 | ≤ 67 ms | 26.6 (×2.51) | 23.5 (×2.85) | **55.7 (×1.20)** | TwoTier is 20 % from failing |
| G7 c1 A camera p98 | ≤ 150 ms | 23.5 (×6.4) | 22.7 (×6.6) | 53.4 (×2.8) | comfortable |
| G7 c1 A telemetry p98 | ≤ 100 ms | 47.3 (×2.1) | 24 (×4.2) | 42 (×2.4) | moderate |
| G1 core p98 | ≤ 95 ms | 33.5 (×2.84) | 28 (×3.39) | **98.5 (FAILS)** | already at the boundary on TwoTier |

**This corrects the brief's premise on two of its four "non-discriminating"
rows.** G2 and G11 C1 are genuinely comfortable (×19 and ×112). **G1
`sensor_dense` and G7 c1 are not** — they read 10/10 because **all three arms
sit at the same near-boundary point**, not because there is headroom:
- G1 `sensor_dense`: PF and Reservation are at **14.5 ms against 15 ms**. And
  the arms **do** separate on margin — TwoTier is at 11.5 ms (30 % headroom)
  **while running the cell at `ul_prb_util 0.930` against PF's 0.710 and
  Reservation's 0.453.** TwoTier is both faster and better utilised here, which
  is the opposite of its parametric-cell behaviour and is not reported anywhere.
- G7 c1: Reservation's worst run has already consumed **two thirds** of the 1 %
  incompleteness allowance. PF and TwoTier have consumed none.

**So only TWO rows are truly inside the comfortable zone: G2 (both directions)
and G11 C1.** The other two need a sharper statistic, not a longer sweep.

---

## Where the arms actually separate, measured

**G12's ramp, telemetry M02 (median over cells and seeds):**

| arm | ×1.0 | ×1.6 | ×2.3 | ×2.7 | ×3.3 | ×4.0 | ×6.0 | ×8.0 |
|---|---|---|---|---|---|---|---|---|
| PF | 0.000 | **0.000** | **0.439** | 0.849 | 0.991 | 0.996 | 1.000 | 1.000 |
| Reservation | 0.000 | **0.000** | **0.039** | 0.263 | 0.642 | 0.925 | 1.000 | 1.000 |
| **TwoTier** | **0.001** | **0.915** | 0.974 | 0.980 | 0.984 | 0.984 | 0.990 | 1.000 |

**TwoTier's entire transition — 0.001 to 0.915 — is hidden inside the single
×1.0 → ×1.6 step.** PF's knee is in (1.6, 2.3]; Reservation's in (2.3, 3.3].
Everything above ×3.3 is three arms at 1.000, i.e. **five of the eight ramp
points carry no information about ordering.**

**And GT-7.3 already specifies the resolution the campaign did not use:**
*"ramp aggregate offered load in **+10 % steps** of the measured ceiling, 60 s/
step, to 145 %."* The `RAMP` tuple uses steps of **0.6, 0.7, 0.4, 0.6, 0.7,
2.0, 2.0.** The plan asked for 0.1; the campaign used up to 2.0.

---

## The sweep specification, per guarantee

**Conventions for every row.** 10 seeds **inside** each axis point, never
pooled. The **boundary is the last passing point BEFORE the first failure**;
a non-monotone sequence (pass → fail → pass) is **reported as non-monotone and
not smoothed**. Where an arm passes at every point swept, the result is written
**"passes to at least X"**, which is a statement that the sweep was too gentle,
not that the arm is good. Cost is wall-clock at **W=12**, from measured
per-run medians ÷ 10.4.

### THE CORE GRID — serves G1, G3, G5 and G8 in one pass

| | |
|---|---|
| **Axis 1** | `committed_mult` (GBR offered rate **and** GFBR together, `sim/scenarios/g12.py`'s mechanism ported onto the parametric cell) — **NOT `load_mult`**, see C-1 |
| **Range/step** | **1.0 → 2.3 in steps of 0.1** (14 points). Rationale: TwoTier's telemetry knee is inside (1.0, 1.6]; PF's inside (1.6, 2.3]. Above 2.3 all arms are floored |
| **Axis 2** | `n_ues` ∈ **{4, 6, 8, 10, 12, 16}** (6 points) |
| **Design** | **L-shaped + 4 interior probes**, not a full cross: axis 1 at N=8, axis 2 at ×1.0, plus (×1.4, N=12), (×1.8, N=12), (×1.4, N=16), (×2.0, N=10) to test interaction. **16 points.** A full 14×6 cross is 84 points ≈ 74 min and is not justified until the L shows interaction |
| **Held fixed** | attach **OFF** (see the note on attach below), `cqi_delay_slots=8`, `min_rb=5`, MFBR 8 Mbps on 5QI 2, `truncated_bsr="off"`, 20 k slots |
| **Cost** | 16 × 10 seeds × 54.8 s/seed-triple ÷ 10.4 = **14 min** |
| **Expected separation** | G1: TwoTier fails at ×1.0/N=8 today, so its boundary is **below the grid's origin** — extend downward to ×0.8/×0.9 if it fails at 1.0. PF/Res have ×2.8–3.4 in the statistic, so expect their p98 boundary around ×1.5–2.0. G5: Reservation and TwoTier already fail at the origin without attach. G8: same |
| **On the floor** | **G1's boundary is the committed video+telemetry load at which teleop stops feeling immediate.** If TwoTier's is ×1.0 and PF's is ×1.8, a site commissioned on TwoTier must run its cameras at **55 % of the bitrate** PF would allow, for the same command responsiveness |

**Note on the attach column.** The fresh run should be **single-column, attach
OFF**, because **M-9's 100 ms rescue is expected to subsume the lock-out's
candidacy fault** — the very thing the attach seed stands in for. *"Does the
attach flag still move anything once M-9 exists"* then becomes a **one-point
registered check**, not a doubled grid. If it still moves rows, that is a
finding about M-9's implementation, not about commissioning.

### THE `sensor_dense` GRID — serves G1 `sensor_dense` and G8 `sensor_dense`

| | |
|---|---|
| **Axis 1** | `n_ues` ∈ **{20, 25, 30, 35, 40, 50}** (6). Today's 30 sits at **14.5 ms against a 15 ms bound** on PF and Reservation, so the boundary is **within one step above 30** |
| **Axis 2** | `snr_spread_db` ∈ **{0, 6, 12}** (3) — the knob exists (`sweep_scenario(snr_spread_db=...)`) and is **fixed at 0 in every published result**, so channel spread has never been varied at all |
| **Design** | full 6 × 3 cross = **18 points** (the cell is cheap) |
| **Cost** | 18 × 10 × 26.9 ÷ 10.4 = **7.8 min** |
| **Expected separation** | PF and Reservation fail between N=30 and N=35 on latency; **TwoTier has 30 % headroom and runs the cell at 0.93 PRB utilisation**, so its boundary should be materially higher — a result that reverses the parametric-cell ordering and is worth stating on its own |
| **On the floor** | **"How many 15 ms sensors fit on one cell."** If TwoTier holds 40 and PF holds 30, a dense-sensor deployment is a scheduler choice worth a third of the fleet |

### G10 — admissible fleet size

| | |
|---|---|
| **Axis** | `n_ues` ∈ **{2, 4, 5, 6, 7, 8, 10, 12, 14, 16}** (10 points) |
| **Correction** | P3-1 proposed {10, 12}. **That resolves PF only** — both QoS arms already fail at 8 (C-3), so **{5, 6, 7} is the half that matters** |
| **Step size** | **1 UE** in [4, 8] and [8, 16]. A robot is a discrete unit; there is no finer step, and no coarser one is defensible when the answer is a procurement number |
| **Clause scope** | today's row scores **M07 only — 1 of 8 sub-clauses.** The grid must emit G1/G3/G5/G8's statistics per N so the real clause (*"largest N with G1–G8 all-pass in 5/5"*) can be formed. **The core grid's axis 2 already does this** — G10 and the core grid should be **one artefact**, not two |
| **Cost** | 10 × 10 × 17.9 ÷ 10.4 = **2.9 min** standalone; **free** if merged into the core grid's axis 2 |
| **On the floor** | the standing example. **"PF holds to 8 robots, TwoTier to 4" means a fleet sized on TwoTier must be half the size** — and the whole deficit is the lock-out, which is what M-9 addresses |

### G7 — isolation

| | |
|---|---|
| **c2 axis** | `offer_x_mfbr` ∈ **{1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0}** (7). **Sweep DOWNWARD from today's 2.1×**, per P3-2 — the failure is already saturated at 2.1 |
| **c2 measured today** | PF ratio med **1.053** (min 0.924, max 1.119) — **PF straddles 1.0**; Reservation **2.025**, TwoTier **2.027**. **PF's apparent clipping is contention, not policy**: it delivers the aggressor its fair share, which happens to be ≈ MFBR at this load. The QoS arms pass the full offer through |
| **c2 result shape** | **not a pass rate — a delivered-vs-offered curve per arm.** The clause has no tolerance, so both QoS arms fail for any offer > 1.0 by construction; the informative quantity is the **slope**, and whether it ever bends |
| **c1/c3 axis** | **aggressor COUNT** ∈ {1, 2, 4}, not multiplier. c1 cannot be broken by a bigger single aggressor — the cell is already at `ul_prb_util 0.933` — but Reservation has already spent **66 % of its 1 % budget**, so a second aggressor is the plausible lever |
| **Design/cost** | 7 × 3 = 21 points × 10 × 24.4 ÷ 10.4 = **8.2 min** |
| **On the floor** | **c2's real answer is already known and the sweep only quantifies it: there is no rate limiter.** MFBR bounds entitlement, not throughput. The deployment consequence is that a mis-set encoder is contained only by *contention*, so containment degrades as the cell empties — **the sweep should therefore also include a LIGHTLY loaded point**, where PF's contention-based clipping disappears |

### G12 — overload degradation ordering

| | |
|---|---|
| **Axis** | `committed_mult` ∈ **1.0 → 2.5 in steps of 0.1** (16 points), replacing the current 8-point ramp |
| **Why 2.5 and not 3.3 or 8.0** | measured above: all three arms are floored by ×3.3 and identical by ×6.0. **Five of the eight current points carry no ordering information.** GT-7.3's own text asks for +10 % steps; the campaign used up to ×2.0 steps |
| **Resolution requirement** | **TwoTier's whole transition is inside one current step.** 0.1 puts ~6 points inside it |
| **Both clauses** | c4 (scored) and the **first-violation ordering** (unscored, and untestable in-range today — only 5QI 2 breaches below ×3.3, a one-element order). At 0.1 resolution the order becomes observable if it is observable at all; if it is still one element, **that is the reportable answer** |
| **Cost** | 16 points × 2 scoreable cells × 3 arms × 10 seeds × 18.3 s ÷ 10.4 = **28 min** — **at the flag boundary, deliberately.** Dropping to 0.2 steps halves it but loses TwoTier's knee |
| **On the floor** | **"the load at which telemetry stops being protected."** TwoTier's ×1.6 against PF's ×2.3 is not a win for PF — PF's telemetry survives longer only because PF is not protecting anything in particular; c4 is the clause that separates them, and it separates 0/20 vs 20/20 |

### G2 — STOP delivery *(no axis today; P3-3's proposal confirmed and made specific)*

| | |
|---|---|
| **Axis 1** | **simultaneous STOP count** ∈ {1, 2, 4, 8} — GT-1.2's *"simultaneous STOP datagrams to A and B"*, generalised to the fleet |
| **Axis 2** | **background saturation** ∈ {none, UL only, **UL+DL**} — GT-1.2's *"cell saturated both directions with 5QI-9 (worst legal case)"*. The **DL** level requires a DL background flow that **no scenario has** (Part 2) |
| **Inside every run, not an axis** | GT-7.2's **event storm: 5 × 300 B bursts within a 10 ms window on 5QI 1 UL, 50 storms/run**, coincident with the DL STOP pair. This is a scenario ingredient, not a sweep dimension, and costs nothing extra |
| **Statistic** | the **maximum**, not p98. The clause says *"100 % of STOPs ≤ 100 ms"*; today's artefact carries p98 and the scorecard correctly labels the substitution as weaker. **The fresh run must emit the max and the full trial distribution** (30 trials/run, ≥ 10 runs, per §5.3) |
| **Both directions** | GT-1.2's STOP is **downlink**. The artefact already carries `DL_stop_p98_ms` and it is unscored (Part 2, finding #3). **Score both columns** |
| **Design/cost** | 4 × 3 = **12 points** × 10 seeds × 13.0 s ÷ 10.4 = **2.5 min**. **The cost is the BUILD, not the sweep** |
| **On the floor** | **"how many robots can be stopped at once before one of them is late."** Today's answer — one STOP, unloaded, ×19 margin — is a smoke test presented as a safety guarantee |

### G4 — post-silence *(no axis today; P3-3's proposal confirmed, with two corrections)*

| | |
|---|---|
| **Axis** | **silence length** ∈ **{1, 5, 10, 60 s}** at **constant message size**. The clause line says {1, 5, 60}; GT-2.3 says {1, 10, 60}; **the plan contradicts itself and both should be run** rather than a choice being made silently |
| **Correction 1 — the current axis is not just different, it is confounded** | `DUTY_LEVELS = (1.0, 0.5, 0.1)` moves silence and payload together under `_burstify`'s constant-mean-rate design (already recorded). Decoupling them is a **scenario change**, not a sweep parameter |
| **Correction 2 — THE OBSERVATION BUCKETS CANNOT RESOLVE THE CLAUSE'S OWN BUCKETS** | `GAP_BUCKETS_MS = (0, 1, 10, 100, 1000, inf)`. A 1 s silence and a 60 s silence **land in the same bucket**. New bucket edges at **1 000 / 5 000 / 10 000 / 60 000 ms** are required or the axis is unobservable even once it exists |
| **Statistic** | **p99**, not p98. The scorecard notes p98 would be **optimistic**, not conservative — so substituting is not available |
| **Horizon** | a 60 s silence needs **> 120 000 slots** at 0.5 ms, **6× the standard 20 k horizon**. This dominates the cost |
| **Cost** | 4 points × 10 seeds × ~329 s/seed-triple ÷ 10.4 = **21 min**, of which the 60 s bucket alone is ~15. **Recommendation: 10 seeds at {1, 5, 10 s}, 5 seeds at 60 s** → ~13 min, with the reduced denominator stated on the row |
| **Depends on** | **M-2 structurally** — "first packet after silence" *is* the SR→grant→PUSCH round trip, and the simulator prices **zero** slots for it. GT-2.3 marks itself `Env: RF` essential, *"SR fragility does not manifest in rfsim"* |
| **On the floor** | **"how long a robot can pause before its next message is late."** A bound that holds at 1 s and fails at 60 s is a **finding about the SR path**, in the plan's own words — not noise |

### G6 — background isolation *(a number exists today; the axis is for the run after)*

| | |
|---|---|
| **Today** | **computable and FAILING** (C-4). No run needed for a first number |
| **Axis** | **background offered rate** — replace the `bg ∈ {False, True}` boolean with `load_mult` ∈ **{0 (paired baseline), 0.5, 1.0, 2.0, 4.0}** (5 points). This is the **one** guarantee where `load_mult` is the right knob, because background pressure **is** the treatment |
| **Second axis, and it is a BUILD** | **direction** ∈ {UL, **DL**}. GT-4.2 (*"a firmware push to one robot cannot blunt another robot's controls"*) is marked **P0** and **cannot be run at all** — every 5QI-9 flow in every built scenario is uplink, and only **160–214 slots per run** carry any DL grant |
| **Pairing** | the baseline must be **within-seed**, as today's `bg=False` cell already is. Do not pool |
| **Reporting** | **both halves of the conjunction separately, and the median AND the tail.** Today's medians are −0.5 % to +4.5 % while the worst shifts are **+222 % to +505 %** |
| **Cost** | 5 × 2 directions × 10 seeds × 54.8 ÷ 10.4 = **8.8 min** (4.4 min UL-only until the DL flow exists) |
| **On the floor** | **"how much background a cell can carry before the fleet notices."** And the answer today is that the *median* robot does not notice while the *worst* robot's command latency goes up 5× |

### G9 — join and recovery *(no axis today; P3-3's proposal confirmed and made concrete)*

| | |
|---|---|
| **Axis 1** | **join rate** — `gt61_warm_rejoin(period_slots=...)` already parameterises it. `period_slots` ∈ **{3200, 1600, 800, 400, 200}** = one join per **1.6 s → 0.1 s** (5 points) |
| **Axis 2** | **cell load** — `n_neighbours` ∈ **{7, 15}** (2 points) |
| **Precondition that is NOT optional** | GT-6.3's fade must **outlast t310 = 2 000 ms**. CLAUDE.md records the prior attempt scripting a fade **half** that length: no RLF declared, **zero join events**, and M18/M19 reporting *instant recovery* — every number correct for events that did not happen |
| **Assertions the runner must carry** | the **expected event count derived from the schedule** (not restated), **and** `n_never_completed`. The prior count-only assertion passed while TwoTier recorded 3.8 of 10 warm restarts and **completed 0 of 50 cold attaches** |
| **Statistic** | **per-run** values, not per-arm medians. Today's artefact stores `m18_p95_median` across runs, which is why no success rate can be formed |
| **Blocked on** | **RA + SRB (Part 1's Part-4 build).** *"Full attach-to-streaming ≤ 15 s"* is a bound on a procedure that does not exist. Axes 1–2 answer only the **warm re-join** and **post-RLF** thirds |
| **Cost** | 10 points × 10 seeds × 54.8 ÷ 10.4 = **8.8 min** |
| **On the floor** | **"how fast robots can be cycled through a busy cell."** A shift change is a join storm; if the bound holds at one join per 1.6 s and fails at one per 0.4 s, the deployment constraint is a **staggered power-on procedure** |

### G11 — **DO NOT RE-RUN**

30 simulated minutes **is** its axis and it is already there (7.2 M slots,
**×112–141** conformance margin). C3 (CoV across runs) and C4 (identical
PASS/FAIL) need a **redesign, not a run** — C4 is *satisfied by construction*,
i.e. a check that cannot fail, which is CLAUDE.md's own third fault shape.
**Cost: 0.**

---

## COST — the whole fresh run

Wall-clock at **W=12**, from measured per-run medians ÷ 10.4.
**Lower bounds** on code that does not exist yet (see the standing caveat).

| grid | guarantees served | points | runs | **wall** | over 30 min? |
|---|---|---|---|---|---|
| **core grid** (`committed_mult` × `n_ues`) | **G1, G3, G5, G8, and G10's axis 2** | 16 | 480 | **14 min** | no |
| **`sensor_dense` grid** (`n_ues` × `snr_spread_db`) | G1-SD, G8-SD | 18 | 540 | **7.8 min** | no |
| G10 standalone (fine steps 5–7, 10–14) | G10 | 10 | 300 | **2.9 min** (free if merged) | no |
| G7 (`offer_x_mfbr` × aggressor count) | G7 c1, c2, c3 | 21 | 630 | **8.2 min** | no |
| G12 (`committed_mult` 1.0→2.5 @ 0.1) | G12 c4 + ordering | 16 × 2 cells | 960 | **28 min** | **at the flag** |
| G2 (STOP count × saturation) | G2 | 12 | 360 | **2.5 min** | no — **the cost is the BUILD** |
| G4 (silence length) | G4 | 4 | 90–120 | **13–21 min** | no, but 60 s dominates |
| G6 (background rate × direction) | G6 | 10 | 300 | **8.8 min** | no |
| G9 (join rate × cell load) | G9 (warm + post-RLF thirds) | 10 | 300 | **8.8 min** | no |
| G11 | — | — | — | **0 — do not re-run** | — |
| **TOTAL** | | **~123 points** | **~3,900 runs** | **≈ 95 min** | |

**Under two hours of wall clock for the entire fresh run.** Nothing exceeds
30 minutes except G12, which sits at 28 and is at the flag deliberately —
halving its resolution to 0.2 would save 14 minutes and lose TwoTier's knee,
which is the one thing the sweep exists to find.

**The cost is not the sweep. It is the builds.** In order:

| build | blocks | rough size |
|---|---|---|
| **M-9** (100 ms `high_inactivity` rescue) | G3, G5, G8, G10, G12 c4 | one commit + a deliberate corpus re-baseline |
| **M-6** (4-UE-per-slot cap) | G1, G2 DL, G5, G8, G10, G12 | one commit + a corpus re-baseline; **arm-differential, so it must land separately from M-9** |
| **M-4** (BSD from PDB, PBR from the enum ladder, non-GBR PBR = kBps8) | G1, G2 UL, G3, G5, G7 | one commit |
| **M-2** (UL k2 on first transmission) | G2 UL, **G4 structurally** | one commit |
| **DL background flow** | **G1, G2 DL, G6 (GT-4.2 is P0)** | a scenario change |
| **GT-1.2 / GT-7.2 scenario** (saturation, simultaneity, storms) | G2 | a scenario build |
| **G4 silence decoupling + bucket edges** | G4 | a scenario change |
| **RA + SRB** | **G9's attach third**, `has_srb` | **one full work package** (Part 1's Part-4 item) |

**One-fidelity-change-per-commit still applies**, so M-9, M-6, M-4 and M-2 are
**four separate corpus diffs**, each recorded. **M-6 and M-9 must not be
bundled** — Part 2's rule that they oppose each other means a bundled diff is
uninterpretable, which is the whole reason the rule exists.

---

## THE RESULT SHAPE

**Per guarantee, per arm, one table:**

```
G<n> · <clause text, verbatim from the test plan line>
axis: <name> · range <lo>..<hi> step <s> · seeds 10 inside each point

arm          x1.0   x1.1   x1.2   x1.3   ...   boundary
PF           10/10  10/10  10/10   9/10  ...   x1.2
Reservation  10/10   8/10   3/10   0/10  ...   x1.0
TwoTier       6/10   0/10   0/10   0/10  ...   BELOW RANGE  <- extend downward
```

**Six rules, each from a defect this project has already produced:**

1. **The seed denominator stays inside a point.** Pooling across axis points is
   what turned G10's *"PF holds twice the fleet"* into *"near-identical arms"*.
2. **The boundary is the last passing point BEFORE the first failure.** Not the
   first failure, not an interpolation.
3. **Non-monotone sequences are reported as non-monotone.** A pass → fail →
   pass run is a finding about variance or about a mechanism, and smoothing it
   destroys the only evidence of it.
4. **"Passes to at least X" where an arm never fails** — and that is a statement
   about the sweep, not about the arm. Four rows read 10/10 today for exactly
   this reason.
5. **Report the margin at the boundary point, not only the verdict.** G1
   `sensor_dense` reads 10/10 at **3 % headroom**; G2 reads 10/10 at **×19**.
   The same cell in a success-rate table, two completely different results.
6. **State the population beside every number** (`sums_over` / `claim_about`),
   as the scorecard now enforces — and for a sweep add **which axis point** and
   **which flag state**, since a measurement carries its configuration.

**And one output that is not a table:** for every row that still passes at every
point swept, the deliverable is *"the axis was pushed to X and did not break
it"* **with the cost of pushing further**, so the decision to stop is explicit
rather than implied by where the sweep happened to end.

---

# FINDINGS, RANKED

| # | finding | touches | consequence |
|---|---|---|---|
| **1** | **`load_mult` is the wrong load axis and the cell is already ~1.5× oversubscribed at ×1.0** (96 Mbps offered against a measured 63.4 Mbps ceiling; `ul_prb_util` 0.933 on all three arms). It scales only the best-effort filler, by design | **the axis for G1, G3, G5** | P3-2's *"4 load points"* would have swept a knob that adds bytes to a flow already getting residual only. **The right knob is `committed_mult`**, which exists in `sim/scenarios/g12.py` |
| **2** | **G6 is computable from the existing artefact and it FAILS.** 240 paired rows, `bg ∈ {False, True}`, full panel. Conjunction: G1 **26/40 · 37/40 · 24/40**, G3 **36 · 38 · 32**, G5 **37 · 7 · 4** | **G6's not-computable status** | The scorecard's stated reason — *"stores only the perturbed arm's summary"* — **is wrong**. A guarantee declared unscoreable has been scoreable all along, and it fails |
| **3** | **Two of the four "non-discriminating" rows are not comfortable — they are at their boundary.** G1 `sensor_dense`: PF and Reservation at **14.5 ms against 15 ms (3 % headroom)**. G7 c1: Reservation has spent **66 % of its 1 % budget** | **the premise that four rows need pushing** | Only **G2 (×19–27)** and **G11 C1 (×112–141)** are genuinely comfortable. The other two need a **sharper statistic**, not a longer sweep — and G1 `sensor_dense` **already separates the arms on margin, in TwoTier's favour**, which no published row says |
| **4** | **G10's QoS-arm boundary is below N=8; P3-1's proposed {10, 12} cannot reach it.** Reservation 3/10 and TwoTier 6/10 already at N=8 | **G10's sweep design** | **{5, 6, 7} is the half that matters.** And `n_never_granted` (median 1.0 at N=8 on Reservation, max **11 of 16** at N=16 on TwoTier) says the boundary **is** the lock-out — i.e. **M-9** |
| **5** | **Five of G12's eight ramp points carry no ordering information, and TwoTier's whole knee is inside one step.** telemetry M02: TwoTier 0.001 → **0.915** across ×1.0 → ×1.6; every arm is 1.000 by ×6.0 | **G12's resolution** | **GT-7.3 specifies +10 % steps; the campaign used up to ×2.0.** 1.0 → 2.5 at 0.1 is both the plan's own resolution and the range where the arms separate |
| **6** | **G4's observation buckets cannot resolve the clause's own buckets.** `GAP_BUCKETS_MS` tops out at `1000 → inf`, so a **1 s and a 60 s silence land in the same bucket** | **G4's axis, twice over** | The axis is wrong (`duty_cycle`) **and** the instrument could not read the right axis if it existed. Both must change. Plus: the plan contradicts itself, {1, 5, 60} vs {1, 10, 60} — **run both** |
| **7** | **G7 c2's "PF clips" is contention, not policy.** PF ratio med **1.053** (straddling 1.0) against the QoS arms' 2.03, at `ul_prb_util 0.933` | **G7 c2's interpretation and its sweep** | Containment that comes from contention **weakens as the cell empties**, so the sweep must include a **lightly loaded** point. c2's result shape is a **delivered-vs-offered curve**, not a pass rate |
| **8** | **`snr_spread_db` has never been varied** — `wp9_sweep.BASE` fixes it at 0.0 and every published result inherits it. `mfbr_multiple` is **0.0** in that BASE and **2.0** in the parametric cell | **G8's second axis; cross-artefact coherence** | Channel spread is the physically obvious fairness axis and has zero coverage. And **G4/G6 run at MFBR 0 while G1/G3/G5/G8 run at MFBR 8 Mbps** — extends Part 2's finding #9 with the mechanism |
| **9** | **The whole fresh run is ≈ 95 min of wall clock at W=12 across ~3,900 runs.** Only G12 approaches the 30-minute flag, at 28 | planning | **The cost is entirely in the builds, not the sweeps** — four separate corpus re-baselines (M-9, M-6, M-4, M-2), three scenario changes, and one full work package (RA + SRB). Sweep time is not the constraint and should not be traded against resolution |

**Nothing here makes the rest of the audit unsound.** Finding #2 is the one that
changes a published status — G6 moves from *not computable* to *computable and
failing* — but it **adds** a result rather than retracting one, and the fresh
run's design is unaffected because G6's remaining gap (the DL background flow)
was already identified in Part 2.

---

**PART 4 CONTINUES IN `docs/mac-fidelity-audit-part4-2026-09-07.md`** — the
ordered build plan. **It corrects this part's finding #8:** `snr_spread_db`
**was** swept in WP9's regime map (60 of 1,770 stage-1 rows, 360 of 720 part-C
rows). The corrected claim is that it is 0.0 in every artefact the **guarantee
scorecard** reads.
