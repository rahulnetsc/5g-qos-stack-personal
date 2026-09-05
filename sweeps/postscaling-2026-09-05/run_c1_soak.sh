cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/postscaling-2026-09-05
# G11 C1 re-run POST-SCALING, at GT-7.1's specified horizon, n=10.
# Identical invocation to sweeps/verification-2026-09-04/run_c1_soak.sh so
# the two are comparable -- W=10 (measured worst-arm RSS 1960 MB; W=12 would
# need 23.0 GiB against ~24 usable), banked per run so a kill costs one run.
uv run python scripts/g11_campaign.py --seeds 10 --n-ues 4 --horizon 7200000 \
    --workers 10 --budget-mb 21000 --out $V/g11_c1_soak.json
echo "EXIT=$?"
