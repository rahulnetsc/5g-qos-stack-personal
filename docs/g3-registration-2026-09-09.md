# G3 registration — written before the campaign ran

**2026-09-09.** Predictions, grid and cost registered before any campaign
number existed. Scored in `docs/g3-stress-experiment-2026-09-09.md` §8, hits
and **misses both**, per the standing rule that a prediction exercise cited
only when it is right is not one.

Baseline: suite green, `regression_corpus.py --check` clean,
`verify_claims.py --check` **20 as expected / 0 not**, core AST
`b1ff4cdaea1183cc` (52 files — 51 before `sim/scenarios/g3.py`).

---

## 1. The clause, enumerated from the plan's own text

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` L97, the G3 catalogue row:

> Max telemetry inter-arrival gap at MEC ≤ ▷ T_live/4 (500 ms); zero gaps
> ≥ T_live over the full campaign; p98 ≤ PDB.

**Three parts, and I read GT-2's whole family plus §5's KPI definitions to
confirm there is nothing else.** There is, in two places, and both are
sub-test criteria rather than fourth clause parts:

| where | the extra criterion | disposition |
|---|---|---|
| GT-2.1 | *"**and** B's SLOs unaffected (ε per G6)"* | GT-2.1 deferred, see §3; the runner computes B's absolute gap/p98/M05 anyway |
| GT-2.2 | *"bg receives residual only"*; *"verify `[P5G-UL-FLOOR]` arming under the right-sized profile and count fires"* | both scored — §4 |
| GT-2.3 | *"first-packet one-way p99 ≤ 300 ms per bucket; time-to-steady ≤ 1 s"* | **these are G4's KPIs, not G3's.** Out of scope and stated rather than quietly folded in |
| §5 | the gap distribution's headline is *"max gap and count of gaps exceeding {T_live/4, T_live/2, T_live}"* | the T_live/2 count is reported beside the two scored ones |
| §5 | *"state the assumed split (▷ RAN budget = PDB − 5 ms) in every report"* | part 3's bound is therefore **95 ms**, derived from 5QI 1's own 100 ms PDB |

**Two things about the parts that the current scorer gets wrong, and both are
about what the number ranges over rather than how it is computed.**

**Part 2 is CAMPAIGN-wide and is scored per-run today.**
`scripts/guarantee_scorecard.py`'s row tests `G3_M03_gaps_over_tlive_prot == 0`
on each row, so a 9-of-10 result reads as *"90 %"* while the clause is failed
by **one gap anywhere in the campaign**. The distinction is not cosmetic: an
AND over rows is the right verdict and a rate is the wrong one. Scored here as
one verdict over every gap, with §5.3's rule of three giving the demonstrable
bound when the count is zero — which is why the denominator (gaps scored) is
carried beside it.

**Part 3 is numerically G1's own statistic under a different guarantee's
name.** The scorecard row reads `G1_M01_p98_prot`. Said plainly here so one
number does not silently carry two verdicts.

## 2. The population — and part 3's is wrong today, measured

The clause says **telemetry**. `G3_M03_prot_ms` is M03's worst-gap contest
over the protected fleet, which is camera, lidar, DL command *and* telemetry.
Checked on the artefact the published row came from
(`sweeps/m6-2026-09-07/plain/core.json`, 30 rows):

| clause part | statistic | winner is telemetry |
|---|---|---|
| part 1 (max gap) | `G3_M03_prot_ms` | **30 of 30** |
| part 3 (p98) | `G1_M01_p98_prot` | **22 of 30** — the other 8 are the 5QI-2 **camera**, a 150 ms-PDB video bearer scored against telemetry's 95 |

So part 1's population happens to be right on this workload (telemetry has the
slowest cadence, so it wins a gap contest naturally) and **part 3's is not**.
Both are scored on the telemetry flow here, derived from the scenario
(`sim/scenarios/g3.py::telemetry_flow_keys`), never named.

**And a flow with fewer than two completions FAILS all three parts.** M03
excludes such a flow from its worst-gap contest, which is right for a
worst-of-fleet statistic and exactly wrong for an instrument: for G3 the
telemetry going silent *is* the failure. Same disposition G1 took.

## 3. Scope, and what is deferred with its reason

Cut from the original three-scenario design on 2026-09-09, before running:

- **GT-2.1 (own camera vs own heartbeat) — DEFERRED.** The plan's own text
  says a GT-2.1 failure is fixed UE-side (*"the fix is UE-side
  `prioritisedBitRate` configuration, not the gNB scheduler"*), so it
  discriminates the **arms** weakly, and the arms are what this evaluation
  exists to compare. **Its mechanism is not lost**: the `ctl` pass runs the
  same PBR lever on GT-2.2's cell, where the neighbour's flood makes grants
  scarce — the condition that makes an intra-UE split bite. The builder
  (`build_gt21_scenario`) and the over-drive axis are landed and tested;
  `--parts C` runs them.
- **The committed-load axis — DEFERRED.** Fleet size is the axis that ranges
  across G10's re-measured boundaries and is therefore comparable with G1's
  and G9's cells. `--parts B` runs load if fleet size shows nothing.
- **Cap 2 — DEFERRED unless a verdict is close.** Cap 4 is the deployment's
  value and the one to quote. For G2 the cap was the dominant term, so this is
  a judgement about G3's own margins and not a general rule.

## 4. The grid, and its cost, sized before launching

| pass | runs | slots | what only it answers |
|---|---|---|---|
| **GT-2.2 fleet axis** `n_ues ∈ {4,6,7,8,10,12,14,16,24}`, cap 4, 3 arms × 10 seeds | 270 | 10.8M | the P0 clause, with every arm's G10 boundary strictly inside the range |
| **GT-2.3 buckets** `{1, 5, 60} s`, N=6, 3 arms × 10 seeds | 90 | 31.0M | the SR path each side of the floor's 2 s arming horizon |
| **long-horizon flatness** 200,000 slots, N=6 | 30 | 6.0M | whether a max-gap verdict survives 5× the window |
| **configuration controls** telemetry PBR off; bucket duration 5 ms | 60 | 2.4M | is the finding the bearer's, and does it survive the one unprovenanced constant |
| **SNR positive control** 7 levels, 2 seeds | 36 | 1.4M | is a failure reachable at all |
| **total** | **486** | **51.6M** (3.58 simulated hours) | |

**Projected 4.86 h CPU → 27 min wall at 14 workers.** The per-arm cost is
measured, not guessed — one run per (arm, cell) at N=6 and N=24 before the
grid was sized (§5) — and the projection is computed over the **full task
list before any flag narrows it**, which is the half of the budgeting defect
that fails silently.

### 4.1 The horizons, and what each supports

Slot 0.25 ms (μ=2); telemetry 10 Hz, so messages per robot is `seconds × 10`.

| pass | slots | seconds | messages / robot |
|---|---|---|---|
| fleet axis, controls, SNR | 40 000 | 10.0 | **100** |
| GT-2.3, 1 s bucket | 92 000 | 23.0 | 200 (3 silences) |
| GT-2.3, 5 s bucket | 140 000 | 35.0 | 200 (3 silences) |
| GT-2.3, 60 s bucket | 800 000 | 200.0 | 200 (3 silences) |
| long-horizon flatness | 200 000 | 50.0 | **500** |

**p98 over 100 messages is a percentile and p99 would not be**: the index
convention is `min(n−1, int(n·p))`, so a percentile needs `n > 1/(1−p)` — 50
for p98, 100 for p99, 1 000 for p99.9. **Only p98 is quoted from the grid.**

**The gap criterion is a MAXIMUM, so what matters is whether the window can
CONTAIN the gap it forbids.** 10 s holds five 2 s gaps arithmetically; the SNR
control is what demonstrates one rather than leaving it argued.

**GT-2.3 accumulates 3 silences per run × 10 seeds = 30 per (arm, bucket),
90 per bucket over the three arms.** The plan asks 100 cycles/bucket; a run
cannot hold 100 sixty-second pauses, so the achieved count is derived and
reported, never restated as the plan's number.

**Against GT-2.2's specified 10 min × 3 arms × 5 runs = 150 min**: the fleet
axis alone is 45 min of simulated cell time and the whole campaign is 3.58 h,
so the **aggregate exceeds the specification**; the **per-run duration is one
sixtieth of it**, and the longest run is 200 s. This is the shape that caught
G11, so it is stated rather than left to be found.

## 5. The cost calibration, with its configuration

One run per (arm, cell), N=6 and N=24, cap 4, RA + SRB, seed 1, on this
machine 2026-09-09. **Quoted with its configuration because a cost quoted
outside one is a statement about a different system.**

| cell | PF | Reservation | TwoTier |
|---|---|---|---|
| GT-2.2 N=6, 40 000 slots | 7.11 s | 9.63 s | 18.90 s |
| GT-2.2 N=24, 40 000 slots | 27.13 s | 39.86 s | 51.99 s |
| GT-2.3 N=6, 92 000 slots | 17.02 s | 22.72 s | 41.31 s |

Cost is very close to linear in slots and roughly linear in fleet size
(×3.34 from N=6 to N=24). TwoTier is **2.66× PF**, consistent with G2's
measured 2.19×.

---

## 6. THE PREDICTIONS

### 6.1 The one put to me, scored as stated

> *"The uplink mechanisms make this the first guarantee where the QoS arms do
> not both hold, and GT-2.3's 60 s bucket is where it shows."*

**First half: I expect it to hold. Second half: I expect it to be WRONG, and
to be wrong for a reason the calibration already shows.**

The calibration ran three cells before any prediction was written, and two of
its nine rows are already failures: **at N=24, Reservation fails all three
parts (worst gap 814.8 ms) and TwoTier fails parts 1 and 3 (754.0 ms, p98
99.5 ms), while PF passes** (114.5 ms, p98 34.75). So the QoS arms already do
not both hold — and **it shows on the FLEET axis, not in GT-2.3**. My
prediction is that the 60 s bucket is *not* where the separation appears,
because the floor's 2 s arming horizon cuts the other way from the intuition:
above it the floor is disarmed for **every** arm equally, so the bucket
removes a two-tier-specific mechanism rather than stressing one.

### 6.2 My own, each with its falsifier

| # | prediction | falsifier |
|---|---|---|
| **P1** | **Part 1 (max gap) is the binding criterion and part 3 (p98) is not**, because `expire()` caps p98 at ~100.25 ms while a discarded message widens the gap without bound. Expect part-1 failures at fleet sizes where part 3 still passes | a cell failing part 3 while passing part 1 |
| **P2** | **The arms separate on the fleet axis, and the boundary order is PF > TwoTier ≥ Reservation** — the same order as G10's admissible fleet (12 / 7 / 6) | any other order, or all three equal |
| **P3** | **G3's part-1 boundary is BELOW G10's admissible fleet on the QoS arms.** G10's boundary is a contract-attainment criterion; a liveness maximum is stricter than a rate average, so telemetry liveness should break first | a boundary at or above 6 (Reservation) / 7 (TwoTier) |
| **P4** | **Part 2 (zero gaps ≥ 2 s) PASSES campaign-wide on every arm at N ≤ 8 and fails at N ≥ 16 on at least one QoS arm.** A 2 s gap is 20 missed telemetry messages in a row, which needs a near-total lock-out, not congestion | a 2 s gap at small N, or none at N=24 |
| **P5** | **GT-2.3's three buckets are INDISTINGUISHABLE on the scored statistic**, because the post-silence gap is one SR round-trip whichever side of the arming horizon the pause sat on. The floor is a rescue for a *stalled* UE, and a UE resuming from a scripted pause has a real BSR to send | a monotone trend across the buckets, or a 60 s failure with 1 s passing |
| **P6** | **The telemetry-PBR control moves the verdict on every arm, and by more than the arm difference does.** This is the sharpest thing I expect: a UE-side configuration change worth more than the choice of scheduler | the control moving one arm only, or by less than the PF↔TwoTier gap |
| **P7** | **The `bsd_ms = 5 ms` control does NOT withdraw the PBR finding** — it should shrink both buckets together, and telemetry's own bucket only has to hold one 300 B message | the finding disappearing at 5 ms |
| **P8** | **The floor fires, and only on TwoTier.** Non-zero fires at every fleet size, rising with N; `None` (no such tier) on PF and Reservation | zero fires on TwoTier at every N |
| **P9** | **The SNR control breaks part 1 before part 3**, the same way G1's control broke its gap criterion while the percentile stayed green — and for the same reason, that losing messages improves a percentile over the ones that arrive | part 3 failing first |

### 6.3 And one I expect to be unanswerable rather than answered

**Whether the cold-start lock-out contributes at all.** RA and SRB are on, so
a UE gets grants during attach, and `sim/bsr.py::seed_attach_bsr` is **off by
default** and stays off here. The lock-out needs a UE whose per-LCG array is
never populated; at N=24 with a flood there are many candidates for that, but
distinguishing "never granted" from "granted and starved" needs the
never-granted counter G10's runner reads, which this campaign does not carry.
**Registered as a gap, so a §8 answer of "not established" is a prediction met
rather than a hole found.**

---

## 7. What was added to the repo, and what it makes live

Per the standing rule, for each addition: who consumes it, what becomes live
that was inert, what it duplicates.

### `sim/scenarios/g3.py` (new)

- **Consumers:** `scripts/g3_stress.py`; `sim/tests/test_g3_scenario.py`
  (25 tests); `sim/tests/test_g3_floor_tally.py`;
  `sim/tests/test_flow_key_collision_sweep.py` (22 new cases, forced by its
  own coverage assertion); `sim/tests/test_workload.py`'s GBR-offered
  invariant, which reaches it through the same `_cases()`.
- **Becomes live that was inert:** **a 5QI-1 telemetry bearer with a GFBR**,
  which no workload in the repo had — and with it the UE-side LCP's
  prioritised round for telemetry (`sim/ue_lcp.py`), which every existing
  scenario left at a zero token bucket. Also `active_windows` on a *telemetry*
  flow with a neighbour flooding, which only `g11.py`'s soak used before.
- **Duplicates:** nothing. It reuses `sim/workload.py::scale_committed_load`
  and `min_bytes_per_period_for_gfbr`, takes its committed-profile shapes from
  `sim/parametric.py`'s factory mix via `g1.py`/`g2.py`, and uses
  `sim/scenarios/schedule_guard.py` rather than growing its own horizon check.
  Fifth guarantee-specific builder beside `g1`, `g2`, `g9`, `g11`, `g12`.
- **Deviation from §2.1, stated:** no lidar. G1's and G2's cells omit it, and a
  third GBR bearer would make G3 incomparable with them *and* move the
  admissible fleet size the axis is ranged against.

### `scripts/g3_stress.py::FloorFireTally`

- **Consumers:** the runner; `sim/tests/test_g3_floor_tally.py`.
- **Becomes observable that was not:** **the UL service-interval floor's
  fires.** CLAUDE.md's unreachable-mechanism audit lists Tier 1.5 as
  unobservable — *"OAI's counters not ported; activation unknowable"*. The
  counter was already there: `floor_fire` is tier 1.5 of two-tier's own UL
  ranking key, and `scheduler/rank_trace.py` records that key verbatim.
- **Duplicates:** nothing, and this is the second attempt. Six counters were
  added to `scheduler/two_tier.py` first and **reverted** — see §7.1.

### 7.1 The scheduler edit that was made and withdrawn, priced

Pure telemetry: six counters, no branch reading them, `regression_corpus.py
--check` moving **zero numbers** (30 shape-only lines over 5 TwoTier records ×
6 keys). It still cost:

| consequence | size |
|---|---|
| corpus re-baseline | shape-only, 30 lines |
| **`verify_claims --check` staleness** | **12 published claims across G1, G2 and G10** |

`scripts/code_state.py` stamps each artefact with the AST hash of its runner's
**transitive import closure**, and every campaign running a TwoTier arm reaches
`two_tier.py` through `g11_campaign._arm`. At *"roughly ten minutes of
re-running each"* (that module's own measured figure) the bookkeeping cost of
six counters was **three campaign re-runs**. The rank stream costs none of it,
and adding `sim/scenarios/g3.py` alone invalidates nothing, because no earlier
runner imports it — confirmed, `20 as expected / 0 not`.

**What is lost by not landing the counters:** the ARMING decomposition
(`has_pending_gbr` passing; `armed`), which is internal state no hook reaches.
It matters only if the fire count comes back zero. A pre-campaign probe with
the counters still in place read `ul_floor_pending_gbr` **131 111 of 192 000**
evaluations and 3 fires per run at N=6, so the gate is reachable on this cell;
the campaign reports fires, and §4 of the result says what they were.

### 7.2 One category guard was widened, not silenced

`sim/tests/test_schedule_guard.py`'s exemption list was module-keyed.
`sim/scenarios/g3.py` is the first module holding **both** a scheduled builder
(GT-2.3's silences, which calls `require_horizon`) and unscheduled ones
(GT-2.1/2.2, steady state), so a module-level exemption would have silently
covered the one builder that most needs the guard. Exemptions are now
per-builder, and the test asserts the scheduled sibling is **not** exempt.

---

## 8. Two things found before the campaign, both measured

**The telemetry bearer's own configuration is worth more than the choice of
scheduler.** N=6, seed 1, cap 4, parametric factory mix, worst telemetry flow:

| arm | PBR 0 (every builder in the repo) | PBR 24 kbps (at the offered rate) | PBR 500 kbps (§2.1's proposal) |
|---|---|---|---|
| PF | p98 22.75 ms | 11.00 | 10.75 |
| Reservation | 23.00 | 19.00 | 17.00 |
| **TwoTier** | **98.50 ms, max gap 313 ms, 94/100 messages** | **51.50, 149 ms, 100/100** | 48.25, 154 ms, 100/100 |

**A PBR at the flow's own offered rate captures the whole benefit of the
plan's 20× larger proposal**, which is what settles the GFBR value: §5's
conformance semantics need offered ≤ GFBR and this repo's own invariant needs
offered ≥ GFBR, so **offered == GFBR is the unique point satisfying both**.

**And the GFBR → PBR coupling is the deployed derivation, not a simulator
convenience.** Files searched: `oai-branches/mac_rrc_dl_handler.c`,
`oai-branches/two-tier/nr_ue_scheduler.c`, all four
`oai-branches/{two-tier,reservation}/gNB_scheduler_*.c`. A DRB's uplink
prioritised bit rate comes from its GFBR and nothing else (`:294-350`, and the
`[IA-P5G FIX]` comment at `:316-343` says so outright); a non-GBR DRB passes
zero (`:296`); the UE skips a zero-bucket channel in round 1
(`nr_ue_scheduler.c:2543-2553`). **And the deployed code records the same
failure mode observed on hardware from the other end of the knob** — a PBR far
above the achievable rate, *"observed as one flow taking ~85 MB while its two
siblings on the same UE got ~10 MB and ~4 bytes"*.

**What could not be established, stated rather than assumed:**
`get_DRB_RLC_BearerConfig` is not in the vendored subset and the full OAI
checkout is **absent from this machine** (checked), so which
`prioritisedBitRate` enum a zero maps to is not readable here. And `bsd_ms`
has no provenance at all: 100 ms is this repo's default, the only bucket
duration in the deployed source is the SRB path's **5 ms**, and 100 ms biases
**toward** the starvation this campaign measures — hence the control.

---

## 9. AMENDMENT, same day, after the first launch was killed — grid re-sized

**Recorded as an amendment rather than an edit**, because §6's predictions were
written before any campaign number existed and must stay as written. Nothing in
§6 is changed by this; only the grid's own dimensions are.

**The first launch was killed at ~4 minutes on MEMORY, not time.** At
`SILENCE_CYCLES = 3` the 60 s bucket is an 800,000-slot run, and 14 of them in
one pool reached **17.0 GB resident with 1.5 GB of machine memory left**, still
climbing at roughly 60 % through — a projected **~56 GB against 31 GB of RAM**.
The cost is `sim/messages.py`'s per-message ledger over a 50 Mbps saturating
uplink flood, ~**2.5 MB of resident set per 1,000 slots per worker**.

**Three things this changes, and one it does not.**

1. **`SILENCE_CYCLES = 1`.** A silence costs its own duration in simulated
   time, so cycles is the only lever on a 60 s bucket. **The buckets keep an
   identical sample size** — one cycle gives two active windows of 5 s, so
   every bucket carries exactly 10 s of active telemetry and 100 messages per
   robot, and the buckets differ *only* in the silence. That is a better
   comparison than three cycles gave, not merely a cheaper one.
2. **The achieved resume count is 10 per (arm, bucket), 30 pooled over arms**,
   against the plan's 100 cycles/bucket. Derived and reported; the shortfall
   is a run, not an argument.
3. **The runner now projects peak memory beside CPU.** That is the check that
   would have caught this before launch, and it is stated at the point of use
   where it can be compared against `free`.

**What it does not change: the buckets still straddle the 2 s arming horizon**,
which is the whole reason for {1, 5, 60}, so P5 remains testable exactly as
registered.

### 9.1 The re-sized grid

| pass | runs | slots each | seconds | messages / robot |
|---|---|---|---|---|
| GT-2.2 fleet axis, `n_ues ∈ {4,6,7,8,10,12,14,16,24}` | 270 | 40 000 | 10.0 | 100 |
| GT-2.3, 1 s bucket | 30 | 44 000 | 11.0 | 100 |
| GT-2.3, 5 s bucket | 30 | 60 000 | 15.0 | 100 |
| GT-2.3, 60 s bucket | 30 | 280 000 | 70.0 | 100 |
| long-horizon flatness | 30 | 200 000 | 50.0 | **500** |
| configuration controls | 60 | 40 000 | 10.0 | 100 |
| SNR positive control | 36 | 40 000 | 10.0 | 100 |
| **total** | **486** | | **2.23 simulated hours** | |

**Projected 3.26 h CPU → 18 min wall at 14 workers; peak 9.6 GB against
23.5 GB available.**

### 9.2 And a finding that is not G3's, recorded where it was found

**`regime_sweep.run_cells` does not watch memory at all.** It carries four
measured lessons about the pool — bit-identity as the acceptance criterion,
`OMP_NUM_THREADS` in the parent, a generator that retains nothing,
longest-first with `chunksize=1` — and an orphan check before launch. It has no
aggregate memory ceiling, and **the one that exists lives inside
`g11_campaign.py`'s own runner**, which is the fix-at-the-site shape CLAUDE.md
records as this project's most expensive recurring habit. A per-process guard
could not have caught this (no single worker approached one); the pool total
is the level the failure occurs at.

**Also reproduced, exactly as the notes describe:** killing the parent left all
fourteen workers alive, orphaned and still allocating. They reparent away and
their argv is the spawn bootstrap, so they cannot be found by script name and
had to be killed by PID. `regime_sweep.check_for_orphans()` then confirmed the
pool was clear before relaunching.

---

## 10. SECOND AMENDMENT — the instrument was corrected mid-campaign

**Recorded as an amendment for the same reason as §9: §6's predictions stay as
written.** The first pass completed (486 runs, 939 s wall) and its own output
was decomposed before any verdict was published. It showed a defect in **this
campaign's scorer**, not in the simulator:

**An inter-arrival maximum cannot see a robot that goes dark and stays dark.**
19 flow-runs had a silence of up to 9.5 s while the scored maximum read
114–342 ms; one delivered **3 of 100** messages and scored 185 ms.

**Two statistics are now published** — part 1 as literally written, and
**part 1s**, the same 500 ms bound over the longest silence the window can
observe (head and tail included). Part 2's count uses the extended set. The
clause is not redefined; the gap between the two is reported as the finding.

**Consequences for this registration:**

- **The grid grew from 486 to 576 runs**, the extra 90 being the SR-path probe
  (`--parts E`, `pause_whole_ue=True`) added for the reason §5.1 of the result
  gives. Projected 4.21 h CPU → 23 min wall; peak memory unchanged at 9.6 GB.
- **The first pass is KEPT** as `sweeps/g3-stress/g3_stress.PRE-SILENCE-FIX.*`,
  because it is the evidence for the finding rather than a superseded artefact.
- **P1's falsifier is unchanged and P1 is already refuted** by the first pass:
  it predicted part 1 binding and part 3 loose; the SNR control fails **part 3
  first** (at 5 dB, with parts 1 and 2 passing). Scored in the result, not here.
