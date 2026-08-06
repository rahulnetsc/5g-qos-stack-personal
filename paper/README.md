# COMSNETS submission draft

A conference-paper draft built from the project's design docs.

- [`main.tex`](main.tex) — the paper (IEEE conference class)
- [`refs.bib`](refs.bib) — bibliography
- `build/main.pdf` — compiled output (gitignored)

**Status: complete first draft, 7 pages.** It compiles clean — no overfull
boxes — and every number in it is reproduced from the current code, not
copied from an older revision of the docs. It has *not* been read by a human
yet, and the items under "Before submitting" below are real blockers, not
polish.

## Building

```bash
# Self-contained, downloads what it needs (used to produce build/main.pdf):
tectonic -X compile main.tex --outdir build

# Or with a normal TeX Live installation:
latexmk -pdf -outdir=build main.tex
```

`IEEEtran.cls` and `IEEEtran.bst` are not vendored here — tectonic fetches
them, and TeX Live ships them. If you need to vendor them for an offline or
camera-ready build, take them from the official IEEE author kit rather than
from CTAN mirrors of unknown vintage.

## Where the content came from

| Paper section | Source |
|---|---|
| §I Introduction, §II Related work | scheduler-study.md §1, §2 |
| §III System model | scheduler-study.md §3, §5.1; scheduler-design.md §2–3 |
| §IV Design | scheduler-study.md §4 (all subsections) |
| §V Methodology | scheduler-study.md §5, §6; simulator-design.md |
| §VI Results | scheduler-study.md §7 |
| §VII Threats to validity | scheduler-study.md §9 |
| §VIII Conclusion | scheduler-study.md §8, §11 |

Everything the study doc carries that did **not** fit: the OAI integration
plan, the SPS reservation-policy derivation, the per-scenario YAML schema,
the slice-floor formulation, and most of §8's deployment guidance. If a
reviewer asks for depth on any of those, the material exists.

## Before submitting

**Blockers.**

1. **Author block and affiliation** — currently placeholders in `main.tex`.
2. **Check the page limit against the current CFP.** COMSNETS has used 6, 8
   and 9 page limits across tracks and years, sometimes counting references
   separately. Do not trust this file for that number. At 7 pages there is
   room to grow *or* to cut, depending.
3. **Check whether the track is double-blind.** If it is, the author block,
   the artifact URL, and the phrase "our implementation" in §IV all need
   handling.
4. **Confirm the GitHub repository is public**, or replace the artifact URL
   with an anonymised archive.

**Worth doing.**

5. **A figure.** The paper is currently all tables. The load sweep (§VI-A)
   would carry much better as a two-line plot — contracts met vs load, for
   PF and TwoTier — and would give a reader the "hump" in one glance. That
   is the paper's headline and it deserves a picture. `pgfplots` is the
   obvious tool; the data is in Table~II.
6. **Fill in the bibliography gaps.** `refs.bib` omits page numbers and DOIs
   where the source doc did not record them, and the 3GPP entries need
   version/date stamps. The Shakkottai & Stolyar venue in particular should
   be checked against the canonical citation.
7. **Related work is thin on recent literature.** The citations trace the
   foundational lineage (Kelly, Neely, Stolyar, Tassiulas) and the classic
   QoS schedulers, but there is nothing from the last few years on
   O-RAN-era or slicing-era scheduling. A reviewer will notice. Worth a
   targeted search before submission.

## Honest notes on the draft

- **The framing is deliberately non-triumphal.** The paper's headline is
  that QoS-awareness *often does not matter*, and it states plainly that at
  the shipped load PF carries more total throughput than our design. That is
  the interesting result and it is also a reviewer's most obvious line of
  attack; the trade is defended in §VI-D rather than hidden.
- **The strongest claim** is the knapsack argument in §IV-C — that soft GBR
  penalties make the strategic program a fractional knapsack whose optimum
  abandons the worst-channel flow, and that no reweighting can fix it. It is
  supported by a six-decade penalty sweep and a sign-flip control. If one
  contribution is going to be pushed back on, it is worth defending this one
  hardest, because it generalises beyond our design.
- **The weakest point** is external validity: three synthetic scenarios, one
  cell, simulation only. §VII says so. Trace-driven workloads or an OAI
  measurement would answer it, and neither exists yet.
