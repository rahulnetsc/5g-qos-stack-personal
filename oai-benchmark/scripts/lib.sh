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
log_stage() {
    echo -e "\n${C_BOLD}${C_BLUE}════════════════════════════════════════${C_RESET}"
    echo -e "${C_BOLD}${C_BLUE} $*${C_RESET}"
    echo -e "${C_BOLD}${C_BLUE}════════════════════════════════════════${C_RESET}"
}

# Wait up to $3 seconds for a command to succeed, polling every 1s
wait_for() {
    local desc="$1" cmd="$2" timeout="$3"
    local elapsed=0
    echo -ne "${C_YELLOW}[WAIT]${C_RESET}  $desc ..."
    while ! eval "$cmd" &>/dev/null; do
        if (( elapsed >= timeout )); then
            echo -e " ${C_RED}TIMEOUT after ${timeout}s${C_RESET}"
            return 1
        fi
        sleep 1; (( elapsed++ ))
        echo -n "."
    done
    echo -e " ${C_GREEN}OK (${elapsed}s)${C_RESET}"
    return 0
}

# Wait for a string to appear in a log file
wait_for_log() {
    local desc="$1" logfile="$2" pattern="$3" timeout="$4"
    wait_for "$desc" "grep -q '$pattern' '$logfile'" "$timeout"
}

# --------------- Database helpers --------------------------------------------

_mysql() {
    # Run a MySQL query against oai_db, suppress password warning
    docker exec mysql mysql -u root -plinux oai_db -sN \
        --connect-timeout=5 "$@" 2>/dev/null
}

# Check both subscriber tables for a given IMSI.
# Returns 0 only if BOTH rows exist.
check_subscribers() {
    local imsi="${1:-208990100001100}"
    log_stage "Subscriber Database Verification (IMSI $imsi)"
    local all_ok=true

    set +e

    # Table 1: Authentication credentials
    local auth_count
    auth_count=$(_mysql -e \
        "SELECT COUNT(*) FROM AuthenticationSubscription WHERE ueid='$imsi';")
    if [[ "${auth_count:-0}" -ge 1 ]]; then
        local algo key_hint
        algo=$(_mysql -e \
            "SELECT algorithmId FROM AuthenticationSubscription WHERE ueid='$imsi';")
        key_hint=$(_mysql -e \
            "SELECT LEFT(encPermanentKey,8) FROM AuthenticationSubscription WHERE ueid='$imsi';")
        log_ok "AuthenticationSubscription : found  algo=$algo  key=${key_hint}..."
    else
        log_fail "AuthenticationSubscription : IMSI $imsi NOT in DB"
        log_fail "  Fix: INSERT INTO AuthenticationSubscription ..."
        all_ok=false
    fi

    # Table 2: Session management profile (needed for PDU session)
    local sess_count
    sess_count=$(_mysql -e \
        "SELECT COUNT(*) FROM SessionManagementSubscriptionData WHERE ueid='$imsi';")
    if [[ "${sess_count:-0}" -ge 1 ]]; then
        local plmn nssai
        plmn=$(_mysql -e \
            "SELECT servingPlmnid FROM SessionManagementSubscriptionData WHERE ueid='$imsi';")
        nssai=$(_mysql -e \
            "SELECT singleNssai FROM SessionManagementSubscriptionData WHERE ueid='$imsi';")
        log_ok "SessionManagementData      : found  plmn=$plmn  nssai=$nssai"
    else
        log_fail "SessionManagementData      : session profile for $imsi NOT in DB"
        log_fail "  This is why PDU sessions fail even after successful authentication"
        log_fail "  Fix: INSERT INTO SessionManagementSubscriptionData ..."
        log_fail "  Full SQL:"
        cat << SQL
  docker exec mysql mysql -u root -plinux oai_db -e "
  INSERT INTO SessionManagementSubscriptionData
    (ueid, servingPlmnid, singleNssai, dnnConfigurations)
  VALUES
    ('$imsi', '20899',
     '{\"sst\": 1, \"sd\": \"FFFFFF\"}',
     '{\"oai\":{\"pduSessionTypes\":{\"defaultSessionType\":\"IPV4\"},
       \"sscModes\":{\"defaultSscMode\":\"SSC_MODE_1\"},
       \"5gQosProfile\":{\"5qi\":9,\"arp\":{\"priorityLevel\":15,
       \"preemptCap\":\"NOT_PREEMPT\",\"preemptVuln\":\"PREEMPTABLE\"},
       \"priorityLevel\":1},
       \"sessionAmbr\":{\"uplink\":\"1000Mbps\",\"downlink\":\"1000Mbps\"}}}');"
SQL
        all_ok=false
    fi

    # Also check SQN (sequence number — can cause auth failure on repeated runs)
    local sqn
    sqn=$(_mysql -e \
        "SELECT JSON_EXTRACT(sequenceNumber,'$.sqn')
         FROM AuthenticationSubscription WHERE ueid='$imsi';" | tr -d '"')
    [[ -n "$sqn" ]] && log_info "Auth SQN                   : $sqn (auto-increments on each attach)"

    set -e
    $all_ok && return 0 || return 1
}

# --------------- CN5G core diagnostics ---------------------------------------

# Scan AMF, SMF, UPF logs for errors and PDU session events.
# Call this automatically when Stage 4 fails.
diagnose_pdu_failure() {
    local imsi="${1:-208990100001100}"
    log_stage "Automated PDU Session Failure Diagnosis"

    echo -e "${C_BOLD}── Subscriber Tables ──${C_RESET}"
    check_subscribers "$imsi" || true

    echo ""
    echo -e "${C_BOLD}── AMF Log: Registration + PDU session events ──${C_RESET}"
    set +e
    docker logs oai-amf 2>&1 | \
        grep -iE "PDU|session|register|error|reject|fail|$imsi|RNTI" | \
        tail -25 | sed 's/^/  [AMF] /'

    echo ""
    echo -e "${C_BOLD}── SMF Log: Session creation + errors ──${C_RESET}"
    docker logs oai-smf 2>&1 | \
        grep -iE "PDU|session|error|fail|reject|$imsi|DNN|UPF|N4" | \
        tail -25 | sed 's/^/  [SMF] /'

    echo ""
    echo -e "${C_BOLD}── UPF Log: N4 session + data plane ──${C_RESET}"
    docker logs oai-upf 2>&1 | \
        grep -iE "error|fail|session|N4|PFCP|GTP|$imsi" | \
        tail -15 | sed 's/^/  [UPF] /'

    echo ""
    echo -e "${C_BOLD}── UE Log: NAS layer messages ──${C_RESET}"
    local ue_log="${LOG_DIR}/ue.log"
    if [[ -f "$ue_log" ]]; then
        grep -iE "NAS|Registration|PDU|Auth|security|error|reject|RNTI" \
            "$ue_log" 2>/dev/null | tail -30 | sed 's/^/  [UE]  /'

        echo ""
        echo -e "${C_BOLD}── UE RNTI and MAC stats (last 5 entries) ──${C_RESET}"
        grep -E "RNTI|DL harq|UL harq" "$ue_log" 2>/dev/null | \
            tail -15 | sed 's/^/  [MAC] /'
    fi

    set -e

    echo ""
    echo -e "${C_BOLD}── Common Causes ──${C_RESET}"
    echo "  1. SessionManagementSubscriptionData missing  → see fix above"
    echo "  2. Auth SQN mismatch after multiple runs      → reset SQN in DB:"
    echo "     docker exec mysql mysql -u root -plinux oai_db -e \\"
    echo "       \"UPDATE AuthenticationSubscription SET"
    echo "         sequenceNumber=JSON_SET(sequenceNumber, '\\$.sqn', '000000000020')"
    echo "         WHERE ueid='$imsi';\""
    echo "  3. DNN 'oai' not in SMF config               → check conf/config.yaml"
    echo "  4. UPF N4 session not established             → check SMF log for N4"
    echo "  5. UE config pdu_sessions array missing       → check ue_smoke.conf"
}

# Quick core health snapshot (for use in Stage 3 or on-demand)
check_core_health() {
    log_stage "Core Network Health Snapshot"
    local containers=("oai-amf" "oai-smf" "oai-upf" "oai-nrf"
                       "oai-udr" "oai-udm" "oai-ausf")
    local all_ok=true
    for c in "${containers[@]}"; do
        local status
        status=$(docker inspect "$c" --format '{{.State.Health.Status}}' 2>/dev/null \
                 || echo "not running")
        if [[ "$status" == "healthy" ]]; then
            log_ok "$(printf '%-12s' "$c") : $status"
        else
            log_fail "$(printf '%-12s' "$c") : $status"
            all_ok=false
        fi
    done

    # Check AMF-SMF-UPF registration chain
    set +e
    local amf_smf
    amf_smf=$(docker logs oai-amf 2>&1 | grep -c "SMF.*registered\|smf.*registered" || echo 0)
    local smf_upf
    smf_upf=$(docker logs oai-smf 2>&1 | grep -c "UPF.*registered\|upf.*associated\|N4.*established" || echo 0)
    set -e
    log_info "AMF→SMF registrations  : $amf_smf"
    log_info "SMF→UPF associations   : $smf_upf"
    $all_ok && return 0 || return 1
}

# --------------- CN5G core start/stop ----------------------------------------

core_start() {
    log_info "Starting CN5G docker stack..."
    cd "$CN5G_DIR" || { log_fail "CN5G directory not found: $CN5G_DIR"; return 1; }
    docker compose up -d 2>&1 | grep -E "Starting|Started|healthy|error" || true
    log_ok "Docker compose started"
}

core_stop() {
    log_info "Stopping CN5G docker stack..."
    cd "$CN5G_DIR" || return 0
    docker compose down 2>&1 | grep -E "Stopping|Stopped|Removing|Removed|Network" || true
    log_ok "CN5G stopped"
}

core_wait_healthy() {
    local containers=("oai-amf" "oai-smf" "oai-upf" "oai-nrf"
                       "oai-udr" "oai-udm" "oai-ausf" "oai-ext-dn")
    local timeout="$CORE_WAIT_TIMEOUT"
    local elapsed=0
    log_info "Waiting for all CN5G containers to be healthy (timeout ${timeout}s)..."
    while true; do
        local all_healthy=true
        for c in "${containers[@]}"; do
            local status
            status=$(docker inspect "$c" --format '{{.State.Health.Status}}' \
                     2>/dev/null || echo "missing")
            [[ "$status" != "healthy" ]] && all_healthy=false && break
        done
        $all_healthy && { log_ok "All containers healthy"; return 0; }
        (( elapsed >= timeout )) && {
            log_fail "Containers not healthy after ${timeout}s"
            check_core_health
            return 1
        }
        sleep 2; (( elapsed+=2 ))
        echo -ne "\r${C_YELLOW}[WAIT]${C_RESET}  ${elapsed}s elapsed..."
    done
}

core_discover_network() {
    log_stage "Network Discovery"
    local containers=("oai-amf" "oai-smf" "oai-upf" "oai-nrf"
                       "oai-udr" "oai-udm" "oai-ausf" "oai-ext-dn" "ims")
    local env_out="$LOG_DIR/discovered_network.env"
    mkdir -p "$LOG_DIR"; : > "$env_out"

    for c in "${containers[@]}"; do
        local ip status
        ip=$(docker inspect "$c" \
             --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
        status=$(docker inspect "$c" --format '{{.State.Health.Status}}' 2>/dev/null)
        if [[ -n "$ip" ]]; then
            log_ok "$(printf '%-15s  IP=%-18s  health=%s' "$c" "$ip" "$status")"
            local varname="${c//-/_}"; varname="${varname^^}_IP"
            echo "export ${varname}=${ip}" >> "$env_out"
        else
            log_warn "$c: not found or no IP"
        fi
    done

    local host_ip
    host_ip=$(ip -4 addr show | grep "192\.168\.70\." | \
              awk '{print $2}' | cut -d/ -f1 | head -1)
    echo "export HOST_BRIDGE_IP=${host_ip}" >> "$env_out"
    log_ok "Host bridge IP : ${host_ip}"
    log_info "Network env    : $env_out"
    # shellcheck source=/dev/null
    source "$env_out"

    local gnb_amf
    gnb_amf=$(grep "amf_ip_address" "$GNB_CONF" \
              | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)
    if [[ "$gnb_amf" == "${OAI_AMF_IP:-$AMF_IP}" ]]; then
        log_ok "gNB AMF IP     : $gnb_amf matches Docker AMF ✓"
    else
        log_warn "gNB config AMF=$gnb_amf but Docker AMF=${OAI_AMF_IP:-$AMF_IP} — fix config!"
    fi
}

# --------------- gNB functions -----------------------------------------------

GNB_PID_FILE="$LOG_DIR/gnb.pid"

gnb_start() {
    local logfile="${1:-$LOG_DIR/gnb.log}"
    log_info "Starting gNB -> $logfile"
    mkdir -p "$LOG_DIR"
    # shellcheck disable=SC2024
    sudo "$GNB_BIN" \
        -O "$GNB_CONF" \
        --rfsim \
        --rfsimulator.[0].serveraddr server \
        --T_stdout 2 \
        --T_nowait \
        > "$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$GNB_PID_FILE"
    log_ok "gNB started (PID $pid)"
}

gnb_stop() {
    if [[ -f "$GNB_PID_FILE" ]]; then
        local pid; pid=$(cat "$GNB_PID_FILE")
        log_info "Stopping gNB (PID $pid)..."
        sudo kill "$pid" 2>/dev/null || true
        sleep 2; sudo kill -9 "$pid" 2>/dev/null || true
        rm -f "$GNB_PID_FILE"
    else
        sudo pkill -f nr-softmodem 2>/dev/null || true
    fi
    log_ok "gNB stopped"
}

gnb_verify() {
    local logfile="${1:-$LOG_DIR/gnb.log}"
    log_stage "gNB Verification"
    local all_ok=true

    _check_log() {
        local label="$1" pattern="$2" ok_msg="$3" fail_msg="$4"
        if grep -q "$pattern" "$logfile" 2>/dev/null; then
            log_ok "$label : $ok_msg ✓"
        else
            log_fail "$label : $fail_msg"
            all_ok=false
        fi
    }

    _check_log "N2 Setup  " "Received NGSetupResponse from AMF" \
        "NGSetupResponse received" "NGSetupResponse NOT found"
    _check_log "F1 Setup  " "sending F1 Setup Response" \
        "CU-DU F1 exchange complete" "F1 Setup not found"
    _check_log "Cell      " "is in service" \
        "$(grep 'is in service' "$logfile" | grep -oP 'PLMN \S+' | head -1) in service" \
        "cell not in service"
    _check_log "SDAP      " "SDAP layer is enabled" "enabled" "SDAP not enabled"

    local gtp_line
    gtp_line=$(grep "Configuring GTPu address" "$logfile" | head -1 | \
               sed 's/.*\[GTPU\]//' | tr -s ' ')
    if [[ -n "$gtp_line" ]]; then
        log_ok "GTP-U (N3):$gtp_line ✓"
    else
        log_fail "GTP-U (N3): not configured"; all_ok=false
    fi

    if ss -tlnp | grep -q "$T_TRACER_PORT"; then
        log_ok "T Tracer  : port $T_TRACER_PORT listening ✓"
    else
        log_warn "T Tracer  : port $T_TRACER_PORT not open (need --T_stdout 2 --T_nowait)"
    fi

    if ss -tlnp | grep -q "$RFSIM_PORT"; then
        log_ok "rfsim     : server listening on port $RFSIM_PORT ✓"
    else
        log_fail "rfsim     : not listening on port $RFSIM_PORT"; all_ok=false
    fi

    local ue_params
    ue_params=$(grep "Command line parameters for OAI UE" "$logfile" | \
                sed 's/.*OAI UE: //' | head -1)
    [[ -n "$ue_params" ]] && log_info "UE hint   : $ue_params"

    $all_ok && return 0 || return 1
}

# --------------- T tracer functions ------------------------------------------

TRACER_PID_FILE="$LOG_DIR/tracer.pid"

tracer_start() {
    local out_dir="${1:-$LOG_DIR}"
    log_info "Starting T tracer collector -> $out_dir"
    : > "$LOG_DIR/tracer_collector.log"
    # -u: unbuffered stdout/stderr so tracer_collector.log populates immediately
    PYTHONUNBUFFERED=1 python3 -u "$T_COLLECTOR" "$out_dir" \
        >> "$LOG_DIR/tracer_collector.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$TRACER_PID_FILE"
    sleep 3
    if kill -0 "$pid" 2>/dev/null; then
        log_ok "T tracer collector running (PID $pid)"
        # Show what events were found and activated
        grep -E "numeric ID|Output:|Found|Connected|Collecting" \
            "$LOG_DIR/tracer_collector.log" 2>/dev/null | sed 's/^/  /' || true
    else
        log_fail "T tracer collector exited — full log:"
        cat "$LOG_DIR/tracer_collector.log" | sed 's/^/  /'
        return 1
    fi
}

tracer_stop() {
    if [[ -f "$TRACER_PID_FILE" ]]; then
        local pid; pid=$(cat "$TRACER_PID_FILE")
        kill "$pid" 2>/dev/null || true
        sleep 1; rm -f "$TRACER_PID_FILE"
        log_ok "T tracer collector stopped"
    fi
}

tracer_snapshot() {
    local name="${1:-before}"
    local snap_file="$LOG_DIR/tracer_snapshot_${name}.env"
    : > "$snap_file"
    for f in "$LOG_DIR"/*_raw.csv; do
        [[ -f "$f" ]] || continue
        local rows; rows=$(wc -l < "$f")
        local key; key=$(basename "${f%_raw.csv}")
        echo "${key}=${rows}" >> "$snap_file"
    done
    log_info "T tracer snapshot '$name' saved ($(wc -l < "$snap_file") files)"
}

tracer_verify_data() {
    local before="${1:-before}" after="${2:-after}"
    local before_f="$LOG_DIR/tracer_snapshot_${before}.env"
    local after_f="$LOG_DIR/tracer_snapshot_${after}.env"
    log_stage "T Tracer — Data Verification"
    local all_ok=true

    if [[ ! -f "$before_f" || ! -f "$after_f" ]]; then
        log_fail "Snapshot files missing"
        return 1
    fi

    declare -A before_counts
    while IFS='=' read -r key val; do
        before_counts["$key"]="$val"
    done < "$before_f"

    printf "  %-48s  %7s  %7s  %9s\n" "Event file" "Before" "After" "New rows"
    printf "  %-48s  %7s  %7s  %9s\n" "---------" "------" "-----" "--------"

    while IFS='=' read -r key val_after; do
        local val_before="${before_counts[$key]:-1}"
        local new=$(( val_after - val_before ))
        local status_str
        if (( new > 5 )); then
            status_str="${C_GREEN}+${new}${C_RESET}"
        elif (( new > 0 )); then
            status_str="${C_YELLOW}+${new} (low)${C_RESET}"
        else
            status_str="${C_RED}+0 (no data)${C_RESET}"; all_ok=false
        fi
        printf "  %-48s  %7s  %7s  " "$key" "$val_before" "$val_after"
        echo -e "$status_str"
    done < "$after_f"

    echo ""
    $all_ok && log_ok "T tracer captured events during traffic ✓" \
             || log_fail "Some T tracer files received no data"
    $all_ok && return 0 || return 1
}

tracer_show_sample() {
    local event="${1:-gnb_mac_lcid_dl}" rows="${2:-5}"
    local f="$LOG_DIR/${event}_raw.csv"
    if [[ -f "$f" ]]; then
        local total; total=$(( $(wc -l < "$f") - 1 ))
        log_info "Last $rows rows of $event ($total data rows total):"
        head -1 "$f" | sed 's/^/  HDR: /'
        tail -"$rows" "$f" | sed 's/^/  ROW: /'
    else
        log_warn "$f not found"
    fi
}

# --------------- Network test functions --------------------------------------

ping_test() {
    local ue_ip="${1:-10.0.0.2}" count="${2:-4}"
    log_stage "Ping Test (ICMP)"
    log_info "Sending $count ICMP pings: oai-ext-dn -> UE ($ue_ip)"

    set +e
    local result
    result=$(docker exec oai-ext-dn ping -c "$count" -W 2 "$ue_ip" 2>&1 || true)
    echo "$result" | sed 's/^/  /'
    local loss
    loss=$(echo "$result" | grep -oP '\d+(?=% packet loss)' || echo "100")
    set -e

    if (( loss == 0 )); then
        log_ok "Ping : 0% loss ✓"
    elif (( loss < 100 )); then
        log_warn "Ping : ${loss}% packet loss (partial)"
    else
        log_warn "Ping : 100% packet loss — ICMP blocked by UPF filter (non-fatal)"
        log_warn "        TCP iperf3 test is the definitive data plane check"
    fi
    return 0   # always non-fatal
}

# --------------- UE TUN policy routing  ─────────────────────────────────────

# After UE attaches, Linux routes via Docker bridge (oai-cn5g) even when the
# source is bound to the TUN IP (10.0.0.2). This bypasses the 5G UL path.
# Policy routing fixes this: traffic FROM 10.0.0.2 → always exit via oaitun_ue1.
setup_ue_routing() {
    local ue_ip="${1:-10.0.0.2}"
    local tun_dev
    tun_dev=$(ip addr show 2>/dev/null | grep "oaitun" | awk -F': ' '{print $2}' | head -1)
    [[ -z "$tun_dev" ]] && tun_dev="oaitun_ue1"

    log_info "Setting up policy routing: from $ue_ip → $tun_dev (table 100)"
    sudo ip rule del from "$ue_ip" table 100 2>/dev/null || true
    sudo ip route flush table 100 2>/dev/null || true
    sudo ip rule add from "$ue_ip" table 100 priority 100 2>/dev/null
    sudo ip route add default dev "$tun_dev" table 100 2>/dev/null
    log_ok "Policy routing active: $ue_ip sources exit via $tun_dev ✓"
}

teardown_ue_routing() {
    sudo ip rule del from 10.0.0.0/8 table 100 2>/dev/null || true
    sudo ip route flush table 100 2>/dev/null || true
}

# =============================================================================
# diagnose_dataplane() — hop-by-hop 5G user-plane diagnosis
#
# Tests each hop of the DL path independently using tcpdump:
#   Hop 1: ext-dn → UPF N6 (does traffic leave ext-dn toward UPF?)
#   Hop 2: UPF → gNB N3 (does UPF emit GTP-U on UDP:2152?)
#   Hop 3: gNB → UE TUN (does traffic arrive at oaitun_ue1?)
#
# Each hop uses a brief tcpdump capture (5s) while injecting a small burst
# from ext-dn to the UE IP. The first hop where packets disappear is the
# failing component.
# =============================================================================
diagnose_dataplane() {
    local ue_ip="${1:-10.0.0.2}"
    local upf_ip ext_dn_ip tun_dev bridge_if
    upf_ip=$(docker inspect oai-upf \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    ext_dn_ip=$(docker inspect oai-ext-dn \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    tun_dev=$(ip addr show 2>/dev/null | grep "oaitun" | awk -F': ' '{print $2}' | head -1)
    tun_dev="${tun_dev:-oaitun_ue1}"
    # Find the Docker bridge interface name
    bridge_if=$(ip link show 2>/dev/null | grep -oP "br-[a-z0-9]+|oai-cn5g" | head -1)
    bridge_if="${bridge_if:-oai-cn5g}"

    log_stage "Data Plane Hop-by-Hop Diagnosis"
    log_info "Testing DL path: ext-dn ($ext_dn_ip) → UPF ($upf_ip) → gNB → UE ($ue_ip)"
    log_info "Bridge interface: $bridge_if  |  UE TUN: $tun_dev"
    echo ""

    # ── Pre-check: ext-dn routing ─────────────────────────────────────────────
    log_info "ext-dn routing table:"
    docker exec oai-ext-dn ip route show 2>/dev/null | sed 's/^/  /'
    echo ""

    # ── Hop 1: Does ext-dn route traffic for 10.0.0.2 toward UPF? ─────────────
    log_info "── Hop 1: ext-dn → UPF N6 (tcpdump at UPF eth0, 5s) ──"
    set +e
    local hop1_pcap="/tmp/hop1_upf_n6.pcap"
    docker exec -d oai-upf \
        tcpdump -i eth0 -c 20 -w /tmp/hop1.pcap dst "$ue_ip" 2>/dev/null || \
        log_warn "tcpdump not available in UPF container — skipping pcap"
    sleep 1
    # Inject traffic from ext-dn to UE IP (nc is more reliable than ping for TCP-filtered UPFs)
    docker exec oai-ext-dn bash -c \
        "for i in 1 2 3; do nc -z -w1 $ue_ip 5201 2>/dev/null; sleep 0.5; done" &
    sleep 4
    local hop1_pkts
    hop1_pkts=$(docker exec oai-upf bash -c \
        "tcpdump -r /tmp/hop1.pcap --count 2>/dev/null | head -1" 2>/dev/null || echo "0")
    if echo "$hop1_pkts" | grep -qE "^[1-9]"; then
        log_ok "Hop 1 (ext-dn→UPF N6): $hop1_pkts packets seen at UPF ✓"
    else
        log_fail "Hop 1 (ext-dn→UPF N6): NO packets at UPF eth0"
        log_fail "  ext-dn is not routing 10.0.0.2 traffic to UPF"
        log_fail "  Check: docker exec oai-ext-dn ip route (need 10.x via $upf_ip)"
    fi
    echo ""

    # ── Hop 2: Does UPF emit GTP-U toward gNB on UDP:2152? ─────────────────────
    log_info "── Hop 2: UPF → gNB N3 (GTP-U on UDP:2152, 5s) ──"
    local hop2_file="/tmp/hop2_gtp.txt"
    sudo timeout 5 tcpdump -i "$bridge_if" -nn \
        udp port "$GTP_PORT" -c 20 2>/dev/null > "$hop2_file" &
    local tcpdump_pid=$!
    # Re-inject from ext-dn
    docker exec oai-ext-dn bash -c \
        "for i in 1 2 3 4 5; do nc -z -w1 $ue_ip 5201 2>/dev/null; sleep 0.5; done" &
    wait $tcpdump_pid 2>/dev/null || true
    local hop2_pkts; hop2_pkts=$(wc -l < "$hop2_file" 2>/dev/null || echo 0)
    if (( hop2_pkts > 2 )); then
        log_ok "Hop 2 (UPF→gNB GTP-U UDP:2152): $hop2_pkts lines captured ✓"
        grep "192.168.70" "$hop2_file" | head -3 | sed 's/^/  /'
    else
        log_fail "Hop 2 (UPF→gNB GTP-U UDP:2152): NO GTP-U packets on $bridge_if"
        log_fail "  UPF is NOT forwarding to gNB via GTP-U"
        log_fail "  Possible causes:"
        log_fail "    • UPF has no N4 FAR rule for this PDU session"
        log_fail "    • gNB GTP-U endpoint in UPF FAR is wrong"
        log_fail "    • PDU session establishment was incomplete at UPF N4 level"
        log_info "  UPF N4 session state:"
        docker logs oai-upf 2>&1 | grep -iE "pfcp|N4|FAR|create|session" | \
            tail -10 | sed 's/^/    /'
    fi
    echo ""

    # ── Hop 3: Does anything arrive at the UE TUN? ────────────────────────────
    log_info "── Hop 3: gNB → UE TUN ($tun_dev, 5s) ──"
    local hop3_file="/tmp/hop3_tun.txt"
    sudo timeout 5 tcpdump -i "$tun_dev" -nn -c 20 2>/dev/null > "$hop3_file" &
    local tun_pid=$!
    docker exec oai-ext-dn bash -c \
        "for i in 1 2 3 4 5; do nc -z -w1 $ue_ip 5201 2>/dev/null; sleep 0.5; done" &
    wait $tun_pid 2>/dev/null || true
    local hop3_pkts; hop3_pkts=$(wc -l < "$hop3_file" 2>/dev/null || echo 0)
    if (( hop3_pkts > 2 )); then
        log_ok "Hop 3 (gNB→UE TUN $tun_dev): $hop3_pkts lines captured ✓"
        head -3 "$hop3_file" | sed 's/^/  /'
        log_ok "Full DL data plane is working — iperf3 failure is version/protocol issue"
    else
        log_fail "Hop 3 (gNB→UE TUN $tun_dev): NO packets arriving at UE TUN"
        if (( hop2_pkts > 2 )); then
            log_fail "  GTP-U reaches gNB but gNB is NOT delivering to UE TUN"
            log_fail "  Possible causes:"
            log_fail "    • gNB MAC scheduler not scheduling DL for RNTI"
            log_fail "    • rfsimulator channel broken after gNB restart"
            log_fail "    • PDCP/RLC layer issue in gNB"
        fi
    fi
    echo ""

    # ── Summary: T tracer snapshot (quick check for any MAC activity) ──────────
    log_info "── T tracer live check (gnb_mac_pusch_power_control rows after attach) ──"
    local pusch_rows
    pusch_rows=$(wc -l < "$LOG_DIR/gnb_mac_pusch_power_control_raw.csv" 2>/dev/null || echo 1)
    pusch_rows=$(( pusch_rows - 1 ))
    if (( pusch_rows > 0 )); then
        log_ok "PUSCH events: $pusch_rows rows — gNB IS scheduling UL for the UE"
        log_info "Sample PUSCH row:"
        tail -1 "$LOG_DIR/gnb_mac_pusch_power_control_raw.csv" | sed 's/^/  /'
    else
        log_fail "PUSCH events: 0 rows — gNB MAC scheduler has NO UL activity"
        log_fail "  This confirms the 5G user plane is not active"
    fi

    set -e
    echo ""
    log_stage "Hop-by-Hop Summary"
    echo "  Hop 1 (ext-dn→UPF N6):      check packets at UPF above"
    echo "  Hop 2 (UPF→gNB GTP-U:2152): check GTP-U capture above"
    echo "  Hop 3 (gNB→UE TUN):         check TUN capture above"
    echo "  Hop 4 (T tracer/PUSCH):      check PUSCH events above"
    echo ""
    echo "  First hop with 0 packets = failing component."
}

# Helper: get IMAGE SHA of running oai-ext-dn (same binary, regardless of tag updates)
_extdn_image_sha() {
    docker inspect oai-ext-dn --format '{{.Image}}' 2>/dev/null
}

# Helper: verify and print which iperf3 version will be used in a container
# Uses --entrypoint iperf3 to bypass any custom container entrypoint.
# log_info is redirected to stderr so the caller captures ONLY the version string.
_log_container_iperf3_ver() {
    local sha="$1"
    local ver
    ver=$(docker run --rm --entrypoint iperf3 "$sha" --version 2>/dev/null | head -1)
    log_info "Container iperf3 : $ver" >&2   # >&2 keeps stdout clean for caller
    echo "$ver"
}

iperf3_dl() {
    local ue_ip="${1:-10.0.0.2}" duration="${2:-$TRAFFIC_DURATION}"
    local result_file="$LOG_DIR/iperf3_dl.json"
    log_stage "iperf3 Downlink (ext-dn → UE via 5G stack)"
    log_info "Duration: ${duration}s  UE IP: $ue_ip"
    log_info "Approach: server in ext-dn (3.9), client on host (3.16) with -R"
    log_info "  -R: server SENDS (= DL); 3.16 client → 3.9 server is compatible"

    set +e

    # ── Version info ──────────────────────────────────────────────────────────
    local host_ver extdn_ver
    host_ver=$(iperf3 --version 2>/dev/null | head -1)
    extdn_ver=$(docker exec oai-ext-dn iperf3 --version 2>/dev/null | head -1)
    log_info "iperf3 host   : $host_ver"
    log_info "iperf3 ext-dn : $extdn_ver"

    # ── Route check ───────────────────────────────────────────────────────────
    local upf_ip extdn_route
    upf_ip=$(docker inspect oai-upf \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    local ext_dn_ip
    ext_dn_ip=$(docker inspect oai-ext-dn \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    extdn_route=$(docker exec oai-ext-dn ip route show 2>/dev/null | grep "10\." || true)
    if [[ -z "$extdn_route" ]]; then
        log_warn "ext-dn missing route to 10.0.0.0/8 — adding via UPF ($upf_ip)..."
        docker exec oai-ext-dn ip route add 10.0.0.0/8 via "$upf_ip" dev eth0 2>/dev/null \
            && log_ok "Route added" || log_warn "Route add failed"
    else
        log_ok "ext-dn route: $extdn_route ✓"
    fi

    # ── Start iperf3 server in ext-dn ────────────────────────────────────────
    # ext-dn server (iperf3 3.9) listens on :5201
    docker exec oai-ext-dn pkill iperf3 2>/dev/null || true
    sleep 1
    docker exec -d oai-ext-dn iperf3 -s
    sleep 3

    if docker exec oai-ext-dn ss -tlnp 2>/dev/null | grep -q ":5201"; then
        log_ok "ext-dn iperf3 server :5201 listening ✓"
    else
        log_fail "ext-dn iperf3 server not listening on :5201"
        set -e; return 1
    fi

    # ── DL test: host client (3.16) → ext-dn server (3.9), -R makes server send ──
    # Traffic path: ext-dn sends → UPF (via 10.0.0.x route) → GTP-U → gNB → UE TUN
    # -B $ue_ip: receive traffic on UE TUN interface
    log_info "Starting ${duration}s DL test (host -R client → ext-dn server) ..."
    local raw
    raw=$(iperf3 -c "$ext_dn_ip" -B "$ue_ip" -R \
          -t "$duration" -i 0 --json 2>&1) || true
    docker exec oai-ext-dn pkill iperf3 2>/dev/null || true
    set -e

    if echo "$raw" | python3 -c "import json,sys; json.load(sys.stdin)" &>/dev/null; then
        echo "$raw" > "$result_file"
        local dl_bps lost retx dl_mbps
        dl_bps=$(echo "$raw" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); \
             print(int(d['end']['sum_received']['bits_per_second']))" 2>/dev/null || echo 0)
        retx=$(echo "$raw" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); \
             print(d['end']['sum_sent'].get('retransmits',0))" 2>/dev/null || echo 0)
        dl_mbps=$(( dl_bps / 1_000_000 ))
        log_ok "DL Throughput  : ${dl_mbps} Mbps"
        log_ok "DL Retransmits : $retx"
        log_info "DL result      : $result_file"
        if (( dl_mbps > 0 )); then return 0; else return 1; fi
    else
        log_fail "iperf3 DL failed — no valid JSON"
        echo "$raw" | tail -8 | sed 's/^/  [CLI] /'
        log_info "UPF N4 session state:"
        docker logs oai-upf 2>&1 | grep -iE "pfcp|FAR|PDR|session" | \
            tail -5 | sed 's/^/  [UPF] /' || true
        return 1
    fi
}

iperf3_ul() {
    local ue_ip="${1:-10.0.0.2}" duration="${2:-$TRAFFIC_DURATION}"
    local result_file="$LOG_DIR/iperf3_ul.json"
    log_stage "iperf3 Uplink (UE → ext-dn via 5G stack)"
    log_info "Duration: ${duration}s  UE IP: $ue_ip"
    log_info "Approach: server in ext-dn (3.9), host client (3.16) sends, -B $ue_ip"

    set +e

    local ext_dn_ip
    ext_dn_ip=$(docker inspect oai-ext-dn \
        --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    log_info "ext-dn IP: $ext_dn_ip"

    # ── Start iperf3 server in ext-dn ────────────────────────────────────────
    docker exec oai-ext-dn pkill iperf3 2>/dev/null || true
    sleep 1
    docker exec -d oai-ext-dn iperf3 -s
    sleep 3

    if docker exec oai-ext-dn ss -tlnp 2>/dev/null | grep -q ":5201"; then
        log_ok "ext-dn iperf3 server :5201 listening ✓"
    else
        log_fail "ext-dn iperf3 server not listening on :5201"
        set -e; return 1
    fi

    # ── UL test: host client (3.16) sends to ext-dn server (3.9) ─────────────
    # -B $ue_ip: bind source to UE TUN IP — traffic exits via oaitun_ue1
    # (policy routing ensures this even though default route is via Docker bridge)
    log_info "Starting ${duration}s UL test (host client -B $ue_ip → ext-dn) ..."
    local raw
    raw=$(iperf3 -c "$ext_dn_ip" -B "$ue_ip" \
          -t "$duration" -i 0 --json 2>&1) || true
    docker exec oai-ext-dn pkill iperf3 2>/dev/null || true
    set -e

    if echo "$raw" | python3 -c "import json,sys; json.load(sys.stdin)" &>/dev/null; then
        echo "$raw" > "$result_file"
        local ul_bps retx ul_mbps
        ul_bps=$(echo "$raw" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); \
             print(int(d['end']['sum_received']['bits_per_second']))" 2>/dev/null || echo 0)
        retx=$(echo "$raw" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); \
             print(d['end']['sum_sent'].get('retransmits',0))" 2>/dev/null || echo 0)
        ul_mbps=$(( ul_bps / 1_000_000 ))
        log_ok "UL Throughput  : ${ul_mbps} Mbps"
        log_ok "UL Retransmits : $retx"
        log_info "UL result      : $result_file"
        if (( ul_mbps > 0 )); then return 0; else return 1; fi
    else
        log_fail "iperf3 UL failed — no valid JSON"
        echo "$raw" | tail -8 | sed 's/^/  [CLI] /'
        return 1
    fi
}

# --------------- UE functions -----------------------------------------------

UE_PID_FILE="$LOG_DIR/ue.pid"

ue_start() {
    local conf="${1:-$BENCH_DIR/config/ue/ue_smoke.conf}"
    local logfile="${2:-$LOG_DIR/ue.log}"
    log_info "Starting UE  conf=$(basename "$conf") -> $logfile"
    # shellcheck disable=SC2024
    sudo "$UE_BIN" \
        -O "$conf" \
        --rfsim \
        -r "$NR_PRB" --numerology "$NR_NUMEROLOGY" \
        --band "$NR_BAND" -C "$NR_ARFCN" \
        > "$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$UE_PID_FILE"
    log_ok "UE started (PID $pid)"
}

ue_stop() {
    if [[ -f "$UE_PID_FILE" ]]; then
        local pid; pid=$(cat "$UE_PID_FILE")
        log_info "Stopping UE (PID $pid)..."
        sudo kill "$pid" 2>/dev/null || true
        sleep 2; sudo kill -9 "$pid" 2>/dev/null || true
        rm -f "$UE_PID_FILE"
    else
        sudo pkill -f nr-uesoftmodem 2>/dev/null || true
    fi
    for tun in $(ip link show 2>/dev/null | grep "oaitun" | awk -F': ' '{print $2}'); do
        sudo ip link delete "$tun" 2>/dev/null || true
    done
    log_ok "UE stopped"
}

ue_verify() {
    local logfile="${1:-$LOG_DIR/ue.log}"
    log_stage "UE Protocol Verification"
    local all_ok=true

    _ue_check() {
        local label="$1" pattern="$2" ok_msg="$3"
        if grep -q "$pattern" "$logfile" 2>/dev/null; then
            log_ok "$(printf '%-15s' "$label") : $ok_msg ✓"
        else
            log_fail "$(printf '%-15s' "$label") : not found in UE log"
            all_ok=false
        fi
    }

    _ue_check "Cell sync"    "SIB1"                              "SIB1 decoded"
    _ue_check "RACH"         "RA procedure succeeded"           "4-step RA complete"
    _ue_check "RRC"          "NR_RRC_CONNECTED"                 "RRC Connected"
    _ue_check "Auth"         "security mode complete\|Security" "Authentication done"
    _ue_check "Registration" "Registration Accept"              "Registration Accept"
    _ue_check "PDU Session"  "PDU Session Establishment Accept" "PDU session established"

    set +e
    local tun_info
    tun_info=$(ip addr show 2>/dev/null | grep -A1 "oaitun" | grep "inet")
    set -e
    if [[ -n "$tun_info" ]]; then
        local ue_ip tun_name
        ue_ip=$(echo "$tun_info" | awk '{print $2}' | cut -d/ -f1 | head -1)
        tun_name=$(ip addr show 2>/dev/null | grep "oaitun" | \
                   awk -F': ' '{print $2}' | head -1)
        log_ok "$(printf '%-15s' "TUN interface") : $tun_name IP=$ue_ip ✓"
    else
        log_fail "$(printf '%-15s' "TUN interface") : no oaitun interface found"
        all_ok=false
    fi

    $all_ok && return 0 || return 1
}

ue_get_ip() {
    set +e
    local ip
    ip=$(ip addr show 2>/dev/null | grep -A1 "oaitun" | \
         grep "inet" | awk '{print $2}' | cut -d/ -f1 | head -1)
    set -e
    echo "$ip"
}

build_rnti_map() {
    local gnb_log="${1:-$LOG_DIR/gnb.log}"
    local ue_log="${2:-$LOG_DIR/ue.log}"
    local conf="${3:-$BENCH_DIR/config/ue/ue_smoke.conf}"
    local out_file="$LOG_DIR/rnti_map.csv"
    echo "rnti_decimal,rnti_hex,imsi,ue_ip,dnn" > "$out_file"

    set +e
    local rnti_hex ue_ip imsi
    rnti_hex=$(grep -oiP '(?:TC-RNTI|C-RNTI|RNTI)[=\s]+(?:0x)?\K[0-9a-f]+' \
               "$ue_log" 2>/dev/null | grep -v "^0$" | tail -1)
    [[ -z "$rnti_hex" ]] && \
        rnti_hex=$(grep -oP 'RNTI\s+\K[0-9a-f]+' "$gnb_log" 2>/dev/null | \
                   grep -v "0000" | tail -1)
    ue_ip=$(grep -oP '(?:UE IPv4|IPv4)[:\s]+\K[\d.]+' "$ue_log" 2>/dev/null | tail -1)
    imsi=$(grep -oP 'imsi\s*=\s*"\K[0-9]+' "$conf" 2>/dev/null | head -1)
    set -e

    if [[ -n "$rnti_hex" ]]; then
        local rnti_dec=$(( 16#$rnti_hex ))
        echo "$rnti_dec,$rnti_hex,$imsi,${ue_ip:-unknown},oai" >> "$out_file"
        log_ok "RNTI map : RNTI=$rnti_dec (0x$rnti_hex)  IMSI=$imsi  IP=${ue_ip:-?}"
    else
        log_warn "RNTI map : RNTI not found (non-fatal)"
    fi
    log_info "RNTI map : $out_file"
}

# --------------- Cleanup trap -----------------------------------------------

cleanup_all() {
    echo ""
    log_warn "Cleanup triggered — stopping all components..."
    tracer_stop  2>/dev/null || true
    ue_stop      2>/dev/null || true
    gnb_stop     2>/dev/null || true
    core_stop    2>/dev/null || true
}
