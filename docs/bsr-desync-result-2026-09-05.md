# The BSR-desync question: an already-served UE cannot fall back into the fault

**2026-09-05.** Scored against
`docs/rejoin-seed-and-desync-registration.md` Part 2, registered first.

**This is the question that decides whether the cold-start finding
transfers.** Model C and the re-join seed both supply a BSR the sim never
generates, so both answer *"does a successful attach clear the lock-out"* —
yes. Neither answers *"can a UE that HAS been served lose its estimate and
fall back in"*, and that is the route hardware would take, because hardware
always grants during attach.

**Answer: no, and there is a structural reason.** G5's and G10's numbers are
**upper bounds**, and the sentence that makes that defensible is in §3.

---

## 1. What was measured

`scripts/bsr_desync_probe.py`, across **three arms × 3 seeds × six
configurations**: n_ues 8 and 16, load_mult 1.0 and 2.0, duty_cycle 1.0, 0.5
and 0.1, `shared_lcg` on and off.

**An episode is only a DESYNC if it begins after the UE's first grant.** The
first version of the probe did not timestamp episodes and reported *"8
episodes"* on 8 UEs — **1 per UE, a number that factors into the run's own
dimensions**, which this project's own rule says is almost never a
measurement. It was the initial cold start, counted as a desync.

| | result |
|---|---|
| **cold-start episodes** | one or more per UE, every run — the known fault |
| **DESYNC episodes** | **0, in every configuration, on every arm and seed** |
| **latched UEs** | **0** |

## 2. And the precondition never occurred, which is reported as that

Per the registration: *"If clause 1 finds nothing at all… the honest
statement is that the question was not answered — the precondition did not
occur."* **So the format counts were measured too**, and they say why:

| BSR format chosen | count (all configurations) |
|---|---|
| `long`, omitting 0 LCGs | tens of thousands |
| `short`, omitting 0 LCGs | tens of thousands |
| **`short_trunc` / `long_trunc` (the truncation route)** | **0** |
| **`none` (the emptiness route)** | **0** |

**Neither desync route ever fired.** `short` is chosen only when exactly one
LCG is active (`_select_format`'s `len(active_lcgs) < 2` guard), so it omits
nothing; `long` reports every active LCG. **This is consistent with WP9
§20.1's independent finding** that padding is 0 on 13,214 of 13,214 grants —
`short_trunc` requires an exact `padding == SHORT_BSR_SZ` and `long_trunc`
requires `LONG_BSR_FIXED_SZ ≤ padding < long_bsr_sz`.

**Attempts to force it, all failed:** bursty traffic at duty 0.1 (to drain
every LCG together), doubled load, 16 UEs, and a shared LCG (fewer LCGs to
drain simultaneously).

---

## 3. THE STRUCTURAL REASON — the sentence that makes the upper bound defensible

> **The per-LCG array is zeroed at exactly one place in the normal path:
> inside `on_ul_grant`, immediately before `_assemble` repopulates it. And
> `on_ul_grant` is called only for a UE that has just received a grant.**

The consequences follow directly:

1. **A served UE's array is emptied only at the instant it is being
   served** — and the same call repopulates it whenever any LCG holds
   backlog.
2. **The only way to leave it empty is `fmt == "none"`, which requires zero
   true backlog on every LCG at grant time — i.e. the UE has nothing to
   send, so there is nothing to starve.**
3. **Therefore a served UE cannot be left holding real backlog with an empty
   array.** The fault needs the array empty *while backlog exists*, and the
   only event that empties it also fills it if backlog exists.

**The asymmetry is the whole finding:** a never-granted UE's array is empty
because **it was never written**. A served UE's array is empty only
transiently, at a moment when it is by definition being served. **Being
unserved is the only way to stay empty.**

### The one route that survives in principle, and its status

`per_lcg_true` is computed from **true backlog** while eligibility uses
**`bytes_reported`**. So a UE granted on a stale report while its true
backlog is zero would take `fmt == "none"`, zeroing the array, and could
then receive new traffic. **That route exists in the code.** It requires
`fmt == "none"`, which fired **0 times across every configuration tested**.

**Reported as: reachable in principle, not reached in practice at any
configuration tried.** Not "impossible".

---

## 4. What this settles

**G5's and G10's numbers are UPPER BOUNDS, and now for a stated reason
rather than a hedge.**

- The cold-start entry is **sim-specific** — hardware grants during attach
  (RACH msg3, RRC on SRB), and this simulator has neither.
- The desync entry, which hardware *could* take, **does not latch**: the
  event that empties the array is itself a grant.
- **So on hardware the fault should be rare and self-clearing**, and the
  frequencies measured here (Reservation 7/10 seeds on M05, the
  PF 8 / Reservation 4 / TwoTier 4 fleet boundary, the 35 % blackout rate)
  are ceilings.

**What does NOT change:** the mechanism is real and is the product's. The
Tier-1.5 floor still cannot arm in the fault it exists for, and reservation
still has no floor at all — `docs/hardware-findings.md`. **A fault that is
rare is still unhandled**, and the three questions there stand unaltered.

**And the sharpest remaining risk is one this experiment does not cover:** a
UE that loses its context and re-attaches on a *loaded* cell enters exactly
the cold-start state, and `docs/attach-path-result-2026-09-05.md`'s
`stagger_only` arm measured that as **strictly worse** than a cold start at
t=0. Hardware grants during attach, so it should clear — **but that is the
same argument this document just made, and it has not been tested with a
real RA procedure because none exists here.**
