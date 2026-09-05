# Finish-the-simulator: the remaining surface, organised BY DEFECT CLASS

**2026-09-05. An inventory, not a plan — nothing is started and no order is
proposed.**

**Organised by class first, guarantee second, deliberately.** This project's
most expensive recurring failure is **fixing at the site of discovery rather
than at the category** — the population fixed for G6 only, MFBR fixed
nowhere, the decompose fix applied to one of five sites *in its own file*,
the write-at-the-end fix landed in one runner and absent in four. **A
per-guarantee inventory reproduces exactly that shape**, so this one refuses
to be read that way: every item carries a **"where else does this appear"**
line, and it is answered explicitly even when the answer is *nowhere*.

**There was already a known instance waiting** — G9's scenarios carry the
same absolute-time defect found and fixed in G11, left unfixed because G9
was deferred. It leads the list, as class A.

---

## CLASS A — Schedules pinned to absolute time, silently no-op at a shorter horizon

**Defect-log #23.** A schedule sized for one horizon, run at another. Events
past the end are consumed-and-discarded, the run exits 0, and the artefact
looks complete.

**Where this appears — the category question was already asked, and the
answer was written down and then acted on in one place only:**

| site | scheduled events | clipped? |
|---|---|---|
| `sim/scenarios/g11.py` | firmware T+600 s, STOP T+1200 s | **FIXED** (refuses construction below `minimum_horizon_slots()`) |
| **`g9.py::gt61_warm_rejoin`** | 10 cycles from slot 2000, period 1600 | **NO** |
| **`g9.py::gt62_cold_attach`** | 5 cycles from slot 2000, period 3000 | **NO** |
| **`g9.py::gt63_rlf_recovery`** | fade from slot 4000, 12000 slots | **NO** |
| **`g9_campaign.expected_event_count`** | returns *all* events, unclipped | **NO** — the count guard would compare against a number the horizon cannot reach |
| `g12.py` | none — one load per run | n/a |

**Measured:** `gt61_warm_rejoin` at h=8,000 places **6 of its 10 events
beyond the horizon**; at h=4,000, **8 of 10**. `gt63_rlf_recovery` at h=4,000
has its **entire fade** outside the run. **Latent, not active** — at G9's
designed horizon (20,000) everything fits, so no published G9 result is
affected.

**Item A1 — fix the class, not G9.** *Scenario. Cost XS-S.* The fix is the
one already written for G11 (`minimum_horizon_slots()` derived from the
schedule + refuse construction below it), applied to all four G9 sites **and
to `expected_event_count`**. **Scoreable alone: no — it is a correctness fix,
not a measurement.** **Divergence: no.** **Where else: the five sites above,
and `g12.py` confirmed n/a.**

> **Listing "fix G9's scenario" without naming the class is the failure this
> section exists to prevent.** A1 is not G9 work that happens to be shared;
> it is class work of which G9 is four sites.

---

## CLASS B — Built, tested, green, and never reached or never observable

**The 2026-09-03 audit found twelve instances.** Two of the remaining
guarantees are blocked by new members of this class, which is why they are
grouped rather than listed under their guarantees.

**Item B1 — G7's MFBR clipping. ⚠ ANSWERED AND RECLASSIFIED 2026-09-05 —
NO LONGER A CLASS-B ITEM.** The grep was run
(`docs/g7-clipping-question-2026-09-05.md`) and **both halves of the recorded
blocker were wrong**: the C clips at three sites (both arms, both
directions), and **the port implements all three faithfully — there is no
divergence flag.** What is clipped is the **GBR target, not delivered
bytes**: `overflow = lcg_estimate - target; be_bytes += overflow`, so excess
becomes best-effort and stays deliverable. GT-4.3's criterion is about
delivered bytes, which are measurable today. **G7 moves to CLASS D (a route
not modelled) as item D3: it needs an aggressor SCENARIO, not a mechanism.
Scenario + metric, cost S–M, SCOREABLE ALONE.** See D3 below.

**Item B2 — G11 C2's skip-reason counters.** *Mechanism + metric. Cost M.*
C2 needs floor-fire rate, `%min_rb` crumb rate and **skip-reason counters**
to show no monotonic drift. **Confirmed: no skip-reason counter exists in
`sim/` or `scheduler/` at all** — the only occurrences are in
`test_g11_drift.py`, which asserts `"skip_reasons": None  # does not exist`
and that the reason string says *"hardware log field"*. **The test already
documents the absence**, which is this class handled correctly.
**Scoreable alone: NO** — the counters and the trend statistic are jointly
required and neither is useful without the other.
**⚠ DIVERGENCE: PARTIAL.** Porting the counters completes the port (the C
emits them via `[P5G-UL-SUMMARY]`). **The trend statistic has no C
counterpart**, so it belongs in `sim/scorecard.py` as a metric, never in
`scheduler/`, and must not change a scheduling decision.
**Where else:** the five driver counters that reach `summary` and are
**dropped by `RunRecord.from_summary`** are the same *unobservable* half of
this class, and `harq_masked_flow_double_grant_count` is the sharpest case —
README §8 calls it a standing Phase-2 guard while it reaches no record, no
corpus and no test, so **that check cannot currently fail.**

---

## CLASS C — Checks that cannot fail, or cannot fail at the level the failure happens

**Item C1 — `verify_claims` staleness.** *Tooling. Cost S.* Proposal written
(`docs/verify-claims-staleness-proposal.md`), not built. It re-derives a
figure from an **artefact on disk**; `0ea02b0` changed **code** and rewrote
no artefact, so all 9 claims passed while `G1.M01.n10.twotier.median =
90.125` had become stale against post-scaling code's 87.78.
**Scoreable alone: n/a — it closes a blind spot.** It would have caught
**five of nine claims**. **Divergence: no.**
**Where else — this is the class with the most live members:**
`harq_masked_flow_double_grant_count` (B2, cannot fail); the M09-hoist
`--check` that read `RunRecord`s while the change was in `scorecard.py`
(wrong *layer*); the 22 GiB per-process watchdog against a machine-level
exhaustion (wrong *aggregation*); and **the same generator-vs-output shape as
`stage6_partA.json` — fixing a producer does not fix what it already
wrote.** C1's fix (stamp the producing path's AST hash into the artefact) is
the only one of these that generalises to the others.

---

## CLASS D — A route or mechanism that is simply not modelled

**Item D1 — the BSR-desync route into the never-granted fault.** *Scenario.
Cost S.* `docs/attach-path-result-2026-09-05.md` answered *"does a successful
attach clear the lock-out"* — yes, at every fleet size. It did **not** answer
*"can a Short/Truncated BSR empty an already-served UE's per-LCG array and
put it back into the fault"*, **which is the route hardware would actually
take** and which gets no second seed.
**Scoreable alone: YES** — and it decides whether the frequency finding
transfers. The instrument exists (`n_never_granted`, and the consolidation
`n_never_granted > 0 ⟺ M08 floored`, **0 counterexamples in 144 runs**).
**Divergence: no** — the desync is already faithful (`sim/bsr.py`'s memset
mirrors the C's); only the *load pattern that triggers it* is missing.
**Where else:** this is the last unexplored branch of the cold-start finding.
Nowhere else.

**Item D2 — G2's UL STOP flow.** *Scenario. Cost S.* The E-STOP flow is
**DL** (`sim/fleet.py:179`) while G2's named failure mode — the BSR/SR
desync — is **uplink**, so the flow cannot reach the failure.
**Scoreable alone: NO, AND THIS IS THE CANONICAL EXAMPLE.** It removes one
blocker of two. **The second blocker has no known fix**: WP9 §20.1 measured
that TB-size quantisation would **not** close G2 — replaying every UL grant
through OAI's own `nr_find_nb_rb`/`nr_compute_tbs` left padding
**completely unchanged, 13,214 of 13,214 grants at padding 0 before and
after** — because the operative scale is the gNB's BSR error at grant time
(median 12,194–13,387 bytes) against a 2–5 byte truncation window.
**Divergence: no.**
**Where else:** the DL/UL direction mismatch between a scenario's flow and
its named failure mechanism appears **once more**: G5's subject flow is UL
while both arms' DL ranking keys are out of scope on the parametric mix —
already documented, not a defect there, but the same class of "the flow
cannot reach the mechanism".

**Item D3 — G7's aggressor scenario** *(moved here from B1, 2026-09-05).*
*Scenario + metric. Cost S–M.* Asset B's camera offered at **2× MFBR**,
Asset A on a full nominal profile, and a **three-part** verdict: A's SLO,
B's camera delivered vs MFBR, **and B's own other flows' SLO** — GT-4.3
requires containment to hold *inside* the misbehaving asset, which is the
clause easiest to drop.
**Scoreable alone: YES.** **Divergence: no** — the port matches the C at all
three clip sites.
**Where else:** `FlowConfig.aggressor_multiplier` is consumed in
`sim/traffic.py:168` but **never set outside tests** — a standing class-B
member this item would retire. And its known issue applies: for `xr_video`
it scales fragments *after* fragmentation and can exceed `fragment_bytes`,
so a camera aggressor must scale `traffic_params["avg_bytes"]` instead.

**G2 overall: L, and not scoreable at any cost today.** What it needs first
is a mechanism hypothesis that survives §20.1's anti-correlation — research,
not build.

---

## CLASS E — Pure scoring, no simulator change

**The cheapest block on the page, and all three read an artefact that now
exists post-scaling** (`sweeps/postscaling-2026-09-05/g11_c1_soak.json`,
30/30 runs at 7.2M slots).

**Item E1 — G11 C3**, CoV(p98) ≤ 15 % per instrument flow across fresh
seeds. *Metric. Cost XS.* **Scoreable alone: YES.** Needs n ≥ 5; we have 10.
**Divergence: no.** **Where else: nowhere — no other guarantee uses a CoV.**

**Item E2 — G11 C4**, identical PASS/FAIL verdicts across repeats. *Metric.
Cost XS.* C1's verdict vector compared across seeds; **C1 exists**.
**Scoreable alone: YES.** **Divergence: no.** **Where else: nowhere.**

**Item E3 — G11 C5**, bimodality inspected before signing. *Metric. Cost S.*
Needs the per-seed p98 **vector**, not the CoV — **C3's named instrument is
structurally blind to C5**, so it cannot be folded in.
**Scoreable alone: YES.** **Divergence: no.**
**Where else — yes, and it matters:** "an aggregate that cannot see the
structure it is summarising" is exactly the **decompose-before-attributing**
class, which has four recorded instances in one WP9 item and **was applied to
one of five sites in its own file**. C5 is a fifth site of that same class,
approached from the scoring side.

---

## The shape, before any order is picked

| class | items | scoreable alone | divergence flags |
|---|---|---|---|
| **A** absolute-time schedules | A1 (5 sites, 4 of them G9) | no — correctness fix | none |
| **B** built but unreachable | B1 (G7), B2 (G11 C2) | **neither** | **both** |
| **C** checks that cannot fail | C1 (`verify_claims`) | n/a | none |
| **D** route not modelled | D1 (BSR-desync), D2 (G2) | **D1 yes, D2 no** | none |
| **E** pure scoring | E1, E2, E3 (G11 C3/C4/C5) | **all three** | none |

**Four items are scoreable alone: D1, E1, E2, E3** — plus **G9 becomes
scoreable once A1 lands and its fade is made to outlast `t310`** (2,000 ms =
8,000 slots at numerology 2; and `sim/driver.py` constructs
`RlfDetectorConfig()` itself, so setting `JoinConfig.rlf_snr_floor_db` does
nothing for detection). **That block takes G11 from one clause of five to
four, adds G9, and answers the largest open question attached to a published
result — for roughly two sessions.**

**Three items must not be started as if they were scoreable:** B1, B2, D2.

**Two carry divergence flags** — B1 and B2 — and both need a justification
the port's fidelity argument does not supply.

**And the single highest-leverage item is C1**, because it is the only one
that protects the correctness of every other item's results.
