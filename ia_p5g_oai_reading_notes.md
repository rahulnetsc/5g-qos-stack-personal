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
| 3 | Metrics Collection (T Tracer) | 🔲 Pending |
| 4 | rfsimulator + Channel Models | 🔲 Pending |
| 5 | Multi-UE Orchestration | 🔲 Pending |

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
Stage 5  MCS Selection           pluggable  ← MCS set HERE, before Stage 6
Stage 6  RB Allocation           pluggable  ← TwoTier Tier-2 goes HERE
Stage 7  Dispatch                fixed
Stage 8  Per-LCID Byte Alloc     pluggable, DL only  ← 5QI-aware mux goes HERE
```

---

### Finding 1.2 — The Three Hook Points for IA-P5G

**Three functions to write. Three lines to register.**

#### DL RB Allocation (replaces `nr_dl_proportional_fair`)

```c
typedef int (*nr_dl_rb_alloc_fn)(const nr_dl_sched_params_t *params,
                                  nr_dl_candidate_t *candidates,
                                  int n_candidates);
// Registration in main.c:
RC.nrmac[i]->dl_rb_alloc = ia_p5g_dl_rb_alloc;
```

#### UL RB Allocation (replaces `nr_ul_proportional_fair`)

```c
typedef int (*nr_ul_rb_alloc_fn)(const nr_ul_sched_params_t *params,
                                  nr_ul_candidate_t *candidates,
                                  int n_candidates);
// Registration in main.c:
RC.nrmac[i]->ul_rb_alloc = ia_p5g_ul_rb_alloc;
```

#### DL Per-LCID Byte Allocation (replaces `nr_dl_lcid_alloc_default`)

```c
typedef void (*nr_dl_lcid_alloc_fn)(const gNB_MAC_INST *mac,
                                     const nr_dl_candidate_t *candidate,
                                     int tbs_available,
                                     int lcid_alloc[NR_MAX_NUM_LCID]);
// Registration in main.c:
RC.nrmac[i]->dl_lcid_alloc = ia_p5g_dl_lcid_alloc;
```

> **Note:** There is no UL equivalent of `lcid_alloc`. UL logical channel muxing
> is handled autonomously by the UE's MAC entity (LCP procedure, TS 38.321).

---

### Finding 1.3 — Complete Tier-2 Input Map

#### DL Candidate (`nr_dl_candidate_t`)

| Field | Type | Staleness | Tier-2 use |
|---|---|---|---|
| `pending_bytes` | `uint32_t` | Fresh every slot | Buffer depth Bᵢ |
| `pending_bytes_per_lcid[NR_MAX_NUM_LCID]` | `uint32_t[]` | Fresh every slot | Per-flow buffer depth (lcid_alloc) |
| `bler` | `float` | 50 ms window | BLER feedback |
| `bler_updated` | `bool` | Per-frame flag | **Staleness guard** — check before using `bler` |
| `avg_throughput` | `float` bps EWMA | Continuous | Throughput tracker, PF denominator |
| `current_mcs` | `int` | Set at collect | Held MCS for efficiency ηᵢ computation |
| `sched_pdsch.mcs` | `uint8_t` | Set by Stage 5 | MCS for TBS calc — already set when rb_alloc runs |
| `max_mcs` | `int` | Config + UE cap | Hard ceiling — never exceed |
| `fiveQI` | `uint64_t` | Set at attach | 5QI of **first DRB only** — see Finding 1.5 |
| `priority` | `int` | Set at attach | LC priority of first DRB (lower = higher priority) |
| `nssai` | `nssai_t` | Set at attach | Slice identity |
| `cqi` | `uint16_t` | CSI report period | Channel quality; held-last-value between reports |
| `csi_ri` | `uint8_t` | CSI report period | Rank indicator |
| `is_retx` | `bool` | Fresh | Must handle before new data |
| `retx_rbSize` | `int` | Fresh | Exact PRBs required for retx |
| `bwp_start` / `bwp_size` | `int` | Set at attach | BWP geometry for PRB indexing |

#### UL Candidate (`nr_ul_candidate_t`) — same fields plus:

| Field | Type | Staleness | Tier-2 use |
|---|---|---|---|
| `ph` | `int` | PHR event-driven | Power headroom — use `nr_ul_phr_advice_t` pattern |
| `pcmax` | `int` | Set at attach | Max configured TX power |
| `snrx10` | `int` | PUSCH measurement | SINR×10; used for SINR-based MCS override path |
| `sched_inactive` | `bool` | Fresh | Must give minimum grant if true |

---

### Finding 1.4 — MCS Is Pre-Set; Tier-2 Only Refines Downward

MCS is selected at **Stage 5** (`mcs_select`) before `rb_alloc` (Stage 6) runs.
`COMMIT_ALLOC` is a macro (not a function) that atomically writes `rbStart`,
`rbSize`, `mcs` onto the candidate, validates CCE assignment, marks the VRB map,
and sets `cand->scheduled = true`. Never mark the VRB map manually.

TBS utility: `nr_find_nb_rb()` in `gNB_scheduler_primitives.c` — given target
bytes, returns minimum `rbSize`.

---

### Finding 1.5 — LCID→5QI Mapping: Already in OAI, No New Fields Needed

OAI already stores per-LCID QoS configuration in `NR_UE_sched_ctrl_t`:

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

Access path from inside `lcid_alloc`: `candidate->UE->UE_sched_ctrl.lc_config`

Populated by `handle_ue_context_drbs_setup()` in `mac_rrc_dl_handler.c:291`
at DRB setup time. Static from the scheduler's perspective — read-only.

---

### Finding 1.6 — Default PF Behaviour (Baseline)

`nr_dl_proportional_fair` runs three phases per slot:
1. Retransmissions first — exact `retx_rbSize` PRBs
2. No-data UEs — minimum grant (5 PRBs) for MAC CEs only
3. New data — sort by `pending_bytes / avg_throughput` (PF weight), greedy

No flow awareness, no GBR, no PDB. TwoTier replaces phase 3 only.

---

### Finding 1.7 — Tunable Config Parameters

From `mac-usage.md`, key `MACRLCs` knobs:

| Parameter | Default | IA-P5G note |
|---|---|---|
| `dl_bler_target_upper` | 0.15 | Lower for URLLC flows (5QI=2, 5QI=82) |
| `dl_bler_target_lower` | 0.05 | — |
| `ulsch_max_frame_inactivity` | 10 frames (100 ms) | Lower for sensor_dense |
| `dl_harq_round_max` | 4 | Consider 2 for PDB=10 ms flows |
| `ul_harq_round_max` | 4 | Same |

---

### Cluster 1 — Open Items

- [ ] Confirm `seq_arr_at()` macro/function signature for iterating `lc_config`
- [ ] Verify `NR_MAX_NUM_QFI` value — max QFIs a single LCID can carry
- [ ] Check whether `fiveQI` on the candidate is populated from
      `lc_config[0].qos_config[0].fiveQI` at collect time or derived elsewhere

---

## Cluster 2 — QoS Flow Chain (5QI → DRB → MAC) ✅

### Goal
Understand the full end-to-end QoS path from PDU session establishment in the
core to the MAC scheduler. Determine the correct flow classification mechanism
for multi-flow UEs across all five scenarios.

### Files Read
- `openairinterface5g/doc/tutorial_resources/oai-cn5g/conf/config.yaml`
- `ci-scripts/oai-cn5g/database/oai_db.sql`
- `openair2/LAYER2/SDAP/nr_sdap/nr_sdap_entity.c`
- `openair2/LAYER2/SDAP/nr_sdap/nr_sdap.c`
- `openair2/LAYER2/NR_MAC_gNB/mac_rrc_dl_handler.c`
- `ci-scripts/yaml_files/5g_rfsimulator_multiue/nrue.uicc.conf`
- `ci-scripts/conf_files/gnb.sa.band78.106prb.rfsim.yaml`
- `grep` of `pdu_sessions` in `openair3/NAS/NR_UE/nr_nas_msg.c` and
  `openair2/RRC/NR/`

---

### Finding 2.1 — Corrected 3GPP QoS Architecture

The actual 5G QoS classification chain (not the simplified DSCP model):

**Control Plane — PDU session establishment:**
```
UE → AMF → SMF
              ├── UDR (subscription QoS profile per IMSI)
              ├── PCF (PCC rules / SDF filter templates)
              ├── UPF via N4 PFCP Session Establishment:
              │     PDR  (Packet Detection Rule — SDF filter → QFI assignment)
              │     QER  (QoS Enforcement Rule — GBR/MBR token bucket)
              │     FAR  (Forwarding Action Rule — GTP-U encapsulation + TEID)
              └── gNB via N2/NGAP PDU Session Resource Setup:
                    QFI list, 5QI, ARP, GBR, MBR per flow
```

**Downlink data path:**
```
App server → UPF N6 → PDR match (SDF filter) → QER (rate enforce)
→ FAR (GTP-U encapsulate, QFI in PDU Session Container ext header)
→ gNB N3 → SDAP reads QFI from GTP-U ext header
→ qfi2drb_table[QFI] → DRB → LCID
→ MAC: lc_config[lcid].fiveQI available for scheduler
```

**Uplink data path:**
```
UE NAS QoS rule match → SDAP prepends SDAP header (QFI field)
→ PDCP → RLC → MAC (UE side)
→ gNB SDAP RX: reads QFI from SDAP header
→ GTP-U encapsulate with QFI → UPF N3 → QER → N6
```

**Key corrections vs. earlier simplified model:**
- QFI is assigned by the PDR at the UPF, not derived from DSCP
- QER handles rate enforcement; FAR handles GTP-U encapsulation (separate rules)
- N4 Session Establishment Request must precede rule installation at UPF
- UE generates SDAP header (not GTP-U header) on the radio side; gNB generates GTP-U
- Reflective QoS (RDI bit in SDAP DL header) is implemented in OAI SDAP but not needed
  for IA-P5G (static private network with known flows)

---

### Finding 2.2 — OAI CN5G Bypasses UDM/PCF

From `config.yaml`:
```yaml
smf:
  support_features:
    use_local_subscription_info: yes   # reads local_subscription_infos, not UDM
    use_local_pcc_rules: yes           # reads local_pcc_rules, not PCF
```

The SMF uses its own config file as the source of truth. The UDM/UDR containers
run but are not consulted for QoS decisions in this deployment mode.

---

### Finding 2.3 — Default Config Has Only 5QI=9 (Best-Effort)

The entire `local_subscription_infos` block in the reference config:
```yaml
local_subscription_infos:
  - single_nssai: *embb_slice
    dnn: "oai"
    qos_profile:
      5qi: 9
      session_ambr_ul: "10Gbps"
      session_ambr_dl: "10Gbps"
  # identical entries for "openairinterface", "ims", "default"
```

Every DNN gets 5QI=9, unlimited AMBR, no GBR. One QoS flow per PDU session.
**All traffic is best-effort out of the box.** This is the unmodified baseline.

---

### Finding 2.4 — `local_pcc_rules` Block Does Not Exist

```bash
grep -A 30 "local_pcc_rules" config.yaml
# Returns: only the flag line, no data block follows
```

`use_local_pcc_rules: yes` is set but no `local_pcc_rules:` data block is
defined anywhere in the file. Port-based SDF filter classification on a single
PDU session is not available through config alone. Implementing it would require
finding the OAI SMF parser for this field and writing filter entries with no
reference example.

---

### Finding 2.5 — `oai_db.sql` Is a 4G EPC Database (Irrelevant)

The SQL file contains 4G constructs: `mmeidentity`, `pdn` (with `qci` column,
not `5qi`), `pgw`, `users`. All `qci=9`. This database is not used by OAI CN5G's
5G core. The active subscriber data is managed via `local_subscription_infos` in
`config.yaml` when `use_local_subscription_info: yes`.

---

### Finding 2.6 — SDAP QFI→DRB Mapping Is Correct and Complete

`nr_sdap_entity.c` confirms:
- `qfi2drb_table[SDAP_MAX_QFI]` per SDAP entity (one entity per PDU session)
- `nr_sdap_qfi2drb()` maps QFI → DRB, falls back to `default_drb` if no rule
- DL TX: gNB prepends SDAP header with QFI before sending to PDCP
- UL RX: gNB reads QFI from SDAP header, forwards to GTP-U via
  `gtpv1uSendDirectWithQFI()` with QFI in PDU Session Container extension header
- Reflective QoS implemented (RDI path) — not needed for IA-P5G

---

### Finding 2.7 — GBR Values Do NOT Reach the MAC

`mac_rrc_dl_handler.c` — `handle_ue_context_drbs_setup()`:
```c
nr_lc_config_t c = {.lcid = ..., .nssai = drb->nr.nssai};
for (int q = 0; q < drb->nr.flows_len; ++q) {
  c.qos_config[q] = get_qos_config(&drb->nr.flows[q].param);  // fiveQI + priority only
  prio = min(prio, c.qos_config[q].priority);
}
nr_mac_add_lcid(&UE->UE_sched_ctrl, &c);
```

`NR_QoS_config_t` contains only `fiveQI` and `priority`. GBR/MBR/GFBR/MFBR
values are not propagated to the MAC. **Tier-1's LP must use 5QI standard
defaults from TS 23.501 Table 5.7.4-1, not actual negotiated values.**
Document as a known limitation.

---

### Finding 2.8 — 5QI→Priority Mapping Is Hardcoded in OAI

From `mac_rrc_dl_handler.c`:
```c
const uint64_t qos_fiveqi[26]   = {1, 2, 3, 4, 65, 66, 67, 71, 72, 73, 74,
                                    76, 5, 6, 7, 8, 9, 69, 70, 79, 80, 82,
                                    83, 84, 85, 86};
const uint64_t qos_priority[26] = {20, 40, 30, 50, 7, 20, 15, 56, 56, 56, 56,
                                    56, 10, 60, 70, 80, 90, 5, 55, 65, 68, 19,
                                    22, 24, 21, 18};
```

Derived from 3GPP TS 23.501 Table 5.7.4-1. **If a 5QI value not in this list
is configured, `get_non_dynamic_priority()` calls `AssertFatal` and crashes
the gNB.** All 5QI values used in IA-P5G scenarios must appear in this array.

Verified 5QIs for IA-P5G scenarios:

| Python QFI | Semantics | Chosen 5QI | In OAI table? | Priority | PDB |
|---|---|---|---|---|---|
| 2 | UL GBR camera/LIDAR | **2** | ✅ | 40 | 150 ms |
| 82 | DL control loop 10 ms | **82** | ✅ | 19 | 10 ms |
| 9 | Best-effort | **9** | ✅ | 90 | 300 ms |
| 8 | TCP ACKs / bulk | **8** | ✅ | 80 | 300 ms |
| 1 | DL interactive 12 ms | **82** (not 1) | ✅ | 19 | 10 ms |

> **Note:** Python QFI=1 (latency_bound scenario, 12 ms PDB) must map to **5QI=82**,
> not 5QI=1. 5QI=1 is VoNR (100 ms PDB) — wrong for motion control. Using 5QI=82
> gives PDB=10 ms and priority=19, which is correct.

---

### Finding 2.9 — RLC Mode Is CU-Controlled via F1AP

From `mac_rrc_dl_handler.c`:
```c
const NR_RLC_Config_PR rlc_conf = drb->rlc_mode == F1AP_RLC_MODE_AM
    ? NR_RLC_Config_PR_am
    : NR_RLC_Config_PR_um_Bi_Directional;
```

RLC mode (AM/UM) comes from the F1AP UE Context Setup message, set by the CU/RRC.
Not directly configurable from the gNB config file — it is determined by the RRC
reconfiguration logic. For URLLC flows with tight PDB, UM is preferred (no retx
overhead). This may require RRC-level tuning in a later phase.

**Also noted:** `long priority = 13; // hardcoded for the moment` in
`get_bearerconfig_from_drb()` — the RLC bearer config priority is hardcoded to 13
for all DRBs. This is distinct from `lc_config.priority` (which is correctly set
from the 5QI lookup) and only affects the RLC layer, not the MAC scheduler.

---

### Finding 2.10 — gNB Config Has No QoS Stanzas

`gnb.sa.band78.106prb.rfsim.yaml` `MACRLCs` block:
```yaml
MACRLCs:
  - tr_s_preference: local_L1
    tr_n_preference: local_RRC
    pusch_TargetSNRx10: 200
    pucch_TargetSNRx10: 200
    stats_max_ue: 17
```

No QoS parameters. All DRB/5QI configuration comes dynamically via RRC/F1AP.
One SNSSAI: `sst=1, sd=0xffffff`. All scheduler knobs at defaults for Stage 1.

---

### Finding 2.11 — Multi-PDU Session Establishment Is Batch, Not Sequential

From `grep` of `pdu_sessions` in NAS/RRC/NGAP code:

- **`nr_nas_msg.c:2047`**: Initial attach loops over ALL `pdu_sessions` array
  entries and sends establishment requests for all in one pass.
- **`rrc_gNB.c`**: gNB RRC allocates `calloc(num_pdu_sessions, ...)` — handles
  all sessions as a batch in a single request structure.
- **`rrc_gNB_NGAP.c`**: NGAP PDU Session Resource Setup Response carries an array
  (`resp->pdusessions[]`, `resp->nb_of_pdusessions`) — multiple sessions in one
  NGAP exchange.
- **`nr_nas_msg.c:1704`**: Individual per-session response handler (Accept/Reject)
  called as each network response arrives.

**Conclusion:** All PDU sessions in the `pdu_sessions` array are established as a
batch at initial attach. All sessions are up before the UE completes registration.
Session setup order follows config array order, which determines DRB/LCID numbering.

---

### Finding 2.12 — DNN-Based Separation Is the Correct Implementation Path

Since `local_pcc_rules` has no defined block (Finding 2.4), port-based SDF filter
classification within a single PDU session is not available through config.
The correct approach for IA-P5G is **DNN-based PDU session separation**:
one PDU session per traffic class per UE, each on a distinct DNN.

**Why this is architecturally correct for a private network:**
- Each PDU session gets its own GTP-U tunnel, SDAP entity, DRB, and LCID
- IP subnet per DNN provides automatic DL routing without SDF filters
- No ambiguity about packet-to-flow assignment
- Fully supported by OAI `nr-uesoftmodem` (`pdu_sessions` is an array)

#### Required DNN Set

| DNN | 5QI | Priority | Use |
|---|---|---|---|
| `oai` | 9 | 90 | Best-effort (already exists) |
| `gbr-video` | 2 | 40 | UL GBR camera/LIDAR streams |
| `urllc-ctrl` | 82 | 19 | DL/UL control loops (PDB 10 ms) |
| `be-bulk` | 8 | 80 | TCP ACKs, bulk transfers |

#### Required `config.yaml` Additions

```yaml
# Add to local_subscription_infos:
- single_nssai: *embb_slice
  dnn: "gbr-video"
  qos_profile:
    5qi: 2
    session_ambr_ul: "50Mbps"
    session_ambr_dl: "50Mbps"

- single_nssai: *embb_slice
  dnn: "urllc-ctrl"
  qos_profile:
    5qi: 82
    session_ambr_ul: "10Mbps"
    session_ambr_dl: "10Mbps"

- single_nssai: *embb_slice
  dnn: "be-bulk"
  qos_profile:
    5qi: 8
    session_ambr_ul: "100Mbps"
    session_ambr_dl: "100Mbps"

# Add to dnns:
- dnn: "gbr-video"
  pdu_session_type: "IPV4"
  ipv4_subnet: "10.0.2.0/24"

- dnn: "urllc-ctrl"
  pdu_session_type: "IPV4"
  ipv4_subnet: "10.0.3.0/24"

- dnn: "be-bulk"
  pdu_session_type: "IPV4"
  ipv4_subnet: "10.0.4.0/24"

# Add same DNNs to smf_info.dnnSmfInfoList and upf_info.dnnUpfInfoList
```

#### Per-UE `pdu_sessions` Convention

**Ordering rule:** put the highest-priority (lowest 3GPP priority number) DNN first.
This ensures `candidate->fiveQI` reflects the most time-sensitive flow.

Example — factory_robots UE 8 (3 flows: UL GBR camera + UL best-effort + DL control):
```
uicc7 = {
  imsi = "208990100001107";
  key  = "fec86ba6eb707ed08905757b1bb44b8f";
  opc  = "C42449363BBAD02B66D16BC975D77CC1";
  pdu_sessions = (
    { dnn = "urllc-ctrl"; nssai_sst = 1; },   # 5QI=82, priority=19 → fiveQI on candidate
    { dnn = "gbr-video";  nssai_sst = 1; },   # 5QI=2,  priority=40
    { dnn = "oai";        nssai_sst = 1; }    # 5QI=9,  priority=90
  );
};
```

Example — factory_robots UE 10 (4 flows: UL GBR camera + DL PF bulk + UL ACKs + DL control):
```
uicc9 = {
  imsi = "208990100001109";
  key  = "fec86ba6eb707ed08905757b1bb44b8f";
  opc  = "C42449363BBAD02B66D16BC975D77CC1";
  pdu_sessions = (
    { dnn = "urllc-ctrl"; nssai_sst = 1; },   # DL control loop (5QI=82)
    { dnn = "gbr-video";  nssai_sst = 1; },   # UL camera (5QI=2)
    { dnn = "oai";        nssai_sst = 1; },   # DL bulk download (5QI=9)
    { dnn = "be-bulk";    nssai_sst = 1; }    # UL TCP ACKs (5QI=8)
  );
};
```

---

### Finding 2.13 — Traffic Generator Binding Strategy

Each PDU session comes up on a distinct TUN interface with a distinct IP from its
DNN subnet. The harness script must:

1. After UE attach, query assigned IPs:
   ```bash
   ip addr show | grep "inet 10\."
   # Expect N IPs for N PDU sessions
   ```
2. Build a map: IP subnet → DNN → traffic profile → iperf3 bind address
3. Launch per-flow traffic generators:
   ```bash
   # UL GBR camera (binds to gbr-video subnet IP, e.g. 10.0.2.x)
   iperf3 -c <server_ip> -B 10.0.2.<ue_x> -u -b 8M -l 33000 -t 60

   # DL control loop (server listens on urllc-ctrl subnet IP)
   iperf3 -s -B 10.0.3.<ue_x> -u &
   # External client sends 40 bytes every 5ms:
   iperf3 -c 10.0.3.<ue_x> -u -b 64k -l 40 -t 60

   # UL best-effort (binds to oai subnet IP)
   iperf3 -c <server_ip> -B 10.0.0.<ue_x> -u -b 10M -t 60
   ```

**Readiness gate for harness:**
```bash
# Wait until all N PDU sessions have an assigned IP before starting traffic
expected_sessions=3   # per-UE-type constant
while [ $(ip addr show | grep "inet 10\." | wc -l) -lt $expected_sessions ]; do
  sleep 0.5
done
```

---

### Cluster 2 — Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| GBR/MBR not propagated to MAC | Tier-1 LP uses 5QI standard defaults, not negotiated rates | Use TS 23.501 Table 5.7.4-1 default GBR values per 5QI |
| `candidate->fiveQI` = first DRB only | Inter-UE priority in `rb_alloc` based on first session's 5QI | Stage 2: use composite priority from `lc_config` loop; Stage 1: ordering convention mitigates |
| RLC mode not directly configurable | AM/UM determined by CU RRC logic | Defer to Stage 3 (core QoS enforcement); verify empirically |
| UL per-flow 5QI differentiation not possible at gNB | UL scheduler sees per-UE BSR only, not per-flow | Known architectural limitation; document in report |
| `local_pcc_rules` SDF filters unsupported | Cannot do single-PDU-session multi-flow via port filters | DNN-based separation fully substitutes |

---

## Cluster 3 — Metrics Collection (T Tracer) 🔲

### Goal
Understand what the T tracer exposes natively per slot, identify gaps
(especially HoL delay and per-flow granularity), and design the metric
correlation strategy that aligns T tracer events with iperf3 and UDP probe
timestamps.

### Files to Read (Priority Order)

| File | What to look for |
|---|---|
| `common/utils/T/T_messages.txt` | **Event catalog** — grep for `MAC`, `SCHED`, `BSR`, `CQI`, `PHR`, `HARQ`, `BLER`, `DLSCH`, `ULSCH` |
| `common/utils/T/tracer/gnb_mac.c` | gNB MAC-specific tracer event handlers |
| `common/utils/T/tracer/csv.c` | CSV export format — can it be consumed directly? |
| `common/utils/T/tracer/throughputlog.c` | Throughput logging; time resolution; per-UE vs aggregate |
| `common/utils/T/tracer/ttilog.c` + `ticked_ttilog.c` | Per-TTI event logging — closest to per-slot granularity |
| `common/utils/T/local_tracer.c` | In-process tracer — useful for collecting without separate process |

### Key Questions to Answer

1. Is HoL delay a native T tracer event, or does it need custom instrumentation?
2. Are per-UE BSR, PHR, and CQI emitted as T events each slot, or only on change?
3. Is per-LCID throughput a native event or only per-UE aggregate?
4. What is the time reference in T tracer events — frame+slot index, wall clock,
   or both? This determines how to correlate with iperf3/UDP probe timestamps.
5. What is the output format of `csv.c` — line format, field names, delimiter?
6. Is there a binary-to-text conversion pipeline already provided, or does
   `local_tracer.c` write text directly?

### Key Design Decision Pending
The metric correlation problem: T tracer gives MAC-layer KPIs, iperf3 gives
application-layer throughput, and UDP probe gives HoL timestamps — all on
different time bases. A unified timestamping strategy must be designed before
the first benchmark run. This cluster is a blocker for Stage 1 harness scripts.

### Expected Deliverable from This Cluster
A per-slot metrics schema listing every KPI (throughput, latency, BLER, BSR,
CQI, PHR, PRB utilisation, per-flow breakdown) with its source (native T event
vs. custom instrumentation), granularity, and how it maps to the Python
simulator's output KPIs.

---

## Cluster 4 — rfsimulator + Channel Models 🔲

### Goal
Confirm which channel model profiles exist natively in OAI's rfsimulator,
identify whether the InF (Indoor Factory) model from TR 38.901 is available,
understand the per-UE channel configuration mechanism, and characterise the
maximum UE count before the timing loop degrades.

### Files to Read (Priority Order)

| File | What to look for |
|---|---|
| `radio/rfsimulator/README.md` | Architecture, multi-UE limits, IQ exchange mechanism |
| `radio/rfsimulator/apply_channelmod.c` | How channel models plug into the rfsim IQ path |
| `openair1/SIMULATION/TOOLS/DOC/channel_simulation.md` | Channel model reference — which TDL profiles (A/B/C/D/E) are defined |
| `openair1/SIMULATION/TOOLS/random_channel.c` | Channel profile struct definitions — grep for `TDL`, `CDL`, `InF`, `AWGN` |
| `openair1/SIMULATION/TOOLS/multipath_tv_channel.c` | Time-varying channel — relevant for mobile UEs (AGVs, drones) |
| `ci-scripts/conf_files/channelmod_rfsimu.conf` | Reference channel config file — syntax and available model names |

### Key Questions to Answer

1. Is there an `InF-SH` or `InF-DH` model defined in `random_channel.c`?
2. Can different UEs have different channel models simultaneously?
3. How is UE mobility (velocity, direction) specified per UE?
4. What is the empirical UE count ceiling before timing loop degrades?
5. Does rfsimulator support a fixed random seed for reproducibility?

### Key Design Decision Pending
If InF is not natively available, a TDL-C or TDL-D approximation must be
agreed before scenario configs are finalised.

### Expected Deliverable from This Cluster
A per-scenario channel model config table:
```
Scenario       UE Type        Channel Model    Velocity    Config File Entry
smoke          sensor         TDL-A / InF-SH   0 km/h      channelmod = ...
factory_robots AGV            TDL-C            3 km/h      channelmod = ...
factory_robots drone          TDL-D            10 km/h     channelmod = ...
```

---

## Cluster 5 — Multi-UE Orchestration 🔲

### Goal
Understand the reference multi-UE Docker setup, determine per-UE container
requirements, design IMSI/DNN assignment for five scenarios, and finalise
traffic injection architecture.

### Files to Read (Priority Order)

| File | What to look for |
|---|---|
| `doc/NR_SA_Tutorial_OAI_multi_UE.md` | Authoritative step-by-step multi-UE setup |
| `doc/NR_SA_Tutorial_OAI_nrUE.md` | Single-UE baseline — read before multi-UE |
| `ci-scripts/yaml_files/5g_rfsimulator_multiue/docker-compose.yaml` | Container structure, networking, rfsim port mapping |
| `ci-scripts/oai-cn5g/docker-compose.yaml` | Core network container topology |

### Key Questions to Answer

1. Does each UE require a separate container, or can multiple IMSIs batch?
2. How is rfsimulator port assignment handled per UE?
3. Where does traffic generation run — inside UE container or separate?
4. What is the recommended network topology for rfsimulator multi-UE?

### Scenario UE Count Reference

| Scenario | UEs | PDU Sessions (max per UE) |
|---|---|---|
| smoke | 3 | 1 |
| overload | 5 | 1 |
| vision | 6 | 1 |
| sensor_dense | 8 | 1 |
| factory_robots | 10 | 4 (UE 10) |

### Expected Deliverable from This Cluster
A `docker-compose.yaml` template for the factory_robots scenario (10 UEs)
with correct IMSI assignment, rfsim port mapping, and per-UE DNN config.

---

## Cross-Cluster Design Decisions

### D1 — Measurement Window and Warm-Up Period
- Discard-warmup: 10 s
- Measurement window: 60 s per scenario
- Reporting granularity: 1 s buckets (matching Tier-1 cadence)

### D2 — Reproducibility Strategy
- Minimum 5 runs per scenario
- Fixed seed if rfsim supports it (Cluster 4 to confirm)
- Report: median ± IQR

### D3 — Baseline Scheduler Pinning
- Confirm `dl_rb_alloc` and `ul_rb_alloc` function pointer assignments in
  `main.c` of the cloned branch before any benchmark
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
UL `lcid_alloc` hook does not exist. UL QoS limited to per-UE PRB sizing
via `ul_rb_alloc` and PHR-based MCS adjustment. Known architectural limitation.

### D6 — GBR Values Not Propagated to MAC (from Cluster 2)
`NR_QoS_config_t` holds only `fiveQI` + `priority`. Tier-1 LP must use
TS 23.501 Table 5.7.4-1 standard default GBR values per 5QI class.

### D7 — Stage 1 Readiness Gate for Multi-PDU-Session UEs
Before injecting traffic, verify all PDU sessions are up:
```bash
expected=$N_PDU_SESSIONS
while [ $(ip addr show | grep "inet 10\." | wc -l) -lt $expected ]; do
  sleep 0.5
done
```

---

## Stage 2 Integration Plan (Derived from Cluster 1)

```
Files to create:
  openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.c   ← three functions
  openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.h   ← declarations + Tier-1 shared struct

Files to modify:
  openair2/LAYER2/NR_MAC_gNB/main.c               ← 3-line registration
  config.yaml                                      ← add 3 DNNs (Cluster 2)
  nrue.uicc.conf (per scenario)                    ← multi-DNN pdu_sessions arrays

Tier-1 integration:
  Separate pthread at ~1 s cadence
  Writes rate targets rᵢ* into shared atomic struct
  ia_p5g_dl_rb_alloc reads targets each slot — no locks on fast path
  OSQP (libosqp) C API required — add to CMakeLists.txt

Function summary:
  ia_p5g_dl_rb_alloc()    Tier-2 DL core: virtual queue update → PRB sizing
  ia_p5g_ul_rb_alloc()    Tier-2 UL core: virtual queue update → PRB sizing
  ia_p5g_dl_lcid_alloc()  5QI-aware intra-UE byte mux via lc_config lookup

Stage 2 design debt (from Cluster 2):
  rb_alloc must derive effective priority from composite lc_config loop,
  not just candidate->fiveQI, for correct inter-UE ranking on multi-flow UEs.
```

---

*Last updated: Clusters 1 and 2 complete. Clusters 3–5 reading plans defined.*
