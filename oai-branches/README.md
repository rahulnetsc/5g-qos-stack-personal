# oai-branches — verified OAI source, per branch

These are files pulled directly from the real OAI gNB scheduler source, kept
as ground truth for Phase 2 (see top-level `README.md` §7). They are split
into `two-tier/` and `reservation/` rather than one flat directory because
several files share a filename across the two branches but have *different*
contents — flattening them would silently overwrite one branch's version
with the other's. Where a file's content *is* identical across branches,
that's called out explicitly below rather than assumed.

Source repo for all entries: `~/projects/Oai_Ran_QoS_Supported_MultiDRB`
(local checkout). `two-tier/` and `reservation/` come from two branches of
this *same* repo — `twotier` and `rrc-qos-handling-v0.1.1` respectively —
not from two separate repos.

## two-tier/

| file | source branch | commit | notes |
|---|---|---|---|
| `gNB_scheduler.c` | — | exact SHA not recorded | byte-identical to `reservation/gNB_scheduler.c` |
| `gNB_scheduler_dlsch.c` | `twotier` | `7358e99` | reviewed 2026-08-07 against this commit; see `design-docs/oai-phase1-review.md` |
| `gNB_scheduler_ulsch.c` | `twotier` | `7358e99` | ditto |
| `ia_p5g_scheduler.c` | `twotier` | `7358e99` | ditto |
| `ia_p5g_scheduler.h` | `twotier` | `7358e99` | ditto |
| `gNB_scheduler_primitives.c` | `twotier` | `f5486434f9139d869cd742065139a1af17a627b4` (2026-03-12, "Working GBR") | byte-identical to `reservation/gNB_scheduler_primitives.c`; predates `7358e99` |
| `nr_mac_common.c` | `twotier` | `98618a7dc8c2c9bdf7fc3d2c789f57658cbd46d1` (2025-10-28) | originally `openair2/LAYER2/NR_MAC_COMMON/nr_mac_common.c`, not `NR_MAC_gNB/`; pulled for WP3 (BSR realism) — carries `NR_SHORT_BSR_TABLE`/`NR_LONG_BSR_TABLE` (38.321 Tables 6.1.3.1-1/-2) and `get_short_bsr_value`/`get_long_bsr_value`, the source `sim/bsr.py`'s quantisation tables are transcribed from |
| `nr_ue_scheduler.c` | `twotier` | `63f3fb55aeab49e6709561828e0555b7eea87a32` (2025-12-09) | originally `openair2/LAYER2/NR_MAC_UE/nr_ue_scheduler.c` — the *UE*-side MAC, not the gNB; pulled for WP3 alongside `nr_mac_common.c` — carries `nr_locate_BsrIndexByBufferSize` (L1506-1542), the UE-side BSR-index encoder (`sim/bsr.py`'s quantisation is a two-step port: this file's encoder, then `gNB_scheduler_ulsch.c`'s `overestim_bsr_index` decoder). Also carries `nr_update_sr` (L1207-1277) and `schedule_RA_after_SR_failure` (L1190-1206), the SR *trigger* half of WP4's uplink access chain — spot-checked against the live repo (`twotier`, current tip) when WP4 was scoped and confirmed unchanged |
| `gNB_scheduler_uci.c` | `twotier` | `98618a7dc8c2c9bdf7fc3d2c789f57658cbd46d1` (2025-10-28) | pulled for WP4 (SR chain) — carries `handle_nr_uci_pucch_0_1`'s `sched_ctrl->SR \|= true` branch (~L950-960, the gNB-side "I received an SR" event) and `nr_sr_reporting` (L1274-1360, schedules the recurring PUCCH SR occasion per UE); both are called from `gNB_scheduler.c` (L254, L256) but were undefined anywhere in what was vendored before this |
| `nr_ue_procedures.c` | `twotier` | `0bf99d9d16d33037827f48836d982688974f25f2` (2025-09-10) | originally `openair2/LAYER2/NR_MAC_UE/nr_ue_procedures.c`; pulled for WP4 alongside `gNB_scheduler_uci.c` — carries `trigger_periodic_scheduling_request` (L2569-2611) and `nr_ue_get_SR` (L2613-2661), the sr-TransMax counter / prohibit-timer gate / RA-fallback trigger — the SR *transmission-attempt* half of the chain, complementing `nr_ue_scheduler.c`'s trigger half above |

## reservation/

| file | source branch | commit | notes |
|---|---|---|---|
| `gNB_scheduler.c` | `rrc-qos-handling-v0.1.1` | exact SHA not recorded | byte-identical to `two-tier/gNB_scheduler.c` |
| `gNB_scheduler_dlsch.c` | `rrc-qos-handling-v0.1.1` | exact SHA not recorded | — |
| `gNB_scheduler_ulsch.c` | `rrc-qos-handling-v0.1.1` | exact SHA not recorded | — |
| `gNB_scheduler_primitives.c` | `rrc-qos-handling-v0.1.1` | `f5486434f9139d869cd742065139a1af17a627b4` (2026-03-12, "Working GBR") | byte-identical to `two-tier/gNB_scheduler_primitives.c` |

## Files confirmed byte-identical across branches

- **`gNB_scheduler.c`** — identical on both branches (shared/common
  dispatcher; no matching commit SHA on record for either side).
- **`gNB_scheduler_primitives.c`** — identical on both branches, and here
  the shared commit explains why: both branches point at the same
  upstream commit (`f548643`, 2026-03-12) for this file, meaning neither
  fork has touched it since. That commit predates `7358e99`
  (2026-08-07, when the two-tier scheduler review was done), so this file
  is stock/upstream OAI rather than fork-modified scheduler logic — Phase 2
  does not need to treat it as branch-specific.
