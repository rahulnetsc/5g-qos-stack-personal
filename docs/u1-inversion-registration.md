# U1 — the workload inversion: registration

**Registered 2026-09-06, before any run.** Closed map. If the data fits no
registered outcome it is reported as a **residual**, not fitted.

---

## 1. The observation

TwoTier's M01 p98 over protected flows:

| workload | PF | Reservation | **TwoTier** | PDB | TwoTier as fraction of budget |
|---|---|---|---|---|---|
| parametric mix | 25.25 | 23.00 | **87.78 ms** | 100 ms | **0.878 — worst** |
| `sensor_dense` | 13.50 | 14.25 | **11.00 ms** | 15 ms | **0.733 — best** |

**The inversion survives normalisation**, which is the first thing to check
and is checked here rather than assumed: the two workloads have different
PDBs (100 vs 15 ms), so an absolute-millisecond comparison across them is the
achievable-ceiling error this project has already recorded three times. As a
fraction of its own budget TwoTier is still worst on parametric (0.878 vs
PF's 0.253) and still best on `sensor_dense` (0.733 vs PF's 0.900). **The
effect is real and is not a units artefact.**

## 2. The candidate under test

*"Tier-1's objective favours periodic flows over saturating ones."*

TwoTier's UL rank key is `(sched_inactive, floor_fire, -floor_sil, -coef)`.
The first three are coarse gates; **`coef` is where ranking actually
happens**, and it decomposes exactly:

```
coef = (base_q + urg) * hyp_tbs_bytes
```

| factor | what it is | which candidate it corresponds to |
|---|---|---|
| `base_q` | Σ `vq_ul` over the UE's LCGs — **Tier-1's virtual queue**, i.e. the objective's output | **the registered candidate** |
| `urg` | `W · φ(urgency01) · norm` — the delay/PDB term, `norm` = slot max `base_q` | competing: a deadline effect |
| `hyp_tbs_bytes` | achievable TB size — the channel/rate term | competing: channel opportunism |

`norm` is a slot-level maximum common to every candidate, so it **cancels**
between any two and cannot itself be decisive.

## 3. The instrument

The existing rank-trace hook (`scheduler/rank_trace.py`), not a new probe.

**First-difference alone is insufficient here and saying so in advance is the
point:** on UL the first three terms are gates, so `decisive_term` will
return `-coef` on nearly every adjacent pair and discriminate nothing. That
is what `_UL_FACTORS` was carried for (the map's L5/L6/L7 distinction).

**The attribution rule — a swap test, registered before the data.** For each
adjacent (winner `w`, loser `l`) pair at a loss point of the flow that drives
M01 p98: for each factor `f ∈ {base_q, urg, hyp_tbs_bytes}`, recompute `l`'s
coef with `f` replaced by `w`'s value. If the recomputed coef ≥ `w`'s, `f` is
**sufficient** to explain that loss. Report the full joint distribution —
including "none singly sufficient" and "all three" — rather than forcing a
single winner.

## 4. Gate A0 — a blocking pre-flight, and it can invalidate the instrument

**M01's worst protected flow on the parametric mix may be a DL flow.** The
mix carries both directions; `sensor_dense` is UL-only. If the parametric p98
is set by DL, then a **UL** rank trace is measuring the wrong direction, and
no amount of it answers the question — this project's own rule about a check
operating at the level the failure occurs at.

**A0 runs first and its result is reported whatever it says.** If the worst
flow is DL, the instrument changes to the DL key
`(has_gbr, pdb_ms, -coef)`, whose `coef` decomposes differently, and this
registration is amended **before** any trace is read.

## 5. Registered outcomes — closed

| id | outcome | what the data would show |
|---|---|---|
| **O1** | **Tier-1's objective is the lever** — the candidate is supported | `base_q` is the sufficient factor in a clear majority (≥60 %) of parametric loss points, and is *not* on `sensor_dense` |
| **O1b** | **Tier-1's objective is INERT on `sensor_dense`, and that is why TwoTier wins there** | `base_q` ≈ 0 for all candidates on `sensor_dense` (no GBR flow ⇒ no live target ⇒ `vq_ul` never grows), so TwoTier reduces to `urg × hyp_tbs` — a *different* conclusion from O1: the objective is not favouring periodic flows, it is **absent** |
| **O2** | **A deadline-term effect, not an objective one** | `urg` is the sufficient factor on both, differing in magnitude — consistent with φ's response to a 100 ms vs a 15 ms budget |
| **O3** | **Channel opportunism** | `hyp_tbs_bytes` sufficient on parametric — TwoTier losing where PF's rate-sensitivity wins, a known PF strength |
| **O4** | **Candidate-set composition — a workload property, not a scheduler one** | the sufficient-factor distribution is *the same* on both, and what differs is who is in the candidate set (saturating BE flows present on parametric, absent on `sensor_dense`) |
| **O5** | **No dominant factor** | top factor < 50 %, or the tally is flat — the trace does not identify a lever, reported as such |
| **R** | **residual** | anything not above |

## 6. Falsifier for the registered candidate

**If `base_q` is not the plurality sufficient factor at parametric loss
points, the "Tier-1's objective favours periodic over saturating" story is
not supported by the trace** and is reported as refuted, not softened. O1b is
a *separate* outcome and does not rescue O1: "the objective is absent on the
workload TwoTier wins" is not "the objective favours periodic flows".

## 7. Could this check have failed?

Named because a check that cannot fail is decoration.

- **The instrument has demonstrated dynamic range on a different question.**
  The same hook and `LossPointTally` identified declaration order as G5's
  lever, i.e. it has already returned a non-obvious answer rather than
  confirming the first hypothesis put to it.
- **The swap test is not floored.** All three factors are strictly positive
  and vary across candidates within a slot, so any of them can be sufficient.
- **The two workloads are scored by the same code path**, so a difference
  cannot be a scoring artefact.
- **A0 can invalidate the instrument outright**, and is run first for that
  reason.

## 8. What this cannot license, whatever it returns

It identifies **which factor decides the sort**. It does **not** establish
that the parametric mix is representative of a deployment, nor that
`sensor_dense` is. **The cross-workload comparison rests on three guarantees
only** (coverage matrix, `docs/STATE.md` §4), and two of the three already
differ. A factor-level answer explains the mechanism of the inversion; it
does not tell anyone which workload the client has.

---

## 9. A0 RESULT (2026-09-06, before any trace was read)

**A0 PASSES — the UL hook is the right instrument.** The parametric mix's
protected flows are all UL:

| 5QI | direction | kind | ×UEs |
|---|---|---|---|
| 1 | **UL** | `periodic_control` | 10 |
| 2 | **UL** | `xr_video` | 10 |
| 9 | **UL** | `poisson` — the saturating flow | 10 |
| 82 | DL | `periodic_control` | 10 |

The flow setting M01 p98 is `qfi1` or `qfi2` in every (arm, seed) cell; the
DL flow (5QI 82) never sets it.

**And A0 reframes the candidate, which is why it was worth running first.**
*"Tier-1's objective favours periodic flows over saturating ones"* implicitly
pictures periodic UEs losing to saturating UEs. **There are no saturating
UEs.** Every one of the 10 UEs carries the identical mix — one periodic, one
XR, one saturating UL flow. The sort ranks **UEs**, so it cannot be
expressing a preference between flow kinds across candidates; any inter-UE
`base_q` difference is a difference of *state*, not of composition.

## 10. A0b — a SECOND blocking pre-flight, at a level A0 did not reach

If every UE is compositionally identical, the periodic flow's latency failure
may not happen in the sort at all. **It may happen inside the UE.**

The gNB sees only aggregate per-LCG BSR and **cannot see a UE's intra-TB
per-flow split** (a standing invariant of this repo). A UE that wins its
grant still divides it by UE-side LCP (`sim/ue_lcp.py`). So a 5QI-1 flow can
miss its budget while its own UE is being granted normally — starved by its
saturating 5QI-9 sibling, inside the TB, **where the rank trace cannot see
it**, because the rank trace observes the ranking of UEs.

**A0b, run before the swap test, and reported whatever it says:** for the
worst protected flow on TwoTier/parametric, is its UE

- **(i) rarely a candidate / rarely a winner** → the loss is in the sort, the
  rank trace applies, proceed to §3's swap test; or
- **(ii) granted at a normal rate while its 5QI-1 flow still misses** → the
  loss is **intra-UE LCP**, the rank trace is the wrong instrument for U1,
  and the registration is amended before anything is read.

**(ii) is a live possibility and would be the more interesting answer**: it
would make the inversion a property of how a *saturating sibling* interacts
with LCP under a 100 ms budget — present on the parametric mix, absent on
`sensor_dense`, which has one 5QI and no sibling to lose to. That is registered
outcome **O4** (composition) arriving by a mechanism O4 did not name.
