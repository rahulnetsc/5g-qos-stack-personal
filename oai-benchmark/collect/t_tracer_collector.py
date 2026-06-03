#!/usr/bin/env python3
"""
Single-connection T tracer collector for IA-P5G.
Connects once to port 2021, activates all needed MAC events,
writes each event type to its own CSV file.

T_messages.txt format:
  ID = SYMBOLIC_NAME          <- sequential position is the numeric event ID
      DESC = ...
      GROUP = ...
      FORMAT = type,name : type,name : ...
"""
import socket, struct, sys, os, time, csv as csvmod, datetime

T_MSG_FILE = os.path.expanduser(
    "~/projects/5g-qos-stack/openairinterface5g/common/utils/T/T_messages.txt")

EVENTS_NEEDED = [
    "GNB_MAC_DL",
    "GNB_MAC_LCID_DL",
    "GNB_MAC_UL",
    "GNB_MAC_LCID_UL",
    "GNB_MAC_PUSCH_POWER_CONTROL",
]

OUTPUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "/tmp"


def parse_event_ids(msg_file, event_names):
    """
    Parse T_messages.txt.
    Every 'ID = SYMBOLIC_NAME' line increments a counter.
    The counter value IS the numeric event ID (0-indexed sequential position).
    """
    events   = {}
    cur_id   = -1          # becomes 0 on first ID line
    cur_name = None        # symbolic name of current event
    with open(os.path.expanduser(msg_file)) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("ID ="):
                cur_id  += 1
                cur_name = stripped.split("=", 1)[1].strip()
                if cur_name in event_names:
                    events[cur_id] = {"name": cur_name, "fields": []}
            elif stripped.startswith("FORMAT =") and cur_name in event_names:
                fmt = stripped.split("=", 1)[1].strip()
                for field in fmt.split(":"):
                    field = field.strip()
                    if "," in field:
                        ftype, fname = field.split(",", 1)
                        events[cur_id]["fields"].append(
                            (ftype.strip(), fname.strip()))
    total_events = cur_id + 1
    return events, total_events


print("Parsing T_messages.txt...")
events, total_events = parse_event_ids(T_MSG_FILE, EVENTS_NEEDED)

if not events:
    print("ERROR: No target events found. Check EVENTS_NEEDED names vs T_messages.txt.")
    sys.exit(1)

print(f"Found {len(events)} target events (total event slots: {total_events})")
for eid, ev in sorted(events.items()):
    field_str = ", ".join(f"{t} {n}" for t, n in ev["fields"])
    print(f"  numeric ID {eid:3d}: {ev['name']}  [{field_str}]")

# Build activation mask: index = numeric event ID, value = 1 to activate
is_on = [0] * total_events
for eid in events:
    if eid < total_events:
        is_on[eid] = 1

# Open one CSV output file per event type
files   = {}
writers = {}
for ev in events.values():
    name = ev["name"].lower()
    path = os.path.join(OUTPUT_DIR, f"{name}_raw.csv")
    fh   = open(path, "w", buffering=1, newline="")
    extra_fields = [fn for _, fn in ev["fields"]
                    if fn not in ("rnti", "frame", "slot")]
    header = ["timestamp", "rnti", "frame", "slot"] + extra_fields
    w = csvmod.writer(fh)
    w.writerow(header)
    files[ev["name"]]   = fh
    writers[ev["name"]] = (w, extra_fields)
    print(f"  -> {path}  cols: {header}")

# Connect to T tracer (retry until gNB is up)
print(f"\nConnecting to 127.0.0.1:2021 ...")
while True:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.connect(("127.0.0.1", 2021))
        break
    except ConnectionRefusedError:
        print("  port 2021 not ready, retrying in 1 s ...")
        time.sleep(1)

# Handshake: send msg-type 1, then total count, then activation mask
print("Connected. Sending activation mask ...")
sock.sendall(struct.pack("b", 1))
sock.sendall(struct.pack("<i", total_events))
sock.sendall(struct.pack(f"<{total_events}i", *is_on))
print("Collecting. Press Ctrl+C to stop.\n")

events_seen = 0
buf = b""
try:
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            print("gNB closed the connection.")
            break
        buf += chunk

        # Wire format: [int32 msg_len][int32 event_id][payload bytes...]
        # msg_len includes event_id (4 bytes) but NOT itself (4 bytes).
        while len(buf) >= 8:
            msg_len  = struct.unpack_from("<i", buf, 0)[0]
            if msg_len <= 0 or msg_len > 2_000_000:
                buf = buf[1:]          # framing error — resync one byte at a time
                continue
            if len(buf) < 4 + msg_len:
                break                  # incomplete — wait for more data
            event_id = struct.unpack_from("<i", buf, 4)[0]
            payload  = buf[8 : 4 + msg_len]
            buf      = buf[4 + msg_len :]

            if event_id not in events:
                continue

            ev = events[event_id]
            w, extra_fields = writers[ev["name"]]
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # Parse fields: only 'int' type fields are fixed-width (4 bytes)
            vals   = {}
            offset = 0
            for ftype, fname in ev["fields"]:
                if ftype == "int" and offset + 4 <= len(payload):
                    vals[fname] = struct.unpack_from("<i", payload, offset)[0]
                    offset += 4
                else:
                    break   # stop at non-int (e.g. buffer) or short payload

            row = [ts,
                   vals.get("rnti",  ""),
                   vals.get("frame", ""),
                   vals.get("slot",  "")]
            for fname in extra_fields:
                row.append(vals.get(fname, ""))
            w.writerow(row)

            events_seen += 1
            if events_seen % 1000 == 0:
                print(f"  {events_seen} events captured ...")

except KeyboardInterrupt:
    pass
finally:
    sock.close()
    for fh in files.values():
        fh.close()
    print(f"\nDone. Total events captured: {events_seen}")
    for ev in events.values():
        name = ev["name"].lower()
        path = os.path.join(OUTPUT_DIR, f"{name}_raw.csv")
        try:
            lines = sum(1 for _ in open(path)) - 1   # minus header
            print(f"  {path}: {lines} rows")
        except Exception:
            pass
