# G2 — slide source

**Status:** ANSWERED as a stress experiment, 2026-09-09 — **and the row it
replaces could not have failed.**
**Full record:** `docs/g2-stress-experiment-2026-09-09.md`, with Step 0 in
`docs/g2-step0-2026-09-09.md` and scored predictions in
`docs/g2-registration-2026-09-09.md`.
**Artefacts:** `sweeps/g2-stress/g2_stress.json`.

**The previously published G2 row is WITHDRAWN.** *"UL STOP p98 ≤ 100 ms,
10/10 on every arm, ×19 margin"* substituted a **percentile for a maximum** on
a bearer that **discards at 5 ms** against a **100 ms** bound. The margin was
never the scheduler's; it was the gap between two numbers that do not describe
the same thing.

---

## 1. The question, in operator terms

**The master disconnects and every ground robot must stop. Does the STOP reach
all of them in time, even when the cell is busy?**

**A late STOP is a robot that does not stop when the master drops.** That is
why the clause is **100 %** and not a percentile: over 30 trials × 2 assets, a
p98 passes with one robot un-stopped.

---

## 2. What Step 0 corrected before any number was read

**The check could not have failed.** 5QI 85's standardised PDB is **5 ms**;
G2's bound is **100 ms**. A STOP older than its PDB is **discarded**, and a
discarded message never enters a latency statistic. Measured across every arm
and load: **the largest delivered STOP latency is 5.25 ms** — the PDB plus one
slot.

**And the failures were in the data all along.** Reservation discarded **87 of
1 607** STOPs while its p98 read a clean pass. **The arm that loses a robot and
the arm that loses none scored identically.**

**GT-1.2's own mechanism had never occurred.** The test is written around
*simultaneous* STOPs exercising same-slot downlink contention. The only STOP
flow in the repo drew an independent per-flow Bernoulli: at its real 0.2 Hz
cadence, **17 events landed in 17 distinct slots and no slot ever held two.**

**And no scenario saturated the cell in both directions**, which is GT-1.2's
"worst legal case". Built as `sim/scenarios/g2.py` on a new shared-schedule
traffic kind, so simultaneity is **structural rather than lucky**.

---

## 3. The result — G2 FAILS its clause, and the answer is a rate

**"100 % of STOP events ≤ 100 ms" is not met.**

| | |
|---|---|
| STOP events | **109 800** (1 320 runs × 30 trials × robots stopped) |
| **missed** | **513** |
| **demonstrated bound** | **miss-rate ≤ 5.0 × 10⁻³ at 95 % confidence** |
| method | Clopper–Pearson — the test plan's rule of three is the zero-miss case and does not apply |

**In the Guarantee Sheet's own form: *"513 misses in 109 800 STOP trials →
miss-rate ≤ 5.0 × 10⁻³ at 95 % confidence."*** Honest, quotable, and **two
orders short of what a safety case needs.**

**NOTHING IS LATE. THINGS ARE MISSING.** Over 39 596 delivered STOPs:

| p50 | p95 | p99 | max |
|---|---|---|---|
| **0.75 ms** | 3.75 ms | 4.75 ms | **5.25 ms** |

That is why the withdrawn row read ×19 margin: **it was measuring the packets
that arrived.**

### The axis that decides is how many robots stop AT ONCE

Missed / STOP events, N = 12:

| cap | arm | 1 | 2 | 4 | 8 | 12 | boundary |
|---|---|---|---|---|---|---|---|
| **4** | PF | 0 | 0 | 0 | 4/2400 | 9/3600 | **4** |
| | Reservation | 0 | 1/600 | 2/1200 | **0** | 6/3600 | **1** · non-monotone |
| | TwoTier | 0 | 0 | 0 | 2/2400 | 4/3600 | **4** |
| **2** | PF | 0 | 5/600 | 12/1200 | 26/2400 | 68/3600 | **1** |
| | **Reservation** | **1/300** | 0 | 1/1200 | 25/2400 | **162/3600** | **none** |
| | TwoTier | 0 | 0 | 3/1200 | 6/2400 | 82/3600 | **2** |

**GT-1.2's own two-asset configuration is the easy case and passes almost
everywhere. The guarantee says "on every ground robot", and that is where it
breaks.**

**Fleet size and offered load barely matter** — sub-experiment B spans 0–67
misses against A's 0–162, and mostly sits at 0–3. **The within-frame trigger
phase does not matter either**: 0.91 %–1.24 % across the frame, a 1.4 %
spread against the cap's 24–37×. A control that comes back flat is a result.

---

## 4. THE FINDING — every lost STOP would have arrived in time

**With the STOP bearer's PDB lifted to the clause's own 100 ms, there are ZERO
misses in 5 760 STOP events** — every arm, both caps, 1 to 16 robots stopped
at once. The worst delivery anywhere is **12.25 ms**, **8× inside the 100 ms
bound**.

**So the STOPs are not lost to congestion. They are discarded by their own
bearer's 5 ms budget while the network would have delivered every one of them
well inside the guarantee.**

**In an operator's terms: a robot that would have stopped 12 ms late instead
does not stop at all.**

**This is a specification finding, not a defect.** 5QI 85's 5 ms PDB is
TS 23.501's and is faithfully derived; discarding past the PDB is what a
delay-critical GBR bearer does. **The inconsistency is between the guarantee's
own 100 ms bound and the bearer chosen to carry it** — they differ by 20×, and
the bearer wins. It is the kind of finding that can only appear once the
statistic is able to express a failure.

---

## 5. Deployment consequence

**The master disconnects. On the deployment's cap, up to four robots stop
together cleanly. Beyond that, some do not stop at all.**

- **Nothing is late — things are missing.** Every delivered STOP arrived
  under 5.25 ms. **A late-STOP dashboard would show nothing wrong**, which is
  precisely how the withdrawn row read a comfortable margin while robots were
  not being stopped.
- **Roughly one un-stopped robot per 200 stop events**, at 95 % confidence.
- **More capacity does not fix it.** Load and fleet size barely move the
  count; §4 shows every lost STOP would have arrived within 12.25 ms had its
  own bearer not discarded it at 5 ms.

**In order of leverage:** widen the STOP bearer's PDB toward the guarantee's
own 100 ms; or raise the per-slot UE cap (the deployment's 106-PRB carrier
gives 4 against this carrier's 2); or stop robots in groups no larger than
the cap. **Adding bandwidth or shedding fleet load does close to nothing.**

## 5a. Runtimes

**1 188 s wall (19.8 min) on 16 workers; 18 919 s CPU (5.26 h); 1 320 runs
× 30 trials = 109 800 STOP events; 14.33 s mean per run.**

| arm | mean/run | relative |
|---|---|---|
| PF | 9.51 s | 1.00× |
| Reservation | 12.66 s | 1.33× |
| **TwoTier** | **20.83 s** | **2.19×** |


## 6. The caveats that travel with every number here

**Cap 2 is this carrier's faithful derivation at 55 PRB; cap 4 is the
deployment's value on half its bandwidth. Neither is the deployment's system.**
Both are run in full — and **for G2 the cap is the dominant term, not a
detail.**

**The 100 ms bound is a PROPOSED default** (the test plan marks it as such),
to be ratified with the client. Every margin here is against that number, and
**the 5 ms bearer PDB is what actually binds.**

**No baseline gate, deliberately.** G9 gated a pre-join window so a slow join
could be told from an already-broken cell. G2's clause reads *"even at
worst-case load"*, so a STOP that misses under saturation **is** the answer,
not a condition to exclude. Gating would have erased the finding.

---

## 7. Process notes worth carrying

- **The withdrawn row's check could not fail.** A percentile over delivered
  STOPs against a bound 20× the bearer's own discard — and the arm losing
  robots scored the same as the arm losing none.
- **A hypothesis written down before being run was wrong** (HARQ retry
  exhaustion, measured at zero), and a cross-check between two independent
  counters corrected the attribution twice within the hour.
- **A control that comes back flat is a result**: the within-frame trigger
  phase spans 0.91–1.24 % against the cap's 24–37×.
- **When a staleness guard fires on values that still re-derive, re-run
  rather than annotate.** It turns a bookkeeping failure into a bit-identity
  check.

## 8. Open external inputs

- **The 100 ms bound is a PROPOSED default** (the plan marks it), to be
  ratified. **And it is inconsistent with the 5 ms PDB of the bearer chosen
  to carry the STOP** — that inconsistency is the finding, and resolving it
  is the client's call, not the simulator's.
- **GT-1.2 specifies ≥ 10 runs of 30 trials and RF for the certifiable
  number.** This is 1 320 runs of 30 trials in simulation: far more trials,
  and not the certifiable environment.
- **The demonstrated bound is what the campaign can support**, ≤ 5.0 × 10⁻³.
  A 10⁻⁵-class safety claim needs ~300 000 zero-miss trials and is not
  reachable here without first removing the loss mechanism.
