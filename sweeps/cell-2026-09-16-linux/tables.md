## G3 tables

**part 1 (max gap <= 500 ms)** — passes of 10 per fleet size, boundary = last N at 10/10 before the first failure

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |
| Reservation | 10 | 8 | 4 | 4 | 2 | 1 | 2 | 2 | 2 | 4 |
| TwoTier | 10 | 10 | 9 | 10 | 6 | 9 | 9 | 7 | 6 | 6 |
| ProtoRRageD2 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |
| ConfigSched | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |

**part 1s (longest silence <= 500 ms)** — passes of 10 per fleet size, boundary = last N at 10/10 before the first failure

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |
| Reservation | 10 | 6 | 3 | 3 | 2 | 1 | 2 | 2 | 1 | 4 |
| TwoTier | 10 | 10 | 9 | 10 | 4 | 4 | 7 | 3 | 5 | 6 |
| ProtoRRageD2 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |
| ConfigSched | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 8 | 16 |

**part 2 (no gap >= 2 s in run)** — passes of 10 per fleet size, boundary = last N at 10/10 before the first failure

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |
| Reservation | 10 | 7 | 4 | 4 | 2 | 1 | 2 | 2 | 3 | 4 |
| TwoTier | 10 | 10 | 9 | 10 | 7 | 4 | 7 | 3 | 5 | 6 |
| ProtoRRageD2 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |
| ConfigSched | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 24 |

**part 3 (p98 <= 95 ms)** — passes of 10 per fleet size, boundary = last N at 10/10 before the first failure

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 4 | 0 | 0 | 1 | 10 |
| Reservation | 10 | 8 | 4 | 4 | 2 | 1 | 2 | 2 | 0 | 4 |
| TwoTier | 10 | 10 | 10 | 8 | 2 | 2 | 2 | 4 | 0 | 7 |
| ProtoRRageD2 | 10 | 10 | 10 | 10 | 10 | 9 | 9 | 6 | 0 | 10 |
| ConfigSched | 10 | 10 | 10 | 10 | 10 | 5 | 0 | 0 | 0 | 10 |

**all parts** — passes of 10 per fleet size, boundary = last N at 10/10 before the first failure

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 4 | 0 | 0 | 1 | 10 |
| Reservation | 10 | 7 | 4 | 4 | 2 | 1 | 2 | 2 | 0 | 4 |
| TwoTier | 10 | 10 | 9 | 8 | 2 | 0 | 1 | 1 | 0 | 6 |
| ProtoRRageD2 | 10 | 10 | 10 | 10 | 10 | 9 | 9 | 6 | 0 | 10 |
| ConfigSched | 10 | 10 | 10 | 10 | 10 | 5 | 0 | 0 | 0 | 10 |

**telemetry p98, median over seeds (ms)**

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 |
|---|---|---|---|---|---|---|---|---|---|
| PF | 17.8 | 23.0 | 26.0 | 29.0 | 38.8 | 97.5 | 98.8 | 99.0 | 98.5 |
| Reservation | 17.8 | 30.2 | 27.0 | 22.5 | 23.8 | 35.0 | 21.8 | 22.8 | 99.5 |
| TwoTier | 12.0 | 40.5 | 59.5 | 74.0 | 97.0 | 97.0 | 99.0 | 96.2 | 99.5 |
| ProtoRRageD2 | 8.8 | 7.0 | 9.2 | 15.2 | 11.0 | 22.5 | 29.0 | 93.0 | 99.5 |
| ConfigSched | 5.2 | 9.0 | 10.2 | 14.0 | 22.0 | 93.0 | 98.8 | 99.2 | 99.0 |

**worst silence in any seed (ms)**

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 |
|---|---|---|---|---|---|---|---|---|---|
| PF | 125 | 130 | 126 | 130 | 138 | 298 | 399 | 399 | 392 |
| Reservation | 118 | 5286 | 1742 | 1740 | 138 | 208 | 320 | 342 | 6207 |
| TwoTier | 148 | 172 | 4384 | 200 | 8470 | 7786 | 9996 | 9976 | 8371 |
| ProtoRRageD2 | 105 | 108 | 107 | 108 | 110 | 199 | 199 | 296 | 494 |
| ConfigSched | 104 | 105 | 107 | 110 | 122 | 357 | 399 | 492 | 1357 |

**telemetry messages missing, sum over seeds (of 2 000)**

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 |
|---|---|---|---|---|---|---|---|---|---|
| PF | 0 | 0 | 0 | 0 | 0 | 34 | 71 | 96 | 86 |
| Reservation | 0 | 275 | 617 | 622 | 800 | 901 | 805 | 807 | 1018 |
| TwoTier | 0 | 0 | 42 | 9 | 438 | 704 | 611 | 799 | 452 |
| ProtoRRageD2 | 0 | 0 | 0 | 0 | 0 | 4 | 4 | 16 | 68 |
| ConfigSched | 0 | 0 | 0 | 0 | 0 | 46 | 37 | 57 | 60 |

**protected uplink delivered, median (Mbps)**

| arm | N=4 | N=6 | N=7 | N=8 | N=10 | N=12 | N=14 | N=16 | N=24 |
|---|---|---|---|---|---|---|---|---|---|
| PF | 16.1 | 24.2 | 28.2 | 32.2 | 39.7 | 43.4 | 43.6 | 43.7 | 43.8 |
| Reservation | 16.1 | 23.3 | 23.6 | 20.1 | 21.4 | 28.2 | 23.9 | 24.2 | 9.2 |
| TwoTier | 16.1 | 24.0 | 27.9 | 31.5 | 32.6 | 28.5 | 23.3 | 18.9 | 8.2 |
| ProtoRRageD2 | 16.1 | 24.1 | 28.1 | 31.6 | 36.4 | 39.7 | 41.8 | 42.7 | 42.8 |
| ConfigSched | 16.1 | 24.2 | 28.2 | 32.2 | 40.2 | 41.7 | 41.4 | 41.4 | 40.9 |

**campaign-wide silences >= 2 s (clause part 2 as written)**

| arm | gaps >= 2 s | gaps scored | verdict |
|---|---|---|---|
| PF | 0 | 37910 | PASS |
| Reservation | 3 | 30219 | FAIL |
| TwoTier | 30 | 35075 | FAIL |
| ProtoRRageD2 | 0 | 38106 | PASS |
| ConfigSched | 0 | 37998 | PASS |

