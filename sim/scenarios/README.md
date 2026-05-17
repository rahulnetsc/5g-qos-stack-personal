# Scenario configs

Each `scenario_config_<id>.yml` in this directory is one self-contained
simulation scenario: the radio, the run window, and the UE/flow workload.
A loader function in [`__init__.py`](__init__.py) (`<id>_scenario()`) reads
one file into a `ScenarioConfig` via [`sim/config_loader.py`](../config_loader.py).

**To add a scenario:** drop a new `scenario_config_<id>.yml` file here and
add a one-line loader function in `__init__.py`.

## File structure

```yaml
name: smoke                # scenario name (defaults to the filename stem)

simulation:
  horizon_slots: 4000      # number of slots to simulate
  seed: 7                  # RNG seed (channel + Poisson traffic)

carrier:
  bandwidth_mhz: 30        # FR1 channel bandwidth
  numerology: 1            # mu; SCS = 15*2^mu kHz, slot = 1/2^mu ms
  overhead_factor: 0.85    # fraction of PRBs usable for data (optional, default 0.85)

tdd:
  pattern: DSUUU           # one TDD period; D=DL, U=UL, S=special
  s_slot_split:            # S-slot OFDM symbol split (must sum to 14)
    dl_symbols: 3
    gap_symbols: 2
    ul_symbols: 9

defaults:                  # optional — inherited by every ue / flow below
  ue:   {mean_snr_db: 20.0, coherence_slots: 2000}
  flow: {flow_class: PF, max_delay_budget_ms: 30}

ues:
  - ue_id: 1
    mean_snr_db: 22.0      # overrides defaults.ue
    flows:
      - qfi: 2
        direction: UL              # UL | DL
        flow_class: GBR            # PF | GBR | Delay
        min_data_rate_bps: 8000000 # GFBR — guaranteed floor (GBR flows)
        max_delay_budget_ms: 30    # PDB
        traffic:
          kind: video_frame        # poisson | deterministic | video_frame
          period_ms: 33.33
          avg_bytes: 33000
          i_frame_multiplier: 4.0
          i_frame_period_in_frames: 30
```

## Conventions

- Each flow is uni-directional (matches 3GPP — the UL and DL halves of one
  app carry separate QFIs). For a bidirectional app, write two flow entries.
- `defaults.ue` / `defaults.flow` are shallow-merged under each `ue` / `flow`.
  The `traffic` block is merged atomically — an override that sets `traffic`
  replaces it whole. An empty flow (`flows: [{}]`) inherits the default flow
  entirely; this is how `sensor_dense` and `latency_bound` stay compact.
- Traffic kinds and their params:
  - `poisson` — `rate_bps`
  - `deterministic` — `period_ms`, `bytes_per_period`
  - `video_frame` — `period_ms`, `avg_bytes`, `i_frame_multiplier`,
    `i_frame_period_in_frames`, optional `i_frame_phase`
- Fields the simulator does not model are accepted and ignored (e.g. a
  flow's `max_data_rate_bps` / MFBR — no rate-cap enforcement yet).

## Scenarios

| id | what it stresses |
|----|------------------|
| `smoke` | mixed workload, no overload — sanity baseline |
| `overload` | severe DL overload — QoS-enforcement differences |
| `vision` | 3 cameras with staggered I-frame bursts — tail latency |
| `sensor_dense` | 30 periodic UL sensors — PDCCH/CCE-limited regime |
| `latency_bound` | medium-rate deadline streams vs bulk on a congested DL |
| `factory_robots` | 10 factory robots, uplink-heavy — the main study scenario |
