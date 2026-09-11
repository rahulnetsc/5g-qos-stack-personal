# G6 — slide source

**Status:** ANSWERED, 2026-09-11.
**Step 0 and registered predictions:** `docs/g6-step0-2026-09-11.md`.
**Artefact:** `sweeps/g6-isolation/g6.json` (1 080 runs, stamped), with
`sweeps/g6-isolation/g6.FLEETWORST.json` kept as the before-and-after evidence
for §7's own scoring defect.

**In one line:** **G6 fails on every arm, and it fails on the SHIFT test rather
than the bound** — a guarantee can report a clean pass while the statistic
behind it doubles.

**Runtimes:** 1 080 runs, **715 s wall (11.9 min) on 26 workers**, on a 32-core
machine.

---

## 1. The question, in operator terms

**A firmware push, a log upload, a map sync. Can ordinary background traffic
degrade the fleet without breaking anything a dashboard would flag?**

That is a different question from isolation. G7 asks whether a *misbehaving*
robot can take the others down. G6 asks whether *entirely legitimate* bulk
traffic quietly erodes the margin the guarantees are sold on.

## 2. G6 IS THE FIRST GUARANTEE WITH NO STATISTIC OF ITS OWN

> *"With saturating 5QI-9 load added (either direction), every G1/G3/G5
> statistic stays within its bound and shifts by ≤ +20 % relative."*

So it re-scores three other guarantees under an added flood and asks **two
independent questions** of each statistic:

| | question | what it catches |
|---|---|---|
| **part A** | still inside its OWN bound? | the flood breaks the guarantee outright |
| **part B** | shifted by more than **+20 %** toward harm? | it degrades materially while still passing |

**Part B is why G6 exists.** Part A is answerable by running G1, G3 and G5 with
a flood. Part B is a *paired ratio*, and a ratio needs a control.

## 3. THE STEP-0 FINDING THAT DECIDED THE DESIGN

**All three base scenarios ALREADY carry 5QI-9 traffic**, so *"load added"* has
nothing to be added to:

| | 5QI-9 flows at N = 8 | what they are |
|---|---|---|
| G1 GT-1.1 | 6 | Poisson, 8 Mbps per UL robot, 50 Mbps DL on the last |
| G3 GT-2.2 | 8 | per-robot filler plus the 50 Mbps flood |
| G5 GT-3.1 | 1 | the 50 Mbps saturator on Asset B |

**The published artefacts are the TREATMENT, not the control**, so G6 cannot be
scored by differencing them — it runs its own control. And the existing
background is **not the same thing in all three**: G1's uplink filler is an
8 Mbps Poisson source, not a saturator, so differencing the three as if they
shared a condition would compare a saturator against a trickle.

Each cell therefore runs **three times** on one seed, differing by exactly one
flow: `none`, `+UL saturator`, `+DL saturator`.

## 4. THE RESULT — every arm fails, and PF fails least

Pass counts over 270 paired deltas per arm per condition:

| | PF | Reservation | TwoTier | Proto |
|---|---|---|---|---|
| **UL flood** — part A / part B | **259 / 257** | 222 / 248 | 176 / 185 | 224 / 199 |
| **DL flood** — part A / part B | 257 / 255 | 230 / 254 | 206 / 237 | **257 / 251** |

**The headline is G1.** Its command p98 never leaves its 95 ms bound on any arm
in any condition — **240 of 240 cells** — and still fails the shift test on
**42 of them**, roughly one in six. **The guarantee reports a clean pass while the statistic
degrades materially**, which is exactly the gap G1 alone cannot see.

**Direction matters and the asymmetry is clean.** The downlink flood barely
reaches the uplink instruments: TwoTier's G3 telemetry gap passes part B on 14
of 30 under the uplink flood and 24 of 30 under the downlink one.

**The first statistic to break its own BOUND is G5's frame age**, on 10 of 30
for both TwoTier and the Proto arm under the uplink flood, while nothing else
on those arms falls below 20.

## 5. THE FINDING WORTH THE SLIDE: part B's pass count prefers rare catastrophes

**TwoTier passes part B more often than the Proto arm and is far worse when it
fails.** Worst absolute telemetry gap under flood, across the campaign:

| worst telemetry gap, any cell | G3 instrument | G5 instrument |
|---|---|---|
| PF | 792 ms | 495 ms |
| Reservation | 2 283 ms | 4 004 ms |
| **TwoTier** | **7 592 ms** | **7 739 ms** |
| **Proto** | **200 ms** | **284 ms** |

**A 27× difference in the worst case, decided the wrong way by a pass count.**
The shift distributions say why — `g5_tele_gap`, uplink flood:

| | median shift | max shift | cells over +20 % |
|---|---|---|---|
| TwoTier | 19 % | 475 % | 15 |
| Proto | 39 % | **151 %** | 19 |

**TwoTier is usually untouched and occasionally catastrophic; the Proto arm is
consistently slightly worse and never catastrophic.** A per-cell relative shift
rewards the first shape. For a safety guarantee that is backwards: an operator
cares about the seven-second silence, not about how many cells moved by a fifth.

**So the honest reading is that the clause's statistic is the problem, not the
scheduler** — and the recommendation is a *scoring* change, not a scheduler
change: **report part B beside the worst absolute value**, so a reader can see
which arm actually leaves a robot silent for seven seconds.

## 6. THE PREDICTIONS, SCORED

| | registered | outcome |
|---|---|---|
| **P-G6-a** | part A passes more often than part B | **HALF RIGHT.** True on PF and TwoTier, FALSE on Reservation and Proto, where part B passes more often. The relationship is per-arm, not structural |
| **P-G6-b** | the DL flood harms G1 and barely touches G3/G5 | **HELD.** TwoTier's G3 gap: 14/30 under UL, 24/30 under DL |
| **P-G6-c** | PF fails part B on G1 where the QoS arms pass | **REFUTED.** PF is the *best* arm on G1's part B (25/30 UL), and best overall |
| **P-G6-d** | the Proto arm fails part B only if the sign convention broke | **REFUTED, and usefully.** It fails 0/30 on frame age with the sign working correctly — see §5 |
| **P-G6-e** | G5's frame age is the first to fail part A | **HELD.** 10/30 on TwoTier and Proto under UL, while nothing else on those arms is below 20 |

**Two of five refuted, one half right.** P-G6-c is the one worth carrying: I
expected PF's shared per-UE rate average to punish a robot that had just
received a firmware burst, as measured in G2. It does not show here, and the
reason is not established.

## 7. A SCORING DEFECT I CAUGHT BEFORE PUBLISHING, AND HOW

**`g5_cam_window_floor` failed part A on every arm in every condition — 0 of
30.** A criterion nothing ever passes is a defect signature, not a result.

**The cause was the population.** I read M23's value, which is the worst
guaranteed-rate flow in the whole protected fleet, and labelled it as the
instrument's. On one cell with no flood: the instrument camera reads **1.0000**
and passes; the fleet's worst reads **0.9901** and fails. That is the
worst-of-N defect this project has recorded repeatedly, and it would also have
let the fleet axis move the statistic as well as the load.

It now reads the instrument's own floor, the fleet-wide value is reported beside
it but is never the verdict, and a test pins both. The uncorrected artefact is
kept rather than deleted.

**What caught it was the impossible number, not a test** — the same recognition
that caught the truncated-BSR wiring: *ask of any surprising count whether it
factors into the run's own dimensions.*

## 8. WHAT THIS DOES NOT SAY

- **No claim is registered.** G6 publishes nothing into
  `config/published_claims.yml` until the 22 stale stamps are resolved
  (`docs/deferred-tasks.md` §2).
- **The Proto arm is a labelled DIVERGENCE.** Its numbers say what a change
  *would* do, never what the product does, and its write-up is deferred
  (`docs/deferred-tasks.md` §3).
- **GT-4.2's 500 MB firmware completion time is specified and not yet
  measured.** It is a characterisation deliverable with no pass line, so it
  cannot fail the guarantee.
- **G4 stays deferred**, so "every G1/G3/G5 statistic" is the whole clause and
  nothing is silently missing from it.
