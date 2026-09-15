# Standards survey — what else, besides configured grants, a dynamic-only design hides

**Date:** 2026-09-14. **Status:** survey, nothing built. Every item below is a
**candidate divergence arm** under the `two_tier_proto.py` docstring rule: it
says what a mechanism would do, never what the deployed product does. The
deployed C has none of them (CLAUDE.md: SPS/CG were deferred to a Phase 2
that was never built; `grep` results per item in §4).

**Question asked:** configured grants were invisible from the default
dynamic-grant path and turned out to fix every uplink liveness failure
(`docs/results-cg-2026-09-14.md`). What else in the standard is like that?

**Sources read:** the six Rel-18 specs in `docs/` (TS 38.300 V18.10.0,
38.321 V18.10.0, 38.331 V18.10.0, 38.214 V18.10.0, 38.213 V18.8.0, 38.212),
text extracted with `pypdf`, clauses cited by number. Web sources are listed
in §6 and were used only for Rel-18 XR framing and TSCAI; every mechanism
claim is anchored in the spec text.

---

## 0. The one-table version

Failure modes this evaluation measured, and which standard mechanism speaks
to each. "Sim" = modelled in this repo today; "OAI" = present in the
vendored `oai-branches/` subset (files searched named in §4).

| # | mechanism | rel. | spec | removes / adds | guarantee it reaches | sim | OAI | verdict |
|---|---|---|---|---|---|---|---|---|
| A1 | **TSCAI** from the core (period, burst arrival time, survival time per QoS flow) | 16 | 38.300 §16.8.1; TS 23.501 | replaces *detecting* a periodic LCH from BSR intervals with being *told* | CG allocator (§1.3 of the plan) | no | no | **adopt in the CG design** |
| A2 | UE-reported UL traffic info (`ul-TrafficInfo` in UEAssistanceInformation: `burstArrivalTime`, `trafficPeriodicity`, `jitterRange`) | 18 | 38.331 §5.7.4, field descriptions | same as A1 for flows the core cannot describe | CG allocator | no | no | note |
| A3 | RAN feedback to shift burst arrival time / periodicity | 18 | 38.300 §16.8.3 | aligns the application timer to the CG occasion / U-slot phase | CG waste, telemetry p98 | no | no | note |
| B1 | **Multi-slot CG per period + UTO-UCI** (`nrofSlotsInCG-Period` 2..32, `nrofBitsInUTO-UCI` 3..8) | 18 | 38.300 §16.15.4.1; 38.321 §5.8.2; 38.213 §9.3.1; 38.214 §6.1.2.3 | CG for *variable-size* periodic traffic: UE flags unused occasions, gNB reuses them | **G5, G7 (video)** — the guarantees CG did not reach | no | no | **measure** |
| B2 | **DL SPS** (`SPS-Config`: `periodicity` ms10..640, `periodicityExt-r16` 1..5120 slots, up to 8 per BWP) | 15/16 | 38.300 §10.2; 38.321 §5.8.1; 38.331 | DL analogue of CG: no DCI for the initial TB | **G1** (cmd_vel, 50 ms = 200 slots exact); **G2** as a standing STOP lane (§2.B2) | no | no (deleted at Phase 2) | **measure** |
| B3 | **Per-LCH SR configurations** (`schedulingRequestID` per LCH, ≤ 8 per cell group, periodicity `sym2`..`sl640`, `sr-ProhibitTimer` per config) | 15 | 38.300 §16.1.1/§16.1.2; 38.321 §5.4.4; 38.331 `LogicalChannelConfig`, `SchedulingRequestResourceConfig` | gNB learns *which class* asked and sizes the first grant per class; more SR occasions for the critical LCH | crumb grants, cold-start latency, G3/G4 | **no — one SR config, fixed floor** | not established | **measure first (cheap, Rel-15, COTS-safe)** |
| B4 | `logicalChannelSR-Mask` / `logicalChannelSR-DelayTimer` | 15 | 38.321 §5.4.5; 38.331 `BSR-Config` | the exact IEs behind "a CG-mapped LCH raises no SR" | CG | modelled implicitly | — | name the IE in `sim/configured_grant.py` |
| B5 | Multi-PUSCH by a single DCI (2–8 PUSCHs, `pusch-TimeDomainAllocationListForMultiPUSCH`) | 16 | 38.214 §6.1.2.1; 38.331 | one DCI per robot per TDD period covers all three U slots — attacks the DCI cap directly | cap M-6, visit cadence | no | no | measure **only if** the target UE declares `multiPUSCH-UL-grant-r16` (NR-U feature group) |
| B6 | Repetition (`repK` on CG 1..8/..32; `pusch-AggregationFactor` / `numberOfRepetitions` on DG; `pdsch-AggregationFactor` on DL/SPS) | 15/16 | 38.300 §10.3; 38.214 §6.1.2.1/§6.1.2.3; 38.331 | K TBs per DCI, no HARQ RTT for the first K−1 | STOP / cmd under blockage (`bytes_harq_lost`), not the cap | no | UE side only | note |
| C1 | **Delay Status Report** (DSR MAC CE: remaining PDCP-discard time + delay-critical bytes per LCG; `remainingTimeThreshold` 1..64 ms) | 18 | 38.321 §5.4.9, §6.1.3.72; 38.331 | the UE **tells the gNB the UL deadline** — what AGE/C3 approximated with an LCG clock | config-scheduler Tier-2 (EDF on UL) | no | no | **design input for the config scheduler** |
| C2 | Refined BSR table (`additionalBS-TableAllowed`, Table 6.1.3.1-3, 4 751 B … ~400 kB in ~2 % steps) | 18 | 38.321 §5.4.5, §6.1.3.1 | less quantisation for camera-size backlogs | BSR error — but the measured error was estimate *desync*, not quantisation | no (Rel-15 tables transcribed) | no | low |
| C3 | **PDU Set QoS** (PSDB supersedes PDB, PSER, PSI; `pdu-SetDiscard-r18`, `discardTimerForLowImportance-r18`) | 18 | 38.300 §16.15.2, §16.15.4.2.2; 38.331 `PDCP-Config` | the *frame* is the deadline unit; drop the rest of a frame once a fragment is lost | **G5** (frame-age p95 is a PSDB statistic) | scoring only (`FrameLedger`) | no | **adopt in Tier-2 design** |
| D1 | `lch-BasedPrioritization` + `autonomousTx` + `phy-PriorityIndex` on CG | 16 | 38.300 §10.3; 38.321 §5.4.1; 38.331 | CG-vs-DG overlap in one UE decided by LCH priority; deprioritised PDU kept for the next occasion | the 3–6 % `skipped_harq_pending` CG occasions | no (DG wins) | no | note; model if the skip fraction matters |
| D2 | UL cancellation (DCI 2_4 / CI-RNTI), DL pre-emption (DCI 2_1 / INT-RNTI) | 15/16 | 38.300 §10.2/§10.3; 38.213 §11.2, §11.2A | inter-UE, sub-slot displacement | none here: PRBs are not the binding resource | no | INT-RNTI parsed only | skip |
| D3 | Packet duplication, survival-time state (`survivalTimeStateSupport-r17`) | 15/17 | 38.300 §16.1.3, §16.8.1; 38.321 §5.4.1 | reliability through a second RLC path | needs CA or DC — single cell here | no | no | not applicable |
| E1 | **Notification control + Alternative QoS profiles** | 15/16 | 38.300 §12.1; TS 23.501 | gNB tells SMF "GFBR not met; profile #k feasible"; app adapts | the admissible-fleet boundaries of G5/G7/G10 become a runtime signal | no admission at all | no | **model as a counter first** |
| E2 | Recommended bit rate MAC CE (ANBR, per LCH per direction, `bitRateQueryProhibitTimer`) | 15 | 38.300 §16.2.1.1; 38.321 §5.18.10, §6.1.3.20 | gNB → UE application rate hint within GBR..MBR | G7 MFBR cap, G5 edge frame age | `adaptive` source has no gNB hint path | no | note; needs the camera stack to honour it |
| E3 | Slice RRM policies (dedicated / prioritised / shared PRB ratios) | 16 | 38.300 §16.3.3.2; TS 28.541 | O&M-configured PRB partition per slice — the Reservation idea, productised | control slice vs video slice | `slice_id` never set | RRC only | measure as an arm if Reservation R1–R4 is ever built |
| F | DRX (incl. non-integer cycles), SDT, 2-step RA, EHC, PDCCH skipping, TBoMS, NTN HARQ disable, PUCCH cell switching, `cg-RetransmissionTimer`, `cg-nrofSlots-r16` | — | see §3 | power, attach, coverage, unlicensed | — | — | — | out of scope (reasons in §3) |

The bold rows are the ones that change what is built next; §5 says how.

---

## 1. Why these were invisible

Every one of the bold rows is a **UE → gNB or core → gNB information path,
or a grant that needs no DCI**. A dynamic-grant scheduler is designed
around the assumption that the gNB learns everything from BSR/SR and acts
only through DCI. The standard has spent Rel-16 through Rel-18 adding side
channels precisely because that assumption fails for periodic, deadline-
bound, variable-size traffic — the factory workload. The failure modes this
evaluation measured (cold-start lock-out, crumb resets of the deadline
clock, BSR desync, the 300 ms visit tail, the DCI cap) are each an instance
of the gNB not knowing something the UE or the core already knows.

---

## 2. The mechanisms, one paragraph each

### A. Traffic knowledge instead of traffic detection

**A1. TSCAI.** TS 38.300 §16.8.1: *"The gNB may also receive TSC Assistance
Information (TSCAI) from the Core Network, e.g. during QoS flow
establishment … TSCAI contains additional information about the traffic
flow such as burst arrival time, burst periodicity, and survival time.
TSCAI knowledge may be leveraged in the gNB's scheduler to more efficiently
schedule periodic, deterministic traffic flows either via Configured Grants,
Semi-Persistent Scheduling or with dynamic grants."* The CG allocator in
`sim/configured_grant.py` **infers** period and size from the first BSR and
the regular-BSR cadence (plan §1.3). With TSCAI the period, the phase and
the survival time arrive with the QoS flow. Two consequences: the detector
becomes a fallback, and the CG **offset** can be set from the burst arrival
time instead of from the first report, which is what decides the constant
part of the telemetry p98 (~20 ms measured with CG on).

**A2. UE-reported UL traffic info (Rel-18).** For flows the core cannot
describe (a robot's own telemetry timer), TS 38.331 lets the gNB configure
`ul-TrafficInfoReportingConfig`; the UE then reports per QoS flow
`burstArrivalTime` (as a reference SFN/slot or as absolute time),
`trafficPeriodicity`, `jitterRange`, and whether it can identify PDU sets
and their importance. Same use as A1.

**A3. Burst-arrival feedback (Rel-18).** TS 38.300 §16.8.3: the RAN may
give *proactive or reactive feedback* so the application aligns its burst
arrival with *"the next expected transmission opportunity over the air
interface"*. In `DSUUU` a telemetry sample generated just after the last U
slot waits for the next period; aligning the robot's timer to the CG
occasion removes that wait and the CG's own wait. This is a core-network
procedure, so for this repo it is a scenario knob (phase offset), not a
mechanism to build.

### B. Grants that need no DCI, and cheaper DCIs

**B1. Multi-slot CG per period with unused-occasion signalling (Rel-18
XR).** 38.300 §16.15.4.1 introduces *"support of multiple CG PUSCH
transmission occasions within a single period of a CG configuration"* and
*"indication of unused CG PUSCH occasion(s) … with Uplink Control
Information multiplexed in CG PUSCH transmission"*. 38.331:
`nrofSlotsInCG-Period-r18 INTEGER (2..32)` (explicitly *not* for shared
spectrum, so licensed FR1 is the intended case) and `uto-UCI-Config-r18`
with `nrofBitsInUTO-UCI (3..8)`. 38.321 §5.8.2: an occasion indicated as
unused is *not available for use* and excluded from the MAC's procedures;
the UE decides *"by considering at least the amount of buffered data that
can be transmitted on the available occasions"*. 38.213 §9.3.1: the bitmap
maps to the next N occasions in start-time order, skipping occasions that
collide with DL symbols. **This is the CG for a camera:** period = frame
period, up to 32 slots of occasions, and the UE hands back what a small
frame does not need — which is exactly the "a 4 Mbps variable-frame source
wastes CG PRBs" reason the allocator declines the camera today. The
measured result that CG *does not reach the video guarantees* is a
statement about single-occasion CG, not about CG.

**B2. DL SPS.** 38.300 §10.2: RRC defines the periodicity, a CS-RNTI DCI
activates/deactivates, *"retransmissions are explicitly scheduled on
PDCCH(s)"*, up to 8 active configurations per BWP. 38.331 `SPS-Config`:
`periodicity` in {10, 20, 32, 40, 64, 80, 128, 160, 320, 640} ms plus
`periodicityExt-r16 INTEGER (1..5120)` in slots — so cmd_vel's 50 ms is
exactly 200 slots at μ = 2. Two uses here:

- *G1 (cmd_vel, 20 Hz).* No DL DCI per command; the DL cap is spent on the
  download and on retransmissions only. G1 passes today, so this is a
  margin measurement, not a fix.
- *G2 (STOP, 5 ms, aperiodic).* SPS cannot follow an aperiodic event, but a
  **standing lane** can: one SPS per robot with `periodicityExt` = one TDD
  period (5 slots) and a one-PRB TB. G2's mechanism is
  `ceil(n_stop / max_sched_ues)` DL opportunities against four TDD periods
  (CLAUDE.md, G2 entry); a lane removes the DCI from that count entirely,
  so all robots can be stopped in the same period. **Costs, both real:**
  (i) the UE blind-decodes every occasion and reports HARQ-ACK for it —
  38.213 §9.1 includes SPS occasions in the codebook whether or not the gNB
  transmitted, so an idle lane is a NACK per robot per period on PUCCH;
  (ii) either the PRB is reserved (N of 55 per D slot) or the gNB reuses it
  for another UE and accepts the NACK. Rel-17
  `downlinkHARQ-FeedbackDisabled` (per HARQ process, NTN-motivated) would
  silence (i) but also removes the retransmission trigger for the lane.
  This needs a measurement with both costs counted before it is an arm.

**B3. Per-LCH SR configurations.** 38.300 §16.1.1: *"RRC can associate
logical channels with different SR configurations, for instance, to provide
more frequent SR opportunities to URLLC services."* 38.321 §5.4.4: *"Each
logical channel … may be mapped to zero or one SR configuration"*; each has
its own `sr-ProhibitTimer` and `sr-TransMax`. 38.331: `schedulingRequestID`
in `LogicalChannelConfig`, `maxNrofSR-ConfigPerCellGroup = 8`, PUCCH SR
periodicity from `sym2` to `sl640`. **What the gNB gains is the identity of
the class that asked.** Today `sim/ul_access.py` models one SR
configuration whose grant is a fixed report floor (`sr_report_floor_bytes`),
and `sr_period_slots` has *no ground truth anywhere* (its own docstring).
With an SR ID the first grant after silence is sized for telemetry (300 B)
or for a camera frame, and the telemetry LCH can have SR occasions in every
U slot. This is Rel-15, needs no UE feature, and touches the crumb-grant and
cold-start mechanisms that CG only removes for the CG-mapped LCH. It is the
cheapest item on this list to model: an SR-ID → floor map.

**B4. The SR/CG interaction IEs.** 38.321 §5.4.5 triggers an SR for a
Regular BSR only if *"there is no UL-SCH resource available"*, or the UE has
a CG and the triggering LCH has `logicalChannelSR-Mask = false`, or the
available resource fails the LCH's mapping restrictions; NOTE 2 says an
active configured grant counts as available UL-SCH. `sim/configured_grant.py`'s
"covered flows raise no SR" is therefore `logicalChannelSR-Mask = true`
semantics, and `logicalChannelSR-DelayTimer` (sf20..sf2560) is the standard's
softer version. Nothing to build; the docstring should name the IEs.

**B5. Multi-PUSCH by a single DCI.** 38.214 §6.1.2.1: a row of
`pusch-TimeDomainAllocationListForMultiPUSCH` schedules *"two to eight
contiguous PUSCHs"* from one DCI 0_1, each with its own SLIV, HARQ process
IDs incremented per PUSCH and *not* incremented for PUSCHs colliding with DL
symbols — so in `DSUUU` one DCI in the D slot covers U, U, U for one robot.
This is the only mechanism that attacks the per-slot DCI cap for **dynamic**
traffic. Caveat that decides it: the UE capability
`multiPUSCH-UL-grant-r16` sits in RAN1 feature group 10 (the NR-U group) and
the Rel-17 extensions are FR2-only, so a licensed FR1 COTS UE may not
declare it; no OAI support. Measure only against a UE that has it.

**B6. Repetition.** 38.300 §10.3: *"for a transport block, two or more
repetitions can be in one slot, or across slot boundary in consecutive
available slots"*, dynamically indicated for DG and CG Type 2. One DCI, K
TBs, no HARQ round trip for the first K−1 — at the price of K× PRBs. The
retry-alignment work measured what a HARQ RTT costs under `DSUUU`; for a
40-byte STOP or a 5QI-1 command K = 2 costs one PRB. It addresses
link-loss failures (`bytes_harq_lost` under blockage, the 0 dB G1 case),
not the cap or the cadence, which is where the measured failures are.

### C. Deadline knowledge on the uplink

**C1. Delay Status Report (Rel-18).** 38.321 §5.4.9: per LCG the UE reports
*"remaining time, which is the smallest remaining value of the running PDCP
discardTimers among PDCP SDUs … buffered for the LCG but … not transmitted"*
and *"the total amount of delay-critical UL data for the LCG"*; triggered
when the remaining time drops below `remainingTimeThreshold` (1..64 ms, per
LCG), and it triggers an SR of its own if no grant is available. The MAC CE
(§6.1.3.72) carries a 6-bit remaining time in 1 ms bins. **This is the
uplink deadline the gNB never had.** The AGE/C3 proto flags reconstruct a
head-of-line age from the LCG clock stamped at BSR time, and the whole
"crumb resets the deadline clock" pathology is an artefact of that
reconstruction. The configuration scheduler's Tier-2 (plan §2, EDF over
per-flow deadlines) should be designed to consume a DSR when present and
fall back to the LCG clock when not. Prerequisite on the UE: PDCP
`discardTimer` set to the PDB (38.331 `discardTimer` ms10 … infinity,
`discardTimerExt-r16` down to 0.5 ms). Rel-18 UE feature
`delayStatusReport-r18`; the vendored OAI UE has nothing.

**C2. Refined BSR table (Rel-18).** 38.300 §16.15.4.2.1: *"One additional
buffer size table to reduce the quantisation errors in BSR and DSR
reporting (e.g. for high bit rates)"*, per LCG via
`additionalBS-TableAllowed`; 38.321 Table 6.1.3.1-3 spans 4 751 B to
~400 kB in ~2 % steps against the Rel-15 8-bit table's ~6–7 %. Low priority
here: the measured BSR error (median 12–13 kB at grant time on multi-LCG
UEs, `docs/wp9-plan.md` §20.1) is per-LCG *estimate desync*, not
quantisation. If it is ever modelled it is a third transcribed table
(`sim/bsr.py` rule: transcribe, never reconstruct).

**C3. PDU Set QoS (Rel-18).** 38.300 §16.15.2: PSDB *"supersedes the PDB of
the QoS flow"*, PSER supersedes PER, PSI ranks sets, PSIHI says whether all
PDUs are needed. §16.15.4.2.2: *"as soon as one PDU of a PDU set is known
to be lost, the remaining PDUs of that PDU Set … may be subject to discard
… to free up radio resources"*; UL side `pdu-SetDiscard-r18` in
`PDCP-Config`, and `discardTimerForLowImportance-r18` for PSI-based
discard. The camera scenarios already *score* by frame (`sim/messages.py::
FrameLedger`, G5's frame-age p95), but every scheduler here orders by
per-packet PDB and `sim/buffer.py::expire()` discards per packet, so PRBs
are spent finishing frames that are already late or already holed — the
same shape as G2's "a fragment of a STOP is not a STOP". For the
configuration scheduler: the per-flow deadline in Tier-2 is the **frame's**
PSDB, and a lost fragment discards its siblings.

### D. Collisions, inside and between UEs

**D1. Intra-UE prioritisation (Rel-16).** 38.300 §10.3: without
`lch-BasedPrioritization` *"the dynamically allocated uplink transmission
overrides the configured uplink grant … if they overlap in time"*; with it
the UE compares the highest LCH priority multiplexable into each, and a
deprioritised MAC PDU is *"kept … to allow the gNB to schedule a
retransmission"* or, with `autonomousTx`, sent on a later occasion of the
same CG. `sim/driver.py` implements the default (a pending dynamic TB
masks the UE, the CG occasion is skipped: `skipped_harq_pending`, 3–6 % of
occasions). With prioritisation a telemetry CG beats a camera DG in the same
slot. Model it if that skip fraction ever shows in a result.

**D2. UL cancellation / DL pre-emption.** 38.300 §10.3: *"The gNB may
cancel a PUSCH transmission … of a UE for another UE with a latency-critical
transmission"* (CI-RNTI, DCI 2_4, 38.213 §11.2A); §10.2 the DL mirror
(INT-RNTI, DCI 2_1, §11.2). Both displace an *already-scheduled* transmission
inside a slot. This simulator re-decides every 0.25 ms slot and the faithful
arms discard 30–65 % of UL PRB at the cap — PRBs are not the binding
resource, DCIs and visits are. Skip.

**D3. Duplication and survival-time state.** 38.300 §16.1.3 (CA/DC
duplication) and §16.8.1: with `survivalTimeStateSupport`, a CG
retransmission grant addressed to CS-RNTI puts the DRB into survival-time
state and *"all RLC entities configured for the DRB are activated … for
duplication"* (38.321 §5.4.1). Requires a second carrier or cell. Not
applicable to a single-cell factory; noted because `FlowConfig.
survival_time_ms` is never non-zero (CLAUDE.md, the twelve unreached
mechanisms) and TSCAI (A1) is where the value would come from.

### E. The rate and admission loop the simulator does not have

**E1. Notification control and Alternative QoS profiles.** 38.300 §12.1:
*"If … notification control is enabled and the RAN determines that the GBR
QoS cannot be guaranteed, RAN shall send a notification towards SMF and keep
the QoS Flow"*, and with Alternative QoS parameter sets *"the NG-RAN may also
include in the notification a reference corresponding to the QoS Parameter
Set which it can currently fulfil"*. The admissible-fleet boundaries
(G10 PF 12 / Reservation 6 / TwoTier 7 without CG, Reservation 6→10 with
CG; G5's fleet axis) are exactly the points
where the deployed gNB would emit this and the camera would be told to drop
to its alternative profile. The simulator has no admission control and no
notification; the cheapest faithful step is a per-GBR-flow counter "GFBR
unmet over the averaging window" emitted into `summary`, which turns a
campaign boundary into something a run reports about itself.

**E2. Recommended bit rate (ANBR).** 38.300 §16.2.1.1 and 38.321 §5.18.10:
a two-octet MAC CE from the gNB *"to indicate the recommended bit rate for
the UE for a specific logical channel and a specific direction"*, within
GBR..MBR; the UE may query, gated by `bitRateQueryProhibitTimer`. Specified
for MMTEL, but the MAC CE is generic. A camera stack that honours it turns
G7's clause-2 MFBR overshoot and G5's edge-SNR frame age into rate
adaptation rather than failure. `sim/traffic.py`'s `adaptive` kind adapts on
its own delivered rate; a gNB → source hint path does not exist.

**E3. Slice RRM policies.** 38.300 §16.3.3.2 with TS 28.541: dedicated,
prioritised and shared resource pools per slice, configured from O&M, with
*"the use of unused resources in the prioritized pool"* allowed. This is the
Reservation arm's idea as a product feature, at slice rather than flow
granularity. `slice_id` is never set and no scheduler reads it; a
control-slice (telemetry + STOP) versus video-slice partition is an arm
worth measuring once Reservation's own edit list exists to compare against.

---

## 3. Looked at and set aside, with the reason

- **`cg-RetransmissionTimer` / autonomous CG retransmission** — 38.331:
  *"not configured for operation in licensed spectrum"*. Confirms the
  choice in `sim/configured_grant.py` that a CG retransmission goes through
  a dynamic grant and the cap.
- **`cg-nrofSlots-r16` / `cg-nrofPUSCH-InSlot-r16`** — only configurable
  with `cg-RetransmissionTimer`, hence unlicensed; the licensed multi-slot CG
  is B1.
- **DRX, non-integer DRX cycles (Rel-18), PDCCH skipping, SSSG switching**
  — UE power; no QoS effect in this model.
- **SDT, 2-step RA** — attach path (`sim/random_access.py` is 4-step CBRA);
  would shorten G9's cold-attach timing, not change any verdict mechanism.
- **Ethernet header compression (Rel-16)** — a few bytes per telemetry
  packet on Ethernet PDU sessions.
- **TB over multiple slots, PUSCH repetition Type B** — coverage and
  sub-slot; the model is slot-granular.
- **NTN `downlinkHARQ-FeedbackDisabled`** — only as the B2 caveat.
- **PUCCH cell switching for TDD (Rel-17)** — needs an SCell.
- **Multi-cell scheduling by one DCI (Rel-18)** — single cell.
- **Pre-emptive BSR** — IAB only (38.300 §10.4 NOTE).

---

## 4. What the vendored OAI subset shows (files searched, per CLAUDE.md)

`grep -rli` over `oai-branches/**/*.{c,h}` — the four gNB scheduler files in
each of `two-tier/` and `reservation/`, `ia_p5g_scheduler.{c,h}`,
`mac_rrc_dl_handler.c`, `nr_mac_common.c`, `nr_ue_procedures.c`,
`nr_ue_scheduler.c`:

| concept | hits | reading |
|---|---|---|
| multi-PUSCH | none | absent |
| SPS | `gNB_scheduler_primitives.c` (both), `ia_p5g_scheduler.{c,h}`, `nr_ue_procedures.c` | the deleted Phase-2 hooks; no scheduler path |
| configured grant | primitives/ulsch (both), `ia_p5g_scheduler.c`, `nr_mac_common.c`, UE files | CG-confirmation MAC CE parsing and UE-side CG Type 1 handling; no gNB allocator |
| DSR, UL CI, ANBR, TSCAI | none | absent |
| pre-emption | `mac_rrc_dl_handler.c`, `ia_p5g_scheduler.c` | INT-RNTI configuration plumbing only |
| repetition | `nr_ue_scheduler.c` | UE side only |
| slice | `mac_rrc_dl_handler.c` | RRC/NSSAI plumbing only |

The vendored copy is a convenience subset, not the evidence base (CLAUDE.md);
a "the deployed C lacks X" claim for port-back planning must be re-checked
in the full checkout. Per-LCH SR (B3) in particular is **not established**
either way from these files.

---

## 5. What this changes in the agreed plan

1. **CG allocator (plan §1.3):** TSCAI (A1) and UE traffic info (A2) become
   the primary source of period, size and phase; the BSR-interval detector
   is the fallback. The CG offset is set from the burst arrival time.
2. **CG for video (the result CG did not reach):** B1 — multi-slot CG with
   UTO-UCI — is the standard's answer and is Rel-18. It is the next CG
   measurement: camera flows, period = frame period, occasions sized for the
   large frame, unused occasions returned to the dynamic path. Counters:
   occasions offered / used / returned / reused.
3. **Configuration scheduler Tier-2 (plan §2.3):** two inputs the design
   should take from the start — the UL deadline from a DSR (C1) with the LCG
   clock as fallback, and the frame (PSDB) rather than the packet as the
   deadline unit for video (C3), with sibling discard on a lost fragment.
4. **Cheap, Rel-15, COTS-safe, before any of the above:** per-LCH SR
   configurations (B3). It reaches the crumb and cold-start mechanisms on
   the flows CG does not cover and costs an SR-ID → grant-floor map in
   `sim/ul_access.py`.
5. **G2:** the only standard lever that removes the DL DCI from the STOP
   path is a standing SPS lane (B2); it has two costs that must be counted
   in the same measurement.
6. **Product-level, not simulator-level:** notification control (E1) and
   ANBR (E2) are how a deployed system would *use* the admissible-fleet
   numbers; a GFBR-unmet counter is the one cheap simulator step.
7. **Port-back reality:** every bold row except B2/B3/E1 is Rel-18 or Rel-16
   UE-capability-gated, and none is in OAI. The order above puts the
   Rel-15 items first for that reason.

---

## 6. Web sources used (framing only; mechanism claims come from the specs)

- 3GPP, "eXtended Reality for NR" — https://www.3gpp.org/technologies/xr-nr
- 3GPP, "Industrial 5G" (TSC, TSCAI, survival time) — https://www.3gpp.org/technologies/ind-5g
- Overview of NR Enhancements for Extended Reality (XR) in 3GPP 5G-Advanced — https://arxiv.org/abs/2412.00741
- Deterministic6G, "Tutorial: 5G Time Sensitive Communications" — https://deterministic6g.eu/images/presentations/European_Wireless_2023_Tutorial_5G_TSC.pdf
- 5G Configured Grant Scheduling for 5G-TSN Integration for the Support of Industry 4.0 — https://arxiv.org/pdf/2607.00704
- An open-source implementation and validation of 5G NR Configured Grant for URLLC in ns-3 5G LENA — https://arxiv.org/pdf/2606.18763
