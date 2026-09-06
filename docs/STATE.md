# State of the guarantee evaluation — start here

**2026-09-06.** A cold-start document. Everything below is current; where a
number is superseded it says so and says by what.

**Count, as of 2026-09-06: ELEVEN guarantees carry a verdict. One of those is
partial (G11 — two clauses of five). G6's is "fails clause 1" rather than a
clean result. G2 alone has none.**

**G12 lost its verdict and got it back the same day.** Its published artefact
had a flow collision — two flows sharing one buffer, not merely one record
(defects log #30) — so the re-run refused it. **Fixed and re-scored**
(`docs/g12-collision-fix-result-2026-09-06.md`): the flood is now 5QI 8 with
priority pinned, `mixed_n8` is bit-identical, and clause 4 still fails. **The
published FIGURES do not survive** — the background at the point telemetry
floors is **8.5 Mbps (PF) / 14.6 (TwoTier)**, not 11.6, because most of the
published background throughput was DL grants draining a UL queue that should
never have been shared.

Use that wording rather than "11 of 12" or "12 guarantees".

---

## 1. The guarantee table

`code state` is the AST hash of `sim/` + `scheduler/` at the time the
artefact was produced; **HEAD is `b9122b2…`**. A row whose stamp differs was
measured on earlier code and its numbers are indicative, not current.

| G | verdict | artefact | n | horizon | workload | code state |
|---|---|---|---|---|---|---|
| **G1** | **PASS all arms.** M01 p98 protected: PF 25.25 / Res 23.00 / **TwoTier 87.78 ms** vs 100 ms | `phase2/core_scaled.json` | 10 | 40k | parametric | **current** |
| **G2** | **NO VERDICT** — see §5 | `postscaling/g2_ul_stop.json` | 10 | 20k | fleet + UL STOP | stale |
| **G3** | **INCONCLUSIVE.** M20 TwoTier +21.34 % [−2.81, +50.02] | `phase2/core_scaled.json` | 10 | 40k | parametric | **current** |
| **G4** | **PASS.** Separation only at duty 0.1; TwoTier−PF +6.76 [+5.52, +7.93] | `postscaling/g4.json` | 10 | 20k | parametric | stale |
| **G5** | **RE-SCORED — the published rate is an artefact**, and its residual is now **CLOSED** (§3a: M05 0.993–0.997 on all arms post-attach). Was Res 30/40, TT 34/40; under an attach path **Res 1/10 marginal, TT 0/10** | `phase2/core_scaled.json` + `g5_rank_attach_scaled.json` | 10 | 40k | parametric | **current** |
| **G6** | **FAILS clause 1, every arm.** Not a clean result — see §5 | `postscaling/g6seeded/` | 40 | 20k | parametric + aggressor | stale |
| **G7** | **FAILS clause 2.** Both QoS arms deliver **2.0–2.1× MFBR**; PF (no MFBR concept) contains better at 1.05×. **PF's containment is now EXPLAINED and is not a fairness property — it grants ~5.8× less** (§3a) | `rerun-2026-09-06/g7.json` | 10 | 20k | fleet + aggressor | **current** |
| **G8** | **FAILS.** M09 protected: Res 1/10, **TT 3/10** below 0.90 | `phase2/core_scaled.json` | 10 | 40k | parametric | **current** |
| **G9** | **SCOREABLE (first time).** Counts complete 10/10, 5/5, 1/1 with the re-join seed. **Clause 4 FAILS on TwoTier** | `postscaling/g9_seeded.json` | 10 | 20k | G9 scenarios | stale |
| **G10** | **PF 8 / Res 4 / TT 4 — UPPER BOUND, not capacity.** Cause established, §3 | `phase2/g5_consol_scaled.json` | 10 | 20k | parametric | **current** |
| **G11** | **TWO CLAUSES OF FIVE.** C1 PASS (900 windows, 0 failing); C3 PASS. C4 not independent; C5 not scoreable; C2 not scoreable | `postscaling/g11_c1_soak.json` | 10 | **7.2M** | G11 scripted | stale |
| **G12** | **RE-SCORED after the collision fix. Clause 4 FAILS on PF and TwoTier** — telemetry M02 ≥ 0.92 while background still carries **8.5–14.6 Mbps**; **TwoTier floors at ×1.6, one ramp point EARLIER than published**. **Not satisfied as written on Reservation** (its background is gone by the time telemetry floors). Ordering **still not established** — the permutation control still flips it. | `g12-rescore-2026-09-06/g12.json` | 10 | 20k | fleet ramp | **current** |

**Also measured on sensor_dense** (30 UL sensors, **15 ms PDB**, n=10, 20k):
G1 **PASS all arms** (PF 13.50 / Res 14.25 / **TwoTier 11.00 ms**), G3, G8
(**Res M09 0.7205, failing 10/10**).

---

## 2. The four findings for the hardware team — one set

Each is read from the deployed C's source and merely *reproduced* by a
faithful port. **No simulator caveat touches any of them.** Full text:
`docs/hardware-findings.md`.

**Shared shape: a mechanism exists, is named for the guarantee it serves, is
faithfully ported, and does not produce the outcome the guarantee is written
in terms of.**

1. **Tier-1.5's UL floor cannot arm in the fault it exists for.** Its gate
   reads `has_pending_gbr` (`ia_p5g_scheduler.c:2325`), set only inside the
   loop that skips every zero per-LCG entry — the exact condition its own
   comment names as defining the fault. Measured: **0 firings in 32,000
   evaluations per starved UE**.
2. **Reservation has no floor at all** — the complement, not another
   instance. The same fault, no remedy even in principle.
3. **MFBR bounds entitlement, not throughput.** The clamp limits `_target`,
   the GBR obligation; the overflow goes to best-effort and stays
   deliverable. **Measured 2.0–2.1× MFBR delivered on both QoS arms.**
4. **The cold-start lock-out** (§3) — the mechanism behind four separate
   observations.

**All four are questions, not defect reports.** Each has a reading under
which the code is right and a guarantee's *wording* is what should change.

---

## 3. The consolidation — one mechanism, four observations, one intervention

A UE whose `estimated_ul_buffer_per_lcg` reads zero enters the sort with
`has_gbr=False` / `pdb_ms=9999`, loses to every UE holding real QoS state,
and **cannot earn the grant that would repopulate the array**.

| observation | cleared by supplying the attach BSR? |
|---|---|
| G5's completeness (Res 7/10, TT 4/10 failing) | **yes** — Res 1/10 marginal, TT 0/10 |
| G10's admissible fleet (PF 8 / Res 4 / TT 4) | **yes** — all three arms identical, common boundary 8 |
| the UL blackout rate | **yes** — same count, renamed |
| G9's join counts (4 of 10 warm events) | **yes** — 10/10, 5/5, 1/1 |

**Supporting prediction: `n_never_granted > 0 ⟺ M08 floored`, zero
counterexamples in 144 runs.**

**Three things it does NOT license.** The frequency is **sim-specific** — the
desync route does not latch (the array is zeroed only inside `on_ul_grant`,
which refills it), so hardware reaches the fault only by cold start and
hardware always grants at attach. **"Clears" ≠ "improves everything"** — the
same intervention takes TwoTier's M06 failures from 14/40 to **40/40**. And
**the mechanism remains the product's** regardless.

---

## 3a. The second consolidation — grant density, four more observations

**Full statement: `docs/grant-density-mechanism-2026-09-06.md`.** Trace
`sweeps/rerun-2026-09-06/traces.json`, 4 cells × 3 arms × 10 seeds,
bit-identical with the hooks off on 120 of 120 cells.

A grant is a TB for a **UE**; which flow it carries is decided **inside the
UE** by LCP, and **the gNB cannot see that split**. An arm therefore chooses
only **how often a UE is granted**. Measured, monotone, and in the same arm
order in every cell — **PF grants least, TwoTier most**:

| | the UE's UL grants | % carrying 5QI 1 | skipped p98 |
|---|---|---|---|
| PF | 2,048–3,286 | **2.5–3.3 %** | **41–74** |
| Reservation | 6,366–13,680 | 0.6–1.0 % | 154–261 |
| TwoTier | 10,865–25,221 | **0.5–0.8 %** | **284–340** |

ρ = **+0.79** (grants vs deferral tail) over 120 runs, p = 2.8e−27.

| observation | what it said before | what it is |
|---|---|---|
| the **workload inversion** (TwoTier 3.5× worst on the mix, best on `sensor_dense`) | "Tier-1's objective favours periodic over saturating" | **refuted** — intra-UE LCP; the UE gets 1.003× the fleet median |
| **G7's inversion** (PF contains better) | why PF contained was unknown | **PF grants ~5.8× less**, so its flow rides on 5.1× more grants |
| **the attach path's M06 regression** (14/40 → 40/40) | "returns locked-out UEs to contention" | tail 286 → 340; the median p95 slightly *improves* — the cost is in the tail, which is what a failing-seed count reads |
| **G5's residual** | open at "4/10" | **empty** — 4/10 was the pre-attach figure |

**The attributional statement, which is the part that matters for a deck: a
headline that reads as a scheduler result is a UE-side LCP effect identical
across all three arms, and no scheduler change reaches it.** The numbers are
right; the attribution was not, and the attribution is what *"is two-tier
needed"* turns on. **The mechanism transfers to hardware (LCP is real 3GPP);
the magnitude does not** — it is uncalibrated.

---

## 4. Coverage — no workload can score the set

| guarantee | parametric mix | sensor_dense |
|---|---|---|
| G1 latency | ✅ *100 ms PDB — not latency-critical* | ✅ **15 ms PDB** |
| G3, G8 | ✅ | ✅ |
| G4, G5, G6, G7, G10, G12 | ✅ | ❌ no GBR flow / no `frame_id` / 1 5QI / no duty axis |

**3 of 10 on sensor_dense, 7 of 10 on the parametric mix, 3 overlap.** So the
cross-workload comparison §0.1 asserts **can only ever be made on three
guarantees**, and **two of the three already differ**: the M01 ranking
inverts (TwoTier worst → best) and G8's M09 verdict differs (Res 1/10 →
10/10).

**PDCCH binds on sensor_dense** — U-slots at **92.2 %**, **40.7 % of slots at
the per-slot cap**. The parametric mix: 4.4 %, 0 %. Configured Grants, which
the study credits for the 30/30-vs-2/30 win, are deleted from this branch —
**so the regime exists here and the mechanism does not.**

---

## 5. What remains, and why

| item | state | what it needs |
|---|---|---|
| **G2** | no verdict | Its named failure mode — the BSR/SR desync — **is shown not to occur**. A UL STOP flow was built and measures a different cost: the access chain takes **35–40 % of a 5 ms budget**, failing 1–3 of 10 seeds. **A specification decision, not a build.** |
| **G6** | "fails clause 1" | The clause **names no estimator**; we chose the median and documented it. Not verdict-determining here, but it would be on data where clause 1 passes. **Test-plan owner's call.** |
| **G11 C2** | not scoreable | **6 of the C's 9 skip-reason counters cannot exist** — no beam model, no `do_sched`, no `transm_interrupt`. Plus a scheduler edit, a windowed emission path, and a trend statistic with no C counterpart. **Stopped at the scope check.** |
| **G11 C5** | not scoreable | p98 is quantised to the 0.25 ms slot; 3–6 distinct levels over 10 seeds. Needs ≥30 seeds or a finer instrument. |
| **TB quantisation** | unbuilt, deliberately | §20.1 measured it would not close G2 — **13,214 of 13,214 grants at padding 0, unchanged**. |
| **G7 × declaration order** | **registered, not investigated** | TwoTier's sort is tied — decided by declaration order — on **14.6 %** of adjacencies in the G7 aggressor cell, against 0.3–5.7 % in every other cell traced. That is the artefact that stopped G12's ordering being promoted, most active in exactly the cell G7's inversion is measured on. **One permutation control**, not a campaign. `docs/declaration-order-in-g7-registration.md`. |
| **A third workload** | not built | Nothing here has a tight PDB *and* GBR/PDU-set structure. Scenario-design question. |

**Deferred with reasons: the C port** (a *free* LP buys 1.60×; largest file
9.2 % against a 25 % threshold) and **the Tier-1 reformulation** (the
correctness gap it would close is already closed — 98.7 % exact after
scaling).
