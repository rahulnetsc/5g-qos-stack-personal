# TwoTierProto E2 — result: it improves G3, and it is MISLABELLED

**2026-09-10.** Registered in `docs/proto-e2-registration-2026-09-10.md` before
the run. Artefact `sweeps/g3-proto/g3_proto_e2.json`, 90 runs, 230 s, compared
against `sweeps/g3-stress/g3_stress.json`'s TwoTier column on 90 paired cells.

**Two results, and the second reinterprets the first.** E2 improves G3
substantially. But its own counters show it is **not** targeting stale reports —
it suppresses **99.8–100 %** of the reserve at every fleet size, so what was
measured is *"remove the reserve always"*, not *"reserve for the needy"*.

---

## 1. The measured improvement

| N | p1 f→p | p1s f→p | p2 f→p | p3 f→p | worst silence f→p | short f→p |
|---|---|---|---|---|---|---|
| 4 | 10→10 | 10→10 | 10→10 | 10→10 | 102.8 → 103.5 | 0 → 0 |
| 6 | 10→10 | 10→10 | 10→10 | **10→9** | 165.5 → **319.5** | 0 → **4** |
| 7 | 10→10 | 10→10 | 10→10 | 10→10 | 159.0 → 156.2 | 0 → 0 |
| 8 | **9→10** | **8→10** | **9→10** | 10→10 | 3 077.2 → **282.5** | 50 → **2** |
| 10 | **7→9** | **7→8** | **8→10** | **6→10** | 5 248.0 → **1 074.8** | 163 → **17** |
| 12 | **3→9** | **2→9** | **4→10** | **1→10** | 9 178.2 → **1 472.5** | 600 → **18** |
| 14 | **8→9** | **7→9** | **7→10** | **2→3** | 9 205.2 → **843.2** | 359 → **232** |
| 16 | **9→2** | 2→2 | **2→10** | 4→3 | 9 505.8 → **926.2** | 823 → **381** |
| 24 | **9→2** | **7→1** | 7→5 | **0→2** | 9 099.8 → **5 083.5** | 356 → **424** |

| | faithful | ProtoE2 |
|---|---|---|
| part-1 boundary | 7 | **8** |
| part-1s boundary | 7 | **8** |
| part-2 boundary | 7 | **16** |
| **part-3 boundary** | **8** | **4** — a regression |
| silences ≥ 2 s over the axis | 26 | **5** |
| telemetry messages short | 2 351 | **1 078** |

**The middle of the axis transforms** — at 12 robots part 3 goes 1 → 10 and the
worst silence falls 6.2×. **Campaign-wide silences fall 5.2×.**

**Two regressions, reported not smoothed.** Part 3's boundary falls 8 → 4 on a
**single seed at N = 6** (10 → 9, worst silence 165 → 320 ms, four messages
lost); under the standing boundary rule one failure at 6 drags it to 4 even
though N = 7 through 12 are all 10/10, so this is non-monotone. And the top of
the axis still degrades — part 1 falls 9 → 2 at N = 16 and N = 24, the same
breadth-for-depth trade E1 showed.

## 2. THE REINTERPRETATION: E2 is not what its name says

Its own classification counters, per run:

| N | followers classified | **current → suppressed** | stale → kept |
|---|---|---|---|
| 6 | 97 677 | **97 677 — 100.0 %** | **0** |
| 8 | 166 972 | **166 972 — 100.0 %** | **0** |
| 12 | 311 156 | 311 110 — 100.0 % | 46 |
| 24 | 631 904 | 630 689 — 99.8 % | 1 215 |

**The staleness test essentially never holds.** A qualifying follower has
`gbr_bytes_slot > 0`, which requires being backlogged with an unmet GBR
obligation — and such a UE is a candidate nearly every slot, so it *is* granted
inside its own PDB. "Current" is almost always true, so the reserve is almost
always suppressed.

**So E2 measures "no reserve, ever", and the sophisticated name is doing no
work.** `P-E2-d` predicted `current_suppressed` would greatly exceed
`stale_kept` and it does — but the consequence is not the one that framing
implied: at 100 % the edit stops being selective and becomes removal.

**And that is exactly what makes E1 and E2 together informative.**

| edit | what it actually does | part-1 boundary |
|---|---|---|
| **E1** | removes the reserve **only above 11 followers** | **7** — unchanged |
| **E2** | removes the reserve **essentially always** | **8** |

**So the reserve costs liveness at the fleet sizes AROUND the boundary — 8 to
14 robots — where it fits and is therefore applied in full.** E1 missed that by
construction, because it only acted where the reserve had already saturated.
**The reserve is not irrelevant to the boundary; it is harmful just below it and
protective just above it**, which is why one edit moved the boundary and the
other did not.

## 3. What follows, and what this does NOT license

**E2 should not be landed as written.** A flag named for stale reports that
suppresses 100 % of the reserve is a mislabelled control, and a future reader
would take its improvement as evidence for report-targeting when it is evidence
for removal.

**The edit the evidence points at is a BOUNDED reserve** — reserve for at most
`floor(prb_count / min_rb) - 1` followers, chosen by need, rather than all or
none. That would keep the anti-monopolisation protection where it fits and drop
it where it cannot, and it is a third edit with its own registration.

**The natural control is now cheap and was not run:** a literal
reserve-always-off arm. E2's counters say it would land within 0.2 % of E2, and
confirming that is one 90-run pass.

**No regression pass has been run.** E2 earned one by improving G3, but
**proving a mislabelled edit safe elsewhere spends the budget on the wrong
configuration** — and the exposure is predictable from what E2 really is:
removing the reserve removes the anti-monopolisation protection that a real
production incident motivated, so the guarantees at risk are the isolation and
video ones (G7, G5), neither of which is in the named regression set.
