# Running log: the five-arm deployed-cell campaign with configured grants on, Linux, 2026-09-16

**Status: running document.** Appended to as steps land, problems appear and
fixes go in; nothing here is a registered claim. The results document this
feeds is `docs/results-cell-2026-09-15.md` (its §0 configuration, its
sections per guarantee); the runbook the launch followed is
`docs/runbook-deployed-cell-campaign-2026-09-15.md`. Every count below is
derived from an artefact or a log line named beside it.

## 0. Decisions that shaped this run (2026-09-15/16, in conversation)

1. **Launch the campaign now with the ConfigSched prototype as committed
   (plus two bug fixes), and redesign it afterwards.** The alternative --
   build the job-level formulation first -- would have held the four
   faithful arms' results and the cross-platform determinism check hostage
   to a redesign they do not depend on.
2. **Configured grants on for every guarantee**, not the four the previous
   script covered. "Product + CG" is the comparison (CLAUDE.md, README §8):
   every arm runs plain, `+CG` (restricted Type 2 on the heartbeat) and
   `+CGt` (period and phase from the declared traffic). Six runners lacked
   the `+CG` plumbing and gained it (§2).
3. **The two ConfigSched bugs were fixed before launch**, each its own
   commit with its own before/after on one seed (§1). The prototype is
   otherwise as first measured (`sweeps/config-sched-2026-09-15/SCORED.md`).

## 1. Code state

| commit | what | evidence it did what it says |
|---|---|---|
| `65d45ae` | ConfigSched applies the per-slot UE cap during placement; a visit is stamped only for a grant that is sent (`cap_skipped_{dl,ul}_{due,notdue}` counters) | phantom stamps N = 24: 978 UL / 11 829 DL → 0 / 0; flood robot's heartbeat 45 → 12 of 100 (the masked mechanism, not a regression) |
| `f6aa911` | ConfigSched Tier 1's PRB budget weights the special slot by its symbols (1 320 → 1 080 symbol-slots per window, = the grid's); the visit budget stays slot-counted | flood robot 12 → 97 of 100 at N = 24; `visit_budget_bound` 2 045 → 0 |
| (this run's HEAD, see `campaign.log` line 1) | six runners accept `+CG`/`+CGt` arm names: `g1_stress`, `g2_stress`, `g4_postsilence`, `g6_isolation`, `g9_stress`, `g12_stress` (+ `g12_campaign.run_ramp`'s pass-through) | manipulation check §2 |

Known non-issues at launch: the suite's two parallel-run flakes
(`test_orphan_check`, `test_m09_hoist`) pass serially and import none of the
changed modules; `parallel_audit --check` fails only on the untracked
`scripts/g11_soak.py`'s dead import (`sim.scenario_realism`), which is not
part of this campaign and not this branch's file.

## 2. The `+CG` plumbing, and the check that it is live

Pattern (from `scripts/g3_stress.py`): `base, cg = split_cg(arm)`; the
scheduler is built from `base`, the driver gets `configured_grant=cg`, the
record keeps the full name. The plain arm passes `None`, the driver's
default, so the plain rows are byte-identical to the runners before the
change by construction. G4's runner takes no `--arms`; it runs every arm
under each of `("", "+CG", "+CGt")` in one artefact (`+CGu` deliberately
excluded: `docs/results-cg-2026-09-14.md`).

Manipulation check, one seed, `PF` against `PF+CG`, same runner call
(`sweeps/…/scratch smoke2`, not kept): G1 differs on `p98_worst_ms`,
`gap_worst_ms`, `dl_mbps`, `ul_mbps`; G2 on `worst_ms`, `median_worst_ms`,
`dl_mbps`, `ul_mbps`; G4's smoke table shows `Reservation+CG − PF` at
−0.35 ms against `Reservation − PF` at −12.78 ms; G9's `warm/n3_cm0.5`
cell differs on every ε column; G12's `mixedN4` cell differs in
`per_point`. A pair that did not differ would have meant the config never
reached the driver.

**Caveat carried on every G9 `+CG` row:** `sim/configured_grant.py` has no
notion of a UE leaving and re-joining. A CG configured before a radio-link
failure persists through it (occasions reserved and skipped) and resumes on
re-attach with no fresh activation; a real gNB releases it at RLF and
re-activates after re-establishment. Not modelled; the G9 `+CG` numbers are
an upper bound on what CG does for a re-joiner.

## 3. Launch

Machine: 32 threads, 30 GB; `WORKERS = nproc − 1 = 31`. Script:
`sweeps/cell-2026-09-16-linux/run_campaign.sh` (a copy of the 09-15 script,
extended). Detached with `setsid nohup`. Steps, in order:
`g3 g3_cg g3_cgt g5 g5_cg g5_cgt g7 g7_cg g10 g10_cg g1 g1_cg g2 g2_cg g6
g6_cg g4 g9 g9_cg g12 g12_cg` (21 steps; G4's one step carries all three
suffixes).

Expected duration: the four-arm Windows steps measured G3 759 s, G5 719 s,
G1 1 198 s on 23 workers; five arms on 31 workers is about the same per
step, and the CG steps roughly triple each guarantee. Budget **5–8 h**.
This is an estimate from a different configuration (four arms, 23 workers,
Windows) and is quoted as such.

Launch record (`sweeps/cell-2026-09-16-linux/campaign.log`, line 1):
`campaign start 2026-09-16 00:07:54  workers=31  H5=10000  HEAD=88d5bd0`.
Liveness at +13 s by process state, not by the file: one parent
`g3_stress.py` and 31 spawn workers (107–191 MB each), 20 GB available.
G3's own projection: 500 runs, 19.0 M slots, ~5 min wall at 31 workers,
peak ~15 GB.

## 4. Step log

Filled in as `campaign.log` grows: one row per step, `rc`, wall seconds,
and anything that needed a fix.

| step | rc | wall (s) | note |
|---|---|---|---|
| g3 | 0 | 555 | 500 runs. **Cross-platform determinism check passed:** the four faithful arms' `A/cap4/<arm>` cells are byte-identical to the Windows artefact (`sweeps/cell-2026-09-15/aligned/g3.json`) on every field of every fleet-size point, and the campaign-wide part-2 counts match exactly (PF 0 / 37 910, Reservation 3 / 30 219, TwoTier 30 / 35 075, Proto 0 / 38 106). Windows took 759 s for four arms on 23 workers |
| g3_cg | 0 | 562 | 500 runs, five `+CG` arms |
| g3_cgt | 0 | 563 | 500 runs, five `+CGt` arms |
| g5 | 0 | 496 | 1 100 runs. Determinism: all 880 four-arm rows identical to the Windows artefact (Windows 719 s) |
| g5_cg | 0 | 520 | 1 100 runs |
| g5_cgt | 0 | 519 | 1 100 runs |
| g7 | 0 | 16 | 50 runs (N = 8, 5 s). No Windows artefact to check against |
| g7_cg | 0 | 28 | 100 runs, `+CG` and `+CGt` in one file |
| g10 | 0 | 134 | 450 runs (N = 2 … 16, 5 s). No Windows artefact |
| g10_cg | 0 | 269 | 900 runs. Reservation+CG: never-granted 94 → 0, admissible 4 → 8 |
| g1 | 0 | 887 | 1 600 runs. Determinism: all 16 four-arm cells identical to Windows (Windows 1 198 s) |
| g1_cg | 0 | 1 807 | 3 200 runs. CG changes nothing on G1 (downlink instrument); 0 breaches on every CG arm |
| g2 | 0 | 1 143 | 2 700 runs, 183 000 STOP events. No Windows artefact. Campaign miss-rate 2.2e-2 (previous cell 3.1e-3) — a cell effect on every arm |
| g2_cg | 0 | 2 390 | 5 400 runs. CG changes nothing on G2 (downlink); every arm within ±15 % of plain |
| g6 | 0 | 477 | 1 350 runs (2 s). No Windows artefact. Fails on every arm; ConfigSched = PF except the windowed GFBR floor |
| g6_cg | 0 | 979 | 2 700 runs. Every CG arm's worst flood silence ~200 ms (Reservation from 6.5–8.9 s, TwoTier from 8.2–9.6 s); G5 half unchanged |
| g4 | 0 | 131 | 450 runs, all fifteen arm names in one artefact. Every arm inside 300 ms on every bucket; PF/Proto's telemetry-after-period p98 24/20 → 72/70 ms on this cell; `+CGt` 11–17 ms on every arm |
| g9 | 0 | 708 | 1 800 runs. Axis top (7, ×1.5) and (8, ×2.0) "cell already broken" on every arm (derived from the OLD cell's G10 boundary). Informative cells passed: Proto 12, PF 11, Reservation 10, ConfigSched 9 (its cell breaks at (6, ×1.25)), TwoTier 4 |
| g9_cg | 0 | 1 461 | 3 600 runs. TwoTier 4 → 11 / 11 (cold 1.0–3.8 s → 0.12–0.25 s); ConfigSched 9 → 12 / 12 (the broken incumbent at ×1.25 was the heartbeat); cold first service +100–200 ms on every arm |
| g12 | 0 | 264 | 200 ramp sweeps (2 200 runs). Clause 4 10/10 everywhere; no arm matches `[9, 4, 2]`; TwoTier's telemetry PDB-violation 0.76 at ×1.0 (previous cell 0.000); ConfigSched 0.105 at ×1.4 → 0.82 |
| g12_cg | 0 | 531 | 400 sweeps. Telemetry indicator TwoTier 0.76 → 0.01, ConfigSched 0.82 → 0.00; class orders unchanged |
| **campaign** | 21 × rc=0 | **14 444 s = 4 h 01** | 00:07:54 → 04:08:34; 43 500 runs; no step re-run, no fix needed mid-campaign |

## 7a. Expectations scored (from §5)

| expectation | verdict | the number |
|---|---|---|
| G3 parts 1/1s/2 at 10/10 to N = 16; flood robot passes part 1 on most seeds at 24 | **hit**, and 10/10 at N = 24 on every seed; part 1s 8/10 at 24 (attach head) | §3.3 |
| G3 part 3 at the expiry ceiling from N = 12 | **hit** (93.0 → 98.8–99.2 ms) | §3.3 |
| G5 worse than PF on parts 1–2 at every N; admissible ≤ 8 | fleet bound **hit** (7); "every N" **miss** — 10/10 like PF at N = 4–7 | §5.4 |
| G1/G2 no misses the deadline arms lack, except >4 due per slot (G2 STOPs, G1 cap 2) | G1 **hit** (0 breaches; cap-2 latency traced to one-visit-per-PDB + early order); G2 **hit** (cap 2: 1 390; cap 4 parity) | §1.4, §2.4 |
| G7 clause 3 no worse than TwoTier; MFBR demand cap the only containment | **hit**, and best on every clause (0.92×, 9.0 ms) | §7.4 |
| G9 joiner served later than PF under load (withdrawn "PF-like") | **hit at the margin** (cold (6) 0.24 vs 0.10 s); the loss is its own cell breaking at ×1.25 (the heartbeat) | §8.4 |
| G10 admissible ≤ Proto's | **miss**, favourable: 10 (Proto 7, PF 8) | §9.4 |
| G12 class order like Reservation's; degradation by declaration | order **hit** (`[]` 7–8/10); declaration part unscoreable at class level | §10.4 |
| G4, G6 | no expectation; first measurements: PF-grade, G6 windowed floor 4/30 | §4, §6 |
| ConfigSched+CG: G3 10/10 to 24; G5 unchanged by CG | **hit** / **hit** | §3.5, §5.5 |

Ten registered, eight hits, two misses (one favourable). Every miss is
recorded with its number; none is edited.
## 5. Expectations registered before the artefacts are read

For ConfigSched (the prototype as committed plus the two fixes), extending
the runbook's §5. Each is scorable; a miss is recorded as a miss.

- **G3:** parts 1/1s/2 at 10/10 on the instrument robot to N = 16. The flood
  robot's own heartbeat at N = 24 is now expected to PASS part 1 on most
  seeds (97/100 on the one seed measured after the capacity fix), a
  reversal of the pre-fix expectation. Part 3 at the expiry ceiling from
  N = 12 on every arm (capacity).
- **G5:** worse than PF on parts 1–2 at every N: the plan sizes camera visits
  at `r/n` with no frame knowledge, so a frame's fragments straddle visits
  and the cap fix removed the phantom stamps that hid late visits
  (`visits_late_qfi2` 5 631 at N = 24). Admissible fleet ≤ PF's 8.
- **G1 / G2 (downlink):** no misses the deadline-tier arms do not have, EXCEPT
  where more than four robots are due in one slot: G2's simultaneous STOPs
  (`ceil(n_stop / cap)` slots) and G1 at cap 2. A first STOP that arrives
  between re-solves has no plan for up to 10 ms against a 5 ms PDB, so G2
  misses are expected to exceed PF's at cap 2.
- **G7:** clause 3 (the aggressor's own telemetry) no worse than TwoTier; the
  MFBR cap on demand is the only containment the arm has.
- **G9:** a re-joined UE's visit clock is cleared by `reset_ue`, so it is
  "due now" -- which sorts as the LEAST overdue due unit; under load the
  joiner's first service is expected LATER than PF's, not earlier (the
  runbook's §5 said PF-like; that expectation is withdrawn on the mechanism
  found 2026-09-15).
- **G10 / G12:** under overload the floors are dropped in `(priority, PDB,
  ue_id)` order, so degradation is ordered by declaration, not by class; G12
  clause order expected to look like Reservation's, and G10's admissible
  fleet ≤ Proto's.
- **G4 / G6:** no expectation registered -- first measurement.
- **`+CG` on ConfigSched:** the heartbeat leaves the dynamic path, so G3's
  instrument robot is 10/10 to N = 24 and the flood robot's heartbeat no
  longer depends on the camera visits; G5 unchanged by CG (the camera is
  never on a CG).

## 6. Results

Regenerated from the artefacts by `sweeps/cell-2026-09-15/report_tables.py`
(the directory is the argument; `--cg` adds the CG rows); filled in per
guarantee as steps land, and folded into `docs/results-cell-2026-09-15.md`.

### 6.1 G3, plain arms (`aligned/g3.json`, 500 runs)

The four faithful arms reproduce the Windows figures exactly (§4), so
`docs/results-cell-2026-09-15.md` §3 stands and gains the ConfigSched row:

| ConfigSched | 4 | 6 | 7 | 8 | 10 | 12 | 14 | 16 | 24 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| part 1 / 1s / 2 / 3 (of 10) | 10/10/10/10 | 10/10/10/10 | 10/10/10/10 | 10/10/10/10 | 10/10/10/10 | 10/10/10/5 | 10/10/10/0 | 10/10/10/0 | 10/8/10/0 | 24 / 16 / 24 / 10 |
| all parts | 10 | 10 | 10 | 10 | 10 | 5 | 0 | 0 | 0 | **10** (PF 10, Proto 10, TwoTier 6, Reservation 4) |
| p98 median (ms) | 5.2 | 9.0 | 10.2 | 14.0 | 22.0 | 93.0 | 98.8 | 99.2 | 99.0 |
| worst silence (ms) | 104 | 105 | 107 | 110 | 122 | 357 | 399 | 492 | 1 357 |
| messages missing (of 2 000) | 0 | 0 | 0 | 0 | 0 | 46 | 37 | 57 | 60 |
| protected UL (Mbps) | 16.1 | 24.2 | 28.2 | 32.2 | 40.2 | 41.7 | 41.4 | 41.4 | 40.9 |

**Expectations scored (§5, G3):** part 1 to N = 16 — **HIT**, and 10/10 at
N = 24 as well, where the runbook's own expectation (written before the two
fixes) was a failure; the flood robot's heartbeat passes part 1 on every
seed, not "most". Part 3 at the expiry ceiling from N = 12 — **HIT**
(93.0 → 98.8–99.2 ms). Not registered but worth stating: at N ≤ 10 the arm
has the lowest p98 of any arm at N = 4 (5.2 ms) and the fewest missing
messages at every N ≤ 10 (0), and its protected uplink is PF's to N = 10;
from N = 12 it carries 41–42 Mbps against PF's 43–44 and misses 37–60
messages per 2 000 against PF's 34–96 and the Proto arm's 4–68. The one
loss is part 1s at N = 24 (8/10): a 1 357 ms silence in one seed, which is
the head-of-run attach silence, not a steady-state gap (part 1 is 10/10 on
the same seeds). Campaign-wide part 2 (zero gaps ≥ 2 s over every run):
ConfigSched **PASS**, 0 of 37 998 gaps — with PF (0 / 37 910) and the
Proto arm (0 / 38 106); Reservation and TwoTier FAIL as before.

**With CG** (`cg/g3_cg.json`, `cg/g3_cgt.json`): every arm 10/10 on all four
parts to N = 24, campaign part 2 PASS on all ten CG arms (0 of 38 192–
38 197). `+CGt` p98 4.5–12 ms against `+CG`'s 16–22 ms from N = 12;
protected uplink unchanged by CG on every arm (TwoTier 8.5 Mbps at N = 24
under both). Registered expectation for ConfigSched+CG (§5) — hit.
Written into `docs/results-cell-2026-09-15.md` §3.5.

### 6.2 G5, plain arms (`aligned/g5.json`, 1 100 runs)

Four arms identical to Windows; `docs/results-cell-2026-09-15.md` §5 gains
the ConfigSched row. **Scored:** admissible fleet 7 (registered ≤ 8: hit);
"worse than PF on parts 1–2 at every N" — miss at N = 4–7 (10/10 like PF,
6–12 ms more age), hit from N = 8 (part 2 2/10, 79 ms). Load knee ×1.1,
the sharpest of any arm passing at ×1.0 (PF ×1.4) — not registered;
hypothesis in the results doc (the residual is shared equally in PRBs with
the best-effort filler, so the camera's above-GFBR offer waits). Edge axis:
parts 1–2 at every SNR but 10 dB. Not registered and the arm's one clear
win: PDU-set completeness 0.93–0.95 to N = 24 (PF 0.45, Proto 0.60) —
frames whole but late, the GFBR floor's doing.

**With CG** (`cg/g5_cg.json`, `cg/g5_cgt.json`): video statistics within
±3 ms / 0.02 of plain on PF, Proto and ConfigSched (the CG never carries
the camera); Reservation+CG admissible fleet 7 → 8, knee ×1.2 → ×1.3, and
its GT-3.3 verdict fail → pass; Proto+CG 8 → 10; part 4 at −6/−3 dB
1/10 → 10/10 on every arm. ConfigSched+CG = ConfigSched (registered: hit).
Written into `docs/results-cell-2026-09-15.md` §5.5.

### 6.3 G7 (`aligned/g7.json`, `cg/g7.json`)

First measurement on this cell. Clause 2: PF 0.67×, Reservation **1.87×**
(fail), TwoTier 1.05×, Proto 0.82×, ConfigSched 0.92×. Clause 1: TwoTier
fails (A's heartbeat 960 bps = 4 % of contract; camera p98 120 ms); the
rest pass. Clause 3 passes everywhere. **ConfigSched best on every clause**
(contained 0.92×, A telemetry 31.5 ms, A camera 30.3 ms, B telemetry
9.0 ms). Registered ("clause 3 no worse than TwoTier; MFBR demand cap the
only containment") — hit, and containment beats PF's. CG: TwoTier's
clause 1 fixed (24 000 bps at 61 ms), Reservation's clause 2 1.87 → 1.18×
with A's camera p98 35 → 84 ms as the cost. Written into
`docs/results-cell-2026-09-15.md` §7.

### 6.4 G10 (`aligned/g10.json`)

Admissible fleet PF 8 / Reservation 4 / TwoTier 5 / Proto 7 /
**ConfigSched 10** (previous cell 12 / 6 / 7 / 10 / —). Registered
("≤ Proto's") — **miss**, favourable: the GFBR floors are M07's statistic
(worst flow 0.981 at N = 10 vs PF 0.955). Past the boundary M08 0.543 /
0.007 at N = 12 / 16 — whole robots' floors dropped by `ue_id`, the
registered degradation-by-declaration mechanism, showing on G10 before
G12. Written into `docs/results-cell-2026-09-15.md` §9.

### 6.5 G1 (`aligned/g1.json`)

Four arms identical to Windows. ConfigSched: 0 breaches at both caps and
both axes (registered "no misses" — hit), but the slowest arm at cap 2:
10.5 ms median at N = 4 (PF 3.5, deadline arms 3.0–3.5), 20.5 at N = 24,
flat 10.5–13 across the load axis. First hypothesis (a fixed timer, the
10 ms re-solve) **refuted by a one-seed probe**: the wait is spent
*early* (922 of 924 slots) because the plan gives a 50 ms source one visit
per 100 ms window (`⌈W/PDB⌉`), and early units sort by next-due, where
the 20-slot fleet-DL flows always win; at cap 2 the two DCIs go to them
(514 of 831) or the firmware download takes the PRBs first (317). The v2
rules L7 (interval below the period) and table placement are the fix.
Written into `docs/results-cell-2026-09-15.md` §1.

### 6.6 G2 — mechanism probe run BEFORE the artefact (one seed, N = 12, two STOPs)

Scratch probe on the prototype, cap 4 and cap 2, instrumenting the two STOP
flows (DL 5QI 85, PDB 5 ms = 10 slots) per DL slot. Every STOP that has a
plan is granted within 1 slot (cap 4) or ≤ 3 slots (cap 2), all inside the
PDB. The expiries are the arrivals that have **no plan**: a STOP arriving
between Tier-1 re-solves is class "no share", sorts after every planned
unit, and the DL flood's planned visit takes the slot's PRBs first; the
next re-solve is up to 10 ms away. Cap 2: 32 of 34 expiries are no-plan
arrivals. **Correction after the artefact:** the probe also reported 11
expiries at cap 4, but the artefact shows ConfigSched at parity with every
arm at cap 4 (224 vs 203–224 campaign-wide; 3/600 vs 3/600 in the probed
cell), so the probe's expiry detector over-counts — a HARQ-masked gap in
the flow's reported backlog (TB pending, then a retry) reads as an
expiry to it. What the probe measures reliably is the *state at arrival*;
its expiry counts are not quotable. The one-change fix for the prototype
stands (a contracted flow with backlog and no plan is due now, not
leftover); v2 has no between-re-solve state to be caught in.

**Scored (artefact):** ConfigSched cap 2 1 390 misses (PF 748, deadline
arms 247–263) — the registered cap-2 loss, **hit**; cap 4 at parity
(224), the registered "no misses the deadline arms do not have except
where more STOPs than DCIs are due" — **hit**. Every arm's cap-4 misses
are ~10× the previous cell's (BLER² vs BLER³ reading, hypothesis in the
results doc). Written into `docs/results-cell-2026-09-15.md` §2.

### 6.7 G9 (`aligned/g9.json`)

The axis's top two points are past this cell's capacity on every arm
(7–10 broken seeds), so twelve cells are informative. ConfigSched passes
9 of 12; its three losses are its own cell breaking at (6, ×1.25) on
8–10 seeds (PF, Reservation, Proto: 0) — the G5 load knee from the
joiner's side, not a join failure. Where its cell holds, the joiner is
served like PF's (cold 0.10–0.13 s, RLF 1.04–1.05 s, warm 0.00).
Registered ("joiner later than PF under load") — hit only at the margin
(cold (6) 0.24 vs 0.10 s). Written into `docs/results-cell-2026-09-15.md`
§8.

**With CG** (`cg/g9_cg.json`): ConfigSched's (6, ×1.25) cells read
0 broken seeds, so the unavailable incumbent was the heartbeat — §8.4's
"G5 load knee" attribution corrected to the telemetry (the G6 windowed-
floor shape). TwoTier's G9 becomes PF-like under CG (11 of 12). Cost on
every arm: cold-attach first service +100–200 ms (the joiner waits for
its CG occasion); after RLF `+CGt` +0.06–0.16 s (the model's CG persists
through RLF — the recorded caveat). Written into §8.5.

### 6.8 G12 (`aligned/g12.json`)

Clause 4 10/10 on every arm; the ordering now partly scoreable (GBR
classes break inside the ramp on four arms) and no arm matches
`[9, 4, 2]` — PF sacrifices video then camera while the background keeps
12 Mbps; Reservation alone breaks nothing (`[]` 10/10). Leading
indicator: TwoTier's telemetry PDB-violation 0.76 at ×1.0 on this cell
(0.000 before). ConfigSched: `[]` on 7–8 seeds, `[2]` on the rest (class
order like Reservation's — registered, hit); telemetry violation 0.105 at
×1.4 → 0.82 at ×2.0 (the heartbeat's one visit per window losing its slot
as the ramp grows the video/camera visits); "by declaration" unscoreable
at class level. Written into `docs/results-cell-2026-09-15.md` §10.

## 8. ConfigSched2 — the increments (running)

The arm `ConfigSched2` (`sim/baselines/config_sched2.py`) starts as a
byte-identical copy of the prototype (increment 0, asserted on a full G3
run) and takes one fidelity change per commit toward the v2 formulation.
Each increment is measured by `sweeps/cs2-increments/run_increment.sh`
(the campaign's G3, G7, G10, G2, G1, G5, G6, G9, G12 steps, same flags
and seeds, one arm, ~20 min on 31 workers) into `sweeps/cs2-increments/
incN/`, and read by `sweeps/cs2-increments/compare.py`, which prints the
campaign's `ConfigSched` against the increment on every guarantee's
deciding statistics. An increment is kept if it moves what it was built
to move and nothing else moves the wrong way; a regression is recorded,
not tuned away.

Order, by evidence weight from the campaign:

| # | change | what it is built to move | expected effect, registered before the run |
|---|---|---|---|
| 1 | a contracted flow with backlog and no plan is due now (class 0), not leftover | G2 cap 2 (1 390 misses; the no-plan STOPs) | G2 cap 2 → within ~2× the deadline-tier arms (≈ 250–500); cap 4 unchanged; nothing else moves beyond noise |
| 2 | visit interval ≤ PDB/2 for a contracted flow (L7, undeclared form) | G1 cap 2 (10.5 ms), G12's telemetry indicator (0.82), G9's broken incumbent at ×1.25, G3 part 1s at N = 24 | G1 cap 2 p98 → ≤ 6 ms; G12 M02 at ×2.0 → < 0.3; G9 cold (6) → PASS; cost: more visits per window, G10 admissible may fall by 1 |
| 3 | residual: contracted above-floor demand before best-effort | G5 load knee (×1.1), G6 windowed floor (4/30) | G5 knee → ≥ ×1.3; G6 floor → ≥ 9/30; cost: bg delivered in G12 falls |
| 4 | floors dropped most-expensive-first, shortfall shared within a class (`z_i`) | G10 past the boundary (M08 0.007 at N = 16), G12 order by declaration | G10 M08 at N = 16 → ≥ 0.4; admissible unchanged |
| 5 | harmonic periods and table placement replace the due order (L4, tracks) | G1's early-order loss, all cadence tails | structural: max gap = T_i; every G3/G9 cadence statistic ≤ the Proto arm's |

| increment | commit | result | kept? |
|---|---|---|---|
| 0 copy | `592d587` | identical on G3 N = 10 (summaries, counters) | yes |
| 1 unplanned contracted flow first, shortest PDB | `10efeb6` | "due now" (class 0) built first and refuted on the seed (32 of 34 expiries remained: the least overdue of the due units, the fleet's visits bunched); ahead-of-planned by PDB: G2 probe expiries 34 → 2. **Measured (`inc1/`, 9 steps, all rc 0):** G2 cap 2 **1 390 → 317** (deadline arms 247–263, PF 748; registered "within ~2×" — hit), cap 4 224 → 192; STOP axis cap 2 22/78/124/318 → 1/8/20/108; fleet axis 58–295 → 22–47. G3, G5 (bar one seed's part 3 at −6 dB), G7, G10, G6, G9, G12 identical. G1 cap 2: N = 14 13.25 → 13.0 ms, N = 16 15.5 → 16.75 (fleet-DL messages now ahead of `cmd_vel`'s early visit); boundaries unchanged | **yes** |

## 7. After the results: ConfigSched iteration

The redesign to build once the table is complete, from the 2026-09-16
design conversation (to be written into `docs/config-scheduler-handoff.md`
§8c): the lifted formulation -- per flow a harmonic visit period `T_i`,
bytes per visit `b_i`, visits per job `k_i`, a track `τ_i` with budget
`P_τ`, an honoured-floors indicator `z_i`; density `Σ z_i / T_i ≤ cap` made
SUFFICIENT by harmonic periods (Kraft), per-slot PRB feasibility by track
budgets, frame completion linear in `(k_i, b_i)`; placement a table.
Measured first on G3 N = 10 / 24 and G2, one fidelity change per commit,
against this campaign's artefacts on the same seeds.
