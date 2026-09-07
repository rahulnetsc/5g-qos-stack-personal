# Scorecard audit — twelve rows, by hand

**2026-09-07. Nothing fixed.** Three defects found; all left in place so the
audited artefact is the audited artefact.

**Bottom line: 5 SOUND, 4 SOUND-BUT-NON-DISCRIMINATING, 3 SUSPECT.** One
SUSPECT row (G3) is **wrong at the verdict level** — TwoTier's 8/10 should be
10/10 on the clause as written.

**Is this converging or unreliable?** §5, and the honest answer is *both*:
every defect found is an instance of one already-documented class, and **two
of the three found today are recurrences of defects written down in this
repo's own docs.** The process converges; the instrument is not yet reliable.

---

## 1. Per-row verdicts

| # | row | verdict | the reason |
|---|---|---|---|
| 1 | **G1** p98 ≤ 95 ms (parametric) | **SOUND** | threshold now from L95; all 3 failures on `qfi1`. Caveat in §2.1 |
| 2 | **G1** p98 ≤ 15 ms (`sensor_dense`) | **NON-DISCRIMINATING** | pass-only in the entire evidence base |
| 3 | **G3** max telemetry gap ≤ 500 ms | **SUSPECT — verdict wrong** | §2.3 |
| 4 | **G5** ≥ 99 % PDU sets complete | **SOUND** | L99 verbatim, protected fleet, both verdicts |
| 5 | **G8** Jain ≥ 0.90 (parametric) | **SOUND** (M09 is panel-status `proxy`) | L102 verbatim, both verdicts |
| 6 | **G8** Jain ≥ 0.90 (`sensor_dense`) | **SOUND** (same `proxy` caveat) | both verdicts |
| 7 | **G2** STOP p98 ≤ 100 ms | **NON-DISCRIMINATING** + threshold substitution | pass-only; p98 stands in for "100 % of events" |
| 8 | **G7 c2** excess clipped at MFBR | **SUSPECT — invented tolerance** | §2.8 |
| 9 | **G7 c1** victim ≥ 99 % complete | **NON-DISCRIMINATING** + borrowed threshold | pass-only; ε is unspecified in the clause |
| 10 | **G10** every GBR flow meets contract | **SUSPECT — wrong configuration** | §2.10 |
| 11 | **G11 C1** every 60 s window | **NON-DISCRIMINATING** | passes with ~100× margin; population wider than the clause |
| 12 | **G12 c4** never starve telemetry | **SOUND** | corrected 2026-09-06; τ gap documented, robustness measured |

## 2. The evidence, row by row

### 2.1 G1 parametric — SOUND, with a population caveat that did not bite

**Q1 population.** `G1_M01_p98_prot` is M01's **worst-flow** p98 over the
protected fleet — which contains both 5QI 1 (drive commands) and 5QI 2
(video). The clause is *"every drive command"*. **Measured: 26 of 30 rows are
scored on `qfi1`, 4 on `qfi2`** — the statistic wanders across flow classes.

**It does not change the verdict**: all three TwoTier failures are on `qfi1`
(97.00 / 98.25 / 98.50 ms, seeds 1826701614 / 1367864806 / 87989972). **But
the row is 4/30 measuring a different guarantee's flow**, and on other data it
could decide the verdict.

**Q2 both verdicts.** Yes — pass 28 ms, fail 97 ms, same artefact.
**Q3 threshold.** L95, quoted: *"p98 ≤ RAN PDB (▷ 95 ms of the 100 ms 5QI-1
budget)"*. **This is the bound that was wrong two days ago** (the metric's
100 ms PDB stood in for it) and is now correct.
**Q4 denominator.** 10 = 10 seeds × 1 cell (n_ues 8, load 1.0). Confirmed.

### 2.3 G3 — SUSPECT, and the verdict is wrong

**Q1 population. The row reads `G3_M03_all_ms` — M03 over ALL flows**,
including the saturating 5QI-9 background. **The clause is "Max TELEMETRY
inter-arrival gap ≤ 500 ms" (L97).**

**Every breach in the artefact is the background flow, not telemetry:**

| arm | seed | gap | flow |
|---|---|---|---|
| TwoTier | 1826701614 | 704.75 ms | **`ue4_qfi9`** |
| TwoTier | 579362555 | 822.25 ms | **`ue1_qfi9`** |

Across all 30 rows, **every** value above 500 ms is `qfi9`. So TwoTier's
**8/10 is scoring a background flood's own starvation as a telemetry liveness
failure** — and starving a contract-less flood is the scheduler working, not
failing. **On the clause as written the row is 10/10 on every arm.**

**This is a recurrence of a defect already documented here** —
`docs/wp9-plan.md` §24.2: *"M03's worst liveness gap is a max over every flow,
so a saturating background aggressor's own starvation was scored as fleet
damage — inverting the causal direction."* The artefact carries
`G3_M03_flow_all` precisely so this can be checked, and the predicate did not
check it.

**Q3 threshold** is correct (L97). **Q4 denominator** correct. **The defect is
purely Q1.**

### 2.8 G7 c2 — SUSPECT, invented tolerance

**Q3.** The clause (L101) says *"B's excess clipped at MFBR"* — **no
tolerance**. The predicate uses `throughput ≤ 1.02 × MFBR`. **The 2 % is mine
and appears in no document.**

**Q2** shows values on both sides (pass 0.9242, fail 1.076), so the region
near the threshold **is populated** — meaning the tolerance is not obviously
inert, and **its sensitivity has not been measured** (unlike G12's τ, which
was swept). The headline verdict (0/10 at 2.03× MFBR) is far from the
boundary and survives any tolerance in [0, 1.0]; **rows near 1.0 are not
audited.**

### 2.9 G7 c1 — NON-DISCRIMINATING, and its threshold is borrowed

**Q3.** The clause says *"Asset A's G1/G3/G5 unchanged **within ε**"* — **ε is
not specified anywhere in the test plan.** The predicate substitutes G5's
absolute 99 % bound (L99). That is a different question: *"is the victim
above 99 %"* rather than *"is the victim unchanged"*. **A row whose threshold
is imported from another guarantee's clause is downstream of that clause** —
the only cross-row dependency found (§4.3).

**Q2:** pass-only across the entire artefact.

### 2.10 G10 — SUSPECT, measured in a configuration the column does not declare

**The row is measured with `attach_seed = True` on every one of its 40
rows**, while every other row in the same column is attach **OFF**. The
"without-attach" column therefore **silently mixes two configurations**.

This also explains a result reported yesterday: G10 "did not move" between the
with- and without-attach columns because **it was attach-on in both**.

**Q1 also scoped**: the clause (L104) is *"largest asset count with G1–G8
all-pass"*; the predicate tests the **GBR contract only** (`M07_met ==
M07_total`). Declared in the row's own note, but it is a narrower question
than the clause.

**Q4 denominator: 40 = 10 seeds × 4 fleet sizes (2, 4, 8, 16). Confirmed
mechanically.**

### 2.11 G11 C1 — NON-DISCRIMINATING, population wider than the clause

`subset = "all"` is the only subset in the artefact, so the windowed M02
covers background flows too, while the clause is about the guarantees. Passes
with ~100× margin (worst window 1.8e-4 against 0.02) either way, so **no
verdict rests on it.**

### 2.12 G12 c4 — SOUND

Corrected 2026-09-06 from an unreachable pass branch to a three-way split. The
floor τ is **not in the test plan** — a stated specification gap — and the
verdict was shown **robust across τ ∈ [0.01, 8] Mbps**, which is what the
other invented threshold (§2.8) lacks.

### Rows 2, 4, 5, 6, 7 — remaining Q2/Q3/Q4 evidence

| row | Q2 on real data | Q3 threshold | Q4 denominator |
|---|---|---|---|
| G1 `sensor_dense` | **PASS-ONLY** (13.5 ms, no failure anywhere) | L95 + workload PDB | 10 = 10 × 1 |
| G5 | both (0.9967 / 0.0) | **L99 verbatim** | 10 = 10 × 1 |
| G8 parametric | both (0.9995 / 0.75) | **L102 verbatim** | 10 = 10 × 1 |
| G8 `sensor_dense` | both (0.9995 / 0.6576) | L102 | 10 = 10 × 1 |
| G2 | **PASS-ONLY** (4 ms) | L96, **p98 substituted for a maximum** | 10 = 10 × 1 |

## 3. Cross-cut: configuration state per row

| row-group | attach | stagger | damper | other |
|---|---|---|---|---|
| G1/G3/G5/G8 parametric | **OFF** | OFF | OFF | n_ues 8, load ×1.0 |
| G1/G8 `sensor_dense` | **OFF** | OFF | OFF | 30 sensors, 20 k slots |
| G2 | **OFF** | OFF | OFF | n_ues 8 |
| G7 c1/c2 | **OFF** | OFF | OFF | **offer = 2.1× MFBR** (runner default, not the clause's "≥ 2×") |
| **G10** | **ON** ← undeclared | OFF | OFF | 4 fleet sizes |
| G11 C1 | OFF | scripted | OFF | n_ues 4, 7.2 M slots |
| G12 c4 | OFF | OFF | OFF | 2 cells, 8-point ramp |

**G7's offer is a runner default (2.1×) satisfying a clause that says "≥ 2×"**
— sound, but it is the runner's number, and at ×2.5 the runner's own
precondition guard refused the cell at 1.99×.

## 4. Cross-cut: the two questions asked directly

### 4.1 Is severity the same quantity in every row? **NO.**

I reported yesterday that M02 made it uniform. **That claim is wrong.**

| population | rows |
|---|---|
| `M02_prot` (protected fleet) | G1 parametric, G5, G8 parametric, G7 c1, G10 — **5** |
| `M02_all` (**every flow, incl. the saturating background/aggressor**) | G1 `sensor_dense`, G3, G8 `sensor_dense`, G2, G7 c2 — **5** |
| `M02w`, subset `all`, per window | G11 C1 |
| `telemetry_m02`, **one flow** | G12 c4 |

**Four different populations.** It is the same *metric* but not the same
*quantity*, and the mixing is invisible in the column. G3's 0.29160 and G7
c2's 0.35806 are dominated by the aggressor's own violations — the very rows
whose Q1 is already suspect.

### 4.2 Is any verdict downstream of another row? **One.**

**G7 c1's threshold is imported from G5's clause** because its own ε is
unspecified. If L99's 99 % were wrong, G7 c1 inherits it silently. No other
row reads a statistic scored elsewhere; G10's M07 and G12's `bg_bps` are both
computed inside their own run.

### 4.3 Denominators — all confirmed mechanically

10 = 10 seeds × 1 cell for rows 1–9 and 11; **G10 = 40 = 10 × 4 fleet sizes**;
**G12 = 20 = 10 seeds × 2 cells** (`mixed_n8`, `drone_heavy_n8`). No mismatch.

## 5. Converging process, or unreliable instrument?

**Both, and the distinction matters.**

**Unreliable as an instrument, today.** Three verdict-changing corrections in
two days, and this audit found three more issues in an hour — one of which
(G3) is wrong at the verdict level. **Five of twelve rows are sound.** It
should not be described as the artefact everything rests on until §2's
findings are addressed.

**Converging as a process, on specific evidence.** Every defect found — here
and in the previous three — is an instance of **one class**: *an aggregate
that is arithmetically correct over the wrong population*. Not a new failure
mode each time. And the class is now enumerated well enough that this audit
found its instances by applying the question mechanically rather than by
noticing something odd.

**But the sharpest evidence cuts the other way: two of today's three findings
are RECURRENCES of defects already written down in this repo.** G3 reproduces
`wp9-plan.md` §24.2 exactly — the aggressor in a worst-flow liveness metric —
and the severity mixing reproduces the mixed-units defect I fixed two days
ago, one level down. **A documented defect that recurs is not evidence of
convergence; it is evidence that the documentation is not reaching the point
of use.**

**The honest characterisation: the failure mode is understood and the
detection is improving, but the defect rate per new artefact has not fallen.**
Three of the four checks now in the scorecard (`--selftest`,
`--denominators`, threshold citation) were each added after a defect of that
exact shape shipped — they are trailing indicators. **The one check that would
have caught all three of today's findings — "name the rows that entered the
sum and the rows the claim is about" — is the one that cannot be automated,
and it was not applied to these twelve rows until asked for.**

## 6. Nothing was fixed

G3, G7 c2, G10 and the severity mixing are all still live in
`scripts/guarantee_scorecard.py` and in
`docs/guarantee-success-rates-2026-09-06.md`. **The published scorecard
currently overstates TwoTier's G3 failure and mislabels G10's configuration.**
