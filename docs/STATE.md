# State of the guarantee evaluation — start here

**2026-09-06.** A cold-start document. Everything below is current; where a
number is superseded it says so and says by what.

**Count: eleven guarantees carry a verdict. One of those is partial (G11 —
two clauses of five). G6's is "fails clause 1" rather than a clean result.
G2 alone has none.** Use that wording rather than "11 of 12".

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
| **G5** | **RE-SCORED — the published rate is an artefact.** Was Res 30/40, TT 34/40; under an attach path **Res 1/10 marginal, TT 0/10** | `phase2/core_scaled.json` + `g5_rank_attach_scaled.json` | 10 | 40k | parametric | **current** |
| **G6** | **FAILS clause 1, every arm.** Not a clean result — see §5 | `postscaling/g6seeded/` | 40 | 20k | parametric + aggressor | stale |
| **G7** | **FAILS clause 2.** Both QoS arms deliver **2.0–2.1× MFBR**; PF (no MFBR concept) contains better at 1.05× | `postscaling/g7.json` | 10 | 20k | fleet + aggressor | stale |
| **G8** | **FAILS.** M09 protected: Res 1/10, **TT 3/10** below 0.90 | `phase2/core_scaled.json` | 10 | 40k | parametric | **current** |
| **G9** | **SCOREABLE (first time).** Counts complete 10/10, 5/5, 1/1 with the re-join seed. **Clause 4 FAILS on TwoTier** | `postscaling/g9_seeded.json` | 10 | 20k | G9 scenarios | stale |
| **G10** | **PF 8 / Res 4 / TT 4 — UPPER BOUND, not capacity.** Cause established, §3 | `phase2/g5_consol_scaled.json` | 10 | 20k | parametric | **current** |
| **G11** | **TWO CLAUSES OF FIVE.** C1 PASS (900 windows, 0 failing); C3 PASS. C4 not independent; C5 not scoreable; C2 not scoreable | `postscaling/g11_c1_soak.json` | 10 | **7.2M** | G11 scripted | stale |
| **G12** | **NO ARTEFACT — the published one is unsound.** The 2026-09-06 re-run cannot reproduce it: defect #28's guard (added later) refuses the run, and the published artefact silently dropped a 5QI-9 flow that is in clause 4's own denominator. Ordering was already **not established**; the clause-4 *figure* is now withdrawn, the qualitative finding stands. See defects log #30. | — | — | 20k | fleet ramp | **BLOCKED** |

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
| **A third workload** | not built | Nothing here has a tight PDB *and* GBR/PDU-set structure. Scenario-design question. |

**Deferred with reasons: the C port** (a *free* LP buys 1.60×; largest file
9.2 % against a 25 % threshold) and **the Tier-1 reformulation** (the
correctness gap it would close is already closed — 98.7 % exact after
scaling).
