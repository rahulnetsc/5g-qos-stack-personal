# Phase 1 audit — findings I verified myself (2026-09-03)

Working notes. The full audit (14 areas, three-lens adversarial verification)
is separate; this file is only the items I probed or read directly, so the
evidence is first-hand.

## Baseline

- `uv run pytest sim/tests -q` — **940 passed** in 250.85 s.
- `uv run python scripts/regression_corpus.py --check` — **clean**, no drift
  beyond `rel_tol=1e-06`.
- Nothing was running on the machine when this started; no soak in flight.

## The write-backs are DONE, in both directions

All four corrections and §2.1's roll-up are present in the source docs **and**
in `deck/artpark-guarantee-deck.html`, and they agree:

| correction | doc site | deck site |
|---|---|---|
| §28.1 protected-fleet mislabel (+0.0000 / −0.0104 / −0.0270) | `wp9-plan.md:4853-4899`, regime map G6 row | present, with the aggressor-excluded row kept only as narrative |
| G6's interval claim (+29.35 % [+4.81, +56.18], INCONCLUSIVE) | `wp9-plan.md:4774`, regime map:446/481/559 | present |
| G12's causal overclaim (restored to §35.13's registered wording) | regime map:487 | present — "not established as a scheduler property" |
| G4's forbidden 500 ms comparison | `sim/scorecard.py:335-341` | present |
| §2.1 roll-up | `regime_map_rollup.py --check` **exits 0** | present |

**G4's caveat is genuinely machine-generated, not prose** — `sim/scorecard.py`
derives it from the winning flow's own median gap, so it fires for any slow
flow from any producer.

Two residual risks, both about the artefact rather than the numbers:

1. `deck/artpark-guarantee-deck.html` is **untracked**. The corrected client
   deck exists only as an unversioned file with no generator.
2. `oai-branches/IA-P5G Guarantee Simulator.html` is a **stale browser
   snapshot** of an earlier deck (Sep 2 12:29 against the deck's 17:00). It
   predates the G6 section entirely — it carries neither the old values nor
   the new ones.

## BLOCKER — G11's C1 is a constant FAIL on the scenario's own scripted silence

**Measured**, not reasoned. One real 60 s window of the real soak
(`build_g11_scenario(seed=0, n_ues=4, horizon_slots=240_000)`, PF,
`cqi_delay_slots=8`, `record_timeseries=True`, `timeseries_resolution="second"`,
`window_slots=240000`), scored through the campaign's own
`windowed_metrics` path:

| conjunct | all flows | scripted-silence flows excluded |
|---|---|---|
| G1 `M01w` p98 ≤ 100 ms | 14.25 PASS | 14.25 PASS |
| **G3 `M03w` ≤ 500 ms** | **8049.999 FAIL** (`ue1_qfi82`) | **114.0 PASS** (`ue3_qfi1`) |
| G5 `M05w` ≥ 0.99 | 0.99945 PASS | 0.99945 PASS |
| G5 `M06w` ≤ 67 ms | 12.50 PASS | 12.50 PASS |
| G8 `M09w` ≥ 0.90 | 0.99976 PASS | 0.99978 PASS |

8,050 ms is exactly `TeleopDuty(period_s=20.0, on_s=12.0)`'s **8-second
off-period**. `ue1_qfi82` is the teleop command flow the scenario itself
silences (`sim/scenarios/g11.py:143`).

**It recurs in every window by construction, not by chance.** Teleop off
intervals are (12,20), (32,40), (52,60), (72,80) … — one every 20 s, so every
60 s window contains exactly three. Over a 30-minute soak that is **30 of 30
windows**, every arm, every seed.

### Why it was not caught

`scripts/wp9_window.py::_m03w` (line 323) computes the windowed liveness gap
with **no cadence caveat**, unlike `Scorecard._m03_liveness_gap_distribution`,
which derives one from the flow's own median gap and says *"do not score it
against that bound"*. `scripts/g11_score.py:33` then scores
`("G3", "M03w", "value", "<=", 500.0)` over **all** flows with no exclusion.

`sim/scenarios/g11.py::scripted_windows()` — the partition that would supply
the exclusion, and whose docstring says it is *"declared once, used by both"*
E1 and E5 — is computed and written into the campaign JSON at
`scripts/g11_campaign.py:383-384` and **never read by the scorer**. The
project's own T7 shape: persisted, and unconsumed.

### What it does to the plan's registered expectations

`docs/wp9-g11-plan.md` E1 partitions windows into QUIESCENT (no scripted
event) and EVENT (**firmware, STOP, a pause boundary**). Teleop-off is not on
that list, but `scripted_windows()` returns it as `teleop_off`. Both readings
break:

- **teleop-off counts as an event** → every window is an event window →
  **zero quiescent windows** → E1's and E5's population is empty.
- **teleop-off does not count** → **21 of 21 quiescent windows fail,
  uniformly across index** → E1's fourth row, whose registered meaning is
  *"not a soak finding at all: a base-cell failure a 5 s run would also
  show."* It would **not** show at 5 s — the first off-period starts at
  t=12 s. So E1's map returns a meaning that is factually false, while E5's
  map ("does it reproduce at 5 s?" → no) reads the same data as a
  **genuinely horizon-dependent failure** and obligates a worktree-
  instrumented per-slot direct-cause trace of a scripted duty cycle.

E2 registers *"G5 (M05) is the binding conjunct; G1, G3 and G8 pass in the
same windows."* Measured: **M05w passes at 0.99945 and G3/M03w is the one
that fails.**

### The plan had the right gate and it was never run

`docs/wp9-g11-plan.md` §10 commit **9** is *"Re-run the pre-flight (§3) with
the real scenario and the real windowed instruments — **Go/no-go on the
campaign**."* `git log` has commits 1–8 and no commit 9; commit 10 is the
campaign. The gate costs **23 seconds** at one window on one arm, and it
returns **no-go**.

## MAJOR — M20 silently drops M03's run-derived cadence caveat

`sim/scorecard.py:390-393`: `protected_fleet_liveness_gap` delegates to
`_m03_liveness_gap_distribution` and then builds a **fresh** `MetricResult`
from `res.value` / `res.status` / `res.note`, never copying `res.caveats`.

Probed with one protected 5QI 1 flow at a 1,000 ms cadence and no aggressor
at all — same flow, same value, same median gap:

```
M03: caveats(1) -> CADENCE, NOT LIVENESS: ... do not score it against that bound.
M20: caveats(1) -> A MAX over UEs. ...            <- the panel caveat only
```

`Scorecard.score()` prepends the panel's registered caveats correctly
(`sim/scorecard.py:162-163`), so the loss is entirely in M20's own
constructor. **M20 is the metric G6's verdict binds to.** Not documented
anywhere.

## MAJOR — C2 cannot be scored at all, and this is not a seed-count issue

`scripts/g11_campaign.py::run_one`'s sink collects only `windowed_metrics`
rows; no per-window crumb rate and no floor-fire rate are collected anywhere.
`scripts/g11_score.py:144-150` therefore passes `None`/`None`/`None` into
`drift_verdict` with a reason. Defects-log **#16**, still open.

Consequence for the plan: trimming G11 to 3 seeds costs C3/C4/C5, as
expected — but **C2 does not survive either**, and for an unrelated reason.
It was never wired in. Commit 7 built the detector; commit 8 did not collect
its inputs.

## MINOR (T5) — `assert_schedule_fired` asserts non-zero, not counts

`sim/scenarios/g11.py:206-249`. The docstring says *"assert the expected
COUNT, not merely non-zero"* and cites G9 §34.5 for it. The body computes
`want` = `{teleop_on_windows: 90, waypoint_pauses: 6, firmware_windows: 1,
stop_bursts: 1}` at the real horizon and **never compares any of them to an
observed count**. The only assertions are `bytes_arrived > 0` and
`bytes_delivered > 0` on the STOP flow and `bytes_arrived > 0` on firmware —
non-zero checks on two of the four scripted ingredients. Teleop windows and
waypoint pauses are not checked at all.

## The cost model, measured — and the stale line in the same file

From `sweeps/wp9/g11_summary.txt`, `record_timeseries=True` at
`timeseries_resolution="second"`, N=4:

| arm | s per M-slot | MiB per M-slot | at 7.2 M slots |
|---|---|---|---|
| PF | 208.4 | 6,776 | 25.0 min · 47.7 GB |
| Reservation | 312.4 | 6,774 | 37.5 min · 47.7 GB |
| TwoTier | 624.3 | 7,027 | 74.9 min · 49.5 GB |

Measured parallel efficiency: W=8 → 87 %, **W=16 → 77 % (12.39×)**,
W=24 → 56 %, W=32 → 45 %.

**The same file still prints `ts=1 W=16: … 2.15 h`.** That LPT table is a
CPU-only model with no memory term — at ~48 GB per run, W=16 needs ~768 GB
against 30 GB of machine. Defects-log **#13** corrected 16 → 8 workers and
**#15** corrected 8 → 2. Budgeting Phase 4 from that line repeats the
"a measurement carries its configuration" error the invariant was written
for.

Note also that with `record_timeseries=False` the cost is still **3,360 MiB
per M-slot** — so timeseries is roughly half the retention and the other half
is unattributed (defects-log #15 records this as unknown, and #12 is struck
through: `hol_delay_samples_s` is ~12 %, not the 49 % first quoted).

## BLOCKER — `priority_level` is never set by any WP9/G9/G11/G12 builder: every flow ties at 100

Found by an auditor, **verified by me directly and empirically**. This is the
largest finding in the pass.

`scheduler/flow.py:172` declares `priority_level: int = 100`. Unlike `lcg`
(and `pdb_ms`), it is **not** self-resolved from 5QI in `__post_init__` —
`priority_for_5qi()` exists at `flow.py:57` and is used by
`sim/config_loader.py:90-91`, but **`sim/fleet.py`, `sim/parametric.py`,
`sim/scenarios/g9.py`, `g11.py` and `g12.py` contain zero occurrences of the
string `priority_level`.**

Measured:

```
sweep_scenario(n_ues=8)      flows=32  priority histogram={100: 32}
      would-be from 5QI: {1: 20, 2: 40, 82: 19, 9: 90}
g11 soak N=4                 flows=18  priority histogram={100: 18}
      would-be from 5QI: {1: 20, 2: 40, 82: 19, 9: 90, 8: 80, 85: 21}
```

**And the contrast that makes it a defect rather than a design choice** —
the three published-study scenarios, which the regression corpus is built
from, DO carry real 5QI-derived priorities:

```
factory_robots   flows=24  priority histogram={40: 10, 19: 10, 90: 3, 80: 1}
sensor_dense     flows=30  priority histogram={20: 30}
latency_bound    flows=12  priority histogram={20: 8, 90: 4}
```

So Studies 1–3 run on a spread and **every WP9 number — stage 1/2/4/5, G9,
G10, G11, G12 — runs on a constant.**

### The three consumers, and what each does at 100

| site | rule | at `priority_level = 100` |
|---|---|---|
| `scheduler/tier1.py:100-104` | `if 0 < p <= _DELAY_PRIO_THRESH(20): _DELAY_WEIGHT else _PF_WEIGHT` | **`_PF_WEIGHT` for every flow — Tier-1's Delay class is never selected on any WP9 run** |
| `scheduler/two_tier.py:1654-1658` | `0.35 + 0.65 × (1 − (p−1)/89)`, clamped to `[0.35, 1.0]` | `1 − 99/89 = −0.1124` → weight `0.2769` → **clamped to the floor 0.35 for every flow**; the priority term contributes nothing to UL urgency ranking |
| `sim/ue_lcp.py:95` | `sorted(ue_flows, key=lambda f: f.priority_level)` | a constant key under a **stable** sort → **the UE's uplink LCP split is decided by flow declaration order** |

That third row is a concrete, verified mechanism for the declaration-order
sensitivity G12 spent a registered control on (§35.13). It does not by itself
establish that it is *the* mechanism behind G12's `[2,4]` inversion — that is
still untested — but the confound now has a named cause rather than a
standing candidate.

### Why nothing caught it

`regression_corpus.py::_cases()` builds all 20 cases from
`scripts/scheduler_study.py`'s three scenarios, which set priorities
correctly. **`--check` is structurally incapable of seeing this**: the
population it reads and the builders that are wrong do not intersect. The
same could-have-failed test the project already applies to checks.

And `docs/oai-port-map.md:220` (row 41) states *"The two coincide on every
scenario in this repo today (5QI-derived priorities line up with
`flow_class`)"*. That was true when written — before
`sim/parametric.py`/`sim/fleet.py` existed — and is false for every WP9
scenario now. A forward-looking note falsified by a later builder.

## Confirmed: M09 scores a starved flow as perfectly fair

`sim/scorecard.py:783`: `ratio = (delivered / arrived) if arrived > 0 else 1.0`.
A flow that delivers nothing during a second in which nothing arrived scores
**1.0**. M09's own note says *"computed over all flows in the record with
timeseries data — pass a same-role flow subset upstream if that's what the
guarantee needs"*, and **no consumer in the repo passes one.** G8's second
conjunct (zero starvation epochs ≥ 1 s) has no instrument at all.

## G11 commit 9 (the go/no-go pre-flight), executed — all three arms

`docs/wp9-g11-plan.md` §10 commit 9 is *"Re-run the pre-flight (§3) with the
real scenario and the real windowed instruments — **Go/no-go on the
campaign**."* `git log` has commits 1–8 and no commit 9; commit 10 is the
campaign. Running it costs about four minutes:

```
teleop off-periods begin at t=12.0s, recur every 20.0s
  -> a 5 s run cannot contain one; a 60 s window contains 3.

===== horizon 20000 slots = 5 s (the plan's premise)
  PF           C1 PASS
  Reservation  C1 PASS
  TwoTier      C1 PASS
===== horizon 240000 slots = 60 s (one real soak window)
  PF           C1 FAIL   <- G3/M03w=8050.0 (flow ue1_qfi82)
  Reservation  C1 FAIL   <- G3/M03w=8050.0 (flow ue1_qfi82)
  TwoTier      C1 FAIL   <- G3/M03w=8050.0 (flow ue1_qfi82)
```

**The premise holds at 5 s and fails at 60 s, and the failing value is
identical to one decimal place across three different schedulers.** Three
arms cannot agree to a tenth of a millisecond on a quantity that depends on
scheduling. It is the scenario's own teleop duty cycle.

**Verdict: NO-GO on the G11 campaign as specified.** Running it overnight
would produce a guaranteed C1 FAIL in all 30 windows on all arms and all
seeds, collapse C4 to "satisfied by construction", refute E2's registered
binding conjunct for the wrong reason, and — under E5's outcome map —
obligate a worktree-instrumented per-slot direct-cause trace of a scripted
duty cycle.

The fix is small and design-consistent: give `_m03w` the same run-derived
cadence caveat `Scorecard._m03_liveness_gap_distribution` already computes,
and have `g11_score.py` skip a caveated conjunct instead of scoring it.
`scripted_windows()` is already written into the campaign JSON and only
needs a consumer.

## G1's "core plane" evidence is an unrestricted worst-flow contest, won by the best-effort filler

Measured on the published artefact, `sweeps/wp9/stage2/stage2_rows.csv`
(7,560 rows), by the 5QI of the flow each metric actually reported:

| metric | 5QI 9 (BE filler) | 5QI 2 (video) | 5QI 1 (telemetry) |
|---|---|---|---|
| `M01.flow` | **6,457 (85.4 %)** | 1,097 | **6 (0.08 %)** |
| `M15.flow` | 2,524 (33.4 %) | 3,360 | 1,676 |

`Scorecard._m01` (`sim/scorecard.py:209-217`) takes an unrestricted max over
`record.flows.values()`; `_m15` does the same. 5QI 9 is the per-UE
best-effort filler and a member of `Scorecard.NON_PROTECTED_5QI = {8, 9}`.
M15's panel row registers it as *"on a command/control flow"*.

`docs/wp9-regime-map.md`:441 and :476 cite **"M01 p98 / M15 across the core
plane"** as G1's evidence. Across that plane, the flow being reported is the
load axis's own filler in 85 % of runs, and the 5QI 1 telemetry bearer G1 is
actually about wins M01's contest in **6 of 7,560**.

### I checked whether this inverts §28.4's headline. It does not.

The obvious next inference — that TwoTier's *"M01 p98 ≤ 100 ms base cell:
PF 0/40, Reservation 0/40, TwoTier 8/40 FAIL"* is also filler-driven — is
**wrong, and I am recording that I checked.** In `stage6_g6_n40.csv` 185 of
240 rows exceed 100 ms and every one is won by 5QI 9 (173) or 5QI 8 (12),
with PF and Reservation breaching in 80/80 rows — which looks like an
inversion until you read the script.

`scripts/g6_conjunction_table.py:13-16` states outright that **both clauses
are evaluated on the PROTECTED FLEET (M20's flow restriction)** and reads
`stage6_g6_n40_records.jsonl`, recomputing rather than reading the CSV
column. §28.4's counts are correct as published.

**So the finding is narrower and sharper than "G1's numbers are wrong":** the
protected-fleet restriction was built for G6 and is applied only there. G6's
analysis restricts; **G1's and G8's cited core-plane evidence reads the
unrestricted columns.** One guarantee got the fix; the two that cite the same
metrics did not.

## BLOCKERS for Phase 4's unattended run — `scripts/g11_campaign.py`, all three verified by direct read

**1. The abandonment timeout cannot fire inside the run it protects.**
`:340` — `if time.time() - t0 > per_task_timeout_s * len(submitted)`. At the
real horizon `per_task_timeout_s = max(1800, 7_200_000/4000*4 + 3600) =
10,800 s`, and with 30 submitted tasks the threshold is
**10,800 × 30 = 324,000 s ≈ 90 hours** against a campaign makespan of ~5.7 h.
The loop `time.sleep(5)`s forever. This is the mitigation for the
2026-09-03 audit's Tier-1 finding #1 (*"a run that neither completes nor
reports"*), and **it is inoperative at the horizon it was written for** —
which matters because the aggregate guard has already killed a worker on a
real-horizon probe. A killed worker now hangs the parent for ~90 h; the
campaign JSON at `:376` is never written. Compare against `len(remaining)`,
or use a per-task deadline.

**2. The resume key omits the horizon and the fleet size.** `:279` builds
`done` from `(r["arm"], r["seed"], r["permutation"])` while the task tuple is
`(arm, seed, horizon, n_ues, permutation)`. The banked record **already
contains** `horizon_slots` and `n_ues` (`run_one` returns both) — they are
simply not in the key. So a short `--smoke` or exploratory run at a different
horizon or N banks entries the production campaign then **skips**. One-line
fix.

**3. A resumed campaign publishes only that invocation's runs.** `:290`
`results: list[dict] = []` is never seeded from `done_path`, and `:376`
writes `"runs": results`. A resume that completes the remaining 10 of 30 runs
writes a well-formed JSON with `n_runs: 10`, `n_expected: 30`, **no failures,
exit 0** — and `g11_score.py` reads `data["runs"]` with no check on
`n_runs == n_expected`. Because `ARMS_LPT` is longest-processing-time-first
(`TwoTier, Reservation, PF`), the published subset is arm-skewed either way.

**Phase 4's own verification step would have caught #3** — *"interrupt a
short grid, resume, compare against a clean single pass"* — but not #1,
because a hung parent produces no artefact to compare.

**And `g9_campaign.py` / `g12_campaign.py` have no resume at all**: each
writes its output with a single `Path(args.out).write_text(...)` after every
case finishes, so a kill at hour 9 loses everything. Neither has a memory
guard. `wp9_sweep.py` has per-cell resume but flushes only `rows.jsonl`
— the completeness ledger — before writing `records.jsonl` and
`online_rows.jsonl`, which are never flushed, so a kill in that window marks
a cell COMPLETE with its records missing and the resume never re-runs it.

---

# Corrections to the above, from adversarial verification and further measurement

## The resume finding was filed too strongly — corrected

The verification pass split three ways on it and the refuting lens is right
about the mechanism. **Horizon mixing is structurally impossible**:
`.runs.jsonl` is read for its KEY only (`:276-279`; `r["rows"]` is never
touched) and the output's `runs` list is built solely from this invocation's
`results` (`:288`, `:330`, `:385`). A short-horizon record has exactly one
possible effect — a run is ABSENT — and no path into a scored number.

So, restated:

- **Resume key omits `horizon`/`n_ues` — MINOR (operator ergonomics).** The
  hazard is that `--smoke` (`:249`, 400,000 slots) shares the production
  `--out` default (`:246`), so a smoke run banks records the real campaign
  then skips. One-line fix: widen the key, or derive `--out` from the mode.
  `--time-cell` is **not** part of this — it runs at the full `a.horizon`,
  so its banked records are legitimate.
- **Banked runs never re-enter `results` — BLOCKER, and it is broader than
  the smoke case.** *Any* resume drops the already-completed runs from the
  scored artefact, including horizon-correct ones. The campaign exits 0
  (only `failures` gates the exit code) having written `n_runs: 21`,
  `n_expected: 30`; `g11_score.py:154` reports the pair and never asserts
  it. With `ARMS_LPT` TwoTier-first, a truncated resume removes whole arms
  first and C1/C3/C4 are then computed per-arm over a self-selected subset
  of a within-seed paired design.
- **The abandonment timeout (`:340`) — BLOCKER, unchanged.** ~90 h against a
  ~5.7 h makespan.

## The memory budget: every published figure is from a different configuration

`sweeps/wp9/g11_probes/g11_probe_session1.py` — the battery behind the
21.8 GB / 48 GB / "~6–9 GB" numbers — runs **`sweep_scenario` at N=8**, and
calls `run(...)` with **no `window_sink` and no `window_slots`**. The
campaign runs `build_g11_scenario` at **N=4, windowed, with eviction and a
retaining sink**. These are different runs, not near-neighbours — CLAUDE.md's
own invariant. **There is no measurement of the campaign's actual
configuration at the real horizon.**

Measured here, on the actual campaign path (PF, N=4, `record_timeseries=True`,
`timeseries_resolution="second"`, `window_slots=240000`), one mode per
process because `ru_maxrss` is a high-water mark:

| horizon | windows | completions | sink DROPS | sink KEEPS | retention |
|---|---|---|---|---|---|
| 240,000 | 1 | 1,047,766 | 468.9 MiB | 470.7 MiB | **1.8 MiB** |
| 480,000 | 2 | 2,095,774 | 519.8 MiB | 868.0 MiB | **348.2 MiB** |

At one window the sink fires once at the end and costs nothing; at two, one
window's completions are held while the next accumulates. That is ~348 bytes
per retained completion.

**Two-point extrapolation to 7,200,000 slots (30 windows) — stated as an
extrapolation, not a measurement:**

- driver side (`drop`): +50.9 MiB per +240,000 slots → ≈ 212 MiB/M-slot with
  a ~418 MiB intercept → **≈ 1.9 GB**. Nearly flat: commit 2's eviction is
  working.
- sink side: 29 retained windows × ~1.05 M completions × ~348 B →
  **≈ 10.6 GB**.

**So ~85 % of the campaign's per-run memory is `run_one`'s `pending` dict
(`scripts/g11_campaign.py:97-99`) — which exactly negates the eviction
commit 2 added to bound it.** Fix the sink and a run costs ~2 GB instead of
~12.5 GB, taking the affordable worker count from ~1 to ~10 within a 22 GB
budget. That is the difference between G11 being unrunnable and being cheap.

**Do not quote 48 GB, 24 GB, or "~6–9 GB" for this campaign.** The first two
are extrapolations from an N=8 unwindowed probe; the third is a mid-run
observation from a job that was killed before finishing.

---

# Fixes landed (2026-09-03)

| # | fix | verification |
|---|---|---|
| 1 | `priority_level` derives from the 5QI table via `FlowConfig.__post_init__`, mirroring `lcg` and `pdb_ms` | `--check` **clean and BINDING**; 940/940 pass; every builder histogram non-degenerate. Predictions scored in `prediction-journal.md` P1 — 2 HIT, 1 **MISS** |
| 2 | `run_one` scores the completion-metric family in the window sink and releases the batch; `windowed_metrics` gained a `families` selector | **18/18 rows byte-identical**, peak RSS **877.1 → 556.0 MiB** at 480k slots. Directional scenario-vs-record flow-key guard added, and it fired on its first run |
| 3 | per-task **stall** deadline replaces `timeout × len(submitted)` (~90 h → 3 h); banked runs re-enter `results`; horizon and `n_ues` admitted into the resume filter; a short campaign now exits non-zero | read + syntax; exercised by Phase 2 |
| 3b | `g9_campaign` / `g12_campaign` write durably after every arm (and every cell for g12) | durability only — **full resume deliberately deferred**, ~25 lines each, buys nothing at Phase 2's budget |
| 4 | `_m03w` reports `median_gap_ms`; `g11_score` marks a cadence-blind G3 conjunct UNSCOREABLE and counts it in `conjuncts_unscoreable_cadence` | the bound stays with the scorer, the cadence with the metric — same split as `Scorecard._m03` |
| 5a | `M20` carries `res.caveats` forward | probe: M20 now shows **2** caveats (panel + run-derived cadence), was 1 |
| 5b | **M22 `starvation_epochs`** added — G8's second conjunct, which had no instrument | 6 tests, including the pairing guard (non-zero on a starved flow, zero on a served one) and the activation-gate discriminator |
| — | write-back gaps at `regime-map:194`, `wp9-plan:4845`, `wp9-plan:6266` | corrected in place, each with a note saying what it had said |
| — | memory figures **retracted** (`defects-log` #17) at the regime map, handover and g11-plan | superseded by measurement on the campaign's own path |

**What I did NOT change, deliberately.** M09's `arrived == 0 → 1.0`
convention stays: it is a pre-registered definition, and editing it would
silently re-interpret every historical M09 reading. M22 is an **addition**
beside it, which is the disposition the panel's own rule requires and the one
M20 already used for M03.

**Still unverified from the blocking bucket (2 of 27):** #22 (does M03's
cadence caveat also fire on genuine liveness failures?) and #18 (handshake
messages bypassing arrival accounting, `delivery_ratio` 129:1). Both need a
run rather than a read, and both are folded into Phase 2's checks. **Phase 2
numbers carry that caveat explicitly.**

## Two corrections found by running the fixes' own checks

**Fix 4's first version was wrong, and its verification caught it.** It
mirrored `Scorecard._m03`'s cadence predicate — *is the flow's own median gap
already above the bound* — and the check returned `median_gap = 50.0 ms`
with C1 still FAILing. The teleop flow sends **every 50 ms while on** and is
silent 8 s of every 20 s, so its median is 50 ms and its max is 8,050 ms.

**The median predicate catches a uniformly SLOW source, not a DUTY-CYCLED
one**, and GT-7.1's soak is entirely duty-cycled. That distinction is not
recorded anywhere and `Scorecard._m03` inherits the same blind spot for any
future duty-cycled scenario.

Replaced with the right discriminator: `_m03w` subtracts the source's own
inactive time (`FlowConfig.traffic_params["active_windows"]`) from each gap,
so a liveness gap measures *how long the network was silent while the source
was trying to send*. A flow that is duty-cycled **and** genuinely starved
still reports the starved part — which excluding the flow would have hidden.

Verified: **M03w 8049.999 → 114.000 ms, C1 window verdict PASS.** That is the
same value my first probe got by excluding the scripted flows outright, so
the general mechanism and the crude one agree.

**The panel test asserted a count, and it fired on the one operation the
panel permits.** `test_panel_loads_and_has_twenty_metrics` asserted
`len(panel["metrics"]) == 21` — stale by one in its own name — and failed
when M22 was appended. **A count cannot distinguish an addition from a
removal-plus-addition**, which is the thing the append-only rule actually
forbids. Rewritten as a subset check against the ids ever registered: it
fires on a removal and stays quiet on an addition. Fifth instance of the
restated-count rule, second in test code.

## The sink fix, re-verified after `_m03w` changed underneath it

Both fixes touch `scripts/wp9_window.py`, so the row-identity result was
re-measured rather than assumed to still hold:

```
peak RSS  old 877.1 MiB -> new 559.0 MiB
identical 16, changed 2
  0|M03w|all  flow ue1_qfi82 -> ue3_qfi1   value 8049.999 -> 114.000
  1|M03w|all  flow ue1_qfi82 -> ue3_qfi1   value 8049.999 -> 114.250
```

**Two rows changed, both `M03w`, both in the direction the scripted-silence
subtraction predicts, in both windows.** The reporting flow moves off the
duty-cycled teleop stream and onto `ue3_qfi1`, whose 114 ms gap is a real
one. Every other row is byte-identical, so the memory change remains
behaviour-neutral and the only behavioural change in the diff is the one
that was intended — which is what the one-fidelity-change-per-commit rule
exists to make visible.
