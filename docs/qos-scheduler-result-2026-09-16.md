# A QoS-aware scheduler for the deployed cell — result, method and recommendation

**2026-09-16. Simulation only. Nothing here has been validated on hardware.**

This document stands alone: it states what was built, what was measured, what
the answer is, and what is not yet known. Supporting detail is in
`docs/configsched2-diagnosis-2026-09-16.md` (per-increment expectations,
falsifiers and traces), `docs/campaign-cell-2026-09-16-linux.md` (the running
campaign log) and `docs/test-definition-changes-2026-09-16.md` (corrections to
what the tests measure).

---

## 1. The answer

**Recommended arm: `ConfigSched2X7+CG`.** Conservative fallback:
`ConfigSched2+CG`.

Compared like-for-like — both arms with the same restricted configured-grant
configuration — the recommended arm carries **more than three times the
admissible camera fleet** and is ahead on isolation, joins and degradation
order, at a small cost in downlink STOP latency.

| statistic | `ConfigSched2+CG` | `ConfigSched2X7+CG` |
|---|---|---|
| **G5 admissible camera fleet** | 7 | **24** |
| **G5 load knee** | ×1.1 | **×1.4** |
| G3 heartbeat part-3 boundary | 24 | 24 (tied) |
| G10 admissible fleet | 8 | 8 (tied) |
| G6 isolation, UL flood (part A/B) | 221/219 of 224 | **243/248 of 249** |
| G9 informative cells passed | 11 of 12 | **12 of 12** |
| G7 containment, camera (vs control) | +11.5 ms | **+6.9 ms** |
| G7 containment, telemetry (vs control) | +15.5 ms | **+6.0 ms** |
| G7 clause 2 (over-driven camera / MFBR) | 1.07× | 1.08× |
| G7 clause 3 (B telemetry p98) | 17.8 ms | **12.0 ms** |
| G2 missed STOPs, cap 4 | **181** / 18 300 | 191 / 18 300 |
| G2 missed STOPs, cap 2 | **263** / 18 300 | 275 / 18 300 |

**It is not a strict dominator.** It loses on G2 (both caps) and on a few G1
percentile points. Everything else is a win or a tie.

**The single most important finding is not about the scheduler.** Configured
grants are worth more than every scheduler change measured here combined, and
CG is a MAC feature that runs ahead of the scheduler — not the scheduler's to
spend. Any future comparison on this cell should be made with CG on.

---

## 2. What the system is

**The cell** is the deployed one (`docs/conf/gnbx310.conf`,
`sim/scenarios/deployed_cell.py`): numerology 1, 106 PRB, TDD `DDSUU` every
2.5 ms with a 6/2/6 special slot, two MIMO layers. A per-slot cap of **4
scheduled UEs** (M-6) applies.

**The guarantees** are factory QoS promises, each measured by its own procedure:

| group | guarantees | what it isolates |
|---|---|---|
| A — downlink deadline | G1 (GT-1.1 `cmd_vel`), G2 (GT-1.2 emergency STOP) | DL ordering, the DCI cap, retries inside a short PDB |
| B — uplink liveness | G3 (GT-2.2 telemetry heartbeat) | when a small periodic UL flow is next served |
| C — uplink video | G5 (GT-3.1/3.2/3.3 camera) | sustained rate, frame assembly, GFBR per window |
| D — isolation | G6 (GT-4.1/4.2 flood), G7 (GT-4.3 over-driven GBR) | harm from a bad actor |
| E — capacity | G10 (GT-5.2), G12 (GT-7.3) | the cell at and past its limit; the order classes break in |
| F — transitions | G9 (GT-6.1/6.2/6.3) | join, re-join, RLF recovery |

**Deferred and not measured here: G4 (GT-2.3), G8, G11.**

**The arms.** Three faithful ports of the deployed OAI scheduler (PF,
Reservation, TwoTier); one flagged divergence of the two-tier port
(`ProtoRRageD2`); and the configuration scheduler (`ConfigSched2`), a
`sim/baselines/` scheduler that plans a window of *visits* per flow and then
realises them on harmonic tracks.

`X7` denotes `ConfigSched2` with four flags on, all default-off:
`density_budget` + `importance_order` + `byte_sized_visits` + `unit_share_cap`.
`+CG` denotes restricted Rel-16 configured grants (TS 38.321 §5.8.2), applied
through one driver flag, identically available to every arm.

---

## 3. How the answer was reached

### 3.1 Diagnose before encoding

A per-slot decision trace (`ConfigSched2.decision_sink`, inert unless hooked and
byte-identical when off) established what actually binds: as load rises,
`cap_skipped` goes 11 % → 30 % → 37 % of units considered while `prb_exhausted`
*falls*, and `visit_budget_bound` reads **0 at every load**. The plan was
budgeting a window total while the constraint that binds is **per-slot
concurrency** — the DCI cap.

### 3.2 Five encodings, each registered before it was built

Every increment had its expectations and falsifiers written down first, and the
cheapest falsifier was checked before spending a campaign.

| flag | what it changes | headline result |
|---|---|---|
| E1 `density_budget` | charge a visit its real harmonic density, not one window-total unit | G5 fleet 6 → 7; **G3 boundary 10 → None** |
| E2 `plan_share_sizing` | a promised visit carries its plan share | camera crumbs −79 %; **G10 10 → 8** |
| E3 `importance_order` | contracted flows meet their deadline bound before best-effort bids | G5 6 → **8**; G3 None → 4 |
| E4 `byte_sized_visits` | size by byte need, not a deadline-inflated count | fixed the 300 B→150 B split; **G3 → None** |
| E5 `unit_share_cap` | bound the **unit's** total to a cap-th of the slot | PRBs/grant 52 → 26; units/slot 1.71 → **3.59** |

**Without CG, none of these dominates.** They map a real frontier: the baseline
holds the heartbeat (G3 boundary 10) with a weak camera (fleet 6); X7 holds the
camera (fleet 8, knee 1.3) with a weakened heartbeat (boundary 6).

### 3.3 Configured grants dissolve the frontier

CG closes the uplink heartbeat class structurally. With CG on, **G3 sits at the
top of its axis (boundary 24) on both arms**, so group B stops being the price
of group C — and X7's camera advantage survives intact (fleet 24 against 7).

### 3.4 The mechanism, traced rather than guessed

E1 was *correct* — it encoded the binding constraint — and it still broke group
B, for two reasons found by trace:

1. **It deleted the repair that was protecting deadlines.** The baseline
   deliberately overcommits, and the period-assignment pass then sheds
   best-effort densest-first and shortens contracted periods with the slack.
   E1 made the plan exactly feasible, removing the overcommit *and* the only
   importance-ordered shedding in the system. E3 makes that explicit instead.
2. **It moved the cell from DCI-bound to PRB-bound.** Grants nearly halved
   (11 858 → 6 154) because PRBs per grant doubled (26 → 52 median).
   `per_visit_cap` bounds a *flow*, but a UL unit is `(ue_id, -1)` — every
   uplink flow of a UE shares one grant sized from their **sum** — so nothing
   bounded the total. E5 fixes that, and the defect is **latent in the baseline
   too**.

---

## 4. Verdicts that measurement overturned

Recorded because the corrections are the evidence that the method worked.

* **All three apparent costs of the recommended arm belong to CG, not to the
  scheduler.** G9's 5 join failures, G10's 10 → 8, and clause 2's loosening are
  *identical* on the baseline with CG. The recommended arm in fact mitigates
  two: its join failures are far less severe (catastrophic 2 and 1 against 10
  and 9), and it passes one more informative cell.
* **A raw p98 measured under an aggressor got the verdict backwards three
  times.** Such a statistic sums the cell's own load and the aggressor's
  marginal harm. A paired no-aggressor control was built for G7 and separates
  them; on containment the recommended arm is *ahead* of the baseline, not
  behind. **No G7 clause-1 figure should be quoted without its control.**
* **Two of my own registered hypotheses were falsified**, and are kept in the
  record: E4's message-splitting fix made G3 *worse*, and a first attempt at a
  G6 threshold reclassified *zero* rows — a check that could not fail.
* **G6's own definition was wrong in two ways** and was corrected as a
  re-scoring (no runs repeated): part A ignored whether the no-flood control had
  already failed, and part B compared a ratio with no absolute floor. One
  published claim was withdrawn as a result — `cmd_vel` p98 passes G6 part B
  30/30 on every arm.

---

## 5. What is open, and what is not claimed

* **Not validated on hardware.** Everything here is simulation on a model of the
  deployed cell. The purpose of this work was to choose what to validate.
* **Group A deficit is real and unexplained.** The recommended arm misses 10
  more STOPs at cap 4 and 12 more at cap 2 than the fallback. It has not been
  traced.
* **G9's join failures are real, and neither arm has an advantage.** The
  occupancy axis was mis-anchored (derived from the *previous* cell's G10
  boundary) and has been re-anchored to this cell's measured boundary, taking
  unscoreable cells from 12 of 36 to **0 of 36**. The failures survive that fix:
  the recommended arm fails one join at 0.25× the boundary — two UEs at nominal
  load — which is not a capacity effect and is **untraced**. On the anchored
  axis the two arms are **exactly tied at 31 PASS / 5 failures**; an earlier
  claim that they separated came from an artefact whose verdict grouping omitted
  `committed_mult`, now fixed. Their *distributions* differ (the fallback is
  clean below the boundary and fails 4 of 5 at 1.5×; the recommended arm spreads
  one across nearly every level), but neither leads on G9.
  Separately, **"JOIN FAILURE" is largely not about joins here**: all 17 failing
  cells met the 90 % join-yield rule and 16 were caused by an SRB dialogue still
  in flight at the horizon. Tested against load, the stall-versus-artefact
  dichotomy **does not hold**: the fallback looks load-driven (0 below the
  boundary, 0.13 at 1.5×) while the recommended arm looks load-independent
  (~0.02 scattered, **zero** at the highest load). It occurs only in `cold` and
  `rlf` — never in `warm` — and 12 events in 720 runs cannot separate two
  mechanisms. **No verdict drawn**; the 31/5 tie is a coincidence of counts, not
  of behaviour.
* **G4, G8 and G11 are not measured.**
* **DL SPS is not implemented.** It is the downlink analogue of CG, inside the
  Rel-16 baseline (TS 38.321 §5.8.1; 8 configurations per BWP against CG's 12),
  and the downlink has had no intervention equivalent to the one that dominated
  every scheduler change on the uplink. It attacks the DCI axis, **not** the
  retry axis, so it is not an obvious fix for G2.
* **G7 clause-1 controls exist for four arms**, not for the full historical
  record; older clause-1 figures remain upper bounds on harm.

---

## 6. Reproducing this

```bash
uv run pytest sim/tests -q                              # suite
uv run python scripts/regression_corpus.py --check      # numeric drift
INC=e8 ARM=ConfigSched2X7+CG bash sweeps/cs2-increments/run_increment.sh
INC=e9 ARM=ConfigSched2+CG   bash sweeps/cs2-increments/run_increment.sh
uv run python sweeps/cs2-increments/compare.py sweeps/cs2-increments/e8 \
    --before sweeps/cs2-increments/e9 \
    --arm-before "ConfigSched2+CG" --arm "ConfigSched2X7+CG"
```

Artefacts: `sweeps/cs2-increments/{inc9,e1,e2,e3,e5,e6,e7,e8,e9}/aligned/*.json`;
G7 controls in `sweeps/cs2-increments/g7_controls*.json`. Every arm resolves
through `scripts/proto_arms.py`, the single registry.

**Known suite state:** three tests fail (`test_verify_claims` ×2,
`test_wp9_sweep_memory` ×1) and **pre-date this work** — verified by running
them at HEAD with the changes stashed. `regression_corpus.py --check` is clean,
and `verify_claims --check` reads 8/22, identical to the baseline measured
before any of this work began.

**Two runner bugs were found and fixed while producing these results**, and any
earlier artefact is affected by them:

1. **Three runners kept private copies of the arm table** (`g3_stress`,
   `g9_stress`, `g4_postsilence`). Two raised on a newly registered arm name, so
   an increment's G3 and G9 steps died in ~1 s while the other seven scored — a
   partial result reported under an arm name the log still carried. The first
   two now delegate to `scripts/proto_arms.py`, verified identical on all 19
   pre-existing arm names.
2. **`g9_stress`'s verdict grouping omitted `committed_mult`**, so every
   occupancy level sharing a UE count was pooled and written three times under
   three keys — an artefact that *looked* per-level and was not. Invisible on
   the old axis, where every level had a unique UE count. The per-run ledger was
   always correct, so fixing it required no re-simulation.

**G9 results produced before 2026-09-16 carry the old, mis-anchored axis** and
should be re-read against §5 rather than quoted directly.
