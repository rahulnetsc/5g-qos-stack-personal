#!/usr/bin/env bash
# =============================================================================
# lib.sh — shared functions for IA-P5G benchmark orchestration
# Source this file: source "$(dirname "$0")/lib.sh"
# Requires: env.sh already sourced
# =============================================================================

# --------------- Logging helpers ---------------------------------------------

log_info()  { echo -e "${C_BLUE}[INFO]${C_RESET}  $*"; }
log_ok()    { echo -e "${C_GREEN}[  OK]${C_RESET}  $*"; }
log_warn()  { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
log_fail()  { echo -e "${C_RED}[FAIL]${C_RESET}  $*"; }
log_stage() { echo -e "\n${C_BOLD}${C_BLUE}════════════════════════════════════════${C_RESET}";
              echo -e "${C_BOLD}${C_BLUE} $*${C_RESET}";
              echo -e "${C_BOLD}${C_BLUE}════════════════════════════════════════${C_RESET}"; }

# Wait up to $3 seconds for $2 to become true (shell command), checking every 1s
# Usage: wait_for "description" "test_command" timeout_secs
wait_for() {
    local desc="$1" cmd="$2" timeout="$3"
    local elapsed=0
    echo -ne "${C_YELLOW}[WAIT]${C_RESET}  $desc ..."
    while ! eval "$cmd" &>/dev/null; do
        if (( elapsed >= timeout )); then
            echo -e " ${C_RED}TIMEOUT after ${timeout}s${C_RESET}"
            return 1
        fi
        sleep 1
        (( elapsed++ ))
        echo -n "."
    done
    echo -e " ${C_GREEN}OK (${elapsed}s)${C_RESET}"
    return 0
}

# Wait for a string to appear in a log file
# Usage: wait_for_log "description" logfile "grep_pattern" timeout_secs
wait_for_log() {
    local desc="$1" logfile="$2" pattern="$3" timeout="$4"
    wait_for "$desc" "grep -q '$pattern' '$logfile'" "$timeout"
}

# --------------- CN5G core functions -----------------------------------------

core_start() {
    log_info "Starting CN5G docker stack..."
    cd "$CN5G_DIR" || { log_fail "CN5G directory not found: $CN5G_DIR"; return 1; }
    docker compose up -d 2>&1 | grep -E "Starting|Started|healthy|error" || true
    log_ok "Docker compose started"
}

core_stop() {
    log_info "Stopping CN5G docker stack..."
    cd "$CN5G_DIR" || return 1
    docker compose down 2>&1 | grep -E "Stopping|Stopped|Removing|Removed" || true
    log_ok "CN5G stopped"
}

# Wait for all expected containers to be healthy
core_wait_healthy() {
    local containers=("oai-amf" "oai-smf" "oai-upf" "oai-nrf"
                       "oai-udr" "oai-udm" "oai-ausf" "oai-ext-dn")
    local timeout="$CORE_WAIT_TIMEOUT"
    local elapsed=0

    log_info "Waiting for all CN5G containers to be healthy (timeout ${timeout}s)..."
    while true; do
        local all_healthy=true
        local statuses=""
        for c in "${containers[@]}"; do
            status=$(docker inspect "$c" --format '{{.State.Health.Status}}' 2>/dev/null || echo "missing")
            statuses+="  $c: $status\n"
            [[ "$status" != "healthy" ]] && all_healthy=false
        done

        if $all_healthy; then
            log_ok "All containers healthy"
            return 0
        fi

        if (( elapsed >= timeout )); then
            log_fail "Containers not healthy after ${timeout}s:"
            echo -e "$statuses"
            return 1
        fi

        sleep 2; (( elapsed+=2 ))
        echo -ne "\r${C_YELLOW}[WAIT]${C_RESET}  ${elapsed}s elapsed..."
    done
}

# Print and store all container IPs + key ports
core_discover_network() {
    log_stage "Network Discovery"
    local containers=("oai-amf" "oai-smf" "oai-upf" "oai-nrf"
                       "oai-udr" "oai-udm" "oai-ausf" "oai-ext-dn" "ims")
    local env_out="$LOG_DIR/discovered_network.env"
    mkdir -p "$LOG_DIR"
    : > "$env_out"

    for c in "${containers[@]}"; do
        ip=$(docker inspect "$c" \
             --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
        status=$(docker inspect "$c" --format '{{.State.Health.Status}}' 2>/dev/null)
        if [[ -n "$ip" ]]; then
            log_ok "$(printf '%-15s  IP=%-18s  health=%s' "$c" "$ip" "$status")"
            # Save as env vars for later sourcing
            varname="${c//-/_}"
            varname="${varname^^}_IP"
            echo "export ${varname}=${ip}" >> "$env_out"
        else
            log_warn "$c: not found or no IP"
        fi
    done

    # Host bridge IP
    host_ip=$(ip addr show | grep "${CN5G_SUBNET%.*}" | awk '{print $2}' | cut -d/ -f1 | head -1)
    echo "export HOST_BRIDGE_IP=${host_ip}" >> "$env_out"
    log_ok "Host bridge IP: ${host_ip}"

    log_info "Network env saved to: $env_out"
    # shellcheck source=/dev/null
    source "$env_out"

    # Verify gNB config uses correct AMF IP
    gnb_amf=$(grep "amf_ip_address" "$GNB_CONF" | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)
    if [[ "$gnb_amf" == "$AMF_IP" ]]; then
        log_ok "gNB config AMF IP matches Docker AMF: $gnb_amf"
    else
        log_warn "gNB config has AMF IP $gnb_amf but Docker AMF is $AMF_IP — update config!"
    fi
}

# --------------- gNB functions -----------------------------------------------

GNB_PID_FILE="$LOG_DIR/gnb.pid"

gnb_start() {
    local logfile="${1:-$LOG_DIR/gnb.log}"
    log_info "Starting gNB -> $logfile"
    mkdir -p "$LOG_DIR"
    sudo "$GNB_BIN" \
        -O "$GNB_CONF" \
        --rfsim \
        --rfsimulator.[0].serveraddr server \
        --T_stdout 2 \
        --T_nowait \
        > "$logfile" 2>&1 &
    echo $! > "$GNB_PID_FILE"
    log_ok "gNB started (PID $!)"
}

gnb_stop() {
    if [[ -f "$GNB_PID_FILE" ]]; then
        local pid; pid=$(cat "$GNB_PID_FILE")
        log_info "Stopping gNB (PID $pid)..."
        sudo kill "$pid" 2>/dev/null
        sleep 2
        sudo kill -9 "$pid" 2>/dev/null || true
        rm -f "$GNB_PID_FILE"
        log_ok "gNB stopped"
    else
        # fallback: kill by name
        sudo pkill -f nr-softmodem 2>/dev/null || true
        log_ok "gNB stopped (by name)"
    fi
}

# Verify all gNB prerequisites from its log file
gnb_verify() {
    local logfile="${1:-$LOG_DIR/gnb.log}"
    log_stage "gNB Verification"

    local all_ok=true

    # N2 Setup (NGAP)
    if grep -q "Received NGSetupResponse from AMF" "$logfile"; then
        log_ok "N2 Setup       : NGSetupResponse received ✓"
    else
        log_fail "N2 Setup       : NGSetupResponse NOT found"
        all_ok=false
    fi

    # F1 Setup (internal CU-DU)
    if grep -q "sending F1 Setup Response" "$logfile"; then
        log_ok "F1 Setup       : CU-DU F1 exchange complete ✓"
    else
        log_fail "F1 Setup       : F1 Setup not found"
        all_ok=false
    fi

    # Cell in service
    if grep -q "is in service" "$logfile"; then
        plmn=$(grep "is in service" "$logfile" | grep -oP 'PLMN \S+' | head -1)
        log_ok "Cell           : $plmn in service ✓"
    else
        log_fail "Cell           : not in service"
        all_ok=false
    fi

    # GTP-U
    gtp_line=$(grep "Configuring GTPu address" "$logfile" | head -1 | sed 's/.*\[GTPU\]//')
    if [[ -n "$gtp_line" ]]; then
        log_ok "GTP-U (N3)     :$gtp_line ✓"
    else
        log_fail "GTP-U (N3)     : not configured"
        all_ok=false
    fi

    # T tracer
    if grep -q "T tracer:" "$logfile"; then
        log_ok "T Tracer       : active (port $T_TRACER_PORT) ✓"
    else
        log_warn "T Tracer       : no client connected yet (start collector first)"
    fi

    # rfsimulator server
    if grep -q "Running as server" "$logfile"; then
        log_ok "rfsimulator    : server listening on port $RFSIM_PORT ✓"
    else
        log_fail "rfsimulator    : not listening"
        all_ok=false
    fi

    # Extract key config values
    ue_params=$(grep "Command line parameters for OAI UE" "$logfile" | \
                sed 's/.*Command line parameters for OAI UE: //' | head -1)
    [[ -n "$ue_params" ]] && log_info "UE params hint : $ue_params"

    $all_ok && return 0 || return 1
}

# --------------- T tracer collector functions --------------------------------

TRACER_PID_FILE="$LOG_DIR/tracer.pid"

tracer_start() {
    local out_dir="${1:-$LOG_DIR}"
    log_info "Starting T tracer collector -> $out_dir"
    python3 "$T_COLLECTOR" "$out_dir" &
    echo $! > "$TRACER_PID_FILE"
    # Give it 3 seconds to connect and confirm
    sleep 3
    if kill -0 "$(cat "$TRACER_PID_FILE")" 2>/dev/null; then
        log_ok "T tracer collector running (PID $(cat "$TRACER_PID_FILE"))"
    else
        log_fail "T tracer collector exited early — check port $T_TRACER_PORT"
        return 1
    fi
}

tracer_stop() {
    if [[ -f "$TRACER_PID_FILE" ]]; then
        local pid; pid=$(cat "$TRACER_PID_FILE")
        kill "$pid" 2>/dev/null || true
        sleep 1
        rm -f "$TRACER_PID_FILE"
        log_ok "T tracer collector stopped"
    fi
}

tracer_verify() {
    local out_dir="${1:-$LOG_DIR}"
    log_stage "T Tracer Verification"
    local all_ok=true
    for event in gnb_mac_dl gnb_mac_lcid_dl gnb_mac_ul gnb_mac_lcid_ul; do
        f="$out_dir/${event}_raw.csv"
        if [[ -f "$f" ]]; then
            lines=$(wc -l < "$f")
            log_ok "$event: $f  ($lines rows)"
            (( lines < 2 )) && log_warn "  -> only header, no data rows yet"
        else
            log_warn "$event: file not found (may appear after first UE attach)"
            all_ok=false
        fi
    done
    $all_ok && return 0 || return 1
}

# --------------- UE functions -----------------------------------------------

UE_PID_FILE="$LOG_DIR/ue.pid"

ue_start() {
    local conf="${1:-$BENCH_DIR/config/ue/ue_smoke.conf}"
    local logfile="${2:-$LOG_DIR/ue.log}"
    log_info "Starting UE  conf=$conf -> $logfile"
    sudo "$UE_BIN" \
        -O "$conf" \
        --rfsim \
        -r "$NR_PRB" --numerology "$NR_NUMEROLOGY" --band "$NR_BAND" -C "$NR_ARFCN" \
        > "$logfile" 2>&1 &
    echo $! > "$UE_PID_FILE"
    log_ok "UE started (PID $!)"
}

ue_stop() {
    if [[ -f "$UE_PID_FILE" ]]; then
        local pid; pid=$(cat "$UE_PID_FILE")
        log_info "Stopping UE (PID $pid)..."
        sudo kill "$pid" 2>/dev/null
        sleep 2
        sudo kill -9 "$pid" 2>/dev/null || true
        rm -f "$UE_PID_FILE"
    else
        sudo pkill -f nr-uesoftmodem 2>/dev/null || true
    fi
    # Remove TUN interfaces
    for tun in $(ip link show | grep oaitun | awk -F': ' '{print $2}'); do
        sudo ip link delete "$tun" 2>/dev/null || true
    done
    log_ok "UE stopped"
}

# Verify UE attach from log
ue_verify() {
    local logfile="${1:-$LOG_DIR/ue.log}"
    log_stage "UE Verification"
    local all_ok=true

    # Cell sync
    if grep -q "BCCH update" "$logfile" || grep -q "SIB1 decoded" "$logfile"; then
        log_ok "Cell sync      : SIB1 decoded ✓"
    else
        log_fail "Cell sync      : SIB1 not found"
        all_ok=false
    fi

    # RACH
    if grep -q "RA procedure succeeded" "$logfile"; then
        rnti=$(grep "RA procedure succeeded" "$logfile" | grep -oP 'TC-RNTI \w+' | head -1)
        log_ok "RACH           : 4-step RA complete, $rnti ✓"
    else
        log_fail "RACH           : RA procedure not found"
        all_ok=false
    fi

    # RRC Connected
    if grep -q "NR_RRC_CONNECTED" "$logfile"; then
        log_ok "RRC            : NR_RRC_CONNECTED ✓"
    else
        log_fail "RRC            : not connected"
        all_ok=false
    fi

    # Registration Accept
    if grep -q "Registration Accept" "$logfile"; then
        log_ok "NAS            : Registration Accept received ✓"
    else
        log_fail "NAS            : Registration Accept not found"
        all_ok=false
    fi

    # PDU session
    if grep -q "PDU Session Establishment Accept" "$logfile"; then
        ue_ip=$(grep "UE IPv4" "$logfile" | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)
        log_ok "PDU Session    : established, UE IP=$ue_ip ✓"
    else
        log_fail "PDU Session    : not established"
        all_ok=false
    fi

    # TUN interface
    local tuns; tuns=$(ip addr show | grep oaitun | awk '{print $2}' || true)
    if [[ -n "$tuns" ]]; then
        log_ok "TUN interfaces : $tuns ✓"
    else
        log_fail "TUN interfaces : none found"
        all_ok=false
    fi

    $all_ok && return 0 || return 1
}

# Run a quick iperf3 DL test from ext-dn and report throughput
ue_iperf3_test() {
    local ue_ip="${1:-10.0.0.2}"
    local duration="${2:-10}"
    log_info "Running iperf3 DL test: ext-dn -> $ue_ip (${duration}s)..."

    # Start server on UE TUN
    iperf3 -s -B "$ue_ip" -D --logfile "$LOG_DIR/iperf3_server.log" 2>/dev/null
    sleep 1

    # Run client from ext-dn
    result=$(docker exec oai-ext-dn iperf3 -c "$ue_ip" -t "$duration" -i 0 --json 2>/dev/null)
    pkill -f "iperf3 -s" 2>/dev/null || true

    if [[ -n "$result" ]]; then
        dl_bps=$(echo "$result" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); \
             print(int(d['end']['sum_received']['bits_per_second']))" 2>/dev/null)
        dl_mbps=$(( dl_bps / 1000000 ))
        log_ok "iperf3 DL      : ${dl_mbps} Mbps ✓"
        echo "$result" > "$LOG_DIR/iperf3_dl_quick.json"
    else
        log_fail "iperf3 DL      : no result from ext-dn"
        return 1
    fi
}

# Map RNTI to UE identity from gNB + UE logs
build_rnti_map() {
    local gnb_log="${1:-$LOG_DIR/gnb.log}"
    local ue_log="${2:-$LOG_DIR/ue.log}"
    local out_file="$LOG_DIR/rnti_map.csv"

    echo "rnti_decimal,rnti_hex,imsi,ue_ip,dnn" > "$out_file"

    # Extract RNTI from UE log
    rnti_hex=$(grep -oP 'TC-RNTI \K[0-9a-f]+' "$ue_log" | tail -1)
    ue_ip=$(grep "UE IPv4" "$ue_log" | grep -oP '\d+\.\d+\.\d+\.\d+' | tail -1)
    imsi=$(grep -oP 'imsi\s*=\s*"\K[0-9]+' "$BENCH_DIR/config/ue/ue_smoke.conf" | head -1)

    if [[ -n "$rnti_hex" ]]; then
        rnti_dec=$(( 16#$rnti_hex ))
        echo "$rnti_dec,$rnti_hex,$imsi,$ue_ip,oai" >> "$out_file"
        log_ok "RNTI map       : RNTI=$rnti_dec (0x$rnti_hex), IMSI=$imsi, IP=$ue_ip"
    else
        log_warn "RNTI map       : could not extract RNTI from UE log"
    fi

    log_info "RNTI map saved to: $out_file"
}

# --------------- Cleanup trap -----------------------------------------------

cleanup_all() {
    log_warn "Cleanup triggered — stopping all components..."
    tracer_stop  2>/dev/null || true
    ue_stop      2>/dev/null || true
    gnb_stop     2>/dev/null || true
    core_stop    2>/dev/null || true
}
