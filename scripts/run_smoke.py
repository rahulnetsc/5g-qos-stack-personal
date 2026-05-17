"""Run the smoke scenario through round-robin and dump per-flow stats.

Usage:
    python scripts/run_smoke.py
"""

import json
import sys
from pathlib import Path

# Allow running as `python scripts/run_smoke.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.driver import run
from sim.scenarios import smoke_scenario
from sim.baselines.round_robin import RoundRobin


def main() -> None:
    summary = run(smoke_scenario(), RoundRobin())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
