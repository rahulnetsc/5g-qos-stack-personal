# Full guarantee re-run — plan, budget and registration

**2026-09-06. Registered before launch.** Budget **120 min**, unattended,
detached (`setsid`), banked per campaign, artefacts inside the repo tree at
`sweeps/rerun-2026-09-06/`.

---

## 1. The registered expectation, and it is the whole point

**Everything reproduces.** No code has changed since these were measured
except the staleness guard's scoping (`scripts/code_state.py`,
`scripts/verify_claims.py`) and the U1 probe — **none of which any of these
campaigns import into a number**. So:

> **Any movement is a finding, not a result.** If a verdict moves, that item
> stops, the cause is found, and it is reported. A re-run that silently
> disagrees with itself is worse than not running it.

**Could this check have failed?** Yes, in three named ways, which is why it is
worth running: (a) the Tier-1 objective scaling landed with a deliberate
re-baseline, and a campaign whose artefact predates it would move; (b) the
attach/re-join seeds are mechanism changes carried by some runners and not
others; (c) `--check` pins a solver path, so any dependency drift shows here
first. All three would move numbers. Nothing in the diff *should*.

## 2. Budget — from measured figures

Anchor for the soak: **2.56 M slots, 1 PF run = 486 CPU-s wall 8:05**
(`sweeps/wp9/g11_horizon_battery.time`). Everything else is the summed
`wall_s` its own artefact recorded, or cells × that artefact's median.

| # | guarantee(s) | runner | grid | measured CPU-s | wall @ W=12 |
|---|---|---|---|---|---|
| 1 | **G1 G3 G5 G8** | `phase2_core.py` | 3 arms × 10 seeds, 40 k, N=10 | 503 | ~1 min |
| 2 | **G1 G3 G8** *(sensor_dense)* | `sensor_dense_score.py` | 3 × 10, 20 k, 30 UEs | 246 | ~0.5 min |
| 3 | **G5 G10** consolidation | `g5_consolidation.py` | 120 cells | 844 | ~1.5 min |
| 4 | **G10** | `g10_rerun.py` | 60 cells | 737 | ~1.5 min |
| 5 | **G4** | `g4_postsilence.py` | 3 duty × 3 arms × 10 seeds | ~1,080 | ~1.5 min |
| 6 | **G6** | `g6_seed_extension.py` | 40 seeds × 3 arms | ~1,440 | ~2 min |
| 7 | **G7** ×3 loads | `g7_aggressor.py` | 30 + 12 + 12 cells | 390 | ~1 min |
| 8 | **G9** | `g9_campaign.py` | 3 scenarios × 3 arms × 10 | ~1,080 | ~2 min |
| 9 | **G12** | `g12_campaign.py` | 2 cells × 8 ramp × 3 × 10 + 4 perms | ~6,500 | ~9 min |
| 10 | **G2** | `g2_ul_stop.py` | 30 cells | 112 | ~0.5 min |
| | **subtotal** | | | **~12,900** | **~20 min** (25 with scoring) |
| 11 | **G11 C1 soak** | `g11_campaign.py` | 10 seeds × 3 arms × **7.2 M slots** | — | **~72 min @ W=10** |
| 12 | **G11 C3/C4/C5** | `g11_c345.py` | scores (11)'s artefact | — | ~1 min |

**Total ≈ 97 min against 120. It fits at full seed count — nothing is cut.**

**Both workloads are included where a guarantee scores on both** (rows 1 and
2): G1, G3 and G8 are the three overlapping guarantees and are where the
cross-workload evidence lives.

## 3. The C1 decision, stated in advance

C1 is 60 % of the budget on its own, so the ordering is deliberate:

**Everything else runs FIRST, banked, then C1.** A soak that overruns then
costs only itself; a soak that ran first and overran would cost all eleven
other items. This is the bank-as-you-go rule applied at campaign granularity.

**And a pre-declared fallback rather than a judgement call at 2 a.m.:** the
orchestrator checks the clock immediately before launching C1. **If more than
45 min of the 120 has already gone, C1 runs at 6 seeds instead of 10**, and
the artefact and the report both say so. Reduced n, stated — not a dropped
guarantee. (The user's stated preference, adopted.)

## 4. Memory

The soak peaks near **2 GB per run**; **W=10 is the operating point** and the
campaign's own aggregate guard stays armed. **No two campaigns run
concurrently at soak horizons** — the orchestrator is strictly sequential, so
this cannot happen by construction rather than by care.

Rows 1–10 run at **W=12** (20–40 k horizons, ~200 MB/run).

## 5. Banking

One fsynced JSONL line per completed campaign in
`sweeps/rerun-2026-09-06/ledger.jsonl` — name, artefact, exit code, elapsed.
A kill loses at most the campaign in flight, and the ledger says exactly
which. Each runner banks internally as well where it already does.

## 6. Verification before walking away

- **one** parent (`rerun_all.sh` under `setsid`), and
- the expected worker count, counted as **`multiprocessing.spawn` children**,
  never by matching the script name — a spawn worker's argv is the bootstrap,
  so a name match finds none of them and can match the checking shell itself.

## 7. Report

A single consolidated diff against `docs/STATE.md`: per guarantee
**reproduced / moved**, with the artefact and n behind each. Then
`verify_claims --check`, `regression_corpus --check`, `parallel_audit
--check`, the full suite, and push.
