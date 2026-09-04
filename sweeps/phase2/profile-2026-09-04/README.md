# Where the wall-clock goes — profile of one sweep record, 2026-09-04

Raw artefacts for the profiling pass that preceded the three optimisation
commits. Kept in the repo tree rather than a session scratchpad, per
`docs/HANDOVER-new-machine.md` §5.2 — this project has lost run logs to
scratchpads twice.

## THE CONFIGURATION THESE NUMBERS WERE TAKEN IN

Named here and repeated in every table below, because `CLAUDE.md`'s
measurement-carries-its-configuration rule has cost this project a 3× and a
4× error in one week, and the mitigation is to state the configuration
beside the number rather than to add an error bar.

| | |
|---|---|
| scenario | `sweep_scenario`, `factory` parametric mix, **N=8, 32 flows** |
| horizon | **20,000 slots** = 5.0 s sim at numerology 2 |
| driver flags | `record_timeseries=True`, `cqi_delay_slots=8` |
| post-processing | **the full sweep path** — `RunRecord.from_summary`, `_online_rows_for` (M16 + 12 scoring variations × 2 populations), `_strip_timeseries` + `json.dumps` + write, `m13_projection`, panel `score()` × 2 populations |
| seeds | 1, 2, 3 (three runs per arm; the split is stable across them) |
| machine | AMD Ryzen 9 9950X, 16 physical cores / 32 threads, 30 GB |
| process | single, no contention |

**Anything measured at a different horizon, with `record_timeseries` off, or
with a different post-processing set is a different run, not an
approximation of this one.**

## What is here

| file | what it is |
|---|---|
| `profile_record.py` | the harness — replicates `wp9_sweep._run_one_cell`'s per-record path exactly, with `perf_counter` phase boundaries |
| `agg.py` | aggregates py-spy raw (folded) stacks into self/inclusive time and per-phase attribution |
| `raw_tt.txt`, `raw_pf.txt` | py-spy `--format raw` at 500 Hz — 8,237 and 4,259 samples |
| `agg_tt.txt`, `agg_pf.txt` | the aggregations |
| `clean_*.json`, `s2_*.json`, `s3_*.json` | phase timings, three seeds × three arms, **without** py-spy attached |
| `phases_tt.json`, `phases_pf.json` | phase timings of the py-spy'd runs (≈27 % sampling overhead — use the `clean_` ones for absolute times) |
| `scale_{10000,20000,40000}.json` | the scaling test |
| `count_lp.py` | counts and times every `linprog` call in one run |
| `lp_micro.py` | scipy `linprog` vs direct `highspy`, on one LP captured from a live run |
| `metric_cost.py` | per-metric cost of one `Scorecard.score()` call, both populations |

## The results, in one place

**Per record**, mean of three seeds:

| arm | driver.run | scoring | persist | total | scoring as % of record |
|---|---|---|---|---|---|
| PF | 3.58 s | 2.57 s | 0.19 s | 6.35 s | 40.5 % |
| Reservation | 5.21 s | 2.66 s | 0.20 s | 8.08 s | 32.9 % |
| TwoTier | 10.14 s | 2.64 s | 0.20 s | 12.99 s | 20.3 % |

**Per cell** (3 arms × 10 seeds = 30 runs): **274 s** — driver 69.1 %,
scoring 28.7 %, persistence 2.1 %.

`docs/wp9-plan.md` §6.3a measured scoring at "~24 % on top of the driver".
That figure is **TwoTier only**. Re-measured across the arms it is 26.5 % on
TwoTier's driver, 48.7 % on Reservation's and **72.6 % on PF's**.

**No hidden quadratic remains.** Measured growth exponents at
10k → 20k → 40k slots: driver 1.07 / 1.02, scoring 1.05 / 1.06, persist
1.10 / 1.05. The M09 hoist (`d1b8834`) removed the only one.

**The Tier-1 LP is 43.5 % of TwoTier's driver, and 78 % of that is not the
solve.** One 20,000-slot run makes **6,656 `linprog` calls** on a **10×64**
dense LP — 50 Tier-1 re-solves × ~133 SCA iterations, hitting the
150-iteration cap — for 4.40 s. Timed on one captured LP, 400 reps:

| | ms/call |
|---|---|
| `scipy.optimize.linprog(method="highs")` — what ships | **0.606** |
| direct `highspy`, fresh model each call | 0.107 |
| warm `Highs`, `changeColsCost` only | **0.0148** |

Identical solution, max abs difference **0.0**. `A_ub` / `b_ub` / `bounds`
are built outside the SCA loop (`scheduler/tier1.py`); only `c` changes.
**One captured LP is a lead, not a result** — bit-identity across the
paired-seed corpus is what would make it one.

**M09 + M22 are 81 % of every `score()` call** (87 % on the protected-fleet
population), and neither depends on any of the four scoring-variation
parameters. One `score()` call is 123 ms all-flow / 78 ms protected;
per-metric: M09 76.8, M22 24.8, M04 13.7, M14 5.6, M03 4.3, everything else
under 0.4 ms combined.

| the 12 variations × 2 populations | |
|---|---|
| as shipped | 2.412 s (measured `online_variations`: **2.420 s**) |
| with per-axis dispatch | 0.099 s |
| | **24.4×** |

## What a C port of channel + traffic generation would buy

Channel (with pathloss and blockage) is **0.95 %** of a TwoTier record and
**1.50 %** of a PF one. Traffic generation is **4.3 %** and **7.7 %**.
Together, at infinite speedup, **1.06× / 1.10×**.

The whole per-slot Python simulator — everything under `driver.run()` except
the LP, which is already C behind a slow wrapper — is **41 % of a TwoTier
record, 52 % of a PF one, 53 % of a cell**. An infinitely fast rewrite of all
of it is **2.13× per cell**. That is a ceiling, not an estimate of a port.
