set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
# MEASURE the memory slope on THE CAMPAIGN PATH (windowed + per-second fold).
# §37's affine fit was taken on a different path -- sweep_scenario at N=8 with
# no window sink -- and defects-log #17 retracted carrying it across. The
# slope has to come from the path that will run.
for H in 800000 1600000 3200000; do
  echo "=== horizon $H ==="
  uv run python scripts/g11_campaign.py --seeds 1 --n-ues 4 --horizon $H \
      --workers 3 --out $V/battery_$H.json 2>&1 | tail -3
done
