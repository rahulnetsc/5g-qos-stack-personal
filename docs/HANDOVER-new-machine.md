# Handover — moving this project to another machine

Written 2026-09-01; **revised 2026-09-01 after G9 and G12 closed** (this
document was first written at `eefe1d1`, before Part C, G9, G12 and four
journal rules landed — every section below is current as of `74789ed`). For
moving `feat/high-fidelity-sim` to an overnight-capable PC over remote VS
Code. **Start a session on the new
machine from this document, not from a chat transcript.**

Every figure below was derived on **this laptop** (24 cores, 290 G disk,
uv 0.12.5, Python 3.12.3). §4 says which of them must be re-measured
before they are trusted anywhere else — the answer is "all the timings".

---

## 1. What travels in a `git clone`, and what does not

`git clone` gives you a **~52 MB** history and a **~346 MB** working tree
excluding `sweeps/`. The code, every plan document, the metric panel, the
regression baseline (`regression/baseline_studies_1_3.json`, 717 KB) and
all committed sweep **CSVs** travel. **11 GB of raw sweep records do not.**

`.gitignore:49` is `sweeps/**/*.jsonl`, and the rule it encodes
(`docs/wp9-plan.md` §7) is: scored CSVs and gate verdicts are committed,
raw per-cell `RunRecord` JSONL is not.

### 1.1 What a clone HAS under `sweeps/`

| file | what it is |
|---|---|
| `stage1/stage1_rows.csv` | 1,770 scored rows — Part A's entire input |
| `stage1/gate_verdict.txt`, `gate_verdict_corrected.txt` | the promotion gate |
| `stage1/study_layer_metrics.json` | M13/M16 |
| **`stage1/online_rows.jsonl` (31 MB)** | **tracked despite the ignore pattern** — it was committed *before* the pattern was added, and `.gitignore` does not untrack. Do not "fix" this by removing it; it is the only online-variation data that survives a clone. |
| `stage2/stage2_rows.csv`, `stage2/contiguity.json` | 7,560 rows |
| `stage4/stages4_rows.csv`, `stage5/stages5_rows.csv` | 1,440 rows each |
| `stage6_*.{csv,json}` | stage 6's scored outputs |
| `stage{1,2,4,5}.log` | per-cell timings — the only surviving record of what each cell cost |

### 1.2 What a clone does NOT have, with sizes

| directory | size | what is lost |
|---|---|---|
| `stage1/records.jsonl` | **1.5 G** | per-flow `completion_ts_by_role_s`, per-flow byte counters |
| `stage2/` records | **5.1 G** | as above, 7,560 records |
| `stage3/` | **1.8 G** | the run that died at cell 51/52; superseded, no committed CSV — **do not copy** |
| `stage4/records.jsonl` | **968 M** | needed for any C5-style bit-identity check |
| `stage5/records.jsonl` | **906 M** | as above |
| `stage6_g6_n40_records.jsonl` | **251 M** | the 240 records §27–§29 were computed from |
| `part_c_records.jsonl` | **652 M** | **added after this document was first written** (Part C, §30). Its scored `part_c_rows.csv` IS committed and covers every published Part-C claim, so this is skippable on the same grounds as stage 2. |

### 1.3 The consequence, stated concretely

**Any re-analysis that needs per-flow data must copy those files by hand or
re-run the cells.** This is not hypothetical — it has already bitten twice:

- **§25.1**: the first n_seeds=40 G6 run called `sweep()` with no
  `record_sink`, so it kept only the CSV. The falsifier that needed
  per-flow completion timestamps had to fall back to stage 1's n_seeds=10
  records, an interval too wide to decide anything, and **the cells were
  re-run** (`scripts/g6_seed_extension.py` now persists;
  `wp9_sweep.PersistingRecordSink` exists so no future excursion repeats
  it).
- **A C5-style bit-identity check against stage 4** (stage 5's control,
  which verified `lidar_ues=0` reproduces stage 4 exactly) needs
  `stage4/records.jsonl`. **On a fresh clone that check is impossible** —
  either copy the 968 MB or re-run stage 4 (~41 min at 10 workers *on this
  laptop*; re-probe first, §4).

**Recommended to copy by hand** if you want full re-analysis capability:
`stage1/records.jsonl` (1.4 G), `stage4/records.jsonl` (937 M),
`stage6_g6_n40_records.jsonl` (251 M) — **2.6 GB total** (`du -ch`,
re-measured 2026-09-01). Skip `stage2/` (5.1 G, its CSV covers every
published claim), `part_c_records.jsonl` (652 M, same grounds), and `stage3/`
entirely (1.8 G, superseded).

**RE-CHECKED after G9 and G12: the 2.6 GB figure is UNCHANGED, and that is a
property of how those two campaigns were built, not luck.** Neither persists
raw `RunRecord` JSONL. `scripts/g9_campaign.py` and `scripts/g12_campaign.py`
score online and write only their scored JSON, so **every G9 and G12 artefact
is tracked and travels in the clone**:

| artefact | size | in a clone? |
|---|---|---|
| `g9_campaign.json` / `.log` | 7 KB / 4 KB | **yes** |
| `g12_campaign.json` | 115 KB | **yes** — carries per-ramp-point telemetry M02, bg throughput and per-class worst fractions, so **§36 is fully re-analysable from a clone alone** |
| `g12_campaign.log`, `g12_score.log`, `g12_ramp_probe.log`, `g12_timed_cell.log` | 14 KB total | **yes** |

**So nothing from G9 or G12 needs hand-copying.** The whole `sweeps/` tree is
**11 G**; the 2.6 GB subset is the part that is neither committed nor cheaply
reproducible.

---

## 1.4 THE HAND-COPY MANIFEST — exactly what to move, measured

Everything else comes from `git clone`. Sizes measured 2026-09-01 on this
laptop; `du` totals, not `ls` sums.

| # | path | size | why it cannot be cloned |
|---|---|---|---|
| 1 | `sweeps/wp9/stage1/records.jsonl` | **1.4 G** | Part A's per-flow input; `.gitignore`d raw records |
| 2 | `sweeps/wp9/stage4/records.jsonl` | **937 M** | needed for any C5-style bit-identity check against stage 5 |
| 3 | `sweeps/wp9/stage6_g6_n40_records.jsonl` | **251 M** | the 240 records §27–§29 were computed from |
| | **subtotal** | **2.6 G** | |
| 4 | `~/.claude/plans/` | **220 K**, 13 files | outside the repo entirely; not in git |
| **5** | **`~/Documents/artpark_projects/Oai_Ran_QoS_Supported_MultiDRB`** | *(size unmeasured — a full OAI checkout)* | **a separate upstream repository, not a subdirectory of this one.** `CLAUDE.md` names it as the evidence base whenever a constant looks sourceless from the vendored `oai-branches/` subset — the rule that settled `nrmac->min_grant_prb` at Phase 2 reservation commit 4. **Needed on demand, not on arrival** |
| | **TOTAL** | **≈ 2.6 G** + the OAI checkout | |

**Deliberately NOT copied, with the reason for each:**

| path | size | why skip |
|---|---|---|
| `sweeps/wp9/stage2/records.jsonl` | 5.1 G | `stage2_rows.csv` is committed and covers every published stage-2 claim |
| `sweeps/wp9/stage3/` | 1.8 G | the run that died at 51/52, superseded, no committed CSV |
| `sweeps/wp9/part_c_records.jsonl` | 652 M | `part_c_rows.csv` is committed; same grounds as stage 2 |
| `sweeps/wp9/stage5/records.jsonl` | 836 M | `stages5_rows.csv` is committed; re-runnable |
| G9 / G12 artefacts | 140 K | **all tracked** — they travel in the clone |

**Why item 5 is on the list even though nothing is blocked without it.**
It was missing from the first version of this manifest, and the first real
move exposed exactly the failure it sets up: the vendored subset and
`calibration-logs/` both travel in a clone, so **the day you need the full
checkout is a day you are already deep in a question, and the manifest that
should have told you to bring it says nothing.** A dependency that is only
needed occasionally is the one most likely to be omitted and least likely to
be missed at the moment of omission.

**Sanity check on arrival**, before trusting any of it:

```bash
du -ch sweeps/wp9/stage1/records.jsonl \
       sweeps/wp9/stage4/records.jsonl \
       sweeps/wp9/stage6_g6_n40_records.jsonl | tail -1   # expect ~2.6G
ls ~/.claude/plans/*.md | wc -l                            # expect 13 -- BUT SEE BELOW
git remote -v | grep -c upstream                           # expect 1, not 0
uv sync && uv run pytest sim/tests -q                      # expect 882 passed
uv run python scripts/regression_corpus.py --check         # expect "no drift"
```

**The `~/.claude/plans/` count check is WEAK, and the first move proved
it.** On arrival that directory held **4 files** — not zero — because the
new host had its own WP1/WP3/WP4-era plans from earlier sessions. **A
non-empty directory reads like a success**, and worse, a count check is
*ambiguous after a partial copy*: copy 13 laptop files into a directory that
already holds 4, with some names overlapping, and the total lands anywhere
between 13 and 17. **13 is then evidence of nothing.**

So the check has to be on **identity, not cardinality**. Take a listing on
the source machine and diff it:

```bash
# on the laptop
ls ~/.claude/plans/ | sort > /tmp/plans.manifest
# after copying, on the new machine
comm -23 /tmp/plans.manifest <(ls ~/.claude/plans/ | sort)   # expect EMPTY
```

**This generalises past the plans directory.** Any arrival check on a
destination that may already be non-empty needs a set difference, not a
count — the same reason `scripts/regime_map_rollup.py` exists rather than a
sentence saying the counts were derived.

**`scripts/transfer_manifest.sh` does the whole thing in one command**, so
the copy and its verification cannot drift apart:

```bash
./scripts/transfer_manifest.sh <ssh-host>            # PULL from host
./scripts/transfer_manifest.sh <ssh-host> --verify   # verify only
./scripts/transfer_manifest.sh <ssh-host> --push     # PUSH to host
```

**RUN IT FROM THE LAPTOP, IN `--push` FORM. The trust between these two
machines is one-way and a pull can never work.** Measured on the desktop:

- the desktop's `~/.ssh/authorized_keys` holds **two keys commented
  `laptop`**, and its `sshd` is listening — so **laptop → desktop works**;
- the desktop has **no private key at all** (`~/.ssh/` contains
  `authorized_keys`, `config`, `known_hosts` and nothing else) and its
  ssh-agent holds no identities — so **desktop → laptop cannot
  authenticate**, and no amount of retrying from this side changes that.

**And the `lab` alias in `~/.ssh/config` is NOT the laptop — it is this
desktop.** `HostName 172.25.70.124` is the desktop's own `wlp7s0` address,
and its `User smartpc` does not exist on the desktop. `ssh lab` is a
loopback to a nonexistent user; it fails for everyone, and anyone reading
the alias as "the other machine" will spend the same time on it twice.
**There is no configured route from the desktop to the laptop.**

So the transfer is driven from the laptop:

```bash
# on the LAPTOP, from its own checkout
./scripts/transfer_manifest.sh smart@172.25.70.124 --push   # same LAN
./scripts/transfer_manifest.sh smart@100.101.171.63 --push  # tailscale
```

It rsyncs items 1–3 with `-P` (a dropped 1.4 G transfer resumes rather than
restarting), copies the plans with `--ignore-existing` so the destination's
own history survives, then verifies **items 1–3 by byte size against the
source** and **item 4 by set difference** — a superset passes, a missing
file fails. It reports on item 5 without copying it. If ssh cannot reach
the host it exits without copying anything, rather than leaving a partial
that reads like a success.

**If `--check` reports drift on a fresh machine, that is a finding about
portability, not a reason to `--capture`.** The corpus is frozen
(CLAUDE.md); re-baselining to make a cross-machine diff disappear would
destroy the only evidence that the simulator is not bit-reproducible across
hosts.

---

## 2. Plan files live OUTSIDE the repo

`~/.claude/plans/` — **13 files, 220 KB**, **not in git**. The stage-5
recovery depended on them. They are session plan documents, not
deliverables, and a clone does not get them. **Copy the directory.**

---

## 3. State of the working tree at handover

- Branch `feat/high-fidelity-sim`, **pushed to both `origin`
  (rahulnetsc/5g-qos-stack-personal) and `upstream`
  (artpark-hub/5g-qos-stack) as of `74789ed`.** A clone of either is
  complete; nothing needs pulling from this laptop.
- Untracked and safe to ignore: `sweeps/wp9/stage3.{log,crash1.log}` —
  leftovers from the dead stage-3 run.
- **A clone does not get the `upstream` remote** — `git clone` configures
  only `origin`. Verified on the first move: the new host had `origin`
  alone, so a push intended for `artpark-hub/5g-qos-stack` would have gone
  silently to the fork. Fix on arrival:
  `git remote add upstream https://github.com/artpark-hub/5g-qos-stack.git`
- **`sweeps/wp9/part_c*` may be mid-run.** `part_c_rows.csv` is written
  ONLY on completion: if `part_c_records.jsonl` exists without it, the run
  died and the records are a partial. Delete both and re-run; do not
  analyse a partial.

---

## 4. EVERY TIMING IN THE PLAN IS THIS LAPTOP'S NUMBER

**Re-probe before budgeting anything.** This is §6.3a's own rule — *time
the thing you are actually going to run, same horizon, same flags, same
post-processing, or state explicitly that the number is a lower bound* —
and it exists because the original budget was wrong by 5–7×.

Machine-specific, all of it:

| quantity | this laptop | why it will differ |
|---|---|---|
| per-cell cost, N=2/8/32 | 81 / 303 / 1093 s | single-core speed |
| cost model (§13) | `4.48 × flows^1.09` s/cell | **fitted to fleet-builder compositions only** — it under-predicts the parametric `factory` mix by 1.23–1.87×, because that mix costs ~1.5× more per flow. `flows` alone is not a sufficient cost index across workloads. |
| parallel efficiency | **6.75×** at 10 workers (68 %) | core count, memory bandwidth |
| worker count | 10 (of 24 cores) | chosen against **1.4–2.1 GiB per worker** peak RSS |
| memory ceiling | ~20 GiB across 12 workers at the largest cells | a machine with less RAM must lower `--workers` |
| end-to-end effective rate | **≈2.9×** sim-s per wall-s (stages 4+5) | everything above |

**The per-run picture is a negative result worth carrying** (§26.1): at
every working fleet size this simulator is **slower than the radio it
models** — 0.495× at the base point, 0.137× at n_ues=32, full pipeline. The
throughput comes from parallelism, not from the model being fast. Do not
put a "faster than real time" claim on a slide.

---

## 5. What an overnight-capable machine CHANGES

### 5.1 G11's 3-seed soak is a budget deviation, and it is REVERSIBLE

`docs/wp9-plan.md` §6.3 records this explicitly as *"the one place the
standing 10-seed rule is broken, deliberately"*: 30 min of sim time is
~43 min/run, so 3 arms × 10 seeds ≈ **21 h**, which did not fit alongside
stage 2 on this laptop. The soak was cut to **3 seeds ≈ 6.5 h**, with no
bootstrap CI and the three runs reported individually.

**On a machine that runs unattended overnight, 21 h fits.** The reduced-seed
decision was a *budget* constraint, not a methodological one, and it should
not be inherited as permanent. Restoring 10 seeds also restores the
cross-seed claims §6.3 currently rules out of bounds.

> **CORRECTION, measured on the new machine before any G11 code was written
> (`docs/wp9-plan.md` §37). The paragraph above is right about the seeds and
> wrong about the constraint.**
>
> **G11 was not runnable as specified at ANY seed count, on either
> machine.** At GT-7.1's 7.2 M-slot horizon one run needs **~48 GiB** with
> `record_timeseries=True` — which G8/M09 requires — against **30 GB on
> both hosts**; ~24 GiB with the timeseries off, and a guarded run of the
> cheapest arm was killed at **21.8 GiB with 2.4 GB left**.
>
> **The time arithmetic here was fine** — 43 min/run against a measured
> 45.8. **The memory budget was never taken**, and it is the binding one, on
> the one resource this move did not improve: both machines have 30 GB.
>
> **So "21 h fits" was true and irrelevant.** Cutting seeds cannot fix an
> out-of-memory condition inside a single run — 3 seeds and 10 seeds OOM
> identically, on run one. G11 needs two mechanisms first (per-window ledger
> eviction, per-second timeseries fold); with them the 10-seed campaign fits
> in **≈2.15 h** and the reversal in this section is not merely affordable
> but comfortable.
>
> **The transferable part is §37.5's rule.** §6.3a says *time the thing you
> are actually going to run*; extend it to every resource, **memory first** —
> a wrong time budget degrades and still delivers a result, a wrong memory
> budget terminates with nothing scored. **A budget that reports only time
> is a partial budget**, and the partiality is invisible because time is
> what the cost model happens to measure.

### 5.2 Part C is a live example of why this matters

Part C (24 cells, 720 runs) died **twice** on this laptop — once to an OS
suspend, once to a reboot — after ~5.5 h serial and again mid-parallel-run.
Its log was also lost both times because it was written to a session-scoped
scratchpad. **Write run logs into the repo tree** (`sweeps/wp9/part_c.log`),
not to `/tmp` session directories.

### 5.3 What else becomes affordable

- **G9's 50-cycle join campaign** (~72 min at 10 seeds) — already fits here,
  but see §6.
- **Stage 2 at full depth** without the 24 h ceiling that forced the
  "at most one excursion axis" cap (§0.4 of the regime map), which is the
  single largest acknowledged weakness in the sweep's coverage.

---

## 6. Current state and the agreed next sequence

**Guarantee inventory: `docs/wp9-regime-map.md` §2.1** — one status per
guarantee with its reason. Summary as of `74789ed`: **3 answered** (G4, G6,
G10), **2 measured failures** (G5, and G12's clause 4 — filed under G1/G3),
**3 partial** (G1, G3, G8), **2 run with clause-level answers** (G9, G12),
**1 unrun** (G11), **1 blocked on a named mechanism** (G2), **1 structurally
out** (G7). **G9 and G12 have both closed since this document was written.**

**The three entries not to skip:**

1. **G5** — a measured base-cell failure on both QoS-aware arms (median
   worst-flow PDU-set completeness **0.0000**), still the most operationally
   serious thing WP9 has found.
2. **G12's clause 4, filed under G1/G3** — telemetry M02 reaches **1.000**
   (every resolved byte PDB-violated) **while background 5QI 9 still carries
   11.6 Mbps**, which is GT-7.3's own worked FAIL example. PF and Reservation
   from 102 % of the measured ceiling; **TwoTier from NOMINAL LOAD on 9 of 10
   seeds**. Two qualifications travel with it and are on G12's row: the arm
   difference is **untested under flow-list permutation**, and G12's clean
   ramp-bottom control **does not cover telemetry** (it reads M13's GBR
   classes; 5QI 1 is `Delay`).
3. **G6** — **passes** on measurement while being **unscoreable as
   specified** (regime map §0.6.1–3).

**And one standing confound a new session must know about before running
anything on the fleet workloads: FLOW DECLARATION ORDER.** Measured in
`docs/wp9-plan.md` §35.5/§36.1: reordering `ScenarioConfig.flows`, with
everything else byte-identical, **changes which 5QI class violates first**,
and on TwoTier it can break a bearer at nominal load outright. PF's
permutation 104 gives the opposite first-violation order from 101/102/103, on
all 5 seeds each — a *deterministic* function of list position, not noise.
**The mechanism is untraced.** Three candidates are named in §35.5 and all
three are position-dependent, so tracing to any of them confirms the artefact
rather than refuting it.

### Next items, none started, each needing its own plan

| item | why it is not started |
|---|---|
| **G11** | **The only unrun guarantee left, and the reason for this move.** **Measured NOT runnable as specified** — see §5.1's correction and `docs/wp9-plan.md` §37; it needs two memory mechanisms before any seed count matters. Plan: `docs/wp9-g11-plan.md`. |
| **The declaration-order trace** | §35.5's confound. Needs a worktree-instrumented direct-cause trace; the promotion bar for calling any ordering result a scheduler property is registered in `wp9-plan.md` §35.13 and must be applied as written, **including its edge** — the three candidate mechanisms are all position-dependent, so finding one of them CONFIRMS the artefact. |
| **G12 clause 1** | Scored weakly: 5QI 9 has no contract, so there is no breach event to order it against the GBR classes. **Answerable from `g12_campaign.json` without a re-run** (§36.7 item 4), but it was never registered as an expectation, so it needs registering before it is scored. |
| **G9's two open threads** | TwoTier's self-selected event shortfall (§34.5 — the scripted restart period must exceed the slowest arm's handshake) and the unexplained neighbour Δp98 (§34.2, r = −0.028 against the obvious explanation). |
| **§15.5's discriminator** | Two fleet profiles holding flow count and GBR fraction fixed while varying tight-PDB density and LCG co-location. |
| **§23.4's UL/DL pair** | One UL and one DL flow identical in size, cadence, PDB and priority, to isolate the SR-resumption cost. |
| **TB-size quantisation** | Fully specified and deliberately unbuilt (`docs/wp9-plan.md` §20.10): `scheduler/tbs.py` is the home, whoever takes it up **starts at commit 2, not at scoping**. |

### Working discipline that must survive the move

`CLAUDE.md` carries the standing rules; `prediction-journal.md` carries the
pre-registration ones.

**`prediction-journal.md` now has FOUR standing form rules. They govern how
an expectation is written and are not optional:**

1. **Predict the SHAPE, not the mechanism.** Say what the data will look
   like and fix each look's meaning *in advance*. A mechanism prediction is
   unscoreable until someone traces code; a shape prediction scores on
   arrival and cannot be re-fitted.
2. **A two-level axis reading can INVERT.** Two levels support *"this axis
   has an effect"*, never *"more of it does more of that"*. Breadth
   establishes existence; depth establishes shape.
3. **Check the instrument has DYNAMIC RANGE before registering a delta.** On
   the control condition alone, ask whether the statistic can move at all. A
   delta on a floored metric is unfalsifiable however well it is written —
   J5 satisfied every other rule and could not have been contradicted.
   **G12 extended this to non-deltas:** a first-violation *order* has the
   same failure mode (stage 5's lidar was pinned at "fails", capped at
   `duration_s/horizon_s`), and the check on an order **leaks part of the
   answer**, so declare when an expectation is pilot-informed rather than
   blind.
4. **A rule can be violated by the code that IMPLEMENTS it.** `g12_score.py`
   cites the decompose rule in its docstring and then pooled a minimum
   across arms. **Analysis code is a claim in advance**: decompose by the
   grouping the report will present, at the time the line is written. What
   caught it was suspicion of the tool's *output*, not a code review.

**And from `docs/wp9-regime-map.md` §4.1 — the clause-by-clause default.**
Two guarantees have now produced their most consequential finding for a
*different* row: G6's work produced G5's failure, G12's produced G1/G3's. In
both cases the clause that went unscored longest was the one **whose
instrument differed from the guarantee's headline instrument** (G6: headline
a delta, unscored clause a bound; G12: headline an ordering via M13, unscored
clause a PDB rate via M02). **So score every guarantee clause by clause, with
each clause's own instrument named** — the discipline G9's row introduced.
This is the default now, not something adopted when a guarantee turns out to
be complicated.

**Also still standing, from CLAUDE.md:**

- **Decompose before attributing** — for any aggregate about a protected
  set, name the rows it sums over, the rows the claim is about, and whether
  they are the same set. Four errors in one item, identical shape; a fifth
  and sixth since, one of them inside the tool built to apply it.
- **Assert the EXPECTED count, not merely non-zero** — a partially
  degenerate run is not a smaller sample of the same thing, because the
  surviving events are self-selected (G9 §34.5). G12 applied this at
  **cell** granularity for the same reason: dropping only the failing seeds
  would have self-selected the survivors.

### Verification, run after every commit

```bash
uv run pytest sim/tests -q                            # 879 passing
uv run python scripts/regression_corpus.py --check    # must say "no drift"
```
