# Step 1 — clause coverage: enumeration and registered predictions

**2026-09-07, registered before any part is scored into the scorecard.**

Every part of every guarantee's clause, from the test plan's own text
(L95-L106) **plus the GT sections**, which state parts the summary table omits.

**Three groups:** scoreable from an existing artefact · scoreable with a
re-run · not scoreable, with the reason.

**Honesty about what is a blind prediction.** The 2026-09-07 audit already
measured several of these by hand while looking for them. Those are marked
**(pre-measured)** — moving them into the scorecard is bookkeeping, not
discovery. The genuinely blind ones are marked **(blind)**. Reporting a
pre-measured value as a prediction hit would be scoring my own answer key.

---

## 1. The enumeration

### Group A — scoreable from an existing artefact, TODAY

| guarantee | clause part | source | field |
|---|---|---|---|
| **G2** | 100 % of STOPs ≤ 100 ms — **the DOWNLINK half** | `g2_ul_stop.json` | `DL_stop_p98_ms` |
| **G3** | **zero gaps ≥ T_live** | `core.json` | `G3_M03_gaps_over_tlive_prot` |
| **G3** | **p98 ≤ PDB** | `core.json` | `G1_M01_p98_prot` (numerically G1's own clause) |
| **G5** | **frame age p95 ≤ 67 ms** | `core.json` | `G5_M06_all_ms` |
| **G6** | **both halves of the conjunction** (within bound **and** shift ≤ +20 %) | `g6/stage6_g6_n40.csv` — **240 rows = 3 arms × 40 seeds × `bg ∈ {False,True}`**, full panel, both populations | `M01.prot.p98`, `M03.prot.max_gap_ms`, `M05.prot.fraction` |
| **G7 c1** | A's **G1** and **G3** halves (today only G5's is scored) | `g7.json` | `A_camera_p98_ms`, `A_telemetry_p98_ms` |
| **G7 c3** | **GT-4.3's third part**: *"B's other flows (its own telemetry!) still within SLO"* | `g7.json` | `B_telemetry_p98_ms` |
| **G8** | **zero starvation epochs ≥ 1 s** — `core` | `core.json` | `G8_M22_epochs_prot`, `G8_M22_longest_s` |
| **G8** | the same — **`sensor_dense`** | `sensor_dense.json` | `G8_M22_epochs`, `n_starved`, `n_never_granted` |
| **G11** | **C3: CoV(p98) ≤ 15 % across repeats** | `g11_c345.json` | `C3[arm].cov` — **one value per arm, not a success rate** |

### Group B — needs a re-run (the statistic is not recorded)

| guarantee | clause part | why |
|---|---|---|
| G1 | **p99.9 reported** | artefact carries p98 only. It is a **reporting** obligation, not a bound |
| G1 | **GT-1.1: zero command gaps ≥ 200 ms** | no per-flow gap statistic at a 200 ms threshold; `G3_M03_*` is 500 ms over the protected fleet |
| G2 | **100 % of STOPs, i.e. the MAXIMUM** | artefact carries p98; p98 is weaker than the clause and the scorecard already labels it so |
| G2 | **demonstrated miss-rate bound (§5.3)** | needs the per-trial distribution, ≥ 30 trials/run |
| G4 | **all three silence buckets** | axis is `duty_cycle`, not silence length; and `GAP_BUCKETS_MS` tops out at `1000→inf`, so 1 s and 60 s land in one bucket |
| G5 | **per-2 s-window goodput ≥ GFBR** | no windowed goodput recorded |
| G6 | the **DL** half (GT-4.2, marked **P0**) | no DL background flow exists in any scenario |
| G9 | **all four parts** | artefact stores per-arm medians across runs, not per-run values |
| G10 | **7 of its 8 sub-clauses** | only M07 is emitted per fleet size; needs G1/G3/G5/G8 per N |

### Group C — not scoreable, with the reason

| guarantee | clause part | why not |
|---|---|---|
| **G11 C4** | *"PASS/FAIL is consistent across repeats"* | **satisfied by construction** — every run reports 0 failing windows, so it cannot fail. CLAUDE.md's own third fault shape |
| **G11 C2** | drift | counters never wired; **6 of the C's 9 skip-reasons cannot exist here** |
| **G12** | **first-violation ordering** | **untestable inside GT-7.3's own ramp** — below ×3.3 only 5QI 2 breaches, so the order is a one-element list. A specification decision, not a run |
| **G1** | p99.9 | a *reporting* requirement; there is no bound to pass or fail |

---

## 2. Registered predictions

**The question this tests: was G8's failing half representative, or the worst
case?** G8 went 9/10 → 3/10 when its second half was checked.

| # | part | prediction | basis |
|---|---|---|---|
| P1 | **G3 zero gaps ≥ T_live** | **PASS 10/10 all arms** | (pre-measured) 0 breaches |
| P2 | **G3 p98 ≤ PDB** | **FAIL — TwoTier 7/10** | (pre-measured) it *is* G1's statistic |
| P3 | **G5 frame age p95** | **PASS 10/10 all arms**, TwoTier closest to the bound | (pre-measured) medians 25/22/45 ms vs 67 |
| P4 | **G7 c1 A_camera_p98** | **PASS 10/10** | (pre-measured) |
| P5 | **G7 c1 A_telemetry_p98** | **PASS 10/10** | (pre-measured) |
| P6 | **G7 c3 B_telemetry_p98** | **PASS 10/10** | (pre-measured) |
| P7 | **G2 DL STOP p98** | **PASS 10/10** | (pre-measured) |
| P8 | **G8 epochs, `core`** | **FAIL — Res 3/10, TT 7/10** | (pre-measured) |
| P9 | **G8 epochs, `sensor_dense`** | **FAIL — PF 10/10, Res 0/10, TT 4/10** | (pre-measured) |
| P10 | **G6 conjunction** | **FAIL — G5 half at 37/40 · 7/40 · 4/40** | (pre-measured, Part 3 C-4) |
| **P11** | **G11 C3 CoV ≤ 15 %** | **PASS on all three arms** | **(blind as a scorecard row)** — the values exist; no threshold has been applied |
| **P12** | **G8 `sensor_dense` `n_starved` / `n_never_granted`** | **FAIL — Reservation 7/10 on both** | (pre-measured) |

### The prediction that actually carries information

**Of the ten Group-A parts, I predict SEVEN PASS and THREE FAIL** (G3 p98,
G8 both cells, G6). **So G8 was NOT representative — it was close to the worst
case**, and the one comparable failure (G6) is a guarantee the scorecard
currently declares *not computable* for a reason Part 3 showed to be wrong.

**If that is right, the shape of the finding is:** the unscored halves are
mostly passing, and the scorecard's under-coverage has cost **two** verdicts
(G8's, and G6's existence) rather than a systematic overstatement everywhere.

**If it is wrong — if four or more of the seven predicted passes fail — then
under-coverage is systematic** and every published PASS is suspect.

## 3. What no outcome licenses

Scoring these does **not** make any row deployment-representative. Part 2
established that six rows need **M-6 and M-9** built first, and **both will
move whatever this step scores.** That is the correct order: a clause nobody
scores is invisible regardless of fidelity, and the halves that fail must be
known before the 100 ms rescue can be judged against them.

---

# RESULT — scored 2026-09-07, after registration

**Twelve clause parts moved from unscored to scored.** The scorecard now
carries **22 predicate rows** against the previous 12.

## Predictions: 12 of 12 hit

| # | part | predicted | measured |
|---|---|---|---|
| P1 | G3 zero gaps ≥ T_live | PASS 10/10 | **10/10 all arms** ✓ |
| P2 | G3 p98 ≤ PDB | FAIL, TT 7/10 | **PF 10 · Res 10 · TT 7** ✓ |
| P3 | G5 frame age p95 | PASS 10/10 | **10/10 all arms** ✓ |
| P4-P6 | G7 c1 camera, c1 telemetry, **c3 aggressor's own telemetry** | PASS 10/10 | **10/10 all arms, all three** ✓ |
| P7 | G2 **downlink** STOP | PASS 10/10 | **10/10 all arms** ✓ |
| P8 | G8 epochs, `core` | FAIL, Res 3/10 TT 7/10 | **PF 10 · Res 3 · TT 7** ✓ |
| P9 | G8 epochs, `sensor_dense` | FAIL, PF 10 Res 0 TT 4 | **PF 10 · Res 0 · TT 4** ✓ |
| P10 | G6 conjunction | FAIL | **G5 half: PF 37/40 · Res 10/40 · TT 6/40** ✓ |
| P11 | G11 C3 CoV ≤ 15 % *(blind)* | PASS all arms | **CoV 0.0142 · 0.0516 · 0.0145** ✓ |
| P12 | G8 `n_never_granted` | FAIL, Res 7/10 | **PF 10 · Res 7 · TT 10** ✓ |

**Ten of the twelve were pre-measured during the audit, so the hit rate is
mostly bookkeeping.** The one blind prediction (P11) hit.

## The registered question, answered

*Was G8's failing half representative, or the worst case?*

**Of the twelve parts scored, NINE PASS and THREE FAIL** — G3's part 3
(inherited from G1), G8's part 2 (both cells), and G6's conjunction.

**G8 was close to the worst case, not representative.** Under-coverage cost
**two** verdicts, not a systematic overstatement:

- **G8**, whose Jain-only row read 9/10 while a UE starved for an entire run;
- **G6**, declared *not computable* on a reason that was wrong — the paired
  baseline was in the artefact all along, and the clause **fails**:
  **G5 within-and-shift at PF 37/40 · Reservation 10/40 · TwoTier 6/40.**

**The seven passing parts are real passes, and two of them matter:** G7's
**c3** (*"the containment must also hold inside the misbehaving asset"*) is
10/10 on every arm — a previously unreported positive result — and G2's
**downlink** STOP, which is the direction GT-1.2 actually names, is 10/10.

## A correction to Part 3's C-4

Part 3 reported G6's G5 conjunction as **37/40 · 7/40 · 4/40**; this scores
**37/40 · 10/40 · 6/40**. The difference is the **undefined-shift** rows,
where the paired baseline is itself 0 (the lock-out kills video with no
background at all, so "+20 % relative" has no denominator).

**Part 3's own caveat says those rows "are counted as failures only on the
within-bound half" — and its conjunction column counted them as failures on
both.** This implementation follows the caveat. The table contradicted its own
footnote; the footnote is right.

## What is left, and it is now precisely bounded

**Group B (needs a re-run): 10 parts** — G1's p99.9 and 200 ms command gaps,
G2's max and miss-rate bound, G4's three buckets, G5's per-2 s goodput, G6's
DL half, G9's four, G10's seven sub-clauses.

**Group C (not scoreable, with reasons): 4** — G11 C4 (satisfied by
construction), G11 C2 (counters unwired), G12's ordering (untestable in its own
ramp), G1's p99.9 (a reporting requirement, not a bound).
