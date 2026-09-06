# Is service burstiness a LEVER or a SYMPTOM? — registration

**Registered 2026-09-06, before the campaign runs.** Closed outcome map.
Anything not registered is reported as a residual.

**Why this is registered rather than published: the correlation it tests has
already survived one retraction.** The grant-density claim held at
ρ = +0.794 and collapsed to ρ = +0.115 (p = 0.21) under a change of units. A
second correlation from the same trace, however clean, is exactly the kind
that should be **tested by intervention** rather than written up again.

---

## 1. The claim under test

**Measured** (`sweeps/phase2/u1_trace.json`, n = 30 per workload): burstiness
of the protected flow's service — `gap p98 / gap p50` — predicts that flow's
p98 **within a workload**:

| workload | PF | Reservation | TwoTier | ρ (burstiness vs flow p98) |
|---|---|---|---|---|
| parametric | 1.3 → 59.0 ms | 1.2 → 29.1 ms | **125.4 → 92.1 ms** | **+0.646**, p = 1.2e−4 |
| `sensor_dense` | 3.8 → 14.5 ms | 1.6 → 14.5 ms | **1.4 → 11.2 ms** | **+0.698**, p = 1.8e−5 |

**The correlation is measured. The causal step is not.** TwoTier is the
burstiest arm where it loses and the most regular where it wins, which is
suggestive and is not evidence of direction.

## 2. The intervention

`TwoTier(anti_hysteresis=α, anti_hysteresis_slots=k)` — **off by default
(α = 0.0), and verified bit-identical to the default arm when off.** When on,
a UE's UL coefficient is multiplied by `(1 − α)` if that UE received a UL
grant within the last `k` slots, damping the run-on that produces clusters.

**It is a divergence probe, not a port and not a proposed default.** Nothing
in `ia_p5g_scheduler.c` corresponds to it. Its only job is to answer the
question.

**Grid:** α ∈ {0.0 (control), 0.25, 0.5, 0.75}, k = 4 slots, parametric mix,
n = 10 paired seeds, 20,000 slots, N=8. Within-seed paired throughout.

## 3. THE MANIPULATION CHECK COMES FIRST, and it can void the experiment

**Before any outcome is read: did burstiness actually fall?** If the damper
does not reduce `gap p98 / gap p50`, the run says **nothing** about the
hypothesis — it is a failed manipulation, not evidence that burstiness is a
symptom. This project has recorded six instances of a mechanism that never
fired being read as a mechanism that did nothing.

**Registered threshold: TwoTier's burstiness ratio must fall by ≥ 30 % at
α = 0.75 relative to α = 0.0, paired within seed.** Below that, the result is
reported as O3 and no causal claim is made in either direction.

## 4. Registered outcomes — closed

| id | outcome | reading |
|---|---|---|
| **O1** | burstiness falls **and** protected-flow p98 improves (paired mean difference excludes 0, favouring the damper) | **burstiness is a LEVER.** The temporal pattern of TwoTier's ranking is a real cause, and the deployed scheduler has a knob-shaped weakness |
| **O2** | burstiness falls **and** p98 is unchanged or worse | **burstiness is a SYMPTOM.** Both it and the latency are downstream of something else; the correlation is confounded and must not be published as a mechanism. **This is the outcome the retraction history makes most likely to be overlooked, so it is named first among the negatives** |
| **O3** | burstiness does **not** fall by the registered threshold | **failed manipulation — the experiment is void**, reported as such. Not evidence for O2 |
| **O4** | p98 improves **but** GBR delivery (M07/M13) or total throughput degrades | **a trade, not a free win.** Report the exchange rate; do not report the p98 improvement alone |
| **O5** | the effect is non-monotone in α | the damper is doing something other than what it is named for; report and stop |
| **R** | anything else | residual, reported unfitted |

## 5. Falsifier, stated so it cannot be softened afterwards

**O2 falsifies the causal reading of §1's correlation.** If burstiness falls
substantially and p98 does not improve, then §1 is a correlation between two
consequences, and `docs/two-tier-settled-2026-09-06.md` §1.1 must be
corrected the same way the grant-density claim was — **at source, in the
document that made it**, not in a footnote.

## 6. Could this check fail?

- **The manipulation is verified independently of the outcome** (§3), so a
  null cannot be produced by an inert knob without being labelled O3.
- **The instrument has dynamic range**: burstiness ranges 1.2–125 across
  existing arms, so there is room in both directions.
- **The control is the same code with α = 0.0**, verified bit-identical to
  the shipped scheduler — so a difference cannot be an artefact of running a
  different program.
- **Paired within seed**, so seed variance is differenced out.

## 7. What no outcome licenses

Whatever it returns, it does **not** establish that this damper should ship.
The Python model matches the deployed scheduler, and a divergence probe that
wins on one metric on one workload is not an argument for changing the
product. **The deliverable is the answer to "lever or symptom", not a
proposed patch.**
