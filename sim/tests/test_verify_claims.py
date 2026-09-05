"""The published-figure checker.

WHAT MUST NOT DRIFT. `scripts/verify_claims.py` exists for defects-log #22 --
a published row contradicted by the artefact it summarises -- and its whole
value rests on one design choice: it fails unless the DECLARED statistic
matches, rather than accepting any statistic that happens to.

That choice is load-bearing and the pre-correction G8 row proves it. Its
protected-fleet M22 values across three seeds are [0, 0, 2]: the claim "0 on
all arms" is a claim about the MAX, which is 2 -- but the MEDIAN and the MIN
are both 0. **A checker that accepted "some estimator matches" would have
passed the exact row it was built to catch.**
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import verify_claims as vc  # noqa: E402


def _claim(**over):
    # `code_state: historical` because this fixture cites the KEPT
    # pre-correction artefact, which predates code-state stamping and is
    # pinned on purpose. Without it every test here would fail on staleness
    # rather than on the estimator behaviour it is actually testing --
    # which is the staleness check working, not a reason to weaken it.
    base = {
        "id": "test", "artefact": "sweeps/phase2/core_mfbr.json",
        "field": "G8_M22_epochs_prot", "statistic": "max", "value": 0,
        "code_state": "historical: the kept pre-correction fixture",
    }
    base.update(over)
    return base


def test_the_pre_correction_G8_row_FAILS():
    """The failing case, run as a test rather than only as a claim entry."""
    r = vc.check_claim(_claim())
    assert not r["ok"], "the checker must fail on the row it was built for"
    assert r["got"] == 2 and r["want"] == 0


def test_the_estimator_constraint_is_what_makes_it_fail():
    """The same data passes under median and under min. If the checker took
    'any estimator matches' as success, the defect would be invisible."""
    r = vc.check_claim(_claim())
    assert set(r["also_match"]) >= {"median", "min"}, (
        "median and min both equal the quoted 0 on this data; the checker "
        "must name them rather than accept them")
    assert not r["ok"], "matching a DIFFERENT statistic is not a pass"


def test_declaring_the_matching_estimator_passes():
    """The converse, so the test above cannot pass by the checker rejecting
    everything."""
    r = vc.check_claim(_claim(statistic="median"))
    assert r["ok"]


def test_an_empty_selection_is_an_error_not_a_zero():
    with pytest.raises(vc.ClaimError, match="matched NO rows"):
        vc.check_claim(_claim(where={"arm": "NoSuchArm"}))


def test_a_missing_artefact_is_an_error():
    with pytest.raises(vc.ClaimError, match="artefact absent"):
        vc.check_claim(_claim(artefact="sweeps/phase2/does_not_exist.json"))


def test_an_unknown_statistic_is_refused():
    with pytest.raises(vc.ClaimError, match="unknown statistic"):
        vc.check_claim(_claim(statistic="whatever_fits"))


def test_check_mode_can_PASS_despite_the_kept_failure():
    """THE CANNOT-PASS SHAPE, caught in this file's own guard. The kept
    demonstration failure made `--check` exit 1 unconditionally -- a gate that
    can never pass is as useless as one that can never fail, and this script
    argues exactly that about other people's checks. `expect: fail` now
    inverts the verdict, so the suite as a whole can be green while the
    demonstration stays red."""
    assert vc.main(["verify_claims.py", "--check"]) == 0


def test_a_kept_failure_that_starts_PASSING_is_an_error():
    """The other direction: if the demonstration claim stops failing, the
    guard has stopped demonstrating its failure mode, and that is the error
    rather than a success."""
    import yaml
    doc = yaml.safe_load((vc.REPO / "config" / "published_claims.yml").read_text())
    kept = [c for c in doc["claims"] if c.get("expect") == "fail"]
    assert kept, "the demonstration failure has been removed from the claims file"
    for c in kept:
        assert not vc.check_claim(c)["ok"]


def test_the_shipped_claims_file_is_consistent_apart_from_the_kept_failure():
    """Every claim in config/published_claims.yml re-derives, except the one
    marked `expect: fail` -- which must still fail, or the guard has stopped
    demonstrating its own failure mode."""
    import yaml
    doc = yaml.safe_load((vc.REPO / "config" / "published_claims.yml").read_text())
    for claim in doc["claims"]:
        r = vc.check_claim(claim)
        if claim.get("expect") == "fail":
            assert not r["ok"], (
                f"{claim['id']} is kept as the demonstration failure and now "
                f"passes -- either the artefact changed or the guard stopped "
                f"working")
        else:
            assert r["ok"], (
                f"{claim['id']}: {r['declared']}={r['got']} but the document "
                f"quotes {r['want']}"
                + (f"; {r['also_match']} would have matched" if r["also_match"] else ""))


def test_a_CURRENT_claim_on_this_same_fixture_FAILS_on_staleness():
    """The other half of the fixture change above: without
    `code_state: historical`, this artefact is unstamped and a current claim
    must fail -- so the historical marking is a real exemption being used
    deliberately, not a default that quietly disables the check."""
    c = _claim(statistic="median")
    c.pop("code_state")
    r = vc.check_claim(c)
    assert r["ok"] is False
    assert "UNSTAMPED" in (r.get("stale") or "")
