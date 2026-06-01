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
| 2 | QoS Flow Chain (5QI → DRB → MAC) | 🔲 Pending |
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
// Signature to match:
typedef int (*nr_dl_rb_alloc_fn)(const nr_dl_sched_params_t *params,
                                  nr_dl_candidate_t *candidates,
                                  int n_candidates);

// Registration in main.c:
RC.nrmac[i]->dl_rb_alloc = ia_p5g_dl_rb_alloc;
```

#### UL RB Allocation (replaces `nr_ul_proportional_fair`)

```c
// Signature to match:
typedef int (*nr_ul_rb_alloc_fn)(const nr_ul_sched_params_t *params,
                                  nr_ul_candidate_t *candidates,
                                  int n_candidates);

// Registration in main.c:
RC.nrmac[i]->ul_rb_alloc = ia_p5g_ul_rb_alloc;
```

#### DL Per-LCID Byte Allocation (replaces `nr_dl_lcid_alloc_default`)

```c
// Signature to match:
typedef void (*nr_dl_lcid_alloc_fn)(const gNB_MAC_INST *mac,
                                     const nr_dl_candidate_t *candidate,
                                     int tbs_available,
                                     int lcid_alloc[NR_MAX_NUM_LCID]);

// Registration in main.c:
RC.nrmac[i]->dl_lcid_alloc = ia_p5g_dl_lcid_alloc;
```

> **Note:** There is no UL equivalent of `lcid_alloc`. UL scheduling is per-UE
> only; the UE's MAC entity handles UL logical channel muxing autonomously
> (LCP procedure, TS 38.321). Only DL has the LCID byte-budgeting hook.

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
| `sched_pdsch.mcs` | `uint8_t` | Set by Stage 5 | MCS to use for TBS calc — already set when rb_alloc runs |
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
By the time TwoTier's `rb_alloc` is called, `sched_p{d,u}sch.mcs` is already
populated by `nr_dl_mcs_select_default` / `nr_ul_mcs_select_default`.

**Rule:** Tier-2 may refine MCS **downward** (e.g. PHR-constrained UL), but
never upward. Pass the final MCS value to `COMMIT_ALLOC` / `COMMIT_UL_ALLOC`.

`COMMIT_ALLOC` is a macro (not a function) that atomically:
1. Writes `rbStart`, `rbSize`, `mcs` onto the candidate
2. Validates a CCE can be assigned for the DCI
3. Marks the VRB map as occupied
4. Sets `cand->scheduled = true`

Never mark the VRB map manually — `COMMIT_ALLOC` handles it. If CCE validation
fails, the macro skips the UE silently.

The TBS utility function is `nr_find_nb_rb()` in `gNB_scheduler_primitives.c`:

```c
// Given target bytes, find minimum rbSize
nr_find_nb_rb(Qm, R, 1, nrOfLayers, nrOfSymbols,
              N_PRB_DMRS * N_DMRS_SLOT,
              pending_bytes + overhead,
              min_rbSize, max_rbSize,
              &tbs, &rbSize);
```

---

### Finding 1.5 — LCID→5QI Mapping: Already in OAI, No New Fields Needed

**Design debt from initial analysis is resolved.** OAI already stores per-LCID
QoS configuration in `NR_UE_sched_ctrl_t`:

```c
typedef struct NR_QoS_config_s {
  int fiveQI;
  int priority;
} NR_QoS_config_t;

typedef struct nr_lc_config {
  uint8_t         lcid;
  bool            suspended;
  int             priority;
  nssai_t         nssai;
  NR_QoS_config_t qos_config[NR_MAX_NUM_QFI];  // 5QI per QFI
} nr_lc_config_t;

// Inside NR_UE_sched_ctrl_t:
seq_arr_t lc_config;  // dynamic array of nr_lc_config_t, one per active LCID
```

**Access path from inside `lcid_alloc`:**
```c
candidate->UE->UE_sched_ctrl.lc_config
```

**Populated by:** `handle_ue_context_drbs_setup()` in
`mac_rrc_dl_handler.c:291`, called at DRB setup time (PDU session
establishment). Static lookup table from the scheduler's perspective — treat
as read-only during scheduling.

**Example for a factory_robots UE with three DRBs:**
```
lc_config[0]: lcid=4, fiveQI=2,  priority=1  → motion control (URLLC)
lc_config[1]: lcid=5, fiveQI=65, priority=3  → camera feed (GBR video)
lc_config[2]: lcid=6, fiveQI=9,  priority=7  → telemetry (best-effort)
```

**Sketch of `ia_p5g_dl_lcid_alloc`:**
```c
void ia_p5g_dl_lcid_alloc(const gNB_MAC_INST *mac,
                           const nr_dl_candidate_t *candidate,
                           int tbs_available,
                           int lcid_alloc[NR_MAX_NUM_LCID])
{
  memset(lcid_alloc, 0, NR_MAX_NUM_LCID * sizeof(int));
  const seq_arr_t *lc_cfg = &candidate->UE->UE_sched_ctrl.lc_config;

  for (int i = 0; i < lc_cfg->size; i++) {
    const nr_lc_config_t *lc = seq_arr_at(lc_cfg, i);
    int fiveQI  = lc->qos_config[0].fiveQI;
    int pending = candidate->pending_bytes_per_lcid[lc->lcid];
    lcid_alloc[lc->lcid] = ia_p5g_budget_for_flow(fiveQI, pending, tbs_available);
  }
}
// ia_p5g_budget_for_flow(): strict priority drain for URLLC 5QIs (1,2),
// then GBR-proportional fill (3,4,65,66), then leftover to best-effort (9).
```

---

### Finding 1.6 — Default PF Behaviour (Baseline Being Benchmarked)

`nr_dl_proportional_fair` runs three phases in order per slot:

1. **Retransmissions first** — exact `retx_rbSize` PRBs, largest free block ≥ needed
2. **No-data UEs** — minimum grant (`min_rbSize = 5`) for TA/beam-switch MAC CEs only
3. **New data** — sort by `pending_bytes / avg_throughput` (PF weight), allocate largest
   free block per UE greedily

Sort key: `dl_pf_weight(mcs, mcs_table, nrOfLayers, avg_throughput)` — uses
the MCS already set by Stage 5. **No flow awareness, no GBR, no PDB.**

TwoTier's phases 1 and 2 should be **identical** to the default — retx handling
and minimal grants are scaffolding, not the scheduler's value-add. Only phase 3
is replaced by the drift-plus-penalty allocation.

---

### Finding 1.7 — Tunable Config Parameters Relevant to IA-P5G

From `mac-usage.md`, these `MACRLCs` config-file knobs directly affect
scheduler behaviour and should be tuned per scenario:

| Parameter | Default | IA-P5G note |
|---|---|---|
| `dl_bler_target_upper` | 0.15 | Lower for URLLC flows (5QI=2) |
| `dl_bler_target_lower` | 0.05 | — |
| `ul_bler_target_upper` | 0.15 | Same consideration for UL URLLC |
| `ulsch_max_frame_inactivity` | 10 frames (100 ms) | Lower for sensor_dense (periodic bursts) |
| `dl_harq_round_max` | 4 | Consider 2 for URLLC PDB=10 ms |
| `ul_harq_round_max` | 4 | Same |
| `min_grant_prb` | 5 | Minimum UL grant for SR/inactivity wakeup |
| `dl_max_mcs` / `ul_max_mcs` | 28 | Cap per UE type if needed |

---

### Cluster 1 — Open Items

- [ ] Confirm `seq_arr_at()` macro/function signature for iterating `lc_config`
      (in `common/utils/seq_arr.h` or similar)
- [ ] Verify `NR_MAX_NUM_QFI` value — needed to know how many 5QIs a single
      LCID can carry (multiple QFIs per DRB is possible in 5G SA)
- [ ] Check whether `fiveQI` in the candidate struct is populated from
      `lc_config[0].qos_config[0].fiveQI` at collect time, or if it's derived
      elsewhere

---

## Cluster 2 — QoS Flow Chain (5QI → DRB → MAC) 🔲

### Goal
Understand the full end-to-end QoS path from PDU session establishment in
the core through to the MAC scheduler, so the DSCP→5QI mapping table covers
every link and the OAI CN5G subscriber DB is configured correctly.

### Files to Read (Priority Order)

| File | What to look for |
|---|---|
| `openair2/LAYER2/SDAP/nr_sdap/nr_sdap_configuration.h` | How 5QI and QoS flow ID map to DRBs |
| `openair2/LAYER2/SDAP/nr_sdap/nr_sdap_entity.c` | Per-flow SDAP entity; how flows are demuxed |
| `openair2/LAYER2/SDAP/nr_sdap/nr_sdap.c` | SDAP↔RLC interface |
| `ci-scripts/conf_files/gnb.sa.band78.106prb.rfsim.conf` | Closest reference config to IA-P5G setup; study QoS/DRB sections |
| `ci-scripts/oai-cn5g/database/oai_db.sql` | Subscriber DB schema; where GBR/MBR/5QI stored per subscriber |
| `ci-scripts/oai-cn5g/conf/config.yaml` | SMF/PCF QoS policy config |

### Key Questions to Answer

1. What 5QIs does the default subscriber DB configure? Are GBR 5QIs (1, 2, 3, 4, 65, 66)
   available out of the box, or do they need to be added per subscriber?
2. Does OAI's SDAP pass the 5QI down to the MAC, or does the MAC only see DRB ID?
   (Cluster 1 suggests 5QI is visible — confirm the population path.)
3. What RLC mode (AM/UM) is configured per DRB? Is it settable from the gNB config file
   or only from RRC signalling?
4. What is the full DSCP→DSCP field→IP filter→5QI→DRB→LCID→MAC priority chain?
   Which links require core config and which require gNB config?
5. How are GBR/MBR/GFBR/MFBR values communicated from the SMF to the gNB — are
   they present in the F1AP UE Context Setup message that feeds `handle_ue_context_drbs_setup()`?

### Expected Deliverable from This Cluster
A DSCP→5QI→DRB→LCID→scheduler mapping table covering all flow types in the
five IA-P5G scenarios, with the config file changes required at both core and gNB.

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
   If not, which TDL profile is the closest approximation for an indoor factory
   environment (dense clutter, high BS)?
2. Can different UEs have different channel models simultaneously in one
   rfsimulator run, or is it one model per gNB?
3. How is UE mobility (velocity, direction) specified per UE?
4. What is the empirical UE count ceiling before timing loop degrades?
   Is there an official rfsimulator guidance on this?
5. Does rfsimulator support a fixed random seed for reproducibility, or is
   there inherent non-determinism from OS scheduling jitter?

### Key Design Decision Pending
If InF is not natively available, a TDL-C or TDL-D approximation must be
agreed before scenario configs are finalised. TDL-C (300 ns delay spread,
moderate mobility) is the most common industrial factory approximation in
the literature.

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
Understand the reference multi-UE Docker setup, determine whether each UE
needs a separate container or can be batched, design the per-UE-type IMSI/
key/OPC assignment for the five scenarios, and understand traffic injection
architecture.

### Files to Read (Priority Order)

| File | What to look for |
|---|---|
| `doc/NR_SA_Tutorial_OAI_multi_UE.md` | Authoritative step-by-step multi-UE setup |
| `doc/NR_SA_Tutorial_OAI_nrUE.md` | Single-UE baseline — read before multi-UE |
| `ci-scripts/yaml_files/5g_rfsimulator_multiue/docker-compose.yaml` | Container structure, networking, rfsim port mapping |
| `ci-scripts/yaml_files/5g_rfsimulator_multiue/nrue.uicc.conf` | UE identity config (IMSI, key, OPC) — template for device-type configs |
| `ci-scripts/oai-cn5g/docker-compose.yaml` | Core network container topology (AMF, SMF, UPF, NRF) |

### Key Questions to Answer

1. Does each UE require a separate container, or can multiple IMSIs run in
   one `nr-uesoftmodem` process?
2. How is rfsimulator port assignment handled per UE — is it deterministic and
   configurable from docker-compose, or auto-assigned?
3. Where does traffic generation (iperf3 / UDP probe) run — inside the UE
   container, or in a separate container that routes through the UPF?
4. How are per-UE QoS parameters (5QI, GBR, MBR) specified when a UE has
   multiple PDU sessions or multiple QoS flows on the same session?
5. What is the recommended network topology for rfsimulator multi-UE:
   shared L2 bridge, macvlan, or host networking?

### Scenario UE Count Reference

| Scenario | UEs | UE Types |
|---|---|---|
| smoke | 3 | 1× controller, 1× sensor, 1× camera |
| overload | 5 | 2× controller, 2× sensor, 1× camera |
| vision | 6 | 1× controller, 4× camera, 1× sensor |
| sensor_dense | 8 | 1× controller, 6× sensor, 1× camera |
| factory_robots | 10 | 2× robot (multi-flow), 2× AGV, 2× drone, 2× camera, 2× sensor |

### Expected Deliverable from This Cluster
A `docker-compose.yaml` template for the factory_robots scenario (10 UEs)
with correct IMSI assignment, rfsim port mapping, channel model per UE,
and traffic generator config per flow.

---

## Cross-Cluster Design Decisions

These items span multiple clusters and need resolution before Stage 2 coding begins.

### D1 — Measurement Window and Warm-Up Period
The Python simulator study showed ~60 windows (~60 s) for steady state.
OAI rfsim runs will have similar transients. Define:
- Discard-warmup duration (suggested: 10 s)
- Measurement window per scenario (suggested: 60 s)
- Reporting granularity (suggested: 1 s buckets, matching Tier-1 cadence)

### D2 — Reproducibility Strategy
rfsimulator has non-determinism from OS scheduling jitter. Decide:
- Minimum runs per scenario for statistical validity (suggested: 5)
- Whether to use fixed seeds if rfsim supports them
- How to report: median ± IQR, or mean ± σ

### D3 — Baseline Scheduler Pinning
OAI's "default" is not a single named scheduler — the function pointer
assignment in `main.c` is the ground truth. Before benchmarking:
- Confirm which function is assigned to `dl_rb_alloc` and `ul_rb_alloc`
  in the `main.c` of the cloned branch
- Document the git commit hash of the OAI tree used for all benchmarks

### D4 — UE Capability Profiles
Different industrial device types have different UE categories.
Agree on per-type settings before building UE Docker configs:

| UE Type | Max MCS | Antenna config | Power class |
|---|---|---|---|
| Motion controller | 28 (256QAM) | 1T1R | PC3 |
| 4K camera | 28 (256QAM) | 1T1R | PC3 |
| Sensor node | 16 (64QAM) | 1T1R | PC3 |
| AGV | 28 (256QAM) | 2T2R | PC3 |
| Drone | 28 (256QAM) | 1T1R | PC2 |

*To be verified against scenario_config YAMLs.*

### D5 — LCID→5QI at UL (No Hook Available)
The UL `lcid_alloc` hook does not exist — UL logical channel muxing is
handled by the UE's MAC entity (LCP procedure). UL QoS enforcement at the
gNB is therefore limited to:
- PRB sizing per UE (the `ul_rb_alloc` hook)
- PHR-based MCS adjustment (already in `nr_ul_proportional_fair` — reuse)
- BSR-based buffer pressure (visible on the candidate as `pending_bytes`)

This means UL per-flow 5QI differentiation is not achievable at the gNB MAC
layer without UE-side changes. Document this as a known limitation.

---

## Stage 2 Integration Plan (Derived from Cluster 1)

```
Files to create:
  openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.c   ← three functions
  openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.h   ← declarations + Tier-1 shared struct

Files to modify:
  openair2/LAYER2/NR_MAC_gNB/main.c               ← 3-line registration

Tier-1 integration:
  Separate pthread at ~1 s cadence
  Writes rate targets rᵢ* into shared atomic struct
  ia_p5g_dl_rb_alloc reads targets each slot — no locks on fast path
  OSQP (libosqp) C API required — add to CMakeLists.txt

Function summary:
  ia_p5g_dl_rb_alloc()    Tier-2 DL core: virtual queue update → PRB sizing
  ia_p5g_ul_rb_alloc()    Tier-2 UL core: virtual queue update → PRB sizing
  ia_p5g_dl_lcid_alloc()  5QI-aware intra-UE byte mux via lc_config lookup
```

---

*Last updated: Cluster 1 complete. Clusters 2–5 reading plans defined.*
