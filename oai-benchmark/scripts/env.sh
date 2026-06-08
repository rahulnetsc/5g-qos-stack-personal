# #!/usr/bin/env bash
# # ==============================================================================
# # 5G QoS Stack Validation Framework Environment Setup Configuration
# # Codifies network interfaces, execution timers, and network namespaces.
# # ==============================================================================

# # Network Topological IPs
# export UE_IP_ADDR="10.0.0.2"
# export EXT_DN_IP_ADDR="192.168.70.135"
# export UPF_N6_IP_ADDR="192.168.70.134"

# # Traffic Profiling Parameters
# export TRAFFIC_DURATION=60
# export IPERF_UL_PORT=5202
# export IPERF_DL_PORT=5201

# # Disaggregated Layer Interface Properties
# export F1_U_INTERFACE="lo"
# export N3_GTPU_INTERFACE="eth0"

#!/usr/bin/env bash
# =============================================================================
# env.sh — IA-P5G environment configuration
# Source this file from every other script: source "$(dirname "$0")/env.sh"
# =============================================================================

# --------------- Paths -------------------------------------------------------
export STACK_ROOT="${STACK_ROOT:-$HOME/projects/5g-qos-stack}"
export OAI_DIR="$STACK_ROOT/openairinterface5g"
export BENCH_DIR="$STACK_ROOT/oai-benchmark"
export CN5G_DIR="$OAI_DIR/doc/tutorial_resources/oai-cn5g"

export GNB_BIN="$OAI_DIR/cmake_targets/ran_build/build/nr-softmodem"
export UE_BIN="$OAI_DIR/cmake_targets/ran_build/build/nr-uesoftmodem"
export T_CSV="$OAI_DIR/common/utils/T/tracer/csv"
export T_MSGS="$OAI_DIR/common/utils/T/T_messages.txt"
export T_COLLECTOR="$BENCH_DIR/collect/t_tracer_collector.py"

export GNB_CONF="$BENCH_DIR/config/gnb/gnb.sa.band78.106prb.rfsim.conf"

# --------------- Radio parameters (must match gNB config) --------------------
export NR_ARFCN=3319680000
export NR_PRB=106
export NR_NUMEROLOGY=1
export NR_BAND=78
export NR_SSB=516

# --------------- CN5G network ------------------------------------------------
export DOCKER_NETWORK="demo-oai-public-net"
export CN5G_SUBNET="192.168.70.128/26"

# These are discovered at runtime by discover_network() and written here
export AMF_IP="192.168.70.132"
export SMF_IP="192.168.70.133"
export UPF_IP="192.168.70.134"
export EXT_DN_IP="192.168.70.135"
export HOST_BRIDGE_IP="192.168.70.129"   # host IP on Docker bridge (gNB bind address)

# --------------- Ports -------------------------------------------------------
export RFSIM_PORT=4043         # gNB rfsimulator server port
export T_TRACER_PORT=2021      # T tracer TCP port
export GTP_PORT=2152           # N3 GTP-U port
export NGAP_PORT=38412         # N2 SCTP port (AMF)

# --------------- Timing (seconds) -------------------------------------------
export CORE_WAIT_TIMEOUT=120   # max wait for all CN5G containers to be healthy
export GNB_N2_TIMEOUT=30      # max wait for gNB N2 setup complete
export UE_PDU_TIMEOUT=60      # max wait for UE PDU session established
export TRAFFIC_DURATION=10    # iperf3 test duration per run (seconds)
export WARMUP_DURATION=10     # discard first N seconds of metrics

# --------------- Results -----------------------------------------------------
export RESULTS_DIR="$BENCH_DIR/results"
export LOG_DIR="/tmp/ia-p5g-logs"

# --------------- Colours for terminal output ---------------------------------
export C_GREEN='\033[0;32m'
export C_RED='\033[0;31m'
export C_YELLOW='\033[1;33m'
export C_BLUE='\033[0;34m'
export C_BOLD='\033[1m'
export C_RESET='\033[0m'

