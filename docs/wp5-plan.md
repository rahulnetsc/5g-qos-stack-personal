# WP5 plan — HARQ

**Provenance.** Written before any code, per CLAUDE.md's standing rule and
this session's own instruction ("Write `docs/wp5-plan.md` BEFORE any code
and commit it"). Unlike `docs/wp7-plan.md` (a post-hoc reconstruction after
a lost session), this document is the actual plan — commit boundaries and
predictions below are commitments to check against, not a memory aid.

Scope per README §4 and `p5g-sim-plan.md` §9: N HARQ processes per UE per
direction, k1/k2 timing, RTT, per-attempt combining gain, max-retx residual
loss. Read `README.md` (especially §3, §4, §7, §8), `CLAUDE.md`, and
`docs/wp7-plan.md` (for the format this document follows) first.

---

## 0. Correction made while scoping this WP

The task that produced this plan cited a combining-gain formula from
`README.md` §3 — `effective_SE(Δ) = SE × Σp_reach(k)(1−BLER_k) / Σp_reach(k)`
— as something to "reuse conceptually" from the stale `feat/harq-bler-retx`
branch. **Verified absent.** `git grep` and `git show` against
`origin/feat/harq-bler-retx`'s actual content (`scheduler/link.py`, the
branch's own `harq-bler-retx.md`) turn up no `effective_SE`, no `p_reach`,
no reachability-weighted sum anywhere. The branch's real mechanism is
simpler — `combining_gain_db(retx_count, mode)`, an SNR-domain dB bonus by
attempt count, added to a sigmoid BLER curve (`scheduler/link.py` on that
branch; full detail in §2 below). This has no provenance beyond a prior
design conversation's summary of the branch, and that summary was wrong.

**Decided (with sign-off): build the branch's actual mechanism, drop the
formula entirely — see Decision 1.** `README.md` §3's mining table is fixed
in the same commit as this document (§6 below) so a future session doesn't
re-derive the formula from that stale citation.

---

## 1. The HARQ mechanism, plain language

**What the gNB holds.** Per (UE, direction), a pool of up to `N` HARQ
processes (real 5G: `N=16`, TS 38.321 §5.3.2.1 — no vendored value in this
repo's `oai-branches/`, see Decision 2). Each process is either free, or
busy holding one in-flight transport block (TB): how many bytes it carries,
how many times it's been sent, and the slot it's next due for action. Real
OAI keeps the busy ones on a `retrans_dl_harq`/`retrans_ul_harq` list and
the free ones on `available_dl_harq`/`available_ul_harq` — a UE with every
process busy cannot receive a new TB, full stop, regardless of backlog.

**What the UE holds.** The mirror-side bookkeeping: which process a
received TB belongs to, and (conceptually, since this simulator has no
actual bits) enough state to combine a retransmission's signal with what
it received before — that combining is *why* a second attempt is more
likely to succeed than the first, at the same channel quality.

**What k1 gates.** After a DL transmission, the UE needs `k1` slots to
decode and report ACK/NACK. Until that report lands, the gNB doesn't know
whether to free the process (ACK) or schedule a retransmission (NACK). Real
OAI does not call this "k1" anywhere — it's `pdsch_to_harq_feedback[]`, a
per-DCI-selectable set of candidate slot-offsets (§2).

**What k2 gates.** The gap between a grant (DCI) and the PUSCH transmission
it authorizes — for UL, this literally is what happens between "you have a
grant" and "you actually transmit." The same `k2` concept governs how soon
a UL retransmission (whose own new grant carries the NACK signal implicitly
— OAI has no separate UL NACK message) actually goes out.

**Where retransmission competes with new data for PRBs.** Each slot, any
HARQ process due for retransmission is served *before* the scheduler
decides how many PRBs are left for new data — a TB already in flight is
"owed," and the real OAI list-head structure (`retrans_dl_harq` etc.)
reflects that priority structurally. This simulator's schedulers see a
resource grid whose `prb_count` has already been reduced by whatever
retransmissions are due that slot (§4, Decision 4) — new data is allocated
against whatever capacity remains.

**Max-retx / residual loss.** Each process has a retry budget (real name:
`harq_round_max`, §2) shared with OLLA's own config struct. After
`harq_round_max` failed attempts the gNB gives up: the process frees, and —
since this simulator has no RLC layer beneath HARQ to retry further — those
bytes are lost for good. This is a **second, distinct loss path** from the
one `sim/buffer.py::expire()` already implements (PDB-clock-driven
discard): a TB can be abandoned on attempt-count exhaustion even while its
PDB hasn't technically expired yet, if `harq_round_max` is tight relative
to the RTT budget. Both paths coexist; §4's design keeps bytes physically
queued (visible to `expire()`'s existing clock) for the whole time they're
in flight, so a TB that never gets a chance at a retry before its PDB
expires is *already* correctly caught by the existing mechanism, with
nothing new to build for that case.

**On `N` (the process count) vs. the acceptance criterion.** It's tempting
to read "N processes per UE per direction" as *the* throughput-limiting
knob. It mostly isn't, at this simulator's traffic/BLER regimes — the
mined branch's own writeup states "at 10% BLER and 8-slot RTT, at most 1–2
processes are simultaneously pending per UE" against a pool of 16; process
exhaustion (real OAI tracks this as `harq_exhausted`,
`oai-branches/two-tier/ia_p5g_scheduler.c` lines 691/788/800/804/832/853/
2293) is a genuine safety cap worth counting as a diagnostic, but the
mechanism the acceptance criterion actually targets is **RTT competing with
PDB**: a flow whose PDB is only a small multiple of the HARQ RTT has no
room for even one retry before its deadline, so bytes that fail their first
attempt now age out via the ordinary PDB-expiry path — not a new
"process-starved" failure mode.

---

## 2. Ground truth, cited exactly (no paraphrase)

**OLLA — `get_mcs_from_bler`.** `oai-branches/two-tier/
gNB_scheduler_primitives.c:785-822`:

```c
785	#define BLER_UPDATE_FRAME 10
786	#define BLER_FILTER 0.9f
787	int get_mcs_from_bler(const NR_bler_options_t *bler_options,
788	                      const NR_mac_dir_stats_t *stats,
789	                      NR_bler_stats_t *bler_stats,
790	                      int max_mcs,
791	                      frame_t frame)
792	{
793	  int diff = frame - bler_stats->last_frame;
794	  if (diff < 0) // wrap around
795	    diff += 1024;
796	
797	  max_mcs = min(max_mcs, bler_options->max_mcs);
798	  const uint8_t old_mcs = min(bler_stats->mcs, max_mcs);
799	  if (diff < BLER_UPDATE_FRAME)
800	    return old_mcs; // no update
801	
802	  const int num_dl_sched = (int)(stats->rounds[0] - bler_stats->rounds[0]);
803	  const int num_dl_retx = (int)(stats->rounds[1] - bler_stats->rounds[1]);
804	  const float bler_window = num_dl_sched > 0 ? (float) num_dl_retx / num_dl_sched : bler_stats->bler;
805	  bler_stats->bler = BLER_FILTER * bler_stats->bler + (1 - BLER_FILTER) * bler_window;
806	
807	  int new_mcs = old_mcs;
808	  if (bler_stats->bler < bler_options->lower && old_mcs < max_mcs && num_dl_sched > 3)
809	    new_mcs += 1;
810	  else if (bler_stats->bler > bler_options->upper || num_dl_sched <= 3)
811	    new_mcs -= 1;
812	
813	  new_mcs = max(new_mcs, bler_options->min_mcs);
814	  bler_stats->last_frame = frame;
815	  bler_stats->mcs = new_mcs;
816	  memcpy(bler_stats->rounds, stats->rounds, sizeof(stats->rounds));
817	  return new_mcs;
818	}
```

(Line numbers shifted by one vs. the raw source dump due to an elided
`LOG_D` call; content and line *ranges* above are exact.) `BLER_UPDATE_FRAME
= 10` is in units of `frame_t`, and an NR frame is spec-fixed at 10 ms
regardless of numerology — so the update gate really is a 100 ms window, as
the scoping task described, even though the literal constant reads `10`,
not `100`. The `-1` branch fires on **either** BLER-too-high **or**
`num_dl_sched <= 3` (line 810); the `+1` branch requires BLER-low **and**
`num_dl_sched > 3` (line 808) — confirmed exactly as the task described,
including the asymmetry (idle/low-activity UEs only ever ratchet down).
`old_mcs = min(bler_stats->mcs, max_mcs)` (line 798) means the climb-back-up
after a forced drop is strictly `+1` per `BLER_UPDATE_FRAME` window, never a
jump.

**Power-headroom → OLLA one-way clamp.** `oai-branches/two-tier/
gNB_scheduler_ulsch.c:2485-2491`:

```c
2485	    if((sched_ctrl->pcmax != 0 || sched_ctrl->ph != 0) && B > 0)
2486	      nr_ue_max_mcs_min_rb(current_BWP->scs, sched_ctrl->ph, &sched, current_BWP, min_rb, B_eff, &available_rb, &sched.mcs);
2487	
2488	    if (sched.mcs < sched_ctrl->ul_bler_stats.mcs)
2489	      sched_ctrl->ul_bler_stats.mcs = sched.mcs; /* force estimated MCS down */
2490	
2491	    update_ul_ue_R_Qm(sched.mcs, current_BWP->mcs_table, current_BWP->pusch_Config, &sched.R, &sched.Qm);
```

`nr_ue_max_mcs_min_rb` (line 2486) is WP1's `sim/power.py::
shrink_to_power_budget`, already ported but **dormant** (not imported by
`driver.py` or any scheduler, per CLAUDE.md/README §4). Lines 2488-2489
write that power-shrunk MCS straight back into the persistent OLLA state
`ul_bler_stats.mcs` — one-directional, since the only place this field is
ever *raised* is `get_mcs_from_bler`'s own `+1` branch above, which starts
from `min(bler_stats->mcs, max_mcs)` (line 798) — i.e. it can only climb
back from wherever it was last forced down, one step per window.

**HARQ retry cap — `harq_round_max`, not `max_retx`.** No literal
`max_retx` exists anywhere in `oai-branches/`. The real cap lives in
`NR_bler_options_t` (the *same* struct as OLLA's `.lower`/`.upper`/
`.min_mcs`/`.max_mcs` thresholds above), field `harq_round_max`:
`gNB_scheduler_uci.c:407` (`harq->round >= harq_round_max - 1`, DL
ACK/NACK handler), `gNB_scheduler_ulsch.c:761,781` (UL, same pattern),
`:799-802` (Msg3/RACH retransmission, same mechanism), `:2723`
(`AssertFatal(cur_harq->round < nr_mac->ul_bler.harq_round_max, ...)`,
bounds-checks the round array); `harq_round_max == 1` is special-cased
(HARQ disabled) at `gNB_scheduler_ulsch.c:2173`, `gNB_scheduler_dlsch.c:792`,
`ia_p5g_scheduler.c:1530,2545`. Identical pattern in
`reservation/gNB_scheduler_ulsch.c:760,780,799-801,876,897,2191,2755` and
`reservation/gNB_scheduler_dlsch.c:805`.

**k2 — literally named, table-driven, not a single constant.**
`nr_mac_common.c:382`: `tda_info.k2 = tda->k2 ? *tda->k2 : j;`; `:396`:
`tda_info.k2 = table_6_1_2_1_1_2[tda_index][1] + j;` (UL table,
`:323-340`, second column ranges 0-3 across its 16 rows); `j =
get_j_for_k2(mu)` (`:4954-4960`, `j_table = {1, 1, 2, 3, 11, 21}` per
numerology, TS 38.214 Table 6.1.2.1.1-4). At this deployment's μ=1
(`sim/config.py::CarrierConfig.numerology` default), `j=1`, so `k2` ranges
**1-4 slots** depending on which TDA row RRC selects — not confirmed
anywhere in this repo which row that is. Also used at
`nr_ue_scheduler.c:1545-1547,1557,1581-1602` (UE-side PUSCH-slot
calculation) and `gNB_scheduler_ulsch.c:76,2050-2052,3042-3043,3075`,
`ia_p5g_scheduler.c:2204-2206`.

**k1 (PDSCH-to-HARQ-feedback) — not literally "k1" anywhere; it's
`pdsch_to_harq_feedback[]`.** `gNB_scheduler_primitives.c:3156-3173`:

```c
3161	  if (dci_format == NR_DL_DCI_FORMAT_1_0) {
3162	    for (int i = 0; i < 8; i++)
3163	      pdsch_to_harq_feedback[i] = i + 1;
3164	    return 8;
3165	  }
3166	  else {
3167	    AssertFatal(pucch_Config != NULL && pucch_Config->dl_DataToUL_ACK != NULL, ...);
3168	    for (int i = 0; i < pucch_Config->dl_DataToUL_ACK->list.count; i++) {
3169	      pdsch_to_harq_feedback[i] = *pucch_Config->dl_DataToUL_ACK->list.array[i];
3170	    }
3171	    return pucch_Config->dl_DataToUL_ACK->list.count;
3172	  }
```

Consumed at `gNB_scheduler_uci.c:1164-1178` to compute which slot the PUCCH
ACK/NACK lands on. For the DCI-format-1_0 fallback (line 3162-3163), the
candidate set is simply **{1..8} slots**, selected per-DCI by a 3-bit
field — no single value is "the" K1 for this deployment either. For other
formats it's whatever RRC's `dl_DataToUL_ACK` list configures, not vendored
here.

**A same-name false lead.** `k1`/`K1` also appear literally in
`gNB_scheduler_primitives.c:149,152-183,238-239,245-248` — but that's
`get_k1_k2_indices`/`get_K1_K2`, Type-II CSI precoding-matrix indices (TS
38.214 codebook tables), unrelated to HARQ timing. Line 239's own comment
flags this: `// get indices k1 and k2 for PHY matrix (not actual k1 and k2
values)`. Don't conflate the two when naming things in `sim/harq.py`.

**Provenance note.** `gNB_scheduler_primitives.c` (home of `get_mcs_from_
bler`) is flagged in `oai-branches/README.md` as **stock upstream OAI**,
predating both forks' divergence (commit `f548643`, 2026-03-12,
byte-identical across `two-tier/`/`reservation/`) — OLLA's behavior is not
fork-specific, applies identically to whichever scheduler Phase 2 builds.

---

## 3. Decisions — no ground truth, made explicitly

### Decision 1 — combining gain: port the branch's actual mechanism; the formula is dropped

Per §0. The real mechanism, `origin/feat/harq-bler-retx:scheduler/link.py`:

```python
_IR_GAIN_DB: dict[int, float] = {0: 0.0, 1: 4.0, 2: 6.5, 3: 8.0}
_CHASE_GAIN_DB_PER_RETX = 3.0

def combining_gain_db(retx_count: int, mode: str = "ir") -> float:
    if mode == "ir":
        return _IR_GAIN_DB.get(retx_count, _IR_GAIN_DB[3])
    return _CHASE_GAIN_DB_PER_RETX * retx_count
```

`retx_count=0` is the first (original) attempt — no combining yet.
**Constant provenance, checked, not assumed:** the branch's own
`harq-bler-retx.md` §11 ("Spec grounding") cites real 3GPP clauses for the
*mechanism's existence* (16 processes: TS 38.321 §5.3.2.1; `harq_round_max`
equivalent: §5.4.2.2; IR's RV sequence: TS 38.214 §6.1.2.1), but is explicit
that the **dB values themselves are not spec-sourced**: *"The combining
gain values (IR table: 0, 4.0, 6.5, 8.0 dB) are approximations derived from
3GPP NR LDPC link-level simulation results in the literature... The exact
values depend on code rate, modulation order, and channel realisation; the
tabulated values are representative for mid-range MCS at 10% target
BLER."* No specific link-level curve or paper is named. This is the same
epistemic tier as `scheduler/link.py`'s existing `_MCS_TABLE` ("crude
staircase... not defensible at the PHY level," already self-disclosed) —
port the numbers, but flag them in `sim/harq.py`'s docstring and a new
README §8 `[OPEN]` entry as an unsourced literature approximation, not a
verified constant, same treatment as `FIVE_QI_LCG`/`sr_period_slots`.

**Not built at all, per explicit rejection:** the reachability-weighted
`effective_SE(Δ)` formula, neither as the driving mechanism nor as a
derived/reported diagnostic — it has no provenance anywhere on disk, and no
`metric_panel.yml` entry would consume it as a diagnostic.

### Decision 1b — flagged, not yet resolved: `bler_sigmoid` vs. today's `bler_for_mcs`

The mined branch's combining-gain mechanism is paired with its own BLER
curve, `bler_sigmoid(delta_snr_db)` — a sigmoid keyed on instantaneous-SNR
deviation from a per-UE EWMA, flat 10% at zero deviation. **This predates
the current codebase's actual BLER mechanism.** `scheduler/link.py` today
has `bler_for_mcs(mcs_threshold_db, true_snr_db, base_bler=0.10)` — a
different, already-shipped, already-tested model: BLER doubles per dB of
shortfall between the scheduler's picked-MCS threshold and the true SNR
(WP1/WP4-era, postdates the May-2026 branch). Reintroducing `bler_sigmoid`
as a second, parallel BLER mechanism would leave two competing
SNR→BLER curves in the codebase with no stated rule for when each applies.

**Recommendation (not finalized — flagging for sign-off before commit 2 is
coded):** compose `combining_gain_db(retx_count)` with the *existing*
`bler_for_mcs`, by adding the dB gain to the SNR argument before the call —
combining gain is, physically, "the channel looks this many dB better for
this attempt," which is orthogonal to *which* SNR→BLER curve consumes it.
This preserves the already-tested mismatch-aware model and avoids shipping
`bler_sigmoid` as dead-on-arrival duplicate machinery. If this is wrong,
say so before commit 2.

### Decision 2 — process pool size `N`: no vendored value; default 16

Real OAI sizes `available_dl_harq`/`available_ul_harq` from UE-capability
config (`nrofHARQ-ProcessesForPDSCH` etc.), not a literal constant in any
vendored file. TS 38.321 §5.3.2.1's ceiling is 16, and the mined branch used
16 as a literal default. **Decided:** 16, as a config-swept knob (matching
`sr_period_slots`/`cqi_delay_slots` precedent), explicitly flagged as "the
spec ceiling, not a confirmed *deployed* value" — this repo's own
`oai-branches/` doesn't confirm this specific deployment configures 16
rather than fewer.

### Decision 3 — k1/k2/RTT granularity: two separate swept knobs, not one lumped RTT

Per §2, neither k1 nor k2 has a single canonical value in real OAI — both
are per-transmission-selectable (k1 from an 8-entry candidate set or an
RRC-configured list; k2 from a TDA-row lookup, 1-4 slots at this
deployment's μ=1). The mined branch collapsed both into one scalar
`harq_rtt=8`. **Decided:** expose `k1_slots` and `k2_slots` as two separate
driver-level scalar knobs (matching the `cqi_delay_slots` precedent),
matching the charter's literal "k1/k2 timing" wording and giving WP9 two
independent sweep axes. Per-attempt RTT = `k1_slots + k2_slots` for DL
(wait for feedback, then wait for the regrant's own transmission gap);
`k2_slots` alone for UL (the gNB already knows the outcome the instant it
finishes decoding — no feedback-transit delay to model on that side, though
gNB decode/processing time folds into `k2_slots` too, a stated
simplification). **Defaults:** `k1_slots=4` (midpoint of the {1..8}
DCI-format-1_0 set), `k2_slots=2` (midpoint of the 1-4 slot TDA range at
μ=1) — both flagged as representative points in a real range, not
confirmed deployed values, same honesty standard as `sr_period_slots`.

### Decision 4 — retransmission architecture: orthogonal driver-level model, zero required scheduler changes

The charter (`p5g-sim-plan.md` §9) names `scheduler/reservation.py`,
`scheduler/two_tier.py` under "Retransmission handling." **This is stale
for this branch's actual phase ordering**: `scheduler/reservation.py`
doesn't exist yet (Phase 2, both schedulers rewritten fresh against OAI
source, hasn't started — README §4); `scheduler/two_tier.py` on this branch
is still `main`'s pre-audit version (has SPS, per-flow intra-TB split —
known bugs per README §2, not yet fixed, since that fix only happens in
Phase 2's fresh rewrite). Building retransmission logic into a scheduler
slated for a full rewrite is wasted work.

**Decided:** follow the pattern this codebase already uses for BSR
(`sim/bsr.py`) and uplink access (`sim/ul_access.py`) — HARQ retry/RTT/
combining/max-retx-loss lives entirely in a new driver-level `sim/harq.py`,
invisible to the `Scheduler` protocol. The PRB-budget correction ("retrans-
mission competes with new data for PRBs") is achieved the same way the
mined branch did it (confirmed real, not part of the rejected formula):
before calling `scheduler.allocate()`, the driver resolves this slot's due
retransmissions directly and passes a reduced-capacity `SlotView` (`prb_
count = total − retx_prbs_due`, structurally satisfying the existing
`SlotView` Protocol in `scheduler/interfaces.py:51-58` — no inheritance
needed, matching that file's own stated design) into `scheduler.allocate()`
for new data. Every current scheduler (RoundRobin/PF/Gradient/legacy-
two_tier) needs **zero** code changes — matches the mined branch's own
architecture claim ("No scheduler code changes are required — all four
schedulers... automatically operate under the same HARQ model") and its own
`two_tier.py` touches, which were an accuracy nicety for that scheduler's
own capacity ranking under a sigmoid BLER curve, not a requirement for
retransmission to function on any scheduler.

**Flag for Phase 2 (not a WP5 blocker):** whoever builds `reservation.py`/
rewrites `two_tier.py` fresh should know the reduced-capacity-`SlotView`
convention exists, and may want the same BLER-aware effective-bits sizing
nicety the mined branch shows for `two_tier.py`'s own ranking score.

### Decision 5 — OLLA: bug #1 lands in WP5; bug #2 is blocked, not built

README §3 previously excluded OLLA entirely ("no GT/T test requires it,
adding it widens scope"). The two bugs found scoping WP5 don't get the same
answer:

- **Bug #1** (`num_dl_sched <= 3` forces `-1`, `+1` also gated on `> 3`,
  §2) is self-contained — it only reads the round-count state (`stats->
  rounds[0]`/`[1]`, i.e. total attempts vs. retx attempts) that WP5's own
  HARQ engine produces as a byproduct of tracking retries. It also now has
  a forcing function README §3 didn't have when OLLA was excluded: an idle
  UE has `num_dl_sched=0`, permanently ratcheting toward `min_mcs`,
  compounding with WP4's SR-chain on resume-after-silence (G4) — a named
  accuracy gap on a guarantee this branch already tests, not a
  hypothetical. **Decided: lands in WP5, its own late commit** (commit 6,
  §4), separated from the core RTT/retry mechanics per one-fidelity-
  change-per-commit.
- **Bug #2** (power-headroom forces `ul_bler_stats.mcs` down, one-way, §2)
  has a hard prerequisite: it only has something to bite on once WP1's
  `sim/power.py::shrink_to_power_budget` is actually wired into `driver.
  py`'s grant-sizing path — and it isn't (dormant, CLAUDE.md/README §4).
  Activating WP1 is itself a separate, larger fidelity change (a full
  power-limited grant-sizing pass through the driver) with its own
  regression diff, out of WP5's charter. **Decided: not built in WP5.**
  New README §8 `[OPEN]` item: activating `sim/power.py` plus this clamp,
  together, for whoever next needs WP1 live — not silently dropped, not
  silently bundled into WP5.

### Decision 6 — no `metric_panel.yml` status flips; flagging a real tension

Checked every metric's `requires:` field directly (17 entries, §-checked
against the file, not memory) — **none names WP5.** WP5 therefore promotes
**zero** panel statuses by the letter of the rule. Flagging, not fixing
unilaterally (a status/definition change needs the same care CLAUDE.md
gives the panel's multiplicity guard): this creates a real tension with the
charter's own text — *"BLER is currently a scalar discount with no
retransmission... every deadline result on this branch is unreliable until
this lands"* — while M01/M02/M13/M14/M15 (every deadline/latency metric)
already show `status: ok` today, silently HARQ-blind. Recorded here for the
same reason M04's proxy-vs-ok gap was recorded rather than quietly fixed;
whoever reviews this plan should decide whether an `ok`-with-caveat
annotation is warranted, separate from WP5's own commits.

---

## 4. Commit checklist

| # | Commit | Files | Wired live? |
|---|---|---|---|
| 1 | `HarqProcess`/`HarqProcessPool` core state + `combining_gain_db()` | `sim/harq.py` (new), `sim/tests/test_harq.py` (new) | No — dormant, unit-tested only (WP1 precedent) |
| 2 | `Allocation.harq_pid`/`is_retx` fields; combining-gain composition in `scheduler/link.py` (pending Decision 1b sign-off) | `scheduler/interfaces.py`, `scheduler/link.py`, tests | No — new optional fields default to old behavior |
| 3 | Process-pool gating on new-data grants (no multi-slot delay yet) | `sim/driver.py`, `sim/harq.py` | Live, but **designed to be inert** — delivery still synchronous, so the pool never actually binds |
| 4a | Deferred drain + real multi-slot retry, **DL** | `sim/driver.py`, `sim/metrics.py` (`bytes_harq_retx`/`bytes_harq_lost` counters) | Live — the big DL fidelity landing |
| 4b | Deferred drain + real multi-slot retry, **UL** — resolves the `sched_ul_bytes`/k2-HARQ gap `sim/bsr.py`'s own docstring flags (CLAUDE.md known issues) | `sim/driver.py`, interaction with `sim/bsr.py`/`sim/ul_access.py` (their own logic unchanged — see note) | Live — the big UL fidelity landing |
| 6 | OLLA bug #1 only (`get_mcs_from_bler`'s round-count ratchet) | `scheduler/link.py` or new `sim/olla.py`, `sim/driver.py` | Live |

**Note on 4b and `sim/bsr.py`:** `BsrModel.on_ul_grant`'s `sched_ul_bytes +=
tb_size` credit fires **at grant time** in real OAI (already faithfully
ported, WP3) — this must **not** change under WP5; only the physical
buffer drain (and `ue_lcp.fill()`'s per-flow split feeding it) defers to
ACK. Getting this wrong would silently break WP3's already-verified BSR
port.

**Predicted metric movement, ranked by confidence within each commit.**
Commits 1-3 predicted **fully clean** `--check` — falsifiable, no scenario
references any new field yet, matching WP7 commits 1/3/9's precedent.

*Commit 4a (DL):*
1. (High) M02 `pdb_violation_rate` — up, for DL flows in tight-PDB
   scenarios. This is the acceptance criterion itself.
2. (High) M01 `flow_latency_percentiles` — p95/p98/p99 up for DL flows
   under nonzero BLER; p50 roughly flat (most TBs still succeed on
   attempt 1 at typical configured SNR margins).
3. (High) M11 `prb_utilization` (DL) — up (retransmissions cost additional
   PRB-symbols for bytes that used to be a zero-additional-cost drop).
4. (Moderate) M10 `aggregate_throughput` — **up**, not down: bytes
   permanently lost under today's flat-discount-on-BLER-failure model now
   often succeed on retry. Predicting this *opposite* to the latency
   metrics' direction, deliberately, as WP4's own mixed-M11/M12 lesson
   argues against single-direction predictions.
5. (Moderate) M12 `pdcch_cce_utilization` — up slightly (extra DCI per
   retransmission).
6. (Low) M06/M17 (`frame_age_at_mec`, `frame_freeze...`) — predicted
   **inert on the 22-record regression corpus** (no `xr_video` scenario in
   studies 1-3, per WP7's own notes); would move worse if exercised.
7. (Low) M09 `per_second_jain_index` (proxy) — some perturbation plausible
   from uneven retry-driven PRB consumption across UEs; no directional
   call.
8. Flag: on the **PF** arm specifically, expect DL-only movement to also
   perturb that UE's UL numbers (`pf.py`'s per-UE, not per-direction,
   `_r_avg` EWMA — CLAUDE.md's known invariant, already confirmed causally
   during WP4). Not a bug if it happens again here.

*Commit 4b (UL):*
1. (High) Same latency/PDB direction as 4a, for UL flows.
2. (Moderate) Crumb fraction (README §8's long-open item) — plausibly
   closer to hardware's 48-52% now that real k2/HARQ pipelining exists,
   closing the gap that item's own text names as a candidate contributor.
   Stated as a hypothesis to check against `--check`, not asserted.
3. (High, "should be flat") `sched_ul_bytes` crediting timing — unchanged,
   per the note above; a good falsifiable check that 4b didn't
   accidentally touch WP3's BSR port.
4. (Low) `sim/ul_access.py` SR-chain interaction — masked in-flight bytes
   could make a UE's visible backlog look emptier at moments it wasn't
   before, plausibly triggering extra SR events; no directional call —
   check directly against `test_ul_access.py`'s scenarios.

*Commit 6 (OLLA bug #1):*
1. (Moderate) M01/M02 for low-rate control flows (`periodic_control`/
   `condition_monitor`, WP7) — worse, since their natural
   `num_dl_sched <= 3` between bursts ratchets them toward `min_mcs`. Ties
   directly to the G4/SR-chain interaction flagged in Decision 5.
2. (Low) M10/M11 — direction depends on how often the ratchet fires on the
   22-record corpus's actual scenarios; no confident call either way.
3. Flag: this commit is the one most likely to interact unpredictably with
   README §8's existing WP4 SR-chain findings (both the negative
   load-inversion result and the qfi8/qfi9 regression anomaly) — recommend
   re-checking those specific scenarios after this commit lands, not just
   the generic corpus diff.

---

## 5. `metric_panel.yml` — no promotions (Decision 6)

No metric's `requires:` names WP5; none flip status. The metrics whose
*accuracy* (not gating status) changes materially once commits 4a/4b land:
M01, M02, M06, M09, M10, M11, M12, M13, M14, M15, M17 — every metric that
touches latency, PDB, throughput, or PRB/CCE utilization. M04 stays
`proxy` (WP5 doesn't touch it, same as WP7's deliberate non-bundling). M03,
M07, M08, M16 expected roughly inert (no direct HARQ-timing dependency in
their definitions) — not confidently predicted either way, low priority to
verify.

---

## 6. Flags — out of order, blocked, or needing sign-off before coding

1. **`bler_sigmoid` vs. `bler_for_mcs` (Decision 1b)** — recommendation
   made, not confirmed. Needs sign-off before commit 2.
2. **OLLA bug #2 is blocked** on WP1's `shrink_to_power_budget` activation,
   itself out of WP5's charter (Decision 5) — new README §8 item, not
   silently dropped or bundled.
3. **The charter's literal "`scheduler/reservation.py`, `two_tier.py`"
   naming is stale** for this branch's actual phase ordering; resolved via
   the orthogonal driver-level pattern (Decision 4), not a blocker.
4. **`metric_panel.yml`'s deadline/latency metrics show `ok` while
   HARQ-blind** (Decision 6) — flagged, not resolved; a status/definition
   question outside this plan's authority to settle unilaterally.
5. **The IR/Chase dB constants are an unsourced literature approximation**
   per the mined branch's own §11 caveat (Decision 1) — ported anyway (no
   better numbers exist), flagged in code + a new README §8 item.
6. **k1_slots/k2_slots defaults (4 and 2) are representative midpoints of
   real per-transmission-selectable ranges, not confirmed deployed values**
   (Decision 3) — same honesty standard as `sr_period_slots`.

Nothing else found blocked. WP5 has no dependency on WP6 (channel) or
WP-Join, and — per Decision 4 — no dependency on Phase 2 either, despite
the charter's literal wording suggesting otherwise.
