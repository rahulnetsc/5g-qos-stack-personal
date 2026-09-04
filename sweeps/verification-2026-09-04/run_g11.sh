set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
# G11's C1 at n=10, EVERYTHING ELSE MATCHING the n=3 artefact exactly
# (N=4, horizon 400,000) so the seed count is the only thing that differs --
# the same isolation G8 needed.
uv run python scripts/g11_campaign.py --seeds 10 --n-ues 4 --horizon 400000 \
    --workers 16 --out $V/g11_c1_n10.json 2>&1 | tail -20
