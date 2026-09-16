# Guarantee groups, and the regression contract for tuning a scheduler

**Decided 2026-09-16 (user).** The objective is a QoS-aware scheduler
proposal, and the two candidates being tuned are **`ProtoRRageD2`** and
**`ConfigSched`**. Every experiment reports all five arms; increments are
applied only to those two. This file is the contract the tuning runs
against: what the groups are, what each isolates, how they couple, and the
rule that decides whether an increment is kept.

## 0. Scope

**In scope, nine guarantees:** G1, G2, G3, G5, G6, G7, G9, G10, G12.

**Deferred to the end, three:** G4 (its only procedure is GT-2.3, unbuilt —
`g4_postsilence.py` answers a different question, and the test plan calls
real RF essential for the clause), G8 (no runner exists in `scripts/`) and
G11 (the shift-long soak). Nothing in this file's tables covers them, and
no verdict should be quoted for them.

The nine in scope are exactly the nine steps
`sweeps/cs2-increments/run_increment.sh` already runs, so a one-arm
increment measurement covers the whole in-scope set in about 20 minutes.

## 1. The groups

Each group is one functional requirement with its own failure mechanism,
its own runners, and its own place to look when it breaks.

| group | guarantees (procedure) | runners | what it isolates | 5 arms | 1 arm |
|---|---|---|---|---|---|
| **A — Downlink deadline** | G1 (GT-1.1), G2 (GT-1.2) | `g1_stress.py`, `g2_stress.py` | DL ordering, the per-slot DCI cap, and how many HARQ retries fit inside a short PDB | ~34 min | ~8 min |
| **B — Uplink liveness** | G3 (GT-2.2) | `g3_stress.py` | *when* a small periodic UL flow is next served — service interval, silence, cadence | ~9 min | ~1 min |
| **C — Uplink video** | G5 (GT-3.1/3.2/3.3) | `g5_video.py` | sustained byte rate and frame assembly: PDU-set completeness, frame age, GFBR per 2 s window | ~8 min | ~1 min |
| **D — Isolation & containment** | G6 (GT-4.1/4.2), G7 (GT-4.3) | `g6_isolation.py`, `g7_aggressor.py` | harm from a bad actor: a non-GBR flood (G6, a within-seed delta test) and a GBR bearer over-driven past MFBR (G7) | ~8 min | ~1 min |
| **E — Capacity & degradation** | G10 (GT-5.2), G12 (GT-7.3) | `g5_consolidation.py`, `g12_stress.py` | the cell at and past its limit: admissible fleet, and the order classes break in | ~7 min | ~1 min |
| **F — Transitions** | G9 (GT-6.1/6.2/6.3) | `g9_stress.py` | join, re-join and RLF recovery — the only group whose stimulus is a UE arriving or leaving | ~12 min | ~2 min |

Flags per group, as the campaign script passes them, are in
`sweeps/cell-2026-09-16-linux/run_campaign.sh`; a single-arm run of all six
groups is `sweeps/cs2-increments/run_increment.sh`.

## 2. How the groups couple

They are **not orthogonal**, and the point of writing the couplings down is
that a tuning change must re-check the groups it can reach, not only the one
it targets.

| coupling | why | consequence for tuning |
|---|---|---|
| **A ↔ B, C, E** | `HarqProcessPool.due_this_slot()` iterates one shared dict across every (UE, direction) pool, so a DL-only change can reorder UL retry draws and vice versa (CLAUDE.md, measured on Phase-2 commit 3) | small but real; A must be re-run after uplink work, and a 1–2-seed move in A after a UL change is expected, not a defect |
| **B ↔ D** | G6's telemetry instrument **is** G3's flow, measured under a flood | any cadence change moves D's telemetry half; D's camera half is independent |
| **C ↔ E** | both spend the same uplink bytes — G5's frames and G10's GBR floors are the same resource seen two ways | a sizing, floor or shedding change moves both; never tune one without reading the other |
| **F ↔ E** | G9's occupancy axis is derived from G10's admissible boundary | if E's boundary moves, F's axis is stale (it already is: the axis came from the previous cell, so F's top two points are past capacity) |
| **A ↔ D** | G6's G1 instrument is the `cmd_vel` flow of A | D's part-B shift test sees any DL deadline change |

## 3. The regression contract

For every increment, on the arm being tuned:

1. **Name the target group and register the expectation before the run** —
   what should move, in which direction, and what would falsify it.
2. **Run all six groups for that arm** (`run_increment.sh`, ~20 min), never
   just the target. The couplings above are the reason.
3. **Compare against that arm's previous kept state** with
   `sweeps/cs2-increments/compare.py <inc> --before <prev> --arm-before <arm>`.
4. **Keep the increment only if:** the target group's *verdict* improves
   (boundary, pass count, or the clause's own statistic) **and no other
   group's verdict degrades**. A within-group metric that moves without
   changing a verdict is recorded, not a veto.
5. **Score the registered expectation honestly** — a miss is written down
   with its number, and the increment's note says what the miss taught.
6. **A reverted increment stays in the log** with its measurement. Four of
   the first nine were reverted; the reasons are the most reusable part of
   the record.

**And the standing rule from the user, 2026-09-16: if a bug is found, every
result it affects is re-run before anything from it is reported.** A known
bug plus a published number is not an acceptable combination at any point.

## 4. Where each tuning target stands per group, before any of this work

From the campaign (`docs/results-cell-2026-09-15.md`) and the ConfigSched2
increments (`docs/campaign-cell-2026-09-16-linux.md` §8). ConfigSched shows
prototype → rebuilt where they differ.

| group | ProtoRRageD2 | ConfigSched | the reference to beat |
|---|---|---|---|
| A | = TwoTier; G1 pass, G2 263 at cap 2 | G1 cap 2 10.5–20.5 → **5–15 ms**; G2 1 390 → **291** | deadline arms 247–263; every arm fails G2 on the retry budget |
| B | boundary **10**, silences ≤ 494 ms | **10**; part-1s boundary 16 → **24**, silences ≤ 294 ms | PF 10 |
| C | **8 / no knee to ×1.5** | 7 / ×1.1 → **6 / ×1.0** ← weak | PF 8 / ×1.4 |
| D | G7 **0.82×** | G7 0.92× → **1.04×** ← weak | G6 fails on every arm (shift test) |
| E | G10 **7** ← weak | G10 **10**, G12 fine | PF 8 |
| F | **12/12** | 9/12 → **12/12** | PF 11/12 |

**So the grouping localises each target to a small number of groups:**
ProtoRRageD2 to **E** alone, and ConfigSched2 to **C and D** — which share
one traced cause (the table gives a contracted flow with backlog any free
DCI beyond its plan, so an over-driven camera exceeds MFBR and a competing
camera takes the instrument's bytes). One increment addresses both.
