"""Derive §2.1's guarantee roll-up from §2.1's own rows.

WHY THIS EXISTS. `docs/wp9-regime-map.md` §2.1 carried a roll-up sentence
reading *"3 unrun-but-buildable (G9, G11, G12)"* under a clause asserting
*"Counts derived from the rows above, not carried separately"* -- while the
same table's G9 row said `run` and its G12 row said `RUN`. The count went
stale the moment those two campaigns closed, and the sentence claiming it
was derived is the part that was false.

That is CLAUDE.md's restated-count rule, with an aggravating feature the
earlier instances did not have: **the restatement carried an explicit
assertion that it was not a restatement**, so a reader had no reason to
check it. `README.md`'s "22-record" corpus, `wp9-plan.md` §6.3's timing
table and stage 1's "56 cells" all failed loudly by disagreeing with
something; this one asserted its own immunity.

The remedy is the rule's own: derive it. Run this and paste, or diff the
committed sentence against `--check`.

    uv run python scripts/regime_map_rollup.py
    uv run python scripts/regime_map_rollup.py --check   # non-zero on drift
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MAP_PATH = Path(__file__).resolve().parent.parent / "docs" / "wp9-regime-map.md"

# Status text -> bucket. Ordered: the FIRST pattern that matches wins, so
# the more specific patterns come first. A status matching none of these is
# a hard error, not a silent drop -- that is the whole point.
_BUCKETS: list[tuple[str, str]] = [
    (r"measured failure", "measured failure"),
    (r"structurally out", "structurally out"),
    (r"blocked on a named mechanism", "blocked on a named mechanism"),
    # "unrun-but-buildable" until G11 was measured NOT runnable as
    # specified (wp9-plan §37): the row carries the qualification, so the
    # roll-up must not contradict it with an optimistic label.
    (r"unrun", "unrun"),
    (r"partially answered", "partially answered"),
    (r"^run\b|^run —|^run --", "run with clause-level answers"),
    (r"answered", "answered"),
]

# The order the roll-up sentence lists buckets in.
_ORDER = [
    "answered",
    "measured failure",
    "partially answered",
    "run with clause-level answers",
    "unrun",
    "blocked on a named mechanism",
    "structurally out",
]


def _strip_md(s: str) -> str:
    """Drop emphasis markers and collapse whitespace, so `**RUN — ...**`
    and `run — ...` bucket identically."""
    return re.sub(r"\s+", " ", s.replace("*", "").replace("`", "")).strip()


def parse_rows(text: str) -> list[tuple[str, str]]:
    """(guarantee_id, status) for every row of §2.1's table, in file order."""
    section = text.split("## 2.1 GUARANTEE INVENTORY", 1)
    if len(section) != 2:
        raise SystemExit("§2.1 heading not found -- has the section been renamed?")
    body = section[1].split("\n## ", 1)[0]
    rows = []
    for line in body.splitlines():
        m = re.match(r"^\|\s*\*\*(G\d+)\*\*\s*\|([^|]*)\|", line)
        if m:
            rows.append((m.group(1), _strip_md(m.group(2))))
    if not rows:
        raise SystemExit("§2.1 table parsed to zero rows")
    return rows


def bucket(status: str) -> str:
    low = status.lower()
    for pat, name in _BUCKETS:
        if re.search(pat, low):
            return name
    raise SystemExit(
        f"unrecognised status {status!r} -- add it to _BUCKETS deliberately "
        "rather than letting a guarantee drop out of the roll-up silently"
    )


def rollup(rows: list[tuple[str, str]]) -> tuple[dict[str, list[str]], str]:
    by: dict[str, list[str]] = {}
    for gid, status in rows:
        by.setdefault(bucket(status), []).append(gid)
    parts = []
    for name in _ORDER:
        if name in by:
            ids = by[name]
            parts.append(f"{len(ids)} {name} ({', '.join(ids)})")
    for name in sorted(set(by) - set(_ORDER)):
        ids = by[name]
        parts.append(f"{len(ids)} {name} ({', '.join(ids)})")
    return by, ", ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed sentence disagrees")
    a = ap.parse_args()

    text = MAP_PATH.read_text()
    rows = parse_rows(text)
    by, sentence = rollup(rows)

    total = sum(len(v) for v in by.values())
    print(f"rows parsed: {len(rows)}   guarantees bucketed: {total}")
    if total != len(rows):
        raise SystemExit("a guarantee was bucketed twice or not at all")
    print()
    for name in _ORDER:
        if name in by:
            print(f"  {len(by[name]):>2}  {name:<32} {', '.join(by[name])}")
    print()
    print("Read as a whole: " + sentence + ".")

    if a.check:
        committed = re.search(r"\*\*Read as a whole:(.+?)\*\*", text, re.S)
        if not committed:
            print("\nFAIL: no 'Read as a whole' sentence found", file=sys.stderr)
            return 1
        got = _strip_md(committed.group(1))
        want = _strip_md(sentence)
        # compare the (count, ids) pairs rather than prose
        norm = lambda s: sorted(re.findall(r"(\d+)\s+([a-z, \-]+?)\s*\(([^)]*)\)", s.lower()))
        if norm(got) != norm(want):
            print("\nFAIL: committed roll-up disagrees with the rows.", file=sys.stderr)
            print(f"  committed: {got}", file=sys.stderr)
            print(f"  derived  : {want}", file=sys.stderr)
            return 1
        print("\nOK -- committed roll-up matches the rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
