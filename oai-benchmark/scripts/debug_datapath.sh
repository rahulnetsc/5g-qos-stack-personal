#!/usr/bin/env bash
# =============================================================================
# debug_datapath.sh — Hop-by-hop 5G data plane debugger for IA-P5G
#
# Assumes: CN5G + gNB + UE already running (all stages 1-3 complete).
# Runs 10-second iperf3 UL + DL tests and traces each network hop.
#
# Usage:
#   ./debug_datapath.sh              # full trace + 10s iperf3 tests
#   ./debug_datapath.sh --trace-only # hop trace without iperf3
#   ./debug_datapath.sh --iperf-only # iperf3 only, skip trace
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env.sh"
source "$SCRIPT_DIR/lib.sh"

MODE="full"
[[ "${1:-}" == "--trace-only" ]] && MODE="trace"
[[ "${1:-}" == "--iperf-only" ]] && MODE="iperf"

mkdir -p "$LOG_DIR"
PASS=0; FAIL=0

check() { if "$@"; then (( PASS++ )) || true; else (( FAIL++ )) || true; fi; }

# =============================================================================
# Step 0 — Discover running state
# =============================================================================
log_stage "Discovering running stack state"

UE_IP=$(ue_get_ip)
if [[ -z "$UE_IP" ]]; then
    log_fail "No UE TUN interface found — is the UE attached?"
    log_fail "Run verify_stack.sh first, or start the UE manually."
    exit 1
fi

UPF_IP=$(docker inspect oai-upf \
    --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
EXT_DN_IP=$(docker inspect oai-ext-dn \
    --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
GNB_PID=$(cat "$GNB_PID_FILE" 2>/dev/null || pgrep -f nr-softmodem | head -1 || echo "?")
UE_PID=$(cat "$UE_PID_FILE" 2>/dev/null || pgrep -f nr-uesoftmodem | head -1 || echo "?")

log_ok "UE TUN IP  : $UE_IP"
log_ok "UPF IP     : $UPF_IP"
log_ok "ext-dn IP  : $EXT_DN_IP"
log_ok "gNB PID    : $GNB_PID"
log_ok "UE  PID    : $UE_PID"

# RNTI from map or gNB log
RNTI_HEX=""
set +e
RNTI_HEX=$(grep -oiP '(?:RNTI)[=\s]+\K[0-9a-f]+' \
    "$LOG_DIR/ue.log" 2>/dev/null | grep -v "^0$" | tail -1)
set -e
[[ -n "$RNTI_HEX" ]] && log_ok "UE RNTI    : 0x$RNTI_HEX ($(( 16#$RNTI_HEX )))" \
                      || log_warn "UE RNTI    : not found (attach first)"

if [[ "$MODE" != "iperf" ]]; then

# =============================================================================
# DOWNLINK hop trace: ext-dn → UPF(N6) → UPF(GTP-U) → gNB → rfsim → UE TUN
# =============================================================================
log_stage "DL Data Path — Hop-by-Hop Trace"

# Hop 1: ext-dn → UPF N6 reachability
log_info "DL Hop 1: ext-dn ←→ UPF N6 ($UPF_IP)"
set +e
h1=$(docker exec oai-ext-dn ping -c 2 -W 1 "$UPF_IP" 2>/dev/null | \
     grep -oP '\d+\.\d+%' | head -1)
set -e
if [[ "${h1:-100%}" == "0%" ]]; then
    log_ok "  ext-dn → UPF N6 : reachable (${h1} loss) ✓"
else
    log_fail "  ext-dn → UPF N6 : unreachable (${h1:-no reply})"
fi

# Hop 2: ext-dn routing for UE subnet
log_info "DL Hop 2: ext-dn route to $UE_IP"
set +e
h2=$(docker exec oai-ext-dn ip route get "$UE_IP" 2>/dev/null | head -1)
set -e
if echo "$h2" | grep -q "$UPF_IP"; then
    log_ok "  ext-dn → $UE_IP via UPF $UPF_IP ✓"
else
    log_warn "  ext-dn route: ${h2:-not found} (expected via $UPF_IP)"
fi

# Hop 3: UPF N4 session — does UPF have a DL PDR for UE IP?
log_info "DL Hop 3: UPF N4 PDR for $UE_IP"
set +e
h3=$(docker logs oai-upf 2>&1 | grep -iE "PDR|${UE_IP//./\\.}|200000a" | tail -5)
set -e
if [[ -n "$h3" ]]; then
    log_ok "  UPF has PDR/session entries:"
    echo "$h3" | sed 's/^/    /'
else
    log_warn "  No UPF PDR log entries for UE IP"
fi

# Hop 4: UPF → gNB GTP-U (UDP 2152 on host)
log_info "DL Hop 4: UPF → gNB GTP-U (192.168.70.129:2152)"
set +e
h4=$(docker exec oai-upf sh -c "nc -zu 192.168.70.129 2152 2>&1" || \
     docker exec oai-upf sh -c \
     "cat /dev/null > /dev/udp/192.168.70.129/2152 2>&1 && echo OK || echo FAIL")
set -e
if ss -ulnp | grep -q ":2152"; then
    log_ok "  Host :2152 (GTP-U) listening ✓ — UPF can reach gNB"
else
    log_fail "  Host :2152 (GTP-U) NOT listening — gNB GTP-U not up"
fi

# Hop 5: gNB rfsimulator — is UE connected?
log_info "DL Hop 5: gNB rfsimulator — UE connection"
set +e
h5_conns=$(ss -tnp | grep ":4043" | grep -v LISTEN | wc -l)
set -e
if (( h5_conns > 0 )); then
    log_ok "  rfsimulator port 4043: $h5_conns active UE connection(s) ✓"
else
    log_fail "  rfsimulator port 4043: no UE connections"
fi

# Hop 6: UE TUN interface health
log_info "DL Hop 6: UE TUN ($UE_IP) on host"
set +e
h6=$(ip addr show | grep "$UE_IP" | head -1)
h6_dev=$(ip addr show | grep "oaitun" | awk -F': ' '{print $2}' | head -1)
set -e
if [[ -n "$h6" ]]; then
    log_ok "  $h6_dev with $UE_IP is UP ✓"
    # Quick self-ping: does the TUN respond?
    ping_result=$(ping -I "$h6_dev" -c 2 -W 1 "$UE_IP" 2>/dev/null | \
                  grep -oP '\d+\.\d+%' | head -1 || echo "N/A")
    log_info "  Self-ping via $h6_dev : ${ping_result} packet loss"
else
    log_fail "  $UE_IP not found on any TUN interface"
fi

# Hop 7: Live GTP-U capture — does any DL traffic actually hit gNB?
log_info "DL Hop 7: Live GTP-U capture (5s) — checking if UPF sends to gNB"
set +e
gtp_count=$(timeout 5 sudo tcpdump -i oai-cn5g -nn udp port 2152 -c 20 2>/dev/null | \
            wc -l || echo 0)
set -e
if (( gtp_count > 0 )); then
    log_ok "  GTP-U packets visible on oai-cn5g bridge : ${gtp_count} captured ✓"
else
    log_warn "  No GTP-U packets seen — trigger some DL traffic first"
    log_warn "  (try: docker exec oai-ext-dn ping $UE_IP -c 3 in another terminal)"
fi

# =============================================================================
# UPLINK hop trace: UE TUN → policy route → rfsim → gNB → UPF(GTP-U) → ext-dn
# =============================================================================
log_stage "UL Data Path — Hop-by-Hop Trace"

# Hop 1: Policy routing active?
log_info "UL Hop 1: Policy routing for $UE_IP"
set +e
ul_rule=$(ip rule show | grep "from $UE_IP lookup 100" || true)
ul_route=$(ip route show table 100 2>/dev/null | head -3)
set -e
if [[ -n "$ul_rule" ]]; then
    log_ok "  ip rule: from $UE_IP lookup 100 ✓"
    log_ok "  table 100: $ul_route"
else
    log_fail "  Policy routing NOT active — call setup_ue_routing $UE_IP"
fi

# Hop 2: Normal routing would bypass 5G (expected, informational)
log_info "UL Hop 2: Default routing for ext-dn $EXT_DN_IP"
set +e
default_route=$(ip route get "$EXT_DN_IP" 2>/dev/null | head -1)
set -e
log_info "  Default: $default_route"
if echo "$default_route" | grep -q "oaitun"; then
    log_ok "  Routes via oaitun (5G UL) ✓"
else
    log_warn "  Routes via Docker bridge (policy routing must override for 10.0.0.2 source)"
fi

# Hop 3: rfsimulator UE↔gNB connection
log_info "UL Hop 3: rfsimulator connection (same as DL Hop 5)"
(( h5_conns > 0 )) && log_ok "  $h5_conns active connection(s) on :4043 ✓" \
                    || log_fail "  No UE connected to gNB rfsimulator"

# Hop 4: gNB GTP-U configured correctly
log_info "UL Hop 4: gNB GTP-U endpoint"
set +e
gtp_line=$(grep "Configuring GTPu address" "$LOG_DIR/gnb.log" 2>/dev/null | \
           tail -1 | grep -oP '[\d.]+, port : \d+')
set -e
if [[ -n "$gtp_line" ]]; then
    log_ok "  gNB GTP-U: $gtp_line ✓"
else
    log_warn "  GTP-U config not found in gNB log"
fi

# Hop 5: UPF N3 → ext-dn N6
log_info "UL Hop 5: UPF N6 → ext-dn connectivity"
set +e
upf_to_dn=$(docker exec oai-upf sh -c \
    "ping -c 2 -W 1 $EXT_DN_IP 2>/dev/null | grep -oP '\d+\.\d+%'" 2>/dev/null | head -1)
set -e
if [[ "${upf_to_dn:-100%}" == "0%" ]]; then
    log_ok "  UPF → ext-dn : reachable ✓"
else
    log_warn "  UPF → ext-dn: ${upf_to_dn:-no reply}"
fi

# T tracer diagnostic
log_stage "T Tracer — Direct Test with csv Binary"
log_info "Testing T tracer with csv binary (10s capture)..."
set +e
CSV_BINARY="$OAI_DIR/common/utils/T/tracer/csv"
if [[ -x "$CSV_BINARY" ]]; then
    tmp_csv="/tmp/debug_tracer_$$.csv"
    timeout 10 "$CSV_BINARY" -d "$T_MSGS" -ip 127.0.0.1 -p 2021 -f -t ts \
        GNB_MAC_LCID_UL ts rnti frame slot lcid data_size >> "$tmp_csv" 2>/dev/null &
    CSV_PID=$!
    sleep 10
    kill "$CSV_PID" 2>/dev/null || true
    rows=$(wc -l < "$tmp_csv" 2>/dev/null || echo 0)
    log_info "csv binary captured: $rows events in 10s"
    if (( rows > 1 )); then
        log_ok "csv binary receiving GNB_MAC_LCID_UL events ✓"
        head -3 "$tmp_csv" | sed 's/^/  /'
        log_warn "Python collector may have framing issue — csv binary works"
    else
        log_warn "csv binary also got 0 events — gNB may not be emitting these events"
        log_warn "Verify gNB started with --T_stdout 2 --T_nowait"
    fi
    rm -f "$tmp_csv"
else
    log_warn "csv binary not found at $CSV_BINARY — build with: cd common/utils/T/tracer && make"
fi
set -e

fi  # end of trace section

# =============================================================================
# iperf3 UL + DL — 10 second tests
# =============================================================================
if [[ "$MODE" != "trace" ]]; then
    log_stage "iperf3 Data Plane Tests (10s each)"

    setup_ue_routing "$UE_IP"

    log_info "Running 10s UL test (UE → ext-dn)..."
    check iperf3_ul "$UE_IP" 10

    log_info "Running 10s DL test (ext-dn → UE)..."
    check iperf3_dl "$UE_IP" 10

    teardown_ue_routing
fi

# =============================================================================
# Summary
# =============================================================================
log_stage "Debug Summary"
printf "  ${C_GREEN}PASS${C_RESET}: %s\n" "$PASS"
printf "  ${C_RED}FAIL${C_RESET}: %s\n" "$FAIL"

if (( FAIL == 0 )); then
    log_ok "Data path fully verified."
else
    log_fail "$FAIL check(s) failed — review hop trace above."
    echo ""
    echo "  Quick reference:"
    echo "  DL fail at hop 4: gNB not receiving GTP-U → check UPF N4 session"
    echo "  DL fail at hop 5: UE not connected to gNB → restart UE"
    echo "  DL fail at hop 7: UPF not sending GTP-U → check PDR rules"
    echo "  UL fail at hop 1: policy routing missing → run setup_ue_routing"
    echo "  T tracer 0 rows:  check csv binary result above"
fi
