set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
# PUBLISHED CONFIGURATION EXACTLY (horizon 40,000, seeds 1) on CURRENT code.
# Isolates the code change from the seed change: phase2-results' G1/G3/G5/G8
# were measured at seeds=1, horizon=40000 (sweeps/phase2/core_fast.json).
echo "=== n=1, h=40000 -- the published cell, on current code ==="
uv run python scripts/phase2_core.py --seeds 1 --n-ues 8 --horizon 40000 \
    --workers 16 --out $V/core_40k_n1.json 2>&1 | tail -3
echo "=== n=10, h=40000 -- the same cell at a defensible seed count ==="
uv run python scripts/phase2_core.py --seeds 10 --n-ues 8 --horizon 40000 \
    --workers 16 --out $V/core_40k_n10.json 2>&1 | tail -3
