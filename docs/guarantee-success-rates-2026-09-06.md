# The guarantee scorecard — success rate per clause, per arm

**2026-09-06.** One primary number per guarantee per arm: **the fraction of
runs in which the guarantee held**, with its denominator. One severity number
under it. **Everything else — p98, jitter, Jain, CoV — is diagnostic** and
appears only in §3, where it explains a failure.

Computed by `scripts/guarantee_scorecard.py` from committed artefacts. **No
figure here is estimated**; where a success rate cannot be computed the row
says so.

**Aggregation.** Seeds and sweep cells **are** aggregated — environmental
variation, and a success rate is the right summary. **Clauses are not**: one
row per clause, because G11's five and G9's four ask different questions.

**Two severity columns, and the second is the one that answers the question.**
`severity` is the median across **all** runs, as specified. But with 7/10
passing, that median *is a passing run* and says nothing about the failures.
`sev|fail` is the median across the **failing** runs only — that is what
separates *"failed narrowly on 4 seeds"* from *"failed totally on 4 seeds"*.

---

## 1. The table

| G | clause | arm | **success** | severity | **sev\|fail** | severity unit |
|---|---|---|---|---|---|---|
| **G1** | p98 < PDB (100 ms, parametric) | PF | **10/10** | — | — | *M02 not recorded* |
| | | Reservation | **10/10** | — | — | |
| | | **TwoTier** | **10/10** | — | — | |
| **G1** | p98 < PDB (15 ms, `sensor_dense`) | PF | **10/10** | 0.0000 | — | fraction of flows late |
| | | Reservation | **10/10** | 0.0000 | — | |
| | | **TwoTier** | **10/10** | 0.0000 | — | |
| **G5** | ≥ 99 % PDU sets complete ≤ 150 ms | PF | **10/10** | 0.0033 | — | fraction of PDU sets incomplete |
| | | Reservation | **3/10** | 1.0000 | **1.0000** | |
| | | **TwoTier** | **6/10** | 0.0066 | **0.2838** | |
| **G7** | clause 1: victim ≥ 99 % complete | PF | **10/10** | 0.0000 | — | fraction of victim sets incomplete |
| | | Reservation | **10/10** | 0.0000 | — | |
| | | **TwoTier** | **10/10** | 0.0000 | — | |
| **G7** | clause 2: aggressor clamped at MFBR | PF | **1/10** | 0.0529 | — | excess over MFBR (× MFBR) |
| | | Reservation | **0/10** | 1.0250 | — | |
| | | **TwoTier** | **0/10** | 1.0272 | — | |
| **G8** | per-1 s Jain ≥ 0.90 (parametric) | PF | **10/10** | 0.0000 | — | Jain shortfall — **not a traffic fraction** |
| | | Reservation | **9/10** | 0.0000 | **0.0668** | |
| | | **TwoTier** | **7/10** | 0.0000 | **0.1500** | |
| **G8** | per-1 s Jain ≥ 0.90 (`sensor_dense`) | PF | **10/10** | 0.0000 | — | |
| | | **Reservation** | **0/10** | 0.1795 | 0.1795 | |
| | | TwoTier | **9/10** | 0.0000 | — | |
| **G10** | every GBR flow meets contract | PF | **30/40** | 0.0375 | — | worst-flow GFBR shortfall |
| | | Reservation | **31/40** | 0.0375 | — | |
| | | **TwoTier** | **32/40** | 0.0381 | — | |
| **G11** | C1: every 60 s window within PDB conformance | PF | **10/10** | 0.00008 | — | **fraction of traffic PDB-violated** |
| | | Reservation | **10/10** | 0.00008 | — | |
| | | **TwoTier** | **10/10** | 0.00008 | — | |
| **G12** | clause 4: telemetry never starved while bg moves bytes | PF | **0/20** | 1.0000 | 1.0000 | telemetry M02, worst ramp point |
| | | Reservation | **0/20** | 1.0000 | 1.0000 | |
| | | **TwoTier** | **0/20** | 1.0000 | 1.0000 | |

**Denominators.** G1/G5/G7/G8/G11 = 10 paired seeds. G10 = 4 fleet sizes × 10
seeds = 40. G12 = 2 cells × 10 seeds = 20.

**Artefacts.** `sweeps/rerun-2026-09-06/{core,sensor_dense,g7,g10_attach,
g11_c1_soak}.json`; `sweeps/g12-rescore-2026-09-06/g12.json`. All reproduce
byte-equal in the 2026-09-06 re-run except G12, which was re-scored after its
collision fix.

## 2. NOT COMPUTABLE from existing artefacts — flagged, not estimated

| G | clause | why |
|---|---|---|
| **G2** | any | **No pass criterion exists.** Its named failure mode is shown not to occur, and nothing was written to replace it |
| **G3** | M20 liveness | M20 is a **delta between arms**, not a per-run pass/fail; the test plan states no per-run bound |
| **G4** | post-silence | scored as a **between-arm separation** at duty 0.1; the artefact's rows are per (duty, ue, qfi, bucket), **not per run** |
| **G6** | clause 1 | the clause **names no estimator**. A success rate would be an artefact of our choosing the median |
| **G9** | clauses 1–3 | scored as **counts of scripted events completed**, not as per-run pass/fail against a bound |
| **G9** | clause 4 | a paired **delta** in neighbour p98; no bound, and treatment and instrument cannot be separated |
| **G11** | C2 | counters never wired; **6 of the C's 9 skip-reasons cannot exist here** |
| **G11** | C3 | CoV is computed **across** runs — 1 result, not n, so it has no per-run rate |
| **G11** | C4 | **satisfied by construction** — every run reports 0 failing windows |
| **G11** | C5 | p98 is quantised to the 0.25 ms slot; 3–6 distinct levels over 10 seeds |

**And one gap that affects the whole table: M02 is recorded by no runner
except the G11 soak and G12.** So the severity column falls back to each
guarantee's own equivalent (PDU-set completeness, GFBR shortfall, Jain
shortfall), and **two of those are not traffic fractions at all** — they are
labelled inline rather than silently mixed in. **Making severity uniform
means emitting M02 from every runner and re-running: ~20 min for the light
campaigns, plus 72 min if the C1 soak is included.** That is the only
estimate in this document and it is an estimate of *cost*, not of a result.

## 3. Where TwoTier fails — the explanations

Diagnostics appear here and nowhere else.

### G5 — 6/10, and the failures are partial, not total

**`sev|fail` = 0.2838**: on a failing seed, ~28 % of PDU sets are incomplete —
against **Reservation's 1.0000, which is total failure on 7 of 10 seeds.**
TwoTier is the better arm here and the success rate alone hides that.

**Cause, traced:** the cold-start lock-out. A UE whose
`estimated_ul_buffer_per_lcg` reads zero enters the UL sort with
`has_gbr=False`/`pdb_ms=9999` and cannot earn the grant that would repopulate
it. **Measured: the joiner carries positive `bytes_reported` with an all-zero
array on 51.3 % of its slots.** Supplying a BSR at attach takes TwoTier to
**0/10 failing** and Reservation to 1/10 marginal
(`docs/attach-path-result-2026-09-05.md`).

**Product, not port:** `update_ul_qos_priority`
(`gNB_scheduler_ulsch.c:41-70`) seeds `best_pending_pdb_ms = 9999` and
`continue`s past every zero per-LCG entry, exactly as ported.

### G8 — 7/10 on parametric, and it is the worst arm there

**`sev|fail` = 0.1500** — a failing seed sits at Jain ≈ 0.75, against
Reservation's 0.0668 (≈ 0.83). **This is a fairness failure, not a latency
one, and the severity is a Jain shortfall rather than a traffic fraction.**

**Cause, traced:** service burstiness. TwoTier serves a UE's flow in clusters
then long gaps — burstiness ratio **125** against PF's **1.3**
(`sweeps/phase2/u1_trace.json`) — and per-second Jain is precisely the
statistic a clustered service pattern damages. **Now established as causal,
not correlational:** damping it (`anti_hysteresis`) cut burstiness 23.0 → 5.0
and improved the protected flow's p98 by **−16.8 ms [−40.6, −1.6]**
(`docs/burstiness-intervention-result-2026-09-06.md`).

**Note the inversion:** on `sensor_dense` TwoTier is **9/10** and Reservation
is **0/10** — the same clause, opposite ranking, because `sensor_dense` gives
TwoTier the most regular service of the three arms (ratio 1.4).

### G7 clause 2 — 0/10, by construction

**Severity 1.0272 = the aggressor delivers 2.03× its MFBR.** Both QoS arms
fail; **PF, which has no MFBR concept at all, passes 1/10.**

**Cause, read from the C, not inferred:** the MFBR clamp bounds `_target` —
the GBR *entitlement* — and the overflow is reclassified best-effort and
stays deliverable. **There is no rate limiter.** So an arm that implements
MFBR faithfully cannot pass a clause written as "throughput is clamped".
**This is a specification question for the design owner, not a defect.**

### G12 clause 4 — 0/20 on every arm

Not a TwoTier-specific failure. Telemetry M02 reaches **1.000** — every
resolved telemetry byte PDB-violated — while background still moves bytes.
**TwoTier reaches it one ramp point earlier than the others (×1.6 vs ×2.3)**,
which is the only arm difference, and it is **untested under flow-list
permutation**.

### G10 — 32/40, the best of the three

TwoTier is not the failing arm. The 8 failures are concentrated at the largest
fleet sizes and the three arms are within one run of each other (30/31/32).

## 4. What the headline is

**On the clauses that are computable, TwoTier is the best arm on G10 (32/40)
and G8/`sensor_dense` (9/10), the middle arm on G5 (6/10), the worst arm on
G8/parametric (7/10), and tied at the floor on G7 clause 2 and G12 clause 4
where every arm fails.**

**No arm fails G1 on either workload** — 10/10 everywhere. The p98 differences
that have dominated three weeks of analysis are **entirely within the
guarantee's own bound**, and none of them changes a verdict.
