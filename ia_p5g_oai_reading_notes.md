# IA-P5G — OAI Codebase Reading Notes

**Project:** QoS-Aware Private 5G for Industrial Automation (IA-P5G)
**Branch:** `feat/oai-integration`
**Purpose:** Living document capturing findings from OAI codebase reading.
Update as each cluster is completed.

---

## Document Status

| Cluster | Topic | Status |
|---|---|---|
| 1 | Scheduler Integration Point | ✅ Complete |
| 2 | QoS Flow Chain (5QI → DRB → MAC) | ✅ Complete |
| 3 | Metrics Collection (T Tracer) | ✅ Complete |
| 4 | rfsimulator + Channel Models | ✅ Complete |
| 5 | Multi-UE Orchestration | ✅ Complete |

---

## Cluster 1 — Scheduler Integration Point ✅

### Goal
Identify the exact hook point in OAI's MAC scheduler where TwoTier replaces the
default PF scheduler, confirm the C function signatures, map all available inputs,
and resolve the per-flow QoS access problem for multi-DRB UEs.

### Files Read
- `doc/MAC/scheduler-architecture.md`
- `doc/MAC/mac-usage.md`
- `openair2/LAYER2/NR_MAC_gNB/nr_mac_gNB.h`
- `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_dlsch_default_policies.h`
- `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch_default_policies.h`
- `openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_dlsch_default_policies.c`

---

### Finding 1.1 — Architecture: Function Pointers, Not Compile-Time Switches

The scheduler is a **7-stage pipeline** (8 for DL). Every stage is a named
function pointer field on `gNB_MAC_INST`, assigned at startup in `main.c`.
There are no `#ifdef` guards. The baseline (PF) and TwoTier can coexist in
the same binary, switchable at startup with three lines.

**Design doc assumption was outdated.** The design doc referred to replacing
`nr_fr1_dlsch_preprocessor()`. This function no longer exists under that name.
MR !3682 refactored the scheduler into a `_default_policies` split. The correct
hook point is now Stage 6 (RB allocation).

Full pipeline for reference:

```
Stage 1  Candidate Collection    fixed, not a function pointer
Stage 2  RI/PMI or RI/TPMI       pluggable
Stage 3  Beam Selection          pluggable
Stage 4  TDA Selection           pluggable
Stage 5  MCS Selection           pluggable  <- MCS set HERE, before Stage 6
Stage 6  RB Allocation           pluggable  <- TwoTier Tier-2 goes HERE
Stage 7  Dispatch                fixed
Stage 8  Per-LCID Byte Alloc     pluggable, DL only  <- 5QI-aware mux goes HERE
```

---

### Finding 1.2 — The Three Hook Points for IA-P5G

**Three functions to write. Three lines to register.**

#### DL RB Allocation (replaces nr_dl_proportional_fair)

```c
typedef int (*nr_dl_rb_alloc_fn)(const nr_dl_sched_params_t *params,
                                  nr_dl_candidate_t *candidates,
                                  int n_candidates);
// Registration in main.c:
RC.nrmac[i]->dl_rb_alloc = ia_p5g_dl_rb_alloc;
```

#### UL RB Allocation (replaces nr_ul_proportional_fair)

```c
typedef int (*nr_ul_rb_alloc_fn)(const nr_ul_sched_params_t *params,
                                  nr_ul_candidate_t *candidates,
                                  int n_candidates);
// Registration in main.c:
RC.nrmac[i]->ul_rb_alloc = ia_p5g_ul_rb_alloc;
```

#### DL Per-LCID Byte Allocation (replaces nr_dl_lcid_alloc_default)

```c
typedef void (*nr_dl_lcid_alloc_fn)(const gNB_MAC_INST *mac,
                                     const nr_dl_candidate_t *candidate,
                                     int tbs_available,
                                     int lcid_alloc[NR_MAX_NUM_LCID]);
// Registration in main.c:
RC.nrmac[i]->dl_lcid_alloc = ia_p5g_dl_lcid_alloc;
```

> **Note:** There is no UL equivalent of lcid_alloc. UL logical channel muxing
> is handled autonomously by the UE's MAC entity (LCP procedure, TS 38.321).

---

### Finding 1.3 — Complete Tier-2 Input Map

#### DL Candidate (nr_dl_candidate_t)

| Field | Type | Staleness | Tier-2 use |
|---|---|---|---|
| `pending_bytes` | uint32_t | Fresh every slot | Buffer depth Bi |
| `pending_bytes_per_lcid[NR_MAX_NUM_LCID]` | uint32_t[] | Fresh every slot | Per-flow buffer depth (lcid_alloc) |
| `bler` | float | 50 ms window | BLER feedback |
| `bler_updated` | bool | Per-frame flag | Staleness guard — check before using bler |
| `avg_throughput` | float bps EWMA | Continuous | Throughput tracker, PF denominator |
| `current_mcs` | int | Set at collect | Held MCS for efficiency computation |
| `sched_pdsch.mcs` | uint8_t | Set by Stage 5 | MCS for TBS calc — already set when rb_alloc runs |
| `max_mcs` | int | Config + UE cap | Hard ceiling — never exceed |
| `fiveQI` | uint64_t | Set at attach | 5QI of **first DRB only** — see Finding 1.5 |
| `priority` | int | Set at attach | LC priority of first DRB (lower = higher priority) |
| `nssai` | nssai_t | Set at attach | Slice identity |
| `cqi` | uint16_t | CSI report period | Channel quality; held-last-value between reports |
| `csi_ri` | uint8_t | CSI report period | Rank indicator |
| `is_retx` | bool | Fresh | Must handle before new data |
| `retx_rbSize` | int | Fresh | Exact PRBs required for retx |
| `bwp_start` / `bwp_size` | int | Set at attach | BWP geometry for PRB indexing |

#### UL Candidate (nr_ul_candidate_t) — same fields plus:

| Field | Type | Staleness | Tier-2 use |
|---|---|---|---|
| `ph` | int | PHR event-driven | Power headroom — use nr_ul_phr_advice_t pattern |
| `pcmax` | int | Set at attach | Max configured TX power |
| `snrx10` | int | PUSCH measurement | SINR*10; used for SINR-based MCS override path |
| `sched_inactive` | bool | Fresh | Must give minimum grant if true |

---

### Finding 1.4 — MCS Is Pre-Set; Tier-2 Only Refines Downward

MCS is selected at Stage 5 (mcs_select) before rb_alloc (Stage 6) runs.
COMMIT_ALLOC is a macro (not a function) that atomically writes rbStart,
rbSize, mcs onto the candidate, validates CCE assignment, marks the VRB map,
and sets cand->scheduled = true. Never mark the VRB map manually.

TBS utility: nr_find_nb_rb() in gNB_scheduler_primitives.c — given target
bytes, returns minimum rbSize.

---

### Finding 1.5 — LCID->5QI Mapping: Already in OAI, No New Fields Needed

OAI already stores per-LCID QoS configuration in NR_UE_sched_ctrl_t:

```c
typedef struct NR_QoS_config_s { int fiveQI; int priority; } NR_QoS_config_t;

typedef struct nr_lc_config {
  uint8_t         lcid;
  bool            suspended;
  int             priority;
  nssai_t         nssai;
  NR_QoS_config_t qos_config[NR_MAX_NUM_QFI];
} nr_lc_config_t;

// Inside NR_UE_sched_ctrl_t:
seq_arr_t lc_config;   // dynamic array of nr_lc_config_t, one per active LCID
```

Access path from inside lcid_alloc: candidate->UE->UE_sched_ctrl.lc_config

Populated by handle_ue_context_drbs_setup() in mac_rrc_dl_handler.c:291
at DRB setup time. Static from the scheduler's perspective — read-only.

---

### Finding 1.6 — Default PF Behaviour (Baseline)

nr_dl_proportional_fair runs three phases per slot:
1. Retransmissions first — exact retx_rbSize PRBs
2. No-data UEs — minimum grant (5 PRBs) for MAC CEs only
3. New data — sort by pending_bytes / avg_throughput (PF weight), greedy

No flow awareness, no GBR, no PDB. TwoTier replaces phase 3 only.

---

### Finding 1.7 — Tunable Config Parameters

From mac-usage.md, key MACRLCs knobs:

| Parameter | Default | IA-P5G note |
|---|---|---|
| dl_bler_target_upper | 0.15 | Lower for URLLC flows (5QI=2, 5QI=82) |
| dl_bler_target_lower | 0.05 | — |
| ulsch_max_frame_inactivity | 10 frames (100 ms) | Lower for sensor_dense |
| dl_harq_round_max | 4 | Consider 2 for PDB=10 ms flows |
| ul_harq_round_max | 4 | Same |

---

### Cluster 1 — Open Items

- [ ] Confirm seq_arr_at() macro/function signature for iterating lc_config
- [ ] Verify NR_MAX_NUM_QFI value — max QFIs a single LCID can carry
- [ ] Check whether fiveQI on the candidate is populated from
      lc_config[0].qos_config[0].fiveQI at collect time or derived elsewhere

---

## Cluster 2 — QoS Flow Chain (5QI -> DRB -> MAC) ✅

### Goal
Understand the full end-to-end QoS path from PDU session establishment in the
core to the MAC scheduler. Determine the correct flow classification mechanism
for multi-flow UEs across all five scenarios.

### Files Read
- openairinterface5g/doc/tutorial_resources/oai-cn5g/conf/config.yaml
- ci-scripts/oai-cn5g/database/oai_db.sql
- openair2/LAYER2/SDAP/nr_sdap/nr_sdap_entity.c
- openair2/LAYER2/SDAP/nr_sdap/nr_sdap.c
- openair2/LAYER2/NR_MAC_gNB/mac_rrc_dl_handler.c
- ci-scripts/yaml_files/5g_rfsimulator_multiue/nrue.uicc.conf
- ci-scripts/conf_files/gnb.sa.band78.106prb.rfsim.yaml
- grep of pdu_sessions in openair3/NAS/NR_UE/nr_nas_msg.c and openair2/RRC/NR/

---

### Finding 2.1 — Corrected 3GPP QoS Architecture

Control Plane — PDU session establishment:
```
UE -> AMF -> SMF
               |-- UDR (subscription QoS profile per IMSI)
               |-- PCF (PCC rules / SDF filter templates)
               |-- UPF via N4 PFCP Session Establishment:
               |     PDR  (Packet Detection Rule — SDF filter -> QFI assignment)
               |     QER  (QoS Enforcement Rule — GBR/MBR token bucket)
               |     FAR  (Forwarding Action Rule — GTP-U encapsulation + TEID)
               +-- gNB via N2/NGAP PDU Session Resource Setup:
                     QFI list, 5QI, ARP, GBR, MBR per flow
```

Downlink data path:
```
App server -> UPF N6 -> PDR match (SDF filter) -> QER (rate enforce)
-> FAR (GTP-U encapsulate, QFI in PDU Session Container ext header)
-> gNB N3 -> SDAP reads QFI from GTP-U ext header
-> qfi2drb_table[QFI] -> DRB -> LCID
-> MAC: lc_config[lcid].fiveQI available for scheduler
```

Uplink data path:
```
UE NAS QoS rule match -> SDAP prepends SDAP header (QFI field)
-> PDCP -> RLC -> MAC (UE side)
-> gNB SDAP RX: reads QFI from SDAP header
-> GTP-U encapsulate with QFI -> UPF N3 -> QER -> N6
```

Key corrections vs. simplified DSCP model:
- QFI is assigned by the PDR at the UPF, not derived from DSCP
- QER handles rate enforcement; FAR handles GTP-U encapsulation (separate rules)
- N4 Session Establishment Request must precede rule installation at UPF
- UE generates SDAP header (not GTP-U header) on the radio side
- Reflective QoS (RDI bit) is implemented in OAI SDAP but not needed for IA-P5G

---

### Finding 2.2 — OAI CN5G Bypasses UDM/PCF

```yaml
smf:
  support_features:
    use_local_subscription_info: yes
    use_local_pcc_rules: yes
```

---

### Finding 2.3 — Default Config Has Only 5QI=9 (Best-Effort)

Every DNN has: 5qi: 9, session_ambr_ul: "10Gbps", session_ambr_dl: "10Gbps".
All traffic is best-effort out of the box.

---

### Finding 2.4 — local_pcc_rules Block Does Not Exist

use_local_pcc_rules: yes is set but no local_pcc_rules: data block exists
in the file. Port-based SDF filter classification not available through config.

---

### Finding 2.5 — oai_db.sql Is a 4G EPC Database (Irrelevant)

Contains 4G constructs (mmeidentity, pdn with qci column, pgw, users).
Not used by OAI CN5G's 5G core. Active subscriber data managed via
local_subscription_infos in config.yaml.

---

### Finding 2.6 — SDAP QFI->DRB Mapping Is Correct and Complete

- qfi2drb_table[SDAP_MAX_QFI] per SDAP entity (one entity per PDU session)
- DL TX: gNB prepends SDAP header with QFI before sending to PDCP
- UL RX: gNB reads QFI from SDAP header, forwards to GTP-U via
  gtpv1uSendDirectWithQFI() with QFI in PDU Session Container extension header
- Reflective QoS implemented (RDI path) — not needed for IA-P5G

---

### Finding 2.7 — GBR Values Do NOT Reach the MAC

NR_QoS_config_t contains only fiveQI and priority. GBR/MBR/GFBR/MFBR
values are not propagated to the MAC. Tier-1's LP must use 5QI standard
defaults from TS 23.501 Table 5.7.4-1, not actual negotiated values.

---

### Finding 2.8 — 5QI->Priority Mapping Is Hardcoded in OAI

```c
const uint64_t qos_fiveqi[26]   = {1, 2, 3, 4, 65, 66, 67, 71, 72, 73, 74,
                                    76, 5, 6, 7, 8, 9, 69, 70, 79, 80, 82,
                                    83, 84, 85, 86};
const uint64_t qos_priority[26] = {20, 40, 30, 50, 7, 20, 15, 56, 56, 56, 56,
                                    56, 10, 60, 70, 80, 90, 5, 55, 65, 68, 19,
                                    22, 24, 21, 18};
```

If a 5QI value not in this list is configured, get_non_dynamic_priority()
calls AssertFatal and crashes the gNB.

Verified 5QIs for IA-P5G scenarios:

| Python QFI | Semantics | Chosen 5QI | In OAI table? | Priority | PDB |
|---|---|---|---|---|---|
| 2 | UL GBR camera/LIDAR | 2 | Yes | 40 | 150 ms |
| 82 | DL control loop 10 ms | 82 | Yes | 19 | 10 ms |
| 9 | Best-effort | 9 | Yes | 90 | 300 ms |
| 8 | TCP ACKs / bulk | 8 | Yes | 80 | 300 ms |
| 1 | DL interactive 12 ms | 82 (not 1) | Yes | 19 | 10 ms |

Note: Python QFI=1 must map to 5QI=82, not 5QI=1. 5QI=1 is VoNR (100 ms PDB).

---

### Finding 2.9 — RLC Mode Is CU-Controlled via F1AP

```c
const NR_RLC_Config_PR rlc_conf = drb->rlc_mode == F1AP_RLC_MODE_AM
    ? NR_RLC_Config_PR_am : NR_RLC_Config_PR_um_Bi_Directional;
```

Also: long priority = 13; // hardcoded for the moment — RLC bearer config
priority hardcoded to 13 for all DRBs.

---

### Finding 2.10 — gNB Config Has No QoS Stanzas

gnb.sa.band78.106prb.rfsim.yaml MACRLCs block has only: pusch_TargetSNRx10,
pucch_TargetSNRx10, stats_max_ue. All QoS comes dynamically via RRC/F1AP.

---

### Finding 2.11 — Multi-PDU Session Establishment Is Batch, Not Sequential

- nr_nas_msg.c:2047: loops over ALL pdu_sessions entries at initial attach
- rrc_gNB.c: allocates calloc(num_pdu_sessions, ...) — batch processing
- rrc_gNB_NGAP.c: NGAP PDU Session Resource Setup Response carries an array

All PDU sessions established as a batch. Session order follows config array order.

---

### Finding 2.12 — DNN-Based Separation Is the Correct Implementation Path

#### Required DNN Set

| DNN | 5QI | Priority | Use |
|---|---|---|---|
| oai | 9 | 90 | Best-effort (already exists) |
| gbr-video | 2 | 40 | UL GBR camera/LIDAR streams |
| urllc-ctrl | 82 | 19 | DL/UL control loops (PDB 10 ms) |
| be-bulk | 8 | 80 | TCP ACKs, bulk transfers |

#### Required config.yaml Additions

```yaml
# Add to local_subscription_infos:
- single_nssai: *embb_slice
  dnn: "gbr-video"
  qos_profile: { 5qi: 2, session_ambr_ul: "50Mbps", session_ambr_dl: "50Mbps" }

- single_nssai: *embb_slice
  dnn: "urllc-ctrl"
  qos_profile: { 5qi: 82, session_ambr_ul: "10Mbps", session_ambr_dl: "10Mbps" }

- single_nssai: *embb_slice
  dnn: "be-bulk"
  qos_profile: { 5qi: 8, session_ambr_ul: "100Mbps", session_ambr_dl: "100Mbps" }

# Add same DNNs to: dnns, smf_info.dnnSmfInfoList, upf_info.dnnUpfInfoList
```

#### Per-UE pdu_sessions Ordering Convention

Put highest-priority (lowest 3GPP priority number) DNN first.

Example — factory_robots UE 8 (UL GBR camera + UL best-effort + DL control):
```
pdu_sessions = (
  { dnn = "urllc-ctrl"; nssai_sst = 1; },
  { dnn = "gbr-video";  nssai_sst = 1; },
  { dnn = "oai";        nssai_sst = 1; }
);
```

---

### Finding 2.13 — Traffic Generator Binding Strategy

```bash
# Readiness gate
expected=$N_PDU_SESSIONS
while [ $(ip addr show | grep "inet 10\." | wc -l) -lt $expected ]; do
  sleep 0.5
done

# Example: factory_robots UE 8
iperf3 -c <server> -B 10.0.2.<x> -u -b 8M -t 60    # UL GBR camera
iperf3 -s -B 10.0.3.<x> -u &                         # DL control (server)
iperf3 -c <server> -B 10.0.0.<x> -u -b 10M -t 60   # UL best-effort
```

---

### Cluster 2 — Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| GBR/MBR not propagated to MAC | Tier-1 LP uses 5QI standard defaults | Use TS 23.501 Table 5.7.4-1 default GBR values per 5QI |
| candidate->fiveQI = first DRB only | Inter-UE priority in rb_alloc based on first session's 5QI | Stage 2: composite priority from lc_config loop; Stage 1: ordering convention mitigates |
| RLC mode not directly configurable | AM/UM determined by CU RRC logic | Defer to Stage 3; verify empirically |
| UL per-flow 5QI differentiation not possible | UL scheduler sees per-UE BSR only | Known architectural limitation |
| local_pcc_rules SDF filters unsupported | Cannot do single-PDU-session multi-flow via port filters | DNN-based separation fully substitutes |

---

## Cluster 3 — Metrics Collection (T Tracer) ✅

### Goal
Understand what the T tracer exposes natively per slot, identify gaps
(especially HoL delay and per-flow granularity), design the metric correlation
strategy, and define the complete KPI collection pipeline for Stage 1.

### Files Read
- common/utils/T/T_messages.txt
- common/utils/T/tracer/gnb_mac.c
- common/utils/T/tracer/csv.c
- common/utils/T/tracer/throughputlog.c
- common/utils/T/local_tracer.c

---

### Finding 3.1 — The Six Key NR gNB MAC T Events

From T_messages.txt, the complete set of NR gNB MAC events relevant to IA-P5G:

```
GNB_MAC_DL
  GROUP = ALL:MAC:GNB
  FORMAT = rnti, frame, slot, mcs, tbs
  -> Per-UE DL scheduler decision, every scheduled slot

GNB_MAC_LCID_DL
  GROUP = ALL:MAC:GNB
  FORMAT = rnti, frame, slot, lcid, data_size, tx_list_occupancy
  -> Per-LCID DL bytes scheduled + RLC TX buffer depth (PDU count)

GNB_MAC_UL
  GROUP = ALL:MAC:GNB
  FORMAT = rnti, frame, slot, mcs, tbs
  -> Per-UE UL scheduler decision (DCI grant)

GNB_MAC_LCID_UL
  GROUP = ALL:MAC:GNB
  FORMAT = rnti, frame, slot, lcid, data_size
  -> Per-LCID UL bytes received at gNB

GNB_MAC_PUSCH_POWER_CONTROL
  GROUP = ALL:MAC:GNB:CSV
  FORMAT = rnti, frame, slot, snrx10, phr, tpc, tb_size, txpower_calc, rbSize, mcs, rssi
  -> PHR + UL SINR, event-driven on each PUSCH reception

GNB_MAC_RETRANSMISSION_DL_PDU_WITH_DATA
  GROUP = ALL:MAC:GNB:WIRESHARK
  FORMAT = gNB_ID, CC_id, rnti, frame, slot, harq_pid, round, data
  -> HARQ retransmission with round number
```

---

### Finding 3.2 — Q1: HoL Delay Is NOT a Native T Event

No HoL delay event exists in T_messages.txt. There is no event that timestamps
packet arrival at the RLC buffer.

The closest proxy is GNB_MAC_LCID_DL.tx_list_occupancy — the number of RLC
PDUs waiting in the TX buffer at scheduling time. This is a queue depth in PDU
count, not delay in milliseconds, and is only available for DL.

Conclusion: HoL delay requires the UDP probe approach — timestamp packets at
the sender, receive them at the UE, compute the difference.

---

### Finding 3.3 — Q2: BSR, PHR, CQI Availability

#### On BSR specifically

BSR IS transmitted over the air from UE to gNB as a MAC CE in the UL MAC PDU
(Short BSR = LCID 61, Long BSR = LCID 62 per TS 38.321 Table 6.2.1-2). The
gNB decodes it and stores the value in NR_UE_sched_ctrl_t.estimated_ul_buffer.
The scheduler uses this as cand->pending_bytes.

However, the decoded BSR value is NOT emitted as a dedicated T tracer event.
The raw MAC PDU (including the BSR MAC CE binary) is visible in
GNB_MAC_UL_PDU_WITH_DATA (WIRESHARK group) but requires MAC PDU decoding.

Full signal availability:

| Signal | T Event? | Where | Availability | Notes |
|---|---|---|---|---|
| BSR (raw CE) | GNB_MAC_UL_PDU_WITH_DATA | Binary buffer | WIRESHARK group, needs PDU decoder | |
| BSR (decoded) | No dedicated event | estimated_ul_buffer in NR_UE_sched_ctrl_t | Add T_RECORD for Stage 2 | |
| PHR | GNB_MAC_PUSCH_POWER_CONTROL.phr | T event | Event-driven on PUSCH; held-last-value | |
| UL SINR | GNB_MAC_PUSCH_POWER_CONTROL.snrx10 | T event | Event-driven; proxy for UL channel quality | |
| DL CQI | No dedicated event | CSI_report in NR_UE_sched_ctrl_t | Readable in-process; not T-traced | |
| HARQ rounds | GNB_MAC_RETRANSMISSION_DL_PDU_WITH_DATA.round | T event | Per retransmission event | |
| UL bytes per LCID | GNB_MAC_LCID_UL.data_size | T event | Per received PDU; indirect BSR proxy | |

For Stage 2 input validation: add T_RECORD(GNB_MAC_BSR, rnti, frame, slot,
estimated_ul_buffer) where BSR MAC CE is decoded in the UL scheduler.

---

### Finding 3.4 — Q3: Per-LCID Throughput Is Native and Complete

GNB_MAC_LCID_DL and GNB_MAC_LCID_UL provide per-LCID per-slot byte counts
directly. Confirmed by gnb_mac.c which uses these for live GUI plots:

```c
// DL per-LCID throughput, 20-slot rolling window:
l = new_throughputlog(h, database, "GNB_PHY_DL_TICK", "frame", "slot",
    "GNB_MAC_LCID_DL", "data_size", 20);

// UL per-LCID throughput:
l = new_throughputlog(h, database, "GNB_PHY_UL_TICK", "frame", "slot",
    "GNB_MAC_LCID_UL", "data_size", 20);

// DL per-LCID RLC TX buffer occupancy:
l = new_ticked_ttilog(h, database, "GNB_PHY_DL_TICK", "frame", "slot",
    "GNB_MAC_LCID_DL", "tx_list_occupancy", 0, -1);
```

From throughputlog.c: accumulates data_size bytes per PHY tick event and
computes rolling throughput. At mu=1, ticks_per_frame=20 gives a 10 ms window.

The harness must build a RNTI -> DNN -> flow class mapping at runtime after
UE attach, since RNTI is the identifier in T tracer events.

---

### Finding 3.5 — Q4: Time Reference — Both Wall Clock AND Frame+Slot

From csv.c:
```c
void csv(void *_d, event e) {
  if (d->fields[i] == TIMESTAMP_FIELD) {
    struct tm *t = localtime(&e.sending_time.tv_sec);
    printf("%2.2d:%2.2d:%2.2d.%6.6ld",
           t->tm_hour, t->tm_min, t->tm_sec, e.sending_time.tv_nsec / 1000);
  }
}
```

Every T event carries e.sending_time (struct timespec wall-clock, ns precision),
formatted as HH:MM:SS.microseconds. Events also carry frame and slot fields.

Both references are available in every event. Wall-clock aligns with iperf3
JSON output. Frame+slot provides MAC-layer alignment. Cross-check:
wall_clock_at_slot_0 + slot_index * 0.5ms should match e.sending_time within
a few microseconds. Discrepancy flags a clock sync problem.

---

### Finding 3.6 — Q5: csv.c Format and Usage

csv.c is a standalone command-line tool:
- Connects to T tracer socket at 127.0.0.1:2021 (configurable)
- Subscribes to a named event with selected field names as arguments
- Prints one CSV row per event to stdout
- -t <name> injects wall-clock timestamp as a named field
- -f flushes stdout after each line (essential for live capture to file)
- -s <sep> configures separator (default comma)

Usage for IA-P5G metrics collection:

```bash
# DL per-LCID: bytes scheduled + RLC queue depth
./csv -d T_messages.txt -ip 127.0.0.1 -p 2021 -f -t ts \
    GNB_MAC_LCID_DL ts rnti frame slot lcid data_size tx_list_occupancy \
    >> results/dl_lcid_raw.csv &

# UL per-LCID: bytes received
./csv -d T_messages.txt -ip 127.0.0.1 -p 2021 -f -t ts \
    GNB_MAC_LCID_UL ts rnti frame slot lcid data_size \
    >> results/ul_lcid_raw.csv &

# PHR + SINR (event-driven)
./csv -d T_messages.txt -ip 127.0.0.1 -p 2021 -f -t ts \
    GNB_MAC_PUSCH_POWER_CONTROL ts rnti frame slot snrx10 phr rbSize mcs \
    >> results/power_ctrl_raw.csv &

# DL scheduler decisions (per-UE MCS + TBS)
./csv -d T_messages.txt -ip 127.0.0.1 -p 2021 -f -t ts \
    GNB_MAC_DL ts rnti frame slot mcs tbs \
    >> results/dl_sched_raw.csv &
```

CRITICAL: csv must be started BEFORE run_scenario.sh injects traffic.
From local_tracer.c: T events are forwarded only to currently-connected
tools. If no csv process is connected, events are silently dropped.

---

### Finding 3.7 — Metric Correlation Strategy

All three measurement sources carry wall-clock timestamps:

| Source | Timestamp format | Granularity |
|---|---|---|
| T tracer (csv.c) | HH:MM:SS.microseconds | Per event (sub-ms) |
| iperf3 | Unix epoch ms (JSON with -i 0.1) | 100 ms intervals |
| UDP probe | Application payload timestamp | Per packet |

Alignment procedure:
1. Record T_start wall clock at start of run_scenario.sh
2. All three tools started before T_start; pre-T_start rows discarded
3. T tracer rows and iperf3 rows aggregated into 1-second buckets by wall-clock
4. UDP probe HoL = receive_time - send_timestamp per packet per flow

---

### Finding 3.8 — RNTI-to-Flow Mapping

T tracer events use RNTI as UE identifier. Build mapping after attach:

```bash
# Query gNB telnet for RNTI list:
echo "nr_show_ue" | nc -q1 localhost 9090
# Or grep from gNB stdout log
```

Mapping chain: RNTI -> IMSI -> uicc config -> pdu_sessions[i].dnn -> flow class -> 5QI

This mapping is static for the duration of a run.

---

### Finding 3.9 — NR_mac_stats_t — Richer In-Process Stats (Not T-Traced)

nr_mac_gNB.h defines a rich stats struct inside NR_UE_info_t:

```c
typedef struct NR_mac_dir_stats {
  uint64_t lc_bytes[64];      // cumulative per-LCID bytes
  uint64_t rounds[8];         // HARQ round counters
  uint64_t errors;
  uint64_t total_bytes;
  uint32_t current_bytes;     // currently in-flight bytes
  uint64_t total_sdu_bytes;
  uint32_t total_rbs;
  uint32_t total_rbs_retx;
  uint32_t current_rbs;
} NR_mac_dir_stats_t;
```

Updated every scheduling cycle but lives only in process memory. Accessible
via gNB telnet nr_show_ue command or by adding T_RECORD calls. ul.lc_bytes[lcid]
provides cumulative per-LCID UL byte counters.

---

### Cluster 3 — Complete KPI Source Table

| KPI | Source | Event/tool | Granularity | Stage 1? |
|---|---|---|---|---|
| DL throughput per flow | T tracer | GNB_MAC_LCID_DL.data_size | Per slot | Native |
| UL throughput per flow | T tracer | GNB_MAC_LCID_UL.data_size | Per slot | Native |
| DL RLC queue depth | T tracer | GNB_MAC_LCID_DL.tx_list_occupancy | Per slot | Native (PDU count proxy) |
| DL MCS per UE | T tracer | GNB_MAC_DL.mcs | Per scheduled slot | Native |
| UL MCS per UE | T tracer | GNB_MAC_UL.mcs | Per scheduled slot | Native |
| DL TBS per UE | T tracer | GNB_MAC_DL.tbs | Per scheduled slot | Native |
| UL TBS per UE | T tracer | GNB_MAC_UL.tbs | Per scheduled slot | Native |
| HARQ retx round | T tracer | GNB_MAC_RETRANSMISSION_DL_PDU_WITH_DATA.round | Per retransmission | Native |
| PHR per UE | T tracer | GNB_MAC_PUSCH_POWER_CONTROL.phr | Event-driven | Native |
| UL SINR per UE | T tracer | GNB_MAC_PUSCH_POWER_CONTROL.snrx10 | Event-driven | Native |
| App-layer throughput | iperf3 | --json -i 0.1 | 100 ms intervals | Native |
| Packet loss ratio | iperf3 | --json | Per run | Native |
| HoL delay p50/p95/p99 | UDP probe | Custom payload timestamps | Per packet | Custom tool needed |
| BSR (decoded) per UE | Not T-traced | estimated_ul_buffer in MAC | — | Stage 2: add T_RECORD |
| DL CQI per UE | Not T-traced | CSI_report in MAC | — | Stage 2: add T_RECORD |

---

### Cluster 3 — What Needs to Be Built for Stage 1

No OAI source changes required. All Stage 1 collection uses existing T events.

```
collect_metrics.sh:
  - Start 4 csv processes (dl_lcid, ul_lcid, power_ctrl, dl_sched)
  - Must start BEFORE run_scenario.sh (events dropped if no consumer connected)
  - All csv processes use -f flag for flush

rnti_map.sh:
  - Run after all UEs attach, before metrics collection
  - Builds RNTI->IMSI->DNN->flow mapping file

udp_probe (custom tool):
  - Sender: inject UDP packets with microsecond wall-clock timestamp in payload
  - Receiver (in UE container): record receive time, compute HoL = recv - send
  - Output: per-packet CSV with (timestamp, flow_id, hol_ms)
  - One probe instance per DL flow with a PDB SLA

generate_report.py:
  - Load: dl_lcid_raw.csv, ul_lcid_raw.csv, iperf3 JSON, udp_probe CSV
  - Join on wall-clock timestamp + rnti_map
  - Aggregate into 1-second buckets
  - Compute: avg_throughput, p50/p95/p99 HoL, BLER, PRB utilisation per flow
  - Output: summary.json + report.md with SLA pass/fail table
```

For Stage 2 additionally (requires OAI recompile):
- Add T_RECORD(GNB_MAC_BSR, rnti, frame, slot, estimated_ul_buffer) at BSR
  MAC CE decode point in UL scheduler
- Add T_RECORD(GNB_MAC_DL_CQI, rnti, frame, slot, cqi, ri) in DL MCS select
- Both require new entries in T_messages.txt

---

## Cluster 4 — rfsimulator + Channel Models ✅

### Goal
Confirm which channel model profiles exist natively in OAI's rfsimulator,
identify whether the InF (Indoor Factory) model from TR 38.901 is available,
understand the per-UE channel configuration mechanism, and characterise the
maximum UE count before the timing loop degrades.

### Files Read
- radio/rfsimulator/README.md
- radio/rfsimulator/simulator.cpp
- openair1/SIMULATION/TOOLS/DOC/channel_simulation.md
- openair1/SIMULATION/TOOLS/random_channel.c
- ci-scripts/conf_files/channelmod_rfsimu.conf

---

### Finding 4.1 — Q1: Available Channel Models (InF Is NOT Present)

From the switch statement in random_channel.c new_channel_desc_scm():

| Config type string | Status | Characteristics |
|---|---|---|
| AWGN | Supported | No multipath, pure noise |
| TDL_A | Supported | 300 ns DS, 23 paths, NLOS |
| TDL_B | Supported | 100 ns DS, 23 paths, NLOS |
| TDL_C | Supported | 300 ns DS, 24 paths, NLOS |
| TDL_D | Supported | 30 ns DS, 23 paths, LoS dominant (Ricean) |
| TDL_E | Supported | 100 ns DS, 23 paths, LoS dominant (Ricean) |
| EPA | Supported | 7 taps, LTE Extended Pedestrian A |
| SCM_C | Supported | 18 taps, urban macro |
| SCM_A, SCM_B | Not supported | LOG_W: "channel model not yet supported" |
| InF-SH, InF-DH | Not present | Not in codebase at all |

InF (Indoor Factory from TR 38.901) is not implemented. No InF case in the
switch statement and no channelmod_names entry for it.

Recommended approximations for IA-P5G:

| Device type | Recommended model | Rationale |
|---|---|---|
| Fixed sensors, cameras | TDL_A (ds_tdl=30e-9) | Static, light clutter |
| AGVs, wheeled robots | TDL_C (ds_tdl=300e-9) | NLOS, heavy factory reflections |
| Drones, elevated UEs | TDL_D (ds_tdl=30e-9) | LoS likely, Ricean channel |

TDL-C is the closest published approximation to InF-SH (dense clutter, high
BS) in terms of delay spread and power delay profile. The ds_tdl config
parameter scales delay spread directly, allowing fine-tuning toward InF
characteristics. ds_tdl=300e-9 matches the InF-SH RMS delay spread.

---

### Finding 4.2 — Q2: Per-UE Channel Models — YES, Fully Supported

From channel_simulation.md:
> "Use rfsimu_channel_ue1, rfsimu_channel_ue2, etc. if you want to use
> different channel models for each client. The client connection order
> determines its channel model."

From simulator.cpp:
```c
ptr->channel_model = find_channel_desc_fromname(modelname);
if (!ptr->channel_model) {
  // fall back to legacy name rfsimu_channel_ue0
  const char *legacy_model_name = "rfsimu_channel_ue0";
  ptr->channel_model = find_channel_desc_fromname(legacy_model_name);
}
```

Naming convention:
- gNB receive path (UL): rfsimu_channel_enB0
- N-th UE to connect (0-indexed): rfsimu_channel_ueN

Each entry in the modellist array maps to a connection by position. If
rfsimu_channel_ueN is not defined, the UE falls back to rfsimu_channel_ue0.
For factory_robots with 10 heterogeneous UEs, define 10 entries (ue0-ue9)
with the appropriate model per device type.

---

### Finding 4.3 — Q3: Mobility / Doppler — NOT Config-Controllable

new_channel_desc_scm() has a maxDoppler parameter (in Hz), but it is
hardcoded in the telnet setmodel path:

```c
// From simulator.cpp rfsimu setmodel handler:
channel_desc_t *newmodel = new_channel_desc_scm(
    t->tx_num_channels, t->rx_num_channels,
    static_cast<SCM_t>(channelmod),
    t->sample_rate, t->rx_freq, t->tx_bw,
    30e-9,   // DS_TDL — hardcoded
    0.0,     // maxDoppler — hardcoded to zero
    ...
```

The channelmod config file schema has no velocity or maxDoppler field.
The telnet channelmod modify command supports: riceanf, aoa, randaoa,
ploss, noise_power_dB, offset, forgetf — no Doppler parameter.

Practical workaround: forgetfact as a mobility proxy.

The forgetting factor controls how fast the channel changes between IQ blocks:
- forgetfact = 1.0: channel generated once, held constant (fully static)
- forgetfact = 0.0: channel regenerated on every call (maximum variation)
- Intermediate values: gradual temporal evolution

Recommended forgetfact mapping for IA-P5G:

| Device | Velocity | forgetfact |
|---|---|---|
| Fixed sensor / camera | 0 km/h | 1.0 |
| AGV / wheeled robot | 3 km/h | 0.99 |
| Drone | 10 km/h | 0.95 |

This is not a physically accurate Doppler model but provides the correct
qualitative behaviour for scheduler benchmarking: fast-moving UEs see
more channel variation, driving more frequent MCS adaptation events.

For Stage 2+ if accurate Doppler is required: a single change in
load_channellist() in random_channel.c to read maxDoppler from the config
file exposes the parameter without architectural impact.

---

### Finding 4.4 — Q4: UE Count Ceiling

Hard ceiling from simulator.cpp:
```c
#define MAX_FD_RFSIMU 250   // buffer array size
```

This is the hard ceiling — 250 concurrent connections. Irrelevant for 10 UEs.

Architecture: gNB is TCP server, UEs are TCP clients. IQ exchange per slot
over TCP. gNB uses epoll to manage all connections non-blocking in one loop.

From README.md:
> "It can run faster than real-time if there is enough CPU, or slower
> (it is CPU-bound instead of real-time RF sampling-bound)."

The simulator is explicitly NOT hard real-time. With 10 UEs + AWGN or light
TDL models on a modern workstation, it will run at or above real-time. With
heavy TDL-C on all 10 UEs it may run below real-time (60s scenario takes
longer in wall clock) — but this does not affect correctness. Scheduler
behaviour is identical regardless of wall-clock speed.

The reference nrue.uicc.conf already contains 10 entries (uicc0-uicc9),
confirming OAI's own reference setup supports exactly the factory_robots
scenario size. Confirmed: 10 UEs is well within limits.

---

### Finding 4.5 — Q5: Reproducibility — No Seed, Use forgetfact=1.0

No seed parameter exists in the config file, CLI options, or telnet interface.
Channel tap realizations are drawn from the C RNG at startup with no
user-controlled seed.

Mitigation: forgetfact = 1.0

With forgetfact=1.0, the channel is initialized once at startup and held
constant for the entire run. The initial realization is still random between
runs, but the comparison within a run (PF vs TwoTier) is perfectly fair since
both schedulers see the same channel.

Across runs, channel variation is absorbed by the 5-run reproducibility
strategy (D2) with median +/- IQR reporting.

For controlled SNR targeting: use the telnet interface at the start of each
run to set a consistent pathloss:
```bash
channelmod modify 0 ploss 10     # set path loss to 10 dB
channelmod modify 0 noise_power_dB -5
```
This can be scripted from the harness to ensure comparable SNR across runs.

---

### Finding 4.6 — Channel Config Architecture

Channel models are included in the gNB and UE configs via:
```
@include "channelmod_rfsimu.conf"
```
at the end of both gnb and nrue config files. The chanmod option must
also be enabled at the command line:
```
--rfsimulator.[0].options chanmod
```

The modellist is selected at startup:
```
--channelmod.modellist modellist_ia_p5g
```

Individual model parameters can be changed at runtime via the telnet server
(--telnetsrv flag required). This is useful for SNR tuning between runs
without restarting the gNB.

---

### Cluster 4 — Scenario Channel Model Config

Complete channelmod_rfsimu.conf structure for factory_robots (10 UEs).
For Stage 1 baseline, AWGN for all UEs isolates scheduler behaviour from
channel effects and matches the Python simulator's static SNR assumption.

Stage 1 (AWGN, isolate scheduler effects):
```
channelmod = {
  max_chan = 15;
  modellist = "modellist_stage1_awgn";
  modellist_stage1_awgn = (
    { model_name = "rfsimu_channel_enB0"; type = "AWGN";
      ploss_dB = 0; noise_power_dB = -20; forgetfact = 1.0;
      offset = 0; ds_tdl = 0; },
    { model_name = "rfsimu_channel_ue0"; type = "AWGN";
      ploss_dB = 0; noise_power_dB = 0; forgetfact = 1.0;
      offset = 0; ds_tdl = 0; },
    # repeat for ue1..ue9 with scenario-appropriate noise_power_dB
    # to reflect different SNR per UE type
  );
};
```

Stage 2 (realistic models, per device type):
```
channelmod = {
  max_chan = 15;
  modellist = "modellist_stage2_factory";
  modellist_stage2_factory = (
    { model_name = "rfsimu_channel_enB0"; type = "AWGN";
      ploss_dB = 0; noise_power_dB = -20; forgetfact = 1.0;
      offset = 0; ds_tdl = 0; },
    # UE 0-1: robots (motion controller + camera, static NLOS)
    { model_name = "rfsimu_channel_ue0"; type = "TDL_C";
      ploss_dB = 0; noise_power_dB = 0; forgetfact = 1.0;
      offset = 0; ds_tdl = 300e-9; },
    # UE 2-3: AGVs (slow NLOS)
    { model_name = "rfsimu_channel_ue2"; type = "TDL_C";
      ploss_dB = 0; noise_power_dB = 0; forgetfact = 0.99;
      offset = 0; ds_tdl = 300e-9; },
    # UE 4-5: drones (LoS, Ricean)
    { model_name = "rfsimu_channel_ue4"; type = "TDL_D";
      ploss_dB = 0; noise_power_dB = 0; forgetfact = 0.95;
      offset = 0; ds_tdl = 30e-9; },
    # UE 6-9: sensors/cameras (static)
    { model_name = "rfsimu_channel_ue6"; type = "TDL_A";
      ploss_dB = 0; noise_power_dB = 0; forgetfact = 1.0;
      offset = 0; ds_tdl = 30e-9; }
  );
};
```

---

### Cluster 4 — Summary

| Question | Answer |
|---|---|
| InF available? | No — TDL-C (NLOS factory) and TDL-D (LoS) as approximations |
| Per-UE models? | Yes — rfsimu_channel_ueN naming, connection-order assignment |
| Doppler configurable? | No — use forgetfact as proxy; add maxDoppler to config for Stage 2+ |
| UE count ceiling? | Hard limit 250; practical limit CPU. 10 UEs confirmed supported |
| Fixed seed? | No — use forgetfact=1.0 + telnet SNR control for reproducibility |

---

## Cluster 5 — Multi-UE Orchestration ✅

### Goal
Understand the reference multi-UE Docker setup, determine per-UE container
requirements, design IMSI/DNN assignment for five scenarios, and finalise
traffic injection architecture.

### Files Read
- ci-scripts/yaml_files/5g_rfsimulator_multiue/nrue.uicc.conf
- radio/rfsimulator/README.md (Cluster 4)

### Open Item
ci-scripts/yaml_files/5g_rfsimulator_multiue/docker-compose.yaml was not
uploaded. Needed before writing the production IA-P5G compose file to confirm
exact image tags, health check commands, volume mounts, and subnet assignments.

---

### Finding 5.1 — Q1: All UEs Run in a Single Process (Not Separate Containers)

nrue.uicc.conf confirms this directly: 10 uiccN blocks, 10 rfsimulator
entries, 10 RU entries — all in one config for one nr-uesoftmodem process.

```
uicc0 = { imsi = "208990100001100"; pdu_sessions = ({dnn="oai";}); }
...
uicc9 = { imsi = "208990100001109"; pdu_sessions = ({dnn="oai";}); }
thread-pool: "-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1"   # 12 threads
rfsimulator = ( { serveraddr = "192.168.71.140"; }, ... x10 );
RUs = ( { nb_tx=1; nb_rx=1; }, ... x10 );
```

ONE container, ONE process, 10 virtual UEs. The 12-thread pool provides
concurrency for all 10 UE stacks. For IA-P5G, the entire factory_robots
scenario is one modified nrue.uicc.conf + one oai-nr-ue Docker service.

---

### Finding 5.2 — Q2: No Per-UE Port Assignment Needed

All 10 UEs connect to the same gNB at 192.168.71.140:4043 (default rfsimulator
port). The gNB epoll accepts all connections on one port, tracking each as a
separate buffer_t slot.

Connection order determines which rfsimu_channel_ueN model is assigned.
Since all 10 UEs start simultaneously in one process, order is nondeterministic.
For Stage 1 AWGN (all identical) this is irrelevant. For Stage 2 TDL models,
use the same model type for all UEs of the same device category.

---

### Finding 5.3 — Q3: Traffic Generation Runs Inside the UE Container

Each PDU session creates a TUN interface inside the container with the IP from
its DNN subnet. Interface naming follows oaitun_ueN. For multi-DNN UEs,
additional TUN interfaces are created per extra PDU session.

Verify exact naming at runtime:
```bash
ip addr show | grep oaitun
# e.g.: oaitun_ue0, oaitun_ue0_1, oaitun_ue0_2 for 3 PDU sessions on UE 0
```

Traffic injection from harness:
```bash
docker exec oai-nr-ue iperf3 -c <server> -B <tun_ip> -u -b 8M -t 60
docker exec oai-nr-ue iperf3 -s -B <tun_ip> -u &   # DL server
```

---

### Finding 5.4 — Q4: Single Docker Bridge Network Topology

```
demo-oai-public-net (bridge)
  ├── mysql
  ├── oai-nrf / oai-udr / oai-udm / oai-ausf
  ├── oai-amf / oai-smf / oai-upf
  ├── oai-gnb   (192.168.71.140, rfsimulator server on :4043)
  └── oai-nr-ue (all N UEs in one container; connects to gNB:4043)
```

GTP-U N3 tunnel between gNB and UPF runs on this same bridge. No MACVLAN
or host networking required for rfsimulator.

---

### Finding 5.5 — Startup Order and Readiness Gates

```
1. mysql       → DB healthcheck pass
2. Core NFs    → SBI /status HTTP 200 on each
3. oai-gnb     → "N2 SETUP COMPLETE" in log
4. oai-nr-ue   → all PDU session TUN IPs visible
```

Readiness gate (D7 from Cross-Cluster Decisions):
```bash
expected=$TOTAL_PDU_SESSIONS   # e.g. 28 for factory_robots
while [ $(ip addr show | grep "inet 10\." | wc -l) -lt $expected ]; do
  sleep 0.5
done
```

---

### Finding 5.6 — factory_robots nrue.uicc.conf Template

```
# UEs 0-3: HD-camera robots (UL GBR camera + DL control)
uicc0 = {
  imsi = "208990100001100";
  key  = "fec86ba6eb707ed08905757b1bb44b8f";
  opc  = "C42449363BBAD02B66D16BC975D77CC1";
  pdu_sessions = (
    { dnn = "urllc-ctrl"; nssai_sst = 1; },   # DL control (5QI=82) -- first = fiveQI on candidate
    { dnn = "gbr-video";  nssai_sst = 1; }    # UL camera  (5QI=2)
  );
}
# uicc1-3: identical structure, IMSI 208990100001101-208990100001103

# UEs 4-6: LIDAR+camera robots (higher bitrate)
uicc4 = {
  imsi = "208990100001104"; key = ...; opc = ...;
  pdu_sessions = (
    { dnn = "urllc-ctrl"; nssai_sst = 1; },
    { dnn = "gbr-video";  nssai_sst = 1; }
  );
}
# uicc5-6: identical, IMSI 208990100001105-208990100001106

# UEs 7-8: Multi-flow robots (UL GBR + UL best-effort + DL control)
uicc7 = {
  imsi = "208990100001107"; key = ...; opc = ...;
  pdu_sessions = (
    { dnn = "urllc-ctrl"; nssai_sst = 1; },
    { dnn = "gbr-video";  nssai_sst = 1; },
    { dnn = "oai";        nssai_sst = 1; }    # UL best-effort (5QI=9)
  );
}
# uicc8: identical, IMSI 208990100001108

# UE 9: Asymmetric TCP robot (4 PDU sessions)
uicc9 = {
  imsi = "208990100001109"; key = ...; opc = ...;
  pdu_sessions = (
    { dnn = "urllc-ctrl"; nssai_sst = 1; },
    { dnn = "gbr-video";  nssai_sst = 1; },
    { dnn = "oai";        nssai_sst = 1; },   # DL bulk (5QI=9)
    { dnn = "be-bulk";    nssai_sst = 1; }    # UL TCP ACKs (5QI=8)
  );
}

thread-pool: "-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1"

rfsimulator = (
  { serveraddr = "192.168.71.140"; }, { serveraddr = "192.168.71.140"; },
  { serveraddr = "192.168.71.140"; }, { serveraddr = "192.168.71.140"; },
  { serveraddr = "192.168.71.140"; }, { serveraddr = "192.168.71.140"; },
  { serveraddr = "192.168.71.140"; }, { serveraddr = "192.168.71.140"; },
  { serveraddr = "192.168.71.140"; }, { serveraddr = "192.168.71.140"; }
);

RUs = (
  { nb_tx=1; nb_rx=1; }, { nb_tx=1; nb_rx=1; }, { nb_tx=1; nb_rx=1; },
  { nb_tx=1; nb_rx=1; }, { nb_tx=1; nb_rx=1; }, { nb_tx=1; nb_rx=1; },
  { nb_tx=1; nb_rx=1; }, { nb_tx=1; nb_rx=1; }, { nb_tx=1; nb_rx=1; },
  { nb_tx=1; nb_rx=1; }
);
```

---

### Scenario PDU Session Count Reference

| Scenario | UEs | Max PDU sessions/UE | Total TUN interfaces |
|---|---|---|---|
| smoke | 3 | 1 | 3 |
| overload | 5 | 1 | 5 |
| vision | 6 | 1 | 6 |
| sensor_dense | 8 | 1 | 8 |
| factory_robots | 10 | 4 (UE 9) | 28 |

---

### Cluster 5 — Summary

| Question | Answer |
|---|---|
| Separate container per UE? | No — all UEs in ONE process, ONE container |
| Port assignment per UE? | Not needed — all connect to gNB:4043 |
| Traffic generation location? | Inside UE container; binds to oaitun_ueN TUN interfaces |
| Network topology? | Single Docker bridge; all components on same network |
| Multi-DNN UE support? | Yes — pdu_sessions array per uiccN |
| Startup order? | mysql → core NFs → gNB (N2 ready) → UE (all TUN IPs up) |

---

## Cross-Cluster Design Decisions

### D1 — Measurement Window and Warm-Up Period
- Discard-warmup: 10 s
- Measurement window: 60 s per scenario
- Reporting granularity: 1 s buckets (matching Tier-1 cadence)

### D2 — Reproducibility Strategy
- Minimum 5 runs per scenario
- Fixed seed: NOT supported in rfsimulator — use forgetfact=1.0 instead (Cluster 4)
- Report: median +/- IQR

### D3 — Baseline Scheduler Pinning
- Confirm dl_rb_alloc and ul_rb_alloc function pointer assignments in main.c
- Record git commit hash for all benchmark runs

### D4 — UE Capability Profiles

| UE Type | Max MCS | Antenna | Power class |
|---|---|---|---|
| Motion controller | 28 | 1T1R | PC3 |
| 4K camera / robot | 28 | 1T1R | PC3 |
| Sensor node | 16 | 1T1R | PC3 |
| AGV | 28 | 2T2R | PC3 |
| Drone | 28 | 1T1R | PC2 |

### D5 — UL Per-Flow 5QI Differentiation Not Possible at gNB MAC
UL lcid_alloc hook does not exist. UL QoS limited to per-UE PRB sizing
via ul_rb_alloc and PHR-based MCS adjustment. Known architectural limitation.

### D6 — GBR Values Not Propagated to MAC
NR_QoS_config_t holds only fiveQI + priority. Tier-1 LP must use TS 23.501
Table 5.7.4-1 standard default GBR values per 5QI class.

### D7 — Stage 1 Readiness Gate for Multi-PDU-Session UEs
```bash
expected=$N_PDU_SESSIONS
while [ $(ip addr show | grep "inet 10\." | wc -l) -lt $expected ]; do
  sleep 0.5
done
```

### D8 — T Tracer Must Be Started Before Traffic Injection
T tracer events are forwarded only to currently-connected csv processes.
Events are dropped if no consumer is connected. The harness must start all
csv processes and confirm socket connections before starting traffic injection.

---

## Stage 2 Integration Plan (Derived from Clusters 1-3)

```
Files to create:
  openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.c   <- three functions
  openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.h   <- declarations + Tier-1 shared struct

Files to modify:
  openair2/LAYER2/NR_MAC_gNB/main.c               <- 3-line registration
  config.yaml                                      <- add 3 DNNs (Cluster 2)
  nrue.uicc.conf (per scenario)                    <- multi-DNN pdu_sessions arrays
  common/utils/T/T_messages.txt                    <- add BSR + CQI event definitions
  openair2/LAYER2/NR_MAC_gNB/gNB_scheduler_ulsch.c <- add T_RECORD for BSR

Tier-1 integration:
  Separate pthread at ~1 s cadence
  Writes rate targets ri* into shared atomic struct
  ia_p5g_dl_rb_alloc reads targets each slot — no locks on fast path
  OSQP (libosqp) C API required — add to CMakeLists.txt

Function summary:
  ia_p5g_dl_rb_alloc()    Tier-2 DL core: virtual queue update -> PRB sizing
  ia_p5g_ul_rb_alloc()    Tier-2 UL core: virtual queue update -> PRB sizing
  ia_p5g_dl_lcid_alloc()  5QI-aware intra-UE byte mux via lc_config lookup

Stage 2 design debts:
  1. rb_alloc must derive effective priority from composite lc_config loop,
     not just candidate->fiveQI, for correct inter-UE ranking on multi-flow UEs
  2. BSR T_RECORD call needed for input validation
  3. DL CQI T_RECORD call needed for input validation
```

---

*Last updated: All five clusters complete. Reading phase done — ready for Stage 1 implementation.*
