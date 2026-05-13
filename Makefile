# 5G QoS stack dev environment, managed by uv (https://docs.astral.sh/uv/).
#
# Quick start (any OS: Linux, macOS, Windows-WSL):
#   1. Install uv:  curl -LsSf https://astral.sh/uv/install.sh | sh
#                   (or: brew install uv  /  pipx install uv  /  see uv docs for Windows)
#   2. make install
#   3. make test
#
# pyproject.toml is the source of truth for deps; uv.lock pins every package
# (including transitive deps) cross-platform — every dev gets identical versions.
#
# Maintainer workflow (after editing pyproject.toml):
#   make lock          # refresh uv.lock
#   make install       # apply to .venv

UV ?= uv

.PHONY: help install lock upgrade test smoke compare plot clean export-requirements

help:
	@echo "Targets (all run in an isolated .venv managed by uv):"
	@echo "  install              create .venv and install from uv.lock (reproducible)"
	@echo "  lock                 regenerate uv.lock from pyproject.toml"
	@echo "  upgrade              upgrade locked versions within pyproject.toml constraints"
	@echo "  test                 run pytest"
	@echo "  smoke                run scripts/run_smoke.py"
	@echo "  compare              run scripts/compare_schedulers.py"
	@echo "  plot                 run scripts/plot_timeseries.py"
	@echo "  export-requirements  generate requirements.txt for pip-only users"
	@echo "  clean                remove .venv and caches"

install:
	$(UV) sync

lock:
	$(UV) lock

upgrade:
	$(UV) lock --upgrade

test:
	$(UV) run pytest

smoke:
	$(UV) run python scripts/run_smoke.py

compare:
	$(UV) run python scripts/compare_schedulers.py

plot:
	$(UV) run python scripts/plot_timeseries.py

export-requirements:
	$(UV) export --no-hashes --format requirements-txt -o requirements.txt
	@echo "Wrote requirements.txt — fallback for pip-only environments."

clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
