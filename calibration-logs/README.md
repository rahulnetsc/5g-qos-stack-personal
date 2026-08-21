# calibration-logs — real deployment captures used for timer/config ground truth

## `twotier_startup_gnb.log`

Source: `git show origin/feat/oai-integration:script-logs/gnb.log`, commit
`1b163d662f3a3194e17474257acbb7a3dd43d436` (2026-06-08, "Restarting
openairinterface5g/") on the `feat/oai-integration` branch of this repo.
`feat/oai-integration` is not merged into this branch (README §1 decision);
this file is a one-off extraction of a single log, not an import of that
branch's history.

What it is: a gNB startup log from one rfsim run (band 78, 106 PRB,
two-tier scheduler config). It carries the real deployed RRC/MAC timer
constants in its startup banner — `sr_ProhibitTimer 0, sr_TransMax 64,
sr_ProhibitTimer_v1700 0, t300 400, t301 400, t310 2000, n310 10, t311
3000, n311 1, t319 400` — used by WP4 as the cited source for `sr-
ProhibitTimer`/`sr-TransMax` values (README §6 already cited the `t3xx`/
`n3xx` values from this same banner format).

What it is **not**: a contention-scenario capture, a sweep, or a source of
throughput/latency numbers. It has no traffic-level data — it's a startup
log, not a run capture. `script-logs/combined_metrics.csv` on the same
branch (checked when locating this file) is a broken tracer artifact (a
t_tracer field-mismatch error, one line of output) — not usable sweep data
either.

This replaces a phantom path, `calibration-logs/contention_twotier_run1.
log`, that appeared in this repo's `README.md` §9 layout diagram but was
never actually committed to any branch — confirmed by searching this
repo's full git history across all branches. Use this file as a guideline
for timer constants, not a fit target.
