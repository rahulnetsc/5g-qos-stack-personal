"""`regime_sweep.RunLedger` -- incremental banking and resume.

WHAT THESE PIN, and it is not "the ledger writes lines". A campaign that
writes its artefact only at the end loses everything to one kill; G12 lost a
completed cell that way and Phase 2 has one cell of G12 because of it. The
property that matters is that a KILLED-AND-RESUMED run produces what an
uninterrupted one would -- and the two ways that quietly fails are both
recorded here as tests, because both happened.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from regime_sweep import RunLedger  # noqa: E402


def test_banked_rows_resume(tmp_path):
    led = RunLedger(tmp_path / "x.runs.jsonl", {"horizon": 20_000}, ("arm", "seed"))
    assert led.done_keys() == set()
    led.bank({"arm": "PF", "seed": 1, "v": 10})
    led.bank({"arm": "TwoTier", "seed": 1, "v": 20})
    again = RunLedger(tmp_path / "x.runs.jsonl", {"horizon": 20_000}, ("arm", "seed"))
    assert again.done_keys() == {("PF", 1), ("TwoTier", 1)}
    assert again.banked() == [{"arm": "PF", "seed": 1, "v": 10},
                              {"arm": "TwoTier", "seed": 1, "v": 20}]


def test_a_different_configuration_does_not_resume_from_the_ledger(tmp_path):
    """G11's own scar: `--smoke` at 400,000 slots shared the production
    `--out`, so its rows were treated as done by a 7,200,000-slot campaign.
    The config is part of the record, not just of the filename."""
    led = RunLedger(tmp_path / "x.runs.jsonl", {"horizon": 400}, ("arm", "seed"))
    led.bank({"arm": "PF", "seed": 1, "v": 1})
    real = RunLedger(tmp_path / "x.runs.jsonl", {"horizon": 20_000}, ("arm", "seed"))
    assert real.done_keys() == set()
    assert real.banked() == []


def test_banked_rows_are_returned_without_the_config_key(tmp_path):
    """They are re-entered into the published result, so the bookkeeping
    field must not travel with them."""
    led = RunLedger(tmp_path / "x.runs.jsonl", {"h": 1}, ("arm",))
    led.bank({"arm": "PF", "v": 1})
    again = RunLedger(tmp_path / "x.runs.jsonl", {"h": 1}, ("arm",))
    assert all("_config" not in r for r in again.banked())


def test_a_half_written_line_does_not_lose_the_rows_before_it(tmp_path):
    """A kill mid-write truncates the last line. Everything before it is
    still a completed run and must survive."""
    path = tmp_path / "x.runs.jsonl"
    led = RunLedger(path, {"h": 1}, ("arm",))
    led.bank({"arm": "PF", "v": 1})
    led.bank({"arm": "TwoTier", "v": 2})
    with path.open("a") as fh:
        fh.write('{"arm": "Reserv')          # killed mid-write
    again = RunLedger(path, {"h": 1}, ("arm",))
    assert again.done_keys() == {("PF",), ("TwoTier",)}


def test_bank_REFUSES_a_payload_that_is_not_json(tmp_path):
    """THE ONE THAT COST A DEBUGGING CYCLE. The first version passed
    `default=str`, so a payload holding RunRecord objects was written as
    their repr() -- valid JSON, silently wrong -- and the resumed run handed
    strings to a scorer. A serialization fallback turns an unserializable
    payload into a corrupt one, which is the boundary-coercion failure
    defects-log #1 records. It must raise instead."""
    led = RunLedger(tmp_path / "x.runs.jsonl", {"h": 1}, ("arm",))

    class NotJson:
        def __repr__(self):
            return "NotJson(...)"

    with pytest.raises(TypeError, match="not JSON"):
        led.bank({"arm": "PF", "obj": NotJson()})
    assert not (tmp_path / "x.runs.jsonl").exists() or \
        "NotJson" not in (tmp_path / "x.runs.jsonl").read_text()


def test_rows_are_on_disk_before_the_next_one_starts(tmp_path):
    """The whole point: a row is durable when bank() returns, not when the
    campaign ends."""
    path = tmp_path / "x.runs.jsonl"
    led = RunLedger(path, {"h": 1}, ("arm",))
    led.bank({"arm": "PF", "v": 1})
    on_disk = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    assert len(on_disk) == 1 and on_disk[0]["arm"] == "PF"
