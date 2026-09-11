# G5 — slide source

**Status:** ANSWERED, 2026-09-10.
**Step 0 and registered predictions:** `docs/g5-step0-2026-09-10.md`.
**Artefacts:** `sweeps/g5-video/g5_video.json` (660 runs, three faithful arms,
stamped), `sweeps/g5-video/g5_protoD2C.json` (220 runs, the divergence arm),
`sweeps/g5-video/g5_video.UNCAPPED.json` kept as the before-and-after evidence
for §6's own metric defect.

**In one line:** **G5 fails on both QoS arms and passes on proportional fair**,
and the contract-blind scheduler carries **more than twice** the fleet the
two-tier port does.

**Runtimes:** 660 runs, **687 s wall (11.4 min) on 12 workers**; the divergence
arm a further 220 runs.

---

## 1. The question, in operator terms

**An operator and a perception model both watch the same camera. Do they see
frames that are complete, on time, and fresh?**

Three different properties of one stream, and they fail independently. A feed
can be complete and stale, or fresh and full of holes.

## 2. THE CLAUSE HAS FOUR PARTS, and one had no metric that could fail

> *"≥ 99 % of PDU sets complete within PDB; frame age at MEC p95 ≤ 2 frame
> periods (67 ms); per-feed goodput ≥ GFBR in every 2 s window."* GT-3.1 adds:
> *"and A and B telemetry unharmed."*

| part | bound | note |
|---|---|---|
| **1** sets complete | ≥ 99 % within 150 ms | |
| **2** frame freshness | p95 ≤ **66.67 ms** | DERIVED as two periods at 30 fps, not the sheet's rounded 67 |
| **3** per-feed goodput | ≥ GFBR in **EVERY** 2 s window | **no metric computed this** |
| **4** collateral | telemetry unharmed | a *different* flow class, and it is why a three-part verdict is not enough |

**Part 3 needed a new metric, and the reason is the slide.** `M08` is
`min_f(delivered / GFBR)` — a minimum over **flows** and a **mean over time**.
The clause is a minimum over both. **A run-level 0.99 can contain a 2 s window
at 0.2 and read as a pass**, so M08 could not fail in the way part 3 is meant
to. `M23 windowed_gfbr_floor` was appended to the pre-registered panel for it.

**It earns its place but not as strongly as claimed.** Over 360 fleet-axis
rows, M23 reads strictly worse than M08 on **304**, and flips an actual verdict
on **2**. The run-level number is optimistic almost everywhere and rarely
changes the answer.

## 3. THE RESULT — PF passes, both QoS arms fail

GT-3.1 fleet axis, passes of 90:

| | PF | Reservation | TwoTier | Proto |
|---|---|---|---|---|
| part 1, sets complete | **76** | 50 | 24 | 61 |
| part 2, frame age | **72** | 51 | 20 | 14 |
| part 3, windowed goodput | **37** | 27 | 8 | 5 |
| part 4, telemetry unharmed | **90** | 56 | 40 | **90** |
| **admissible fleet, parts 1-2** | **14** | 10 | **6** | 12 |

**TwoTier collapses at seven robots — one below the fleet size G10 certifies it
for** — and by ten robots fails all four parts including the telemetry it
exists to protect. PF holds to fourteen and never loses a single telemetry cell
anywhere on the axis.

## 4. THE CEILING — GT-3.2, and it is the deliverable the plan calls P0

Stepping the whole committed portfolio ×1.0 → ×1.5:

| load | PF | Reservation | TwoTier |
|---|---|---|---|
| ×1.0 – ×1.2 | pass | pass | pass |
| **×1.3** | pass | pass | **1 of 10** |
| **×1.5** | **pass** | **pass** | 0 of 10 |

**No ceiling exists inside the swept range for PF or Reservation** — both carry
1.5× the committed portfolio with no failures, which refutes prediction
P-G5-d. **TwoTier's knee is ×1.2.** So the deployment's committed rates are
safe on two arms and **20 % over-subscribed on the third**.

## 5. GT-3.3 — containment holds, and a different fault appears

Every arm keeps its camera parts at a degraded neighbour, so **cross-asset
containment holds**, which is GT-3.3's hard criterion. But **part 4 goes to
zero on all three arms at −6 dB and −3 dB**: a cell-edge robot's own telemetry
dies. That is common to every arm, so it is **not a scheduler difference** — it
is a statement about what a cell edge costs the robot standing in it.

## 6. A METRIC DEFECT CAUGHT BY AN IMPLAUSIBLE RESULT

**Part 3 failed on 9 of 10 seeds at FOUR robots on PF** — a configuration with
ample spare capacity. That is not a believable result, so the offered load was
checked per window before it was reported:

```
 w   offered B  delivered B  off/need  del/need  del/off
 2     1027432      1027432    1.0274    1.0274   1.0000
 3      983407       983407    0.9834    0.9834   1.0000
```

**The network delivered every byte offered and window 3 still scored a
failure.** The camera is a variable-frame-size source sized to its contract on
*average*, so its offered load moves a few percent either side of it in any one
window. Uncapped, `delivered / (GFBR × window)` fails about half the windows of
a perfect run.

**This is the repo's own offered-shortfall defect one level down** — a
contract-reading metric measuring the traffic generator rather than the
scheduler. The clause's meaning fixes it: a guaranteed-rate contract obliges the
**network** to carry up to the rate, not the application to send it. The
denominator is now `min(offered, GFBR × window)`, and the under-offering is
reported beside the value rather than silently forgiven.

## 7. THE PREDICTIONS, SCORED

| | registered | outcome |
|---|---|---|
| **P-G5-a** | part 3 fails where M08 passes | **HELD, weakly.** Strictly worse on 304 of 360 rows, verdict flipped on 2 |
| **P-G5-b** | part 2 fails first as the fleet grows | **HELD** on the QoS arms; parts 1 and 2 fail together at N = 7 on TwoTier |
| **P-G5-c** | PF passes 1-3 where the QoS arms fail, and fails part 4 | **HALF RIGHT.** The first half holds decisively; PF is **perfect** on part 4, 90 of 90 |
| **P-G5-d** | the ×1.5 knee exists on all three arms | **REFUTED.** Only TwoTier has one, at ×1.2 |
| **P-G5-e** | part 4 fails where 1-3 pass, making the four-part verdict stronger | **HELD** — Reservation at N = 12 passes nothing else and still shows 6 of 10 on part 4, and GT-3.3 fails part 4 alone at the cell edge |

**Two of five refuted or half right.** P-G5-d is the one that matters
operationally: the cell has more headroom than expected on two of three arms.

## 8. THE DIVERGENCE ARM, and the one thing it cannot fix

The proto arm reaches **90 of 90 on telemetry** and 61 on completeness against
the port's 40 and 24 — and is **worse on frame age**, 14 against 20.

**Every proto variant tried is behind the port on freshness while ahead on
everything else**, and the cause was isolated: removing the spatial reserve
costs the whole regression, the reordering adds nothing. A multi-fragment frame
needs the steady trickle a per-follower minimum provides; a 300-byte heartbeat
does not. Bounding the reserve instead of removing it recovers most of it and
**does not close it**.

## 9. WHAT THIS DOES NOT SAY

- **No claim is registered yet** — G5 publishes nothing into
  `config/published_claims.yml` while the 22 stale stamps are open
  (`docs/deferred-tasks.md` §2).
- **This is a RAN result, not end-to-end.** The plan gates GT-3 on a smoke test
  because the radio can deliver while nothing reaches the core; **this
  simulator has no N6 leg**, so the 5QI-4 blackhole is annotated rather than
  tested.
- **The Proto arm is a labelled DIVERGENCE**, and its write-up is deferred
  (`docs/deferred-tasks.md` §3).
