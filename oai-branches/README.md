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
