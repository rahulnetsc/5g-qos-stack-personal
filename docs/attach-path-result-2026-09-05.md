# The attach path clears the starvation — G5's frequency does not transfer, the mechanism still does

**2026-09-05.** Read against `docs/attach-path-map.md`, which was closed
before Model C was built.

**Outcome: A1**, plus a residual on A6's stated meaning. **A5 does not
fire** — checked first, as registered.

---

## 0. WHAT THIS DOES AND DOES NOT LICENSE — read this before the tables

**The mechanism is unchanged and is still a product finding.** Nothing below
retracts it:

> `ia_p5g_scheduler.c`'s Tier-1.5 UL service-interval floor is gated on
> `has_pending_gbr` (:2325), which `update_ul_qos_priority`
> (`gNB_scheduler_ulsch.c:41-70`) sets only inside a loop that skips every
> LCG whose `estimated_ul_buffer_per_lcg[]` is ≤ 0 — the exact condition the
> floor's own comment names as defining the fault it exists to rescue. **The
> remedy cannot arm in the fault it was built for.** Reservation's 5-tier UL
> comparator has no floor at all.

That is read from the C's source, not measured here, so **no result in this
document can change it.** What this experiment settles is only **how often
this simulator reaches that fault**, which was inflated by a missing attach
procedure.

**A reader seeing "cleared at every N" must not take it as the finding being
retracted.** The finding is the dead gate. This is its frequency.

---

## 1. A5 FIRST — the instrument survived the treatment

The consolidation (`n_never_granted > 0` ⟺ M08 floored) is what makes this
experiment sharp, so it is checked before anything is read from it.

**108 new runs, 0 counterexamples. 144 runs total across both campaigns, 0
counterexamples.** A5 does not fire; the instrument is sound.

---

## 2. The result, and the control that makes it attributable

Three conditions, because the map's treatment bundles two changes and this
project's rule is to decompose before attributing. `n_never_granted` per
seed, 3 arms × 4 fleet sizes × 3 seeds each:

| condition | arm | N=2 | N=4 | N=8 | N=16 |
|---|---|---|---|---|---|
| **off** | PF | 0,0,0 | 0,0,0 | 0,0,0 | 0,0,0 |
| | Reservation | 0,0,0 | 0,0,0 | 0,0,**1** | **4,1,3** |
| | TwoTier | 0,0,0 | 0,0,0 | 0,0,0 | **1,1,2** |
| **stagger_only** | PF | 0,0,0 | 0,0,0 | 0,0,0 | 0,0,0 |
| | Reservation | 0,0,0 | 0,0,0 | **2,2,2** | **7,7,8** |
| | TwoTier | 0,0,0 | 0,0,0 | **0,1,3** | **1,3,8** |
| **stagger_seed** | PF | 0,0,0 | 0,0,0 | 0,0,0 | 0,0,0 |
| | **Reservation** | 0,0,0 | 0,0,0 | **0,0,0** | **0,0,0** |
| | **TwoTier** | 0,0,0 | 0,0,0 | **0,0,0** | **0,0,0** |

**Model C clears the starvation at every fleet size, every arm, every seed.
That is A1.**

**And `stagger_only` is what makes it attributable: staggering ALONE makes it
strictly WORSE.** Reservation N=16 goes 4,1,3 → **7,7,8**; TwoTier N=8 goes
0,0,0 → **0,1,3**. So the stagger is not the lever — it aggravates — and the
**seed** is what clears it. Without this arm the result would have been
unattributable between the two halves of the treatment.

That aggravation is itself the hardware-realistic reading: **a UE joining an
already-loaded cell with an empty array is *more* likely to be locked out
than one present at cold start.** It is the case the attach-order finding
pointed at, and it is worse, not better.

Maximum delay from a UE's own attach to its own first grant, N=16:

| | Reservation | TwoTier |
|---|---|---|
| stagger_only | **18,406 slots** | **16,296 slots** |
| stagger_seed | **1,321** | **497** |

---

## 3. The re-score, on G5's OWN metric

The tables above are M07/M08. **G5 is scored on M05**, so re-scoring on the
proxy would be the mistake this project has a rule against — a check must
intersect the claim. Re-measured at **G5's own configuration** (n=8, 40,000
slots, load 1.0, `cqi_delay_slots=8`, `record_timeseries=True`), 10 paired
seeds, **8 of 8 seeds fired on every run**:

| arm | baseline: FAIL under 0.99 | min M05 | **Model C: FAIL** | **min M05** |
|---|---|---|---|---|
| PF | 0/10 | 0.9934 | **0/10** | 0.9933 |
| **Reservation** | **7/10** | **0.0000** | **1/10** | **0.9900** |
| **TwoTier** | **4/10** | **0.0000** | **0/10** | **0.9932** |

**The catastrophic failures are gone.** The single residual is
`Reservation seed=661058651`, M05 = **0.989967** — 0.00003 under the bound,
against a baseline where the same arm returned **0 of 299 frames** on seven
seeds.

**And the victim is no longer index-determined.** That residual is `ue4`, not
the last position — the deterministic last-position starvation, which was the
whole of `docs/g5-lever-2026-09-05.md`'s finding, does not survive an attach
path.

---

## 4. G5's VERDICT — re-scored, because its own registered falsifier fired

`docs/g5-mechanism-2026-09-05.md` §4 registered the falsifier in these words:

> *"if the sim gained an attach procedure (RACH/Msg3/RRC-setup grants) and
> the starvation disappeared at every fleet size, then G5's failure would be
> an artefact of the missing attach path and should be re-scored."*

**That condition is met.** So the re-score is done here rather than left
implied:

**G5's published failure rate — Reservation 30/40, TwoTier 34/40 — is an
artefact of this simulator's missing attach procedure and must not be quoted
as a property of either scheduler.** Under an attach path the same
configuration gives Reservation **1/10 marginal** and TwoTier **0/10**.

**What survives the re-score, stated precisely so it is not over- or
under-claimed:**

1. **The mechanism is real and is the product's** (§0). Unchanged.
2. **The fault is reachable on hardware**, and `stagger_only` shows it is
   reached *more* readily under realistic arrival than under cold start. Model
   C models a *successful attach*; it does not model a UE whose array is
   later emptied by a Short/Truncated BSR desync, which has no second seed.
   **That route is untested and is the one hardware would actually take.**
3. **G5's frequency is sim-specific.** Every blackout rate and
   admissible-fleet figure measured without an attach path is an **upper
   bound**, not an estimate — including G10's PF 8 / Reservation 4 /
   TwoTier 4.

**I was wrong about the frequency and right about the mechanism.** The
previous verdict said G5 "stays a failure" on four grounds; ground 1 (total
and permanent) and ground 2 (deterministic) were both properties of the
missing attach path, and they do not survive. Grounds 3 (faithful to the C)
and 4 (attach order is real) do.

---

## 5. Scoring all six outcomes

| # | fired? | note |
|---|---|---|
| **A1** cleared at every N | **YES** | the result |
| **A2** cleared at N≤8, persists at 16 | no | it cleared at 16 too |
| **A3** persists everywhere | no | — and the no-op guard is why this can be trusted: a seed written against an empty buffer would have produced exactly A3 by a bug, so `seed_attach_bsr` returns whether it wrote, the driver only marks a UE seeded when it did, and 8 of 8 fired on every run |
| **A4** control cells break | **no** | N=2 and N=4 are 0 in every condition and arm |
| **A5** consolidation breaks | **no** | 0 counterexamples in 108 new / 144 total |
| **A6** M07 misses at N=16 without M08 flooring | **outcome yes, MEANING NOT ESTABLISHED — residual** | see below |

### The residual on A6

A6's *outcome* is observed: at N=16 under `stagger_seed`, M08 is healthy
(Reservation 0.7730, TwoTier 0.7432, PF 0.7721) while M07 is 0.125. But A6's
registered *meaning* — *"real capacity contention, a legitimate scheduling
result"* — **is not established**, because **PF shows the same M07 collapse
(0.062, worse than either QoS arm)**, and PF starves nobody in any condition.

The likely cause is a **measurement artefact of the stagger itself**: M07 is
the fraction of GBR flows meeting GFBR *over the whole horizon*, and a UE
that attaches at slot 3,000 of 20,000 has no traffic for 15 % of the window,
so its run-average throughput misses GFBR for reasons that have nothing to do
with scheduling. The pattern fits — at N=2 (200-slot stagger) M07 is 1.000;
at N=4 it is 0.500; at N=16 it is ~0.1.

**So A6's outcome fired and its meaning did not, which is reported as a
residual rather than resolved by picking whichever reading suits.** Logged as
defects-log #27: **M07 under a staggered arrival is not a usable statistic
without excluding pre-attach time**, and no result in this document rests on
it.

---

## 6. Logged and parked

- **defects-log #26** — `summary` carries live objects (`_ue_lcp`,
  `_message_ledger`) whose `repr()` embeds a memory address, so
  `json.dumps(summary, default=str)` differs between two **identical** runs.
  Found because the first bit-identity test failed against itself.
- **defects-log #27** — M07 under a stagger (above).
- **The desync route is untested.** Model C answers "does a successful
  attach clear it". It does not answer "can a Short-BSR desync put a
  served UE back into the fault", which is how hardware would get there.
  That is the natural next experiment and is not done here.

## Artefacts

- `sweeps/phase2/attach_path.json` — 108 runs, 3 conditions
- `sweeps/phase2/g5_rank_attach.json` — 30 runs at G5's own configuration
- `sim/bsr.py::seed_attach_bsr`, `sim/driver.py`'s `attach_seed_slots`
- `sim/tests/test_attach_path.py` (10 tests), `scripts/attach_path_experiment.py`
