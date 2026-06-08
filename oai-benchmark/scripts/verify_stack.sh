#!/usr/bin/env bash
# =============================================================================
# verify_stack.sh — 4-stage end-to-end stack verification for IA-P5G
#
# Usage:
#   ./verify_stack.sh              # all 4 stages
#   ./verify_stack.sh --stage 1   # CN5G only
#   ./verify_stack.sh --stage 2   # gNB only
#   ./verify_stack.sh --stage 3   # core + gNB + tracer (stays alive)
#   ./verify_stack.sh --stage 4   # UE only (stages 1-3 assumed running)
#
# Key env overrides:
#   UE_CONF=path/to/conf     change UE config
#   UE_IMSI=208990100001100  change IMSI to check in DB
#   TRAFFIC_DURATION=30      shorter traffic test
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env.sh"
source "$SCRIPT_DIR/lib.sh"

STAGE_ONLY="all"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage) STAGE_ONLY="$2"; shift 2 ;;
        --help)
            echo "Usage: $0 [--stage 1|2|3|4]"
            echo "Env: UE_CONF=  UE_IMSI=  TRAFFIC_DURATION="
            exit 0 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

trap cleanup_all EXIT INT TERM
mkdir -p "$LOG_DIR" "$RESULTS_DIR"

PASS=0; FAIL=0
GNB_LOG="$LOG_DIR/gnb.log"
UE_IMSI="${UE_IMSI:-208990100001100}"
UE_CONF="${UE_CONF:-$BENCH_DIR/config/ue/ue_smoke.conf}"

# check(): run function, track PASS/FAIL, never abort on failure
# NOTE: use PASS+=1 / FAIL+=1 not (( VAR++ )) — bash arithmetic with
# value=0 makes (( 0++ )) exit non-zero, which || true silently swallows
# while the increment still happens, making the display misleading.
check() {
    if "$@"; then
        PASS=$(( PASS + 1 )); return 0
    else
        FAIL=$(( FAIL + 1 )); return 1
    fi
}

# check_warn(): like check() but failure is non-fatal (no FAIL increment)
check_warn() {
    "$@" || log_warn "(non-fatal — see above)"
    return 0
}

run_stage() {
    local n="$1"; shift
    [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "$n" ]] || return 0
    log_stage "STAGE $n — $*"
}

# =============================================================================
# STAGE 1 — CN5G
# =============================================================================
if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "1" ]]; then
    run_stage 1 "CN5G: Start → Health → Network Discovery → Subscriber Check → Stop"

    check core_start
    check core_wait_healthy

    echo ""
    log_info "Container status:"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" \
        | grep -E "NAME|oai-|ims|mysql" | column -t
    echo ""

    check core_discover_network

    # Verify BOTH subscriber tables — auth AND session management
    check check_subscribers "$UE_IMSI"

    [[ "$STAGE_ONLY" == "1" ]] && core_stop
fi

# =============================================================================
# STAGE 2 — gNB
# =============================================================================
if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "2" ]]; then
    run_stage 2 "gNB: Start → Verify N2/F1/GTP/T-tracer → Stop/Restart Test"

    [[ "$STAGE_ONLY" == "2" ]] && { core_start; core_wait_healthy || exit 1; }

    gnb_start "$GNB_LOG"
    check wait_for_log \
        "N2 Setup (NGSetupResponse)" "$GNB_LOG" \
        "Received NGSetupResponse from AMF" "$GNB_N2_TIMEOUT" || {
        log_fail "N2 Setup failed. Checking core logs..."
        set +e
        docker logs oai-amf 2>&1 | grep -iE "error|setup|fail" | tail -10 | sed 's/^/  [AMF] /'
        set -e
        exit 1
    }

    check wait_for "T tracer port $T_TRACER_PORT" \
        "ss -tlnp | grep -q $T_TRACER_PORT" 15

    check gnb_verify "$GNB_LOG"

    echo ""
    log_info "gNB radio configuration:"
    grep -E "MCC=|TDD period index|DL frequency|N_RB_DL=|SDAP|GTPu address|Supported PLMN" \
        "$GNB_LOG" 2>/dev/null | grep -v "slot\|Initializing\|frame" | \
        sed 's/.*\[.*\]/  /' | sort -u | head -15
    echo ""

    # NOTE: Stop/restart cycle REMOVED.
    # Restarting the gNB invalidates the UPF's N4 PFCP DL FAR (old TEID stays
    # in UPF, new gNB issues a new TEID the UPF doesn't know about).  Stage 4
    # data-plane then silently drops all DL packets even though PDU session NAS
    # succeeds. gNB restart resilience is a separate Stage 2.2 test; for the
    # baseline smoke test we keep gNB alive from Stage 2 through Stage 4.
    log_ok "gNB verified and staying alive for Stage 3 → 4 data plane tests ✓"

    [[ "$STAGE_ONLY" == "2" ]] && { gnb_stop; core_stop; }
fi

# =============================================================================
# STAGE 3 — Core + gNB + T tracer
# =============================================================================
if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "3" ]]; then
    run_stage 3 "Core + gNB + T tracer: Metrics Pipeline"

    if [[ "$STAGE_ONLY" == "3" ]]; then
        core_start; core_wait_healthy || exit 1
        gnb_start "$GNB_LOG"
        wait_for_log "N2 Setup" "$GNB_LOG" \
            "Received NGSetupResponse from AMF" "$GNB_N2_TIMEOUT" || exit 1
    fi

    check tracer_start "$LOG_DIR"

    log_stage "T Tracer — CSV File Check"
    for event in gnb_mac_dl gnb_mac_lcid_dl gnb_mac_ul gnb_mac_lcid_ul \
                 gnb_mac_pusch_power_control; do
        f="$LOG_DIR/${event}_raw.csv"
        if [[ -f "$f" ]]; then
            hdr=$(head -1 "$f")
            log_ok "$event: [$hdr]"
            (( PASS++ )) || true
        else
            log_warn "$event: file not yet created"
        fi
    done

    if [[ "$STAGE_ONLY" == "3" ]]; then
        log_info "Staying alive — attach a UE or Ctrl+C to stop."
        log_info "Monitor: tail -f $LOG_DIR/gnb_mac_lcid_dl_raw.csv"
        wait
    fi
fi

# =============================================================================
# STAGE 4 — UE attach + full data plane + T tracer verification
# =============================================================================
if [[ "$STAGE_ONLY" == "all" || "$STAGE_ONLY" == "4" ]]; then
    run_stage 4 "UE: Attach → Protocols → Ping → iperf3 DL/UL → T tracer Data"
    UE_LOG="$LOG_DIR/ue.log"
    log_info "UE config : $UE_CONF"
    log_info "UE IMSI   : $UE_IMSI"

    # Re-verify subscriber tables immediately before UE attach
    log_info "Pre-attach subscriber check..."
    if ! check_subscribers "$UE_IMSI"; then
        log_fail "Subscriber data incomplete — PDU session WILL fail"
        log_fail "Fix the database entries shown above, then re-run"
        (( FAIL++ )) || true
    fi

    # Snapshot T tracer BEFORE UE attaches
    tracer_snapshot "pre_attach"

    # Start UE
    check ue_start "$UE_CONF" "$UE_LOG"

    # Wait for PDU session with full auto-diagnosis on timeout
    if ! wait_for_log \
        "PDU Session Established" "$UE_LOG" \
        "PDU Session Establishment Accept" "$UE_PDU_TIMEOUT"; then

        log_fail "PDU session timed out after ${UE_PDU_TIMEOUT}s"
        (( FAIL++ )) || true
        diagnose_pdu_failure "$UE_IMSI"
        ue_stop

    else
        # Allow UPF N4 PFCP rules and UE TUN to fully stabilise before data tests
        log_info "Data plane stabilisation (5s) ..."
        sleep 5

        # Verify all protocol layers
        check ue_verify "$UE_LOG"

        # Get UE TUN IP
        UE_IP=$(ue_get_ip)
        if [[ -z "$UE_IP" ]]; then
            log_fail "Cannot determine UE TUN IP"
            (( FAIL++ )) || true
        else
            log_ok "UE TUN IP : $UE_IP"

            # Build RNTI map (non-fatal)
            set +e; build_rnti_map "$GNB_LOG" "$UE_LOG" "$UE_CONF"; set -e

            # Set up policy routing so UL traffic from $UE_IP exits via TUN
            # (without this, Linux routes via Docker bridge, bypassing 5G)
            setup_ue_routing "$UE_IP"

            # ── Ping test (non-fatal) ────────────────────────────────────────
            check_warn ping_test "$UE_IP" 4

            # Snapshot T tracer BEFORE traffic
            tracer_snapshot "pre_traffic"

            # ── iperf3 Uplink FIRST (UE → ext-dn via 5G UL path) ─────────────
            if check iperf3_ul "$UE_IP" "${TRAFFIC_DURATION:-10}"; then
                tracer_snapshot "post_ul"
                tracer_show_sample "gnb_mac_lcid_ul" 5
                tracer_show_sample "gnb_mac_pusch_power_control" 3
            else
                log_warn "UL iperf3 failed — running hop-by-hop data plane diagnosis"
                diagnose_dataplane "$UE_IP"
            fi

            # ── iperf3 Downlink (ext-dn → UE via 5G DL path) ─────────────────
            if check iperf3_dl "$UE_IP" "${TRAFFIC_DURATION:-10}"; then
                tracer_snapshot "post_dl"
                tracer_show_sample "gnb_mac_lcid_dl" 5
            else
                log_warn "DL iperf3 failed — check hop-by-hop diagnosis above"
            fi

            # ── T tracer data verification ───────────────────────────────────
            if [[ -f "$LOG_DIR/tracer_snapshot_pre_traffic.env" && \
                  -f "$LOG_DIR/tracer_snapshot_post_dl.env" ]]; then
                check tracer_verify_data "pre_traffic" "post_dl"
            elif [[ -f "$LOG_DIR/tracer_snapshot_pre_traffic.env" && \
                    -f "$LOG_DIR/tracer_snapshot_post_ul.env" ]]; then
                check tracer_verify_data "pre_traffic" "post_ul"
            else
                log_warn "T tracer verification skipped (no post-traffic snapshot)"
            fi

            # Clean up policy routing
            teardown_ue_routing
        fi

        ue_stop
    fi

    if [[ "$STAGE_ONLY" == "all" ]]; then
        tracer_stop; gnb_stop; core_stop
    fi
fi

# =============================================================================
# Final summary
# =============================================================================
log_stage "Verification Summary"
printf "  ${C_GREEN}PASS${C_RESET}: %s\n" "$PASS"
printf "  ${C_RED}FAIL${C_RESET}: %s\n" "$FAIL"
echo ""

# T tracer file summary
if ls "$LOG_DIR"/*_raw.csv &>/dev/null 2>&1; then
    log_info "T tracer CSV files:"
    for f in "$LOG_DIR"/*_raw.csv; do
        set +e; rows=$(( $(wc -l < "$f" 2>/dev/null) - 1 )); set -e
        printf "  %-52s  %6d rows\n" "$(basename "$f")" "$rows"
    done
    if [[ -f "$LOG_DIR/tracer_collector.log" ]]; then
        log_info "T tracer collector log (last 15 lines):"
        tail -15 "$LOG_DIR/tracer_collector.log" | sed 's/^/  /'
    fi
fi
echo ""

if (( FAIL == 0 )); then
    log_ok "All checks passed — stack verified and ready for benchmarking."
    exit 0
else
    log_fail "$FAIL check(s) failed — see diagnosis above."
    exit 1
fi
