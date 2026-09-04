set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
echo "=== G1/G3/G5/G8 -- phase2_core, N=8, load 1.0, 10 seeds, 20k slots ==="
uv run python scripts/phase2_core.py --seeds 10 --n-ues 8 --horizon 20000 \
    --workers 16 --out $V/core.json 2>&1 | tail -40
echo "=== G10 -- g10_rerun, 6 fleet sizes x 3 arms x 10 seeds ==="
uv run python scripts/g10_rerun.py --seeds 10 --horizon 20000 --workers 16 \
    --out $V/g10_rows.csv 2>&1 | tail -5
echo "=== G10 admissible, scored from that ==="
uv run python scripts/g10_admissible.py 2>&1 | tail -25 || true
