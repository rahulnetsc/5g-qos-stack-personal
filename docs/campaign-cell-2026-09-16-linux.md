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

**Increment 5 design, registered 2026-09-16 04:50 before it is built** (the
v2 core; increments 2–3 showed the due-order under contention is what
binds, and increment 4 does not touch it, so 5 comes next):

- *Tier 1 adds a period.* For every flow with visits `n_i`, `T_i` = the
  largest power of two ≤ `W / n_i` in slots (so visits ≥ `n_i`); then
  spare density is spent shortening `T_i` for contracted flows, shortest
  PDB first, while `Σ_i 1/T_i ≤ cap` per direction (the M-6 cap as a
  density — Kraft). Under overload the residual visits are cut first
  (largest density, best-effort first) until the density fits; floors
  are cut last, in the existing priority order (increment 4 will change
  that order; not here).
- *Tracks.* `cap` tracks per direction; flows assigned coarsest period
  first by the canonical Kraft construction (a free block `(r, T')` with
  `T' ≤ T` is split into `(r, 2T')`, `(r + T', 2T')` until modulus `T`);
  first-fit over tracks. Harmonic sizes make first-fit exact whenever the
  density fits.
- *Tier 2 is the table.* In slot `t`, each track's mapped flow (residue
  `t mod T_i`) is placed first, sized as increment 3 sizes a visit; a
  mapped slot with no symbols for the direction slips to the next slot
  that has them (the driver's own alignment rule); a mapped flow with
  nothing reported frees its DCI. Freed DCIs go, in order, to a flow owed
  a slipped or pre-empted visit, then an unplanned contracted flow
  (increment 1's rule), then best-effort by the r/n share. The visit
  clock, EDF, the early/no-share classes and the `ue_id` tie-break are
  deleted.
- *Expectations.* G3: flood robot 100/100 at N = 24 (it holds a residue
  class no other flow can take), worst silence ≤ `T` + a slip at every N
  (≤ Proto's 199–494 ms), campaign part 2 PASS. G1 cap 2: `cmd_vel`'s
  wait ≤ its `T`; with two driven robots and fleet DL at N = 4 the
  density is small, so `T` ≤ 8 slots and p98 ≤ 6 ms. G2: unchanged
  (increment 1's rule survives as the freed-DCI order). G5, G7, G10:
  within noise — the plan's bytes do not change. G9 (6, ×1.25): the
  incumbents' heartbeats hold their classes — PASS. G12 M02 at ×2.0 <
  0.3. Cost: at N = 24 UL, 72 contracted flows on a cap of 4 give a mean
  density of 1/18, so `T` ≈ 32 slots (16 ms) is the structural wait
  bound; p98 at N = 24 will be ~16–20 ms, not the 5 ms of small fleets.

| increment | commit | result | kept? |
|---|---|---|---|
| 0 copy | `592d587` | identical on G3 N = 10 (summaries, counters) | yes |
| 1 unplanned contracted flow first, shortest PDB | `10efeb6` | "due now" (class 0) built first and refuted on the seed (32 of 34 expiries remained: the least overdue of the due units, the fleet's visits bunched); ahead-of-planned by PDB: G2 probe expiries 34 → 2. **Measured (`inc1/`, 9 steps, all rc 0):** G2 cap 2 **1 390 → 317** (deadline arms 247–263, PF 748; registered "within ~2×" — hit), cap 4 224 → 192; STOP axis cap 2 22/78/124/318 → 1/8/20/108; fleet axis 58–295 → 22–47. G3, G5 (bar one seed's part 3 at −6 dB), G7, G10, G6, G9, G12 identical. G1 cap 2: N = 14 13.25 → 13.0 ms, N = 16 15.5 → 16.75 (fleet-DL messages now ahead of `cmd_vel`'s early visit); boundaries unchanged | **yes** |
| 2 visit interval = PDB − 6 slots (the retry gap) | see git log | telemetry and `cmd_vel` 1 → 2 visits/window, fleet DL 10 → 15, camera 1. G1 probe BEFORE the run: `cmd_vel` due in 175 of its waiting slots (2 before) and its wait unchanged at p98 13 slots — the DCIs go to unplanned fleet-DL messages (increment 1, PDB 10 ms), so the registered G1 ≤ 6 ms is predicted a miss; the uplink targets (G12 indicator, G9 (6)) go to the measurement `inc2/`. Correction to `5092c09`'s message: the suite before it was 1 569 passed, 1 failed — `test_m09_hoist`'s cost-growth ratio under 24 workers, which passes serially on the idle box (7 s, twice tonight); not "green" as written. **Measured (`inc2/`, 9 steps rc 0): NOT KEPT.** G3 campaign part 2 PASS → **FAIL** (1 gap ≥ 2 s: a 4 164 ms silence on one seed at N = 24), part-2 boundary 24 → 16, messages missing at N = 14/16/24 37/57/60 → 63/81/123, worst silences at N = 7/10 107/122 → 198/198 ms; G7 A-telemetry p98 31.5 → 47.8, B 9.0 → 12.8; G12 M02 at ×2.0 0.82 → 0.88 (registered < 0.3: **miss**); G9 (6, ×1.25) still broken (b7; registered PASS: **miss**); G1 cap 2 N = 24 20.5 → 9.25 ms, N = 4–8 unchanged 10.5 (registered ≤ 6: **miss**, as the probe predicted); G2 301 (noise). **Mechanism, traced to the line:** `bytes_per_visit = ceil(r_i / n_i)` and `want = min(bytes_per_visit, reported)` — two visits per window halve the heartbeat's visit to 150 B for a 300 B message, so every message is split across visits 50 ms apart, delivery rate = arrival rate with no slack, and one missed visit grows the backlog without bound; `cmd_vel`'s 100 B message still fits its 100 B visit, which is why G1 alone improved. Left in the tree (a revert would lose the attribution): increment 3 stacks the companion rule — a visit carries what the flow reports, up to a cap-th of the slot — so inc3 − inc2 isolates the sizing and inc3 − campaign measures the pair | **not on its own** |
| 3 a contracted visit carries what the flow reports, up to a cap-th of the slot (on top of 2) | see git log | unit test: the 300 B heartbeat rides one grant again with a 2-visit plan. Probe BEFORE the run, N = 24 seed 1826701614: instrument robot 100/100, worst gap 104.5 ms (prototype 117.5); **flood robot 71/100 (prototype 97)**, 294 late telemetry visits — two visits per robot per window double the due-unit load on the cap and the `ue_id` tie-break makes the last robot lose. Registered: G3 campaign part 2 back to PASS and part-2 boundary 24 (the sizing fixed the unbounded backlog); G3 messages missing at N = 24 expected WORSE than the campaign's 60 (probe: the flood robot's loss); G1 cap 2 N = 24 ≈ 9 ms kept; if G3 regresses, the pair is not kept and the due-order is the finding — increment 5's table placement is the next change, not increment 4. (The suite before `e7fd1cf` was fully green, 1 571 passed — its message says the timing flake fired; it did not). **Measured (`inc3/`, 9 steps rc 0): NOT KEPT.** G3 campaign part 2 FAIL (3 of 37 873; worst silence 2 862 ms at N = 24), part-2 boundary 16, part-1s 14, messages missing at N = 12/14/16/24 46/37/57/60 → 30/55/78/159; G7 A-telemetry p98 31.5 → 54.2; G12 M02 at ×2.0 0.82 → 0.81 (registered < 0.3: miss); G9 (6, ×1.25) still broken (b6); G1 cap 2 N ≥ 10 improved (N = 24 20.5 → 8.5 ms), G2 285. Against inc2 alone the sizing made G3's misses at N = 24 worse (123 → 159): the two-visit plan's contention, not the visit size, is the loss. **Both increments reverted** (`git revert e7fd1cf 5092c09`); ConfigSched2 stands at increment 1. The finding they leave: under a due-order with a `ue_id` tie-break, planning more visits per robot is more contention for the robots at the end of the order — the table (increment 5) replaces the order; the interval rule returns inside it as a period, not as extra due units | **no** |
| 5 harmonic periods + Kraft tracks + table placement (on increment 1) | see git log | Three forms before the run, each caught by a probe: (a) residues over ABSOLUTE slots — 19 684 pattern slips, owed backlog snowballed, flood robot 76/100; (b) direction-indexed slots — slips gone but `mapped_visit_missed` 32 992 vs 11 866 served: promised units sized in bytes rounded up to PRBs let four exceed the slot, and owed-before-mapped displaced the next slot's visits; (c) per-unit PRB cap + mapped before owed — misses 3 647. **Probes on (c), seed 1826701614:** G1 N = 4 `cmd_vel` p98 cap 2 **10.5 → 5.5 ms** (registered ≤ 6: on track), cap 4 3.5 → 3.0; G2 N = 12 cap 4 misses 1, cap 2 12 (increment 1: 2 — worse); G3 N = 24 instrument 99/100 (prototype 100), flood robot 93/100 (97); N = 10 both 100/100, worst gaps 188 / 177 ms (prototype 113 / 122) — the mapped visits are every ~7 ms, so the tail is not the table's cadence; HARQ masking of a UE with a camera TB in flight is the suspect, untraced. **Measured (`inc5/`, 9 steps rc 0): NOT KEPT AS-IS, kept as the base.** Hits: G3 part 1s boundary 16 → **24**, worst silences at N = 12/14/16/24 357/399/492/1 357 → 198/342/300/295 ms (registered ≤ Proto's 199–494: hit), campaign part 2 PASS; G9 informative cells **9 → 12** (the ×1.25 cells pass, b2–b4; registered: hit); G12 M02 at ×1.4/×2.0 0.105/0.822 → **0.000/0.201** (registered < 0.3: hit), orders `[4, 2]` 10/10; G1 cap 2 N = 4 **10.5 → 5.5 ms** (registered ≤ 6: hit), N = 24 20.5 → 15.5; G6 UL A/B 225/254 → 226/262; G7 clause 3 9.0 → 6.0. Misses, each to a line: **G2 cap 2 1 390 → 2 297**, cap 4 224 → 251 — an unplanned STOP (rank 2, PDB 5 ms) waits behind fleet-DL messages mapped on their tracks (rank 0, PDB 10 ms): increment 1's shortest-PDB-first was lost in the rank list; **G7 clause 2 0.92 → 1.04×, A-telemetry p98 31.5 → 80.5** — leftover service (rank 4, sized at a cap-th of the slot) feeds the over-driven camera past its MFBR-capped plan; **G3 part 3 boundary 10 → 8** (p98 at N = 6–8 9/10/14 → 27/31/38 ms, missing at N ≥ 14 up to 157) and **G10 admissible 10 → 8** (M08 0.981 → 0.965 at N = 10; past the boundary better, 0.543/0.007 → 0.728/0.076) — the heartbeat waits for its own slot behind mapped best-effort (increment 6's finding). G5 mixed: ages better at N ≤ 7, N = 8 part 1 10 → 6, edge 10 dB 8 → 10/10 | **base** |
| 6 (registered 05:20, before 5's result) leftover contracted ahead of mapped best-effort in the DCI order | — | The N = 10 tail probed while 5 ran: at the heartbeat's 750 mapped slots per robot, HARQ/join masking is **1 %** (suspect refuted), "nothing queued" 57–71 %, visible 23–27 %, BSR-invisible (SR path) 6–14 %. The heartbeat's period is 16 or 64 direction-slots (13–53 ms), not ~7: the cameras' residual visits take the density first. Between mapped slots an arrived heartbeat is rank 4 (leftover contracted) behind rank 3 (mapped best-effort), so it waits for its own slot while the fillers use theirs; the prototype served it at the first free DCI. Expected: G3 worst gaps at N ≤ 10 back to ≤ the prototype's (113 / 122 ms) with G1/G2 unchanged; best-effort throughput in G3's protected-UL column unchanged (fillers are not protected) | pending |
| 6 built as one rule: contracted by PDB whatever the claim (`e9d2e2a`) | `e9d2e2a` | Probes: G2 N = 12 cap 2 misses 12 → **1**, cap 4 0; G1 N = 4 cap 2 `cmd_vel` p98 3.5 / 5.0 ms; G3 N = 24 instrument 100/100, flood robot 93 → **98**/100; G3 N = 10 both 100/100 but worst gaps ~190 ms and **per-robot heartbeat p98 73–96 ms** (prototype 22): 40 370 of 42 704 UL grants are crumbs. Traced to increment 3's sizing carried into the table — `max(share, per_visit_cap)` inflates a mapped camera visit to 1 530 B / 27 PRBs against a ~800 B plan share, four of them take 108 of 106 PRBs, and a leftover heartbeat gets a 2-PRB crumb that splits its message; the same over-service is G7's 1.04×. Registered as increment 7: a promised unit is sized to its plan share with the deployed `min_rb` grant as the floor, no per-unit PRB cap. (Suite before `e9d2e2a`: 1 569 passed, 2 failed under xdist — the message says green; `test_m09_hoist` and all six `test_orphan_check` cases pass serially, 7 of 7.) **Measured (`inc6/`, 9 steps rc 0): KEPT.** G2 cap 2 **1 390 → 245** (deadline arms 247–263, PF 748), cap 4 224 → 205; G3 part 1s boundary 24, worst silence ≤ 242 ms at every N (prototype 1 357 at N = 24), missing at N = 12/14/16/24 46/37/57/60 → 0/13/21/43, campaign part 2 PASS; G9 **12/12**; G12 M02 at ×2.0 0.82 → 0.21; G1 cap 2 10.5–20.5 → 5–15 ms, cap 4 ≤ 8.5; G6 UL/DL A/B 226/266, 228/267. Regressions, all on the crumb line: G3 part 3 boundary 10 → 8 (p98 at N = 6/7/8 9/10/14 → 27/46/35), G7 clause 2 0.92 → 1.03× with A-telemetry p98 55.2, G10 admissible 10 → 8 (M08 0.971 at N = 10; past the boundary 0.760/0.424 against 0.543/0.007) | **yes** |
| 7 the cap-th of a slot in PRBs first (`4fe0dc3`) | `4fe0dc3` | 40 296 of 40 370 crumbs at N = 10 were the camera's — 4 × 27 = 108 PRBs of 106 — and the per-unit PRB cap of increment 5 capped the fourth at 26 PRBs = 1 501 B against a 1 530 B want (the same crumb from the other side). Now `(PRB // cap)` PRBs first, bytes second, in Tier 1 and Tier 2; the PRB cap removed. Seed 1826701614, N = 10: crumbs 40 370 → 8 643 (S-slot visits), mapped served 2 503 → 18 309. **The heartbeat's legs** (generation → first slot reported → grant → complete): total p98 73.5 → 51.5 ms, p50 14 → 6.5; visible → grant 0–2 ms always; the tail is entirely generation → visible (p98 51.5, max 81). Suite 1 571 passed. **Measured (`inc7/`, 9 steps rc 0): KEPT as the base, with two attributed regressions.** Against the prototype: G3 part 1s boundary **24**, worst silence ≤ 294 ms at every N (1 357), messages missing 46/37/57/60 → 0/6/12/42 at N = 12/14/16/24, campaign part 2 PASS; G2 cap 2 **260** (1 390), cap 4 168 (224); G1 cap 2 **5–15 ms** (10.5–20.5); G9 **11**/12; G12 M02 at ×1.8/×2.0 0.694/0.822 → **0.030/0.078**, the lowest of any build; G10 admissible **10** (increment 6 lost it to 8; recovered), M08 past the boundary 0.759/0.443 against 0.543/0.007. Regressions, both traced to one line — `want = min(reported, max(share, per_visit_cap))` gives every contracted flow a floor of a cap-th of the slot whatever its plan says: **G7 clause 2 0.92 → 1.08×** (the over-driven camera served past its MFBR-capped plan, A-telemetry p98 70.0) and **G5 admissible 7 → 6, load knee ×1.1 → ×1.0**. G3 part 3 boundary 8 (N = 10 is 8/10; N = 12 is 10/10 where the prototype was 5/10) | **yes** |
| 8 (keepalive form) — refuted, not built into the module | scratch only | A per-UE keepalive track (`min_rb` every 16 direction-slots) **never fired**: its key `(ue, -1)` is the UL unit key, so a UE with any reported flow already has that unit and gets no keepalive; the 14 that were created all lost the cap (they rank last among contracted) and `keepalive_grants` stayed 0. The visibility tail was unchanged-to-worse (p98 51.5 → 89.5). Dropped as built. The registered expectation asked for inter-grant ≤ K and heartbeat visibility ≤ 15 ms; neither was testable because the mechanism did not run — recorded as a mechanism-never-reached, not as a negative result about keepalives |
| 9 (registered 06:05) a planned contracted visit carries its PLAN SHARE, not a cap-th floor | pending | Increment 3 added `max(share, per_visit_cap)` to stop a two-visit plan halving a 300 B message; increment 2 (the two-visit plan) was then reverted, so the floor now only inflates: the telemetry's plan share IS its 300 B message, while a camera's share is ~800 B and the floor hands it 1 530. Change to `want = min(reported, share)` for a planned contracted flow, keeping `per_visit_cap` as an upper bound and `reported` for an unplanned one. Expected: G7 clause 2 back to ≤ 0.95× with A-telemetry p98 ≤ 40 ms, G5 admissible back to 7 and the knee to ×1.1, G3/G2/G9/G12/G1 unchanged within noise (the heartbeat's share already carries its whole message). If G3 part 3 or the silences regress, the floor was load-bearing for the heartbeat too and the pair is the finding. **Probes (seed 1826701614):** G7 through its own runner, 10 seeds — clause 2 1.08 → **1.04×**, A-telemetry p98 70.0 → **57.8 ms**, A camera 46.9, B telemetry 6.0, UL util 0.892: the floor was **half** the over-service, and against the prototype (0.92×, 31.5 ms) G7 is still worse. G3 N = 10 — crumbs 8 643 → 5 773, mapped served 18 309 → 22 920, 100/100 delivered, but generation → visible p98 51.5 → **71.5 ms**, the regression the expectation named. Suite 1 571 passed. **Measured (`inc9/`, 9 steps rc 0): KEPT, and it refutes its own premise for G5.** Expectations scored: G7 clause 2 ≤ 0.95× with A-telemetry p98 ≤ 40 ms — **miss** (1.04×, 57.8 ms), though both improved from increment 7's 1.08× and 70.0; G5 admissible back to 7, knee ×1.1 — **miss**, and the sharper result is that **neither moved at all** (6, ×1.0, identical to increment 7), so the cap-th floor was not G5's cause and the remaining candidate for G5 *and* the rest of G7 is the same one: placement over-service (increment 10); "G3/G2/G9/G12/G1 unchanged" — **G3's part-3 boundary 8 → 10** and **G9 11 → 12**, better than registered, with G12 at ×2.0 0.078 → 0.071, G2 260 → 291 and G1 flat. Recorded against it, both past the scored boundaries: G3 messages missing at N = 14/16/24 6/12/42 → **118/141/183** and G10's M08 at N = 16 0.443 → 0.175. Against the frozen prototype the arm now stands: G3 part-1s boundary **24** (16) and part-3 boundary **10** (10), G2 cap 2 **291** (1 390), G9 **12/12** (9), G12 ×2.0 **0.071** (0.822), G1 cap 2 **5–15 ms** (10.5–20.5), G10 admissible **10** (10) — and worse on G7 (1.04× against 0.92×) and G5 (6 / ×1.0 against 7 / ×1.1) | **yes** |
| **D1 (ProtoRRageD2, registered 2026-09-16, group E)** a GBR-deficit tie-break beneath the age order | pending | Proto's only weak group. Diagnosed and gated first (`docs/guarantee-groups-2026-09-16.md` §5): at G10 N = 8 every protected GBR flow is the same 4 Mbps camera, and Proto spreads identical contracts by 0.096 median / 0.230 max against PF's 0.023 / 0.030, worst flow 0.917 median / 0.782 min against PF's 0.988 / 0.982. Sizing refuted (identical contracts), channel refuted by construction (`snr_spread_db = 0` gives every UE 20.0 dB). Placed BENEATH `-age`, because the deficit's median sample is 0 bytes (37 450 samples, 3 848 distinct, none at the cap) and a term above the age would be inert on most slots and disruptive on the rest. **Expected:** G10 admissible 7 → 8 with the spread at or under PF's 0.03 and the worst flow ≥ 0.95; groups A/B/C/D/F unchanged within noise — the tie-break only separates candidates the age order already ties. **Falsified by:** the spread not narrowing (the deficit is not the missing signal), or G3's boundary dropping below 10 (the tie-break is reordering more than ties) |
| **10 — REFUTED before measurement, premise false, reverted** | not committed | Built twice and killed by its own manipulation checks, without spending a six-group run. **v1 keyed on the PLAN** (`n_visits × bytes_per_visit`): fired 6 015 times on G7 and every one was the 300 B TELEMETRY — a small flow finishes its plan early each window and was demoted for the rest of it, while the over-driven camera, plan already MFBR-capped and backlog unbounded, never reached its plan and was never demoted. Exactly inverted. **v2 keyed on the CONTRACT** (MFBR × W): fired **zero** times — no flow is served twice its guaranteed rate inside a 100 ms window. **v3 keyed on GFBR × W:** also **zero**. The diagnosis that ended it: on G7 the cameras peak at **14.7–18.8 kB served per window against a 50 kB GFBR allowance (ratio 0.29–0.38)** — at N = 8 this cell cannot give a 4 Mbps camera its guarantee inside one window, so **no within-window contract threshold can ever fire**. G7's 1.04× is therefore over-service accumulated ACROSS windows, not within one, and any placement-side containment must compare against a running entitlement (bytes owed since the run began, or an EWMA). That is a different mechanism and gets its own registration. Reverted to increment 9; `sim/tests/test_config_sched2.py` green |
| ~~10 (registered 06:20) a contracted flow that has received its planned bytes this window drops to best-effort rank~~ for the rest of it | pending | The other half of G7. The table's DCI order (increment 6) puts every contracted flow with backlog ahead of every best-effort unit, so once the mapped visits are served a contracted flow keeps taking free DCIs — unbounded extra service, which is why the over-driven camera exceeds its MFBR-capped plan (1.04× against the plan's 1.00) while A's telemetry waits. This is v2's L3 upper bound (`r_i ≤ MFBR · W`) enforced at PLACEMENT, not only in the plan: count bytes served per (flow, window) and rank a flow that is over its plan as best-effort leftover. Expected: G7 clause 2 ≤ 0.95× with A-telemetry p98 back under 40 ms; G5 admissible back to 7; G3/G2/G9/G12 unchanged (their instruments never exceed their plans); G10 unchanged or better (the M08 floor is the plan) |
| 8 (masking form) — refuted on the seed, not built into the module | scratch only | "A mapped slot read empty while the UE is masked by our own grant ≤ 2 slots ago is owed": only 3 912 of ~27 000 empty mapped slots qualify, and owing them made the visibility tail WORSE (p98 51.5 → 87). Dropped. **Traced instead by inter-grant gaps to the instrument robot: increment 7 max 100 ms (p98 10), prototype max 22.5** — the table gives every free DCI to contracted units, so a UE whose contracted flows momentarily read empty gets no grant, no BSR rides, its reports go stale, and the SR does not fire while the filler keeps its queue non-empty. | **no** |
| 8 (keepalive form, registered 05:55) a per-UE keepalive track: a `min_rb` grant every K direction-slots whether or not anything is reported | pending | The §8a "common visit floor", and what the deployment's `min_grant_prb = 5` was chosen for ("so BSRs keep being reported"). K = 16 direction-slots (13 ms), lengthened by the density fit under overload, skipped if the UE was granted within the mask window. Expected: inter-grant max to any UE ≤ ~K; heartbeat generation → visible p98 ≤ ~15 ms; G3 part 3 boundary back to 10 with p98 at N = 6–10 within ~2× the prototype's; G10 back toward 10; cost: density 1/K per UE (1.5 of 4 at N = 24), so camera periods lengthen under overload — G5 at N ≥ 12 may lose a little | pending |

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



### 8.x  D1 (`ProtoRRageD2X1`) — MEASURED AND REJECTED, 2026-09-16

**The change.** `ProtoRRageD2` plus a GBR-deficit tie-break *beneath* the age
order (`deficit_tiebreak=True`). Registered against group E (G10), whose
diagnosis said the age order alone cannot tell two equally-stale UEs apart when
one is further behind its contract.

**Two runner bugs had to be fixed before the result was valid**, and they are
recorded because they voided a result that was briefly reported as eight-of-nine
clean: `g3_stress._resolve_arm` and `g9_stress._arms` each kept a PRIVATE copy
of the arm table and raised on a name only `proto_arms` knew. Both steps died
in ~1 s while the other seven scored — a partial result under an arm name the
log still carried. Both now delegate to `proto_arms.resolve_arm`, verified
identical on all 19 pre-existing arm names.

**It hits its target and loses four other groups.**

| group | statistic | ProtoRRageD2 | D1 | verdict |
|---|---|---|---|---|
| **E (G10)** | admissible fleet | 7 | **8** | **win** |
| **E (G10)** | M08 median at N=10 | 0.661 | **0.933** | **win** |
| **B (G3)** | part-3 passes per N | 10 10 10 10 10 9 9 6 0 | 10 10 10 10 10 **7 2 1** 0 | **regression** |
| **B (G3)** | worst silence | 494 ms | 499.5 ms (mid-N 199→297) | regression |
| **C (G5)** | gt31 N=10 | 10/9/3/10, 42 ms | **5/2/0/10, 125 ms** | **severe regression** |
| **C (G5)** | gt31 N=12 | 9/4/2/10, 74 ms | **0/0/0/10, 146 ms** | **severe regression** |
| **C (G5)** | load knee | none | 1.3 | regression |
| **D (G7)** | clause 2 camera/MFBR | 0.82x | 0.66x | regression |
| **D (G7)** | A telemetry p98 | 74.0 ms | 86.8 ms | regression |
| **A (G2)** | cap-2 missed STOPs | 263/18300 | 305/18300 | regression |
| **F (G9)** | informative cells passed | 12 of 12 | **11 of 12** | regression |
| **E (G12)** | order agreement | 8/10 | 6/10 | regression |
| **E (G12)** | telemetry M02 at x1.8/x2.0 | 0.066/0.077 | 0.020/0.020 | win |

**Verdict: REJECTED under the regression contract.** With all nine steps now
valid (G3 and G9 re-run after the registry fix), D1 wins **one** group and
regresses **five**: it buys group E's admissible fleet by spending B, C, D, F
and the cap-2 half of A. The G5 collapse is the
decisive one — at N=10 the camera goes from 3 of 10 seeds passing part 3 to 0,
with frame age tripling.

**Independently confirmed on a second observable.** G6's *control* condition
(same seed, same fleet, **no flood**) was re-scored: 38 cells that were healthy
on `ProtoRRageD2` are broken on D1 against only 2 the other way, with camera
completeness falling 0.994 → 0.820 and frame-age p95 61 → 144 ms at N=12. That
is the same group-C damage seen through a different runner, so it is not a G5
artefact.

**The flag and the arm STAY in the tree**, default off, exactly as the AGE / C3
/ C4 variants did — the result has to stay reproducible. `ProtoRRageD2` remains
the divergence candidate, unchanged.


### 8.y  The E-series: encoding the binding constraint in the outer problem (2026-09-16)

Driven by the standing rule that a hard operational requirement is expressed as
a constraint or objective term in the OUTER problem before any inner heuristic
(`config-scheduler-handoff.md` §8e). Full diagnosis, per-increment expectations
and falsifiers: `docs/configsched2-diagnosis-2026-09-16.md`.

**Diagnosis first.** `ConfigSched2.decision_sink` (a per-slot decision trace,
inert unless hooked, bit-identical when off) established that the binding
constraint is the **per-slot DCI cap**, not PRBs and not the rate budget:
`cap_skipped` rises 11 % → 30 % → 37 % of units considered as load rises while
`prb_exhausted` FALLS, and `visit_budget_bound` reads **0 at every load** —
the plan's visit budget is a window total while the constraint that binds is
per-slot concurrency.

| inc | arm | change | measured | kept |
|---|---|---|---|---|
| E1 | `ConfigSched2X1` | charge a visit its real harmonic **density** (`1/T`) instead of one unit against a window total | G5 admissible **6 → 7**, knee 1.0 → 1.3; **G3 boundary 10 → None**; `prb_exhausted` 1 774 → 2 454 (registered expectation MISSED) | **no** |
| E2 | `ConfigSched2X2` | a promised visit carries its **plan share**, not a cap-th clamp | camera crumb short-bytes 902 kB → **192 kB**; G3 still None; **G10 10 → 8** | **no** |
| E3 | `ConfigSched2X3` | claim the density budget in **importance order** (contracted meet their deadline bound first, best-effort takes the rest) | G5 **6 → 8**, knee 1.3; G3 None → **4**; G10 held; G2 cap-4 202 → 186; G6 better; G12 order agreement 9/10 → 10/10 | **no** |
| E4 | `ConfigSched2X5` | size a visit by its **byte** need, not a deadline-inflated count | telemetry bpv 150 → **300** (the split fixed, verified pre-run); **G3 → None**, i.e. WORSE — the registered hypothesis was falsified | **no** |
| E5 | `ConfigSched2X6` (standalone) | bound the **unit's total** to a cap-th, not each flow's share | G3 **8**; G5 6 → 7, knee 1.1; G10 held; G2 cap-2 291 → 266; G6 better; G7 A-telemetry throughput **held at 24 000 bps** | **no** |
| E5 | `ConfigSched2X7` (stacked) | E1+E3+E4+E5 | G5 **6 → 8**, knee **1.3**; G3 **6**; G10 held; G2 cap-4 **176** (best); G6 better; G9 12/12 | **best density variant** |

**Two mechanisms found by trace rather than guessed, both recorded to the line.**

1. *Why E1 broke group B.* The heartbeat gets ONE visit per window on both arms;
   what changed was its PERIOD (T = 32 → 64), because E1 removes the plan's
   overcommit **and with it the repair pass that was doing importance-ordered
   shedding**. E3 fixed exactly that and G3 only reached 4.
2. *Why none of them recovered group B.* The E-variants issue roughly **half**
   the uplink grants the baseline does (6 154 / 7 105 against 11 858), because
   PRBs per grant double, 26 → 52 median. `per_visit_cap` bounds a **flow**, but
   a UL unit is `(ue_id, -1)` — every uplink flow of a UE shares ONE grant sized
   from their SUM — so nothing bounded the total. **The density budget converted
   a DCI-limited cell into a PRB-limited one**, and the PRB wall costs more
   grants than the DCI cap did. E5 fixes that aggregation defect, which is
   latent in the baseline too.

**Outcome: no variant dominates the baseline; the series mapped a real frontier**
— heartbeat first (`ConfigSched2`, G3 boundary 10 / camera fleet 6) versus
camera first (`X7`, fleet 8 and the load ramp transformed / G3 boundary 6). Which
point is right is a product decision, and it is the degrade-by-importance
question in `guarantee-groups-2026-09-16.md` §7. **`ConfigSched2` remains the arm
of record**; every E flag is default-off with its result recorded.

**In flight at the time of writing:** `X7+CG` and `ConfigSched2+CG`. G3 is the
only group X7 gives up and restricted CG closed the entire uplink heartbeat class
on every arm previously measured, so CG may dissolve the trade. Registered in the
diagnosis doc §21 **before** the results were read, including why X7+CG must be
compared against `ConfigSched2+CG` and not against a baseline without CG.

### 8.z  Test-definition corrections made during this work

`docs/test-definition-changes-2026-09-16.md` is the running log. Two G6 defects
(no control-health gate; a relative shift with no absolute floor) were fixed as
**re-scorings** — 43 M slots were not re-simulated — and all ten stored `g6.json`
artefacts were rescored, with the three tools that read `deltas` made gate-aware.
One published claim was **withdrawn**: `cmd_vel` p98 now passes G6 part B 30/30
on every arm. G7 clause 1 gained a **paired no-aggressor control**, which showed
the raw p98 was overstating containment harm several-fold and **corrected the
group-D verdicts for every E-series arm** (X7's containment is +0.8 ms, the best
of any arm; X6's is +23.2 ms, the worst — the opposite of the raw ranking).

---

## DL SPS — the downlink analogue of CG, NOT IMPLEMENTED (registered 2026-09-16)

**Status: not built, not measured, no code. This is a registered candidate,
not a result.** Recorded here so it is not rediscovered as a new idea, and so
the next person knows what is already settled about it.

### What it is, from the Rel-16 text (read, not recalled)

Semi-Persistent Scheduling is the downlink's configured grant: a periodic
**downlink assignment** the UE keeps without a PDCCH per occasion.

* **TS 38.321 V16.22.0 §5.8.1** — SPS is configured by RRC per Serving Cell
  per BWP; *"Multiple assignments can be active simultaneously in the same
  BWP"*; a DL assignment is provided by PDCCH and stored or cleared on L1
  signalling (activation / deactivation); activation is independent per
  Serving Cell. RRC supplies `cs-RNTI`, `nrofHARQ-Processes`,
  `harq-ProcID-Offset`, `periodicity`, and the N-th assignment lands at
  `(numberOfSlotsPerFrame x SFN + slot) = (... start time ...) + N x periodicity
  x numberOfSlotsPerFrame / 10` modulo `1024 x numberOfSlotsPerFrame`.
* **TS 38.331 V16.22.0 `SPS-Config`** — `periodicity` ENUMERATED
  {ms10, ms20, ms32, ms40, ms64, ms80, ms128, ms160, ms320, ms640};
  `nrofHARQ-Processes` INTEGER (1..8); Rel-16 extensions `sps-ConfigIndex-r16`,
  `harq-ProcID-Offset-r16` (0..15), `periodicityExt-r16` (1..5120 **slots**),
  `pdsch-AggregationFactor-r16`. `BWP-DownlinkDedicated` carries
  `sps-ConfigToAddModList-r16` / `-ToReleaseList-r16` /
  `sps-ConfigDeactivationStateList-r16`.
* **The bound that differs from CG:** `maxNrofSPS-Config-r16 = 8` SPS
  configurations per BWP, against `maxNrofConfiguredGrantConfig-r16 = 12` for
  CG. A staged-configuration design on the downlink therefore has **8**
  phases to play with, not 12.

So **SPS is fully inside the Rel-16 compliance baseline** — the constraint the
deployment imposes is satisfied, and `docs/rel16-baseline-2026-09-15.md`
§2.1/§2.2 already carries the clause rows (survey row B2, *"Rel-16, keep as a
candidate"*).

### Why it is worth exploring: CG moved uplink and left downlink untouched

The 2026-09-16 campaign measured configured grants on every arm. **CG closed
the entire uplink heartbeat class on every arm, and nothing in the downlink
moved** — G1 and G2 are where they were without it. That is not a surprise
(CG is an uplink mechanism), but it does mean the downlink has had **no
equivalent intervention at all**, on any arm. SPS is the one Rel-16 lever that
is structurally the same shape.

### What it would and would NOT fix — stated before building, so it can be wrong

* **It attacks the DCI / per-slot-cap axis, not the retry axis.** SPS removes
  the PDCCH for the *initial* transmission only; **TS 38.300 §10.2 is explicit
  that retransmissions are scheduled on PDCCH**. So the honest expectation is
  that SPS relieves the M-6 per-slot UE cap (4 at 106 PRB) and the DCI budget.
* **It is therefore NOT an obvious fix for G2.** G2 fails on every arm on the
  **retry budget** (the BLER^2 floor inside a 5 ms PDB), and SPS adds no
  retries. Anyone picking this up should not expect G2 to move, and should
  register that expectation before measuring rather than after.
* **G1 passes today**, so SPS there is a *margin* measurement, not a fix.
* The real candidate is the one the survey already names: a standing DL lane
  for a periodic downlink flow, freeing DCI for the download and for retries.

### Where it would be built — `sim/`, not `scheduler/`

**CLAUDE.md's invariant "Do not add SPS / Configured Grant to the schedulers"
governs `scheduler/` files and is NOT a ban on this work.** Configured grants
were built as a **MAC feature in `sim/`** (`sim/configured_grant.py`) that runs
*ahead of* every scheduler and reaches them only as pre-scheduler occupancy
(`sim/pre_sched.py::Occupancy`) plus a reduced buffer view. SPS follows that
same pattern exactly:

* a `sim/` module owning the SPS configurations and their phases;
* occasions added to the ONE `Occupancy` map, so the DL path cannot diverge
  from the CG path;
* every arm — faithful ports included — runs it through one driver flag, and
  any arm with it on is **labelled in its name and in every table**, exactly as
  `+CG` is;
* `scheduler/two_tier.py` and `scheduler/reservation.py` stay the port, with
  no SPS mechanism re-added (the deleted `_SPSReservation` / `_allocate_sps`
  must not come back).

### Open questions to settle before building

1. **Does the HARQ mask compose?** `HarqAwareBufferView` fully masks a flow
   with a pending process; a standing DL assignment interacts with that the
   way a restricted CG TB did (`HarqProcess.cg_qfi`, build 2c). The DL analogue
   is unbuilt and is the first thing to get right.
2. **Does an SPS occasion suppress anything the way CG suppressed SR?** The
   unrestricted-CG result (it broke G5 on every arm by suppressing SR for every
   channel) is the cautionary precedent. The downlink has no SR, so the naive
   answer is no — which is exactly the kind of naive answer this project has
   been wrong about before, and it should be measured, not assumed.
3. **8 configurations per BWP** is the budget for any staged design.
