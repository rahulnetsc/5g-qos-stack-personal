# Request to the testbed: an SRB traffic capture from a normal session

**Sent 2026-09-08. Long lead time — please start it before anything else in
this note is discussed.**

## What we need

A capture of **RRC/NAS signalling on SRB1 and SRB2 during an ordinary
session** on the deployed gNB (the `twotier` build, N_RB 106, μ=1), from
one UE's attach through at least **10 minutes** of steady operation with
its data bearers active, including at least one of each of:

- an RRC connection setup (Msg3 → Msg5),
- a measurement report / RRC reconfiguration cycle,
- an RLF + reestablishment if one can be provoked safely,
- a UE-initiated release and re-attach.

For each signalling message, in order: **timestamp (ms), direction
(UL/DL), SRB id, RRC message type, and the PDCP SDU size in bytes.** Any of
these sources is sufficient:

1. `gNB` MAC/RLC log at `LOG_D` for `NR_MAC`/`NR_RLC` with the `[LCG-DEBUG]`
   and per-LCID delivery lines enabled (the `twotier_startup_gnb.log`
   format, but at debug level, over the whole session); **or**
2. a `pcap` from the gNB's F1/E1-less monolithic path via the OAI T-tracer
   (`T_GNB_MAC_UL_PDU_WITH_DATA` / `..._DL_PDU_WITH_DATA` suffice — we need
   sizes and LCIDs 1 and 2, not decoded RRC); **or**
3. Wireshark on the UE side with the `nr-rrc` dissector, exported as CSV.

Please also include the **RRC configuration in force** (the `.conf` the gNB
was started with, or the startup banner) so we can confirm
`sr-ProhibitTimer`, `periodicBSR-Timer`, and the SRB `logicalChannelGroup`
(expected 0) against what we model.

## Why it matters

Both deployed schedulers rank a UE with pending SRB data **above every GBR
bearer** (`has_srb`, the top tier in both directions on the reservation
build, `gNB_scheduler_ulsch.c:2167-2176`). That tier has never been live in
the simulator, because the simulator has no SRB traffic at all. We are
building it now (Build 1, RA + SRB). The procedure is a port of your code;
**the traffic that drives it is not in any log we have** — there are no
SRB message sizes or inter-arrival times anywhere in `calibration-logs/`.

Without a capture the SRB cadence will be **chosen**, from 38.331 message
sizes and a guessed inter-arrival, and every result it moves will say so on
the row. With a capture it is **measured**, and the guarantee table's
top-tier behaviour rests on your system rather than on our opinion.

## What would change if the chosen model were wrong

The direction is knowable and the magnitude is not. SRB traffic promotes a
UE above GBR, so more frequent or larger SRB messages make the deployed
Reservation and TwoTier **less** purely QoS-ordered than the simulated ones
have been — the G5 (video completeness), G8 (fairness / starvation) and
G10 (admissible fleet size) rows are the ones at stake, in the direction of
**worse** for the QoS arms as the SRB rate rises. A capture bounds that.

Contact: rahul.r@artpark.in
