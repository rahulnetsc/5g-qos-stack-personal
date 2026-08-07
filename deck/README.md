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
| 2 | motivation: the factory floor asks for three different things | scheduler-design §1 |
| 3 | what the prior art told us to do — and not to | paper §II |
| 4 | Tier-1: the strategic solve, with the formulation | paper §IV-A…D |
| 5 | Tier-2: virtual queues, UE ranking, LCP, configured grants | paper §IV-E…G |
| 6 | the simulator: what it models and what it does not | simulator-design |
| 7 | result 1: the control channel binds (`sensor_dense`) | scheduler-study §8.2 |
| 8 | result 2: deadline-blindness is silent (`latency_bound`) | scheduler-study §8.3 |
| 9 | result 3: rate contracts across load (`factory_robots`) | adoption-decision §2 |
| 10 | what the design adds, and what it costs | adoption-decision §3–4 |
| 11 | where this stands, and what remains (OAI) | oai-phase1-review |

Slide 9's chart uses slots 1 and 2 of the reference categorical palette in
fixed order (`#2a78d6`, `#eb6834`); the series are also legend-labelled, so
identity is never carried by colour alone.

## A note on layout

python-pptx cannot measure text, and PowerPoint will happily render a
paragraph out of the bottom of its box and over whatever sits below. So
`build_deck.py` estimates rendered height (`est_h`) and the `block()`,
`callout()` and `math()` helpers each return the y-coordinate just below
themselves, letting a slide stack its own content. The per-point character
widths in `CW_PROP` / `CW_MONO` are calibrated against LibreOffice's
rendering at this deck's sizes.

**After any edit, rebuild and look at the pages** — the estimator has
headroom but is not exact, and a slide that grows by a line can push its
last element off the bottom:

```
make && pdftoppm -png -r 55 two-tier-scheduler.pdf /tmp/deck
```
