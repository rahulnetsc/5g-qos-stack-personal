# The guarantee scorecard — audit fixes applied, both columns, restated

**2026-09-07.** Supersedes `docs/guarantee-success-rates-2026-09-06.md`.
Regenerate: `scripts/guarantee_scorecard.py` (add `--attach` for the
with-attach column). Audit: `docs/scorecard-audit-2026-09-07.md`.

**Four verdicts moved, and one of the movements retracts a conclusion I
published yesterday.**

---

## 1. Every row now declares its population, as data

The audit's conclusion was that the check catching this defect class cannot be
automated. It is now **required** instead: each clause carries `sums_over`
(the rows the predicate ranges over) and `claim_about` (the rows the clause is
about). **A row missing either raises `MissingPopulation` and does not
score** — verified by deleting one and confirming the refusal. Both strings
print beside every verdict, so a mismatch is visible without reading source.

That does not make the judgement. It forces the question to be answered where
the row is written.

## 2. The table — both columns

Denominators: 10 seeds × 1 cell, except **G10 = 10 × 4 fleet sizes = 40** and
**G12 = 10 seeds × 2 cells = 20**. Severity is **M02 over the protected fleet
on every row** — one population, stated.

| guarantee | clause | arm | **without attach** | **with attach** | moved? |
|---|---|---|---|---|---|
| **G1** responsive commands | cmd_vel p98 ≤ 95 ms | PF | 10/10 | 10/10 | |
| | | Reservation | 10/10 | 10/10 | |
| | | **TwoTier** | **7/10** | **9/10** | |
| **G1** | p98 ≤ 15 ms (`sensor_dense`) | all | 10/10 | 10/10 | |
| **G2** STOP always lands | STOP p98 ≤ 100 ms | all | 10/10 | 10/10 | |
| **G3** never look dead | max gap ≤ 500 ms | PF | 10/10 | 10/10 | |
| | | Reservation | 10/10 | 10/10 | |
| | | **TwoTier** | **10/10** | **10/10** | **was 8/10 — FIXED** |
| **G5** fresh complete video | ≥ 99 % PDU sets | PF | 10/10 | 10/10 | |
| | | **Reservation** | **3/10** | **10/10** | |
| | | **TwoTier** | **6/10** | **10/10** | |
| **G7** isolation | c1 victim ≥ 99 % | all | 10/10 | 10/10 | |
| **G7** | c2 excess clipped at MFBR | PF | **1/10** | 1/10 | |
| | | Reservation | **0/10** | 0/10 | |
| | | **TwoTier** | **0/10** | 0/10 | |
| **G8** equal service | Jain ≥ 0.90 (parametric) | PF | 10/10 | 10/10 | |
| | | Reservation | 9/10 | 10/10 | |
| | | **TwoTier** | **7/10** | **10/10** | |
| **G8** | Jain ≥ 0.90 (`sensor_dense`) | PF | 10/10 | 10/10 | |
| | | **Reservation** | **0/10** | **10/10** | |
| | | TwoTier | 9/10 | 10/10 | |
| **G10** stated fleet size | GBR contract met | PF | 30/40 | 30/40 | |
| | | **Reservation** | **23/40** | **31/40** | **was 31/40 — FIXED** |
| | | **TwoTier** | **26/40** | **32/40** | **was 32/40 — FIXED** |
| **G11** holds for a shift | every 60 s window | all | 10/10 | 10/10 | |
| **G12** safety order | c4 | **PF** | **0/20** | 0/20 | |
| | | Reservation | 20/20 | 20/20 | |
| | | TwoTier | 20/20 | 20/20 | |

## 3. What moved, and why

**G3 — TwoTier 8/10 → 10/10 on every arm.** The row read M03 over **all**
flows; every breach was `ue*_qfi9`, the saturating background flood. **Scoring
a flood's own starvation as a telemetry liveness failure was scoring the
scheduler working as the scheduler failing.** Now reads the panel-declared
population (protected fleet). *L97's second half — "zero gaps ≥ T_live" — is
now also recorded (`G3_M03_gaps_over_tlive_prot`); it was never scored.*

**G10 — the without-attach column was attach-ON.** All 40 rows carried
`attach_seed=True`. Corrected, the true without-attach figures are
**Reservation 23/40 and TwoTier 26/40**, not 31 and 32. **The published
numbers were the with-attach ones mislabelled.** Note PF is **30/40 in both**
— it does not suffer the lock-out at all.

**G7 c2 — tolerance removed, verdict unchanged.** Swept as G12's τ was:
Reservation and TwoTier are insensitive (ratios ~2.0; 0/10 at every tolerance
to 1.5), but **PF sits on the boundary** — 1/10 at ≤1.02, 5/10 at 1.05, 10/10
at 1.25. The invented 2 % was deciding 9 of PF's 10 runs. Scored as written
(≤ 1.0); PF's 1/10 happens to be the same number for a defensible reason now.

## 4. RETRACTION — yesterday's attach conclusion was computed on a contaminated artefact

I reported *"6 of 8 predictions missed; do not make the attach path
default."* **That is withdrawn.**

`sweeps/attach-2026-09-06/core.runs.jsonl` has **30 banked runs whose ledger
key is `(arm, seed, n_ues, load_mult, sim_s, wall_s)` — the attach flag is not
in it.** The broken first attempt (flag never reached the `spawn` workers)
banked 30 attach-OFF runs, and the corrected second attempt **resumed them**.
So the "with-attach" column I scored was attach-off, and its null was an
artefact.

**This is the exact defect CLAUDE.md documents:** *"The ledger key carries the
run-defining CONFIG, or a `--smoke` invocation sharing the production `--out`
displaces real records."* Third bank-related defect in three days.

**Corrected prediction scoring — 7 of 8 hit:**

| prediction | outcome |
|---|---|
| G5 TwoTier → clears | **HIT** 6/10 → 10/10 |
| G5 Reservation → ~9/10 | **HIT** 3/10 → 10/10 |
| G10 improves | **HIT** 23→31, 26→32 |
| G3 TwoTier improves | **HIT** (by the fix, not the flag) |
| G8 parametric improves | **HIT** 7/10 → 10/10, 9/10 → 10/10 |
| G8 `sensor_dense` Reservation from 0/10 | **HIT** → 10/10 |
| G8 `sensor_dense` TwoTier 9→10 | **HIT** |
| **G1 TwoTier gets WORSE** | **MISS — it gets BETTER, 7/10 → 9/10** |

**So the attach path is not a trade at all**: on this evidence nothing
degrades. My predicted degradation came from the M06 14/40→40/40 figure, which
was measured under **staggered arrival**, not this grid — configuration not
carried, again.

**Revised recommendation: the case for defaulting it is now strong** (it moves
6 of 12 rows, all favourably, and the physical argument — hardware grants at
attach, this sim has no RA procedure — is unchanged). **I am not flipping the
default in this commit**, because the decision should be taken against a
result that has not just been retracted once.

## 5. Deployment consequence, per row

| guarantee | what the numbers mean for a deployment |
|---|---|
| **G1** commands | **Holds on every arm on a warm cell.** On a cold-starting cell TwoTier misses on 3 of 10 runs — by 2–4 ms over a 95 ms bound, not by a large margin |
| **G2** STOP | **Holds everywhere, with ~25× margin** (2–4 ms against 100 ms). The strongest row in the set |
| **G3** liveness | **Holds on every arm.** The previously-reported TwoTier failure did not exist |
| **G5** video | **The cold-start row that matters.** Without an attach grant, Reservation delivers complete video on 3 of 10 runs and TwoTier on 6. With one, both are 10/10. **This is a commissioning-procedure requirement, not a scheduler choice** |
| **G7** isolation | **The victim is always protected** (c1 10/10 everywhere). **No arm clips the aggressor** — both QoS arms pass 2.03× MFBR through, because MFBR bounds entitlement, not throughput. **A deployment that expects a rate limiter does not have one** |
| **G8** fairness | Warm: all arms ≥ 9/10. Cold: TwoTier 7/10, Reservation 0/10 on `sensor_dense`. **Reservation's dense-sensor fairness failure is entirely a cold-start artefact** |
| **G10** fleet size | **PF 30/40 regardless; the QoS arms are 23–26/40 cold and 31–32/40 warm.** Admissible fleet size is a function of the attach procedure, not only of the scheduler |
| **G11** shift | **Holds on every arm over 7.2 M slots**, with ~100× conformance margin |
| **G12** safety order | **PF violates the safety order 20/20** — it keeps serving 8.6 Mbps of background while telemetry dies, because its ranking reads no QoS field. **Both QoS arms hold 20/20.** For a deployment with safety-critical telemetry this is the clearest argument against PF in the set |

## 6. Time audit

**One full column (5 campaigns, 10 seeds × 3 arms) = 192 s wall on 12
workers, from 2,101 s of serial CPU — a 10.9× speedup.** Both columns,
including the G3 re-run: **~7.5 min.**

| campaign | wall (12 workers) | runs | serial CPU | median run |
|---|---|---|---|---|
| `core` (40 k slots, N=8) | **52 s** | 30 | 542 s | **13.9 s** |
| `sensor_dense` (20 k, 30 UEs) | **25 s** | 30 | 270 s | **8.5 s** |
| `g10` consolidation (20 k, N=2–16) | **78 s** | 120 | 914 s | **5.2 s** |
| `g7` aggressor (20 k, N=8) | **24 s** | 30 | 245 s | **6.6 s** |
| `g2` UL STOP (20 k, N=8) | **13 s** | 30 | 131 s | **3.5 s** |

**Cost per run by arm — TwoTier is 2–3× PF everywhere:**

| campaign | PF | Reservation | **TwoTier** |
|---|---|---|---|
| core (40 k) | 10.1 s | 13.9 s | **30.8 s** |
| sensor_dense | 5.3 s | 8.5 s | **13.1 s** |
| g10 | 3.5 s | 4.9 s | **9.5 s** |
| g7 | 4.7 s | 6.6 s | **13.1 s** |
| g2 | 3.0 s | 3.5 s | **6.5 s** |

**Where the cost sits.** TwoTier is **3.0× PF** on the 40 k core run and
**2.7×** on g10 — consistent with Tier-1's LP: 150 SCA iterations per solve,
re-solved every 200 slots. **The scorecard's whole evidence base is ~35 CPU-min
per column**; the only expensive artefact in the project is the **G11 soak at
4,355 s (72.6 min)**, which is 20× the entire rest combined and is why it is
excluded from routine re-runs.
