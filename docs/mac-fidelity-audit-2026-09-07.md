# MAC-layer fidelity audit — what a real 5G RAN does that this simulator does not

**Part 1 of four. Started 2026-09-07, appended from the first finding onward.**
Build nothing. Every item gets an entry; an item with no entry is a gap in the
audit, not evidence the item is fine.

**Verdict vocabulary:** `present-and-faithful` / `present-but-approximate` /
`absent-and-filtered-out` / `absent-and-admitted`.

**THE FILTER.** This simulator models the MAC scheduler. PHY is abstracted
deliberately; RLC/PDCP/SDAP are absent by design. An absence is a finding ONLY
if a guarantee's clause depends on it to be answered correctly. `has_srb`
passes (a dead top ranking tier changes every arm's ordering); RLC
segmentation does not.

**Reference:** `/home/smart/projects/Oai_Ran_QoS_Supported_MultiDRB`, branches
`twotier` (MAC) and `rrc-qos-handling-v0.1.1` (reservation).

**Prior pass:** `docs/system-audit-2026-09-07.md` worked four items of this
list — random access (P1-1), DRX (P1-2), reservation's dead comparator tiers
(P1-3), and the measured per-term decisive counts across 16.9 M adjacencies
(P1-4). Those are not repeated; they are cited and extended.

---

## Log

### M-1 — THE RANKING COMPARATORS, TIER BY TIER, PER ARM — and the measured evidence base is **UPLINK ONLY** (ADMITTED; sharpens P1-4)

P1-4 measured decisive-term counts across 16.9 M adjacencies and reported them
as **one pooled table**. Two things it did not separate, both material.

**(a) Per arm, from the same artefact** (`sweeps/rerun-2026-09-06/traces.json`,
120 rows, cells `attach` / `attach_control` / `g5_residual` / `g7`):

| arm | adjacencies | decisive terms |
|---|---|---|
| **PF** | 6,022,026 | `-metric` 99.9903 % · TIED 0.0097 % |
| **Reservation** | 5,598,120 | `-coef` 66.34 % · `pdb_ms` 21.77 % · `has_gbr` 11.53 % · TIED 0.357 % · **`has_srb` 0** |
| **TwoTier** | 5,299,905 | `-coef` 96.64 % · TIED **3.359 %** · `floor_fire` 27 · **`sched_inactive` 0** · **`-floor_sil` 0** |

`sched_inactive` and `-floor_sil` are **TwoTier UL** terms, not Reservation's —
P1-4's pooled table does not say so and reads as if they were reservation's.

**(b) The tally is constructed `LossPointTally("UL")`**
(`scripts/trace_cells.py:130`) and `__call__` returns early on
`snap.direction != self.direction` (`scheduler/rank_trace.py:202-203`). **So
every number in P1-4 and in (a) is uplink.** The downlink comparators have
**never been measured at all**:

| arm | DL comparator tiers (code) | measured? |
|---|---|---|
| PF | single scalar `-metric` | no |
| Reservation | `has_srb` → `has_gbr` → `pdb_ms` → `-coef` (`_dl_rank_key`, `reservation.py:1411-1433`) | **no** |
| TwoTier | `has_gbr` → `pdb_ms` → `-coef` (`_dl_rank_key`, `two_tier.py:1489-1501`) | **no** |

TwoTier's pooled totals contain **no `has_gbr` and no `pdb_ms` rows at all** —
they are DL-only terms for that arm, and the DL stream was discarded. So the
claim "both QoS arms are effectively ranking on `coef → pdb_ms → has_gbr`" is
supported for Reservation UL and **unsupported for TwoTier**, whose UL
comparator is `-coef` alone (96.6 %) with a 3.4 % tie rate and whose DL
comparator is unobserved.

**(c) A structural point P1-3 states as "inert" is stronger than that:
Reservation's `liveness` and `sched_inactive` tiers are not in the ported key
at all.** Ground truth is 5 UL tiers (`gNB_scheduler_ulsch.c:2010-2039`) and
4 DL (`gNB_scheduler_dlsch.c:692-715`); `_ul_rank_key` returns a **4-tuple**
and `_dl_rank_key` a **4-tuple**, both omitting liveness/TA outright. They
cannot be traced because there is nothing to trace. Verdict:
**present-but-approximate** on structure, **absent-and-admitted** on those two
tiers.

**Filter — ADMITTED.** The DL blind spot is a finding on its own terms: G1's
clause is about a **downlink** command (P2-2) and no evidence exists about
which tier orders downlink at all.

**Inert because of it:** TwoTier's UL Tier 1 (`sched_inactive`) is hardcoded
`False` (`two_tier.py` docstring) — dead by construction, matching P1-3's
shape; Tier 1.5 (`floor_fire`) fires 27 times in 5.3 M.

### M-2 — SCHEDULING REQUEST: the state machine is faithful; **the SR→grant→PUSCH latency is zero** (ADMITTED)

`sim/ul_access.py` is a genuine port: recurring PUCCH occasion
(`trigger_periodic_scheduling_request`), `sr-ProhibitTimer`, `sr-TransMax`
counter with RACH fallback (`nr_ue_get_SR`, `nr_ue_procedures.c:2613-2661`),
gNB-side flag clear on grant (`gNB_scheduler_ulsch.c:2694`). Retransmission on
every occasion, not one-shot. **present-and-faithful as a state machine.**

**What is absent is the delay.** In `sim/driver.py:640-770`, one slot runs:
`ul_access.tick()` → `bsr.broadcast()` → `scheduler.allocate()` → the UE fills
and transmits the TB, all at `slot_index`. So:

| leg | real NR | here |
|---|---|---|
| SR occasion → gNB decodes → DCI | ~1 slot + processing | **0** |
| UL grant (DCI) → PUSCH | **k2 slots** (TDA row, 1–4) | **0** |
| PUSCH → gNB decode/ACK | k2-ish | 0 (outcome drawn in-slot) |

`k2_slots` **exists** (`driver.py:34`, default 2) but is used **only** as the
retransmission gap: `harq_rtt_ul = k2_slots` (`driver.py:188`). The *first*
transmission of every UL TB is same-slot. At numerology 1 (0.5 ms slots) that
is ~1–2 ms of UL access latency missing from every uplink number, per grant,
plus the SR decode leg.

**Filter — ADMITTED, small-magnitude, one-directional (optimistic).** Against
G1's 95 ms and G2's 100 ms bounds, 1–2 ms is ~2 % — it cannot flip those
verdicts. It matters for two things that are *at* that scale: (i) the WP4
low-load UL latency calibration target, which is a round-trip time; (ii) the
crumb-fraction gap, since a longer SR→grant round trip lets more backlog
accumulate before the grant is sized, which pushes crumb fraction the *wrong*
way relative to hardware's 48–52 %.

**Four knobs are unreachable from `run()`** (already in CLAUDE.md's dead-
mechanism table, re-confirmed here): `sr_prohibit_ms`, `sr_trans_max`,
`rach_recovery_ms`, `sr_report_floor_bytes` are constructed at defaults
(`driver.py:138-143` passes only `sr_period_slots`/`sr_offset_slots`). At the
deployed `sr_ProhibitTimer 0` the prohibit path is a no-op by design, so the
first is harmless; `sr_report_floor_bytes=150` is a **first-class determinant
of grant size at cold start** and cannot be swept.

### M-3 — BUFFER STATUS REPORTING: quantisation and triggers faithful; **the padding trigger and both truncated formats are OFF in every published run** (ADMITTED, then filtered)

**Present-and-faithful.** `sim/bsr.py` transcribes TS 38.321 Tables 6.1.3.1-1/-2
from `oai-branches/two-tier/nr_mac_common.c` and re-checks them byte-for-byte
every test run; short-BSR aliasing (`estimate_ul_buffer_short_bsr`), the
per-LCG array's freeze-between-BSRs, and the three trigger kinds
(regular on previously-empty-LCG arrival, periodic 5 ms, retx 80 ms) are
ported with the hardware timer values.

**Absent in practice: the Padding BSR.** `truncated_bsr` defaults to `"off"`
(`sim/driver.py:37`) and the only caller that sets it is
`scripts/bsr_desync_study.py:159`. Grep across `scripts/scheduler_study.py`,
the campaign runners and `sim/scenarios/` finds no other setter. So in **every
published result**:
- the **padding trigger never fires** — `on_ul_grant` returns early unless
  `st.pending` (`bsr.py:406-416`);
- **Short-Truncated and Long-Truncated BSR are unreachable**;
- the "restart periodicBSR-Timer except when all generated BSRs are
  truncated" branch (`bsr.py:457-460`) is a constant.

**Filter — this one is legitimately filtered out, and it is filtered out by a
MEASUREMENT rather than by judgement.** `scripts/tbs_counterfactual.py`
(CLAUDE.md, WP9 §20.1) found **13,214 of 13,214 UL grants at padding 0** at the
load in question, and the truncation window is 2–5 bytes wide against a
gNB BSR error of 12,194–13,387 bytes. Turning the flag on would change
nothing at load. **Recorded as absent-and-filtered-out, with the caveat that
the filtering evidence is one load point.**

**Present-but-approximate, and not previously recorded: the BSR MAC CE costs
no bytes.** `sim/ue_lcp.py::fill` is handed the **whole** `bytes_capacity` and
splits it entirely across data flows. Real MAC puts the BSR CE (and every
other CE except a padding BSR) ahead of every logical channel
(TS 38.321 §5.4.3.1.3), and each SDU carries a subheader. So every UL TB here
delivers 2–10 bytes more user data than the real one would. **Filter:
absent-and-filtered-out** — at a 1,000-byte TB this is <1 %, below the
`overhead_factor` haircut already applied, and no clause resolves at that
scale.

### M-4 — LOGICAL CHANNEL PRIORITISATION: the algorithm is faithful; **both of its configured inputs disagree with the deployed gNB** (ADMITTED)

`sim/ue_lcp.py` is a correct two-round LCP: round 1 priority-ordered and
bucket-bounded, round 2 strict-priority over the remainder, buckets keyed
per logical channel, `capacity_bits = PBR × BSD`. Structure:
**present-and-faithful**, and correctly placed in `sim/` (it models the UE).
Two of the deployment's own confirmations were previously recorded as
judgement calls and are now sourced:

- `logicalChannelSR_Mask = 0` and `logicalChannelSR_DelayTimerApplied = 0`
  (`nr_radio_config.c:3794-3795`) — so `sim/ul_access.py`'s two "simplified
  away" SR conditions are **faithful to this deployment**, not a
  simplification.
- `*schedulingRequestID = 0` for every logical channel (`:3793`) — **one SR
  resource per UE** is the deployed configuration, confirming `ul_access.py`'s
  UE-granularity choice.

**But the two numbers that set the bucket are both wrong**, from
`nr_radio_config.c:3686-3775` (the deployed `get_DRB_RLC_BearerConfig`):

| input | deployed gNB | this simulator | consequence |
|---|---|---|---|
| **PBR, GBR bearer** | smallest PBR enum **≥** GFBR, from {8,16,32,…,65536 kBps, infinity} (`:3711-3739`) | **exactly** `gfbr_bps` (`flow.py:367-372`) | sim's prioritised round is **smaller** than deployed — rounding is always upward, so a 1.2 Mbps GFBR gets a **2048 kBps** PBR on hardware, ~1.7× the sim's |
| **PBR, non-GBR bearer** | **`kBps8`** (`:3703`) | **0.0** (`flow.py:372`) | sim's non-GBR flows are served **only from round 2**; the deployed ones hold a real token bucket and enter round 1 |
| **BSD** | **PDB-derived**: ≤100 ms → **ms20**, ≤150 → ms50, ≤300 → ms100, else ms150 (`:3765-3771`) | **`bsd_ms = 100.0` for every flow** (`flow.py:288`), never overridden by any scenario | for a 5QI-1 flow (PDB 100 ms) the sim's bucket ceiling is **5× the deployed one**; for 5QI 2 (PDB 150) **2×** |

**And the non-GBR PBR is a comment/code mismatch of exactly the kind
CLAUDE.md's governing rule covers.** The deployed comment reads *"non-GBR LCs
should use PBR=0 so they are served only after all GBR LCs"* and the line
below it assigns `prioritisedBitRate_kBps8`. **The simulator implements the
comment.** Per the standing rule — reproduce measured behaviour, not
documented intent — the code is what shipped. Flagged, not reconciled.

**Filter — ADMITTED.** LCP decides the **intra-TB split**, which is the one
thing `sim/ue_lcp.py` exists to model correctly (it was built to remove
`_mac_lcp_fill`'s gNB-side split). A 5× oversized bucket on the
highest-priority flow means the sim's UE can dump 5× more prioritised bytes
into a single TB before round 2 begins, so a multi-flow UE's low-priority
flows are starved *harder* here than on hardware; and non-GBR flows are
starved harder still, since they have no round-1 entry at all. **Which
clauses depend on it:** G7 c1/c2 (victim protection and aggressor clipping
are both intra-UE-split questions when the aggressor shares a UE), and G8
(per-UE fairness where a UE carries mixed classes). It does **not** touch
inter-UE ordering, so G1/G3/G5/G10 are unaffected.

### M-5 — **THE SIMULATOR'S LCG NUMBERING IS INCOMPATIBLE WITH THE DEPLOYED COMPARATOR'S OWN DEFINITION OF `has_srb`** (ADMITTED — and it is a trap for the Part-4 build)

The deployed invariant, stated in the code twice and used by both branches:

```
// LCG = DRB ID, LCID = DRB ID + 3
```
(`gNB_scheduler_ulsch.c:51-52` on `twotier`; the same comment in
`update_ul_qos_priority`), and set at `nr_radio_config.c:3781-3785`:
`lcg_id = drbId`, capped at 7. **DRB IDs start at 1, so no DRB ever lands on
LCG 0** — LCG 0 is the SRB group (`get_SRB_RLC_BearerConfig(..., logicalChannelGroup=0)`).

That is precisely what `has_srb` keys on
(`gNB_scheduler_ulsch.c:2167-2176`, reservation branch):

```c
/* SRB data maps to LCG0 ... LCG0 buffer with no DRB on LCG0 == control/RRC pending -> top tier. */
if (sched_ctrl->estimated_ul_buffer_per_lcg[0] > 0) { ... ul_has_srb = true; }
```

Since `lcg0_is_drb` can never be true in this deployment, the real predicate
reduces to **`estimated_ul_buffer_per_lcg[0] > 0`**.

**In this simulator LCG 0 carries DATA.** `scheduler/flow.py:206-213` maps
5QI 1 and 5QI 3 → LCG 0. Measured over the built scenarios:

| scenario | UL LCGs in use | LCG 0 carries |
|---|---|---|
| parametric `factory` (N=8) | 0, 1, 6 | the **5QI-1 telemetry flow on every UE** |
| `sensor_dense` | **0 only** | **every UL flow of every UE** |
| `factory_robots` | 1, 5, 6 | — |

**So wiring `has_srb` to the C's own predicate — the obvious Part-4 move —
would classify ordinary 5QI-1 data as SRB.** On the parametric mix that
promotes every telemetry-backlogged UE above every video/BE UE permanently;
on `sensor_dense` it sets the top tier for all UEs at once, a universal tie.
Neither is the behaviour `has_srb` exists to produce.

**Second consequence, latent today.** The deployed lookup is
`lcg → lcid = lcg+3 → exactly one `qos_config``. That data structure cannot
represent two QoS classes on one LCG. `FIVE_QI_LCG` **can** — 5QI {1,3}→0,
{5,7}→4, {6,8}→5, {82,83,84,85}→3. **Measured: zero collisions in any built
scenario** (checked per (ue,lcg) across all three), so it is latent, not
active. It becomes active the moment a scenario gives one UE both 5QI 1 and
5QI 3 uplink.

**Filter — ADMITTED.** It does not change any current number (`has_srb` is
hardcoded `False`). It is recorded because Part 4's stated purpose is to make
that tier live, and the naive wiring is wrong in a way that would look like a
working mechanism.

### M-6 — PDCCH: **the sim's CCE budget never binds in any slot, while the deployed gNB has a hard 4-UE-per-slot cap that this simulator exceeds on ~half of all uplink slots — and the excess is ARM-DIFFERENTIAL** (ADMITTED; largest MAC finding of this pass)

**What the deployed system actually limits.** Both schedulers cap the number
of UEs scheduled per slot per direction, before any CCE search:

```c
int average_agg_level = 4;                                   // TODO find a better estimation
int max_sched_ues = bw / (average_agg_level * NR_NB_REG_PER_CCE);   // dlsch.c:1019-1020
max_sched_ues = min(max_sched_ues, MAX_DCI_CORESET);                // = 8, dlsch.c:1022-1023
```
and identically for uplink (`gNB_scheduler_ulsch.c:3017-3021`, `max_dci`).
`NR_NB_REG_PER_CCE = 6`; `MAX_DCI_CORESET = 8`
(`nfapi_nr_interface_scf.h:803`); `bw` is the carrier bandwidth **in PRBs**,
and the deployment runs **N_RB 106 at mu 1**
(`calibration-logs/twotier_startup_gnb.log:45`).

**106 / (4 × 6) = 4.** So the deployed gNB schedules **at most 4 UEs per slot
in DL and issues at most 4 UL DCIs per slot** — a hard cap, independent of
channel quality, and far below `MAX_DCI_CORESET`.

**What this simulator does.** `sim/resource.py:41-49` hands each slot a flat
`pdcch_cce_budget` of 48 (D) / 32 (U) / 16 (S) — invented numbers, the U-slot
one explicitly described in the code as an amortisation — and each arm spends
`cce_aggregation_level(snr)` CCEs per grant (`scheduler/link.py:176-186`).
There is **no UE-count cap anywhere**: `grep max_sched_ues|max_dci` over
`scheduler/` and `sim/baselines/` returns nothing.

**Measured, not asserted** (parametric `factory` mix, seed 1, full horizon,
`cqi_delay_slots=8`, `min_rb=5`, via `grant_sink`):

| N | arm | UL UEs/slot mean · max · **frac > 4** | DL UEs/slot mean · max · frac > 4 |
|---|---|---|---|
| 8 | TwoTier | 4.28 · 8 · **46.2 %** | 5.50 · 8 · 62.5 % |
| 8 | Reservation | 2.93 · 7 · 7.5 % | 5.52 · 8 · 62.9 % |
| 8 | **PF** | **1.00 · 5 · 0.0 %** | 5.01 · 8 · 56.2 % |
| 16 | TwoTier | 5.43 · 12 · **49.1 %** | 8.59 · 16 · 53.1 % |
| 16 | **Reservation** | 6.19 · 10 · **87.4 %** | 8.81 · 16 · 50.2 % |
| 16 | **PF** | **1.00 · 7 · 0.0 %** | 8.34 · 16 · 53.3 % |

**Caveat on the DL column, stated rather than buried:** this mix is
uplink-heavy, so only 160–214 slots per run carry any DL grant at all. The DL
rows are a real measurement over a small population; the UL rows are over
16,000–18,000 slots.

**Two separate findings live in that table.**

1. **The sim's own PDCCH model is inert.** Every grant costs 1 or 2 CCEs
   (SNR is 14 dB+ everywhere in these scenarios; the histogram is
   `{1: …, 2: …}` with nothing above 2), and the worst observed slot spends
   **27 of 48** DL CCEs and **22 of 32** UL. **The CCE budget is never the
   binding constraint in any slot of any arm at any fleet size measured.**
   This is the per-slot-distribution form of CLAUDE.md's defects-log #29 rule:
   an aggregate CCE utilisation of 0.6357 is consistent with a constraint that
   never binds once.
2. **The deployed cap that *does* bind is absent, and its absence favours the
   two QoS arms specifically.** PF grants effectively one UL UE per slot
   (mean 1.00, p50 1, `frac > 4` = **0.0 %** at both fleet sizes), so imposing
   `max_dci = 4` would leave PF essentially untouched. It
   would bind on TwoTier **46–49 %** of UL slots and on Reservation **87.4 %**
   at N=16.

**Filter — ADMITTED, and it is not a haircut, it is a comparison effect.**
A capacity approximation that shifts all arms together does not touch an
ordering claim (P1-1's reasoning). This one does not shift all arms together:
it is a constraint that is slack for PF and heavily binding for both QoS arms.

**(a) What it would change if present.** Under the cap the QoS arms serve only
their top-4-ranked UEs per slot, so the ranking becomes far more consequential
than it is here (today a mid-ranked UE usually gets served anyway). Aggregate
UL throughput on both QoS arms falls; per-UE service intervals lengthen for
everything below rank 4; PF is untouched.

**(b) Which published results depend on its absence.** **G10** (admissible
fleet — the cap binds harder as N grows, so the boundary is an upper bound in
the same direction as P1-1's, and this time arm-differentially); **G8** (both
halves — a cap concentrates service on high-ranked UEs, which is exactly the
mechanism producing Reservation's 10 s starvation epochs, so those epochs are
likely *understated*); **G5** (Reservation 3/10, TwoTier 6/10 — all UL video);
and any comparison sentence of the form "the QoS arms serve more UEs".

**(c) What is inert because of it.** `scheduler/link.py::cce_aggregation_level`
returns 4/8/16 only below 8 dB SNR; no built scenario reaches there, so the
whole low-SNR half of that function has never executed in a published run.
`SlotGrid.pdcch_cce_budget`'s three constants have never bound. The
`average_agg_level = 4` known issue in CLAUDE.md is **resolved by this
reading**: the real code does not use the aggregation level to price a grant
at all — it uses a fixed 4 to derive a **UE-count cap**, so "model it fixed or
SNR-dependent" is the wrong question. The right port is the cap.

### M-7 — HARQ: process pools, binary outcomes and retx PRB cost faithful; **k1/k2 are retransmission-only, and the combining table is uncalibrated** (present-but-approximate)

**Faithful.** Per-(UE, direction) process pools (DL 8 / UL 16), binary per-TB
outcome, retransmissions charged the **original** grant's PRBs and CCEs
(`driver.py:626-628`, matching OAI's retx path which re-finds an rbSize giving
the same TBS), full masking of a flow with a pending process, `harq_round_max=4`,
and the WP5 fix that credits UL receipt only on confirmed success.

**Approximate, and both are already flagged in-code rather than hidden:**
- `_IR_GAIN_DB = {0: 0.0, 1: 4.0, 2: 6.5, 3: 8.0}` — an uncalibrated table
  "ported as-is, not derived", saturating for any attempt past the third. With
  `harq_round_max = 4` nothing exceeds the table, so the saturation note is
  currently moot.
- **`k1` and `k2` price only retransmissions.** `harq_rtt_dl = k1 + k2`,
  `harq_rtt_ul = k2` (`driver.py:183-188`); the **first** attempt in both
  directions is same-slot. DL is defensible (PDSCH is same-slot as its PDCCH;
  k1 is when the *gNB* learns the outcome). **UL is not** — see M-2: a real UL
  grant is followed by PUSCH k2 slots later, always.
- **No PUCCH resource is consumed by HARQ-ACK**, and none by SR or CSI — see
  P1-1's admitted absence, of which this is a further instance rather than a
  new one.

**Filter — present-but-approximate; the UL k2 half is ADMITTED under M-2.**

### M-8 — TB-SIZE QUANTISATION: absent, and filtered out by measurement (absent-and-filtered-out)

`bits_per_prb()` returns `int(se × 12 × symbols)` and grant sizing multiplies
by PRBs; there is no `nr_compute_tbs`, no LDPC base-graph quantisation, no
3824-bit boundary. Real TBS lands on a coarse ladder.

**Filtered out on evidence, not judgement:** `scripts/tbs_counterfactual.py`
replayed every UL grant of a real run through OAI's own
`nr_find_nb_rb`/`nr_compute_tbs` and the padding distribution was
**unchanged — 13,214 of 13,214 grants at padding 0** (CLAUDE.md, WP9 §20.1).
The one clause that could have depended on it (the truncated-BSR/padding path)
was closed by that measurement. **Caveat carried forward: that is one load
point**, and the counterfactual was run for the padding question only, not for
grant-size accuracy in general.

### M-9 — **THE DEPLOYED UL ELIGIBILITY GATE HAS A 100 ms ESTIMATE-FREE ANTI-STARVATION RESCUE. THIS PORT HAS NO EQUIVALENT, IN ANY ARM.** (ADMITTED — the sharpest finding of this pass)

Ground truth, `gNB_scheduler_ulsch.c:1735-1766`, called by **both** deployed
schedulers (`_ulsch.c:2155` for reservation, `ia_p5g_scheduler.c:2299` for
two-tier):

```c
const bool has_data = sched_ctrl->estimated_ul_buffer > sched_ctrl->sched_ul_bytes
                    || sched_ctrl->ul_has_unfulfilled_gbr;
const bool high_inactivity = diff >= (ulsch_max_frame_inactivity > 0
                                      ? ulsch_max_frame_inactivity * n
                                      : num_slots_per_period);
return has_data || sched_ctrl->SR || high_inactivity;
```

`ulsch_max_frame_inactivity` is **10 frames = 100 ms**, both as the config
default (`MACRLC_nr_paramdef.h:125`) and in the deployment `.conf` files
(`gnb-vnf.sa.cbrs.aerial.conf:191`). **So on hardware, any connected UE that
has not been scheduled in the uplink for 100 ms becomes a candidate,
unconditionally — regardless of BSR estimate, per-LCG array, SR state or
deficit.**

**What this port implements is the first disjunct only.** Every arm's UL
candidate list is pre-filtered to `bytes_reported > 0`
(`reservation.py:150-158` states this explicitly: *"a B=0-but-`do_sched`-True
candidate, which the C's own gate admits, never reaches our candidate list at
all"*). Mapping the four terms:

| deployed term | this port |
|---|---|
| `estimated_ul_buffer > sched_ul_bytes` | **faithful** — `bytes_reported = max(0, estimated_ul_buffer − sched_ul_bytes)` |
| `\|\| ul_has_unfulfilled_gbr` | **absent** — but dead in the fault anyway: set only inside the zero-gated per-LCG loop (`_ulsch.c:2231-2241`, and `ia_p5g_scheduler.c:594-596` says so itself) |
| `\|\| sched_ctrl->SR` | **approximated, not ported** — routed through a **fake 150-byte `bytes_reported`** (`ul_access.sr_report_floor`), so it also *sizes* the grant; the C's SR is an eligibility bit that does not cap the TB |
| `\|\| high_inactivity` (100 ms) | **ABSENT ENTIRELY.** `grep -rn inactivity scheduler/ sim/ --include=*.py` returns two comments and no code |

**(a) What it would change if present.** A starved UE re-enters the candidate
list every 100 ms whatever its estimate says. It does **not** fix that UE's
*rank* — it is a candidacy rescue, not a ranking one — so it does not overturn
defects-log #24/#25's product finding (that fault is `update_ul_qos_priority`
ranking a zero-array UE last, which is confirmed in the C and correctly
ported). But it changes the **worst case** from "never a candidate" to "a
candidate at least every 100 ms".

**(b) Which published results depend on its absence.**
- **G8's second half, which is the audit's finding #2.** *"Zero starvation
  epochs ≥ 1 s"*, with **Reservation 7/10 runs affected and a 10.0 s epoch on
  a 10 s run**. A 10-second uplink starvation epoch requires the UE to be
  excluded for 100 consecutive 100 ms windows. On the deployed gate that
  cannot happen by exclusion; it could only happen by the UE being a candidate
  and losing the sort 100 times running. **The published G8 severity is
  therefore an upper bound on the deployed system's, and the correction is
  not small.**
- **G3** (*"can the network make a healthy robot look dead"*, max gap ≤ 500 ms):
  passes 10/10 here, and the deployed gate makes a >500 ms gap structurally
  much harder. Right answer, wrong margin.
- **G10 / G5**: the cold-start lock-out is a candidacy fault, and this is the
  deployed system's candidacy rescue. G10's without-attach boundary
  (Res 4, TT 4 vs PF 8) is measured on a gate strictly narrower than deployed.

**(c) What is inert because of it.** Nothing dormant in the sim — like
P1-1's RA absence this is a missing mechanism, not a dead branch. But it is
the second half of the `has_srb` shape: P1-3/P1-4 enumerated the dead **ranking**
tiers; this is a dead **eligibility** disjunct, and the eligibility gate was
never enumerated as a set at all.

**Note the interaction with M-6, and it cuts the other way.** The deployed
`max_dci = 4` cap means a rescued-but-last-ranked UE still may not get a DCI.
So M-6 and M-9 are opposing corrections and neither can be signed without
running them together. **Do not net them by argument.**

### M-10 — TIMING ADVANCE: absent; magnitude bounded, plus one unrecorded consequence (absent-and-admitted, low)

P1-3 established TA's arming rate (`frame == sched_ctrl->ta_frame`,
`gNB_scheduler_dlsch.c:745-746`, ~once per 10.24 s per UE) and the flat
`oh = 12` substitution. **One consequence it did not record:**
`gNB_scheduler_dlsch.c:784` reads

```c
if (sched_ctrl->num_total_bytes == 0 && sched_ctrl->ta_apply == false) continue;
```

— so a UE with **zero downlink backlog is still scheduled** when TA is
pending. The deployed system issues DL grants that carry no user data,
consuming PRBs and a DCI. The sim never does. At ~1 per UE per 10.24 s this is
negligible against any clause. **absent-and-admitted, filtered on magnitude.**

### M-11 — SPS / CONFIGURED GRANTS: absent here **and disabled in the deployed RRC config** (NOT a finding — and it removes an escape hatch)

`ubwp->bwp_Dedicated->configuredGrantConfig = NULL`
(`nr_radio_config.c:1894`) and
`configDedicated->initialDownlinkBWP->sps_Config = NULL` (`:4130`). The
deployment configures **neither** uplink Configured Grants nor downlink SPS.
CLAUDE.md's standing "do not add SPS" rule was argued from *"the real hardware
scheduler defers SPS to a Phase 2 that was never built"*; **it now has a
config citation.** Same status as DRX (P1-2): a **correct abstraction**.

**The consequence worth recording is the negative one.** A Configured Grant
Type 1 gives a UE periodic uplink resources with no SR and no BSR — it is the
one mechanism that would dissolve the cold-start lock-out outright. It is
absent from the deployment too. **So the lock-out has no configured escape
hatch on hardware either**, which is a second, independent confirmation of
defects-log #25's product finding, arrived at from the configuration rather
than from the comparator.

### M-12 — LOGICAL CHANNEL RESTRICTIONS: absent here **and never configured in the deployment** (absent-and-filtered-out)

TS 38.321 §5.4.3.1.1's grant-selection restrictions — `allowedSCS-List`,
`maxPUSCH-Duration`, `configuredGrantType1Allowed`, `allowedServingCells` —
have **zero occurrences** in the deployed `openair2/LAYER2/NR_MAC_gNB` and
`openair2/RRC/NR` sources. Single carrier, single numerology, single BWP, no
CG: every restriction is all-permissive, so `sim/ue_lcp.py` offering the whole
TB to every logical channel is **exactly** what the deployed UE would do.
Filtered out on the deployment's own config, not on judgement.

### M-13 — RANDOM ACCESS (extends P1-1, no repetition): the calibration instance restated precisely

P1-1 established RA's absence and its **scheduling priority** over the data
plane. The one thing to add is the shape of the calibration instance the brief
names: *"a UE simply exists at slot 0 with an empty buffer estimate — the state
the cold-start lock-out requires."* Cross-referencing M-9 and M-11: on
hardware that same state is exited by **three** routes, of which this port has
one and a half — `SR` (approximated as a 150-byte fake report), `high_inactivity`
(absent), and a Configured Grant (absent from the deployment too, so correctly
absent here). **The lock-out is therefore over-represented here relative to the
deployed system, but not fabricated by it.**

## CONTROL PLANE

| item | verdict | reason |
|---|---|---|
| **RRC connection setup** | **absent-and-admitted** | No Msg3/Msg4, no RRCSetup exchange. `sim/join.py` models the *timing* (`t300`/`t301`/`t319`/`t311`) as an FSM gating a UE out of scheduling, with no messages and no resource cost. **Depends on it:** G9 (attach ≤ 15 s is a bound on a procedure that does not exist), and `has_srb` (M-5) |
| **RRC reconfiguration** | **absent-and-admitted** | `SchedulerContextReset` models the *effect* of a reestablishment on scheduler state (`"mac"` vs `"full"` scope) without the message. **Depends on it:** nothing scored today; it is the second-largest SRB traffic source and therefore an input to `has_srb` |
| **Measurement reporting** | **absent-and-filtered-out** | Single-cell deployment (`calibration-logs`: one gNB, N_RB 106, one CC). No neighbour cell exists to measure. Would generate SRB1 uplink traffic — the third `has_srb` input — but there is no clause it answers |
| **SRB traffic** | **absent-and-admitted — the single highest-leverage absence in the audit** | It is the *only* input to Reservation's **top** ranking tier in both directions, decisive **0 times in 5.6 M UL adjacencies**, and DL is unmeasured (M-1). See M-5 for the trap in wiring it |
| **Handover** | **absent-and-filtered-out** | Single cell. No clause references mobility between cells; G9's mobility is join/re-join within one cell, which `sim/join.py` does model |

## PHY / RLC / PDCP / SDAP — one line each

- **PHY** — **present-but-approximate, deliberately.** A 12-row SNR→spectral-efficiency
  staircase (`scheduler/link.py`, self-described as *"not defensible at the PHY
  level"*) plus a doubles-per-dB BLER slope; no OFDM numerology beyond slot
  duration, no DMRS/CSI-RS/SSB/PTRS resource cost, no MIMO layers, no power
  control (`sim/power.py` is dormant). **Filtered out** — the comparison is
  between schedulers over an identical PHY.
- **RLC** — **absent-and-filtered-out.** No segmentation, no AM/UM, no
  retransmission, no status PDU, no RLC header bytes. The one place it could
  matter is that `has_srb` reads *SRB RLC bytes* on hardware; that is an SRB
  finding (M-5), not an RLC one.
- **PDCP** — **absent-and-filtered-out.** No sequence numbering, reordering,
  duplication, header compression or ciphering. No clause references end-to-end
  ordering or PDCP latency; PDB here is measured MAC-buffer-to-delivery.
- **SDAP** — **absent-and-filtered-out.** QFI→DRB mapping is collapsed:
  `FlowConfig` carries the 5QI directly and `lcg` self-resolves from it. This
  is the same collapse M-5 is about — the deployed mapping is
  QFI→DRB→LCID→LCG with `LCG = DRB ID`, and flattening it is what puts data on
  LCG 0.

---

# THE CHECKLIST, IN ONE TABLE

| item | verdict | entry |
|---|---|---|
| random access (PRACH/RAR/Msg3/contention) | absent-and-admitted | P1-1 + **M-13** |
| scheduling request | present-and-faithful (state machine) / **absent-and-admitted (latency)** | **M-2** |
| buffer status reporting | present-and-faithful (short/long, triggers) / **padding + both truncated formats OFF in every published run**, filtered by measurement | **M-3** |
| logical channel prioritisation | present-and-faithful (algorithm) / **present-but-approximate — PBR and BSD both disagree with the deployed gNB** | **M-4** |
| HARQ (k1, k2, IR, retx PRB cost) | present-and-faithful except **UL k2 priced only on retransmissions** | **M-7**, M-2 |
| DRX | absent-and-filtered-out (`255, // no drx`) | P1-2 |
| timing advance | absent-and-admitted, low magnitude | P1-3 + **M-10** |
| SPS / configured grants | absent-and-filtered-out — **`configuredGrantConfig = NULL`, `sps_Config = NULL`** | **M-11** |
| logical channel restrictions | absent-and-filtered-out — never configured in the deployment | **M-12** |
| TB-size quantisation | absent-and-filtered-out, by counterfactual measurement | **M-8** |
| PDCCH (CCE budget, AL, DCI cost) | **present-but-inert (never binds) / the deployed 4-UE-per-slot cap is absent** | **M-6** |
| ranking comparator, tier by tier, measured | present-but-approximate; **evidence base is UL-only** | **M-1** (+ P1-3, P1-4) |
| — *and the eligibility gate that precedes it* | **absent-and-admitted: `high_inactivity` (100 ms)** | **M-9** |
| RRC setup / reconfig / meas / SRB / handover | see control-plane table | above |
| PHY / RLC / PDCP / SDAP | see one-line table | above |

# FINDINGS, RANKED BY HOW MUCH THEY TOUCH

| # | finding | touches | invalidates |
|---|---|---|---|
| **1** | **M-9 — the deployed UL eligibility gate rescues any UE unscheduled for 100 ms (`high_inactivity`, `ulsch_max_frame_inactivity = 10` frames); this port has no equivalent in any arm.** The gate here is `has_data` alone | **every UL result on every arm** | **G8's second half** — Reservation's 7/10 runs with a starvation epoch and its **10.0 s epoch on a 10 s run** require 100 consecutive 100 ms exclusions, which the deployed gate forbids. G3's margins; G10's and G5's without-attach boundaries. It is a **candidacy** rescue, not a ranking one, so it does **not** overturn defects-log #24/#25 |
| **2** | **M-6 — the deployed gNB schedules at most 4 UEs per slot per direction (`bw / (4 × 6)` capped at `MAX_DCI_CORESET`, at N_RB 106 → 4); the sim has no UE-count cap, and its own CCE budget never binds in any slot.** Measured: TwoTier exceeds 4 on **46–49 %** of UL slots, **Reservation on 87.4 %** at N=16, **PF on 0.0 %** | **G10, G8, G5, and every "the QoS arms serve more UEs" sentence** | **Arm-differential**, so unlike P1-1's flat haircut it touches ordering, not only capacity. Opposes finding #1 in direction — **they must be run together, not netted by argument** |
| **3** | **M-1 — the measured dead-tier evidence is UPLINK ONLY** (`LossPointTally("UL")`, `rank_trace.py:202`). Every DL comparator is unmeasured, including TwoTier's `has_gbr`/`pdb_ms` tiers, which appear nowhere in the pooled totals | **P1-4's headline** | P1-4's *"both QoS arms rank on `coef → pdb_ms → has_gbr`"* holds for **Reservation UL only**. TwoTier's UL comparator is `-coef` at 96.6 % with a 3.4 % tie rate; its DL comparator has never been observed — and **G1's clause is about a downlink flow** (P2-2) |
| **4** | **M-5 — the sim's LCG numbering is incompatible with the deployed `has_srb` predicate.** Deployed: `LCG = DRB ID`, DRB IDs start at 1, so LCG 0 **is** the SRB group and `has_srb ≡ per_lcg[0] > 0`. Here LCG 0 carries 5QI-1 **data** (all of `sensor_dense`; the telemetry flow of every UE in the parametric mix) | **Part 4's build**, nothing today | Wiring `has_srb` to the C's own predicate would promote every telemetry-backlogged UE permanently and look like a working mechanism. Latent second half: `FIVE_QI_LCG` can put two QoS classes on one LCG, which the deployed `lcg → lcid → one qos_config` lookup cannot represent (measured: **zero collisions in any built scenario today**) |
| **5** | **M-4 — LCP's two configured inputs both disagree with the deployment.** BSD is PDB-derived on hardware (**ms20** for a 100 ms PDB) against a flat **100 ms** here → the sim's bucket is **5×** oversized on the highest-priority flow; GBR PBR is rounded **up** to an enum ladder on hardware and exact here; non-GBR PBR is **kBps8** in the deployed code and **0** here | **intra-TB split on every multi-flow UL UE** | G7 c1/c2 and G8 where a UE carries mixed classes. **And the non-GBR case is a comment/code mismatch: the deployed comment says PBR=0, the deployed line assigns kBps8, and this simulator implements the comment** — the governing rule says port the code |
| **6** | **M-2 — the SR→grant→PUSCH chain has zero latency.** `k2` prices retransmissions only; the first UL TB of every grant is transmitted in the grant's own slot | every UL latency figure | ~1–2 ms per grant, one-directional (optimistic). Cannot flip G1/G2 (95/100 ms bounds); **does** touch WP4's low-load round-trip calibration and pushes crumb fraction away from hardware's 48–52 % |
| **7** | **M-3 — the Padding BSR trigger and both truncated formats are OFF in every published run** (`truncated_bsr="off"`; only `scripts/bsr_desync_study.py` sets it) | the BSR desync narrative | Filtered out **by measurement, not judgement**: 13,214/13,214 grants at padding 0. Caveat: that is **one load point** |
| **8** | **M-10 / M-11 / M-12 — three absences confirmed correct against the deployment's own configuration**: TA (armed once per 10.24 s; its only unrecorded effect is a data-free DL grant), SPS/CG (`configuredGrantConfig = NULL`, `sps_Config = NULL`), LC restrictions (never configured) | nothing | **Not findings.** Recorded so they are not re-raised — and because SPS/CG being absent *from the deployment* removes the only configured escape from the cold-start lock-out, independently confirming defects-log #25 |
| **9** | **M-8 — no TB-size quantisation**; **M-7** — the IR combining table is uncalibrated | grant sizing; retry BLER | Both already flagged in-code. TBS filtered out by the `tbs_counterfactual` result |

**Nothing found here makes the rest of the audit unsound**, so it ran to
completion. The one item that comes closest is finding #1, because it is an
eligibility-gate absence and the audit's prior finding #2 (G8's failing second
half) is a starvation result — but it corrects a *magnitude*, not the audit's
method, and finding #2 remains a real unscored clause either way.

**Two items are explicitly NOT netted against each other** (#1 rescues starved
UEs, #2 removes service from mid-ranked ones). Estimating their combined sign
by argument would be exactly the mistake CLAUDE.md's decompose-before-
attributing rule exists to prevent.

---

**PART 2 CONTINUES IN `docs/mac-fidelity-audit-part2-2026-09-07.md`** — the
per-guarantee scenario and clause audit, which consumes M-1 … M-13 above.
