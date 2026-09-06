# Can PDCCH be made to bind? — it already does, and I had the normalisation wrong

**2026-09-06.** Configured Grants were **not** restored; the question is
whether the regime exists, not whether TwoTier wins in it.

---

## THE CORRECTION FIRST, because it changes every earlier statement

**I have been comparing CCE utilisation against 1.0. For an uplink-only
workload the achievable ceiling is 0.7000, and it is exact.**

The carrier is `DSUUU`, and the per-slot CCE budgets are D=48, S=16, U=32.
Over a period the total budget is `48 + 16 + 3×32 = 160`, of which an
**uplink-only** workload can spend only the S and U slots: `16 + 96 = 112`.

> **112 / 160 = 0.7000.** The D-slot budget sits in the denominator and
> **cannot be spent by a workload with no downlink flows.**

Re-normalised:

| workload | CCE utilisation | **% of the achievable 0.70** |
|---|---|---|
| parametric mix | 0.073–0.094 | **10–13 %** |
| **sensor_dense (n=30)** | **0.6357** | **90.8 %** |

**So sensor_dense is already at 91 % of the maximum an uplink-only workload
can reach, and individual slots hit the per-slot cap on 2,308 of them.** My
statement in `docs/sensor-dense-result-2026-09-05.md` — *"the control channel
is LOADED, not BOUND"* — **was wrong, and wrong because of the
normalisation, not the measurement.** The regime exists in this codebase and
sensor_dense is in it.

## The sweep: adding UEs moves AWAY from CCE-bound

| n_ues | CCE | % of ceiling | UL PRB | slots at the per-slot cap |
|---|---|---|---|---|
| **30** | 0.6357 | **90.8 %** | 0.698 | **2,308** |
| 45 | 0.5836 | 83.4 % | 0.790 | 1,462 |
| 60 | 0.5308 | 75.8 % | 0.850 | 845 |
| 90 | 0.4449 | 63.6 % | 0.910 | 140 |
| 120 | 0.3960 | 56.6 % | **0.923** | 14 |

**The premise that saturation lies near 45–50 UEs is refuted: CCE pressure
*falls* monotonically as UEs are added.** PRB saturates instead (0.698 →
0.923), and once PRB binds the scheduler cannot issue enough grants to spend
the CCE budget. **More UEs is the wrong lever, and it is the wrong lever in
the wrong direction.**

## Candidate 1 — aggregation level: REFUTED, and the mechanism is why

The current scenario puts every UE at a **mean** of 12.0 dB, but the AR(1)
channel means the *instantaneous* SNR varies and the realised AL histogram is
**`{2: 4557, 4: 37813, 8: 47}` — mostly AL 4, mean 3.79 CCE per DCI**, not
the uniform AL 2 the mean SNR suggests. **So the "uniform good SNR" premise
was already false before any spread was added.**

Adding a spread, and pushing every UE to cell-edge:

| configuration | mean CCE/DCI | CCE | UL PRB |
|---|---|---|---|
| 12 dB, no spread | 3.79 | **0.636** | 0.698 |
| 12 dB, ±24 dB spread | 3.77 | 0.537 | 0.783 |
| **4 dB uniform** | **8.14** | **0.454** | 0.872 |
| **0 dB uniform** | **14.83** | **0.434** | 0.885 |

**Raising the CCE cost per DCI by 3.9× LOWERS CCE utilisation.** The reason
is the mechanism, and it is the finding:

> **Aggregation level and spectral efficiency degrade together.** A UE that
> needs 16 CCE instead of 4 also needs roughly 4× the PRBs for the same
> bytes. **Both costs rise with the same variable**, PRB is the scarcer
> resource on this carrier, so PRB binds first and harder — every lever that
> raises CCE pressure raises PRB pressure faster.

**A spread does not help either**, because it creates AL-1 UEs alongside
AL-16 ones and the mean barely moves (3.79 → 3.77).

## Candidate 2 — grant frequency: this is the lever, and it is weak

CCE is charged **per DCI**; PRB is charged **per byte**. So the only way to
raise CCE pressure without raising PRB pressure is **more, smaller grants at
the same bitrate**:

| period / payload | CCE | UL PRB | CCE:PRB |
|---|---|---|---|
| 5.0 ms / 200 B *(as shipped)* | 0.636 | 0.698 | 0.91 |
| 2.5 ms / 100 B | 0.638 | 0.632 | 1.01 |
| 1.0 ms / 40 B | 0.640 | 0.578 | 1.11 |
| **0.5 ms / 20 B** | **0.639** | **0.546** | **1.17** |

**This is the only lever that works, and what it does is lower PRB rather
than raise CCE** — CCE is already pinned at ~91 % of its ceiling and cannot
go higher. At 0.5 ms/20 B **CCE exceeds PRB** and is unambiguously the
binding constraint.

## What the data supports

**Neither candidate as posed, and the real answer is a third thing.**

1. **CCE already binds** — 91 % of the achievable ceiling and 2,308 slots at
   the per-slot cap. The earlier "loaded, not bound" reading was a
   normalisation error against 1.0.
2. **The UE-count lever runs backwards.** PRB saturates first, and every
   added UE makes CCE *less* pressed.
3. **Aggregation level cannot be the lever** because AL and spectral
   efficiency are the same variable seen twice. **This is the more
   interesting answer, just not the one predicted:** it is not that a spread
   is needed instead of UEs — it is that **no channel-side lever can make CCE
   bind, because every one of them costs PRBs faster.**
4. **Only the grant-size lever decouples them**, and it works by relieving
   PRB rather than by loading CCE.

**Consequence for the study's regime.** The 30/30-against-2/30 result needs
CCE to be the binding constraint *and* a mechanism that bypasses it.
**Condition one is already met at n=30**; condition two is Configured Grants,
which this branch deleted. **So the regime exists here and the mechanism does
not** — which is a cleaner statement than "we never reached the regime", and
it is the opposite of what I reported yesterday.
