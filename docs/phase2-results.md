# Phase 2 — complete results  ·  **SUPERSEDED**

> **⚠ CCE NORMALISATION, corrected 2026-09-06.** Any CCE-utilisation figure on this page is against a denominator that includes the D-slot budget. For an **uplink-only** workload the achievable ceiling is **0.7000**, not 1.0 (`DSUUU`; D=48, S=16, U=32; 112 usable of 160). So sensor_dense's 0.636 is **90.8 % of achievable and the control channel DOES bind**, while the parametric mix's 0.073–0.094 is 10–13 %. See `docs/cce-binding-2026-09-06.md`.


> **⛔ SUPERSEDED 2026-09-04 by `docs/verification-2026-09-04.md`.** Every
> guarantee has been re-measured on current code. **The "Phase 2" label is
> retired** — it meant *fast numbers to check the plumbing*, and that is what
> these were: the G1/G3/G5/G8 row below comes from a **`--seeds 1`** run
> (`sweeps/phase2/core_fast.json`).
>
> **Two verdicts below are known-wrong at a defensible seed count.** G8's
> "both conjuncts pass, 0 starvation epochs on all arms" is n=1; at n=10 both
> conjuncts fail on both QoS-aware arms. And G12's "neither promotion clause
> fires" was a consequence of the campaign not completing — with the
> permutation control run, **clause 1 fires**.
>
> **What is still current here:** the specification findings (including 1a,
> registered in this document), the scope limits at the top, and the two
> Tier-1 solver sections. Use the verification document for every number.

**2026-09-04.** Every guarantee, with a verdict or a named cause. This is the
artefact Phase 3 diffs against, so it is written to be readable without the
conversation that produced it.

---

## READ THIS BEFORE ANY NUMBER BELOW

**1. All results are on the PARAMETRIC MIX, whose tightest PDB is 100 ms.**

| | classes present | tightest PDB |
|---|---|---|
| parametric mix (what Phase 2 ran) | 5QI 1 (100 ms), 2 (150 ms), 9 (300 ms), 82 (100 ms) | **100 ms** |
| fleet builder (not run here) | the same **plus 5QI 83 (10 ms) and 5QI 85 (5 ms)** | 5 ms |

**The workload contains no latency-critical flow.** Every latency-critical
conclusion is **structurally unavailable from this pass, however clean it
reads** — including `docs/wp9-plan.md` §15.5's tight-PDB-density hypothesis,
which cannot be tested on a workload with no tight-PDB flows. It bites
hardest on **G1**, whose 100 ms bound is evaluated against a mix whose
tightest configured budget *equals that bound*, and on **G3**, whose liveness
numbers come from flows whose slowest cadence is 300 ms.

**2. These numbers supersede every pre-fix figure.** Six commits changed what
prior results mean: `priority_level` derivation, the required population
argument, MFBR configuration, M03's slow-vs-degraded predicate, handshake
arrival accounting, and the 5QI table upgrade. **Any number from before
`8f9ad34` is measured on different code.**

**3. Two guarantees and four G11 clauses are NOT MEASURED, each with a named
cause** — listed as such below, never omitted. A guarantee absent from a
results table is indistinguishable from one that failed to produce a number.

---

## The list

> **TIER-1 SCALING, 2026-09-05 (`0ea02b0`).** `scheduler/tier1.py` now
> scales the LP objective (`_OBJ_SCALE = 1e4`); the shipped solve was
> returning a numerically wrong vertex on ~89 % of solves and a strictly
> suboptimal point on 6.7 %. The regression baseline was deliberately
> re-captured (838 values, all TwoTier). **G1, G3, G5, G8 and G10 have been
> re-scored at n=10 and every verdict HELD** — see
> `docs/tier1-scaling-followup-2026-09-05.md`. **G4, G6, G11 C1 and G12 have
> NOT been re-run and their verdicts below are pre-scaling.** PF and
> Reservation are unaffected in principle and were confirmed bit-identical.


> **COVERAGE, 2026-09-05: every row below is on the PARAMETRIC MIX, which is
> PRB-bound at 93 % with a tightest PDB of 100 ms — so no row below is a
> latency-critical result.** `sensor_dense` (30 UL sensors, **15 ms PDB**,
> CCE 44–65 %) has now been scored for G1/G3/G8
> (`docs/sensor-dense-result-2026-09-05.md`), and **the ranking inverts**:
> TwoTier's M01 p98 is the **worst** of three arms here (87.78 ms) and the
> **best** there (11.00 ms). **G8's verdict also differs by workload** —
> Reservation fails M09 on 1/10 seeds here and 10/10 there.


> **COUNT, as of 2026-09-06: eleven guarantees carry a verdict, one of those
> is partial (G11 — 2 clauses of 5), and G6's is "fails clause 1" rather than
> a clean result. G2 alone has none.** Use that wording rather than
> "11 of 12".

| G | status | result or cause |
|---|---|---|
| **G1** | **measured** | M01 p98 **protected fleet**: PF 24.83 / Reservation 24.42 / TwoTier **94.51 ms** against a 100 ms bound — all pass, 3.8× arm separation. **The all-flow reading is saturated and must not be quoted**: ~300 ms on every arm, won by the 5QI-9 filler, pinned at that filler's own PDB, three arms agreeing to 0.25 ms. |
| **G2** | **NOT MEASURED — out of scope** | Two independent blockers. TB-size quantisation is planned and unbuilt. **And separately** the E-STOP flow is **DL** (`sim/fleet.py:179`) while G2's named failure mode — the BSR/SR desync — is an **uplink** mechanism, so the flow cannot reach the failure even once the mechanism exists. Building only the first would not produce a scoreable G2. |
| **G3** | **measured** | M20 protected-fleet liveness gap, n=40: PF **+0.44 % PASS**, Reservation **+1.84 % PASS**, TwoTier **+21.34 %** [−2.81, +50.02] **INCONCLUSIVE**. Unblocked by the M03 slow-vs-degraded fix (`2a4b382`), which previously silenced real breaches. |
| **G4** | **measured** | Post-silence p98 on the T1 telemetry instrument, 10 paired seeds per cell, all nine cells at **n=10** — no seeds silently dropped. **duty 0.1:** PF 106.56 / Reservation 117.50 / TwoTier 112.42 ms; Reservation−PF **+10.94** [+5.93, +16.20] and TwoTier−PF **+5.86** [+4.50, +7.25], both intervals excluding zero. **duty 0.5 and 1.0:** every arm difference's interval **contains zero** (TwoTier−PF −6.48 [−22.14, +7.91] and −6.20 [−25.19, +10.72]) — no arm separation. So the only separation G4 shows is at duty 0.1, where PF is fastest to resume. |
| **G5** | **RE-SCORED 2026-09-05 — its own registered falsifier fired; see `docs/attach-path-result-2026-09-05.md`** | **The published rate is an ARTEFACT of this simulator's missing attach procedure and must not be quoted as a property of either scheduler.** Published: PF 3/40, Reservation 30/40, TwoTier 34/40 failing M05 under 0.99. **Under an attach path (Model C: staggered arrival + the one BSR a UE sends during RRC setup), at G5's own configuration, 10 paired seeds: PF 0/10, Reservation 1/10 (marginal, M05 0.989967), TwoTier 0/10.** The catastrophic 0-of-299-frames failures are gone and the victim is no longer the last position. Starvation cleared at every fleet size, arm and seed (108-run experiment; the `stagger_only` control shows staggering ALONE makes it strictly WORSE, so the seed is the lever). **WHAT SURVIVES.** (a) The mechanism is unchanged and is the PRODUCT's: `ia_p5g_scheduler.c`'s Tier-1.5 floor is gated on `has_pending_gbr`, set only inside the loop that skips every zero per-LCG entry — the exact condition its own comment names as defining the fault it rescues — and Reservation has no floor at all. Read from the C's source, so no result here touches it. (b) The fault is reached MORE readily under realistic arrival than under cold start. (c) Model C models a *successful attach* and does not model a Short/Truncated-BSR desync emptying a served UE's array, which is the route hardware would actually take — **untested**. **Scope: UL only on this workload** (no DL flow on the parametric mix carries PDU-set structure). **Consequence: every blackout rate and admissible-fleet figure measured without an attach path is an UPPER BOUND**, G10's PF 8 / Reservation 4 / TwoTier 4 included.  **AND M05 IS A MIN, NOT A COUNT — so it does NOT reward concentration.** `adoption-decision.md` §2 records the opposite shape on `factory_robots`: at 0.67× load TwoTier holds **every** robot at ≥82 % of contract while PF leaves its worst at **26 %**, yet PF scores **6/10** to TwoTier's **1/10**, because the metric counts flows crossing 95 % and six of PF's do. A **count above a bar rewards concentrating the shortfall**; TwoTier is built to spread it (§8.5's max-min-vs-contract-count opposition, with a magnitude). **M05 is the other shape**: `sim/scorecard.py::_m05_pdu_set_completeness` takes `min(candidates)` — the WORST flow's fraction — against a 0.99 bar. A concentrating scheduler fails it outright, since its starved flow reads 0. **But a spreading one fails too unless the level it spreads to clears 0.99**, so M05 rewards neither strategy: it demands universality, and is the strictest of the three shapes. That is consistent with what G5 measures — under the attach path TwoTier is 0/10 because every flow clears the bar, not because the metric favours spreading. |
| **G6** | **SCORED 2026-09-05 on the MEDIAN — FAILS on clause 1, every arm; see `docs/g6-result-2026-09-05.md`** | **The call, documented:** the clause names no estimator over runs, so we chose the **median** because this workload produces outlier seeds — TwoTier's clause-2 mean on M02 is **+1087 %** against a median of **+0.28 %**, and on M06 **+42.6 %** against **−0.41 %**. Mean and per-run are reported alongside as sensitivity. **On the median, clause 2 PASSES on every metric and every arm.** **BUT THE ESTIMATOR CHOICE DOES NOT DECIDE G6:** it is a conjunction, and **clause 1 ("stays within its bound") needs no estimator** — it is a per-run bound check and it fails. M05 ≥0.99: PF 3/40, Reservation 30/40, TwoTier 34/40; TwoTier also fails M01 8/40, M03 2/40, M06 14/40. **Decomposition matters more than the verdict: PF and Reservation fail clause 1 on M05 ALONE, and M05's failures are the known attach-path artefact** — so their G6 failure is inherited and should be re-scored under the attach path. **TwoTier fails on four statistics, so its failure survives.** The specification defect stands and goes to the test-plan owner as a **note, not a blocker** — it is not verdict-determining on this data but would be on data where clause 1 passes. **Control unverified:** stage-1's reproduction check could not run (CSV absent), reported as unverified rather than as a pass.  **RE-SCORED UNDER THE ATTACH PATH, and my prediction MISSED:** clause 1 still fails on every arm. Reservation's M05 collapses **30/40 → 3/40** and PF's 3/40 → 2/40 — the artefact was most of it — but a bound check does not care how small a residual is, so the verdict is unchanged and the specification defect stays moot. **UNEXPECTED: the attach path makes TwoTier WORSE on latency** — M06 within-bound failures go **14/40 → 40/40**, M03 2/40 → 15/40, M01 8/40 → 11/40, while M05 improves 34/40 → 17/40. Relieving the lock-out does not create capacity; it returns the locked-out UEs to contention, paid for in delay. |
| **G7** | **MEASURED 2026-09-05 — FAILS on clause 2; see `docs/g7-result-2026-09-05.md`** | GT-4.3, asset B's camera offered at **2.01–2.10× MFBR** (achieved rate asserted from the artefact, not the knob), n=8, 10 paired seeds. **Clause 1 (A within SLO): PASS 0/10 breaches on all arms.** **Clause 2 (B's camera delivered ≤ MFBR + tol): FAIL 0/10 on Reservation and TwoTier at every tolerance including 25 % — both deliver ≈16.2 Mbps against an 8 Mbps MFBR, 2.0–2.1×.** **Clause 3 (B's own telemetry): PASS 0/10 on all arms.** **THE INVERSION IS THE HEADLINE: PF, which has no MFBR concept at all, contains the aggressor better (1.05×) than the two arms that implement the clamp.** Mechanism read from the C, not inferred: the clamp bounds `_target`, the GBR obligation (`ia_p5g_scheduler.c:2663-2665` + the UL/DL twins), and the overflow goes to the best-effort accumulator where it stays deliverable — so MFBR bounds **entitlement, not throughput**. Excess **grows** rather than vanishing as load rises (2.02× → 2.14× over a 2.5× load range), though UL utilisation could not be driven above ~0.933, so "at saturation" was not reached and the second read is only partly conclusive. **A product finding of the same class as the Tier-1.5 dead gate: if MFBR is meant to be a delivery ceiling, no code path implements it.** |
| **G8** | **⛔ KNOWN-WRONG — see `docs/verification-2026-09-04.md` §1.** This row's *"0 on all arms"* is contradicted by `sweeps/phase2/core_mfbr.json`, the n=3 file it was written from: Reservation starves `ue8_qfi9` for **10.0 s** on 1 of 3 seeds. At n=10 **both conjuncts fail on both QoS-aware arms**. Not a code change — isolated at the published configuration, where the published numbers reproduce. | **Both** conjuncts. M09 per-1s Jain protected: PF 0.9995 / Reservation 0.9998 / TwoTier 0.9654 — all pass ≥ 0.90. **M22 starvation epochs** (added this pass, G8's second conjunct previously had no instrument): 0 on all arms at the core cell. |
| **G9** | **SCOREABLE FOR THE FIRST TIME — clauses 1–3 pass their count guard, clause 4 FAILS on TwoTier; see `docs/g9-result-2026-09-05.md`** | **On post-A1 scenarios alone the guard still refused** (4 of 10 warm, was 2 of 10) — A1's clip is inert at G9's horizon (last event slot 16,400 of 20,000, derived) and the change is attributable to the Tier-1 scaling, measured: 2 events/135 joiner UL grants at `_OBJ_SCALE=1.0` vs **8/458** at 1e4. **The cause is the cold-start lock-out** — the joiner carries positive `bytes_reported` with an all-zero per-LCG array on **51.3 %** of its slots. **With the re-join BSR seed (a MECHANISM change, justified by the sim having no RA/SRB path that hardware always grants on): 10/10 warm, 5/5 cold, 1/1 rlf on every arm**, and the all-zero fraction falls to **0.3 %**. **M18 is the one usable recovery statistic**: warm p95 PF 16.5 / Reservation 19.1 / **TwoTier 168.4 ms**. **M19 is 0.0 in all nine cells and is NOT a result** — a p95 of exactly 0.0 was registered in advance as the failure signature; warm-path M21 carries the same caveat. **TwoTier registers its 1 RLF event and completes none** (M18 `None`) — §34.5a's firing-vs-finishing warning, exactly. **Clause 4 (neighbours unaffected) FAILS on TwoTier**: Δp98 **+3.08 ms [+2.22, +4.05]** warm and **+2.35 [+0.37, +4.57]** rlf, both excluding zero — and the sign is the surprise, since the control keeps the joiner always-transmitting so neighbours should be *better* in the treatment, as PF shows (−0.62 to −1.77). **ΔM02 is 0.000 [0.000, 0.000] in all nine cells — saturated, cannot move, and is not evidence**; clause 4 rests on Δp98 alone. **THE SIGN IS UNEXPLAINED AND IS LOGGED AS SUCH.** The control keeps the joiner UE and removes only its join schedule, so in the control the joiner transmits *continuously*; neighbours should therefore be **better** in the treatment, where it is intermittently absent — which is what PF and Reservation show. TwoTier's neighbours being **worse** is backwards from the control's own logic. Candidates, none tested: (a) each re-join perturbs Tier-1's demand vector, forcing re-solves whose SCA loop is capped rather than converged; (b) `reset_ue(scope="mac"/"full")` clears the joiner's fairness ledger, so a freshly-reset UE looks under-served and outranks neighbours — an effect the control never triggers; (c) `HarqProcessPool.due_this_slot()`'s shared insertion order, a documented cross-UE mechanism; **(d) the re-join seed itself**, which hands the joiner a full BSR estimate at each re-entry — **and clause 4 was necessarily measured WITH the seed on, since without it the guard refuses and no neighbour delta is produced, so the treatment and the instrument cannot currently be separated.** |
| **G10** | **measured — and the boundary's CAUSE IS NOW ESTABLISHED, and DIFFERS BY ARM** | **⚠ PF 8 / Reservation 4 / TwoTier 4 IS AN UPPER BOUND, not a capacity figure — do not present it as how many robots a cell hosts.** **The PDCCH explanation is WITHDRAWN**: on this workload CCE utilisation is 7.3–9.4 % against UL PRB 93 %, so the agreement with `32 CCE ÷ AL 4 = 8` was coincidental. (PDCCH *does* bind on `sensor_dense`, 30 periodic UL sensors, where TwoTier meets 30/30 against PF's 2/30 via Configured Grants — the bound is real, it just does not apply here.) **THE CAUSE, established by a controlled test** (`g10_seeded.json`: the attach seed at slot 0, **no stagger**, so the seed is the only difference): **PF's boundary is CAPACITY** — 0 starvation at every N, M07 1.000 at N=8 and 0.875 at N=16, and the seed changes nothing (M08 0.964 → 0.964), which is the control holding. **Reservation's and TwoTier's boundary is the COLD-START LOCK-OUT** — Reservation at N=8 goes starved 7/10 → **0/10**, M08 0.000 → **0.964**, M07 0.875 → **1.000**, i.e. identical to PF; TwoTier at N=16 goes 6/10 → 0/10, M08 0.000 → 0.942. **With the lock-out removed all three arms are the same: all pass at N=8 and all fail at N=16 (M07 0.844–0.875).** So the published 8/4/4 SPREAD IS ENTIRELY THE LOCK-OUT, and the common boundary is 8, set by capacity. **Earlier readings corrected:** the staggered arm's residual M08 of 0.89/0.77 that led me to call the cause open was the stagger's own pre-attach-time artefact (defects-log #27), not a residual capacity effect. |
| **G11** | **TWO CLAUSES OF FIVE carry a result — not four; see `docs/g11-c345-result-2026-09-05.md`** | **C1 PASS** (re-run post-scaling: 30/30 runs at 7,200,000 slots, 1.000 on all three arms, 900 windows, 0 failing; PF and Reservation window counts bit-identical). **C3 PASS** on all three arms — CoV of worst-window p98 across 10 fresh seeds: PF 0.0142, Reservation 0.0516, TwoTier 0.0145, all 3–10× inside the 0.15 bound. **C4 passes but IS NOT INDEPENDENT EVIDENCE: satisfied by construction.** Every run reports 0 failing windows, so the verdict vector is constant and C4 could not have come out otherwise — it reads C1's vector, so C1 and C4 are one observation counted twice. **C5 NOT SCOREABLE at n=10**: p98 is quantised to the 0.25 ms slot and the per-seed vectors hold only 3–6 distinct levels, so a separation-in-SDs statistic measures the quantisation; Reservation clears that guard but its signal is a 3-point right tail whose extreme seed is the extreme seed on **every** arm (PF–TwoTier rank correlation 0.733), pointing at the traffic realisation. The registered candidate — the index lock-out — was checked first and is **refuted**: it is not armed at the soak's n_ues=4 (0 never-granted in 60 runs at N≤4). **C2 remains unscoreable** — its drift detector was built and its inputs never collected. |
| **G12** | **one cell of several — `mixed_n8` complete, rest not reached** | First-violation order by 5QI, 10 seeds/arm. **PF `[4,2]` 10/10 uniform; Reservation `[4,2]` 6/10; TwoTier `[4,2]` 5/10, `[2,4]` 4/10, and one seed a degenerate one-element `[2]`.** The run timed out inside `drone_heavy_n8`; **no JSON was written**, so the evidence is the preserved stdout (`sweeps/phase2/g12_mfbr_partial.log`). **The control moved more than the treatment** — see below. |

### G11 in full — the absence is the headline

**C1 passes 1.000 on all three arms. That is not G11 passing.**

| clause | status | cause |
|---|---|---|
| **C1** | **measured** — 1.000 pass rate, 3/3 seeds, 0 failing windows, all arms | 6 windows at the **400k-slot smoke horizon**, not the 7.2 M-slot soak GT-7.1 specifies |
| **C2** | **NOT SCORED** | never wired — commit 7 built the drift detector, commit 8 never collected its inputs (defects-log #16) |
| **C3** | not scoreable | CoV needs ≥ 5 seeds per GT-7.4; run at n=3 |
| **C4** | **not scoreable, self-declared** | the scorer reports `scoreable: false` on all arms — *"every window has the same verdict on every seed, so consistency is satisfied by construction"* |
| **C5** | not scoreable | bimodality undetectable at 3 points |

C1's pass is still a real result: before the fixes it was a **constant FAIL in
every window on every arm** at 8,050 ms — the scripted teleop off-period
scored as a liveness breach. The scripted-silence subtraction removed that.

---

## Open threads

### G4's separation exists only at duty 0.1 — and that is the cell M03's cadence caveat governs

At duty 0.1 the telemetry source's configured period is **1,000 ms**, above
G3's 500 ms bound, which is exactly the condition `Scorecard._m03`'s
CADENCE-NOT-LIVENESS caveat fires on. G4's own statistic is post-silence
latency rather than a liveness gap, so the caveat does not apply to it —
but the two describe the same cell, and a reader moving between them should
know that **the one cell where G4 separates the arms is the one where G3's
liveness reading is not scoreable against its bound.**

Recorded as an adjacency, not a defect. Nothing here is wrong; the point is
that a G4 claim at duty 0.1 and a G3 claim at duty 0.1 rest on different
footings.

### The camera UL loss at N=8 — the only unexplained thing bounding G10

Three of TwoTier's four failing seeds at N=8 have **zero dead flows** and
still miss contract: worst GBR **0.8875 / 0.5458 / 0.4498**, always
`*_qfi2`, the camera, with M07 missing 3–4 of 8 contracts.

**Ruled out by measurement:** starvation (zero dead flows), provisioning (the
0.9697 ceiling sits *above* the 0.95 line and passes at N=2 and N=4 —
`prediction-journal.md` P17), channel variance (margins of 0.11–0.55 are far
too large and land on the same class every time).

**Three candidates, with the discriminator named in advance:**

| candidate | signature in a per-slot trace |
|---|---|
| PRB lost to **other flows on the same UE** | UE granted; camera's share of each TB small while siblings take the rest |
| PRB lost to **other UEs** | the UE itself granted rarely; its share fine when it is |
| capacity lost to **retransmissions** | grants issued, bytes not delivered; `bytes_harq_lost` non-zero |

> **TRACED 2026-09-05, and read against this map without amending it**
> (`sweeps/camera-trace-2026-09-05/`). The first decision-site hook —
> `sim/trace.py`'s grant stream — on all three failing seeds plus two
> passing controls.
>
> | seed | GFBR | c1: camera's share of its UE's TBs | c2: its UE's grants vs others' mean | c3: retx PRB / failed / `bytes_harq_lost` |
> |---|---|---|---|---|
> | **161576974** | 0.4389 | 0.517 | **4,370 vs 7,310** | 0.099 / 0.099 / **0** |
> | **579362555** | 0.5260 | 0.908 | **4,586 vs 7,516** | 0.101 / 0.099 / **0** |
> | **1097657231** | 0.8601 | 0.595 | 9,252 vs 9,366 | 0.101 / 0.100 / **0** |
> | *1826701614* (pass) | 0.9559 | 0.550 | 10,501 vs 10,259 | 0.099 / 0.102 / 288 |
> | *1367864806* (pass) | 0.9596 | 0.691 | 10,575 vs 9,995 | 0.098 / 0.100 / 183 |
>
> **CANDIDATE 3 IS REFUTED, and cleanly.** Retransmission PRB fraction is
> **0.098–0.101 on failing and passing seeds alike**, the failed-first-grant
> fraction likewise 0.099–0.102 — no separation at all. And
> `bytes_harq_lost` is **0 on every failing seed and non-zero on both
> controls**, which is the *opposite* of the registered signature.
>
> **CANDIDATE 1 IS NOT SUPPORTED.** The camera's share of its own UE's TBs
> does not separate the groups: failing seeds read 0.517 / **0.908** / 0.595
> against controls at 0.550 / 0.691. The largest share in the table belongs
> to a failing seed. Sibling contention is not what distinguishes them.
>
> **CANDIDATE 2 FIRES — ON TWO OF THE THREE.** The two worst seeds grant the
> camera's UE **40 % and 39 % less often** than the average of the other
> UEs, while both controls grant it *more* often than average. That is the
> registered signature — *"the UE itself granted rarely"* — and it separates
> exactly where the damage is worst.
>
> **AND THE THIRD FAILING SEED IS EXPLAINED BY NONE OF THE THREE.** Seed
> 1097657231 (GFBR 0.8601) grants its camera UE 9,252 times against a
> 9,366 mean — a 1.2 % shortfall, indistinguishable from the controls — with
> a middling share and control-identical retransmissions. **No fourth
> candidate is added here.** The map was registered in advance precisely so
> that a residual could be reported as a residual, and this is one: the
> mildest of the three failures is not accounted for by the mechanism that
> accounts for the two severe ones.
>
> **What this licenses:** the severe camera failures are a *between-UE*
> scheduling effect, not sibling contention and not retransmission loss.
> **What it does not:** it does not say *why* those UEs are granted less
> often — that is the ranking question, which needs the candidate-set hook
> this one was deliberately scoped short of.

One per-slot trace of one failing seed separates all three. Registered as an
outcome→meaning map before any trace runs.

### R1 — the UL floor gap is ESTABLISHED, and it is the deployed C's

After the second re-attach the joiner's per-LCG estimate is **zero in 2,000
of 2,000 slots** and it receives **zero grants** — estimate reset → no grant →
no BSR → estimate stays zero, and the floor cannot arm because arming reads
that estimate. **Severity varies by event** (the first re-attach shows 8
grants and 85 % zero), so quote the per-event view, not the run aggregate.

**This is `gNB_scheduler_ulsch.c:48-66`, and the port reproduces both
conditions exactly.** The hardware team is being told about their own
product's join path — which every deployment exercises on every attach and
recovery — not about a limitation of this model.

### Tier-1's SCA loop has NO FIXED POINT, and where it stops decides the allocation

**This supersedes the framing below it.** The convergence half was recorded
first as an adjacency to the degeneracy finding; investigated, it is the
larger of the two and it bears on G3.

**It is not converging slowly — it is not converging.** All 50 Tier-1 solves
of one run, at the shipped cap and at a cap 133× larger: **9 converge (median
56 iterations), 41 hit the cap, identically at both caps**, and the best
`rel_change` those 41 ever reach is **~0.15** against a 1e-6 tolerance.
**Not one of the 41 has its `rel_change` minimum at the end**, so the series
is not decaying. One capped solve's last five values are
`0.085069, 0.07840, 0.085069, 0.07840, 0.085069` — **a period-2 limit
cycle.** The SCA iteration damps toward a vertex the degenerate LP selects by
solver path; when that selection alternates, the damped average has nothing
to settle on.

**So the cap is not truncating a convergence. It is picking a point on a
cycle** — and the point it picks is a real choice: moving the cap from 150 to
**151** changes delivered bytes on 7 of 32 flows and moves **11 of 20 panel
metrics**, including M01 p98 **+13.96 %**, M06 p95 **+10.37 %** and M14
**−12.50 %**.

**THE SCALE THAT DECIDES WHETHER THAT MATTERS IS THE ARM DIFFERENCE.**
TwoTier@150 vs TwoTier@151, against TwoTier vs PF, medians over 5 paired
seeds:

| metric | cap-induced | TwoTier − PF | **cap / arm** |
|---|---|---|---|
| M09 worst Jain | 5.0e-05 | 0.25 | 0.02 % |
| M01 p98 | 5.34 ms | 59.44 ms | 8.98 % |
| M15 jitter | 7.63 ms | 65.44 ms | 11.66 % |
| M06 p95 frame age | 12.48 ms | 63.90 ms | 19.53 % |
| **M03 max gap** | **48.75 ms** | **55.75 ms** | **87.44 %** |
| **M14 availability** | **0.0612** | **0.0259** | **236.36 %** |

**WHERE M14's 236 % LANDS: NOWHERE, AND THAT IS THE ANSWER.** It is the
largest cap sensitivity measured and it belongs in no G-row, so it is placed
here rather than left implied:

- **M14 binds to G11 and to nothing else** (`config/metric_panel.yml`,
  `guarantees: [G11]`).
- **G11's own scorer does not use it.** `scripts/g11_score.py`'s five C1
  conjuncts are M01w / M03w / M05w / M06w / M09w. M14 carries no G11 clause.
- **It appears in no committed scored artefact.** The only non-test reader is
  `wp9_sweep.py`'s online variation rows — where, as this pass established,
  M14 responds to no variation parameter, so those are twelve identical
  copies of one number.
- **And it has never measured what it defines.** `FlowConfig.survival_time_ms`
  is never non-zero anywhere, so M14's `pdb_ms + survival_time_ms` threshold
  collapses to `pdb_ms` and the metric is "fraction of gaps within the flow's
  own PDB" — not a TS 22.104 CSA figure (CLAUDE.md's dormant-mechanism
  table).

**So M14 currently carries no verdict, and must not be quoted without the
236 % beside it.** Its within-seed movement from an arbitrary solver stopping
point is more than twice its TwoTier-vs-PF difference: at that ratio the arm
comparison is not merely imprecise, it is unavailable.

**One place already quotes it as evidence and is wrong to.**
`docs/wp9-regime-map.md`'s G3 rows read *"M03/M14 scored at `t_live_s` ∈
{1,2,4}, reported as a function of it"*. M14 does not read `t_live_s` — its
own docstring says the threshold is used *"instead of T_live-derived ones"* —
so it is not a function of it and never was. Corrected in that document.

**G1 (M01), G8 (M09) and jitter are not threatened** — their arm separations
are 5–5,000× the cap noise. **G3 is.** Its M20 liveness gap is the same
statistic as M03, and this is a **within-seed** variance source, so it is
**invisible to every bootstrap interval in this project**, all of which
resample seeds. G3's TwoTier reading (**+21.34 % [−2.81, +50.02]
INCONCLUSIVE**) therefore rests on an instrument whose within-seed movement
is ~87 % of the difference being measured. **The INCONCLUSIVE verdict
stands; what changes is that adding seeds will not resolve it.**

**Is the deployed C exposed? Unknown, and stated as a hypothesis.** The
degeneracy is a property of the model, and the cap, damping and tolerance are
all ground truth, so the mechanism is present in the C — but GLPK's vertex
selection is not HiGHS's and this is not testable from here. **It is cheap to
answer on the hardware side**: log `rel_change` per SCA iteration and count
how many solves reach `IA_P5G_TIER1_SCA_TOL` before the cap. Owned by whoever
owns the deployed scheduler.

Evidence and reproduction: `sweeps/phase2/sca-convergence-2026-09-04/`.

### Tier-1's LP is degenerate — the mechanism underneath the above

Found while profiling, and it changes what a TwoTier number rests on. Over
one real run's **2,437** Tier-1 LPs, solving each twice — through
`scipy.optimize.linprog` and through a directly-built HiGHS model with
scipy's own options — returns a **different `x` on 1,781 (73 %)**, median max
abs difference **3.3e6**, while the **relative objective gap never exceeds
9.5e-11** and **both points are feasible in every one**. Same optimal face,
different vertex, selected by the solver's path.

**And 41 of 50 Tier-1 solves hit `_SCA_MAXITERS = 150` without reaching
`_SCA_TOL`.** So on 82 % of solves the targets are not a converged fixed
point — they are where the damped sequence stood at iteration 150, over 150
degenerate LPs.

**What this does and does not say.** It does **not** invalidate any Phase 2
number: within a pinned scipy the path is deterministic and the corpus
reproduces. It says those numbers are **contingent on a solver path that
nothing in the repo declares** — a scipy upgrade is a scheduler change here
— and that TwoTier's Tier-1 targets are not uniquely determined by Tier-1's
own model. The 150-iteration cap is faithful to ground truth
(`IA_P5G_TIER1_SCA_MAXITERS`); **whether the deployed C, on GLPK, converges
where this does not is untested**, and GLPK's vertex selection is not
HiGHS's.

Evidence and reproduction: `sweeps/phase2/lp-degeneracy-2026-09-04/`.

### Specification findings — these belong to the test plan's owner

Properties of the guarantees' **definitions**, not of any scheduler. None
surfaced until someone executed the clause literally.

1. **G6 is unscoreable as written.** Its *"shifts by ≤ +20 % relative"* bar is
   undefined when the baseline is legitimately zero, and one of G6's own
   bound statistics is exactly that.

1a. **G6 NAMES NO ESTIMATOR, AND THE THREE DEFENSIBLE READINGS GIVE THREE
   DIFFERENT VERDICTS ON THE SAME CELL.** A second, independent defect in the
   same guarantee — the bar is undefined at a zero baseline (above), *and*
   undefined over runs.

   The clause is *"every G1/G3/G5 statistic stays within its bound and shifts
   by ≤ ▷ +20 % relative"*. It fixes a number and a direction and says
   nothing about how the shift is aggregated across the campaign's runs.
   **That omission is a gap, not an implied convention: the plan names a
   run-rule wherever it means one** — G10 is *"all-pass in **5/5** runs"*, and
   §7 of the open items sets *"defaults are 5 runs (P0) / 3 runs (P1+), 5/5
   for admissible-N"*. G6 is silent.

   Measured on the n=40 records, **protected fleet** (the population G6
   binds to), M03's max gap:

   | arm | median | mean | per-run (all seeds within bar) |
   |---|---|---|---|
   | PF | −0.30 % **PASS** | +0.44 % **PASS** | 36/40 **FAIL** |
   | Reservation | +0.10 % **PASS** | +1.84 % **PASS** | 38/40 **FAIL** |
   | **TwoTier** | **−1.39 % PASS** | **+21.34 % INCONCLUSIVE** | **29/40 FAIL** |

   **PASS, INCONCLUSIVE and FAIL, on one cell, from one dataset.** The
   verdict is a property of a choice the guarantee does not make.

   **AND THE ALL-FLOW ROW DISAGREES IN EXACTLY THE SAME WAY** — TwoTier reads
   median −0.85 % PASS against mean +30.24 % INCONCLUSIVE — so restricting to
   the protected fleet does not stabilise it. Worth stating because the
   protected reading is the one G6 binds to, and it is not the safer one.

   **A THIRD UNSPECIFIED CHOICE COMPOUNDS IT: the run count itself.** A
   per-run conjunction gets strictly harder as runs are added, and §7 lists
   the count as unconfirmed. Reservation **passes at n=3 and fails at n=5**:

   | arm | n=3 | n=5 | n=10 | n=20 | n=40 |
   |---|---|---|---|---|---|
   | PF | FAIL 2/3 | FAIL 4/5 | FAIL 8/10 | FAIL 17/20 | FAIL 36/40 |
   | **Reservation** | **PASS 3/3** | **FAIL 4/5** | FAIL 8/10 | FAIL 18/20 | FAIL 38/40 |
   | TwoTier | FAIL 2/3 | FAIL 4/5 | FAIL 7/10 | FAIL 14/20 | FAIL 29/40 |

   **REGISTERED DISPOSITION: no single G6 verdict is published.** No
   estimator is derivable from the guarantee, so choosing one in code would
   be the tool deciding what the specification declined to. All three
   readings are reported side by side, with the disagreement marked
   (`scripts/g6_fleet_restricted_m03.py`,
   `scripts/g6_conjunction_table.py`). **G6 becomes publishable when its
   owner ratifies an estimator AND a run count** — not before, and not by
   this project picking the one whose answer reads best.

   **This belongs to the test plan's owner, and it is the second defect in
   G6's single sentence.**
2. **GT-7.3's ramp does not reach its own failure condition.**
3. **G10's all-pass criterion cannot distinguish 1/10 from 6/10.** An
   all-pass requirement is binary in a quantity that is not, so a **6×
   improvement is invisible** and the arms read 4 = 4 when the seed counts
   are 6 vs 3. **Recommendation: report the admissible N *and* the per-seed
   pass fraction at the first failing N** — the second is already computed on
   the way to the first.

4. **`two_tier.py:340` and `reservation.py:108-110` assert a fact that
   commit `3788202` falsified, and cite a check that cannot detect it.**
   Both docstrings state *"`mfbr_bps` is never configured on any flow in any
   scenario in this repo"* and offer as proof
   `grep -rn "mfbr_bps" sim/scenarios/ scripts/scheduler_study.py`. MFBR is
   now configured — but in `sim/fleet.py` and `sim/parametric.py`, **which
   that grep does not cover**, so re-running the cited check still returns
   zero matches and still "confirms" the false claim. This is the
   cannot-fail-check shape, and the cost is not cosmetic: those paragraphs
   are the stated justification for treating the `gbr_below` / FIX-2 reserve
   as dormant, so a reader who trusts them concludes a now-reachable path is
   unreachable. **Fix is two edits and a widened grep; deliberately NOT made
   in this block** — it is a claim about scheduler behaviour and belongs with
   a measurement of whether that path now fires, not with a doc pass.

## G12 — the control moved, and the explanation is not the priority fix

**PF's first-violation order flipped to `[4, 2]` on 10 of 10 seeds.** PF's
ranking never reads `priority_level`, so the priority commit cannot be the
route, and **MFBR is eliminated by inspection**: `grep -rn mfbr_bps` outside
tests returns hits in `scheduler/reservation.py` and `scheduler/two_tier.py`
**only** — no traffic generator, no buffer, and nothing on PF's path reads it.

**The candidate that survives is UE-side, which is why it moves every arm.**
`sim/ue_lcp.py:95` orders a UE's logical channels by
`sorted(ue_flows, key=lambda f: f.priority_level)` — logical channel
prioritisation, applied under whichever gNB scheduler is running. Before
`8f9ad34` every flow was tied at `priority_level = 100`, and a stable sort
under a total tie returns **insertion order — i.e. declaration order**. After
it, 5QI 2 (prio 40) is served ahead of 5QI 4 (prio 50), 5QI 4 starves, and
5QI 4 breaches first: `[4, 2]`.

**This is a HYPOTHESIS, not a measurement.** It is consistent with the shape
of the result — uniform on PF, partial on Reservation (6/10), whose own
grant-level ranking still intervenes — but consistency is not confirmation,
and this session has already produced two wrong conclusions drawn from a read.

**The discriminator is cheap and already exists in this campaign.** G12 runs
a canonical declaration order *and* a permutation chosen to give the opposite
order. If the tie-fallback account is right, **the permuted arm should now
agree with the canonical one**, because a real priority dominates declaration
order — whereas pre-fix the permutation is what produced the opposite result.
Read `permutation_orders` against `in_range_orders` in
`sweeps/phase2/g12_mfbr.json`; agreement confirms, continued opposition
refutes.

**If it confirms, G12's published finding is an artefact of the tie.** The
claim that declaration order determines first-violation order would have been
measuring the absence of priorities rather than a scheduler property — which
is a larger finding than P8's outcome either way, and is why this row must
not be closed on the prediction alone.

### P8 scored — NOT CONFIRMED, and the arm ordering is the reason

**P8 predicted TwoTier's order would move toward `[4, 2]`** on the strength of
the priority fix selecting Tier-1's Delay class. **TwoTier is the arm that
moved least.**

| arm | reads `priority_level` in its own ranking? | in-range `[4,2]` |
|---|---|---|
| PF | **no** | **10/10 — uniform** |
| Reservation | partially | 6/10 |
| TwoTier | **yes** | **5/10** (+1 degenerate `[2]`) |

**The effect is strongest exactly where scheduler intervention is weakest**,
which is the opposite of the mechanism P8 named and the signature of the
UE-side `ue_lcp.py` tie-fallback described above: the LCP order is
arm-independent, so it shows through cleanly on PF and is progressively
overridden as the gNB scheduler's own ranking asserts itself. **This is
evidence for that account beyond the PF observation alone** — a monotone
across three arms, not a single control movement — but it remains a
hypothesis until the permutation discriminator is read, because a consistent
story is not a measured one.

**P8's own outcome is a miss, and is recorded as one.** It predicted the right
*direction* on the wrong *mechanism*, which the journal's rules count as a
miss: a prediction that lands for a reason it did not name has not been
tested by the result.

**Two caveats on the cell itself.**

1. **One seed produced a one-element in-range order (`[2]`)** — the degeneracy
   `assert_order_non_degenerate` exists to catch, admitted here under
   `allow_one_element`. A one-element "order" is not an ordering, and it is
   the same shape as the truncated-population family this project keeps
   hitting. It is 1 of 10 and does not change the counts above, but it should
   not be averaged into them either.
2. **Only `mixed_n8` completed.** `drone_heavy_n8` and every later cell were
   not reached before the 2,400 s timeout, so **no cross-composition claim is
   available** — and because the campaign serialises its JSON only at the end,
   a timeout yields no artefact at all. The stdout was preserved manually.
   **That is a real defect in the runner**: a 40-minute campaign that writes
   nothing until the final line loses every completed cell to a timeout.
   Registered, not fixed.

### G12's defect category, searched across what is already measured

Per the stability criterion, G12's runner defect — **a campaign that persists
nothing until its final line** — was searched across the scripts that produced
Phase 2's other numbers. **It is general, not specific to G12.**

| script | run loop | single terminal write | what it produced |
|---|---|---|---|
| `blackout_frequency.py` | `Pool` :80 | `write_text` :84 | the blackout frequency table |
| `phase2_core.py` | :107 | `write_text` :109 | **G1, G3, G5, G8** |
| `g10_rerun.py` | :66 | `open(..., "w")` :72 | **G10** |

**No result was lost to it** — those three ran to completion, so the defect is
**latent** in them and **realized** only in G12, which is the honest way to
state it. But the exposure is real and scales with horizon: every one of these
is a single kill, timeout, or OOM away from discarding a completed multi-hour
grid, and this machine's history includes all three. `g11_campaign.py` is the
counter-example and the model to copy — it banks runs incrementally and
re-enters them on resume.

**This is why Phase 2 is COMPLETE but not STABLE.** The criterion was that a
full pass finds nothing new; this pass found the M21 unlisted-metric
fall-through, `g6_fleet_restricted_m03`'s silent default, the manifest's
transfer-coupled verification, the two cannot-fail `mfbr_bps` docstrings, and
now this. **A clean pass has not yet happened.**

**The `scripts/` layer has now been read — `docs/wp9-defects-log.md` #20.**
Two corrections to this paragraph's own description of it, both derived
rather than restated: there are **44** files, not 42, and **10** are imported
by a test, not 14. The "14 named" counted *mentions*, five of which are
docstring references, so the tested fraction was overstated by half.

The read changed no published number and found, among others: **nine scripts
that cannot run at all** (`TwoTier.__init__` stopped accepting
`tier1_period_slots` at the Phase 2 rewrite; they import cleanly and raise on
their first scheduler), **`wp9_gate.py` silently omitting one axis from its
committed verdict** — `min_rb`, score 152.579, absent from both
`gate_verdict.txt` and `gate_verdict_corrected.txt` under a docstring
promising nothing is omitted — and **`g12_score.py`'s decompose fix applied
at one of five aggregation sites in its own file**, whose triggering
condition is G12's own next step of running a second cell.
