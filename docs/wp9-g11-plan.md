# WP9 G11 — the production-shift soak (GT-7.1 + GT-7.4)

**Status: PLAN ONLY. No code written.** Machine #2 (see §1), first session
on this host, HEAD `c29d6ec`.

G11 is the last unrun guarantee (`docs/wp9-regime-map.md` §2.1) and the
reason for the move to an overnight-capable host. This document settles the
five things the task brief requires it to — the 30-minute horizon's real
cost, memory, resumability, the clause-by-clause statistics, and the
pre-registered expectations — plus four things the work turned up that were
not asked for: **a fifth guarantee clause nobody had scored** (§2.1), **a
forced reinterpretation of what "repeat" means in a deterministic
simulator** (§2.2), **the memory result that makes the bigger machine
irrelevant on its own** (§7.2), and **a self-contradicting count in
`wp9-regime-map.md` §2.1** (§10.1).

**A note on how this document was checked, because it is part of the
result.** Two adversarial review passes were run over it against the repo.
The first found **30 defects in the first draft**, including six arithmetic
errors — one of them a measured data point silently dropped because the
table was hand-built from a `wc -l` count on a JSONL whose last record has
no trailing newline. Every quantitative table is now emitted by
`sweeps/wp9/g11_probes/summarise.py` rather than typed, and the places
where a correction changed a conclusion say so inline rather than quietly.

---

## 0. On-arrival check — STEP 1

| check | expected | measured | verdict |
|---|---|---|---|
| `uv run pytest sim/tests -q` | 879 passed | **879 passed** (131 s) | clean |
| `regression_corpus.py --check` | no drift at `rel_tol=1e-6` | **no drift** (17.8 s) | clean |
| `--check --rel-tol 0 --abs-tol 0` | *not asked for* | **no drift** | **bit-identical** |
| `len(_cases())` vs baseline keys | equal | **20 == 20** | consistent |

**The corpus is bit-identical across hosts, not merely inside tolerance.**
`--check --rel-tol 0 --abs-tol 0` also reports no drift, which is a
stronger portability result than §1.4 asked for and is worth recording as
such: all 20 records reproduce **exactly** on a different machine and a
different `uv` (0.11.15 here vs 0.12.5 there). (The laptop's CPU model is
not recorded in the handover, so this is "a different host", not a stated
cross-vendor claim.) §1.4's contingency — *drift is a portability finding,
not a reason to `--capture`* — did not have to be exercised.

### 0.1 What lived outside git — the honest answer

The mechanical answer is "nothing": the suite and `--check` both pass on a
bare clone, so no code, config, baseline or plan document was needed and
absent. The honest answer has **three gaps** — a transfer gap covering
manifest items 1–3, a partial on item 4, and one item the manifest does not
list at all.

| # | item | expected | found | consequence |
|---|---|---|---|---|
| 1 | `sweeps/wp9/stage1/records.jsonl` | 1.4 G | **absent** | Part A per-flow re-analysis impossible |
| 2 | `sweeps/wp9/stage4/records.jsonl` | 937 M | **absent** | the C5-style bit-identity check against stage 5 is impossible |
| 3 | `sweeps/wp9/stage6_g6_n40_records.jsonl` | 251 M | **absent** | §27–§29's 240 records unavailable |
| 4 | `~/.claude/plans/` | 13 files, 220 K | **4 files, 80 K** | see below |
| 5 | **full OAI checkout** | *not in the manifest* | **absent** | see below |

**Items 1–3 were not copied.** `sweeps/` here is 39 M — clone-only content.
This is a *transfer* gap, not a documentation gap: §1.2 and §1.4 predicted
each file, its size and the exact analysis each one gates. The
documentation discipline worked; the copy step did not happen.

**Item 4 is a partial that reads like a success.** `~/.claude/plans/` exists
and is non-empty, so a cursory check passes. But the four files present are
`wp1`/`wp3`/`wp4`-era (mtimes 19–21 Aug), i.e. this host's own earlier
history — **none of the WP9-era plans travelled, including the stage-5
recovery plans §2 names as the reason to copy the directory at all.** A
non-empty directory is not evidence the right directory arrived; the
manifest's own `ls ~/.claude/plans/ | wc -l # expect 13` check catches it
and is worth keeping.

**Item 5 is the real documentation gap, and it is a gap in the manifest.**
`CLAUDE.md` names `~/Documents/artpark_projects/Oai_Ran_QoS_Supported_MultiDRB`
as the evidence base whenever a constant looks sourceless from the vendored
`oai-branches/` subset — that rule is what settled `nrmac->min_grant_prb`
in Phase 2 reservation commit 4. **It does not exist on this host and it is
not item 5 of §1.4's manifest.** The vendored subset (1.7 M, 17 files) and
`calibration-logs/` (304 K) both travel in the clone, so nothing is blocked
today; but the next constant that looks sourceless has no way to be
resolved here, and the manifest would not have told anyone to bring it.

**Recommended manifest amendment:** add the full OAI checkout as item 5,
with its own "why it cannot be cloned" (it is a separate upstream repo, not
a subdirectory) and an explicit note that it is needed only on demand.

### 0.2 Two smaller observations

- `git remote -v` shows **`origin` only**. §3 records the branch as pushed
  to both `origin` and `upstream` (artpark-hub/5g-qos-stack); `upstream` is
  not configured on this clone. Harmless, but a push intended for upstream
  would silently go to the fork.
- A prior session on this host (`182c2f59`, ~11:42 today) had already run
  two G11 budget batteries before this one. Its outputs survive in
  `sweeps/wp9/g11_probe*.jsonl`; **its probe script survives only because
  the session scratchpad has not been collected yet** — §5.2's exact
  failure mode, recurring. This plan's §10 puts every G11 probe in
  `scripts/`, not a scratchpad.

---

## 1. This machine, measured — STEP 2

**Every timing below was measured here today.** §6.3a's rule (*time the
thing you are actually going to run, or state the number as a lower bound*)
is applied throughout, and every number that is a lower bound says so.

### 1.1 The host

| | laptop (handover §4) | **this machine** |
|---|---|---|
| CPU | 24 cores | **AMD Ryzen 9 9950X — 16 physical / 32 logical** |
| RAM | 30 GB | **30 GB** (≈24 GB available; ~6 GB held by the GUI/VS Code session) |
| disk free | 290 G | **459 G** on `/home` |
| uv / Python | 0.12.5 / 3.12.3 | **0.11.15 / 3.12.3** |

**RAM did not improve.** The handover's own §6.3b names memory, not CPU, as
the binding constraint on worker count — and it is *identical* here, minus
~6 GB permanently held by the desktop session. Any plan that assumed "a
bigger machine" would be wrong about the one resource that binds.

### 1.2 Single-core speed — essentially unchanged

Base cell (`sweep_scenario` N=8, 32 flows, `cqi_delay_slots=8`), horizon
20,000, `record_timeseries=True`, `driver.run` only:

| arm | laptop §6.3a | this machine | ratio |
|---|---|---|---|
| PF | 3.63 s | 3.57 s | 1.02× |
| Reservation | 5.74 s | 5.39 s | 1.06× |
| TwoTier | 10.88 s | 9.88 s | 1.10× |

**The machine is ~1.06× faster per core.** Whatever G11 gains, it does not
gain from single-thread speed.

### 1.3 Parallel efficiency — measured, not inherited

W identical single-threaded cells launched at once; speedup =
`W × t(W=1) / t_wall(W)`. Two per-worker resident footprints.
**All figures recomputed by `sweeps/wp9/g11_probes/summarise.py` from the
raw JSONL, not typed.**

**E1 — horizon 80,000 (~0.53 GiB/worker, `peak_rss_after_run`):**

| W | wall s | speedup | efficiency | throughput (cells/s) |
|---|---|---|---|---|
| 1 | 17.15 | 1.00× | 100 % | 0.0583 |
| 2 | 17.47 | 1.96× | 98 % | 0.1145 |
| 4 | 18.20 | 3.77× | 94 % | 0.2198 |
| 8 | 19.59 | 7.01× | 88 % | 0.4084 |
| 12 | 20.35 | 10.12× | 84 % | 0.5898 |
| **16** | 22.14 | **12.39×** | 77 % | 0.7225 |
| 20 | 28.75 | 11.93× | 60 % | 0.6956 |
| 24 | 30.45 | 13.52× | 56 % | 0.7883 |
| 32 | 37.73 | **14.55×** | 45 % | **0.8480** |

**E2 — horizon 320,000 (~1.9 GiB/worker):**

| W | wall s | speedup | efficiency |
|---|---|---|---|
| 1 | 68.55 | 1.00× | 100 % |
| 2 | 70.61 | 1.94× | 97 % |
| 4 | 73.62 | 3.72× | 93 % |
| 8 | 78.91 | 6.95× | 87 % |
| 10 | 80.26 | **8.54×** | 85 % |

**There is no knee at the physical core count, and an earlier draft of this
section claimed there was.** W=20 *is* absolutely slower than W=16 (11.93×
vs 12.39×), but W=24 and W=32 are both faster again (13.52×, 14.55×), and
in raw throughput **W=32 is the most productive point tested** (0.8480
cells/s, 1.17× W=16). Generalising the single non-monotone point at W=20
into a "knee at 16" was reading a shape from one dip — the second form
rule's failure mode, committed on a nine-level axis where it had no excuse.

**W=16 is still the right operating point for G11, for a different and
better reason: the job list is short.** G11 is 30 long jobs, not thousands
of short ones, so past ~16 workers the extra capacity cannot be filled —
an LPT schedule of the real job list gives an *ideal* makespan of 99.8 min
at W=16 and 74.9 min at both W=24 and W=32 (both bounded by one 74.9 min
TwoTier run), and once de-rated by the measured efficiency at each W the
ordering reverses (§7.3). **Raw throughput favours W=32; the campaign
favours W=16.** Those are different questions and the earlier draft
conflated them.

**Two things this does settle.**

1. **It is not the laptop's 6.75× at 10 workers.** At the *same* 10
   workers and the *same* ~1.9 GiB footprint this machine gives **8.54×
   (85 %)** — **1.27× better, like-for-like.** (Comparing this machine's
   own best point to the laptop's reported point would give a larger
   number, but the laptop was never measured at 16 or 32 workers, so that
   comparison is optimum-vs-point and is not made here.)
2. **Efficiency is insensitive to per-worker RESIDENT SIZE** over the range
   tested — 88 % vs 87 % at W=8 for 0.53 GiB and 1.9 GiB per worker. **This
   does not show that memory bandwidth is not the limiter**, and an earlier
   draft claimed it did: both configurations run the identical simulator
   doing identical per-slot work, so bytes-touched-per-second is
   essentially equal and only *retention* differs. What it licenses is
   narrower and is what §7 needs: **a 3.6× heavier resident footprint costs
   nothing in efficiency, so worker count can be set from capacity alone.**

### 1.4 The soak-horizon battery

30 min of sim at numerology 2 (0.25 ms slots) is **7,200,000 slots** —
360× stage 5's horizon and 360× every horizon in every WP9 campaign to
date. Measured here, `driver.run` only, base cell (N=8, 32 flows),
`cqi_delay_slots=8`. **Every cell below is measured; `—` means not run.**

| arm | ts | 20,000 | 80,000 | 320,000 | 1,280,000 | 2,560,000 |
|---|---|---|---|---|---|---|
| PF | 1 | 3.6 s / 216 MiB | 15.7 / 630 | 65.1 / 2,256 | 265.9 / 8,757 | — |
| Reservation | 1 | 5.4 / 214 | 23.6 / 629 | 96.5 / 2,249 | 398.5 / 8,753 | — |
| TwoTier | 1 | 9.9 / 226 | 45.2 / 655 | — | 795.5 / 9,083 | — |
| PF | 0 | — | — | 57.9 / 1,150 | 235.2 / 4,375 | **477.5 / 8,676** |
| Reservation | 0 | — | — | 88.7 / 1,143 | 360.0 / 4,344 | **734.1 / 8,613** |
| TwoTier | 0 | — | — | 184.4 / 1,191 | 764.8 / 4,518 | **1,520.5 / 8,960** |

**Least-squares affine fits per (arm, ts) series**, and the point count each
rests on — which is not the same for every row, and matters:

| arm | ts | n | run: a + b·h | R² | RSS: a + b·h | R² |
|---|---|---|---|---|---|---|
| PF | 1 | **4** | −1.0 s + 208.4 s/Mslot | 0.99999 | 85.0 MiB + 6,776 MiB/Mslot | 1.00000 |
| Reservation | 1 | **4** | −1.8 + 312.4 | 0.99996 | 82.3 + 6,774 | 1.00000 |
| TwoTier | 1 | **3** | −3.7 + 624.3 | 0.99999 | 89.4 + 7,027 | 1.00000 |
| PF | 0 | **3** | −3.0 + 187.4 | 0.99995 | 74.4 + 3,360 | 1.00000 |
| Reservation | 0 | **3** | −5.5 + 288.3 | 0.99991 | 75.5 + 3,335 | 1.00000 |
| TwoTier | 0 | **3** | −3.5 + 596.1 | 0.99996 | 79.4 + 3,469 | 1.00000 |

**Three corrections an earlier draft got wrong, all in the same direction —
claiming more evidence than exists:**

- **TwoTier ts=1 has three points, not four.** No 320,000-slot ts=1 TwoTier
  run exists; the table above prints `—` for it and the fit says n=3.
- **The ts=0 rows briefly had only n=2, and R² was suppressed for them.** A
  two-point affine fit has zero residual degrees of freedom, so R²=1 by
  construction and carries no information; printing `1.00000` there would
  have been the strongest possible statement of the weakest possible
  evidence. The 2,560,000-slot points have since landed for all three arms
  and every series above now has n≥3 with a real R².
- **One measured point was silently dropped** — TwoTier ts=0 at 1.28 M —
  because the table was built by hand from a `wc -l` count, and the JSONL's
  last record has no trailing newline, so `wc -l` said 8 for a 9-record
  file. The extrapolation for that arm was then taken from 320 k instead.
  **The remedy is the one CLAUDE.md already prescribes for restated
  counts: derive it.** `sweeps/wp9/g11_probes/summarise.py` (which reads
  with `splitlines()`) emits §1.3's efficiency tables, §1.4's
  measured-point and fit tables, §4.1's exponent table, and §7.1/§7.3's
  tables. **It does not yet emit §1.2's, §4.2's, or a handful of derived
  figures in §7.3–§7.4** — and a second adversarial pass found that **every
  remaining numeric error was in exactly those hand-typed figures, and not
  one was in a table the script produced.** Ten errors, cleanly separated
  by provenance; about as direct a demonstration of the derive-it rule as
  this project has recorded. The residual tables should move into the
  script before this plan is executed.

Net of the ~80 MiB interpreter intercept, both curves are **strictly
proportional to horizon**. (A naive ratio-of-ratios reads *sublinear* for
RSS — 2.93× at the 20 k→80 k step — purely because that intercept dominates
at small horizons; the affine fit is the right instrument.)

**The battery is complete**, including a guarded run at the **real**
7,200,000-slot horizon, which the watchdog stopped at 21.8 GiB. §7.5 is
that result, and it is the one number here that settles a choice rather
than informing one.

## 2. What G11 asks — clause by clause, each with its own instrument

`docs/wp9-regime-map.md` §4.1's clause-by-clause default, applied before
anything is built. G11's text (Test Plan §3, GT-7.1, GT-7.4) is **four
clauses in four different currencies**:

| # | clause | source | instrument | exists today? |
|---|---|---|---|---|
| **C1** | every 60 s window of a ≥30 min soak passes G1/G3/G5/G8 | GT-7.1 KPI | per-window M01 p98 + M15 (G1); M03 (G3); M05 + M06 (G5); M09 (G8) | **partly** — `Window`/`windowed_metrics` are general, but only M01w/M02w/M07w/M08w exist |
| **C2** | internals stable — floor-fire rate, `%min_rb` crumb rate, skip-reason counters show **no monotonic drift** | GT-7.1 KPI | a monotone-trend statistic over per-window internal counters | **no** — no trend statistic anywhere, and **no skip-reason counter exists in `sim/` or `scheduler/` at all** (§3.2) |
| **C3** | across repeats, **CoV(p98) ≤ ▷15 %** per instrument flow | GT-7.4 | CoV of worst-flow M01 p98 across **fresh seeds** — see §2.2, this is a reinterpretation | trivial arithmetic, but needs n ≥ 5 |
| **C4** | **identical PASS/FAIL verdicts** across repeats | GT-7.4 | C1's verdict vector compared across **fresh seeds** — §2.2 | needs C1 |
| **C5** | **any bimodality investigated** before the Guarantee Sheet is signed | GT-7.4 | the per-seed p98 *vector*, inspected for clustering — **not** the CoV | **no**, and see below |

### 2.1 C5 was missing from this plan's first draft — and its absence is exactly the §4.1 shape

**GT-7.4's KPI line has three clauses, not two, and the third has no
instrument in common with the other two.**The full line is *"CoV(p98) ≤ 15 % per instrument flow; identical
PASS/FAIL verdicts across repeats; **any bimodality investigated before the
Guarantee Sheet is signed**."* The third is not decorative: **CoV is the one statistic that
cannot see bimodality.** A clean two-mode p98 distribution — half the
seeds at 20 ms, half at 30 ms — sits at CoV ≈ 20 %, and a tighter pair sits
comfortably under 15 % while being the most interesting thing in the run.
So C3's named instrument is *structurally blind* to C5, which is why C5
needs its own instrument (the raw per-seed vector) and its own row.

### 2.2 What "repeat" means here — a forced reinterpretation, not a substitution

**GT-7.4's procedure is *"5–10 repeats of a 10 min GT-7.1 slice, clean
restarts between."*** On hardware a repeat re-runs the same configuration
and the numbers move because the world does.

**In this simulator a literal repeat is degenerate, and §0 proves it.**
`--check --rel-tol 0 --abs-tol 0` reports no drift: a run is a pure
function of `(scenario, seed)` and reproduces **bit-identically** across
hosts. So the literal reading of GT-7.4 gives **CoV(p98) = 0 and identical
verdicts by construction** — an unfalsifiable pass, the J5 shape at the
level of the whole guarantee.

**C3/C4 therefore read "repeat" as "a fresh seed", and that is a
reinterpretation that must travel with every G11 row**, because it changes
what is being claimed:

- the literal clause asks *"does the same run reproduce?"* — in sim,
  answered **yes, exactly, by §0**, at zero cost and with no soak needed;
- the reinterpreted clause asks *"does the guarantee survive a different
  draw of the traffic and channel?"* — a **strictly stronger** question
  than hardware's repeat, and the only one with any content here.

**Both are reported.** §0's bit-identity result *is* C3/C4's literal
answer and it is stated as such; the seeded version is stated as a
different and harder test. Quoting the seeded CoV as "GT-7.4's
repeatability number" without that distinction would compare it against a
hardware figure measuring something else.

### 2.3 A further thing G11 owes, and the panel already binds it — M14

`config/metric_panel.yml` binds **M14 `communication_service_availability`
to `guarantees: ['G11']`**, and both its own note and README §6 say it is
*"the number that actually fills in G11's Guarantee Sheet row."* Its status
is **`ok`**.

**None of C1–C5 uses it.** GT-7.1 and GT-7.4 state G11's *pass criteria*
in windows, CoV and verdict stability; M14 is the *reported* number. Both
are owed, and a G11 that scores four clauses and never emits M14 has left
the panel's own binding unserved — which is exactly §4.1's shape, one step
earlier than usual: **the mismatch here is between the guarantee's pass
criteria and its registered metric**, not between two clauses.

**And M14 as configured is not a CSA measurement.** Its own caveat is
explicit, and the code confirms it: `budget_s = (fr.pdb_ms +
fr.survival_time_ms) / 1000.0` (`sim/scorecard.py:429`), and
`survival_time_ms` is **dormant at 0.0 on every flow** — `grep
'survival_time_ms='` outside tests finds only the `RunRecord` passthrough,
never a scenario setting it. So M14 currently collapses to *"fraction of
gaps within `pdb_ms`"*, with the TS 22.104 survival-time grace period
absent.

**Consequence for G11, registered here rather than discovered later:**
M14 is emitted, and **every G11 row quoting it states `survival_time_ms=0`
inline**, the same way the seed count travels. It is a partial CSA and
naming it a CSA without that qualifier would be the same error shape as
quoting a reduced-seed row without its n.

**§4.1's own prediction, applied to G11.** The clause most likely to go
unscored is *the one whose instrument differs from the guarantee's headline
instrument*. G11's headline instrument is a **threshold pass** (C1, C3, C4
are all "is this statistic inside a bound"). **C2 is a trend statistic** —
a different kind of question entirely, with no existing code and no
existing metric. **C2 is this guarantee's G6-clause-1 / G12-clause-4.** It
is called out here so it cannot be quietly dropped for being the hard one.

---

## 3. The dynamic-range pre-flight — RUN, not assumed

The journal's third form rule, extended to non-deltas by §35: **on the
control alone, ask whether each instrument can move at all.** Applied per
clause, this is where G11 is most exposed, and two of the four already have
a *measured* reason to doubt.

### 3.1 C1 may be pinned at FAIL before the soak starts

`docs/wp9-regime-map.md` §2.1 records G5 as **a measured base-cell
failure on both QoS-aware arms: median worst-flow PDU-set completeness
0.0000** (`docs/wp9-plan.md` §29), *with no aggressor, at the base cell*.
G5 is one of C1's four conjuncts. If M05 reproduces at 0.0000 in the soak
workload, **every 60 s window fails, C1 is pinned, and C4 ("consistent
PASS/FAIL") passes trivially and unfalsifiably** — the exact J5 shape the
third form rule exists to catch.

**So the pre-flight must establish, per arm, on a short control run:** for
each of G1/G3/G5/G8, does its statistic sit *strictly inside* its bound,
and does it *vary across windows*? — **and for M05, which flows carry the
breach**, since §29 found the base-cell failure concentrated in 2–4 video
flows per arm rather than spread across the fleet (E2).

> **ANSWERED for the run-aggregate half, from `stage2_rows.csv` — see
> §7.4.** C1's conjunction passes **10/10 on every arm at N=4** and is
> **0/10 on TwoTier, 3/10 on Reservation, 10/10 on PF at N=8**. So the
> feared outcome is real *at N=8* and is why §7.4 moves the primary soak to
> **N=4**, where C1 can still fall over the horizon rather than being
> pinned before the run starts. **What remains for the pre-flight is the
> per-window and scripted-event behaviour**, which no existing grid
> contains. A conjunct pinned at FAIL (or at PASS)
cannot enter C1, exactly as a class pinned at "fails" could not enter
G12's ordering (§35.4).

### 3.2 C2's three internals: one absent, one untested here, one usable

GT-7.1 names three internals. **One of them is already measured at
identically zero:** `docs/wp9-plan.md` §19.5 reports the UL floor as
**armed but never firing — `gate_passes ≈ 65,200, fires = 0`** — and the
regime map's §5 **item 2** (that section has no subsections; a "§5.2"
citation would point at nothing) records the firing half as *structurally*
unreachable, not merely unobserved. **But that measurement covers only one of two firing routes, and G11's
workload is the first that could exercise the other.** `docs/wp9-plan.md`
§18.5 item 2 names them separately — *"attribute each fire to **desync** vs
**ordinary starvation via `floor_rx_lastseen`**"* — and both §19.5's
`fires = 0` and the regime map's structural-unreachability argument concern
the **desync** route only, reached through truncated BSR. Nothing rules out
the starvation route, and **GT-7.1 is the first workload in this project
with scripted silences** (duty-cycled teleop, waypoint pauses), which is
precisely what `floor_rx_lastseen` keys on.

**So floor-fire rate is NOT known to be dead in this scenario**, and the
pre-flight must measure it here rather than inherit §19.5's number from a
workload with no silences. If it does fire, that is a finding in its own
right: the first observed fire of a mechanism WP9 recorded as armed and
never firing.

**The genuinely missing internal is the third one.** `grep -rn
'skip_reason\|skip_count' sim/*.py scheduler/*.py` returns **nothing** —
GT-7.1's *"skip-reason counters from `[P5G-UL-SUMMARY]`"* are a **hardware
log field with no simulator counterpart**. C2 therefore has, at most:
crumb rate (exists), floor-fire rate (exists, dynamic range unknown here),
and skip reasons (**does not exist — would have to be built, or the clause
scoped out explicitly**). Whichever way that is settled, **the count of
internals actually covered travels with the C2 verdict inline**, the way
G11's seed count does.

### 3.3 C3 needs p98 to have cross-seed spread

CoV(p98) is a ratio of a cross-seed standard deviation to a cross-seed
mean. If p98 is tightly clustered the CoV is near zero and "≤15 %" is
unfalsifiable; if p98's mean is near zero the CoV explodes. The pre-flight
reports the **raw p98 per seed** alongside the CoV, always — the same
"report the guarantee's currency *and* the instrument with range" rule
§33.3 settled for ΔM02/Δp98.

### 3.3a C5's substrate is the same vector, and n is its binding limit

C5 asks for bimodality to be *investigated*. Its instrument is the raw
per-seed p98 vector — the same object C3 reduces to a CoV — so it inherits
§3.3's dynamic-range question and adds one of its own: **at n=3 a two-mode
structure is not detectable at all.** C5 is therefore the clause with the
sharpest dependence on §6's seed-count reversal, and the pre-flight reports
the per-seed vector rather than only its summary statistics.

### 3.4 C4 is degenerate under either pinned outcome

C4 compares C1's verdict vector across seeds. If C1 is all-PASS or
all-FAIL everywhere, C4 is satisfied by construction. **C4 is only
scoreable if C1 has at least one window that could go either way**, which
is precisely what §3.1 puts in doubt. C4's pre-flight is C1's.

### 3.5 The pre-flight leaks part of the answer — declare it

§35's extension: checking an *order* or a *verdict* for dynamic range
reveals some of the result, so **any expectation informed by the pre-flight
is registered as pilot-informed, not blind.** §9 marks each expectation
accordingly.

---

## 4. What the 30-minute soak needs that no WP9 run has had

Seven things. Five are measured here; two are structural gaps found by
reading the code.

### 4.1 M09 is O(horizon²) — a hard blocker, measured

`sim/scorecard.py:731-738` re-buckets the **entire** `ts_arrived_bytes`
array *once per second-bucket*, inside the per-second loop. Cost is
`O(flows × seconds × slots)`, i.e. quadratic in horizon.

Measured today (same record, shipped vs a hoisted variant that buckets the
arrived series once per flow):

| horizon | sim s | shipped | hoisted | speedup | values identical? |
|---|---|---|---|---|---|
| 20,000 | 5 | 0.215 s | 0.077 s | 2.8× | **yes** |
| 80,000 | 20 | 3.627 s | 0.337 s | 10.8× | **yes** |
| 160,000 | 40 | 17.792 s | 0.963 s | 18.5× | **yes** |

**Measured growth exponents, rather than the nominal 2 and 1** — the two
steps disagree, so the extrapolation is a range, not a number:

| | 20 k→80 k (×4) | 80 k→160 k (×2) | log-log slope |
|---|---|---|---|
| shipped | ×16.87 ⇒ exp **2.038** | ×4.905 ⇒ exp **2.294** | 2.111 |
| hoisted | ×4.377 ⇒ exp **1.065** | ×2.858 ⇒ exp **1.515** | 1.193 |

**Extrapolated from the largest measured point (160 k) to 7,200,000 slots,
across the plausible exponent range:**

| | at the nominal exponent | at the log-log slope | at the top-step exponent |
|---|---|---|---|
| **shipped** | 10.0 h | 15.3 h | **30.7 h** |
| **hoisted** | 43 s | 1.9 min | **5.5 min** |

**for ONE M09 evaluation of one record** — and the sweep path evaluates M09
**13 times per record** (`_SCORING_VARIATIONS`, pinned at 12 by
`test_wp9_sweep_memory.py`, plus the panel pass), i.e. **130–400 h/record**
shipped.

An earlier draft quoted only the nominal-exponent column and called it the
answer. The conclusion is unchanged across the whole range — **10 hours and
30 hours are equally disqualifying, and 43 s and 5.5 min are equally
fine** — but quoting a single extrapolated figure from a two-step series
whose exponent is visibly still climbing is exactly the over-reading the
second form rule names.

**This is not an optimisation, it is the difference between G11 being
runnable and not.** The hoist changed no value at any of three horizons.

Two further facts from the same read, both larger wins than the hoist:

- **12 of the 13 scoring passes discard M09 entirely.** `Scorecard.score()`
  computes 19 metrics; `wp9_sweep.py:401` harvests **6**
  (`("M03","M04","M07","M08","M14","M19")`), so **13 are discarded on each
  of the 12 variation passes** — M09 among them. *(Count derived from
  `score()`'s own body and that harvest tuple; an earlier draft
  hand-enumerated the discarded set and omitted M18 — the restated-count
  rule, committed inside a plan that cites it.)*
  **A hypothesis, flagged as one:** M09's value appears not to depend on
  any of the four variation parameters (`score()`'s `cfg` feeds only
  M03/M20, M04, M07/M08 and M19). That is an argument about existing code,
  not a measurement, and CLAUDE.md's third-kind rule applies — it is the
  load-bearing premise for skipping those passes, so **the commit that acts
  on it verifies it by running both ways and diffing**, rather than porting
  the claim on the strength of it being written here.
- **A value test cannot catch a re-introduced quadratic**, so the guard
  should be a *scaling* assertion — score at N and 2N, assert the ratio —
  not an output assertion. **This prescription is a recommendation of this
  plan, not a quotation from CLAUDE.md**, which says something adjacent but
  narrower: *a test proves the helper you just fixed stays fixed; it does
  not prove the pipeline that calls it is clean.* An earlier draft
  attributed the scaling-assertion form to CLAUDE.md, which is the
  wrong-citation failure this project treats as a finding in its own
  right.

### 4.2 Memory — the binding constraint, and it is NOT the timeseries

`record_timeseries=True` appends **one sample per slot per flow with no
stride** (`sim/metrics.py:91-121`): 5 arrays per flow × 32 flows + 6 system
+ 2 record-level, each of length `horizon_slots` exactly (`ts_len ==
horizon` confirmed at every probe).

Measured peak RSS (base cell, 32 flows, `sweep_scenario` N=8):

| horizon | sim s | ts=1 (PF) | ts=0 (PF) | timeseries share |
|---|---|---|---|---|
| 20,000 | 5 | 215 MB | — | — |
| 80,000 | 20 | 630 MB | — | — |
| 320,000 | 80 | 2,256 MB | **1,149 MB** (Res 1,143 / TT 1,191) | 1,107 MB |
| 1,280,000 | 320 | 8,757 MB | **4,375 MB** (Res 4,344 / TT 4,518) | 4,382 MB |

All eight cells above are **measured**. At 1.28 M the timeseries are
almost exactly half the footprint (4,382 of 8,757 MB) — so neither half
can be ignored, and **turning `record_timeseries` off buys a factor of
two, not a solution.**

**The decisive column is ts=0.** Turning the timeseries *off* still leaves
**1.15 GB at 320,000 slots and 4.38 GB at 1.28 M**, growing linearly with
horizon. So the per-slot arrays are only **half** the problem, and the
half that no flag can reach is the other one.

#### What the residual actually is — attributed, not assumed

The first version of this section asserted the residual was "the message
ledger". That is an argument about code that already exists, so per
CLAUDE.md it is a hypothesis until someone runs it. **It was run, and the
naive filename attribution is misleading.** `tracemalloc` on a
`record_timeseries=False` run, live allocation by line:

| MB (h=80,000) | objects | site | what it is |
|---|---|---|---|
| 93.8 | 1,378,969 | `traffic.py:178` | `Message(...)` — every message ever generated |
| 50.6 | 843,192 | `buffer.py:161` | `MessageCompletion(...)` on drain |
| 32.1 | 535,722 | `buffer.py:249` | `MessageCompletion(...)` on expiry |
| 19.3 | 689,228 | `messages.py:77` | `next(self._id_counter)` — the message **ids**, 28.0 B/object = one CPython int each |
| **222.2** | **~3.9 M** | **tracked total** | |

So it **is** per-message bookkeeping — but only 19.3 MB of 222 MB is
allocated *in* `sim/messages.py`, and even that is not the completions
list: line 77 is `return next(self._id_counter)` inside `new_id()`, so
those 689,228 objects at exactly 28.0 B each are the **message-id
integers**. The list append is line 80 and does not appear in the top
twelve at all. The objects that matter are allocated in `sim/traffic.py`
and `sim/buffer.py` and merely *retained by*
`MessageLedger._completions` and `BufferModel._completed`.

**Two lessons, and the second is the one to carry.** A filename-level read
blames the wrong module. And a *line*-level read still needs its object
size checked against what the line allocates — 19.3 MB over 689 k objects
is 28 bytes, which is an int, not a `MessageCompletion`. **The arithmetic
is what identified the line, not the line number.**

#### It is linear in horizon and nearly independent of load

| load_mult | horizon | traffic objs | buffer objs | tracked MB |
|---|---|---|---|---|
| 1.0 | 80,000 | 1,688,292 | 1,555,965 | 222.2 |
| 1.0 | 320,000 | 6,829,860 | 6,276,652 | 897.9 |
| **0.5** | 80,000 | 1,495,885 | 1,452,769 | **216.5** |

4× the horizon gives **4.04×** the objects — linear. **Halving the offered
load changes it by 2.6 %**, so this is *not* a saturation artefact that a
gentler soak workload would avoid: it is driven by message count, and the
periodic flows (telemetry 100 ms, command 50 ms, video 33 ms) do not scale
with `load_mult` at all.

#### The extrapolation, and what it costs

Tracked allocation scales `222 MB × (7,200,000 / 80,000) = 20.0 GB`; the
measured RSS/tracked ratio at 320 k is **1.34** — `tracemalloc` reports
decimal MB while `ru_maxrss` is MiB, so the two must be put in one unit
before dividing (1,149.5 MiB = 1,205.3 MB against 897.9 MB tracked; an
earlier draft divided across units and got 1.28). That gives **≈26 GiB peak
RSS for ONE 30-minute run with `record_timeseries` already OFF** — while
§1.4's direct affine fit of the ts=0 series puts it at **23.5–24.5 GiB**.
**§7 uses the affine fit**, which is measured end-to-end RSS rather than a
tracemalloc extrapolation multiplied by a ratio.

**And there is no flag that turns it off.** `driver.run` constructs the
`MessageLedger` unconditionally (`sim/driver.py:113-115`) and hands it to
`TrafficModel`. The parameter that would disable it is
`TrafficModel(..., ledger: MessageLedger | None = None)`
(`sim/traffic.py:80`, stored at `:91`, guarded at `:177`) — it exists, and
**it is unreachable through `run()`**, which always passes a live ledger.

**This is the finding that reshapes the budget, and it inverts §1.3's good
news.** On a 24 GB working budget (30 GB less the ~6 GB desktop session),
**one run at a time is all that fits.** This machine's measured 12.39×
parallelism is *unavailable to G11 as currently structured* — not because
of cores, but because RAM is the same 30 GB the laptop had. A memory-bound
G11 reverts to a fully serial campaign, i.e. **back to the ~21 h the
3-seed deviation was taken to avoid**, on a machine that is only ~1.06×
faster per core.

#### The fix is the mechanism G11 already needs

G11 scores in **60 s windows**. It therefore never needs the whole run's
completions in memory at once — only the current window's. **Evicting each
window's completions as the window closes** takes per-run retention from
~26 GB to roughly one window's worth (≈0.9 GB at 60 s by the same linear
fit), which puts 16 concurrent runs at ~14 GB and restores the full
12.39×.

**So the windowed-ledger eviction is not an optimisation — it is the
precondition for running 10 seeds at all**, and it is the same mechanism
the per-window scoring requires anyway. §10 commits 2 and 3 own it.

**What it forfeits, stated rather than hidden:** any metric needing the
whole run's completions at once (a run-aggregate M01/M03/M05) becomes a
per-window quantity that must be *combined* across windows rather than
computed globally. For percentiles that is not associative, so the
run-level M01 p98 the Guarantee Sheet quotes must either be accumulated
from retained per-window percentile inputs or declared as
"worst window", explicitly. This is a real design decision and it belongs
in commit 1, decided against the measurement.

**The eviction is necessary and NOT sufficient — the per-second fold is
required too, and the measurement now says so.** At 1.28 M the timeseries
are 4,382 MB of 8,757 MB. Evicting completions removes the *other* half;
the per-slot arrays remain, and at 7.2 M they alone are **~24 GB**. So
option (c) in §7.3 is **eviction *and* fold**, both, and each is its own
commit.

Everything C1 needs from the per-slot arrays is consumed *bucketed to one
second* — M09 buckets by second by definition, M08w sums over a window —
so folding to per-second accumulators reduces 7.2 M samples per array to
**1,800**, a 4,000× reduction, **preserving M09 and M08w exactly.** What
it forfeits is per-slot resolution for **M04, M19 and M21**, none of which
C1 needs. That trade is stated as a scope limitation, not hidden.

### 4.3 Windowed scoring re-scans the whole run, once per window

`scripts/wp9_window.py` is **fully general over arbitrary windows** —
`Window(name, start_s, end_s)` and `windowed_metrics(..., windows, subsets)`
know nothing about lidar; only `lidar_windows()` and `DEFAULT_SUBSETS` are
lidar-shaped, and both are parameters.

But every metric function takes the **whole** completion list and the
**whole** time axis and filters inside (`wp9_window.py:165-169`, `:208-209`,
`:143-146`). Work is
`n_subsets × n_windows × (2·|completions| + |time_s| + n_gbr·|idx|)`.
**The last term is the one that dominates at G11's horizon** and is easy to
drop: `_m07w_m08w` re-sums `f.ts_delivered_bytes` over the window's index
list for *every GBR flow* (`:264-268`), so summed over 30 windows it
touches each GBR flow's entire 7.2 M-sample array once per subset.
Its only caller today pays 4 subsets × 5 windows over a 5 s run. **G11 is
4 subsets × 30 windows over an 1,800 s run** — 240 full scans of a
completion list that is itself ~360× longer. Pre-bucketing completions by
window index once is a change to the internals only; the API survives.

### 4.4 Five windowed metrics C1 needs do not exist, and one needs an input the module is not handed

| needed by | metric | status |
|---|---|---|
| G1 | M01w p98 | **exists** |
| G1 | M15w (jitter) | missing — cheap, same inputs as M01w |
| G3 | M03w (liveness gap) | missing; computable from `completions` alone, but **must select on completion time, not generation time** — the opposite of M01w/M02w's deliberate choice |
| G5 | M05w / M06w | missing, but **cheaper than it looks**: `sim/messages.py::FrameLedger.group(completions)` already regroups completions by `message.frame_id`, and `windowed_metrics` is *handed the completions*. No new `WindowedFlow` field is needed — an earlier draft said there was, which named the wrong input |
| G8 | M09w | missing **and not computable from current inputs** — `WindowedFlow` carries `ts_delivered_bytes` but not `ts_arrived_bytes`, which M09's denominator requires |

M09w also needs an aggregation shape the module does not have: every
existing windowed metric is a per-flow reduction then argmax/argmin, while
Jain is an index over the vector of all flows within each sub-bucket.

**The count is five (M15w, M03w, M05w, M06w, M09w) and it is the same five
commit 5 lists** — derived from the rows above and from
`wp9_window.py`'s own three metric functions (`_m01w`, `_m02w`,
`_m07w_m08w`), not carried as prose.

### 4.5 Three of GT-7.1's four scripted ingredients have no mechanism

GT-7.1's "scripted realism" is: teleop `cmd_vel` duty-cycled on A, waypoint
pauses on B, a firmware window at T+10 min, one STOP drill at T+20 min.

| ingredient | mechanism | status |
|---|---|---|
| firmware window at T+10 min | `traffic_params["active_from_s"/"active_until_s"]`, applied pre-dispatch so it composes with every generator (`sim/traffic.py:211-216`) | **exists** |
| duty-cycled teleop | — | **none.** `FlowConfig` has no `duty_cycle` field; `sweep_scenario`'s `duty_cycle` is `_burstify`, which trades cadence against burst size **at constant mean rate — the flow is never off** |
| waypoint pauses | — | **none.** The single activation window is one `(from, until)` pair: a flow can turn on once and off once, never repeat. The only source-suppression gate is driven by `JoinState.app_running` |
| STOP drill at T+20 min | — | **none.** The e-stop flow exists (UGV 5QI 85 DL) but is Poisson-triggered at `rate_hz=0.2`, i.e. random in time |

**Recommendation — one mechanism, not three.** Extend the activation gate
from a single `(active_from_s, active_until_s)` pair to a **list of
windows**. That single change expresses all three: duty-cycled teleop is a
repeating list, a waypoint pause is a list with gaps, a STOP drill is a
one-period window. It is a strict generalisation (a single pair is a
one-element list), so it should be `--check` neutral — **which is testable,
and the test is the point.** One fidelity change, one commit, one
`--check`, per CLAUDE.md's rule.

### 4.6 There is no factory_fleet asset, and no "both assets" composition

GT-7.1 wants *both assets, full `factory_fleet` profile*. `grep factory_fleet
--include=*.py` returns nothing. `sim/fleet.py`'s UGV carries 5QI 4 but not
5QI 1; DRONE carries 5QI 1 but not 5QI 4; the test plan's asset needs both.
And `COMPOSITIONS` are proportional mixes — at `n_ues=2`, `ugv_heavy` gives
`['ugv','sensor']`, not two full assets.

Following G12's own precedent (§35.6 D2: *no `sim/fleet.py` change*), the
scenario module `sim/scenarios/g11.py` composes the two assets itself.

### 4.7 No drift detector exists

C2's instrument. Nothing in the repo computes a monotone-trend statistic
over anything. It is study-layer code (the panel is pre-registered and is
not edited for it).

---

## 5. Resumability — `_run_resumable` is reusable in shape, not in granularity

`_run_resumable` (`wp9_sweep.py:957`) is the right pattern and should not be
reimplemented. But **its unit of work is a CELL = 3 arms × n_seeds runs**
(`expected_per_cell = 3 * n_seeds`, hardcoded at `:969`), and the worker
returns only after all of them finish.

**For G11 that is the entire campaign in a single checkpoint.** A crash at
hour 19 of a 20-hour job would lose everything — the precise failure mode
the handover says three runs have already hit.

**What G11 needs:**

1. **One run = one cell.** Grid `{"arm": [...], "seed": [...]}`, so a crash
   loses at most one run. `expected_per_cell` must become a parameter
   rather than `3 * n_seeds`; `_load_completed`'s partial-cell logic then
   has nothing to drop, which is a simplification, not a special case.
2. **Fix the append-mode duplicate on resume.** `rows.jsonl` is rewritten
   in truncate mode from complete cells only, but `records.jsonl` and
   `online_rows.jsonl` are opened `"a"` and **not** pruned — a re-run cell
   appends a second copy of its records. Bounded and harmless at cell
   granularity today; at run granularity with a long job it is a real
   duplicate-row hazard for any downstream aggregate.
3. **Horizon must not reach `_build` through the module-global.**
   `_build` reads `horizon_slots=axis_values.get("horizon_slots",
   _HORIZON[0])` (`wp9_sweep.py:113-114`) — **the global is only the
   fallback.** No current grid declares a `horizon_slots` axis, so today
   every stage sets `_HORIZON[0]` and a worker that forgets to would
   **silently run at 20,000 slots**: a 360×-too-short soak that completes
   normally and looks like a result.
   **G11 should declare `horizon_slots` as a grid axis instead**, which
   removes the failure mode rather than adding a test for it — and has the
   side benefit that the horizon then appears in `cell_id`, so a resumed
   run cannot silently mix horizons. Either way the worker asserts its
   realised `scenario.horizon_slots`; no test asserts this today.
4. **`spawn`, so `pkill -f` will not reach the workers.** Already recorded
   in CLAUDE.md; the runner should log worker PIDs so they can be killed
   individually. **This session hit the other half of that same invariant
   twice while taking §1's measurements** — once when a `while pgrep -f
   par_eff.sh` wait loop matched *its own command line* and so could never
   exit, and once when `pkill -f "memwatch.sh"` killed the shell that
   issued it (exit 144). Both are the documented trap, both cost a few
   minutes, and both argue the same fix: **the runner and any monitor
   around it address processes by PID, never by pattern.**
5. **Live RSS instrumentation with a kill threshold**, not just a green
   suite — and a memory guard test for the new worker, since neither
   `_run_one_cell_s3` nor `_run_one_cell_s4` has one and a new worker
   inherits no coverage.

---

## 6. Seeds — reversing the 3-seed deviation, and why it is not only a budget question

### 6.1 The deviation as recorded

`docs/wp9-plan.md` §6.3: *"G11 soak — the one place the standing 10-seed
rule is broken, deliberately."* 30 min of sim ≈ 43 min/run, so 3 arms ×
10 seeds ≈ **21 h**, which did not fit alongside stage 2. Cut to 3 seeds
≈ 6.5 h, no bootstrap CI, three runs reported individually.

**Defensible *only* because** — §6.3's own words — *"GT-7.1's actual KPI is
monotonic drift in internals — a within-run check — not a cross-seed
mean. Any cross-seed claim from the soak is out of bounds."*

### 6.2 The justification covers one clause of five

Apply §4.1's clause-by-clause default to that sentence. "A within-run
check, not a cross-seed mean" is an accurate description of **C2**. It is
**not** a description of C3 or C4:

- **C3 is `CoV(p98)` across repeats.** That is a cross-seed statistic by
  definition. At n=3 it has 2 degrees of freedom.
- **C5 is "investigate any bimodality".** Detecting two modes in three
  points is not a thing that can be done.
- **C4 is "identical PASS/FAIL across repeats."** Also cross-seed by
  definition. At n=3, the rule of three bounds an unobserved inconsistency
  rate only at ≤63 %; at n=10, ≤26 %.

**So the 3-seed decision, as justified, silently drops half the
guarantee** — the entire GT-7.4 half. It was recorded as a *budget*
deviation and it is one; but its stated justification is a *clause-scope*
argument that holds for exactly one of the four clauses. Reversing it is
therefore **not merely affordable, it is required for C3 and C4 to exist as
scoreable claims at all.**

Note also that **GT-7.4's own procedure says "5–10 repeats."** Three is
below the spec's own lower bound.

### 6.3 The recommendation

**Plan at 10 seeds, 3 arms — 30 runs — reversing the deviation**, backed by
this machine's measured budget (§7), not by an assumption that a bigger
machine makes it fit.

**One honest qualification on that argument, because the plan's own E6
undercuts part of it.** §6.2 justifies 10 seeds by C3 *and* C4. But E6
registers, in advance, that **C4 is expected to be "not scored"** — pinned
by construction if C1 is pinned — and §3.3 registers C3 as itself at risk
of a degenerate CoV. **So on this plan's own priors, the seed count's value
rests on C3 and C5 surviving the pre-flight.** If §3's pre-flight finds C1
pinned *and* p98 degenerate, the correct response is not "run 10 seeds
anyway" but **fix the scenario until the instruments have range** — which
is the third form rule applied to a seed-count decision instead of to an
expectation. The pre-flight is commit 0 precisely so this is decided before
30 runs are launched. **If the measured budget does not support 10, §7
states the arithmetic and proposes what it does support** — and the fallback
is *not* "back to 3": it is the largest n that keeps C3 and C4 scoreable,
which is 5 (GT-7.4's own floor).

**The inline-qualifier rule still applies, unchanged.** §5's rule is about
a row stating its own seed count and CI status inline; it is not a rule
that G11 must be reduced-seed. At n=10 the row says "10 seeds, bootstrap
CI" inline for the same reason.

---

## 7. Budget

**Derived, never restated.** Every figure below is emitted by
`sweeps/wp9/g11_probes/summarise.py` from the raw probe JSONL. That is not
a stylistic choice: the first draft of this section hand-built its tables
and an adversarial review found **six** arithmetic errors in them, one
caused by `wc -l` dropping a record (§1.4). The extrapolation is also taken
over the **full** population **before** any mode flag narrows it —
CLAUDE.md's restated-count rule and its fifth instance, which was in the
*budgeting* path and reported "22 min for the grid" from a list silently
truncated to one element (`g12_campaign.py:352-360`).

### 7.1 Per-run cost at the soak horizon — EXTRAPOLATED, and labelled

From §1.4's affine fits evaluated at 7,200,000 slots. **These are
extrapolations**, and the point count behind each is stated because it is
not uniform:

| arm | ts=1 run | ts=1 peak RSS | n | ts=0 run | ts=0 peak RSS | n |
|---|---|---|---|---|---|---|
| PF | 25.0 min | **47.7 GiB** | 4 | 22.4 min | 23.7 GiB | 3 |
| Reservation | 37.5 min | **47.7 GiB** | 4 | 34.5 min | 23.5 GiB | 3 |
| TwoTier | 74.9 min | **49.5 GiB** | 3 | 71.5 min | 24.5 GiB | 3 |
| **per seed (3 arms)** | **137.3 min** | | | **128.4 min** | | |
| **× 10 seeds, serial CPU** | **22.9 h** | | | **21.4 h** | | |

**§6.3's "≈43 min/run" is close to this figure** — 137.3/3 = 45.8 min/run —
so the *time* budget was approximately right even though §6.3a found the
cell table beside it 5–7× low. **But 45.8 min/run is a mean of
extrapolations, not a measurement**, and an earlier draft of this section
called it "measured" while sitting under a heading that said the same. §7.5
is the run that closes that gap.

### 7.2 The finding that matters more than the timing

**At this workload, G11 as specified does not fit in memory at any seed
count, on either machine.** `record_timeseries=True` is not optional — the
sweep sets it by default because *"M04/M09/M19 are `pending` without it"*
(`wp9_sweep.py:101`) and C1's G8 conjunct **is** M09. At 7.2 M slots that
run extrapolates to **~48 GiB on a 30 GiB host.**

The 3-seed deviation was taken to fit a 21-hour *time* budget. **The
binding constraint is memory, it is ~1.6× the whole machine, and it would
have announced itself as an OOM part-way into the first run** — the same
failure mode as stage 1's 25 GB death. This is §6.3a's rule (*time the
thing you are actually going to run*) extended to the resource it did not
cover: **measure the memory of the thing you are actually going to run,
too.**

**The scope of that claim, stated because the decompose rule applies to it
and an earlier draft failed the rule here.** Every memory number above is
measured at the **32-flow parametric base cell** (`sweep_scenario`, N=8).
"G11 as specified" in the sentence above means *this workload* — **not**
GT-7.1's literal two-asset workload, which §7.4 says is ~7–12 flows and
which these numbers **upper-bound**. §4.2 shows the residual is driven by
message count, so a two-asset soak would be proportionally smaller and
might well fit. **The honest statement is: at the fleet size WP9 has been
running, G11 does not fit; at GT-7.1's literal two-asset reading, it is
untested and probably does.** §7.4 is where that is settled, and it must be
settled before the budget is trusted.

### 7.3 Three options, priced by simulated LPT rather than division

Makespan is **not** total-CPU ÷ speedup: G11 is 30 long jobs, so the
schedule matters and the longest job is a floor. The figures below run an
actual longest-processing-time schedule over the real job list
(10 × each arm's per-run time) and then de-rate by the **measured**
efficiency at that worker count. An earlier draft divided by 16 at 100 %
efficiency in one line and by 12.39× in the next, publishing two makespans
computed under contradictory assumptions.

| option | per-run RSS | fits in ~24 GiB? | serial CPU | best makespan |
|---|---|---|---|---|
| **(a) as specified** (ts=1) | 47.7–49.5 GiB | **no, on every arm** | 22.9 h | **does not run** |
| **(b) ts=0**, forfeit the timeseries | 23.5–24.5 GiB | **NO — measured** (§7.5) | 21.4 h | **does not run** |
| **(c) eviction + per-second fold** | ~1 GiB | yes, 16-wide | ~22 h | **≈2.15 h** (W=16) |

**Option (b) is not the runnable fallback an earlier draft called it, and
this is now measured rather than extrapolated.** Its predicted numbers are
23.7 / 23.5 / **24.5** GiB against a ~24 GiB working budget (30 GiB less
the ~6 GiB desktop session) — and **§7.5's guarded run confirmed it: PF,
the cheapest arm, hit 21.8 GiB and was killed with 2.4 GB of system memory
left.** **Option (b) removes the timeseries, still does not fit, and loses
C1's G8 conjunct — it fails on all three counts.**

**Option (c) requires BOTH changes, not just the eviction.** §4.2's
measurement settles this: at 1.28 M the timeseries are 4,382 of 8,757 MiB,
so eviction alone (which removes the message-bookkeeping half) still leaves
~24 GiB of per-slot arrays at 7.2 M. Commits 2 **and** 3 in §10.

**Option (c) makespan, LPT-simulated at each W and de-rated by measured
efficiency:**

| W | ideal LPT | measured eff | de-rated |
|---|---|---|---|
| 8 | 174.8 min | 88 % | 3.33 h |
| 12 | 124.8 min | 84 % | 2.47 h |
| **16** | **99.8 min** | **77 %** | **2.15 h** |
| 24 | 74.9 min | 56 % | 2.21 h |
| 32 | 74.9 min | 45 % | 2.74 h |

**W=16 wins, and W=24/32 lose despite higher raw throughput** — with only
30 jobs, the ideal makespan bottoms out at one TwoTier run (74.9 min) and
the extra workers buy nothing while costing efficiency. **This is why §1.3
declines to call W=32's higher `cells/s` the operating point.**

**Adding §9's permutation control** (10 more TwoTier runs, +12.5 h CPU)
raises the W=16 de-rated makespan to **3.22 h** (LPT over the augmented
50-job list: ideal 149.7 min ÷ 0.7747). Both fit
overnight comfortably.

**One cost these figures still exclude, stated rather than buried:** every
per-run time descends from a `driver.run`-only probe, so **scoring is not
in the makespan.** §4.1 puts hoisted M09 at 43 s–5.1 min per evaluation at
this horizon and §4.3 puts windowed scoring at hundreds of full scans of a
completion list ~360× longer than its only current caller's. **Scoring
could plausibly rival the run.** Commit 7's own `--time-cell` pass measures
it before launch; until then every makespan here is a **lower bound**.

### 7.4 The fleet size — SETTLED, from data already on disk

An earlier draft left this open. It is now answered, and **neither N=4 nor
N=8 is right on its own**, because C1's dynamic range is **arm-dependent**
and §3's pre-flight was assuming one fleet size would serve all three arms.

**Computed from `stage2_rows.csv` (committed, no new runs) — C1's conjuncts
at their own bounds, per-seed passes out of 10, load ×1.0, base slice:**

| N | PF | Reservation | TwoTier |
|---|---|---|---|
| 2 | 10/10 | 10/10 | 10/10 |
| **4** | **10/10** | **10/10** | **10/10** |
| **8** | **10/10** | **3/10** | **0/10** |
| 16 | 0/10 | 0/10 | 0/10 |

*(M01 is excluded from the conjunction and that exclusion is load-bearing:
its worst flow is the **best-effort filler `qfi9` in every cell**, and at
N≥8 its p98 is pinned at **300.0–300.2 ms against that flow's own 300 ms
PDB** — the eviction bound read back, not a latency. Including it makes
every arm fail at N≥8 for a reason that is not about latency, which is the
decompose error this plan is written to avoid, and which the first version
of this check committed.)*

**So the fleet size determines which clauses are scoreable at all:**

- **N=4 — C1 is pinned at PASS on every arm.** E1's first row applies: a
  soak here that passes is *"a ceiling reading"* unless the pre-flight shows
  the conjuncts near their bounds.
- **N=8 — C1 is pinned at FAIL on TwoTier (0/10) and at PASS on PF
  (10/10).** Neither can score C1. **Reservation's 3/10 is the only cell in
  the entire grid where C1 varies across seeds** — which is precisely what
  §3.4 says C4 requires.
- **N=16 — pinned at FAIL everywhere.** Out.

#### The recommendation: MOVE the primary soak to N=4, and add a second cell at N=8

**The plan moves, and the reason is the opposite of the obvious one.** N=4
is right **not** because "every arm runs clean" makes it a fair test — that
is what makes C1 *pinned* — but because **N=4 is the only fleet size where
the soak can DISCOVER a failure rather than re-measure one.**

That is the whole argument, and it is E5's:

- **At N=8 the deployed arm already fails C1 at a 5-second horizon.** A
  30-minute run there re-measures a known base-cell failure at **360× the
  cost** and E5 is trivially true before it starts.
- **At N=4 the guarantees hold at 5 seconds.** If they *stop* holding over
  30 minutes, that is a genuinely horizon-dependent failure — **the single
  most valuable result G11 could produce**, and the only cell where it is
  even possible. If they keep holding, C2's drift check and C3/C5's
  reproducibility are measured on a statistic that is actually alive.

**And a shift-length claim about the deployed product belongs where the
product works.** "The guarantees hold for a whole shift" is not a claim one
can make at a fleet size where they do not hold for five seconds.

**The second cell, at N=8, is for the reproducibility clauses only**, and it
is small: **Reservation alone**, where C1's 3/10 gives C4 and C5 their only
genuine cross-seed variation anywhere in the grid. It is explicitly **not**
asked to score C1 — the verdict there is already known — and its row says so.

| cell | arms | clauses it can score | why |
|---|---|---|---|
| **N=4** (primary) | all three | **C1, C2, C3, C5** | the only N where C1 can move *downward* over the horizon |
| **N=8** (secondary) | **Reservation only** | **C4, C5** | the only cell where C1's verdict varies across seeds |

**Cost consequence, and it is favourable.** N=4 is roughly half the base
cell's flows, so §13's model puts it well under §7.1's figures — the
primary campaign gets *cheaper* than the numbers in §7.3, and the N=8
secondary is one arm rather than three.

**What this does to §3's pre-flight: most of it is already answered.**
Commit 0 was scoped to ask whether C1's conjuncts have range on short runs.
The stage-2 grid contains that answer for every (arm, N) already, and it is
the table above. Commit 0 therefore shrinks to the parts stage 2 cannot
supply — the **per-window** behaviour and the **scripted-event** windows,
neither of which exists until commits 4–6 — which is a further argument for
§10's split of the pre-flight across commits 0 and 9.

#### N=2 — GT-7.1's literal reading, and why it cannot produce the evidence

**Settled here rather than left open, because a hardware team running
GT-7.1 as written will run two robots and get a result that means something
different from this plan's.**

GT-7.1 says *"both assets"* — **N=2**. At N=2 C1 passes **10/10 on every
arm**, and that is not a scheduler result: **N=2 is 4× below the binding
bound.** §0.3/§1.1 locate the boundary at the PDCCH limit, `32 U-slot CCE ÷
aggregation level 4 = 8 robots`, and D4-4 measured **zero qualifying
arm separations at N=4** with N=2 as an excluded-cell control. So at N=2:

- **C1 cannot fail for a scheduling reason** — the cell is nowhere near the
  resource that binds;
- **the arms cannot separate** — they are measured identical there;
- **a PASS is therefore structurally guaranteed and carries no information
  about the deployed fleet size.**

**This is the same shape as G12's specification finding**, one guarantee
over: **the test as written puts itself outside the regime where its own
evidence exists.** G12's ramp tops out at 145 % of ceiling and the ordering
only appears at 177–265 %; GT-7.1's soak runs at 2 robots and the
guarantees only become discriminating at 4–8. In both cases the fix is
owned by whoever owns the test plan, not by the simulator.

**What a hardware team should expect if they run the literal version:** a
clean pass, on every arm, that says *"two robots run for a shift"* — which
is true, worth having as a smoke test, and **not evidence about the fleet.**
It cannot distinguish the deployed scheduler from the baseline, and it
cannot be used to support an admissible-fleet claim of any size.

**Recommendation for the test plan:** run GT-7.1's soak at **the admissible
N of the arm under test** — 4 for the deployed product, 8 for PF (§7.4's
table) — or state explicitly that GT-7.1 certifies a two-robot shift and
that fleet-size evidence comes from GT-5.2 alone.

**Which reading this plan answers:** **N=4, the informative one**, and
G11's row says so — with the reason being *discovery versus
re-measurement* (above), **not** fairness between arms.

### 7.5 The guarded run at the real horizon

§6.3a's rule is *time the thing you are actually going to run, or state
explicitly that the number is a lower bound.* §7.1's figures are
extrapolations, so a run at the **real** 7,200,000-slot horizon is being
taken to close that gap directly, alongside a fifth fitting point at
2,560,000 (PF's has landed and is in §1.4; it moved PF's ts=0 series from
two points to three, and with it PF's ts=0 extrapolation from an
uninformative 2-point fit to a real one).

The guarded run was `record_timeseries=False`, **PF — the cheapest arm**,
alone, under a 22 GiB watchdog that kills by PID. Two possible results,
both fixed in meaning **before** the run:

- **it completes** ⇒ §7.1's ts=0 column becomes measured rather than
  fitted, and the exact peak RSS says how much headroom one run leaves;
- **the watchdog kills it** ⇒ *"a single 30-minute run exceeds 22 GiB"*,
  which refutes option (b) outright and makes (c) mandatory.

#### RESULT — the second branch fired

```
14:06:00 pid=868929 rss=22317MB avail=2441MB
14:06:00 KILL pid=868929 rss=22317MB exceeded 22000MB
```

**The cheapest arm's 30-minute run reached 21.8 GiB and was still climbing
when the guard stopped it, with 2.4 GB of system memory left.** It never
reached the end, so no record was written — the kill *is* the measurement.

**This settles §7.3 empirically rather than by extrapolation:**

- **Option (b) is refuted.** Even with the timeseries off, and on the arm
  with the smallest footprint, **one run does not fit** alongside a desktop
  session on a 30 GiB host. The 23.7 GiB the affine fit predicts for PF is
  consistent with a run that was at 21.8 GiB and rising; Reservation and
  TwoTier are predicted higher still.
- **Option (c) is mandatory, not preferred.**
- **And the extrapolation is corroborated where it can be**: the fit said
  PF would pass 22 GiB before finishing, and it did.

It was deliberately **not** run for all three arms: at ~24 GiB predicted,
Reservation and TwoTier would each have been killed near the end of a 34-
and 72-minute run, spending an hour of wall clock to re-learn what PF
settles in twenty minutes. **That decision was recorded before the run, and
the outcome vindicates it** — the information was in the cheapest arm.

## 8. Pre-registered expectations

Written in the journal's four-rule form: **shape not mechanism**; a
two-level reading gives direction not shape; **dynamic range checked in the
control first**; and the analysis code that will score these is itself a
claim in advance, so it decomposes by the grouping the report will present
at the moment the line is written.

Each entry names its outcome→meaning map **before** the data exists, and
declares whether it is blind or pilot-informed (§3.5).

### E1 — C1's per-window pass rate *(pilot-informed by §3's pre-flight)*

**Shape:** per arm, the fraction of the 60 s windows passing all four
conjuncts, **partitioned into QUIESCENT windows (no scripted event) and
EVENT windows (firmware, STOP, a pause boundary)** — the same partition E5
depends on, declared here so both use one definition.

| outcome | meaning, fixed in advance |
|---|---|
| all windows pass, all arms | C1 holds — **and is a ceiling reading unless the pre-flight showed the conjuncts near, not at, their bounds** |
| failures **confined to event windows** | the scripted disturbances are what break it — locatable by index against the schedule, and the clearest *soak-specific* result available |
| failures in a **minority of quiescent** windows, clustered in index | a transient with no scripted cause — the most interesting outcome, and the one E5 is registered against |
| failures in a **majority of quiescent** windows, uniform across index | not a soak finding at all: a base-cell failure a 5 s run would also show, i.e. §29's G5 result reappearing at 30 min |

**Registered — and it moves with §7.4's fleet-size decision.** At the
**N=4 primary cell**, where C1 passes 10/10 on every arm at a 5 s horizon,
the registered outcome is the **first** row: all windows pass, on all three
arms. **The interesting outcome is therefore a MISS**, and E5 is where that
is scored.

*(Had the soak stayed at N=8, the registered outcome would have been the
fourth row — a majority of quiescent windows failing on both QoS-aware arms,
carried by M05 — and it would have been known true before the run. That is
exactly why §7.4 moves the cell.)*

### E2 — which conjunct carries any C1 failure *(decompose, registered in advance)*

C1 is a conjunction over four guarantees; a bare "C1 fails" is an aggregate
over four populations. **Registered: G5 (M05) is the binding conjunct;
G1, G3 and G8 pass in the same windows.**

**And one level deeper, because §29 already did this decomposition once and
it changed the reading.** M05's base-cell breaches are counts over *seeds*,
not over flows, and the breaching flows are a handful: Reservation's 33/40
seeds came from **2 distinct flows** (`ue8_qfi2` ×24, `ue7_qfi2` ×9),
TwoTier's 35/40 from **4, one of them accounting for 30**. So *"G5 fails"*
is a statement about a small number of chronically-incomplete `xr_video`
flows, not about the fleet.

**Registered:** the same shape holds in the soak — C1's G5 failure is
carried by **≤4 distinct flows per arm**, concentrated rather than
fleet-wide.

**Requirement on the scorer, written now rather than after:** every
per-window verdict emits (a) the conjunct that failed and (b) the
**identity of the breaching flow**. A window verdict that reports only
"G5 FAIL" is an aggregate over a population the claim is not about — the
fourth form rule applied to the line of code before it is written, and the
exact error `g12_score.py` committed while citing the rule in its own
docstring.

### E3 — C2's drift statistic, scored PER INTERNAL *(pilot-informed)*

**C2 has up to three internals and they must be scored SEPARATELY** — an
earlier draft's three-row table conflated them and was not a partition
(row 1 was compatible with rows 2 and 3, and there was no row for "one flat,
one drifting", which is a likely outcome). Per internal, the map is:

| per-internal outcome | meaning |
|---|---|
| the counter does not exist | **not scored** — skip-reason counters are a hardware log field with no simulator counterpart (§3.2) |
| exists, identically constant across all 30 windows | **no dynamic range**; excluded, with the exclusion stated inline |
| exists, varies, trend CI includes 0 | **that internal passes** |
| exists, varies, trend CI excludes 0 | **a real leak on that internal** — the finding GT-7.1 exists to catch |

**Registered, per internal:**

- **crumb rate** — exists, varies, **flat** (CI includes 0);
- **floor-fire rate** — **exists and fires**, because GT-7.1 is the first
  workload with scripted silences and the `floor_rx_lastseen` route is
  untested (§3.2). *This is the one I expect to be wrong in the interesting
  direction*; §19.5's `fires = 0` is from a workload with no silences;
- **skip-reason counters** — **not scored**, absent from the simulator.

**C2's verdict therefore states the number of internals it actually
covered**, inline, and that number is at most 2 of GT-7.1's 3.

### E4 — C3's CoV(p98) *(blind)*

**Shape:** CoV of the worst-flow M01 p98 across the 10 seeds, per arm,
reported **always** alongside the raw per-seed p98 vector — §33.3's "report
the guarantee's own currency *and* the instrument with range".

| outcome | meaning, fixed in advance |
|---|---|
| CoV < 15 %, p98 vector visibly spread | **C3 passes** — reproducibility demonstrated at n=10 |
| CoV < 15 %, p98 vector near-constant or near-zero | **not scored.** A CoV computed on a degenerate statistic is a fact about the floor, not about reproducibility — the same trap as E6's first row |
| CoV ≥ 15 % | **C3 fails**, and GT-7.4's own instruction applies: *"any bimodality investigated before the Guarantee Sheet is signed"* — so the per-seed vector is inspected for two clusters before anything is concluded about variance |

**Registered:** the first row, on all three arms. **This is the entry n=3
could not have supported** — a CoV with 2 degrees of freedom is not an
estimate — and is §6.2's argument in its most concrete form.

### E5 — **MOST LIKELY WRONG**, with its trace obligation *(blind)*

**The naive form of this expectation is unsound, and saying why is half
its value.** *"Every C1 failure reproduces at a 5 s horizon"* cannot be
tested as written: the G11 scenario contains a firmware window at
**T+10 min** and a STOP drill at **T+20 min**, so a 5 s run of the same
scenario and seed **cannot contain those events at all**. Any failure
located in a scripted window would be non-reproducible *by definition*,
and the naive map would convert that tautology into "a horizon-dependent
failure" and obligate a trace for it.

**Registered, in the form that is actually testable:** partition C1's
failing windows into **quiescent** windows (no scripted event) and
**event** windows (firmware, STOP, a pause boundary). Then:

*the soak finds nothing, in its QUIESCENT windows, that a short run does
not.* Every C1 failure in a quiescent window reproduces at a 5 s horizon on
the same scenario and seed. **The soak's unique contributions are the event
windows, C2, C3, C4 and C5.**

**Why it is the most-likely-wrong slot:** it is the claim this whole work
package is built to test, and the entire reason a 30-minute horizon is
worth 360× the cost. If it holds, G11's row must say plainly that the soak
bought reproducibility evidence and a drift check — and *not* new failure
modes.

**§7.4's move to N=4 is what makes this expectation scoreable at all.** At
N=8 E5 would be trivially true before the run: C1 already fails at 5 s on
the QoS-aware arms, so nothing the soak found could be horizon-dependent.
**At N=4 C1 passes at 5 s on every arm, so a C1 failure in a quiescent
window at 30 minutes CANNOT be a re-measurement — it can only be
horizon-dependent.** The cell was chosen so that this entry can be wrong.

**Trace obligation on a miss:** if a C1 failure appears in a **quiescent**
window at 30 min and does **not** reproduce at 5 s on the same
`(scenario, seed)`, that is a genuinely horizon-dependent failure and
obligates a direct-cause trace — a worktree-instrumented per-slot trace of
the first failing quiescent window, not more reading (CLAUDE.md's
third-kind rule: *an argument about existing code is also a hypothesis
until someone runs it*). **A failure in an event window carries no such
obligation**, because non-reproduction there is definitional rather than
informative.

### E6 — C4's verdict stability *(pilot-informed, and conditional by construction)*

**C4 is only scoreable if C1 has at least one window that could go either
way** (§3.4). The expectation is therefore registered as a **conditional**,
with the antecedent named:

| if C1 is... | then C4... | and the row must say |
|---|---|---|
| all-PASS or all-FAIL in every window on every seed | is satisfied **by construction** | **"not scored"** — not "passed". A trivially-satisfied conjunction is not evidence of reproducibility |
| mixed, with at least one window varying across seeds | is a real claim | the fraction of windows whose verdict is identical across all 10 seeds, and the identity of any that are not |

**Registered:** the first row, on the QoS-aware arms — consistent with E1.
**This is the J5 shape and it is being declared in advance rather than
discovered afterwards**, which is the only difference between a caveat and
a retraction.

### E7 — C5's bimodality check *(blind)*

**C5 has no threshold and cannot pass or fail** — GT-7.4 says only that any
bimodality is *investigated* before the sheet is signed. So it is
registered as a **procedure with a stated trigger**, not a bound, which is
the honest form for a clause written that way.

**Shape:** the 10 per-seed p98 values per arm, as a sorted vector.

| outcome | meaning, fixed in advance |
|---|---|
| the vector has one visible mode (gap-to-spread ratio small) | C5 discharged; **reported as "inspected, unimodal", never as "passed"** |
| the vector separates into two clusters | **C5 triggers**: the modes are characterised and the split is traced to a seed property before anything else in G11 is quoted, because a bimodal p98 makes both the CoV (E4) and the mean uninterpretable |
| n too small to tell | at n=10 this is a real possibility and is reported as such rather than resolved by assertion |

**Registered:** the first row — **and this is the entry that most depends
on reversing the 3-seed deviation.** Bimodality in three points is not
detectable at all, so at n=3 C5 could only ever have been reported as
"not scored".

---

## 9. The standing confound G11 cannot ignore — flow declaration order

`docs/wp9-plan.md` §35.5/§36.1: reordering `ScenarioConfig.flows`, with
everything else byte-identical, **changes which 5QI class violates first,
and on TwoTier can break a bearer at nominal load outright.** PF's
permutation 104 gives the opposite first-violation order from 101/102/103,
on all 5 seeds each — a *deterministic* function of list position. **The
mechanism is untraced** — §35.5 says only *"the mechanism is NOT identified
and is not guessed at."* The further point that **all three candidates are
position-dependent, so tracing to any of them CONFIRMS the artefact rather
than refuting it**, is **§35.13's** promotion-bar edge, not §35.5's; an
earlier draft attributed it to the wrong section.

**And §36.1 quantifies how weak a two-permutation control is.** G12 ran
**four** permutations × 5 seeds on PF: 101/102/103 all gave `[2,4]` and only
104 gave `[4,2]`. Under that empirical distribution **two permutations
agreeing is the majority outcome even though a total, deterministic order
effect exists** — so "invariant across 2 permutations" licenses almost
nothing. Worse for G11's own arm of interest: **7 of TwoTier's 20 permuted
runs could not produce a clean ramp bottom at all.**

**This bears directly on G11.** C1's verdict is a pass/fail over a
multi-flow fleet scenario whose flows are declared in *some* order. A
"TwoTier fails window 7" result could be a fact about TwoTier or a fact
about list position, and nothing in G11 as specified distinguishes them.

**Recommendation — a permutation control, and it needs FOUR permutations,
not two.** §36.1 is the reason: at two permutations, agreement is the
majority outcome even under a total order effect, so a two-level control
would most likely return a null that means nothing. **G11 runs 4
permutations × the same seeds on TwoTier** (the arm §35.5 shows is most
exposed), matching G12's own design so the two are comparable.

Outcomes, meanings fixed in advance:

| outcome | meaning |
|---|---|
| **any permutation gives a different C1 verdict vector** | **decisive.** G11's headline is not a scheduler property, and the row must say so. More valuable than the soak itself |
| **all 4 agree, and C1 has range** | the confound does not reach G11's conclusion *at these 4 orders* — a real but bounded null, quoted with its n |
| **all 4 agree, and C1 is pinned** (§3.4) | **not scored.** Invariance is by construction and the control established nothing |
| **any permutation cannot produce a scoreable run at all** | §36.1's TwoTier result (7/20) recurring — itself a finding, reported rather than dropped, since dropping it self-selects the survivors |

**The invariance branch is conditional on C1 having range, and the
condition is the same one §3.4 puts on C4.** If C1 is all-FAIL (or
all-PASS) in every window on every seed, then it is permutation-invariant
*by construction* and the control has established nothing. **So the
permutation control is only scoreable in the same world where C4 is** —
and it is registered here with that antecedent named, not discovered
afterwards. If the pre-flight (§3) finds C1 pinned, the control is reported
as **"not scored"**, exactly as E6 requires for C4.

**And an invariance result is weaker than a difference result**, because
one alternative permutation is one draw from many. A *difference* under a
single permutation is decisive (it exhibits the confound); *sameness* under
a single permutation bounds nothing except that this particular pair
agrees. The row states which of the two it got, and never reads the second
as "declaration order does not matter".

**Form rule 2 applies and bounds the claim.** Two permutations are a
**two-level axis**: they support *"declaration order has an effect on
G11's verdict"* or *"it does not"*, and they do **not** support any
statement about how much, or which orders are worse. If the effect exists,
establishing its shape needs a third permutation and is a separate
question — breadth establishes existence, depth establishes shape.

This is affordable on this machine (§7) and it converts a standing
untested qualification into a measured one. It does **not** start §35.5's
mechanism trace, which stays out of scope (§11).

---

## 10. Commit sequence

One fidelity change per commit; full suite + `--check` after each; the
numbers that move recorded with the reason. Commits 1–3 are
**preconditions** — without all three G11 does not run at all (§4.1, §7.2,
§7.3).

| # | commit | `--check` expectation |
|---|---|---|
| **0** | **Pre-flight probe** (§3) in `scripts/`, output verbatim to `sweeps/wp9/`. **Run-aggregate metrics on short runs of the CURRENT base cell** — it cannot use per-window instruments, which do not exist until commit 5, nor the scripted scenario, which does not exist until commit 4. See the note below on what this can and cannot decide. | no code change |
| **1** | **M09 hoist** (§4.1), alone, plus a **scaling** guard test (time at N and 2N, assert the ratio). | **`--check` is structurally BLIND here — see the box below.** The real guard is a bit-identity test against the original nesting. **LANDED** (`d1b8834`): 2.9×/11.6×/23.0× at 20 k/80 k/160 k, value bit-identical |
| **2** | **Windowed ledger eviction** (§4.2) — removes the message-bookkeeping half of memory. Settles the run-level-percentile question the eviction forces. Needs its own worker-retention test: neither `_run_one_cell_s3` nor `_s4` has one. | **WILL MOVE, and that is expected.** §4.2 says percentiles are not associative, so a run-level M01 p98 built from evicted windows is a *different estimator* unless inputs are retained. The commit states which it chose and re-baselines deliberately, or retains enough to keep `--check` clean — **decided in the commit, not assumed here** |
| **3** | **Per-second timeseries fold** (§4.2) — removes the other half. M09 and M08w preserved *exactly*; M04/M19/M21 lose per-slot resolution. | **must not move for M09/M08**; M04/M19/M21 move and the commit says so |
| **4** | **Multi-window activation gate** in `sim/traffic.py` (§4.5) — one mechanism covering teleop duty cycle, waypoint pauses and the STOP drill. Strict generalisation of the single `(from, until)` pair. | **must not move** — a one-element list must reproduce the current path exactly |
| **5** | `sim/scenarios/g11.py` — the GT-7.1 scenario **and its guards**: expected-count assertions for all four scripted ingredients, **derived from the schedule** and asserted at **equality** (G9 §34.5). Settles §7.4's fleet-size and horizon-unit questions in code. | no change |
| **6** | **60 s window partition + M03w / M05w / M06w / M09w / M15w** (§4.3, §4.4), with completion pre-bucketing. **M05w carries a C3-style calibration obligation** — see below. `config/metric_panel.yml` is **not** edited. | no change |
| **7** | **Drift detector** (§4.7) — C2's instrument, per-internal (E3), with the exclusions encoded in the tool. | no change |
| **8** | `scripts/g11_campaign.py` — per-run resumability (§5), `horizon_slots` as a grid axis, LPT ordering, worker memory guard, live RSS instrumentation with a kill threshold, worker PIDs logged. **Includes a `--time-cell` pass that measures SCORING cost**, which §7.3's makespan excludes. | no change |
| **9** | **Re-run the pre-flight** (§3) with the real scenario and the real windowed instruments — the check commit 0 could only approximate. **Go/no-go on the campaign.** | no change |
| **10** | **The campaign**, including §9's 4-permutation control. Log to `sweeps/wp9/g11_campaign.log` in the repo tree, never a scratchpad (handover §5.2). | no change |
| **11** | Scoring: five clause verdicts each with its own instrument named, M14 emitted with `survival_time_ms=0` inline, the regime-map row with its seed count and CI status inline, and prediction scoring — hits **and** misses. | no change |

**Why the pre-flight is split across commits 0 and 9.** §3 asks whether
each instrument varies *across windows* of the real scenario — and neither
the windows nor the scenario exist until commits 4–6. An earlier draft put
the whole pre-flight at commit 0 and would have found it could not execute.
**Commit 0 answers the cheaper half** — on short runs of the current base
cell, do M01/M03/M05/M06/M09 sit strictly inside their bounds, and which
flows carry any M05 breach (§3.1)? That is enough to catch the pinned-M05
case before three commits of mechanism work are spent. **Commit 9 answers
the rest**, and is a real go/no-go: if C1 is pinned there, the campaign as
designed cannot score C1, C4 or the permutation control, and the right
move is to fix the scenario rather than run 30 soaks.

**The M05w calibration obligation, registered now.** Panel M05 reads
`FlowRecord.frame_completions`; a windowed M05w built from `completions`
regrouped by `message.frame_id` (via `sim/messages.py::FrameLedger.group`)
is a **different estimator**, the same way M02w differs from M02 — which
`wp9_window.py`'s own docstring flags and which control C3 exists to
calibrate. **M05 is C1's binding conjunct on this plan's own prediction
(E2)**, so shipping M05w without a C3-style calibration at the `full`
window would put the whole C1 verdict on an uncalibrated instrument.

**Commits 1, 3 and 4 each assert `--check` does not move; commit 2 asserts
it does.** Three preconditions that change cost or capacity without
changing behaviour, and one that genuinely changes an estimator — stating
which is which in advance is the point.

> **CORRECTION, found when commit 1 landed: `--check` cannot verify commit
> 1 at all, and this table claimed it could.** The regression corpus stores
> **`RunRecord`s** — `flows`, `system`, `timeseries_*`, `join_events` — and
> **no scorecard output whatsoever** (verified against
> `regression/baseline_studies_1_3.json`). M09 is a scorecard metric, so a
> change to `_m09_per_second_jain` is **structurally invisible** to
> `--check`. Its passing is *no evidence at all* for commit 1, and quoting
> it as the verification would have been **a check that never looked** —
> the same shape as G12's clean-ramp-bottom control not covering telemetry,
> and the reason that row is written the way it is.
>
> **The real guard is `sim/tests/test_m09_hoist.py`**: it diffs the hoisted
> implementation against a verbatim copy of the original nesting and
> asserts bit-identity, plus a scaling test, plus a *guards-the-guard* test
> asserting the reference is still quadratic — so the identity test cannot
> silently degenerate into comparing the shipped code with itself.
>
> **This extends to commits 2, 3 and 5–7**, to varying degrees: anything
> touching only the scoring layer is invisible to `--check`. **Commit 4**
> (`sim/traffic.py`'s activation gate) is the one where `--check` genuinely
> binds, because it changes the simulator. Each remaining commit should say
> which of the two it is *before* it lands.

## 10.1 Defects found while scoping this, all now FIXED

Scoping G11 turned up six defects in already-committed results. **None is
G11's to carry and all are landed**, so this plan cites a corrected regime
map:

| what | where | commit |
|---|---|---|
| §2.1's roll-up said "3 unrun (G9, G11, G12)" while its own G9 and G12 rows said *run* — **under a sentence asserting the counts were derived** | `wp9-regime-map.md` | `da84845`, with `scripts/regime_map_rollup.py` + a test |
| G6's protected-fleet M02 numbers were the **aggressor-excluded** row (one population short of `NON_PROTECTED_5QI = {8,9}`), and the headline claimed a pass **M20 does not support** | `wp9-plan.md` §28.1, regime map | `1cc4dbc` |
| G12's registered ordering wording had been **hardened**, not softened — §35.13's guard was one-directional — plus the undisclosed camera **under-provisioning** (3.879 vs 4.000 Mbps) | both docs, `sim/fleet.py`, `sim/parametric.py`, `sim/scenarios/g12.py` | `38248f9` |
| **G10's admissible fleet size had never been computed**; the 8/16 figure was the arm-separation boundary | both docs, `scripts/g10_admissible.py` | `9ce9787` |
| **G9: TwoTier completed 0 of 50 cold attaches**; §34.5's overlap mechanism refuted and the operational instruction changed | both docs, `CLAUDE.md`, `scripts/g9_campaign.py` | `e9f7f65` |
| M03's cadence exclusion said `duty ≤ 0.5` where the arithmetic says `0.1`, **discarding a real TwoTier breach** | `wp9-plan.md` §24.6, `scripts/wp9_part_c.py` | `e598470` |

**Two of these change G11's own framing** and are already reflected above:
G10's per-arm admissible N settles §7.4's fleet size, and the regime map's
new **§2.2** states the two-tier pattern G11's results will land beside.

---

## 11. Explicitly out of scope

Named because the handover lists them as adjacent and unstarted, and each
needs its own plan:

- **§15.5's discriminator** (two fleet profiles holding flow count and GBR
  fraction fixed).
- **§23.4's UL/DL pair** (isolating the SR-resumption cost).
- **TB-size quantisation** (`scheduler/tbs.py`; whoever takes it up starts
  at commit 2, not at scoping).
- **G9's two open threads** (TwoTier's self-selected event shortfall; the
  unexplained neighbour Δp98).
- **§35.5's declaration-order mechanism trace.** G11 *measures* whether the
  confound reaches its own conclusion (§9); it does not trace the
  mechanism, and §35.13's promotion bar is not invoked.
- **G12 clause 1**, answerable from `g12_campaign.json` without a re-run
  but needing registration first.
- **The scoring-pass waste** (§4.1): 13 of the 19 metrics `score()` computes
  are discarded on each of the 12 variation passes, and a per-axis dispatch
  would cut that to 12 single-metric calls. **A larger saving than the M09
  hoist**, and deliberately *not* taken here — the hoist alone makes G11
  runnable, and bundling an unrelated optimisation into a precondition
  commit defeats the attribution the one-change-per-commit rule exists for.
  G11's own runner sidesteps it locally by not using
  `_online_rows_for`'s variation sweep; fixing it properly in
  `sim/scorecard.py` is its own commit, on the same footing as the M04
  refinement CLAUDE.md already holds open.
- **`_strip_timeseries`'s untested `system` branch and `_run_resumable`'s
  append-mode duplicate on resume** (§5 items 2 and 5) — both real, both
  pre-existing, and neither caused by G11. Flagged rather than fixed as a
  drive-by.
