# G5's falsifier: does an attach-path grant remove the starvation?

**Registered 2026-09-05, BEFORE anything is built.** Same discipline as
`docs/g5-ranking-map.md`, and for the same reason: this experiment exists to
decide whether a measured frequency transfers to hardware, and an
expectation written after the data is not an expectation.

**The question, stated so it can come out either way.** This simulator has
no attach procedure, so a UE enters the never-granted fault at **cold
start** — all N tie at slot 1 and the PRB budget picks a prefix. Hardware
runs RACH → Msg3 → RRC setup, during which a UE is granted outside this
ranking, so it would enter the fault only by **BSR desync**. If an attach
path clears the starvation at every fleet size, the *mechanism* stays a
product finding and the *frequency measured here* is sim-specific. If it
does not, the frequency transfers.

---

## 0. What is being built, and what is NOT

**NOT a scheduler change.** `scheduler/` is untouched. Neither circularity
found in `docs/g5-mechanism-2026-09-05.md` is fixed — the port reproduces
the deployed C including its dead rescue gate, and diverging toward "better"
defeats what the port is for.

**The attach path is a missing SCENARIO/mechanism, and that is what makes it
buildable.** Three models were considered; the choice is recorded because
two of them are not available and a later reader will wonder why:

| model | what it is | verdict |
|---|---|---|
| **A** — SRB flow on LCG 0 during attach | the faithful mechanism: RRC signalling is UL traffic that reaches Reservation's tier-1 `has_srb`, wins a grant, and the resulting BSR populates the array | **UNAVAILABLE.** `has_srb` is hardcoded `False` in `scheduler/reservation.py` and there is no SRB traffic model (README §8). Making it work needs a scheduler change — excluded |
| **B** — an unranked one-off UL grant at attach | models the RA/Msg3 grant directly, issued by the driver outside `scheduler.allocate()` | available, but adds a second grant path to `driver.py` with its own HARQ/accounting surface |
| **C** — seed the BSR state at attach | the gNB records the UE's buffer as an RRC-setup-era BSR would have. One write, at the moment the UE becomes connected | **CHOSEN.** It is the minimal thing that reproduces B's *effect* on the ranking without a second grant path, and it is exactly what the C's own two BSR writers do |

**C is chosen because the C's own comment says what is needed:** *"It only
needs to land ONCE: the resulting BSR … repopulates
`estimated_ul_buffer_per_lcg[]`."* C supplies that one landing.

**Staggered arrival is part of the build, not a refinement.** Attaching all
N at slot 0 would test a case hardware never runs. The interesting question
— and the one the attach-order finding raised — is a UE joining an
**already-loaded** cell, so UEs arrive spread over time and the last one
faces N−1 established competitors.

---

## 1. THE PREDICTIONS — per fleet size, committed now

Measured with `scripts/g5_consolidation.py`'s instrument unchanged, so the
before/after is within-instrument: `n_never_granted`, `served_at_slot_1`,
M07, M08, at N ∈ {2, 4, 8, 16}, 3 arms, ≥3 seeds.

**Baseline to beat** (`sweeps/phase2/g5_consolidation.json`, 36 runs):

| arm | N=2 | N=4 | N=8 | N=16 |
|---|---|---|---|---|
| PF | 0 | 0 | 0 | 0 |
| Reservation | 0 | 0 | 0,0,**1** | **4,1,3** |
| TwoTier | 0 | 0 | 0 | **1,1,2** |

**My prediction, and I am committing to the strong form:**

| N | prediction | confidence |
|---|---|---|
| **2, 4** | `n_never_granted = 0` — unchanged. **This is the CONTROL**: these cells never starved, so a non-zero here means the attach path broke something rather than fixed it | high |
| **8** | **cleared to 0 on every arm and seed** | high |
| **16** | **cleared to 0 on every arm and seed** | **medium — this is the one I could be wrong about** |

**The reasoning, stated so it can be checked against the outcome rather than
re-derived afterwards.** With the array seeded, every UE enters the sort
holding real `has_gbr`/`pdb_ms`, so tiers 2 and 3 no longer separate
served from unserved. The decision falls to tier 4 (`-coef`), whose
composite is *inversely* related to delivered throughput — so an under-served
UE ranks **better**, which is the opposite of the lock-in. And the array is
never drained: only a later BSR overwrites it, and a BSR requires the grant
the seed enables. **So the trap should have no entry point left.**

**Why N=16 is the uncertain one.** At N=16 the cell is genuinely
oversubscribed. Clearing "never granted" does not create capacity, so I
expect **"never" to become "rarely"** — which is a different failure and
should show up as M07 misses without M08 flooring.

---

## 2. WHAT EACH OUTCOME MEANS — fixed now

| # | outcome | meaning |
|---|---|---|
| **A1** | starvation cleared at **every** N | **The frequency is sim-specific.** The mechanism and the dead Tier-1.5 gate remain product findings; the *rate* measured in this campaign is an artefact of the missing attach path, and every blackout/admissible-fleet number taken without one is an upper bound. G5's row gets re-scored under its own registered falsifier |
| **A2** | cleared at N≤8, **persists at N=16** | **The frequency partly transfers.** Cold start is not the only entry to the fault; oversubscription alone can re-create it. The hardware statement strengthens: a late joiner on a loaded cell is at risk even with a normal attach |
| **A3** | **persists at every N** | **The frequency transfers in full**, and the seed was not the lever — meaning the fault is reached by a route the cold-start story does not describe. This would refute my own mechanism account, not just my prediction, and the mechanism document would need reopening |
| **A4** | starvation **appears at N=2 or N=4**, which never starved before | **The attach path is broken**, not informative. A control failure; fix the build, do not read the treatment |
| **A5** | cleared, but **M08 stays floored** | the consolidation `n_never_granted > 0 ⟺ M08 < 0.5` has broken. Then M08 is floored by something else and the 36-run zero-counterexample result was true only over the sizes tested — the instrument, not the treatment, is what needs re-reading |
| **A6** | cleared, and **M07 misses at N=16 without M08 flooring** | the predicted "never → rarely" transition. Real capacity contention, which is a legitimate scheduling result rather than a lock-in, and it separates the two cleanly for the first time |

**A5 is the one that most needs registering**, because it is the outcome
that would quietly invalidate the instrument I am using to judge the
treatment. The consolidation is what makes this experiment sharp; if it
breaks under the attach path, the sharpness was borrowed.

---

## 3. ACCEPTANCE CONDITIONS

1. **The attach path must be OFF by default and bit-identical when off.**
   Every existing artefact, the regression corpus included, must be
   unmoved — `--check` clean with the mechanism present but disabled.
2. **It must be observable.** A counter that survives into whatever the
   campaign persists, so "the seed fired" is distinguishable from "the seed
   was configured". Five mechanisms in this project emit a counter that
   `RunRecord.from_summary` then drops; this one is checked end to end.
3. **Assert the expected count, not non-zero.** The number of attach seeds
   must equal the number of UEs, derived from the scenario rather than
   restated. `docs/wp9-plan.md` §34.5's rule: *fired at all* is a weaker
   question than *fired as often as the schedule specifies*.
4. **The control cells must be run and reported**, not assumed. N=2 and N=4
   are the check that could fail (outcome A4).

---

## 4. What the hardware team is told, REGARDLESS of this outcome

Kept separate on purpose — this experiment is about *this simulator's
frequency*, and none of it changes the product finding:

> **`ia_p5g_scheduler.c`'s Tier-1.5 UL service-interval floor is gated on
> `has_pending_gbr` (:2325), which `update_ul_qos_priority`
> (`gNB_scheduler_ulsch.c:41-70`) sets only inside a loop that skips every
> LCG whose `estimated_ul_buffer_per_lcg[]` is ≤ 0 — the exact condition the
> floor's own comment (:2119-2135) names as defining the fault it exists to
> rescue. The remedy cannot arm in the fault it was built for. And
> Reservation's 5-tier UL comparator has no floor at all, so it has no
> remedy even in principle.**

**That stands whatever the attach path does here**, because it is read from
the C's own source, not measured in the port. What the attach path changes
is only **how often a deployed system would reach that fault**, which is a
separate question and is what this experiment is for.

---

## 5. Park rule

Anything found that does not answer this question is logged and parked.
