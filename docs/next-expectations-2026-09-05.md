# Registered expectations: G7's aggressor scenario, and G11 C3/C4/C5

**Registered 2026-09-05, before either is built or run.**

**Written under `prediction-journal.md`'s new form rule 4: a prediction must
name WHAT moves — the statistic, the level and the direction — not merely
whether something moves.** The two sessions that produced that rule are the
reason each item below names its level explicitly and states its falsifier.

---

## G7 — the aggressor scenario (GT-4.3)

**Three separate clauses, and they are predicted separately** because
GT-4.3's criterion is a conjunction and the interesting outcome is a split.

| # | clause | statistic | prediction | falsifier |
|---|---|---|---|---|
| **1** | A entirely within SLO | A's M01 p98 protected, M05, M03 vs their bounds | **PASS** — the arms already isolate a non-GBR flood (G6's control), and this aggressor is GBR-on-GBR at 2× MFBR, not a saturating flood | any A-side bound breached on ≥ 2 of 10 seeds |
| **2** | **B's camera delivered ≤ MFBR + tolerance** | B's qfi-2 `throughput_bps` vs `mfbr_bps` | **FAIL, on TwoTier and Reservation alike** | B's delivered ≤ MFBR × 1.1 on ≥ 8 of 10 seeds |
| **3** | B's *other* flows within SLO | B's qfi-1 M01 p98 | **PASS** — B's telemetry is 5QI-1, and both arms' UL rankings put a lower `pdb_ms` ahead of the camera's | B's own telemetry breached on ≥ 2 of 10 seeds |

**Clause 2's mechanism, named rather than a shape.** The clamp
(`two_tier.py:1748-1752`, `reservation.py:1109-1113`) bounds the **GBR
target**; the immediately following `overflow = lcg_estimate - target;
be_bytes += overflow` re-classifies excess as best-effort, where it stays
deliverable. **So delivery above MFBR is expected exactly when spare capacity
exists**, and clause 2 should pass only when the cell is saturated.

**The discriminating second read, registered now:** if clause 2 fails,
compare B's delivered excess against **cell utilisation**. Excess that
vanishes as utilisation → 1.0 confirms the mechanism above (BE-path
delivery). Excess that persists at saturation refutes it and means something
else is exceeding the clamp.

**What clause 2 failing would mean:** a **product** finding — the deployed
scheduler does not implement MFBR as a delivery ceiling — read from the C's
own source, like the Tier-1.5 dead gate. **Not** a simulator gap.

**Control:** PF has no MFBR concept at all, so **PF's clause-2 result is not
evidence about the guarantee** — it is the reference for what "no clipping
whatsoever" looks like.

---

## G11 C3, C4, C5 — three different statistics on one artefact

**No new runs.** All three read
`sweeps/postscaling-2026-09-05/g11_c1_soak.json` — 10 seeds, 7.2M slots,
30/30 runs, already landed. **They are predicted separately because they are
three different questions**, and the form rule exists precisely because
"G11's clauses will pass" is not scoreable.

### C3 — CoV(p98) ≤ 15 % per instrument flow, across fresh seeds
**Statistic:** coefficient of variation of the worst-flow M01 p98 over the
10 seeds, per arm.
**Prediction: PASS on PF and Reservation; PASS on TwoTier but with the
largest CoV of the three.**
**Why, as a mechanism:** TwoTier's p98 spread at n=10 on the core cell is
51.2–98.5 ms against a median of 87.8 — that is a CoV near 15 % on a
*different* cell and metric, and the soak's per-window aggregation over 30
windows per run should shrink it well below the bound.
**Falsifier:** any arm above 0.15.

### C4 — identical PASS/FAIL verdicts across repeats
**Statistic:** C1's per-seed verdict vector, compared across the 10 seeds.
**Prediction: PASS, trivially and uninformatively — all 30 runs already
report 0 failing windows**, so every seed's verdict is identical by
construction.
**Falsifier:** any seed with ≥ 1 failing window.
**AND THE CAVEAT IS THE POINT: C4 cannot fail on this artefact, so its pass
is worth almost nothing.** A verdict vector that is constant because nothing
ever fails is not evidence of consistency — it is evidence the soak is not
near any bound. **Report it as such**; do not present C4 as a passed clause
without that sentence.

### C5 — bimodality that CoV cannot see
**Statistic:** the per-seed p98 **vector**, inspected for clustering — not a
summary.
**Prediction: NO bimodality on PF or Reservation; UNKNOWN on TwoTier, and
this is the only one of the three I would not bet on.**
**Why:** TwoTier is the arm with a lock-out mechanism whose victim is
index-determined, and an arm that either locks a UE out or does not is
exactly the shape that produces two clusters. The soak runs n_ues=4, where
no starvation was observed — so the mechanism is present but may not be
armed at that fleet size.
**Falsifier:** a clear two-cluster structure in PF's or Reservation's
vector, which would mean the bimodality is not scheduler-specific and my
account is wrong.
**Registered explicitly: C5 is the clause most likely to return a real
finding, and C3's instrument is structurally blind to it** — a CoV is
identical for a tight unimodal spread and for two tight clusters equidistant
from the mean, which is why C5 exists as a separate clause and must not be
folded into C3.

---

## What this block would deliver

**G11 from one clause of five to four**, and **G7 from not-measured to
measured — nine guarantees with a verdict rather than eight.** With C4's
caveat stated, and C5 the one that might actually surprise.


---

## SCORED 2026-09-05

### G7 — all three clause predictions HIT, including clause 2's direction

| clause | predicted | measured |
|---|---|---|
| 1 A within SLO | PASS | **PASS**, 0/10 on every arm |
| 2 B delivered ≤ MFBR | **FAIL on both QoS arms** | **FAIL 0/10 at every tolerance incl. 25 %**, 2.0–2.1× MFBR |
| 3 B's own telemetry | PASS | **PASS**, 0/10 on every arm |

**And one correction to my own registered mechanism.** I wrote that delivery
above MFBR should appear *"exactly when spare capacity exists"*. **Too
weak** — the excess persists and *grows* (2.02× → 2.14×) across a 2.5× load
range at ~93 % UL utilisation, so the BE overflow is winning capacity **in
competition**, not merely mopping up idle resources. The second read's limit
is stated with it: utilisation could not be driven above ~0.933 with the load
knob, so *"at saturation"* was never actually reached.

**Unpredicted and the more striking half:** PF, with no MFBR concept at all,
contains the aggressor **better** (1.05×) than either arm implementing the
clamp.

### G11 — C3 hit-with-a-direction-miss, C4 hit, C5 falsifier FIRED

| clause | predicted | measured |
|---|---|---|
| C3 | PASS all three; **TwoTier largest CoV** | **PASS all three** — but **Reservation's CoV is 3.6× TwoTier's**. Verdict hit, direction **MISS** |
| C4 | PASS, satisfied by construction | **exactly that**, and the caveat now travels with the number |
| C5 | no bimodality on PF or Reservation | **the registered falsifier FIRED** — the first scorer reported bimodal on all three including PF |

**C3's direction miss has a named cause:** I extrapolated TwoTier's spread on
the *core cell at n=8* to a soak running *n_ues=4*, where its lock-out is not
armed. A measurement carries its configuration.

**C5's outcome is stronger than a miss:** the scorer itself was unsound on
quantised data, and the fix is a validity guard (pooled SD must exceed the
measurement quantum), not a threshold tuned until the result went away. **C5
is NOT SCOREABLE at n=10 on this artefact** — reported as that rather than as
"no bimodality found".
