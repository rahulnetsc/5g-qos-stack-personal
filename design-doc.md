# Private 5G QoS-Aware Scheduler — OAI Integration PoC

## Mission Statement

Design, integrate, and benchmark a QoS-aware two-tier MAC scheduler for a
private 5G deployment in an industrial automation setting. The scheduler must
reliably meet per-flow QoS contracts — Guaranteed Bit Rate (GBR), Packet Delay
Budget (PDB) — for mixed industrial traffic (motion control, machine vision,
sensor telemetry, best-effort) under realistic factory load conditions.

The proof of concept runs on a real software 5G stack
(OpenAirInterface core + gNB + UE via rfsimulator) so that results are
directly transferable to a physical private 5G deployment.

---

## Background and Prior Work

A Python discrete-event simulator was built first to develop and validate the
two-tier scheduler algorithm in isolation. It established:

- The two-tier architecture is sound: a slow Tier-1 LP (~1 s cadence) sets
  per-flow rate targets; a fast Tier-2 drift-plus-penalty rule ranks UEs
  per slot using virtual queue deficits weighted by spectral efficiency.
- TwoTier outperforms OAI-equivalent PF, Round Robin, and Gradient schedulers
  on GBR contract adherence and p99 HoL delay for delay-sensitive flows in
  all five validated scenarios (smoke, overload, vision, sensor_dense,
  factory_robots).
- HARQ sigmoid BLER model and IR combining were implemented and validated;
  empirical gains were modest under current scenario parameters.
- MAC LCP multiplexing, PHR modelling, and token bucket LCP were analysed and
  deliberately deferred — these are handled natively by the real OAI stack.

The Python simulator remains available as an algorithm development sandbox for
rapid prototyping of scheduler variants before OAI integration.

**The scheduler being ported is the `main` branch TwoTier — not the
`feat/harq-bler-retx` branch.** Complexity is added incrementally after the
baseline OAI integration is validated.

---

## Objectives

### Primary
1. Run OAI gNB + core + UE (rfsimulator) with default PF scheduler and
   produce a clean baseline benchmark across all five scenarios.
2. Replace the OAI MAC scheduler with TwoTier and benchmark the same scenarios.
3. Produce a side-by-side comparison demonstrating QoS contract adherence
   (GBR met / PDB met) improvements over the PF baseline.

### Secondary
4. Build a reusable benchmarking harness (shell scripts + metrics collector)
   that can be driven by a GUI in a later phase.
5. Establish the monitoring variable exposure points on the gNB so that CQI,
   BSR, PHR, HARQ stats, PRB utilization, and per-flow throughput are
   observable at runtime.

---

## Technical Stack

| Component | Software | Role |
|---|---|---|
| 5G Core | OAI CN5G | AMF, SMF, UPF, NRF, UDM |
| gNB | OAI gNB (`nr-softmodem`) | MAC scheduler is the integration point |
| UE emulation | OAI `nr-uesoftmodem` + rfsimulator | RF channel emulated in process, no hardware |
| RF transport | rfsimulator (built-in OAI) | IQ sample exchange over shared memory / loopback |
| Traffic generation | iperf3 + custom UDP probe | Reproduces scenario traffic profiles |
| Metrics collection | OAI T tracer + custom callback | gNB-side KPIs |
| Orchestration | Bash shell scripts | Start/stop/benchmark automation |

**Numerology:** μ=1, 30 kHz SCS, 0.5 ms slot, 14 symbols/slot, 2 slots/subframe.
**TDD pattern:** DSUUU (configurable per scenario).
**Carrier:** 30 MHz (106 PRBs) default; 40 MHz variant for vision-heavy scenarios.

---

## Scenarios

Five scenarios are carried over from the Python simulator. Each maps to a
specific UE count, traffic mix, and QoS stress condition.

| # | Name | UEs | Primary stress | Key flows |
|---|---|---|---|---|
| 1 | smoke | 3 | None — sanity baseline | DL PF, UL Delay, UL GBR video |
| 2 | overload | 5 | DL capacity overload | Multiple GBR + PF competing for same PRBs |
| 3 | vision | 6 | UL bandwidth + I-frame bursts | 4K camera UL GBR flows |
| 4 | sensor_dense | 8 | Many small UL flows, tight PDB | Periodic sensor control loops |
| 5 | factory_robots | 10 | Mixed DL+UL, multi-flow UEs | Motion control + vision + best-effort on same UE |

**Scenario → real stack translation:**
Each Python `FlowConfig` maps to an iperf3/UDP traffic generator instance with
DSCP marking that the core maps to a 5QI, which carries the QoS profile
(GBR, PDB) through the PDU session. The DSCP → 5QI → QoS policy mapping
table is a required deliverable of Phase 1.

---

## Benchmarking Metrics

### Per-flow KPIs
| Metric | Source | SLA check |
|---|---|---|
| Throughput (bps) | iperf3 / gNB metrics | ≥ GBR for GBR flows |
| p50 / p95 / p99 HoL delay (ms) | UDP probe timestamps | p99 ≤ PDB |
| Packet loss ratio | iperf3 | — |
| HARQ retx ratio | gNB T tracer | — |

### Per-cell KPIs
| Metric | Source |
|---|---|
| DL / UL PRB utilization | gNB scheduler metrics |
| PDCCH CCE utilization | gNB scheduler metrics |
| Per-UE CQI | gNB L1 feedback |
| Per-UE BSR | gNB MAC layer |
| Per-UE PHR | gNB MAC layer |

### SLA verdict (per run, per flow)
```
GBR_met   : delivered_bps >= contracted_gbr_bps
PDB_met   : p99_hol_ms    <= contracted_pdb_ms
```
Every benchmark run produces a pass/fail table alongside raw numbers.

---

## Benchmarking Harness Structure

```
oai-benchmark/
  infra/
    start_core.sh          # start OAI CN5G, wait for AMF ready
    stop_core.sh
    start_gnb.sh           # start nr-softmodem, wait for N2 setup complete
    stop_gnb.sh
    start_ue.sh <ue_id>    # start nr-uesoftmodem, wait for PDU session up
    stop_ue.sh <ue_id>
    start_all.sh           # ordered: core → gNB → UEs with readiness gates
    stop_all.sh

  traffic/
    run_scenario.sh <scenario_name>   # inject traffic per scenario profile
    iperf_dl.sh  <ue_id> <rate_mbps> <dscp> <duration_s>
    iperf_ul.sh  <ue_id> <rate_mbps> <dscp> <duration_s>
    udp_probe.sh <ue_id>              # latency measurement

  benchmark/
    run_benchmark.sh <scheduler> <scenario>
    collect_metrics.sh
    generate_report.py

  config/
    scenarios/             # one .yml per scenario (carried from Python sim)
    gnb/                   # OAI gNB config files per scenario
    ue/                    # OAI UE config files (IMSI, QoS profiles)
    core/                  # Open5GS subscriber DB + QoS policy

  results/
    <timestamp>_<scheduler>_<scenario>/
      raw/                 # iperf3 JSON, T tracer logs, UDP probe output
      summary.json         # structured KPIs
      report.md            # human-readable pass/fail table
```

`run_benchmark.sh` is the single entry point:
1. Calls `start_all.sh`, waits for stack ready
2. Calls `run_scenario.sh <scenario>` to inject traffic
3. Runs for scenario duration
4. Calls `collect_metrics.sh`
5. Calls `stop_all.sh`
6. Calls `generate_report.py` → writes to `results/<timestamp>/`

---

## OAI MAC Scheduler Integration Point

The TwoTier scheduler replaces the per-TTI PRB allocation logic inside the
OAI gNB MAC layer. The relevant files are in:

```
openair2/LAYER2/NR_MAC_gNB/
  nr_mac_gNB.h              # NR_UE_info_t, NR_UE_sched_ctrl_t — UE state
  gNB_scheduler.c           # gNB_dlsch_ulsch_scheduler() — main entry point
  gNB_scheduler_dlsch.c     # DL preprocessor — replace this
  gNB_scheduler_ulsch.c     # UL preprocessor — replace this
  gNB_scheduler_fairRR.c    # current Round Robin / PF implementation
```

**Inputs available at scheduling time (from `NR_UE_sched_ctrl_t`):**
- `estimated_ul_buffer` — BSR equivalent
- `dl_pdus_total` — DL buffer depth
- `cqi_req` / `ul_cqi` — channel quality
- `ph` — Power Headroom Report value
- `raw_rssi` — received signal strength
- HARQ process state per UE

**Outputs the scheduler must produce:**
- PRB allocation bitmap per UE (DL and UL)
- MCS index per UE
- HARQ process assignment

**Integration strategy:** implement TwoTier Tier-2 as a drop-in replacement
for `nr_fr1_dlsch_preprocessor()` and `nr_ulsch_preprocessor()`. Tier-1 LP
runs in a separate pthread at ~1 s cadence, writing rate targets into a
shared memory struct that Tier-2 reads each TTI. No OAI core stack
modifications required.

---

## Phased Execution Plan

### Phase 1 — OAI Baseline (current phase)
- [ ] Single UE smoke test: attach, iperf3 DL, verify metrics flow end-to-end
- [ ] DSCP → 5QI → QoS policy mapping table
- [ ] Benchmarking harness shell scripts
- [ ] Baseline benchmark: all 5 scenarios × default PF scheduler
- [ ] Baseline report with SLA pass/fail table

### Phase 2 — TwoTier Integration
- [ ] Map `NR_UE_sched_ctrl_t` fields to TwoTier inputs
- [ ] Implement Tier-2 per-TTI allocator in C (port from Python `two_tier.py`)
- [ ] Implement Tier-1 LP in separate pthread (CVXPY → C via OSQP or similar)
- [ ] Integration test: single UE, single flow, verify Tier-1 rate target flows to Tier-2
- [ ] Full benchmark: all 5 scenarios × TwoTier
- [ ] Comparison report: PF vs TwoTier, SLA pass/fail delta

### Phase 3 — Iterative Hardening
- [ ] Validate PHR handling (real PHR reports available from UE, use directly)
- [ ] Validate HARQ interaction (real HARQ feedback, no modelling needed)
- [ ] Token bucket LCP (already in OAI — configure PBR/BSD per flow class)
- [ ] Multi-cell extension (future)
- [ ] GUI for benchmark orchestration and live monitoring (future)

---

## Key Design Decisions (from Python simulator phase)

- **Numerology μ=1 throughout.** 30 kHz SCS, 0.5 ms slot duration.
- **TDD pattern DSUUU as default** with S-slot split 3:2:9 (DL:GP:UL symbols).
- **Single cell, single carrier.** Mobility and handover explicitly out of scope.
- **TwoTier main branch for OAI integration.** HARQ sigmoid model and IR
  combining from `feat/harq-bler-retx` deferred — the real stack handles
  HARQ natively.
- **Python simulator retained** as algorithm sandbox. New scheduler variants
  are prototyped there before OAI porting.
- **Shell script orchestration layer** designed for GUI automation in Phase 3.
  Every operation has a discrete script with a clean readiness gate so a GUI
  can drive it without parsing stack logs.

---

## Repository Layout (target)

```
/
  python-sim/          # existing Python simulator (read-only reference)
    scheduler/         # TwoTier, PF, RR, Gradient — algorithm source of truth
    sim/               # simulator engine
    scripts/           # compare_schedulers.py, compare_harq.py, etc.
    scenarios/         # scenario_config_*.yml, ran_config_*.yml

  oai-benchmark/       # new — this project
    infra/
    traffic/
    benchmark/
    config/
    results/

  oai-scheduler/       # new — OAI fork with TwoTier integrated
    (OAI submodule or fork)
    patches/           # TwoTier scheduler patch against OAI main

  docs/
    MISSION.md         # this document
    scheduler-design.md
    scheduler-study.md
```

---

## What to Carry into the New Project

### Upload these files from the Python simulator project:

**Algorithm reference (will be ported to C):**
- `scheduler/two_tier.py`
- `scheduler/tier1.py`
- `scheduler/link.py`
- `scheduler/interfaces.py`
- `scheduler/flow.py`
- `scheduler/_mac.py`
- `scheduler/pf.py`
- `scheduler/round_robin.py`
- `scheduler/gradient.py`

**Scenario definitions (will be translated to OAI configs):**
- `scenario_config_1.yml` through `scenario_config_6.yml`
- `ran_config_dsuuu_30mhz.yml`
- `ran_config_dsuuu_40mhz.yml`
- `ran_config_dddsu_40mhz.yml`

**Design documentation:**
- `scheduler-design.md` — algorithm specification, the porting reference
- `scheduler-study.md` — simulation results, establishes the baseline claims
- `simulator-design.md` — simulator internals (reference only)

**Protocol reference:**
- `38321-gm0_MAC_protocol_specification.pdf` — LCP, PHR, HARQ spec sections

### Do NOT carry over (Python sim internals, not needed in OAI project):
- `sim/driver.py`, `sim/channel.py`, `sim/buffer.py`, `sim/traffic.py`
- `sim/metrics.py`, `sim/resource.py`, `sim/config.py`
- `scripts/compare_harq.py`, `scripts/compare_schedulers.py`
- `scripts/diagnose_*.py`, `scripts/transient_check.py`
- `scripts/plot_timeseries.py`, `scripts/scheduler_study.py`

---

*Document version: initial — created at project handoff from Python simulator
phase to OAI integration phase.*
