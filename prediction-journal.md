# Prediction journal

Predictions registered **before** the investigation that would settle them,
so a diagnosis cannot be scored against a hypothesis written after the
evidence. One entry per question. Scored at the end of the same
investigation, hits and misses both.

---

## P1 — G6's TwoTier M03 failure at 40 seeds (registered 2026-08-31)

**The observation to be explained.** On the `bg` (saturating background
aggressor) excursion at the base point, paired within seed against the
no-`bg` base cell, TwoTier's M03 `max_gap_ms` impairment is **+136.84 %**
with a bootstrap CI of **[+35.23, +267.01]**, entirely above GT-4.1's
+20 % bar. PF (+0.44 %) and Reservation (+1.84 %) pass. M01.p98 moves the
same way on TwoTier (+67.52 %, CI [+14.91, +123.74]) and not on the other
two arms.

**A disambiguation registered up front, because the answer depends on it:
`n=40` is a SEED COUNT, not a fleet size.** The cell is **N=8 UEs, offered
load ×1.0** — the base point. If the intended question was "does G6 hold at
40 UEs", no such cell exists in any run to date and the answer is *unrun*,
not *failed*.

### The prediction — one sentence, falsifiable

**(a) A real scheduler behaviour, not a metric artefact and not a scope
error: TwoTier's UL ranking composite multiplies its priority term by the
candidate's own hypothetical grant size, so a saturating best-effort
aggressor carrying a large backlog outranks the 300-byte periodic telemetry
flow and intermittently starves it, widening the worst liveness gap.**

### What would distinguish (a) from (b) and from (c)

- **Against (c), a max-statistic or metric-definition artefact:** if the
  excess were an artefact of `max_gap_ms` being a *maximum* over the run,
  it would show up in **that statistic alone** and be carried by **one or
  two extreme seeds**, leaving M03's own count-based companion
  (`gap_count_over_t_live`) and M01.p98 flat. The prediction requires the
  opposite: the excess is present across the seed distribution and the
  count-based companion moves too. **M01.p98 already moved (+67.52 %),
  which is weak prior evidence against (c) but is not decisive, because
  both could share a single starvation episode.**
- **Against (b), a guarantee stated at the wrong scope:** scope would mean
  the failing cell lies outside the regime G6 claims. It does not appear
  to — N=8 at load ×1.0 is the base point, and G10's own admissible-fleet
  finding puts N=8 inside the covered range at that load. **(b) becomes the
  answer only if G6's authoritative wording restricts it to a
  load/fleet/traffic-class regime this cell is outside of.**
- **The decisive positive observation for (a):** a code path in
  `scheduler/two_tier.py` where the telemetry flow's UL candidate loses to
  the `bg` flow's candidate *because of* a size-proportional term, plus
  per-seed evidence that the widened gaps coincide with the aggressor being
  served.

### The competing outcome I would have to report

If the mechanism cannot be located in the code path, **the correct result
is "unexplained", recorded as such.** A plausible story invented to close
an unexplained failure is worse than the unexplained failure, and this
project has recorded three corrections that began exactly that way.

**Scored:** see the end of this entry once the investigation completes.
