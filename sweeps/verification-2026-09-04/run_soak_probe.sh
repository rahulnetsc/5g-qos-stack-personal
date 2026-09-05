set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
# ONE GUARDED RUN AT THE REAL HORIZON. §37's own rule -- measure at the
# horizon you will run -- and the projection below is 4.5x beyond the largest
# measured point, which is exactly the extrapolation that rule exists to
# forbid relying on. 3 arms x 1 seed, aggregate guard at 20 GB.
uv run python scripts/g11_campaign.py --seeds 1 --n-ues 4 --horizon 7200000 \
    --workers 3 --budget-mb 20000 --out $V/soak_probe.json 2>&1 | tail -6
