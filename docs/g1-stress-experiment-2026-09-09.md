# G1 as a stress experiment — driving a robot while the fleet works

**2026-09-09.** Registered in `docs/g1-step0-2026-09-09.md`, which is Step 0
and must be read first: **all three of its findings had to land before any
number here was worth taking.** In particular the guarantee had never been
scored on the flow it is named for.

**Artefacts.** `sweeps/g1-stress/g1_stress.json` (960 runs, stamped, with a
projected row list so `verify_claims` can re-derive every published figure
from it — its `.runs.jsonl` resume ledger is gitignored by repo convention,
which is why the checkable figures had to live in the JSON),
`sweeps/g1-stress/g10_remeasure_cap4.json` (270 runs).
**Code.** Suite green, `--check` re-baselined **shape-only with zero numbers moved** (§11), `verify_claims --check` 15 as expected / 0 not.

---

## 0. What had to be fixed first

Three, each measured rather than assumed (`docs/g1-step0-2026-09-09.md`):

1. **The clause has two pass criteria**, and they fail in opposite
   directions. `p98 ≤ RAN PDB` ranges over DELIVERED commands, so dropping
   commands improves it; `zero gaps ≥ 200 ms` is receiver-side, so it widens
   around a command that never came. Every prior G1 row reported neither of
   them.
2. **G1 is a downlink guarantee and the published statistic was uplink** —
   M01's winner was a UL flow on 9 of 9 runs, and on TwoTier it was the
   5QI-2 camera, not even the telemetry. The DL flow the clause is about sat
   at 2.75–4.25 ms p98 and could never surface through a maximum.
3. **GT-1.1's cell did not exist.** No workload any guarantee is scored on
   carried a 5QI-1 downlink flow — the two YAML scenarios that do are
   `Delay` class with GFBR 0 and are not scored on — and **no scenario in
   the repo has a saturating downlink at all**, the condition GT-1.1's own
   text calls *"an idle DL link measures nothing"*. Built as
   `sim/scenarios/g1.py`.

---

---

## 1. The question, in operator terms

**Driving a robot feels immediate while the rest of the fleet works.**

- A **p98 breach** is a robot that lurches.
- A **200 ms gap** is a command that never arrives.

Both are scored, separately, and neither implies the other.

---

---

## 2. G10's boundary, re-measured first because it sets the axis

The UE axis is only interpretable against the fleet size the cell can
actually host, and that number has moved twice in a week. **Re-measured on
current code rather than quoted** — `n_ues ∈ {2,4,5,6,7,8,10,12,16}`, 10
seeds per point, cap 4, RA + SRB, horizon 20,000, 270 runs, 2,669 s CPU:

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | **boundary** |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 10 | 10 | **10** | 4 | **12** |
| Reservation | 10 | 10 | 10 | **10** | 7 | 3 | 0 | 0 | 0 | **6** |
| TwoTier | 10 | 10 | 10 | 10 | **10** | 9 | 0 | 0 | 0 | **7** |

**PF 12 / Reservation 6 / TwoTier 7, reproducing the 2026-09-08 figure cell
for cell, and no arm is non-monotone.** The published `6 / 6 / 5` and the
`8 / 4 / 4` before it are both withdrawn (`docs/gbr-offered-shortfall-2026-09-08.md`).

**The re-measurement is also a check on this campaign's own code change.**
`delay_p999_ms`/`delay_max_ms` landed between the 2026-09-08 measurement and
this one, changing the AST stamp (`0ef6fa56f0878872` → `cd84ef3b7ba88103`).
The boundary is identical in every cell, which is what a shape-only addition
should do and is stronger evidence than the corpus diff alone.

---

---

## 3. The experiment

| | |
|---|---|
| **scenario** | `sim/scenarios/g1.py::build_gt11_scenario` — GT-1.1's cell, built for this |
| **the instrument** | cmd_vel, **20 Hz × 100 B on 5QI 1 DL, GBR**, GFBR 16 kbps. PDB (100 ms) and priority (20) DERIVED from TS 23.501, never authored |
| **driven robots** | **2, FIXED, independent of the axis.** If every robot were driven, "worst cmd_vel p98" would be a worst-of-N order statistic and the UE axis would move the statistic as well as the load |
| **the load** | Asset B's full committed profile UL **plus a saturating 5QI-9 DL firmware pull** — 50 Mbps offered against a downlink that delivers ~17 |
| **arms** | PF, Reservation, TwoTier |
| **seeds** | 10, paired |
| **horizon** | **40,000 slots = 10.0 s** at μ=2 (0.25 ms slots), DSUUU, 40 MHz — **200 cmd_vel messages per driven robot per run** at 20 Hz. GT-1.1 specifies 10 min; §3b states every pass's horizon and what each supports |
| **caps** | both (§7) |

**Two sub-experiments, both reported.**

- **A — fleet size.** `n_ues ∈ {4, 6, 7, 8, 10, 12, 14, 16, 24}` at committed
  ×1.0. 6, 7 and 12 are on the grid because they ARE the three arms'
  re-measured boundaries; 24 is 2× the largest.
- **B — load per robot.** `committed_mult ∈ {0.5, 0.75, 1.0, 1.25, 1.5,
  1.75, 2.0, 3.0}` at **N = 6**.

**Why B fixes at N = 6, stated because G1's current 8-UE row is exactly the
incoherence this avoids.** 6 is the MINIMUM of the three re-measured
boundaries (Reservation's), so **every arm is inside its own admissible
fleet and the committed axis is the only thing that moves.** At the old
row's N = 8, Reservation and TwoTier are already past their boundaries while
PF has 4 robots of headroom — the same point is overload for one arm and
comfort for another, and a comparison across it is a comparison of two
different situations.

**The grid.** 2 clause parts × 9 UE counts × 3 arms × 10 seeds × 2 caps for
A, and 2 clause parts × 8 load levels × 3 arms × 10 seeds × 2 caps for B,
sharing the point (N=6, ×1.0): **960 driver runs.**

---

---

## 3a. Was the hook non-perturbing, and could the check have failed?

The rank trace runs on every graded run, so it has to be shown not to change
what it observes. **Hook on versus hook off, byte-identical on 6 of 6 cells**
(3 arms × 2 caps, 8,000 slots, G1's own scenario).

**And the first version of that check said every arm DIFFERED — including PF,
whose rank sink cannot change anything.** A null control (hook off, twice)
also "differed", which is what exposed it: the digest was hashing
`_message_ledger` and `_ue_lcp`, two live object handles the driver hands
back, whose `repr()` carries a memory address. **The instrument was
measuring allocation, not results.** Excluded, and the check has dynamic
range — it separates the two caps and the three arms.

That is `docs/dl-comparator-result-2026-09-07.md`'s bit-identity result
re-established **on this scenario** rather than inherited from a different
one, which is the standing scope rule.

---

## 3b. Horizons, stated per pass, and what each one supports

**Every pass, explicitly.** Slot duration is **0.25 ms** throughout (μ=2), and
cmd_vel runs at **20 Hz**, so commands per robot is `seconds × 20`.

| pass | slots | seconds | runs | **commands per robot** | total commands | aggregate cell time |
|---|---|---|---|---|---|---|
| **the grid** (§4) | **40 000** | **10.0** | 960 | **200** | 383 959 | **9 600 s (160 min)** |
| extension probe (§6) | 40 000 | 10.0 | 30 | 200 | 12 000 | 300 s |
| **positive control** (§5) | **40 000** | **10.0** | 18 | **200** (185 / 46–49 / **0** as the radio degrades) | 4 998 | 180 s |
| tie-break control (§4.5) | 40 000 | 10.0 | 80 | 200 | 32 000 | 800 s |
| tail pass A (§7) | 200 000 | 50.0 | 36 | 1 000 | 71 992 | 1 800 s |
| **tail pass B** (§7a) | **1 000 000** | **250.0** | 18 | **5 000** | 179 977 | 4 500 s |
| **all cmd_vel passes** | | | **1 142** | | **684 926** | **17 180 s (4.77 h)** |

Command totals are **measured** for the grid, the positive control and the two
tail passes (from their own `message_count`s) and **derived** as
`runs × 2 robots × 200` for the extension and tie-break probes, which recorded
pass/fail rather than counts; the extension probe's log shows `msgs=200` on all
30 runs. **The positive control's 4 998 is far below `18 × 2 × 200 = 7 200`
because that is the point of it** — the radio degrades until commands stop
arriving, and at −6 dB none do.

**G10's re-measurement (§2) is 20 000 slots = 5.0 s over 270 runs**, and it
carries **no cmd_vel flow at all** — it runs the parametric workload and
supports no G1 statistic. It sets the UE axis range and nothing else.

### 3b.1 Which statistic each horizon supports

**p98 over 200 commands is the 4th-largest sample** (`k = min(n-1, int(n·0.98))
= 196`, 0-based, so 3 samples sit above it). That is **adequate for a bound
check and thin for a distribution**: it says whether four commands in ten
seconds exceeded 95 ms, and it does not describe the shape of the tail. The
per-seed yield rule over 10 seeds is what carries it, not the single run.

**And the short horizon does not flatter the bound — it is conservative.**
Like-for-like at N=6, worst p98 over the seeds in each pass:

| | 10 s (grid, 10 seeds) | 250 s (tail B, 3 seeds) |
|---|---|---|
| PF | **3.00 ms** | 1.50 ms |
| Reservation | **3.00 ms** | 1.50–1.75 ms |
| TwoTier | 1.50–3.00 ms | 1.50–1.75 ms |

The 4th-largest of 200 lands on a higher quantised level than the 100th-largest
of 5 000 does, so **the 10 s runs report the same or a worse p98 than the 250 s
runs at the same fleet size.** A longer horizon would not have found a p98 the
grid missed.

### 3b.2 The gap criterion is the one where horizon genuinely matters — and it was checked

**"Zero gaps ≥ 200 ms" over 10 s IS a weaker per-run statement than over
250 s**, and unlike p98 the statistic *grows* with observation time. Measured:
the grid's largest gap anywhere is **103.0 ms** and tail pass B's is also
**103.0 ms** — but the grid needed 960 runs to reach it while tail B reached it
in 18.

**Can a 10 s run contain a 699 ms gap? Yes, and it is not an argument —
it is measured at the grid's own horizon.** The positive control (§5) runs
**the same 40 000 slots** and records gaps of **698.8 ms** and **2 935.0 ms**.
So the grid's horizon is not structurally unable to hold a breach; a 200 ms gap
is 2 % of a 10 s run, and gaps 14× the bound fit inside one comfortably. **The
criterion is not passing because the window is too short to contain a failure.**

**What the grid actually observed**, over 382 039 inter-arrival gaps. The
cadence is 50 ms, so a gap is counted in command periods, not milliseconds:

| worst gap in a run | meaning | runs of 960 |
|---|---|---|
| 51.5 – 61.8 ms (~1 period) | ordinary jitter, nothing missed | 923 |
| **≥ 90 ms (2 periods)** | **one command missed** | **37** |
| ≥ 140 ms (3 periods) | two consecutive missed | **0** |
| **≥ 200 ms (4 periods)** | **THE BOUND** | **0** |

**The largest run of consecutive losses anywhere in 960 runs is ONE, and the
bound needs three.** Per flow: 38 of 1 920 show a ≥ 90 ms gap, and 41 of 1 920
delivered 199 rather than 200 — the three-flow difference is losses at a run's
first or last command, which leave no interior gap.

That is a more useful margin statement than "1.9× inside", and it is why
§4.1 says to size headroom in commands rather than milliseconds.

### 3b.3 Against GT-1.1's specified 10 minutes — and whether it matters

**GT-1.1 specifies 10 min of steady state, 3 arms, 5 runs — 150 min of
observation. The grid alone is 160 min, and all cmd_vel passes together are
286 min, so the AGGREGATE exceeds the specification by 1.9×.** What is short is
the **per-run duration: 10 s against 600 s, one sixtieth**, and the longest run
here is 250 s, five twelfths.

**This is the shape that caught G11** — a clause passing at a fraction of its
specified duration, unnoticed until the scenario was audited
(`docs/wp9-g11-plan.md`) — so it is stated rather than left to be found.

**Where the difference does NOT matter.** Both criteria are evaluated inside a
window, not across one, and 960 independent seeds sample 960 different 10 s
windows. For a **stationary** process, aggregate coverage substitutes for run
length, and the aggregate here exceeds the plan's.

**Where it could matter, and what bounds it.** Aggregate coverage does *not*
substitute for run length against a **non-stationary** effect — something that
only appears after minutes, such as a slowly-filling queue or a drifting
fairness ledger. **This cell has such an element**: the firmware pull offers
50 Mbps into a downlink that delivers ~17, so its backlog grows without bound
for the whole run. At 250 s that backlog is 25× what it is at 10 s.

**The check is that the numbers are flat across a 25× horizon span.** Tail
pass B's p98, p99, p99.9 and worst gap at N=6 are indistinguishable from the
grid's at the same point. **That is evidence of stationarity out to 250 s, and
it is not proof out to 600 s** — the remaining factor is 2.4×, and closing it
is a run, not an argument.

**Neither criterion's verdict is at risk from the shortfall**: p98 is
10.6× inside its bound and reported *conservatively* by the short horizon, and
the gap criterion demonstrably fires at this horizon while the worst observed
gap used one of the three misses the bound allows.


## 4. The result — 0 failures of 960, on both criteria

| | |
|---|---|
| **part 1** — cmd_vel p98 ≤ 95 ms | **0 breaches of 960** |
| **part 2** — zero command gaps ≥ 200 ms | **0 breaches of 960** |
| instrument went silent | **0 of 960** (min 199 of 200 commands delivered) |
| worst p98 anywhere | **9.00 ms** — 10.6× inside the bound |
| worst max anywhere | 12.00 ms |
| worst gap anywhere | **103.00 ms** — 1.9× inside the bound |

**There is no boundary inside either axis, on any arm, at either cap.**
Reporting the "boundary" as the top of each axis would be reading the grid's
own edge as a measurement; the honest statement is that the clause does not
break anywhere it was swept, and §6 is what establishes how far past that
the statement survives.

### 4.1 The two criteria have very different margins, and the second is the tight one

**p98 is 10.6× inside its bound; the worst gap is 1.9× inside its.** The gap
criterion is not decoration — it is the binding one, by a factor of five.

**And the mechanism is arithmetic.** The command cadence is 50 ms and the
worst run delivered **199 of 200**, so a 103 ms gap is exactly *one missed
command*: two nominal periods back to back. **The 200 ms bound tolerates three
consecutive losses; the largest run of consecutive losses anywhere in 960 runs
is one** (§3b.2 has the distribution: 37 runs of 960 lost a single command,
none lost two in a row). A reader sizing headroom should size it in commands,
not milliseconds.

### 4.2 Sub-experiment A — the QoS arms are flat in fleet size and PF is not

Worst cmd_vel p98 (ms), max over 10 seeds × 2 driven robots:

| cap | arm | N=4 | 6 | 7 | 8 | 10 | 12 | 14 | 16 | 24 |
|---|---|---|---|---|---|---|---|---|---|---|
| **4** | PF | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | **3.25** | **4.00** | **5.50** |
| | Reservation | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 |
| | TwoTier | 3.00 | 1.50 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 |
| **2** | PF | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | **4.00** | **5.50** | **6.50** | **9.00** |
| | Reservation | 3.00 | 3.00 | 3.00 | 2.75 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 |
| | TwoTier | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 | 3.00 |

**Reservation and TwoTier are flat at 3.00 ms from 4 robots to 24. PF's
command latency grows with the fleet** — 3.00 → 5.50 ms at the deployment's
cap, 3.00 → 9.00 ms on the narrow carrier, a 3× rise. **The narrower carrier
roughly doubles PF's degradation and does nothing to the QoS arms.**

### 4.3 Sub-experiment B — nothing moves with load, on any arm

Across `committed_mult` ×0.5 → ×3.0 at N=6, every arm sits at **3.00 ms**
(one Reservation cell at 3.25). **Six-fold offered load changes the drive
command's latency by one 0.25 ms slot.**

**The two sub-experiments answer differently, and that is the finding.**
Fleet size moves PF and nothing else; load moves nothing at all. The
operator-facing form: *how many robots you run matters on PF and not on the
QoS arms; how hard you work them does not matter on any of them.*

### 4.4 The rank trace — the prediction, scored

**The registered prediction was that drive commands now take precedence.**
It holds, and the trace names the term.

Mean downlink rank of a driven robot (0 = served first):

| arm | mean rank | worst |
|---|---|---|
| PF | **1.434** | **8.385** |
| Reservation | **0.467** | 0.975 |
| TwoTier | **0.463** | 1.000 |

**On both QoS arms a driven robot never falls below rank 1 — it is first or
second on every slot of every run. On PF it can fall to rank 8.4.** That is
the whole of the arm difference in §4.2, in one number.

Which term decided each downlink adjacency:

| arm | all runs | **at N=6, the realistic cell** |
|---|---|---|
| PF | `-metric` 99.69 % · TIED 0.31 % | `-metric` 99.64 % · TIED 0.36 % |
| Reservation | `-coef` 91.93 % · **`has_gbr` 3.71 %** · TIED 2.50 % · `pdb_ms` 1.86 % | `-coef` 76.74 % · **`has_gbr` 13.14 %** · TIED 8.29 % · `pdb_ms` 1.83 % |
| TwoTier | TIED 85.85 % · `pdb_ms` 7.30 % · **`has_gbr` 4.24 %** · `-coef` 2.61 % | TIED 71.64 % · **`has_gbr` 11.91 %** · `pdb_ms` 9.82 % · `-coef` 6.63 % |

**`has_gbr` — dead on every scenario this repository had before today —
decides 12–13 % of downlink adjacencies at the realistic fleet size.** It is
diluted at N=24 (0.6–0.8 %) because most robots there carry only the fleet
control loop.

**And what puts a driven robot BEHIND the robot above it:**

| arm | decisive terms on a driven robot's losses |
|---|---|
| PF | `-metric` 99.26 % · TIED 0.74 % |
| Reservation | TIED 46.63 % · `-coef` 45.18 % · `pdb_ms` 8.19 % |
| TwoTier | TIED 92.04 % · `pdb_ms` 7.96 % |

**`has_gbr` accounts for 0.00 % of driven-robot losses on either QoS arm.
It only ever promotes them, never demotes them** — which is precedence
stated as a measurement rather than as an intention. Where a driven robot
*is* demoted, the term is `pdb_ms`: it loses to a flow with a **tighter**
deadline (5QI 82's standardised 10 ms against 5QI 1's 100 ms), which is the
ordering behaving correctly.

**5QI 1 is not SRB, and the trace confirms the distinction matters.** SRB is
RRC signalling promoted onto LCG 0 through `sched_inactive`; the commands
here are protected by `priority_level` and the GBR/PDB tiers. `sched_inactive`
appears in no downlink adjacency in this campaign.


### 4.5 The tie-break control — the result is NOT declaration order

**The driven robots are UEs 1 and 2, and TwoTier's downlink order is a TIE on
92 % of the adjacencies where a driven robot loses.** So "commands are served
first" could be *position* rather than *priority*, and that is exactly the
artefact that stopped G12's ordering being promoted to a scheduler property.
It has to be excluded before the prediction is scored.

**The control is tie-break-only** (`scheduler/flow.py::tie_break_term`), not
`permute_flows`: permuting the flow list moves the tie-break AND every
first-flow-found-wins lookup at once, so an outcome that shifts under it does
not say which caused it. Run at **cap 2**, where TwoTier's tie rate is
highest — the strongest test. PF is excluded and needs no control: its ties
are 0.31 % of adjacencies.

80 runs, 10 seeds per cell:

| N | arm | tie-break | p98 median | p98 worst | worst gap | part 1 | part 2 |
|---|---|---|---|---|---|---|---|
| 6 | Reservation | position | 1.75 | 3.00 | 54.5 | 10/10 | 10/10 |
| 6 | Reservation | **seeded** | **1.75** | **3.00** | 54.5 | 10/10 | 10/10 |
| 6 | TwoTier | position | 1.75 | 3.00 | 100.0 | 10/10 | 10/10 |
| 6 | TwoTier | **seeded** | **1.75** | **3.00** | **54.5** | 10/10 | 10/10 |
| 16 | Reservation | position | 2.75 | 3.00 | 56.5 | 10/10 | 10/10 |
| 16 | Reservation | **seeded** | **2.75** | **3.00** | 55.0 | 10/10 | 10/10 |
| 16 | TwoTier | position | 1.75 | 3.00 | 100.0 | 10/10 | 10/10 |
| 16 | TwoTier | **seeded** | **1.75** | **3.00** | **54.7** | 10/10 | 10/10 |

**The p98 median and worst are IDENTICAL in all four pairs.** Re-seeding the
tie-break moves neither statistic on either arm at either fleet size, so the
commands' precedence is not being supplied by their position in the flow
list.

**And the one thing that does move goes the other way**: TwoTier's worst gap
*improves* under a seeded tie-break, 100.0 → 54.5 ms — position-decides was
the slightly worse of the two. Both pass either way, so this is reported
rather than leaned on.

**A registered control that fired and CONFIRMED.** Most of this project's
controls have refuted the thing they were pointed at (G12's ordering, the
grant-density framing, `permute_flows` on the first-violation order). This
one did not, and the difference matters: `has_gbr` deciding 12–13 % of
adjacencies at N=6 while never demoting a driven robot is a real ranking
property, not a sort artefact wearing one.

1 775 s over 80 runs.

---

## 5. The positive control — this instrument CAN report a failure

**A passing check is information only if failure was reachable.** G1 passes
everywhere, so the pass is worth nothing until some reachable configuration
breaches. The lever is the **radio**, deliberately: it degrades the cell's
ability to carry the command without touching the instrument, the bound, or
the scoring. Changing the payload or the bound would prove the scorer's
arithmetic works, not that the experiment can detect a real failure.

N=16, cap 2, one seed, `snr_db` swept:

| SNR (dB) | DL delivered (Mbps) | commands (of 200) | worst p98 (ms) | worst gap (ms) | gaps ≥ 200 | **part 1** | **part 2** |
|---|---|---|---|---|---|---|---|
| 20.0 | 15.8–17.1 | 200 | 1.50–6.00 | 53–57 | 0 | PASS | PASS |
| 10.0 | 5.6–6.3 | 200 | 2.50–7.75 | 53–58 | 0 | PASS | PASS |
| 5.0 | 2.5–2.8 | 200 | 2.75–10.00 | 55–61 | 0 | PASS | PASS |
| **0.0** | 0.71–0.91 | **185** | 23.75–31.25 | **698.8** | **2** | **PASS** | **FAIL** |
| **−3.0** | 0.18–0.20 | **46–49** | 96.25–98.00 | **2 935** | **14** | **FAIL** | **FAIL** |
| −6.0 | 0.00 | **0** | 56.25 | 1.2 | 0 | **FAIL** | **FAIL** |

**9 of 18 points fail. The instrument has dynamic range in both criteria,
and they fail at different thresholds.**

### 5.1 The two criteria come apart exactly where Step 0 predicted

**At 0 dB, part 1 PASSES on every arm while part 2 FAILS on every arm.**
p98 sits at 23.75–31.25 ms — comfortably inside a 95 ms bound — while
**15 of 200 commands never arrive** and the robot goes **698.8 ms** without
one. The percentile stays green *because* the missing commands left the
sample.

**This is the failure mode Step 0 (a) named, measured rather than argued.**
A G1 row reporting only p98 would have called this cell responsive. In
operator terms it is a robot that did not lurch — it stopped answering for
seven tenths of a second.

### 5.2 And a second instance, sharper, at the bottom of the sweep

**At −6 dB the worst-flow p98 reads 56.25 ms — a comfortable pass — for a
pair of robots one of which received ZERO commands.** The other delivered
enough to supply a percentile, and a worst-of-two maximum reported *that*.

This is why G1's scorer treats **fewer than two completions as a FAILURE,
not an exclusion**, where `sim/scorecard.py`'s M01 and M03 exclude such a
flow from their worst contests. Both dispositions are right for a
worst-of-fleet statistic and wrong for an instrument: excluding the silent
robot is how a total outage scores as the best possible value. The rule was
written from the argument in Step 0; **this run is the measurement that the
argument was about something real.**

### 5.3 What the control does NOT license

It says the *scoring* can detect a failure. It does not say the failure is
reachable by load — every point in §3's grid and §6's extension is at the
base 20 dB, where the carrier is what it is. **The two questions are
separate and are answered separately.**

---

## 6. The extension probe — the range was pushed until it either broke or stopped meaning anything

Nothing in §3's grid breaks, so the range was extended, which is the
procedure `sim/scenarios/g12.py::RAMP` registers for exactly this case:
extend until a class breaches, and if nothing does, report that as the
answer rather than as a pass.

One seed, cap 2, `n_ues` to **64** and `committed_mult` to **16.0**:

| | PF | Reservation | TwoTier |
|---|---|---|---|
| worst p98 over 30 points | **12.75 ms** | **3.00 ms** | **3.00 ms** |
| worst max | 15.75 ms | 4.50 ms | 4.50 ms |
| worst gap | 62.5 ms | 54.5 ms | 54.5 ms |
| commands delivered | 200/200 everywhere | 200/200 | 200/200 |

**0 failing points of 30.** At N=64 that is **5.3× PF's admissible fleet and
10.7× Reservation's**; at ×16 committed it is eight times the top of G12's
own ramp. **Every other guarantee has failed long before any of these
points** — G10's contract clause fails at N=8 on Reservation — so the range
was extended past the point where the cell is a cell at all, and G1's
downlink clause still does not bend.

**Why, structurally, and this is the deployment answer rather than a
scheduler one.** DSUUU at μ=2 offers a downlink transmission opportunity
every **1.25 ms** against a **95 ms** budget — 76 of them. A drive command is
**100 bytes**, and the whole command stream is **32 kbps against a downlink
that delivers 14–18 Mbps**: about **0.2 % of one per-mille** of the
capacity. For the clause to breach, a 100-byte packet would have to be
deferred through ~76 consecutive downlink opportunities while occupying
essentially none of them.

**So the binding constraint on G1 is the TDD pattern's opportunity spacing,
not contention** — and 1.25 ms against 95 ms is not close.

---

## 7. p99.9 and max — the pass that was SUPPOSED to separate them, and did not

**At the grid's 10 s horizon a driven robot delivers 200 commands, so the
99.9th-percentile INDEX IS THE MAXIMUM.** Reporting both from the grid would
be two names for one number, so a separate pass ran **200,000 slots (50 s,
1,000 commands per robot)**.

**It did not fix it, and the correction below is the point of this section.**
1,000 is exactly the boundary: read §7a for the pass that actually separates
them.

36 runs, 3 seeds × 2 driven robots per cell — **6,000 delivered commands per
cell** — at N=6 (sub-experiment B's fleet) and N=12 (PF's boundary, the
largest any arm admits):

| N | cap | arm | commands | p98 | p99 | **p99.9** | **max** | worst gap | gaps ≥ 200 |
|---|---|---|---|---|---|---|---|---|---|
| 6 | 4 | PF | 5 999 | 1.50 | 3.00 | **4.50** | 4.50 | 100.0 | 0 |
| 6 | 4 | Reservation | 6 000 | 1.50 | 3.00 | **4.50** | 4.50 | 54.5 | 0 |
| 6 | 4 | TwoTier | 5 999 | 1.50 | 3.00 | **4.50** | 4.50 | 100.0 | 0 |
| 6 | 2 | PF | 5 999 | 1.75 | 3.00 | **4.50** | 4.50 | 100.0 | 0 |
| 6 | 2 | Reservation | 6 000 | 1.75 | 3.00 | **4.50** | 4.50 | 54.5 | 0 |
| 6 | 2 | TwoTier | 5 999 | 1.75 | 3.00 | **4.50** | 4.50 | 100.0 | 0 |
| 12 | 4 | PF | 5 999 | 1.75 | 3.00 | **4.75** | 4.75 | 100.0 | 0 |
| 12 | 4 | Reservation | 5 999 | 1.50 | 3.00 | **4.50** | 4.50 | 100.0 | 0 |
| 12 | 4 | TwoTier | 6 000 | 1.50 | 3.00 | **4.50** | 4.50 | 54.5 | 0 |
| 12 | 2 | **PF** | 5 998 | **3.75** | **4.00** | **5.25** | 5.25 | 102.5 | 0 |
| 12 | 2 | Reservation | 6 000 | 2.75 | 3.00 | **4.50** | 4.50 | 54.5 | 0 |
| 12 | 2 | TwoTier | 6 000 | 1.75 | 3.00 | **4.50** | 4.50 | 54.5 | 0 |

**The tail is 4.50–5.25 ms — 18–21× inside the 95 ms bound — and zero gaps
reach 200 ms in 71,992 delivered commands.**

**CORRECTION, and it is the same discipline this document applies
everywhere else.** I first wrote that p99.9 equalling the max was *"a
property of the distribution rather than of the sample size"*. **It is
neither — it is the percentile-index convention.** `message_latency_percentiles_ms`
uses `k = min(len - 1, int(len * p))`, so at any n ≤ 1000 the 99.9th index IS
the last index:

| n | p99.9 index | max index | samples above p99.9 |
|---|---|---|---|
| 200 (the grid) | 199 | 199 | **0 — same value** |
| 1 000 (this pass, per flow) | 999 | 999 | **0 — same value** |
| 1 001 | 999 | 1 000 | 1 |
| 5 000 | 4 994 | 4 999 | 5 |

**The percentiles above are computed PER FLOW**, and a flow delivers 1,000
commands here — exactly the boundary. So this pass did not make p99.9 a
percentile either; the claim that it did was wrong, and §7a re-runs it at a
horizon where the two separate.

**The figures in the table stand** — they are correct maxima over 6,000
delivered commands per cell, and *"max ≤ 5.25 ms"* is the stronger statement
anyway. Only the label was wrong.

**PF at N=12 on the narrow carrier is the worst cell on every column**, which
is §4.2's fleet-size effect showing up again in the tail. 2 746 s over 36
runs.

---

## 7a. p99.9, re-run where it separates from the max

**5,000 commands per driven robot** (1,000,000 slots, 250 s), N=6, 3 seeds,
both caps — **30,000 delivered commands per cell**, so the 99.9th index has
5 samples above it and is a percentile in its own right:

| N | cap | arm | commands | p98 | p99 | **p99.9** | **max** | worst gap | gaps ≥ 200 |
|---|---|---|---|---|---|---|---|---|---|
| 6 | 4 | PF | 29 998 | 1.50 | 3.00 | **4.50** | 4.50 | 101.5 | **0** |
| 6 | 4 | Reservation | 29 997 | 1.50 | 3.00 | **4.50** | **5.00** | 100.0 | **0** |
| 6 | 4 | TwoTier | 29 992 | 1.50 | 3.00 | **4.50** | 4.50 | 100.0 | **0** |
| 6 | 2 | PF | 29 996 | 1.50 | 3.00 | **4.50** | **4.75** | 103.0 | **0** |
| 6 | 2 | Reservation | 29 998 | 1.75 | 3.00 | **4.50** | **5.75** | 100.0 | **0** |
| 6 | 2 | TwoTier | 29 996 | 1.75 | 3.00 | **4.50** | 4.75 | 100.0 | **0** |

**p99.9 = 4.50 ms on every arm at both caps — 21× inside the 95 ms bound —
and the max separates from it for the first time (4.50 to 5.75 ms).** The two
columns now carry different numbers, which is the check that the re-run did
what it was for.

**Zero gaps reach 200 ms in 179,977 delivered commands.** The worst gap is
100–103 ms on every arm: one missed command, the same single-loss signature
as the grid.

**And the arms are indistinguishable here**, unlike §4.2's fleet-size sweep —
N=6 is inside every arm's admissible fleet, which is exactly why
sub-experiment B fixes there. 4 293 s over 18 runs.


## 8. Runtimes

| | |
|---|---|
| **campaign wall clock** | **1 033 s (17.2 min)**, 16 workers |
| total CPU across runs | **16 420 s (4.56 h)** |
| runs | 960 |
| **mean per run** | **17.10 s** |
| parallel speed-up | **15.90× on 16 workers** |

**Per arm**, 320 runs each:

| arm | total CPU | mean/run | max/run | relative |
|---|---|---|---|---|
| PF | 3 738 s | **11.68 s** | 55.1 s | 1.00× |
| Reservation | 4 953 s | **15.48 s** | 50.3 s | **1.33×** |
| TwoTier | 7 729 s | **24.15 s** | 64.9 s | **2.07×** |

**TwoTier costs 2.07× PF, holding this campaign's own pattern of every prior
one.** Reservation's 1.33× is the narrower gap the two QoS arms usually show
against each other.

**Other passes in this experiment:**

| pass | runs | CPU |
|---|---|---|
| G10 boundary re-measurement | 270 | 2 669 s |
| extension probe (§5) | 30 | ~2 800 s |
| positive control (§4) | 18 | ~900 s |
| tie-break control (§4.5) | 80 | 1 775 s |
| long-horizon p99.9 pass (§7) | 36 | 2 746 s |
| **the grid** | **960** | **16 420 s** |
| **total** | **1 412 runs** | **~28 900 s CPU (8.0 h)** |

---

## 9. Deployment consequence, in an operator's terms

**Driving a robot feels immediate, and stays immediate as the floor fills
up.** A drive command lands within **1.5 to 9 milliseconds** against a 95 ms
budget, on every scheduler, at every fleet size and load measured — and at
fleet sizes well past the point the cell stops meeting its other guarantees.

**Three things an operator can act on:**

1. **Fleet size is not a teleop risk.** On the two QoS arms, command latency
   is *flat* from 4 robots to 24 — adding robots does not make driving less
   responsive. On PF it rises, 3.0 → 9.0 ms on the narrow carrier, and still
   never approaches the bound. **Whatever bounds the fleet, it is not the
   drive path** — G10's contract clause fails at 6 to 12 robots while G1 is
   still 10× inside its bound at 24.
2. **Working the robots harder changes nothing.** Six-fold offered load moves
   the command latency by one 0.25 ms slot on every arm.
3. **The thing to watch is missed commands, not slow ones.** The gap
   criterion is 1.9× inside its bound where the latency criterion is 10.6×
   inside its. At a 20 Hz cadence the 200 ms bound is three consecutive
   losses; **37 of 960 runs lost a single command and none lost two in a
   row.** **Under a genuinely bad radio the two come apart** — §5's 0 dB
   point is responsive by the latency measure and silent for 699 ms.

**What this does NOT say.** It is not evidence that the drive path is safe on
a degraded radio: §5 breaks both criteria at 0 dB and −3 dB. The clause is
robust to *load and fleet size* on this carrier, which is what GT-1.1 asks,
and is bounded by *link quality*, which it does not.

---

## 10. The carrier caveat, stated once

**Cap 2 is this carrier's faithful derivation** — `min(55 // (4 × 6), 8) = 2`
at 55 PRB. **Cap 4 is the deployment's value**, derived the same way from its
own 106 PRB. **Neither is the deployment's system**: this carrier is 55 PRB
against the deployment's 106, so cap 4 is the deployment's cap on half its
bandwidth. Both are run in full and reported separately.

---

## 11. Corpus, suite, and what this campaign changed in the code

**Two fields were added to the record**: `delay_p999_ms` and `delay_max_ms`
(`sim/messages.py` → `sim/driver.py` → `sim/run_record.py`). GT-1.1 asks for
p99.9 and max as *reported* figures; computing them privately inside one
runner would leave the next guarantee that needs a tail to build the same
hook again.

**The corpus was re-baselined, and the re-baseline is SHAPE-ONLY — provable
rather than asserted.** `--check` before capture:

| | |
|---|---|
| diff lines | **912** |
| of which `MISSING in baseline` (a new key) | **912** |
| **of which a number that moved** | **0** |
| distinct new keys | `delay_p999_ms`, `delay_max_ms` |

456 flow-records × 2 keys = 912. **Not one existing value changed**, which is
what the project's own rule asks for: re-baseline when a change is *intended*
to move the numbers, and say which moved and why. Here the intent was to
*add* numbers, and none moved.

**A second, independent check on the same claim:** G10's boundary was
re-measured on the new code (AST stamp `0ef6fa56f0878872` →
`cd84ef3b7ba88103`) and is **identical in all 27 cells** to the 2026-09-08
measurement on the old code. A shape-only addition should do exactly that,
and the corpus diff alone would not have shown it.

**`scripts/verify_claims.py --check`: 15 as expected, 0 not as expected**,
including seven new claims registered for this campaign — four on G1's own
two criteria and three on G10's re-measured boundary.

**Also added:** `sim/scenarios/g1.py`, `scripts/g1_stress.py`,
`sim/tests/test_g1_scenario.py` (14 tests), one test in
`sim/tests/test_messages.py`, and three cases plus a coverage mapping in
`sim/tests/test_flow_key_collision_sweep.py`. Full itemisation with
consumers, what becomes live, and what it duplicates:
`docs/g1-step0-2026-09-09.md` §1–2.

---

---

## 12. Process notes worth carrying

- **My own spawn probe had no `__main__` guard** and re-entered its own pool,
  respawning workers in a loop for six minutes. Found by `ps`-ing the worker
  PIDs when the elapsed times all read 00:00 — not by the empty output file,
  which looked identical to a slow run. The observation channel again.
- **`pgrep -f g1_stress` matched the shell running the check**, so an
  `until ! pgrep …` guard deadlocked on itself and the campaign never
  launched — the self-match half of CLAUDE.md's `pgrep` warning, reproduced
  by accident.
- **The hook-identity check reported every arm as differing, including PF.**
  A null control (hook off, twice) also "differed", which is what exposed it:
  the digest was hashing two live object handles whose `repr()` carries a
  memory address. **A check that fails on the control is failing on the
  instrument.**
- **Regenerating the artefact from the ledger reset its `_wall_s` to 0.0**,
  which reads as a measurement of nothing. Fixed at the runner —
  `_wall_s_this_invocation`, `_ran_this_invocation` and `_cpu_s_total` are
  now separate, and the campaign's cost survives a resume.
- **A strict `>` where the data sits exactly on the threshold.** The first
  version of §3b.2's table counted runs with a worst gap `> 100 ms` and found
  **7**; 25 runs sit at exactly 100.0 ms, so the real count of runs that lost a
  command is **37**. The fix was to stop thresholding in milliseconds at all
  and count in **command periods** — a 50 ms cadence makes 2 periods the
  physically meaningful line, and it falls at 90 ms where no data sits. **A
  threshold placed on a quantised value's own level is a coin flip;** put it in
  the gap between levels, in the units the mechanism works in.
- **I claimed a percentile I had not established was one.** The 50 s pass was
  built to make p99.9 a real percentile and reported as having done so. It had
  not: the index convention is `min(n-1, int(n·p))`, so at any n ≤ 1000 the
  99.9th index IS the maximum, and a flow delivers exactly 1,000 there.
  **Caught by asking of my own figure the question this project asks of every
  check — could it have come out differently?** A p99.9 that is arithmetically
  pinned to the max cannot. §7a is the re-run at a horizon where it separates,
  and the shape generalises: **a percentile is only a percentile above
  `1/(1-p)` samples, and the campaign that quotes one owes that arithmetic.**
- **The budget was extrapolated from the FULL population before any flag
  narrowed it** — 16 axis points × 3 arms × 10 seeds × 2 caps = 960, derived,
  never the truncated one-seed list the costing run actually executed.
  Estimate 18 min at 16 workers; actual **17.2 min**.
