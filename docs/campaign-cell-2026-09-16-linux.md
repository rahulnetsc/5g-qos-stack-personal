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
