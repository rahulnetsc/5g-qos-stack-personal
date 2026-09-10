# TwoTierProto E1 — result: the reserve is NOT what sets G3's boundary

**2026-09-10.** Registered in `docs/proto-e1-registration-2026-09-10.md` before
the run. Artefact `sweeps/g3-proto/g3_proto_e1.json`, 90 runs, 210 s wall.
Compared against `sweeps/g3-stress/g3_stress.json`'s TwoTier column —
**same seeds, same builder, same scoring code, 90 paired cells.**

**VERDICT: E1 does not improve G3, so no regression pass is owed.** Every
boundary is unchanged, and the campaign-wide silence count moves 26 → 25.

---

## 1. The result

`p1` / `p1s` / `p2` / `p3` are pass counts of 10; `silence` is the worst
observable silence in ms; `short` is telemetry messages missing of 100 per
robot; `identical` counts cells where every scored figure matched the faithful
arm exactly.

| N | p1 f→p | p1s f→p | p2 f→p | p3 f→p | worst silence f→p | short f→p | identical |
|---|---|---|---|---|---|---|---|
| 4 | 10→10 | 10→10 | 10→10 | 10→10 | 102.8 → 102.8 | 0 → 0 | **10/10** |
| 6 | 10→10 | 10→10 | 10→10 | 10→10 | 165.5 → 165.5 | 0 → 0 | **10/10** |
| 7 | 10→10 | 10→10 | 10→10 | 10→10 | 159.0 → 159.0 | 0 → 0 | **10/10** |
| 8 | 9→9 | 8→8 | 9→9 | 10→10 | 3 077.2 → 3 077.2 | 50 → 50 | **10/10** |
| 10 | 7→7 | 7→7 | 8→8 | 6→6 | 5 248.0 → 5 248.0 | 163 → 163 | **10/10** |
| 12 | **3→8** | **2→5** | **4→5** | **1→4** | 9 178.2 → **8 292.8** | 600 → **403** | 0/10 |
| 14 | 8→8 | **7→4** | **7→5** | 2→1 | 9 205.2 → **8 046.8** | 359 → **444** | 0/10 |
| 16 | **9→4** | 2→1 | **2→4** | 4→2 | 9 505.8 → 9 189.5 | 823 → **624** | 0/10 |
| 24 | **9→3** | **7→2** | 7→7 | 0→0 | 9 099.8 → **4 528.5** | 356 → **394** | 0/10 |

| | faithful | ProtoE1 |
|---|---|---|
| **part-1 boundary** | **7** | **7** |
| **part-1s boundary** | **7** | **7** |
| **part-2 boundary** | **7** | **7** |
| **part-3 boundary** | **8** | **8** |
| silences ≥ 2 s over the axis | 26 | **25** |
| telemetry messages short | 2 351 | **2 078** |

## 2. THE FINDING: the reserve is not the boundary mechanism

**Every boundary is identical on all four criteria**, and the reason is visible
in the `identical` column: **N = 4 through 10 are bit-identical to the faithful
arm, and divergence starts exactly at N = 12.** That transition is the gate's
own footprint — `prb_count > min_rb * need` cannot fire until the qualifying
follower count reaches 11, so E1 is inert by construction precisely where the
boundary sits.

**So the prediction put to me holds, in the form it was put:** E1 changes
large-fleet behaviour and leaves G3's boundary exactly where it was. **The most
plausible candidate for what sets the boundary is now eliminated**, and that is
worth more than the improvement would have been, because the boundary is what
decides the clause and no fix can be aimed at it until the mechanism is named.

**What the boundary is NOT:**

- **not the follower reserve** — this result;
- **not the missing deadline term in sizing** — that term is inert behind the
  reserve, and at N ≤ 10 the reserve is not even suppressed, so nothing about
  sizing changed in the cells that decide the boundary;
- **not the UE-side LCP round-1 exhaustion alone** — the prioritised-bit-rate
  control already moved N = 6 without moving the boundary
  (`docs/g3-stress-experiment-2026-09-09.md` §7.1).

**What is left, and it is now the open question.** At N = 8 the first failure
appears with telemetry at 89 of 100 on one robot while the reserve's floor fires
on 10 % of grants and never on the leader. Something else is starving one robot
at eight. The candidates this campaign has not separated are **per-slot UE
admission** (`max_sched_ues = 4`, so twelve of sixteen robots are not even
candidates in a given slot) and **rank persistence** — a robot that loses the
sort consistently rather than occasionally. The bimodal delivery at large fleets
(`3,4,4,5,5,6,7,27, 89,90,93,93,93,94,95,96` on the faithful arm at N = 16)
points at the second, and that is where a next probe should go.

## 3. And E1 is not free: it trades breadth for depth

Above the threshold the result is **mixed, not better**:

- **the worst silence improves**, substantially at N = 24 (9 100 → 4 529 ms, a
  2.0× reduction) and modestly at N = 12 and 14;
- **total shortfall improves**, 2 351 → 2 078 messages;
- **but pass counts get WORSE** — part 1 falls 9 → 4 at N = 16 and 9 → 3 at
  N = 24, part 1s falls 7 → 4 at N = 14 and 7 → 2 at N = 24.

**A coherent reading, offered as a hypothesis rather than a measurement:**
greedy-by-rank gives the leader the band it asks for, so fewer robots are served
per slot; the deepest silence shrinks because the worst-off robot eventually gets
a real grant, while more robots end up moderately starved because the leader
took the room. **That is exactly the monopolisation the reserve exists to
prevent** — so this result is also evidence that the reserve is doing its job,
at a cost, rather than being simply wrong. Separating that from noise needs the
per-robot distribution, which this artefact's projected rows do not carry.

**Which means E1 is not a candidate fix as written.** A version worth testing
would gate on feasibility *and* keep a bounded number of reserves — reserve for
the `floor(prb_count / min_rb) - 1` neediest followers rather than for all or
none. That is a different edit and would need its own registration.

## 4. What this run does NOT license

- **No regression pass was run**, per the revised scope: an edit that does not
  improve its own target does not need proving safe elsewhere. G1, G2, G9, G10
  and G12 are untested against `ProtoE1` and no claim is made about them.
- **The faithful arm is untouched** — `scheduler/two_tier.py` has no diff, the
  published G3 artefact is unchanged, and `verify_claims --check` is 30/0 with
  the Proto arm present.
- **E3's liveness is still unmeasured.** E1 was supposed to be the thing that
  might make a deadline term in sizing live; since E1 is not a candidate fix,
  that question now attaches to whichever edit survives rather than to E1.
