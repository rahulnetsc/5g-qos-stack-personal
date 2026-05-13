# Installation and usage

The project is managed by [uv](https://docs.astral.sh/uv/). uv handles the
Python interpreter, the virtualenv, and the lockfile — so every developer on
Linux / macOS / Windows ends up with byte-pinned identical package versions.

## Prerequisites

Install uv (one time, system-wide):

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# macOS via Homebrew
brew install uv

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After install, restart the shell (or `source ~/.local/bin/env`) so `uv` is on PATH.

That is the only system-level dependency. No conda, no separate Python
install — uv will download CPython 3.12 the first time you run `make install`.

## First-time setup

From the repo root:

```bash
make install
make test
```

`make install` runs `uv sync` under the hood, which:

1. Reads `.python-version` (currently pinned to **3.12**) and installs that
   Python interpreter if uv doesn't already have it cached.
2. Creates `.venv/` in the repo root.
3. Reads `uv.lock` and installs all 37 packages (incl. transitive deps)
   at exactly the locked versions.

`make test` runs `uv run pytest` — 26 tests, takes ~60 s on a cold cache
(cvxpy's first solve is slow), ~8 s warm.

## Running scenarios

```bash
make smoke      # scripts/run_smoke.py — single scenario, RoundRobin, JSON dump
make compare    # scripts/compare_schedulers.py — five scenarios x four schedulers
make plot       # scripts/plot_timeseries.py — per-slot time-series figures
```

For one-off commands, prefix with `uv run`:

```bash
uv run python scripts/plot_timeseries.py --scenario sensor --schedulers pf twotier
uv run python scripts/plot_timeseries.py --scenario smoke --scheduler twotier
```

`uv run` activates the venv transparently — no `source .venv/bin/activate`
required (though that works too if you want a long-running shell session).

## Configuration files

Two YAML files in [configs/](configs/) drive a fifth scenario alongside the
four hardcoded ones:

- [configs/system_config.yml](configs/system_config.yml) — radio side:
  TDD pattern, S-slot symbol split, bandwidth (MHz), numerology, MU-MIMO
  flag, gNodeB count, PDCCH CCE budget.
- [configs/sim_config.yml](configs/sim_config.yml) — workload side:
  simulation horizon, per-UE SNR / coherence, per-flow QFI / direction /
  flow class / GFBR / PDB / traffic spec. Uses a `defaults:` block so each
  UE/flow stanza only specifies overrides.

Both are loaded by [sim/config_loader.py](sim/config_loader.py), which maps
them to a `ScenarioConfig`. The `yaml_scenario()` helper in
[sim/scenarios.py](sim/scenarios.py) is the entry point — used by
`compare_schedulers.py`. Fields the simulator doesn't yet model
(MU-MIMO, multi-gNodeB, MFBR enforcement) are accepted and ignored; the
loader docstring lists them.

A few fields don't map directly to the simulator's model and are worth
calling out:

- **Per-UE radio quality is `mean_snr_db`, not MCS.** The simulator is
  SNR-driven — MCS is derived from SNR via a 12-row staircase in
  [sim/channel.py](sim/channel.py). Pinning MCS would be a code change.
- **`max_data_rate_bps` (MFBR)** is in the schema but the simulator
  doesn't yet enforce an upper cap on delivered rate. Offered load is set
  by the traffic source's `rate_bps`.

## Updating dependencies (maintainer flow)

```bash
# 1. Edit pyproject.toml — add/remove/change a dependency
$EDITOR pyproject.toml

# 2. Refresh the lockfile
make lock           # uv lock — resolves and writes uv.lock

# 3. Apply to the local .venv
make install        # uv sync — installs locked versions

# Periodic refresh of pinned versions within pyproject.toml constraints
make upgrade        # uv lock --upgrade

# Fallback for pip-only environments (rare — generates requirements.txt)
make export-requirements
```

Commit `pyproject.toml` and `uv.lock` together so the next clone gets the
same versions.

## Why uv and not conda

Conda is the right tool when the project depends on non-Python pieces:
specific BLAS variants, CUDA, gfortran, R, or system Python that can't
be replaced. None of this project's dependencies need that — numpy, scipy,
cvxpy (with clarabel / scs / osqp), matplotlib, pyyaml, and pytest all
ship pre-built wheels on PyPI for every supported platform. uv handles
the rest:

| | `python -m venv` + pip | conda | **uv** |
|---|---|---|---|
| Manages Python interpreter | no | yes | **yes** |
| Cross-platform lockfile | no | yes | **yes** |
| Resolves transitive deps | pip (slow) | conda (slow) | **uv (fast)** |
| Standard `pyproject.toml` | yes | partial | **yes** |
| Bundles non-Python C libs | no | yes | no |

For a scheduler simulator, the "bundles non-Python C libs" column doesn't
matter. uv wins on speed and lockfile portability.

## Troubleshooting

**`error: Failed to inspect Python interpreter ... Bad CPU type in executable`**
You have an old, architecture-incompatible Python binary in PATH (often
`/Library/Frameworks/Python.framework/Versions/3.6/bin/python3` left over
from an ancient python.org installer). Fix:

```bash
uv python install 3.12   # gives uv its own managed Python
```

uv will then prefer the managed interpreter over the broken one.

**IDE warns "Package `cvxpy` is not installed in the selected environment"**
The IDE is looking at a different Python env than `.venv/`. Point it at
`.venv/bin/python` (VS Code: command palette → "Python: Select Interpreter"
→ pick `./.venv/bin/python`). The tests themselves use the right env.

**`UserWarning: Solution may be inaccurate` from CVXPY**
Cosmetic — emitted by the default solver on near-degenerate LPs. The
solutions are correct (regression-tested). Suppressing it cleanly would
require pinning a specific solver.

**`uv sync` is slow on first run**
About 20–30 s, mostly cvxpy and its solver backends (clarabel, scs, osqp).
Subsequent runs are <1 s — uv caches downloaded wheels under
`~/.cache/uv/`.

**A test fails after pulling new changes**
Probably a stale `.venv` after someone changed `pyproject.toml`. Re-run
`make install` to bring the venv in sync with the current `uv.lock`.

## Bit-exact reproducibility (caveat)

uv.lock pins every Python package by version + content hash, and
`.python-version` pins the CPython version. What it does *not* pin is the
BLAS / LAPACK library bundled inside scipy and numpy wheels — that
varies per OS (OpenBLAS on Linux wheels, Accelerate on macOS wheels).
For this project's scheduler simulation that's invisible. For numerical
work where sub-ULP float reproducibility matters, you'd need conda with
a pinned MKL or a Docker image. Out of scope here.
