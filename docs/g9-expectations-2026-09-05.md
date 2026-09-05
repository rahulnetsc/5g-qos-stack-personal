# G9 re-run on post-A1 scenarios — expectations, registered before the run

**2026-09-05.** Under `prediction-journal.md` form rule 4: each clause names
its **statistic**, its **level**, and its **falsifier** — not whether
something moves.

## The question that comes first

**Does the count guard now pass?** It previously refused to score:
*"GT-6.1_warm/TwoTier: 2 'warm' events but the scenario schedules 10."*

**PREDICTION: IT STILL REFUSES, AND FOR THE SAME REASON AS BEFORE.**

**Statistic:** `expected_event_count(sc, "warm")`. **Level:** the value it
returns, not whether the campaign aborts.

**Why, derived rather than assumed.** A1 clipped `expected_event_count` to
the horizon, and that clip **cannot change anything at G9's designed
horizon**: measured just now, `gt61_warm_rejoin` places its last event at
**slot 16,400 of 20,000**, `gt62_cold_attach` at 14,800 of 20,000, and
`gt63_rlf_recovery`'s fade ends at 16,000 of 30,000. **Every event was
already reachable, so the unclipped count was already correct at 10.**

**So if the guard still refuses, the original diagnosis stands and is
strengthened, not repeated:** the arm is genuinely degenerate — TwoTier
records 2 of 10 scripted warm events — and this was never a guard artefact.
A1 fixed a **latent** defect that would have bitten a *shorter* run; it was
never the cause of this abort.

**Falsifier:** the campaign scores, or `expected_event_count` returns fewer
than 10 for warm. Either would mean the horizon *was* implicated and my
reading of A1's scope is wrong.

**And a second, independent falsifier worth naming:** if the guard now
refuses with a *different count* (not 2 of 10), the arm's degeneracy has
moved — plausibly via the Tier-1 scaling, which changed TwoTier's targets —
and that is a new finding rather than the old one.

---

## The four clauses, predicted separately

**All four are conditional on the guard passing.** If it refuses, clauses
1–3 are **not scoreable** and saying so is the result — a partially
degenerate arm's survivors are self-selected, which is exactly what the
guard exists to refuse.

| # | clause | statistic | level | prediction |
|---|---|---|---|---|
| **1** | warm re-join recovery | **M19 p95 (ms), `by_path="warm"`, median over seeds** | per-arm scalar | **NOT SCOREABLE on TwoTier** (guard). PF and Reservation **scoreable and small** — both complete their scripted cycles |
| **2** | cold attach | **M18 p95, `by_path="cold"`** | per-arm scalar | **scoreable on all three**; the cold path was never the degenerate one. **But check `n_never_completed` before quoting** — §34.5a recorded an arm registering its full count while completing **0 of 50** |
| **3** | RLF recovery | **M21 p95, `by_path="reestablish"`** | per-arm scalar | **scoreable**, because the fade is 12,000 slots against t310's 8,000 and `test_g9_scenarios.py` asserts that ratio. **A p95 of exactly 0.0 is the failure signature, not a result** |
| **4** | neighbours unaffected | **ΔM02 and Δp98 (joiner on − joiner off), paired bootstrap** | interval vs zero | **ΔM02's interval contains zero AND is uninformative** — the campaign's own comment records M02 saturated at zero on the neighbours (p98 15.5 ms against a 100 ms PDB, ~6× headroom). **Δp98 is the sensitive instrument and its interval should also contain zero** |

### Clause 4 carries a caveat like C4's, and for the same reason

**ΔM02 cannot move**: a delta of a floored statistic is floored. Its
"interval contains zero" is satisfied by construction and **is not evidence
that the neighbours were unaffected.** Only Δp98 can detect a change, so
clause 4's verdict rests on Δp98 alone and must say so. **Reporting both
without that sentence would be counting one observation twice**, which is
the error G11's C1/C4 pair already made.

---

## What would make this a result rather than a repeat

The informative outcomes, in order:

1. **The guard refuses with 2 of 10 again** → the degeneracy is stable and
   independent of the Tier-1 scaling. G9's row keeps its verdict with a
   stronger cause.
2. **The guard refuses with a different count** → the degeneracy moved;
   new finding.
3. **The guard passes** → my reading of A1's scope is wrong, and clauses 1–3
   become scoreable for the first time.
