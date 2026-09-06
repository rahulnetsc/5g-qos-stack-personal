"""Re-derive every published figure from the artefact it cites.

THE DEFECT THIS EXISTS FOR (`docs/wp9-defects-log.md` #22). The G8 row read
*"M22 starvation epochs … 0 on all arms at the core cell"* while the file it
was written from, `sweeps/phase2/core_mfbr.json`, recorded Reservation
starving a flow for **10.0 s** on one of its three seeds. The data was
correct and on disk; the row summarising it was never read back against it.
Nothing in this project closed that gap: `--check` compares `RunRecord`s, the
metric panel governs how a metric is *computed* rather than how it is
*quoted*, and `regime_map_rollup.py` checks one derived sentence against its
own table. Every guard sat on one side of the JSON-to-prose boundary.

So: each published figure declares its artefact, its `n`, its horizon, the
field it reads and the statistic it is; this script recomputes it and diffs.

THE ESTIMATOR CONSTRAINT, and it is the part that carries the lesson. A
checker that accepted "the value matches SOME statistic" would have passed
the very row that motivated it — G8's *"PF 0.9995 / Reservation 0.9998 /
TwoTier 0.9654"* mixes a single seed with a 3-seed mean, and each figure does
match *something*. So this reports **which** statistics match and fails
unless the DECLARED one does. A near-miss where a different estimator agrees
is called out by name, because that is the shape of the defect rather than a
coincidence.

Usage:
    uv run python scripts/verify_claims.py
    uv run python scripts/verify_claims.py --check       # exit non-zero on any failure
    uv run python scripts/verify_claims.py --claims config/published_claims.yml
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from code_state import artefact_state, core_hash, expected_for

sys.path.insert(0, str(Path(__file__).resolve().parent))

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CLAIMS = REPO / "config" / "published_claims.yml"


# --- the statistics a claim may declare ------------------------------------
#
# Deliberately small and named. A claim that needs something not here adds it
# HERE, visibly, rather than the checker growing a general expression
# evaluator -- at which point it could match anything and would stop being a
# check.

def _count_gt(values: list[float], arg: float) -> float:
    return float(sum(1 for v in values if v > arg))


def _count_lt(values: list[float], arg: float) -> float:
    return float(sum(1 for v in values if v < arg))


STATISTICS: dict[str, Callable[..., float]] = {
    "median": lambda v, a=None: float(statistics.median(v)),
    "mean": lambda v, a=None: float(statistics.fmean(v)),
    "min": lambda v, a=None: float(min(v)),
    "max": lambda v, a=None: float(max(v)),
    "sum": lambda v, a=None: float(sum(v)),
    "count": lambda v, a=None: float(len(v)),
    "count_gt": _count_gt,
    "count_lt": _count_lt,
    "count_nonzero": lambda v, a=None: float(sum(1 for x in v if x)),
    "single": lambda v, a=None: float(v[0]) if len(v) == 1 else float("nan"),
}


class ClaimError(Exception):
    pass


def _load_artefact(path: Path, _state: Optional[list] = None) -> list[dict[str, Any]]:
    """Rows, and (via `_state`) the artefact's stamp AND the hash it should
    be compared against -- which depends on the scope the producer recorded."""
    if not path.exists():
        raise ClaimError(f"artefact absent: {path}")
    if path.suffix == ".json":
        blob = json.loads(path.read_text())
        if _state is not None:
            _state.append((artefact_state(blob), *expected_for(blob)))
        rows = blob.get("rows")
        if rows is None:
            raise ClaimError(
                f"{path} has no top-level 'rows'; this checker reads the "
                f"row-shaped artefacts. Add a reader here deliberately rather "
                f"than teaching it to guess a schema.")
        return rows
    if path.suffix == ".jsonl":
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    if path.suffix == ".csv":
        with path.open() as fh:
            return list(csv.DictReader(fh))
    raise ClaimError(f"unsupported artefact type: {path.suffix}")


def _values(rows: list[dict], field: str, where: Optional[dict]) -> list[float]:
    sel = rows
    if where:
        def match(r):
            for k, v in where.items():
                got = r.get(k)
                if got is None:
                    return False
                # CSVs stringify everything; compare on the declared type.
                if isinstance(v, bool):
                    if str(got).lower() not in ("true", "false"):
                        return False
                    if (str(got).lower() == "true") != v:
                        return False
                elif isinstance(v, (int, float)):
                    try:
                        if float(got) != float(v):
                            return False
                    except (TypeError, ValueError):
                        return False
                elif str(got) != str(v):
                    return False
            return True
        sel = [r for r in rows if match(r)]
    if not sel:
        raise ClaimError(f"selection {where} matched NO rows -- an aggregate "
                         f"over nothing is not a figure")
    out = []
    for r in sel:
        v = r.get(field)
        if v in (None, ""):
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            raise ClaimError(f"{field}={v!r} is not numeric")
    if not out:
        raise ClaimError(f"field {field!r} present but empty on all "
                         f"{len(sel)} selected rows")
    return out


def check_claim(claim: dict) -> dict:
    """Recompute one claim. Returns a verdict dict; never raises for a
    mismatch -- only for a claim that cannot be evaluated at all."""
    path = REPO / claim["artefact"]
    _st: list = []
    rows = _load_artefact(path, _st)
    values = _values(rows, claim["field"], claim.get("where"))

    declared = claim["statistic"]
    if declared not in STATISTICS:
        raise ClaimError(f"unknown statistic {declared!r}; known: "
                         f"{sorted(STATISTICS)}")
    arg = claim.get("statistic_arg")
    got = STATISTICS[declared](values, arg) if arg is not None \
        else STATISTICS[declared](values)
    want = float(claim["value"])
    tol = float(claim.get("tolerance", 1e-9))
    ok = abs(got - want) <= tol

    # THE ESTIMATOR CONSTRAINT: which OTHER statistics would have matched?
    also = []
    for name, fn in STATISTICS.items():
        if name == declared:
            continue
        try:
            other = fn(values, arg) if arg is not None else fn(values)
        except (ValueError, TypeError, ZeroDivisionError):
            continue
        if other == other and abs(other - want) <= tol:   # NaN-safe
            also.append(name)

    # `n` and `horizon` are part of the citation, so they are checked too --
    # a figure quoted with the wrong n is the same defect one field over.
    meta = []
    if "n" in claim:
        n_rows = len(values)
        arms = {str(r.get("arm") or r.get("scheduler")) for r in rows}
        expected = claim["n"] * (len(arms) if not claim.get("where") else 1)
        if claim.get("where") and "arm" not in (claim.get("where") or {}) \
                and "scheduler" not in (claim.get("where") or {}):
            expected = claim["n"] * len(arms)
        if n_rows != expected:
            meta.append(f"n: claim says {claim['n']} seeds "
                        f"({expected} values expected), artefact yields {n_rows}")
    # --- THE STALENESS CHECK (docs/verify-claims-staleness-proposal.md) ---
    # A figure matching its artefact says nothing about whether the artefact
    # still matches the CODE. `code_state` says which question this claim is
    # making: `current` (must have been produced by HEAD) or
    # `historical: <reason>` (deliberately pinned, e.g. a kept failing case).
    cs = claim.get("code_state", "current")
    stale = None
    if isinstance(cs, str) and cs.startswith("historical"):
        pass                                    # pinned on purpose
    else:
        got_state, want_state, how = (_st[0] if _st else (None, core_hash(),
                                                          "whole core"))
        if got_state is None:
            stale = ("UNSTAMPED -- this artefact predates code-state stamping, "
                     "so it cannot be shown to match current code. Unknown is "
                     "NOT treated as matching.")
        elif got_state != want_state:
            stale = (f"STALE ({how}) -- produced by code {got_state}, HEAD "
                     f"is {want_state}. Re-run the campaign, or mark the "
                     f"claim `code_state: historical: <reason>`.")

    return {"id": claim["id"], "ok": ok and not meta and stale is None,
            "got": got, "want": want,
            "declared": declared, "also_match": also, "meta": meta,
            "stale": stale,
            "n_values": len(values), "artefact": claim["artefact"]}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", default=str(DEFAULT_CLAIMS))
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any claim fails")
    ap.add_argument("--only", help="check one claim id")
    a = ap.parse_args(argv[1:])

    doc = yaml.safe_load(Path(a.claims).read_text())
    claims = doc["claims"]
    if a.only:
        claims = [c for c in claims if c["id"] == a.only]
        if not claims:
            raise SystemExit(f"no claim with id {a.only!r}")

    print(f"{len(claims)} published figure(s) re-derived from their artefacts\n")
    bad = 0
    for claim in claims:
        try:
            r = check_claim(claim)
        except ClaimError as exc:
            bad += 1
            print(f"  ERROR  {claim['id']:<28} {exc}")
            continue
        # `expect: fail` INVERTS the verdict. The kept demonstration failure
        # made `--check` exit 1 unconditionally -- a gate that can never pass
        # is as useless as one that can never fail, and this file argues that
        # about other people's checks. A claim marked `expect: fail` must
        # FAIL; if it starts passing, the guard has stopped demonstrating its
        # own failure mode and THAT is the error.
        expect_fail = claim.get("expect") == "fail"
        good = (not r["ok"]) if expect_fail else r["ok"]
        tag = ("ok* " if expect_fail else "ok  ") if good else "FAIL"
        if not good:
            bad += 1
        print(f"  {tag}   {claim['id']:<28} {r['declared']}={r['got']:g} "
              f"quoted={r['want']:g}  ({r['n_values']} values, "
              f"{Path(r['artefact']).name})")
        if expect_fail and good:
            print(f"         {'':<28} EXPECTED to fail, and does -- this is "
                  f"the guard demonstrating its own failure mode")
        for m in r["meta"]:
            print(f"         {'':<28} {m}")
        if r.get("stale"):
            print(f"         {'':<28} code_state: {r['stale']}")
        if not r["ok"] and r["also_match"]:
            # THE POINT OF THE CONSTRAINT. Naming the estimator that DOES
            # match is what turns "the number is wrong" into "the number is a
            # different statistic than the one claimed" -- which is the G8
            # defect exactly.
            print(f"         {'':<28} but these DO match the quoted value: "
                  f"{', '.join(r['also_match'])} -- the figure is a different "
                  f"statistic from the one declared")
        elif r["ok"] and r["also_match"]:
            print(f"         {'':<28} (note: {', '.join(r['also_match'])} "
                  f"also match -- the claim is not estimator-discriminating "
                  f"on this data)")
    print(f"\n{len(claims) - bad} as expected, {bad} NOT as expected "
          f"(`ok*` = a claim that is meant to fail and does)")
    return 1 if (a.check and bad) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
