# Talk deck

A ~15-minute version of the engineering study: the two structural wins, the one
mixed result, the three fidelity corrections, and the adoption decision.

| file | what it is |
|---|---|
| `build_deck.py` | the source of truth — the deck is generated, never hand-edited |
| `two-tier-scheduler.pptx` | the deck |
| `two-tier-scheduler.pdf` | same, for reading without PowerPoint |

```
make        # rebuild both
```

`build_deck.py` needs `python-pptx` on the *system* interpreter
(`pip install --user python-pptx`) — it is not a project dependency, since the
deck is not part of the simulator. The PDF step needs LibreOffice.

**Do not edit the `.pptx` by hand.** Every number in it is a measured result;
if one changes, change it in `build_deck.py` and rebuild, or the deck and the
repo will drift. All figures are post-2026-08-07, i.e. after the three fidelity
corrections — they match
[adoption-decision.md](../design-docs/adoption-decision.md) and
[scheduler-study.md](../design-docs/scheduler-study.md).

## Slide map

| # | slide | source |
|---|---|---|
| 1 | title | — |
| 2 | one cell, three kinds of promise | scheduler-design §1 |
| 3 | the design — and no novelty claim | scheduler-design §2–4 |
| 4 | win 1: the control channel binds (`sensor_dense`) | scheduler-study §8.2 |
| 5 | win 2: deadline-blindness is silent (`latency_bound`) | scheduler-study §8.3 |
| 6 | the mixed one: metric differs, not outcome (`factory_robots`) | adoption-decision §2 |
| 7 | the turn — results are mediated by a simulator | — |
| 8 | shortcut 1: uplink transport-block fill | oai-phase1-review §C |
| 9 | shortcuts 2 and 3: priorities, demand | oai-phase1-review §C |
| 10 | the decision: adopt, no PF fallback | adoption-decision §3–4 |
| 11 | what this is and is not | adoption-decision §5 |

Slide 6's chart uses slots 1 and 2 of the reference categorical palette in
fixed order (`#2a78d6`, `#eb6834`); the series are also legend-labelled, so
identity is never carried by colour alone.
