# Three questions for whoever owns the scheduler design

**2026-09-05.** Three observations about `ia_p5g_scheduler.c` and its
siblings, stated **as one section because the shared shape is the finding**
and it is stronger said once than implied three times.

**These are questions, not defects.** Every one is a statement about **what
the code does**, established by reading the C and confirmed by a port that
reproduces it. **None of them is a statement about what was intended** — we
can measure the first and cannot know the second, and in each case there is
a reading under which the code is correct and the *guarantee's wording* is
what needs changing instead.

**No simulator caveat touches any of these.** Not the missing attach path,
not the Tier-1 scaling, not the horizons or seed counts. The mechanisms were
read from the deployed source; the port only supplies the counts.

---

## The shape all three share

> **A mechanism exists, is named for the guarantee it serves, is faithfully
> ported — and does not produce the outcome the guarantee is written in terms
> of.**

Questions 1 and 3 are exactly this. Question 2 is the **complement** — the
same fault with no mechanism at all — and is grouped here because the set is
organised by *fault*, not by shape: someone asking *"is entitlement
enforced?"* should find all three in one place.

**Why the shape is worth stating separately.** In each case a reviewer
reading the code would reasonably conclude the guarantee is implemented.
There is a clamp named for MFBR. There is a floor named for the
service-interval fault. The names are right, the code is reached, and it
runs. **What is absent in every case is the step from the mechanism to the
outcome — and that step is not visible from the mechanism's own source**,
only from what happens downstream of it. If that step was never intended to
be there, the guarantees should be reworded; if it was, three code paths are
incomplete. **We cannot tell which from here.**

---

## Question 1 — is the Tier-1.5 UL floor meant to arm in the state its own comment describes?

`ia_p5g_scheduler.c:2119-2135` describes the fault the floor exists for:

> *"A floor-fired UE is in the fault state where BOTH composite inputs are
> gated on `estimated_ul_buffer_per_lcg[] > 0`, which reads 0 by definition
> of the fault… under Tier 2 it would sort dead last… **It only needs to
> land ONCE**: the resulting BSR… repopulates
> `estimated_ul_buffer_per_lcg[]`."*

Its arming gate, `:2325`:

```c
if (_fl && sched_ctrl->has_pending_gbr && !_intr) {
```

`has_pending_gbr` is set **only** by `update_ul_qos_priority`
(`gNB_scheduler_ulsch.c:41-70`), inside a loop that `continue`s past every
LCG whose per-LCG estimate is ≤ 0.

**So the gate is false exactly when the fault holds.** In the port —
faithful at this site — the floor is evaluated **32,000 times per UE per
run** and fires **0 times** for UEs receiving **0 UL grants in 40,000 slots**;
the one firing seen across two seeds landed on a UE that already had 19,805.

**The question.** The v2 comment records deliberately removing three
estimate-derived arming inputs (`B`, `vq`, the deficit) *because* they read
zero in the fault. **Was `has_pending_gbr` intended to be removed with them,
or is it a deliberate precondition — i.e. is the floor meant to rescue only
UEs with a live GBR obligation the gNB can still see?** Both are coherent
designs. The code implements the second; the comment reads like the first.

## Question 2 — is the reservation scheduler meant to have no equivalent?

The same never-served fault reaches `gNB_scheduler_ulsch.c`'s five-tier UL
comparator, which has **no rescue tier of any kind**.

**The question.** Is that intentional — reservation being a simpler
scheduler where this fault is accepted or handled elsewhere — or is the
floor a two-tier-only addition that reservation was expected to receive?
**We measure the consequence** (a starved UE completes 0 of 299 PDU sets on
reservation, worse than on two-tier) **but the consequence does not tell us
which design was chosen.**

## Question 3 — is MFBR meant to bound delivered rate, or entitlement?

`ia_p5g_scheduler.c:2663-2665`, with twins at `gNB_scheduler_ulsch.c:2248`
and `gNB_scheduler_dlsch.c:397`:

```c
int _max_burst = (int)(_c->gbr_ul_max / 8) / (_spf_ul * 100) * 2;
if (_max_burst < _obl * 2) _max_burst = _obl * 2;
if (_target > _max_burst) _target = _max_burst;
sched_ctrl->ul_total_target_bytes += _target;
```

**What is clamped is `_target`, the GBR obligation.** Demand above it is not
discarded — it falls through to the best-effort accumulator and stays
deliverable.

**Measured** (GT-4.3, aggressor at 2.01–2.10× MFBR, n=8, 10 paired seeds):
both QoS-aware schedulers deliver **2.0–2.1× MFBR**, missing containment at
every tolerance tested including 25 %, and the excess **grows** with offered
load rather than being a spare-capacity artefact. **PF, which has no MFBR
concept at all, contains the aggressor better (1.05×).** The other assets are
unharmed, and so is the misbehaving asset's own telemetry.

**The question.** The DL site's own comment says *"cap at 2x per-slot MBR to
prevent cell monopolisation"* — which reads as **burst shaping, and burst
shaping is what the code does.** But the guarantee is written as *"B's
excess clipped at MFBR"*, which is a **delivered-rate ceiling**, and no code
path implements that. **Which is MFBR meant to be?** If entitlement, the
guarantee's wording is wrong and the code is right. If a delivery ceiling,
the mechanism for it does not exist.

---

## What we can and cannot say

**We can say:** what each mechanism does, where, and with what measured
consequence — all three read from the deployed source, all three reproduced
by a port that matches it line for line at these sites.

**We cannot say** whether any of the three is a defect. Each has a coherent
reading under which the code is correct and a guarantee's wording is what
should change. **That judgement needs whoever chose the design, which is why
these are three questions and not three bug reports.**
