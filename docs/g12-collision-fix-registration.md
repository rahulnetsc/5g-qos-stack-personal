# G12's flow collision — fix and re-score: registration

**Registered 2026-09-06, before the fix is written or anything is run.**
Closed expectations. Anything not registered is reported as a residual.

---

## 1. What is actually wrong — and it is worse than defects-log #30 recorded

**#30 said a flow was dropped from the record. That is true and it is the
smaller half.** `sim/buffer.py::BufferModel` keys **every** structure on
`(ue_id, qfi)` with **no direction**, and `register()` **overwrites**:

```python
def register(self, ue_id, qfi, is_ul=False, lcg=-1):
    key = (ue_id, qfi)
    self._buffers[key] = BufferState(lcg=lcg)     # second call REPLACES
```

In `drone_heavy` at n=8 the flood UE carries **both**:

| flow | direction | offered |
|---|---|---|
| `ue8_qfi9` (from `build_fleet`) | **DL** | **2 kbps** |
| `ue8_qfi9` (the appended flood) | **UL** | **50 Mbps** |

The flood registers second, so the surviving `BufferState` is the **UL** one
with `is_ul=True`, and **both flows enqueue into it**. Consequences, all
mechanical:

1. The DL flow's eligibility gate reads `bytes_reported`, which for a
   BSR-managed buffer is written only by `BsrModel` — i.e. **by the UL
   flood**. The 2 kbps DL flow was therefore eligible essentially always,
   carrying a **50 Mbps phantom backlog**.
2. `drain()` is also `(ue_id, qfi)`-keyed, so **DL grants drained the UL
   flood's bytes.**
3. Those bytes were credited to whichever record survived (the flood's).

**So the published `drone_heavy` cell did not merely mis-report; it simulated
a queue that does not exist.** This corrects #30's own framing, and the
correction matters because the two halves are wildly different sizes — see §3.

**Scope: `drone_heavy` only.** `mixed`, `ugv_heavy` and `sensor_dense` have no
colliding pair (checked across all four compositions).

## 2. The fix

Give the appended flood its own 5QI — the user's instruction and the
`sim/fleet.py` precedent (5QI 85 → 86).

**5QI 8, with `priority_level` PINNED to 90.** 5QI 8 and 9 are the same
standardised non-GBR class — **PDB 300 ms, PER 1e-6** — differing only in
priority level (80 vs 90), and the flood already declares `flow_class="PF"`,
`pdb_ms=300.0` and `lcg=6` explicitly. Pinning the one remaining derived
field makes the change **purely de-aliasing**.

**This is deliberately stricter than the 86 precedent**, which let priority
(21 → 18) and LCG (3 → 7) move: there the flow is a diagnostic pair that is
off by default, here it is the workload's own background flood and a re-score
must not be confounded by a priority change.

## 3. What I expect — and the two halves are different sizes

**THE RECORD-LOSS EFFECT IS NEGLIGIBLE. THE SHARED-BUFFER EFFECT IS NOT.**
Naming this in advance because #30 conflated them and I am correcting myself:

- **The dropped record** is a **2 kbps** DL poisson flow. Against a published
  background figure of **11.6 Mbps** that is **0.02 %**. Restoring it to the
  denominator, on its own, changes nothing anyone would notice.
- **The shared buffer** let DL grants drain a 50 Mbps UL queue for the whole
  run. That is the effect worth measuring.

### Registered expectations

| id | expectation | why |
|---|---|---|
| **E1** | **Clause 4's qualitative direction SURVIVES**: telemetry M02 reaches 1.000 while 5QI 9 still carries multi-Mbps. | 11.6 Mbps against a floored flow is not a margin one 2 kbps flow reverses. |
| **E2** | **Telemetry gets WORSE OR EQUAL, never better.** | Telemetry (5QI 1) is **UL in every composition**. The collision let DL grants bleed bytes out of the flood's queue, so telemetry faced a **weaker** UL flood than the workload specifies. Removing that makes the flood compete **harder** in UL. |
| **E3** | **The recovered background figure MOVES BY MORE THAN 0.02 % AND LESS THAN 2×**, and stays multi-Mbps. | The record restoration is 0.02 %; the de-aliasing removes ue8's former DL contribution while raising its UL delivery. Sign not predicted — the two push opposite ways, and pretending to a sign here would be a story. |
| **E4** | **`mixed`, `ugv_heavy` and `sensor_dense` are BIT-IDENTICAL to the published run.** | They have no colliding pair, so the fix must not touch them. |
| **E5** | **The relabel is behaviourally inert.** Verified directly: apply it to a **non-colliding** composition and require bit-identical `RunRecord.to_dict()`. | If anything else keys off `qfi` behaviourally, this fires. |
| **E6** | **Flow count 30 → 31 in `drone_heavy`; the restored DL record shows ~2 kbps offered and delivery ratio near 1.0.** | It is a tiny flow with no competitor once de-aliased. |

### Falsifiers, stated so they cannot be explained away afterwards

- **If E2 fails — telemetry IMPROVES after the fix — then the published
  clause-4 failure was partly the collision**, and G12's headline finding is
  weaker than reported, not merely mis-figured. **This is the outcome that
  would matter most and it is the reason to run this rather than assume.**
- **If E4 fails**, the fix is not scoped to the colliding pair and the whole
  re-score is confounded; stop and report rather than scoring.
- **If E5 fails**, the relabel is not a relabel; stop.

**Could these checks fail?** E4 and E5 are byte-equality against artefacts
that already exist, so yes, trivially. E2 is a directional claim on a
statistic that is **not** saturated at the ramp bottom (M02 runs 0.009–0.068
at ×1.0 on TwoTier), so it has room to move either way.

## 4. The category question — asked because #28's guard now exists

**Sweep every scenario builder in the repo for a UE carrying the same 5QI in
both directions**, after the fix, not before. This was swept when the guard
landed and found none; G12's collision was found later by the re-run, which
means the earlier sweep did not cover the parameterised builders. **Confirm,
do not assume** — and report the sweep's coverage as well as its result, since
a sweep that missed `build_g12_scenario` once can miss another.

## 5. What this changes if it all lands

The count goes **ten → eleven** guarantees with a verdict. G12 is the only one
whose verdict was lost to a **defect** rather than to a structural reason, so
it is the only one a fix can restore.
