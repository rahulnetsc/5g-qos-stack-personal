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
processes — real OAI's own fallback-when-unconfigured defaults are
**asymmetric by direction: 8 for DL, 16 for UL** (not one shared spec-
ceiling value; see Decision 2 for the exact citation). Each process is either free, or
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

**Saturation beyond the table, flagged explicitly (not just inherited):**
`.get(retx_count, _IR_GAIN_DB[3])` clamps every attempt past the third to
the *same* `8.0 dB` (IR) / `retx_count × 3.0 dB`-uncapped (Chase) bonus —
ported as-is from the branch, not derived. This matters because the table
only goes to `retx_count=3` while the real retry cap is `harq_round_max`
(§2), a config value with no vendored default confirmed here — if a
scenario's `harq_round_max` exceeds 4, every attempt past the third gets an
identical, unvarying, uncalibrated bonus rather than a value that
continues to reflect diminishing returns. `sim/harq.py`'s docstring must
state this explicitly next to the table, not leave it to be discovered by
reading `.get()`'s fallback argument.

**Not built at all, per explicit rejection:** the reachability-weighted
`effective_SE(Δ)` formula, neither as the driving mechanism nor as a
derived/reported diagnostic — it has no provenance anywhere on disk, and no
`metric_panel.yml` entry would consume it as a diagnostic.

### Decision 1b — resolved: compose with today's `bler_for_mcs`; `bler_sigmoid` is not reintroduced

The mined branch's combining-gain mechanism is paired with its own BLER
curve, `bler_sigmoid(delta_snr_db)` — a sigmoid keyed on instantaneous-SNR
deviation from a per-UE EWMA, flat 10% at zero deviation. **This predates
the current codebase's actual BLER mechanism.** `scheduler/link.py` today
has `bler_for_mcs(mcs_threshold_db, true_snr_db, base_bler=0.10)` — a
different, already-shipped, already-tested model: BLER doubles per dB of
shortfall between the scheduler's picked-MCS threshold and the true SNR
(WP1/WP4-era, postdates the May-2026 branch).

**Decided: compose, don't reintroduce.**
`bler_for_mcs(mcs_threshold_db, true_snr_db + combining_gain_db(retx_count,
mode))` — combining gain is an SNR-domain quantity, so it adds into the
existing curve's SNR argument rather than needing a second curve.
`bler_for_mcs` is the shipped, tested model every current result depends
on; two BLER curves differing only by which commit wrote them is the same
problem WP7 solved by unifying its jitter distributions onto one shared
helper (`_clipped_gaussian_jitter_ms`) rather than writing a second one per
generator. `bler_sigmoid` is not ported.

**Flagged, not a blocker: this composition stacks three uncalibrated
constructs into one modelled probability** — `bler_for_mcs`'s
doubles-per-dB slope, the `{0, 4.0, 6.5, 8.0}` dB IR table (Decision 1),
and `base_bler=0.10`. Each is individually flagged already (in this
document and in `scheduler/link.py`'s own docstrings); the *composition*
had not been, anywhere, until now. Recorded as its own new `README.md` §8
`[OPEN]` entry (landed alongside this document's own commit) rather than
left implicit across three separate places.

### Decision 2 — process pool size `N`: real OAI fallback defaults, asymmetric by direction — DL 8, UL 16

Real OAI sizes `available_dl_harq`/`available_ul_harq` from UE-capability
config, and the config accessor's own fallback-when-unconfigured values
**are** vendored and findable — `nr_mac_common.c:2724-2744`:

```c
2724	// 32 HARQ processes supported in rel17, default is 8
2725	int get_nrofHARQ_ProcessesForPDSCH(const NR_UE_ServingCell_Info_t *sc_info)
2726	{
2727	  if (sc_info && sc_info->nrofHARQ_ProcessesForPDSCH_v1700)
2728	    return 32;
2729	  if (!sc_info || !sc_info->nrofHARQ_ProcessesForPDSCH)
2730	    return 8;
2731	  int IEvalues[] = {2, 4, 6, 10, 12, 16};
2732	  return IEvalues[*sc_info->nrofHARQ_ProcessesForPDSCH];
2733	}
2734	
2735	// 32 HARQ processes supported in rel17, default is 16
2736	int get_nrofHARQ_ProcessesForPUSCH(const NR_UE_ServingCell_Info_t *sc_info)
2737	{
2738	  if (sc_info && sc_info->nrofHARQ_ProcessesForPUSCH_r17)
2739	    return 32;
2740	  return 16;
2741	}
```

This is a stronger citation than "the spec ceiling" — it's OAI's own
code-level behavior when RRC doesn't explicitly configure a count, and
**it's asymmetric**: DL defaults to **8**, UL to **16**, both capped at 16
pre-Rel17 (32 if the `_v1700`/`_r17` extension fields are set — not
confirmed present or absent for this deployment). `gNB_scheduler_
primitives.c:2613-2668` also independently clamps `nrofHARQ > 16 → 16` for
non-`dci_00_10` formats before sizing `available_dl_harq`/`available_ul_
harq`, confirming 16 is a real ceiling in the code path that actually
allocates the process lists, not just the accessor's return value.

**Decided:** `HarqProcessPool` takes separate `dl_capacity: int = 8`,
`ul_capacity: int = 16` (not one shared `N`), as config-swept knobs
(matching `sr_period_slots`/`cqi_delay_slots` precedent). **This is a
different claim from a flagged, ungrounded default**: these are OAI's own
fallback values for an unconfigured deployment, cited exactly above — what
remains unconfirmed is only whether *this specific* deployment's RRC
overrides them (via `nrofHARQ_ProcessesForPDSCH`'s `{2,4,6,10,12,16}` index
or the Rel17 extension fields), not whether the fallback numbers themselves
are real.

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
  §2) is self-contained — it needs nothing outside WP5's own files
  (`sim/harq.py`/`sim/driver.py`/the new `sim/olla.py`), no scheduler or
  buffer changes. **Correction, found scoping commit 6**: "reads the
  round-count state... WP5's own HARQ engine produces as a byproduct"
  overstated what already existed — nothing in commits 1-4b tracks a
  cumulative, windowed history of transmissions vs. first-retries per UE;
  `HarqProcess.retx_count` is per-in-flight-process and resets on
  `free()`. Commit 6 adds this bookkeeping fresh (`OllaRoundCounters`,
  `sim/olla.py`) rather than reusing something already produced. "Self-
  contained" (no cross-cutting dependencies) still holds; "already
  produced as a byproduct" did not, and is corrected here rather than
  left standing. It also now has
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

### Decision 5b — bug #1 lands dormant, not wired into grant sizing

Found scoping commit 6, not anticipated when Decision 5 was written: real
`get_mcs_from_bler`'s ratcheted MCS reaches exactly one call site (it
directly becomes the grant's MCS before TBS sizing). This simulator has no
persistent per-UE MCS anywhere grant sizing reads — link adaptation here
is stateless, a pure function of instantaneous (possibly CQI-delayed) SNR.
The only zero-scheduler-change route to feed a ratcheted value in is
wrapping `ChannelModel.get_reported_snr_db()`, matching the pattern
already used for HARQ (`HarqAwareBufferView`, `ReducedSlotView`) — but
every current scheduler calls that same method for things that are not
MCS selection: PF's ranking, `TwoTier`'s `_r_avg`, Tier-1's capacity
estimates. Wrapping it would feed OLLA's ratcheted value into every one of
those unrelated reads too. That is not a fidelity trade-off between two
honest options — it is a different mechanism wearing OLLA's name, with a
failure mode no test would catch and no metric would attribute to OLLA.

**Decided: land the ratchet dormant, matching WP1's `sim/power.py`
precedent exactly** — pure functions/dataclasses (`sim/olla.py`),
unit-tested against the C's exact -1/+1 asymmetry, zero `sim/driver.py`
changes, not wired into any scheduler. Activation belongs in Phase 2's
fresh scheduler rewrite, where MCS selection can live at the one call
site it actually needs to, not bolted on via a wrapper that leaks into
unrelated call sites. New README §8 `[OPEN]` item records this, plus the
compounding-vs-coincidence test (§4 below) that couldn't run without live
wiring, so Phase 2 doesn't have to re-derive it.

### Decision 6 — resolved: no status change; a new `caveats:` field instead — landed ahead of commit 1

Checked every metric's `requires:` field directly (17 entries, checked
against the file, not memory) — **none names WP5.** WP5 therefore promotes
**zero** panel statuses by the letter of the rule. This surfaced a real
tension with the charter's own text — *"BLER is currently a scalar discount
with no retransmission... every deadline result on this branch is
unreliable until this lands"* — while M01/M02/M14/M15 (M13 needs a
load-ramp study, not scored per-run, so it's excluded here) already show
`status: ok` today, silently HARQ-blind.

**Decided: not a status change.** Reverting to `proxy` would be wrong —
these metrics *are* computed exactly from true per-message data; the gap
is a missing simulator mechanism (no HARQ yet), not a measurement
approximation, and collapsing the two loses information `status` exists to
carry. Instead: `config/metric_panel.yml` gains an additive `caveats:`
field (list of str, optional, empty for most metrics) — M01/M02/M14/M15
each get a `caveats` entry stating "HARQ-blind until WP5 commits 4a/4b
land," with the concrete mechanism named. `sim/scorecard.py::Scorecard.
score()` attaches every metric's caveats list to its `MetricResult`
unconditionally (empty list otherwise) so a caveat travels with the value
the same way M03/M14's `t_live_s`/`survival_time_ms` already do — never a
bare number. Same treatment M04's proxy-vs-ok gap got: recorded rather than
quietly resolved either direction. **Landed** in its own small commit
before commit 1 (`config/metric_panel.yml`, `sim/scorecard.py`,
`sim/tests/test_scorecard.py`) — pre-registration holds, since this is
purely additive.

---

## 4. Commit checklist

| # | Commit | Files | Wired live? |
|---|---|---|---|
| 0 | Panel `caveats:` field (M01/M02/M14/M15) + `Scorecard` wiring — **landed** | `config/metric_panel.yml`, `sim/scorecard.py`, `sim/tests/test_scorecard.py` | N/A — scoring-layer only, `regression_corpus.py` never calls `Scorecard.score()` |
| 1 | `HarqProcess`/`HarqProcessPool` core state (asymmetric `dl_capacity=8`/`ul_capacity=16`, Decision 2) + `combining_gain_db()` | `sim/harq.py` (new), `sim/tests/test_harq.py` (new) | No — dormant, unit-tested only (WP1 precedent) |
| 2 | `Allocation.harq_pid`/`is_retx` fields; `bler_for_mcs_with_combining()` composition (Decision 1b) | `scheduler/interfaces.py`, `sim/harq.py` (**not** `scheduler/link.py` — see correction below), tests | No — new optional fields default to old behavior; `bler_for_mcs` itself untouched, composition uncalled until 4a/4b |
| 3 | Process-pool gating on new-data grants (no multi-slot delay yet) — **landed** | `sim/driver.py` | Live, but **designed to be inert** — delivery still synchronous, so the pool never actually binds |
| 4a | Deferred drain + real multi-slot retry, **DL** | `sim/driver.py`, `sim/metrics.py` (`bytes_harq_retx`/`bytes_harq_lost` counters) | Live — the big DL fidelity landing |
| 4b | Deferred drain + real multi-slot retry, **UL** — resolves the `sched_ul_bytes`/k2-HARQ gap `sim/bsr.py`'s own docstring flags (CLAUDE.md known issues) — **landed** | `sim/driver.py`, `sim/harq.py` (`ul_split`, UL masking, `draw_dl_outcome`→`draw_harq_outcome` rename), `sim/tests/test_ul_access.py` (threshold+docstring) | Live — the big UL fidelity landing |
| 6 | OLLA bug #1 only (`get_mcs_from_bler`'s round-count ratchet) — **landed, dormant** | `sim/olla.py` (new) — **not** `scheduler/link.py` or `sim/driver.py` (Decision 5b) | No — dormant, unit-tested only (WP1 `sim/power.py` precedent) |

**Note on 4b and `sim/bsr.py`:** `BsrModel.on_ul_grant`'s `sched_ul_bytes +=
tb_size` credit fires **at grant time** in real OAI (already faithfully
ported, WP3) — this must **not** change under WP5; only the physical
buffer drain (and `ue_lcp.fill()`'s per-flow split feeding it) defers to
ACK. Getting this wrong would silently break WP3's already-verified BSR
port.

**Commit 0 — landed** (`fc719d7`). Scoring-layer only; `regression_corpus.
py` never calls `Scorecard.score()`, so no prediction was even needed —
confirmed by running both anyway: `pytest sim/tests -q` 216 passed,
`--check` clean.

**Commit 1 — landed.** `sim/harq.py` (`HarqProcess`/`HarqProcessPool`,
asymmetric `dl_capacity=8`/`ul_capacity=16`, `combining_gain_db`) +
`sim/tests/test_harq.py` (13 tests). **Predicted, before writing any code:
fully clean `--check`, same as WP7 commits 3/5** — new, unimported by
`driver.py` or any scenario/scheduler. **Confirmed exactly:** `pytest
sim/tests -q` 229 passed (216 + 13 new), `regression_corpus.py --check`
clean, zero mismatches.

**Correction found scoping commit 2, before writing any code:** this
table originally placed the `bler_for_mcs`/`combining_gain_db` composition
in `scheduler/link.py`. `scheduler/interfaces.py`'s own docstring states
the package must "depend on nothing outside itself"; `scheduler/link.py`
today imports nothing from `sim/` (checked directly — zero hits), and
putting the composition there would need `from sim.harq import
combining_gain_db`, the first `scheduler` → `sim` dependency ever. The
composition instead lives in `sim/harq.py` (already importing nothing
from `sim.driver`/etc.; adding `from scheduler.link import bler_for_mcs`
matches the allowed, already-established direction `sim.driver` uses).
`sim/harq.py`'s own docstring is corrected to stop claiming "no simulator
or scheduler imports."

**Commit 3 — landed.** First WP5 commit to touch `sim/driver.py`.
**Falsifiable inertness argument, made precise before writing any code:**
every `Allocation` the existing per-slot loop processes is wrapped —
unmodified in between — with one `harq_pool.allocate(...)` immediately
before its existing (untouched) delivery logic and one `harq_pool.free
(...)` immediately after, **within that same loop iteration**, before the
next `Allocation` (even one for the identical `(ue_id, direction)` key) is
reached. Consequently occupancy for any key never exceeds 1 at any instant
`allocate()`/`exhausted()` could observe it — a structural property of the
code (sequential allocate-then-free, never allocate-allocate-then-
free-both), true for *any* scenario, not contingent on which 22 happen to
be in the corpus. Since `dl_capacity=8`/`ul_capacity=16` (Decision 2) are
both `>= 1`, `allocate()` can therefore never return `None` under this
discipline — `harq_exhausted_count` is counted (real OAI's own
`harq_exhausted` diagnostic, `ia_p5g_scheduler.c`) but unreachable this
commit **by construction**. It would have bound only under a different,
not-chosen design (e.g. allocating for every `Allocation` up front and
freeing them all at slot-end).

**Scope confirmed:** the wrap adds two bookkeeping lines around each
iteration and changes zero lines of the existing body (BLER computation,
`ue_lcp.fill`/`buffers.drain`, `bsr.on_ul_grant`, `ul_access.on_ul_grant`,
`metrics.record_*`, PRB/CCE accounting). Exhaustion is counted, not
enforced — blocking delivery on it would itself be a behavior change, out
of scope until 4a/4b give exhaustion something to actually bind on.

**Two counters, not one, and why:** `summary["harq_exhausted_count"]`
alone would pass trivially if gating silently never ran at all (a wiring
bug), which is a different failure than "runs but never binds" — added
`summary["harq_allocate_calls"]` alongside it so a test can tell the two
apart. Neither is threaded into `RunRecord` (`RunRecord.from_summary` only
reads keys it names explicitly, same idiom as `_ue_lcp`/`_message_ledger`)
— this is *why* `--check` stays fully clean rather than "clean but for one
new trivial field" (WP7 commits 4/6/7/8's pattern for a field that *does*
reach `RunRecord`).

**Test, on the scenario the argument actually turns on:** `sim/tests/
test_smoke.py::test_wp5_harq_process_pool_gating_is_live_but_never_binds`
runs `factory_robots_scenario` (README §8: the one scenario with
multi-flow UEs sharing a slot, UEs 8/9/10) through `RoundRobin`, and
asserts both `harq_allocate_calls > 0` (gating is actually live) and
`harq_exhausted_count == 0` (it never bound) — exercising exactly the
"2+ Allocations for one key in one slot" case that would break occupancy
≤ 1 under the not-chosen design, not an arbitrary scenario that happens
not to.

**Predicted, before writing any code: fully clean `--check` — the 13th
such prediction in this WP7/WP5 lineage. Confirmed exactly:** `pytest
sim/tests -q` 237 passed (236 + 1 new), `regression_corpus.py --check`
clean, zero mismatches.

**Commit 2 — landed.** `Allocation.harq_pid: int = -1`/`is_retx: bool =
False` (`scheduler/interfaces.py`) + `bler_for_mcs_with_combining()`
(`sim/harq.py`) + `sim/tests/test_interfaces.py` (new, 3 tests) +
`sim/tests/test_harq.py` (4 more tests). **Predicted, before writing any
code:** (1) the two new `Allocation` fields are inert — every current
`Allocation(...)` construction site (`scheduler/two_tier.py`,
`sim/baselines/_mac.py`) uses all-keyword args, confirmed by grep before
writing, so appending defaulted fields changes nothing; (2)
`bler_for_mcs_with_combining` cannot be reached with `retx_count > 0` by
anything today, not because no caller happens to pass one, but because
**nothing calls it at all yet** — it's a new sibling function,
`bler_for_mcs` itself stays byte-for-byte unmodified (confirmed: its only
real call site is `sim/driver.py:148`, untouched this commit). Predicted
fully clean `--check`. **Confirmed exactly:** `pytest sim/tests -q` 236
passed (229 + 7 new), `regression_corpus.py --check` clean, zero
mismatches.

**Predicted metric movement, ranked by confidence within each commit.**
Commits 2-3 predicted **fully clean** `--check` — falsifiable, no scenario
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

**Commit 4a — landed.** Scored against the actual 7,042-mismatch
`--check` diff (22 records, before `--capture`):

| # | Predicted | Actual | Verdict |
|---|---|---|---|
| 1 | M02 up | `bytes_dropped_pdb` 129↑/77↓, `bytes_delivered_late_pdb` 67↑/43↓ | **Held** |
| 2 | M01 p95/98/99 up, p50 flat | p50 86↑/**244↓**; p95/98/99 also skew down (~60% of moves) | **Missed** |
| 3 | M11 up | **19/19 (100%) down** | **Missed** |
| 4 | M10 up, not down | `bytes_delivered` 251↑/150↓, `delivery_ratio` 243↑/145↓ | **Held** |
| 5 | M12 up | **19/19 (100%) down** | **Missed** |
| 6 | M06/M17 inert (no `xr_video` in corpus) | zero `frame_completions`/`xr_frame_period_ms` hits | **Held** |
| 7 | M09 broader variance | **untested — see below**, not scored held/missed | **Untested** |
| 8 | PF-arm UL perturbed via `_r_avg` | `PF.ue10_qfi2` (UL, GBR): `bytes_delivered` 0→4939 | **Held**, on a real flow |
| 9 | `harq_exhausted_count` can now fire | **0 across all 22 cases** — never fired | **Missed as stated** |

**Headline result, not a footnote: #2/#3/#5 missing is one mechanism, not
three, and it is the real finding of this commit.** Switching DL delivery
from `bytes_capacity * (1 - bler)` (a partial fraction on *every* grant,
success or not) to a full-byte stochastic draw means a successful attempt
now completes a chunk in one grant instead of several. Across this
corpus, that speed-up dominates the added retry delay for most flows,
pulling p50, the percentile tail, PRB utilization, and CCE utilization
downward on net — the retry-delay mechanism only wins out in the minority
of flows that actually retry heavily (e.g. `study3/latency_bound/TwoTier.
ue6_qfi1`: `p99` 5.0→11.5ms) or exhaust (`bytes_harq_lost` fired on
exactly **6 of 510** flow-records — `harq_round_max=4` exhaustion is real
but rare at these BLERs). **Read plainly: this branch's pre-4a latency
numbers were shaped more by the fractional-delivery model's own artifact
— every grant "completing" only part of a chunk regardless of channel
quality — than by anything physical.** WP5 didn't just add a delay
mechanism; it removed a different, larger, unphysical one that was
already there.

**#9 as stated didn't happen — pool-wide exhaustion never fired — but a
different counter did, heavily: `harq_masked_flow_double_grant_count` =
3,628 across 13 of 22 cases, all `TwoTier`.** Traced to `scheduler/
two_tier.py::_allocate_sps` pooling a UE's SPS-eligible flows into one
grant sized off their *summed* backlog, defeating single-flow masking
without corrupting FIFO order (the defensive guard catches it before any
`drain()` call). Recorded as a new `README.md` §8 `[OPEN]` item with the
full mechanism, measured scale, and an explicit instruction that Phase
2's rewrite must not reintroduce it — **deliberately not fixed**:
`_allocate_sps` is exactly the SPS machinery CLAUDE.md already says
shouldn't exist (real hardware two-tier defers it to a Phase 2 that was
never built), so fixing accounting drift in a doomed code path, at the
cost of Decision 4's "zero scheduler changes" claim, is the wrong trade.
`harq_masked_flow_double_grant_count` is kept as a **permanent**
diagnostic (confirmed 0 on PF/RoundRobin/Gradient across the full
corpus) — a Phase-2 regression check, not one-off debugging.

**Prediction #7 (M09) — untested, and this is a gap in the corpus itself,
not something to keep re-flagging per-WP.** `config/metric_panel.yml`
gates M09 on `record_timeseries=True`; `scripts/regression_corpus.py::
collect_records()` never passes it, so **no WP's regression-corpus
`--check` can ever move M09 — this isn't specific to WP5.** M09 is
checkable in principle (`sim/tests/test_scorecard.py` already exercises
it directly against a `record_timeseries=True` run), just not through
this corpus. Recording here rather than leaving it to look like WP5's own
gap; whoever next needs M09 regression coverage should add a
`record_timeseries=True` case to the corpus, not assume one exists.

**The one test failure investigated, not left unexplained:**
`test_latency_bound_two_tier_protects_deadlines` (`TwoTier on_time > PF`)
now ties 5=5. Checked directly against the pre-4a commit (`3cfd0c0`, via
a throwaway `git worktree`): **PF is unchanged, 5→5. TwoTier degraded,
8→5** — this is 100% TwoTier-side movement, not PF catching up. The
three flows TwoTier lost dropped below the test's `delivery_ratio >=
0.99` bar (down to 0.971-0.979), and two of the eight flows show nonzero
`bytes_harq_lost` (519 bytes each) in this specific run, alongside 552
`harq_masked_flow_double_grant_count` hits — a mix of genuine new
HARQ-loss fidelity and the SPS finding above, on the one scenario
literally named for tight PDB constraints, exactly where HARQ RTT
competing with PDB is supposed to bite hardest per the acceptance
criterion. Not a new bug — the assertion's strict `>` no longer holds
given a real fidelity change plus a knowingly-not-fixed doomed-path
limitation; loosened to `>=` with a comment recording why, rather than
left red or silently strengthened.

The SAME test also had a second, stronger claim (`on_time(tt) ==
len(delay_keys)`, TwoTier holds *all 8* deadlines) that fails by a wider
margin (5/8) and was not part of what was asked to be investigated — split
into its own `sim/tests/test_smoke.py::
test_latency_bound_two_tier_holds_every_deadline`, marked `xfail(strict=
True)` with the same reasoning recorded inline, rather than silently
loosened alongside the first or left failing the whole suite. Whether
"holds every deadline" is still the right bar for TwoTier post-HARQ is an
open decision, not resolved by this commit.

**Final state:** `pytest sim/tests -q` — 237 passed, 1 xfailed.
`regression_corpus.py --capture` run and `--check` reconfirmed clean
against the new baseline.

*Commit 4b (UL) — revised before writing code, per commit 4a's real
lesson (fractional->binary dominates the retry mechanism itself):*
1. (Revised, was "High, up") M01/M02 for UL flows — **not a clean "up"**,
   same reason as 4a: p50/utilization likely skew DOWN in aggregate (full
   TB fill replaces a fractional discount) with only a minority of
   heavily-retrying flows showing worse tails. Predicting the mixed shape
   directly this time instead of repeating 2/3/5's miss.
2. (Revised, was "should be flat") `sched_ul_bytes` crediting timing is
   unchanged (still fires once, at grant time, per WP3's port) — **but
   the AMOUNT it credits is not flat.** Pre-4b, `ue_lcp.fill()` was called
   with the BLER-discounted `delivered` amount, not the full
   `bytes_capacity` -- double-counting BLER (once by under-filling the TB
   before LCP, which isn't how a real UE behaves -- it fills the whole
   granted TB regardless of predicted outcome -- and again via the
   fractional "delivered" concept itself). Commit 4b fixes this
   alongside adding retry: `fill()` now gets the full `bytes_capacity`.
   Expect `sched_ul_bytes`/crumb-fraction-adjacent numbers to move for
   this reason even setting HARQ retry aside.
3. (Moderate) Crumb fraction (README §8's long-open item) — plausibly
   closer to hardware's 48-52% now that real k2/HARQ pipelining exists
   AND item 2's fuller-fill effect, both candidate contributors named in
   that item's own text. Stated as a hypothesis to check against
   `--check`, not asserted.
4. (Low) `sim/ul_access.py` SR-chain interaction — masked in-flight bytes
   could make a UE's visible backlog look emptier at moments it wasn't
   before, plausibly triggering extra SR events; no directional call --
   check directly against `test_ul_access.py`'s scenarios.
5. (New) Given 4a's `harq_masked_flow_double_grant_count` finding was
   TwoTier-SPS-only and UL GBR flows can also be SPS-eligible, expect the
   SAME counter to fire on UL grants too, on the same TwoTier cases --
   not a new bug, the same README §8 item extended to UL.

**Commit 4b — landed.** UL deferred drain + real HARQ retry: per-flow
`ul_split` replay (the UE's own LCP decision at grant time, never redone
at resolution -- `HarqProcess.ul_split`), per-UE full masking (matching
DL's per-flow masking, at the granularity UL grants actually happen at),
and the same preemption/exhaustion resolution as 4a, generalized in
`draw_dl_outcome` -> `draw_harq_outcome` (renamed -- it was never actually
DL-specific).

**Bug found and fixed before scoring anything: `harq_rng` shared between
DL and UL draws.** Once UL started consuming random draws too, the shared
stream's *interleaving order* shifted, which shifted every subsequent DL
draw in any scenario with both directions -- confirmed by `PF.flows.
ue10_qfi82`/`ue1_qfi82` (pure DL flows) moving in the `--check` diff with
zero change to DL's own mechanism. Fixed with independent `harq_rng_dl`/
`harq_rng_ul` streams (`scenario.seed ^ 0x48415251` / that XOR'd again
with `0xFFFFFFFF`), the same isolation principle as `cqi_seed`. After the
fix, PF's DL flows are exactly stable; a residual few-byte ripple remains
on **TwoTier only** (`bytes_delivered` off by 1 of 8612, sub-millisecond
delay-percentile shifts) -- consistent with, and most plausibly explained
by, TwoTier's Tier-1 LP jointly solving DL+UL capacity (a pre-existing,
legitimate coupling: adding UL retransmission PRB consumption changes the
total UL demand fed into that joint solve). **Not fully isolated as a
code-level certainty**: no corpus scenario runs a coupling-free scheduler
(RoundRobin) on mixed UL+DL traffic, since `sensor_dense_scenario` (study
2) is UL-only and `latency_bound_scenario` (study 3) is DL-only -- the
only two schedulers on mixed-direction traffic in this corpus
(`factory_robots_scenario`, study 1) are PF and TwoTier, both of which
have their own independently-documented reason for some cross-direction
coupling. Flagged here rather than claimed with more certainty than the
evidence supports.

**Prediction scorecard**, scored against the final `--check` diff (6,394
mismatches, `harq_rng` fix included):

| # | Predicted | Actual | Verdict |
|---|---|---|---|
| 1 | Mixed M01/M02 for UL, not clean "up" | p50 70↑/**173↓**; p98 **216↑**/98↓; p99 194↑/129↓ -- genuinely mixed, not one direction | **Held** |
| 2 | `sched_ul_bytes` AMOUNT not flat (full-TB-fill fix) | Not directly observable in `RunRecord` (internal BSR state); crumb-fraction shift (#3) is consistent, indirect evidence | **Held, indirect evidence only** |
| 3 | Crumb fraction closer to hardware | Measured directly: 4.4503% (WP4) → **5.1233%** (162/3162, `factory_robots_scenario`/`TwoTier`@1.0×), mean crumb size 146.03→135.38 bytes | **Held** — still ~10x short of hardware's 48-52% |
| 4 | SR-chain interaction, no directional call | Real, and larger than "some extra SR events": full masking blocks the SR-triggered fresh-grant path for the whole retry cycle -- see the new README §8 finding below | **Held, and is now the commit's second headline finding** |
| 5 | SPS/double-grant extends to UL | `harq_masked_flow_double_grant_count`: 3,628 (4a) → **7,092** (4b), incl. 1,220 on `study2/pdcch_limited` (all-UL) | **Held** |

**New finding, not predicted, recorded in `README.md` §8 (not repeated in
full here): full masking can make MORE retry attempts WORSE for delivery
ratio on cold-start-heavy UL traffic.** Measured on `sensor_dense_
scenario`/`ProportionalFair`: `harq_round_max=4` (default) → 0.471 mean
delivery; `harq_round_max=1` (no retry) → 0.576; `k2_slots=1` (default 2)
→ 0.667. Confirmed not cross-flow compounding (zero UEs in that scenario
have >1 UL flow). Masking is not weakened and `k2_slots`'s default is not
changed -- both would trade a correctness requirement or an honest
no-ground-truth parameter for a metric. README §8 also connects this to
WP4's load-inversion negative result and the crumb-fraction shortfall as
one "access chain dominates at low load / for small messages" hypothesis
for WP9, rather than three separately-filed items.

**Confirmed the mechanism is genuinely live beyond the one scenario
investigated**: `bytes_harq_lost` (UL) now fires nonzero on multiple
flows across `study1`/`study2` (e.g. `study1/overload_mult3.0/TwoTier.
ue1_qfi2`: 462 bytes; `study2/pdcch_limited/TwoTier.ue11_qfi1`: 169
bytes) -- real UL residual loss under `harq_round_max=4`, not confined to
the sensor-dense stress case.

**Test fallout, investigated and fixed with both a threshold and a
docstring change, not just one:** `sim/tests/test_ul_access.py::
test_sr_retires_the_cold_start_deadlock_without_it` failed (mean delivery
47.1%, threshold was `> 0.6`). Its own docstring told the WP4 "~50%
mean -> ~82% mean" story as the *current* regime -- now stale, since
retry/masking depresses absolute delivery back down. Loosened the
threshold to `0.4` (comfortably below 0.471, still a real regression
guard) **and** rewrote the docstring to say the SR mechanism still works
structurally (retires the deadlock, ~10x over the no-SR case -- the
OTHER two assertions in the same test still prove this, unaffected), but
absolute delivery is now further depressed by the commit-4b retry/
masking interaction, pointing at the new README §8 entry. A loosened
threshold under an unchanged docstring is exactly how a number ends up
quoted later without its caveat (README §7/§8's two-number-sweep-summary
lesson) -- checked that this test has no second, stronger assertion to
split out the way 4a's TwoTier test did (it doesn't: the other two
assertions already pass).

**Final state:** `pytest sim/tests -q` — 237 passed, 1 xfailed (the 4a
xfail persists unchanged). `regression_corpus.py --capture` run and
`--check` reconfirmed clean against the new baseline.

*Commit 6 (OLLA bug #1) — original pre-code predictions, superseded, not
deleted:* the three predictions below (M01/M02 worse for low-rate flows,
uncertain M10/M11 direction, unpredictable interaction with WP4's SR-chain
findings) all assumed the ratchet would be *wired into grant sizing*.
Scoping the commit found that wiring it in without touching scheduler
code requires wrapping `ChannelModel.get_reported_snr_db()`, which bleeds
into unrelated scheduler logic (PF's ranking, `TwoTier`'s `_r_avg`,
Tier-1's capacity estimates) — Decision 5b, decided with the user: land
the ratchet **dormant** instead, matching WP1's `sim/power.py` precedent.
Recorded here rather than silently dropped, since the reasoning (low-rate
flows are the ones the ratchet targets, and it could compound with the
access-chain finding on the same UEs) is still correct and still relevant
— to Phase 2, once OLLA is actually wired in.

**Revised prediction, made before writing code: fully clean `--check` —
the 14th such prediction in this lineage, and the strongest form of it.**
Every prior "predicted clean" commit (WP7 commits 1/3/9, WP5 commits 0-3)
was clean because no scenario referenced a new field yet, even though the
new code was reachable from `driver.py`. This one is stronger: `sim/
driver.py` is not touched *at all* this commit, so there is no code path
by which anything in `sim/olla.py` could run during a `driver.run()` call,
regardless of scenario. Falsifiable the same way as every prediction in
this lineage — if any driver-reachable code path is later found calling
into `sim/olla.py`, the "dormant" claim is wrong and must be retracted.

**Commit 6 — landed.** `sim/olla.py` (new, dormant): `OllaRoundCounters`
(cumulative `rounds0`/`rounds1`, `record_new_tx`/`record_first_retry`),
`OllaOptions`/`OllaState` (mirroring `NR_bler_options_t`/`NR_bler_stats_t`),
`init_olla_state` (mirrors `init_bler_stats` — seeds at `min_mcs`),
`update_mcs_from_bler` (the ratchet itself, bug-for-bug per
`gNB_scheduler_primitives.c:787-822`). `MCS_INDEX_COUNT = 12` gives
`_MCS_TABLE`'s implicit row ordering explicit indices for the ratchet to
operate on, without importing that private table across modules — checked
directly against it in a test instead (`sim/tests/test_olla.py::
test_mcs_index_count_matches_the_shared_table`), same discipline
`sim/bsr.py`'s own vendored-table tests use.

13 new tests, covering: the `-1`-on-either/`+1`-on-both asymmetry
(isolating each disjunct separately, including the case where good BLER
alone would have qualified for `+1` but low activity forces `-1` instead);
the idle-UE case (`num_dl_sched=0`, confirmed the EWMA becomes a literal
no-op on `bler` while `mcs` still ratchets down); strictly-`+1`-per-window
climb-back (three consecutive favourable windows, asserted `[1, 2, 3]`,
never a jump); `min_mcs`/`max_mcs` floors/ceilings; the per-call `max_mcs`
parameter being clamped by `options.max_mcs`, not the reverse; the
`BLER_UPDATE_FRAME` gate firing at exactly the boundary and not before;
frame-counter wraparound at 1024. All 13 passed on first run.

**Predicted fully clean, confirmed exactly:** `pytest sim/tests -q` — 250
passed (237 + 13 new), 1 xfailed (unchanged from commit 4b).
`regression_corpus.py --check` — clean, no `--capture` needed (nothing
that reaches `RunRecord` changed).

**Decision 5's "self-contained" premise corrected, not silently
inherited** — see Decision 5 above: the round counts did not already
exist; commit 6 built them fresh. **Decision 5b records the dormant-
landing choice** in full, including why wrapping the channel view was
rejected rather than accepted with a caveat.

**The compounding-vs-coincidence test, recorded for Phase 2 rather than
run now** (README.md §8's new commit-6 entry has the short form; full
method here): once OLLA is wired in, compare per-UE aggregate degradation
— not per-flow — between UEs with *both* a low-rate/OLLA-ratcheted DL
flow and a low-rate/SR-access-chain-limited UL flow, against UEs with only
one condition present. Additive degradation (consistent with summing each
mechanism's isolated effect) is coincidental co-occurrence; supra-additive
degradation is a genuine interaction between the two mechanisms, worth
naming as such rather than left as three items (this one, WP4's
load-inversion result, WP3/WP4's crumb-fraction shortfall) that merely
rhyme. This can't run with OLLA dormant — recorded now so Phase 2 doesn't
have to re-derive the method, only supply the wiring.

---

## 5. `metric_panel.yml` — no promotions (Decision 6)

No metric's `requires:` names WP5; none flip status. M01/M02/M14/M15 now
carry a `caveats` entry recording their HARQ-blind gap ahead of commits
4a/4b (Decision 6, already landed). The metrics whose *accuracy* (not
gating status) changes materially once commits 4a/4b land: M01, M02, M06,
M09, M10, M11, M12, M13, M14, M15, M17 — every metric that touches latency,
PDB, throughput, or PRB/CCE utilization. M04 stays `proxy` (WP5 doesn't
touch it, same as WP7's deliberate non-bundling). M03, M07, M08, M16
expected roughly inert (no direct HARQ-timing dependency in their
definitions) — not confidently predicted either way, low priority to
verify.

---

## 6. Flags — out of order, blocked, or needing sign-off before coding

1. **Resolved:** `bler_sigmoid` is not reintroduced; combining gain
   composes with `bler_for_mcs` (Decision 1b) — confirmed, no longer open.
2. **OLLA bug #2 is blocked** on WP1's `shrink_to_power_budget` activation,
   itself out of WP5's charter (Decision 5) — new README §8 item, not
   silently dropped or bundled.
3. **The charter's literal "`scheduler/reservation.py`, `two_tier.py`"
   naming is stale** for this branch's actual phase ordering; resolved via
   the orthogonal driver-level pattern (Decision 4), not a blocker.
4. **Resolved:** `metric_panel.yml`'s deadline/latency metrics keep
   `status: ok` and gain an additive `caveats:` field instead (Decision 6,
   landed) — not a status/definition change, so pre-registration holds.
5. **The IR/Chase dB constants are an unsourced literature approximation,
   and their composition with `bler_for_mcs` compounds three uncalibrated
   constructs into one probability** (Decision 1, Decision 1b) — ported
   anyway (no better numbers exist), flagged in code + two new README §8
   items (the table itself, and the composition).
6. **k1_slots/k2_slots defaults (4 and 2) are representative midpoints of
   real per-transmission-selectable ranges, not confirmed deployed values**
   (Decision 3) — same honesty standard as `sr_period_slots`.
7. **`combining_gain_db`'s saturation beyond `retx_count=3` is ported
   as-is and interacts with `harq_round_max`** (Decision 1) — every attempt
   past the third gets an identical, uncalibrated bonus if a scenario's
   retry cap exceeds 4. Must be stated in `sim/harq.py`'s docstring, not
   left to be discovered by reading `.get()`'s fallback argument.
8. **Decision 2's `dl_capacity=8`/`ul_capacity=16` are OAI's own
   fallback-when-unconfigured values (`nr_mac_common.c:2724-2744`), not a
   confirmed value for this specific deployment's RRC config** — a
   different, stronger claim than "a flagged default": the fallback
   numbers are real cited code, only whether *this* deployment overrides
   them via RRC is unconfirmed.

Nothing else found blocked. WP5 has no dependency on WP6 (channel) or
WP-Join, and — per Decision 4 — no dependency on Phase 2 either, despite
the charter's literal wording suggesting otherwise.

---

## 7. Status

All commits in the charter's own numbering (0, 1, 2, 3, 4a, 4b, 6 — the
gap at 5 is the charter's own numbering, not a skipped commit) are landed.
What's left, explicitly not silently dropped:

- **OLLA bug #2** (power-headroom-forces-MCS-down) — blocked on WP1's
  `sim/power.py` activation, out of WP5's charter (Decision 5).
- **OLLA bug #1's grant-sizing wiring** — deliberately dormant (Decision
  5b); belongs to Phase 2's fresh scheduler rewrite.
- **The compounding-vs-coincidence test** (README §8, this doc's commit 6
  section) — designed, can't run until OLLA is wired in; Phase 2's job.
- **The SPS/masking accounting-drift finding** (README §8, commits 4a/4b)
  — deliberately not fixed; Phase 2's rewrite must not reintroduce it.
- **The compound-uncertainty in the combining-gain composition** (README
  §8, Decision 1/1b) — ported anyway, flagged, revisit only if any of the
  three composed constructs is recalibrated.
- **UL split-preemption's DL/UL asymmetry** — fully solved for both
  directions as of commit 4b; nothing outstanding here specifically, but
  worth remembering if a future WP adds a third traffic direction or
  multi-connectivity concept that this design didn't anticipate.
