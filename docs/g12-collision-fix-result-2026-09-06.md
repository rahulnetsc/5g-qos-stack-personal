# G12's collision fix and re-score — RESULT

**Registered** `docs/g12-collision-fix-registration.md`, before the fix was
written. **Artefact** `sweeps/g12-rescore-2026-09-06/g12.json`, 10 seeds × 3
arms × 8 ramp points × 3 scoreable cells + the 4-permutation control.

## Verdict: **G12 has a verdict again — the count goes ten → eleven.** Clause
## 4 still FAILS, but **two of my six registered expectations were wrong**,
## and one of them is the falsifier I named.

---

## 1. The fix

The flood is now **5QI 8** with `priority_level` **pinned to 90** (5QI 9's), so
the change is purely de-aliasing: 8 and 9 are the same standardised non-GBR
class (300 ms PDB, 1e-6 PER) and every other QoS field was already declared
explicitly. Stricter than the 5QI 85 → 86 precedent, which let priority and
LCG move.

## 2. Scoring the registered expectations

| id | expectation | outcome |
|---|---|---|
| **E1** | clause 4's direction survives | **HOLDS on PF and TwoTier. FAILS on Reservation** — §4 |
| **E2** | telemetry gets worse or equal, **never better** | **FAILS on Reservation** — the registered falsifier fired, §4 |
| **E3** | background moves **>0.02 % and <2×** | **REFUTED — the move is up to ~1,200×**, §3 |
| **E4** | non-colliding cells bit-identical | **PASSES — `mixed_n8` has 0 differences**; only `drone_heavy_n8` moved (977) |
| **E5** | the relabel is behaviourally inert | **PASSES** — on two non-colliding compositions every other flow, the system record, and the flood itself are identical except the key |
| **E6** | 31 flows, restored DL record | **PASSES** — 31 flows, no `(ue, qfi)` repeated |

**E4 and E5 passing is what licenses reading E1–E3 at all**: the fix is scoped
to the colliding pair and changes nothing else.

## 3. E3 refuted — the phantom DL drain was most of the background, not a correction

I predicted the background figure would move by less than 2×. Measured, at
`drone_heavy_n8` (median over 10 seeds, Mbps):

| ramp | PF old → new | Reservation old → new | TwoTier old → new |
|---|---|---|---|
| ×2.3 | 17.41 → **8.53** (2.0×) | 16.83 → **0.079** (213×) | 17.33 → **1.35** (12.9×) |
| ×3.3 | 17.46 → **8.51** | 0.438 → **0.002** | 16.78 → **0.311** |
| ×8.0 | 17.49 → **8.51** | 0.435 → **0.002** | 0.943 → **0.002** |

**Up to ~1,200× on Reservation, against my bound of 2×.** The reasoning error
is worth naming: I treated the DL drain as a *contamination* of a
mostly-legitimate figure. It was the other way round — **on the QoS arms most
of the background's measured throughput came from DL grants draining a UL
queue that should never have been shared.** Once de-aliased, the QoS arms
starve the contract-less background, which is what a QoS scheduler is supposed
to do to a 50 Mbps flood with no contract.

**Consequence for the published figure:** *"5QI 9 still carrying 11.6 Mbps"*
was measuring, in substantial part, an artefact of the shared queue. The
corrected comparable figure at the point telemetry floors is **8.5 Mbps (PF)**
and **14.6 Mbps (TwoTier at ×1.6)**.

## 4. E2 failed — and it is the falsifier, so it is reported as one

The registration said: *"If E2 fails — telemetry IMPROVES after the fix — then
the published clause-4 failure was partly the collision, and G12's headline
finding is weaker than reported."*

**Telemetry M02, `drone_heavy_n8`, median over 10 seeds:**

| ramp | PF old → new | Reservation old → new | TwoTier old → new |
|---|---|---|---|
| ×1.0 | 0.0000 → 0.0000 | 0.0000 → 0.0000 | 0.0035 → **0.0165** worse |
| ×1.6 | 0.0000 → 0.0000 | 0.0000 → 0.0000 | 0.4477 → **0.9099** much worse |
| ×2.3 | 0.3602 → **0.9206** much worse | 0.1115 → **0.0792 BETTER** | 0.9796 → 0.9796 |
| ×2.7 | 0.9674 → 0.9821 worse | 0.3958 → **0.3260 BETTER** | 0.9837 → 0.9837 |
| ×3.3 | 0.9918 → 0.9918 | 0.9653 → **0.9332 BETTER** | 0.9878 → 0.9878 |

**On PF and TwoTier telemetry is worse or equal everywhere, as predicted — the
failure is real and on TwoTier it is now WORSE, floored at ×1.6 rather than
×2.3.** On **Reservation it improves at three of eight ramp points.**

**So the published clause-4 numbers were partly the collision, on one arm.**
Not the finding as a whole — PF and TwoTier carry it more strongly than before
— but Reservation's published telemetry degradation was overstated.

**And E1 fails on Reservation for a second, separate reason:** clause 4's FAIL
pattern is *"telemetry gap grows while bg still moves bytes"*. Post-fix,
Reservation's background collapses to **2 kbps** by the time telemetry floors,
so **the two halves no longer co-occur on that arm** — there is no "while bg
still moves bytes". Clause 4 as written is not satisfied on Reservation; it is
satisfied, more strongly than published, on PF and TwoTier.

## 5. What G12's verdict now is

- **Clause 4 FAILS on PF and TwoTier**, inside GT-7.3's own ramp: telemetry
  M02 ≥ 0.92 while the background still carries **8.5–14.6 Mbps**. **TwoTier
  floors at ×1.6, one ramp point earlier than published.**
- **Clause 4 is not satisfied as written on Reservation** — telemetry floors,
  but the background is gone by then.
- **The ordering is still not established.** The permutation control still
  flips it (PF `[4,2]`×10 canonical; TwoTier `[2,4]`×6/`[4,2]`×3 in one cell
  and `[4,2]`×7 in another). Unchanged conclusion, and the registered
  declaration-order question (`docs/declaration-order-in-g7-registration.md`)
  is the same artefact.

## 6. Two instrument defects found on the way, both mine

**(a) The scorer's population followed the label, not the population.**
`bg_bps` selected `qfi == QFI_BG`, so relabelling the flood 9 → 8 silently
dropped it from the sum: **11.6 Mbps → 4 kbps**, which looked like a
catastrophic behaviour change and was a selector reading a different
population. This is the population defect a fourth time, with a *label
change* as its cause rather than a boundary coercion. Fixed by selecting on
`BG_QFIS`, derived from the scenario module's own constants rather than
restated.

**(b) A re-run that reused its bank scored nothing.** After fixing the
selector I re-ran to the same `--out`; `RunLedger` correctly resumed 240
banked runs whose payloads already contained the old `bg_bps`, so **the
scorer change never executed and the artefact was byte-identical**. Caught by
checking the artefact's mtime against the edit, not by reading the log — the
log said "wrote". Re-run to a fresh `--out`. **A bank makes a scorer change
invisible unless the bank is invalidated**, which is worth knowing before the
next scorer fix.

## 6a. A third defect the SUITE caught, and the label choice it forced

`test_bg_is_5qi_9_and_not_the_5qi_8_aggressor` failed on the fix, and it was
right to: **5QI 8 already means "aggressor"** in `sim/parametric.py` and
`sim/scenarios/g9.py`, and both 8 and 9 sit in `Scorecard.NON_PROTECTED_5QI`,
so a mix-up would load a cell correctly and be **invisible to every
protected-fleet statistic**.

**8 is nonetheless the only available label, and the constraint that settles
it is the one that test names.** The flood must be **non-protected** (no
contract; it must never enter a fleet statistic) and must keep **5QI 9's
300 ms PDB**. Only **8 and 9** satisfy both, and 9 is what it is aliasing
against. **5QI 6 has the same 300 ms PDB but is NOT in `NON_PROTECTED_5QI`**,
so choosing it would have scored a 50 Mbps flood as protected fleet — a worse
defect than the one being fixed, and one that would have been invisible.

The hazard is handled by construction rather than by avoiding the number: the
flood is the **only** 5QI-8 flow in a G12 scenario (asserted), and the scorer
selects the background as a **population**, not a label.

## 7. The category question, asked properly

`sim/tests/test_flow_key_collision.py`'s docstring asserted the category
answer was **zero**. **It was wrong**, and a published result did lose a flow.
The first sweep enumerated the **nullary** scenario functions; the collision
is reachable only through a **parameterised** builder, at particular
compositions and fleet sizes, and only with the flood on.

`sim/tests/test_flow_key_collision_sweep.py` replaces it: it enumerates
builders **by reflection**, drives them over a grid (all four compositions ×
two fleet sizes × flood on/off, plus G9/G11/parametric/nullary), and
**asserts its own coverage**, so a new builder fails loudly rather than
widening the blind spot. **34 cases, all clean after the fix.**

**Verified it could have failed:** reverting `QFI_BG_UL` to 9 makes it fail on
**four** grid points — `drone_heavy` n=8 *and* `mixed`/`ugv_heavy` at **n=4**.
**So the collision was a property of the builder at several parameter points,
not one cell**; the campaign only ever ran n=8, which is why only
`drone_heavy` surfaced.

**The stale claim is corrected at source**, in the docstring that made it.
