"""A sweep's base point is DERIVED from its builder, or it drifts invisibly.

`wp9_sweep.BASE` was hand-listed and diverged from `sweep_scenario`'s own
defaults on exactly one key -- `mfbr_multiple = 0.0` against a default of 2.0 --
so every artefact built through it ran with two-tier's MFBR-dependent
protections **inert**, while G1/G3/G5/G7/G8/G10 ran at MFBR 8 Mbps. No row said
so.

**Why it was invisible, which is the transferable part.** A WP9 artefact records
an axis value only when it is *off-base*: 1,740 of 1,770 stage-1 rows carry a
blank `mfbr_multiple`. **A blank means "whatever BASE said at the time"**, so
the effective configuration cannot be read off the artefact at all -- you have
to know `BASE`. That is CLAUDE.md's restated-count rule in a configuration.

The fix is derivation plus an explicit reasoned override map, on the
`parallel_audit.ALLOW_SERIAL` pattern: divergence on purpose is fine,
divergence silently is the finding.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from wp9_sweep import BASE, BASE_DRIVER_KWARGS, BASE_OVERRIDES  # noqa: E402

from sim.parametric import sweep_scenario  # noqa: E402


def _defaults():
    return {n: p.default for n, p in inspect.signature(sweep_scenario).parameters.items()
            if p.default is not inspect.Parameter.empty and n != "horizon_slots"}


def test_every_scenario_parameter_appears_in_BASE():
    """A parameter added to the builder tomorrow is in BASE without anyone
    remembering it -- the property a hand-list cannot have."""
    missing = set(_defaults()) - set(BASE)
    assert not missing, f"{missing} are sweep_scenario parameters absent from BASE"


def test_every_divergence_from_the_builder_is_DECLARED_with_a_reason():
    """THE CHECK THAT WOULD HAVE CAUGHT IT. Any key whose BASE value differs
    from the builder's default must be in BASE_OVERRIDES with a reason."""
    undeclared = []
    for name, default in _defaults().items():
        if BASE[name] != default and name not in BASE_OVERRIDES:
            undeclared.append((name, default, BASE[name]))
    assert not undeclared, (
        f"BASE diverges from sweep_scenario's defaults on {undeclared} without "
        f"an entry in BASE_OVERRIDES. Declare it with the reason, or remove "
        f"the divergence -- silently differing is how G4 and G6 came to run at "
        f"MFBR 0 while every other guarantee ran at 8 Mbps.")


def test_the_known_divergence_is_still_declared_and_still_zero():
    """Pins the one real instance, so a later 'tidy-up' that flips it to 2.0
    cannot pass as a config fix -- it would silently RE-MEASURE G4 and G6."""
    assert "mfbr_multiple" in BASE_OVERRIDES
    value, reason = BASE_OVERRIDES["mfbr_multiple"]
    assert value == 0.0
    assert len(reason) > 80, "an override needs a reason, not a label"
    assert BASE["mfbr_multiple"] == 0.0


def test_an_override_naming_a_nonexistent_parameter_FAILS_LOUDLY():
    """An override that matches nothing would be silently ignored, which is the
    same silence in the opposite direction."""
    import wp9_sweep
    saved = dict(wp9_sweep.BASE_OVERRIDES)
    wp9_sweep.BASE_OVERRIDES["not_a_parameter"] = (1, "x" * 100)
    try:
        with pytest.raises(KeyError, match="not a parameter"):
            wp9_sweep._derive_base()
    finally:
        wp9_sweep.BASE_OVERRIDES.clear()
        wp9_sweep.BASE_OVERRIDES.update(saved)


def test_driver_kwargs_are_listed_separately_and_are_NOT_scenario_params():
    """They are not in the builder's signature, so they must be listed -- but
    listing them beside derived values is what made the drift invisible."""
    sig = set(inspect.signature(sweep_scenario).parameters)
    assert not (set(BASE_DRIVER_KWARGS) & sig), (
        "a driver kwarg collides with a scenario parameter name")
    for k in BASE_DRIVER_KWARGS:
        assert BASE[k] == BASE_DRIVER_KWARGS[k]


def test_BASE_is_unchanged_by_the_derivation():
    """The derivation must reproduce what the campaigns actually ran, or this
    'config fix' is a silent re-measurement of every WP9 artefact."""
    # `committed_mult` was added to sweep_scenario on 2026-09-08 (the G9
    # stress experiment's load axis, sim/workload.py). Its base value is the
    # identity, so every WP9 artefact's configuration is unchanged -- which
    # is exactly what this test exists to establish, and why the new key is
    # declared here rather than the assertion being loosened.
    expected = {"n_ues": 8, "load_mult": 1.0, "committed_mult": 1.0,
                "mix": "factory", "duty_cycle": 1.0,
                "snr_spread_db": 0.0, "pdb_ms": None, "shared_lcg": False,
                "mfbr_multiple": 0.0, "bg": False, "inf_scenario": None,
                "min_rb": 5, "sr_period_slots": 10, "k2_slots": 2}
    assert BASE == expected
