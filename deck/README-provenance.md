# Deck provenance and the artefact risk this file exists to close

`artpark-guarantee-deck.html` is the **client-facing** guarantee deck. It has
no generator: it is hand-authored HTML, so it cannot be rebuilt from the data
and every correction to it is a manual edit.

**It was UNTRACKED until 2026-09-03**, which is the stale-artefact problem
this project already named once, one level up. A corrected client artefact
living only as an unversioned working file has no history, no diff, and no
way to tell which corrections it carries — exactly the condition that let
`stage6_partA.json` and the pre-correction figures survive. It is committed
now for that reason, not because the HTML is interesting to version.

## What this deck currently carries

- The four write-back corrections (§28.1's protected-fleet mislabel, G6's
  interval claim, G12's causal overclaim, G4's forbidden 500 ms comparison)
  and §2.1's roll-up.
- **A withdrawal banner on G1 and G8**, added 2026-09-03. Their numbers were
  computed over an unrestricted flow population and are KNOWN-WRONG, not
  merely uncertain. Replacement values arrive with the Phase 2 re-run.

## Known stale sibling — do not use

`../oai-branches/IA-P5G Guarantee Simulator.html` (265,889 bytes) is a
browser "save page as" snapshot of an **earlier** version of this deck, taken
2026-09-02 12:29 against the deck's 17:00 edit. It predates the G6 section
entirely and carries **none** of the four corrections and **none** of the G1/
G8 withdrawal. It is not a build output and nothing references it.

**If you are reading a guarantee number, read it from
`deck/artpark-guarantee-deck.html` or from `docs/wp9-regime-map.md`, never
from that snapshot.**

## The rule this establishes

An artefact that goes in front of a client is versioned, or the risk is
written down where someone will find it. A corrected artefact nobody can
diff is indistinguishable from an uncorrected one.
