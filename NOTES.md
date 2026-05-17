# Working notes

Open issues, partial findings, and things to investigate next. Distinct
from [design-docs/](design-docs/) (what the architecture *should* be) and
[README.md](README.md) (what *works*). Append-only history of "we noticed
this but haven't acted on it yet."

---

## 2026-05-13 — Tier-1 LP behaviors surfaced by the 10-robot scenario

The uplink-heavy factory scenario in [configs/sim_config.yml](configs/sim_config.yml)
(24 flows: 10 robots with UL camera/LIDAR + DL control, 3 with extra PF
best-effort, 1 bidirectional TCP) exposes two TwoTier behaviors that
the prior 3-flow overload scenario didn't surface. Reproduce with
`make compare` and look at the "yaml" block.

### Headline numbers (per-flow delivery ratio)

| Flow | SNR | Class / target | RR | PF | Grad | TwoTier |
|---|---|---|---|---|---|---|
| ue1_qfi2 UL video | 22 | GBR 8M | 48% | 60% | 58% | **79%** ✓ |
| ue2_qfi2 UL video | 18 | GBR 8M | 37% | 44% | 49% | **71%** ✓ |
| ue3_qfi2 UL video | 20 | GBR 8M | 43% | 48% | 52% | **76%** ✓ |
| **ue4_qfi2 UL video** | **16** | GBR 8M | 37% | 40% | 47% | **8%** ⚠️ |
| ue5_qfi2 UL LIDAR | 24 | GBR 14M | 42% | 46% | 52% | **82%** ✓ |
| ue6_qfi2 UL LIDAR | 19 | GBR 14M | 29% | 31% | 42% | **86%** ✓ |
| **ue7_qfi2 UL LIDAR** | **14** | GBR 14M | 18% | 19% | 30% | **4%** ⚠️ |
| **ue8_qfi2 UL video + PF** | 21 | GBR 6M | 72% | 78% | 66% | **42%** ⚠️ |
| ue8_qfi9 UL best-effort | | PF | 73% | 67% | 34% | 37% |
| **ue9_qfi2 UL video + PF** | 17 | GBR 6M | 47% | 57% | 56% | **29%** ⚠️ |
| ue9_qfi9 UL best-effort | | PF | 49% | 46% | 24% | 17% |
| **ue10_qfi2 UL video + TCP** | 20 | GBR 6M | 58% | 73% | 63% | **42%** ⚠️ |
| All DL Delay control | | PDB 10ms | ~98% | 100% | 100% | 100% |

UL utilization saturates at 100% for PF / Grad / TwoTier (overload regime
as designed). DL is at 30–73% utilization (DL underloaded — Delay control
and TCP bulk all met).

### Aggregate summary

Total delivered = sum of delivered throughput over all 24 flows. Mean /
min GBR delivery = mean / min delivery ratio over the 10 GBR (qfi2) flows.

| Scheduler | Total delivered | Mean GBR delivery | Min GBR delivery |
|---|---|---|---|
| RoundRobin | 58.6 Mbps | 43.0% | 17.6% |
| ProportionalFair | 71.9 Mbps | 49.5% | 19.0% |
| Gradient | 70.4 Mbps | 51.3% | **29.6%** |
| TwoTier | **76.1 Mbps** | **51.7%** | 4.4% |
| TwoTier (adaptive penalty, `lr=1e5`) | 70.6 Mbps | 47.5% | 19.8% |

TwoTier wins every *aggregate* — highest total throughput and highest
mean GBR delivery — yet has the **worst** min GBR delivery (4.4% vs
Gradient's 29.6%). That gap is Finding 1: the aggregate win is bought by
starving ue4/ue7. Mean GBR delivery hides it; min GBR delivery is the
metric that exposes it. (The adaptive penalty, 05-16 section below,
trades some of TwoTier's aggregate lead back for a higher floor:
min GBR 4.4→19.8%.)

### Finding 1 — Cell-edge starvation under soft GBR floors

UE 4 (16 dB SNR) and UE 7 (14 dB SNR) drop to 4–8% GBR delivery under
TwoTier vs 19–40% under plain PF. The higher-SNR UEs (1, 2, 3, 5, 6 at
18–24 dB) get 71–86% — *better* than PF.

The Tier-1 LP in [sim/tier1.py](sim/tier1.py) is trading cell-edge GBR
for system-wide log utility: each PRB given to UE 7 yields roughly 2 bits
per RE (SNR 14 dB → MCS staircase row at 13 dB threshold), versus ~4.5
bits per RE for UE 5 at 24 dB. Under utility maximization with *soft*
GBR floors, abandoning the expensive UEs lets more of the cheap ones'
GBR be met. Classic pathology of weighted-log objectives.

**Fix options to evaluate:**
- Hard GBR floors as inequality constraints — feasible-or-not, no
  graceful degradation. Could make the LP infeasible under deep overload.
- SNR-aware GBR weighting (down-weight cheap UEs so the LP sees them as
  less attractive to over-serve).
- Per-UE max-rate caps so high-SNR UEs can't absorb arbitrary capacity
  past their offered load (currently they can).
- Lexicographic / max-min on GBR before maximizing log utility — protects
  worst-case at the cost of total throughput.

### Finding 2 — Mixed-flow UE penalty (root cause unknown)

UEs that have GBR + at least one other flow on the same UE (UE 8, 9, 10)
get *worse* GBR delivery under TwoTier (29–42%) than under plain PF
(57–78%). Worse than doing nothing.

The PF best-effort flows on these same UEs *are* squeezed by TwoTier as
intended (37% / 17% vs PF's 67% / 46%). So the "sacrifice" behavior
works — but the GBR side of the same UE is also being squeezed, which
shouldn't happen.

**Hypotheses to test (in rough order of likelihood):**
- Tier-1 allocates a single per-UE-per-direction PRB budget across all
  the UE's flows, and the LP's split between GBR and PF on the same UE
  is wrong (favors PF in some regime).
- Tier-2 drift-plus-penalty weights on a flow are influenced by other
  flows on the same UE through some shared state.
- A bug in how per-flow `gfbr_bps` is read by the LP when multiple flows
  share a UE.

**How to investigate:** Add temporary logging in `sim/tier1.py` to dump
the per-flow target rates from the LP solution for UEs 8, 9, 10 and
compare against UEs 1, 2, 3 (single-flow UEs). If the LP is already
under-allocating GBR for the mixed-flow UEs, the bug is in Tier-1. If
Tier-1 says "give UE 8's GBR 6 Mbps" but Tier-2 only delivers 2.5 Mbps,
the bug is in Tier-2.

### Caveat on prior session's headline

The 2026-05-02 session reported "TwoTier delivers 97% of GFBR vs 57% for
PF" on an overload scenario. That scenario has 3 flows total (one GBR
UE, no SNR diversity, no mixed-flow UEs). The 10-robot scenario above
is a much harder test and TwoTier is a clear win on only 5 of the 10
GBR flows. Future claims should cite the 10-robot scenario, not just
the 3-flow overload.

### Where to start next session

1. Pick finding 2 first — root cause is small in scope and a clean win
   if it turns out to be a bug (vs design choice).
2. For finding 1, prototype hard-GBR-floors and see how the LP fails
   under deep overload. Compare against an SNR-aware weighting variant.
3. Each tweak: run `make compare` and check the yaml block. Lock in any
   improvements in this file (replace ⚠️ with ✓ once a finding is closed).

---

## 2026-05-16 — Windowed ceiling fix, adaptive penalty, SE-tilt knob

Three changes since the 05-13 notes. The headline table above is the
*default* TwoTier (`gbr_penalty_lr=0`, `gbr_penalty_se_exponent=0`) and
its numbers still hold — the work below is a fix plus two opt-in knobs.

### Regression caught and reverted: virtual-queue clamp

An interim change clamped the Tier-2 virtual queue to instantaneous real
backlog (`Q = min(Q, backlog_bits)`). It was claimed behavior-preserving
on the 3-flow scenario but crushed bursty mixed-flow GBR on the 10-robot
scenario (ue8 42→6%, ue10 42→1%): the clamp zeroes a bursty flow's
virtual queue in the gaps between video frames, destroying its
rate-tracking debt. Replaced with a **windowed ceiling** —
`ceiling = max(0, min(target·W, arrived_W) − delivered_W)` over a
trailing Tier-1 window. Restores the 05-13 baseline. Regression guard:
`test_two_tier_windowed_ceiling_protects_bursty_gbr`.

### Finding 1 — now has a working mitigation (adaptive penalty)

The adaptive per-flow GBR penalty (dual ascent, `gbr_penalty_lr>0`)
escalates `p_i` on whichever flow is *actually* missing its GFBR,
channel-agnostic. On the 10-robot scenario (`lr=1e5`, vs default):

| Metric | default | adaptive |
|---|---|---|
| ue4_qfi2 / ue7_qfi2 | 8% / 4% | **45% / 26%** |
| ue9_qfi2 | 30% | **69%** |
| min GBR delivery | 4.4% | **19.8%** |
| mean GBR delivery | 51.7% | 47.5% |
| total throughput | 76.1 Mbps | 70.6 Mbps |

It lifts the worst-case floor by targeting the real misser. Cost: ~4 pts
mean GBR, ~7% throughput, and it trades *within* the GBR set —
ue8 42→24%, ue10 38→20%. So Finding 1 is **mitigated, not closed**: a
fairness/efficiency tradeoff knob, not a free win. Hard floors /
lexicographic max-min are still worth prototyping for a cleaner guarantee.

### SE-tilt knob (k) — explored, does NOT fix Finding 1

New knob `gbr_penalty_se_exponent` (k): scales each flow's penalty by
`(SE_i/SE_max)^k`. Motivation was "RB-level vs rate-level fairness."
Sweep on the 10-robot scenario, `lr=0`:

| k | mean GBR | min GBR | sum Mbps | ue4 | ue7 | ue8 | ue9 | ue10 |
|---|---|---|---|---|---|---|---|---|
| −1 (RB-parity) | 39.4% | 0.0% | 66.9 | 65% | 64% | 4% | 0% | 4% |
| **0 (default)** | **51.7%** | **4.4%** | **76.1** | 8% | 4% | 42% | 30% | 38% |
| +1 (efficiency) | 52.5% | 4.5% | 76.7 | 8% | 5% | 64% | 11% | 48% |

`k>0` is a near no-op — the objective is already efficiency-tilted, so
the cell-edge flows are sacrificed at `k=0` and `k>0` can't sacrifice
them harder. `k<0` *does* rescue ue4/ue7 but **only relocates**
starvation: it re-sorts victims by SE rank, crushing ue8/9/10 and
lowering both mean GBR and throughput. A static tilt cannot lift the
worst-case floor — only the adaptive penalty does. Stacking `k<0` with
`lr>0` interferes (overshoots the adaptive correction; min GBR
19.8→9.8%). Default stays `k=0`. Full writeup in
[design-docs/scheduler-design.md](design-docs/scheduler-design.md).

### Finding 2 — still open, and now more visible

The `k<0` sweep makes Finding 2 sharper: ue8/9/10 (the mixed-flow UEs)
are exactly the UEs that absorb relocated starvation under every
redistribution we try. Root cause still uninvestigated — see the
05-13 hypotheses and the per-flow LP-dump plan above.

---

## 2026-05-17 — Scheduler study: when does QoS-awareness earn its complexity?

The 05-16 aggregate table made TwoTier (adaptive) look barely
distinguishable from plain PF. Before committing engineering effort to
the two-tier LP + drift-plus-penalty machinery — and the OAI work it
implies — we need to know which deployments it actually changes outcomes
*users feel*, and which it doesn't. Three studies, reproducible with
`python scripts/scheduler_study.py`. Metrics are contract-oriented (a GBR
flow's contract is its GFBR; a Delay flow's is on-time delivery within
PDB) because mean delivery ratio hid every finding below.

### Study 1 — Overload sweep: the value of QoS-awareness is a hump

GBR contracts met (delivered throughput ≥ 95% of GFBR), 10-robot scenario
with carrier capacity scaled around the as-shipped point (1.0×):

| Capacity | PF | TwoTier | TwoTier + adaptive |
|---|---|---|---|
| 1.0× (deep overload) | 1/10 | 3/10 | 0/10 |
| 1.5× | 4/10 | 5/10 | 4/10 |
| 2.0× (moderate overload) | 8/10 | **10/10** | 10/10 |
| 3.0× (light load) | 10/10 | 10/10 | 10/10 |

The scenario as shipped (1.0×) sits in *deep* overload — GBR demand ≈ 2×
capacity — where no scheduler can honor the contracts and PF ≈ TwoTier.
At 3.0× everyone has slack and converges. The scheduler choice decides
outcomes only in the **moderate band (1.5–2.0×)**: at 2.0× TwoTier honors
10/10 contracts vs PF's 8/10, and carries +6.5 Mbps total.

**Engineering implications.** Dimension cells for ~1.5–2× peak overload —
that is the band where the two-tier scheduler earns its complexity. A cell
that *systematically* runs at ≥2.5× overload has a capacity-planning
problem no scheduler fixes; the answer is spectrum/cells or admission
control, not a smarter MAC.

### The adaptive penalty is the wrong shape for deep overload

At 1.0× the adaptive penalty meets **0/10** contracts — worse than default
TwoTier's 3/10 — even though it raised *min delivery* 4%→20% (05-16). Dual
ascent drives toward equal normalized shortfall (PF among GBR flows), but
a GBR contract is a **step function**: 94% of GFBR is a miss. Equalizing
shortfall parks every flow just below the bar so none clears it.

**Engineering implication.** In genuine infeasibility the right tool is
**admission control** — defer/drop some flows, fully satisfy a feasible
subset (a knapsack on contracts) — not penalty equalization. Keep
`gbr_penalty_lr = 0` as the default; treat the adaptive penalty as a
fairness-reporting knob, not a contract mechanism. A flow pinned at
`p_max` and still missing is precisely the admission-control reject signal.

### Study 2 — PDCCH-limited: a structural win PF cannot replicate

30 dense periodic sensors; the per-slot DCI/CCE budget binds before the
data channel. Delay contract = ≥99% on-time within the 15 ms PDB:

| Scheduler | On-time | Worst p99 | Total |
|---|---|---|---|
| RoundRobin | 0/30 | 15.0 ms | 7.0M |
| PF | 18/30 | 15.0 ms | 9.4M |
| TwoTier | **30/30** | **5.0 ms** | 9.6M |

The mechanism is SPS / Configured Grants — a periodic flow gets a standing
allocation and consumes **zero PDCCH per slot**. PF-class schedulers have
no equivalent; this is not tuning, it is a feature they structurally lack.

**Engineering implications.** Any deployment with dense periodic
small-payload traffic (sensors, PLCs, AGV telemetry) *requires* Configured
Grants — put CG support firmly in OAI scope; it is the highest-leverage
feature here. And the bottleneck is the *control* channel, not data:
capacity planning that only counts PRBs/throughput will mis-size it.

### Study 3 — Latency-bound: PF's deadline blindness is silent

8 medium-rate (5 Mbps) interactive streams, 12 ms PDB, sharing a saturated
DL with 80 Mbps of bulk. Delay contract = ≥99% packets on-time:

| Scheduler | On-time | Worst p99 | Bulk DL |
|---|---|---|---|
| RoundRobin | 3/8 | 12.0 ms | 22.8M |
| PF | 4/8 | 12.0 ms | 24.9M |
| TwoTier | **8/8** | **7.5 ms** | 16.8M |

PF schedules by channel-relative throughput and equalizes delivered rate —
no notion of PDB or backlog age — so a healthy 5 Mbps deadline flow is
throttled like any bulk flow. TwoTier funds the interactive set (Delay
class 5× in Tier-1, HoL urgency in Tier-2) and squeezes bulk: an explicit,
deliberate ~8 Mbps bulk trade to meet every deadline.

The dangerous part: PF's failure is **silent**. Its control-flow mean
delivery is 89% — that reads "fine" on a dashboard — but the missing 11%
are aged-out packets, the late control commands, and in a teleoperation /
motion-control loop those are the safety-relevant ones.

**Engineering implication.** Deployments mixing medium-rate
latency-critical flows (teleoperation, AR, motion-control video) with bulk
*require* a deadline-aware scheduler. PF misses, and misses quietly.

### Bottom line — build / don't build

| Deployment characteristic | Scheduler needed | Why |
|---|---|---|
| Uniformly best-effort, or always deeply overloaded | PF | Two-tier LP adds no contract PF can't ~match — pure overhead |
| Dense periodic sensors / PLCs | Two-tier **with SPS/CG** (mandatory) | PDCCH-bound; PF structurally cannot do configured grants |
| Medium-rate latency-critical + bulk mix | Two-tier (deadline-aware Tier-2) | PF is deadline-blind; misses are silent |
| GBR contracts at moderate (1.5–2×) overload | Two-tier (Tier-1 LP) | PF misses contracts the cell could honor |
| GBR contracts at deep (≥2.5×) overload | Admission control, not a scheduler | Genuine infeasibility — satisfy a feasible subset |

Net: the two-tier scheduler is worth building for this factory/warehouse
target — but the load-bearing features are **Configured Grants** and a
**deadline-aware Tier-2**, not the adaptive GBR penalty. The Tier-1 LP
earns its place specifically in the moderate-overload GBR band.

### Metric guidance for the rest of the project

Stop using mean delivery ratio as a headline — it hid all three findings
above. Report: count of GBR flows meeting GFBR, count of Delay flows
on-time within PDB, and p99 HoL. Those are the numbers a deployment owner
feels. (Caveat: in study 1 the worst p99 saturates at the 30 ms PDB for
every scheduler — a burst/PDB-bound ceiling, see the 05-16 side-finding —
so there the GBR-contract count is the discriminator, not p99.)
