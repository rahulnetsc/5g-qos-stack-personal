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
