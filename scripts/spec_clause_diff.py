"""Clause-by-clause diff of two editions of a 3GPP spec (2026-09-15).

The repo carries two editions of each spec: Rel-18 (`docs/ts_*.pdf`, the
editions the 2026-09-14 survey was read from) and Rel-16 (`docs/Rel 16/`,
the release the OAI gNB and the COTS UE comply with). "What changed for
the clauses we depend on" must be derived from the text, never recalled,
so this tool extracts a numbered clause (or an RRC IE's ASN.1 block plus
field descriptions) from each edition, normalises page headers and
whitespace, splits into sentences and prints a unified diff. Sentence
splitting keeps the diff readable; nothing is summarised.

Usage (text must be extracted first -- pypdf, no poppler on this box):

    uv run --with pypdf python scripts/spec_clause_diff.py extract \
        "docs/Rel 16/ts_138321v162200p- Medium Access Control (MAC) protocol specification.pdf" \
        out/r16_138321.txt
    uv run python scripts/spec_clause_diff.py clause out/r16_138321.txt out/r18_138321.txt 5.8.2
    uv run python scripts/spec_clause_diff.py ie out/r16_138331.txt out/r18_138331.txt ConfiguredGrantConfig

The clause finder takes the LAST occurrence of the heading that is not a
table-of-contents line (those carry dot leaders), and ends at the next
heading that is not a sub-clause. Must not import the simulator.
"""
from __future__ import annotations

import difflib
import io
import re
import sys

HEAD = re.compile(r"^(\d+(?:\.\d+)*)\s+\S")
PAGE = re.compile(r"^(===== PAGE \d+ =====|ETSI\s*$|ETSI TS 138 \d+ V\d.*|.*3GPP TS 38\.\d+ version.*)$")


def extract(pdf: str, out: str) -> None:
    from pypdf import PdfReader  # optional dependency, only for `extract`
    r = PdfReader(pdf)
    with io.open(out, "w", encoding="utf-8") as f:
        for i, pg in enumerate(r.pages):
            f.write(f"\n===== PAGE {i + 1} =====\n")
            f.write(pg.extract_text() or "")
    print(f"{pdf}: {len(r.pages)} pages -> {out}")


def _lines(path: str) -> list[str]:
    return io.open(path, encoding="utf-8", errors="replace").read().splitlines()


def clause_text(lines: list[str], num: str) -> list[str] | None:
    starts = [i for i, l in enumerate(lines)
              if HEAD.match(l) and HEAD.match(l).group(1) == num and "...." not in l]
    if not starts:
        return None
    s, e = starts[-1], len(lines)
    for j in range(s + 1, len(lines)):
        m = HEAD.match(lines[j])
        if m and "...." not in lines[j]:
            n = m.group(1)
            if not n.startswith(num + ".") and n != num:
                e = j
                break
    return [l for l in lines[s:e] if not PAGE.match(l.strip())]


def ie_text(lines: list[str], name: str) -> list[str] | None:
    hdr = re.compile(r"^[–-]\s+" + re.escape(name) + r"\s*$")
    starts = [i for i, l in enumerate(lines) if hdr.match(l.strip())]
    if not starts:
        return None
    s, e = starts[-1], len(lines)
    nxt = re.compile(r"^[–-]\s+[A-Z][A-Za-z0-9-]+\s*$")
    for j in range(s + 1, len(lines)):
        if nxt.match(lines[j].strip()):
            e = j
            break
    return [l for l in lines[s:e] if not PAGE.match(l.strip())]


def sentences(lines: list[str]) -> list[str]:
    txt = re.sub(r"\s+", " ", " ".join(l.strip() for l in lines))
    parts = re.split(r"(?<=[.;:])\s+(?=[A-Z0-9(\-–>])|\s+(?=- |\d> )", txt)
    return [p.strip() for p in parts if p.strip()]


def diff(a: list[str], b: list[str], label_a: str, label_b: str) -> str:
    sa, sb = sentences(a), sentences(b)
    return "\n".join(difflib.unified_diff(sa, sb, fromfile=label_a, tofile=label_b, lineterm="", n=1))


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "extract":
        extract(argv[2], argv[3])
        return 0
    if len(argv) == 5 and argv[1] in ("clause", "ie"):
        getter = clause_text if argv[1] == "clause" else ie_text
        a, b = getter(_lines(argv[2]), argv[4]), getter(_lines(argv[3]), argv[4])
        if a is None or b is None:
            print(f"{argv[4]}: missing in {'first' if a is None else 'second'} edition")
            return 2
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(diff(a, b, f"{argv[2]} {argv[4]}", f"{argv[3]} {argv[4]}"))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
