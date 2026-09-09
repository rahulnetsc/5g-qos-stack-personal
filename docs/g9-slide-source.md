# G9 — slide source

**Status:** ANSWERED as a stress experiment, 2026-09-08.
**Full record:** `docs/g9-stress-experiment-2026-09-08.md` (453 lines).
**Artefact:** committed at `548c0b0`. Suite 1238, `--check` clean.

**The previously published G9 rows are WITHDRAWN** — produced with
`--rejoin-seed` on and undeclared, on artefacts predating M-9 and M-6.
Nothing here inherits from them.

---

## 1. The question, in operator terms

**If the cell is already busy, will a newly connecting robot start working
correctly and immediately?**

Formally: warm re-handshake, cold attach-to-streaming, post-RLF
time-to-SLO, and neighbours unaffected throughout.

---

## 2. The experiment

**Axis:** cell occupancy — UE count and offered load (`committed_mult`)
together, since an operator experiences them as one thing. Range set by
G10's measured boundary rather than assumed.

**Grid:** 2 seed-columns × 3 scenarios × 6 occupancy levels × 3 arms ×
10 seeds, each run building its paired control. **1,080 rows = 2,160
driver runs.**

**Two sub-experiments, both reported:**
- **A** — time to first service (the join itself)
- **B** — time to a stable cell (the settling period, incumbents included)

**Baseline sanity gate:** a pre-join window on incumbents gives three
outcomes per point — PASS, JOIN FAILURE, or CELL ALREADY BROKEN. The last
is a result an operator needs, not a skipped cell.

**Thresholds:** derived from TS 22.104's availability rule (unavailable
when latency exceeds PDB + survival_time), not invented. Cold attach keeps
the plan's 15 s. `survival_time_ms` derived per flow from its own transfer
interval; the TS 22.104 table could not be obtained (ETSI 403), so the
definition was transcribed from the locally-held TS 122 261 and the
multiplier `n` is chosen and swept.

**Yield rule:** 9 of 10 seeds pass AND no failing seed is catastrophic.

---

## 3. The results

| scenario | PF | Reservation | TwoTier |
|---|---|---|---|
| **Warm re-join** | 0.000 s | 0.000 s | 0.000 s |
| **Cold attach** | ~100 ms, flat across a 4× load range | ~100 ms, flat | **fails at 5–6 UEs** |
| **Post-RLF** | ~1.1 s | ~1.1 s | **no seed recovers at 6 or 8 UEs** |

**Margins on the passing arms:** cold attach is **150× inside** the 15 s
bound; post-RLF is **9× inside** the 10 s bound.

**TwoTier's failures:** half the cold attaches never complete at 6 UEs;
after an RLF at 6 or 8 UEs **not one seed recovers**.

**PF's cell breaks at 8 UEs × 2.0 while its joins keep working** —
reported as CELL ALREADY BROKEN, not JOIN FAILURE, which is exactly the
distinction the gate exists to draw.

---

## 4. Deployment consequence

**On PF and Reservation:** a robot joining a busy cell starts working
essentially immediately, with two orders of magnitude of margin. Adding a
robot mid-shift is safe.

**On TwoTier:** at 6 robots, half of cold attaches never complete — a
robot powers on and does not register. And after a radio-link failure at
6 or 8 robots, **it does not come back at all.** In a factory that is a
robot that stops and stays stopped until someone intervenes.

**And the fleet-size interaction:** G10's admissible boundary is 5–6
robots. TwoTier's join failures begin at exactly that point, so the two
limits coincide rather than compounding.

---

## 5. Two findings worth more than the pass/fail grid

**The neighbours clause is not testable as written.** Over 540 runs, the
fraction whose worst incumbent p98 moved by no more than ε:

| ε | runs within |
|---|---|
| 0.5 ms | 184 / 540 (34 %) |
| 1.0 ms | 217 / 540 (40 %) |
| 2.0 ms | 266 / 540 (49 %) |
| 5.0 ms | 408 / 540 (76 %) |

**At 0.5 ms the clause fails on two runs in three; at 5 ms it passes on
three in four. Nothing about the system changed between those rows — only
the number the plan does not state.** Every ε is reported; no neighbours
verdict should be quoted without its ε beside it.

**And the rejoin seed is nearly retired.** Outcomes identical on 53 of 54
cells, and TwoTier is no longer degenerate unseeded — before Build 1 the
guard refused to score it at all. It still rescues TwoTier at exactly its
boundary. Disposition: keep, default off, declared as data on every row
that uses it.

---

## 6. What Step 0 corrected before any number was read

**The control-plane floor was hardcoded off.** Build 1.2 concluded the
two-tier arm has no SRB ranking tier; that was wrong, and the error was a
**wrong file** — `has_srb` was grepped in `gNB_scheduler_ulsch.c`, which is
not this arm's UL scheduler. `ia_p5g_scheduler.c:2778-2783` promotes any UE
with LCG-0 bytes to the control-plane class under a different field name
(`srb_pending_bytes → srb_floor → sched_inactive`).

**Four readers of that state; two were wrong once the tier went live** —
the `max_q` urgency normaliser and grant sizing. Neither would have shown
in a test of the comparator alone.

**And it was not an SRB story.** `cp_floor` = `B > 0 && data_lcg_bytes == 0`
is precisely the BSR-desync fault of defects-log #24/#25 — the SR floor
putting bytes on `bytes_reported` while the per-LCG array reads zero. **The
C rescues that UE; this port never did.** It fires 6 / 24 / 92 times at
N = 4 / 8 / 16 **with no SRB traffic at all**.

Deliberate re-baseline: **1,905 corpus values move, every one TwoTier**;
PF, Reservation and RoundRobin byte-identical. `sensor_dense` UL
utilisation **0.633 → 0.822**.

**G10's boundary re-measured on current code: unchanged at 6 / 6 / 5.**
> **SUPERSEDED 2026-09-09 — that line is a G10 number and G10 has since moved
> twice.** It was true of the code G9 ran on; the GBR offered-shortfall fix
> (`docs/gbr-offered-shortfall-2026-09-08.md`) landed afterwards and the
> boundary is now **PF 12 / Reservation 6 / TwoTier 7**, re-measured again
> 2026-09-09 (`sweeps/g1-stress/g10_remeasure_cap4.json`). **G9's own rows
> above are unaffected** — none of them reads a GBR contract.

---

## 7. Process notes worth carrying

- **A near-miss on G10:** `M07_met` is a count, and truthiness-testing it
  made every arm pass to N=16. Re-scoring the *old* artefact with the
  *same* code reproduced the published table exactly — that check is what
  made the comparison trustworthy.
- **The manipulation guard conflated two things** — a mechanism that never
  fired (unwired, abort) with one that fired and did not finish (a measured
  stall at overload, which is the answer the experiment exists to produce).
  Split along the firing-vs-finishing line.
- **The campaign was restarted from scratch** at 175/1080 after finding the
  handshake pair's fire-once sentinel derived a 1e9 ms survival time. It
  could not have changed a number, but the artefact would have spanned two
  code versions.

---

## 8. Open external inputs

- **The neighbours ε** — on the spec-findings list for the test plan's
  owner, with G6's missing estimator and G7 c1's unspecified ε.
- **TS 22.104's survival-time table** — requested; ETSI 403, no local copy.
- **The SRB capture** — requested; until it arrives, the SRB cadence is
  chosen rather than measured.
