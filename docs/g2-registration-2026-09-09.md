# G2 — predictions, registered before the campaign

**2026-09-09.** Written after `docs/g2-step0-2026-09-09.md` and after the
instrument was built and smoke-tested, **before** the graded campaign.

**DECLARED, because a prediction claimed as blind when it was not is worse
than an informed one:** a 9-run single-seed smoke ran first, to verify the
scorer produces a miss where one exists. It did — **2 misses of 990 STOP
events, both at `n_stop = 8`, none at 1 or 2** — and the drop-byte counter
corroborated exactly (40 B = one 40-byte STOP per miss). So the predictions
below are informed by that smoke and by arithmetic, not blind. What they are
not informed by is any multi-seed, multi-cap, multi-load measurement.

---

## 1. Where the first miss appears, and by what mechanism

**PREDICTION: the first misses appear on sub-experiment A's `n_stop` axis,
not on B's fleet or load axes — and the mechanism is the M-6 per-slot UE cap,
not congestion.**

**The arithmetic.** `max_sched_ues` caps how many UEs get a DL grant in one
slot. A disconnect stopping `n_stop` robots therefore needs at least
`ceil(n_stop / cap)` downlink opportunities, *no matter how empty the cell
is*. On DSUUU at μ=2 those come once per 5-slot period. So:

| cap | n_stop | DL slots needed | earliest the last robot can be served |
|---|---|---|---|
| 4 | 2 | 1 | first opportunity |
| 4 | 8 | **2** | ~1 period later |
| 2 | 2 | 1 | first opportunity |
| 2 | 8 | **4** | ~3 periods later |
| 2 | 16 | **8** | ~7 periods later |

**Against a 5 ms PDB this is the binding constraint**, and it is a property of
the cap and the frame, not of load.

**Specifically predicted:**
1. **Misses rise with `n_stop` and are roughly twice as frequent at cap 2 as
   at cap 4** at the same `n_stop`, because the cap halves.
2. **`n_stop = 1` and `n_stop = 2` miss zero** on every arm at both caps.
   GT-1.2's own configuration is the easy case.
3. **Sub-experiment B — fleet size and offered load — moves the miss count far
   less than `n_stop` does.** A STOP is 40 bytes and outranks the flood on
   `pdb_ms`; ambient traffic is not what keeps it waiting.

**FALSIFIERS, each one specific:**
- If misses appear at `n_stop = 1` or `2`, the ceiling is not the cap — a
  single robot needs one slot at any cap, so a miss there is congestion or
  ranking, and prediction 1's whole mechanism is wrong.
- If cap 4 and cap 2 miss at the same rate at `n_stop = 8`, the cap is not
  binding and the arithmetic above is irrelevant.
- If sub-experiment B's load axis moves the miss count more than A's
  `n_stop` axis does, the mechanism is ambient contention and I have the
  dominant term backwards.

## 2. The arms

**PREDICTION: the arms differ little, and PF is not the worst.** G2's packet
is 40 bytes with the tightest PDB in the panel; every arm's DL ranking reads
`pdb_ms` (TwoTier, Reservation) or an achievable-rate metric on a UE with
almost no throughput history (PF). The smoke is consistent — PF 1 miss,
TwoTier 1, Reservation 0 of 240 each at `n_stop = 8`.

**FALSIFIER:** a consistent, seed-stable arm ordering with a gap wider than
the cap arithmetic explains would mean the ranking, not the cap, is deciding.

## 3. The lifted-PDB diagnostic

**PREDICTION: with the STOP bearer's PDB raised to the clause's own 100 ms,
the misses become deliveries in the 5–15 ms range, and ZERO trials exceed
100 ms on any arm at any point.**

The reasoning is the same arithmetic: 16 simultaneous STOPs at cap 2 need 8
downlink opportunities ≈ 8 × 1.25 ms = 10 ms, which is twice the 5 ms PDB and
a tenth of the 100 ms bound.

**This is the prediction that carries the deployment consequence.** If it
holds, the finding is that **the STOPs are not lost to congestion — they are
discarded by their own bearer's 5 ms budget while the network would have
delivered them inside the guarantee's 100 ms.** A robot that would have
stopped 10 ms late instead does not stop at all.

**FALSIFIER:** any trial exceeding 100 ms with the PDB lifted. That would mean
the network genuinely cannot deliver the STOP in time and the discard is not
the operative cause.

## 4. The miss-rate bound

**PREDICTION: the campaign will NOT be able to state a zero-miss bound at
`n_stop = 8` or 16**, so §5.3's rule of three does not apply there and a
Clopper–Pearson upper limit is what gets reported. At `n_stop ∈ {1, 2}` I
expect zero misses and therefore `≤ 3/n`.

**Stated in advance because the two are different claims** and the temptation
is to quote 3/n everywhere — it holds only for k = 0.

## 5. What would make me withdraw the whole experiment

If the lifted-PDB arm shows the *same* miss pattern as the faithful one, the
5 ms discard is not the mechanism, Step 0's central finding is wrong about
consequence (though not about the statistic being unfalsifiable), and the
experiment needs rebuilding around whatever is actually dropping the packets.


---

# SCORED — the predictions against the mechanism probe

**Measured before the graded campaign**, N=16, 3 seeds, both caps, both PDB
settings, `n_stop ∈ {1,2,4,8,16}` — 180 runs, 5,760 STOP events per PDB
setting. **Recorded here hits AND misses, per the standing rule that a
prediction exercise cited only when right is not one.**

## Prediction 1 — direction RIGHT, magnitude BADLY wrong

*"Misses rise with `n_stop` and are roughly twice as frequent at cap 2 as at
cap 4."* Misses per 1 440 events at `n_stop = 16`:

| arm | cap 4 | cap 2 | ratio |
|---|---|---|---|
| PF | 4 | **150** | **37×** |
| Reservation | 24 | **583** | **24×** |
| TwoTier | 7 | **179** | **26×** |

**Predicted 2×, measured 24–37×.** The direction held and the size did not —
the same shape as the GBR-shortfall miss, where "2 points of headroom against
5" was read as a small difference against a hard threshold. Halving the cap
does not halve the service; it doubles the number of downlink opportunities
each disconnect needs, and each opportunity costs a whole TDD period against a
5 ms budget.

## Prediction 2 — FALSIFIED, and it revealed a SECOND mechanism

*"`n_stop = 1` and `n_stop = 2` miss zero on every arm at both caps."*
**PF at cap 2 misses 3 of 90 at `n_stop = 1` and 2 of 180 at `n_stop = 2`.**

My own registered falsifier said this would mean *"the ceiling is not the cap
— a single robot needs one slot at any cap"*. That is right, and the
conclusion is that **there are two mechanisms, not one**:

1. **The per-slot UE cap**, which dominates as `n_stop` grows and is
   essentially arm-independent — every arm degrades together at 16.
2. **PF's rate-based ranking**, which loses a LONE STOP under a crowded
   downlink at cap 2. PF has no QoS concept; a 40-byte flow with no
   throughput history competes on achievable rate against 16 UEs for 2
   downlink grants per period.

**Prediction 1's mechanism is not wrong, it is incomplete** — it explains the
scaling and not the floor.

## Prediction 3 — CONFIRMED exactly, and it is the headline

*"With the PDB lifted to 100 ms the misses become deliveries in the 5–15 ms
range, and ZERO trials exceed 100 ms."*

**Zero misses in 5 760 STOP events**, every arm, both caps, `n_stop` 1 to 16.
Worst delivery anywhere: **12.25 ms** (Reservation, cap 2, 16 simultaneous) —
**8× inside the 100 ms bound**, and the predicted range was 5–15.

## Prediction on the arms — PARTLY FALSIFIED

*"The arms differ little, and PF is not the worst."* **Both halves fail.** At
cap 2 / `n_stop = 16` Reservation misses **583** against PF's 150 — a 3.9×
spread, not "little". And **which arm is worst depends on `n_stop`**: PF is
worst at 1–4 (it is the only arm missing at all there), Reservation is worst
at 8–16. A single "worst arm" statement would be wrong at one end or the
other.

## Prediction 4 — held

Zero misses at `n_stop ∈ {1,2}` on Reservation and TwoTier, so `≤ 3/n`
applies there; misses elsewhere, so Clopper–Pearson is what those points
report. The two are kept distinct as registered.

## Prediction 5 — the withdrawal condition did NOT fire

The lifted arm shows a completely different pattern from the faithful one
(zero misses against up to 583), so the 5 ms discard **is** the mechanism and
the experiment stands.


---

# RE-SCORED against the full 1 320-run campaign

The mechanism probe's scoring above stands. The graded campaign changes two
verdicts and sharpens a third.

| prediction | mechanism probe | **full campaign** |
|---|---|---|
| 1. misses rise with `n_stop`; cap 2 ≈ 2× cap 4 | direction right, 24–37× not 2× | **same** — at `n_stop=12`: 9→68 (PF), 6→162 (Res), 4→82 (TT), i.e. **7.6× to 27×** |
| 2. `n_stop` 1 and 2 miss zero everywhere | **FALSIFIED** (PF at cap 2) | **FALSIFIED again, and by a different arm** — Reservation misses at `n_stop=1` cap 2 AND at `n_stop=2` cap 4; PF misses 5 at `n_stop=2` cap 2 |
| 3. B moves less than A | not tested | **CONFIRMED** — A spans 0–162, B spans 0–67 and is mostly 0–3 |
| 4. arms differ little, PF not worst | partly falsified | **falsified both ways, and WHICH arm is worst depends on the axis**: Reservation worst on A (162), PF worst on B (67) |
| 5. lifted PDB → zero misses, none over 100 ms | **CONFIRMED**, worst 12.25 ms | unchanged |

**A prediction I did not register, and should have.** I never predicted
anything about the **within-frame trigger phase**, despite building the
randomisation specifically because *"a STOP landing just before a D-slot
waits differently from one landing just after"*. Measured: **0.91 %–1.24 %
miss rate across the five phases, a 1.4× spread against the cap's 24–37×.**
The reasoning that motivated the mechanism is **not wrong but is
second-order**, and had I registered it I would have scored a miss. Recorded
because the omission is the kind that quietly turns a control into
decoration — the randomisation was still worth building, since a fixed phase
could not have shown this.

**And one hypothesis written into a document before being run: the residual
misses attributed to HARQ retry exhaustion, measured at ZERO.** Corrected in
`docs/g2-step0-2026-09-09.md` §2. It is the fourth instance in this project
of a wrong *diagnosis* — an inference about behaviour that was never run —
and it was caught in hours by a cross-check rather than shipping.
