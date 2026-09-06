# Full guarantee re-run — consolidated result

**Registered** `docs/rerun-2026-09-06-registration.md` (before launch).
**Ran** 07:36–09:10, **94 min against a 120-min budget**, detached under
`setsid`, banked per campaign. Artefacts `sweeps/rerun-2026-09-06/`.

**Registered expectation: everything reproduces.** It largely did. **Two
campaigns did not, and neither is a numeric movement** — both are guards
refusing to produce a result, which is a stronger finding than a delta.

---

## 1. The diff, per guarantee

| guarantee | verdict | artefact | n | evidence |
|---|---|---|---|---|
| **G1 G3 G5 G8** (parametric) | **REPRODUCED** | `core.json` | 10 seeds × 3 arms | 30 paired rows, **18 numeric fields byte-equal to 1e-9** |
| **G1 G3 G8** (`sensor_dense`) | **REPRODUCED** | `sensor_dense.json` | 10 × 3 | 30 rows, 15 fields |
| **G5 G10** consolidation | **REPRODUCED** | `g5_consol.json` | 10 × 3 × 4 fleet sizes | 120 rows, 8 fields |
| **G10** (attach path) | **REPRODUCED** | `g10_attach.json` | 10 × 3 × 2 | 60 rows, 8 fields |
| **G4** | **REPRODUCED** | `g4.json` | 10 × 3 × 3 duty | **3,852 rows**, 4 fields |
| **G6** | **REPRODUCED** | `g6/stage6_g6_n40.json` | 40 × 3 | full structural diff clean |
| **G7** (load 1.0) | **REPRODUCED** | `g7.json` | 10 × 3 | 30 rows, 31 fields |
| **G7** (load 1.5) | **REPRODUCED** | `g7_load1.5.json` | 4 × 3 | 12 rows, 32 fields |
| **G7** (load 2.5) | **BLOCKED — guard fired** | — | — | §2 |
| **G9** | **REPRODUCED** | `g9.json` | 10 × 3 × 3 scenarios | full structural diff clean |
| **G11 C1** | **REPRODUCED** | `g11_c1_soak.json` | 10 × 3 @ **7.2 M slots** | **30/30 runs, no failures, memory guard not tripped**, 4,355 s |
| **G11 C3/C4/C5** | **REPRODUCED** | `g11_c345.json` | scored from the NEW C1 artefact | full structural diff clean |
| **G12** | **BLOCKED — guard fired, and it invalidates the published figure** | — | — | §3 |
| **G2** | **REPRODUCED** | `g2_ul_stop.json` | 10 × 3 | 30 rows, 13 fields |

**Both workloads are covered on the three overlapping guarantees** (G1, G3,
G8), which is where the cross-workload evidence lives.

`verify_claims --check` 8/8 as expected · `regression_corpus --check` no drift
· `parallel_audit --check` clean · **suite 1103 passed**.

## 2. G7 at load 2.5 — the offered-rate guard refused it

```
achieved offered rate: 1.99-2.06x MFBR (GT-4.3 requires >= 2.0x)
the aggressor offered only 1.99x MFBR -- this is not GT-4.3's scenario
```

This is the precondition assertion working: GT-4.3 is defined at ≥2× MFBR and
the cell landed at 1.99×. **G7's own cell (load 1.0) and load 1.5 both
reproduced exactly**, so the guarantee is not in doubt; the 2.5× excursion is.
**Not chased** — the instruction was to name a non-reproduction and stop.

## 3. G12 — the one that invalidates a published result

`g12_campaign.py` now exits on defect #28's guard: `ue8_qfi9` collides DL with
UL, **31 flows collapsing to 30 records**.

**The guard is new; the collision is not.** It postdates
`sweeps/postscaling-2026-09-05/g12.json`, so the published run hit the same
collision with nothing to stop it and **silently dropped a 5QI-9 flow**.

**Why it is material.** G12's clause-4 finding reads *"telemetry M02 reaches
1.000 while 5QI 9 is still carrying 11.6 Mbps"*. **The lost flow is a 5QI-9
flow** — it is in the denominator of the claim's own aggregate.

**What survives and what does not.** The qualitative finding survives: 11.6
Mbps against a floored telemetry flow is not a margin one flow reverses. **The
figure is not the number it says it is, and G12 has no reproducible artefact
at all.** Logged as defects-log **#30**. **Not fixed** — the fix is a scenario
change (give the second flow its own 5QI, as `sim/fleet.py`'s UL E-STOP flow
already does with 5QI 86) with its own re-score.

**The transferable shape:** the re-run did not find a number that moved, it
found a number that **cannot be recomputed** — invisible to any check that
only compares values.

## 4. Two defects in my own instruments, found by running them

**(a) The orchestrator ran the wrong runner for G10.** The published artefact
came from `g5_consolidation.py --attach-seed` (n_ues 8/16, attach on), not
`g10_rerun.py` (n_ues 2–32, attach off) — same field names, different grid and
a different mechanism. Caught because the differ reports **pairing** and not
only deltas: it said *"NO PAIRED ROWS (60 old, 60 new)"* rather than printing
nothing. **A diff that only prints differences is silent on an artefact it
never read.** The correct campaign was queued and reproduced.

**(b) A positional deep-diff on a parallel campaign is meaningless.**
`run_cells` yields in **completion** order, so C1's diff compared each run
against a different run and reported **14,477 differences**. Paired on
`(arm, seed)` the same artefact is **byte-identical across all 30 runs**. Both
lessons are now in `rerun_diff.py` as comments at the point of use.

## 5. Traces — captured during the re-run, not instead of it

**Cost: 275 s against the soak's 4,355** (~6 % of the budget), so nothing was
cut to afford them. Sequenced strictly after the soak so the 10×2 GB pool
never shared the machine.

**Acceptance conditions, all met:** declared at construction; **bit-identical
with the hook off on 120 of 120 cells** (compared on `RunRecord.to_dict()`,
not the raw summary — defect #26); both sinks raise on an empty collection.

### The result: one mechanism explains all four unexplained results

| cell | arm | the UE's UL grants | % carrying the protected 5QI | deferral tail (skipped p98) |
|---|---|---|---|---|
| G7 aggressor | **PF** | 2,047 | **2.69 %** | **45** |
| G7 aggressor | Reservation | 11,557 | 0.06 % | 0 |
| G7 aggressor | **TwoTier** | 12,458 | **0.47 %** | **298** |
| attach control | PF | 2,050 | 2.68 % | 52 |
| attach control | TwoTier | 4,641 | 0.58 % | 344 |
| **attach** | PF | 2,164 | 2.40 % | 77 |
| **attach** | TwoTier | **9,727** | 0.69 % | **456** |
| G5 residual | PF | 3,246 | 3.11 % | 39 |
| G5 residual | TwoTier | 25,607 | 0.71 % | 318 |

**Monotone across every cell: the more grants an arm issues to a UE, the
smaller the share that carries the UE's protected flow, and the longer that
flow's deferral tail.** PF sits at 2.4–3.1 % carried with a tail of 39–77;
TwoTier at 0.47–0.71 % with a tail of 298–456.

**U2(b) — why PF contains the aggressor better.** Not a fairness property of
its ranking. **PF issues ~6× fewer grants** (2,047 vs 12,458) and its
protected flow therefore rides on **5.7× more of them**. PF's containment is
the same grant-pattern effect U1 identified, seen from the other side.

**U3 — why the attach path makes TwoTier worse.** *"Returns locked-out UEs to
contention"* is refined by the trace into something measurable: the attach
path **doubles TwoTier's grants to that UE** (4,641 → 9,727) and **lengthens
the deferral tail from 344 to 456**. More grants, worse tail — the same
monotone relationship. (Note the median worst-flow M06 p95 actually *improves*
slightly, 50.8 → 47.4 ms; the published 14/40 → 40/40 is a count of failing
seeds, so the damage is in the tail across seeds, not in the central value.)

**U4 — G5's residual.** M05 is **0.993–0.997 on all three arms**: after the
lock-out clears there is essentially no residual. **The "4/10" in the task
list is the pre-attach figure**; post-attach it is Reservation 1/10 marginal
and TwoTier 0/10. This item is empty and should not be worked further.

**A secondary reading worth recording:** in the G7 aggressor cell TwoTier's
sort is decided by **declaration order on 14.6 % of adjacencies** (`TIED`),
against 0.3–5.7 % elsewhere. The declaration-order artefact that stopped
G12's ordering being promoted is **most active in exactly the cell G7's
inversion is measured on**.

## 6. What this changes

Nothing in the guarantee verdicts except G12's, which now has none. **The
substantive change is attributional:** four results previously carried as
separate unexplained scheduler behaviours are one mechanism — **grant
frequency interacting with a UE-side LCP that no scheduler can see into** —
and it is not a property of any arm's ranking logic.
