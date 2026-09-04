# Reservation edit list — living document

**What this is.** Mechanisms the deployed **two-tier** scheduler has that the
deployed **Reservation** scheduler does not, with the measured evidence that
Reservation lacks them and what adding each would cost. Written as findings
accumulate rather than reconstructed later.

**What this is NOT.** Not a list of simulator changes. Every entry is a
proposal about the **real product**. Nothing here is applied to
`scheduler/reservation.py`: doing so would stop the sim's Reservation being
the deployed Reservation, and every arm comparison would silently become
two-tier versus Reservation-plus-a-mechanism-it-does-not-have.

**How it gets tested, when it does.** As a clearly-labelled **divergence
arm** — "Reservation + edits" — alongside the faithful Reservation, never
replacing it, so the campaign can always be told what the deployed product
does separately from what a modified one would do. Port-map rows for that arm
are marked **divergence**, not **port**.

**Status: OPEN — not complete, and the arm is not to be built until it is.**

---

## R1 — UL service-interval floor

**The mechanism.** `oai-branches/two-tier/ia_p5g_scheduler.c:560-640` (design
rationale) and `:2311-2360` (arming). A GBR-configured UE that has delivered
**no UL bytes for θ = PDB/8** is force-included as if an SR had arrived —
gNB-initiated, needing neither an SR over PUCCH nor a trustworthy buffer
estimate. Arming is **delivery-history based** (`floor_rx_lastseen`), not
estimate-derived, because — in the C's own words — *"B==0 defines the
fault"*. The fired grant is the full post-power-adaptation allocation,
bypassing `nr_find_nb_rb`, because every `B_eff` input is estimate-derived
and reads zero in this fault; the surplus triggers a padding BSR, which is
the resync a `min_rb` crumb cannot deliver.

**Evidence Reservation lacks it.** `oai-branches/reservation/gNB_scheduler_ulsch.c`
has no floor — confirmed by reading. Measured, 3 arms × N=8 × 20 seeds:

| arm | blackout rate, mfbr=0 | mfbr configured |
|---|---|---|
| PF | 0 % | 0 % |
| **TwoTier** | 35 % | **5 %** |
| **Reservation** | **65 %** | **65 % — unchanged** |

**And the mechanism split shows the floor is what does the work**, not the
reserve: the still-dead seed has `has_pending_gbr` true in **110,218 calls**
— FIX-2's reserve fully active — and still loses nine flows, while the
rescued seed differs only in the floor firing **three times**. Three fires
clear nine dead flows: breaking a deadlock, not adding capacity.

**Cost.** Per-UE state (`floor_rx_lastseen`, `floor_last_move_slot`,
`floor_alive_slot`, `floor_fruitless`, `floor_disarmed`), one delivery-bytes
read per UE per slot, and a bypass path in the grant loop. Bounded by
`FLOOR_FRUITLESS_MAX` backoff so an idle flow disarms. **Known residual
carried from the C**: after a long silence the PHR is stale, so power
adaptation clamps to the last reported headroom.

**A LIMITATION OF THE DEPLOYED TWO-TIER, NOT OF OUR PORT — state this first
to whoever reads the proposal.** The floor cannot arm for a **never-served**
UE. Arming is gated on `has_pending_gbr`, computed by
`update_ul_qos_priority` (`gNB_scheduler_ulsch.c:48-66`) by skipping any LCG
whose `estimated_ul_buffer_per_lcg <= 0` — **the very estimate a first grant
would populate.** A UE that has never been granted has that array at zero, so
the gate is false and the floor never arms for it.

**This is in the C. It is not something the simulator introduced, and the
port did not narrow it** — `scheduler/two_tier.py::_ul_has_pending_gbr`
reproduces both of the C's conditions exactly, checked line by line. Without
this stated up front a reader will reasonably assume the sim added the gap,
and the distinction decides whether the hardware team is being told about a
limit in **their own product** or in our model of it. It is the former.

**Why the C has it.** The array is *frozen between BSRs and never drained on
a grant* (CLAUDE.md's invariant), which is exactly what makes it a durable
arming signal **for the fault the C was written for**: the C's own comment
names that fault as *"BSR desync / SR loss on real RF"* — a UE that **had
service and lost it**, whose scalar reads 0 while the array still holds its
last BSR. The design is sound for that case and silent for ours.

**ESTABLISHED 2026-09-04: RE-ATTACH IS A TRIGGER, so this is the JOIN PATH,
not a corner case.** Measured on `gt61_warm_rejoin` (seed 1, 7 neighbours,
30,000 slots, TwoTier), instrumented around the events themselves:

```
per-LCG estimate zero in 27,805 of 30,000 slots (93 %)
grants: joiner 135   vs   neighbours 1,324 / 1,376   (~10x fewer)

  event @slot 2000:  estimate zero in 1,691/2,000 of the next 2,000 slots;  8 grants
  event @slot 3600:  estimate zero in 2,000/2,000 of the next 2,000 slots;  0 grants
```

**After the second re-attach the estimate is zero in every one of the next
2,000 slots and the joiner receives zero grants** — the closed loop exactly:
estimate reset → no grant → no BSR → estimate stays zero. The floor cannot
arm through it because arming reads that estimate.

**Severity VARIES BY EVENT and the variation is part of the finding.** The
first event shows 8 grants and 85 % zero-estimate — degraded but recovering;
the second shows total starvation. So *"zero grants after re-attach"* is true
of **some** re-attaches, not all, and the run-level figure (135 grants) hides
where the zero lives. Quote the per-event view, not the aggregate.

**THIS IS THE DEPLOYED C's BEHAVIOUR, NOT OUR SIMULATOR'S.** Arming is gated
on `has_pending_gbr`, computed by `update_ul_qos_priority`
(`gNB_scheduler_ulsch.c:48-66`) by skipping any LCG whose
`estimated_ul_buffer_per_lcg <= 0` — **the very estimate a first grant would
populate**. `scheduler/two_tier.py::_ul_has_pending_gbr` reproduces both
conditions exactly, checked line by line. **The hardware team is being told
about their own product's join path**, which every deployment exercises on
every attach and every recovery — not about a limitation of this model.

**Our residual 5 % is the never-served case**, and it is why R1 does not go
to 0 %. Porting R1 into Reservation **inherits this gap** unless the arming
signal is changed — and changing it would be a **DIVERGENCE from the C, not
a port of it**, which must be labelled as such in any proposal.

**Whether a never-served UE is reachable on real hardware is the campaign's
question and this simulator cannot answer it.** RACH and attach are modelled
(`sim/join.py`, `sim/rlf.py`), but whether a real UE is *guaranteed* an
initial grant after attach is a property of the deployed gNB's own
scheduling, not of anything modelled here. Offer it as an uncovered case with
a known trigger condition, never as a predicted failure rate.

---

## R2 — FIX-2's GBR PRB reserve

**The mechanism.** Two-tier reserves PRBs for GBR UEs waiting behind the
current candidate, gated on `has_pending_gbr`.

**Reservation already has a follower reserve, and it is NOT MFBR-gated** —
`gNB_scheduler_ulsch.c:2424-2431`, budget `bwpSize − n_followers_need*min_rb`
floored at `min_rb`, with `needs_service = (B>0) || ul_has_srb ||
ul_has_unfulfilled_gbr || do_sched` (`:2340-2341`). So it is **always live**,
and the port implements it faithfully (`scheduler/reservation.py:493`, called
at `:943`; verified running — 79,116 calls, mean 5.28 followers, budget
flooring at `min_rb`).

**Why it does not help anyway, measured.** It reserves for **candidates**. A
never-served UE is absent from the candidate list in **30,784 of 40,000
slots** (present in only 9,216, against ~30,900 for every peer), so the
reserve operates over a population that excludes the UE it exists to protect.

**Cost / status.** **Nothing to add** — Reservation's variant is already
present, always live, and faithful. Whether two-tier's differently-gated
variant would help Reservation is **untested**, and testing it is meaningful
only after R1, since the measured evidence says the reserve is insufficient
without the floor.

**Do NOT make the reserve unconditional.** Its own comment: *"when no
downstream GBR UE is waiting, reserve_rb is 0 and the cap is inert, so
aggregate throughput in the uncontended case is unaffected"*. An
unconditional `n_candidates * min_rb` reserve holds back **35 of 55 PRBs**
permanently at 8 UEs.

---

## R3 — the GBR-deficit target-spread cap — ESTABLISH BEFORE PROPOSING

**The claim.** `scheduler/flow.py::FlowConfig.mfbr_bps`'s docstring: *"the
reservation scheduler's GBR-deficit target-spread caps at 2× a per-slot burst
derived from this (`gNB_scheduler_{ul,dl}sch.c`'s `gbr_{ul,dl}_max`, Phase 2
commit 3). 0 = 'not configured' — the cap then falls back to its own floor."*

**The measurement refutes it.** Registered as P14's falsifier before running:
*"Reservation identical on every metric ⇒ the documented cap does not bind."*
Configuring MFBR from 0 to 2× GFBR left **Reservation identical on all 7
metrics** (M01 p98, M15, M20, M05, M06, M09, M22), 3 seeds, protected fleet.

**So this is a documentation defect at minimum and possibly a dead
mechanism**, and which one it is has to be established before anything is
proposed around it:

- **mis-documented** — the cap exists but is reached by a path MFBR does not
  feed, so the docstring names the wrong input; or
- **dead** — the cap is ported but never fires, which would put it in
  CLAUDE.md's built-but-not-reached family.

**Cost.** Zero to establish: one trace of the deficit-target path with MFBR
set and unset. **Nothing should be proposed around R3 until that runs** — a
proposal resting on a mechanism that may not fire is the shape this project
has been repeatedly caught by.

---

## Not yet on this list

Entries are added only with measured evidence. Candidates seen but not
evidenced: two-tier's Tier-1 LP re-solve, the CTRL/DATA class split, and the
`sched_inactive` liveness tier — none has a measured Reservation-lacks-it
result yet.
