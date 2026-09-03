# Phase 2 — fast numbers on fixed code

## SCOPE, FIXED BEFORE RUNNING — three states, not "every guarantee"

Written down first so the output is **a list of what was measured and what
was not**, rather than a table with silent gaps. A guarantee missing from a
results table is indistinguishable from one that failed to produce a number,
which is the empty-selection shape at the level of the report.

### SCOREABLE NOW — re-measure all seven

**G1, G4, G5, G6, G8, G10, G12.**

**None of their existing numbers survive.** Every one was computed under BOTH
defects: the population default (worst-flow statistics unrestricted, fixed in
`9c23327`) and the `priority_level` default (every flow tied at 100, fixed in
`8f9ad34`). G6 and G10 were argued to be population-immune — G6 restricted
via M20, G10's M07/M08 select `flow_class == "GBR"` — **but neither is immune
to the priority default**, so both re-run. That argument is registered as a
falsifier in `prediction-journal.md` P9: if G10 moves under the population
change specifically, the `flow_class` reasoning was insufficient.

### SCOREABLE WITH A STATED LIMIT — three, each limit named in the output

| G | limit | why |
|---|---|---|
| **G3** | ~~Do not measure before #22 lands.~~ **UNBLOCKED — #22 landed.** | The cadence caveat was silencing real breaches on M03/M20, the metric G3 binds to, so a verdict computed before the fix was silent precisely on the flows that failed worst. `M03` now distinguishes slow-BY-DESIGN (suppressed) from DEGRADED-by-the-network (scored, and flagged as such). G3 moves into the re-measure set: **8 scoreable now, 2 with a stated limit.** |
| **G9** | Score 3 of 4 clauses; state the 4th OPEN. | **0 of 50 scheduled cold cycles completed attach.** Whether that is a scenario defect or a real scheduler finding is unestablished, and scoring it either way would assert something unmeasured. |
| **G11** | Report WHAT WAS MEASURED, not a G11 verdict. | C2 was never wired (commit 7 built the drift detector, commit 8 never collected its inputs — defects-log #16). C3/C4/C5 cannot be scored at n=3: C3's CoV needs ≥5 per GT-7.4, and C4/C5 are cross-seed by construction. Only **C1** is a within-run check that survives at 3 seeds. |

### NOT PARTICIPATING — two, and the reasons are structural

| G | why it is out |
|---|---|
| **G2** | Needs TB-size quantisation, planned and unbuilt. **And separately**, its E-STOP flow is **DL** (`sim/fleet.py:179`) while its named failure mode — the BSR/SR desync — is an **uplink** mechanism. So the flow cannot reach the failure even once the mechanism exists. Two independent blockers, and building only the first would not produce a scoreable G2. |
| **G7** | No MFBR enforcement anywhere in `sim/`. Containment is observable; **clipping is not**, and clipping is half the pass criterion. Structurally out. |

**Count, derived from the rows above: 8 re-measured (G3 joined once #22
landed), 2 with a stated limit, 2 not participating. Twelve accounted for.**

### Carried into Phase 4's budget

**Overnight time goes to guarantees where more samples buy tighter numbers,
not to ones blocked on missing code.** So the budget excludes G2 and G7
entirely, and gives G3 a full share now that #22 has landed. G11's share is
sized for C1 only — spending an overnight on C3/C4/C5 at n=3 buys nothing,
because they are unscoreable at that seed count for reasons no amount of
wall-clock changes.

---


**What this pass validates, stated before any number.** At 3 runs / 5–10
minutes per guarantee these check **plumbing**, not statistics: that the code
runs, that the instrument fires, and that the value is plausible. They do not
establish that a value is right. Two blocking findings from Phase 1 remain
unverified (#22 M03's cadence caveat firing on a genuine failure, #18 the
handshake bypassing arrival accounting), and **every number below carries
that caveat.**

**And one thing this pass supersedes.** Every persisted artefact under
`sweeps/wp9/` was produced with `priority_level` constant at 100. Re-scoring
them measures the pre-fix configuration, so Phase 2 **re-runs** rather than
re-scores.

---

## G2 — the record was wrong twice, and the real blocker is arithmetic

`docs/wp9-regime-map.md`'s G2 row reads: *"Not answered by WP9 — and the
reason is now STRUCTURAL, not scenario coverage. Needs an event-triggered
STOP flow and trial accumulation; no WP9 cell models it."*

**Both halves are false.**

1. **The event-triggered mechanism exists.** `sim/traffic.py` dispatches
   `traffic_kind="aperiodic_event"` (and `"machine_vision"`) to
   `_gen_poisson_triggered_burst`, a per-slot Bernoulli-thinned Poisson
   **event** trigger — its own docstring says *"applied here to event
   triggering instead of byte counts"* — parameterised by `rate_hz` and
   `burst_bytes`.
2. **WP9 cells DO model it.** `sim/fleet.py:179` declares a 5QI 85 DL Delay
   E-STOP on `aperiodic_event` at **0.2 Hz, 40 bytes**, and it is present in
   3 of the 4 compositions:

   | composition | 5QI-85 flows |
   |---|---|
   | `ugv_heavy` | 4 |
   | `mixed` | 2 |
   | `drone_heavy` | 1 |
   | `sensor_dense` | 0 |

   So a STOP flow has been generating traffic in **every stage-4, stage-5 and
   G12 run**.

**What is actually missing is that nothing SCORES it.** No metric in
`config/metric_panel.yml` reads 5QI 85. The trials were generated and never
counted — the *unobservable* half of the built-but-not-reached shape, not the
unreachable half.

**And the real blocker is a denominator, not a mechanism.** At 0.2 Hz, the
sweep's own 8,000-slot cell (2 s at numerology 2) yields
`0.2 × 2 × n_ues` events — **under one per run**. "100 % of STOP events
≤ 100 ms across all trials" over a denominator near zero is the
empty-selection shape wearing a guarantee. G2 needs a long horizon or a
raised rate; it does not need a new mechanism.

**A naming mistake worth keeping.** The first version of
`scripts/phase2_g2.py` set `traffic_kind="poisson_triggered_burst"` — the
FUNCTION name — and died on `ValueError: Unknown traffic kind`. The dispatch
key is `aperiodic_event`. It failed loudly only because `sim/traffic.py`
raises on an unknown kind rather than returning no arrivals; had it returned
`[]`, the run would have completed with zero STOP trials and looked exactly
like the "structurally unreachable" claim it was testing.

### G2 measured — 91 trials, and the margin is not what the bound suggests

`scripts/phase2_g2.py`, N=8, load ×1.0, 200,000 slots (50 s), one seed, the
E-STOP's own 0.2 Hz / 40 B from `sim/fleet.py:180`, one STOP flow per UE.

```
expected trials/run (derived from rate x duration x n_ues): 80

arm           trials  undel  miss    pass   p50 ms   max ms   wall
PF                91      0     0  1.0000     0.50     1.75  38.6s
Reservation       91      0     0  1.0000     0.25     3.75  56.6s
TwoTier           91      0     0  1.0000     0.25     2.00 117.9s
```

**91 trials against 80 expected** — a Poisson draw at +1.2σ, so the mechanism
fired as specified. That check is stated first because a pass fraction over a
near-empty denominator is the shape this guarantee was previously stuck in.

**Every arm passes G2 at 100 %. The margin against G2's bound is 27–57×, and
that is the wrong comparison.** 5QI 85's *standardised* PDB is **5.0 ms**
(TS 23.501, via `pdb_for_5qi`), not 100 ms. Against the flow's own budget:

| arm | max STOP latency | vs G2's 100 ms | vs 5QI 85's own 5 ms PDB |
|---|---|---|---|
| PF | 1.75 ms | 57× margin | 2.9× |
| Reservation | 3.75 ms | 27× margin | **1.3×** |
| TwoTier | 2.00 ms | 50× margin | 2.5× |

**So this pass could not have failed at this cell**, and saying so is the
point: it is a plumbing result. What it establishes is that the instrument
exists, fires at the specified rate, and produces a scoreable number — which
is exactly what the record said was structurally impossible. What it does
NOT establish is that G2 holds under load, and the Reservation row is the one
to watch, because 3.75 ms against a 5 ms budget has almost no headroom while
looking like a 27× win against the guarantee's own bar.

### G2's could-it-have-failed test: it could not, and the reason is structural

Same cell at **load ×3.0**:

```
arm           trials  undel  miss    pass   p50 ms   max ms
PF                87      0     0  1.0000     0.25     3.75
Reservation       87      0     0  1.0000     0.25     2.25
TwoTier           87      0     0  1.0000     0.50     3.50
```

**Tripling the offered load does not move STOP latency at all** — it stays in
the same 2–4 ms band, and the per-arm ordering reshuffles within it (PF's max
rose 1.75 → 3.75, Reservation's fell 3.75 → 2.25), which is noise at this
sample size, not a load response.

**Why it cannot fail here, stated mechanically.** The E-STOP is a **40-byte**
burst on the tightest-PDB class in the panel. Forty bytes fits inside any
grant on any arm, and 5QI 85's priority (21) is above every background class,
so no amount of best-effort load displaces it. The 2–4 ms observed is the
scheduling latency floor — a few slots — not a queueing result.

**AND THE DECISIVE POINT: the E-STOP is DL, while G2's named failure mode is
a UL mechanism.** `sim/fleet.py:179` declares `_Flow(85, "DL", ...)`. The
BSR/SR desync that `docs/wp9-plan.md` §19.5/§20.1 identifies as G2's real
failure class is an **uplink** path — SR on PUCCH, `sr-ProhibitTimer`, grant,
BSR. A downlink flow never touches it.

**So the two halves of G2 do not currently meet.** The flow that exists is
structurally immune to the failure mode that was named as its blocker. That
is a sharper statement than "G2 is blocked": it says the blocker and the
instrument are about different directions, and a G2 test that could fail
needs either a UL STOP flow or a DL failure mode. Neither exists today.

**G2 verdict for the fast pass: MEASURABLE, PASSES TRIVIALLY, NOT YET
INFORMATIVE.** Budget spent: 6 runs, ~10 min — at the limit, so no further
excursion was bought.

---

## G1 / G3 / G5 / G8 — one run, both populations, and the population decides the verdict

`scripts/phase2_core.py`, N=8, load ×1.0, 40,000 slots (10 s), 1 seed,
3 arms, **44 s total wall**. Every worst-flow statistic is reported over all
flows and over the protected fleet (`NON_PROTECTED_5QI = {8, 9}` excluded).

### G1 — M01 p98 (bound 100 ms) and M15 jitter

| arm | p98 ALL | winner | p98 PROTECTED | winner | M15 all | M15 prot |
|---|---|---|---|---|---|---|
| PF | 300.00 | `ue8_qfi9` | **28.00** | `ue6_qfi1` | 38.25 | 38.25 |
| Reservation | 300.25 | `ue8_qfi9` | **22.00** | `ue8_qfi1` | 27.50 | 27.50 |
| TwoTier | 300.00 | `ue4_qfi9` | **96.75** | `ue6_qfi1` | 171.25 | 92.25 |

**The all-flow reading is saturated, not measured.** All three arms report
~300.0 ms, won by 5QI 9 in every case — and 300 ms is exactly 5QI 9's own
PDB. The statistic is pinned at the filler's ceiling, which is why the three
arms agree to within 0.25 ms.

**Read that way, G1 FAILS on every arm (300 ms against a 100 ms bound) and
no arm is distinguishable. Read on the protected fleet, G1 PASSES on every
arm and the arms separate 4.4×** — 22.00 / 28.00 / 96.75. The unrestricted
statistic destroys exactly the differentiation G1 exists to show, and it is
the one the regime map cites.

**TwoTier's protected p98 is 96.75 ms against a 100 ms bound** — 3.25 ms of
headroom, at one seed. That is the number worth carrying forward.

M15 tells the same story one level down: TwoTier's jitter **halves**,
171.25 → 92.25 ms, when the filler is excluded. PF's and Reservation's do not
move at all, because their worst jitter was already a protected flow.

### G3 — liveness gap (bound 500 ms)

| arm | M03 all-flow | M20 protected | winner | caveat |
|---|---|---|---|---|
| PF | 136.50 | 136.50 | `ue6_qfi1` | MAX-over-UEs |
| Reservation | 127.00 | 127.00 | `ue3_qfi1` | MAX-over-UEs |
| **TwoTier** | **515.50** | **515.50** | `ue4_qfi1` | MAX-over-UEs |

**TwoTier BREACHES G3's 500 ms bound at the base cell** (515.50 ms) where PF
and Reservation sit at ~130 ms. Checked, not assumed: the caveat carried is
the panel's registered *"A MAX over UEs"* one, **not** the cadence caveat —
the flow's median gap is 100 ms, far below the 500 ms threshold that would
make the reading unscoreable. So this is a real breach.

M03 and M20 are identical here because the winning flow is already a
protected 5QI 1 bearer. **That is the useful control**: it shows the
restriction is not simply moving numbers around, and it makes the G1 and G8
divergences below meaningful rather than mechanical.

### G5 — PDU-set completeness (≥ 0.99) and frame age p95 (≤ 67 ms)

| arm | M05 all | M05 prot | M06 p95 |
|---|---|---|---|
| PF | 0.9967 | 0.9967 | 25.50 |
| Reservation | 0.9967 | 0.9967 | 23.48 |
| TwoTier | 0.9967 | 0.9967 | **83.11 FAIL** |

M05 passes on every arm and is **identical to four decimals across all
three** — a flat statistic at this cell, worth noting because a flat metric
cannot discriminate. **TwoTier fails M06** at 83.11 ms against 67.

### G8 — BOTH conjuncts, and the second one is new

| arm | Jain ALL | Jain PROT | M22 epochs all | M22 epochs prot | longest |
|---|---|---|---|---|---|
| PF | 0.9446 | 0.9995 | 0 | 0 | 0.00 s |
| Reservation | 0.9419 | 0.9998 | 0 | 0 | 0.00 s |
| TwoTier | **0.8783 FAIL** | 0.9584 | 0 | 0 | 0.00 s |

**Same inversion as G1, opposite direction.** All-flow Jain says TwoTier
FAILS G8's ≥ 0.9 bar; protected says it passes at 0.9584. The all-flow number
is dominated by the deliberate starvation of a non-GBR filler, which a
QoS-aware scheduler is *supposed* to starve — §24.2's causal inversion,
reproduced live on fixed code.

**M22 reports 0 starvation epochs on every arm, and it is not floored.** The
filler is being starved by TwoTier (all-flow Jain 0.8783) yet registers no
epoch, which is the correct answer: its starvation is *partial* — some
delivery in every one-second bucket — not a full second of silence. M22
distinguishing "served badly" from "not served at all" is exactly what G8's
second conjunct asks, and it took a value that could have been non-zero.

### The pattern across all four

**On two of the four guarantees the population changes the VERDICT, and in
opposite directions:**

| | all-flow verdict | protected verdict |
|---|---|---|
| G1 | FAIL, all arms, no separation | PASS, all arms, 4.4× separation |
| G8 | TwoTier FAIL | TwoTier PASS |

G3 and G5 are unaffected, because their winning flows were already protected.
**So the restriction is not a uniform shift — it changes the answer exactly
where the aggressor or filler was winning the contest, and nowhere else.**
That is the shape Phase 1 predicted from `stage2_rows.csv` (5QI 9 winning
M01 in 85.4 % of 7,560 rows) and it is now reproduced end-to-end on fixed
code.
