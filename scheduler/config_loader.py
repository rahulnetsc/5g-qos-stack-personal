"""Load `TwoTier` parameters from a YAML config file.

Kept in a separate module with a *lazy* PyYAML import so the core
`scheduler` library still imports cleanly with only cvxpy / numpy
available -- yaml is a host convenience, not a library dependency.

The YAML schema is flat and one-to-one with `TwoTier.__init__` kwargs;
see `scheduler/scheduler_config.yaml` for the reference file with
defaults and per-parameter comments. The loader validates each key
against the constructor signature and rejects unknowns rather than
silently ignoring them (typos in a config file otherwise become
"the default was used").
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from .two_tier import TwoTier


def load_two_tier_config(path: str | Path) -> dict[str, Any]:
    """Read a YAML file at ``path`` and return a dict suitable for
    ``TwoTier(**cfg)``. Raises ``ValueError`` for unknown keys."""
    try:
        import yaml
    except ImportError as e:
        raise ImportError(
            "load_two_tier_config requires PyYAML. Either install pyyaml "
            "or construct TwoTier(**kwargs) directly from your own config."
        ) from e

    with open(path, "r") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ValueError(
            f"{path}: top level must be a mapping, got {type(raw).__name__}"
        )

    valid = set(inspect.signature(TwoTier.__init__).parameters) - {"self"}
    unknown = set(raw) - valid
    if unknown:
        raise ValueError(
            f"{path}: unknown TwoTier parameters: {sorted(unknown)}. "
            f"Valid keys: {sorted(valid)}."
        )
    return raw


def load_two_tier(path: str | Path, **overrides: Any) -> TwoTier:
    """Convenience: load a config file and construct a ``TwoTier`` with
    optional per-call overrides layered on top. Sensitivity studies use
    this to sweep one parameter while keeping the rest at file defaults.
    """
    cfg = load_two_tier_config(path)
    cfg.update(overrides)
    return TwoTier(**cfg)
