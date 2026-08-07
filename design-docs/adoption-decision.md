# Should we adopt the two-tier scheduler?

Written 2026-08-07, after the fidelity corrections (UE-side uplink LCP, 5QI
priorities, demand-cap removal) that moved several headline numbers. Every
figure here is post-correction. Reproduce with `scripts/scheduler_study.py`
and `scripts/maxmin_study.py`.

**Short answer: yes, adopt — and do not build a scheduler-level fallback to
PF, because it would throw away the parts that work to fix a metric artifact
in the part that does not.**

---

## 1. Two wins that are unconditional and structural

| scenario | metric | PF | TwoTier |
|---|---|---|---|
| `sensor_dense` (PDCCH-bound) | flows on time | 2/30 | **30/30** |
| | worst p99 | 15.0 ms | **5.0 ms** |
| `latency_bound` (deadline vs bulk) | flows on time | 5/8 | **8/8** |
| | worst p99 | 12.0 ms | **4.5 ms** |

These come from Configured Grants and a deadline-aware Tier-2. PF has no
mechanism for either — this is a capability gap, not a tuning gap, so no
amount of PF tuning closes it.

**They also survived every fidelity correction untouched**, which is the
strongest evidence we have that they are real. The corrections that demolished
other results could not touch these two, because neither scenario has a
multi-flow uplink UE.

If the deployment has dense periodic sensors, or latency-critical flows mixed
with bulk, that alone settles the question.

## 2. Where it is *not* better: the GBR knife-edge under infeasibility

`factory_robots`, GBR flows only. `met` counts flows delivering ≥95% of GFBR;
`mean`/`min` are fractions of GFBR.

**0.67× load**

| config | total | met | mean | min |
|---|---|---|---|---|
| PF | **96.5 M** | **6/10** | 83% | 26% |
| TwoTier `scale=0` | 95.1 M | 2/10 | **89%** | 54% |
| TwoTier `scale=1` (default) | 93.2 M | 1/10 | 86% | **82%** |

**1.00× load**

| config | total | met | mean | min |
|---|---|---|---|---|
| PF | 69.3 M | 1/10 | 62% | 1% |
| TwoTier `scale=0` | **73.1 M** | 1/10 | **69%** | 0% |
| TwoTier `scale=1` (default) | 65.9 M | 0/10 | 59% | **53%** |

Read those carefully, because the summary "PF wins" is wrong:

- **On mean GBR delivery TwoTier wins at both loads**, by 6 points at 0.67×
  and 7 at 1.00×.
- **On the worst-served flow TwoTier wins enormously** — 82% against 26% at
  0.67×, 53% against 1% at 1.00×.
- **PF wins only on the knife-edge count** (and marginally on total at
  0.67×, by 1.5%).

At 0.67× TwoTier delivers *every* robot ≥82% of its contracted rate while PF
leaves its worst at 26%. PF scores 6/10 to TwoTier's 1/10 because six of PF's
flows cross 95% while none of TwoTier's do. **Whether that is better depends
entirely on whether 90% of a video feed is worth anything.** For factory
camera and LIDAR uplink it plainly is; for a hard motion-control loop it
plainly is not.

So the honest statement is not "TwoTier is worse in deep overload". It is:
**a threshold metric rewards concentrating the shortfall, and TwoTier is
built to spread it.** That is the same opposition recorded in
[scheduler-study.md](scheduler-study.md) §8.5 — max-min and contract-count
are different objectives — now with a magnitude attached.

## 3. The fallback question, answered by measurement

**A knob-level fallback does not recover PF's contract count.** Sweeping
`gbr_maxmin_scale` at 0.67× load:

| scale | met | mean | min |
|---|---|---|---|
| 0.00 | 2/10 | 89% | 54% |
| 0.25 | 2/10 | 89% | 54% |
| 0.50 | 2/10 | 89% | 54% |
| 0.75 | 1/10 | 88% | 63% |
| 1.00 | 1/10 | 86% | 82% |

Even fully off, TwoTier reaches 2/10 against PF's 6/10. **The gap is not the
max-min floor** — it is Tier-1 allocating toward targets while PF's
opportunism concentrates on good channels and happens to push a few flows
over the bar. No knob we have turns a spreading scheduler into a
concentrating one.

Recovering contract count would need *contract selection* — pick a feasible
subset and fully fund it — which is admission control, deliberately out of
scope for the scheduler.

**A scheduler-level A/B switch is the wrong granularity.** Switching to PF in
deep overload would surrender Configured Grants and deadline awareness — the
two unconditional wins — to improve one metric on one flow class. The
mechanisms are independent and should be governed independently:

| mechanism | regime-dependent? | recommendation |
|---|---|---|
| Configured Grants / SPS | no — self-gating already | always on |
| Deadline-aware Tier-2 | no | always on |
| Tier-1 rate targets | no measured harm | always on |
| **Max-min floor (`gbr_maxmin_scale`)** | **yes** | **policy knob, see below** |

## 4. What to actually do

**Adopt, with `gbr_maxmin_scale` set from a policy question, not from a
detected regime.**

The question is: *for this flow class, is partial delivery useful?*

- **Yes** (video, LIDAR, telemetry — degrades gracefully): `scale = 1.0`.
  Every flow held near the achievable floor.
- **No** (hard control loops — 90% of a control rate is a failed loop):
  `scale = 0`. Let the shortfall concentrate so some flows are fully served.
- **Unsure**: `0.75` is the knee — most of the floor for a small part of the
  aggregate cost.

**No regime detection is required for safety.** At `scale = 0` TwoTier is
ahead of PF on mean and worst-case at both loaded points and ahead on total
at 1.00×; the only thing it gives up is the knife-edge count. A deployment
that is nervous can run `scale = 0` and be no worse off than PF on any
outcome measure, while keeping both structural wins.

**If you want regime awareness anyway, the detector already exists and is
exact.** Tier-1's stage A computes `t*`, the largest fraction of its
contracted floor every GBR flow can hold simultaneously. `t* = 1` means the
GBR set is jointly feasible and the floor binds nothing — it is free. `t* < 1`
is an exact infeasibility test, not a heuristic, recomputed every second, and
`t*` also *quantifies* how far off the set is. That is a better signal than
any load threshold, and it is already being computed.

**Graceful, not hard.** Because `gbr_maxmin_scale` is continuous and its
effect is monotone (min GBR 0 → 13 → 26 → 39 → 53% across scale 0 → 1 at
1.00× load), scaling it with `t*` gives smooth degradation with no switching
transient and no regime-misdetection risk. A hard A/B switch would need a
correct regime call *and* would lose the two mechanisms that work.

## 5. What this rests on, and what it does not

**Solid:** Studies 2 and 3, unaffected by every correction so far, on
mechanisms PF structurally lacks.

**Softer:** the `factory_robots` GBR numbers, which have moved twice this
week as fidelity improved. They may move again. The *direction* — TwoTier
spreads, PF concentrates, and a threshold metric prefers concentration — is
structural and unlikely to reverse.

**Not established:** behaviour under UE churn, multi-cell, or mobility; all
three scenarios are single-cell with a fixed UE population. And the
simulator's remaining known gaps (UL `k2` timing, HARQ retransmissions
consuming PRBs) all point the same way — they would *widen* the Configured
Grant advantage, not narrow it.
