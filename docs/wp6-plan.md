# WP6 plan — Channel

**Provenance.** Written before any code, per CLAUDE.md's standing rule and
this session's own instruction ("Write `docs/wp6-plan.md` BEFORE any code
and commit it"). Follows `docs/wp5-plan.md`'s format: ground truth cited
exactly, decisions made explicitly with alternatives surfaced, a commit
checklist with per-commit metric predictions checked against `requires:`
fields in the file (not memory), and ranked falsifiable predictions.

Scope per README §4 and `p5g-sim-plan.md` §9 WP6 (lines 547-563): TR 38.901
InF path loss + two-state Markov blockage. Plus one addition not in §9:
README §6's sync-loss threshold (lines 192-199), which feeds WP-Join. Read
`README.md` (§4, §6, §7, §8), `CLAUDE.md`, and `docs/wp5-plan.md` first.

---

## 0. The naming flag — checked and resolved against spec text

Per sign-off: (a) checked whether anything in this repo or `oai-branches/`
cites TR 38.901 §7.2/§7.4 directly rather than repeating this repo's own
naming — it does not (`grep -rn "38\.901\|InF-\|Table 7\.2\|Table 7\.4"`
across the whole tree hits only `README.md`, `p5g-sim-plan.md`, this
document, and three `oai-branches/two-tier/*.c` files whose matches are
false positives on unrelated citations — `TS 38.211 Table 7.4.1.1.2-3/-4`
DMRS positions, `TS 38.213 Table 7.2.1-1` PDCCH candidates, and a bare
`pathloss` variable name in `nr_ue_scheduler.c:263`'s PHR code. None is a
38.901 InF citation). (b) Rather than stop at "unverified, use repo
naming," I fetched the actual spec text — ATIS's transposition of 3GPP
TR 38.901 V16.1.0 (`ATIS.3GPP.38.901.V1610.pdf`, the ATIS/3GPP joint
document, publicly hosted), extracted with `pdftotext -layout` (the PDF's
own embedded text layer, not an OCR or LLM-summarized reading — the
extracted text preserves the spec's own Unicode math glyphs, e.g. `𝑃𝐿 =
33 + 25.5 log10(𝑑3𝐷) + 20 log10(𝑓𝑐)`, verbatim). This is no longer an
unverified recollection — it's a direct read of the primary source, cited
by table and page number below.

**Finding: the repo's own "SL/DL/SH/HH" is verifiably incomplete, not just
possibly mistyped.** TR 38.901's actual Table 7.2-4 (spec-text extract,
`38901.txt:1216-1230`, ATIS PDF p.23) defines **five** InF sub-scenarios,
not four: **InF-SL, InF-DL, InF-SH, InF-DH, InF-HH** — sparse/dense clutter
crossed with low/high BS height, *plus* a fifth, structurally different
case, InF-HH ("high Tx, high Rx" — both antennas elevated above clutter,
independent of clutter density). The repo's four-item list keeps
InF-HH but drops **InF-DH** (dense clutter, high BS) — the actual fourth
member of the clutter×height cross-product. This is exactly the
"conflating InF clutter variants (S/D × L/H) with InF-HH's antenna-
placement meaning" the sign-off named as a candidate failure mode, and
the spec text confirms it as the actual one.

**Why the omission is easy to make and easy to miss**: InF-HH is
special-cased in **both** tables that matter — Table 7.4.2-1 (LOS
probability, `38901.txt:1806-1824`, ATIS p.31) gives it
`Pr_LOS = 1` unconditionally (always LOS, no clutter-density formula
needed), and correspondingly **Table 7.4.1-1 has no NLOS path-loss row for
InF-HH at all** (`38901.txt:1671-1710`, ATIS pp.30-31) — only the shared
`PL_LOS` formula ever applies to it, since NLOS is never reached. A reader
skimming for "the four InF path-loss formulas" would see exactly four
named rows (SL/DL/SH/DH) and, without checking Table 7.2-4 first, could
plausibly mis-transcribe the fourth as "HH" from memory of the sub-
scenario *list* rather than the *path-loss table* — which is what I
suspect happened whenever this repo's own docs first wrote "HH."

**Decided, now that this is verified rather than guessed:** implement the
real five-member enum (`SL`, `DL`, `SH`, `DH`, `HH`), not the repo's
four-item list — using a known-incomplete enum in new code, once the gap
is confirmed rather than suspected, would just be re-authoring the same
mistake with better documentation. `InF-HH` gets no NLOS branch in
`sim/pathloss.py` (matching the spec: `bler`-equivalent path loss for
InF-HH is always `PL_LOS`, LOS probability always 1.0 — this is a real
simplification in the *spec's own model*, not one WP6 is introducing).
**New README §8 item, landed alongside WP6's first commit:** `README.md:
336` and `p5g-sim-plan.md:670`'s "(SL/DL/SH/HH)" should be corrected to
name the real five-member set — recorded as a doc fix, not silently
folded into this plan's own text, per the same discipline that keeps
`p5g-sim-plan.md` itself unedited as the historical record (README §0)
while README carries the correction.

---

## 1. The mechanism, plain language

**What exists today (`sim/channel.py`).** `ChannelModel` holds one
stationary AR(1) process per UE: SNR mean-reverts to a fixed per-UE
`mean_snr_db` (a `UEConfig` field, hand-authored per scenario YAML —
confirmed via `sim/config_loader.py:138-140`, which reads
`mean_snr_db` straight out of each scenario's YAML with a `20.0` fallback).
There is no concept of a UE's physical position, no path loss, no
blockage. `get_snr_db()` (true, used for BLER draws) and
`get_reported_snr_db()` (CQI-delayed, used by schedulers for MCS pick and
ranking) both derive from this one per-UE stochastic process.

**What WP6 adds — three separate mechanisms, not one:**

1. **TR 38.901 InF path loss + LOS probability.** A large-scale,
   distance-and-frequency-dependent quantity that, for a scenario that
   opts in, computes what `mean_snr_db` *would be* from UE/gNB geometry
   and a link budget, instead of a scenario author typing a number. The
   AR(1) process stays exactly as today — it is the small-scale term
   riding on top of whatever large-scale mean is in effect (`p5g-sim-
   plan.md:551`: "Keep AR(1) as the small-scale term; add ... path loss").
2. **Two-state Markov blockage.** A per-UE, per-slot {Unblocked, Blocked}
   process modelling a transient obstruction (forklift, robot arm) —
   `p5g-sim-plan.md:556-559`: "a forklift or robot arm crossing the
   path — a 15-20 dB drop lasting hundreds of milliseconds." This is a
   *dynamic* large-scale term, independent of whether path loss (a
   *static* large-scale term) is active.
3. **A sync-loss (RLF-declaration) threshold** — README §6 (lines
   192-199), not in `p5g-sim-plan.md` at all. A discrete state transition,
   separate from the continuous BLER discount: when the channel sits below
   a floor long enough, the UE declares radio link failure. Calibration
   anchor: `calibration-logs/twotier_startup_gnb.log:17`'s startup banner —
   `t300 400, t301 400, t310 2000, n310 10, t311 3000, n311 1, t319 400`
   (ms/counts), confirmed real deployed RRC/MAC timer constants (see §2).

All three compose into the *same* SNR domain `scheduler/link.py` already
consumes — see Decision 1 for why that's the right boundary and not a
second BLER curve.

---

## 2. Ground truth, cited exactly

**Calibration timers — `calibration-logs/twotier_startup_gnb.log:17`:**

```
17: [0m[GNB_APP] sr_ProhibitTimer 0, sr_TransMax 64, sr_ProhibitTimer_v1700 0, t300 400, t301 400, t310 2000, n310 10, t311 3000, n311 1, t319 400
```

Per `calibration-logs/README.md:1-31`: this is a real gNB startup log
(band 78, 106 PRB, two-tier config, `origin/feat/oai-integration:script-
logs/gnb.log`, commit `1b163d66`), confirmed as a startup banner (RRC/MAC
timer constants only), **not** a traffic-level capture — "use this file as
a guideline for timer constants, not a fit target." Units: `t3xx` in ms,
`n3xx` in counts, per standard 3GPP naming (`t310`=2000ms, `n310`=10,
`t311`=3000ms, `n311`=1; `t300`/`t301`/`t319`=400ms each).

**Existing SNR pipeline — `sim/channel.py:38-106`.** `ChannelModel.__init__`
takes `ues: list[UEConfig]` and sets `self.mean_snr_db = {ue.ue_id:
ue.mean_snr_db for ue in ues}` (line 49) — a fixed dict, never
reassigned after construction. `update()` (lines 76-95) computes
`mean = self.mean_snr_db[ue_id]` fresh every slot from that same fixed
dict (line 78) before applying the AR(1) step. `get_snr_db`/
`get_reported_snr_db` (lines 97-106) are the only two read surfaces;
`scheduler/link.py` never imports `sim/channel.py` — the dependency runs
one way (`sim.channel` → `scheduler.link`, confirmed by the module's own
`from scheduler.link import bits_per_prb, cce_aggregation_level` at line
12).

**`UEConfig`/`ScenarioConfig` — `sim/config.py:36-49`.** `UEConfig` today
has exactly three fields: `ue_id`, `mean_snr_db: float = 20.0`,
`coherence_slots: int = 100`. No position, no clutter, no blockage config.
`ScenarioConfig` (lines 42-49) has no gNB-position field either.

**Slot duration — `sim/resource.py:23`:** `self.slot_duration_s = 0.001 /
(2 ** carrier.numerology)`. `CarrierConfig.numerology` defaults to `1`
(`sim/config.py:31`) — 0.5 ms/slot, matching README §7's confirmed
100 ms Tier-1-period-at-200-slots figure.

**HARQ retry-cycle duration — `sim/driver.py:27-29,124-129`.** Defaults
`k1_slots=4`, `k2_slots=2`, `harq_round_max=4`; `harq_rtt_dl = k1_slots +
k2_slots` (line 124, = 6 slots), `harq_rtt_ul = k2_slots` (line 129, =
2 slots). At 0.5 ms/slot: one full DL retry cycle (up to `harq_round_max`
attempts, each spaced by `harq_rtt_dl`) spans **at most ~12 ms**; UL, **at
most ~4 ms**. Both are two orders of magnitude below "hundreds of
milliseconds" — load-bearing for the blockage×HARQ prediction in §4.

**`scheduler/link.py` — the SNR consumer, unchanged by WP6.**
`_MCS_TABLE` (lines 17-30) is a 12-row SNR-threshold staircase; its lowest
threshold is `-2.0` dB (`bits_per_prb` returns `(0, 1.0)` — untransmittable
— below it, line 55). `bler_for_mcs` (lines 95-108) takes
`(mcs_threshold_db, true_snr_db, base_bler=0.10)` and composes with WP5's
`combining_gain_db` by adding into `true_snr_db` (`sim/harq.py:107-127`,
`docs/wp5-plan.md` Decision 1b) — this is the established "compose in the
SNR domain, don't add a second curve" precedent WP6 follows (Decision 1).

**TR 38.901 InF path loss / LOS probability — verified against spec text
(§0), not reconstructed from memory.** Source: `ATIS.3GPP.38.901.V1610.pdf`
(3GPP TR 38.901 V16.1.0, ATIS transposition), extracted with
`pdftotext -layout` — the PDF's embedded text layer, quoted verbatim
below, not an OCR/LLM-summarized paraphrase. Per CLAUDE.md's BSR-table
rule ("reconstructing a table by formula is exactly the same
silent-wrongness risk as recalling it from memory"), this is the same
standard applied to 38.901: the numbers below are transcribed from the
spec text directly, and `sim/tests/test_pathloss.py` must check the
transcription byte-for-byte the same way `sim/tests/test_bsr.py` checks
the BSR tables, not re-derive it.

*Common LOS formula, Table 7.4.1-1 (`38901.txt:1666`, ATIS p.30) — applies
to all five InF sub-scenarios:*

```
PL_LOS = 31.84 + 21.50*log10(d_3D) + 19.00*log10(f_c)      sigma_SF = 4.3
```

*Per-sub-scenario NLOS, same table (`38901.txt:1671-1710`, ATIS pp.30-31),
each combined with `PL_LOS` via `max()`:*

```
InF-SL: PL' = 33.00 + 25.5*log10(d_3D) + 20*log10(f_c)     sigma_SF = 5.7
        PL_NLOS = max(PL', PL_LOS)

InF-DL: PL' = 18.6  + 35.7*log10(d_3D) + 20*log10(f_c)     sigma_SF = 7.2
        PL_NLOS = max(PL', PL_LOS, PL_InF-SL)   <- note: maxes against
                                                    InF-SL's NLOS value
                                                    too, not just PL_LOS

InF-SH: PL' = 32.4  + 23.0*log10(d_3D) + 20*log10(f_c)     sigma_SF = 5.9
        PL_NLOS = max(PL', PL_LOS)

InF-DH: PL' = 33.63 + 21.9*log10(d_3D) + 20*log10(f_c)     sigma_SF = 4.0
        PL_NLOS = max(PL', PL_LOS)

InF-HH: no NLOS row exists -- PrLOS(InF-HH) = 1 always (below), so only
        PL_LOS ever applies.
```

`f_c` in GHz, `d_3D` in metres. Validity range `1 <= d_3D <= 600 m`
(`38901.txt:1689`, stated once against the InF row); frequency range
`0.5 < f_c < 100 GHz` (Note 2, `38901.txt:1728-1730` — 100 GHz is the
"all other scenarios" bound, not RMa's 30 GHz one). **InF-DL's NLOS
formula maxing against InF-SL's own NLOS value (not just the shared
`PL_LOS`) is easy to drop by analogy with the other three rows — flag it
explicitly in `sim/pathloss.py`'s docstring, not just here.**

*LOS probability, Table 7.4.2-1 (`38901.txt:1806-1824`, ATIS p.31):*

```
InF-SL, InF-SH, InF-DL, InF-DH:
    Pr_LOS(d_2D) = exp(-d_2D / k_subsce)
    where k_subsce = -d_clutter / ln(1 - r)                    (SL, DL)
                    = -d_clutter/ln(1-r) * (h_BS-h_UT)/(h_c-h_UT)  (SH, DH)

InF-HH:
    Pr_LOS = 1   (always LOS -- both antennas elevated above clutter)
```

`d_clutter` (typical clutter size), `r` (clutter density ratio, fraction
of surface area occupied by clutter), and `h_c` (effective clutter height)
are per Table 7.2-4 (`38901.txt:1216-1281`, ATIS p.23) — see Decision 6
for the calibration-study example values.

**What Decision 5/6 below still need to decide, since the spec leaves
them open:** `d_clutter`/`r`/`h_c`/BS-height numeric values for *this*
deployment (the spec gives typical/example ranges, not a single number —
same "representative, not confirmed" epistemic tier as `sr_period_slots`).

---

## 3. Decisions — no ground truth, made explicitly

### Decision 1 — composition: path loss and blockage feed the same SNR domain; no second BLER curve

Per §1/§2, `ChannelModel` is the *only* SNR-producing surface;
`scheduler/link.py`'s `_MCS_TABLE`/`bler_for_mcs` and `sim/harq.py`'s
`combining_gain_db`/`bler_for_mcs_with_combining` all consume whatever
`get_snr_db()`/`get_reported_snr_db()` return, blind to how that number was
produced. **Decided:** path loss and blockage change *what feeds into*
`ChannelModel`'s existing per-UE `mean_snr_db`/AR(1) pipeline — they do
not add a parallel BLER mechanism, a second table in `scheduler/link.py`,
or a new argument threaded through `bler_for_mcs`. Concretely:

- Path loss (static per link) replaces the *source* of `mean_snr_db` for
  any UE that opts in (Decision 2) — computed once from geometry, not
  swept over time.
- Blockage (dynamic) subtracts a further dB penalty from that same mean,
  *while the Markov state is Blocked*, before the AR(1) small-scale step
  is applied — additive in the SNR domain, same pattern as
  `combining_gain_db` adding into `bler_for_mcs`'s `true_snr_db` argument
  (Decision 1b, `docs/wp5-plan.md`). `scheduler/link.py` needs zero
  changes; `sim/harq.py` needs zero changes.

This is the answer to prompt item (b): **38.901 path loss feeds the same
SNR argument** `link.py`/`harq.py` already consume — it does not replace
`_MCS_TABLE`, `bler_for_mcs`, or `bits_per_prb`, and blockage does not
introduce a second discount mechanism alongside `bler_for_mcs`. The
duplicate-mechanism risk WP5 Decision 1b flagged (two BLER curves
differing only by which commit wrote them) does not recur here because
nothing about path loss or blockage is BLER-shaped at all — both are
pure SNR-domain quantities, same as combining gain.

### Decision 2 — path loss lands opt-in via `UEConfig.position`; existing scenarios are untouched

**The alternative considered and rejected:** derive every UE's
`mean_snr_db` from path loss unconditionally, the way WP3/WP4/WP5 made
BSR/UL-access/HARQ live for every scenario immediately. **Rejected**
because `mean_snr_db` today is not a placeholder waiting for a real
computation — it is a **deliberate per-scenario authoring choice**
(`sim/config_loader.py:138-140` reads it straight from each scenario's
YAML). A scenario author who set `mean_snr_db=2.0` to construct a
cell-edge UE, or `25.0` for a near UE, made that choice on purpose; no
existing scenario has ever specified a physical position, so forcibly
inventing positions to recompute those same UEs' SNR from path loss would
not be a fidelity improvement — it would silently overwrite a deliberate
test-regime choice with an arbitrary one. This is a different situation
from WP3/4/5, where the driver mechanism changed underneath a config value
the scenario author *wasn't* using to encode a specific regime.

**Decided:** `UEConfig` gains `position: tuple[float, float, float] |
None = None` (metres, x/y/z) and `inf_scenario: str | None = None`;
`ScenarioConfig` gains `gnb_position: tuple[float, float, float] = (0.0,
0.0, 8.0)` (an always-present, harmless default — irrelevant unless some
UE sets `position`). When `position is None` (every existing scenario),
`ChannelModel` behaves **exactly as today** — `mean_snr_db` stays the
authored constant. When set, `ChannelModel` derives `mean_snr_db` from
the link budget (Decision 6) and the TR 38.901 formula for
`ue.inf_scenario`. This is the same "new optional field, default equals
old behaviour" pattern already used for `Allocation.harq_pid`/`is_retx`
(`docs/wp5-plan.md` commit 2) and `FlowConfig.phase_jitter_ms` (WP7 commit
9) — falsifiably inert on the existing 22-record corpus, since no scenario
sets the new field yet.

### Decision 3 — blockage is decoupled from path loss: its own opt-in, its own RNG stream

Blockage is a *delta* on top of whatever large-scale mean is already in
effect (hand-authored `mean_snr_db` or path-loss-derived) — it needs no
position and no path-loss mechanism to make sense on its own. Coupling it
to Decision 2's position opt-in would force scenario authors who just want
"this UE also has a blockage event" to first author a fake position and
`inf_scenario`, for no reason.

**Decided:** `UEConfig` gains a fourth field, `blockage:
BlockageConfig | None = None` — independent of `position`. `BlockageConfig`
(new frozen dataclass, `sim/config.py`) carries `mean_unblocked_slots`,
`mean_blocked_slots`, `blocked_extra_loss_db` — **in slots, not
milliseconds**, a deliberate deviation from this Decision's original
draft (which used `_ms` names) made while actually writing the code: every
other timing knob in this codebase (`k1_slots`/`k2_slots`/
`cqi_delay_slots`/`sr_period_slots`) is slot-denominated, numerology-
agnostic the same way, and there is no reason for this one mechanism to
be the exception. The per-slot transition probabilities (`sim/
blockage.py::transition_probability`) are the standard two-state
(Gilbert-Elliott-style) construction: `p_leave = 1 / mean_dwell_slots`
(memoryless/geometric approximation of an exponential dwell time — the
same "coherence time → AR(1) alpha" translation `ChannelModel` already
does for small-scale fading, `sim/channel.py:51-53`, applied to a
discrete process instead of a continuous one), clamped to 1.0 when the
configured mean dwell is at or below one slot.

**No ground truth — literature or vendored — exists anywhere for factory
blockage rate or duration; this is stronger than "a flagged default,"
worth stating explicitly per the sign-off's own question.**
`p5g-sim-plan.md:557`'s "a forklift or robot arm crossing the path — a
15-20 dB drop lasting hundreds of milliseconds" is this project's own
qualitative *motivating description* for why WP6 includes blockage at
all, not a measured distribution from any external literature source —
unlike, say, WP5's IR/Chase combining-gain table, which at least cites an
unnamed literature basis (`docs/wp5-plan.md` Decision 1). `mean_blocked_
slots=600` (300ms at 0.5ms/slot) is this document's own order-of-magnitude
anchor to that phrase, nothing more.

**Nothing about the mechanism itself restricts it to that "long" regime —
confirmed in commit 2, not just claimed.** `transition_probability` is a
pure `1/mean_dwell_slots` relationship with no long-duration assumption
baked in anywhere; `sim/tests/test_channel.py::
test_blockage_dwell_matches_configured_mean_at_both_short_and_long_
settings` empirically verifies the same construction reproduces its
configured mean dwell at `mean_blocked_slots=4` (2ms — shorter than even
the ~8-slot/4ms UL HARQ retry cycle, `sim/driver.py`'s defaults) just as
well as at the 600-slot default. This is what makes commit 4's two-
configuration falsifiability design (§4 prediction #2) mechanically sound
rather than aspirational — the "short" arm isn't fighting the
parameterisation to exist.

**New independent RNG stream, per CLAUDE.md's standing rule** ("every new
independent random draw needs its own seed stream... WP5 found a real bug
from *not* following this"): blockage transitions draw from their own
`self._blockage_rng` (`sim/channel.py`), seeded `scenario.seed ^
0x424C4F4B` (ASCII "BLOK", `sim/driver.py`) — distinct from `cqi_seed`,
`harq_rng_dl`, `harq_rng_ul`, and commit 1's own two new streams
(`los_seed`, `shadow_fading_seed`). **This is the fourth independent
stream WP6 has added across its first two commits** (LOS realization and
shadow fading in commit 1, blockage in commit 2) — confirmed independent
in `sim/tests/test_channel.py::
test_blockage_transitions_use_their_own_independent_rng_stream`, the same
"change one seed, hold the others fixed, confirm the result changes"
check commit 1's own LOS/shadow-fading independence test used.

### Decision 4 — sync-loss (RLF-declaration) DETECTION lands in WP6, dormant; recovery timing stays WP-Join's — sign-off given, corrected before commit 3

The prompt requires a decision here, not inheritance of either README
§6's WP-Join framing or `p5g-sim-plan.md`'s silence. Looking at what the
calibration banner's timers actually govern:

- `t310`/**`n310`**/`n311` govern **detection**: how long (and after how
  many bad indications) the UE declares RLF, and what cancels that
  countdown. This is a function of instantaneous channel quality alone —
  it doesn't need a join/attach state machine to define, only a floor and
  a dwell timer. **`n310` belongs here too, corrected from this
  Decision's earlier draft**, which named only `t310`/`n311` in this
  bullet and then, in its own next paragraph, collapsed `n310` away
  entirely (approximating it as `n310=1`) rather than actually placing it
  on the detection side and using it. `n310` gates *when the t310 dwell
  timer itself starts counting* — there's no reading of "detection" that
  excludes the condition that arms the detector's own timer, and once
  commit 3 was actually being coded there was no reason not to use the
  real cited value (10) instead of discarding it.
- `t311` governs the **reestablishment search window** — how long the UE
  may spend finding a suitable cell and sending
  `RRCReestablishmentRequest` after RLF is already declared.
- `t300`/`t301`/`t319` govern **attach/resume timing** — RRC Setup,
  Reestablishment-request-wait, and RRC Resume respectively. All three are
  squarely about what happens *after* a UE decides it needs to
  (re)connect, not about detecting that it needs to.

**Decided, sign-off given:** WP6 owns detection only — `rlf_snr_floor_db`
(a threshold) and the full `n310`-armed `t310`-dwell / `n311`-cancel state
machine, landed **dormant**, matching the `sim/power.py` (WP1) / `sim/
olla.py` (WP5 commit 6) precedent exactly: a new small module (`sim/
rlf.py`), pure functions/dataclass state, unit-tested against the exact
timer values below, **not wired into `sim/driver.py`, `sim/config.py`,
any buffer, or any scheduler**. `t311`/`t300`/`t301`/`t319` — everything
about the *recovery* procedure — stay entirely WP-Join's, since that's a
new state machine (attach/RACH/reestablishment) this branch doesn't have
yet, and README §8's own open item ("calibrated delay distribution...
needs your sign-off") already flags that WP-Join's timing-model shape is
an open decision independent of this one.

**`t310`/`n310`/`n311` are real, measured, deployed values — cite the log
directly, don't call them representative defaults.**
`calibration-logs/twotier_startup_gnb.log:17`'s startup banner: `t310
2000, n310 10, ..., n311 1` (ms/counts) — this is the actual deployed
gNB's own RRC/MAC config, the same citation strength as `sim/pathloss.py`
citing TR 38.901's tables, not the `sr_period_slots`/`k1_slots` epistemic
tier. **`rlf_snr_floor_db` is the one exception, and stays a genuine
choice**: no calibration log or spec text anywhere in this repo gives an
SNR/RSRP/RSRQ threshold for out-of-sync detection (a normally-internal
PHY implementation choice, not an RRC-visible config value). Anchored to
`scheduler/link.py:68`'s existing "no viable MCS" floor
(`_MCS_TABLE[0][0] - 3.0` = `-5.0` dB) — reusing a boundary the codebase
already treats as physically meaningful rather than inventing an
unrelated number, flagged the same way as every other representative-not-
confirmed default in this document.

**`n310`/`n311`'s counting structure is approximated, and this is a
deliberate, stated simplification, not a silent drop — corrected from
collapsing `n310` away entirely.** Real RLF detection counts `n310`/
`n311` consecutive **out-of-sync/in-sync indications**, and the
indication-sampling period is UE-implementation-defined — nothing in this
repo's calibration data gives that cadence. **Decided (revised): model
`n310`/`n311` as real consecutive-SLOT counters using the cited values
(10 and 1) directly** — one slot standing in for one indication, an
approximation of the counting *cadence* (at 0.5ms/slot, `n310=10` slots is
5ms, almost certainly faster than any real UE's indication period) but
not of the counting *structure* itself, which is now reproduced exactly
rather than collapsed to `n310=1`. `n311` is implemented generically
(a configurable consecutive-good-slots threshold), not hardcoded to "1",
so a deployment with a different `n311` would be handled correctly. State
this approximation in `sim/rlf.py`'s own docstring, not just here.

**The WP6/WP-Join interface, decided now since this is the seam between
two separate work packages:** `sim/rlf.py` exposes three things, no more —
`RlfDetectorState.sync_state` (the level: `IN_SYNC`/`T310_RUNNING`/
`RLF_DECLARED`, for any code checking "is this UE currently failed" at an
arbitrary point), `RlfStepResult.rlf_declared_this_slot` (an edge-
triggered event, true for exactly the one slot RLF is declared — WP-Join
should react to this to start its own reattach procedure exactly once,
not re-derive the edge by polling the level state), and
`RlfDetectorState.rlf_declared_at_slot` (the slot index, for timing/
metrics). `step()` never un-declares RLF once reached — re-arming after a
real reattach is WP-Join's job (constructing a fresh `RlfDetectorState`,
or a reset method WP-Join adds when it needs one), not something this
module invents without a consumer to justify it.

### Decision 5 — InF sub-scenario exposure: real five-member enum now, sweep in WP9, one arbitrary default for WP6's own acceptance demo

Per prompt item (a) and README §8 (line 336): the sub-scenario choice is
"deployment-dependent, sweep in WP6 rather than picking blind" — read as
*WP6 builds the mechanism so the axis is sweepable*, not *WP6 itself picks
the headline answer*. **Decided:** `UEConfig.inf_scenario` (Decision 2) is
a plain string/enum with all **five** verified variants implemented and
tested individually (`SL`, `DL`, `SH`, `DH`, `HH` — §0; not the repo's
previous four-item list) — `InF-HH` implemented as the always-LOS special
case (no NLOS branch, per §2); `scripts/regime_sweep.py` (WP9, Phase 3) is
where the actual cross-sub-scenario comparison happens, against the full
metric panel, per README §4's phasing.

**A default is still needed for WP6's own acceptance-criterion demo**
(a new scenario exercising path loss/blockage — Decision 2/3's opt-in
design means the existing 22-record corpus can't exercise this at all).
**Decided: InF-DH** (dense clutter, high BS) for the demo scenario —
"a production floor with equipment-height obstruction and overhead-mounted
radios," a plausible private-5G factory deployment, and (now that §0 is
resolved) an unambiguous, spec-real choice. **Flagged as arbitrary
regardless**: this carries **zero evidentiary weight** on the actual
deployment question — it's a demo default so WP6's own acceptance
criterion has something concrete to run, not a Phase-3 finding, and the
commit message must say so.

### Decision 6 — link-budget constants: Tx power flagged (no repo ground truth); noise figure and clutter parameters now anchored to the spec's own calibration example

Deriving an SNR from path loss needs a link budget: `SNR_db = tx_power_dbm
+ tx_gain_db - PL_db - noise_figure_db - thermal_noise_dbm(bandwidth_hz)`
(`CarrierConfig.bandwidth_hz`, `sim/config.py:29`, already exists and
feeds the standard `-174 dBm/Hz + 10*log10(bandwidth_hz)` thermal-noise
floor). **No prior mechanism in this repo computes an absolute link
budget** — `sim/power.py` (WP1) works entirely in relative power-headroom
terms (`ph_factor`, dB deltas), never an absolute dBm Tx power or noise
figure — so this isn't a duplicate-mechanism risk the way WP5's BLER
curve was; it's a genuinely new quantity.

**Decided, Tx power:** UE Tx power defaults to 23 dBm (3GPP UE power
class 3, TS 38.101-1 — an actual spec value, no change from the original
plan). No gNB Tx power / antenna gain value is vendored anywhere in this
repo; still flagged as representative-not-confirmed.

**Upgraded from a flagged literature guess to a spec-cited example,
found while verifying §0/§2: TR 38.901's own InF calibration study**
(Table 7.8-7, `38901.txt:5578-5625`, ATIS p.91 — "Simulation assumptions
for large scale calibration for the indoor factory scenario") **states
concrete example values for every clutter/link-budget parameter WP6
needs**, not just the abstract ranges in Table 7.2-4:

```
UT noise figure:        9 dB
BS height:               1.5 m  (InF-SL, InF-DL)
                          8 m    (InF-SH, InF-DH)
Clutter density r:       20%   (low clutter)  /  60%  (high clutter)
Clutter height h_c:       2 m   (low clutter)  /   6 m  (high clutter)
Carrier frequency:       3.5 GHz, 28 GHz
Bandwidth:               100 MHz
Hall size:               120x60 m (InF-SL, InF-DH), 300x150 m (InF-DL, InF-SH)
```

**Decided:** use these as the module's defaults, cited to Table 7.8-7
directly rather than an invented or half-remembered "5-7 dB" placeholder.
**Still flagged, honestly:** this is the spec's own *calibration-study*
setup (used to validate the model against reference simulators), not a
confirmed value for *this* factory deployment — same epistemic tier as
`sr_period_slots`, just with a stronger citation than before. One gap:
Table 7.8-7 gives only a UT-side noise figure, not a separate gNB-side
one; **decided to reuse 9 dB symmetrically for both UL and DL noise-figure
terms**, flagged explicitly as a same-value-both-directions
simplification, not a second vendored gNB number.

### Decision 7 — mobility / correlated multi-UE blockage: deferred out of WP6

`p5g-sim-plan.md:552` lists `sim/mobility.py` as "New, **optional**" under
WP6's file list, "so blockage correlates across UEs sharing an aisle."
**Decided: not built in WP6**, same treatment README §3 already gave
UE mobility and OLLA when scoping this branch ("no guarantee test... needs
mobility specifically... revisit only if a specific GT/T test fails and
mobility is the diagnosed cause") — no G1-G12 guarantee in README §5's
traceability table names correlated multi-UE blockage, and per-UE
independent blockage (Decision 3) already gives WP6's own acceptance
criterion (§4) something to test. New README §8 `[OPEN]` item to record
this deferral explicitly rather than let the spec's file list imply it
was silently dropped by oversight.

---

## 4. Commit checklist

| # | Commit | Files | Wired live? |
|---|---|---|---|
| 1 | TR 38.901 InF path loss + LOS probability (Decision 2, 5, 6) — **landed** | `sim/pathloss.py` (new), `sim/config.py` (`UEConfig.position`/`inf_scenario`, `ScenarioConfig.gnb_position`), `sim/channel.py` (wiring, opt-in), `sim/tests/test_pathloss.py` (new) | No — dormant on the existing corpus (no scenario sets `position`), same falsifiable-inertness argument as `docs/wp5-plan.md` commit 2 |
| 2 | Two-state Markov blockage (Decision 3) — **landed** | `sim/blockage.py` (new), `sim/config.py` (`UEConfig.blockage`, `BlockageConfig`), `sim/channel.py` (wiring, opt-in), `sim/tests/test_blockage.py`, `sim/tests/test_channel.py` (new/extended) | No — dormant on the existing corpus (no scenario sets `blockage`), independent RNG stream added but unused until referenced |
| 3 | Sync-loss / RLF detection (Decision 4) — **landed** | `sim/rlf.py` (new), `sim/tests/test_rlf.py` (new) | No — dormant, unit-tested only, matching `sim/power.py`/`sim/olla.py` precedent; zero `sim/driver.py`/`sim/config.py` changes |
| 4 | WP6's own acceptance-criterion demo: one new scenario exercising blockage (and optionally path loss) on an existing baseline scheduler, run at **two** `mean_blocked_slots` settings so the exhaustion-spike claim is falsifiable (Decision 5, see prediction #2 below) | `sim/scenarios/scenario_config_7.yml` (new, or similar) + a short comparison script/test — **no existing scenario file touched** | Yes, but scoped to the new scenario only; existing 22-record corpus untouched |

**Predicted, before writing any code — commits 1-3: fully clean `--check`.**
This is the same falsifiable-inertness pattern as `docs/wp5-plan.md`
commits 0/1/2/3/6 and `docs/wp7-plan.md` commits 1/3/9: every new field
defaults to `None`, no existing scenario references it, so no code path
reachable from the 22-record corpus changes behaviour. Commit 3 is the
*strongest* form of that claim (same as WP5 commit 6): `sim/driver.py` is
untouched, so there is no path by which `sim/rlf.py` could run during any
`driver.run()` call regardless of scenario.

**Commit 4 is the only one predicted to move numbers, and only for its own
new scenario** — not scored against `--check`'s existing 22 records at all
(it adds a 23rd, which `--capture` must pick up deliberately, with a
commit message stating why, per CLAUDE.md's re-baseline rule).

**Ranked predictions for commit 4, checked against `requires:` fields in
`config/metric_panel.yml` directly (not assumed) — none name WP6, so no
metric's `status` promotes; see §5.**

1. (High) **M02 `pdb_violation_rate`** — spikes sharply for the blocked
   UE(s) during blocked intervals; this is the acceptance criterion itself
   (`p5g-sim-plan.md:562-563`: "sustained multi-hundred-millisecond
   starvation").
2. (High) **`bytes_harq_lost`/`harq_exhausted_count`** (WP5's counters,
   `sim/driver.py:131,330,463`) — expected far above WP5's baseline rate
   of 6-of-510 flow-records, **but only at the "long blockage" setting.**
   Per §2's cited numbers: one full HARQ retry cycle is ~12 ms (DL) /
   ~4 ms (UL); a blockage event lasting "hundreds of milliseconds"
   (Decision 3) outlasts *many* consecutive retry cycles, so every attempt
   issued for the blocked UE during that whole window should exhaust, not
   just the one in flight at blockage onset. This is the answer to prompt
   item (d)'s explicit question — yes, this interaction is real and should
   be one of the largest-magnitude, most confidently predicted effects in
   this WP, on the same footing as WP5's own headline binary-delivery
   finding.

   **Made falsifiable, per sign-off feedback:** the mechanism claims the
   effect is driven by blockage duration *relative to the retry cycle*,
   not by blockage merely existing — so commit 4's scenario/script must
   run `BlockageConfig.mean_blocked_slots` at **two** settings, not one: a
   "short" setting below both retry-cycle lengths (e.g. 4 slots = 2ms,
   shorter than the ~8-slot/4ms UL cycle) and a "long" one anchored to
   `p5g-sim-plan.md:557`'s "hundreds of milliseconds" (commit 2's own
   default, 600 slots = 300ms). **Confirmed in commit 2, not just assumed:
   the same Markov construction reproduces its configured mean dwell at
   both settings** (`sim/tests/test_channel.py::
   test_blockage_dwell_matches_configured_mean_at_both_short_and_long_
   settings`, empirical run-length check within 35% relative tolerance at
   both 4-slot and 600-slot means) — so commit 4's two-configuration
   design is mechanically sound, not just intended. **Predicted:** short
   blockage leaves `harq_exhausted_count`/`bytes_harq_lost` close to WP5's
   own baseline rate (most in-flight TBs get all their retry attempts
   either entirely before or entirely after the brief dip, not stranded
   inside it); long blockage spikes it well above baseline. If short and
   long both spike equally, or neither does, the "duration vs. retry-cycle"
   mechanism as stated is wrong, not just quantitatively off — this is the
   falsifiable form the sign-off asked for, distinguishing "exhaustion
   spikes" from "exhaustion always spikes whenever blockage exists at
   all."
3. (High) **M01 `flow_latency_percentiles`** — p95/p98/p99 for the blocked
   UE's flows spike during/immediately after blockage; p50 comparatively
   unaffected (most slots are unblocked).
4. (Moderate) **M09 `per_second_jain_index`** (proxy, needs
   `record_timeseries=True` — same corpus gap WP5's commit 4a already
   found, `docs/wp5-plan.md` §4 prediction #7) — should oscillate visibly
   in phase with the blockage Markov state, if the new scenario is run
   with `record_timeseries=True` directly (not through
   `regression_corpus.py`, which never sets it).
5. (Moderate) **M10 `aggregate_throughput`**, **M11 `prb_utilization`** —
   down for the blocked UE specifically; roughly flat in aggregate if the
   new scenario has other, unblocked UEs to absorb the freed PRBs (which
   scheduler-dependent — RoundRobin should redistribute more evenly than
   PF, which favours already-good UEs; TwoTier's Tier-1 LP re-solves only
   every 100 ms — README §7 — so it may be slow to reallocate away from a
   UE stuck at floor SNR mid-cycle. No directional call on the size of
   this gap; worth checking directly rather than asserted.)
6. (Low, out of WP6's own charter but worth flagging) **Crumb fraction /
   SR-chain metrics** — a UE whose SNR drops below
   `rlf_snr_floor_db`-adjacent levels during blockage may also fail to get
   a usable PUCCH SR occasion through, extending the cold-start-after-
   silence pattern WP4/WP5 already found (README §8's "access chain
   dominates at low load" hypothesis cluster). `sim/ul_access.py` does not
   currently model SR success as a function of SNR at all, so this
   commit's blockage model can't actually produce that interaction yet —
   flagged as a real candidate mechanism for WP9 to test once both exist,
   not something commit 4 will show.

**Metrics predicted inert even in commit 4:** M04/M07/M08/M13 (gated on
different mechanisms entirely), M06/M17 (no `xr_video` flow in this
commit's scenario, same reasoning `docs/wp5-plan.md` commit 4a used for
the same metrics), M16 (needs a caller-specified UL/DL bearer pair,
`config/metric_panel.yml` M16's own `requires:` — not exercised unless
the new scenario's own test explicitly asks for it).

**Commit 1 — landed.** `sim/pathloss.py` (new, five InF sub-scenarios per
§0), `sim/config.py` (`UEConfig.position`/`inf_scenario`,
`ScenarioConfig.gnb_position`, `CarrierConfig.center_freq_ghz`), `sim/
channel.py` (opt-in wiring + two new RNG streams), `sim/tests/
test_pathloss.py` + `sim/tests/test_channel.py` (new). **Predicted, before
writing any code: fully clean `--check`.** **Confirmed exactly:** `pytest
sim/tests -q` — 275 passed (254 + 21 new), 1 xfailed (unchanged);
`regression_corpus.py --check` — clean, zero mismatches.

**Commit 2 — landed.** `sim/blockage.py` (new, pure two-state Markov
functions), `sim/config.py` (`BlockageConfig`, `UEConfig.blockage`), `sim/
channel.py` (opt-in wiring + third new RNG stream, `is_blocked()`
accessor), `sim/tests/test_blockage.py` (new) + `sim/tests/test_channel.py`
(extended). **Predicted, before writing any code: fully clean `--check` —
the sixteenth such prediction in this WP5/WP6 lineage** (matching the
falsifiable-inertness pattern of every prior opt-in-default-`None`
commit). **Confirmed exactly:** `pytest sim/tests -q` — 286 passed (275 +
11 new), 1 xfailed (unchanged); `regression_corpus.py --check` — clean,
zero mismatches.

**Answering the sign-off's explicit questions, not left implicit:**
1. *Does the parameterisation support a "short" (shorter-than-retry-cycle)
   blockage regime, or only "long"?* **Both, confirmed empirically** — see
   Decision 3's update above and `sim/tests/test_channel.py::
   test_blockage_dwell_matches_configured_mean_at_both_short_and_long_
   settings` (4-slot and 600-slot means, both within 35% relative
   tolerance of configured over many cycles). Nothing in `sim/blockage.py`
   is duration-regime-specific.
2. *Are the transcribed values literature-sourced, and do they only cover
   long blockages?* **Neither — there is no literature source at all**,
   for either regime. `p5g-sim-plan.md:557`'s "hundreds of milliseconds"
   is this project's own qualitative motivating description, and only the
   *default* (`mean_blocked_slots=600`) is anchored to it; a "short"
   configuration is exactly as easy to construct and exactly as
   well-supported (i.e., equally unconfirmed either way) as the default.
   This is recorded as a finding per the sign-off's own framing, not
   glossed over.
3. *Does blockage need its own RNG stream?* **Yes — a fourth new
   independent stream** (`blockage_seed`, `0x424C4F4B`), distinct from
   commit 1's `los_seed`/`shadow_fading_seed` and the pre-existing
   `cqi_seed`/`harq_rng_dl`/`harq_rng_ul`. Confirmed independent by test,
   not just asserted in a docstring.
4. *Does any panel metric flip?* **No** — checked `requires:` directly
   again for commit 2; still none name WP6. See §5, unchanged from
   commit 1's conclusion.

**Commit 3 — landed.** `sim/rlf.py` (new: `SyncState`, `RlfDetectorConfig`,
`RlfDetectorState`, `RlfStepResult`, `t310_slots()`, `step()`), `sim/
tests/test_rlf.py` (new, 12 tests). **Predicted, before writing any code:
fully clean `--check` — the seventeenth such prediction in this WP5/WP6
lineage, and the strongest form of it** (same as WP5 commit 6 / `sim/
olla.py`): `sim/driver.py` and `sim/config.py` are not touched at all this
commit, so there is no code path by which anything in `sim/rlf.py` could
run during a `driver.run()` call, regardless of scenario — a state
machine's dormancy claim is exactly as falsifiable as a continuous
quantity's (WP1/WP5's precedent) when nothing calls it at all. **Confirmed
exactly:** `pytest sim/tests -q` — 298 passed (286 + 12 new), 1 xfailed
(unchanged); `regression_corpus.py --check` — clean, zero mismatches;
`git status` after this commit touches exactly `sim/rlf.py` and `sim/
tests/test_rlf.py`, confirming no other file (in particular `sim/
driver.py`) changed.

**Answering the sign-off's explicit questions:**
1. *Cite the calibration log the way commit 1 cited spec tables; say
   which values are measured vs. still a choice.* **`t310_ms=2000`,
   `n310=10`, `n311=1` are measured** — `calibration-logs/
   twotier_startup_gnb.log:17`'s real startup banner, cited directly in
   `sim/rlf.py`'s own docstring and `RlfDetectorConfig`'s. **`rlf_snr_
   floor_db=-5.0` is still a choice** — no calibration log or spec text
   anywhere in this repo gives an out-of-sync SNR threshold; anchored to
   `scheduler/link.py:68`'s existing "no viable MCS" floor instead of an
   unrelated invented number.
2. *Does detection need n310, and was the split named correctly?*
   **Yes, and the split was corrected, not inherited** — see Decision 4's
   rewrite above. `n310` gates when `t310` itself arms, which is squarely
   a detection-side concept; `sim/rlf.py` now uses the real cited value
   (10) as a genuine consecutive-slot counter, not collapsed to `n310=1`
   the way this Decision's first draft had it.
3. *Confirm this state-transition commit still lands dormant and predict
   clean.* **Confirmed** — see above; predicted and landed as the
   seventeenth clean `--check` in the lineage.
4. *What does detection expose for WP-Join, decided now?* **Three things,
   specified in Decision 4's rewrite**: `sync_state` (level),
   `rlf_declared_this_slot` (edge event), `rlf_declared_at_slot`
   (timestamp) — no more, since nothing else has a named consumer yet.

---

## 5. `metric_panel.yml` — no promotions, no new caveats

Checked every metric's `requires:` field directly (17 entries) — **none
names WP6.** Same conclusion as `docs/wp5-plan.md` Decision 6, for a
different reason: WP5's mechanism (HARQ) was live for every existing
scenario immediately, so its landing genuinely made every latency/PDB
metric's *value* HARQ-blind-no-longer even though `status` didn't change,
which is why those metrics got a `caveats` entry. WP6's mechanisms land
**opt-in and dormant** (Decisions 2-4) — until a scenario sets `position`/
`blockage`, every existing metric's value is computed from **exactly the
same channel model as before**, not a channel-blind approximation of a
more-real one. **Decided: no `caveats` entries added.** If a future WP
activates path loss/blockage for scenarios beyond WP6's own demo (e.g.
folding it into the regression corpus's existing 22 scenarios), *that*
commit is the one that should ask whether M01/M02/M09/M10/M11's existing
`caveats` lists need a "channel-model-simplistic-until-WP6-activation"
entry — not WP6 itself, which never touches those scenarios.

---

## 6. Flags — out of order, blocked, or needing sign-off before coding

1. **Resolved, sign-off given:** Decision 4 (sync-loss threshold placement,
   WP6 detection / WP-Join recovery) is confirmed. No longer open.
2. **Resolved, verified against spec text (§0):** the repo's own
   "SL/DL/SH/HH" is confirmed incomplete — TR 38.901 Table 7.2-4 defines
   five InF sub-scenarios (`SL`/`DL`/`SH`/`DH`/`HH`), and `sim/pathloss.py`
   implements the real five, not the repo's four. New README §8 item
   (landed with commit 1) records that `README.md:336`/`p5g-sim-plan.md:
   670` should be corrected to match.
3. **Resolved, verified against spec text (§2):** the path-loss/
   LOS-probability formulas and coefficients are transcribed from
   `ATIS.3GPP.38.901.V1610.pdf` (3GPP TR 38.901 V16.1.0) via direct
   `pdftotext` extraction of the PDF's embedded text layer, cited by table
   and page number — not reconstructed from memory. `sim/tests/
   test_pathloss.py` must still check the transcription byte-for-byte
   against that same source before commit 1 lands, per CLAUDE.md's
   BSR-table discipline — verifying *this document's* transcription is
   not the same as the implementation's own test verifying *its*
   transcription; both need to happen.
4. **WP6's own acceptance criterion (`p5g-sim-plan.md:562-563`) is partly
   stale for this branch's phase ordering, same species of issue as
   WP5's stale `scheduler/reservation.py`/`two_tier.py` charter reference
   (`docs/wp5-plan.md` Decision 4).** The full sentence — "blockage
   produces sustained... starvation **that a scheduler must actively
   recover from**," with the surrounding text naming "reservation's
   min-RB floor and two-tier's virtual-queue growth" as the two recovery
   mechanisms that "should visibly diverge" — is a Phase 2 question
   (neither scheduler exists yet in its intended form on this branch,
   README §4). **WP6 itself can only demonstrate the first half**
   (starvation exists, is sustained, is multi-hundred-ms) against
   `sim/baselines/` (PF/RoundRobin/Gradient), same as every other Phase 1
   WP's "scored against baselines" scope. The scheduler-divergence half
   is explicitly Phase 2/3's job, not something commit 4's demo scenario
   should be read as answering.
5. **Blockage × HARQ retry (prompt item d) is a real, high-confidence
   predicted interaction (§4, prediction #2), not a hypothetical worth
   flagging only.** Recommend WP9 read it together with WP5's own
   "uplink access chain dominates at low load" hypothesis cluster
   (README §8) the same way WP5 asked its own commit 4b finding to be
   read alongside two other open items — this may end up a fourth facet
   of the same underlying story rather than a separate one.
6. **Decision 7 (mobility / correlated blockage) deferral needs its own
   new README §8 `[OPEN]` item**, landed in the same commit as this
   document, mirroring how `docs/wp5-plan.md`'s Decision 1 correction was
   landed alongside README's own mining-table fix.
7. **No dependency the other direction**: WP6 has no dependency on
   WP-Join or Phase 2, matching WP5's own "Nothing else found blocked"
   conclusion (`docs/wp5-plan.md:999-1001`) — every WP6 commit here can
   land regardless of WP-Join's schedule, since Decision 4 keeps the
   RLF-detection/recovery boundary strictly one-directional (WP-Join reads
   `sim/rlf.py`'s output; WP6 reads nothing from WP-Join).

---

## 7. Status — all pre-coding gates cleared

- Decision 4's WP6/WP-Join sync-loss boundary — **signed off.**
- The InF sub-scenario naming — **verified against TR 38.901 Table 7.2-4**
  (§0): the real set is `SL`/`DL`/`SH`/`DH`/`HH`, not the repo's
  `SL`/`DL`/`SH`/`HH`; `sim/pathloss.py` implements the real five.
- The path-loss/LOS-probability coefficients — **verified against
  TR 38.901 Tables 7.4.1-1/7.4.2-1/7.2-4/7.8-7** (§2, Decision 6), quoted
  from a direct `pdftotext` extraction of `ATIS.3GPP.38.901.V1610.pdf`,
  not reconstructed from memory. `sim/tests/test_pathloss.py` re-verifies
  the transcription independently, per CLAUDE.md's BSR-table rule.
- Commit 4's blockage-duration prediction is now built to be falsifiable
  (short vs. long `mean_blocked_ms`, §4 prediction #2), not just directionally
  plausible.

Proceeding to commit 1: `sim/pathloss.py` (TR 38.901 InF path loss + LOS
probability), `sim/config.py` (`UEConfig.position`/`inf_scenario`,
`ScenarioConfig.gnb_position`), `sim/channel.py` wiring (opt-in), and
`sim/tests/test_pathloss.py`.
