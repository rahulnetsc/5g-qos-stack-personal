"""INVERTED claim checking: enumerate PUBLISHED FIGURES, require each to
carry a claim.

`verify_claims.py` enumerates the claims someone registered and verifies each
against its artefact. That answers *"do the registered claims hold?"* and is
routinely read as *"do our published figures hold?"* -- **measured, 8 claims
over 3 artefacts against 13 artefacts behind the guarantee table.** It cannot
fail on an unregistered figure, and unregistered is the default.

This inverts the enumeration. The domain is the **documents we publish
results in**; every numeric figure in them is CLAIMED, EXEMPT, or UNCLAIMED.

**IT FAILS WIDE, DELIBERATELY.** The extractor over-matches -- any number
with a plausible result shape in a table row or a bold span. A figure that is
not a result is dismissed by an explicit inline exemption, never by the
extractor quietly not seeing it. Under-extraction is the exact defect this
tool exists to fix (`docs/defects-status-2026-09-06.md` §3), so the extractor
may only err toward finding too much.

**Exempting one:** put `<!-- fig-exempt: 0.95 -- contract threshold, not a
measurement -->` on the line, or list the literal in `EXEMPT_LITERALS` with a
reason. Both are visible in review; a silent miss is not.

**AND IT ASSERTS ITS OWN COVERAGE** (the standing rule): it reports which
documents it scanned and how many lines it considered, so "zero unclaimed"
can never be read as a statement about a document it never opened.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
CLAIMS = REPO / "config" / "published_claims.yml"

#: Documents whose figures MUST be claimed. Start narrow and enforced rather
#: than wide and advisory -- a gate that fails is worth more than a survey.
ENFORCED = ["docs/STATE.md"]

#: THE RATCHET, and it is a deliberate decision rather than a weakened gate.
#:
#: Measured 2026-09-06: **387 figures across the three results documents, 362
#: unclaimed -- 6.5 % covered.** Writing 362 claims is real work with a real
#: artefact behind each, and it is not done in the session that built this.
#:
#: Two bad options were rejected. Making the gate pass by loosening the
#: extractor is the "tuned until it stops firing" shape this project has
#: recorded four times. Leaving it permanently red makes it furniture that
#: nobody reads.
#:
#: So it RATCHETS: the count may not rise. Adding an unclaimed figure fails
#: TODAY, which is a check that can fail against the thing that actually goes
#: wrong; and the absolute number is printed every run so that "passing" can
#: never be mistaken for "covered".
BASELINE_UNCLAIMED = {"docs/STATE.md": 48,
                      "docs/wp9-regime-map.md": 160,
                      "docs/phase2-results.md": 154}
#: Scanned and reported, not yet gated. Named so the gap is visible.
ADVISORY = ["docs/wp9-regime-map.md", "docs/phase2-results.md"]

#: A number with a result shape. Loose on purpose -- see the module docstring.
FIGURE = re.compile(
    r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(ms|Mbps|kbps|%|×|x(?![\w])|GiB|GB|MB|B(?![\w])|/\s*\d+)")

#: Literals that recur as thresholds, budgets or shapes rather than as
#: measurements. Each needs a reason; the reason is the point.
EXEMPT_LITERALS = {
    "0.95": "the GFBR contract line -- a threshold, not a measurement",
    "0.90": "M09 fairness threshold",
    "100 ms": "the parametric mix's PDB -- a configured bound",
    "15 ms": "sensor_dense's PDB -- a configured bound",
    "300 ms": "5QI 9's standardised PDB",
    "5 ms": "5QI 85/86's standardised PDB",
}
EXEMPT_RE = re.compile(r"<!--\s*fig-exempt:\s*(.+?)-->")


def figures_in(path: pathlib.Path) -> tuple[list[tuple[int, str, str]], int]:
    """(line_no, literal, line) for every figure, plus lines considered."""
    out, considered = [], 0
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not (line.lstrip().startswith("|") or "**" in line):
            continue
        considered += 1
        if EXEMPT_RE.search(line):
            continue
        for m in FIGURE.finditer(line):
            out.append((i, m.group(0).strip(), line.strip()))
    return out, considered


def claimed_literals() -> set[str]:
    """Every value a registered claim pins, in the forms it could be written."""
    blob = yaml.safe_load(CLAIMS.read_text())
    vals: set[str] = set()
    for c in blob.get("claims", []):
        for k in ("value", "expected", "lo", "hi"):
            v = c.get(k)
            if isinstance(v, (int, float)):
                vals |= {f"{v}", f"{v:g}", f"{round(float(v), 2):g}",
                         f"{round(float(v), 3):g}"}
    return vals


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list-unclaimed", action="store_true")
    a = ap.parse_args(argv)

    claimed = claimed_literals()
    worst = 0
    print("SCANNED (asserted, so 'zero unclaimed' cannot mean 'never opened'):")
    totals = {}
    for scope, paths in (("ENFORCED", ENFORCED), ("ADVISORY", ADVISORY)):
        for rel in paths:
            p = REPO / rel
            if not p.exists():
                print(f"  {scope:8s} {rel:32s} MISSING -- refusing to pass")
                worst = 2
                continue
            figs, considered = figures_in(p)
            # EXACT equality on the numeric part. Substring matching -- the
            # first version -- let a claimed "8" cover "18 ms" and reported
            # 79.8 % coverage that did not exist. That is the same
            # under-detection defect this tool was built to fix, one level
            # down, and it is why the match is exact.
            unclaimed = []
            for f in figs:
                num = f[1].split()[0].rstrip("%×x").replace(",", "")
                if num in claimed:
                    continue
                if f[1] in EXEMPT_LITERALS or num in EXEMPT_LITERALS:
                    continue
                unclaimed.append(f)
            totals[rel] = (len(figs), len(unclaimed))
            print(f"  {scope:8s} {rel:32s} {considered:5d} lines, "
                  f"{len(figs):4d} figures, {len(unclaimed):4d} UNCLAIMED")
            if a.list_unclaimed:
                for ln, lit, _ in unclaimed[:40]:
                    print(f"             {rel}:{ln}  {lit}")
            base = BASELINE_UNCLAIMED.get(rel)
            if base is not None and len(unclaimed) > base:
                print(f"           RATCHET BROKEN: {len(unclaimed)} unclaimed, "
                      f"baseline {base}. A new figure was published without a "
                      f"claim.")
                worst = max(worst, 1)

    tf = sum(v[0] for v in totals.values())
    tu = sum(v[1] for v in totals.values())
    print(f"\nTOTAL {tf} figures, {tu} unclaimed "
          f"({100 * (tf - tu) / max(tf, 1):.1f} % covered)")
    print("NOT A COVERAGE PASS. The ratchet only says the backlog did not "
          "grow; the coverage number above is the real state.")
    if worst == 1:
        print("FAIL: unclaimed figures increased. Register a claim, or exempt "
              "the line with `<!-- fig-exempt: <literal> -- <reason> -->`.")
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
