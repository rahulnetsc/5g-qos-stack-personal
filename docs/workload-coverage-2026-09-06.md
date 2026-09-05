# No single workload can score the guarantee set — the coverage matrix

**2026-09-06.** Scored against `docs/workload-coverage-registration.md`.

**Prediction: G4, G5, G10 and G12 are all UNSCOREABLE on sensor_dense, and
none will differ because none can be read at all. CONFIRMED, by measurement
rather than by reading the scenario file.**

Running the panel on a real sensor_dense record:

| metric | status | value | guarantee |
|---|---|---|---|
| **M05** | ok | **None** | G5 |
| **M06** | ok | **None** | G5 |
| **M07** | ok | **None** | G10 |
| **M08** | ok | **None** | G10 |
| M01 | ok | `{p98: 10.5, …}` | G1 |
| M03 | ok | `{flow: ue21_qfi1, …}` | G3 |
| M09 | proxy | `{worst: 0.989, …}` | G8 |

`ok` with `value=None` is the documented "ran, found no applicable flow"
path — **not a failure, and not `pending`**. G4 and G12 need scenario *axes*
rather than flows: a duty-cycle knob producing silences, and ≥ 2 5QI classes
to order a first violation across. sensor_dense has neither.

**The guess that G5 would differ was well-reasoned and its premise was
false**: M05 is indeed a `min` over flows and this workload is 30 identical
flows, but M05 needs PDU-set structure and **no flow here has any**, so there
is no value to compare.

---

## THE FINDING: each workload covers a disjoint subset

| guarantee | needs | parametric mix | **sensor_dense** |
|---|---|---|---|
| **G1** latency | any Delay flow | ✅ *(100 ms PDB — not latency-critical)* | ✅ **15 ms PDB — the real reading** |
| **G3** liveness | any flow | ✅ | ✅ |
| **G4** post-silence | a **duty-cycle axis** | ✅ | ❌ continuous periodic, no silence |
| **G5** PDU-set | a **`frame_id` flow** | ✅ | ❌ **0 `xr_video` flows** |
| **G6** conjunction | a **background aggressor** | ✅ | ❌ |
| **G7** MFBR | an **MFBR-configured GBR flow** | ✅ | ❌ 0 GBR flows |
| **G8** fairness | any flow | ✅ | ✅ |
| **G10** admissible fleet | **GBR flows + a fleet axis** | ✅ | ❌ 0 GBR flows |
| **G11** soak | a **scripted schedule** | ❌ *(G11 has its own)* | ❌ |
| **G12** class ordering | **≥ 2 5QI classes + a ramp** | ✅ | ❌ **1 distinct 5QI** |

**Three of ten on sensor_dense; seven of ten on the parametric mix; and the
three that overlap are the only ones where a cross-workload comparison is
possible at all.**

### Why this is the stronger result

**§0.1 says the ranking does not generalise across regimes.** The evidence
for that is now:

1. **The M01 ranking inverts** — TwoTier worst of three on the parametric mix
   (87.78 ms), best on sensor_dense (11.00 ms).
2. **G8's M09 verdict differs** — Reservation fails 1/10 seeds on one
   workload and 10/10 on the other.
3. **And the comparison can only ever be made on 3 of 10 guarantees**,
   because the workloads exercise disjoint subsets.

**Point 3 bounds how much evidence §0.1 can ever have from these two
workloads.** Four instances were wanted; **only three guarantees are even
eligible, and two of the three already show a difference.** That is a
stronger statement than four verdicts would have been: **the ranking differs
on two of the three guarantees where it can be tested at all.**

### The gap this names

**No workload in this repository can produce a latency-critical reading of
the GBR, PDU-set, post-silence or class-ordering guarantees.** The parametric
mix scores them at a 100 ms PDB; sensor_dense has a 15 ms PDB and none of the
flows those guarantees need.

**A variant closing the gap is its own decision and is not taken here.**
Adding GBR or `xr_video` flows to sensor_dense makes a third workload, not
sensor_dense, and breaks the comparison to `scheduler-study.md` §7.2 that
made it worth running. **What would be needed is a workload with a tight PDB
AND GBR/PDU-set structure — which is a scenario-design question, not a
measurement.**
