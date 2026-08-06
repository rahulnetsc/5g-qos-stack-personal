# Working notes

Open issues, partial findings, and things to investigate next. Distinct
from [design-docs/](design-docs/) (what the architecture *should* be) and
[README.md](README.md) (what *works*). Append-only history of "we noticed
this but haven't acted on it yet."

---

## 2026-05-13 — Tier-1 LP behaviors surfaced by the 10-robot scenario

The uplink-heavy factory scenario in [sim/scenarios/scenario_config_factory_robots.yml](sim/scenarios/scenario_config_factory_robots.yml)
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
| PF | 1/30 | 15.0 ms | 8.9M |
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
| PF | 5/8 | 12.0 ms | 24.6M |
| TwoTier | **8/8** | **9.5 ms** | 14.4M |

PF schedules by channel-relative throughput and equalizes delivered rate —
no notion of PDB or backlog age — so a healthy 5 Mbps deadline flow is
throttled like any bulk flow. TwoTier funds the interactive set (Delay
class 5× in Tier-1, HoL urgency in Tier-2) and squeezes bulk: an explicit,
deliberate ~10 Mbps bulk trade to meet every deadline.

The dangerous part: PF's failure is **silent**. Its control-flow mean
delivery is 86% — that reads "fine" on a dashboard — but the missing 14%
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

---

## Next — deep dive: Findings 2 & 3

Two open findings to take apart before the OAI work. Both bear on whether
the GBR contracts in [sim/scenarios/](sim/scenarios/) are even dimensionable.

### Finding 2 — Mixed-flow UE penalty (carried forward, still open)

Recap: UEs carrying a GBR flow *plus* another flow on the same UE
(ue8/9/10 in the 10-robot scenario) get worse GBR delivery under TwoTier
than under plain PF. The 05-16 `k`-sweep sharpened it — ue8/9/10 are the
consistent victims of every redistribution — but the root cause is still
uninvestigated. Plan unchanged: dump per-flow Tier-1 target rates for
ue8/9/10 vs the single-flow UEs ue1/2/3. If Tier-1 already under-allocates
the mixed-flow GBR, the bug is in the LP; otherwise it is in Tier-2's
per-UE handling. See the 05-13 hypotheses above.

### Finding 3 — Burst/PDB loss ceiling (promoted from 05-16 side-finding)

Across the Study 1 overload sweep, even at **3× capacity**: GBR *rate*
contracts are all met (10/10 at ≥95% of GFBR), yet delivery ratio plateaus
at ~85% — ~15% of offered GBR bytes are still dropped on PDB expiry — and
worst-case p99 HoL pins at the 30 ms PDB. The loss is capacity-independent;
tripling spectrum does not close it.

Hypothesis: the binding constraint is the *burst*, not the average rate.
The video_frame flows carry an I-frame multiplier — an I-frame is several×
the average frame. If one I-frame's bytes exceed what the cell can deliver
to that flow within a single PDB window, the tail of every I-frame expires
no matter how much average capacity exists.

Why it matters for engineering: a GFBR *rate* contract does not capture
burst or latency integrity. "Contract met" at 3× still means ~15% of
frames arrive with a dropped I-frame tail — visible video artifacts — and
the latency tail sits at the PDB. If the hypothesis holds, these contracts
as written (GFBR + 30 ms PDB for that burst profile) are **partly
undimensionable**: the fix is not in the scheduler but in the contract
(PDB that accounts for the burst), the source (frame-level pacing so an
I-frame spreads over several slots), or admission shaping. This is a
system-design finding, not a scheduler bug.

How to investigate: `buffer.py` already tracks `bytes_dropped_pdb` per
flow — surface it in the metrics summary and the study output. Then
correlate drops with I-frame slots, and compare one I-frame's byte count
against the bytes deliverable to that flow within one PDB at its SNR. If
drops concentrate on I-frame arrivals, Finding 3 is confirmed.

---

## 2026-05-17 — Warm-up transient: a standard run reads GBR delivery ~5 pts low

Checked whether the standard 4000-slot horizon captures steady state by
running `factory_robots` for 60 consecutive 4000-slot windows (60 s) and
tracking GBR delivery and total backlog per window —
`scripts/transient_check.py`.

| | window 1 (= a standard run) | steady state (windows 31–60) | per-window std |
|---|---|---|---|
| TwoTier GBR delivery | 53.7% | 58.5% | ±2.0 pts |
| PF GBR delivery | 45.2% | 49.6% | ±1.5 pts |
| total backlog | ~0.8 MB (still filling) | ~1.0 MB | — |

**Finding — warm-up bias.** Window 1 reads GBR delivery **4.5–4.8 pts
below steady state** on both schedulers (2.3–3.1× the per-window noise
std — a real bias, not scatter). Cause: the buffers fill from empty over
the first ~second (0 → ~1 MB); until occupancy is stationary,
arrived-but-not-yet-delivered bytes depress the delivered/arrived ratio.
Backlog plateaus within one window — the transient is ~1 s long.

**Finding — per-window noise.** Even in steady state a single 4000-slot
window scatters ±1.5–2.0 pts. Channel coherence is 2000 slots, so a
4000-slot run spans only ~2 coherence times — a noisy sample of the
channel ensemble.

**Implication.** Every single-4000-slot number in this file is ~5 pts low
on *absolute* GBR delivery and carries ±~2 pt scatter. But the
**TwoTier − PF gap is stable** — 8.9 pts at steady state vs 8.5 pts at
window 1 — so the comparative findings (which scheduler wins, by roughly
how much) hold; it is the absolute figures that are soft.

**Recommendation.** For absolute figures, discard a 4000-slot warm-up
window (measure from slot 4000 on) and/or average several windows. For
scheduler-vs-scheduler comparison the standard horizon is fine as-is.
Whether to raise the project-default horizon is left open — it would
2–6× every test and study run.

### Studies 2 and 3 are not transient benefits

Same check over 60 windows (120 s) on the two scenarios where TwoTier
shows a clear win, tracking on-time count and worst p99 HoL:

| | TwoTier (window 1 → steady) | PF (window 1 → steady) |
|---|---|---|
| Study 2 — sensor_dense, on-time /30 | 30/30 → **30/30** (flat) | 1/30 → 1.2/30 |
| Study 2 — worst p99 | 5.0 ms (flat) | 14.5 ms (flat) |
| Study 3 — latency_bound, on-time /8 | 8/8 → **7.9/8** | 5/8 → 3.9/8 |
| Study 3 — worst p99 | 9.5 → 9.4 ms | 12.0 → 11.5 ms |

**Study 2.** TwoTier holds 30/30 on time at 5 ms p99 in *every one of the
60 windows* — the SPS / PDCCH win is structural and permanent, not a
warm-up artifact. PF stays at ~1/30 throughout.

**Study 3.** TwoTier is stable at ~7.9/8. PF's window-1 reading of 5/8
was a *mildly favourable* sample (+1.1, 1.6σ above its 3.9/8 steady-state
mean) — so the standard 4000-slot run, if anything, **understated**
TwoTier's edge: the on-time gap is 3 at window 1 but 4 at steady state.
Neither study's TwoTier benefit is a transient. (Backlog on latency_bound
does show a small ~0.3 MB warm-up ramp, but it does not move the on-time
or p99 contract metrics.)

---

## 2026-05-17 — Finding 2 root cause: SPS reservation order, not within-UE cannibalisation

Finding 2 was framed as "within-UE GBR cannibalisation" — UEs carrying a
GBR flow *plus* another flow (ue8/9/10) lose GBR delivery. Root-caused
with `scripts/diagnose_finding2.py`. **It is neither within-UE nor a
Tier-1 issue — it is the SPS reservation policy.**

### Evidence — per-flow dump, factory_robots / TwoTier

| GBR flow | SNR | GFBR | Tier-1 target | SPS reservation | delivered |
|---|---|---|---|---|---|
| ue1–3 (single-flow) | 18–22 | 8 M | 77–100% | 8 PRB each | 71–79% |
| ue8 (mixed) | 21 | 6 M | **6.0 M (100%)** | **none** | 42% |
| ue9 (mixed) | 17 | 6 M | 3.6 M (60%) | **none** | 30% |
| ue10 (mixed) | 20 | 6 M | **6.0 M (100%)** | **none** | 38% |

Tier-1 gives ue8 and ue10 their *full* 6 Mbps GFBR target — the LP has no
per-UE coupling, exactly as expected. But ue8/9/10 get **no SPS
reservation** while ue1–7 do. The extra UL flow is not the culprit
either: ue9's and ue10's PF flows deliver ~0 Mbps yet their GBR is still
starved (ue8's PF flow does harvest 6.3 Mbps, but of *idle* inter-frame
slots its own video was not using — leftovers, not contention).

### Mechanism

`_update_sps_reservations` grants SPS reservations greedily in
flow-enumeration order, skipping a flow once the per-direction PRB budget
is hit (`prbs_reserved + needed > prb_count`). The 10 UL video flows
collectively want more PRBs than the 55-PRB carrier has — the first 7
(ue1–7) already reserve 51 — so the **last-enumerated flows get nothing**
and fall back to pure dynamic scheduling. A bursty video flow with no SPS
cannot drain its I-frame bursts inside the 30 ms PDB → heavy PDB drops
(ue8/9/10 drop 3.5–4.4 Mbps each). ue8/9/10 are the *mixed-flow* UEs only
because the scenario author listed them last; the correlation is
coincidental — the cause is list position.

### Decisive control

| config | ue1–3 single | ue8–10 mixed | gap |
|---|---|---|---|
| TwoTier, SPS on (default) | 75% | 37% | **39 pt** |
| TwoTier, SPS off | 66% | 66% | **1 pt** |
| TwoTier, SPS on, 1.5× carrier | 80% | 46% | 34 pt |

With `enable_sps=False` the gap collapses to 1 pt — the mixed/single
split is entirely an SPS-reservation artifact. Note SPS-on does not merely
withhold a *bonus* from ue8/9/10: it makes them **worse than SPS-off**
(66% → 37%), because the 7 reserved flows lock up 51 of 55 UL PRBs every
slot and the unreserved flows scavenge only the remainder. And 1.5× the
carrier does *not* fix it — higher Tier-1 targets inflate every SPS
reservation in step, so the budget still over-commits. This is a policy
bug, not a capacity shortage.

### Fix direction (next step)

SPS reservations must be allocated by need, not list order — e.g. size
each flow to its GBR floor and, if the total over-commits, shrink all
reservations proportionally so every eligible flow keeps *some* standing
grant; or admit SPS flows in GBR-priority order with a per-flow cap. The
deeper question the control raises: SPS as it stands is net-negative for
worst-case GBR here (it helps 7 flows by +9 pt and hurts 3 by −29 pt) —
the fix should be judged on min GBR delivery, not mean.

---

## 2026-05-17 — Finding 2 fixed: priority-tiered SPS reservation + viability floor

`_update_sps_reservations` rewritten. SPS reservations are now sized to
each flow's contracted floor (GFBR, or the deterministic rate), allocated
per direction in priority order (new `FlowConfig.priority_level`, 5QI
convention — lower = higher priority), and within a tier scaled back
proportionally if they over-commit, so no flow is dropped for being late
in the list. Capped at `sps_budget_fraction` (0.85) of the carrier.

| | before | after |
|---|---|---|
| ue8 / ue9 / ue10 GBR delivery | 42% / 30% / 38% | 76% / 45% / 76% |
| single (ue1–3) vs mixed (ue8–10) gap | 39 pt | **1 pt** |

**Finding 2 is closed.** (ue9's residual 45% is its Tier-1 target — 60% of
GFBR at SNR 17 — the SE/cell-edge effect of Finding 1, not a per-UE
artifact.)

### The viability floor — and a finding it exposed

Shipping just the proportional rewrite first exposed something the old
list-order lottery had hidden: **SPS is net-negative on factory's
overloaded UL.** With every flow treated equally, SPS-on measured *below*
SPS-off at every sizing/budget setting (47% GFBR-sized, 51% target-sized,
vs 56% SPS-off). Cause: factory's UL GBR floors (92 Mbps) over-subscribe
UL capacity (~75 Mbps), so the proportional scale-back shrinks every
reservation to roughly half — and undersized-but-still-occupying SPS locks
most of the carrier into fixed allocation, starving the (better)
drift-plus-penalty dynamic scheduler.

Fix: a **viability floor**. If a priority tier's reservations would be
scaled below `sps_min_scale` (0.75), the tier runs dynamically instead —
*unless* dropping it would overrun the per-slot PDCCH/CCE budget, in which
case SPS's zero-DCI property keeps it the lesser evil. SPS is now
self-gating:

- factory UL — over-subscribed, only ~29% CCE-utilised → tier self-drops →
  dynamic → 56% (= SPS-off, the right answer). SPS no longer hurts.
- vision / sensor_dense — reservations fit → SPS engages as before.
- factory at 1.5× carrier — fits → SPS engages, 77%, gap 1 pt.

factory TwoTier mean GBR delivery: 52% (old lottery) → 56%. SPS engages
where it helps (PDCCH-bound, or capacity ≥ demand) and stands aside where
it would hurt (data-channel overload) — the same hump as the overload
sweep.

Knobs: `sps_budget_fraction` (0.85), `sps_min_scale` (0.75). Decision
recorded: SPS is sized by the GFBR contract (a Tier-1 *input*), not the
LP's derived target — the viability floor compensates for GFBR's tendency
to over-subscribe under overload. Regression guards:
`test_two_tier_sps_oversubscribed_tier_falls_back_to_dynamic`,
`test_two_tier_sps_priority_tier_decides_the_winner`.

---

## 2026-05-17 — Finding 3 confirmed: a contract-dimensioning problem, not a scheduler one

Confirmed with `scripts/diagnose_finding3.py` — three independent lines of
evidence, all pointing the same way.

**Contract arithmetic.** An I-frame arrives as one chunk and has the PDB to
drain, so it needs `I_frame_bytes·8 / PDB` of rate. For the factory video
profiles:

| profile | GFBR | I-frame | burst rate | burst / GFBR |
|---|---|---|---|---|
| camera 8M | 8 M | 132 KB | 35 M | 4.4× |
| lidar 14M | 14 M | 174 KB | 46 M | 3.3× |
| camera 6M | 6 M | 100 KB | 27 M | 4.4× |

The I-frame burst rate is 3–4× the GFBR. At exactly the contracted GFBR
only 22–30 % of an I-frame drains within the 30 ms PDB. **The contract
(GFBR + 30 ms PDB) is internally inconsistent with a 4× I-frame source** —
before any scheduler is involved.

**Scheduler-independence.** One video flow, alone on a 20 MHz carrier (no
contention at all): RoundRobin 98.0 %, PF 98.0 %, TwoTier 97.9 % delivery —
identical. With a single flow there is nothing to schedule; every policy
gives it every PRB. So the loss is provably *not* a scheduler artifact.
Sweeping capacity, delivery is thresholded on the ~35 Mbps burst rate, not
the ~9 Mbps average — it reaches 100 % only once peak capacity clears the
burst, ~5–8× the average.

**The fix is in the inputs.** On a fixed carrier where the lone flow drops,
relaxing the PDB (30→60 ms) or shrinking the I-frame multiplier (4→2×, with
1× = paced/CBR) takes delivery to ~100 %. Both are contract / source
changes; neither touches the scheduler.

**Verdict — Finding 3 confirmed: an admission / contract-dimensioning
problem.** No scheduling policy fixes it. The levers are: dimension the
cell for the *burst* rate not the average; relax the PDB to fit the burst;
pace the source / cap I-frame inflation; or admission-control flows whose
burst cannot be served within PDB. A "GFBR + tight PDB" contract for a
bursty video source is a specification error.

(The isolated test drops only ~2 % — the per-flow burst-vs-capacity tail.
Factory's deeper ~15 % loss adds *aggregate* burst coincidence: its 10
video flows are not I-frame-staggered, unlike `vision`'s, so their bursts
can land together and the summed burst demand exceeds capacity. That too is
a source/dimensioning matter — stagger the encoders — not a scheduler one.)

---

## 2026-05-17 — Tier-2 refactored to per-UE grants + a MAC LCP multiplexer

Restructured Tier-2 to match how the 5G MAC actually schedules — toward
the OAI integration. Tier-2 previously allocated **per flow**: each
`(UE, QFI)` competed independently in the PRB pool and got its own grant
and its own DCI. It now allocates **per UE**:

1. UEs are ranked by the summed drift-plus-penalty deficit of their
   backlogged flows × spectral efficiency.
2. Each granted UE gets PRBs once (**one DCI**) → a transport block size.
3. A MAC logical-channel multiplexer (`_mac_lcp_fill`) fills the TB across
   the UE's flows — by `priority_level`, then drift-plus-penalty deficit.

This holds for both the dynamic pool and SPS (a UE's configured grants are
pooled into one per-UE grant). `Allocation` stays per-flow — the buffer and
metrics are per-flow — so the driver and the other schedulers are untouched.

**What carried over unchanged:** the drift-plus-penalty virtual queues are
now the multiplexer's fill weights (they generalise the LCP prioritised-bit-
rate token bucket); `priority_level` is the logical-channel priority;
`bits_per_prb` is the TBS calc.

**Validation.** 42 tests pass. `sensor_dense` and `latency_bound` (one flow
per UE) are byte-identical before/after — per-UE ≡ per-flow there — which
confirms the refactor. `factory_robots` (multi-flow UEs) shifts, as it must:
the per-UE model is a genuinely different, correct policy for multi-flow
UEs, and it stops over-counting their DCIs (one per UE, not per flow).

**Effect on the overload sweep (Study 1).** The per-UE model evens out GBR
delivery across multi-flow UEs: mean and min GBR delivery stay about the
same or slightly better, but the knife-edge "≥95 % of GFBR" contract count
falls at 1×/1.5× — the old per-flow count was inflated because a multi-flow
UE got several independent entries in the PRB competition. The qualitative
study conclusions are unchanged: the value-of-QoS hump still peaks at
moderate overload (2× is 10/10 vs PF 8/10). Finding 2 stays fixed
(single-vs-mixed gap 1 pt).

**Known gap.** The RR / PF / Gradient baselines still schedule per flow —
a fidelity inconsistency, but low-impact in the current scenarios: the only
multi-flow-UE scenario, `factory_robots`, is not CCE-bound, so the per-flow
DCI over-count does not change its results. Flagged for a later pass if the
baselines need to be strictly comparable on PDCCH.

---

## 2026-05-17 — `scheduler/` library extraction + network slicing

### Reorg — the two-tier scheduler is now a standalone library

The two-tier scheduler is pulled out of the simulator into a top-level
`scheduler/` package that imports only cvxpy / numpy — never `sim/` — so it
can be lifted into OpenAirInterface. `scheduler/` holds Tier-1 (`tier1.py`),
Tier-2 (`two_tier.py`), `FlowConfig` (`flow.py`), the link-adaptation model
(`link.py`), and the I/O contract (`interfaces.py`: `Allocation`, the
`Scheduler` protocol, and structural `SlotView` / `BufferView` /
`ChannelView` / `GridView` views that a host satisfies without inheritance).
`sim/` now depends on `scheduler/` (the correct direction); `sim/config.py`
and `sim/channel.py` re-export `FlowConfig` / link adaptation so simulator
code keeps one import surface. Baselines moved to `sim/baselines/`, tests to
`sim/tests/`. Behaviour unchanged — all tests green.

### Network slicing — a soft slice floor in Tier-1

`FlowConfig.slice_id` tags each flow's network slice;
`TwoTier(slice_shares={slice_id: {"DL": frac, "UL": frac}})` gives each
slice a guaranteed share of per-direction PRB-symbol capacity. It is a
**soft floor** in the Tier-1 LP, not a hard cap:

```
Σ_{slice s, dir d} r_i/SE_i  +  slice_slack_{s,d}  ≥  min(share·C_d, slice_demand_{s,d})
```

The floor is capped at the slice's own offered demand (an idle slice holds
nothing), the slack is penalised (so the LP stays feasible when slice and
GBR floors collide), and the existing per-direction capacity constraint
keeps it **work-conserving** — a busy slice freely borrows an idle slice's
unused share. Verified: under contention a 75/25 share splits capacity
75/25; when a slice is under-utilised the other borrows past its own share.
Tier-2 needs no slice logic — it tracks the (now slice-aware) Tier-1
targets. Same constraint shape as the GBR floor — a contained Tier-1
addition.

---

## 2026-05-17 — RR / PF / Gradient baselines converted to per-UE grants

Closes the **Known gap** flagged in the per-UE Tier-2 entry above. The
three comparison baselines previously scheduled **per flow** — each
`(UE, QFI)` competed independently in the PRB pool and drew its own DCI —
while Tier-2 had already moved to **per-UE** grants. That asymmetry made
the DCI/CCE accounting awkward to explain. All three now grant **per UE**,
matching Tier-2 and the 5G MAC:

1. This direction's backlogged flows are grouped by UE.
2. Each UE is ranked by the baseline's own metric (RR: round-robin cursor
   over UEs; PF: `bits_per_rb / R_avg_ue`; Gradient: per-UE base PF × the
   largest class-aware urgency multiplier among the UE's backlogged flows).
3. The selected UE(s) get PRBs once (**one DCI**) → a transport block.
4. A shared MAC multiplexer ([`sim/baselines/_mac.py`](sim/baselines/_mac.py),
   `lcp_fill` / `emit_grant`) fills the TB across the UE's flows — by
   `priority_level`, then backlog. The baselines carry no virtual queues,
   so the within-priority tiebreak is plain backlog (Tier-2 uses
   drift-plus-penalty deficit there instead).

`R_avg` is now keyed per UE (was per `(UE, QFI)`). For Gradient's GBR
urgency term this means the UE's smoothed rate is compared against a
flow's GFBR — exact for a single-GBR-flow UE, an approximation for a
multi-flow UE; acceptable for a baseline. `Allocation` stays per-flow
(PRBs + `cce_cost` ride on the first filled flow), so the driver and
metrics are untouched.

**Validation.** 44 tests pass. Single-flow-per-UE scenarios
(`sensor_dense`, `latency_bound`) are unchanged — per-UE ≡ per-flow there.
`factory_robots` (multi-flow UEs) shifts, as expected: the baselines now
draw one DCI per UE instead of one per flow, so all four schedulers are
finally strictly comparable on PDCCH/CCE.

---

## 2026-05-17 — UL BSR round-trip modeled; SPS's second bypass surfaces

The sim previously gave the scheduler zero-latency, perfect-fidelity
visibility of the UL buffer -- unrealistic. In real 5G the gNB learns
about UE-side data only via a delayed and quantised BSR MAC CE that
piggybacks on a UL grant that itself was triggered by a Scheduling
Request; the round-trip is ~4-8 ms for an idle UE. **This gap surfaced
during the parallel OAI-integration workstream**, not in the sim itself.

**Fix (cheap approximation).** `BufferModel` gains `ul_bsr_delay_slots`;
`BufferState.bytes_reported` lags `bytes_queued` by that many slots for UL
flows, `== bytes_queued` for DL. Dynamic schedulers (RR / PF / Gradient /
TwoTier's `_allocate_dynamic`) now read `bytes_reported` for eligibility
and grant sizing. **SPS / Configured Grants read `bytes_queued` directly**
-- a CG UE fills its reserved PRBs with real data, no BSR needed. The MAC
LCP fill also reads real bytes (once a grant exists the UE fills with
what it has). Study default: 8 slots ≈ 4 ms at μ=1. Tests default to 0
(backward compat); new tests lock in the pipeline behaviour.

**Effect on the studies.**

| Study | Metric | BSR off | BSR on (8 slots) |
|---|---|---|---|
| 1 @ 2.0× | PF GBR met | 8/10 | **5/10** |
| 1 @ 2.0× | PF min GBR | 66% | **32%** |
| 1 @ 2.0× | TwoTier GBR met | 10/10 | **10/10** (SPS bypasses) |
| 2 (sensor_dense) | TwoTier / PF on-time | 30/30 vs 1/30 | 30/30 vs 1/30 |
| 3 (latency_bound) | any | unchanged (DL) | unchanged |

The 2.0× row is the big one. Dynamic PF now absorbs the full ~4 ms BSR
latency and its GBR-contract count drops from 8/10 to 5/10; min GBR halves
(66→32 %). TwoTier's SPS-served UL flows do not see BSR at all, so
TwoTier holds 10/10. The value-of-QoS-hump story sharpens: the 2.0× band
is now unambiguously TwoTier's, with almost twice the PF contract count.

**Interpretation shift.** SPS's win in Study 2 was previously credited to
"zero PDCCH." It is actually *two* bypasses -- zero PDCCH *and* zero BSR
round-trip. Both matter, and Configured Grants are the only mechanism
that skips both. The PDCCH story alone understated SPS's structural edge.

**Not modeled (still).** BSR quantisation (5/8-bit table entries) and
loss (SR on PUCCH; BSR MAC CE). Each would add small further hits to
dynamic UL scheduling but not to SPS -- so a fuller model would only
widen the SPS win, not narrow it. Reasonable to leave as future work.

Reproduce: `python scripts/scheduler_study.py` (BSR on by default in the
study). Set `ul_bsr_delay_slots=0` on `run()` to disable.

---

## 2026-05-17 — BSR sensitivity sweep: delay linear, loss essentially flat

Added `ul_bsr_loss_rate` to `BufferModel` (per-slot per-UL-flow Bernoulli;
on loss the gNB keeps last-successful `bytes_reported`), with its own
seeded RNG so loss draws don't perturb channel/traffic streams. New
`scripts/bsr_study.py` sweeps delay ∈ {0,2,4,8,16} slots (loss=0) and
loss ∈ {0,5,10,20%} (delay=8) on `factory_robots` @ 2.0× and on
`sensor_dense`.

### Findings

**Delay sweep, factory 2.0×.** PF's min GBR delivery drops smoothly:
66 → 56 → 45 → 32 → 30 % from 0 to 16 slots. PF contract count breaks
between 4 and 8 slots (8/10 → 5/10). PF total slips ~10% (119.3 → 107.0
M). TwoTier is essentially flat: min GBR 81% across every row, 10/10
contracts, total slips only ~5%. Gap grows roughly linearly with delay
-- no cliff, no saturation.

**Loss sweep, factory 2.0× @ delay=8.** Both schedulers barely move
across 0-20% loss. PF min GBR wobbles by 1 point (32 ↔ 33 %); TwoTier
unchanged. Reason: factory UEs carry continuous video, so buffers are
almost always non-empty -- individual BSR losses don't change the
eligibility bit, only slightly restale the sizing. Loss would matter
more on a workload with frequent empty-to-non-empty transitions.

**sensor_dense.** TwoTier holds **30/30 on-time at 5 ms p99 across every
(delay, loss) point**. PF stays broken at 1-2/30. Clean structural
invariance -- SPS uses no BSR, so nothing about BSR touches it.

### What this actually tells us

Adding BSR delay does not change *which scheduler wins* on any scenario
-- but it puts a concrete number on the SPS story: SPS-served flows are
*invariant* to BSR delay and loss, while dynamic PF's floor scales
roughly linearly with delay. In a real deployment where BSR degrades
under stress (imperfect PUCCH, marginal SR reception), the operational
value of Configured Grants is exactly the gap between "PF's minimum
drops a factor of two" and "TwoTier stays put." That is a stronger,
more concrete claim than the previous scheduler-study said.

Loss at *low* delays would probably show more effect (the pipeline
starts near-perfect and losing updates degrades it noticeably) -- we
don't sweep that corner. Kept the study compact.

New tests: `test_buffer_bsr_loss_holds_last_reported_value`,
`test_buffer_bsr_loss_rng_independent_of_seed_variation` (49 pass).
Reproduce: `python scripts/bsr_study.py`.

---

## 2026-05-17 — Modelling-gap audit (post-BSR)

BSR delay+loss was one blind spot; a systematic audit surfaced several
more. Recorded here so they are not lost. Each is annotated with (a) what
we don't model, (b) direction the bias goes (which scheduler is likely
favoured), (c) whether it could plausibly *flip* a study conclusion, and
(d) cost to model. The meta-pattern that produced the BSR fix is worth
naming explicitly: **any place where the scheduler is given perfect,
instant knowledge of state a real gNB learns via a delayed and lossy
report is a candidate blind spot** -- and every remaining candidate on
this list points in the same direction as BSR did (SPS's advantage is
currently *understated* in the sim, not overstated).

### Rank 1 -- DL CQI staleness + quantisation (the BSR twin)

The gNB in real 5G does not know the true DL SNR -- it knows the last
CQI report the UE sent, which is (i) quantised to a 4-bit index (16
levels), (ii) reported on a period of 5-160 ms, (iii) sometimes lost on
PUCCH. Our sim: `channel.get_snr_db(ue)` returns the true instantaneous
SNR to the scheduler -- exactly the sin we fixed on the UL side.

Bias: symmetric across schedulers on the ranking side, but real SPS uses
a *more conservative MCS baseline* than dynamic (see Rank 2) which we
also do not model, so combined they produce an "SPS is more BLER-robust"
axis currently invisible in our sim. Study 3 is the only DL study, so
this is where the effect would show up.

Flip risk: no. Study 3's mechanism is deadline awareness, orthogonal to
MCS accuracy. But the *magnitude* of the TwoTier win might grow.

Cost: cheap. Snapshot per-UE SNR into a delay pipeline exactly like
`bytes_reported`. Quantisation is already implicit in our SNR→MCS
staircase.

**Implementing next together with Rank 2.**

### Rank 2 -- SPS's more conservative MCS

Real SPS grants use a semi-static, more conservative MCS than dynamic
per-grant scheduling, because a mispicked MCS costs *every subsequent
firing*. Our sim: SPS re-picks MCS every slot from the current true SNR,
which is unrealistic (real SPS MCS is fixed at reservation time). The
consequence: with Rank 1 also unfixed, SPS in reality is more robust to
CQI errors than dynamic; our sim shows both equally CQI-blessed.

Bias: SPS favoured (widens SPS win under CQI staleness).
Flip risk: no; direction-consistent with existing findings.
Cost: modest. Fix MCS in `_SPSReservation` at reservation time using
`snr_avg - safety_margin`; drive BLER at firing from that fixed MCS vs
the true SNR at the firing slot.

**Implementing next together with Rank 1.** The two must ship as a pair
because SPS conservative MCS is only meaningful once BLER depends on the
MCS-vs-true-SNR mismatch, which requires a mismatch-BLER curve.

### Rank 3 -- UL k2 grant-to-transmission timing

Real: gNB issues a UL grant in D-slot `n`; the UE transmits at U-slot
`n+k2` (~4 slots at μ=1, ~2 ms). Our sim schedules and transmits in the
same slot, hiding this delay. Compounds with BSR: real dynamic UL total
round-trip is BSR (~4 ms) + k2 (~2 ms) + processing. SPS bypasses k2 too
(the grant is standing).

Bias: SPS favoured (widens SPS win on Study 2, further weakens dynamic
PF on Study 1). Direction consistent with BSR finding.
Flip risk: no.
Cost: modest. Per-UE UL grant-pending queue with `k2` slot delay before
drain.

### Rank 4 -- Proper HARQ retransmissions consuming PRBs

Real HARQ: failed TBs are retransmitted with incremental redundancy;
retransmits consume PRBs on later slots; 8-16 HARQ processes per UE.
Our sim: failed bytes are just dropped (BLER-discounted delivery),
retransmits neither consume PRBs nor eventually succeed.

Bias: uniform across schedulers, so comparative claims unchanged.
Absolute capacity is over-counted (retransmit PRBs not charged). The
Tier-1 LP already sizes capacity as SE × (1 - BLER), so its budget is
roughly right.
Flip risk: no.
Cost: non-trivial (state machine). Worth it only if the flat 10% BLER
assumption starts feeling wrong for real deployment data.

### Rank 5 -- RRC signalling latency for SPS reconfiguration

Real: setting up / modifying an SPS/CG grant is an RRC reconfiguration
costing ~50-100 ms. Our sim assumes Tier-1 can update SPS reservations
every ~1 s at zero signalling cost. **Immaterial for our current
scenarios** because the workloads are static (no UE join/leave, no flow
churn) so Tier-1 solves the same SPS configuration on every re-solve.
Would matter only when the study grows to dynamic membership.

Cost: modest, but not now.

### Rank 6 -- Traffic model realism

Our video: fixed period, fixed I-frame multiplier, no GOP structure, no
rate variability. Sensor telemetry: perfectly periodic, no jitter.
No TCP closed-loop dynamics. Real workloads have all of these.

Bias: mainly shifts Finding 3 (burst/PDB ceiling) numbers, not
direction. The *root cause* of Finding 3 -- the GFBR/PDB contract is
arithmetically inconsistent with a 4× burst -- is a contract-arithmetic
finding independent of traffic-model detail.
Flip risk: no.
Cost: workload-dependent. Trace-driven workloads already listed as
future work.

### Rank 7 -- Absolute-only refinements (no comparative impact)

- **3GPP TBS table extract** vs our fitted SE staircase -- already in
  simulator-design.md open items.
- **MU-MIMO** -- would multiply capacity, unclear which scheduler
  benefits more; probably no directional flip.
- **Real channel model (TDL/CDL)** vs AR(1) on dB-SNR -- affects tail
  statistics.
- **UL power control** -- power-limited cell-edge UEs would *exacerbate*
  Finding 1 in reality.
- **DRX / handover / inter-cell** -- out of scope for a single-cell
  factory.

### Meta-observation

Every remaining candidate that could plausibly move a study conclusion
(Ranks 1, 2, 3) points the same direction BSR did: **SPS's operational
advantage is currently understated in the sim, not overstated.** The
"give the scheduler perfect knowledge of state a real gNB only knows via
delayed and lossy reports" pattern is where to look for the next blind
spot. Ranks 1 and 2 are next.

---

## 2026-05-17 — Gaps 1 and 2 implemented: CQI staleness + SPS conservative MCS

**Gap 1 (DL CQI staleness).** `ChannelModel(cqi_delay_slots=…, cqi_loss_rate=…)`
snapshots true SNR per-UE each slot; `get_reported_snr_db(ue)` returns the
value delayed by `cqi_delay_slots` (with independent Bernoulli loss).
Scheduler-side code (baselines, `TwoTier._update_snr_ewma`,
`_allocate_dynamic`) switched to `get_reported_snr_db`. The driver keeps
`get_snr_db` for delivery-time BLER.

**Coupled to that: MCS-mismatch BLER.** New `bler_for_mcs(threshold,
true_snr)` in `scheduler/link.py` — BLER = target when true SNR is at or
above the picked MCS's threshold, doubles per dB below. `Allocation` grows
a `snr_used_db` field carrying the scheduler's CQI view; the driver
computes BLER from that vs the true SNR (falls back to the legacy path
via a NaN sentinel for test allocations that don't set it). This is what
makes stale-optimistic CQI actually cost something.

**Gap 2 (SPS conservative MCS).** `TwoTier(sps_snr_margin_db=…)` picks
the SPS MCS at reservation time from `snr_avg − margin` and stamps
`snr_ref_db` on each `_SPSReservation`; every firing uses that fixed MCS.
Default 0.0 (see below).

### The empirical finding: on our channel, both are small

`scripts/cqi_study.py` sweeps CQI delay ∈ {0,4,8,16,32} slots and SPS
margin ∈ {0,1,2,3,5} dB on factory @ 2.0×, on both the shipped near-
static channel (coherence 2000 slots) and a short-coherence "mobile"
variant (coherence 30 slots).

- **CQI delay.** Essentially flat everywhere. PF's min GBR moves 32 → 31 %
  across delay 0 → 32 slots on the static channel; on the short-coherence
  mobile channel it moves 38 → 31 % only at 32 slots. TwoTier flat
  (10/10, min 81 %) across the whole sweep on both channels.
- **SPS margin.** One-directional. `margin = 0` gives 10/10 contracts and
  the best total (118.9 M on static, 118.2 M on mobile). Any margin ≥ 2 dB
  crosses the SPS viability floor (`sps_min_scale = 0.75`) → SPS drops to
  dynamic → contracts collapse to 0-2/10.

### Why -- and what it means

Our AR(1) channel with `stationary_std_db = 1.5` produces per-slot SNR
innovations that are small (< 0.7 dB per √8 slots even at coherence 30)
compared to the ~3 dB spacing of MCS thresholds. So even a stale CQI
usually picks the right MCS, and even short-coherence UEs don't feed the
mismatch-BLER penalty enough to matter. The SPS "conservative margin"
only pays off when the BLER-protection benefit exceeds the reservation-
size cost -- which requires the true SNR to routinely dip below the
picked MCS's threshold. On our channel model, it doesn't.

**Physical intuition matches:** SPS's semi-static MCS is a mobility hedge.
A static factory doesn't need it. `sps_snr_margin_db` should be sized
from the deployment's channel-volatility budget: 0 dB for a warehouse /
fixed AGVs, larger and swept-experimentally as mobility rises.

Default now: `sps_snr_margin_db = 0.0`. Non-zero margin is opt-in.

### Effect on the main study conclusions

**None of Study 1-3's conclusions change.** Small numeric shifts:
- Study 1 @ 2.0x TwoTier total: 120.2 M → 118.9 M (SPS now uses smoothed
  MCS instead of per-slot true SNR -- small BLER variance around threshold
  boundaries). Contract count 10/10 unchanged. Same for mean/min GBR.
- Study 2 PF on-time: 1/30 → 2/30 (small noise). TwoTier 30/30 unchanged.
- Study 3 TwoTier ctrl worst p99: 10.0 → 10.5 ms; bulk DL 14.2 → 15.5 M.
- Factory per-flow @ 1.0x: ue4 (16 dB) improved 0 → 22 %; ue2/ue9
  slightly regressed. Mean GBR 67 → 62 %. Story preserved (mixed-flow
  UEs protected; cell-edge starvation persists at ue7).

### What this rules out for future modelling

The "SPS's advantage is understated" hypothesis from the gap audit (i.e.
CQI staleness + SPS conservative MCS should widen the SPS win) is
**false on our channel model** -- the channel is too well-behaved for
either effect to matter. It would matter on:
- Faster fading (higher `stationary_std_db` and/or shorter coherence).
- A more punishing BLER curve (real 5G BLER above threshold is more
  forgiving than "doubles per dB"; real BLER *below* threshold might be
  even steeper).
- Larger SNR quantisation error (real CQI has ~2 dB granularity vs our
  finer staircase).

None of these are worth implementing unless a scenario surfaces them.

Reproduce: `python scripts/cqi_study.py`. Tests: 53 pass -- new
`test_channel_cqi_delay_lags_true_snr`,
`test_channel_cqi_loss_holds_last_reported_value`,
`test_bler_for_mcs_matched_vs_mismatched`,
`test_two_tier_sps_uses_conservative_mcs`.

**Axis housekeeping (same commit).** Study 1's table used to be labelled
"Capacity × shipped" (1.0x = as-shipped, 3.0x = light load). §8's
interpretation used "Nx overload" (higher = worse). These were inverse
and confusing to a cold reader. Relabelled Study 1 to "Load × shipped"
so both sections increase-with-badness; sim still varies capacity
(equivalent knob). §7.5, §7.6, §8.1, §11, and the sweep scripts'
display headings updated for consistency.

---

## 2026-08-06 — Finding 1 root cause: the slack penalty, not the log utility

Finding 1 (cell-edge starvation) has been carried as open since 05-13, with
the mechanism recorded as "Tier-1's log-utility LP is trading cell-edge GBR
for system-wide log utility — classic pathology of weighted-log objectives."
**That attribution is wrong, and it is why two rounds of fixes failed.**
Measured on `factory_robots` at 1.0× load, with the default penalty:

| objective term | value |
|---|---|
| utility `Σ w·log(r+ε)` | 709 |
| penalty `Σ p·s` at `p = 1e3` | 2.39e10 |
| **ratio** | **3.4e7** |

The log utility contributes nothing but a tie-break. Tier-1 is, to seven
significant figures, solving

```
minimize  Σ_i (GFBR_i − r_i)      subject to   Σ_i r_i / SE_i  ≤  C
```

— minimise total shortfall *bits* under a PRB budget. That is a **fractional
knapsack**, and its optimum is the greedy one: buy rate where it is cheapest
per PRB, i.e. in descending spectral efficiency. The solved targets are
exactly that staircase:

| SE (bits/PRB-sym) | flows | target |
|---|---|---|
| 48.6 | ue1 (22 dB), ue5 (24 dB) | 100% |
| 37.8 | ue3, ue6, ue8, ue10 (19–21 dB) | 100% |
| 29.7 | ue2 (18 dB), ue4 (16 dB), ue9 (17 dB) | 53–56% |
| 21.6 | ue7 (14 dB) | **0%** |

One fully-served head, exactly one partially-served boundary tier, a zeroed
tail — a textbook LP basic solution. Note it orders by **SE, not SNR**: ue2
(18 dB) and ue4 (16 dB) land on the same MCS step and get the identical 56%.

**Decisive control — a penalty sweep over six decades.** Targets are
*identical* for `p ∈ {1, 10, 1e3, 1e6}`. The solution is fixed by the
knapsack structure, not by the penalty magnitude. And running the other way,
at `p = 1e-6` (utility alone), the allocation is 44–56% *rising* as SE falls
— ue7, the starved flow, gets the **highest** ratio of all. The log utility
is the term that protects cell-edge flows; the slack penalty is the term
that starves them. The 05-13 note had it backwards.

(Credit where due: `design-docs/scheduler-design.md`'s adaptive-penalty
section already stated the shortfall-minimisation argument correctly. It was
NOTES.md and scheduler-study.md §8.5 that mis-attributed it to the `log`.)

### Why every previous fix was structurally doomed

Once the penalty dominates, the program is effectively an **LP**, so its
optimum sits at a **vertex** of the feasible polytope: bang-bang, flows
served in full or abandoned, at most one partial per tier. Reweighting `p`
moves *which* vertex, never the fact that there is one:

- **`k < 0` (SE tilt)** sets `p_i ∝ 1/SE_i`, equalising the knapsack's value
  density `p_i·SE_i` — so the greedy order becomes arbitrary and the victim
  set merely permutes. Exactly the observed "only relocates starvation".
- **Adaptive dual ascent** escalates `p_i` on whoever is missing, promoting
  that flow up the greedy order and demoting another. Still a vertex, hence
  "equalises shortfall but meets 0/10 contracts".

No choice of a *linear* penalty vector removes the vertex. Only changing the
**feasible region** does — i.e. a constraint, not a weight.

---

## 2026-08-06 — Finding 1 fix: a max-min GBR stage ahead of the utility solve

Implemented the fix the design docs committed to. Two stages, both convex,
both in `scheduler/tier1.py`:

**Stage A — `solve_maxmin_gbr_level`.** `maximize t` s.t. `r_i ≥ t·contract_i`
for every GBR flow, plus capacity, demand caps and (soft) slice floors.
Returns `t*`: the largest fraction of its contracted floor that *every* GBR
flow can hold simultaneously. `contract_i = min(GFBR_i, demand_i)` — the
demand cap matters, or an under-offered GBR flow pins `t*` at its own
unreachable ratio and drags the whole set down.

**Stage B — `solve_tier1(gbr_floor_bps=…)`.** The existing solve, with
`gbr_maxmin_floors(…, t*, scale)` added as *hard* lower bounds. The soft
GFBR constraint is kept alongside, so the utility term still has an
incentive to close the remaining gap wherever that is cheap. Stage B is
feasible by construction (stage A's solution satisfies it).

Wired as `TwoTier(gbr_maxmin=True, gbr_maxmin_scale=1.0)`; **off by
default**, so every published study number is unchanged. `scale` dials how
much of the achievable floor to claim: 0.0 is the single-stage behaviour,
1.0 the full guarantee.

### A conditioning bug found on the way — worth generalising

The first cut posed stage A in raw bps: `t` of order 1, rate variables of
order 1e7. The solver returned `optimal` on a level that was both wrong and
**non-monotone in capacity** — `t*` peaked at 0.87 around 2× and then *fell*
to 0.84 at 4×, never reaching 1.0 however much spectrum it was given. Since
more capacity can never shrink a max-min level, that is a pure numerical
artifact. Rebuilt in normalised units (rates as a fraction of the largest
contract, capacity usage as a fraction of each direction's own budget, every
coefficient O(1)), `t*` is now exactly linear in PRB count and saturates
cleanly at 1.0. Regression guard:
`test_maxmin_level_monotone_and_saturating_in_capacity`.

**The general lesson, and an open item.** Stage B has the *same* smell and
worse: utility ≈ 709 against a penalty term ≈ 2.4e10, a 1e8 dynamic range,
and `problem.solve()` does emit "Solution may be inaccurate" on some
scenarios. Its answer is structurally sound — invariant across six decades
of `p`, and it saturates UL at exactly 100.0% — so this is not currently
corrupting results. But it has never been checked in normalised units, and
after the BSR/CQI "perfect knowledge" meta-pattern this is worth naming as a
second one: **any convex program mixing O(1) and O(1e7) magnitudes is a
candidate for a silently inaccurate `optimal`.** Rescaling stage B is
unfinished business.

### Results — `factory_robots`, contract metrics, BSR 8 / CQI 8 slots

Reproduce with `python scripts/maxmin_study.py`.

| load | scheduler | total | GBR met | mean GBR | **min GBR** | ue4 (16 dB) | ue7 (14 dB) |
|---|---|---|---|---|---|---|---|
| 1.00× | TwoTier | 74.2M | 0/10 | 53% | **0%** | 16% | 0% |
| 1.00× | +adaptive | 68.7M | 0/10 | 44% | 34% | 47% | 36% |
| 1.00× | **+maxmin** | 66.7M | 0/10 | 44% | **40%** | 40% | 46% |
| 0.67× | TwoTier | 95.8M | 0/10 | 68% | 43% | 63% | 43% |
| 0.67× | +adaptive | 94.6M | 0/10 | 65% | 33% | 33% | 68% |
| 0.67× | **+maxmin** | 94.1M | 0/10 | 65% | **60%** | 61% | 69% |
| 0.50× | TwoTier / +maxmin | 120.1M | 10/10 | 82% | 78% | 78% | 84% |
| 0.33× | TwoTier / +maxmin | 125.4M | 10/10 | 85% | 83% | 83% | 86% |

(Re-measured after the 2026-08-06 solve_tier1 rescale below; the numbers
this entry originally carried came from the pre-rescale solver.)

Three things to read off it:

1. **It fixes the thing it was built to fix.** min GBR 0% → 40% at 1.00×,
   43% → 60% at 0.67×. ue7 goes 0% → 46%. Per-flow at 1.00× the whole GBR
   set collapses into a **40–48% band**, against the single-stage spread of
   0–80% — max-min doing exactly what it says.
2. **It costs nothing where nothing is wrong.** At 0.50× and 0.33×, `t* = 1.00`,
   the floor is non-binding, and results are identical to default TwoTier.
   The knob is self-disabling in the regime where the single-stage solve is
   already right — which the adaptive penalty never managed.
3. **It dominates the adaptive penalty.** Better min GBR at both loads
   (40 vs 34, 60 vs 33), same mean. And note the 0.67× row: the adaptive
   penalty is *worse than doing nothing* there (min 43% → 33%), while
   max-min improves it.

DL Delay flows stay 10/10 on time in every row — the hard UL GBR floor does
not crowd out the deadline class. Studies 2 and 3 are structurally untouched:
neither `sensor_dense` nor `latency_bound` has a GBR flow, so stage A returns
`t* = 1` over an empty set and imposes no floor (test:
`test_maxmin_level_is_one_without_gbr_flows`).

### The cost curve, and choosing `scale`

`gbr_maxmin_scale` at 1.00× load (`t* = 0.59`):

| scale | total | mean GBR | min GBR |
|---|---|---|---|
| 0.00 | 74.2M | 53% | 0% |
| 0.25 | 73.7M | 51% | 8% |
| 0.50 | 72.7M | 50% | 17% |
| 0.75 | 71.9M | 48% | 28% |
| 1.00 | 66.7M | 44% | 40% |

Monotone and smooth — the first 28 points of floor cost 3.1% of throughput,
the last 12 cost another 7%. At 0.50× load the curve is flat (floor
non-binding at any scale). A deployment that has to name one number: `scale`
is "what fraction of the worst-case guarantee is worth buying", and the knee
is around 0.75.

### What it does *not* fix — and why that is expected

**The GBR-contract count is unchanged at every load** (0/10 at 1.00× and
0.67×, 10/10 at 0.50× and 0.33×). Max-min addresses *fairness of shortfall*;
it cannot address the fact that a GBR contract is a **step function**.
Parking ten flows at a uniform 59% of GFBR clears zero 95%-contracts, just as
equalising shortfall did (§8.4). This is the same wall the adaptive penalty
hit, and it is not a scheduler problem: at 0.67× load PF meets **4/10**
contracts to TwoTier's 0/10 precisely *because* PF concentrates — it fully
serves a few and abandons the rest, which is the knapsack answer a
contract-count metric rewards.

So the two objectives are genuinely in tension and Tier-1 can serve one at a
time:
- **max-min** (`gbr_maxmin=True`) — maximise the worst-served flow. Right
  when partial delivery has value (video that degrades gracefully, telemetry).
- **contract count** — maximise flows fully meeting GFBR, accepting that the
  rest get nothing. Right when partial delivery is worthless (a control loop
  at 59% of its rate is a failed control loop).

The second is a knapsack over contracts — i.e. an admission-control /
contract-selection decision, deliberately **out of scope** for the scheduler
(owner's call, 2026-08-06). Worth recording that Tier-1 now hands that gate a
clean signal for free: `t* < 1` *is* the infeasibility detector, and `t*`
quantifies how far off the GBR set is, before any flow has been starved to
find out.

**Finding 1 status: closed as a scheduler issue.** The mechanism is
understood, the fix is implemented, measured, and self-disabling where
unneeded. What remains under it is the contract-selection question above,
which is not Tier-1's to answer.

### Open: should max-min be the default?

Left as `False` so every number in the study docs still reproduces. The case
for flipping it: it is free at moderate load and only binds where the
single-stage solve is doing something indefensible. The case against: it
costs 10% throughput at deep overload, which is exactly the regime the study
already says to solve with capacity planning rather than scheduling. Not
decided.

---

## 2026-08-06 — solve_tier1 rescaled: the penalty was hiding a wrong answer

Closing the open item flagged in the max-min entry above. It was logged as
a conditioning smell; it turned out to be a live defect.

### The symptom

On `overload` (scenario 2, three flows) the shipped `solve_tier1` returned
`optimal_inaccurate`, and **CLARABEL and SCS disagreed with each other**:

| | PF flow | GBR flow | Delay flow |
|---|---|---|---|
| CLARABEL | 0.847 M | 4.000 M | 0.461 M |
| SCS | 0.233 M | 4.000 M | 0.202 M |
| **analytic optimum** | **0.667 M** | **4.000 M** | **0.640 M** |

The problem is small enough to solve by hand: pin the GBR flow at its 4 Mbps
floor, then split the residual 1.307 Mbps between the PF flow (`w=1`) and the
Delay flow (`w=5`) under `log`. The Delay flow should sit at its 0.64 Mbps
demand cap with the PF flow taking the rest. Both solvers missed it, and the
shipped answer **under-served the Delay class by 28%** — the highest-weighted
class in the model, in the scenario used for the SPS and adaptive-penalty
regression tests.

### Why rescaling alone could not fix it

The first instinct — normalise like stage A — is not enough, and the reason
is worth writing down. Rescaling variables cannot change the *ratio* between
two objective terms; that ratio is a property of the model. Here it is ~1e7
(utility 709, penalty 2.4e10), and it is there on purpose: `p = 1e3` was
chosen so the GBR floor would be "effectively hard whenever feasible."

Measured directly: normalising the variables and dividing the objective by
the rate scale produced a clean `optimal` status — and a *still-wrong*
answer, because the utility term had been pushed to ~1e-6 and became
invisible to the solver. That is the worst outcome available: a confident
wrong answer. **Status is not accuracy.**

### The fix: state the lexicographic order instead of encoding it as a weight

A penalty 1e7 larger than the utility is not a weighting, it is a
lexicographic order written as a magnitude. So `solve_tier1` now says so:

```
phase 1:  minimize  Σ p_i s_i + p_slice Σ ss_j
phase 2:  maximize  Σ w_c log(r_i + ε)
          s.t.      the phase-1 penalty stays at its optimum
```

Each phase is well conditioned alone, and both are posed in normalised
units (rates as multiples of `rate_scale`, capacity usage as a fraction of
each direction's own budget). Phase 2 is feasible by construction; if it
fails anyway the code keeps phase 1's answer, which already honours every
floor it could — strictly better than the old fall-back to raw demand.

Result on the case above: **both solvers return `optimal` and land within
100 bps of the analytic optimum**, agreeing with each other. Across the six
shipped scenarios the solver warning is gone from five; `factory` still
reports `optimal_inaccurate` in phase 2, but there CLARABEL and SCS now
agree to **18 kbps** on rates of 4–14 Mbps (0.4%), against 440 kbps of
mutual disagreement before. Sweeping the log's `ε` over four decades moves
the answer by <0.1 kbps, so `ε` is not the residual — 24 simultaneous log
terms against a tight budget constraint simply is a harder problem than
CLARABEL's default tolerance likes. Left as is: 0.4% is an order of
magnitude below the ±2 pt per-window scatter this project already documents.

**Side benefit: one less magic number.** `gbr_slack_penalty` now means only
what it always should have — the *relative* worth of closing one flow's GBR
gap against another's, which is all the adaptive dual-ascent update and the
SE tilt `k` ever read it for. Its absolute magnitude no longer holds the
model together.

### What moved, and what did not

Re-ran every study. **No qualitative conclusion changes anywhere.** All
contract counts in Studies 1–3 are identical; Study 2 is bit-identical
(no GBR flows → phase 1's optimum is 0 → phase 2 is a pure utility solve).
Absolute figures shift by ~1–3 points, i.e. within the documented
per-window scatter. Two documented claims did need softening:

- **BSR delay (§7.5).** "TwoTier is essentially invariant: min 81%, 10/10
  contracts at every delay" becomes 80→77% min and **10/10 → 8/10** over
  0–16 slots. The SPS bypass is not total immunity at the contract level.
  The comparative claim is untouched and still large: PF goes 8/10 → 5/10
  and loses 10% of cell throughput, TwoTier loses ~1%.
- **SPS margin (§7.6).** "Any margin ≥ 2 dB collapses contracts to 0–2/10"
  becomes a graded 10/10 → 7/10 → 3/10 → 0/10 over 0/1/2/3 dB. Direction
  and design implication unchanged — margin is a mobility hedge this
  channel does not need — but the first dB already costs.

The per-flow breakdown (§7.4) sharpened in a way that *supports* the
Finding 1 story: TwoTier now zeroes **both** cell-edge flows (ue4 and ue7 at
exactly 0%), where the old solve showed ue4 at a smeared 22%. Two clean
zeros is the fractional-knapsack vertex; the smear was solver error.

**Reading older entries in this file.** Every absolute number recorded
before today came from the pre-rescale solver. The comparative findings all
survive re-measurement, but treat pre-2026-08-06 absolute figures as
carrying an unknown few-percent solver error on top of the ±2 pt warm-up
and channel scatter already documented. The dated entries above are left as
written — they are what was measured at the time.

### The generalisable bit

The BSR/CQI work named one meta-pattern ("the scheduler is given perfect
knowledge of state a real gNB learns late"). This is a second:
**a term many orders of magnitude larger than its neighbours is not a
weighting, it is a constraint or an ordering that has not been written
down.** Look for those; each one is both a modelling smell and a numerical
one. `slice_slack_penalty` (still `1e3`, same shape as the old GBR penalty)
is the remaining candidate in this file — it is now folded into phase 1, so
it is no longer competing with the utility, but its *relative* weight
against the GBR penalty has never been studied.

---

## 2026-08-06 — slice vs GBR penalty: the ratio was a function of the channel

Third and last item on today's list, flagged at the end of the rescale
entry. Same family as lesson 6 above, in a different disguise: not an
oversized weight this time, but a weight compared against something in
**different units**.

### The defect

Phase 1 minimises `Σ p_gbr,i · s_i + p_slice · Σ ss_j`. But `s_i` is a GBR
shortfall in **bps** and `ss_j` is a slice shortfall in **PRB-symbols/s**.
Those are not the same thing, and the conversion between them is the
spectral efficiency — so the *relative priority of a slice floor against a
GBR floor was a function of the UEs' SNR.*

Measured on a designed conflict (slice 1 holds a GBR flow wanting 80% of DL;
slice 2 has a 50% DL floor and unbounded demand — only one can be met),
bisecting for the `p_slice` at which the winner flips, with `p_gbr = 1e3`:

| SNR | SE (bits/PRB-sym) | crossover `p_slice` | `p_gbr × SE` | ratio |
|---|---|---|---|---|
| 10 dB | 16.2 | 1.620e4 | 1.620e4 | 1.00 |
| 14 dB | 21.6 | 2.160e4 | 2.160e4 | 1.00 |
| 20 dB | 37.8 | 3.780e4 | 3.780e4 | 1.00 |
| 25 dB | 59.4 | 5.940e4 | 5.940e4 | 1.00 |
| 30 dB | 70.2 | 7.020e4 | 7.020e4 | 1.00 |

Exact, to two decimal places, at every point. The consequences:

- **A 4.3× policy swing across the SNR range these scenarios already use.**
  Same deployment, same contracts, same config file — move a UE from the
  cell edge to the cell centre and the operator's slice guarantee changes
  rank against the GBR guarantee.
- **With the shipped defaults (`p_gbr = p_slice = 1e3`) the GBR floor
  outranked the slice floor by 16–70×** — not as a policy decision, but as
  an artifact of the units. Nobody chose that.

### Fix

Convert the slice slack to bps before weighing it: multiply by the slice's
**demand-weighted spectral efficiency** over its flows in that direction —
the rate the slice would actually have realised on the PRB-symbols it was
denied. Both penalties are then quoted in the same currency, "cost per bps
of denied rate", and the crossover lands at exactly `p_slice = p_gbr` for
every SNR (re-measured: 1.000e3 at all five points).

The GBR side is deliberately left in raw bps. Normalising it by GFBR would
have been the tidier-looking move and is *wrong*: it changes the relative
weighting **among** GBR flows, which is precisely the fractional-knapsack
ordering behind Finding 1. This fix touches only the slice-vs-GBR
comparison, nothing else.

`slice_slack_penalty` now has a stable meaning: at the default `1e3`, equal
to `gbr_penalty_init`, a bit denied to a slice floor costs the same as a bit
denied to a GBR floor. Whether tenant-level slice guarantees *should* rank
equal with per-flow GBR guarantees is a genuine policy question and is now
an explicit, single-number choice rather than an emergent property of the
link budget. Default left at parity.

### Blast radius: none

No scenario YAML sets `slice_shares`, and the two existing slice tests carry
only PF flows — with no GBR flow there is no GBR slack, and phase 1 is then
minimising the single remaining term, whose optimum is independent of its
own coefficient. Every study number is byte-identical to the pre-change run.
This was latent, caught before slicing was used in anger.

New guard: `test_slice_vs_gbr_priority_is_channel_independent`, which asserts
the tie-break goes the same way an order of magnitude either side of the
crossover at 10, 20 and 30 dB. Tests 62 → 63.

### Why the two-phase form made this findable

Worth recording the sequence. Under the old single-objective form, both
penalties were mainly busy overpowering the log utility, and their ratio to
*each other* was buried. Once phase 1 became "minimise shortfall" on its
own, the absolute magnitudes stopped mattering entirely and the ratio became
the only thing those knobs control — at which point a ratio that silently
tracked the channel was the obvious next question to ask. Fixing the
conditioning did not just make the answer accurate; it made the next bug
visible.

---

## 2026-08-06 — gbr_maxmin is now the default

Owner's decision, taken with the tradeoff on the table. `TwoTier` now ships
`gbr_maxmin=True, gbr_maxmin_scale=1.0`.

### The case that decided it

The stage is **self-disabling**. Whenever the GBR set is jointly feasible
`t* = 1`, the floor binds nothing, and the run is bit-identical to leaving
it off. So the default is free in every regime except genuine GBR overload —
verified as a test, not an argument
(`test_two_tier_maxmin_default_is_free_when_gbr_set_is_feasible`, byte-equal
delivery on `smoke`). Confirmed at scale too: the BSR study is byte-identical
and the CQI study moves by tenths of a Mbps, because both run at 0.50× load
where `t* = 1`.

Where it does bind, it is the difference between a fleet degraded evenly and
a fleet with two robots switched off. That is the judgement.

### What the default now looks like — `factory_robots` per-flow, 1.0× load

| flow | SNR | RR | PF | Gradient | **TwoTier** |
|---|---|---|---|---|---|
| ue1 | 22 dB | 77% | 91% | 77% | 56% |
| ue2 | 18 dB | 57% | 68% | 66% | 54% |
| ue3 | 20 dB | 63% | 74% | 71% | 53% |
| ue4 | 16 dB | 51% | 62% | 64% | **50%** |
| ue5 | 24 dB | 56% | 67% | 67% | 56% |
| ue6 | 19 dB | 37% | 46% | 55% | 55% |
| ue7 | 14 dB | 23% | 28% | 41% | **53%** |
| ue8 | 21 dB | 3% | 3% | 3% | 53% |
| ue9 | 17 dB | 3% | 3% | 3% | 50% |
| ue10 | 20 dB | 89% | 0% | 0% | 53% |
| **mean** | | 46% | 44% | 45% | **53%** |

**Every GBR flow between 50% and 56% — a 6-point spread over a 10 dB SNR
range**, against PF's 0–91%. That column is the clearest single picture of
what the two-tier design does that PF cannot.

### The honest cost, stated where it will be read

**At 1.0× load PF now carries more total throughput than TwoTier: 69.3 M vs
66.7 M.** That reverses a claim the study made at every load point until
today. It is the max-min trade taken deliberately — −4% aggregate for a
worst-served flow at 40% of contract instead of 0% — but it is a real
reversal and §7.1 now says so in bold rather than leaving a reader to notice.

Load-by-load, default vs the single-stage form it replaces:

| load | metric | −maxmin | **default** |
|---|---|---|---|
| 1.00× | total / mean / min GBR | 74.2 M / 53% / **0%** | 66.7 M / 44% / **40%** |
| 0.67× | total / mean / min GBR | 95.8 M / 68% / 43% | 94.1 M / 65% / **60%** |
| 0.50× | — | identical | identical |
| 0.33× | — | identical | identical |

GBR contract counts are unchanged at every load (0/10, 0/10, 10/10, 10/10),
as are Studies 2 and 3 — neither has a GBR flow. The value-of-QoS hump still
peaks at 0.50× load, 10/10 contracts against PF's 5/10; that headline is
untouched.

### Consequences for the harness

- `scripts/scheduler_study.py` Study 1 now runs four rows: PF, TwoTier
  (default), TwoTier−maxmin, and TwoTier−maxmin+adaptive. The adaptive row
  had to be re-based on the single-stage form or it became a duplicate of
  the default — max-min dominates it, so with both on the rows were
  identical. §8.4's negative result needs the like-for-like baseline.
- Three tests had to pin `gbr_maxmin=False` because they measure mechanisms
  the floor would otherwise mask — notably
  `test_two_tier_adaptive_penalty_helps_poor_snr_gbr`, which is precisely a
  test that the adaptive penalty protects the poor-SNR flow. With the floor
  on, it protects it first and the test measures nothing.
- `test_two_tier_maxmin_disabled_by_default` became
  `test_two_tier_maxmin_enabled_by_default`, so the default cannot be
  flipped back silently.

Tests 63 → 64.

### Still not settled

`gbr_maxmin_scale` stays at 1.0 — full claim on the achievable floor. The
scale sweep at 1.0× load (§7.7) shows the curve is smooth, with the knee
around 0.75 (min GBR 28% for 3.1% of throughput, against 40% for 10%). A
deployment that wants the throughput back has a one-number dial, and 0.75 is
the defensible alternative if the −4% ever becomes contentious.

---
