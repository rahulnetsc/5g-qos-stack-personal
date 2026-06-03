#!/usr/bin/env bash
# =============================================================================
# verify_stack.sh — 4-stage end-to-end stack verification for IA-P5G
#
# Stage 1: Start CN5G, verify health, discover network, stop
# Stage 2: Start gNB alone, verify N2/F1/GTP/T-tracer, stop
# Stage 3: Start core + gNB + T tracer collector, verify data flowing
# Stage 4: Attach UE, verify full stack + metrics pipeline, then stop all
#
# Usage:
#   ./verify_stack.sh              # run all 4 stages
#   ./verify_stack.sh --stage 1   # run specific stage only
#   ./verify_stack.sh --stage 3   # assume core+gnb already running
#
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env.sh"
source "$SCRIPT_DIR/lib.sh"

# Parse arguments
STAGE_ONLY="${STAGE_ONLY:-all}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage) STAGE_ONLY="$2"; shift 2 ;;
        --help)  echo "Usage: $0 [--stage 1|2|3|4]"; exit 0 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

# Register cleanup on exit
trap cleanup_all EXIT INT TERM

mkdir -p "$LOG_DIR" "$RESULTS_DIR"

PASS=0; FAIL=0

run_stage() {
    local n="$1" name="$2"
    [[ "$STAGE_ONLY" != "all" && "$STAGE_ONLY" != "$n" ]] && return 0
    log_stage "STAGE $n — $name"
}

check() {
    if "$@"; then
        (( PASS++ )) || true
        return 0
    else
        (( FAIL++ )) || true
        return 1
    fi
}

# =============================================================================
# STAGE 1 — CN5G: start, health check, network discovery, stop
# =============================================================================
run_stage 1 "CN5G: Start → Verify → Network Discovery → Stop"

if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "1" ]]; then

    core_start
    check core_wait_healthy || {
        log_fail "CN5G containers failed health check — aborting Stage 1"
        exit 1
    }

    # Print container status table
    echo ""
    log_info "Container status:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" \
        | grep -E "NAME|oai-|ims|mysql" | column -t
    echo ""

    # Discover and store network addresses
    core_discover_network

    # Verify subscriber exists
    log_info "Checking subscriber database..."
    sub=$(docker exec mysql mysql -u root -plinux oai_db \
          -e "SELECT ueid FROM AuthenticationSubscription WHERE ueid='208990100001100';" \
          2>/dev/null | grep -v ueid || true)
    if [[ -n "$sub" ]]; then
        log_ok "Subscriber     : IMSI 208990100001100 found in DB ✓"
        (( PASS++ )) || true
    else
        log_fail "Subscriber     : IMSI 208990100001100 NOT in DB"
        log_fail "Run: docker exec mysql mysql -u root -plinux oai_db -e \"INSERT...\""
        (( FAIL++ )) || true
    fi

    # Stop core after stage 1 (unless continuing to stage 2+)
    if [[ "$STAGE_ONLY" == "1" ]]; then
        core_stop
        log_ok "Stage 1 complete"
    fi
fi

# =============================================================================
# STAGE 2 — gNB: start alone, verify N2/F1/GTP/T-tracer, stop
# =============================================================================
run_stage 2 "gNB: Start → Verify N2/F1/GTP/T-tracer → Stop"

if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "2" ]]; then

    # CN5G must be running for gNB N2 setup
    if [[ "$STAGE_ONLY" == "2" ]]; then
        core_start
        core_wait_healthy || exit 1
    fi

    GNB_LOG="$LOG_DIR/gnb_stage2.log"
    gnb_start "$GNB_LOG"

    # Wait for N2 setup complete
    check wait_for_log \
        "N2 Setup (NGSetupResponse)" \
        "$GNB_LOG" \
        "Received NGSetupResponse from AMF" \
        "$GNB_N2_TIMEOUT" || {
        log_fail "N2 Setup failed — last 20 gNB lines:"
        tail -20 "$GNB_LOG"
        gnb_stop; [[ "$STAGE_ONLY" == "2" ]] && core_stop
        exit 1
    }

    # Wait for T tracer port to open
    check wait_for \
        "T tracer port $T_TRACER_PORT" \
        "ss -tlnp | grep -q $T_TRACER_PORT" \
        15

    # Verify all gNB prerequisites
    check gnb_verify "$GNB_LOG"

    # Print a concise summary extracted from log
    echo ""
    log_info "gNB configuration summary:"
    grep -E "MCC=|TDD period|DL freq|N_RB|SDAP layer|GTPu address" "$GNB_LOG" \
        | sed 's/.*\]/  /' | sort -u
    echo ""

    # Can we stop and restart? (important for harness)
    log_info "Testing gNB stop/restart cycle..."
    gnb_stop
    sleep 3
    gnb_start "$GNB_LOG"
    check wait_for_log \
        "gNB restart: N2 Setup" \
        "$GNB_LOG" \
        "Received NGSetupResponse from AMF" \
        "$GNB_N2_TIMEOUT"
    log_ok "Stop/restart cycle      : ✓"

    if [[ "$STAGE_ONLY" == "2" ]]; then
        gnb_stop; core_stop
        log_ok "Stage 2 complete"
    fi
fi

# =============================================================================
# STAGE 3 — Core + gNB + T tracer collector
# =============================================================================
run_stage 3 "Core + gNB + T tracer: verify metrics pipeline"

if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "3" ]]; then

    if [[ "$STAGE_ONLY" == "3" ]]; then
        core_start; core_wait_healthy || exit 1
        GNB_LOG="$LOG_DIR/gnb_stage3.log"
        gnb_start "$GNB_LOG"
        wait_for_log "N2 Setup" "$GNB_LOG" \
            "Received NGSetupResponse from AMF" "$GNB_N2_TIMEOUT" || exit 1
    fi

    # Start T tracer collector
    check tracer_start "$LOG_DIR"

    # Brief verification: connect and confirm output files created
    sleep 2
    check tracer_verify "$LOG_DIR"

    log_info "T tracer CSV files (will fill with data once UE attaches):"
    ls -lh "$LOG_DIR"/*_raw.csv 2>/dev/null | awk '{print "  " $5, $9}' || \
        log_warn "No CSV files yet (expected — UE not attached yet)"

    if [[ "$STAGE_ONLY" == "3" ]]; then
        log_info "Stage 3 verification complete. Core, gNB, and tracer are running."
        log_info "Attach a UE to see metrics flow. Run Stage 4 or Ctrl+C to stop all."
        # Don't auto-stop — let user inspect
        wait  # wait for Ctrl+C
    fi
fi

# =============================================================================
# STAGE 4 — UE attach + full end-to-end verification
# =============================================================================
run_stage 4 "UE: Attach → Verify protocols → Data plane → Metrics"

if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "4" ]]; then

    if [[ "$STAGE_ONLY" == "4" ]]; then
        # Assume core+gnb+tracer already running; just start UE
        :
    fi

    UE_LOG="$LOG_DIR/ue_stage4.log"
    UE_CONF="${UE_CONF:-$BENCH_DIR/config/ue/ue_smoke.conf}"

    log_info "Using UE config: $UE_CONF"
    check ue_start "$UE_CONF" "$UE_LOG"

    # Wait for PDU session
    check wait_for_log \
        "PDU Session Established" \
        "$UE_LOG" \
        "PDU Session Establishment Accept" \
        "$UE_PDU_TIMEOUT" || {
        log_fail "PDU session failed — last 30 UE lines:"
        tail -30 "$UE_LOG"
        exit 1
    }

    sleep 2   # give TUN interface time to come up

    # Verify UE attach
    check ue_verify "$UE_LOG"

    # Build RNTI map
    GNB_LOG="${GNB_LOG:-$LOG_DIR/gnb_stage2.log}"
    build_rnti_map "$GNB_LOG" "$UE_LOG"

    # Discover UE IP from TUN
    UE_IP=$(ip addr show | grep "inet 10\." | awk '{print $2}' | cut -d/ -f1 | head -1)
    if [[ -z "$UE_IP" ]]; then
        log_fail "No UE TUN IP found"
        (( FAIL++ )) || true
    else
        log_ok "UE IP          : $UE_IP"

        # iperf3 data plane test
        check ue_iperf3_test "$UE_IP" 10
    fi

    # Wait for tracer to collect some events
    sleep 5
    log_stage "T Tracer — Events Captured"
    for f in "$LOG_DIR"/*_raw.csv; do
        [[ -f "$f" ]] || continue
        rows=$(( $(wc -l < "$f") - 1 ))
        log_ok "$(basename "$f"): $rows data rows"
        head -3 "$f" | sed 's/^/  /'
        echo ""
    done

    # Stop UE (leave core/gnb/tracer running for further inspection)
    ue_stop

    if [[ "$STAGE_ONLY" == "all" ]]; then
        tracer_stop
        gnb_stop
        core_stop
    fi
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
log_stage "Verification Summary"
echo -e "  ${C_GREEN}PASS${C_RESET}: $PASS"
echo -e "  ${C_RED}FAIL${C_RESET}: $FAIL"
echo ""
if (( FAIL == 0 )); then
    log_ok "All checks passed. Stack is ready for benchmarking."
    exit 0
else
    log_fail "$FAIL check(s) failed. Review output above."
    exit 1
fi
