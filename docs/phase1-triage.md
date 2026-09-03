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
