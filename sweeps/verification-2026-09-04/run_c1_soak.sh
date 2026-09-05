cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
# C1 AT GT-7.1's SPECIFIED HORIZON, n=10.
# W=10, not 12: measured worst-arm RSS is 1960 MB, so W=12 needs 23.0 GiB
# against ~24 usable -- 0.9 GiB of headroom, and the aggregate guard exists
# because that margin has been wrong before. W=10 is 19.1 GiB.
# Banked per run, so a kill costs one run rather than the campaign.
uv run python scripts/g11_campaign.py --seeds 10 --n-ues 4 --horizon 7200000 \
    --workers 10 --budget-mb 21000 --out $V/g11_c1_soak.json
echo "EXIT=$?"
