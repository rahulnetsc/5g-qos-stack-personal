- [Step 1 — Install build dependencies](#step-1--install-build-dependencies)
- [Step 2 — Build gNB + nrUE with rfsimulator](#step-2--build-gnb--nrue-with-rfsimulator)
- [Step 3 — Build the T tracer tools](#step-3--build-the-t-tracer-tools)
- [Step 4 — Pull CN5G Docker images](#step-4--pull-cn5g-docker-images)
- [Step 5 — Locate the rfsimulator gNB config](#step-5--locate-the-rfsimulator-gnb-config)
- [Step 6 — Gate check](#step-6--gate-check)
- [Full Startup Sequence (fresh after reboot)](#full-startup-sequence-fresh-after-reboot)

# Step 1 — Install build dependencies

```
cd ~/projects/5g-qos-stack/openairinterface5g

# Installs all system packages OAI needs (run once, takes ~5 minutes)
cmake_targets/build_oai -I
```
# Step 2 — Build gNB + nrUE with rfsimulator

```
# --ninja: faster parallel build (vs default make)
# --gNB:   build nr-softmodem (the gNB binary)
# --nrUE:  build nr-uesoftmodem (the UE binary)
# -w SIMU: rfsimulator only — skips UHD/USRP/SDR drivers entirely
cmake_targets/build_oai --ninja --gNB --nrUE -w SIMU \
  --cmake-opt "-DENABLE_TTRACER=ON" \
  2>&1 | tee build_ttracer.log
```

Verify
```
ls -lh cmake_targets/ran_build/build/nr-softmodem \
       cmake_targets/ran_build/build/nr-uesoftmodem
# Both files should exist and be ~100-200MB

ss -tlnp | grep 2021
```

# Step 3 — Build the T tracer tools

```
cd ~/projects/5g-qos-stack/openairinterface5g/common/utils/T/tracer

# Install tracer dependencies (GTK3 for the GUI tools, not needed for csv)
sudo apt-get install -y libgtk-3-dev

make
```

Verify:
```
ls -lh tracer/csv tracer/gnb_mac
# csv is the one we need for metrics collection
# gnb_mac is the live GUI (useful for debugging later)
```

# Step 4 — Pull CN5G Docker images

```
cd ~/projects/5g-qos-stack/openairinterface5g/doc/tutorial_resources/oai-cn5g
docker compose pull
```

# Step 5 — Locate the rfsimulator gNB config

```
# Find the rfsimulator SA-mode configs
find ~/projects/5g-qos-stack/openairinterface5g/ci-scripts/conf_files \
     -name "*rfsim*" | sort

# Also check targets/ for SA configs
find ~/projects/5g-qos-stack/openairinterface5g/targets \
     -name "*sa*band78*" | sort
```

# Step 6 — Gate check

```
# CN5G images present
docker images | grep -E "oai-amf|oai-smf|oai-upf|oai-nrf|oai-udm|oai-udr|oai-ausf|mysql"

# Docker compose valid
cd ~/projects/5g-qos-stack/openairinterface5g/doc/tutorial_resources/oai-cn5g
docker compose config --quiet && echo "compose OK"

# T_messages.txt exists (needed by csv tool)
ls -lh ~/projects/5g-qos-stack/openairinterface5g/common/utils/T/T_messages.txt
```

**Create the IA-P5G config directory and patch the gNB config*

```
cd ~/projects/5g-qos-stack

# Create the benchmark config structure (from design doc repo layout)
mkdir -p oai-benchmark/config/gnb \
         oai-benchmark/config/ue \
         oai-benchmark/config/core \
         oai-benchmark/results

# Copy the reference gNB config — never modify originals
cp openairinterface5g/ci-scripts/conf_files/gnb.sa.band78.106prb.rfsim.conf \
   oai-benchmark/config/gnb/gnb.sa.band78.106prb.rfsim.conf

# Apply all three IP fixes
sed -i \
  -e 's/192\.168\.71\.132/192.168.70.132/g' \
  -e 's/192\.168\.71\.140/192.168.70.129/g' \
  oai-benchmark/config/gnb/gnb.sa.band78.106prb.rfsim.conf

# Verify the patch applied correctly
grep -n "ipv4\|IPV4\|serveraddr\|interface_name" \
  oai-benchmark/config/gnb/gnb.sa.band78.106prb.rfsim.conf
```

Expected output:
```
164:        amf_ip_address = ({ ipv4 = "192.168.70.132"; });
169:           GNB_IPV4_ADDRESS_FOR_NG_AMF              = "192.168.70.129";
170:           GNB_IPV4_ADDRESS_FOR_NGU                 = "192.168.70.129";
213:    serveraddr = "server";
```

Once that matches, the config is correct. Now open the four terminals in order.

The database has only PLMN 001.01 subscribers (001010000000001 through 001010000000004). IMSI 208990100001100 (PLMN 208.99) does not exist. We need to add it directly to the running MySQL container.
First, find the MySQL root password:
```
grep -E "MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD" \
  ~/projects/5g-qos-stack/openairinterface5g/doc/tutorial_resources/oai-cn5g/docker-compose.yaml \
  | head -5
```
Then insert the subscriber (replace <PASSWORD> with the value from above):
```
docker exec mysql mysql \
  -u root -p<PASSWORD> oai_db \
  -e "
INSERT INTO AuthenticationSubscription
  (ueid, authenticationMethod, encPermanentKey, protectionParameterId,
   sequenceNumber, authenticationManagementField, algorithmId,
   encOpcKey, encTopcKey, vectorGenerationInHss, n5gcAuthMethod,
   rgAuthenticationInd, supi)
VALUES
  ('208990100001100', '5G_AKA',
   'fec86ba6eb707ed08905757b1bb44b8f',
   'fec86ba6eb707ed08905757b1bb44b8f',
   '{\"sqn\": \"000000000020\", \"sqnScheme\": \"NON_TIME_BASED\", \"lastIndexes\": {\"ausf\": 0}}',
   '8000', 'milenage',
   'C42449363BBAD02B66D16BC975D77CC1',
   NULL, NULL, NULL, NULL,
   '208990100001100');

INSERT INTO SessionManagementSubscriptionData
  (ueid, servingPlmnid, singleNssai, dnnConfigurations)
VALUES
  ('208990100001100', '20899',
   '{\"sst\": 1, \"sd\": \"FFFFFF\"}',
   '{\"oai\":{\"pduSessionTypes\":{\"defaultSessionType\":\"IPV4\"},\"sscModes\":{\"defaultSscMode\":\"SSC_MODE_1\"},\"5gQosProfile\":{\"5qi\":9,\"arp\":{\"priorityLevel\":15,\"preemptCap\":\"NOT_PREEMPT\",\"preemptVuln\":\"PREEMPTABLE\"},\"priorityLevel\":1},\"sessionAmbr\":{\"uplink\":\"1000Mbps\",\"downlink\":\"1000Mbps\"}}}');
"
```
Verify the insertion worked:
```
docker exec mysql mysql \
  -u root -p<PASSWORD> oai_db \
  -e "SELECT ueid, authenticationMethod, algorithmId FROM AuthenticationSubscription WHERE ueid='208990100001100';"
```
Also add the subscriber to database/oai_db.sql so it survives a CN5G restart:
```
# Add to oai_db.sql so it persists across restarts
cat >> ~/projects/5g-qos-stack/openairinterface5g/doc/tutorial_resources/oai-cn5g/database/oai_db.sql << 'EOF'

-- IA-P5G subscriber: IMSI 208990100001100 (PLMN 208.99)
INSERT INTO `AuthenticationSubscription` (`ueid`, `authenticationMethod`, `encPermanentKey`, `protectionParameterId`, `sequenceNumber`, `authenticationManagementField`, `algorithmId`, `encOpcKey`, `encTopcKey`, `vectorGenerationInHss`, `n5gcAuthMethod`, `rgAuthenticationInd`, `supi`) VALUES
  ('208990100001100', '5G_AKA', 'fec86ba6eb707ed08905757b1bb44b8f', 'fec86ba6eb707ed08905757b1bb44b8f', '{"sqn": "000000000020", "sqnScheme": "NON_TIME_BASED", "lastIndexes": {"ausf": 0}}', '8000', 'milenage', 'C42449363BBAD02B66D16BC975D77CC1', NULL, NULL, NULL, NULL, '208990100001100');

INSERT INTO `SessionManagementSubscriptionData` (`ueid`, `servingPlmnid`, `singleNssai`, `dnnConfigurations`) VALUES
  ('208990100001100', '20899', '{"sst": 1, "sd": "FFFFFF"}', '{"oai":{"pduSessionTypes":{"defaultSessionType":"IPV4"},"sscModes":{"defaultSscMode":"SSC_MODE_1"},"5gQosProfile":{"5qi":9,"arp":{"priorityLevel":15,"preemptCap":"NOT_PREEMPT","preemptVuln":"PREEMPTABLE"},"priorityLevel":1},"sessionAmbr":{"uplink":"1000Mbps","downlink":"1000Mbps"}}}');
EOF
```

# Full Startup Sequence (fresh after reboot)


Open four terminals side by side.

**Terminal 1 — Start CN5G**

**(Do only once)  Fix the PLMN in config.yaml**
```
sed -i \
  -e 's/mcc: 001/mcc: 208/g' \
  -e 's/mnc: 01/mnc: 99/g' \
  conf/config.yaml

# Verify
grep -E "mcc|mnc|tac" conf/config.yaml
```
Expected output:
```
- mcc: 208
      mnc: 99
      tac: 0x0001
```

**Start CN5G**
```
cd ~/projects/5g-qos-stack/openairinterface5g/doc/tutorial_resources/oai-cn5g
docker compose up -d

# Wait ~30 seconds, then verify all healthy
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Health}}"
```

All containers must show healthy before going further. If any show unhealthy or starting, wait another 20 seconds and recheck.

**Terminal 2 — Start gNB**
```
cd ~/projects/5g-qos-stack/openairinterface5g

sudo cmake_targets/ran_build/build/nr-softmodem \
  -O ../oai-benchmark/config/gnb/gnb.sa.band78.106prb.rfsim.conf \
  --rfsim \
  --rfsimulator.[0].serveraddr server \
  2>&1 | tee ../gnb.log
```

```
sudo cmake_targets/build_oai --ninja --gNB --nrUE -w SIMU \
  --cmake-opt "-DENABLE_TTRACER=ON" \
  2>&1 | tee ../build_ttracer.log
```

**Terminal 3 — T tracer (start before UE):**
```
cd ~/projects/5g-qos-stack/openairinterface5g/common/utils/T/tracer

> /tmp/dl_lcid.csv && > /tmp/dl_sched.csv

./csv -d ../T_messages.txt -ip 127.0.0.1 -p 2021 -f -t ts \
    GNB_MAC_LCID_DL ts rnti frame slot lcid data_size tx_list_occupancy \
    >> /tmp/dl_lcid.csv &

./csv -d ../T_messages.txt -ip 127.0.0.1 -p 2021 -f -t ts \
    GNB_MAC_DL ts rnti frame slot mcs tbs \
    >> /tmp/dl_sched.csv &

echo "Tracers running: $(jobs -p)"
```

**Terminal 4 — UE:**
```
cd ~/projects/5g-qos-stack/openairinterface5g

sudo cmake_targets/ran_build/build/nr-uesoftmodem \
  --rfsim \
  --rfsimulator.[0].serveraddr 127.0.0.1 \
  --uicc0.imsi 208990100001100 \
  --uicc0.key fec86ba6eb707ed08905757b1bb44b8f \
  --uicc0.opc C42449363BBAD02B66D16BC975D77CC1 \
  -r 106 --numerology 1 --band 78 -C 3319680000 \
  2>&1 | tee /tmp/ue.log
```
