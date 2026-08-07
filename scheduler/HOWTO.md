# Integrating the two-tier scheduler into OpenAirInterface

Audience: an OAI gNB developer who wants to replace (or augment) OAI's
default PF scheduler with this library. Assumes familiarity with the
OAI 5G NR MAC layer (`openair2/LAYER2/NR_MAC_gNB/`), Python-in-C
embedding (or a language-boundary strategy of your choice), and
`gNB_MAC_INST`.

For the *why* (design goals, evaluated tradeoffs, and the deployment
regimes where this scheduler earns its complexity), read
[design-docs/scheduler-study.md](../design-docs/scheduler-study.md).

---

## 1. What this library gives you

- A per-slot MAC scheduler decision function: given the current slot's
  resource grid, per-flow buffer state, and per-UE channel estimate,
  return one `Allocation` per (UE, LCID) share of a per-UE grant.
- A strategic tier: a CVXPY LP that runs once per ~1 s, sets per-flow
  target rates (respecting GBR floors, delay-class priority, and slice
  shares), and configures SPS / Configured Grant reservations.
- A clean I/O contract: four structural views (`SlotView`, `GridView`,
  `BufferView`, `ChannelView`) that the host satisfies by *shape*, not
  by inheritance -- no `scheduler` import needs to reach into OAI headers
  and no OAI struct needs to inherit anything.

What this library does **not** give you:
- Any PHY code. The scheduler is above MCS selection: it consumes a
  per-UE SNR (or its CQI-derived proxy) and emits an MCS via
  `bits_per_prb`. OAI's link adaptation stays where it is.
- Any RRC / F1 / NGAP glue. Contracts (GFBR, PDB, priority, slice) come
  in as `FlowConfig` fields; how you populate them (5QI mapping, PDU
  session setup, DRB config) is out of scope.
- Any HARQ state machine. Failed TBs are represented as a BLER discount
  on delivered bits; a real gNB MAC layers HARQ on top.
- Any BSR / SR / PUCCH decoding. Buffer state is delivered to the
  scheduler via `BufferView`; how the state gets there (BSR MAC CE
  decoding, SR trigger handling) is host work.

---

## 2. Files to include from `scheduler/`

All Python, no C extension, ~2000 lines total:

| File | What's in it |
|---|---|
| `flow.py` | `FlowConfig` — per-flow QoS descriptor (5QI-shaped). |
| `link.py` | Link adaptation model: `bits_per_prb(snr_db, symbols)`, `cce_aggregation_level(snr_db)`, `bler_for_mcs(threshold, true_snr)`. Replace with OAI's own MCS / TBS table on the port. |
| `interfaces.py` | `Allocation`, `Scheduler` protocol, and the four structural views. |
| `tier1.py` | Strategic LP (`solve_tier1`, `solve_maxmin_gbr_level`, `gbr_maxmin_floors`). CVXPY-based. |
| `two_tier.py` | Per-slot scheduler class `TwoTier`. Consumes the four views, emits `list[Allocation]`. |
| `config_loader.py` | Optional YAML → `TwoTier(**cfg)` helper. Uses PyYAML (lazy). |
| `scheduler_config.yaml` | Reference config file with defaults + per-parameter comments. |

The library imports **only** cvxpy and numpy. If you cannot afford
cvxpy in the gNB process (LP solve on the fast path is a bad idea
regardless -- see §5 below), the recommended pattern is to run Tier-1
in a separate process and share its output via a lock-free snapshot.

---

## 3. The I/O contract — four structural views

The scheduler reads state through four Python protocols. Any object
that has the right attributes / methods satisfies them; no inheritance,
no registration. In practice you write four small adapter classes over
OAI's own structs.

### 3.1 `SlotView` — one slot's resource grid

```python
class SlotView(Protocol):
    slot_index: int          # monotone slot counter (any zero point)
    dl_symbols: int          # usable DL OFDM symbols this slot (0..14)
    ul_symbols: int          # usable UL OFDM symbols this slot (0..14)
    prb_count: int           # PRBs across the carrier's usable BW
    pdcch_cce_budget: int    # CCEs available for dynamic DCIs this slot
```

Populated per slot from OAI's `NR_UE_sched_ctrl_t` / TDD pattern /
CORESET config. The S-slot's DL / gap / UL symbol counts come from the
TDD-UL-DL-ConfigCommon; `prb_count` is derived from `bwp` and MU pattern.
`pdcch_cce_budget` needs a real count of CCEs left after fixed
CSS/RA/SI reservations.

### 3.2 `GridView` — the TDD pattern (call at scheduler `configure()` time)

```python
class GridView(Protocol):
    pattern: str             # e.g. "DSUUU" (one period)
    prb_count: int
    slot_duration_s: float
    def slot_grid(self, slot_index: int) -> SlotView: ...
```

Read once at scheduler configure time so Tier-1 can compute per-direction
PRB-symbol capacity for the LP.

### 3.3 `BufferView` — per-flow buffer state

```python
class BufferStateView(Protocol):
    bytes_queued: int        # true RLC backlog (what the gNB owns for DL)
    bytes_reported: int      # BSR-visible view for UL; == bytes_queued
                             # for DL, or when no BSR delay is modelled

class BufferView(Protocol):
    def state(self, ue_id: int, qfi: int) -> BufferStateView: ...
    def hol_delay_s(self, ue_id: int, qfi: int, now_s: float) -> float: ...
    def arrived_cum(self, ue_id: int, qfi: int) -> int: ...
    def delivered_cum(self, ue_id: int, qfi: int) -> int: ...
```

The **`bytes_queued` vs `bytes_reported` split is load-bearing** (§5
below). On DL the gNB owns the RLC buffer, so both are the same live
value. On UL the gNB only knows what the last BSR said -- expose that
as `bytes_reported`, and use whatever local state the gNB has for
`bytes_queued` (typically the same value; the split matters mostly in
sim). Dynamic scheduling reads `bytes_reported`; SPS reads
`bytes_queued`.

`hol_delay_s(now_s)` is the age of the oldest queued SDU; needed for
the Delay-class urgency term in Tier-2.

`arrived_cum` / `delivered_cum` are monotone cumulative byte counters
used only for the Tier-2 windowed-ceiling clamp. Any bookkeeping that
gives monotone cumulative arrivals/deliveries at the SDU boundary is
sufficient.

### 3.4 `ChannelView` — per-UE channel quality

```python
class ChannelView(Protocol):
    def get_snr_db(self, ue_id: int) -> float: ...            # true SNR
    def get_reported_snr_db(self, ue_id: int) -> float: ...   # CQI view
```

- `get_snr_db` is used at transmission time to compute the actual BLER
  of the chosen MCS. On the gNB, this is the freshest SNR estimate you
  have (from SRS / DMRS / OLLA). If the two are the same in your host,
  return the same value from both.
- `get_reported_snr_db` is what the scheduler reads for MCS pick and
  UE ranking. On DL this is the CQI-index-derived SNR (aperiodic or
  periodic CQI). On UL, use the SRS-derived estimate; there is no CQI
  as such, but the concept -- "the last measurement, not what is true
  right now" -- is the same.

---

## 4. Per-slot integration

Once you have the four view adapters written, the per-slot loop is:

```python
from scheduler import TwoTier, load_two_tier

scheduler = load_two_tier("path/to/scheduler_config.yaml")
scheduler.configure(flows, slot_duration_s, grid_view)  # once, at bring-up

# Per slot -- inside your MAC scheduler thread, replacing the PF call:
for alloc in scheduler.allocate(slot_view, buffer_view, channel_view):
    if alloc.bytes_capacity <= 0:
        continue
    # Map each Allocation to the OAI side:
    #   * The FIRST Allocation per UE per direction carries the DCI cost
    #     (alloc.cce_cost) and the total PRB count (alloc.prbs).
    #   * All Allocations from the same UE grant share the transport
    #     block; each Allocation's bytes_capacity is that flow's share.
    #   * alloc.snr_used_db is the SNR the scheduler used to pick the
    #     MCS; feed it into your MCS lookup or link-adaptation call so
    #     the transmitted MCS matches the scheduling decision.
    #   * alloc.is_sps is True for SPS-served allocations (skip PDCCH
    #     encoding for these).
    ...
```

### 4.1 A per-UE grant is emitted as several `Allocation`s

Tier-2 issues one DCI per UE (one transport block); if that UE has
multiple flows sharing the grant, the MAC logical-channel prioritisation
step inside `TwoTier` splits the TB across them and emits one
`Allocation` per participating flow. Only the *first* Allocation for the
grant carries the DCI cost and PRB count; the follow-on ones carry a
`bytes_capacity` share and zeros for `prbs` and `cce_cost`. Match this
by tracking `(ue_id, direction)` and only encoding one DCI per pair.

### 4.2 SPS / Configured Grants

`alloc.is_sps == True` means the scheduler is serving this flow from a
standing reservation. In OAI: this Allocation should not cause a new
DCI to be encoded, and its resource use should go against the CG
allocation that was set up earlier (via RRC reconfiguration triggered
by Tier-1). Tier-1's SPS-configuration output lives on the `TwoTier`
instance as `_sps` (a list of `_SPSReservation`); read it after each
Tier-1 solve and translate to OAI's CG-configuration path.

---

## 5. Threading and CPU cost

Tier-2 (`allocate`) is per-slot and cheap: dict lookups, sorts of
per-UE lists, one arithmetic pass. Runs on the MAC scheduler thread.

Tier-1 (`solve_tier1` and the max-min stage) is a small convex program
(24 flows in the study scenarios), typically <100 ms wall-clock -- but
it is CVXPY, and it is **not** slot-safe. Runs by default every
`tier1_period_slots` slots (2000 slots = 1 s at μ=1).

The recommended integration pattern:

- **Separate process / thread** for Tier-1. It reads the same
  `FlowConfig` list and a snapshot of per-UE `snr_avg` and `demand_bps`;
  it writes an atomic snapshot of `_targets_bps` and the SPS
  reservation list.
- **Lock-free swap** (double-buffered pointer, `std::atomic` on the
  C++ side, or a POSIX shm) on Tier-2's read. If Tier-2 sees the old
  targets for one extra slot, nothing breaks; the drift-plus-penalty
  loop tolerates stale targets by construction.
- **Graceful degradation** if Tier-1 stalls: keep the last-good solution.
  `TwoTier` already does this internally when `solve_tier1` returns a
  non-optimal status.

If the LP genuinely cannot fit even at 1 s cadence on your target
hardware, the fallback is to solve it *less* often -- the design
tolerates Tier-1 periods of up to several seconds without qualitative
degradation, because Tier-2's virtual queues integrate over the gap.

---

## 6. Configuration

Every parameter is in [`scheduler_config.yaml`](scheduler_config.yaml)
with a comment. Load via `load_two_tier(path)`, or via
`load_two_tier_config(path)` for the raw dict if you want to override
some values.

At the OAI boundary, the natural place to source these values is the
`.conf` file that OAI already uses for MAC scheduler configuration --
translate each YAML key into an OAI config key and populate a
`TwoTier(**kwargs)` call from that. The 17 parameters are all scalar or
`None`/`bool` except `slice_shares` (a `dict[int, dict[str, float]]`),
which needs an OAI-side array-of-structs equivalent.

Do **not** ship the YAML file as the OAI config: it's a reference, not
a source of truth for a live gNB. Bind the values through RRC / OAI's
config machinery so operations can change them without restarting.

---

## 7. Deviations to expect vs the sim

The sim gives the scheduler some things a real gNB doesn't. Each is
either modelled cheaply in the sim (with a knob you can leave at 0 in
tests) or documented as a known gap. Expect them to bite on the OAI
port:

- **BSR round-trip.** Sim models this via `BufferModel(ul_bsr_delay_slots=8)`;
  OAI has real BSR MAC CE latency, ~4-8 ms. Study `bsr_study.py` shows
  the effect. Populate `BufferView.bytes_reported` from actual BSR
  arrival, not from local RLC state.
- **CQI staleness and quantisation.** Sim models delay + Bernoulli loss;
  OAI has real CQI-report periodicity, quantisation to 4-bit indices,
  and occasional PUCCH loss. `ChannelView.get_reported_snr_db` should
  reflect that, not the fresh SNR estimate.
- **UL k2 grant-to-transmission.** Not modelled in the sim. A dynamic
  UL grant issued in slot n is used at slot n+k2 (~4 slots at μ=1).
  Expect an extra ~2 ms of dynamic UL latency in OAI that the sim
  numbers do not carry.
- **HARQ.** Sim uses a BLER-discount; OAI has real HARQ processes,
  re-transmissions, and ACK/NACK feedback. TB retransmits consume PRBs
  on later slots -- the Tier-1 capacity budget should account for this
  (subtract expected HARQ overhead from `capacity_safety_factor`, or
  reduce the effective PRB count).
- **RRC signalling latency for SPS reconfig.** Sim assumes Tier-1 can
  reconfigure SPS instantly at each solve; OAI has ~50-100 ms of RRC
  round-trip. If your workload is dynamic (UEs joining / leaving,
  contracts changing), rate-limit SPS reconfiguration to what the RRC
  side can absorb, or hold SPS reservations across several Tier-1 solves.

---

## 8. Verification

Before wiring to real UEs:

1. **Sanity: same input, same output.** Feed a canned scenario (say,
   `sim/scenarios/scenario_config_1.yml`) through both the sim's
   `driver.run(scenario, TwoTier(...))` and your OAI adapter (with the
   same view snapshots replayed). Per-flow throughput and per-UE PRB
   allocation should agree to a few percent -- disagreement bigger than
   that means a view is misconfigured (usually `BufferView` or
   `pdcch_cce_budget`).
2. **The four structural views** each have a small acceptance test in
   `sim/tests/test_smoke.py` -- port those to OAI-side test doubles as
   a mock-driven check that your adapters satisfy the protocol.
3. **PF baseline in OAI.** Run your OAI build against a static
   workload with the two-tier scheduler swapped out for OAI's default
   PF. If PF's own numbers don't match published OAI results, the sim
   comparison isn't measuring what you think it is.

Common failure modes:
- `pdcch_cce_budget` too generous -- your SPS wins go away (see
  §7.2 of the study doc: SPS's value depends on PDCCH being bound).
- `BufferView.bytes_reported` populated from live RLC state instead of
  from BSR arrivals -- CQI/BSR sensitivity results won't reproduce.
- `slot_duration_s` in the wrong units at `configure()` time -- Tier-1
  target rates come out wrong by orders of magnitude.

---

## 9. Known open gaps the OAI port will probably surface

Ranked by the audit in `NOTES.md` (2026-05-17). Ranks 1-2 are already
modelled in the sim; expect Rank 3 in particular to show up:

3. **UL k2 grant-to-transmission timing** (~4 slots). Widens SPS's win
   on any UL-heavy scenario. Sim currently schedules and transmits in
   the same slot; OAI won't.
4. **Proper HARQ retransmissions consuming PRBs.** Uniform across
   schedulers, but the Tier-1 capacity budget should account for the
   expected HARQ overhead.
5. **RRC signalling latency for SPS reconfig** (§7 above).

None of these are showstoppers; each is a distinct place where the sim
was optimistic and the OAI port will find out by how much.

---

## Cross-references

- Architecture and per-tier math: [../design-docs/scheduler-design.md](../design-docs/scheduler-design.md)
- Rationale, results, sensitivity studies: [../design-docs/scheduler-study.md](../design-docs/scheduler-study.md)
- Sim model & fidelity discipline: [../design-docs/simulator-design.md](../design-docs/simulator-design.md)
- Modelling-gap audit and dated findings: [../NOTES.md](../NOTES.md)
