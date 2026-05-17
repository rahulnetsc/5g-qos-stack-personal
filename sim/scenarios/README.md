# Scenario configs

A simulation run is assembled from three independently editable files, so
each concern can be varied without touching the others:

| file | concern | what it holds |
|------|---------|---------------|
| `ran_config_<id>.yml` | radio | carrier (bandwidth, numerology, overhead), TDD pattern + S-slot split |
| `simulation_config.yml` | run window | `horizon_slots`, `seed` — shared by every run |
| `scenario_config_<n>.yml` | workload | the UEs and flows, plus a `default_ran:` naming the radio it expects |

`sim.scenarios.scenario(n)` loads `scenario_config_<n>.yml` on its
`default_ran`; pass `ran_id=` to run the same workload on a different
radio — e.g. `scenario(5, ran_id="dsuuu_40mhz")` runs the latency-bound
workload on a balanced TDD instead of its DL-heavy default. Named helpers
(`smoke_scenario()`, …) in [`__init__.py`](__init__.py) wrap the numbered
scenarios.

**To add a scenario:** drop a `scenario_config_<next>.yml` file here (it
names its own `default_ran`); `scenario(<next>)` then loads it. **To add a
radio:** drop a `ran_config_<id>.yml` file.

## scenario_config_&lt;n&gt;.yml

```yaml
name: smoke                # human-readable name (-> ScenarioConfig.name)
default_ran: dsuuu_30mhz    # ran_config_<id>.yml to pair with by default

defaults:                   # optional — inherited by every ue / flow below
  ue:   {mean_snr_db: 20.0, coherence_slots: 2000}
  flow: {flow_class: PF, max_delay_budget_ms: 30}

ues:
  - ue_id: 1
    mean_snr_db: 22.0       # overrides defaults.ue
    flows:
      - qfi: 2
        direction: UL              # UL | DL
        flow_class: GBR            # PF | GBR | Delay
        min_data_rate_bps: 8000000 # GFBR — guaranteed floor (GBR flows)
        max_delay_budget_ms: 30    # PDB
        priority_level: 100        # optional; 5QI convention, lower = higher
        slice_id: 0                # optional; network slice for Tier-1 RB shares
        traffic:
          kind: video_frame        # poisson | deterministic | video_frame
          period_ms: 33.33
          avg_bytes: 33000
          i_frame_multiplier: 4.0
          i_frame_period_in_frames: 30
```

## ran_config_&lt;id&gt;.yml

```yaml
carrier:
  bandwidth_mhz: 30
  numerology: 1            # mu; SCS = 15*2^mu kHz, slot = 1/2^mu ms
  overhead_factor: 0.85    # fraction of PRBs usable for data (optional, default 0.85)
tdd:
  pattern: DSUUU           # one TDD period; D=DL, U=UL, S=special
  s_slot_split:            # S-slot OFDM symbol split (must sum to 14)
    dl_symbols: 3
    gap_symbols: 2
    ul_symbols: 9
```

## simulation_config.yml

```yaml
simulation:
  horizon_slots: 4000      # slots to simulate
  seed: 42                 # RNG seed (channel + Poisson traffic)
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
- `priority_level` (optional, default 100) follows the 3GPP 5QI convention
  — lower value = higher priority. It tiers SPS reservations: higher-priority
  flows are reserved first, lower tiers take what is left. With every flow
  at the default it is a single tier (the current scenarios do this).
- `slice_id` (optional, default 0) tags a flow's network slice. Tier-1 can
  give each slice a guaranteed share of PRB capacity via
  `TwoTier(slice_shares={slice_id: {"DL": frac, "UL": frac}})`; the share is
  a soft, work-conserving floor. Default 0 puts every flow in one slice.
- Fields the simulator does not model are accepted and ignored (a flow's
  `max_data_rate_bps` / MFBR — no rate-cap enforcement yet).

## Catalogue

| n | name | default RAN | what it stresses |
|---|------|-------------|------------------|
| 1 | smoke | `dsuuu_30mhz` | mixed workload, no overload — sanity baseline |
| 2 | overload | `dsuuu_10mhz` | severe overload — QoS-enforcement differences |
| 3 | vision | `dsuuu_30mhz` | 3 cameras, staggered I-frame bursts — tail latency |
| 4 | sensor_dense | `dsuuu_30mhz` | 30 periodic UL sensors — PDCCH/CCE-limited |
| 5 | latency_bound | `dddsu_40mhz` | deadline streams vs bulk on a congested DL |
| 6 | factory_robots | `dsuuu_40mhz` | 10 factory robots, uplink-heavy — main study |

RAN configs: `dsuuu_30mhz`, `dsuuu_10mhz` (small cell), `dsuuu_40mhz`
(wide, numerology 2), `dddsu_40mhz` (DL-heavy TDD).
