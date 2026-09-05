# Finish-the-simulator: the whole remaining surface, in one place

**2026-09-05. An inventory, not a plan — nothing here is started, and no
order is proposed.** Each item says what must be built, roughly what it
costs, whether it is a **scenario / mechanism / metric**, and — the column
that decides sequencing — **whether building it yields a scoreable verdict
or only removes one blocker of several.**

**A separate flag column marks anything that would be a DIVERGENCE FROM THE
DEPLOYED C rather than a missing piece of the port.** Those need a different
justification: the port's defence is fidelity, and a divergence has to be
argued on its own terms, not slipped in as "completing" something.

---

## Summary

| item | kind | cost | scoreable alone? | divergence? |
|---|---|---|---|---|
| **G2** — E-STOP timing | scenario **+** mechanism | **L** | **NO — 2 blockers, and one is now known not to help** | no |
| **G7** — MFBR containment + clipping | **mechanism** | **M** | **NO — half the criterion missing** | **YES** |
| **G9** — join/re-join/RLF recovery | **scenario** | **S** | **YES** | no |
| **G11 C2** — internals stable, no drift | **mechanism + metric** | **M** | **NO — no skip-reason counter exists at all** | **YES** |
| **G11 C3** — CoV(p98) ≤ 15 % | **metric** | **XS** | **YES** | no |
| **G11 C4** — identical verdicts across repeats | **metric** | **XS** | **YES (needs C1, which is done)** | no |
| **G11 C5** — bimodality inspection | **metric** | **S** | **YES** | no |
| **BSR-desync route** (parked) | **scenario** | **S** | **YES — answers a named open question** | no |
| **`verify_claims` staleness** (parked) | **tooling** | **S** | n/a — closes a blind spot | no |

**Cost key:** XS ≈ an afternoon; S ≈ 1 session; M ≈ 2–3 sessions; L ≈ a work
package. These are *build* costs; campaign wall-clock is separate and noted
per item.

---

## G2 — Emergency-stop under worst case (GT-1.2)

**Two independent blockers, and the second one is the reason this is not a
quick win.**

1. **The E-STOP flow is DL** (`sim/fleet.py:179`) while G2's named failure
   mode — the BSR/SR desync — is an **uplink** mechanism. The flow cannot
   reach the failure. *Fix: a UL STOP flow. Scenario work, S.*
2. **TB-size quantisation is planned and unbuilt** — **and WP9 §20.1 measured
   that building it would not close G2.** Replaying every UL grant of a real
   run through OAI's own `nr_find_nb_rb`/`nr_compute_tbs` left the padding
   distribution **completely unchanged**: 13,214 of 13,214 grants at padding
   0 before and after. The operative scale is the gNB's **BSR error at grant
   time** (median 12,194–13,387 bytes) against a truncation window **2–5
   bytes** wide.

**So: adding the UL STOP flow removes one blocker and changes nothing** —
the canonical example of an item that must not be built alone. **And the
second blocker has no known fix**: §20.1 also established the *shape* any
attempt must defeat, an anti-correlation (load a UE until its grants are
PRB-limited and padding is exactly 0; unload it and 38.321 §5.4.5 mandates a
Short BSR rather than a truncated one).

**Verdict: L, and not currently scoreable at any cost.** What it needs first
is a *mechanism hypothesis that survives §20.1*, which is research, not
build.

---

## G7 — MFBR containment and clipping (GT-5.x)

**There is no MFBR *enforcement* anywhere in `sim/`.** Containment (does a
flow stay under its MFBR?) is observable today. **Clipping (does the
scheduler actively hold it there?) is not, and clipping is half the pass
criterion.**

**⚠ DIVERGENCE FLAG.** Before building an enforcement path, establish
whether the deployed C clips at all. `mfbr_bps` reaches `has_pending_gbr`
and the Tier-1.5 floor arming, but no clipping site has been identified in
`ia_p5g_scheduler.c`. **If the C does not clip, building clipping is a
divergence from the deployed system, not a completion of the port** — and
G7 would then be unmeasurable *by construction* rather than unbuilt, which
is a finding, not a gap. **That question is cheap (a grep and a read) and
should precede any build.**

**Verdict: M to build, but do the C-side question first — it may convert
this from "unbuilt" to "structurally out", which is a better answer.**

---

## G9 — Join, loss and recovery (GT-6.1/6.2/6.3)

**The nearest thing to a free verdict on this list.** The machinery exists
and works: `sim/join.py`, `sim/rlf.py`, M18/M19/M21, and `g9_campaign.py`
**already refuses to score a degenerate run** — it exited non-zero with
*"2 'warm' events but the scenario schedules 10"*, which is the guard doing
its job.

**What has to be built is scenario, not mechanism**, and the diagnosis is
already written down: **depth arms `t310`, duration expires it.** The fade
must outlast `t310` = 2,000 ms = **8,000 slots at numerology 2**, and
`sim/driver.py` constructs `RlfDetectorConfig()` itself — so setting
`JoinConfig.rlf_snr_floor_db` does nothing for detection. GT-6.3's scripted
fade was **half the length of `t310`**, so zero join events occurred and
M18/M19 reported instant recovery for a UE that never left.

**Also required by this project's own rule:** assert the expected event
count *and* that nothing failed to complete — M18 already computes
`n_never_completed`, and §34.5a records an arm that logged its full count
while completing **0 of 50** cold attaches.

**Verdict: S, and SCOREABLE ALONE.** Highest verdict-per-unit-cost on the
list.

---

## G11 C2–C5 (GT-7.1 / GT-7.4)

C1 is done. The other four split sharply.

### C3, C4, C5 — metrics only, and all scoreable
- **C3** — CoV(p98) ≤ 15 % per instrument flow across fresh seeds.
  *Trivial arithmetic over the existing soak artefact; needs n ≥ 5 and we
  have n = 10.* **XS, scoreable alone.**
- **C4** — identical PASS/FAIL verdicts across repeats. *C1's verdict vector
  compared across seeds; C1 exists.* **XS, scoreable alone.**
- **C5** — bimodality inspected before signing. *Requires the per-seed p98
  **vector**, not the CoV — and §2.1 records that **C3's named instrument is
  structurally blind to C5**, so C5 cannot be folded into C3.* **S,
  scoreable alone.**

**All three read the soak artefact that now exists post-scaling. This is the
cheapest block on the page and it converts G11 from "one clause of five" to
"four of five".**

### C2 — internals stable, no monotonic drift
**The expensive one, and it is a mechanism gap.** C2 needs floor-fire rate,
`%min_rb` crumb rate and **skip-reason counters** to show no monotonic
drift. **No skip-reason counter exists in `sim/` or `scheduler/` at all**
(§3.2), and there is no trend statistic anywhere.

**⚠ DIVERGENCE FLAG — partial.** The C emits these through
`[P5G-UL-SUMMARY]`. Porting the counters is *completing the port*. But the
**trend statistic** over them is a scoring construct with no C counterpart,
so it belongs in `sim/scorecard.py` as a metric, not in `scheduler/` as
behaviour — and it must not change any scheduling decision.

**Verdict: M, NOT scoreable alone** — the counters and the trend statistic
are both required, and neither is useful without the other.

---

## The two parked items

### The BSR-desync route into the never-granted fault
`docs/attach-path-result-2026-09-05.md` answers *"does a successful attach
clear the lock-out"* — yes, at every fleet size. It does **not** answer
*"can a Short/Truncated BSR empty an already-served UE's per-LCG array and
put it back into the fault"*, **which is the route hardware would actually
take** and which gets no second seed.

**Scenario work, S** — it needs a load pattern that drives a served UE into
a Short BSR while it still holds backlog on other LCGs. The instrument
already exists (`n_never_granted`, and the consolidation
`n_never_granted > 0 ⟺ M08 floored` with 0 counterexamples in 144 runs).

**Scoreable alone: YES**, and it decides whether the frequency finding
transfers to hardware — currently the largest open question attached to a
published result.

### `verify_claims` staleness
Proposal written (`docs/verify-claims-staleness-proposal.md`), not built.
**Tooling, S.** Stamp a content hash of the producing path into each
artefact; `code_state:` becomes `current | historical:<reason>`; fail a
`current` claim whose artefact predates the code. Hash the **AST**, not the
bytes, so comment edits do not trip it.

**Not scoreable — it closes a blind spot.** It would have caught **five of
nine claims** after `0ea02b0`. Its value is that it makes a silent pass
loud, and it is the only item here that protects every other item's results.

---

## What this adds up to

**Four items are scoreable alone**: G9 (S), G11 C3 (XS), C4 (XS), C5 (S),
plus the BSR-desync question (S). **Together they would take G11 to four
clauses of five and add G9 — moving the set from eight guarantees with a
verdict to nine, and G11 from 20 % to 80 % complete — for roughly two
sessions of build.**

**Two items are not scoreable alone and should not be started as if they
were**: G2 (needs a mechanism hypothesis that survives §20.1 before any
build is worth doing) and G11 C2 (counters and trend statistic are jointly
required).

**One item may not be a build at all**: G7's clipping. Ask the C-side
question first; if the deployed scheduler does not clip, G7 is structurally
out and that is a better answer than an unbuilt mechanism.

**Two items carry divergence flags** — G7's clipping and G11 C2's trend
statistic — and both need a justification the port's fidelity argument does
not supply.
