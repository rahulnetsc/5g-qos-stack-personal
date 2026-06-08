#!/usr/bin/env python3
"""
Single-connection T tracer collector for IA-P5G.
Connects once to port 2021, activates all needed MAC events,
writes each event type to its own CSV file.

Run with --probe to discover what event IDs the compiled gNB actually emits
(useful when T_messages.txt may have drifted from the compiled binary).
"""
import socket, struct, sys, os, time, csv as csvmod, datetime, argparse

T_MSG_FILE = os.path.expanduser(
    "~/projects/5g-qos-stack/openairinterface5g/common/utils/T/T_messages.txt")

EVENTS_NEEDED = [
    "GNB_MAC_DL",
    "GNB_MAC_LCID_DL",
    "GNB_MAC_UL",
    "GNB_MAC_LCID_UL",
    "GNB_MAC_PUSCH_POWER_CONTROL",
]

# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser()
parser.add_argument("output_dir", nargs="?", default="/tmp")
parser.add_argument("--probe", action="store_true",
    help="Probe mode: activate ALL events for 10s and print which IDs fire. "
         "Use this to discover the real event IDs when T_messages.txt drifted "
         "from the compiled binary.")
args = parser.parse_args()
OUTPUT_DIR = args.output_dir
PROBE_MODE = args.probe

# ---------------------------------------------------------------------------

TYPE_MAP = {
    "int":      ("<i", 4),
    "uint64_t": ("<Q", 8),
    "uint32_t": ("<I", 4),
    "uint16_t": ("<H", 2),
    "uint8_t":  ("<B", 1),
    "unsigned": ("<I", 4),
    "short":    ("<h", 2),
    "char":     ("<b", 1),
    "float":    ("<f", 4)
}

def parse_event_ids(msg_file, event_names):
    events = {}
    cur_id = -1
    cur_name = None
    if not os.path.exists(os.path.expanduser(msg_file)):
        print(f"ERROR: T_messages.txt not found at: {msg_file}")
        sys.exit(1)
    with open(os.path.expanduser(msg_file)) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("ID ="):
                cur_id += 1
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

def parse_all_names(msg_file):
    """Return {id: name} for every event in T_messages.txt."""
    names = {}
    cur_id = -1
    with open(os.path.expanduser(msg_file)) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("ID ="):
                cur_id += 1
                names[cur_id] = stripped.split("=", 1)[1].strip()
    return names, cur_id + 1

# ---------------------------------------------------------------------------

if PROBE_MODE:
    print("=== PROBE MODE: discovering real event IDs from running gNB ===")
    print("Activating ALL events for 10 seconds. Events that fire will be printed.")
    print("Compare against EVENTS_NEEDED to see if IDs match T_messages.txt.\n")

    id_to_name, total_events = parse_all_names(T_MSG_FILE)
    is_on = [1] * total_events   # activate everything

    print(f"Connecting to 127.0.0.1:2021 (total_events={total_events})...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 2021))
    sock.sendall(struct.pack("b", 1))
    sock.sendall(struct.pack("<i", total_events))
    sock.sendall(struct.pack(f"<{total_events}i", *is_on))
    print("Connected. Listening for 10 seconds...\n")

    seen = {}   # id → count
    buf = b""
    sock.settimeout(10.0)
    try:
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            while len(buf) >= 8:
                msg_len = struct.unpack_from("<i", buf, 0)[0]
                if msg_len <= 0 or msg_len > 2_000_000:
                    buf = buf[1:]; continue
                if len(buf) < 4 + msg_len:
                    break
                event_id = struct.unpack_from("<i", buf, 4)[0]
                buf = buf[4 + msg_len:]
                seen[event_id] = seen.get(event_id, 0) + 1
    except Exception:
        pass
    finally:
        sock.close()

    print(f"Events seen in 10s ({len(seen)} distinct IDs):")
    for eid in sorted(seen.keys()):
        name = id_to_name.get(eid, "UNKNOWN")
        print(f"  ID {eid:4d}  count={seen[eid]:6d}  name={name}")

    print(f"\nTarget events in T_messages.txt:")
    _, te = parse_event_ids(T_MSG_FILE, EVENTS_NEEDED)
    for eid, ev in sorted(te.items()):
        match = eid in seen
        status = "✓ FOUND" if match else "✗ NOT SEEN"
        print(f"  ID {eid:4d}  {ev['name']}  {status}")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Normal collection mode
# ---------------------------------------------------------------------------

print("Parsing T_messages.txt...")
events, total_events = parse_event_ids(T_MSG_FILE, EVENTS_NEEDED)

if not events:
    print("ERROR: No target events found. Check EVENTS_NEEDED names vs T_messages.txt.")
    sys.exit(1)

print(f"Found {len(events)} target events (total event slots: {total_events})")
for eid, ev in sorted(events.items()):
    field_str = ", ".join(f"{t} {n}" for t, n in ev["fields"])
    print(f"  numeric ID {eid:3d}: {ev['name']}  [{field_str}]")

is_on = [0] * total_events
for eid in events:
    if eid < total_events:
        is_on[eid] = 1

files = {}
writers = {}
for ev in events.values():
    name = ev["name"].lower()
    path = os.path.join(OUTPUT_DIR, f"{name}_raw.csv")
    fh = open(path, "w", buffering=1, newline="")
    extra_fields = [fn for _, fn in ev["fields"]
                    if fn not in ("rnti", "frame", "slot")]
    header = ["timestamp", "rnti", "frame", "slot"] + extra_fields
    w = csvmod.writer(fh)
    w.writerow(header)
    files[ev["name"]] = fh
    writers[ev["name"]] = (w, extra_fields)
    print(f"  -> {path}  cols: {header}")

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
        while len(buf) >= 8:
            msg_len = struct.unpack_from("<i", buf, 0)[0]
            if msg_len <= 0 or msg_len > 2_000_000:
                buf = buf[1:]; continue
            if len(buf) < 4 + msg_len:
                break
            event_id = struct.unpack_from("<i", buf, 4)[0]
            payload  = buf[8 : 4 + msg_len]
            buf      = buf[4 + msg_len:]

            if event_id not in events:
                continue

            ev = events[event_id]
            w, extra_fields = writers[ev["name"]]
            ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

            vals = {}
            offset = 0
            error_parsing = False
            for ftype, fname in ev["fields"]:
                if ftype in TYPE_MAP:
                    fmt_str, size_bytes = TYPE_MAP[ftype]
                    if offset + size_bytes <= len(payload):
                        vals[fname] = struct.unpack_from(fmt_str, payload, offset)[0]
                        offset += size_bytes
                    else:
                        error_parsing = True; break
                else:
                    break

            if error_parsing:
                continue

            row = [ts, vals.get("rnti",""), vals.get("frame",""), vals.get("slot","")]
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
            lines = sum(1 for _ in open(path)) - 1
            print(f"  {path}: {lines} rows")
        except Exception:
            pass
