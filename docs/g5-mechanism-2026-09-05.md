# The cold-start lock-in: one mechanism behind G5, G10's boundary and the UL blackout — and it is in the deployed C

**2026-09-05.** Two questions, answered in order, then the G5 verdict and the
hardware-order question.

**Headline.** The chain holds in full. It consolidates three separate
findings into one. **And the deployed C shares the structure** — including a
rescue mechanism whose arming gate is the very condition whose absence
defines the fault, which makes this a finding about the product's ranking
rather than about this simulator.

---

## 1. The chain, traced link by link

> last position → no first grant → per-LCG array stays 0 → `pdb_ms` reads
> the 9999 sentinel → ranks last forever

**Every link measured**, not inferred from the ends. Reservation, seed
1097657231, n=8, 40,000 slots:

| ue | UL first-tx grants | first grant slot | `on_ul_grant` calls | BSRs assembled | SR floor hits |
|---|---|---|---|---|---|
| 1–5 | ~11,300 | **slot 1** | ~11,300 | ~1,730 | 13–17 |
| 6–7 | ~11,370 | **slot 38** | ~11,370 | ~1,720 | 121–123 |
| **8** | **0** | **NEVER** | **0** | **none** | **34,560** |

**ue8 receives zero UL grants in 40,000 slots while its SR fires 34,560
times.** The uplink-access model is working — it re-arms `bytes_reported`, so
ue8 is a candidate on 9,216 slots — and the ranking never converts one of
those into a grant.

### The symmetry break is one slot wide, and it is visible

Reservation's UL keys, first slots (`(has_srb, has_gbr, pdb_ms, -coef)`):

```
slot 1  order=[1,2,3,4,5,6,7,8]
        keys = (1,1,9999,-52.0) x8          <- IDENTICAL on all eight
        decided by = TIE,TIE,TIE,TIE,TIE,TIE,TIE
slot 2  order=[5,1,2,3,4,6,7,8]
        keys = (1,0,100,...) x5   then  (1,1,9999,-52.0) x3
        decided by = -coef,TIE,TIE,TIE,has_gbr,TIE,TIE
```

**At slot 1 nothing has been granted, so every UE is at the sentinel and
every adjacency is a tie.** Python's stable sort therefore serves declaration
order, and the PRB budget reaches the first five. By slot 2 those five carry
real `has_gbr` and `pdb_ms=100`; the three that missed still carry the
sentinel, and the boundary adjacency is decided by `has_gbr` from then on.

**Having been served is what makes you look worthy of service.** The
starved UE's `coef` is ~300× the healthy ones' — it would win tier 4
outright — and tiers 2 and 3 never let it get there.

### The consolidation, tested rather than asserted

If this is one mechanism, then `n_never_granted > 0` should be *equivalent*
to M08 failing — because M08 is a worst-GBR-flow statistic and one
permanently-ungranted UE floors it. `scripts/g5_consolidation.py`, 3 arms ×
4 fleet sizes × 3 seeds = **36 runs**:

| arm | N=2 | N=4 | N=8 | N=16 |
|---|---|---|---|---|
| **PF** | 0 starved | 0 | **0** | **0** |
| **Reservation** | 0 | 0 | 0,0,**1** | **4,1,3** |
| **TwoTier** | 0 | 0 | 0 | **1,1,2** |

**Zero counterexamples in 36 runs to `n_never_granted > 0 ⟺ M08 < 0.5`.**

So the three observations are one:

- **G5** — the last-position UE's PDU sets never complete, because it is
  never granted.
- **G10's admissible-fleet boundary** — the largest N at which nobody is
  locked out. Reservation and TwoTier pass at N≤4 and fail at N=8/16; PF
  starves nobody at any N. That reproduces G10's published **PF 8 /
  Reservation 4 / TwoTier 4** from the mechanism rather than from the metric.
- **The UL blackout** — a "total UL blackout" *is* a never-granted UE. The
  same count, renamed.

---

## 2. Is it in the deployed C? YES — and the rescue is gated on the fault

### The gate is identical

`oai-branches/reservation/gNB_scheduler_ulsch.c:41-70`:

```c
static void update_ul_qos_priority(NR_UE_sched_ctrl_t *sched_ctrl)
{
  sched_ctrl->best_pending_pdb_ms = 9999;
  sched_ctrl->has_pending_gbr = false;
  for (int lcg = 0; lcg < 8; lcg++) {
    if (sched_ctrl->estimated_ul_buffer_per_lcg[lcg] <= 0)
      continue;
    ...
```

Same seeds, same `continue`. **The port is faithful.**

And `estimated_ul_buffer_per_lcg` has exactly **two writers in the C**, both
inside the BSR MAC-CE handlers (`UL_SCH_LCID_S_BSR` / `UL_SCH_LCID_L_BSR`
and their truncated variants, :625-665). Those run on receipt of an uplink
MAC PDU, which requires a grant. `update_ul_qos_priority` has exactly **two
call sites**, both immediately after those writes. **No grant → no PDU → no
BSR CE → the array is never written → `has_pending_gbr=false` and
`best_pending_pdb_ms=9999` forever.**

### The C's own comment names this fault state

`ia_p5g_scheduler.c:2119-2135`, in `ia_p5g_ul_cmp`'s Tier 1.5:

> *"A floor-fired UE is in the fault state where BOTH composite inputs are
> gated on `estimated_ul_buffer_per_lcg[] > 0`, which reads 0 by definition
> of the fault… Its coef is therefore EXACTLY 0 — the arithmetic minimum —
> so under Tier 2 it would sort dead last… Ranking a fired floor above
> ordinary data UEs makes the rescue land. **It only needs to land ONCE:**
> the resulting BSR… repopulates `estimated_ul_buffer_per_lcg[]`."*

So the fault was known, and Tier 1.5 — the UL service-interval floor — is
the designed remedy.

### AND THE REMEDY CANNOT ARM IN THE FAULT IT WAS BUILT FOR

`ia_p5g_scheduler.c:2325`:

```c
if (_fl && sched_ctrl->has_pending_gbr && !_intr) {
```

**`has_pending_gbr` is set only inside the loop that `continue`s past every
zero per-LCG entry.** The rescue for "the per-LCG array reads 0" is gated on
a flag that is false exactly when the array reads 0. It is circular in the
deployed C, not only in this port.

The C's own v2 comment shows the trap was half-seen:

> *"v1 armed on (B>0 || deficit>0 || vq>0), all estimate-derived: B==0
> defines the fault and vq_ul stops updating once the per-LCG estimate reads
> 0, so arming rested entirely on the deficit staying non-zero…"*

**v2 removed three estimate-derived arming inputs and left a fourth standing
in the gate.**

### Measured in the port, which reproduces the C

| seed | ue | floor evaluated | floor **FIRED** | UL grants |
|---|---|---|---|---|
| 35492826 | 6, 7, 8 | 32,000 each | **0** | **0** |
| 1097657231 | 3 (healthy) | 32,000 | 1 | 19,805 |

**Evaluated 32,000 times per UE per run and never once fires for a UE in the
fault state.** The single firing observed lands on a UE that already had
19,805 grants. This is why `floor_fire` decides 0.000 % of adjacencies (the
G5 trace's L1 refutation) — not "armed and outranked", but "never armed".

It also explains why Reservation's failure is *worse* than TwoTier's (0 of
299 frames vs partial): Reservation's 5-tier comparator has **no floor at
all**, so it has no remedy even in principle.

### Who owns it

| | owner |
|---|---|
| the gate structure (`continue` past a zero LCG; sentinel seeds) | **the product** — faithful port |
| the rescue's circular arming gate | **the product** — `ia_p5g_scheduler.c:2325` |
| **the ROUTE into the fault state** | **partly this simulator** — see below |

**The honest caveat, and it matters for how often this bites.** This
simulator has no attach procedure: every UE exists from slot 0 with an empty
array, so all N tie at slot 1 and the fault is entered *at cold start*. Real
hardware runs RACH → Msg3 → RRC setup, during which a UE receives grants
before any of this ranking applies, so a freshly-attached UE would normally
have a populated array. **On hardware the fault is reached by desync** — a
Short or Truncated BSR leaves the omitted LCGs at 0 (`sim/bsr.py`'s own
docstring: *"that memset is what makes truncation a DESYNC rather than a
stale read"*) — **rather than by cold start.** The *mechanism* and the
*unreachable rescue* are the product's; the *frequency* measured here is
inflated by a missing attach path.

---

## 3. Does declaration order correspond to anything real? YES — attach order

From the full checkout
(`/home/smart/projects/Oai_Ran_QoS_Supported_MultiDRB`):

- `add_UE_to_list` (`gNB_scheduler_primitives.c:2974`) writes the UE into
  **the first free slot** — an append.
- `remove_UE_from_list` (:2985) `memmove`s the tail down, **compacting** and
  preserving relative order.
- `UE_iterator(UE_list, UE)` (`ia_p5g_scheduler.c:2225`) builds the
  pre-`qsort` candidate array in exactly that order.

**So `connected_ue_list` is in attach order, and last-attached is
last-in-list.** Declaration order is not a simulator artefact — it is the
deployment's own arrival order.

**Which changes what the campaign should test.** "The last position starves"
becomes "**a UE attaching into an already-loaded cell can fail to ever get
its first grant**" — a nameable operational condition, testable by growing
the fleet rather than by permuting a list. And it is arguably *worse* on
hardware than here: a late joiner has to out-rank N established UEs all
holding real QoS state, from the sentinel, with the designed rescue unable
to arm.

**One difference to keep straight, and it is a real one.** C's `qsort` is
**not required to be stable** (glibc uses mergesort when it can allocate and
quicksort when it cannot), while Python's `list.sort` is stable by
specification. So the *deterministic victim* observed here is a property of
this port; on hardware the fault state and the dead rescue are structural,
but which UE lands in it is implementation-defined. **The failure is the
product's; its reproducibility is ours.**

---

## 4. THE G5 VERDICT — stated, not left open

**G5 stays a FAILURE. I agree with the reading, and the attach-order finding
makes the case stronger than when I raised the question.**

I previously wrote that *"the starvation is real; its victim is arbitrary."*
**The second half of that is now wrong and I am withdrawing it.** The victim
is not arbitrary — it is the last UE in attach order, which on hardware
names a specific operational role (the most recent joiner). "Arbitrary"
would have been grounds for discounting the result; "the newest UE on the
cell" is not.

Four grounds, in increasing weight:

1. **The starvation is total and permanent**, not marginal — 0 of 299 frames
   inside PDB, 0 UL grants in 40,000 slots.
2. **It is deterministic.** Every failing run has a victim; nothing about
   this is a tail event. Being predictable makes it *more* actionable, not
   less real — a QoS guarantee that fails on a known UE every time is a
   worse guarantee than one that fails on a random UE sometimes.
3. **The mechanism is faithful to the deployed C**, including the rescue's
   circular gate. This is not an artefact of the Python.
4. **The index means something.** Attach order is real, so the guarantee's
   failure has a deployment-facing statement: *a UE joining a loaded cell may
   never receive an uplink grant, and the mechanism designed to rescue it
   cannot arm.*

**What would change the verdict, stated so it is falsifiable:** if the sim
gained an attach procedure (RACH/Msg3/RRC-setup grants) and the starvation
disappeared at every fleet size, then G5's failure would be an artefact of
the missing attach path and should be re-scored. **That is a scenario change
with its own commit and its own regression diff, and it is not done here.**
Until then G5 is a measured failure with a named, product-side cause.

---

## 5. Logged and parked

- **The attach-path gap itself.** No RACH/Msg3/RRC-setup UL grant exists in
  `sim/`; `sweep_scenario` sets no `JoinConfig`. That is the difference
  between "enters the fault at cold start" and "enters it by desync". It is
  a scenario/mechanism change, not a fix to anything measured here.
- **Whether the C's `qsort` is stable in the deployed build** — glibc's is
  in practice but not by contract. Answerable only against the deployment's
  own libc, and it changes victim selection, not the fault.
- **`_ul_has_pending_gbr`'s flagged circularity** was already recorded in
  `scheduler/two_tier.py`'s own docstring as *"the flagged, not-resolved
  consequence"*. This document supplies the measurement it lacked (0 firings
  in 32,000 evaluations × 3 starved UEs) and the C citation showing it is not
  a port choice.

## Artefacts

- `sweeps/phase2/g5_consolidation.json` — 36 runs
- `scripts/g5_consolidation.py`
- `oai-branches/reservation/gNB_scheduler_ulsch.c:41-70, 625-665`
- `oai-branches/two-tier/ia_p5g_scheduler.c:2119-2135, 2325`
- `/home/smart/projects/Oai_Ran_QoS_Supported_MultiDRB/openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_primitives.c:2974-2999`
