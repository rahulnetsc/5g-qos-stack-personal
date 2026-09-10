# G3 as a stress experiment — can the network make a healthy robot look dead?

**2026-09-09.** G3 rebuilt in the shape of G1, G2, G9 and G12. Step 0 and the
scored predictions are `docs/g3-registration-2026-09-09.md`; the slide is
`docs/g3-slide-source.md`. Artefacts `sweeps/g3-stress/g3_stress.json` and
`sweeps/g3-stress/g3_sr_probe.json`, both stamped.

**Every earlier G3 number is stale and is treated as such.** The published row
(*"max gap ≤ 500 ms: PF 10/10, Reservation 10/10, TwoTier 4/10"*) was scored
over all flows including the saturating background, so a flood's own starvation
counted as a telemetry liveness failure; it was corrected to 10/10 on
pre-rebuild code, before M-9, M-6, random access, SRBs, `cp_floor` and the GBR
offered-shortfall fix. Nothing here inherits from it.

---

## 0. Why this one is the hardest of the five so far

**G1 and G2 are downlink.** The gNB reads its own buffers: no scheduling
request, no buffer-status report, no estimate that can desync. G3 is **uplink**,
so every mechanism this project has traced is in play at once — the cold-start
lock-out, the BSR desync, the never-served fault, `cp_floor`, and the Tier-1.5
service-interval floor that exists specifically to rescue a stalled telemetry
bearer. The test plan calls the GT-2 family *"the family this scheduler's known
failure mode makes existential"*, and it is uplink that makes it so.

It is also the guarantee whose **scored statistic** needed the most repair, and
the repairs are what §1 and §2 are about.

## 1. The clause has three parts, and two of them were being scored wrongly

L97: *"Max telemetry inter-arrival gap at MEC ≤ ▷ T_live/4 (500 ms); zero gaps
≥ T_live over the full campaign; p98 ≤ PDB."*

**Part 2 is CAMPAIGN-wide and the current scorer treats it per-run.**
`scripts/guarantee_scorecard.py` tests `G3_M03_gaps_over_tlive_prot == 0` on
each row, so a 9-of-10 result reads as *"90 %"* — while the clause is failed by
**one gap anywhere in the campaign**. The right verdict is an AND over every
gap, and when the count is zero the demonstrable bound is §5.3's rule of three
over the **gap** population, which is why the denominator travels with it.

**Part 3 is numerically G1's own statistic under a different guarantee's
name.** The scorecard row reads `G1_M01_p98_prot`. Stated so one number does
not silently carry two verdicts.

**Nothing else is in the clause, and I checked rather than assumed.** GT-2.1
adds *"B's SLOs unaffected"*; GT-2.2 adds *"bg receives residual only"* and the
floor-arming verification; **GT-2.3's own KPIs — first-packet p99 ≤ 300 ms,
time-to-steady ≤ 1 s — belong to G4**, and are out of scope rather than quietly
folded in. §5 also asks for the T_live/2 count, which is reported.

## 2. The population — part 3's was wrong, measured on the row's own artefact

The clause says **telemetry**. `G3_M03_prot_ms` is a worst-flow maximum over
the protected fleet, which includes camera, lidar and the DL command loop.
Checked on `sweeps/m6-2026-09-07/plain/core.json`, the artefact the published
row came from, 30 rows:

| clause part | statistic | how often its winner is telemetry |
|---|---|---|
| part 1, max gap | `G3_M03_prot_ms` | **30 of 30** |
| part 3, p98 | `G1_M01_p98_prot` | **22 of 30** — the other 8 are the 5QI-2 **camera**, a 150 ms-PDB video bearer scored against telemetry's 95 |

So part 1's population is right on this workload by luck (telemetry has the
slowest cadence, so it wins a gap contest naturally) and **part 3's is not**.
Both are scored here on the telemetry flow, derived from the scenario.

**And a flow with fewer than two completions FAILS all three parts.** M03
excludes such a flow from its worst-gap contest — right for a worst-of-fleet
statistic, exactly wrong for an instrument. For G3, the telemetry going silent
*is* the failure.

## 3. THE STEP-0 FINDING: the telemetry bearer's own configuration is worth
more than the choice of scheduler

**Every 5QI-1 telemetry flow in this repo is `flow_class="Delay"` with
`gfbr_bps=0`** — `sim/parametric.py`, `sim/fleet.py`'s DRONE, `sim/scenarios/
{g1,g2,g9,g11}.py`, all six YAML scenarios. Three things follow and each one is
a reason the clause could not be scored properly before.

1. **5QI 1 is a GBR 5QI** (TS 23.501 Table 5.7.4-1), so a 5QI-1 bearer without
   a GFBR is an infidelity. `sim/scenarios/g1.py` reached the same conclusion
   independently for its downlink command bearer.
2. **Part 3 is a GBR-conformance statistic.** §5: *"while the flow stays within
   GFBR, 98 % of packets shall not exceed the PDB."* With no GFBR there is no
   "within GFBR", so those semantics never attached to any published G3 number.
3. **`FlowConfig.effective_pbr_bps()` returns 0 for such a flow**, so the UE's
   own logical-channel prioritisation gives telemetry **no token bucket** and
   skips it in LCP round 1. §3.2 corrects what happens next, and the correction
   matters: **telemetry is never outranked — it is never reached.**

**Measured before this campaign's scenario existed**, N=6, seed 1, cap 4, on
the parametric factory mix, worst telemetry flow of six:

| arm | PBR 0 (the repo as it stood) | PBR 24 kbps (the offered rate) | PBR 500 kbps (§2.1's proposal) |
|---|---|---|---|
| PF | p98 22.75 ms | 11.00 | 10.75 |
| Reservation | 23.00 | 19.00 | 17.00 |
| **TwoTier** | **98.50 ms, max gap 313 ms, 94/100 messages** | **51.50, 149 ms, 100/100** | 48.25, 154 ms, 100/100 |

**A prioritised bit rate at the flow's own offered rate captures the whole
benefit of the plan's 20× larger proposal.** That settles the GFBR value: §5
needs offered ≤ GFBR, this repo's own invariant needs offered ≥ GFBR, so
**offered == GFBR is the unique point satisfying both.**

### 3.2 CORRECTION — the mechanism above was wrong, and the measured one is sharper

**An earlier version of this section said telemetry "is served only from LCP
round 2, out of whatever the camera's 4 Mbps bucket leaves". That is false, and
the standard says so.**

**TS 38.321 §5.4.3.1 step 3 serves ALL logical channels in strict decreasing
priority order *regardless of the value of Bj*.** 5QI 1 carries priority 20 and
5QI 2 carries 40 (TS 23.501 Table 5.7.4-1, and `scheduler/flow.py`'s own
table), so in round 2 telemetry is served **first**, tokens or not. It is not
waiting behind the camera at any point.

**The only mechanism consistent with the standard is that round 1 exhausts the
grant**, so step 3 never runs. That is what happens, and it is now measured
rather than reasoned.

#### The port implements step 3 correctly

`sim/ue_lcp.py::fill` sorts once by `priority_level` and round 2 iterates that
order with the buckets ignored entirely. **Not a port defect**, and the trace
agrees: over the starved cell, **zero** grants had round 2 run and skip
telemetry.

#### OAI's own UE does not, and the significance is CONDITIONAL on whose UE runs

`oai-branches/two-tier/nr_ue_scheduler.c`. `select_logical_channels`
(`:2538-2556`) builds `lcids_bj_pos` from **only** the channels with `Bj > 0`,
and the `do { … } while` multiplexing loop (`:2744-2814`) iterates *that same
array* on every run — `lcp_allocation_counter` 0, 1, 2, … — with the loop's own
continuation test (`get_dataavailability_buffers(avail_lcids_count,
lcids_bj_pos, …)`) scanning the same set. **A channel with `Bj ≤ 0` is in no
run at all.** And with `pbr == 0` the update at `:1490-1494` adds nothing, so
`Bj` never becomes positive. The C's own code flags the gap:
`select_logical_channels` opens with *"(TODO: selection of logical channels for
logical channel prioritization procedure as per 5.4.3.1.2 …)"*.

**BUT THE SPLIT HAPPENS INSIDE THE UE, AND WHICH UE IS NOT ESTABLISHED HERE.**
`nr_ue_scheduler.c` is OAI's **nrUE**, not the gNB. It governs a robot's uplink
only if that robot's modem *is* an OAI UE. What this repo establishes:

| | evidence |
|---|---|
| the **testbed** runs OAI UEs | test plan §2: *"Current testbed: 2 OAI rfsim UEs (containers `oai-ue1`/`oai-ue2`)"*; `calibration-logs/twotier_startup_gnb.log`'s `CMDLINE` is `nr-softmodem --rfsim` |
| the **production robots' modems** | **not stated anywhere** — §2's asset table names IMSIs and IP addresses only, and §11's seven open items do not include it |

**So the claim is conditional, and it is worth stating in the direction that
matters:**

- **If the robots carry commercial modems**, each implements its own LCP and
  §5.4.3.1 step 3 presumably applies. **`sim/ue_lcp.py` is then the right model
  and OAI's deviation is a TESTBED artefact** — not a product defect, but a
  **threat to the hardware campaign's own validity**, because a GT-2.1 or
  GT-2.2 run on OAI UEs would show a starvation the product does not have and
  attribute it to the gNB scheduler.
- **If the robots carry OAI UEs**, the deviation is live in the product and is
  strictly worse than what this simulator models, since telemetry would get
  nothing even when the block has room.

**Either way this port is defensible** (it models a standards-compliant UE) and
**either way the reading changes**, which is why it is flagged rather than
resolved. **Resolving it is one question to the client: what modem do the
robots carry?** It belongs on §11's open-items list and is not there.

#### The counts, per grant, on the starved cell

N=6, TwoTier, seed 1, GT-2.2, telemetry PBR 0. The instrumented fill is a
verbatim copy of the real one; per-flow delivered bytes match an uninstrumented
run exactly, so the probe is not perturbing what it measures.

| | grants |
|---|---|
| UL grants observed | 108 373 |
| … with telemetry **backlogged** | **24 971** |
| telemetry served in round 1 | **0** — correct, it has no bucket |
| telemetry served in round 2 | 909 |
| **telemetry served in NEITHER** | **24 062** |
| … of those, **grant exhausted in round 1** (`remaining == 0`) | **24 062 — every one** |
| … of those, **round 2 ran and skipped telemetry** | **0** |

**The camera's bucket is 72× the transport block.** Median bucket at grant
**20 784 B**, median block **288 B**; the bucket equals or exceeds the whole
block on **24 830 of 24 971** grants. So round 1 hands the entire block to the
camera — measured directly: on the starved grants the camera's round-1 take
**equals the transport block** at the minimum, the median and the maximum.

#### And this is why the PBR lever works

With a PBR at the flow's own offered rate, telemetry enters round 1 and the
same priority order reaches it **before** the camera:

| | PBR 0 | PBR = GFBR |
|---|---|---|
| grants with telemetry backlogged | 24 971 | **3 264** |
| served in round 1 | 0 | **2 983** |
| served in neither round | **24 062** | 271 |
| messages delivered, six robots | 87, 69, 100, 100, 68, 100 | **100 × 6** |

**The lever does not change who outranks whom. It changes which round
telemetry is reached in.**

### 3.3 THE GNB HALF — nothing sizes an uplink grant by urgency, in either code base

**`pdb_ms` is a RANKING term, and ranking decides which UE is served, not how
deep the block is.**

**In the port**, `_allocate_direction`'s uplink sizing is
`b_eff = max(ul_total_target_bytes, ue_backlog, gbr_bytes_slot)` →
`prbs_needed` → `prbs_used = min(prbs_left, max_rbSize, prbs_needed)`. No PDB,
no deadline, no urgency. For uplink the candidate's `pdb_ms` is **discarded at
the call site** (`_ul_gbr_and_pdb`'s return is unpacked into `_pdb_ms`); the
deadline reaches the uplink only through `urgency01` folded into `coef`, which
is a ranking tier.

**In the deployed C**, `ia_p5g_scheduler.c:3193-3204` computes
`B_eff = max(estimated_ul_buffer − sched_ul_bytes, ul_total_target_bytes,
gbr_bytes_slot)`. A search of the entire uplink sizing region (`:3080-3290`)
for `pdb`, `urgency` or `deadline` returns **nothing**.

**So a UE can be ranked first and still receive a block too small for its
urgent flow.** Measured, telemetry backlogged, TwoTier, PBR 0:

| | N = 6 | N = 16 |
|---|---|---|
| grants with telemetry backlogged | 24 971 | 117 216 |
| transport block, median | **288 B** | **288 B** |
| transport block, p90 / max | 1 361 / 4 083 B | **288 / 371 B** |
| **grant is PRB-limited** (block < UE backlog) | **24 971 of 24 971 — 100 %** | **117 216 of 117 216 — 100 %** |
| **block smaller than ONE 300 B heartbeat** | **20 882 — 83.6 %** | **113 807 — 97.1 %** |

**At sixteen robots, 97 % of the grants issued to a robot with a pending
heartbeat are too small to carry that heartbeat whole**, and every grant in the
campaign is PRB-limited rather than demand-limited — the gNB is not
under-estimating demand, it is dividing a fixed PRB budget.

**This is a finding about the deployed scheduler, not a provisioning gap.** The
uplink comparator was given a deadline term and the grant sizer was not, so
urgency can win the sort and still lose the block. The prioritised-bit-rate
lever mitigates it inside the UE — it gets the heartbeat to the front of the
one round that runs — but it cannot make a 288-byte block carry 300 bytes.

**BUT THE MISSING DEADLINE TERM IS NOT WHAT MAKES THE BLOCK SMALL, AND §3.4
CORRECTS THAT IMPLICATION.** A deadline-aware sizer could not ask for more than
`max_rbSize`, and `max_rbSize` is set by FIX-2's own GBR follower reserve on
74–99.7 % of grants at every fleet size measured. The reserve is what binds.

### 3.4 WHAT ACTUALLY BINDS: the anti-monopolisation reserve, measured

FIX-2 caps each uplink grant by reserving `min_rb` for every still-unserved GBR
UE ranked below the current one:

```
reserve_rb = gbr_below[i] * min_rb          # min_rb = 5
cap        = max(prbs_left - reserve_rb, min_rb)
max_rbSize = min(slot.prb_count, cap)       # prb_count = 55
```

**Eleven such followers exhaust a 55-PRB band.** Reconstructed exactly per
grant — the rank stream gives the sorted candidates with `has_gbr` and
`gbr_bytes_slot` as recorded factors, and a pass-through wrapper on
`_emit_grant` gives the realised PRB count in candidate order, which is what
makes `prbs_left` recoverable. TwoTier, seed 1, the **scored** configuration
(telemetry PBR = GFBR):

| N | `gbr_below` med / max | reserve **clamps to min_rb** | grant **equals `max_rbSize`** | grant is exactly 5 PRB | **top-ranked clamped** | PRB med / max |
|---|---|---|---|---|---|---|
| 6 | 2 / 5 | 20.7 % | 77.9 % | 78.4 % | **0 %** | 5 / 55 |
| 7 | 3 / 6 | 11.1 % | 74.6 % | 84.2 % | **0 %** | 5 / 55 |
| 8 | 3 / 7 | 10.0 % | 74.3 % | 86.1 % | **0 %** | 5 / 55 |
| 12 | 5 / 11 | 12.3 % | 86.2 % | 95.5 % | 3.8 % | 5 / 30 |
| **16** | 10 / 15 | **100.0 %** | 99.7 % | 99.7 % | **100.0 %** | **5 / 10** |
| **24** | 18 / 23 | **100.0 %** | 99.6 % | 99.6 % | **100.0 %** | **5 / 5** |

**Three things follow, and the middle one is the sharpest.**

**(a) The reserve sets the grant at EVERY fleet size.** The grant equals
`max_rbSize` on **74.3–99.7 %** of grants from six robots upward, and
`max_rbSize` is the reserve-reduced budget. At N=8 the median `gbr_below` is 3,
so the reserve withholds **15 of 55 PRB — 27 % of the band — on a median
grant**, without ever reaching the floor. **That is what makes the median block
288 bytes.** It is not demand under-estimation: every grant in §3.3 is
PRB-limited.

**(b) ABOVE ELEVEN ROBOTS THE FLOOR SATURATES AND EVEN THE TOP-RANKED UE GETS
min_rb.** The arithmetic is exact: 55 ÷ 5 = 11, and the top-ranked candidate is
clamped on **0 % of slots at N ≤ 8**, 3.8 % at N=12, and **100 % at N=16 and
N=24**. At N=24 *every* grant in the run is 5 PRB — the largest PRB count
across 337 599 grants is 5. **The anti-starvation reserve produces starvation
once the fleet exceeds the band divided by `min_rb`.**

**(c) But it is NOT what breaks G3 at the boundary.** TwoTier's clause boundary
is **7** and Reservation's is **6** — below the threshold, where the top-ranked
UE is never clamped. At N=8, the first failing size, the floor fires on 10 % of
grants and never on the leader, yet telemetry already falls to 89 of 100 on one
robot. **So the reserve is a large-fleet amplifier, not the boundary
mechanism**: below eleven robots what shrinks a grant is the reserve *plus*
`prbs_left` depletion by the UEs served earlier in the same slot; above eleven
the floor makes it total.

**Which binds, in one line: the reserve, at every fleet size — as the CAP below
eleven robots and as the FLOOR above.** The missing deadline term in sizing is
real and is reported in §3.3, but it is **inert**: `prbs_used =
min(prbs_left, max_rbSize, prbs_needed)`, so no urgency-derived demand could
exceed a `max_rbSize` the reserve has already set to 5.

**And the delivery pattern at large fleets is bimodal rather than uniform**,
which the reserve alone does not explain: at N=16 the sixteen robots deliver
`3, 4, 4, 5, 5, 6, 7, 27, 89, 90, 93, 93, 93, 94, 95, 96` of 100 — half nearly
whole, half nearly nothing. Reported, not explained; separating "clamped" from
"consistently ranked last" needs a per-slot rank trace this probe does not
carry.

**A note on the PBR-0 control, because the contrast is informative.** The same
measurement with telemetry at PBR 0 gives an identical reserve picture
(`gbr_below` median 2/6/10/18 at N=6/12/16/24, floor saturating at 100 % from
N=16) but far worse delivery — at N=12, `0,0,0,0,0,1,1,1,1,2,2,2` of 100
against the scored configuration's `10,12,14,19,20,83…99`. **The reserve is the
same; what the prioritised bit rate changes is whether the heartbeat gets any
of the small block the reserve produces.** Both findings are real and they
compose.

### 3.1 And the coupling is the deployed derivation, read from the C

Files searched: `oai-branches/mac_rrc_dl_handler.c` (the deployed DU's F1AP
bearer-setup handler), `oai-branches/two-tier/nr_ue_scheduler.c` (the UE MAC —
the file that would hold the LCP if it existed anywhere, and it does), and all
four `oai-branches/{two-tier,reservation}/gNB_scheduler_*.c`.

- **A DRB's uplink `prioritisedBitRate` comes from its GFBR and nothing else.**
  `get_bearerconfig_from_drb` (`:294-350`) derives `gbr_ul_kbps` from
  `gbr_qos_flow_information->ul.guaranteedFlowBitRate`, and the `[IA-P5G FIX]`
  comment (`:316-343`) says so outright: *"This value is consumed solely by
  get_DRB_RLC_BearerConfig() to pick a prioritisedBitRate enum."*
- **A non-GBR DRB passes zero** — `gbr_ul_kbps` is initialised to `0` at `:296`
  and assigned only inside the `if (…gbr_qos_flow_information)` guard. So
  *"no GFBR → no PBR"* is the deployment's own arithmetic.
- **The UE really skips a zero-bucket channel in round 1** —
  `nr_ue_scheduler.c:2543-2553`, *"selection of logical channels with Bj > 0"*,
  with `Bj` refilling at `pbr` (`:1479-1501`). That is what `sim/ue_lcp.py`
  ports.
- **AND THE FAILURE MODE IS ALREADY ON RECORD FROM HARDWARE**, from the other
  end of the same knob: the same comment (`:326-335`) describes a PBR that
  outran the achievable rate and *"observed as one flow taking ~85 MB while its
  two siblings on the same UE got ~10 MB and ~4 bytes."*
- **Its own precondition for apportionment is met here** — the comment requires
  the sum of a UE's PBRs to stay inside its achievable rate; telemetry 24 kbps +
  camera 4 Mbps = 4.02 Mbps per robot.

**What could not be established, stated rather than assumed.**
`get_DRB_RLC_BearerConfig` is not in the vendored subset and the full OAI
checkout `CLAUDE.md` names is **absent from this machine** (checked), so which
enum a zero maps to is not readable here. And **`bsd_ms` has no provenance at
all**: 100 ms is this repo's default, the only bucket duration in the deployed
source is the SRB path's **5 ms** (`mac_rrc_dl_handler.c:227-228`), and 100 ms
biases **toward** the starvation this campaign measures — hence the control.

## 4. THE SECOND STEP-0 FINDING, and it is in MY OWN instrument

**An inter-arrival maximum cannot see a robot that goes dark and stays dark.**
A gap needs a message on both sides of it, so a flow whose last message lands at
t = 1.7 s of a 10 s run has **no gap at all** describing the 8.3 s of silence
that follows.

**This was found by decomposing the campaign's own first artefact, before any
verdict was published** (`sweeps/g3-stress/g3_stress.PRE-SILENCE-FIX.json`,
kept for exactly this reason). Over the fleet axis:

**19 flow-runs where the robot was silent for up to 9.5 s while the scored
maximum read 114–342 ms.** The worst examples:

| arm | N | messages delivered | scored max gap | head silence | tail silence |
|---|---|---|---|---|---|
| TwoTier | 16 | **3 of 100** | 185.0 ms | 569 ms | **9 143 ms** |
| TwoTier | 16 | 3 of 100 | 342.0 ms | 477 ms | **8 984 ms** |
| TwoTier | 24 | 6 of 100 | 174.0 ms | 296 ms | **9 100 ms** |
| TwoTier | 12 | 18 of 100 | 146.5 ms | 4 ms | **8 291 ms** |
| Reservation | 12 | 61 of 100 | 116.0 ms | **3 962 ms** | 78 ms |

**A robot that delivered three of a hundred heartbeats scored a comfortable
pass.** That is the same defect class as the G3 row this campaign withdraws and
the same shape as G2's — **reproduced inside the instrument built to replace
them**, which is why it is reported rather than quietly fixed.

### 4.1 The fix does not redefine the clause

Two statistics are published side by side:

- **part 1** — the clause **as literally written**: a maximum over
  inter-arrival gaps. Unchanged, because that is what L97 says.
- **part 1s** — the same 500 ms bound over the **longest silence the window can
  observe**, adding the head (session start to first message) and the tail
  (last message to run end).

**The gap between the two IS the finding.** A clause phrased as an
inter-arrival statistic cannot express its own worst failure, and saying so is
more useful than widening the definition and moving on. Part 2's count uses the
extended set, because *"zero gaps ≥ T_live"* is a claim about the MEC seeing
nothing for two seconds and a terminal silence is exactly that.

**Head and tail are LOWER BOUNDS** — a silence can extend past the window on
either side — and the head contains attach, which is G9's clause rather than
G3's, so it is reported separately as well as scored.

**The cost of the correction was one re-run**, 576 runs against the first
pass's 486 (the extra 90 are §5's SR probe). The first pass is kept as the
before-and-after evidence rather than deleted.

## 6. THE RESULT — G3 FAILS on both QoS arms and PASSES on PF

**The clause is not met.** Part 2 is campaign-wide, and the campaign has
**36 telemetry silences of two seconds or more in 115 872 scored silences**:

| arm | part 2, campaign-wide | silences ≥ 2 s |
|---|---|---|
| **PF** | **PASS** | **0 of 40 854** — demonstrable bound ≤ 7.3 × 10⁻⁵ (rule of three) |
| **Reservation** | **FAIL** | 10 of 36 514 |
| **TwoTier** | **FAIL** | 26 of 38 504 |

**A two-second silence is twenty consecutive heartbeats missed.** That is not
congestion; it is a robot the MEC would halt.

### 6.1 The fleet axis — and the boundaries are G10's own, on both QoS arms

`n_ues` 4 → 24, cap 4, committed ×1.0, 10 seeds. `part1 | part1s` are the
clause as written and the silence-aware form; `g` is the worst inter-arrival
gap, `s` the worst observable silence, `p` the worst p98, all in ms.

| N | PF | Reservation | TwoTier |
|---|---|---|---|
| 4 | 10\|10/10/10 · g110 s110 p9.8 | 10\|10/10/10 · g110 s110 p7.8 | 10\|10/10/10 · g103 s103 p4.0 |
| 6 | 10\|10/10/10 · g205 s205 p15.2 | 10\|10/10/10 · g120 s120 p18.5 | 10\|10/10/10 · g166 s166 p66.5 |
| 7 | 10\|10/10/10 · g114 s114 p13.5 | **9\|9/9/9** · g125 s125 p22.2 | 10\|10/10/10 · g159 s159 p64.2 |
| 8 | 10\|10/10/10 · g113 s113 p13.0 | **4\|4/4/4** · g124 s124 p23.8 | **9\|8/9/10** · g1111 **s3077** p89.8 |
| 10 | 10\|10/10/10 · g116 s116 p17.0 | **5\|4/4/5** · g125 **s6762** p62.0 | **7\|7/8/6** · g2955 s5248 p99.2 |
| 12 | 10\|10/10/10 · g202 s202 p20.2 | **7\|4/6/7** · g198 **s3962** p61.0 | **3\|2/4/1** · g5995 **s9178** p100.2 |
| 14 | 10\|10/10/10 · g116 s116 p25.2 | **2\|1/4/2** · g1242 s5429 p99.8 | **8\|7/7/2** · g5876 s9205 p100.2 |
| 16 | 10\|10/10/10 · g201 s201 p27.8 | **0\|0/2/2** · g5149 s6431 p99.8 | **9\|2/2/4** · g3685 **s9506** p100.2 |
| 24 | 10\|10/10/10 · g122 s122 p49.0 | **0\|0/0/0** · g3202 s3202 p93.2 | **9\|7/7/0** · g1115 s9100 p100.2 |

**Boundaries — the last fleet size passing on every seed, contiguous from the
smallest:**

| | part 1 | part 1s | part 2 | part 3 | all |
|---|---|---|---|---|---|
| **PF** | **24+** | **24+** | **24+** | **24+** | **24+** |
| **Reservation** | **6** | 6 | 6 | 6 | **6** |
| **TwoTier** | **7** | 7 | 7 | 8 | **7** |

**AND THOSE ARE G10'S OWN BOUNDARIES ON THE QOS ARMS, EXACTLY.** G10's
admissible fleet, re-measured 2026-09-09, is **PF 12 / Reservation 6 / TwoTier
7** on a contract-attainment criterion. G3's liveness boundary lands on **6 and
7** — the same two numbers — while **PF's liveness boundary is at least 24,
twice its own contract boundary**. So on the QoS arms the fleet size that breaks
the GBR contract is the fleet size that breaks the heartbeat, and on PF the two
are far apart. That is a common-cause result, not a coincidence: what fails is a
UE running out of uplink service, and both criteria read it.

**The registered prediction P3 is REFUTED.** It predicted G3's boundary would
sit *below* G10's, on the reasoning that a maximum is stricter than a rate
average. It is not below; it is identical.

### 6.2 What PF is doing differently, and it is not free

PF passes every criterion at every fleet size with **zero telemetry messages
lost at any N**. The QoS arms lose them in quantity:

| N | Reservation messages missing | TwoTier |
|---|---|---|
| 7 | 100 of 2 000 | 0 |
| 8 | **600 of 2 000** | 50 |
| 12 | 366 | **600 of 2 000** |
| 16 | **862 of 2 000** | 823 |
| 24 | **1 140 of 2 000** | 356 |

**And PF delivers 2.8× more protected uplink at N=24** — 67.06 Mbps against
Reservation's 23.87 and TwoTier's 24.20. So this is not PF trading video for
telemetry at the margin; **PF is carrying more of everything.**

**It does sacrifice something, and it should be said.** PF's neighbour-camera
PDU-set completeness falls from 0.9967 to **0.0300** as the fleet grows to 24 —
video is destroyed. But both QoS arms reach **0.0000** from N=7 or N=8 onward,
so PF's video is worse only at the very top of the axis and better everywhere
else. **Neither QoS arm buys video by giving up telemetry; it loses both.**

### 6.3 The silence-aware statistic is what makes the failures visible

Compare the two columns in §6.1 at the failing points:

| cell | worst inter-arrival gap | worst observable silence | part 1 | part 1s |
|---|---|---|---|---|
| **Reservation N=10** | **125 ms — a 4× PASS** | **6 762 ms** | 5/10 | **4/10** |
| **Reservation N=12** | 198 ms — a PASS | 3 962 ms | 7/10 | **4/10** |
| **TwoTier N=16** | 3 685 ms | 9 506 ms | 9/10 | **2/10** |
| **TwoTier N=8** | 1 111 ms | 3 077 ms | 9/10 | 8/10 |

**Reservation at ten robots is the sharpest case: the clause as literally
written reads 125 ms, four times inside its bound, while a robot was silent for
6.8 seconds.** At TwoTier N=16 the correction moves the verdict by **seven runs
of ten**.

### 6.4 The UL service-interval floor fires, and it does not save telemetry

**First measurement of Tier 1.5 firing anywhere in this project.** CLAUDE.md's
audit records it as unobservable, *"activation unknowable"*, and it is neither:

| N | 4 | 6 | 7 | 8 | 10 | 12 | 14 | 16 | 24 |
|---|---|---|---|---|---|---|---|---|---|
| **TwoTier floor fires** (10 seeds) | 1 | 42 | 141 | 264 | 527 | 334 | 428 | 575 | **744** |

**PF and Reservation report `None`, not zero** — their comparators have no such
tier, and **Reservation has no floor even in principle**. That distinction is
kept in the artefact rather than flattened.

**The floor arms, fires, rises with load — and TwoTier still fails from N=8.**
So the mechanism built to rescue a stalled telemetry bearer is active and
insufficient at the same time. That is a stronger statement than the previous
record could make, which was that activation was unknown.

## 7. The controls

### 7.1 The telemetry bearer's prioritised bit rate — the campaign's biggest single lever

N=6, cap 4, 10 seeds, against the same cell with the PBR configured:

| arm | PBR at the offered rate (scored) | PBR 0 (the historical configuration) |
|---|---|---|
| PF | 10/10/10 · p98 median 8.75 | 10/10/10 · 17.75 |
| Reservation | 10/10/10 · 16.62 | 10/10/10 · 20.38 |
| **TwoTier** | **10/10/10 · 15.75, 0 messages lost** | **10/10/7 · 93.25, worst gap 438 ms, 121 of 2 000 lost** |

**P6 is HALF RIGHT and the miss is worth recording.** It predicted the control
would move *every* arm by more than the arm difference. On G3's own cell it
moves **only TwoTier** — from a clean pass to a part-3 failure on 3 of 10 seeds,
with p98 median 5.9× worse. PF and Reservation are unmoved at N=6. The Step-0
probe on the parametric mix *did* move all three, so the effect is
workload-dependent, and quoting the probe's three-arm result on this cell would
have been the configuration-carrying error this project has recorded three times.

**What survives, and it is the operator-facing half:** a single UE-side RRC
parameter turns TwoTier's telemetry from a pass into a failure at a fleet size
inside its own admissible limit. **That is a bigger lever than the choice of
scheduler at N=6.**

### 7.2 The bucket duration — the finding survives its own weakest constant

`bsd_ms` 100 → 5 ms (the only value the deployed source states anywhere):
**no degradation on any arm.** TwoTier's worst gap improves 165.5 → 137.2 ms and
its p98 median 15.75 → 18.75. **P7 holds**: the finding is not an artefact of an
unprovenanced 20× bucket.

### 7.3 The long-horizon check — and it does NOT come back clean

50 s per run, 500 messages per robot, N=6: **all three arms pass 10/10/10, zero
silences over either threshold in 10 015–10 019 gaps.** But the maximum moves:

| arm | worst gap at 10 s | at 50 s | ratio |
|---|---|---|---|
| PF | 204.8 ms | 204.8 ms | 1.00 |
| Reservation | 120.5 ms | 201.2 ms | 1.67 |
| **TwoTier** | **165.5 ms** | **416.8 ms** | **2.52** |

**TwoTier's worst gap goes from 3.0× inside the bound to 1.2× inside it over a
5× longer window.** So **every boundary in §6.1 is an UPPER bound on the
admissible fleet**, and the direction is measured rather than assumed. PF is
flat, so this is TwoTier's sensitivity and not the statistic's.

## 8. The positive control — failure is reachable, and the parts fail in a definite order

The radio was degraded until the clause broke: the one lever that weakens the
cell without touching the instrument, the bound or the scoring. N=6, cap 4,
2 seeds, worst of the pair.

| SNR | messages (of 400) | worst gap | worst p98 | **p98 ≤ 95** | **max gap ≤ 500** | **zero ≥ 2 s** |
|---|---|---|---|---|---|---|
| 20 → 10 dB | 400 | 118–259 ms | 10–89 ms | PASS | PASS | PASS |
| **5 dB** | 345–387 | 132–299 ms | **55.75–99.75** | **FAIL** | PASS | PASS/FAIL |
| **0 dB** | 310–375 | **838–967 ms** | 98–100 ms | FAIL | **FAIL** | PASS |
| **−3 dB** | 172–181 | **2 209–2 238 ms** | 100.25 | FAIL | FAIL | **FAIL** |
| **−6 dB** | **3 of 400** | 6 121 ms | **26.50** | FAIL | FAIL | FAIL |

**PART 3 FAILS FIRST, AND MY REGISTERED PREDICTION P1 SAID THE OPPOSITE.** P1
argued that part 1 would bind because `expire()` caps p98 near the PDB while a
gap has no ceiling. Both halves of the mechanism are real — **p98 does pin at
exactly 100.25 ms** at every overloaded cell — and the conclusion drawn from
them was backwards: the cap is at 100.25 against a **95 ms** bound, so p98 fails
on a **5 %** excursion, while the gap bound tolerates **four consecutive losses**
at a 100 ms cadence. **The tighter criterion is the capped one.** Recorded as a
miss.

**And at −6 dB the worst p98 reads 26.50 ms — better than at 20 dB — for a pair
of robots that delivered three heartbeats between them.** Every surviving
message was one the network happened to carry quickly; the rest left the sample.
That is the same trap G1's control found, and it is why a flow with fewer than
two completions is scored as a failure here rather than excluded.

**One anomaly, reported rather than smoothed.** Reservation at **15 dB** fails
all three criteria with 200 of 400 messages and a silent instrument on both
seeds, while 20 dB and 10 dB both pass 2/2. A non-monotone cold-start lock-out
on the flooding robot at one SNR level. Two seeds cannot resolve it and it is
not chased.

## 11. Runtimes

| | pass 1 (pre-fix, kept as evidence) | **pass 2 (the published artefact)** |
|---|---|---|
| runs | 486 | **576** |
| wall, 14 workers | 939 s (15.7 min) | **1 202 s (20.0 min)** |
| CPU | 3.62 h | **4.64 h** |
| mean per run | 26.84 s | **29.03 s** |
| **both passes** | | **35.7 min wall, 8.26 h CPU** |

| arm | mean per run | relative |
|---|---|---|
| PF | 19.35 s | 1.00× |
| Reservation | 25.75 s | 1.33× |
| **TwoTier** | **41.98 s** | **2.17×** |

| sub-experiment | runs | CPU |
|---|---|---|
| GT-2.2 (fleet axis, controls, long horizon, SNR) | 396 | 9 248 s |
| GT-2.3 (both configurations, three buckets) | 180 | 7 471 s |

**Projected 23 min wall against 20.0 measured**, from a cost model calibrated on
nine timed runs before the grid was sized. **Peak memory 9.6 GB projected**
against 23.5 GB available.

## 5. GT-2.3 — and its own named mechanism costs at most nine milliseconds

**The scored quantity is the post-silence gap, not the raw one.** A 60 s
waypoint pause produces a 60 s receiver-side gap by construction; scoring that
against a 500 ms bound would fail the clause on the application's own
behaviour. So the clock starts at the **resume instant**, derived from the same
windows the scenario is built from, and the raw straddling gap is reported
beside it.

**The raw gap is the scripted pause plus one cadence, on every bucket** — 1 116
ms, 5 234 ms and 60 177 ms against silences of 1 s, 5 s and 60 s. The network's
contribution is the ~100 ms of ordinary cadence, and nothing else.

### 5.1 THE MECHANISM THE TEST IS WRITTEN FOR IS BARELY REACHED, and the reason is arithmetic

GT-2.3 exists for *"the SR-fragility and desync class"* — the first packet after
silence has to buy a grant, which costs a scheduling request on PUCCH, its
prohibit timer, a grant and a BSR. **Two things stop that costing anything
here, and both were measured rather than assumed.**

**First, a robot whose camera keeps running never pays it at all.** The UE is
still receiving uplink grants for another logical channel, so the resumed
heartbeat rides the next one and the UE's own LCP splits the transport block.
So the campaign runs a **second configuration** — `pause_whole_ue=True`, every
uplink flow on Asset A paused over the same windows, DL control still running —
which is the cell that genuinely has to re-acquire a grant. It is a strictly
harder cell, kept out of the graded tables and reported separately.

**Second, and this is the sharper half: every scripted resume lands exactly on
a scheduling-request opportunity.** The silences are whole seconds, a second is
4 000 slots at μ=2, and `sr_period_slots` is **10**. So `resume_slot % 10 == 0`
at every bucket — 24 000, 40 000 and 260 000 — and the resume never waits for
the next occasion:

| bucket | resume at | resume slot | slot mod SR period |
|---|---|---|---|
| 1 s | 6.0 s | 24 000 | **0** |
| 5 s | 10.0 s | 40 000 | **0** |
| 60 s | 65.0 s | 260 000 | **0** |

**A phase offset would move the resume by at most one SR period, 2.5 ms**, so
the alignment is worth stating but is not what bounds the answer. What bounds it
is the measurement: **the largest post-silence gap anywhere, across both
configurations and all 180 GT-2.3 runs, is 134.25 ms** — TwoTier, 5 s bucket,
whole robot paused — which is **3.7× inside the 500 ms bound**. PF and
Reservation resume in **0.25–13.0 ms**; TwoTier's 78–134 ms is two orders larger
and is **not** the SR wait, since the SR wait cannot exceed a few milliseconds.
It is TwoTier's own ranking taking that long to return a re-entering UE to the
front, which is a real arm difference and still an order of magnitude inside the
bound.

**`sr_period_slots` has no ground truth** — `sim/ul_access.py` says so in its
own docstring — so the 2.5 ms is a scenario choice. The test plan reaches the
same place from the other direction: GT-2.3 is the one sub-test it marks
**`Env: RF` essential**, with *"SR fragility does not manifest in rfsim"* written
next to it. **A simulator agreeing with that is weak evidence and is reported as
weak** — what this campaign establishes is that the SR path is not the mechanism
that breaks G3 *here*, not that it is safe on hardware.

### 5.2 What GT-2.3 does establish

**The buckets are indistinguishable, and that is the finding rather than a
null.** They were chosen to straddle two-tier's 2 s floor-arming horizon —
1 s inside it, 5 s and 60 s outside — precisely so a difference would localise
to the floor. There is none, and the reason is structural: **above the arming
horizon the floor is disarmed for every arm equally**, so the bucket removes a
two-tier-specific mechanism rather than stressing one. The prediction that the
60 s bucket is where the arms separate is **refuted**.

**Nothing failed to complete.** Every scheduled resume was observed, on every
arm, bucket and seed — `n_never_returned = 0` throughout, and the resume count
equals the schedule's own derived count. That is the assertion `docs/wp9-plan.md`
§34.5a asks for: firing and finishing are different questions, and both were
checked.

## 9. What this campaign added to the repo, and what it makes live

Per the standing rule, for each addition: who consumes it, what becomes live
that was inert, what it duplicates.

### `sim/scenarios/g3.py` (new)

- **Consumers:** `scripts/g3_stress.py`; `sim/tests/test_g3_scenario.py`
  (25 tests); `sim/tests/test_g3_floor_tally.py` (4);
  `sim/tests/test_flow_key_collision_sweep.py` (22 new cases, forced by its own
  coverage assertion); `sim/tests/test_workload.py`'s GBR-offered invariant,
  which reaches it through the same `_cases()`.
- **Becomes live that was inert:** **a 5QI-1 telemetry bearer with a GFBR**,
  which no workload in this repo had — and with it the UE-side LCP's
  *prioritised round* for telemetry (`sim/ue_lcp.py`), which every existing
  scenario left at a zero token bucket. Also `active_windows` on a **telemetry**
  flow with a neighbour flooding, which only `g11.py`'s soak used before, and
  the first uplink cell in the repo that pauses a robot's **whole** uplink.
- **Duplicates:** nothing. It reuses `sim/workload.py::scale_committed_load` and
  `min_bytes_per_period_for_gfbr`, takes its committed-profile shapes from
  `sim/parametric.py`'s factory mix via `g1.py`/`g2.py`, and uses
  `sim/scenarios/schedule_guard.py` rather than growing its own horizon check.
  Fifth guarantee-specific builder beside `g1`, `g2`, `g9`, `g11`, `g12`.
- **Deviation from §2.1's three-flow profile, stated:** no lidar. G1's and G2's
  cells omit it, and a third GBR bearer would make G3 incomparable with them
  **and** move the admissible fleet size the axis is ranged against.

### `scripts/g3_stress.py::FloorFireTally`

- **Consumers:** the runner; `sim/tests/test_g3_floor_tally.py`.
- **Becomes observable that was not:** **the UL service-interval floor's
  fires.** CLAUDE.md's unreachable-mechanism audit lists Tier 1.5 as
  unobservable — *"OAI's counters not ported; activation unknowable."* The
  counter was already there: `floor_fire` is tier 1.5 of two-tier's own UL
  ranking key, and `scheduler/rank_trace.py` records that key verbatim.
- **Duplicates:** nothing, and this was the **second** attempt — see §9.1.

### 9.1 The scheduler edit that was made and withdrawn, priced

Six counters were added to `scheduler/two_tier.py` first: pure telemetry, no
branch reading them, `regression_corpus.py --check` moving **zero numbers** (30
shape-only lines over 5 TwoTier records × 6 keys). They still cost:

| consequence | size |
|---|---|
| corpus re-baseline | shape-only, 30 lines |
| **`verify_claims --check` staleness** | **12 published claims across G1, G2 and G10** |

`scripts/code_state.py` stamps each artefact with the AST hash of its runner's
**transitive import closure**, and every campaign running a TwoTier arm reaches
`two_tier.py` through `g11_campaign._arm`. At that module's own measured figure
of *"roughly ten minutes of re-running each"*, six counters cost **three
campaign re-runs**. Reverted; the rank stream costs none of it, and adding
`sim/scenarios/g3.py` alone invalidates nothing because no earlier runner
imports it — confirmed, `20 as expected / 0 not`.

**What is lost by not landing them:** the arming decomposition
(`has_pending_gbr` passing, and `armed`), which is internal state no hook
reaches. It matters only if the fire count comes back zero. A pre-revert probe
read `ul_floor_pending_gbr` at **131 111 of 192 000** evaluations at N=6, so the
gate is reachable on this cell; the campaign reports fires, and §6 says what
they were.

### 9.2 A category guard was widened, not silenced

`sim/tests/test_schedule_guard.py`'s exemption list was module-keyed.
`sim/scenarios/g3.py` is the first module holding **both** a scheduled builder
(GT-2.3's silences, which calls `require_horizon`) and unscheduled ones
(GT-2.1/2.2, steady state), so a module-level exemption would have silently
covered the one builder that most needs the guard. Exemptions are now
per-builder, and the test asserts the scheduled sibling is **not** exempt.

### 9.3 And one finding that is not G3's, recorded where it was found

**`regime_sweep.run_cells` does not watch memory at all.** It carries four
measured lessons about the pool — bit-identity as the acceptance criterion,
`OMP_NUM_THREADS` set in the parent, a generator that retains nothing,
longest-first with `chunksize=1` — plus an orphan check before launch. It has no
aggregate memory ceiling, and **the one that exists lives inside
`g11_campaign.py`'s own runner**: the fix-at-the-site shape CLAUDE.md records as
this project's most expensive recurring habit. A per-process guard could not
have caught this campaign's near-OOM, because no single worker approached one.
Not built here — it is its own commit — and the runner now prints a peak-memory
projection so the check exists at the point of use.

## 10. The horizons, stated per pass

Slot 0.25 ms (μ=2) throughout; telemetry 10 Hz, so **messages per robot is
`active seconds × 10`**.

| pass | slots | seconds | messages / robot | runs |
|---|---|---|---|---|
| **GT-2.2 fleet axis** | **40 000** | **10.0** | **100** | 270 |
| GT-2.3, 1 s bucket | 44 000 | 11.0 | 100 (10 s active) | 30 |
| GT-2.3, 5 s bucket | 60 000 | 15.0 | 100 (10 s active) | 30 |
| GT-2.3, 60 s bucket | 280 000 | 70.0 | 100 (10 s active) | 30 |
| GT-2.3 SR probe, whole UE paused, same three buckets | 44/60/280 k | 11/15/70 | 100 | 90 |
| configuration controls | 40 000 | 10.0 | 100 | 60 |
| **long-horizon flatness** | **200 000** | **50.0** | **500** | 30 |
| SNR positive control | 40 000 | 10.0 | 100 | 36 |
| **all** | | **3.03 simulated hours** | | **576** |

**The GT-2.3 buckets carry an identical sample size.** One cycle gives two
active windows of 5 s, so every bucket has exactly 10 s of active telemetry and
the buckets differ *only* in the silence between them. That is a better
comparison than three cycles gave, and it is what the memory re-size bought.

### 10.1 What each horizon supports, and what it does not

**p98 over 100 messages IS a percentile; p99 would not be.** The index
convention is `min(n−1, int(n·p))`, so a percentile needs `n > 1/(1−p)` — 50 for
p98, 100 for p99, 1 000 for p99.9. **Only p98 is quoted from the grid**; the
50 s pass carries 500 messages and is where a tail could be read.

**The gap criterion is a MAXIMUM, so what matters is whether the window can
contain the gap it forbids — and that was checked rather than assumed.** A
10 s run holds five 2 s gaps arithmetically, and the SNR control **demonstrates**
one at this exact horizon: 6 121 ms at −6 dB, 2 209 ms at −3 dB. So the
criterion is not passing for want of a window to fail in.

**But the maximum IS horizon-sensitive, and this is the caveat that matters
most.** Over a 5× longer window at the same fleet size, TwoTier's worst gap
grows from 165.5 ms to **416.8 ms** — 2.5×, and from 3.0× inside the bound to
1.2× inside it. **So every part-1 boundary here is an upper bound on the
admissible fleet**, and the direction is known rather than guessed. PF and
Reservation are flat across the same span (204.8 → 204.8, 120.5 → 201.2), so the
sensitivity is TwoTier's, not the statistic's.

### 10.2 Against GT-2.2's own specification

The plan asks **10 min × 3 arms × 5 runs = 150 min** for GT-2.2, and 100
cycles per bucket for GT-2.3.

- **Aggregate: exceeded.** 3.03 simulated hours against 2.5.
- **Per-run duration: one sixtieth of it** — 10 s against 600 s, with the
  longest run at 70 s. **This is the shape that caught G11**, so it is stated
  rather than left to be found, and §10.1's 5× flatness check is the evidence
  offered against it. That check is not clean on TwoTier, which is why the
  boundaries are called upper bounds.
- **GT-2.3 cycles: 10 per (arm, bucket), 30 pooled over arms, against 100.** A
  run cannot hold 100 sixty-second pauses. Derived and reported; closing it is a
  run, not an argument.

## 12. Open external inputs

- **`T_live` = 2 s is a PROPOSED default and the plan's own first open
  question** — *"the MEC's actual liveness timeout and the safe-margin policy;
  ask the MEC team; it calibrates GT-2 pass lines."* Both scored bounds derive
  from it: 500 ms is `T_live/4` and the campaign-wide criterion is `T_live`
  itself. **Halving T_live to 1 s would move part 1's bound to 250 ms**, which
  several passing cells sit above.
- **The 95 ms RAN share is likewise proposed** (§5's *"RAN budget = PDB − 5 ms"*
  against 5QI 1's standardised 100 ms).
- **The telemetry bearer's `prioritisedBitRate` is the campaign's biggest lever
  and its value is a deployment choice this repo cannot read.** §3.1 establishes
  the GFBR → PBR derivation from the deployed source, and that a non-GBR DRB
  passes zero; what it cannot read is the enum a zero maps to, because
  `get_DRB_RLC_BearerConfig` is not vendored and the full checkout is absent
  from this machine. **This is the one open input a client answer would change a
  verdict on.**
- **`bsd_ms` has no provenance at all.** 100 ms is this repo's default; the only
  bucket duration anywhere in the deployed source is the SRB path's 5 ms.
  Controlled here, and the control does not withdraw the finding.
- **`sr_period_slots` has no ground truth** (`sim/ul_access.py` says so), which
  is why §5.1's conclusion is stated as a bound over any value this repo could
  justify rather than as a measurement at one.
- **GT-2.3 is `Env: RF` essential in the plan's own table**, with *"SR fragility
  does not manifest in rfsim"* beside it. This campaign's agreement is weak
  evidence and is reported as weak.

## 13. THE PREDICTIONS, SCORED — three refuted, two half right

Registered in `docs/g3-registration-2026-09-09.md` §6 before the campaign ran.
**Misses recorded, not just hits**, per the standing rule that a prediction
exercise cited only when it is right is not one. **Five of ten are wrong or
partly wrong, and two of the wrong ones were wrong in the mechanism rather than
the direction**, which is the more useful kind to have written down.

| # | prediction | verdict | what actually happened |
|---|---|---|---|
| **put to me** | *"the QoS arms do not both hold"* | **HELD** | neither holds; PF passes every criterion at every fleet size |
| **put to me** | *"GT-2.3's 60 s bucket is where it shows"* | **REFUTED** | the buckets are indistinguishable — 10/10/10 on every arm at every bucket |
| **P1** | part 1 (gap) binds, part 3 (p98) is loose because `expire()` caps it | **REFUTED, backwards** | the cap is real and p98 pins at exactly **100.25 ms**, but against a **95 ms** bound that makes it fail on a 5 % excursion, while the gap bound tolerates four consecutive losses. **The capped statistic is the tighter one** |
| **P2** | arms separate on the fleet axis, order PF > TwoTier ≥ Reservation | **HELD** | 24+ / 7 / 6 |
| **P3** | G3's boundary sits BELOW G10's | **REFUTED** | **identical** on both QoS arms (6 and 7) and far above on PF |
| **P4** | part 2 passes at N ≤ 8 everywhere; fails at N ≥ 16 on a QoS arm | **HALF** | second half holds (Reservation 2/10, TwoTier 2/10 at N=16). First half fails: **Reservation already loses a seed at N=7 and six at N=8** |
| **P5** | GT-2.3's buckets are indistinguishable | **HELD** | and for the registered reason: above the arming horizon the floor is disarmed for every arm equally |
| **P6** | the PBR control moves EVERY arm, by more than the arm difference | **HALF** | it moves **only TwoTier** on this cell (10/10/10 → 10/10/7). The Step-0 probe moved all three on the parametric mix — a workload difference, and quoting the probe on this cell would have been the configuration-carrying error |
| **P7** | `bsd_ms = 5 ms` does not withdraw the PBR finding | **HELD** | no degradation on any arm; TwoTier slightly better |
| **P8** | the floor fires, only on TwoTier, rising with N | **HELD, with a caveat** | 1 → 744 fires, `None` on the other two arms. **Not monotone**: 527 at N=10 falls to 334 at N=12 before rising again |
| **P9** | the SNR control breaks part 1 before part 3 | **REFUTED** | part 3 fails first, at 5 dB, with parts 1 and 2 still passing — same inversion as P1 |
| **§6.3** | the cold-start lock-out's contribution is unanswerable here | **HELD as registered** | one candidate appeared (Reservation, 15 dB, silent on both seeds while 20 and 10 dB pass) and two seeds cannot resolve it |

**The two refutations that share a mechanism are the ones worth carrying.** P1
and P9 are the same error: I reasoned that a statistic with a hard ceiling must
be the loose one, and did not check the ceiling against the bound. **100.25
against 95 is a 5 % margin; 500 against a 100 ms cadence is four whole missed
messages.** A ceiling makes a statistic *insensitive at the top*, not *lenient*.

**And P3's refutation is the most substantive result in the campaign** — the
prediction was directional and reasonable, and the answer is sharper than either
alternative: the two boundaries are not merely close, they are the same numbers,
which points at one mechanism rather than two.

## 14. Deployment consequence, in an operator's terms

**On the two QoS schedulers, the fleet size at which a robot starts looking dead
is the fleet size at which the GBR contract breaks — six robots on Reservation,
seven on TwoTier. On proportional fair it is at least twenty-four.**

- **A false failsafe is what this costs.** At the failing points a robot is
  silent for **three to nine and a half seconds** while healthy. A MEC with a
  two-second liveness timeout halts it. **36 such silences occurred in the
  campaign**, all of them on a QoS arm.
- **Watch missing heartbeats, not slow ones.** At the failing fleet sizes,
  **up to 1 140 of 2 000** telemetry messages never arrive, and the latency
  statistic pins at 100.25 ms whatever the severity — a dashboard reading p98
  cannot tell a marginal cell from a broken one. **Count deliveries.**
- **And a dashboard reading the clause as literally written would show nothing
  at all** on some of the worst cells: Reservation at ten robots reads a
  comfortable 125 ms while a robot sat silent for 6.8 seconds.
- **Sizing the fleet on G10 is sufficient here, which is the one piece of good
  news.** The liveness boundary does not sit below the contract boundary on any
  arm, so a fleet sized on G10's admissible count does not additionally break
  liveness. It has no margin on the QoS arms either.
- **The single cheapest intervention is not a scheduler change.** Configuring
  the telemetry bearer's prioritised bit rate — one RRC parameter, derived from
  its GFBR — is worth more than the choice of scheduler at six robots, and
  costs nothing in this cell's measurement.

**Not established: the mechanism behind the multi-second silences.** They begin
mid-run (first delivery at 1–4 ms on almost every failing flow), so they are not
the cold-start lock-out; distinguishing a BSR desync from ordinary rank
starvation needs a per-slot trace this campaign does not carry. **What is
established is that the floor built to rescue exactly this state is firing —
744 times per ten runs at N=24 — and the silences happen anyway.**

## 15. Provenance notes on the artefact itself

**Two things about `sweeps/g3-stress/g3_stress.json` a later reader needs.**

**`_wall_s_this_invocation` reads 0.0 and is NOT a measurement.** The artefact
was regenerated from its own `RunLedger` after the campaign finished — 576
banked, **0 to run** — because one doc-level key had to be renamed (below). The
runner's own docstring warns about exactly this reading, which is why the
campaign's own cost travels separately as `_cpu_wall_s_total` (a sum of per-run
times, which survives a resume) and why **the 1 202 s wall figure quoted in §11
comes from `sweeps/g3-stress/g3.log`**, not from the artefact.

**That regeneration is also the kill-and-resume identity property being
exercised for real**, not as a test: every row re-entered from the ledger and
the artefact rebuilt with no simulation, which is the acceptance condition
CLAUDE.md sets for the banking machinery.

**`_cpu_s_total` was renamed `_cpu_wall_s_total`, and the reason is a guard
working.** `scripts/verify_parallel.py`'s serial-vs-parallel identity check
requires any field excluded as *timing* to LOOK like a clock — name ending in
`_s`, or containing wall/time/elapsed — so that a **result** cannot be slipped
into the exclusion list to make a diff disappear. `_cpu_s_total` satisfied
neither, and the guard refused it. Renaming the field was the correct fix;
widening the rule would have been the defect it exists to prevent.

**G3's runner is registered in that identity check** (`scripts/verify_parallel.py`,
case `g3_stress`) — one arm, one seed, the full nine-point fleet axis, nine runs
each side. **G1's and G2's runners are not**, which is a standing gap in those
two campaigns rather than something this one inherits. The axis is deliberately
NOT narrowed by a new flag: a `--ue-axis` argument would enter
`invocation_config` and therefore the ledger key, orphaning the published
campaign's banked rows.

## 16. Process notes worth carrying

- **The instrument built to replace a defective statistic had the same defect,
  one step along.** G2's percentile could not see a dropped STOP; G3's
  inter-arrival maximum could not see a robot that never comes back. **Both were
  caught by decomposing the campaign's own output, not by a test** — and this
  one was caught in the campaign's own first artefact, before publication, which
  is the cheapest place it has ever been caught.
- **A ceiling makes a statistic insensitive at the top, not lenient.** Two
  registered predictions (P1, P9) got this backwards in the same way. p98 is
  capped near 100.25 ms by the bearer's own discard, and I inferred it must be
  the loose criterion — but 100.25 against a **95 ms** bound is a 5 % margin,
  while 500 ms against a 100 ms cadence tolerates four whole missed messages.
  **Compare the ceiling to the bound, not to infinity.**
- **Memory bound this grid and time did not**, and no per-process guard could
  have seen it: 14 workers reached **17.0 GB with 1.5 GB of machine memory
  left**, projecting ~56 GB against 31 GB of RAM. The shared pool helper watches
  memory not at all; the one aggregate guard that exists lives inside a single
  campaign's runner. **The runner now projects peak memory beside CPU**, which is
  the check that would have caught it before launch.
- **Killing the parent orphaned all fourteen workers**, still allocating. Their
  argv is the spawn bootstrap, so they cannot be found by script name and had to
  go by PID — exactly as the project notes describe, reproduced rather than read.
- **Extrapolating a longest-first pool's wall clock from RUN COUNT is wrong by
  3×.** At 60 % of projected CPU consumed the run count read 12 %, because the
  expensive runs are submitted first *by design*. CPU consumed is the basis;
  run count is not.
- **Six counters added to a scheduler file and reverted, and the price was
  bookkeeping rather than behaviour.** Pure telemetry, zero numbers moved in the
  corpus — and **12 published claims across G1, G2 and G10 went stale**, because
  the artefact stamp is the runner's transitive import closure. **The same fires
  were already readable from the existing rank stream**, which is where a
  mechanism's observability should be looked for first.
- **Two category guards fired on the new builder and both were widened rather
  than silenced** — the flow-key collision sweep's coverage assertion forced 22
  new cases, and the schedule guard's module-level exemption became per-builder
  because `g3.py` is the first module holding both a scheduled and an
  unscheduled builder.
- **A negative claim about the deployed C named the files searched**, and the
  search found more than expected: not only that a DRB's PBR is derived from its
  GFBR, but a **hardware observation of the same starvation from the other end of
  the knob**, sitting in a comment two lines from the derivation.

### 16.1 And the serial-vs-parallel check caught a real defect on its first run

**It was worth registering, and it found something immediately.** The first run
of `scripts/verify_parallel.py g3_stress` reported the two artefacts differing
at `.rows[0].dl_mbps` — **0.077 against 0.23**.

**The cause: rows were appended in COMPLETION order.** `regime_sweep.run_cells`
is a generator yielding whichever run finishes first, and it carries each task's
original index through *precisely* so a caller can place results itself. This
runner ignored the index and appended as results arrived, so the artefact's row
order moved with `--workers` — and, on a resume, with the ledger's file order on
top of that.

**No verdict was affected**, because every aggregate in the runner selects by
field rather than by position. **But byte-identity is this project's acceptance
criterion for a pool, not a nicety** — CLAUDE.md's own words are *"it is a
CORRECTNESS change, not a speedup"* — and an artefact whose row order depends on
the worker count fails it. Fixed by sorting on the task key before projection,
which is total, deterministic, and survives a resume as well as a re-run.

**The same defect is present in `scripts/g1_stress.py` and
`scripts/g2_stress.py`**, which append in completion order too and are **not
registered in the identity check**. Stated rather than fixed here: it is their
commit, and the reason it went unnoticed is exactly the reason CLAUDE.md gives
for the check existing per runner rather than once.

**Two guards also refused their first configuration, and both refusals were
right.** The check rejected `_cpu_s_total` as a *timing* exclusion because the
name does not look like a clock — the rule that stops a result being slipped into
the list — and it rejected `out`/`workers` as *provenance* exclusions this runner
never stamps, which is its rule that an exclusion doing no work is reported. One
field was renamed and one list emptied; neither rule was widened.

## 17. One latent defect found in the end-of-work review, FLAGGED not fixed

**`sim/scenarios/g3.py::flood_ue_id` tests `rate_bps >= FLOOD_UL_BPS`.** The
flood and the per-UE best-effort filler share 5QI 9 — the plan names the flood's
class by number, so the filler is the one displaced — which makes rate the only
discriminator. Correct at and above the default; **for any caller passing a
SMALLER `flood_bps` it returns `None`, and that propagates into
`instrument_ue_ids`, silently dropping Asset B from the scored population.**

**No published figure is affected.** The campaign runs only the default rate.

**The fix is one comparison** (`> BG_UL_BPS`, i.e. "bigger than a filler"). It
was written, tested, and then **reverted out of this commit**, and the reason is
worth stating because it is a real constraint on how this repo works:
`sim/scenarios/g3.py` is inside the artefact's own `code_state` scope, so editing
it re-stales **every G3 claim** and demands a 20-minute re-run to restore exact
provenance — for a change that cannot alter a single row. **One fidelity change
per commit applies to a latent-defect fix as much as to a mechanism.**

**Both halves are pinned by a test** (`test_flood_ue_id_is_correct_at_the_
campaign_rate_and_FLAGGED_below_it`), including the flagged behaviour, with an
assertion message saying that fixing the comparison means inverting the
assertion and re-stamping the artefact in the same commit. That is the
difference between a flagged defect and a forgotten one.

### 17.1 Standing checks, at the close

| check | result |
|---|---|
| `uv run pytest sim/tests -q` | **1 431 passed** |
| `regression_corpus.py --check` | **OK — no drift.** No re-baseline: nothing in `sim/` or `scheduler/` changed behaviour |
| `verify_claims.py --check` | **30 as expected, 0 not** (10 of them G3's, all newly added) |
| `parallel_audit.py --check` | **exit 0**; `g3_stress.py` registered PARALLEL via `regime_sweep.run_cells` |
| `verify_parallel.py g3_stress` | **PASS** — identical after excluding four timing fields, every one present and differing |

**The corpus needed no re-baseline at all**, which is the cleanest possible
statement about scope: this campaign added a scenario, a runner, three test
files and documentation, and changed the behaviour of nothing.

### 3.5 Two observation errors made while measuring §3.4, recorded

**Both are on CLAUDE.md's own list, and I made them in the same ten minutes.**

**A `pgrep` pattern that did not match reported a live probe as finished.**
`pgrep -f "fix2_reserve"` from a shell whose own command line differed returned
nothing while the process was at 103 % CPU. I wrote "probe finished" on that
evidence. The fix is the one already written down: **wait on a PID
(`kill -0 $PID`), not on a pattern.**

**And an empty output file was read as a dead process.** The probe redirected
stdout to a file; Python block-buffers a redirected stdout, so the file stayed
at zero bytes for minutes while the run was healthy. **An empty file is
evidence about the FILE, not about the process** — the exact sentence in the
invariants, applied after the fact rather than before.

**The consequence was a duplicated run**, then a `kill` aimed at the wrong one
of two identical processes. No result was affected — the surviving run produced
§3.4's table — but the two readings together cost about ten minutes and are
worth recording as a third and fourth instance rather than being quietly
tidied away.

**The probe is preserved** as `scripts/g3_reserve_probe.py` and registered in
`scripts/parallel_audit.py`'s `ALLOW_SERIAL` with its reason, so §3.4 can be
re-derived rather than re-discovered.

## 18. THE PROTO ARM'S TWO EDITS, and what has to be recorded before sweeping further

**2026-09-10**, after `docs/proto-e1-result-2026-09-10.md` and
`docs/proto-e2-result-2026-09-10.md`. Two records that have to stand before any
further gate is built, because both correct something a later reader would
otherwise take from the edits' own names and headline numbers.

### 18.1 E2 IS MISLABELLED — the finding is about REMOVAL, not targeting

The flag is called `stale_bsr_reserve` and was registered as *"keep the reserve
only for followers whose buffer report is stale"*. **It does not do that.** Its
own classification counters, which exist precisely so an edit cannot be
believed on its name:

| N | followers classified | current → suppressed | stale → kept |
|---|---|---|---|
| 6 | 97 677 | 97 677 — **100.0 %** | 0 |
| 8 | 166 972 | 166 972 — **100.0 %** | 0 |
| 12 | 311 156 | 311 110 — **100.0 %** | 46 |
| 24 | 631 904 | 630 689 — **99.8 %** | 1 215 |

**The staleness test holds on 0.0–0.2 % of classifications.** A qualifying
follower has `gbr_bytes_slot > 0`, which requires a backlogged GBR LCG with an
unmet obligation — such a UE is a candidate nearly every slot and is therefore
granted well inside its own PDB, so "current" is almost always true.

**So E2 measured "remove the reserve, always."** The name is doing no work, and
its improvement is evidence for *removal*, not for *report-targeting*. Every
number in E2's result table should be read under that heading. The flag name is
left as it is only because renaming it would move
`scheduler/two_tier_proto.py`'s AST hash and stale the artefact the counters
above come from; **the label is corrected here rather than in the identifier**,
and no future edit should cite E2 as evidence that targeting works.

**This is the manipulation check earning its place a second time.** The first
was the unreachability catch — `e2_never_granted_kept == e2_stale_kept ==
757 143 of 757 143`, an impossible equality. The second is this one: the same
counters that proved the edit ran also proved it was not doing what it was
named for. A headline improvement with no decomposition underneath it would
have shipped both errors.

### 18.2 THE RESERVE'S PROTECTIVE ROLE IS REAL, so "improves G3" is not sufficient

Both edits bought the middle of the axis by giving up the top:

| | N = 12 part 1 | N = 16 part 1 | N = 24 part 1 |
|---|---|---|---|
| faithful | 3 | **9** | **9** |
| E1 (removes above 11 followers) | 8 | **4** | **3** |
| E2 (removes essentially always) | 9 | **2** | **2** |

**Part 1 falls 9 → 2 at both N = 16 and N = 24 under E2, and 9 → 4 and 9 → 3
under E1.** The mechanism is the one the reserve exists for: with no reserve,
greedy-by-rank lets the leader take the band it asks for, so fewer robots are
served per slot and more end up moderately starved — **the monopolisation FIX-2
was written to prevent, reproduced by removing it.**

**Taken with E1 the pair localises the reserve's cost precisely.** E1 removes it
only above eleven qualifying followers and moves no boundary; E2 removes it
essentially always and moves part 1 from 7 to 8 and part 2 from 7 to 16. **So
the reserve is harmful just BELOW the boundary — at 8 to 14 robots, where it
fits and is therefore applied in full — and protective above it.**

**The success criterion for any further gate is therefore two-sided, and is
registered here so a one-sided win cannot be reported as a win:**

1. **improve the 8–14 band** — part-1 and part-2 pass counts up, worst silence
   down, relative to the faithful arm on the same seeds; **and**
2. **do not lose the top** — part 1 at N = 16 and N = 24 must not fall below
   the faithful arm's 9 and 9.

**Neither E1 nor E2 meets it.** A candidate that satisfies (1) and fails (2) is
the same trade already measured twice, not a new result.

## 19. THE BOUNDARY IS A SINGLE-SEED STATISTIC — report it beside the aggregate, never alone

**2026-09-10, and it caught me after five variants had been ranked on it.**

The standing boundary rule is *"the last passing fleet size before the first
failure"*. That makes it a **maximum over rare events**, and its variance
depends on how often the arm fails at all:

- **the faithful arm fails often**, so its first failure is not a rare event and
  its boundary is stable — **7 on both seed sets**, part 1;
- **a good arm passes nearly everywhere**, so its boundary is decided by
  whichever single seed happens to fail earliest — and G-kpi's part-1 boundary
  read **14 on the seeds it was selected on and 8 on ten held-out seeds**, on
  one seed failing at N = 10 instead of N = 16.

**The underlying effect is stable to within four cells in a hundred.** Paired,
same builder, same scoring code, `--seed-base 1` giving a provably disjoint
sample:

| statistic, 100 paired cells | selection seeds | held-out seeds |
|---|---|---|
| part-1 passes, faithful → G-kpi | 85 → **98** | 85 → **94** |
| part-1s passes, faithful → G-kpi | 73 → **98** | 72 → **94** |
| part-2 passes | 77 → **100** | 78 → **100** |
| part-3 passes | 63 → **77** | 59 → **78** |
| campaign silences ≥ 2 s | 26 → **0** | 23 → **0** |
| telemetry short | 2 356 → 860 | 2 309 → 914 |
| **part-1 BOUNDARY** | 7 → **14** | 7 → **8** |

**Every aggregate reproduces. Only the boundary moves, and it moves by six.**

**So the boundary is fine as a DEPLOYMENT figure and wrong as a RANKING
statistic.** An operator sizing a fleet wants the last size that passed; a
comparison between two candidates that both pass nearly everywhere cannot use
it, because the difference between them is one seed's worth of noise. **The
ranking I reported between G-per-deadline (12), G-denial (12) and G-kpi (14) is
inside that noise and is withdrawn**; what survives is that all three are large
improvements on the faithful arm and that G-slack is genuinely worse.

**This is the same class as the two errors this campaign already recorded** — a
threshold placed on a quantised value's own level, and a percentile quoted below
`1/(1-p)` samples. In all three the arithmetic was right and the statistic could
not carry the weight put on it. **Mechanically: never quote a boundary without
the pass count over the same cells beside it, and never rank two candidates on a
boundary alone.**

**`scripts/g3_stress.py --seed-base` exists for this.** Default 0 reproduces
every published G3 figure exactly; any other value draws a disjoint sample from
`regime_sweep.paired_seeds`, confirmed non-overlapping. **A candidate selected
over several variants on one seed set is not believed until it is re-scored on a
fresh one** — and that check cost 10 minutes against five variants' worth of
ranking it corrected.


## 20. THE PROTO SWEEP'S WRITE-UP IS DEFERRED, deliberately

**Decided 2026-09-10.** The `TwoTierProto` sweep produced a candidate that
clears every guarantee tested (G-kpi: G3 silences 26 -> 0 across two disjoint
seed sets, G10's admissible fleet 7 -> 12, G7's uplink utilisation 0.456 ->
0.931, G1/G2/G5/G9 unregressed). **None of it is folded into the roll-ups, and
that is a decision rather than an omission.**

**Not done, on purpose:**

- no proto figure is registered in `config/published_claims.yml`, so **none of
  the numbers above is quotable** under this repo's own convention;
- no proto row in `docs/GUARANTEE-RESULTS.md` or the guarantee table;
- G7's uplink-utilisation result is not written up as a product finding.

**Why.** The sweep is a side-thread of G3, and the guarantee table is what the
evaluation is for. Putting *"what a change would do"* beside *"what the product
does"* in that table before the guarantee set is complete is exactly the
confusion `scheduler/two_tier_proto.py`'s docstring exists to prevent.

**What IS landed and stays landed:** the arm itself, each edit's own
registration and result document, and every sweep artefact — so the work is
reproducible and auditable now, and only its promotion into the published
figures waits.

**The gate:** all guarantees rebuilt. As of this date **G1, G2, G3, G9 and G12**
have their own stress experiments; **G4, G6 and G8 have not been started**, and
**G5, G7 and G10 exist only as runners used for regression checks**.

**One finding worth carrying forward when the gate opens, because it is about
the DEPLOYED scheduler and not about the divergence:** on the faithful arm G7
runs the uplink band at **45.6 % utilisation while a protected asset is being
starved**. FIX-2's reserve was holding capacity nobody spent. That is a
statement about the port, needs no proto arm to make, and nothing currently
records it.
