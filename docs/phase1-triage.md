# Phase 1 triage — 67 filed findings, 58 distinct defects

67 findings from 14 auditors. 9 are duplicate filings of the same defect
across areas, leaving **58 distinct**. 55 of 201 verification agents
returned before the session limit; they refuted 13.

Buckets per the stated rule. `[V]` = verified by hand already.
`[R]` = refuted by a verification lens that did run.

## BLOCKS PHASE 2 — 27 distinct: **25 verified by hand, 2 open, 8 FIXED**

Status as of the fix pass. `V` = verified by hand. `F` = verified AND fixed.
`—` = still unverified, and Phase 2's numbers carry that caveat.

| # | defect | file | verified |
|---|---|---|---|
| 26 | `priority_level` never set; every flow ties at 100 | `sim/fleet.py`, `sim/parametric.py` | **F** |
| 34 | window sink retains every window; negates commit 2 eviction | `g11_campaign.py:98` | **F** |
| 63 | C1's G3 conjunct pinned FAIL by scripted teleop silence | `g11_score.py:33` | **F** |
| 2/64 | resumed campaign publishes only this invocation's runs | `g11_campaign.py:385` | **F** |
| 3/67 | abandonment timeout ~90 h vs ~5.7 h makespan | `g11_campaign.py:340` | **F** |
| 44 | M09 scores a starved flow as perfectly fair | `scorecard.py:783` | **F** (M22 added beside it; M09 unedited) |
| 43/61 | M01/M15 unrestricted worst-flow contest | `scorecard.py:202,209` | **V** |
| 59 | M20 drops M03's run-derived cadence caveat | `scorecard.py:390` | **F** |
| 30 | `assert_schedule_fired` checks 2 of 4, at non-zero | `g11.py:206` | **V** |
| 32 | `scripted_windows` emitted, read by nothing | `g11_campaign.py:383` | **V** — moot for C1: the fix reads `active_windows`, not `scripted_windows` |
| 22 | M03's cadence caveat fires on GENUINE liveness failures | `scorecard.py:334` | — |
| 58 | M14 measures source cadence, 0.000 on 60/60 duty rows | `scorecard.py:453` | **V** |
| 60 | M21 reads green through a source-gated outage | `scorecard.py:1077` | **V** |
| 39 | M15 max over every flow; panel says command/control | `scorecard.py:822` | **V** |
| 40 | M16 flow pair hardcoded; KeyError swallowed on stage 4/5 | `wp9_sweep.py:393` | **V** |
| 25/36/51 | caveats/notes reach no persisted artefact | `regime_sweep.py:191` | **V** |
| 31/45/65 | G11 + M09 consumers never apply the protected restriction | `g11_campaign.py:113` | **V** |
| 46 | per-window drain drops boundary-straddling messages | `g11_campaign.py:111` | **V** |
| 66 | C1 implements 5 of 9 pass conditions; G1's bound wrong | `g11_score.py:31` | **V** |
| 35 | G11 persists no panel metric or record; M14 unavailable | `g11_campaign.py:119` | **V** |
| 48 | G4 drops entire starved UEs (TwoTier 59 of 80 cells) | `g4_postsilence.py:124` | **V** |
| 50 | G4's "CONFOUND-FREE" comparison pools 5QI 9 | `g4_postsilence.py:225` | **V** |
| 27 | G12's 5QI-9 aggressor collides with fleet 5QI-9 | `g12.py:263` | **V** — only `drone_heavy` collides; `mixed` does not |
| 18 | handshake bypasses arrival accounting; ratio 129:1 | `driver.py:720` | — |
| 20 | M18/19/21 medians over silently self-selected seeds | `g9_campaign.py:200` | **V** |
| 13 | E3 keyed on arm alone, pooling cells | `g12_score.py:240` | **V** |
| 4 | starvation trip kills our own workers on a loop | `g11_campaign.py:214` | **V** |

## HIGH PRIOR — 19 distinct, verify after the blocking bucket

1 [R] resume key omits horizon (corrected to minor) · 5/9 [R] wp9_sweep cell
marked complete before durability · 7 [R] `evaluate_axis` no cell filter
(corrupts committed gate verdicts) · 10 [R] wp9_sweep has no memory guard ·
11 [R] E4 median pools three arms · 12 %-of-ceiling denominator includes the
flood · 15 [R] no assert that a scored cell has the clause-4 flow ·
16/37 [R] g9 asserts fired not completed (already in CLAUDE.md) · 28 bg
aggressor forces `lcg=6` · 38 six metrics give a false "predates WP7" reason ·
41 G2's recorded next step moves the blocker the wrong way · 47 PF tie-break
contamination wider than documented · 49 part_c's cadence claim falsified by
its own column · 53–57 `analyse_stage3/5` (null-cell pooling, vacuous stop
condition, breaking-N carry-forward, empty-selection defaults, nested subsets)
· 62 M21 counts drops only

## DEFER — 9 distinct

6 [R] dropped-axis record · 8 [R] stage-3 tally (stage 3 unrun) · 14 [R]
`CONTRACT_FRACTION` literal · 17 [R] joiner-exclusion tautology · 19 [R]
fade-depth guard reads the wrong field (test-only) · 29 `mix` axis dormant ·
33 `fixed_windows()` dormant · 42 8.58 vs 8.61 · 52 `transient_check.py`
broken (not on the Phase 2 path)

## WRITE-BACK GAP — 3, confirmed by hand, not previously reported

21 `regime-map:194` labels the aggressor-excluded +0.0010 as protected-fleet
(correct: −0.0270) · 23 `wp9-plan:4845` heading still says "on both
statistics" · 24 `wp9-plan:6266` still says the verdict "IS currently a
property of declaration order"

**My earlier report that the write-backs were complete was wrong.** I checked
that the corrected values were present and that the deck agreed; I did not
check for old values still *labelled* as protected-fleet in other sections.


---

## Fix-pass outcome (2026-09-03)

**8 of the 27 blockers are fixed**, each with its own binding check:
`priority_level` derivation, the window sink, the abandonment timeout, the
resume subset, C1's scripted-silence FAIL, M20's dropped caveat, M22 for
G8's second conjunct, and the panel test's restated count.

**2 of the 27 remain unverified** — #22 (does M03's cadence caveat also fire
on a genuine liveness failure?) and #18 (handshake messages bypassing arrival
accounting, `delivery_ratio` 129:1). Both need a run rather than a read.
**Phase 2's numbers carry that caveat explicitly.**

**17 verified but NOT fixed.** They are real and they reach Phase 2's
numbers, but each is a scoring-population or instrument change of its own,
and bundling them would defeat the per-commit attribution. The largest
cluster is one shape: **a metric whose population is every flow while the
guarantee is about a subset** (#39 M15, #43/61 M01/M15, #31/45/65 M09
consumers, #48/#50 G4, #25/36/51 caveats not persisted). G6 already solved
this once, with M20. Nothing else adopted it.

---

## The two open blockers — both VERIFIED, 2026-09-03

**#22 — M03's cadence caveat suppresses GENUINE liveness failures.** Three
fixtures with the SAME 2 s outage, differing only in what the flow was doing
around it:

| case | max gap | median | caveat | outcome |
|---|---|---|---|---|
| A healthy 100 ms source + one real 2 s outage | 2000 | 100 | no | scored ✓ |
| B slow 1 s source + same outage | 2000 | 1000 | yes | suppressed ✓ (the intended case) |
| **C degraded 100 → 600 ms + same outage** | **2000** | **600** | **yes** | **suppressed ✗** |

The predicate is `median_gap > t_live/4`. It cannot distinguish *"this source
is slow by configuration"* from *"the network degraded this flow until its
median got large"* — both look identical to a statistic computed from
delivery timestamps alone. **So it silences the breach exactly when the flow
is worst**, on the metric G3 binds to, with the text *"do not score it
against that bound"*.

**The fix needs the flow's CONFIGURED cadence**, which `FlowRecord` does not
carry — only `FlowConfig.traffic_params["period_ms"]` has it. Adding it to
the record is a `RunRecord` schema change and therefore **`--check` BINDS**,
unlike every other fix in this pass. Scoped, not done here.

**#18 — the join handshake bypasses arrival accounting.** Confirmed by
reading and then measured. `sim/driver.py:254-255` — the normal traffic path
increments **both** `metrics.record_arrival()` and `per_flow_arrived`.
`:397` — the UL handshake request increments `per_flow_arrived` **only**.
`:720-723` — the DL response enqueues with **neither**. Deliveries are
counted normally either way.

Measured on `gt61_warm_rejoin(seed=1, n_neighbours=3, horizon_slots=30_000)`,
PF — the configuration is stated because the filed claim said 129:1 and this
is a different cell:

```
flow            qfi   arrived  delivered     ratio
ue1_qfi70        70         1        641     641.00
ue1_qfi71        71         1        641     641.00
```

**641:1.** Every other flow in the run sits at 1.00 or below. So
`delivery_ratio` is meaningless for the handshake pair and **any
byte-weighted statistic over the joiner is unsound** — which is exactly the
population G9 exists to measure.

### #18 FIXED — and #22 explicitly blocks G3 until it lands

**#18.** Both handshake sites now credit `metrics.record_arrival()` beside
`per_flow_arrived`. Measured on the same cell as the defect:

```
              before                          after
ue1_qfi70     arrived 1  delivered 641        arrived 641  delivered 641   ratio 1.00
ue1_qfi71     arrived 1  delivered 641        arrived 641  delivered 641   ratio 1.00
```

**Every other flow byte-for-byte identical** — 22500 / 3628856 / 15000 /
46871326 / 42871821 unchanged — which was registered as prediction 2 in
`prediction-journal.md` P5 and is what "movement confined to runs with join
events" means in practice.

Pinned by `sim/tests/test_handshake_arrival_accounting.py`, and the invariant
is stated over **every** flow rather than the two handshake 5QIs, because a
test naming only those could not catch the next enqueue site that delivers
without recording an arrival. It also asserts the handshake actually fired,
so the invariant cannot pass vacuously.

**#22 BLOCKS G3'S NUMBER, and this is a plan statement, not a caveat.**

The cadence caveat currently silences a real breach on **M03/M20 — the
metric G3 binds to** — whenever a flow has been degraded badly enough that
its median gap crosses `t_live/4`. Case C above is exactly that: healthy at
100 ms, collapsed to 600 ms, a real 2 s outage, and the reading suppressed
with *"do not score it against that bound"*.

**So G3 cannot be scored honestly until #22 lands.** A G3 verdict computed
today is silent precisely on the flows that failed worst, and reports the
remainder as a pass. That is not a confidence interval or a qualifier — it is
a selection effect that removes failures from the numerator.

**#22 is held deliberately, and it is the one commit in this pass that
legitimately re-baselines the corpus.** The fix needs the flow's CONFIGURED
cadence to distinguish "slow by design" from "degraded by the network";
`FlowRecord` does not carry it, only `FlowConfig.traffic_params`. Adding it
is a `RunRecord` schema change, so **`--check` will bind AND move** — unlike
every other fix in this pass, where a moved corpus would have signalled a
second defect. That deserves its own registered prediction and its own
commit, not to be slipped in beside a document pass.

---

## HIGH-PRIOR bucket — verified by hand, 2026-09-03

Verified by reading and probing, not by agents. **Status is stated per
finding, including the ones I could not settle from a read** — an unresolved
finding recorded as unresolved is worth more than one promoted on a guess.

### CONFIRMED (6)

**#49 — `wp9_part_c.py`'s "the caveat does NOT fire at duty 0.5" is false,
and it is #22 in real data.** Measured over the committed
`sweeps/wp9/part_c_rows.csv` (720 rows): at duty 0.5 the cadence predicate
fires on **4 of 44 breaches** (Reservation 3, TwoTier 1):

| arm | max gap | median | configured period |
|---|---|---|---|
| TwoTier | 963.25 | 596.63 | 200 ms |
| Reservation | 2815.00 | 602.25 | 200 ms |
| Reservation | 2041.25 | 551.25 | 200 ms |
| Reservation | 2063.75 | 525.00 | 200 ms |

Medians ~2.7× the configured period — degraded by the network, not slow by
design — with real 1–2.8 s breaches suppressed. **This is #22's case C
occurring in a published dataset**, and it also shows the earlier correction
(defects-log #8, "cadence exclusion said duty ≤ 0.5; arithmetic says 0.1")
over-corrected: the replacement claim is wrong in the other direction.

**#47 — PF's tie-break is declaration order, and it reaches M01/M15.**
`sim/baselines/pf.py` sorts `scored` by the PF metric alone under Python's
STABLE sort, and `scored` is built from `ue_flows.items()` — insertion order,
i.e. flow declaration order. Since M01/M15 report the WORST flow, persistent
starvation of a fixed UE subset lands directly in them. The plan scopes this
contamination to M09 only; that scoping is too narrow.

**#54 — stage-3's Q2 null control returns PASS over zero comparisons.** With
no matching rows, `pick()` returns empty dicts, `compared` stays 0,
`problems` stays empty, and the function returns `True`. Latent: stage 3 died
at cell 51/52 and has no artefacts — but a died-partway run is exactly the
input shape it would next see.

**#55 — E3 and E4 are fed the breaking-N the same file documents as firing on
noise.** `for comp, v in e2.items(): n = v["breaking_n"] ... e3_h6_split(w, comp, n)`.
The post-hoc paired-CI correction is computed, printed, and never consumed.

**#56 — `c4_pre_window` returns "identical" on an empty selection.** An empty
metric yields `{"n": 0}`, which has no `separated` key, so `any(...)` is
False and `branch` reads "identical" — indistinguishable from a measured
negative result, in a pre-registered control.

**#28 — the `bg` excursion is not single-axis.** The aggressor is 5QI 8
(`lcg_for_5qi(8) = 5`) but is forced to `lcg=6` at `sim/parametric.py:298`,
`g12.py:263` and `g9.py:163` — and `lcg_for_5qi(9) = 6`, the per-UE
best-effort filler's LCG. So `bg=True` adds a flow AND creates a shared LCG
on that UE, in a grid whose whole discipline is one axis at a time.

**#38 — 10 "predates" reasons, 2 flag checks.** Only two methods consult
`record.message_ledger_windowed`; the rest can emit "record predates WP7" for
a record produced by today's driver, misattributing a scoring-configuration
choice to a stale record — the exact distinction the flag was added to make.

### REFUTED (1 additional, on mechanism)

**#7 — `evaluate_axis` does filter to a cell.** `carries_axis()` exists
specifically to kill the bug the finding describes, and its docstring names
it: the `None`-base contamination that selected 1,710 of 1,770 rows. That
defect is already fixed; the finding re-reports it as live. (The reachability
lens had refuted it separately.) A residual question — whether a CORE-PLANE
axis still mixes other axes' levels within a cell — is unresolved and gates
nothing, since stage 1's gate is a completed selection Phase 2 does not
re-run.

### PREVIOUSLY REFUTED BY THE VERIFICATION PASS (11)

#1, #5/9, #6, #8, #10, #11, #15, #16/37, #17, #19 — refuted on mechanism,
reachability or novelty by the 55 verdicts that returned before the session
limit. Not re-litigated.

### UNRESOLVED FROM A READ (4)

**#12** (%-of-ceiling denominator including the 50 Mbps flood), **#41** (G2's
recorded next step moving the blocker the wrong way), **#53** (C4 pooling
structurally-zero null cells), **#57** (E4 ranking nested subsets), **#62**
(M21 counting drops only). Each needs the run's data rather than the source
to settle. **None gates Phase 2**: #12 and #41 are framing claims about
already-published G12/G2 text, and #53/#57/#62 concern stage-5 analysis and
M21's secondary reading. Carried into the document pass, where #12 and #41
are corrections to prose rather than code.
