# G3 — slide source

**Status:** ANSWERED as a stress experiment, 2026-09-09.
**Full record:** `docs/g3-stress-experiment-2026-09-09.md`, with Step 0 and the
scored predictions in `docs/g3-registration-2026-09-09.md`.
**Artefacts:** `sweeps/g3-stress/g3_stress.json` (576 runs, stamped),
`sweeps/g3-stress/g3_stress.PRE-SILENCE-FIX.json` (486 runs, kept as the
before-and-after evidence for §2b).

**In one line:** on the flow the clause is actually about, **G3 fails on both
QoS arms and passes on proportional fair** — and the QoS arms' liveness boundary
is exactly G10's contract boundary, six robots and seven.

**Runtimes:** 576 runs, **1 202 s wall (20.0 min) on 14 workers**, 4.64 h CPU,
29.03 s mean per run; TwoTier 2.17× PF. With the withdrawn first pass, 35.7 min
wall and 8.26 h CPU.

**The previously published G3 row is WITHDRAWN.** It was scored over all flows
including the saturating background, so a flood's own starvation counted as a
telemetry liveness failure; the correction to 10/10 was made on pre-rebuild
code, before M-9, M-6, random access, SRBs, `cp_floor` and the GBR
offered-shortfall fix. Nothing here inherits from it.

**A CAVEAT ADDED 2026-09-11 THAT APPLIES TO EVERY BOUNDARY QUOTED BELOW.** The
boundary rule -- *"the last passing fleet size before the first failure"* -- is
a **maximum over rare events**, so its variance depends on how often the arm
fails at all. An arm that fails often has a stable boundary; an arm that passes
nearly everywhere has one decided by whichever single seed fails earliest.
Measured on ten held-out seeds: **the faithful arm's part-1 boundary is 7 on
both seed sets**, while a candidate scheduler's read **14 on the seeds it was
selected on and 8 on fresh ones** -- on one seed failing at a different fleet
size. **Every aggregate reproduced to within four cells in a hundred; only the
boundary moved.**

**So the boundaries below are sound as DEPLOYMENT figures and must not be used
to RANK two arms that both pass nearly everywhere.** The faithful arms' own
boundaries here are the stable kind, because they fail often enough for the
first failure not to be a rare event. `docs/g3-stress-experiment-2026-09-09.md`
§19 carries the full table and the mechanism.

---

## 1. The question, in operator terms

**The MEC decides a robot is alive because its telemetry keeps arriving. Can
the network make a healthy robot look dead, and get it halted?**

A liveness failure is not a slow robot. It is a **false failsafe** — a robot
stopped because the network stopped carrying its heartbeat.

**Three pass criteria, and they do not fail together.**

- **max telemetry gap ≤ 500 ms** — the MEC's own margin, a quarter of its
  liveness timeout.
- **zero gaps ≥ 2 s across the whole campaign** — a *campaign-wide* zero, not
  a per-run rate. One gap anywhere fails it.
- **p98 ≤ 95 ms** — and this is numerically **G1's own statistic under a
  different guarantee's name**, said plainly so one number does not carry two
  verdicts.

## 2. Why this is the hardest of the five

**G1 and G2 are downlink**, where the gNB reads its own buffers: no scheduling
request, no buffer-status report, no estimate that can desync. **G3 is
uplink**, so every mechanism this project has traced is in play at once — the
cold-start lock-out, the BSR desync, the never-served fault, and the Tier-1.5
service-interval floor that exists specifically to rescue a stalled telemetry
bearer. The test plan calls the family *"existential"* for this scheduler, and
uplink is why.

## 2a. What Step 0 corrected before any number was read

**The bearer was configured in a way that made two of the three criteria
meaningless.** Every 5QI-1 telemetry flow in this repo was `Delay` class with
**no GFBR** — and 5QI 1 is a GBR 5QI in TS 23.501. Three consequences:

- **p98 ≤ PDB is a GBR-conformance statistic** (*"while the flow stays within
  GFBR, 98 % of packets shall not exceed the PDB"*). With no GFBR there is no
  "within GFBR", so those semantics never attached to any published G3 number.
- **No GFBR means no prioritised bit rate**, so the UE's own logical-channel
  prioritisation gave telemetry **no token bucket** and skipped it in round 1.
  **Telemetry is never outranked — it is never reached** (§2c).
- **And that coupling is the deployment's own arithmetic, not a simulator
  convenience.** A DRB's uplink PBR is derived from its GFBR and nothing else
  (`oai-branches/mac_rrc_dl_handler.c:294-350`), a non-GBR DRB passes zero
  (`:296`), and the UE really skips a zero-bucket channel in round 1
  (`nr_ue_scheduler.c:2543-2553`). **The deployed source even records the same
  failure observed on hardware from the other end of the knob** — a PBR above
  the achievable rate, *"one flow taking ~85 MB while its two siblings on the
  same UE got ~10 MB and ~4 bytes."*

**The population was wrong for one criterion.** On the artefact the published
row came from, part 1's worst-gap winner is telemetry on 30 of 30 runs — but
**part 3's winner is the 5QI-2 camera on 8 of 30**, a video bearer with its own
150 ms budget scored against telemetry's 95.

## 2c. A CORRECTION TO THE MECHANISM, and the corrected one is sharper

**An earlier version of this slide said telemetry "waits behind the camera".
That is false.** TS 38.321 §5.4.3.1 step 3 serves every logical channel in
strict decreasing priority order **regardless of Bj**, and telemetry's 5QI-1
priority (20) beats the camera's (40) — so in round 2 telemetry goes *first*.

**What starves it is that round 2 never runs.** The camera's token bucket
exceeds the transport block, so round 1 hands over the whole block and step 3
has nothing left. Measured per grant, N=6, TwoTier:

| | grants |
|---|---|
| telemetry backlogged | 24 971 |
| **served in neither round** | **24 062** |
| … **grant exhausted in round 1** | **24 062 — every one** |
| … round 2 ran and skipped telemetry | **0** |

Median camera bucket **20 784 B** against a median **288 B** block — 72×.

**AND OAI's OWN UE DEVIATES FROM THE STANDARD HERE — conditionally.** Its LCP
builds the channel list from `Bj > 0` only and iterates *that same list* on
every run (`nr_ue_scheduler.c:2538-2556`, `:2744-2814`), so a PBR-0 channel is
excluded from the procedure entirely rather than deprioritised; the C carries a
`TODO` admitting it does not implement §5.4.3.1.2.

**But that file is the nrUE, and whose UE the robots run is not established in
this repo.** The testbed is OAI UEs (test plan §2); the production modem is
named nowhere, and is not on the plan's own open-items list. **If the robots
carry commercial modems this is a testbed artefact — a threat to the hardware
campaign's validity rather than a product defect**, because a GT-2 run on OAI
UEs would show a starvation the product does not have and blame the gNB. **If
they carry OAI UEs it is live and worse than modelled here.** One question to
the client settles it.

## 2d. AND THE ROOT CAUSE IS THE GRANT, WHICH IS THE gNB's

**Nothing sizes an uplink grant by urgency — in this port or in the deployed
C.** `pdb_ms` is a *ranking* term: it decides which UE is served, not how deep
the block is. Uplink sizing is
`max(estimated_ul_buffer − sched_ul_bytes, ul_total_target_bytes,
gbr_bytes_slot)` (`ia_p5g_scheduler.c:3193-3204`); a search of the whole uplink
sizing region for `pdb`/`urgency`/`deadline` returns nothing.

**So a UE can be ranked first and still get a block too small for its urgent
flow.** Measured, robots with a pending heartbeat:

| | N = 6 | N = 16 |
|---|---|---|
| transport block, median | 288 B | 288 B |
| **grant is PRB-limited, not demand-limited** | **100 %** | **100 %** |
| **block smaller than ONE 300 B heartbeat** | **83.6 %** | **97.1 %** |

**At sixteen robots, 97 % of grants to a robot with a pending heartbeat cannot
carry that heartbeat whole.** The comparator was given a deadline term and the

## 2e. AND WHAT ACTUALLY BINDS IS THE ANTI-MONOPOLISATION RESERVE

FIX-2 reserves `min_rb` for every still-unserved GBR UE ranked below the
current one: `cap = max(prbs_left − gbr_below·5, 5)`. **On a 55-PRB band with
`min_rb` 5, eleven such followers exhaust it.** Reconstructed per grant from the
rank stream plus the realised PRB count, TwoTier, scored configuration:

| N | reserve **clamps to min_rb** | grant **equals the cap** | **top-ranked clamped** | PRB med / max |
|---|---|---|---|---|
| 6 | 20.7 % | 77.9 % | **0 %** | 5 / 55 |
| 8 | 10.0 % | 74.3 % | **0 %** | 5 / 55 |
| 12 | 12.3 % | 86.2 % | 3.8 % | 5 / 30 |
| **16** | **100 %** | 99.7 % | **100 %** | 5 / 10 |
| **24** | **100 %** | 99.6 % | **100 %** | **5 / 5** |

- **The reserve sets the grant at every fleet size** — the grant equals the cap
  on 74–99.7 % of grants. At eight robots it withholds **27 % of the band** on a
  median grant without reaching the floor. That is what makes the block 288 B.
- **Above eleven robots the floor saturates and even the top-ranked UE gets
  5 PRB.** At 24 robots the largest grant in 337,599 is 5 PRB. **The
  anti-starvation reserve produces starvation.**
- **It is not the boundary mechanism.** The arms fail at 6 and 7, below the
  threshold, where the leader is never clamped. It is a large-fleet amplifier.

**Which binds: the reserve — as the cap below eleven robots, as the floor
above.** The missing deadline term is real but **inert**, because no
urgency-derived demand can exceed a `max_rbSize` the reserve has already set
to 5.
grant sizer was not.

## 2b. AND A SECOND CORRECTION, IN THE INSTRUMENT BUILT TO REPLACE THEM

**An inter-arrival maximum cannot see a robot that goes dark and stays dark.**
A gap needs a message on both sides of it, so a flow whose last message lands
at t = 1.7 s of a 10 s run has no gap describing the 8.3 s that follow.

**Found by decomposing this campaign's own first artefact, before publishing:
19 flow-runs where the robot was silent for up to 9.5 s while the scored
maximum read 114–342 ms.** One delivered **3 of 100** heartbeats and scored
185 ms — a comfortable pass.

**The fix does not redefine the clause.** Both are published: **part 1** as
literally written, and **part 1s**, the same bound over the longest silence the
window can observe. *The gap between them is the finding.*

---

## 3. The result — G3 FAILS on both QoS arms and PASSES on proportional fair

**The clause is not met.** Part 2 is campaign-wide, and the campaign holds
**36 telemetry silences of two seconds or more in 115 872**:

| arm | verdict | silences ≥ 2 s |
|---|---|---|
| **PF** | **PASS** | **0 of 40 854** — bound ≤ 7.3 × 10⁻⁵ at 95 % |
| **Reservation** | **FAIL** | 10 of 36 514 |
| **TwoTier** | **FAIL** | 26 of 38 504 |

**A two-second silence is twenty consecutive heartbeats missed on a healthy
robot.** That is a false failsafe, not a slow link.

### The fleet size at which a robot starts looking dead

| | part 1 | part 1s | part 2 | part 3 | **all** |
|---|---|---|---|---|---|
| **PF** | 24+ | 24+ | 24+ | 24+ | **24+** |
| **Reservation** | 6 | 6 | 6 | 6 | **6** |
| **TwoTier** | 7 | 7 | 7 | 8 | **7** |

**AND THOSE ARE G10's OWN NUMBERS ON THE QOS ARMS, EXACTLY.** G10's admissible
fleet is **PF 12 / Reservation 6 / TwoTier 7** on a *contract* criterion. G3's
*liveness* boundary lands on **6 and 7** — the same two — while **PF's is at
least 24, twice its own contract boundary.** One mechanism reads out through
both criteria: a UE running out of uplink service.

**My registered prediction that G3 would break BEFORE G10 is refuted**, and the
answer is sharper than either alternative.

### PF is not trading video for telemetry — it is carrying more of everything

| N = 24 | PF | Reservation | TwoTier |
|---|---|---|---|
| protected uplink delivered | **67.06 Mbps** | 23.87 | 24.20 |
| telemetry messages missing (of 2 000) | **0** | 1 140 | 356 |

PF's neighbour-camera completeness does collapse at the very top of the axis
(0.9967 → 0.0300 at N=24). **But both QoS arms reach 0.0000 from seven or eight
robots onward.** Neither buys video by giving up telemetry; it loses both.

## 4. THE UL SERVICE-INTERVAL FLOOR FIRES — first measurement in this project

CLAUDE.md's audit records Tier 1.5 as unobservable, *"activation unknowable"*.
It is neither, and no scheduler change was needed to see it: `floor_fire` is
tier 1.5 of two-tier's own ranking key, which `scheduler/rank_trace.py` already
records.

| N | 4 | 6 | 7 | 8 | 10 | 12 | 14 | 16 | 24 |
|---|---|---|---|---|---|---|---|---|---|
| **fires per 10 runs** | 1 | 42 | 141 | 264 | 527 | 334 | 428 | 575 | **744** |

**PF and Reservation report `None`, not zero** — no such tier exists in their
comparators, and Reservation has no floor even in principle.

**The floor arms, fires, and rises with load — and TwoTier fails from eight
robots anyway.** The mechanism built to rescue a stalled telemetry bearer is
demonstrably active and demonstrably insufficient. That is a stronger statement
than "activation unknown".

## 5. The controls

**The telemetry bearer's prioritised bit rate is the biggest lever available
INSIDE THE UE** — it moves the heartbeat into the one LCP round that runs, ahead
of the camera in the same priority order. **It is a mitigation, not the cause**
(§2d), and it cannot make a 288-byte block carry 300 bytes. At six robots it
still moves TwoTier further than the choice of scheduler does:

| arm | PBR configured | PBR 0 (every earlier G3 number) |
|---|---|---|
| PF | 10/10/10 · p98 median 8.75 ms | 10/10/10 · 17.75 |
| Reservation | 10/10/10 · 16.62 | 10/10/10 · 20.38 |
| **TwoTier** | **10/10/10 · 15.75, nothing lost** | **10/10/7 · 93.25, 121 of 2 000 lost** |

**It moves only TwoTier on this cell** — my prediction said all three, and the
Step-0 probe on a different workload did move all three. Reported as a partial
miss rather than smoothed.

**The bucket duration control does not withdraw it.** `bsd_ms` 100 → 5 ms, the
only value the deployed source states anywhere: no degradation on any arm.

**The long-horizon check does NOT come back clean.** Over a 5× window at N=6,
TwoTier's worst gap goes **165.5 → 416.8 ms**, from 3.0× inside the bound to
1.2× inside it. PF is flat. **So every boundary above is an upper bound**, and
the direction is measured, not assumed.

## 6. The positive control — and it inverts the criteria's order

| SNR | messages (of 400) | **p98 ≤ 95** | **gap ≤ 500** | **zero ≥ 2 s** |
|---|---|---|---|---|
| 20 → 10 dB | 400 | PASS | PASS | PASS |
| **5 dB** | 345–387 | **FAIL** | PASS | PASS/FAIL |
| **0 dB** | 310–375 | FAIL | **FAIL** | PASS |
| **−3 dB** | 172–181 | FAIL | FAIL | **FAIL** |
| **−6 dB** | **3 of 400** | FAIL | FAIL | FAIL |

**Part 3 fails first, and I predicted the opposite.** The reasoning was that
`expire()` caps p98 near the bearer's 100 ms PDB, so it must be the loose
criterion. The cap is real — **p98 pins at exactly 100.25 ms** on every
overloaded cell — but 100.25 against a **95 ms** bound is a 5 % margin, while
500 ms against a 100 ms cadence tolerates **four consecutive losses**. *A ceiling
makes a statistic insensitive at the top, not lenient.*

**And at −6 dB the worst p98 reads 26.50 ms — better than at full signal — for
two robots that delivered three heartbeats between them.** Every message that
survived was one the network carried quickly. That is why a flow with fewer than
two completions is scored here as a failure rather than excluded.

## 6a. GT-2.3 — silence and resume passes everywhere, and the buckets do not differ

**10/10/10 on every arm at every bucket**, in both configurations, over 180 runs
and 180 scheduled resumes with **none failing to complete**. The raw gap is the
scripted pause plus one cadence; the network contributes ~100 ms.

**The buckets were chosen to straddle two-tier's 2 s floor-arming horizon so a
difference would localise to the floor. There is none, and the reason is
structural: above that horizon the floor is disarmed for every arm equally.**
The prediction that the 60 s bucket is where the arms separate is refuted.

**Its own named mechanism is barely reached, and the arithmetic says why.** The
first packet after silence should have to buy a grant with a scheduling request —
but a robot whose camera keeps running never pays that, so a second
configuration pauses the **whole** robot's uplink. Even then: every scripted
resume lands exactly on an SR opportunity (whole-second silences, 4 000 slots
each, SR period 10 slots). **The largest post-silence gap anywhere is 134.25 ms,
3.7× inside the bound**; PF and Reservation resume in 0.25–13 ms, and TwoTier's
78–134 ms is its own ranking, not the SR wait.

**The plan already says this.** GT-2.3 is the one sub-test it marks `Env: RF`
essential, with *"SR fragility does not manifest in rfsim"* beside it. **A
simulator agreeing is weak evidence, and is reported as weak.**

---

## 7. The caveats that travel with every number here

**Cap 4 only — the deployment's value on half its bandwidth.** Cap 2 is this
carrier's faithful derivation at 55 PRB and is **not run**: G3's margins are
not close enough for the cap to decide them (unlike G2, where the cap was the
dominant term). Stated as a scope decision, not an omission.

**GT-2.1 is DEFERRED, with the plan's own reason.** *"If this fails, the fix is
UE-side `prioritisedBitRate` configuration, not the gNB scheduler."* It
discriminates the arms weakly, and the arms are what this evaluation compares.
**Its mechanism is not lost**: the PBR control runs on GT-2.2's cell, where the
flood makes grants scarce — the condition that makes an intra-UE split bite.

**The committed-load axis is DEFERRED.** Fleet size is the axis that ranges
across G10's re-measured boundaries and is comparable with G1's and G9's cells.

**T_live = 2 s and the 500 ms margin are PROPOSED defaults** (the plan marks
them, and names T_live as an open question for the MEC team). Every margin here
is against those numbers.

## 8. Process notes worth carrying

- **The instrument built to replace a defective statistic had the same defect,
  one level along.** A percentile could not see a dropped STOP (G2); an
  inter-arrival maximum cannot see a robot that never comes back. Both were
  caught by decomposing the campaign's own output rather than by a test.
- **Memory bound this grid, not time**, and no per-process guard could have
  seen it: 14 workers reached 17.0 GB with 1.5 GB left, projecting ~56 GB
  against 31 GB of RAM. The shared pool helper watches memory not at all.
- **Killing the parent orphaned all fourteen workers**, still allocating. Their
  argv is the spawn bootstrap, so they cannot be found by script name and had
  to go by PID — exactly as the project notes describe.
- **Six counters added to the scheduler and reverted.** Pure telemetry, zero
  numbers moved in the corpus, and still **12 published claims across G1, G2
  and G10 went stale** because the artefact stamp is the transitive import
  closure. The same fires were already readable from the existing rank stream.
- **Extrapolating a longest-first pool's wall clock from run count is wrong by
  3×.** At 60 % of CPU consumed the run count read 12 %. CPU is the basis.
