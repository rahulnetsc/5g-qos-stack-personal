set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
echo "=== G4 -- post-silence, 3 duty levels x 10 seeds x 3 arms ==="
uv run python scripts/g4_postsilence.py --workers 16 --out $V/g4.json 2>&1 | tail -30
echo
echo "=== G6 -- n=40 seed extension, then the conjunction table ==="
uv run python scripts/g6_seed_extension.py --workers 16 --root $V 2>&1 | tail -25
