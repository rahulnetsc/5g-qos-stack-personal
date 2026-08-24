# WP-Join plan — join / re-join / RLF-recovery state machine

Follows `docs/wp5-plan.md`/`docs/wp6-plan.md`'s format: ground truth cited
exactly, decisions made explicitly with alternatives surfaced, a commit
checklist with per-commit metric predictions checked against `requires:`
fields in the file (not memory), and ranked falsifiable predictions.

**Unlike every prior WP, this one has no `p5g-sim-plan.md` §9 entry to scope
against.** WP-Join is new: added to `README.md` §4's phasing table ("§6
below — not in `p5g-sim-plan.md` at all") after the guarantee-document
review. Its charter is entirely `README.md` §5/§6/§8, the authoritative
`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` (GT-6, validates G9), and the
dormant contract `sim/rlf.py` already exposes (landed by WP6, Decision 4,
sign-off given). Read `README.md` (§4, §5, §6, §8), `CLAUDE.md`,
`docs/wp6-plan.md` (Decision 4 and the commit-checklist format), and
`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` (GT-6) first.

Two scope questions this document would otherwise need to leave `[OPEN]`
were put to the user directly and are recorded resolved below (§3, D0a/D0b).

---

## 0. What G9 needs to become sim-answerable, and what this WP delivers

`README.md` §5's guarantee-traceability table is unambiguous about where
things stand:

> "| G9 | Fast join / re-join | **Join/RLF state machine — does not exist
> yet** | **WP-Join** | **No, until WP-Join lands** |"
>
> "**G9 is the one guarantee this simulator currently cannot address at
> all**, not just imprecisely — there is no concept anywhere in `sim/` of a
> UE joining, leaving, or losing sync mid-run."

G9's authoritative pass line (`docs/IA_P5G_Factory_Guarantee_Test_Plan.md`
§3) is three numbers, one per path: *"Warm app re-handshake p95 ≤ ▷ 1 s;
full attach-to-streaming ≤ ▷ 15 s; post-RLF time-to-SLO ≤ ▷ 10 s; neighbours
unaffected throughout."* Becoming sim-answerable means the simulator can
(1) produce all three events, (2) measure all three numbers plus the
isolation clause, and (3) do so with the same regression discipline every
other guarantee in the panel gets.

**This WP delivers (1) and (2) in full, and (3) for GT-6.3 only.** It does
not deliver a validated pass/fail verdict for G9 as a whole, for three
reasons stated up front rather than discovered later:

- **`T_live` is a separate, still-open calibration item.** `README.md` §8:
  *"`[OPEN]` `T_live` (MEC liveness timeout) — assumed 2 s in the guarantee
  docs... Calibrates every G3/G9 pass line."* WP-Join's own metrics (§5,
  M19) are built to consume whatever `T_live` resolves to; they cannot
  resolve it themselves, and this WP does not attempt to.
- **Two of the three ▷-marked thresholds (15 s, 10 s) are themselves
  provisional** ("proposed defaults to be ratified with the client" per the
  test plan's own `▷` marker) — a number this WP reports against them is a
  measurement against a draft target, not a certified pass/fail.
  Specifically for GT-6.2's 15 s line: §1's finding that every phase this
  simulator can model sums to under 1 second (the 15 s budget is dominated
  by container boot / modem init / cell search this simulator has never
  modeled and is not adding) means a reported number is a **lower bound**,
  not a validated bound — flagged again at Prediction 3, so it cannot be
  mistaken for a validated result later.
- **GT-6.1/6.2's own campaigns are 50-cycle and 10-cycle repeated runs**
  (test plan §3). By user decision (§3, D0b) this WP builds unit-level
  coverage for both paths but defers their repeated-cycle statistical
  campaigns to a WP9-style sweep — the same division of labor `README.md`
  §5 already uses for G10 ("N-sweep... Phase 3").

So: **after this WP, G9 changes from "no concept exists" to "mechanism and
metrics exist, GT-6.3 has an acceptance-criterion demo, GT-6.1/6.2 have unit
coverage."** Turning that into a ratified G9 verdict needs `T_live` and the
▷ thresholds resolved (neither is this WP's to resolve) and a WP9-scale
cycle campaign (explicitly deferred, not omitted).

**This qualification must land in `README.md` §5's G9 row itself, not only
here.** That row currently reads *"No, until WP-Join lands."* Commit 8
(§4) — the commit that makes this WP's status assessable — must update it
to something like *"Mechanism and metrics: yes. Ratified verdict: no —
blocked on `T_live` (§8, still `[OPEN]`) and the provisional ▷ thresholds;
GT-6.1/6.2 cycle campaigns deferred to WP9."* Not a bare "Yes": flipping
it to "Yes" would silently claim a validated guarantee this WP explicitly
does not deliver, and the row would then need someone to notice and
walk it back later rather than being right the first time. The commit
checklist (§4) names commit 8 as the one responsible for this edit so it
lands with the work instead of being deferred or forgotten.

---

## 1. The mechanism, plain language

### 1.1 What exists today, and why it can't represent G9 at all

`sim/driver.py` treats `scenario.ues`/`scenario.flows` as a fixed roster,
consumed exactly once at `driver.run()` setup. `ChannelModel`, `BsrModel`,
`UlAccessModel`, and `BufferModel.register()` all build their per-UE state
from that one snapshot and have no way to learn about a UE that wasn't in
it; `scheduler.configure()` is called once, before the slot loop, and
`allocate()` — called every slot — takes no UE-set argument at all, reading
instead from a copy the scheduler froze at that one `configure()` call. The
existing dormant module `sim/rlf.py` (WP6, Decision 4) can *detect* sync
loss, but nothing calls it, and nothing acts on what it would report even
if it did — there is no reattach procedure, no delay model, and no way for
a UE to be gated out of scheduling and later gated back in.

### 1.2 The three GT-6 paths reduce to two independent gates, not three mechanisms

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md`'s GT-6 family (validates G9)
defines three scripted scenarios:

- **GT-6.1 warm re-join** — *"An app restart on a busy cell, and the robot
  is back in a second."* Client process restarts; PDU session stays up.
  Pass: handshake round-trip p95 ≤ 1 s; all streams back ≤ 3 s; the other
  asset unperturbed. 50 cycles.
- **GT-6.2 cold attach** — *"Powering on a new robot mid-shift just
  works."* RACH → attach → PDU sessions → handshake → streams, against a
  loaded cell. Pass: power-on-to-streaming ≤ 15 s (▷); zero impact on the
  other asset; no residual gNB pathology (ghost RNTIs, stale deficit/VQ
  state) after 10 consecutive cycles.
- **GT-6.3 deep fade / RLF and return** — *"A robot drives through a dead
  zone; it comes back cleanly, and nobody else notices."* Scripted SNR fade
  below sync for 10 s; the MEC declares the session lost; recovery must be
  bounded and clean. Pass: RF-restore-to-all-SLOs-green ≤ 10 s; the other
  asset's KPIs flat throughout; gNB state clean across re-establishment.

These differ in exactly two independent booleans, not in three separate
state machines:

| | radio gate (`rrc_connected`) | source gate (`app_running`) | arrivals during outage |
|---|---|---|---|
| GT-6.1 warm re-join | stays up | down → up | suppressed — the client is what's down |
| GT-6.2 cold attach | down → up | down → up | suppressed — the robot is powered off |
| GT-6.3 RLF reestablish | down → up | up throughout | **continue** — the robot's sensors don't stop |

The third row is the load-bearing case: masking the radio side while
arrivals keep landing in `sim/buffer.py` produces PDB-violation backlog
buildup and a post-recovery drain burst *for free*, with zero new
mechanism — exactly what GT-6.3's 10-second budget is measuring. The other
two paths need the opposite: suppress the source so a returning UE doesn't
attach carrying a fabricated backlog generated while it didn't exist (or
its client was down).

### 1.3 The UE roster stays fixed; every path is a gate, not an add/remove

**Decided (§3, D1): all three paths model a UE that is present in
`scenario.ues`/`scenario.flows` from slot 0 and gated inactive/reattaching,
never added or removed from `ChannelModel`/`BsrModel`/`UlAccessModel`/the
scheduler mid-run.**

The deciding argument is not blast radius (though it is real — true
add/remove would touch four fixed-at-init constructors and the `Scheduler`
protocol) but **falsifiability**: GT-6.2's own pass criterion is "no
residual pathologies (ghost RNTIs, stale deficit/VQ state) ... after 10
consecutive cycles." A ghost RNTI *is* per-UE state that should have been
released and wasn't. If cold attach worked by deleting the UE from every
model and re-adding it, residual state would be impossible by construction
and the test would pass trivially, measuring nothing. Gating keeps the
state where it is and makes "was it correctly cleared?" an explicit,
checkable decision (§3, D7) instead of a structural accident.

This is also not a new idiom for this codebase — `FlowConfig
.aggressor_trigger_ms` (a mid-run rate step on a statically-declared flow)
and `UEConfig.blockage` (a mid-run channel event, pre-declared per UE) are
the same pattern. `UEConfig.join` (below) is the third instance.

`GT-6.2`'s "10 consecutive cycles" requirement — the same UE must
power-off/power-on repeatedly within one run — is why the new config is an
**event list**, not a scalar "join slot":

```
UEConfig.join: JoinConfig | None = None        # None -> today's behaviour, exactly
JoinConfig:
    initial_state: "connected" | "powered_off"  # "powered_off" = cold-attach start
    events: list[JoinEvent]                     # scripted, ordered by slot
JoinEvent: (slot, kind)   kind in {"power_on", "power_off", "app_restart"}
UEConfig.scripted_fade: list[(start_slot, end_slot, extra_loss_db)] = []   # see 1.5
```

RLF itself is never scripted directly — it is **emergent**, produced by
`sim/rlf.py` observing the real SNR trace. Scripting an RLF event outright
would assert the test's own answer.

### 1.4 The gating mechanism

**Radio gate — `JoinAwareBufferView`, the direct structural analogue of the
existing `sim/harq.py::HarqAwareBufferView`:**

```
masked = HarqAwareBufferView(buffers, harq_pool, direction_by_flow)   # existing
masked = JoinAwareBufferView(masked, join_model)                      # new, outermost
```

While a UE is radio-gated, `JoinAwareBufferView.state()` zeroes
`bytes_queued` **and** `bytes_reported` for every one of its flows,
matching what `HarqAwareBufferView` already does for a HARQ-pending flow.
Both fields matter: `TwoTier`'s SPS path (`_allocate_sps`) reads
`bytes_queued` directly, bypassing BSR entirely, so a `bytes_reported`-only
mask would leave that path open. `hol_delay_s` and the cumulative
arrived/delivered/dropped counters are passed through unmasked, matching
`HarqAwareBufferView`'s own choice — they are genuinely-known gNB state
(HoL age of its own queue) or lifetime accounting that later windowing
depends on; masking them would corrupt post-recovery demand estimates, not
just this slot's grant.

Composed with a HARQ-pool flush on the transition into a radio-gated
state: `harq_pool.due_this_slot()` runs *before* the masked view exists, so
a UE entering RLF with pending processes would otherwise keep consuming
retransmission PRBs/CCEs through the outage — stealing resources from
exactly the neighbours GT-6 requires to be unaffected. `HarqProcessPool`
already exposes `free()` per process; this WP adds the one missing
aggregate, `flush_ue(ue_id)`. No bytes are lost — `drain()` only fires on
success, so flushed bytes remain in `BufferModel` and are re-granted after
recovery, matching what PDCP retention would do on real hardware.

**Source gate — generate-then-drop, never skip generation.**
`TrafficModel.generate()` draws from the same shared `rng` that also
advances `ChannelModel`'s AR(1) fading. Skipping a suppressed flow's
generation call would shift that shared stream's draw order for every
*other* flow in the scenario — the exact shape of bug WP5 found and
documented for `harq_rng` (CLAUDE.md's standing RNG-independence rule).
The gate therefore always calls `generate()`, then drops the resulting
arrival (both the enqueue and the `metrics.record_arrival` call) when
`app_running` is false. `traffic.observe_delivery()`'s feedback to
`adaptive` sources is suppressed too while gated, to avoid ratcheting a
source's offered rate down for a reason that has nothing to do with the
radio — a documented limitation (§6), not a silent one, and one that means
`adaptive`-source flows should be avoided in the first GT-6 scenarios until
someone picks it up.

Whether arrivals continue during an outage is **path-dependent, and that
distinction is the single most consequential modeling choice in this WP**
(§3, D5): GT-6.3 (radio gated, source not) keeps generating and lets
`sim/buffer.py::expire()` do its ordinary job; GT-6.1/6.2 (source gated
too) suppress generation from the event's start, because a robot that's
powered off or mid-app-restart is not producing sensor data to backlog in
the first place.

### 1.5 Blockage cannot reach the RLF floor — GT-6.3 needs a new, scripted fade

`sim/rlf.py`'s `rlf_snr_floor_db` default is **-5.0 dB**. WP6's blockage
model, at its documented defaults (`mean_snr_db=20`, `blocked_extra_loss_
db=17.5`), leaves a blocked UE at **~2.5 dB** — 7.5 dB above the floor. RLF
is structurally unreachable through the existing blockage mechanism at
default parameters. GT-6.3 needs a **new**, deterministic, scripted
channel event: `UEConfig.scripted_fade`, read in `ChannelModel.update()`
and composed as one more dB penalty exactly the way blockage's penalty
already composes — opt-in, dormant for every scenario that doesn't set it.

### 1.6 Per-UE lifecycle state machine (owned by new `sim/join.py`)

Strictly separate from — and a consumer, not an extension, of —
`sim/rlf.py`'s detection-only FSM:

```
                     rlf_declared_this_slot (edge, from sim/rlf.py)
CONNECTED ───────────────────────────────────► CELL_SEARCH [t311]
    │ app_restart event                               │ cell found + sampled delay
    ▼                                                  ▼
APP_RESTART ──► APP_HANDSHAKE ──► CONNECTED       REESTABLISH [t301]
 (radio ON,          ▲                                │ success           │ t301/t311 expiry
  source OFF)         │                                ├──► APP_HANDSHAKE   │
                       │                                                    ▼
POWERED_OFF ─power_on─►│                                              IDLE (post-RLF fallback)
                       │                                                    │
IDLE ─────────────► RRC_ESTABLISH [t300] ──► PDU_SESSION ──► APP_HANDSHAKE ─┘
(also fed by             ▲ t300 expiry, retry
 IDLE-fallback above)    │ (counted)
```

| state | `rrc_connected` | `app_running` | `sim/rlf.py::step()` runs |
|---|---|---|---|
| `CONNECTED` | yes | yes | yes |
| `APP_RESTART` (warm) | yes | no | yes |
| `APP_HANDSHAKE` | yes | inherited from entry path | yes |
| `POWERED_OFF` | no | no | no |
| `IDLE` (post-RLF fallback) | no | yes | no |
| `RRC_ESTABLISH` / `PDU_SESSION` | no | inherited (`POWERED_OFF`→no, `IDLE`→yes) | no |
| `CELL_SEARCH` / `REESTABLISH` | no | yes | no |

Three consequences worth stating plainly:

- **`T310_RUNNING` is not a WP-Join state.** While `sync_state ==
  T310_RUNNING`, the UE stays `CONNECTED` and ungated — that link is
  degraded, not failed, and real hardware keeps transmitting through it.
  Gating here would delete fidelity WP5/WP6 already built.
- **`IDLE` and `POWERED_OFF` share the entire attach chain and differ in
  exactly one bit** (`app_running`) — the same code path distinguishes "the
  robot is fine but out of RRC" from "the robot is off," rather than two
  separate implementations.
- **`APP_HANDSHAKE` is the common tail of all three paths**, which is what
  makes GT-6.1's KPI (handshake round-trip) comparable across all three —
  the test plan itself asks for "re-establishment *and re-handshake*" in
  GT-6.3, not two unrelated numbers.

**Re-arming**: a fresh `RlfDetectorState()` is constructed at the instant
`rrc_connected` flips true (on `REESTABLISH` or `RRC_ESTABLISH` success),
and `sim/rlf.py::step()` is called only while `rrc_connected` is true. This
uses the module's existing contract exactly as documented — no change to
`sim/rlf.py`, no reset method added to it (its own docstring offers one
"when WP-Join needs one"; it doesn't). One pleasant consequence: nested
failure during recovery needs no special-case code, because the detector
simply isn't running to redeclare anything — a second fade during
`CELL_SEARCH` just fails to satisfy the search's own SNR-restoration
condition, `t311` expires, and the UE falls to `IDLE` and retries, which is
what real hardware does.

**The RlfDetectorState/RlfStepResult contract is sufficient as-is — no gap
found.** Both independent design passes for this WP built the entire
recovery side (search, reestablish, attach, re-arm) using only
`sync_state`, `rlf_declared_this_slot`, and `rlf_declared_at_slot`, exactly
as `docs/wp6-plan.md` Decision 4 promised, with no extension to `sim/
rlf.py` required or requested.

### 1.7 Simulate what can be computed; sample what can't

The **app handshake is modeled as real traffic**, not a sampled delay: two
`Message`-tagged (`role="handshake"`) UL request / DL response messages
traverse the ordinary buffer → scheduler → HARQ path, using WP7's existing
`Message`/`MessageLedger`/`pop_completions` machinery. Sampling it instead
would make GT-6.1's own pass criterion — "handshake round-trip p95 ≤ 1 s
**under load**" — a tautology: the load-dependence is the entire content
of the test. Payload sizes are deterministic and fixed (no distributional
data exists for them, and drawing them from the shared traffic `rng` would
be the same shared-stream hazard as skipping generation in §1.4).

RACH, RRC Setup, cell search, reestablishment, and PDU-session setup are
the opposite case: none of SRB0/SRB1, PRACH, or NAS signaling is modeled
anywhere in this simulator, and adding them is out of scope (they'd need
their own bearers competing for real PRBs/PDCCH — a materially larger
change than this WP). Those are **sampled** from a shifted-exponential
distribution, floor + ceiling both cited where a citation exists:

```
D = floor + Exponential(mean_excess),  mean_excess = (ceiling - floor) / -ln(p_expiry)
if D > ceiling: timer expiry -> the FSM's own real failure edge (retry / fall back to attach)
```

A supervision timer is a deadline, not a distribution's scale parameter —
this shape treats it as exactly that, produces a real, reportable
`timer_expiry_count`, and collapses to today's fixed-delay behavior (`sim/
ul_access.py`'s `rach_recovery_until`) at `p_expiry → 0`. `p_expiry` is the
one invented scalar in the whole model (§3, D3).

Per-procedure floor/ceiling (`calibration-logs/twotier_startup_gnb.log:17`,
the only line in the 4117-line file mentioning any of these):

| procedure | floor | ceiling | status |
|---|---|---|---|
| RACH + RRC Setup (merged — see below) | 20 ms | `t300 = 400 ms` | floor measured, n=1; ceiling real deployed |
| cell search | 0, plus SNR-restoration gate (n311-equivalent) | `t311 = 3000 ms` | ceiling real deployed |
| reestablishment | 20 ms *(borrowed from the RACH trace)* | `t301 = 400 ms` | ceiling real deployed; floor is a borrow, flagged |
| PDU session | — | — | **no ground truth anywhere; default 0.0** |
| app restart | — | — | **no ground truth; default 0.0** (handshake carries the measurable part) |

RACH and RRC Setup are **merged into one sampled state** rather than given
separate parameters: the only real measurement in the corpus
(`calibration-logs/twotier_startup_gnb.log:163-182`, preamble at 369.19 →
`RRC_CONNECTED` at 371.17, one uncontended UE, ~2 frames ≈ 20 ms) measures
the combined procedure end-to-end. Splitting it would invent a
decomposition the data doesn't support.

**`t319` (RRC Resume, for `RRC_INACTIVE`) is out of scope** — none of
GT-6.1/6.2/6.3 involves `RRC_INACTIVE`, nothing in this repo models an
inactivity timer that would ever suspend a UE into it, and no GT-6 pass
criterion touches it. Its value is transcribed in a comment next to the
other four so a future WP that adds `RRC_INACTIVE` has it (§3, D4).

### 1.8 Slot-loop wiring and an ordering hazard

`sim/rlf.py::step()` needs the **true** instantaneous SNR
(`channel.get_snr_db`), so it must run after `channel.update(slot_index)`.
The source gate needs to filter `traffic.generate()`, which runs *before*
`channel.update()`. Resolving this by reordering `channel.update()` earlier
would perturb the shared-`rng` interleaving between channel and traffic
draws for every scenario — not acceptable for an allegedly-inert commit.

Resolution: split the join model into a pure read and a stateful step —

- **`join.gates(ue_id)`** — no draws, no mutation — consulted where
  arrivals are filtered, before `channel.update()`.
- **`join.step(slot_index, channel, harq_pool, ...)`** — advances the FSM,
  draws from the join RNG streams, re-arms `RlfDetectorState`, flushes
  HARQ — placed immediately after `channel.update(slot_index)` and before
  `harq_pool.due_this_slot()` (so a UE declaring RLF this slot doesn't get
  a stale retransmission serviced) and before `bsr.broadcast()` /
  `scheduler.allocate()`.

Cost: the source gate acts on the *previous* slot's FSM state — a 0.5 ms
lag, negligible against every timer in this WP, in exchange for exact
RNG-stream stability on every scenario that doesn't opt in.

### 1.9 Scheduler-side state: flagged, then targeted, never a `configure()` reset

`TwoTier` (and, more weakly, the PF/gradient baselines) hold persistent
per-UE ranking state — `_snr_avg`, `_virtual_q`, `_demand_bps`,
`_ul_shadow_bucket`, SPS reservations — frozen at the single `configure()`
call `driver.py` makes before the slot loop. Nothing resets a single UE's
share of that state today; the only reset mechanism is a full
`configure()`, which would also erase every *other* UE's state — precisely
what GT-6 requires not to happen.

GT-6.2 and GT-6.3 name this directly in their own pass criteria ("stale
deficit/VQ state," "floor/VQ/deficit reset correctness across
re-establishment"), so — unlike the SPS double-grant limitation CLAUDE.md
already flags and deliberately leaves unfixed — this cannot be left as a
permanent limitation without leaving two of three acceptance criteria
unmeasurable. It is staged as its own commit (§4, commit 7), landing an
additive, duck-typed hook:

```python
class SchedulerContextReset(Protocol):     # new, does NOT extend Scheduler
    def reset_ue(self, ue_id: int, scope: str) -> None: ...   # scope: "full" | "mac"
```

implemented in `scheduler/two_tier.py` **only**. `PF`/`gradient`'s single
piece of relevant state (`_r_avg`, decayed every slot toward a floor of
`1.0` regardless of grants) provably decays to numerically indistinguishable-
from-fresh within ~1000 slots for any outage of GT-6 scale (a 2 s fade is
4000 slots at µ=1) — a reset there is a checkable no-op, not an untested
assumption, so it is documented rather than implemented. `Scheduler
.configure`/`allocate` stay untouched; every existing arm stays conformant
without modification.

Reset scope is **path-dependent**, and this is itself a no-ground-truth
call (§3, D7): warm re-join clears nothing (RRC never dropped — that stale
state is the *correct* state); reestablishment clears only the MAC/BSR
side (`"mac"` — C-RNTI and context are retained on real hardware, which is
what makes reestablishment fast; VQ/deficit/demand are deliberately kept,
since GT-6.3 is testing whether that retention is correct, not asserting
it away); cold attach and the RLF→IDLE fallback clear everything (`"full"`).

---

## 2. Ground truth, cited exactly

**RRC/MAC timer constants** — `calibration-logs/twotier_startup_gnb.log:17`
(verified directly, the only line in the 4117-line file mentioning any of
these):

```
17:[0m[GNB_APP] sr_ProhibitTimer 0, sr_TransMax 64, sr_ProhibitTimer_v1700 0,
    t300 400, t301 400, t310 2000, n310 10, t311 3000, n311 1, t319 400
```

`t310`/`n310`/`n311` are already cited and consumed by `sim/rlf.py` (WP6).
`t300`/`t301`/`t311`/`t319` carry the identical evidentiary tier — same log
line, same "real deployed value, not chosen" status — and are this WP's
own. Units: `t3xx` in ms, `n3xx` in counts.

Per `docs/wp6-plan.md` Decision 4 (sign-off given), the functional split:

> "`t311` governs the **reestablishment search window**... `t300`/`t301`/
> `t319` govern **attach/resume timing** — RRC Setup, Reestablishment-
> request-wait, and RRC Resume respectively. All three are squarely about
> what happens *after* a UE decides it needs to (re)connect, not about
> detecting that it needs to."

**The one real RACH trace in the entire log** — lines 163–182, a single
uncontended attach (RNTI `2cf9`), the only `[RAPROC] Initiating RA
procedure` line in the file: preamble at frame.slot `369.19` → Msg2/Msg3 at
`370.10`/`370.19` → Msg4 ack + `RRC_CONNECTED` at `371.17` — roughly 2
frames (~20 ms), one data point, not a distribution. **No RRCReestablish-
ment, handover, disconnect, second RA attempt, preamble collision, or
timer-expiry event appears anywhere else in the file** (verified by
targeted grep across all 4117 lines). Per `calibration-logs/README.md`:
this is a startup banner, "not a contention-scenario capture... use this
file as a guideline for timer constants, not a fit target."

**`sim/rlf.py`'s contract** (WP6 commit 3, Decision 4, verified directly
against the source, §1.6 above) — `SyncState.{IN_SYNC, T310_RUNNING,
RLF_DECLARED}`, `RlfDetectorState.{sync_state, rlf_declared_at_slot}`,
`RlfStepResult.rlf_declared_this_slot`, `step()`'s no-op guard once
`RLF_DECLARED`. `RlfDetectorConfig.rlf_snr_floor_db = -5.0` is the module's
one uncalibrated constant, anchored to `scheduler/link.py`'s MCS-0 floor
minus 3 dB — flagged in its own docstring, not a hidden assumption.

**WP6's blockage defaults cannot reach that floor** — `BlockageConfig`
(`sim/blockage.py`) defaults `mean_snr_db=20.0`, `blocked_extra_loss_
db=17.5`, leaving a blocked UE at ≈2.5 dB, 7.5 dB above `-5.0 dB` (§1.5).

**The fixed-UE-roster constraint**, verified directly against the source:
`sim/bsr.py::BsrModel.__init__` and `sim/ul_access.py::UlAccessModel
.__init__` build `_ue_flows`/`_state` once from the `flows` list passed at
construction; `sim/channel.py::ChannelModel.__init__` does the same for its
per-UE dicts; `scheduler/interfaces.py::Scheduler.allocate(slot, buffers,
channel)` takes no UE-set argument, and `sim/driver.py` calls `scheduler
.configure(...)` exactly once, before the slot loop. `sim/harq.py
::HarqProcessPool` is the one exception — it lazily creates a pool the
first time a `(ue_id, direction)` key is touched.

**No `T8` in the authoritative test plan.** `docs/IA_P5G_Factory_Guarantee_
Test_Plan.md` has no numbered "T" tests at all (only GT-0 through GT-7);
"T8" exists only in the superseded `IA_P5G_Guarantee_Validation_Suite.md`,
under a *different*, non-authoritative G8 ("Recovery time"). README's
"no G9/GT-6/T8 pass criterion needs [contention resolution]" is loosely
referencing that superseded T8 for vocabulary continuity, not citing it as
a binding threshold — GT-6.1/6.2/6.3's own KPIs (§1.2) are the actual
binding criteria.

**Note for a future README fix (not this WP's to make):** README §6 cites
this timer banner as `contention.log`'s startup banner; per `calibration-
logs/README.md`, `contention.log` is a phantom path from an old layout
diagram that was never committed — the real, only file is `calibration-
logs/twotier_startup_gnb.log`. Flagged in §6 below.

---

## 3. Decisions — no ground truth, made explicitly

### D0a. RACH/attach/reestablishment timing model — **user sign-off obtained**

README §6/§8's standing `[OPEN]` item, put to the user directly:
*calibrated delay distribution keyed to the real timers* vs.
*contention-based RACH simulation*. **Decided: calibrated delay
distribution** — the documented recommendation, confirmed by the user.
Full RACH contention (preamble collision/backoff probability) is PHY-layer
fidelity this simulator's non-goals already exclude elsewhere, no G9/GT-6
pass criterion needs contention *resolution* rather than realistic
*timing*, and the calibration log has zero contention data to ground a
collision model in regardless (§2). This governs §1.7's entire delay
model.

### D0b. Acceptance-demo scope — **user sign-off obtained**

**Decided: the commit-checklist's wired-live acceptance demo (commit 8)
covers GT-6.3 only.** Reasons, put to the user and confirmed: (a) it is the
only path that exercises every prior commit in one run — the delay
sampler, the RLF wiring, the radio gate, and the scheduler reset; GT-6.1
exercises only the app-layer half and GT-6.2 only the cold chain. (b) its
two variants (§3, D6 below) straddle `t310 + t311 = 5.0 s`, a real, cited
boundary — sharper than WP6's own `mean_blocked_slots` split, which had no
ground truth on either side. (c) it is P1 with a live hardware
investigation feeding it (`README` §8's F8d/RLF-OWD tie-in: "runs of this
test are its data source"). GT-6.1/6.2 get unit-level coverage in commits
6 and 5 respectively; their 50-cycle/10-cycle repeated campaigns are
deferred to a WP9-style sweep (§0).

### D1. Gating, not add/remove, for all three paths — see §1.3

Decided above; repeated here for the record. Falsifiability of GT-6.2's
own "no residual pathology" criterion is the deciding argument, not just
blast radius.

### D2. Delay-distribution family — shifted exponential, ceiling = failure branch

See §1.7. One invented scalar (`p_expiry`); the shape treats each 3GPP
timer as the supervision deadline it actually is rather than a
distribution's mean, and collapses to today's fixed-delay behavior at
`p_expiry → 0`.

### D3. `p_expiry` default

**0.01**, global default with a per-procedure override available. No
ground truth; exposed as a named, sweepable parameter rather than a silent
default, matching `sr_period_slots`'/`mean_blocked_slots`'s treatment.

### D4. `t319` out of scope

See §1.7. Value transcribed in a comment in `sim/join.py` next to the
other four timers, not implemented — a recorded scope call, not an
oversight, for whichever future WP adds `RRC_INACTIVE`.

### D5. Traffic-admission asymmetry across paths

See §1.2/§1.4: GT-6.3 lets arrivals continue (radio-gated only); GT-6.1/6.2
suppress the source too. This is the single most consequential modeling
choice in the WP — it is what makes Prediction 2 (§4) falsifiable at all.
Generate-then-drop, never skip-generation, to protect the shared-RNG
interleaving (§1.4).

### D6. GT-6.3 needs two scenario variants, not one

**Finding, not just a decision:** `t310 (2000 ms) + t311 (3000 ms) = 5.0 s`
— less than the test plan's own scripted 10 s fade. A UE fading for the
full 10 s cannot stay in `CELL_SEARCH`/`REESTABLISH` long enough to
reestablish; `t311` expires at ≈5.0 s into the fade (2.0 s to declare RLF +
3.0 s search window), the UE falls to `IDLE`, and performs a full attach
on RF restore instead. That's correct UE behavior, not a bug, but it means
the test plan's literal phrasing ("≤10 s including re-establishment")
describes a path its own stimulus doesn't reach. **Decided: build both.**
GT-6.3a (fade < 5 s, e.g. 3 s) exercises the true reestablishment path,
where "gNB state clean across re-establishment" is actually testable;
GT-6.3b (the plan's literal 10 s fade) exercises the IDLE-fallback / full
re-attach path, whose recovery budget must accommodate an attach, not a
reestablishment. Both land in commit 8; the discrepancy itself should be
raised with the test-plan owner separately from this WP's build.

### D7. Scheduler-reset scope is path-dependent, and is itself under test

See §1.9. `"mac"` for reestablishment (deliberately leaves VQ/deficit/
demand alone, since whether that retention is correct is GT-6.3's own
question), `"full"` for cold attach / IDLE-fallback, none for warm
re-join. Exposed as a switch, not hardcoded, precisely because there is no
ground truth for the `"mac"` row — OAI's own `sched_ctrl` re-init scope on
reestablishment is not documented anywhere in this repo.

### D8. `reset_ue()` lands in `scheduler/two_tier.py` only

PF/gradient's only relevant state (`_r_avg`) provably decays to
indistinguishable-from-fresh within any GT-6-scale outage (§1.9) — a
checkable arithmetic claim, not an assumed one. Implementing a no-op there
would be a second, unnecessary scheduler-file change in a WP already
touching two independent gates.

### D9. RNG streams — three, one per path family

`join_cold_seed = scenario.seed ^ 0x434F4C44` ("COLD"),
`join_reest_seed = scenario.seed ^ 0x52454553` ("REES"),
`join_warm_seed = scenario.seed ^ 0x4A4F494E` ("JOIN", reserved — the warm
path's app-restart delay defaults to 0.0 per §1.7 and draws nothing until
someone gives it a nonzero distribution). Matches this repo's existing
per-mechanism seed-tagging precedent (`los_seed`/`shadow_fading_seed`/
`blockage_seed`, WP6) rather than one shared stream across three
mechanistically distinct procedures — cheap to get right now, and the
exact shape of bug (`harq_rng`, WP5) that One Stream For Now would risk
the moment a scenario mixes two paths.

### D10. Scheduler state is not snapshotted into `RunRecord`

GT-6.2/6.3's "no residual gNB-state pathology" is asserted directly on the
scheduler object commit 8's own test constructs and holds a handle to
(plus a `summary["_join_state"]` diagnostic handle, following the
`_ue_lcp`/`_message_ledger` precedent) — not routed through `RunRecord`,
which would force `sim/scorecard.py` to know scheduler-internal field
names, contrary to its stated contract of consuming `RunRecord` only.

### D11. M04 is not promoted by this WP

Commit 8's demo is the first WP-Join scenario to run with
`record_timeseries=True`, which makes M04's existing `proxy` computation
tempting to tighten. **Declined.** CLAUDE.md records M04's exact promotion
as deliberately kept out of every prior WP, "own commit, whenever taken
up," to protect commit attribution. Same discipline here, recorded rather
than silently skipped.

---

## 4. Commit checklist

| # | Commit | Files | Wired live? |
|---|---|---|---|
| 1 | `sim/join.py` — dormant FSM (§1.6), `JoinConfig`/`JoinEvent`, calibrated delay sampler (D2/D3) | `sim/join.py` (new), `sim/tests/test_join.py` (new) | No — zero driver/config wiring, unit-tested only |
| 2 | Wire `sim/rlf.py::step()` into `sim/driver.py`'s slot loop, unconditionally, per-UE per-slot on true SNR; two diagnostic counters | `sim/driver.py`, `sim/tests/test_smoke.py` | Live, designed to be inert (§4.1) — no new `UEConfig` field |
| 3 | Scripted fade in `sim/channel.py` (§1.5) — `UEConfig.scripted_fade`, deterministic override (not a mean-shift) while a window is active | `sim/config.py`, `sim/channel.py`, `sim/tests/test_channel.py`, `sim/tests/test_wpjoin_fade_boundary.py` (new — cross-module GT-6.3 boundary characterization) | No — opt-in, `()` default preserves today's behavior exactly |
| 4 | Panel/schema: M18/M19 at `status: pending`, `JoinEventRecord`/`RunRecord.join_events`, `Scorecard` stubs returning pending on every existing record, `defaults.slo_green_dwell_s` (`[OPEN]`, D-new below) | `config/metric_panel.yml`, `sim/run_record.py`, `sim/scorecard.py`, `sim/tests/test_scorecard.py`, `sim/tests/test_run_record.py`, `regression/baseline_studies_1_3.json` | No — schema only. **The one commit that is not `--check`-clean** (§4.1) |
| 5 | Radio-layer gate: `UEConfig.join`, `JoinAwareBufferView`, `HarqProcessPool.flush_ue`, RLF-edge → reestablish trigger, re-arm on reconnect, `JoinEventRecord` emission, `join_cold_seed`/`join_reest_seed`. **M18 `pending` → `ok`** | `sim/config.py`, `sim/driver.py`, `sim/join.py`, `sim/harq.py`, `config/metric_panel.yml`, `sim/tests/test_join_gate.py` (new) | No — opt-in, `UEConfig.join=None` default |
| 6 | Application-layer gate: traffic-admission suppression (warm/cold only), handshake `Message` pair through the real buffer/scheduler/HARQ path. **M19 `pending` → `proxy`** | `sim/driver.py`, `sim/join.py`, `sim/traffic.py`, `config/metric_panel.yml`, `sim/tests/test_join_handshake.py` (new) | No — same opt-in gate as commit 5 |
| 7 | Per-UE scheduler context reset: `SchedulerContextReset.reset_ue()` (duck-typed, additive), implemented in `two_tier.py` only; sim-side per-UE re-inits in `BsrModel`/`UlAccessModel`/`UeLcp` | `scheduler/interfaces.py`, `scheduler/two_tier.py`, `sim/bsr.py`, `sim/ul_access.py`, `sim/ue_lcp.py`, `sim/tests/test_join_reset.py` (new) | No — only invoked on a join-event transition; no effect without one |
| 8 | Acceptance-criterion demo — **GT-6.3 only** (D0b), two fade-duration variants straddling `t310+t311=5.0s` (GT-6.3a short fade / true reestablish path; GT-6.3b literal 10 s fade / IDLE-fallback path), × TwoTier and PF, `record_timeseries=True`, `isolation_check` scorecard helper. **Also updates `README.md` §5's G9 row** (§0) — qualified, not a bare flip to "Yes" | `sim/tests/test_wpjoin_rlf_recovery.py` (new; scenario built in-line, not `sim/scenarios/*.yml`), `README.md` (§5 G9 row only) | Yes, scoped to this test file's own runs — stays outside the 22-record corpus entirely |

### Why this order

Commit 2 lands before commit 3 so its "provably inert" claim is checked
against the untouched pre-WP-Join baseline, not one already re-captured by
commit 4 — an independent confirmation, not a confounded one. Commits 1–3
land every new *mechanism* dormant before commit 4 touches the scoring
schema, so the one commit expected to move the regression snapshot
(structurally, not numerically) is isolated and easy to review on its own.
Commits 5/6 split the radio and app gates because they are independent
fidelity changes with different physics (§1.2) — bundling them would make
it impossible to tell, from a corpus delta, which gate caused it. Commit 7
(the scheduler reset) follows both gates because GT-6.2/6.3's "residual
state" criteria need both a place for residue to appear (5/6) and a place
to check it was cleared (7) before the demo (8) can test either.

**No `sim/config_loader.py`/YAML change in any commit** — `UEConfig.join`
and `UEConfig.scripted_fade` are Python-API-only opt-ins, matching WP6's
own treatment of `position`/`blockage`/`inf_scenario` (never plumbed into
the YAML loader); commit 8's scenario is built in-line, mirroring WP6
commit 4's demo.

### `requires:`-gated metrics, checked against the file directly

All 17 existing `config/metric_panel.yml` entries checked: none names
WP-Join, and none can — M04 needs WP7+timeseries, M09/M16 need timeseries
(+ a named flow pair for M16). **No existing metric's `requires:` or
`status` changes anywhere in this WP.** Commits 1–3 and 7 touch no panel
rows. Commit 4 adds M18/M19 at `status: pending` (a never-omitted row per
the panel's own contract). Commit 5 flips **M18 `pending` → `ok`**; commit
6 flips **M19 `pending` → `proxy`**. Commit 8 moves *values* on M01/M02/
M03/M08/M09/M14/M18/M19 inside its own demo file only, with zero further
`status` changes — the same shape as `docs/wp6-plan.md` §5's own commit 4.

**No `caveats:` added to M01–M17.** Every mechanism in this WP lands
opt-in; until a scenario sets `UEConfig.join`, every existing metric is
computed by exactly the simulator that existed before this WP, not a
join-blind approximation of a more-real one.

### Commit 1 — landed

`sim/join.py` (new: `JoinPhase`, `JoinEvent`, `JoinConfig`, `JoinRngStreams`/
`init_join_rng_streams`, `JoinState`/`init_join_state`, `JoinStepResult`,
`step()`), `sim/tests/test_join.py` (new, 21 tests). **Predicted, before
writing any code: fully clean `--check` — the eighteenth such prediction
in the WP5/WP6/WP-Join lineage** (verified against the file directly:
`docs/wp6-plan.md` commit 3 was the seventeenth — line 772 — so this is
the next), **and the strongest form of it**, matching `sim/rlf.py`/`sim/
olla.py`'s own precedent: `sim/driver.py` and `sim/config.py` are not
touched at all this commit, so there is no code path by which anything in
`sim/join.py` could run during a `driver.run()` call, regardless of
scenario. **Confirmed exactly:** `pytest sim/tests -q` — 324 passed (303 +
21 new), 1 xfailed (unchanged); `regression_corpus.py --check` — clean,
zero mismatches; `git status` after this commit touches exactly `sim/
join.py` and `sim/tests/test_join.py` — no other file, in particular
neither `sim/driver.py` nor `config/metric_panel.yml`, changed.

**Answering the pre-commit checklist explicitly, not left implicit:**

1. *Is the inertness claim "nothing imports it" or "imported but never
   reached"?* **"Nothing imports it"** — the strongest form. `sim/join.py`
   has zero call sites outside its own test file, the same as `sim/
   rlf.py` at WP6 commit 3 and `sim/olla.py` at WP5 commit 6.
2. *Is `sim/rlf.py`'s contract still sufficient once writing against it?*
   **Yes — and the boundary ended up stricter than sec1.6 first
   described.** `sim/join.py` does not import `sim/rlf.py` at all:
   `step()` takes `rlf_declared_this_slot` as a plain `bool` parameter,
   not an `RlfDetectorState`/`RlfStepResult` object. "Consume, don't
   extend" (CLAUDE.md) is therefore enforced at the type signature, not
   only the docstring — `sim/join.py` cannot reach into `sim/rlf.py`'s
   state machine even by accident, since it never holds a reference to
   it. The one place this method could have leaked a gap — `sim/join.py`
   needing to know the RLF SNR floor for `CELL_SEARCH`'s SNR-restoration
   gate — is handled by `JoinConfig.rlf_snr_floor_db`, a value the wiring
   commit (5) must copy from the same UE's `RlfDetectorConfig`, documented
   in the module docstring as that commit's responsibility, not solved by
   importing the type. No gap found; nothing added to `sim/rlf.py`.
3. *Per-path RNG seeds, tested for independence?* **Three streams, XOR-
   tagged exactly as sec3 D9 specifies** — `init_join_rng_streams(seed)`
   returns `cold = seed ^ 0x434F4C44`, `reest = seed ^ 0x52454553`,
   `warm = seed ^ 0x4A4F494E`. `test_rng_streams_are_independent_and_
   reproducible` confirms same-seed reproducibility and three-way
   independence by draw, not just by construction; `test_deterministic_
   delay_consumes_no_rng_draw_when_ceiling_equals_floor` confirms the
   deterministic branch (PDU-session/app-restart at their 0.0 defaults)
   draws nothing at all, checked via the generator's own `bit_generator
   .state`, matching the standard this repo already holds `harq_rng_dl`/
   `harq_rng_ul` to.
4. *Any `config/metric_panel.yml` change this commit?* **None.** M18/M19
   land at commit 4, per the checklist above — confirmed via `git status`
   showing zero touch to that file this commit.

### Commit 2 — landed

`sim/driver.py` (new: `rlf_config`/`rlf_states`/`rlf_step_calls`/
`rlf_declared_count`, wired into the slot loop right after `channel
.update(slot_index)`, before the HARQ-resolution block), `sim/tests/
test_smoke.py` (new test). `sim/rlf.py` itself untouched.

**Predicted, before writing any code: fully clean `regression_corpus.py
--check`.** This commit's inertness is a different shape from every
other commit in this WP, worth stating precisely rather than reusing the
same sentence by habit: `sim/rlf.py::step()` now runs **unconditionally**,
for every UE, every slot, on every scenario — there is no new `UEConfig`
field gating whether it runs at all (detection is a property of every
real UE, not a feature). What keeps this commit inert is that **nothing
downstream reads its output yet** — `rlf_step_calls`/`rlf_declared_count`
are diagnostic-only, merged into `summary` the same way `harq_allocate_
calls` already is, deliberately not threaded into `RunRecord`. **Confirmed
exactly:** `pytest sim/tests -q` — 325 passed (324 + 1 new), 1 xfailed
(unchanged); `regression_corpus.py --check` — clean, zero mismatches;
`git diff --stat` touches exactly `sim/driver.py` (+41) and `sim/tests/
test_smoke.py` (+25) — no `config/metric_panel.yml`, no `sim/config.py`.

**Answering the pre-commit checklist explicitly, confirming the four
points above rather than just restating them:**

1. *Which config field gates it?* **None — see above.** Checked
   empirically, not just structurally, before writing the permanent test:
   ran all 22 regression-corpus cases (`scripts/regression_corpus.py::
   _cases()`) with the instrumentation in place — **1,144,000 total
   `rlf_step_calls`, 0 `rlf_declared_count`**, across every study/case/
   scheduler combination. Every corpus UE sits at `mean_snr_db=20.0`
   (`scripts/scheduler_study.py`), 25dB above `RlfDetectorConfig`'s
   default `-5.0`dB floor — a real finding recorded here, not assumed
   from the default's distance alone, since an AR(1) fading tail could in
   principle still dip that far.
2. *Ordering confirmed live, not just planned:* placed immediately after
   `channel.update(slot_index)`, before `slot_grid = grid.slot_grid(...)`
   and the HARQ-resolution block — exactly where commit 5's own gate will
   need to act on a declared RLF before that slot's retransmissions are
   serviced (sec1.8), so that commit won't need to move this call site.
3. *Live, repeated-call behaviour vs. the unit tests:* the state machine
   itself is unmodified and already unit-tested (WP6, `sim/tests/
   test_rlf.py`, 12 tests); this commit adds no new logic there, only a
   caller. Two things ARE genuinely new relative to those tests: (a)
   `test_rlf.py` feeds hand-crafted step sequences; this is the first time
   `step()` has processed a real, continuously AR(1)-varying SNR trace
   across a full multi-thousand-slot horizon, uninterrupted, at the
   corpus's actual UE counts. (b) `rlf_step_calls == len(scenario.ues) *
   scenario.horizon_slots` is asserted specifically to confirm no slot/UE
   combination is silently skipped or double-counted across that many
   calls — the same "count that matters, not just present" pairing
   `test_wp5_harq_process_pool_gating_is_live_but_never_binds` already
   established for `harq_allocate_calls`.
4. *Per-UE state driver.py must now own and reset between runs:*
   `rlf_states: dict[int, RlfDetectorState]`, built fresh at the top of
   `run()` from `scenario.ues` — the same freshness discipline as
   `harq_pool`/`bsr`/`ul_access` a few lines above it, confirmed by
   inspection (a local, rebuilt every call, nothing module-level).

### Commit 3 — landed

`sim/config.py` (new: `ScriptedFadeWindow`, `UEConfig.scripted_fade`),
`sim/channel.py` (`ChannelModel` forces `snr_db` deterministically for
every slot inside a window and resets it at the window's end), `sim/
tests/test_channel.py` (5 new tests), `sim/tests/test_wpjoin_fade_
boundary.py` (new, 10 tests — a cross-module characterization composing
this commit's fade with the already-landed, unmodified `sim/rlf.py` and
`sim/join.py`, since all three are pure/importable well before commit
5's driver.py wiring makes them a real pipeline).

**Predicted, before writing any code: fully clean `regression_corpus.py
--check`** — the same opt-in-default shape as WP6's `position`/
`blockage` commits (1/2 in that WP's own lineage), **the twentieth such
prediction in the WP5/WP6/WP-Join lineage** (18th = this WP's commit 1,
"nothing imports it"; 19th = commit 2, "diagnostic-only, unread"; this is
the 20th, back to the standard "opt-in default preserves today's
behaviour exactly" shape — `UEConfig.scripted_fade` defaults to `()`, and
no corpus scenario sets it). **Confirmed exactly:** `pytest sim/tests -q`
— 340 passed (325 + 15 new), 1 xfailed (unchanged); `regression_corpus.py
--check` — clean, zero mismatches; `git diff --stat` touches exactly
`sim/config.py`, `sim/channel.py`, `sim/tests/test_channel.py`, and the
new `sim/tests/test_wpjoin_fade_boundary.py` — no `sim/driver.py`, no
`config/metric_panel.yml`.

**Answering the pre-commit checklist explicitly:**

1. *What must the scripted fade do that blockage can't; are the two
   GT-6.3 variants still needed?* **Restated, and one thing sharpened
   while implementing it.** Blockage's defaults (`mean_snr_db=20`,
   `blocked_extra_loss_db=17.5`) leave a blocked UE at ≈2.5dB, 7.5dB above
   the `-5.0`dB RLF floor — but the deeper reason blockage can't serve
   this role isn't just "the default is too shallow," it's that
   **blockage is a stochastic two-state Markov process with random dwell
   times**, structurally incapable of guaranteeing a fade crosses a known
   threshold for a known, exact duration. The sharpened finding, found
   while implementing (not anticipated in §1.5): **even a hypothetical
   deep, deterministic blockage-style *mean shift* couldn't deliver this
   either**, because the AR(1) process only mean-reverts geometrically
   (rate `alpha` per slot) — at this deployment's typical `coherence_
   slots` (100-2000), reaching within noise of a new mean takes many
   hundreds to thousands of slots, and recovering back afterward takes
   just as long. A "scripted" fade that still needed thousands of slots
   to actually arrive at its target value, and thousands more to leave
   it, would not deliver the exact, known-instant transitions GT-6.3's
   own timing boundaries depend on. `ChannelModel` therefore forces
   `snr_db` directly (bypassing AR(1) entirely) during the window and
   resets it explicitly the instant the window ends — the mechanism this
   commit actually landed, not a deeper blockage config.
   **The two variants (D6) are still exactly what's needed, now with
   an exact number instead of a qualitative one — see point 4.**
2. *Predict the drift; state the falsifiable form.* **Opt-in, default-`
   ()`, "preserves today's behaviour exactly"** — the same falsifiable
   form as WP6's `position`/`blockage` commits, not commit 1/2's dormant
   shapes (`sim/channel.py` is already imported by `sim/driver.py`; this
   commit adds a new opt-in field to an already-wired module, exactly
   like `blockage` did). No corpus scenario sets `scripted_fade`, so
   `ChannelModel`'s SNR computation is byte-identical for every existing
   scenario — confirmed via `regression_corpus.py --check` above, and via
   `test_ue_without_scripted_fade_is_unaffected`.
3. *Does the fade need its own RNG stream?* **No — deterministic by
   construction, and confirmed empirically, not just asserted.** A
   scripted fade is scenario-AUTHORED (exact `start_slot`/`end_slot`/
   `extra_loss_db`), not a draw. `test_scripted_fade_draws_no_rng_of_its_
   own` goes one step further than commit 1's own floor-equals-ceiling
   check: rather than checking a dedicated stream draws nothing, it runs
   two otherwise-identical `ChannelModel`s — one with the fade active,
   one without — and confirms the SHARED AR(1) innovation stream
   (`self.rng`) ends in the exact same `bit_generator.state` either way.
   The innovation draw still happens, every slot, for a faded UE — only
   discarded, never skipped — so a scenario mixing faded and unfaded UEs
   can never have one UE's fade state shift another UE's draw order
   (CLAUDE.md's RNG-independence rule, satisfied here by never having a
   second stream to isolate in the first place).
4. *Record the concrete GT-6.3 numbers, not just the qualitative
   finding.* **Three numbers, all confirmed by execution
   (`sim/tests/test_wpjoin_fade_boundary.py`), not derived by hand alone:**
   - **Depth**: `extra_loss_db > mean_snr_db - rlf_snr_floor_db` to cross
     the floor at all (25dB at this deployment's typical `mean_snr_db=
     20.0`); **30dB recommended** (5dB of margin, giving an exact -10dB
     during the window).
   - **Minimum fade duration to declare RLF at all: `n310 + t310 = 4,010
     slots (2.005s)`.** Shorter than this, RLF never declares regardless
     of depth — `n311=1` (default) cancels `T310_RUNNING` on the very
     first good slot once the fade ends, before `t310`'s 4,000-slot dwell
     can complete. Not anticipated in §1.5/D6 — found and locked down here.
   - **The GT-6.3a/6.3b boundary: exactly `n310 + t310 +
     cell_search_ceiling_slots = 10 + 4,000 + 6,000 = 10,010 slots
     (5.005s)`.** Fades of 10,009 slots (5.0045s) or shorter reach
     `REESTABLISH`; 10,010 slots (5.005s) or longer fall back to `IDLE` /
     a full re-attach — confirmed exactly at both sides of that boundary,
     not just predicted. The test plan's own literal 10s (20,000-slot)
     fade sits **almost exactly 2x past this boundary**, confirming D6's
     finding numerically: it exercises the IDLE-fallback/full-reattach
     path, not the reestablishment path its own phrasing names. This
     boundary is governed by whether SNR restores before `t311`'s ceiling
     is reached, independent of `JoinConfig`'s own random cell-search
     processing-delay draw *as long as that draw itself stays under the
     ceiling* — the ~1% tail case (`p_expiry`'s own design point) where it
     doesn't is a distinct, rarer failure mode (search times out on its
     own processing delay, not on the channel), not conflated with this
     finding.

### 4.1 Falsifiable inertness — commits 1/2/3/5/6/7, and why commit 4 is the one exception

**Commits 1, 3, 5, 6, 7: standard opt-in-default-`None`/`[]` inertness**,
the same claim WP5 (commits 0/1/2/3/6) and WP6 (commits 1/2/3) each made
and verified for their own dormant/opt-in landings — no corpus scenario
sets any of `UEConfig.join`, `UEConfig.scripted_fade`, so no gate, sampler,
or reset ever engages.

**Commit 2 is the one dormant-by-consequence landing that adds no config
field at all**, and its inertness argument has to be made more carefully
because of that:

1. **Zero RNG consumption.** `sim/rlf.py::step()` takes a plain float and
   draws nothing; its input, `ChannelModel.get_snr_db(ue_id)`, is a dict
   read. The shared-stream hazard that bit `harq_rng` (WP5) cannot occur
   here because there is no new draw to interleave.
2. **No consumer exists yet.** Commit 2 writes only to a local
   `dict[int, RlfDetectorState]` and two `summary` counters
   (`rlf_step_calls`, `rlf_declared_count`) that `RunRecord.from_summary`
   does not read — the same idiom as `harq_allocate_calls`/`_ue_lcp`.
   `regression_corpus.py` snapshots `RunRecord.to_dict()` only.
3. **No ordering perturbation** — `step()`'s loop sits immediately after
   the existing `channel.update(slot_index)` call, iterating
   `scenario.ues` in existing order, mutating nothing any existing code
   reads.
4. **The claim does not depend on RLF never firing** on the existing
   corpus. A declared RLF increments a counter and does nothing else, so
   inertness holds whether or not some corpus UE's real AR(1) fading
   happens to dip below `-5.0 dB` for 10 consecutive slots. **The counters
   must actually be asserted in `sim/tests/test_smoke.py`, not assumed
   zero** — a nonzero `rlf_declared_count` on the existing corpus would be
   a real finding about the corpus's own channel realism and needs to
   surface here, before commit 5 makes RLF load-bearing, not be discovered
   afterward (the mirror image of WP6 commit 4's own
   `harq_exhausted_count`-vs-`bytes_harq_lost` near-miss).

**Commit 4 is predicted NOT clean, and predicted exactly.** Per
`scripts/regression_corpus.py`'s own diff logic (a key-presence diff over
`sorted(set(a) | set(b))`, not a numeric one), adding `join_events` to
`RunRecord.to_dict()` produces **exactly 22 mismatches**, one per record,
each of the form `studyN/case/Sched.join_events: MISSING in baseline ->
None`, and zero mismatches on any other path. `--rel-tol` cannot suppress
a key-presence diff. Re-capture in this same commit, with the reason
stated in the commit message — the same path WP7 took for each of its own
schema-only field additions (`c904e92`/`1799fb1`/`921333c`). Do **not**
special-case `join_events` out of `to_dict()` when `None` to dodge the
diff; that would hide a real schema change rather than show it.
`SCHEMA_VERSION` stays at 1, matching WP7's own precedent of adding
Optional-defaulted fields without a version bump.

### Commit 4 — landed

`sim/run_record.py` (new: `JoinEventRecord`, `RunRecord.join_events`),
`config/metric_panel.yml` (M18/M19 at `status: pending`,
`defaults.slo_green_dwell_s`), `sim/scorecard.py` (`_m18_rejoin_
interruption_time`, `_m19_slo_recovery_time`, `_first_sustained_green` —
the full computation, not a placeholder, since `sim/driver.py` is
deliberately untouched this commit and commits 5/6 (§4's own file list)
touch only `config/metric_panel.yml`'s `status` field, not `sim/
scorecard.py` again), `sim/tests/test_run_record.py` (+3),
`sim/tests/test_scorecard.py` (+6, plus the existing seventeen-metrics
test renamed to nineteen), `regression/baseline_studies_1_3.json`
(re-captured).

**Predicted, before writing any code: exactly 22 structural mismatches,
zero numeric — confirmed exactly, not approximately.**

1. *Restate the predicted diff precisely; confirm it landed exactly.*
   `--check` (run BEFORE `--capture`, specifically to see the predicted
   diff rather than immediately erase it) printed **exactly 22
   mismatches**, one per record, each of the *exact* literal form
   predicted:
   ```
   study1/overload_mult1.0/PF.join_events: MISSING in baseline -> None
   ... (22 total, one per study{1,2,3}/case/scheduler combination)
   ```
   All 22 records — not 21, not 23 — because `RunRecord.join_events`
   defaults to `None` for every record regardless of scenario or
   scheduler (nothing in `sim/driver.py` sets it; this commit doesn't
   touch that file at all), and the corpus has exactly 22 (study 1: 4
   capacity multipliers × 4 scheduler variants = 16; study 2: 3
   schedulers; study 3: 3 schedulers; 16+3+3=22, `scripts/regression_
   corpus.py::_cases()`). No adjustment to the prediction was needed —
   confirmed exactly, not "close enough."
2. *Zero numeric drift is load-bearing — how to tell structural from
   numeric in the diff.* `_diff_value`'s two branches produce
   textually distinguishable output: a numeric mismatch reads
   `"{path}: {a} -> {b} (delta {b-a:+.6g})"` (produced only by the
   `_is_number(a) and _is_number(b)` branch); a structural (key-
   presence) mismatch reads `"{path}.{k}: MISSING in baseline -> {v!r}"`
   and never carries a `delta` clause at all. **All 22 lines are the
   second form; zero contain the word `delta`.** Grepped for it
   directly rather than eyeballed: `grep delta` over the `--check`
   output returns nothing. If a schema addition had also changed a
   computed number, at least one line would carry a `delta` clause
   alongside the structural ones — this run has none, confirming the
   split is clean, not merely plausible.
3. *What M19 still needs; confirm nothing else moves.* Checked against
   the panel file directly, not memory: M19's `requires:` field states
   *"WP-Join (join event log) + `record_timeseries=True`; an exact
   per-message SLO evaluation reusing WP7's message ledger is a
   follow-on commit, not this one."* Confirmed unchanged from the plan.
   `requires:`/`status` on every other entry (M01–M17) checked directly
   against the file both before and after this commit's edit — byte-
   identical; only M18/M19's own two new entries and the new
   `defaults.slo_green_dwell_s` line were added.
4. *Confirm the late-addition provenance and §5-preamble note are in the
   committed file, not just the plan doc.* Both are — verified by
   reading `config/metric_panel.yml` directly after editing it, not by
   re-reading this document: the file's own M04/M09/M16 section is
   followed by a standalone comment block ("M18/M19 are the panel's
   FIRST additions since WP0 pre-registration...") immediately before
   the M18 entry, and each of M18's and M19's own `note:` fields opens
   with *"Added WP-Join commit 4 (not at WP0 -- see the comment above
   this entry)."* `pytest sim/tests -q` — 349 passed (340 + 9 new), 1
   xfailed (unchanged). `regression_corpus.py --check` — clean after
   `--capture` (`git diff` on the baseline file: exactly 22 line
   additions, one `"join_events": null,` per record, no other line
   touched).

---

## 5. `config/metric_panel.yml` additions

**M18/M19 are the first metrics added to this panel since its WP0
pre-registration** — every one of M01–M17 was present (at whatever
`status`) from the panel's original construction. That is permitted:
`config/metric_panel.yml`'s own rule bars *removing* a metric or
*redefining* one to separate schedulers better; it does not bar adding
one. But an addition this late should be visibly deliberate, not quiet,
so it doesn't read as evidence the panel's shape has started drifting:

- **Why M18/M19 weren't foreseeable at WP0**: WP-Join itself postdates
  `config/metric_panel.yml` — it was added to `README.md` §4 only after
  the guarantee-document review that happened after WP0 (and after WP1,
  WP3, WP4, WP7, WP5, WP6). There was no G9 mechanism, and no join/RLF
  concept anywhere in `sim/`, for WP0 to have pre-registered a metric
  against — unlike M04/M09/M16, which *were* foreseeable at WP0 and were
  pre-registered as `proxy`/`pending` placeholders naming their unlock
  condition. G9 had no such placeholder (verified directly against the
  file: zero of the 17 existing entries name G9 or reference join/RLF/
  attach in their `guarantees:`/`description`), which is exactly why
  commit 4 (§4) has to add the rows from scratch rather than promote one.
- **No existing metric is changed to accommodate M18/M19.** Commits 1–3
  and 5–8 touch zero `status`/`requires`/`definition` fields on M01–M17
  (§4's own per-commit metric mapping); M18/M19 land as two net-new
  entries at the end of the file, at `status: pending` until commits 5/6
  promote them, following the panel's already-established `pending`
  contract rather than inventing a new one.
- **Landed at commit 4 of 8** (schema commit), promoted at commits 5/6 —
  i.e. added at the tail end of an 8-commit WP that itself landed after
  seven prior WPs' worth of panel stability. Both the panel entries below
  and `docs/wp-join-plan.md` (this document) record that provenance so a
  future reader sees the addition was deliberate and dated, not an
  undocumented scope creep into WP0's contract.

### M18 — `rejoin_interruption_time`

```yaml
- id: M18
  name: rejoin_interruption_time
  # Added WP-Join commit 4 (8-commit WP), not at WP0 pre-registration:
  # G9/join/RLF had no mechanism to score against until this WP existed,
  # and this WP itself postdates WP0 by seven WPs (docs/wp-join-plan.md
  # §5). No existing M01-M17 entry was changed to add this row.
  definition: >
    Per join/re-join/re-establishment event, wall-clock from the event's
    own trigger instant to procedure completion (radio attached AND app
    handshake complete), broken down by path (warm/cold/reestablish) and
    by phase. For the reestablish path, also reported from the RF-restore
    instant, which is what GT-6.3's own pass line is measured from.
  guarantees: [G9]
  unit: ms
  direction: lower_better
  status: pending      # -> ok at commit 5
  requires: WP-Join (join/RLF event log)
```

One metric with a path tag, not three IDs — the three GT-6 paths differ in
trigger, resumption definition, and threshold, but not in *what* is
measured ("time from trigger to procedure complete"). A path-keyed
breakdown matches how M03 already handles `Message.role` and M13 handles
5QI class; three separate IDs would force permanently-empty rows on any
single-path scenario. `ok`, not `proxy` — computed directly from
timestamps the simulator itself produces.

### M19 — `slo_recovery_time`

```yaml
- id: M19
  name: slo_recovery_time
  # Added WP-Join commit 4 alongside M18, for the same reason: not
  # foreseeable at WP0, since WP-Join itself postdates the panel. No
  # existing M01-M17 entry was changed to add this row.
  definition: >
    Per event, time from the event's trigger (RF-restore, for the
    reestablish path) to the first sustained window (default
    slo_green_dwell_s) in which every flow of the recovering UE is back
    inside its own PDB and GFBR contract. Events where SLOs never go
    green before the run ends are counted, not excluded.
  guarantees: [G9, G3]
  unit: ms
  direction: lower_better
  status: pending      # -> proxy at commit 6
  requires: >
    WP-Join (join event log) + record_timeseries=True; an exact
    per-message SLO evaluation reusing WP7's message ledger is a
    follow-on commit, not this one
```

M18 answers "did the RRC procedure finish"; M19 answers "is the robot
usable again." M19 ≥ M18 for every event by construction, and the gap is
the backlog-drain-plus-ranking-catchup — the interesting finding this WP
exists to surface, which collapsing the two into one number would hide.
GT-6.1/6.3 both name these as two separate pass clauses in the test plan
itself ("handshake round-trip p95 ≤1s" *and* "all streams back within SLO
≤3s"); the panel mirrors that split. `proxy`, staying `proxy`: judging
"green" from head-of-line age against `pdb_ms` stands in for a true
per-message SLO test WP7's ledger could do exactly — the same shape as
M04's own long-standing proxy note.

`config/metric_panel.yml`'s `defaults:` block gains
`slo_green_dwell_s: 1.0  # [OPEN] — anchored to M09's own 1s Jain window,
not independently calibrated`.

### `RunRecord` addition

```python
@dataclass
class JoinEventRecord:
    ue_id: int
    path: str                        # "warm" | "cold" | "reestablish"
    trigger_slot: int
    trigger_ts_s: float
    rf_restore_slot: int | None      # reestablish only
    attached_slot: int | None        # None == never completed before horizon
    attached_ts_s: float | None
    phases: dict[str, float]         # phase name -> duration_ms
    timer_expiries: dict[str, int]   # phase -> count of ceiling-exceeding draws
    rlf_declared_at_slot: int | None
    handshake_rtt_ms: float | None

RunRecord.join_events: Optional[list[JoinEventRecord]] = None
```

`None` means "predates WP-Join"; `[]` means "this run had zero join
events" — the same never-`None`-post-landing convention `message_count`/
`completion_ts_by_role_s` already use. Nothing added to `FlowRecord`/
`SystemRecord`; no thresholded "is it green" field lives in the record —
that's a scoring-time choice, computed by M19 from `join_events` plus the
per-slot timeseries plus each flow's own `pdb_ms`/`gfbr_bps`, matching how
`T_live` thresholding already happens in `scorecard.py`, not `driver.py`.

### The "neighbours unaffected" criterion — no new metric

**No M20.** Two mechanisms instead: (1) primary — a two-arm, seed-matched
comparison inside commit 8's own demo (identical scenario, with and
without the event schedule, same seed), comparing the undisturbed UE's
existing M01/M02/M08 across arms — WP6 commit 4's exact design, needing no
new scoring code. (2) secondary — an `isolation_check(record,
disturbed_ue, window)` scorecard helper, in the same "metrics that need
extra arguments, called explicitly" section M13/M16 already live in,
returning a `dict` keyed by the *existing* IDs it recomputes (`"M01"`,
`"M02"`, `"M08"`) rather than inventing a new one that re-states their
definitions under a different scope — the exact drift the panel's own
multiplicity-guard header warns against.

**One hard caveat, made falsifiable by Prediction 4 below**: "flat" is the
wrong bar. A masked UE frees PRBs/CCEs every scheduler in this branch
redistributes; the criterion commit 8 actually checks is **"never worse,"**
with the improvement's sign and magnitude reported.

---

## 6. Flags — needing sign-off or noted for someone else to act on

1. **README §6's timer-banner citation names `contention.log`; the real,
   only file is `calibration-logs/twotier_startup_gnb.log`.** Per
   `calibration-logs/README.md`, `contention.log` is a phantom path from an
   old layout diagram, never committed. Not fixed by this WP (out of
   scope for a planning document); flagged for a small follow-up README
   correction.
2. **D6's finding (§3) should reach the test-plan owner, not just this
   repo — now with exact numbers (commit 3), not a qualitative estimate.**
   The GT-6.3a/6.3b boundary is exactly `n310 + t310 +
   cell_search_ceiling_slots = 10,010 slots (5.005s)`, confirmed by
   execution: fades of 10,009 slots (5.0045s) or shorter reach
   `REESTABLISH`; 10,010 slots or longer fall back to `IDLE`/a full
   re-attach. The test plan's own literal 10s (20,000-slot) scripted fade
   sits almost exactly 2x past this boundary, so it exercises the
   IDLE-fallback/full-reattach path, not the reestablishment path its own
   phrasing ("≤10s including re-establishment") describes. A second,
   related number worth the same visibility: fades **shorter** than
   `n310 + t310 = 4,010 slots (2.005s)` never declare RLF at all,
   regardless of depth — there is a floor on usefully short fades too,
   not just a ceiling on how long one can be before the path changes.
   This WP builds both variants (D6) rather than silently picking one,
   but the test plan's own wording is worth raising separately, with
   these numbers attached.
3. **`T_live` (`README` §8, still `[OPEN]`) calibrates M19's green-line and
   every G9/G3 pass judgment** — not this WP's to resolve; M19 is built to
   consume whatever value it resolves to.
4. **The two ▷-marked thresholds in G9 (15 s, 10 s) are provisional**
   ("proposed defaults to be ratified with the client") — numbers this WP
   reports against them are measurements against a draft target, restated
   at §0 and Prediction 3 so they are never later mistaken for a validated
   result.
5. **`sim/traffic.py`'s `adaptive` source kind is distorted by the source
   gate** (§1.4: suppressed `observe_delivery` feedback ratchets its
   offered rate down for reasons unrelated to the radio) — avoid it in the
   first GT-6.1/6.2 scenarios until a follow-up addresses it properly.
6. **`FIVE_QI_LCG`/M04/the crumb-fraction gap and every other standing
   `[OPEN]` item in `README.md` §8 are untouched by this WP** — none of
   WP-Join's mechanisms interact with BSR quantization, LCG mapping, or
   the SR-path chain (only `sim/ul_access.py`'s `rach_recovery_until` field
   is read as a design precedent, never modified).

---

## 7. Status

**Commits 1–4 of 8 landed** (`sim/join.py` dormant FSM + delay sampler;
`sim/rlf.py::step()` wired into `driver.py`'s slot loop, unconditional,
diagnostic-only; deterministic scripted fade in `sim/channel.py`, with
the GT-6.3a/6.3b boundary now pinned exactly at 10,010 slots/5.005s;
M18/M19 + `RunRecord.join_events` schema, regression baseline
re-captured with exactly the predicted 22-record structural diff and
zero numeric drift). Commits 5–8 not yet started. Two scope questions
that would otherwise be
`[OPEN]` here were put to the user and are recorded resolved at D0a/D0b.
Section 8 (end-of-WP judgment-calls review, per CLAUDE.md's standing step)
will be added after commit 8 lands, following `docs/wp5-plan.md`/`docs/
wp6-plan.md`'s own precedent.
