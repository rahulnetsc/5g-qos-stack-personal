# Rel-16 is the compliance baseline — what changes from the Rel-18 editions we read

**Date:** 2026-09-15. **Decision (the user's):** the OAI gNB code base and,
more importantly, the COTS UE are **Rel-16** compliant. Everything the
simulator models as UE behaviour, and everything a port-back asks the UE to
do, must exist in the Rel-16 editions now in `docs/Rel 16/`. A gNB-internal
idea from a later release may still be ported, since it needs nothing from
the UE. The Rel-18 editions in `docs/` stay as the reference for what later
releases added, and every clause the survey of 2026-09-14 cited from them
is re-read here against Rel-16.

| set | editions (ETSI numbering) |
|---|---|
| Rel-16, `docs/Rel 16/` | TS 38.212 V16.15.0 · 38.213 V16.17.0 · 38.214 V16.17.0 · 38.300 V16.22.0 · 38.321 V16.22.0 · 38.331 V16.22.0 |
| Rel-18, `docs/` | TS 38.212 V18.8.0 · 38.213 V18.8.0 · 38.214 V18.10.0 · 38.300 V18.10.0 · 38.321 V18.10.0 · 38.331 V18.10.0 |

**Method.** Text extracted with `pypdf`; every clause and RRC IE the
simulator or the survey relies on was cut out of both editions and diffed
sentence by sentence (`scripts/spec_clause_diff.py`, the tool that produced
§2; the raw diffs are reproducible from it). "Unchanged" below means the
diff showed no change in the sentences the model depends on — not that the
clause is identical elsewhere.

---

## 1. The rule

1. **UE-side behaviour: Rel-16 only.** A mechanism the UE must implement
   (a MAC procedure, an RRC field the UE acts on, a UCI format) is usable
   only if it is in the Rel-16 editions. Cite the Rel-16 clause.
2. **gNB-side behaviour: any release, if it needs nothing from the UE.**
   Scheduler policy, allocator logic, what the gNB does with information it
   already receives (NGAP, its own measurements) can follow later-release
   ideas, labelled as such.
3. **Core-side inputs are conditional.** TSCAI is Rel-16 on NGAP, but
   free5GC's support is unverified, so anything that consumes it stays its
   own label (`+CGt`).

---

## 2. The delta, clause by clause

### 2.1 TS 38.321 (MAC)

| clause | what Rel-16 has (what the model uses) | added by Rel-17/18 | effect on the model |
|---|---|---|---|
| §5.4.1 UL grant reception | C-RNTI / CS-RNTI grants; CG Type 2 activation and release with the CG-confirmation trigger; `configuredGrantTimer`; `cg-RetransmissionTimer` (shared spectrum); HARQ process ID for a CG = `floor(CURRENT_symbol / periodicity) mod nrofHARQ-Processes` (+ `harq-ProcID-Offset2`); `lch-basedPrioritization` and `autonomousTx` de-prioritisation | 2-TB spatial multiplexing; CG-SDT, RACH-less HO / LTM; survival-time duplication trigger (`survivalTimeStateSupport`, Rel-17); `intraCG-Prioritization` (Rel-17); multi-PUSCH CG process IDs (`ID_OFFSET`, Rel-18); the "available for use" gate of UTO-UCI (Rel-18) | `sim/configured_grant.py` and the per-configuration HARQ blocks of 2026-09-15 use only the Rel-16 rules |
| §5.4.2.2 HARQ process | retransmission on the PDCCH-indicated resource, or autonomously on CG resources when `cg-RetransmissionTimer` is configured | SDT / RRC retransmission timers | unchanged: CG retries go through a CS-RNTI dynamic grant |
| §5.4.3.1 LCP | the mapping restrictions incl. `allowedCG-List` and `allowedPHY-PriorityIndex`; the two-round token-bucket procedure of §5.4.3.1.3; the MAC-CE priority list (BSR above data, padding BSR and bit-rate query below) | `allowedHARQ-mode` (NTN, Rel-17); DSR, TA report and other MAC CEs in the priority list | `sim/ue_lcp.py`, checked 2026-09-14 against V18.10.0, holds unchanged against V16.22.0 |
| §5.4.4 SR | multiple SR configurations, at most one per LCH; `sr-ProhibitTimer` / `sr-TransMax` per configuration; cancellation on a transmitted Long/Short BSR; RA fallback without a PUCCH resource | SR triggers for DSR, TA report, BFD-RS-set BFR, positioning gaps; simultaneous PUCCH-PUSCH configurations (Rel-17); SDT / LTM exceptions | `sim/ul_access.py`'s single SR path is a Rel-15 subset; per-LCH SR (survey B3) is Rel-16 |
| §5.4.5 BSR | Regular / Periodic / Padding triggers; `logicalChannelSR-DelayTimer`; the SR-trigger conditions (no UL-SCH resource; `logicalChannelSR-Mask` false with a CG; available resource fails the LCH's mapping restrictions); Short / Long / Truncated formats | Refined Long BSR with the second table (`additionalBS-TableAllowed`, Rel-18); IAB 256-LCG formats; SDT delay timer | `sim/bsr.py` and the CG's SR suppression are Rel-16 |
| §5.8.1 DL SPS | multiple SPS configurations per BWP, activation per configuration | MBS SPS | survey B2 is Rel-16 |
| §5.8.2 CG | Type 1 and Type 2; "multiple configurations can be active simultaneously in the same BWP"; period, `timeDomainOffset` + `timeReferenceSFN` (Type 1), recurrence from the activated PUSCH (Type 2); `harq-ProcID-Offset2` | multi-PUSCH CG (`nrofSlotsInCG-Period`), UTO-UCI availability, CG-SDT, RACH-less, hyper-SFN | the phase-per-configuration rule of 2026-09-15 is Rel-16; **multi-slot CG per period and UTO-UCI are not** |
| §6.1.3.1 BSR MAC CEs | Short, Long, Short/Long Truncated, Pre-emptive (IAB); Tables 6.1.3.1-1 (5-bit) and -2 (8-bit) | Refined Long, Extended formats and Table 6.1.3.1-3 | the transcribed tables in `sim/bsr.py` are the Rel-16 ones |
| §5.18.10 Recommended bit rate | the MAC CE and the query, with `bitRateQueryProhibitTimer` | — | survey E2 is Rel-15/16 |

### 2.2 TS 38.331 (RRC IEs)

| IE | Rel-16 fields the model or the survey rely on | Rel-17/18 additions | Rel-16 bounds that matter |
|---|---|---|---|
| `ConfiguredGrantConfig` | `periodicity` (enumerated, the 60 kHz set is identical to Rel-18's), `periodicityExt-r16` (any integer number of slots: 640 at 15 kHz, 1280 at 30 kHz, 2560 at 60 kHz, 5120 at 120 kHz), `nrofHARQ-Processes` 1..16, `harq-ProcID-Offset2-r16` 0..15, `configuredGrantTimer` 1..64, `repK` 1..8, `configuredGrantConfigIndex-r16` / `-IndexMAC`, `phy-PriorityIndex-r16`, `autonomousTx-r16`, `startingFromRV0-r16`; shared-spectrum only: `cg-RetransmissionTimer`, `cg-nrofSlots`, `cg-nrofPUSCH-InSlot`, `cg-StartingOffsets` | `repK-v1710` (12..32), `nrofHARQ-Processes-v1700` (17..32), `configuredGrantTimer-v1700`, `harq-ProcID-Offset2-v1700`, mTRP fields, CG-SDT, `periodicityExt-r17` (480/960 kHz), `disableCG-RetransmissionMonitoring-r18`, **`nrofSlotsInCG-Period-r18`**, **`uto-UCI-Config-r18`** | `sim/configured_grant.py`'s 2 processes per configuration, 400-slot period and 12 configurations per BWP are all inside Rel-16 |
| `LogicalChannelConfig` | `allowedCG-List-r16`, `allowedPHY-PriorityIndex-r16`, `configuredGrantType1Allowed`, `allowedSCS-List`, `maxPUSCH-Duration`, `schedulingRequestID`, `logicalChannelSR-Mask`, `logicalChannelSR-DelayTimerApplied`, `bitRateQueryProhibitTimer` | `allowedHARQ-mode` (Rel-17), IAB LCG extension | the restricted-CG switch is Rel-16 |
| `MAC-CellGroupConfig` | `lch-BasedPrioritization-r16`, `enhancedSkipUplinkTxDynamic/Configured`, `usePreBSR` | `intraCG-Prioritization-r17`, `drx-LastTransmissionUL-r17`, `dsr-ConfigToAddModList-r18`, the refined-BSR-table bitmap (Rel-18) | survey D1 is Rel-16; C1 and C2 are not |
| `SPS-Config` | `periodicity`, `periodicityExt-r16`, `sps-ConfigIndex-r16`, `harq-ProcID-Offset-r16`, `pdsch-AggregationFactor-r16`, `nrofHARQ-Processes` 1..8 | `sps-HARQ-Deferral-r17`, PUCCH sSCell, `nrofHARQ-Processes-v1710` (9..32) | a 5-slot DL SPS lane (survey B2) is expressible in Rel-16 |
| `SchedulingRequestResourceConfig` | per-SCS periodicities: 15 kHz 2sym, 7sym, 1, 2, 4, 5, 8, 10, 16, 20, 40, 80 sl; **30 kHz 2sym, 7sym, 1, 2, 4, 8, 10, 16, 20, 40, 80, 160 sl; 60 kHz 2sym, 7/6sym, 1, 2, 4, 8, 16, 20, 40, 80, 160, 320 sl**; 120 kHz 1..640 | 5 sl at 30 kHz and 5, 10 sl at 60 and 120 kHz (Rel-17 `additionalSR-Periodicities`), `periodicityAndOffset-r17` | see §4.2: the model's 10-slot SR period is lawful at the deployed 30 kHz and not at the modelled 60 kHz |
| `PUSCH-Config` | `pusch-AggregationFactor` (Type A repetition), `numberOfRepetitions-r16` in the TDRA row, PUSCH repetition Type B, `pusch-TimeDomainAllocationListForMultiPUSCH-r16` (the NR-U multi-PUSCH capability) | TBoMS, `numberOfRepetitionsExt-r17`, `extendedK2-r17`, available-slot counting for Type A (Rel-17) | in Rel-16 a Type A repetition that falls on a downlink slot is **omitted**, not deferred (TS 38.214 V16.17.0 §6.1.2.1) |
| `PDCP-Config` | `discardTimer` (ms10..infinity), `discardTimerExt-r16` (0.5 ms..), duplication with up to four RLC entities | `survivalTimeStateSupport-r17`, `discardTimerExt2-r17`, `pdu-SetDiscard-r18`, `discardTimerForLowImportance-r18` | survey C3 (PDU sets) has no UE-side Rel-16 form |
| `BSR-Config` | `periodicBSR-Timer`, `retxBSR-Timer`, `logicalChannelSR-DelayTimer` | — | unchanged |

### 2.3 TS 38.214 / 38.213 / 38.300

| clause | Rel-16 | Rel-17/18 additions | effect |
|---|---|---|---|
| 38.214 §6.1.2.1 TDRA / K2 | K2, SLIV, mapping type, `numberOfRepetitions` per row | TBoMS slot count, `extendedK2`, available-slot counting | the retry alignment's K2 reading holds |
| 38.214 §6.1.2.3 CG | `repK`, `repK-RV`, `startingFromRV0`, NR-U `cg-nrofSlots` | mTRP SRS-set mapping; `nrofSlotsInCG-Period` (Rel-18), which also disables repetition for that configuration | the model's single-occasion CG is the Rel-16 form |
| 38.213 §10.2 activation | the HARQ-process-number field names the `ConfiguredGrantConfigIndex` / `sps-ConfigIndex` when more than one configuration exists; joint release via the deactivation-state lists | G-CS-RNTI (MBS), DCI 4_x, 480/960 kHz timing | multi-configuration activation is Rel-16 |
| 38.213 §11.1 slot format | the TDD pattern rule | 480/960 kHz periods | unchanged |
| 38.213 §9.2.4 SR | the SR occasion rule | second LRR configuration | unchanged |
| 38.213 §9.3 UCI on PUSCH | CG-UCI (shared spectrum) | **UTO-UCI** | Rel-18 only |
| 38.300 §10.2 / §10.3 / §10.5 / §12.1 | SPS, CG Type 1/2, up to 12 CGs and 8 SPS per BWP, pre-emption (INT-RNTI), cancellation (CI-RNTI), MDBV, notification control | cell DTX, UE-Slice-MBR, NCR | unchanged |
| 38.300 §16.8 TSC | TSCAI with burst arrival time and periodicity; reference time delivery | survival time in TSCAI, PDC, timing-status monitoring (Rel-17); burst-arrival feedback (Rel-18) | `+CGt`'s inputs are Rel-16 on NGAP |
| 38.300 §16.15 XR | absent | the whole clause (Rel-18) | survey B1, C1, C2, C3, A2, A3 come from here |

---

## 3. The survey re-scoped

| survey row | mechanism | verdict under the rule |
|---|---|---|
| A1 | TSCAI | **Rel-16, gNB + core.** Keep, conditional on the core (`+CGt`). |
| A2 | UE-reported traffic info | **Rel-18 UE.** Out. |
| A3 | burst-arrival feedback | **Rel-18 core/RAN.** Out. |
| B1 | multi-slot CG per period + UTO-UCI | **Rel-18 UE.** Out. The Rel-16 route to a video CG is several single-occasion configurations at staggered phases (12 per BWP, `periodicityExt`) with dynamic top-up through the BSR that rides each CG PUSCH — waste is then the gNB's problem, since the UE cannot hand occasions back. |
| B2 | DL SPS, incl. the STOP lane | **Rel-16.** Keep as a candidate. |
| B3 | per-LCH SR configurations | **Rel-15/16.** Keep; still the cheapest next measurement. |
| B4 | `logicalChannelSR-Mask` / delay timer | **Rel-16.** Already what the model does. |
| B5 | multi-PUSCH by one DCI | **Rel-16 (NR-U capability group).** Only if the UE declares `multiPUSCH-UL-grant-r16`. |
| B6 | repetition | **Rel-16**, with the omitted-on-DL-slot rule, not deferral. |
| C1 | Delay Status Report | **Rel-18 UE.** Out. The gNB keeps inferring UL age (the LCG-clock model, the AGE/C3 lesson). |
| C2 | refined BSR table | **Rel-18 UE.** Out. |
| C3 | PDU-set QoS / discard | **Rel-18 UE and core.** Out on the UE side. A gNB may still treat DL fragments of one frame as a unit by its own inference — gNB-internal, labelled heuristic. |
| D1 | `lch-BasedPrioritization` | **Rel-16.** Keep. |
| D2 | UL cancellation / DL pre-emption | **Rel-16.** Still skipped on merit. |
| D3 | duplication / survival-time state | duplication Rel-15/16; the survival-time state is **Rel-17**. Both need CA or DC anyway. |
| E1 | notification control / alternative QoS | **Rel-16.** Keep (gNB + core). |
| E2 | recommended bit rate | **Rel-16.** Keep. |
| E3 | slice RRM policies | **Rel-16 / O&M.** Keep. |

---

## 4. What this means for the model as it stands

### 4.1 Nothing landed on 2026-09-14/15 needs a Rel-17/18 UE
Restricted CG (`allowedCG-List-r16`), Type 2 activation and release,
`periodicityExt-r16` periods, one HARQ-process block per configuration
(`harq-ProcID-Offset2-r16`), a phase per configuration (Type 2 recurrence
from the activated PUSCH, §5.8.2), independent HARQ processes across
configurations (§5.4.1 NOTE 5, present in V16.22.0), the SR suppression
rules (§5.4.5), the two-round LCP (§5.4.3.1.3), the BSR tables — every one
is in the Rel-16 text. The code's docstrings cited the V18 editions because
those were the ones read; the citations are now dual (V16.22.0 / V18.10.0)
where the text is the same.

### 4.2 One finding about the modelled cell, not the UE
`calibration-logs/twotier_startup_gnb.log` says the deployed cell is
**numerology 1 (30 kHz), 106 PRB, band n78**. The guarantee scenarios run
`ran_config_dsuuu_40mhz.yml`, **numerology 2 (60 kHz)**. That was chosen
before this note and is not changed by it, but it has one Rel-16
consequence: the model's default SR period of 10 slots
(`sim/ul_access.py`, "no ground truth anywhere") is a lawful Rel-16 value
at the deployed 30 kHz and **not** at the modelled 60 kHz, where Rel-16
allows 8, 16 or 20 slots and 10 arrives only with Rel-17. Recorded, not
fixed: changing it moves every run and needs the deployed value first
(the RRC configuration is not in the vendored files or the log).

### 4.3 The plan, re-scoped
- CG allocator: as planned (phase, HARQ blocks, `+CGt`), all Rel-16.
- Camera CG: the Rel-18 multi-slot form is off the table for the UE. The
  Rel-16 form is several configurations at staggered phases plus dynamic
  top-up; it is measurable with the model as it stands.
- Configuration scheduler Tier-2: no DSR, so the uplink deadline stays an
  inference from the LCG clock; no PDU-set signalling, so frame-level
  deadlines are a gNB-side heuristic for DL and unavailable for UL.
- Port-back note: UE side limited to `allowedCG-List-r16`,
  `lch-BasedPrioritization-r16` and Type 2 CG; gNB side may carry any
  scheduler policy.
