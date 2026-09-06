"""The staleness check, and the two sensitivities it was designed around.

`verify_claims` re-derives a figure from an ARTEFACT; a code change rewrites
no artefact, so before this existed all nine claims passed while
`G1.M01.n10.twotier.median = 90.125` was stale against post-scaling code's
87.78. The check's whole value is that unknown and stale both FAIL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from code_state import artefact_state, core_files, core_hash, stamp  # noqa: E402


def test_the_hash_is_stable_and_nonempty():
    assert len(core_files()) > 20
    assert core_hash() == core_hash()
    assert len(core_hash()) == 16


def test_UNSTAMPED_is_None_and_must_not_read_as_matching():
    """The empty-selection failure in a new hat: an artefact with no stamp
    is exactly the case this check exists for."""
    assert artefact_state({"rows": []}) is None
    assert artefact_state([]) is None
    assert artefact_state({"code_state": {}}) is None
    assert artefact_state({"code_state": stamp()}) == core_hash()


def test_the_hash_IGNORES_docstrings():
    """A design choice made BEFORE the check fired, not a later tuning: this
    repository edits docstrings constantly and a docstring cannot change a
    number."""
    import ast
    from code_state import _strip_docstrings
    a = _strip_docstrings(ast.parse('def f():\n    """one"""\n    return 1\n'))
    b = _strip_docstrings(ast.parse('def f():\n    """TOTALLY DIFFERENT"""\n    return 1\n'))
    assert ast.dump(a) == ast.dump(b)


def test_the_hash_FIRES_on_a_constant():
    """`_OBJ_SCALE = 1e4` is a constant change, and it is the case that
    motivated the whole check. If constants were invisible this would be a
    guard that cannot fail."""
    import ast
    from code_state import _strip_docstrings
    a = _strip_docstrings(ast.parse("K = 1.0e4\n"))
    b = _strip_docstrings(ast.parse("K = 1.0e5\n"))
    assert ast.dump(a) != ast.dump(b)


# --- the claim-level behaviour -------------------------------------------

def _claim(tmp: Path, blob: dict, code_state=None) -> dict:
    p = tmp / "a.json"
    p.write_text(json.dumps(blob))
    c = {"id": "T", "artefact": str(p.relative_to(Path.cwd())) if False else None,
         "field": "v", "statistic": "median", "value": 1.0}
    if code_state is not None:
        c["code_state"] = code_state
    c["_path"] = p
    return c


def test_check_claim_FAILS_an_unstamped_artefact(tmp_path, monkeypatch):
    import verify_claims as VC
    monkeypatch.setattr(VC, "REPO", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps({"rows": [{"v": 1.0}]}))
    r = VC.check_claim({"id": "T", "artefact": "a.json", "field": "v",
                        "statistic": "median", "value": 1.0})
    assert r["ok"] is False
    assert "UNSTAMPED" in r["stale"]


def test_check_claim_FAILS_a_stale_stamp(tmp_path, monkeypatch):
    import verify_claims as VC
    monkeypatch.setattr(VC, "REPO", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps(
        {"code_state": {"sim_core_ast_sha256_16": "deadbeefdeadbeef"},
         "rows": [{"v": 1.0}]}))
    r = VC.check_claim({"id": "T", "artefact": "a.json", "field": "v",
                        "statistic": "median", "value": 1.0})
    assert r["ok"] is False
    assert "STALE" in r["stale"]


def test_check_claim_PASSES_a_current_stamp(tmp_path, monkeypatch):
    import verify_claims as VC
    monkeypatch.setattr(VC, "REPO", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps(
        {"code_state": stamp(), "rows": [{"v": 1.0}]}))
    r = VC.check_claim({"id": "T", "artefact": "a.json", "field": "v",
                        "statistic": "median", "value": 1.0})
    assert r["stale"] is None and r["ok"] is True


def test_historical_claims_SKIP_the_staleness_check(tmp_path, monkeypatch):
    """A deliberately pinned claim -- the kept pre-correction demonstration
    failure -- must not be dragged into the current-code comparison."""
    import verify_claims as VC
    monkeypatch.setattr(VC, "REPO", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps({"rows": [{"v": 1.0}]}))
    r = VC.check_claim({"id": "T", "artefact": "a.json", "field": "v",
                        "statistic": "median", "value": 1.0,
                        "code_state": "historical: kept on purpose"})
    assert r["stale"] is None and r["ok"] is True


def test_every_current_claim_in_the_real_file_cites_a_stamped_artefact():
    """The live configuration, not a fixture. If someone repoints a claim at
    an unstamped artefact, this fails here rather than in a release."""
    import yaml
    import verify_claims as VC
    doc = yaml.safe_load((VC.REPO / "config" / "published_claims.yml").read_text())
    bad = []
    for c in doc["claims"]:
        cs = c.get("code_state", "current")
        if isinstance(cs, str) and cs.startswith("historical"):
            continue
        p = VC.REPO / c["artefact"]
        if p.suffix != ".json":
            bad.append(f"{c['id']} (non-JSON artefact cannot carry a stamp)")
            continue
        if artefact_state(json.loads(p.read_text())) is None:
            bad.append(f"{c['id']} (unstamped)")
    assert not bad, ("current claims citing artefacts that cannot be shown to "
                     "match HEAD: " + ", ".join(bad))


# --- THE NARROWING: hash only what a producer imports ---------------------

def test_the_scope_is_DERIVED_from_the_caller_not_restated():
    """A hand-written module list per producer is the restated-count defect:
    it drifts the moment imports change, and it drifts toward UNDER-covering.
    So `stamp()` reads the caller's own imports."""
    from code_state import _caller_scope
    # called from a test in sim/tests/, not scripts/ -- so it finds nothing
    # and falls back, which is the fail-wide direction
    assert _caller_scope() == ()


def test_scoping_is_NARROWER_than_the_core_but_covers_what_matters():
    from code_state import _reachable_from, core_files
    ents = ("sim.driver", "sim.scorecard", "sim.fleet", "sim.baselines.pf")
    files = {p.name for p in _reachable_from(ents)}
    assert len(files) < len(core_files()), "narrowing achieved nothing"
    # the files a campaign's numbers actually depend on
    for must in ("tier1.py", "two_tier.py", "reservation.py", "bsr.py",
                 "harq.py", "pf.py", "scorecard.py", "fleet.py"):
        assert must in files, f"{must} fell outside the scope"


def test_an_IN_SCOPE_change_still_moves_the_scoped_hash(tmp_path, monkeypatch):
    """THE VERIFICATION THAT MATTERS. A narrowing that stops firing is worse
    than no narrowing -- it is the silent under-coverage this whole mechanism
    exists to catch."""
    import ast as _ast
    import code_state as CS
    ents = ("sim.driver",)
    before = CS.scoped_hash(ents)[0]
    real = CS._hash_files

    def perturbed(files):
        # simulate an edit to an IN-SCOPE file by hashing it differently
        h = real(files)
        names = {p.name for p in files}
        return h + "X" if "tier1.py" in names else h

    monkeypatch.setattr(CS, "_hash_files", perturbed)
    assert CS.scoped_hash(ents)[0] != before, (
        "the scoped hash did not move on an in-scope change")


def test_an_OUT_OF_SCOPE_change_does_NOT_move_the_scoped_hash():
    """The point of the narrowing: five firings in one session, zero false
    alarms, ~10 minutes each. A module the producer never imports should not
    cost a re-run."""
    from code_state import _reachable_from
    ents = ("sim.scorecard",)
    files = {p.name for p in _reachable_from(ents)}
    # scorecard does not reach the schedulers
    assert "tier1.py" not in files and "two_tier.py" not in files


def test_stamp_records_BOTH_hashes_so_a_narrow_one_cannot_pass_as_broad():
    from code_state import stamp
    d = stamp(("sim.driver",))
    assert d["sim_core_ast_sha256_16"]          # the whole core, always
    assert d["scoped_ast_sha256_16"]            # and the scope
    assert d["scope"] == ["sim.driver"]
    assert d["n_scoped_files"] <= d["n_core_files"]


def test_an_unresolvable_scope_FAILS_WIDE():
    """A narrowing may only ever err broad. Under-covering is the defect."""
    from code_state import _reachable_from, core_files
    assert len(_reachable_from(("nonexistent.module",))) == len(core_files())


def test_a_PARTIALLY_unresolvable_sim_scope_also_fails_wide():
    """The first version failed wide only when NOTHING resolved. A scope with
    one good entry and one dead one silently narrowed -- which is how
    `sim/baselines/pf.py` fell out of two campaigns' scopes."""
    from code_state import _reachable_from, core_files
    got = _reachable_from(("sim.driver", "sim.deleted_module"))
    assert len(got) == len(core_files())


def test_the_walk_TRAVERSES_scripts_without_hashing_them():
    """A producer reaches most of the core through `scripts/` helpers. The
    walk has to follow them or the scope under-covers; it must not hash them,
    or a comment in a runner would invalidate every artefact."""
    from code_state import _reachable_from
    got = _reachable_from(("g11_campaign",))
    names = {p.name for p in got}
    assert "pf.py" in names, "the walk stopped at the scripts/ boundary"
    assert not any("scripts" in str(p) for p in got), "a script got hashed"
