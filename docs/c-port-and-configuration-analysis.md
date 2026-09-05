# Two questions settled with existing data: the C port, and the configuration approach

**2026-09-05. Analysis only — nothing built.** Both are answered from data
already on disk plus one query.

---

# 1. THE C PORT — recommendation: PORT ZERO FILES

## The per-file shares, from the 2026-09-04 profile

Complete self-time breakdown over all 8,237 samples of one TwoTier record
(N=8, 20,000 slots, `record_timeseries=True`, full sweep post-processing) —
**derived from `raw_tt.txt`'s full stacks, not from the top-40 summary,
which covers only 56.8 % of samples.**

| file | self % | portable? |
|---|---|---|
| `scipy/.../_highs_wrapper.py` | **23.78 %** | no — third-party |
| **`sim/scorecard.py`** | **18.57 %** | yes |
| **`sim/harq.py`** | **9.19 %** | yes |
| **`scheduler/two_tier.py`** | **6.36 %** | yes |
| `sim/buffer.py` | 4.70 % | yes |
| `sim/traffic.py` | 4.33 % | yes |
| `scipy/.../_linprog_highs.py` | 3.16 % | no |
| `sim/bsr.py` | 3.05 % | yes |
| `sim/metrics.py` | 2.71 % | yes |
| `sim/messages.py` | 2.53 % | yes |
| `sim/driver.py` | 2.00 % | yes |
| `scheduler/tier1.py` | 1.65 % | yes |

**Total portable (`sim/` + `scheduler/`): 59.23 %.**

**The bound, derived:** if *every* line of our own code became free, the
record speeds up **2.45×**. Excluding `sim/scorecard.py` — which is the
scoring layer, not the simulator, and is a separable port — the portable
share is 40.66 % and the bound is **1.69×**. *(The 2.13× figure in the brief
is between these two; the difference is which files count as portable, and
the derivation above is what the profile actually supports.)*

**Confirmed: after the LP, no single file exceeds ~9 % of a record** — the
largest simulator file is `sim/harq.py` at 9.19 %. `scorecard.py`'s 18.57 %
is scoring, and it does not run inside the slot loop at all.

## What porting the top one, two and three would buy

| ported | cumulative share | speedup |
|---|---|---|
| **top 1** — `sim/scorecard.py` | 18.57 % | **1.228×** |
| **top 2** — `+ sim/harq.py` | 27.76 % | **1.384×** |
| **top 3** — `+ scheduler/two_tier.py` | 34.13 % | **1.518×** |

## The costs a port carries *here*, which are not generic

1. **Bit-identity against numpy's PCG64.** Every comparison in this project
   is within-seed and paired. A ported file that draws randomness must
   reproduce **numpy's exact PCG64 stream and its exact `poisson` /
   `normal` / `integers` algorithms**, bit for bit, or every paired seed is
   invalidated and every published figure is re-baselined. `sim/traffic.py`,
   `sim/harq.py` and `sim/channel.py` all draw.
2. **A port-map row per file**, with per-function provenance — this
   project's own convention, and the thing that makes the existing C-to-
   Python port auditable.
3. **A new defect surface**: a second implementation to keep in sync, in a
   project whose recorded failure mode is *fixing at the site of discovery
   rather than the category*. Two implementations double the number of
   sites.

## Recommendation, with the stopping rule stated

> **Port zero files. The stopping rule: port a file only if it alone exceeds
> 25 % of a record — i.e. buys ≥ 1.33× on its own. The largest candidate is
> 18.57 %, and the largest *simulator* candidate is 9.19 %. The rule stops
> the incremental approach at zero files, and that is the answer.**

**Why 25 %:** below it the gain is smaller than the risk introduced by
maintaining a second implementation that must stay bit-identical through a
PCG64 reimplementation. A 1.23× that costs a permanent sync obligation and a
re-baseline risk is not a trade this project should take when
`regime_sweep.run_cells` already delivers 8–16× from parallelism at zero
fidelity risk.

**And the top candidate has a cheaper fix that is not a port.**
`sim/scorecard.py`'s 18.57 % is concentrated in **two lines** —
`_bucket_by_second` at `scorecard.py:150-151` accounts for **11.1 % of the
whole record**. That is a Python-level data-structure problem, it is outside
the slot loop, it draws no randomness, and `Scorecard.score(only=...)`
already exists to skip work. **Fixing it in Python plausibly recovers most
of the top candidate's 1.228× at a fraction of a port's cost and none of its
risk** — which strengthens rather than weakens "port zero files".

---

# 2. THE CONFIGURATION APPROACH — the gate fails; stop

## The gate

**Question: at N=16, does Tier-1 emit more than 8 flows with non-zero
targets?** Queried against 6,466 captured LPs from a real N=16 run
(50 Tier-1 solves, 64 flows):

| | min | median | max |
|---|---|---|---|
| flows with non-zero target | 16 | **31** | 31 |
| DL | 16 | **16** | 16 |
| UL | 0 | **15** | 15 |

**Yes — 31, comfortably more than 8.** So the *precondition* for PDCCH to
matter is present.

## But PDCCH does not bind, and that is the gate

| N | **CCE utilisation** | DL PRB | UL PRB |
|---|---|---|---|
| 8 | **9.4 %** | 0.4 % | **93.7 %** |
| 16 | **7.6 %** | 0.9 % | **93.7 %** |
| 32 | **7.3 %** | 2.6 % | **93.1 %** |

**PDCCH utilisation is 7–9 % at every fleet size measured, while UL PRB sits
at 93 %.** The binding constraint is **PRB, not PDCCH** — and it is
*already* binding, at every N.

**So the configuration approach's premise does not hold on this workload.**
Its value comes from PDCCH limiting how many flows can be granted
simultaneously, forcing a choice of *which subset* to serve. Here there is
no such limit: the scheduler can address every flow it wants to, and what it
runs out of is spectrum.

**Per the brief's own instruction: PDCCH never binds at the fleet sizes
measured, so this stops here.** The architecture is not scoped.

## The one thing worth recording, since it changes if the workload does

**The gate is workload-dependent, not architectural.** CCE utilisation is
low because this mix is UL-heavy (48 of 64 flows UL at N=16) and DL carries
one small `periodic_control` flow per UE. **A DL-heavy workload — many small
DL flows, which is what a large sensor or camera fleet on the downlink looks
like — would move CCE utilisation and could reopen the gate.** The query to
re-run is the one above: CCE utilisation against PRB utilisation, per fleet
size. **Nothing else in the configuration argument needs revisiting unless
that number moves.**
