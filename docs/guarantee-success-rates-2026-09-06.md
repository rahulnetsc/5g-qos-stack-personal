# The guarantee scorecard

**2026-09-06.** One primary number per guarantee per arm: **the fraction of
runs in which the guarantee held**, with its denominator. **One severity
number under it, uniform on every row: M02, the fraction of resolved bytes
that missed their PDB.** Everything else — p98, jitter, Jain, CoV — is
diagnostic and appears only in §4, where it explains a failure.

Regenerate: `scripts/guarantee_scorecard.py`. Verified: `--selftest`
(every predicate can fail) and `--denominators`.

**Aggregation.** Seeds and sweep cells are aggregated — environmental
variation, and a success rate is the right summary. **Clauses are not**: one
row per clause.

---

## 1. The guarantees, in their own words

| | the guarantee, as the test plan states it |
|---|---|
| **G1** | Every drive command reaches the robot in time to feel responsive |
| **G2** | A STOP always lands, on every ground robot, fast |
| **G3** | The network never makes a healthy robot look dead |
| **G4** | After a robot goes quiet, its next message still arrives promptly |
| **G5** | Operators and the AI always see fresh, complete video |
| **G6** | Background traffic can never impair the fleet |
| **G7** | One misbehaving robot cannot take down the others |
| **G8** | Robots of equal entitlement get equal service, continuously |
| **G9** | A robot joins (or re-joins after an outage) quickly, even on a busy cell |
| **G10** | The cell hosts a stated fleet size with all of the above intact |
| **G11** | The guarantees hold for a whole shift, and reproduce run after run |
| **G12** | When the cell is genuinely overloaded, degradation follows the safety order |

## 2. The table

| guarantee | clause | arm | **success** | **severity (M02)** | sev\|fail |
|---|---|---|---|---|---|
| **G1** responsive commands | cmd_vel p98 ≤ 95 ms (parametric) | PF | **10/10** | 0.00000 | — |
| | | Reservation | **10/10** | 0.12267 | — |
| | | **TwoTier** | **7/10** | 0.00014 | 0.00014 |
| **G1** | p98 ≤ 15 ms (`sensor_dense`) | PF | 10/10 | 0.00576 | — |
| | | Reservation | 10/10 | 0.08853 | — |
| | | **TwoTier** | **10/10** | 0.01433 | — |
| **G2** STOP always lands | STOP p98 ≤ 100 ms (UL) | PF | 10/10 | 0.00074 | — |
| | | Reservation | 10/10 | 0.00125 | — |
| | | **TwoTier** | **10/10** | 0.00027 | — |
| **G3** never look dead | max telemetry gap ≤ 500 ms | PF | 10/10 | 0.29160 | — |
| | | Reservation | 10/10 | 0.30173 | — |
| | | **TwoTier** | **8/10** | 0.29917 | 0.29959 |
| **G5** fresh complete video | ≥ 99 % PDU sets complete | PF | 10/10 | 0.00000 | — |
| | | Reservation | **3/10** | 0.12267 | 0.12359 |
| | | **TwoTier** | **6/10** | 0.00014 | 0.10455 |
| **G7** one robot can't take down others | c1: victim ≥ 99 % complete | PF | 10/10 | 0.17143 | — |
| | | Reservation | 10/10 | 0.17327 | — |
| | | **TwoTier** | **10/10** | 0.26304 | — |
| **G7** | c2: aggressor's excess clipped at MFBR | PF | **1/10** | 0.35806 | 0.35872 |
| | | Reservation | **0/10** | 0.37042 | 0.37042 |
| | | **TwoTier** | **0/10** | 0.36771 | 0.36771 |
| **G8** equal service continuously | per-1 s Jain ≥ 0.90 (parametric) | PF | 10/10 | 0.00000 | — |
| | | Reservation | 9/10 | 0.12267 | 0.24687 |
| | | **TwoTier** | **7/10** | 0.00014 | 0.12553 |
| **G8** | per-1 s Jain ≥ 0.90 (`sensor_dense`) | PF | 10/10 | 0.00576 | — |
| | | Reservation | **0/10** | 0.08853 | 0.08853 |
| | | **TwoTier** | **9/10** | 0.01433 | 0.03657 |
| **G10** stated fleet size | every GBR flow meets contract | PF | 30/40 | 0.00000 | 0.00555 |
| | | Reservation | 31/40 | 0.00000 | 0.00431 |
| | | **TwoTier** | **32/40** | 0.00002 | 0.00459 |
| **G11** holds for a shift | C1: every 60 s window conformant | PF | 10/10 | 0.00008 | — |
| | | Reservation | 10/10 | 0.00008 | — |
| | | **TwoTier** | **10/10** | 0.00008 | — |
| **G12** safety-ordered degradation | c4: never 5QI 1 while a lower class has throughput | PF | **0/20** | 1.00000 | 1.00000 |
| | | Reservation | **0/20** | 1.00000 | 1.00000 |
| | | **TwoTier** | **0/20** | 1.00000 | 1.00000 |

**Denominators, checked** (`--denominators`): 10 seeds × 1 cell for every row
except **G10 = 10 seeds × 4 fleet sizes = 40** and **G12 = 2 cells × 10 seeds
= 20**. Both confirmed to aggregate what they claim.

**Artefacts:** `sweeps/sev-2026-09-06/*.json` (re-run to emit M02 uniformly),
`sweeps/rerun-2026-09-06/g11_c1_soak.json`,
`sweeps/g12-rescore-2026-09-06/g12.json`.

## 3. Verifying the scorecard itself

### 3.1 Every predicate can fail — `--selftest`, and it passes

Each clause's statistic is perturbed across its threshold in both directions
and the verdict must flip. **All 12 flip.** Three clauses show only passes in
this data (G1 `sensor_dense`, G2, G7 c1) — the predicate is falsifiable, but
those rows have **no discriminating power on this evidence** and should not
be quoted as evidence of a margin.

**The self-test caught a bug in itself**: the tuple branch tested "can
produce a pass" twice instead of once each way, flagging G10 as unfalsifiable
while its data plainly contained both verdicts.

### 3.2 Every threshold traced to the test plan — and one was not

| clause | source |
|---|---|
| G1 p98 ≤ **95 ms** | L95, verbatim |
| G2 STOP ≤ 100 ms | L96 |
| G3 gap ≤ 500 ms | L97 |
| G5 ≥ 99 % complete | L99 |
| G7 c2 clipped at MFBR | L101 |
| G8 Jain ≥ 0.90 | L102 |
| G10 all-pass | L104 |
| G11 C1 every window | L105 + L122's 98 % conformance basis |
| G12 c4 | L106, verbatim |

**THE FINDING: the previous scorecard scored G1 against the 100 ms PDB — the
metric's number, not the document's.** The test plan states **95 ms of the
100 ms budget**. Correcting it moves **TwoTier from 10/10 to 7/10** on the
guarantee the whole campaign is framed around. **A threshold taken from a
metric default rather than the specification is the population defect applied
to a bound.**

**One substitution remains, labelled not equated:** G2's clause is *"100 % of
STOP events ≤ 100 ms"* — a **maximum** — and the artefact records **p98**. The
row is therefore **weaker than the clause**. It passes 10/10 either way at
p98 ≈ 2–4 ms, but the row is not the clause.

### 3.3 Denominators — checked mechanically, above.

## 4. Where TwoTier fails

**G1 (7/10, parametric).** Three seeds land between 95 and 100 ms — inside
the PDB, outside the guarantee. **Cause: service burstiness.** TwoTier serves
a UE's flow in clusters then long gaps (ratio **125** vs PF's **1.3**), and
p98 reads the tail. **Established causal, not correlational:** damping it cut
burstiness 23.0 → 5.0 and improved p98 by **−16.8 ms [−40.6, −1.6]**.

**G3 (8/10).** Two seeds exceed the 500 ms liveness gap. Same mechanism — a
long inter-service gap *is* an apparent liveness gap. **This is the clause
where burstiness matters most**, because G3 is a *maximum*, and a maximum is
exactly what a clustered service pattern damages.

**G5 (6/10).** The cold-start lock-out: a UE whose `estimated_ul_buffer_per_lcg`
reads zero enters the UL sort with `has_gbr=False`/`pdb_ms=9999` and cannot
earn the grant that would repopulate it — measured at **51.3 %** of the
joiner's slots. Reproduces `update_ul_qos_priority`
(`gNB_scheduler_ulsch.c:41-70`) exactly. **TwoTier's failures are partial
(sev|fail 0.105) against Reservation's near-total (0.124 on 7 of 10 seeds).**

**G8 parametric (7/10).** Per-second Jain is the statistic a clustered
service pattern damages most directly. **Note the inversion:** on
`sensor_dense` TwoTier is **9/10** and Reservation **0/10** — same clause,
opposite ranking, because there TwoTier is the *most regular* arm (1.4).

**G7 c2 (0/10) and G12 c4 (0/20)** — every arm fails. G7 c2 is failed **by
construction**: the MFBR clamp bounds *entitlement*, not throughput, and the
overflow is reclassified best-effort. That is a **specification question**,
not a defect.

## 5. The scorecard's own limits

**5.1 Severity is now uniform — and it exposes a disagreement.** M02 is the
same quantity on every row. That immediately shows something the success rate
hides: **Reservation passes G1 10/10 while 12.3 % of protected traffic misses
its PDB.** p98 is computed over *delivered* packets; M02's denominator is
*resolved* bytes, so dropped traffic never enters p98 but does enter M02. **A
clause can pass on the percentile while an eighth of the traffic misses its
deadline.** Both numbers are correct; neither alone is the answer.

**5.2 Six clauses remain NOT COMPUTABLE**, listed rather than estimated:

| guarantee | clause | why |
|---|---|---|
| **G4** | first packet after silence p99 ≤ 300 ms | the artefact records **p98, not p99**, and p98 ≤ p99 — substituting would be **optimistic**. Rows are per (duty, ue, qfi, bucket), not per run |
| **G6** | statistics within bound and shift ≤ +20 % | the +20 % **is** stated, but the clause needs the unperturbed baseline per statistic; the artefact stores only the perturbed arm |
| **G9** | warm ≤ 1 s / attach ≤ 15 s / post-RLF ≤ 10 s | bounds are stated (L103), but the artefact stores **per-arm medians across runs**, not per-run values — a success rate needs a re-run |
| **G9** | neighbours unaffected | a paired delta with no stated bound; treatment and instrument cannot be separated |
| **G11** | C2 drift | counters never wired; 6 of the C's 9 skip-reasons cannot exist here |
| **G11** | C3 / C4 / C5 | C3 is computed *across* runs (one result, not n); C4 is satisfied by construction; C5's p98 is quantised to the slot |

**5.3 The four guards cannot catch the class that has produced every serious
defect in this project: a predicate that is arithmetically correct over the
wrong population.**

`--selftest` proves a predicate can fail. `--denominators` proves n is what it
claims. Neither asks whether the rows entering the sum are the rows the claim
is about. Every serious defect here has been of that shape — M03's worst gap
counting the aggressor's own starvation as fleet damage; CCE utilisation
against a ceiling of 1.0 when only 0.70 was reachable; a background aggregate
that stopped counting its own flood after a relabel; and the G1 threshold
above, which was arithmetically perfect against the wrong number.

**No check in this file can catch that, and none can be written**, because it
is a modelling judgement rather than a property of the data. **The only
defence is the question asked by hand of every row: what rows entered this
sum, what rows is the claim about, and are they the same set?**
