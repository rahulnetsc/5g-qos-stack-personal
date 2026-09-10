# TwoTierProto E2 — registered before the run

**2026-09-10.** E2 aims FIX-2's reserve at followers whose buffer report has
gone stale, instead of at every follower with an unmet obligation. Written
before any E2 number existed. E1's result is
`docs/proto-e1-result-2026-09-10.md` — negative, boundary unchanged.

---

## 1. The edit

The reserve exists so a UE the gNB has stopped serving still gets a grant and
therefore still reports. **Reserving band for a follower whose report is already
current spends PRB on information the gNB holds.** E2 keeps the reserve only for
followers whose report is stale.

**Stale is DERIVED, and which derivation is forced by an architectural
boundary.** The BSR periodicity is the natural quantity and is **unreachable**:
the timer lives in `sim/bsr.py`, `scheduler/` must not import `sim/`, and a real
gNB cannot read a UE-side constant either. So the threshold is **the tightest
PDB among the UE's currently-backlogged logical channels**, read through the
port's own `_ul_best_pending_pdb_ms` — the same helper Tier-1.5's floor uses.
A report older than the deadline of the tightest flow it describes cannot be
relied on for that flow.

**Age is a proxy and is stated as one:** `_last_ul_grant_slot[ue_id]`, which
`TwoTier` already keeps, is when the gNB last had the chance to refresh the
report, not the report's own timestamp. **A UE never granted has no report and
is maximally stale**, which keeps the reserve pointed at the UE it was built for.

Same seam as E1, so the same exactness holds: `B_eff` unchanged, ranking
untouched, both pinned as arithmetic in `sim/tests/test_two_tier_proto.py`.

## 2. HOW E2 DIFFERS FROM E1 IN A WAY THAT MATTERS FOR THE PREDICTION

**E1 was inert below eleven followers by construction. E2 is not.** Its
condition is per-follower freshness, not band feasibility, so it acts at *every*
fleet size. **That makes E2 the first edit that CAN move G3's boundary — and
equally the first that can move it DOWN.**

## 3. Predictions

| # | prediction | falsifier |
|---|---|---|
| **P-E2-a** | **No cell is bit-identical to the faithful arm**, including N ≤ 10, because freshness does not depend on the band fitting | any identical cell at any N |
| **P-E2-b** | **The boundary stays at 7 or falls below it.** In a busy cell most backlogged UEs are granted often, so most reports are fresh and most reserves are suppressed — E2 approaches greedy at all fleet sizes, and E1 already showed greedy costs breadth | a boundary above 7 |
| **P-E2-c** | **The same breadth-for-depth trade as E1, starting lower**: worst silence down, pass counts down | both moving the same way |
| **P-E2-d** | **`e2_current_suppressed` greatly exceeds `e2_stale_kept`** — the mechanism's own premise is that most followers do not need the reserve. If the reverse holds, the premise is wrong and E2 is close to a no-op | stale_kept ≥ current_suppressed |

**If P-E2-b holds in its "falls below" form, that is a second elimination and a
positive statement**: the reserve is not merely irrelevant to the boundary, it
is load-bearing *for* it, and both edits that weaken it make the clause worse.

## 4. Grid

Identical to E1's so the three arms are directly comparable: GT-2.2 fleet axis
`n_ues ∈ {4,6,7,8,10,12,14,16,24}`, `ProtoE2` only, cap 4, 10 paired seeds,
40 000 slots, **90 runs**, artefact `sweeps/g3-proto/g3_proto_e2.json`.

**No regression pass unless E2 improves G3.**
