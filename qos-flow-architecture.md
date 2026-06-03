Here are the highly refined, 3GPP-standard-compliant details of both the Downlink and Uplink QoS Flow Data Paths, incorporating the technical architecture, constraints, and specific message Information Elements (IEs) from TS 23.501, TS 38.413, and TS 38.473.

# 1. The Refined Downlink (DL) QoS Flow Data Path
   
In the Downlink direction, network traffic transits from the external Application Server through the 5G Core ($5GC$) User Plane Function ($UPF$), bridges across the gNB Central Unit ($gNB-CU$) and Distributed Unit ($gNB-DU$) software partition, and maps directly onto the physical radio resource blocks ($PRBs$).

```
[Plain IP Packet from Application Server]
                    │
                    ▼
          [ UPF N6 Interface ]
                    │
                    │ (1) Ingress IP packet arrival. Evaluated against PDRs in increasing 
                    │     order of Precedence[cite: 149, 825]. Matches the IP Packet Filter Set 
                    │     (5-tuple: Src/Dst IP, Src/Dst Port, Protocol ID, ToS Mask)[cite: 423, 424, 425, 718].
                    ▼
       [ UPF QER & FAR Engine ]
                    │
                    │ (2) Service Data Flow (SDF) Match Found[cite: 93]. PDR match determines the QFI; QER enforces the rate for that QFI
                     (INTEGER 0..63) [cite: 107, 757, 1022] and applies 
                    │     Downlink MBR/MFBR token-bucket rate policing[cite: 134, 143, 751]. 
                    │     Forwarding Action Rule (FAR) executes Outer Header Creation[cite: 795, 796], 
                    │     encapsulating the payload into N3 GTP-U headers with the QFI stamped 
                    │     inside the PDU Session Container extension header[cite: 120, 795].
                    ▼
                    │ (Pushed over N3 GTP-U Tunnel to the Central Unit) [cite: 120, 130]
                    │
  ==================▼=============================================================================
  gNB-CU LAYER (Central Unit — Terminates NGAP, Evaluates DRB Maps)
  ================================================================================================
                    │
       [ gNB-CU SDAP Rx Processor ] 
                    │
                    │ (3) GTP-U packet arrives at the CU user plane endpoint[cite: 124]. SDAP pulls 
                    │     the QFI from the extension header [cite: 124] and references the 
                    │     "DRBs to QoS Flows Mapping List" (TS 38.413 Section 9.3.1.34) [cite: 1018] 
                    │     instantiated via NGAP during PDU Session Resource Setup[cite: 1007, 1018]. 
                    │     The QFI item maps to a target DRB ID (1..32)[cite: 1019, 1024]. SDAP 
                    │     prepends a 5G SDAP Data Header containing the active QFI tag.
                    ▼
                    │ (Transferred to DU over the F1-U User Plane Interface)
                    │
  ==================▼=============================================================================
  gNB-DU LAYER (Distributed Unit — Executes F1AP Context, Controls Physical Scheduler)
  ================================================================================================
                    │
        [ gNB-DU RLC Processor ] 
                    │
                    │ (4) SDU payload context maps to the DU via F1AP during "UE Context Setup 
                    │     Request" (TS 38.473 Section 8.3.1)[cite: 1033]. The DU honors the 
                    │     designated "DRB To Be Setup List" [cite: 1048] and configures the explicit 
                    │     RLC Mode (AM/UM via TS 38.473 Section 9.3.1.27)[cite: 1045]. The incoming 
                    │     bearer instance maps directly to a target Logical Channel ID (LCID) queue.
                    ▼
       [ MAC Scheduler Pipeline ]
                    │
                    │ (5) Downlink Logical Channel buffer data becomes visible to the scheduler.
                    │     • Stage 8 (ia_p5g_dl_lcid_alloc): Evaluates pending bytes per LCID queue, 
                    │       extracting target flow profiles from `lc_config[lcid].fiveQI`.
                    │     • Stage 6 (ia_p5g_dl_rb_alloc): The custom Stage 2 Tier-2 scheduler hook 
                    │       hijacks the allocation loop, using TS 23.501 Table 5.7.4-1 default metrics 
                    │       (Priority, PDB) to optimize physical PRB slicing per UE.
                    ▼
       [ Physical Airwaves (Uu) ] ──► Transmitted over the air as raw resource grid blocks.
                    │
                    ▼
       [ UE MAC / RLC / PDCP ]    ──► Phone Lower Layers decode radio frames back into clean SDUs.
                    │
                    ▼
            [ UE SDAP Layer ]     ──► Strips the Access Stratum SDAP data header, parsing the 
                                      embedded QFI to route the raw IP packet to the target client app.
```

# 2. The Refined Uplink (UL) QoS Flow Data Path
   
In the Uplink direction, the data flow originates directly from the client application inside the phone. The phone handles its own internal traffic classification, tags the stream with the proper Access Stratum cellular wrappers, and transits back through the disaggregated base station components to the core network gateway.

```
[Application on the Phone]
                    │
                    │ (1) Outgoing plain IP packet generated (e.g., Destination Port: 5001).
                    ▼
          [ UE NAS / SDAP Layer ]
                    │
                    │ (2) NAS evaluates the IP packet against explicitly signaled QoS rules in 
                    │     increasing order of precedence value[cite: 76, 113, 149]. Matches the IP Packet 
                    │     Filter Set (5-tuple) to bind the traffic to a unique QFI (0..63)[cite: 113, 117, 1022]. 
                    │     The UE SDAP Layer prepends an SDAP Data Header stamped with this QFI and 
                    │     uses RRC rules to map the flow onto an active DRB ID queue.
                    ▼ 
                    │ (UE MAC transmits a Buffer Status Report (BSR) to request an over-the-air grant. 
                    │  UE local rate limitation is enforced per session using Session-AMBR)[cite: 141, 1127].
                    │ (UE transmits via granted PRB time/frequency slots over the Uu interface)
                    ▼
  ================================================================================================
  gNB-DU LAYER (Distributed Unit — Decodes Over-The-Air Frames)
  ================================================================================================
                    │
        [ gNB-DU L1 / MAC / RLC ]
                    │
                    │ (3) DU lower layers decode raw radio frequency grids into a standard PDU block. 
                    │     The DU executes uplink traffic policing for non-GBR bearers using the stored 
                    │     UL PDU Session Aggregate Maximum Bit Rate constraints configured via F1AP 
                    │     during context instantiation (TS 38.473 Section 8.3.1.2)[cite: 1127].
                    ▼
                    │ (Intermediate SDU payload forwarded over the F1-U User Plane Interface)
                    │
  ================================================================================================
  gNB-CU LAYER (Central Unit — Prepares Outer Network Encapsulation)
  ================================================================================================
                    │
       [ gNB-CU PDCP Termination ]──► Terminates radio link ciphering, integrity, and packet reordering.
                    │
                    ▼
       [ gNB-CU SDAP Processing ] 
                    │
                    │ (4) CU SDAP reads the explicit QFI field embedded inside the incoming Access 
                    │     Stratum SDAP Data Header. The SDAP data header wrapper is stripped.
                    ▼
       [ gNB-CU GTP-U Generation ]
                    │
                    │ (5) CU encapsulates the plain IP payload into a standard Uplink GTP-U packet. 
                    │     It encodes the extracted QFI value into the UL PDU Session Container 
                    │     extension header (TS 38.413 Section 9.3.1.51)[cite: 1020].
                    ▼
                    │ (Pushed over N3 interface tunnel directly to the 5G Core Network) [cite: 130]
                    │
  ================================================================================================
  5GC CORE LAYER (Gateway Traffic Reception & Egress)
  ================================================================================================
                    │
          [ UPF N3 / QER Engine ]   
                    │
                    │ (6) UPF terminates the incoming N3 tunnel interface, stripping the outer GTP-U 
                    │     wrapping. The QER engine verifies that the incoming QFI is properly aligned 
                    │     with verified rules established via N4 session management[cite: 132, 709]. 
                    │     UPF enforces Session-AMBR and Uplink GBR/MBR token bucket constraints[cite: 134, 619].
                    ▼
          [ UPF N6 Interface ]      ──► Plain IP packet leaves the cellular universe and is exposed 
                                        directly to the local data network or open internet.
```

# 2. End-to-End QoS Flows: Layer-by-Layer Walkthrough
Let’s trace your active network pipeline once more, explicitly highlighting how every single step maps to the exact layers 

## **A. Downlink Path (From Internet down to the Phone)**

## Step 1: The External Gateway Interface
Layers Involved: Application → IP

The Action: The application server generates an raw data packet wrapped inside a standard network IP layer container (e.g., matching a port number like 5001).

## Step 2: Core Network Core Rules Execution (UPF)
- Layers Involved: Core network routers (The UPF)

- The Action: The UPF evaluates the incoming packet against its internal PDR (Packet Detection Rule) parameters. It matches the IP 5-tuple, passes it to a QER (QoS Enforcement Rule) to assign a target QFI, and wraps it into a GTP-U tunnel via a FAR (Forwarding Action Rule) to send over the wire to the base station.

## Step 3: RAN Boundary Translation (gNB Central Unit)
- Layers Involved: SDAP

- The Action: The packet arrives at the gNB−CU. The SDAP layer un-encapsulates the N3 tunnel, reads the QFI tag, and uses its configuration matrix to select an active target Data Radio Bearer (DRB). SDAP then prepends a 5G data header containing this QFI tag onto the packet.

## Step 4: Link Integrity and Queue Management (gNB Central & Distributed Units)
- Layers Involved: PDCP → RLC

- The Action: The PDCP layer applies ciphering protection and handles sequence number tracking. It then passes the frame down to the RLC layer. RLC translates the designated DRB profile directly into a specific software queue called a Logical Channel ID (LCID).  

## Step 5: Resource Slicing & Scheduling (gNB Distributed Unit)
- Layers Involved: MAC

- The Action: The MAC layer sublayer is where your custom project codebase is actively injected:

Your Stage 8 hook (ia_p5g_dl_lcid_alloc) inspects the RLC buffer depth queues, parsing their underlying fiveQI priority definitions.

Your Stage 6 hook (ia_p5g_dl_rb_alloc) hijacks the allocation loop to decide how many time and frequency blocks are needed for that priority level.

## Step 6: Over-The-Air Transmission
-Layers Involved: PHY (gNB) → PHY (UE)

- The Action: The physical PHY layer takes the scheduling blueprint from the MAC layer, modulates the digital bits onto high-frequency waves, and transmits them across the physical Uu air interface directly to the user equipment physical layer.

## Step 7: Device Reception
Layers Involved: MAC → RLC → PDCP → SDAP → IP → Application

## The Action: The phone reassembles the waves up through its own lower layers (PHY → MAC → RLC → PDCP). The phone's SDAP layer strips away the 5G cellular headers, reads the embedded QFI tag, strips it, and passes a clean, standard IP packet to your local device client Application (iperf3 client).

## B. Uplink Path (From the Phone back to the Core)

## Step 1: Device-Side Core Data Mapping
- Layers Involved: Application → IP → NAS

- The Action: Your phone's application layer generates an upload packet. The IP layer stamps it with addressing. The internal NAS controller layer matches it against its stored configuration profiles to declare exactly what QFI this upload path deserves.

## Step 2: Access Stratum Encapsulation
- Layers Involved: SDAP (UE) → PDCP → RLC → MAC

- The Action: The phone's SDAP sublayer stamps a header carrying the assigned QFI onto the packet and binds it to an active DRB. The lower layers (PDCP and RLC) move the data down to the MAC sublayer queue. The phone's MAC engine transmits a Buffer Status Report (BSR) across the physical PHY layer waves to tell the base station tower that it has data waiting to be pushed.

## Step 3: Base Station Split Ingestion
- Layers Involved: PHY → MAC → RLC (gNB-DU)

- The Action: The gNB−DU receives the raw blocks at its PHY layer, processes them through the MAC sublayer scheduling loops, and passes them to the RLC layer. Here, the DU applies local aggregate bitrate policing to ensure the uplink stream complies with the configuration profiles established via F1AP signaling.

## Step 4: Interface Delivery and Encapsulation
- Layers Involved: PDCP → SDAP (gNB-CU)

- The Action: The data is pushed over F1-U up to the Central Unit. The PDCP layer deciphers the radio stream, and passes it to the SDAP processing engine. The gNB-CU SDAP layer reads the QFI tag directly from the over-the-air protocol header, strips it away, and re-packages the plain IP payload into an Uplink GTP-U tunnel container. It copies the QFI into the standard N3 interface outer extension header to tunnel it back over IP to the 5G Core.

## Step 5: Core Network Verification and Egress
- Layers Involved: Gateway Processing (UPF)

- The Action: The UPF reads the incoming packet from the N3 tunnel interface, strips the outer encapsulation wrappers, and passes it to its core engines. It ensures the incoming QFI aligns safely with verified session parameters, enforces aggregate limits, and exposes a plain, unencapsulated IP packet directly to the IP data network via the N6 local interface.