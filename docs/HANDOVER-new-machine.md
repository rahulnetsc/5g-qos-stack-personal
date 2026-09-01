# Handover — moving this project to another machine

Written 2026-09-01, for moving `feat/high-fidelity-sim` to an
overnight-capable PC over remote VS Code. **Start a session on the new
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
| `stage6_g6_n40_records.jsonl` | ~230 M | the 240 records §27–§29 were computed from |

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
`stage1/records.jsonl` (1.5 G), `stage4/records.jsonl` (968 M),
`stage6_g6_n40_records.jsonl` — **2.6 GB total** (measured with `du -ch`). Skip stage 2 (5.1 G,
its CSV covers every published claim) and stage 3 entirely (superseded).

---

## 2. Plan files live OUTSIDE the repo

`~/.claude/plans/` — **13 files, 220 KB**, **not in git**. The stage-5
recovery depended on them. They are session plan documents, not
deliverables, and a clone does not get them. **Copy the directory.**

---

## 3. State of the working tree at handover

- Branch `feat/high-fidelity-sim`, **49 commits ahead of origin, unpushed.**
  A new machine should clone and then `git pull` from this one, or this
  laptop should push first.
- Untracked and safe to ignore: `sweeps/wp9/stage3.{log,crash1.log}` —
  leftovers from the dead stage-3 run.
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
guarantee with its reason. Summary: 3 answered (G4, G6, G10), 1 measured
failure (G5), 3 partial (G1, G3, G8), 3 unrun-but-buildable (G9, G11, G12),
1 blocked on a named mechanism (G2), 1 structurally out (G7).

**The two entries not to skip:** G5 is a measured base-cell failure on both
QoS-aware arms (median worst-flow PDU-set completeness **0.0000**) and is
the most operationally serious thing WP9 has found; G6 **passes** on
measurement while being **unscoreable as specified** (regime map §0.6.1–3).

### Next items, none started, each needing its own plan

| item | why it is not started |
|---|---|
| **G12** | Needs a workload with **≥ 2 GBR 5QI classes** — every WP9 workload has exactly one, so M13 has nothing to order. Scenario work. |
| **G9** | Unrun, buildable, with a **measured** argument: M18/M19 read `pending` on every row of every stage because no scenario configures `UEConfig.join`. |
| **G11** | Unrun; see §5.1 — revisit the seed count on the new machine. |
| **§15.5's discriminator** | Two fleet profiles holding flow count and GBR fraction fixed while varying tight-PDB density and LCG co-location. |
| **§23.4's UL/DL pair** | One UL and one DL flow identical in size, cadence, PDB and priority, to isolate the SR-resumption cost. |
| **TB-size quantisation** | Fully specified and deliberately unbuilt (`docs/wp9-plan.md` §20.10): `scheduler/tbs.py` is the home, whoever takes it up **starts at commit 2, not at scoping**. |

### Working discipline that must survive the move

`CLAUDE.md` carries the standing rules; `prediction-journal.md` carries the
pre-registration ones. The two earned most recently:

- **Decompose before attributing** — for any aggregate about a protected
  set, name the rows it sums over, the rows the claim is about, and whether
  they are the same set. Four errors in one item, identical shape.
- **Predict the shape, not the mechanism** — and if the shape is
  quantitative, name the cut in advance.

### Verification, run after every commit

```bash
uv run pytest sim/tests -q                            # 826 passing
uv run python scripts/regression_corpus.py --check    # must say "no drift"
```
