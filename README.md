# 5G QoS-Optimized Scheduler

Research / exploration project: a two-tier scheduler for a private 5G
deployment (factory / warehouse / port), targeted at OpenAirInterface (OAI)
once the design is validated.

The scheduler combines:
- **Tier-1** — a CVXPY LP that runs once per ~1 s, computes per-flow target
  rates that respect GBR floors, delay-class priority, and per-direction
  PRB-symbol capacity.
- **Tier-2** — a per-slot drift-plus-penalty (Lyapunov virtual queues)
  scheduler that tracks Tier-1's targets opportunistically.

A lightweight Python simulator validates the design comparatively against
round-robin, pure proportional fair, and a class-aware gradient baseline.
OAI integration is planned but not yet started.

## Documents

- [design-docs/scheduler-study.md](design-docs/scheduler-study.md) — start
  here: the scientific rationale — design goals, state of the art (incl. the
  OAI default scheduler), the mathematical formulation, the comparative
  results, and when the two-tier design earns its complexity.
- [design-docs/scheduler-design.md](design-docs/scheduler-design.md) — the
  scheduler architecture (workload model, TDD/numerology, Tier-1 LP form,
  Tier-2 metric, OAI integration plan).
- [design-docs/simulator-design.md](design-docs/simulator-design.md) — what
  the simulator models and (more importantly) what it deliberately doesn't.
- [scheduler/HOWTO.md](scheduler/HOWTO.md) — for a gNB developer wiring
  this scheduler into OpenAirInterface (or any other gNB codebase): the
  four structural views to satisfy from host structs, per-slot integration,
  Tier-1 threading pattern, configuration binding, and the deviations to
  expect vs the sim. Its companion is
  [scheduler/scheduler_config.yaml](scheduler/scheduler_config.yaml) —
  the reference/default config for `TwoTier` with per-parameter comments.

The design docs have `[OPEN]` markers on remaining decisions.

## Quick start

The project is managed by [uv](https://docs.astral.sh/uv/) — see
[installation_usage.md](installation_usage.md) for the full guide,
including OS-specific install commands, troubleshooting, and the
maintainer workflow.

```bash
# One-time: install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup (downloads Python 3.12, creates .venv, installs all pinned deps)
make install

# Run the test suite
make test

# Single smoke scenario, JSON output
make smoke

# Five scenarios x four schedulers, side-by-side
make compare

# Three contract-oriented studies: overload sweep, PDCCH-limited, latency-bound
uv run python scripts/scheduler_study.py

# Sensitivity studies: UL BSR delay/loss, DL CQI staleness + SPS MCS margin,
# and the max-min GBR stage that fixes cell-edge starvation
uv run python scripts/bsr_study.py
uv run python scripts/cqi_study.py
uv run python scripts/maxmin_study.py

# Per-slot time-series plots
uv run python scripts/plot_timeseries.py --scenario sensor --schedulers pf twotier
uv run python scripts/plot_timeseries.py --scenario smoke --scheduler twotier
```

## Comparing schedulers

`scripts/compare_schedulers.py` (`make compare`) runs five scenarios
(smoke / overload / vision / sensor-dense / YAML-driven) through four
schedulers for a side-by-side per-flow view.

`scripts/scheduler_study.py` runs three contract-oriented studies — an
overload sweep, a PDCCH-limited regime, and a latency-bound regime — to
establish *where* the two-tier scheduler changes outcomes users feel.
Headline: the value of QoS-awareness is a hump — it shows at moderate
overload, not at deep overload or light load; for dense periodic traffic
SPS / Configured Grants is a structural win plain PF cannot match; and
for medium-rate latency-critical flows a deadline-aware scheduler is
required. Full results and a build/don't-build decision table are in
[NOTES.md](NOTES.md).

## Layout

```
.
├── README.md
├── installation_usage.md         install + usage guide (uv workflow, troubleshooting)
├── pyproject.toml                project metadata + dependencies
├── uv.lock                       cross-platform pinned versions (37 packages)
├── .python-version               pins CPython to 3.12
├── Makefile                      thin wrapper over uv (install / test / smoke / ...)
├── design-docs/                  scheduler + simulator design notes
│   ├── scheduler-study.md        scientific rationale + comparative results
│   ├── scheduler-design.md
│   └── simulator-design.md
├── scheduler/                    the two-tier scheduler — a self-contained library
│   ├── HOWTO.md                  gNB-developer guide: integrating into OAI / other gNB
│   ├── scheduler_config.yaml     reference/default TwoTier config, per-parameter comments
│   ├── config_loader.py          YAML -> TwoTier kwargs (lazy PyYAML import)
│   ├── flow.py                   FlowConfig: per-flow QoS / traffic descriptor
│   ├── link.py                   link adaptation (SNR -> bits/PRB, PDCCH AL)
│   ├── interfaces.py             Allocation + Scheduler / slot / buffer / channel views
│   ├── tier1.py                  Tier-1 CVXPY LP solver
│   └── two_tier.py               Tier-2 drift-plus-penalty + SPS + MAC multiplexer
├── sim/                          simulation harness for comparative study
│   ├── config.py                 scenario / UE / TDD dataclasses
│   ├── config_loader.py          scenario YAML -> ScenarioConfig loader
│   ├── resource.py               TDD pattern, per-slot grid
│   ├── channel.py                stationary AR(1) SNR model
│   ├── buffer.py                 fluid byte buffers w/ HoL timestamps
│   ├── traffic.py                deterministic / Poisson / video-frame
│   ├── metrics.py                per-flow stats, percentile latency
│   ├── driver.py                 main simulation loop
│   ├── scenarios/                ran / simulation / scenario YAML configs + loaders
│   ├── baselines/                RoundRobin / ProportionalFair / Gradient (comparison)
│   └── tests/                    unit + scenario tests
├── scripts/                      entry points
│   ├── run_smoke.py
│   ├── compare_schedulers.py
│   ├── scheduler_study.py        overload-sweep / PDCCH / latency studies
│   ├── bsr_study.py              UL BSR delay / loss sensitivity
│   ├── cqi_study.py              DL CQI staleness / SPS MCS margin sensitivity
│   ├── maxmin_study.py           max-min GBR stage (cell-edge starvation)
│   ├── knapsack_diagnostic.py    why soft GBR floors abandon the cell edge
│   ├── transient_check.py        long-run windowed steady-state check
│   └── plot_timeseries.py
└── ...
```

`scheduler/` is the deliverable — a self-contained library (it imports only
cvxpy / numpy, never `sim/`) intended for OpenAirInterface integration.
`sim/` is the harness that exercises and benchmarks it.

## What works today

- Slot-driven simulation at any 5G NR numerology.
- Configurable TDD pattern including S-slot DL/guard/UL split.
- AR(1) per-UE SNR with stationary variance (regression-tested).
- Four schedulers: RoundRobin, ProportionalFair, Gradient, TwoTier.
- CVXPY-backed Tier-1 LP with soft GBR floors and weighted log utility.
- Drift-plus-penalty Tier-2 with deadline-aware delay urgency.
- SPS / Configured Grants in TwoTier with I-frame burst spillover.
- Per-slot PDCCH/CCE budget enforcement across all schedulers (this is
  what makes SPS' value visible — without it, dynamic scheduling keeps up).
- Variable DCI aggregation level (AL ∈ {1,2,4,8,16}) per UE based on SNR.
  High-SNR UEs get cheap DCIs; edge UEs pay more, making PDCCH bind sooner.
- Per-slot time-series recording (opt-in) and matplotlib plots for
  throughput, HoL latency, buffer occupancy, PRB and PDCCH utilization.
- Scenarios in [sim/scenarios/](sim/scenarios/) are a three-file split —
  `ran_config_<id>.yml` (radio), `simulation_config.yml` (run window), and
  `scenario_config_<n>.yml` (workload, naming a `default_ran`) — so one
  workload can be run on different radios. Assembled by
  [sim/config_loader.py](sim/config_loader.py); see the
  [scenarios README](sim/scenarios/README.md).
- Contract-oriented scheduler study ([scripts/scheduler_study.py](scripts/scheduler_study.py)):
  overload-sweep, PDCCH-limited, and latency-bound regimes scored on
  GBR/Delay contract satisfaction and p99 latency.
- 39 unit tests covering buffer mechanics, channel stationarity, GBR
  protection under overload, fairness, Tier-1 feasibility, adaptive and
  SE-tilt penalty behaviour, windowed-ceiling protection, SPS accounting,
  PDCCH-limited and latency-bound deadline protection, AL monotonicity,
  time-series shape, and every scenario YAML loading end to end.

## Roadmap

Near-term:
- Real 3GPP TBS table extract (currently a fitted curve).
- Deep dive on Findings 2 and 3 (see [NOTES.md](NOTES.md)).

Longer-term:
- OAI integration (see [scheduler-design.md §10](design-docs/scheduler-design.md)).
- MU-MIMO awareness in the LP.
- Trace-driven traffic from real factory measurements.

## Status

Pre-prototype. Numbers from the simulator are good for *comparing*
schedulers on identical workloads but should not be cited as absolute
performance claims (the link adaptation, BLER, and HARQ models are
deliberately approximate).
