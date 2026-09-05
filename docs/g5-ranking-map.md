# G5's lever — the map, registered BEFORE the hook is built

**2026-09-05. Nothing has been built and no ranking term has been sampled.**
Registered the way the camera question's map was, and for the same reason:
the interpretation must be fixed before the data exists, so a residual can be
reported as a residual instead of a fourth candidate appearing after the
fact.

**Deliverable for the next session: G5's lever isolated, or stated as
unreachable with the reason.**

---

## 0. A SCOPE FACT ESTABLISHED FIRST, because it removes half the map

**G5's subject flow is `qfi 2`, `xr_video`, and it is UPLINK.**

M05 (PDU-set completeness) and M06 (frame age) read
`FlowRecord.frame_completions`, which `sim/messages.py::FrameLedger` populates
only for flows carrying a `frame_id` — and `sim/traffic.py` assigns
`frame_id` only in `_gen_xr_video`. On the parametric mix G5 is measured on,
the inventory is:

| qfi | kind | direction | class | count |
|---|---|---|---|---|
| 1 | `periodic_control` | UL | Delay | 8 |
| **2** | **`xr_video`** | **UL** | **GBR** | **8** |
| 9 | `poisson` | UL | PF | 8 |
| 82 | `periodic_control` | DL | Delay | 8 |

**There is no DL flow with PDU-set structure.** So on this workload:

- **TwoTier's DL key `(has_gbr, pdb_ms, −coef)` cannot decide anything for
  G5** and is **OUT OF SCOPE**. Registering an expectation about it would be
  registering one about a tier that cannot reach the flow.
- **The same is true of Reservation's DL key.**
- G5's lever, if it is a ranking term at all, is a **UL** term.

**AND G5's SUBJECT IS THE SAME FLOW AS THE CAMERA QUESTION'S.** `*_qfi2` is
the camera. G5's M05 (completeness) and G10's M08 (GFBR fraction) are two
statistics on one flow. That is why the candidate-set hook has two real
customers and not one anticipated — and it means **the camera result is
already evidence here**: the severe failures are a *between-UE* effect, not
sibling contention, not retransmission loss.

---

## 1. The terms, per arm, as they actually are in the code

Verified by reading, not recalled.

| arm | UL ranking key | other terms carried on the candidate |
|---|---|---|
| **TwoTier** | `(sched_inactive, floor_fire, −floor_sil, −coef)` | `urgency01`, `gbr_bytes_slot`, `hyp_tbs_bytes`, `ul_total_target_bytes`, `has_gbr`, `pdb_ms` (carried, **not** in the UL key) |
| **Reservation** | `(has_srb, has_gbr, pdb_ms, −coef)` | per-LCG deficit state |
| **PF** | `metric = bits_per_rb / max(1.0, _r_avg[ue])` (`_allocate`, not `allocate`) | `_r_avg` is **one EWMA per UE**, shared across that UE's UL and DL flows. `bits_per_rb` is from the **CQI-visible** SNR — `get_reported_snr_db`, not the true one |

**Two facts about TwoTier's UL key that the map must not assume away.**
`sched_inactive` is hardcoded `False` (no `do_sched`-equivalent signal
exists), so tier 1 can never decide. `floor_fire` requires `mfbr_bps > 0` to
arm — **which is now configured** (`3788202`), so tier 1.5 is live for the
first time and is a real candidate rather than a dormant one.

---

## 2. THE MAP — each outcome's meaning fixed now

Sampled per UL candidate per slot, at the sort, on G5's failing seeds against
passing controls.

| # | outcome observed | meaning |
|---|---|---|
| **L1** | the video flow's UE loses at **`floor_fire`** — another UE's floor fires and outranks it | **the UL service-interval floor is the lever.** A protection mechanism starving the flow it is not protecting. Newly reachable since MFBR was configured, so this would also be a regression window nobody has looked in |
| **L2** | it loses on **`−coef`** with tiers tied | **the composite coefficient is the lever.** Then the sub-question is which factor of it — `urgency01`, `hyp_tbs_bytes`, or the Tier-1 target — and that is a second, narrower read, not a new candidate |
| **L3** | Reservation's video flow loses at **`has_gbr`** | its GBR-deficit accounting has dropped the flow out of the GBR tier — i.e. the deficit was satisfied or reset when it should not have been |
| **L4** | Reservation loses on **`pdb_ms`** | a *tie-tier* decides: 5QI 2's 150 ms PDB against 5QI 1's 100 ms, so telemetry outranks video structurally, on every slot, by configuration rather than by state |
| **L5** | PF's video UE loses on **`_r_avg`** rather than `bits_per_rb` | the shared per-UE EWMA is the lever — and because it is shared across UL and DL, a DL-heavy UE would be de-prioritised on UL for reasons that have nothing to do with UL. **This is a candidate in its own right, named in advance** |
| **L6** | PF loses on **`bits_per_rb`** | channel-driven, not scheduler-driven. Note it is the **CQI-visible** SNR, so at `cqi_delay_slots=8` this is a *stale-CQI* result rather than a link-budget one, and the two are distinguishable by re-reading against the true SNR |
| **L7** | PF's `_r_avg` is at its **`max(1.0, …)` floor** for the video UE | the EWMA has collapsed to the clamp, so the ranking is `bits_per_rb` alone and PF is not proportionally fair for that UE at all — a distinct outcome from L5, and cheap to distinguish |

**Cross-arm reading, registered now.** G5 fails on **Reservation (7/10) and
TwoTier (4/10) and not on PF (0/10)**. If the lever is the same term on both
QoS-aware arms, it is a property of QoS-aware ranking. **If it is a different
term on each, then "concentrate-vs-spread" names a shared *outcome* produced
by two different mechanisms**, and the documented explanation is a
description rather than a cause.

---

## 3. WHAT "UNREACHABLE" LOOKS LIKE — named in advance so it is an answer

| # | outcome | meaning |
|---|---|---|
| **U1** | **every term is tied and the sort falls back to list position** | **the declaration-order artefact again** (`wp9-plan.md` §35.5, G12's confirmed artefact). It is an ANSWER, not a failure: G5's outcome would be a scenario-authoring property with no physical referent, and the same finding that stopped G12's ordering being promoted |
| **U2** | the video flow **is not in the candidate set** in the slots that matter | not a ranking question at all — it is an eligibility question, and the lever is upstream in BSR/SR or the HARQ mask |
| **U3** | the terms separate cleanly on **both failing and passing seeds alike** | the ranking is not what distinguishes them; G5's failure is downstream of the sort — sizing, LCP split, or delivery |
| **U4** | the flow **wins its rank and still misses contract** | the same shape as the camera question's third seed, and it would make G5 and that residual one question rather than two |

**U1 is the outcome that most needs registering, because it is the one that
would otherwise read as "the trace failed".** A tie is a measurement.

---

## 4. Acceptance conditions — and one is harder here than at the grant site

Same three as `sim/trace.py`, with one strengthened:

1. **Bit-identity.** A run with the sink attached produces a byte-identical
   `RunRecord` to one without. The parallelism precedent.
2. **Cost when off**, measured by A/B against the pre-hook build, not argued
   — and measured correctly: the first attempt at this for the grant hook was
   void because `git stash` silently failed on an untracked path and both
   arms ran the same code.
3. **FAILS LOUDLY — AND THIS ONE IS DIFFERENT HERE.** The grant hook is a
   direct call at a fixed call site, so there is no name to bind wrongly.
   **This hook binds by name inside the ranking**, which is exactly the
   `self._ue`-vs-`self._state` failure: a hook that read zero for the
   HEALTHY control too and would have confirmed a hypothesis on no evidence.
   So:
   - each hook **declares the attribute it binds and asserts at construction
     that it exists** — `getattr` with a raise, never a silent `None`;
   - a test asserts the sink receives a **non-empty candidate list on a
     known-active slot, for every arm**;
   - a sink that records nothing **raises** rather than returning zero;
   - and a test asserts the recorded candidate count **matches the number of
     eligible UEs** on a slot where that is independently known — so a hook
     that binds but under-collects fails too.

---

## 5. The park rule

**Anything found that does not make G5 wrong is logged and parked.** That is
the rule agreed for this work, and the evidence it works is the session that
produced this map: one deliverable, met, committed — while the LP
degeneracy, the SCA non-convergence, the seed-count defect, the scenario
horizon defects and five `g12_score` pooling sites were each recorded and
left, rather than chased.

**Explicitly not in scope:** G8, G10, G2, G3's delta, G9, and G11's C2–C5.
