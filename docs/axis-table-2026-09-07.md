# The guarantee table in axis form — boundaries, not single points

**2026-09-07, after M-9 and M-6 landed and were scored separately.**
Per guarantee per arm: the **boundary** (last passing axis point before the
first failure) and the **success rate at each point**, seeds always **inside**
a point and never pooled.

---

## 0. THE CORRECTION THAT MUST TRAVEL WITH EVERY PDCCH CLAIM

> **`sensor_dense`'s "PDCCH binds at 92 % of achievable, 40.7 % of slots at the
> per-slot cap" DOES NOT SURVIVE M-6.**
>
> With the deployed per-slot UE cap in place, **`cce_slots_at_cap` is ZERO** and
> U-slot CCE utilisation falls **0.84 → 0.336**. The UE-count cap binds
> *first* and leaves the CCE budget slack. **That headline was measured without
> the deployed cap.**
>
> It also inverts my own registered prediction that M-6 might make CCE bind for
> the first time: the two are **alternative limiters**, and the UE cap is the
> tighter one. Corrected here, in `sim/tests/test_capacity_denominators.py`
> (whose assertions now pin the capped behaviour), and in the M-6 result doc.

## 1. THE CAP CAVEAT, on every row M-6 touches

| | PRB | derived cap |
|---|---|---|
| this repo's parametric cell (40 MHz, μ=2) | **55** | **2** |
| this repo's `sensor_dense` (30 MHz, μ=1) | 83 | 3 |
| **the deployment** (N_RB 106, μ=1) | **106** | **4** |

The formula `min(prb_count // 24, 8)` is a faithful port; **the value is not
the deployment's**, because the carrier is not. **Both were run.**

**Which is the deployment-faithful number? Neither exactly — cap = 4 is the
deployment's VALUE, and it is the one to quote**, but the deployment also has
**106 PRB**, so its *system* is neither of these. Running cap 4 on a 55-PRB
carrier gives the deployment's DCI budget on half its bandwidth.

**And the difference is not a uniform softening.** Across the 22-row scorecard:
**8 rows softer at cap 4, 4 rows HARSHER, 66 unchanged.** A looser cap admits
more UEs per slot, which spreads service (helping fairness and starvation) and
lengthens individual tails (hurting max-gap and frame-age):

| softer at cap 4 | harsher at cap 4 |
|---|---|
| G8 Jain parametric — Res **2→7**, TT **0→5** | G3 max gap — TT **4→2** |
| G8 epochs parametric — TT **0→6** | G5 frame age — TT **4→0** |
| G3 zero gaps ≥ T_live — TT **6→10** | G7 c1 PDU sets — TT **9→6** |
| G5 ≥99 % sets — TT **0→2**; G10 — TT **20→22** | G1 `sensor_dense` — Res **10→9** |

## 2. G10 — admissible fleet size. THE AXIS THAT WAS WRONG

`n_ues ∈ {2, 4, 5, 6, 7, 8, 10, 12, 16}`, 10 seeds inside each point.
**The {5, 6, 7} correction was right and it changes every boundary.**

**cap = 2 (this carrier)**

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | **boundary** |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10/10 | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 | 9/10 | 0/10 | **6** · non-monotone |
| Reservation | 10/10 | 10/10 | 10/10 | 10/10 | **2/10** | 1/10 | 0/10 | 0/10 | 0/10 | **6** |
| TwoTier | 10/10 | 10/10 | 10/10 | **2/10** | 0/10 | 0/10 | 0/10 | 0/10 | 0/10 | **5** |

**cap = 4 (the deployment's value)**

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | **boundary** |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10/10 | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 | 9/10 | 0/10 | **6** · non-monotone |
| Reservation | 10/10 | 10/10 | 10/10 | 10/10 | 3/10 | 1/10 | 0/10 | 0/10 | 0/10 | **6** |
| TwoTier | 10/10 | 10/10 | 10/10 | **9/10** | 6/10 | 2/10 | 0/10 | 0/10 | 0/10 | **5** |

**Every boundary is at 5-6, not 8.** The old {2, 4, 8, 16} grid put all three in
an unresolved 2× gap and the pooled figure read them as near-identical.

**PF is NON-MONOTONE** — 9/10 at N=7, back to 10/10 at N=8, 9/10 at N=12. Per
the standing rule the boundary is the **last passing point before the first
failure = 6**, and the non-monotonicity is reported, not smoothed. It is a
finding about variance at the knee, not noise to average away.

**The cap changes the SHAPE, not the boundary.** TwoTier's decline is a cliff
at cap 2 (10/10 → 2/10 in one step) and a slope at cap 4 (10/10 → 9/10 → 6/10 →
2/10). **Same boundary, very different degradation** — and a slope is what an
operator can be warned about.

> **DEPLOYMENT CONSEQUENCE.** **The cell hosts 5-6 robots with the GBR contract
> intact, on every arm — not the 8 previously published.** PF degrades
> gracefully past it; TwoTier falls off a cliff at the deployment's own cap and
> a sheer one at this carrier's. **A fleet sized on the old figure is
> over-provisioned by ~30 %.**

## 3. G12 — the fine ramp, and it cannot be scored under M-6

`committed_mult ∈ {1.0, 1.1, … 2.5}`, 16 points, GT-7.3's own +10 % resolution
(the shipped tuple used steps up to 2.0 and five of its eight points carried no
ordering information).

**The ramp ran and the result is that there is no result:**

```
mixed_n8         CONTAMINATED: 10/30 (arm, seed) groups breach at x1.0; EXCLUDED WHOLE
ugv_heavy_n8     CONTAMINATED: 12/30 ...
drone_heavy_n8   CONTAMINATED: 10/30 ...
cells with a clean control: []
NO CELL HAS A CLEAN CONTROL. E1 fails outright and no ordering is computed.
```

**Under M-6 the ramp has no clean bottom.** The cap causes GBR breaches at
×1.0 — the ramp's own origin — in 10-12 of 30 groups in every cell, so E1's
precondition fails and the ordering clause is unscoreable **for a new reason**.
It was previously unscoreable because the order was a one-element list; it is
now unscoreable because the workload is already breaching before the ramp
starts.

> **DEPLOYMENT CONSEQUENCE.** **At the deployed per-slot cap this workload is
> already over capacity at its nominal load.** G12's ramp was designed on a
> simulator without the cap and its origin is no longer a valid baseline. The
> ramp must be re-based to a load the capped cell can actually carry before the
> safety-ordering clause can be asked at all.

## 4. G1 / G3 / G5 / G8 — the load axis is a BUILD, not a sweep

C-1 established that `load_mult` is the wrong knob: it scales **only** the
best-effort filler by design, and the cell is already ~1.5× oversubscribed at
×1.0 (`ul_prb_util` 0.933). The right knob is **`committed_mult`**, which
scales both GBR classes' offered rate *and* their GFBR together.

**Measured: `committed_mult` does not exist on the parametric cell.** It is
`sim/scenarios/g12.py`'s mechanism and `sim/parametric.py` has no equivalent
(`grep` returns nothing). **Porting it is a build, and it is not done here.**

**What is available today is the fleet-size axis**, which the core grid shares
with G10 — and §2's boundaries apply to it.

## 5. The four guarantees still with no axis

Unchanged from the Step 5 specification and **all four need a scenario build**,
not a sweep: **G2** (simultaneous STOPs × saturation, plus GT-7.2's 50
storms/run), **G4** (silence length at constant message size, plus bucket edges
that can resolve 1 s from 60 s), **G6** (background rate × direction — the DL
half is **P0** and unbuildable without a DL background flow), **G9** (join rate
× cell load).

## 6. Staleness — swept, not trusted to row labels

Run over the whole table with the code-state stamp:

| artefact | before | after |
|---|---|---|
| the five M-6 grids | **all STALE** (they predate the cap-override commit) | **regenerated, all CURRENT** |
| G6 `stage6_g6_n40` | **UNSTAMPED** and pre-M-6 | **re-run under M-6**; its runner still does not stamp — a gap |
| G11 C1, G11 C345, G12 | **UNSTAMPED** | still unstamped; they predate stamping entirely |

**G6 re-run under M-6 — and its G5 half collapses:**

| G6 conjunction | PF | Reservation | TwoTier |
|---|---|---|---|
| G1 half | 24/40 | 25/40 | 20/40 |
| G3 half | 37/40 | 38/40 | 33/40 |
| **G5 half** | 36/40 | **0/40** | **0/40** |

> **DEPLOYMENT CONSEQUENCE.** **With background traffic present and the deployed
> cap in place, neither QoS arm delivers complete video on any seed.** The
> previous 10/40 and 6/40 were measured without the cap.
