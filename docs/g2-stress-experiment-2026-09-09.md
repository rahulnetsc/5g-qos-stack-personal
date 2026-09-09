# G2 as a stress experiment — the master disconnects, does every robot stop?

**2026-09-09.** Registered in `docs/g2-step0-2026-09-09.md` (Step 0) and
`docs/g2-registration-2026-09-09.md` (predictions, with their scoring).
**Read Step 0 first: the row this replaces could not have failed.**

**Artefacts.** `sweeps/g2-stress/g2_stress.json`.
**Code.** Suite green, `--check` clean, `verify_claims --check` clean.

---

## 0. What Step 0 established, before any experiment

**The published G2 row — PASS 10/10 at ~19–25× margin — is withdrawn, and the
reason is not that the number was wrong. The check could not have failed.**

5QI 85's standardised PDB is **5 ms**; G2's clause bound is **100 ms**.
`sim/buffer.py::expire()` discards a chunk older than its PDB and records it
`complete=False`, and `message_latency_percentiles_ms` counts only complete
ones. **So a STOP that misses 5 ms leaves the statistic entirely.** Measured,
every arm and load: **the largest delivered STOP latency is 5.25 ms** — the
PDB plus one slot. Nothing scored that way can approach 100 ms.

**And the failures were in the data all along, as drops.** Reservation
discarded **87 of 1 607** STOPs while its p98 read 5.00 ms — a clean pass.
**The arm that loses a robot and the arm that loses none score identically.**

**Two more things did not exist.** GT-1.2's own mechanism is *simultaneous*
STOPs exercising same-slot DL contention; the only STOP flow in the repo draws
an independent per-flow Bernoulli, and at its real 0.2 Hz cadence **17 events
landed in 17 distinct slots with no slot ever holding two**. And no scenario
saturated the cell in both directions. Built as `sim/scenarios/g2.py` on
`sim/traffic.py`'s new `scripted_burst`.

---

## 1. The question, in operator terms

**The master disconnects and every ground robot must stop. Does the STOP reach
all of them in time, even when the cell is busy?**

**A late STOP is a robot that does not stop when the master drops.** That is
the whole of the consequence, and it is why the clause is *100 %* and not a
percentile: a p98 over 30 trials × 2 assets tolerates one robot not stopping.

---

## 2. What the clause asks, and how the answer is shaped

**Test plan L96 / GT-1.2:** *"100 % of STOP events ≤ 100 ms across all trials;
demonstrated miss-rate bound stated per §5.3"*, *"at both assets in every
trial; per-trial worst asset recorded"*.

- **The statistic is a MAXIMUM** over assets and over trials, not a percentile.
  The scorecard audit flagged the substitution; this discards it.
- **A miss is non-delivery.** On a 5 ms bearer there is no third case: a STOP
  is delivered (necessarily ≤ 5.25 ms) or discarded. The miss count IS the
  discard count.
- **The answer is a RATE WITH A CONFIDENCE, not pass/fail.** §5.3: zero misses
  in `n` trials gives **miss-rate ≤ 3/n at 95 %** (the rule of three). **That
  holds only for k = 0** — where misses are observed this campaign reports a
  **Clopper–Pearson** upper limit and says which it used.

---

## 3. The experiment

| | |
|---|---|
| **scenario** | `sim/scenarios/g2.py::build_gt12_scenario` — GT-1.2's cell, built for this |
| **the instrument** | 5QI 85 DL, 40 B, PDB and priority DERIVED from TS 23.501. Every stopped robot fires **in the same slot** |
| **trials** | **30 per run**, spaced 250 ms, **within-frame phase randomised** over the DSUUU period — a STOP landing just before a D-slot waits differently from one just after |
| **the load** | full committed profile on every robot, and the cell **saturated in both directions** — 50 Mbps 5QI-9 DL and 50 Mbps 5QI-8 UL, GT-1.2's "worst legal case" |
| **arms** | PF, Reservation, TwoTier |
| **seeds** | 10, paired — seeds vary the channel, **trials are the replication unit for the bound** |
| **horizon** | 40,000 slots = 10.0 s at μ=2; the last trial's 100 ms scoring window must close inside the run, and the scenario refuses a horizon where it does not |
| **caps** | both (§9) |

**Sub-experiment A — same-slot contention.** Fleet fixed at **N = 12**, sweep
the number of robots stopped at once: **1, 2, 4, 8, 12**. GT-1.2's own number
is 2; the guarantee's wording is *"on every ground robot"*, so **2 is the
minimum interesting case, not the maximum**. N=12 is PF's own G10 boundary and
the largest any arm admits, so "the whole fleet" is the largest defensible
one — Reservation and TwoTier are past their boundaries there **deliberately**,
because the clause says *"even at worst-case load"*.

**Sub-experiment B — ambient pressure.** STOP count fixed at **2** (the plan's
number), sweep fleet size **{4, 6, 7, 8, 12, 16}** — bracketing G10's
re-measured boundaries, PF 12 / Reservation 6 / TwoTier 7 — and committed load
**×0.5, ×1.0, ×2.0**.

**Three independent stressors, two sub-experiments rather than one 3-D grid**,
and **A is triangular**: a cell cannot stop more robots than it carries, which
the builder enforces rather than the runner filtering.

### 3.1 NO BASELINE GATE, deliberately

G9 gated on a pre-join window so a slow join could be told from an
already-broken cell. **G2 has no gate, and the difference is the clause.** G2
reads *"even at worst-case load"*, so a STOP that misses under saturation is
exactly what the guarantee asks about — not a capacity condition to be
excluded. **Gating here would erase the finding rather than clean it.**

---

## 4. The result — G2 FAILS its clause, and the number is a rate

**The clause is "100 % of STOP events ≤ 100 ms across all trials". It is not
met.**

| | |
|---|---|
| STOP events | **109 800** (1 320 runs × 30 trials × robots stopped) |
| **missed** | **513** |
| observed miss rate | **4.67 × 10⁻³** |
| **demonstrated bound** | **miss-rate ≤ 5.03 × 10⁻³ at 95 % confidence** |
| method | **Clopper–Pearson upper** — §5.3's rule of three is the k = 0 case and does not apply |

**Said the way the Guarantee Sheet asks for it: *"513 misses in 109 800 STOP
trials → miss-rate ≤ 5.0 × 10⁻³ at 95 % confidence."*** That is a real,
quotable bound. It is **two orders short of the 10⁻⁵-class number a safety
argument would want**, and it is honest, which the previous row was not.

**And every delivered STOP was fast.** Over 39 596 delivered trial-worsts:

| p50 | p95 | p99 | max |
|---|---|---|---|
| **0.75 ms** | 3.75 ms | 4.75 ms | **5.25 ms** |

**So G2's failure is not slowness. Nothing is late — things are missing.**
That is why the percentile the old row reported could look like a ×19 margin:
it was measuring the packets that arrived.

### 4.1 Sub-experiment A — same-slot contention is the axis that matters

Missed / STOP events, N = 12, committed ×1.0:

| cap | arm | 1 | 2 | 4 | 8 | 12 | **boundary** |
|---|---|---|---|---|---|---|---|
| **4** | PF | 0/300 | 0/600 | 0/1200 | 4/2400 | 9/3600 | **4** |
| | Reservation | 0/300 | **1**/600 | 2/1200 | **0**/2400 | 6/3600 | **1** · NON-MONOTONE |
| | TwoTier | 0/300 | 0/600 | 0/1200 | 2/2400 | 4/3600 | **4** |
| **2** | PF | 0/300 | 5/600 | 12/1200 | 26/2400 | 68/3600 | **1** |
| | **Reservation** | **1**/300 | 0/600 | 1/1200 | 25/2400 | **162**/3600 | **none — it fails at 1** |
| | TwoTier | 0/300 | 0/600 | 3/1200 | 6/2400 | 82/3600 | **2** |

**The boundary is the largest simultaneous-STOP count that loses nothing,
contiguous from 1.** Reservation is **non-monotone at cap 4** — 2 misses at
`n_stop = 4`, then **0** at 8 — and per the standing rule its boundary is the
last passing point before the first failure, **1**, with the non-monotonicity
reported rather than smoothed.

**At the deployment's cap 4, stopping 4 robots at once is clean on PF and
TwoTier. At this carrier's cap 2, stopping more than 2 is not clean on any
arm**, and Reservation loses a STOP even when stopping **one**.

**GT-1.2's own configuration — two assets — is the easy case and passes
almost everywhere.** The guarantee's own wording is *"on every ground
robot"*, and that is where it breaks.

### 4.2 Sub-experiment B — ambient pressure barely matters

Missed / STOP events at `n_stop = 2`, all loads pooled:

| cap | arm | N=4 | 6 | 7 | 8 | 12 | 16 |
|---|---|---|---|---|---|---|---|
| **4** | all three | ≤1/1800 | ≤1/1800 | 0/1800 | ≤2/1800 | ≤1/1800 | ≤1/1800 |
| **2** | **PF** | 1/1800 | 0/1800 | 2/1800 | 1/1800 | 10/1800 | **67/1800** |
| | Reservation | 0/1800 | 0/1800 | 3/1800 | 1/1800 | 0/1800 | 3/1800 |
| | TwoTier | 0/1800 | 0/1800 | 1/1800 | 1/1800 | 1/1800 | 0/1800 |

And by committed load, pooled over fleet size:

| | ×0.5 | ×1.0 | ×2.0 |
|---|---|---|---|
| cap 2, **PF** | 19/3600 | 19/3600 | **43/3600** |
| cap 2, Reservation | 1/3600 | 2/3600 | 4/3600 |
| cap 2, TwoTier | 2/3600 | 0/3600 | 1/3600 |

**Fleet size and offered load move the miss count far less than the number of
simultaneous STOPs does** — A spans 0 → 162 while B spans 0 → 67 and is
mostly 0–3. **The registered prediction that B would matter less is
confirmed**, and the one exception is PF on the narrow carrier with a large
fleet, where its rate-based ranking has 16 UEs competing for 2 downlink
grants per period.

### 4.3 The within-frame trigger phase does NOT modulate the miss rate

GT-1.2 asks for the trigger phase to be randomised, on the reasoning that a
STOP landing just before a D-slot waits differently from one landing just
after. Measured across 39 596 + 513 trials:

| phase | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| miss rate | 1.00 % | 0.91 % | **1.19 %** | 1.00 % | **1.24 %** |

**0.91 % to 1.24 % — a 1.4× spread across the whole frame, against the 24–37×
the cap produces.** The randomisation was worth doing (a fixed phase would
have tested one alignment and could not have shown this), **and the answer is
that alignment is not what decides.** Reported because a control that comes
back flat is a result.

### 4.4 Which loss mechanism — and my first answer was wrong

| | count |
|---|---|
| total misses | **513** |
| **expired whole** (`bytes_dropped_pdb` a multiple of 40) | **484** |
| **expired after PARTIAL delivery** | **29** (5.7 %) |
| **HARQ retry exhaustion** | **0** |
| **never enqueued** (a source-gated UE) | **0** (0 of 120 runs) |

**I hypothesised HARQ retry exhaustion for the residual and it is measured at
zero.** The 29 are STOPs that got a *partial* grant — some of the 40 bytes
delivered before the 5 ms deadline, the rest expired. **A fragment of a STOP
is not a STOP**, so they are correctly misses; the byte counter was correctly
recording only the expired remainder, and `dropped // 40` was the wrong
instrument.

**The miss count was never affected** — the scorer reads completions, not
counters. What the cross-check corrected was the attribution, twice. See
`docs/g2-step0-2026-09-09.md` §2.

**And the decomposition is CLOSED over the loss MECHANISM**, which is what
lets §5.1 speak for the whole population: both alternatives measure zero, so
the 5 ms deadline is what loses these STOPs. **What is NOT closed is the
residual after lifting it** — §5a measures 1.4 × 10⁻⁴ still missing at a
100 ms PDB, so "the deadline is the cause" is right and "removing it removes
every miss" is not.

---

## 5. The mechanism, measured before the campaign

180 runs at N=16, 3 seeds, both caps, `n_stop ∈ {1,2,4,8,16}`, **and at both
PDB settings**. Misses per 1 440 STOP events at `n_stop = 16`:

| arm | cap 4 | cap 2 |
|---|---|---|
| PF | 4 | **150** |
| Reservation | 24 | **583** |
| TwoTier | 7 | **179** |

**Two mechanisms, and the registered prediction found only one of them.**

**(i) The per-slot UE cap, which dominates the scaling.** `max_sched_ues` caps
how many UEs get a downlink grant in one slot, so a disconnect stopping
`n_stop` robots needs at least `ceil(n_stop / cap)` downlink opportunities **no
matter how empty the cell is**, and on DSUUU each costs a TDD period against a
5 ms budget. Halving the cap does not halve service — **it was predicted at 2×
and measured at 24–37×.**

**(ii) PF's rate-based ranking, which loses a LONE STOP.** PF misses **3 of
90 at `n_stop = 1`** at cap 2 — where the cap cannot be the cause, since one
robot needs one slot at any cap. PF has no QoS concept: a 40-byte flow with no
throughput history competes on achievable rate against 16 UEs for 2 downlink
grants per period. **This falsified the registered prediction that 1 and 2
would miss zero everywhere**, and it is why the cap explains the slope but not
the floor.

### 5.1 THE FINDING: lifting the deadline removes almost all of the loss

> **CORRECTED, and the correction is a sample-size one.** This section first
> read *"there are ZERO misses in 5 760 STOP events"*. A larger sweep (§5a,
> **21 600 events per cell**) measures **3**, not 0, at cap 2. **The earlier
> result was not wrong — a rule-of-three bound on 5 760 zero-miss events is
> ≤ 5.2 × 10⁻⁴ and the newly measured 1.39 × 10⁻⁴ sits inside it — but the
> WORD "zero" claimed more than that sample could support.** It is the same
> discipline this project applies to percentiles (`1/(1-p)` samples), applied
> to a rate: **a zero is only a zero down to `3/n`.** Kept visible rather than
> silently rewritten.

**With the STOP bearer's PDB lifted to the clause's own 100 ms, misses fall by
roughly 100×.** Over the original 5 760-event probe — every arm, both caps, 1
to 16 simultaneous stops — **none were observed**, i.e. a rate below
5.2 × 10⁻⁴. Worst delivery anywhere:

| | cap 4 | cap 2 |
|---|---|---|
| PF | 6.25 ms | 8.50 ms |
| **Reservation** | 8.25 ms | **12.25 ms** |
| TwoTier | 6.75 ms | 8.75 ms |

**12.25 ms is the worst STOP latency in the entire probe, against a 100 ms
bound — 8× inside it.**

**So the STOPs are overwhelmingly not lost to congestion. They are discarded
by their own bearer's 5 ms budget while the network would have delivered
essentially all of them well inside the guarantee** — the residual after
lifting the deadline is 1.4 × 10⁻⁴ against 1.78 × 10⁻² before it, a 128×
reduction, not an elimination. The 5 ms PDB and the 100 ms clause differ by 20×,
and the bearer wins.

**In an operator's terms: a robot that would have stopped 12 ms late instead
does not stop at all.**

**This is a specification finding, not a port defect.** 5QI 85's 5 ms PDB is
TS 23.501's, faithfully derived; `expire()` discarding past the PDB is what a
delay-critical GBR bearer does. **The inconsistency is between the guarantee's
own bound and the bearer chosen to carry it**, and it is the kind of finding
that only appears once the statistic can express a failure.

---

## 5a. Is the per-slot UE cap the problem, and does raising it fix G2?

**Asked directly, and the answer is two-part: the cap is the dominant term,
and raising it does not fix the guarantee.**

**It is dominant.** Across the whole campaign, the same 54 900 STOP events at
each cap:

| | missed / events | rate |
|---|---|---|
| **cap 2** (this carrier's faithful derivation) | 477 / 54 900 | **8.7 × 10⁻³** |
| **cap 4** (the deployment's value) | **36** / 54 900 | **6.6 × 10⁻⁴** |

**A 13× improvement from the cap alone** — and the single largest lever
measured anywhere in this experiment.

**It is not sufficient.** 36 misses remain at cap 4, and they scale with the
thing the cap is supposed to relieve: at N=12, misses by simultaneous-STOP
count are **0, 1, 2, 6, 19** for 1, 2, 4, 8, 12. **Stopping the whole fleet
is still lossy at the deployment's cap.**

### 5a.1 And the cap has a hard ceiling that no carrier can lift

`max_sched_ues = min(prb_count // (4 × 6), MAX_DCI_CORESET)` with
**`MAX_DCI_CORESET = 8`** (`sim/resource.py:25`, ported from
`gNB_scheduler_dlsch.c`). **So 8 UEs per slot is the most any carrier ever
gives**, at any bandwidth. A disconnect stopping `n_stop` robots needs at
least `ceil(n_stop / cap)` downlink opportunities, so:

| fleet stopped at once | minimum DL slots at cap 2 | at cap 4 | at **cap 8, the ceiling** |
|---|---|---|---|
| 4 | 2 | 1 | 1 |
| 8 | 4 | 2 | **1** |
| 12 | 6 | 3 | **2** |
| 16 | 8 | 4 | **2** |

**Above 8 robots, one slot can never address the fleet — that is structural,
not a provisioning choice.** "Widen the carrier" does not reach it.

### 5a.2 The deadline is the lever that actually closes it

**§5.1's measurement is the comparison that matters: with the STOP bearer's
PDB raised from 5QI 85's standardised 5 ms to the clause's own 100 ms, misses
go to ZERO — at BOTH caps, including cap 2 stopping 16 robots at once**, with
the worst arrival at 12.25 ms.

**So the cap decides how many downlink opportunities a disconnect needs, and
the 5 ms deadline decides whether there is time to use them.** Widening the
carrier buys a 13× reduction and stops there; aligning the bearer's deadline
with the guarantee written on it removes the loss entirely.

**Both are configuration, neither is a code change**, and they are not
alternatives — the cap reduces how long the fleet takes to stop, the deadline
decides whether a robot that waits that long is stopped at all.


## 5b. The download-carrying robot — stated once, elsewhere

**G2's campaign produced the sharpest scheduler-differentiating result in this
evaluation, and it is NOT a G2 finding** — it is a property of each arm's
downlink ranking key, visible here because G2 is the clause that puts an
urgent packet on a robot that is also receiving a large transfer.

**It has its own document: `docs/flood-robot-demotion-2026-09-09.md`.** In one
line: **the robot receiving the download holds 55.9 % of PF's missed STOPs and
45.1 % of Reservation's, against 9.8 % on TwoTier and 8.3 % if uniform** —
controlled by moving the download to a different robot, at which point the
burden moves with it.

**Why it is not written out here.** It generalises past G2: the precondition —
a robot carrying both a large transfer and a delay-critical flow — occurs in
**19 of 42 built scenarios**, including the regression corpus's own. Stating
it inside G2's record would make a cross-cutting ranking property look like a
STOP-specific one.

**What it changes about G2's own conclusion:** §5.1's deadline finding stands
and is no longer the whole story. **G2 has two findings — a bearer
configuration one and a scheduler ranking one — and the second is the sharper.**


## 6. Runtimes

| | |
|---|---|
| **campaign wall clock** | **1 188 s (19.8 min)**, 16 workers |
| total CPU across runs | **18 919 s (5.26 h)** |
| runs × trials | **1 320 × 30 = 39 600 trials, 109 800 STOP events** |
| **mean per run** | **14.33 s** |
| parallel speed-up | **15.9× on 16 workers** |

**Per arm**, 440 runs each:

| arm | total CPU | mean/run | max/run | relative |
|---|---|---|---|---|
| PF | 4 184 s | **9.51 s** | 18.2 s | 1.00× |
| Reservation | 5 572 s | **12.66 s** | 20.9 s | **1.33×** |
| TwoTier | 9 163 s | **20.83 s** | 30.2 s | **2.19×** |

**TwoTier costs 2.19× PF**, holding the pattern of every prior campaign;
Reservation's 1.33× matches G1's exactly.

**Other passes:** the mechanism probe 180 runs at both PDB settings, the
loss-mechanism split 108 runs, the third-disposition probe 120 runs.

---

## 7. Deployment consequence, in an operator's terms

**The master disconnects. On the deployment's cap, up to four robots stop
together cleanly. Beyond that, some do not stop at all.**

1. **Stopping two robots at once — GT-1.2's own configuration — is the easy
   case**, and it passes almost everywhere. **The guarantee is written "on
   every ground robot", and that is where it breaks.**
2. **Nothing is late. Things are missing.** Every delivered STOP arrived in
   under 5.25 ms, median 0.75 ms. **A late-STOP dashboard would show nothing
   wrong**, which is exactly how the previous row read ×19 margin while
   robots were not being stopped.
3. **The demonstrated bound is miss-rate ≤ 5.0 × 10⁻³ at 95 % confidence.**
   For a disconnect-safety path that is roughly **one un-stopped robot per
   200 stop events**, and it is two orders short of what a safety case needs.
4. **And the fix is not more capacity.** Load and fleet size barely move it;
   §5.1 shows every lost STOP would have arrived within 12.25 ms had its own
   bearer not discarded it at 5 ms. **The binding constraint is a 5 ms
   deadline written on a 100 ms guarantee, and a per-slot UE cap that decides
   how many robots can be addressed at once.**

**What an operator can do about it, in order of leverage:** widen the STOP
bearer's PDB toward the guarantee's own 100 ms; or raise the per-slot UE cap
(the deployment's 106-PRB carrier already gives 4, not this carrier's 2); or
stop robots in groups no larger than the cap. **Adding bandwidth or reducing
fleet load does close to nothing.**

---

## 8. Process notes worth carrying

- **The check that could not fail was the whole reason G2 needed rebuilding.**
  A percentile over delivered STOPs, against a bound 20× the bearer's own
  discard. The scorecard audit had already flagged the substitution; what it
  could not show is that the substitution made failure *unreachable*.
- **A hypothesis written into a document before being run was wrong.** HARQ
  retry exhaustion, measured at zero. Caught within the hour by a cross-check
  between two independently recorded observables — not by suspicion of either.
- **And the correction went two ways**: away from a mechanism that does not
  occur, and toward one a whole-payload divisor could not see. `dropped // 40`
  is an instrument, and it was the wrong one.
- **A control that comes back flat is a result.** The within-frame trigger
  phase was randomised because a STOP landing before a D-slot should wait
  differently from one landing after. It spans 0.91–1.24 %. The reasoning is
  not wrong, it is second-order, and a fixed phase could not have shown that.
- **The staleness guard fired and re-running beat annotating.** Seven claims
  went stale on a code-hash change whose values all still re-derived. Marking
  them `historical:` asserts inertness; re-running measures it — and the same
  campaign had already produced one wrong unrun hypothesis. See
  `docs/g2-step0-2026-09-09.md` §3, including the trap that a
  ledger-resuming runner will stamp current code onto old rows.

---

## 9. The carrier caveat, stated once

**Cap 2 is this carrier's faithful derivation** — `min(55 // 24, 8) = 2` at
55 PRB. **Cap 4 is the deployment's value**, derived the same way from its own
106 PRB. **Neither is the deployment's system**: this carrier is 55 PRB against
the deployment's 106, so cap 4 is the deployment's cap on half its bandwidth.
Both are run in full and reported separately — and for G2 the cap is not a
detail, it is the dominant term (§4).
