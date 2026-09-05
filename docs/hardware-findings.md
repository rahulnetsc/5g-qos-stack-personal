# Findings for the hardware team — the set, because the pattern is the finding

**2026-09-05.** Three results that are **not** about this simulator. Each is
read from the deployed C's own source and merely *reproduced* by a faithful
port, so no simulator caveat — not the missing attach path, not the Tier-1
scaling, not the horizon or seed counts — touches any of them.

**They are stated as a set because listing them as three rows loses the
thing they have in common**, and the thing they have in common is more
actionable than any one of them.

---

## The shape

> **A mechanism exists, is named for the guarantee it serves, is faithfully
> ported — and does not do what the guarantee needs.**

Two of the three are exactly this. The third is the same fault with **no
mechanism at all**, and it is in the set because the set is organised by
*fault*, not by shape — a reader looking for "is entitlement enforced?" must
find all three in one place.

**Why the pattern matters more than the instances:** in each case a reviewer
inspecting the code would conclude the guarantee is implemented. There is a
clamp named for MFBR. There is a floor named for the service-interval fault.
The names are right and the code runs. **What is missing in every case is the
step from the mechanism to the outcome the guarantee is written in terms
of** — and that step is not visible from the mechanism's own source, only
from what happens after it.

---

## 1. The Tier-1.5 UL service-interval floor cannot arm in the fault it exists for

`ia_p5g_scheduler.c:2119-2135` states the fault in its own comment:

> *"A floor-fired UE is in the fault state where BOTH composite inputs are
> gated on `estimated_ul_buffer_per_lcg[] > 0`, which reads 0 by definition
> of the fault… under Tier 2 it would sort dead last… **It only needs to
> land ONCE**: the resulting BSR… repopulates
> `estimated_ul_buffer_per_lcg[]`."*

Its arming gate, `:2325`:

```c
if (_fl && sched_ctrl->has_pending_gbr && !_intr) {
```

`has_pending_gbr` is written **only** by `update_ul_qos_priority`
(`gNB_scheduler_ulsch.c:41-70`), inside a loop that `continue`s past every
LCG whose per-LCG estimate is ≤ 0. **The rescue for "the array reads 0" is
gated on a flag that is false exactly when the array reads 0.**

**Measured in the faithful port:** evaluated **32,000 times per UE per run**,
fired **0 times** for the three UEs that received **0 UL grants in 40,000
slots**. The single firing observed across two seeds landed on a UE that
already had 19,805 grants.

**The C's own v2 comment shows the trap half-escaped**: v2 removed three
estimate-derived arming inputs from the body and left a fourth standing in
the guard.

## 2. Reservation has no floor at all

The same never-served fault reaches `gNB_scheduler_ulsch.c`'s five-tier UL
comparator, which has **no rescue tier of any kind**. So the fault has no
remedy even in principle there — which is why the measured starvation is
worse on Reservation (0 of 299 frames complete) than on two-tier.

**This is the complement of finding 1, not another instance of it**, and it
is stated as such: finding 1 is a remedy that cannot reach its fault;
finding 2 is the same fault with no remedy. **Together they say the
never-served fault is unhandled on both schedulers, by two different
routes.**

## 3. MFBR bounds entitlement, not throughput

`ia_p5g_scheduler.c:2663-2665`, with twins at `gNB_scheduler_ulsch.c:2248`
and `gNB_scheduler_dlsch.c:397`:

```c
int _max_burst = (int)(_c->gbr_ul_max / 8) / (_spf_ul * 100) * 2;
if (_max_burst < _obl * 2) _max_burst = _obl * 2;
if (_target > _max_burst) _target = _max_burst;
sched_ctrl->ul_total_target_bytes += _target;
```

**What is clamped is `_target`, the GBR obligation.** The demand above it is
not dropped — it falls through to the best-effort accumulator and stays
deliverable. The DL site's own comment names the intent: *"cap at 2x
per-slot MBR to prevent cell monopolisation"* — burst shaping, not a rate
ceiling.

**Measured (GT-4.3, n=8, 10 paired seeds, aggressor at 2.01–2.10× MFBR):**
both QoS-aware schedulers deliver **2.0–2.1× MFBR**, failing containment at
every tolerance tested including 25 %. The excess **grows** with offered load
(2.02× → 2.14× over a 2.5× range) rather than being a spare-capacity
artefact.

**And the inversion:** PF, which has no MFBR concept whatsoever, contains the
aggressor **better** (1.05×) — proportional fairness bounds any one UE's
share, while the clamp does not bound delivery at all.

**The other assets are unharmed** and so is the misbehaving asset's own
telemetry; that half of GT-4.3 holds. **What does not hold is "entitlement is
a ceiling."**

---

## What this set asks of the hardware team

1. **Is the Tier-1.5 floor meant to arm in the state its comment describes?**
   If so, its gate needs an arming input that is not estimate-derived — the
   v2 change removed three and left one.
2. **Is the never-served fault meant to be handled on reservation at all?**
   It currently is not, by any path.
3. **Is MFBR meant to be a delivery ceiling?** If so, no code path currently
   implements it. If it is meant to be burst shaping only — which the DL
   comment suggests — then the guarantee written as *"B's excess clipped at
   MFBR"* is not the guarantee the scheduler provides, and the specification
   should say so.

**None of these is a simulator change and none is blocked on one.** Each is
answerable against `ia_p5g_scheduler.c` and its siblings.
