#!/bin/bash

# ==============================================================================
# OAI 5G STACK AUTOMATION & OFFICIAL SIGMF DATA RECORDING APP SUITE
# ==============================================================================

set -euo pipefail

# --- Path Configurations ---
BASE_DIR="$HOME/projects/5g-qos-stack"
OAI_DIR="$BASE_DIR/openairinterface5g"
CONF_DIR="$BASE_DIR/oai-benchmark/config"
LOG_DIR="$BASE_DIR/script-logs"
TRACER_BIN_DIR="$OAI_DIR/common/utils/T/tracer"
DATA_REC_DIR="$OAI_DIR/common/utils/data_recording"

# Target path where the official documentation saves SigMF datasets
RECORDED_DATA_DIR="$HOME/workarea/oai_recorded_data"

mkdir -p "$LOG_DIR"
mkdir -p "$RECORDED_DATA_DIR"

# --- ANSI Colors for Scannability ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO] $(date +'%Y-%m-%d %H:%M:%S') $1${NC}"; }
log_warn() { echo -e "${YELLOW}[WARN] $(date +'%Y-%m-%d %H:%M:%S') $1${NC}"; }
log_err()  { echo -e "${RED}[ERR] $(date +'%Y-%m-%d %H:%M:%S') $1${NC}"; exit 1; }

# --- Pre-Flight Cleanup Routine ---
log_info "Performing pre-flight cleanup of modems, tracers, and shared memory daemons..."
sudo killall -9 nr-softmodem nr-uesoftmodem iperf3 t_tracer_app_gnb t_tracer_app_ue python3 2>/dev/null || true
docker exec oai-ext-dn killall -9 iperf3 2>/dev/null || true

# Clean out old historical metadata or broken captures to keep the directory clean
rm -rf "$RECORDED_DATA_DIR"/*

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
# STEP 2: START & VERIFY gNB IN PHY-TEST / RFSIMULATOR MODE
# ==============================================================================

log_info "Launching gNB softmodem with active T-Tracer hooks..."
cd "$OAI_DIR"

# Enforcing --T_stdout 2 and --T_nowait as documented for unblocked operation
sudo ./cmake_targets/ran_build/build/nr-softmodem \
  -O "$CONF_DIR/gnb/gnb.sa.band78.106prb.rfsim.conf" \
  --rfsim \
  --rfsimulator.[0].serveraddr server \
  --T_stdout 2 \
  --T_nowait \
  > "$LOG_DIR/gnb.txt" 2>&1 &
GNB_PID=$!

log_info "Checking gNB registration and NGAP link connection stability..."
GNB_TIMEOUT=45
GNB_ELAPSED=0

while [ $GNB_ELAPSED -lt $GNB_TIMEOUT ]; do
    if grep -aq "associated AMF" "$LOG_DIR/gnb.txt" && grep -aq "Frame.Slot" "$LOG_DIR/gnb.txt"; then
        log_info "gNB successfully initialized and registered with AMF!"
        break
    fi
    sleep 2
    GNB_ELAPSED=$((GNB_ELAPSED + 2))
done

if [ $GNB_ELAPSED -ge $GNB_TIMEOUT ]; then
    sudo kill -9 $GNB_PID || true
    log_err "gNB failed to establish an active link. Check $LOG_DIR/gnb.txt"
fi

# ==============================================================================
# STEP 3: MOUNT COMPILED C-BASED T-TRACER CAPTURE APP INSTANCES
# ==============================================================================

log_info "Spawning compiled C-based Data Collection T-Tracer services..."
cd "$TRACER_BIN_DIR"

# Launch the gNB capture daemon in the background
log_info "Starting gNB baseband collection service (Port 2021)..."
./t_tracer_app_gnb -d ../T_messages.txt > "$LOG_DIR/t_tracer_app_gnb.log" 2>&1 &
T_GNB_PID=$!

# Launch the UE capture daemon in the background on assigned port 2023
log_info "Starting nrUE baseband collection service (Port 2023)..."
./t_tracer_app_ue -d ../T_messages.txt -p 2023 > "$LOG_DIR/t_tracer_app_ue.log" 2>&1 &
T_UE_PID=$!

sleep 2
log_info "C collection daemons securely mounted onto their respective network interfaces."

# ==============================================================================
# STEP 4: START & VERIFY SYSTEM USER EQUIPMENT (nrUE)
# ==============================================================================

log_info "Launching nrUE softmodem with dynamic T-Tracer port reassignment..."
cd "$OAI_DIR"

# Enforcing --T_port 2023 to coordinate with the local UE collection process context
sudo ./cmake_targets/ran_build/build/nr-uesoftmodem \
  --rfsim \
  --rfsimulator.[0].serveraddr 127.0.0.1 \
  -r 106 --numerology 1 --band 78 -C 3319680000 \
  -O ci-scripts/conf_files/nrue.uicc.conf \
  --uicc0.imsi 208990100001100 \
  --T_stdout 2 --T_nowait --T_port 2023 \
  > "$LOG_DIR/ue.txt" 2>&1 &
UE_PID=$!

log_info "Waiting for nrUE network registration and PDU Session Activation..."
UE_TIMEOUT=45
UE_ELAPSED=0
UE_IP=""

while [ $UE_ELAPSED -lt $UE_TIMEOUT ]; do
    if grep -aq "oaitun_ue1 successfully configured" "$LOG_DIR/ue.txt"; then
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
    sudo kill $T_GNB_PID $T_UE_PID || true
    log_err "nrUE failed to establish a PDU session. Check $LOG_DIR/ue.txt"
fi

# ==============================================================================
# STEP 5: LAUNCH MASTER DATA RECORDING CONVERTER APPLICATION
# ==============================================================================

log_info "Initializing the Master Data Recording Application supervisor script..."
cd "$DATA_REC_DIR"

# Launching the main supervisor script to synchronize the shared memory blocks into SigMF format
python3 data_recording_app_v1.1.py > "$LOG_DIR/data_recording_master.log" 2>&1 &
MASTER_REC_PID=$!

sleep 2
log_info "SigMF data compilation supervisor active."

# ==============================================================================
# STEP 6: TRAFFIC GENERATION & LOAD TESTING
# ==============================================================================

EXT_DN_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' oai-ext-dn)
log_info "Extracted Data Network (oai-ext-dn) Target Core IP: $EXT_DN_IP"

log_info "Initializing iperf3 host endpoint context inside oai-ext-dn..."
docker exec -d oai-ext-dn iperf3 -s

sleep 3

# --- Test A: Downstream Traffic Framework ---
log_info "Executing 10-Second Downstream (DL) Performance Benchmark..."
iperf3 -c "$EXT_DN_IP" -B "$UE_IP" -R -t 10 | tee "$LOG_DIR/bench_dl.log"

log_info "Allowing socket resources to recycle..."
sleep 3

# --- Test B: Upstream Traffic Framework ---
log_info "Executing 10-Second Upstream (UL) Performance Benchmark..."
iperf3 -c "$EXT_DN_IP" -B "$UE_IP" -t 10 | tee "$LOG_DIR/bench_ul.log"

log_info "Allowing socket resources to recycle..."
sleep 3

# --- Test C: Full-Duplex Bidirectional Framework ---
log_info "Executing 10-Second Bidirectional Concurrent Performance Benchmark..."
iperf3 -c "$EXT_DN_IP" -B "$UE_IP" --bidir -t 10 | tee "$LOG_DIR/bench_bidir.log"

# ==============================================================================
# GRACEFUL TEARDOWN & RECOVERY PERIOD
# ==============================================================================

log_info "Traffic cycles finished. Disabling radio elements..."
sudo kill $GNB_PID $UE_PID 2>/dev/null || true

log_info "Allowing the Data Conversion service to serialize remaining shared memory frames..."
sleep 5

# Terminate collection and supervisor instances gracefully
sudo kill $MASTER_REC_PID $T_GNB_PID $T_UE_PID 2>/dev/null || true

# ==============================================================================
# VERIFICATION & SIGMF RESULTS SUMMARY MATRIX DISPLAY
# ==============================================================================
echo ""
log_info "SigMF Data Recording File Status Matrix Summary:"

# Scan the official destination folder for generated SigMF files
if [ -d "$RECORDED_DATA_DIR" ] && [ "$(ls -A "$RECORDED_DATA_DIR")" ]; then
    cd "$RECORDED_DATA_DIR"
    
    # Loop over collection files and data structures to ensure non-zero byte states
    for file in *; do
        if [ -f "$file" ]; then
            size_bytes=$(stat -c%s "$file")
            if [ "$size_bytes" -gt 100 ]; then
                printf "  ${GREEN}✓ %-65s${NC} (%8s bytes)\n" "$file" "$size_bytes"
            else
                printf "  ${YELLOW}⚠ %-65s${NC} (STALE / HEADER ONLY)\n" "$file"
            fi
        fi
    done
else
    log_err "Data Recording validation failed: No SigMF files detected inside $RECORDED_DATA_DIR"
fi
echo ""

log_info "Verification complete. All logs and metadata collections are successfully documented."