# G12 — slide source

**Status:** clause 4 ANSWERED; first-violation order NOT SCOREABLE, with a
reason that changed once and is now a statement about the system.
**Full record:** `docs/g12-stress-experiment-2026-09-08.md`, plus
`docs/gbr-offered-shortfall-2026-09-08.md` and
`docs/tie-break-fidelity-2026-09-08.md`.
**Artefact:** `sweeps/g12-stress/g12_stress.json`, pushed at `974cfa7` /
`fbf60a2`.

---

## 1. The question, in operator terms

**End of shift, everything running hard: what breaks first, and does the
safety telemetry survive?**

The specified degradation order is **best-effort (5QI 9) → lidar (5QI 4) →
camera (5QI 2), and never the safety telemetry (5QI 1).**

Two clauses, scored separately because they are different questions:
- **clause 4** — telemetry is never starved while lower classes still move
  bytes.
- **first-violation order** — the sequence the classes actually break in.

---

## 2. The experiment

| | |
|---|---|
| **axis** | the committed ramp, ×0.5 → ×2.0, with 0.1 steps through the knee at ×1.0–×1.6 |
| **what the ramp scales** | the **whole committed workload** — every GBR/Delay flow's offered bytes and its contract together. Everyone busy at once is G12's question; one misbehaving robot is G7's |
| **occupancy** | **fixed, not a second axis. N = 6**, since G10's boundary put the arms' limits at 5–6 — the realistic worst case. **N = 4** as a comfortable control |
| **arms** | PF, Reservation, TwoTier |
| **seeds** | 10, paired |
| **horizon** | 20,000 slots, μ=2, DSUUU, 40 MHz |
| **caps** | both — cap 2 (this carrier's faithful derivation at 55 PRB) and cap 4 (the deployment's value) |
| **control** | tie-break off (position decides) and on (seeded), both run in full |
| **cost** | 2,640 driver runs, ~14 min |

---

## 3. Clause 4 — the safety telemetry survives

**PASS 10/10 on every arm, both cells, both caps, both tie-break
settings.** 240 ramp sweeps, not one violation and not one vacuous
premise.

**But the margin is the carrier's, not the scheduler's:**

| | telemetry violation rate at ×2.0 |
|---|---|
| TwoTier, 55-PRB cell (cap 2) | **0.969** — two points under the 0.99 starvation threshold |
| TwoTier, deployment's cap 4 | **0.236** |
| PF and Reservation, both caps | **0.000** |

**Deployment consequence:** under a full-shift load ramp to twice committed
capacity, safety telemetry is never sacrificed to keep lower-priority
traffic moving — on any of the three schedulers. On the narrower carrier
TwoTier approaches the starvation threshold and does not cross it.

---

## 4. The ordering clause — not scoreable, and the reason changed

**First reason (now fixed): the traffic generator, not the scheduler.**

The 5QI-2 camera offered **3.8788 Mbps against a 4.0000 Mbps GFBR** — a
ceiling of 0.9697 — so it was pinned 3.5 % below contract at every ramp
point on every arm regardless of load, while 5QI 4 (offered 3.0 against a
GFBR of 3.0) sat at exactly 1.000 throughout.

**The class that appeared to break first was the only one that could not
pass by construction, and the class the spec says should break first never
breached at all.** The previously published TwoTier `[2,4]` was reading the
traffic generator and is **WITHDRAWN** — it does not reproduce at either
cap under either tie-break setting.

**Second reason (current): nothing breaks in the range swept.**

With the shortfall fixed, 5QI 2 moves 0.965 → 0.995 (the residual is now
delivery, not arithmetic) and 5QI 4 stays at 1.000. Neither class is
structurally predisposed to break first.

**At the deployment's cap, nothing breaches anywhere on ×0.5–×2.0, on any
arm.** So "what breaks first" is unanswered because **nothing breaks in
this range** — which is a statement about the system rather than about the
generator. The ramp has to extend past ×2.0.

At cap 2 only TwoTier breaches, and 5QI 4 appears in an order for the first
time — which it structurally could not before.

---

## 5. Why the tie-break control was load-bearing

**A tie never orders 5QI 2 against 5QI 4 directly.** Every UE carrying
5QI 4 also carries 5QI 2, and none carries 4 alone — so their relative
order is settled *inside* those UEs by `priority_level` (40 vs 50).
**Zero ties in 4,594–7,766 intra-UE fills at every ramp point.**

**But an inter-UE tie can move class 4 indirectly** — a tie between a
4-bearing and a non-4-bearing UE shifts service between them. 85–374 such
ties per run, 12–16 % of all UL ties, and 7.8 % of UL slots at ×0.5 falling
to 1.8–2.8 % under load.

**So the control isolates the one thing.** `permute_flows` cannot: it moves
the tie-break *and* every first-flow-found-wins lookup at once, so an order
that shifts under it does not identify the cause. The correct control holds
the flow list fixed and breaks ties on a seeded key instead of position.

**A third reason not to publish an ordering from this resolution:** order
agreement at cap 2 / N=4 falls to **5/10 under a seeded tie-break against
7/10 with position deciding** — a one-element order here is not separable
from the tie-break.

---

## 6. The caveat that travels with any ordering statement

The deployed C ties on the same terms and resolves them the same way —
**measured**, on glibc 2.39, 64-byte records, n = 2…4096, order preserved
at every size. But `qsort` is not required to be stable and glibc has
changed algorithms across releases, so **the order at a tie is libc
behaviour the product inherits rather than something it specifies.**

---

## 7. What this experiment corrected elsewhere

The GFBR shortfall was **never just G12's**. Six flow definitions across
five builders and three YAML scenarios offered below their own GFBR, one
below the 0.95 threshold outright. Fixed at source with one helper; the
enforcement test then found a **seventh** instance the manual sweep had
missed — `g9.py`'s camera, the identical shortfall.

**And it moved G10's headline.** The camera's own contract, not the cell's
capacity, was binding the admissible-fleet boundary:

| arm | published | corrected |
|---|---|---|
| PF | 6 | **12** |
| Reservation | 6 | **6** |
| TwoTier | 5 | **7** |

Reservation not moving is the confirmation — its boundary was
capacity-bound and therefore real.

---

## 8. Process notes worth carrying

- **A predicate inversion caught before any number was read:** the first
  draft scored clause 4 as `m02 ≥ 0.99` meaning healthy, when M02 is a
  violation *rate*. It called every point a failure while the telemetry was
  perfect.
- **The first full run used cap 2 rather than the deployment's cap 4**,
  because `run_ramp` never passed it. Threading it through and running both
  is how the carrier-dependence in §3 surfaced at all.
- **A prediction miss worth recording as a reasoning error:** G10's
  boundary was predicted to hold because 2 points of headroom against 5
  looked like a small difference. Against a hard threshold it is not a
  margin at all.
