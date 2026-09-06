# Registered, NOT investigated — is G7's inversion partly the declaration-order artefact?

**Logged 2026-09-06. No work done on this, deliberately.** Recorded now
because the observation arrived free with another trace and would otherwise be
lost, and because registering a question before anyone has an answer is the
only way its eventual answer means anything here.

---

## The observation

From `sweeps/rerun-2026-09-06/traces.json` (the rank stream, captured for a
different question), **TwoTier's UL sort is decided by declaration order —
adjacent candidates fully tied on every key term — on:**

| cell | TwoTier's `TIED (declaration order)` share |
|---|---|
| **G7 aggressor** | **14.6 %** |
| attach control | 5.7 % |
| attach | 0.8 % |
| G5 residual | 0.3 % |

**14.6 % against 0.3–5.7 % elsewhere — the artefact is 2.6× to 49× more
active in the aggressor cell than in any other cell traced.**

## Why it is worth a registered question rather than a shrug

**This is the same artefact that stopped G12's ordering being promoted.**
`docs/wp9-regime-map.md`'s G12 row records the registered control that
settled it: permutations 101/102/103 give `[2,4]` on all 5 seeds and
**permutation 104 gives `[4,2]` on all 5** — a deterministic function of
flow-list position with no physical referent. On that evidence G12's ordering
was **not promoted to a scheduler property**.

**And it is most active in exactly the cell G7's inversion is measured on.**
G7's clause-2 failure (both QoS arms deliver 2.0–2.1× MFBR while PF contains
at 1.05×) is a headline result. If a seventh of TwoTier's ranking decisions in
that cell are settled by declaration order, then part of what is being
attributed to the scheduler's ranking is attributable to the order flows
happen to appear in a list.

## The question, stated so it can be answered rather than argued

> **Does G7's inversion survive a flow-list permutation?**

The discriminator is the one G12 already used and which already exists:
permute the declaration order at the G7 aggressor cell, hold seeds and
provisioning byte-identical, and re-measure clause 2 on each arm. **If the
2.0–2.1× MFBR delivery and PF's 1.05× containment are stable across
permutations, the artefact is present but not load-bearing and G7's result
stands as attributed. If they move, part of G7's inversion is the artefact.**

## What must NOT be concluded from the 14.6 % on its own

**A tie rate is not an error rate.** A tie only matters if the two tied
candidates would have been treated differently, and nothing here establishes
that. **This registration records an elevated rate and a question, not a
finding** — and it is written this way specifically so that a later reader
does not cite "14.6 % declaration order" as though it were already a defect in
G7. On the current evidence it is neither confirmed nor excluded.

## Interaction with the mechanism that IS established

`docs/grant-density-mechanism-2026-09-06.md` explains PF's containment
**without** appealing to this: PF grants ~5.8× less, so its protected flow
rides on 5.1× more grants. That explanation is measured across 12 cells
(ρ = +0.79, p = 2.8e−27) and does not depend on tie behaviour.

**So the two are additive candidates, not competing ones**, and the same rule
G12's row already carries applies: any future promotion of G7's inversion to a
scheduler property must defeat **both**.

## Status

**OPEN. Not scheduled. Not investigated.** Owner: whoever next has budget for
a permutation control on the G7 cell — it is one control, not a campaign.
