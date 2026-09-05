# Do G4, G5, G10, G12 differ on sensor_dense? — registered before measuring

**2026-09-06.** Follows `docs/sensor-dense-result-2026-09-05.md`, which found
G8's M09 verdict differs by workload and the M01 ranking inverts. **One
instance is thinner than four**, so the rest are attempted here.

## The prediction, and it is not the one that was guessed

**PREDICTION: G4, G5, G10 and G12 are ALL UNSCOREABLE on sensor_dense, and
none of them will differ — because none of them can be read at all.**

**Statistic:** the metric each guarantee binds, and whether it returns a
value or `pending` / `no applicable flow`. **Level:** scoreable vs not, per
guarantee. **Direction:** not applicable — the claim is that no verdict
exists.

**Derived from the scenario's own inventory, measured not recalled:** 30
flows, **all `Delay` class, all 5QI 1, one flow per UE**, and:

| needed by | sensor_dense has |
|---|---|
| G5's M05/M06 — a flow carrying `frame_id` (`_gen_xr_video`) | **0** |
| G10's M07/M08 — a GBR flow with `gfbr_bps > 0` | **0** |
| G4 — a duty-cycle axis producing silences | **no duty knob; flows are continuous periodic** |
| G12 — ≥ 2 5QI classes to order a first violation across | **1 distinct 5QI** |

**The guessed alternative, recorded because it was reasonable:** that G5
would differ, since M05 is a `min` and this workload has 30 identical flows
rather than a spread. **That reasoning is sound and the premise is false** —
M05 needs PDU-set structure and no flow here has any, so M05 returns
`pending` rather than a value to compare.

**Falsifier:** any of the four returning a scoreable value on this workload.
**If that happens my inventory reading is wrong and the verdicts must be
compared.**

## What the outcome means, fixed now

- **If all four are unscoreable** — the finding is not four verdicts but a
  **coverage gap with a shape**: the workload that exercises the control
  channel and a 15 ms deadline **cannot exercise the GBR, PDU-set,
  post-silence or class-ordering guarantees at all**, and the workload that
  can exercise those cannot produce a latency-critical reading. **Each
  workload covers a disjoint subset**, and no single workload in this
  repository can score the full guarantee set.
- **If some are scoreable and agree with the parametric mix** — §0.1's
  "the ranking does not generalise" is weaker than G8's single instance
  suggested.
- **If some are scoreable and differ** — that is the four-instance evidence
  §0.1 has been asserting without.

**A modified sensor_dense is explicitly NOT the answer here.** Adding GBR or
`xr_video` flows to it would make it a third workload, not sensor_dense, and
would break the comparison to `scheduler-study.md` §7.2 that made it worth
running. **If a variant is wanted it is its own decision.**
