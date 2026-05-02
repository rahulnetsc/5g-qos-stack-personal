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

- [design-docs/scheduler-design.md](design-docs/scheduler-design.md) — the
  scheduler architecture (workload model, TDD/numerology, Tier-1 LP form,
  Tier-2 metric, OAI integration plan).
- [design-docs/simulator-design.md](design-docs/simulator-design.md) — what
  the simulator models and (more importantly) what it deliberately doesn't.

Both have `[OPEN]` markers on remaining decisions.

## Quick start

```bash
pip install -r requirements.txt

# Unit tests
python -m pytest tests/

# Run smoke scenario through round-robin, dump per-flow JSON
python scripts/run_smoke.py

# Run smoke + overload + vision + sensor scenarios through 4 schedulers,
# side-by-side table
python scripts/compare_schedulers.py

# Per-slot time-series plots for one scheduler or two side-by-side
python scripts/plot_timeseries.py --scenario sensor --schedulers pf twotier
python scripts/plot_timeseries.py --scenario smoke --scheduler twotier
```

## What `compare_schedulers.py` shows

Two scenarios (mixed workload under capacity, and a 4.8× DL overload),
each run through four schedulers. The interesting comparison is on the
overload scenario, where the two-tier system delivers 97% of GFBR vs 57%
for plain PF, by sacrificing best-effort throughput. See the design doc
for the full table.

## Layout

```
.
├── README.md
├── requirements.txt
├── design-docs/                  scheduler + simulator design notes
│   ├── scheduler-design.md
│   └── simulator-design.md
├── sim/                          simulator core
│   ├── config.py                 scenario / flow / UE / TDD dataclasses
│   ├── resource.py               TDD pattern, per-slot grid
│   ├── channel.py                stationary AR(1) SNR, MCS staircase
│   ├── buffer.py                 fluid byte buffers w/ HoL timestamps
│   ├── traffic.py                deterministic / Poisson / video-frame
│   ├── metrics.py                per-flow stats, percentile latency
│   ├── tier1.py                  CVXPY LP solver
│   ├── scenarios.py              reusable scenario definitions
│   ├── driver.py                 main simulation loop
│   └── schedulers/
│       ├── round_robin.py        baseline
│       ├── pf.py                 standard proportional fair
│       ├── gradient.py           class-aware multiplicative urgency
│       └── two_tier.py           Tier-1 LP + Tier-2 drift-plus-penalty
├── scripts/                      entry points
│   ├── run_smoke.py
│   └── compare_schedulers.py
└── tests/
    └── test_smoke.py             buffer, channel, grid, all schedulers
```

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
- 23 unit tests covering buffer mechanics, channel stationarity, GBR
  protection under overload, fairness, Tier-1 feasibility, SPS
  accounting, PDCCH-limited regime, AL monotonicity, time-series shape.

## Roadmap

Near-term:
- Real 3GPP TBS table extract (currently a fitted curve).
- More scenarios beyond the four canned ones.

Longer-term:
- OAI integration (see [scheduler-design.md §10](design-docs/scheduler-design.md)).
- MU-MIMO awareness in the LP.
- Trace-driven traffic from real factory measurements.

## Status

Pre-prototype. Numbers from the simulator are good for *comparing*
schedulers on identical workloads but should not be cited as absolute
performance claims (the link adaptation, BLER, and HARQ models are
deliberately approximate).
