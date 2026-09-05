# sensor_dense scored — the ranking inverts, and four of my five expectations missed

**2026-09-05.** Scored against `docs/sensor-dense-registration.md`, registered
before the run. n=10 paired seeds, horizon 20,000 slots (10 s at μ=1), PDB
**15 ms**.

## It exists, it runs, and it is a different regime

`sensor_dense_scenario()` builds and runs on all three arms: **30 UEs, 30 UL
periodic flows (5 ms period, 200 B), all `Delay` class, PDB 15 ms.**

| | parametric mix | **sensor_dense** |
|---|---|---|
| CCE utilisation | 7.3–9.4 % | **44–65 %** |
| UL PRB | 93 % | 44–93 % |
| tightest PDB | 100 ms | **15 ms** |

**But the control channel is LOADED, not BOUND: CCE never exceeds 0.650 in
30 runs.** So the PDCCH-bound regime `scheduler-study.md` §7.2 reports is
**still not reached in this branch** — and the reason is structural:
Configured Grants were deleted at Phase 2 two-tier commit 1, so TwoTier
cannot demonstrate the CG bypass, and without SPS reserving capacity the CCE
load does not saturate either. **The study's 30/30-vs-2/30 headline is not
reproducible here, and it is not a disagreement with the study.**

## THE HEADLINE: the ranking inverts between workloads

| arm | parametric M01 p98 (protected) | **sensor_dense M01 p98** |
|---|---|---|
| PF | 25.25 ms | 13.50 ms |
| Reservation | 23.00 ms | 14.25 ms |
| **TwoTier** | **87.78 ms — worst by 3.5×** | **11.00 ms — best** |

**On the parametric mix TwoTier has the worst latency of the three arms. On
sensor_dense it has the best.** `docs/wp9-regime-map.md` §0.1 says the ranking
does not generalise across regimes; **this is the first direct test of that
claim and it holds.**

## The full result

| arm | on-time /30 | starved | worst p98 | M01 p98 | M20 gap | M09 Jain |
|---|---|---|---|---|---|---|
| PF | 30–30 | 0 | 14.50 | 13.50 | 49.3 ms | 0.9997 |
| **Reservation** | 28–30 | **0–2** | 14.50 | 14.25 | **551.7 ms** | **0.7205** |
| TwoTier | 30–30 | 0 | 11.25 | **11.00** | **18.5 ms** | 0.9624 |

**Verdicts against this workload's own 15 ms bound:**

| | G1 (M01 ≤ 15 ms) | G8 (M09 ≥ 0.90) | M22 epochs > 0 | seeds with starvation |
|---|---|---|---|---|
| PF | **PASS 0/10 fail** | **PASS** | 0/10 | 0/10 |
| **Reservation** | PASS 0/10 fail | **FAIL 10/10** | **10/10** | **3/10** |
| TwoTier | PASS 0/10 fail | FAIL 1/10 | 6/10 | 0/10 |

### Which guarantees gained a latency-critical reading

**G1 did, and it is the one that matters.** On the parametric mix every arm
passes a 100 ms bound, which says nothing about deadline behaviour. **Here
TwoTier holds p98 at 11.00 ms against a 15 ms budget** — a latency-critical
pass no parametric result can supply. G3 and G8 also gain a reading; G5, G10,
G4, G6 and G12 cannot be scored here (no `frame_id`, no GBR flow, and no
duty/aggressor/ramp axis).

### And one verdict DIFFERS by workload

**G8's M09 on Reservation: 1/10 failing on the parametric mix, 10/10 failing
here.** Driven by its 551.7 ms liveness gap and its starvation on 3/10 seeds.
**That is a verdict that differs by workload, which is a finding in itself.**

## Scoring my expectations — FOUR OF FIVE MISSED

| # | prediction | outcome |
|---|---|---|
| 1 | PF worst on flows-on-time; TwoTier not near 30/30 | **MISS on both halves** — PF ties best at 30/30, TwoTier reaches 30/30 |
| 2 | all three FAIL the 15 ms bound on most seeds | **MISS** — all three pass, 0/10 |
| 3 | `n_never_granted` = 0 on every arm | **MISS** — Reservation starves on 3/10 seeds |
| 4 | M09 ≥ 0.90 on all three | **MISS** — Reservation 0.7205, failing 10/10 |
| 5 | a verdict differs from the parametric mix | **HIT** — G8 on Reservation, plus the ranking inversion |

**One hit in five.** The common error: I reasoned from the parametric mix's
behaviour and from the study's numbers, and **this workload matches neither**
— it is easier than I expected on latency (a 5 ms period at 200 B is light)
and harder than I expected on fairness for Reservation.

### Expectation 3's miss is the informative one, and it corrects my own account

I predicted no starvation because *"30 UEs each with ONE flow, so there is no
per-LCG array to empty across LCGs and the cold-start lock-out has no
purchase."* **That reasoning is wrong.** The lock-out does not require a
*desync across LCGs* — it requires the array to have **never been written**,
which happens to any UE that loses its first grants regardless of how many
flows it has. **Reservation starves 1–2 UEs on 3 of 10 seeds here with one
flow per UE.**

**This is consistent with, and sharpens, the desync finding**
(`docs/bsr-desync-result-2026-09-05.md`): never-written is the route, desync
is not. I had the right conclusion there and then mis-applied it here.

## A probe defect caught before it reached a result

The first version of `flows_on_time` counted `p98 ≤ 15 ms` without requiring
delivery. **A flow with `delivered = 0` reports `p98 = 0.0`**, so three fully
starved flows scored as *on time* — measured directly: `ue24_qfi1
arrived=80000 delivered=0 p98=0.0`. **Same shape as M19's `p95 = 0.0` failure
signature**, and as the journal's *"a statistic undefined on the data returns
a confident value"* class.

**`sim/scorecard.py::_m01` gets this right** — it filters on `message_count`
and reports the exclusion count — so the defect was mine, not the metric
layer's. Fixed: delivery is now a precondition, and starved flows are counted
separately. **The corrected starved count matches `n_never_granted` exactly
on every run**, which is two independent instruments agreeing.
