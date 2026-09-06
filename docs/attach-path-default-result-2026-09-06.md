# The attach-path default — decision result, and 6 of 8 predictions missed

**Registered** `docs/attach-path-default-registration.md` before the run.
**Both columns** in `scripts/guarantee_scorecard.py` (`--attach`).
**Artefacts** `sweeps/sev-2026-09-06/` (without) and
`sweeps/attach-2026-09-06/` (with).

## Verdict: **do NOT make it default on the strength of this evidence.** The
## clearance it was justified by came from a different configuration.

---

## 1. Prediction scoring — 2 hits, 6 misses

| prediction | outcome |
|---|---|
| G5 TwoTier 6/10 → 10/10 | **MISS — 6/10, unmoved** |
| G5 Reservation 3/10 → ~9/10 | **MISS — 3/10, unmoved** |
| G10 improves, spread collapses | **MISS — 30/31/32 of 40, unmoved** |
| G3 TwoTier improves | **MISS — 8/10, unmoved** |
| G8 parametric improves | **MISS — unmoved on all arms** |
| G1 TwoTier gets **worse** | **MISS — 7/10, unmoved** |
| G8 `sensor_dense` Reservation improves from 0/10 | **HIT — 0/10 → 10/10** |
| G8 `sensor_dense` TwoTier 9/10 → 10/10 | **HIT — 10/10** |

## 2. The mechanism check says the intervention worked

**It is not a failed manipulation.** `attach_seeds_fired = 8` of
`attach_seeds_expected = 8`, every UE seeded. The flag did what it says.

**So the parametric mix genuinely does not move**, and that is the finding.

## 3. Why — and it corrects the premise of the decision

**The lock-out is a property of a UE joining a LOADED cell, not of a cold
start with everyone present.**

The published clearance — TwoTier G5 4/10 → 0/10 failing, Reservation 7/10 →
1/10 — was measured with `attach_path_experiment._stagger`, which **staggers
UE arrival** and seeds each UE at *its own* arrival slot. The scorecard's
parametric grid has **all 8 UEs present from slot 0**, where no UE has to win
a sort against an established fleet. Seeding them all at slot 0 fires
correctly and clears nothing, because there is nothing to clear.

**This is consistent with the record rather than contradicting it.**
CLAUDE.md already states that staggering *alone* makes starvation strictly
worse, and that **"a UE joining a loaded cell is at MORE risk than one present
at cold start."** I predicted from the *clearance figure* without carrying its
*configuration* — the measurement-carries-its-configuration error, applied to
my own registration.

## 4. What the attach path DOES do — and it is real

On `sensor_dense` (30 UL sensors, PDCCH-bound, 15 ms PDB):

| clause | arm | without | with |
|---|---|---|---|
| **G8** Jain ≥ 0.90 | **Reservation** | **0/10** | **10/10** |
| | TwoTier | 9/10 | **10/10** |
| **severity (M02)** | Reservation | 0.08853 | **0.02776** — 3.2× lower |
| | TwoTier | 0.01433 | **0.00009** — **160× lower** |
| **G7 c1** victim severity | TwoTier | 0.26304 | **0.00015** |
| | Reservation | 0.17327 | **0.04954** |

**Reservation's `sensor_dense` fairness failure was entirely starvation**, and
the attach path removes it completely. **No clause got worse anywhere** — the
predicted G1/TwoTier degradation did not appear.

## 5. The decision

**Not default.** Three reasons, in order:

1. **It is inert where most of the guarantee set is scored.** Every parametric
   clause is unmoved, and that is 8 of the 12 scored rows.
2. **The justification I registered was sound but the evidence I cited for it
   was from a different configuration.** The physical argument stands —
   hardware grants during attach, this sim has no RA procedure and
   `has_srb` is hardcoded `False` — but "it clears G5" is not supported by
   this run.
3. **Where it does act it is large and one-directional** (160× on a severity),
   so it should be **available and used deliberately**, not silently on.

**Recommendation: keep the flag, default off, and require any scenario with
STAGGERED OR MID-RUN ARRIVALS to set it** — that is the population where the
fault is real and where hardware's missing input actually bites.

## 6. The port map row

Recorded as a **divergence**, not a ported behaviour: the flag supplies the
effect of an input the deployed system has and this model lacks. Direction
stated (the sim is *missing* an input; the flag restores it), so it cannot be
mistaken for a fidelity improvement to the scheduler. The lock-out mechanism
and Tier-1.5's dead rescue gate are **unchanged**.

## 7. A defect caught on the way, and it would have published a false null

The first with-attach run was **byte-identical to the without run** on every
row. The flag was passed to the pool as a **module global set in `main()`** —
which does not reach a `spawn` worker, because the worker re-imports the
module and sees the declared default. **CLAUDE.md records this exact trap from
G9's seed flag, and I reproduced it.**

Caught by a manipulation check before scoring: run the same seeds with and
without and require the output to differ. **A "with-attach column that shows no
change" is indistinguishable from a flag that never arrived**, and the
difference is eight minutes of compute against a wrong conclusion published
as a decision.
