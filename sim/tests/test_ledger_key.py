"""A resume ledger's key must include every flag that changes a run's output.

THE CLASS, and it is the reason this file exists rather than a comment:
**a cache key that omits a parameter silently returns the WRONG ANSWER**, and
its symptom is an artefact that is byte-identical to the column it was
supposed to differ from. That is indistinguishable from "the flag did
nothing" -- and it was read that way twice in three days, the second time
producing a published conclusion ("6 of 8 predictions missed; do not default
the attach path") that had to be retracted in full.

`phase2_core.py` hand-listed `{n_ues, horizon, load_mult, arms}` and omitted
`attach_seed`. `RunLedger` HAS a config guard and it worked correctly; what
was wrong was the config handed to it. A hand-listed cache key is the
restated-count defect applied to a resume, and it fails toward silently
reusing stale work.

**THE CHECK BELOW DID NOT EXIST, WHICH IS WHY THIS RECURRED THREE TIMES.**
Bank a run, flip a flag, and require the second invocation NOT to resume.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from regime_sweep import RunLedger, invocation_config  # noqa: E402


def _args(**kw):
    ns = argparse.Namespace(out="x.json", workers=12, seeds=10, n_ues=8,
                            horizon=40000, load_mult=1.0, attach_seed=False)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_the_derived_config_carries_every_behavioural_flag():
    cfg = invocation_config(_args())
    for must in ("seeds", "n_ues", "horizon", "load_mult", "attach_seed"):
        assert must in cfg, f"{must} missing from the derived ledger config"


def test_it_drops_only_what_cannot_change_the_output():
    cfg = invocation_config(_args())
    assert "out" not in cfg, "the artefact PATH is not run-defining"
    assert "workers" not in cfg, (
        "worker count is excluded on evidence -- verify_parallel.py checks "
        "serial == parallel per runner")


def test_A_NEW_FLAG_IS_INCLUDED_WITHOUT_ANYONE_REMEMBERING():
    """The property that makes this stay correct. A hand-list cannot have it."""
    cfg = invocation_config(_args(some_flag_invented_tomorrow=True))
    assert cfg.get("some_flag_invented_tomorrow") is True


def test_FLIPPING_A_FLAG_MUST_NOT_RESUME(tmp_path):
    """THE CHECK THAT WAS MISSING. Bank a run with the flag off; re-open the
    same ledger with the flag on; the banked work must NOT be reused."""
    p = tmp_path / "run.jsonl"
    off = RunLedger(p, invocation_config(_args(attach_seed=False)),
                    ("arm", "seed"))
    off.bank({"arm": "TwoTier", "seed": 1, "value": 0.5})
    assert off.done_keys() == {("TwoTier", 1)}

    on = RunLedger(p, invocation_config(_args(attach_seed=True)),
                   ("arm", "seed"))
    assert on.done_keys() == set(), (
        "the banked attach-OFF run was resumed by an attach-ON invocation -- "
        "the exact defect that produced a byte-identical 'with-attach' column "
        "and a retracted conclusion")
    assert on.banked() == []


def test_THE_SAME_FLAGS_DO_RESUME(tmp_path):
    """The other direction: the guard must not refuse legitimate resumption,
    or a killed campaign loses everything and the ledger is pointless."""
    p = tmp_path / "run.jsonl"
    a = RunLedger(p, invocation_config(_args(attach_seed=True)), ("arm", "seed"))
    a.bank({"arm": "PF", "seed": 7, "value": 1.0})
    b = RunLedger(p, invocation_config(_args(attach_seed=True)), ("arm", "seed"))
    assert b.done_keys() == {("PF", 7)}
    assert len(b.banked()) == 1


@pytest.mark.parametrize("flag,val", [("n_ues", 16), ("horizon", 20000),
                                      ("load_mult", 2.5), ("seeds", 4)])
def test_every_run_defining_argument_invalidates_the_bank(tmp_path, flag, val):
    p = tmp_path / f"{flag}.jsonl"
    a = RunLedger(p, invocation_config(_args()), ("arm", "seed"))
    a.bank({"arm": "PF", "seed": 1, "value": 1.0})
    b = RunLedger(p, invocation_config(_args(**{flag: val})), ("arm", "seed"))
    assert b.done_keys() == set(), f"changing {flag} did not invalidate the bank"


def test_a_non_json_config_fails_LOUDLY(tmp_path):
    """A config that cannot round-trip JSON compares unequal on reload and
    would silently never resume -- the opposite failure, equally silent."""
    with pytest.raises(TypeError, match="non-JSON"):
        invocation_config(_args(weird=object()))
