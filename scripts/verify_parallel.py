"""Serial-vs-parallel identity check, one entry per converted runner.

THE ACCEPTANCE CRITERION FOR PARALLELISING A RUNNER IS NOT "IT IS FASTER".
Every comparison this project publishes is within-seed -- the same channel
realisation replayed across arms -- so a runner that reorders, drops or
perturbs a run has broken the basis of its own result, not merely its
throughput. `0ec8ddb` established that by running one smoke grid at
`--workers 0` and `--workers 4` and diffing; this file makes that check a
standing artefact rather than a thing done once, for a specific reason:
0ec8ddb's own determinism argument was correct and complete, and the five
runners written afterwards inherited neither the pool nor the check.

WHY ANYTHING IS EXCLUDED AT ALL, AND WHAT STOPS THE EXCLUSION LIST GROWING.
Two kinds of field cannot match by construction, and they are kept apart
because they admit different assertions:

  * PROVENANCE -- the output path and the worker count, which every runner
    stamps into its own JSON. These differ DETERMINISTICALLY, so the check
    requires them to be present AND to differ. An entry that does neither is
    reported as an exclusion doing no work.
  * TIMING -- `wall_s` and friends, which measure the thing that changed.
    Whether two 4-second runs round to the same tenth is noise, so requiring
    a difference here would make the check itself flaky. Instead each name
    must LOOK like a clock (`_s` suffix, or `wall`/`time`/`elapsed` in it),
    asserted mechanically below, so a result field cannot be slipped into
    the list to make a diff go away.

Excluding a field silently is how a check stops being able to fail
(CLAUDE.md); excluding one loudly, with a rule about what may go in the
list, is the part that keeps it able to.

Usage:
    uv run python scripts/verify_parallel.py              # every runner
    uv run python scripts/verify_parallel.py phase2_core  # just one
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

# Each entry: the argv (minus --workers/--out), the flag that names the
# output path, the output's format, and the keys that CANNOT match because
# they measure wall time. Grids are deliberately small -- this checks
# determinism, not results, and a 3-hour identity check would not be run.
CASES: dict[str, dict[str, Any]] = {
    "phase2_core": {
        "argv": ["scripts/phase2_core.py", "--seeds", "2", "--n-ues", "4",
                 "--horizon", "4000"],
        "out_flag": "--out", "out_name": "core.json", "fmt": "json",
        "timing_keys": ["wall_s"], "provenance_keys": ["out", "workers"],
    },
    "g6_seed_extension": {
        "argv": ["scripts/g6_seed_extension.py", "--smoke"],
        "out_flag": "--root", "out_name": "g6root", "fmt": "csv_dir",
        "csv_glob": "*.csv", "timing_keys": [], "provenance_keys": [],
    },
    "g4_postsilence": {
        "argv": ["scripts/g4_postsilence.py", "--smoke"],
        "out_flag": "--out", "out_name": "g4.json", "fmt": "json",
        "timing_keys": [], "provenance_keys": [],
    },
    "g9_campaign": {
        # PF and Reservation only: on the default arms TwoTier aborts on the
        # event-count assertion, which is G9's published result. That abort
        # gets its own case below rather than being tolerated here.
        "argv": ["scripts/g9_campaign.py", "--smoke", "--arms",
                 "PF,Reservation"],
        "out_flag": "--out", "out_name": "g9.json", "fmt": "json",
        "timing_keys": [], "provenance_keys": [],
    },
    "g9_campaign_stop": {
        # THE STOP CONDITION MUST FIRE THE SAME WAY IN BOTH PATHS. g9's
        # event-count assertion is a result, not an error, so a parallel
        # runner that swallowed it -- or that raised a different one --
        # would silently turn a refusal-to-score into a score. The partial
        # JSON is NOT compared: which groups finished before the abort
        # depends on the pool, legitimately. What is compared is the exit
        # code and the assertion's own text.
        "argv": ["scripts/g9_campaign.py", "--smoke"],
        "out_flag": "--out", "out_name": "g9stop.json", "fmt": "exit_and_error",
        "expect_exit": 1, "error_match": "ZERO 'cold' events|'warm' events but",
        "timing_keys": [], "provenance_keys": [],
    },
    "g12_campaign": {
        # --perm-seeds 2, NOT the default 5, and the trade is stated rather
        # than absorbed. A check nobody can afford to run before a commit is
        # one that quietly stops being run. At full width this case is 204
        # runs; it WAS run at full width once, on 2026-09-04, and passed --
        # 3 arms x 4 permutations x 5 seeds. At 2 seeds it is 24 permutation
        # tasks instead of 60, which still exercises the three-level index
        # arithmetic (arm, permutation, seed) that is the only thing the pool
        # can get wrong here.
        #
        # MEASURED at --perm-seeds 2: 671 s end to end (serial reference half
        # plus parallel half), against roughly 28 min at full width. The
        # remaining cost is not the permutations -- it is that every run here
        # is a full 20,000-slot N=8 run under ramped load, which has nothing
        # to do with what the check tests. Cutting HORIZON_SLOTS for the
        # identity case is the next lever if 11 min is still too slow to run
        # before a commit; it is not taken here because the horizon is a
        # scenario property this runner reads from sim/scenarios/g12.py, and
        # overriding it from the check would make the check exercise a
        # configuration the campaign never runs.
        "argv": ["scripts/g12_campaign.py", "--smoke", "--perm-seeds", "2"],
        "out_flag": "--out", "out_name": "g12.json", "fmt": "json",
        "timing_keys": [], "provenance_keys": [],
    },
}


def _read(path: Path, fmt: str, glob: str = "*.csv") -> Any:
    if fmt == "json":
        return json.loads(path.read_text())
    if fmt == "csv_dir":
        # BOTH the scored CSV and the persisted records. Comparing only the
        # CSV would leave the record stream -- the thing g6's own falsifier
        # needed and did not have -- outside the identity claim.
        out = {}
        for f in sorted(path.glob(glob)):
            with f.open() as fh:
                out[f.name] = list(csv.DictReader(fh))
        for f in sorted(path.glob("*.jsonl")):
            out[f.name] = [json.loads(ln) for ln in
                           f.read_text().splitlines() if ln.strip()]
        if not out:
            raise SystemExit(f"{path}: no CSV or JSONL output to compare -- "
                             f"an identity check over nothing cannot fail")
        return out
    raise ValueError(fmt)


def _strip(obj: Any, keys: list[str], found: set[str], differed: set[str],
           other: Any) -> Any:
    """Recursively null the named timing keys, recording which were present
    and which actually differed between the two runs."""
    if isinstance(obj, dict):
        other_d = other if isinstance(other, dict) else {}
        out = {}
        for k, v in obj.items():
            if k in keys:
                found.add(k)
                if k in other_d and other_d[k] != v:
                    differed.add(k)
                out[k] = "<timing>"
            else:
                out[k] = _strip(v, keys, found, differed, other_d.get(k))
        return out
    if isinstance(obj, list):
        other_l = other if isinstance(other, list) else []
        return [_strip(v, keys, found, differed,
                       other_l[i] if i < len(other_l) else None)
                for i, v in enumerate(obj)]
    return obj


def _run(case: dict, workers: int, out: Path) -> subprocess.CompletedProcess:
    argv = [sys.executable, *case["argv"], case["out_flag"], str(out),
            "--workers", str(workers)]
    r = subprocess.run(argv, cwd=REPO, capture_output=True, text=True)
    expected = case.get("expect_exit", 0)
    if r.returncode != expected:
        sys.stdout.write(r.stdout[-4000:])
        sys.stderr.write(r.stderr[-4000:])
        raise SystemExit(f"{case['argv'][0]} --workers {workers} exited "
                         f"{r.returncode}, expected {expected}")
    return r


def _check_stop_condition(name: str, case: dict, workers: int) -> bool:
    """For a runner whose correct behaviour is to ABORT. Compares the exit
    code and the assertion text, not the partial output -- which groups
    finished before the abort is a legitimate property of the pool."""
    import re
    import tempfile as _tf
    ok = True
    seen = []
    with _tf.TemporaryDirectory() as td:
        for w in (1, workers):
            r = _run(case, w, Path(td) / f"{w}_{case['out_name']}")
            m = re.search(case["error_match"], r.stderr)
            seen.append((w, r.returncode, bool(m)))
            if not m:
                print(f"  --workers {w}: exited {r.returncode} but the "
                      f"assertion text did not match "
                      f"{case['error_match']!r}")
                sys.stderr.write(r.stderr[-1500:])
                ok = False
    for w, rc, matched in seen:
        print(f"  --workers {w:<2} exit {rc}, stop condition raised: {matched}")
    if ok:
        print(f"  the stop condition fires identically in both paths")
    return ok


def check(name: str, workers: int = 4) -> bool:
    case = CASES[name]
    print(f"\n{'=' * 72}\n{name}: serial (--workers 1) vs parallel "
          f"(--workers {workers})\n{'=' * 72}", flush=True)
    if case["fmt"] == "exit_and_error":
        return _check_stop_condition(name, case, workers)
    with tempfile.TemporaryDirectory() as td:
        ser_p = Path(td) / f"serial_{case['out_name']}"
        par_p = Path(td) / f"par_{case['out_name']}"
        _run(case, 1, ser_p)
        _run(case, workers, par_p)
        glob = case.get("csv_glob", "*.csv")
        ser = _read(ser_p, case["fmt"], glob)
        par = _read(par_p, case["fmt"], glob)

    timing = list(case["timing_keys"])
    prov = list(case["provenance_keys"])
    keys = timing + prov
    found: set[str] = set()
    differed: set[str] = set()
    ser_s = _strip(ser, keys, found, differed, par)
    par_s = _strip(par, keys, set(), set(), ser)

    ok = json.dumps(ser_s, sort_keys=True, default=str) == \
        json.dumps(par_s, sort_keys=True, default=str)
    print(f"  identical after excluding {keys or '(nothing)'}: "
          f"{'YES' if ok else 'NO'}")
    if not ok:
        _report_first_difference(ser_s, par_s)

    # A TIMING EXCLUSION HAS TO LOOK LIKE A CLOCK. This is the mechanical
    # part: it stops a result field being reclassified as "timing" to make a
    # real difference disappear, which is the only way this list gets abused.
    not_a_clock = [k for k in timing
                   if not (k.endswith("_s") or k.endswith("_ms")
                           or "wall" in k or "time" in k or "elapsed" in k)]
    if not_a_clock:
        print(f"  NOT A TIMING FIELD by name: {not_a_clock} -- a result "
              f"cannot be excluded under this heading")
        ok = False
    # Provenance differs deterministically, so it must be present AND differ.
    p_missing = [k for k in prov if k not in found]
    p_inert = [k for k in prov if k in found and k not in differed]
    if p_missing:
        print(f"  PROVENANCE EXCLUSION NOT PRESENT: {p_missing} -- remove it")
        ok = False
    if p_inert:
        print(f"  PROVENANCE EXCLUSION NEVER DIFFERED: {p_inert} -- it is not "
              f"provenance; remove it and let it be compared")
        ok = False
    t_missing = [k for k in timing if k not in found]
    if t_missing:
        print(f"  TIMING EXCLUSION NOT PRESENT: {t_missing} -- remove it")
        ok = False
    if keys:
        print(f"  excluded keys present: {sorted(found)}; "
              f"of those, differed: {sorted(differed)}")
    return ok


def _report_first_difference(a: Any, b: Any, path: str = "") -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                print(f"  first difference at {path}.{k}: "
                      f"{'missing in parallel' if k not in b else 'missing in serial'}")
                return True
            if _report_first_difference(a[k], b[k], f"{path}.{k}"):
                return True
        return False
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            print(f"  first difference at {path}: len {len(a)} vs {len(b)}")
            return True
        for i, (x, y) in enumerate(zip(a, b)):
            if _report_first_difference(x, y, f"{path}[{i}]"):
                return True
        return False
    if a != b:
        print(f"  first difference at {path}: {a!r} vs {b!r}")
        return True
    return False


def main(argv: list[str]) -> int:
    names = argv[1:] or list(CASES)
    bad = [n for n in names if n not in CASES]
    if bad:
        raise SystemExit(f"unknown runner(s) {bad}; known: {list(CASES)}")
    results = {n: check(n) for n in names}
    print(f"\n{'=' * 72}")
    for n, ok in results.items():
        print(f"  {n:<22} {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
