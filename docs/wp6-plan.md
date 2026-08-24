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

## 0. A naming flag, before anything else

Both `README.md:336` and `p5g-sim-plan.md:670` write the four InF
sub-scenarios as **"SL/DL/SH/HH."** My own recollection of TR 38.901 Table
7.4.1-1 is that the fourth variant is **InF-DH** (Dense clutter, High BS
height) — SL/DL/SH/DH, not SL/DL/SH/HH. I am not confident enough in that
recollection to silently "correct" this repo's own docs, and CLAUDE.md's
standing instruction for a comment/code (or here, doc/spec) mismatch is to
flag it and ask, not reconcile silently in either direction. **Flagging,
not resolving:** whoever writes `sim/pathloss.py` must check the actual
TR 38.901 table before naming the fourth enum value, and if it really is
"DH" in the spec, this plan's and the two docs' "HH" should be corrected
together, not left as a second undocumented mismatch alongside the
Tier-1-period and deficit-drain ones CLAUDE.md already tracks.

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

**TR 38.901 InF path loss / LOS probability — spec structure, coefficients
flagged as unverified.** I recall the general shape with reasonable
confidence: a common LOS formula (log-distance + frequency dependent,
valid over a stated 3D-distance range), four sub-scenario-specific NLOS
formulas combined with the LOS formula via `PL_NLOS = max(PL_LOS, PL')`,
and a LOS-probability function of 2D distance and clutter parameters
(density ratio, average clutter element size) that differs between the
two low-BS sub-scenarios and the two high-BS ones. **I am not citing
specific numeric coefficients here** — unlike the OAI C source (checked
line-for-line) or the calibration log (read directly above), I have no
vendored copy of TR 38.901 §7.4.1/§7.4.2 in this repo to check against,
and reconstructing coefficients from memory is exactly the failure mode
CLAUDE.md's BSR-table rule already names: *"38.321 tabulates rather than
publishing a generating formula, so 'reconstructing' a table by formula is
exactly the same silent-wrongness risk as recalling it from memory."* The
same standard applies to 38.901's tables. **Action for the coding commit,
not this plan:** transcribe the actual PL/LOS-probability formulas and
per-sub-scenario coefficients from the TR 38.901 spec text directly (or a
verified secondary source), and add a test that checks the transcription
the same way `sim/tests/test_bsr.py` checks the BSR tables byte-for-byte —
not "derive it from a formula I'm recalling."

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
(new dataclass, `sim/channel.py` or a small new `sim/blockage.py`) carries
`mean_unblocked_ms`, `mean_blocked_ms`, `blocked_extra_loss_db`. The
per-slot transition probabilities are the standard two-state
(Gilbert-Elliott-style) construction: `p(unblocked→blocked) =
slot_duration_ms / mean_unblocked_ms`, `p(blocked→unblocked) =
slot_duration_ms / mean_blocked_ms` (memoryless/geometric approximation
of an exponential dwell time — the same "coherence time → AR(1) alpha"
translation `ChannelModel` already does for small-scale fading, `sim/
channel.py:51-53`, applied to a discrete process instead of a continuous
one). **No ground truth exists in this repo for factory blockage rate or
duration** — flagged the same way `sr_period_slots`/`k1_slots` are:
representative defaults (duration order-of-magnitude anchored to
`p5g-sim-plan.md:557`'s "hundreds of milliseconds," e.g.
`mean_blocked_ms≈300`), not confirmed values, swept properly in WP9.

**New independent RNG stream, per CLAUDE.md's standing rule** ("every new
independent random draw needs its own seed stream... WP5 found a real bug
from *not* following this"): blockage transitions draw from their own
`blockage_rng = np.random.default_rng(scenario.seed ^
<new_constant>)`, distinct from `cqi_seed`, `harq_rng_dl`, `harq_rng_ul`.
**Also flagged:** if Decision 2's path-loss commit adds a per-UE LOS/NLOS
realization draw (a per-link Bernoulli draw from TR 38.901's clutter-
density LOS probability, drawn once at scenario setup, not per-slot), that
needs its own independent stream too (`los_rng`), separate from
`blockage_rng` — two new mechanisms, two new streams, not one shared
"channel extras" RNG.

### Decision 4 — sync-loss (RLF-declaration) threshold lands in WP6, dormant; recovery timing stays WP-Join's

The prompt requires a decision here, not inheritance of either README
§6's WP-Join framing or `p5g-sim-plan.md`'s silence. Looking at what the
calibration banner's timers actually govern:

- `t310`/`n310`/`n311` govern **detection**: how long (and after how many
  bad indications) the UE declares RLF, and what cancels that countdown.
  This is a function of instantaneous channel quality alone — it doesn't
  need a join/attach state machine to define, only a floor and a dwell
  timer.
- `t311` governs the **reestablishment search window** — how long the UE
  may spend finding a suitable cell and sending
  `RRCReestablishmentRequest` after RLF is already declared.
- `t300`/`t301`/`t319` govern **attach/resume timing** — RRC Setup,
  Reestablishment-request-wait, and RRC Resume respectively. All three are
  squarely about what happens *after* a UE decides it needs to
  (re)connect, not about detecting that it needs to.

**Decided:** WP6 owns detection only — `rlf_snr_floor_db` (a threshold)
and the `t310`-dwell / `n311`-cancel state machine, landed **dormant**,
matching the `sim/power.py` (WP1) / `sim/olla.py` (WP5 commit 6)
precedent exactly: a new small module (`sim/rlf.py`), pure
functions/dataclass state, unit-tested against the exact timer values
above, **not wired into `sim/driver.py`, any buffer, or any scheduler**.
`t311`/`t300`/`t301`/`t319` — everything about the *recovery* procedure —
stay entirely WP-Join's, since that's a new state machine (attach/RACH/
reestablishment) this branch doesn't have yet, and README §8's own open
item ("calibrated delay distribution... needs your sign-off") already
flags that WP-Join's timing-model shape is an open decision independent
of this one.

**`n310` is not modelled precisely, and this is a deliberate
simplification, not a silent drop.** Real RLF detection counts `n310`
consecutive **out-of-sync indications**, and the indication-sampling
period is UE-implementation-defined — nothing in this repo's calibration
data gives that cadence. Modelling `n310` at a fixed 10-consecutive-*slots*
cadence (5 ms at 0.5 ms/slot) would be inventing a parameter with strictly
less justification than not modelling it at all. **Decided:** collapse
detection to "if `get_snr_db(ue)` stays below `rlf_snr_floor_db` for a
continuous `t310` (2000 ms), declare RLF; if it rises back above the floor
before `t310` expires, cancel the timer" — which is exactly what `n311=1`
already means (one recovery sample cancels), so that part of the real
mechanism is reproduced exactly, not approximated. Only `n310`'s
multi-sample counting structure is collapsed into a single continuous-
dwell check. State this in `sim/rlf.py`'s own docstring, not just here.

**`rlf_snr_floor_db` needs a default with no ground truth for it either.**
Recommended anchor: `_MCS_TABLE`'s own lowest threshold minus its stated
margin — `scheduler/link.py:68`'s existing "no viable MCS" floor
(`_MCS_TABLE[0][0] - 3.0` = `-5.0` dB) — reusing a boundary the codebase
already treats as physically meaningful ("untransmittable") rather than
inventing an unrelated number. Flagged the same way as every other
representative-not-confirmed default in this document.

**This decision needs sign-off before commit 3 lands** (§6) — it draws a
new scope boundary between WP6 and WP-Join that neither `p5g-sim-plan.md`
nor README §6 stated explicitly.

### Decision 5 — InF sub-scenario exposure: enum now, sweep in WP9, one arbitrary default for WP6's own acceptance demo

Per prompt item (a) and README §8 (line 336): the sub-scenario choice is
"deployment-dependent, sweep in WP6 rather than picking blind" — read as
*WP6 builds the mechanism so the axis is sweepable*, not *WP6 itself picks
the headline answer*. **Decided:** `UEConfig.inf_scenario` (Decision 2) is
a plain string/enum with all four variants implemented and tested
individually (not just one "the factory" path); `scripts/regime_sweep.py`
(WP9, Phase 3) is where the actual cross-sub-scenario comparison happens,
against the full metric panel, per README §4's phasing.

**A default is still needed for WP6's own acceptance-criterion demo**
(a new scenario exercising path loss/blockage — Decision 2/3's opt-in
design means the existing 22-record corpus can't exercise this at all).
Picking one for that purpose only, **flagged as arbitrary, not a claimed
answer to the deployment question**: whichever variant matches "a
production floor with equipment-height obstruction, not open warehouse
space" (dense clutter) — deferred to the naming resolution in §0, since I
won't commit to "InF-DH" vs "InF-HH" as a concrete value until that's
checked against the real table. The important property is that this
choice carries **zero evidentiary weight** — it's a demo default, not a
Phase-3 finding, and the commit message must say so.

### Decision 6 — link-budget constants (Tx power, noise figure): flagged, not vendored

Deriving an SNR from path loss needs a link budget: `SNR_db = tx_power_dbm
+ tx_gain_db - PL_db - noise_figure_db - thermal_noise_dbm(bandwidth_hz)`
(`CarrierConfig.bandwidth_hz`, `sim/config.py:29`, already exists and
feeds the standard `-174 dBm/Hz + 10*log10(bandwidth_hz)` thermal-noise
floor). **No prior mechanism in this repo computes an absolute link
budget** — `sim/power.py` (WP1) works entirely in relative power-headroom
terms (`ph_factor`, dB deltas), never an absolute dBm Tx power or noise
figure — so this isn't a duplicate-mechanism risk the way WP5's BLER
curve was; it's a genuinely new quantity. **Decided:** UE Tx power
defaults to 23 dBm (3GPP UE power class 3, TS 38.101-1 — an actual spec
value, citable with more confidence than the InF coefficients above);
gNB receiver noise figure defaults to a representative literature value
(5-7 dB range typically cited for NR gNB receivers) — **flagged exactly
like WP5's IR/Chase dB table**: ported/used because no better number
exists in this repo, not because it's confirmed for this deployment.
Antenna/cable gains: 0 dB (unmodelled), same honesty standard.

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
| 1 | TR 38.901 InF path loss + LOS probability (Decision 2, 5, 6) | `sim/pathloss.py` (new), `sim/config.py` (`UEConfig.position`/`inf_scenario`, `ScenarioConfig.gnb_position`), `sim/channel.py` (wiring, opt-in), `sim/tests/test_pathloss.py` (new) | No — dormant on the existing corpus (no scenario sets `position`), same falsifiable-inertness argument as `docs/wp5-plan.md` commit 2 |
| 2 | Two-state Markov blockage (Decision 3) | `sim/channel.py` or `sim/blockage.py` (new), `sim/config.py` (`UEConfig.blockage`), `sim/tests/test_blockage.py` (new) | No — dormant on the existing corpus (no scenario sets `blockage`), independent RNG stream added but unused until referenced |
| 3 | Sync-loss / RLF detection (Decision 4) — **needs sign-off first** | `sim/rlf.py` (new), `sim/tests/test_rlf.py` (new) | No — dormant, unit-tested only, matching `sim/power.py`/`sim/olla.py` precedent; zero `sim/driver.py` changes |
| 4 | WP6's own acceptance-criterion demo: one new scenario exercising blockage (and optionally path loss) on an existing baseline scheduler (Decision 5) | `sim/scenarios/scenario_config_7.yml` (new, or similar) — **no existing scenario file touched** | Yes, but scoped to the new scenario only; existing 22-record corpus untouched |

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
   of 6-of-510 flow-records. Per §2's cited numbers: one full HARQ retry
   cycle is ~12 ms (DL) / ~4 ms (UL); a blockage event lasting "hundreds of
   milliseconds" (Decision 3) outlasts *many* consecutive retry cycles, so
   every attempt issued for the blocked UE during that whole window should
   exhaust, not just the one in flight at blockage onset. This is the
   answer to prompt item (d)'s explicit question — yes, this interaction
   is real and should be one of the largest-magnitude, most confidently
   predicted effects in this WP, on the same footing as WP5's own
   headline binary-delivery finding.
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

1. **Decision 4 (sync-loss threshold placement, WP6 vs WP-Join) needs
   sign-off before commit 3.** This plan draws a new scope boundary
   neither source document stated explicitly; get confirmation the same
   way README §6's own WP-Join RACH-depth item already asks for it.
2. **§0's naming flag (SL/DL/SH/HH vs SL/DL/SH/DH) must be checked against
   the real TR 38.901 table before `sim/pathloss.py`'s enum is written**,
   not inherited from this repo's two existing (possibly wrong) mentions.
3. **§2's numeric path-loss/LOS-probability coefficients are unverified**
   — flagged with the same severity as CLAUDE.md's BSR-table rule. This is
   the single highest-risk item in this plan: getting a table wrong here
   is silent-wrong, not loud-wrong, exactly the failure mode CLAUDE.md
   warns about.
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

## 7. Summary of what needs a decision before coding starts

- Sign-off on Decision 4's WP6/WP-Join boundary for sync-loss (item 1
  above).
- Resolution of the SL/DL/SH/HH-vs-DH naming question against the actual
  spec table (item 2).
- Verification of TR 38.901's actual path-loss/LOS-probability
  coefficients before `sim/pathloss.py` is written, not before this plan
  is approved — the plan's mechanism design (Decision 1, 2, 6) doesn't
  depend on the specific numbers, only the coding commit does.

Everything else in this document (Decisions 2, 3, 5, 6, 7; the commit
checklist; the metric predictions) is ready to implement once those three
are settled.
