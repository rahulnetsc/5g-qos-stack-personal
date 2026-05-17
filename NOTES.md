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
