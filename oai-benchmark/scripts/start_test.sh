#!/bin/bash

# ==============================================================================
# OAI 5G STACK AUTOMATION & BENCHMARKING SCRIPT
# ==============================================================================

set -euo pipefail

# --- Path Configurations ---
BASE_DIR="$HOME/projects/5g-qos-stack"
OAI_DIR="$BASE_DIR/openairinterface5g"
CONF_DIR="$BASE_DIR/oai-benchmark/config"
LOG_DIR="$BASE_DIR/script-logs"

mkdir -p "$LOG_DIR"

# --- ANSI Colors for Scannability ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO] $(date +'%Y-%m-%d %H:%M:%S') $1${NC}"; }
log_warn() { echo -e "${YELLOW}[WARN] $(date +'%Y-%m-%d %H:%M:%S') $1${NC}"; }
log_err()  { echo -e "${RED}[ERR] $(date +'%Y-%m-%d %H:%M:%S') $1${NC}"; exit 1; }

# --- Pre-Flight Cleanup Routine ---
log_info "Performing pre-flight cleanup of legacy modems and performance test instances..."
sudo killall -9 nr-softmodem nr-uesoftmodem iperf3 2>/dev/null || true
docker exec oai-ext-dn killall -9 iperf3 2>/dev/null || true

# ==============================================================================
# STEP 1: DEPLOY & VERIFY CN5G CORE
# ==============================================================================

log_info "Starting OAI 5G Core Network via Docker Compose..."
cd "$OAI_DIR/doc/tutorial_resources/oai-cn5g"
docker compose up -d

log_info "Waiting for Core Network containers to reach 'healthy' state (2 min timeout)..."
TIMEOUT=120
ELAPSED=0
CHECK_INTERVAL=5

while [ $ELAPSED -lt $TIMEOUT ]; do
    UNHEALTHY=$(docker compose ps --format json | grep -v '"Health":"healthy"' | grep -v '"State":"running"' || true)
    
    if [ -z "$UNHEALTHY" ]; then
        log_info "All core network containers are HEALTHY!"
        break
    fi
    
    sleep $CHECK_INTERVAL
    ELAPSED=$((ELAPSED + CHECK_INTERVAL))
    echo -n "."
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    log_err "Timeout reached! Some CN5G containers failed to become healthy."
fi

# ==============================================================================
# STEP 2: START & VERIFY gNB
# ==============================================================================

log_info "Launching gNB in rfsimulator mode..."
cd "$OAI_DIR"

sudo ./cmake_targets/ran_build/build/nr-softmodem \
  -O "$CONF_DIR/gnb/gnb.sa.band78.106prb.rfsim.conf" \
  --rfsim \
  --rfsimulator.[0].serveraddr server \
  > "$LOG_DIR/gnb.txt" 2>&1 &
GNB_PID=$!

log_info "Checking gNB health alignment and NGAP connection to AMF..."
GNB_TIMEOUT=45
GNB_ELAPSED=0

while [ $GNB_ELAPSED -lt $GNB_TIMEOUT ]; do
    # Fixed with -aq to handle hidden ANSI formatting sequences smoothly
    if grep -aq "associated AMF" "$LOG_DIR/gnb.txt" && grep -aq "Frame.Slot" "$LOG_DIR/gnb.txt"; then
        log_info "gNB successfully initialized and registered with AMF!"
        break
    fi
    sleep 2
    GNB_ELAPSED=$((GNB_ELAPSED + 2))
done

if [ $GNB_ELAPSED -ge $GNB_TIMEOUT ]; then
    sudo kill -9 $GNB_PID || true
    log_err "gNB failed to establish an active link with AMF. Check $LOG_DIR/gnb.txt"
fi

# ==============================================================================
# STEP 3: START & VERIFY SYSTEM USER EQUIPMENT (nrUE)
# ==============================================================================

log_info "Launching nrUE in rfsimulator mode..."
sudo ./cmake_targets/ran_build/build/nr-uesoftmodem \
  --rfsim \
  --rfsimulator.[0].serveraddr 127.0.0.1 \
  -r 106 --numerology 1 --band 78 -C 3319680000 \
  -O ci-scripts/conf_files/nrue.uicc.conf \
  --uicc0.imsi 208990100001100 \
  > "$LOG_DIR/ue.txt" 2>&1 &
UE_PID=$!

log_info "Waiting for nrUE network registration and PDU Session Activation..."
UE_TIMEOUT=45
UE_ELAPSED=0
UE_IP=""

while [ $UE_ELAPSED -lt $UE_TIMEOUT ]; do
    # Fixed with -aq to force binary-safe text matching on logs
    if grep -aq "oaitun_ue1 successfully configured" "$LOG_DIR/ue.txt"; then
        # Dynamically extracts the IP assignment with binary-safe text streaming options
        UE_IP=$(grep -aoP "TUN Interface oaitun_ue1 successfully configured, IPv4 \K[0-9.]+" "$LOG_DIR/ue.txt" || true)
        if [ ! -z "$UE_IP" ]; then
            log_info "nrUE connected! Dynamic IP assigned: $UE_IP"
            break
        fi
    fi
    sleep 2
    UE_ELAPSED=$((UE_ELAPSED + 2))
done

if [ -z "$UE_IP" ]; then
    sudo kill -9 $GNB_PID || true
    sudo kill -9 $UE_PID || true
    log_err "nrUE failed to establish a PDU session. Check $LOG_DIR/ue.txt"
fi

# ==============================================================================
# STEP 4: TRAFFIC EXTRACTION & PERFORMANCE TESTS
# ==============================================================================

# Extract the correct Entrypoint / DN destination IP context
EXT_DN_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' oai-ext-dn)
log_info "Extracted Data Network (oai-ext-dn) Target Core IP: $EXT_DN_IP"

# Spin up iperf3 target inside the Data Network container containerizing your routing space
log_info "Initializing iperf3 host endpoint context inside oai-ext-dn..."
docker exec -d oai-ext-dn iperf3 -s

# Allow the routing fabric paths to stabilize
sleep 3

# --- Test A: Downstream Traffic Framework ---
log_info "Executing 10-Second Downstream (DL) Performance Benchmark..."
iperf3 -c "$EXT_DN_IP" -B "$UE_IP" -R -t 10 | tee "$LOG_DIR/bench_dl.log"

# Defensive delay loop: Allows the server socket to release its ephemeral bindings safely
log_info "Allowing socket resources to recycle..."
sleep 3

# --- Test B: Upstream Traffic Framework ---
log_info "Executing 10-Second Upstream (UL) Performance Benchmark..."
iperf3 -c "$EXT_DN_IP" -B "$UE_IP" -t 10 | tee "$LOG_DIR/bench_ul.log"

# Defensive delay loop: Guard against packet overlap before starting bidirectional load
log_info "Allowing socket resources to recycle..."
sleep 3

# --- Test C: Full-Duplex Bidirectional Framework ---
log_info "Executing 10-Second Bidirectional Concurrent Performance Benchmark..."
iperf3 -c "$EXT_DN_IP" -B "$UE_IP" --bidir -t 10 | tee "$LOG_DIR/bench_bidir.log"

# ==============================================================================
# CLEANUP & TEARDOWN PREPARATION
# ==============================================================================
log_info "Benchmarks completed successfully! Retaining background execution units."
log_info "To clean up execution stack, execute: sudo kill $GNB_PID $UE_PID"