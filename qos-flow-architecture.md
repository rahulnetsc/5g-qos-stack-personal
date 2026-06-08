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

# End-to-End QoS Flows: Layer-by-Layer Walkthrough

**Refined Downlink (DL) QoS Flow Layer-by-Layer Path**

```
[Application / Internet Server]
                │
                │  Plain IP Packet (e.g., Destination Port: 5001)
                ▼
      ┌───────────────────┐
      │  UPF N6 Interface │ ──► Ingress plain IP packet arrival.
      └─────────┬─────────┘
                │
                ▼
      ┌───────────────────┐
      │   PDR Evaluation  │ ──► Evaluated against Packet Detection Rules (PDRs) 
      └─────────┬─────────┘     in strict increasing order of precedence.
                │               Matches IP Packet Filter Set (5-tuple).
                ▼
      ┌───────────────────┐
      │  QER Enforcement  │ ──► QoS Enforcement Rule (QER) assigns a specific 
      └─────────┬─────────┘     QoS Flow Identifier (QFI: 0..63).
                │               Applies maximum bitrate token-bucket policing.
                ▼
      ┌───────────────────┐
      │   FAR Execution   │ ──► Forwarding Action Rule (FAR) executes packet encapsulation.
      └─────────┬─────────┘     Wraps raw IP payload into N3 GTP-U headers.
                │               Stamps the QFI into the outer tunnel extension header.
                ▼ (Pushed over the N3 interface GTP-U tunnel to the gNB-CU)
                │
 ===============================▼=============================================================================
 gNB-CU LAYER (gNB Central Unit — Control Plane terminates NGAP, User Plane evaluates DRB Maps)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │ gNB-CU SDAP Layer │ ──► Receives the GTP-U packet from the N3 interface tunnel.
      └─────────┬─────────┘     Pulls the QFI directly from the extension header.
                │               References "DRBs to QoS Flows Mapping List" (TS 38.413 9.3.1.34).
                │               Maps the parsed QFI scalar item to a target DRB ID (1..32).
                │               Prepends a 5G SDAP Data Header containing the active QFI tag.
                ▼
      ┌───────────────────┐
      │ gNB-CU PDCP Layer │ ──► Terminates core network connectivity, maintains COUNT.
      └───────────────────┘     Applies ciphering and header compression (ROHC/EHC) functions.
                │
                ▼ (Transferred to the DU over the F1-U User Plane Interface)
                │
 ===============================▼=============================================================================
 gNB-DU LAYER (gNB Distributed Unit — Configured via F1AP Context, Controls Physical Scheduler)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │ gNB-DU RLC Layer  │ ──► Context initialized via F1AP "UE Context Setup Request" (TS 38.473 8.3.1).
      └─────────┬─────────┘     Sets up RLC Mode (AM/UM channel properties via TS 38.473 9.3.1.27).
                │               Maps incoming bearer directly to a target Logical Channel ID (LCID) queue.
                ▼
      ┌───────────────────┐
      │ gNB-DU MAC Layer  │ ──► Downlink Logical Channel buffer configurations become visible to the scheduler.
      └─────────┬─────────┘     • Stage 8 (ia_p5g_dl_lcid_alloc): Evaluates pending bytes per LCID,
                │                 extracting underlying target profiles from `lc_config[lcid].fiveQI`.
                │               • Stage 6 (ia_p5g_dl_rb_alloc): Custom Tier-2 scheduler hook hijacks loop,
                │                 referencing TS 23.501 default metrics to calculate optimal PRB slicing.
                ▼
      ┌───────────────────┐
      │ gNB-DU PHY Layer  │ ──► Compiles scheduling decisions into Downlink Control Information (DCI).
      └───────────────────┘     Modulates digital payload blocks directly onto target frequency slots.
                │
                ▼ (Transmitted over the airwaves via the physical Uu interface)
                │
 ===============================▼=============================================================================
 USER EQUIPMENT (UE) LAYER (Receives Waveforms, De-encapsulates Cell Stacks)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │ UE MAC/RLC/PDCP   │ ──► Phone lower layers decode raw radio parameters back into clear text.
      └─────────┬─────────┘     Handles HARQ feedback loops and link-layer reassembly.
                │
                ▼ (Intermediate user-plane data frame delivered up to device SDAP)
                │
      ┌───────────────────┐
      │   UE SDAP Layer   │ ──► Strips the Access Stratum SDAP data header wrapper.
      └─────────┬─────────┘     Parses the embedded QFI to confirm target routing properties.
                │
                ▼
      [ Client Application (iperf3) ] ──► Receives plain, unencapsulated IP packet payload.
```
Refined Uplink (UL) QoS Flow Layer-by-Layer Path

```
[Client Application on Phone]
                │
                │  Generates Outgoing IP Packet (e.g., Destination Port: 5001)
                ▼
 ===============================▼=============================================================================
 USER EQUIPMENT (UE) LAYER (Performs In-Device Classification and Radio Queue Enqueue)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │   UE NAS Layer    │ ──► Acts as an internal router, inspecting outbound IP packets.
      └─────────┬─────────┘     Evaluates traffic filters against explicitly signaled rules in precedence order.
                │               Matches the IP Packet Filter Set to map the packet to a unique QFI (0..63).
                ▼
      ┌───────────────────┐
      │   UE SDAP Layer   │ ──► Prepends an SDAP Data Header stamped with the assigned QFI.
      └─────────┬─────────┘     Uses internal RRC configuration rules to map that QFI to a target DRB ID.
                │               Chunnels the payload into the corresponding RLC / LCID buffer queue.
                ▼
      ┌───────────────────┐
      │   UE MAC Layer    │ ──► Tracks buffer occupancy across Logical Channel Groups (LCGs).
      └───────────────────┘     Fires a Buffer Status Report (BSR) to request uplink grant resources.
                                Enforces local maximum bitrates per PDU session using Session-AMBR.
                │
                ▼ (Grants received; transmits radio blocks on assigned PRBs over the Uu interface)
                │
 ===============================▼=============================================================================
 gNB-DU LAYER (Distributed Unit — Terminates Radio Waves, Enforces Session AMBR)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │ gNB-DU PHY/MAC/RLC│ ──► L1/L2 hardware components decode over-the-air grids back into digital SDUs.
      └───────────────────┘     Applies strict uplink traffic policing for non-GBR bearers using the stored 
                                UL PDU Session Aggregate Maximum Bit Rate constraints (TS 38.473 8.3.1.2).
                │
                ▼ (Intermediate payload context pushed over the F1-U User Plane Interface)
                │
 ===============================▼=============================================================================
 gNB-CU LAYER (Central Unit — Prepares private cellular network tunnel encapsulation)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │ gNB-CU PDCP Layer │ ──► Terminates radio link ciphering, integrity verification, and reordering.
      └─────────┬─────────┘
                │
                ▼
      ┌───────────────────┐
      │ gNB-CU SDAP Layer │ ──► Reads the explicit QFI tag directly from the over-the-air SDAP header.
      └─────────┬─────────┘     Strips the Access Stratum SDAP data header wrapper away.
                │
                ▼
      ┌───────────────────┐
      │ gNB-CU GTP-U Gen  │ ──► Encapsulates the clean IP payload into an Uplink GTP-U tunnel container.
      └───────────────────┘     Stuffs the parsed QFI value into the UL PDU Session Container extension.
                │
                ▼ (Pushed over the N3 tunnel interface directly to the Core Network gateway)
                │
 ===============================▼=============================================================================
 5GC CORE LAYER (Gateway Routing Engine — Validates QFI rules & enforces Core AMBR)
 =============================================================================================================
                │
                ▼
      ┌───────────────────┐
      │  UPF N3 / QER     │ ──► Terminates the incoming N3 tunnel interface, stripping the GTP-U layer.
      └─────────┬─────────┘     QER verifies the incoming QFI aligns with the rules from N4 session management.
                │               Enforces Session-AMBR and Uplink GBR/MBR token bucket constraints.
                ▼
      ┌───────────────────┐
      │  UPF N6 Interface │ ──► Clear, unencapsulated IP packet leaves the cellular network universe.
      └───────────────────┘     Pushed directly to the local data network or open internet.
```
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
- Layers Involved: MAC → RLC → PDCP → SDAP → IP → Application

- The Action: The phone reassembles the waves up through its own lower layers (PHY → MAC → RLC → PDCP). The phone's SDAP layer strips away the 5G cellular headers, reads the embedded QFI tag, strips it, and passes a clean, standard IP packet to your local device client Application (iperf3 client).

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

# Implementation Roadmap

- Implement probabilistic guarantees for QoS
- Implement BLER based data transfer limits for system capacity (1-BLER)*R
- Use multiple copies in the time freq grid to combat BLER
- Implement UL power control with mitigator
- Slicing
- Preemptive sending for urllc
  
# gNB Initial Setup and Core Connection Signaling Flow

```
[ gNB-DU ]                       [ gNB-CU ]                     [ 5G Core (AMF) ]
    │                                │                                 │
    │──(1) SCTP Association Establish│                                 │
    │      [Port 38472]              │                                 │
    │                                │                                 │
    │──(2) F1 SETUP REQUEST─────────►│                                 │
    │      [F1AP: Sec 8.5.1]         │                                 │
    │                                │──(3) SCTP Association Establish │
    │◄─(4) F1 SETUP RESPONSE─────────│      [Port 38412]               │
    │      [F1AP: Sec 8.5.1]         │                                 │
    │                                │──(5) NG SETUP REQUEST──────────►│
    │                                │      [NGAP: Sec 8.8.1]          │
    │                                │                                 │
    │                                │◄─(6) NG SETUP RESPONSE──────────│
    │                                │      [NGAP: Sec 8.8.1]          │
    ▼                                ▼                                 ▼
```

## Layer-by-Layer Walkthrough

### Step 1 & 2: The Internal RAN Split Integration (gNB-DU $\rightarrow$ gNB-CU)

- Layers Involved: gNB-DU F1AP $\rightarrow$ TNL (SCTP) $\rightarrow$ gNB-CU F1AP.
  
- The Interface/Port: F1-C Interface running over standard registered SCTP destination port 38472 (defined in TS 38.471).
  
- The Action: Upon powering on and acquiring local IP addresses, the gNB-DU initiates a stream control transmission protocol (SCTP) handshake with the gNB-CU. Once the socket state is established, the DU sends the F1 SETUP REQUEST (TS 38.473 Section 8.5.1).

- Key Information Elements (IEs) Transmitted:
  - gNB-DU ID and gNB-DU Name: Globally identifying this specific physical distributed unit hardware block.
  - Supported TAC (Tracking Area Code) & PLMN Identity: Mapping the geographical tracking grid of the radio hardware cells.
  - gNB-DU System Information: Contains the raw Master Information Block (MIB) and System Information Block Type 1 (SIB1) bytes that the DU plans to broadcast over the physical Uu interface for the cell.

### Step 3 & 4: RAN Capacity Acceptance (gNB-CU $\rightarrow$ gNB-DU)
- Layers Involved: gNB-CU F1AP $\rightarrow$ gNB-DU F1AP.
- The Action: The gNB-CU validates that the incoming DU's PLMN matches its own software configuration profiles. It responds down the F1-C tunnel with an F1 SETUP RESPONSE (TS 38.473 Section 8.5.1).
- Key Information Elements (IEs) Transmitted:
  - gNB-CU Name: Confirming central controller identity.
  - Cells to be Activated List: The CU explicitly instructs the DU which specific cell transmitters, physical cell identities (PCIs), and absolute radio-frequency channel numbers (ARFCNs) are cleared to go live and begin active radio transmission over the airwaves.
  
### Step 5: Bridging to the Core Cloud (gNB-CU $\rightarrow$ AMF)
- Layers Involved: gNB-CU NGAP $\rightarrow$ TNL (SCTP) $\rightarrow$ AMF NGAP.

- The Interface/Port: NG-C Interface running over standard registered SCTP destination port 38412 (defined in TS 38.411).

- The Action: Once the internal DU assets are bound and validated, the Central Unit initiates its external control-plane backbone link. It connects via an SCTP socket to the Access and Mobility Management Function (AMF) in the 5G Core network and submits the NG SETUP REQUEST (TS 38.413 Section 8.8.1).
  
- Key Information Elements (IEs) Transmitted:
  - Global gNB ID: Combines the PLMN ID and the gNB ID to uniquely represent this entire macro/micro station to the core global routing table.
  - Supported TA List: Explicitly tells the core network which precise Tracking Area Codes this base station manages.
  - Broadcast PLMN List $\rightarrow$ Slice Support List: Informs the AMF of the precise Network Slices (S-NSSAIs consisting of SST/SD values) supported across the radio interfaces.

### Step 6: Core Admittance & Global Mapping (AMF $\rightarrow$ gNB-CU)

- Layers Involved: AMF NGAP $\rightarrow$ gNB-CU NGAP.

- The Action: The Core network verifies that the incoming base station's identifiers are authorized within the operator network database. The AMF acts as the master sync element and locks the configuration by returning an NG SETUP RESPONSE (TS 38.413 Section 8.8.1).

- Key Information Elements (IEs) Transmitted:
  - AMF Name and AMF Region ID / AMF Set ID: Letting the CU know exactly which pool of core nodes is answering and handling load balanced control sessions.
  - Served GUAMI List (Globally Unique AMF Identifier): Explicitly provisions the globally distinct core identifiers the gNB must map individual UEs toward during initial attach requests.
  - Relative AMF Capacity: An integer factor (0..255) dictating weight allocation properties so that the gNB-CU knows how to distribute random incoming device registrations across redundant core nodes.

Once Step 6 finishes, the base station turns on its cellular radios, begins broadcasting its system configuration information (SIB1) to searching phones, and is fully ready to handle the uplink registration flows.

# Control plane signalling for new connections

## Uplink Connection & Registration Flow (UE $\rightarrow$ gNB-DU $\rightarrow$ gNB-CU $\rightarrow$ 5G Core)

This flow tracks the initial entry of the phone from raw airwaves up into the core network gateway to request admission.

```
[ UE ]                  [ gNB-DU ]               [ gNB-CU ]             [ 5G Core (AMF) ]
  │                         │                        │                         │
  │──(1) RRCSetupRequest───►│                        │                         │
  │   [Uu: SRB0 / CCCH]     │                        │                         │
  │                         │──(2) Initial UL RRC───►│                         │
  │                         │      Message Transfer  │                         │
  │                         │      [F1AP: Sec 8.6.1] │                         │
  │                         │                        │──(3) Initial UE────────►│
  │                         │                        │      Message (NAS)      │
  │                         │                        │      [NGAP: Sec 8.6.1]  │
  │──(4) RRCSetupComplete──►│                        │                         │
  │   [Uu: SRB1 / DCCH]     │──(5) UL RRC Message───►│                         │
  │   (Contains NAS             Transfer (NAS)       │                         │
  │    Registration Request)    [F1AP: Sec 8.6.2]    │──(6) Uplink NAS────────►│
  │                         │                        │      Transport (NAS)    │
  │                         │                        │      [NGAP: Sec 8.2.2]  │
  ▼                         ▼                        ▼                         ▼
```                                      

## Layer-by-Layer Walkthrough

### Step 1: The Airwave Trigger (UE $\rightarrow$ gNB-DU)

- Layers Involved: UE PHY/MAC/RLC $\rightarrow$ gNB-DU PHY/MAC/RLC (Control Plane: SRB0, CCCH Logical Channel).
- The Action: After completing the Random Access (RACH) preamble exchange, the UE transmits the RRCSetupRequest (TS 38.331). It passes its identity (5G-S-TMSI or random value) and establishment cause (e.g., mo-Signalling).

### Step 2: The F1-C Boundary Cross (gNB-DU $\rightarrow$ gNB-CU)

- Layers Involved: gNB-DU F1AP $\rightarrow$ gNB-CU F1AP (Control Plane: F1-C interface over SCTP).

- The Action: The gNB-DU allocates a unique identifier (gNB-DU UE F1AP ID). Because it does not process RRC messages directly, it wraps the raw RRC packet into an F1AP INITIAL UL RRC MESSAGE TRANSFER message (TS 38.473 Section 8.6.1) and pushes it up to the gNB-CU.
  
### Step 3: Core Network Admission Request (gNB-CU $\rightarrow$ AMF)

- Layers Involved: gNB-CU NGAP $\rightarrow$ AMF NGAP (Control Plane: NG-C interface over SCTP).
  
- The Action: The gNB-CU parses the RRC layer, allocates its own gNB-CU UE NGAP ID, and assigns an RRC connection. The gNB-CU then creates an NGAP INITIAL UE MESSAGE (TS 38.413 Section 8.6.1). It bundles the UE's location details (User Location Information) and routes this towards the AMF inside the 5G Core.
  
### Step 4 & 5: The NAS Payload Injection (UE $\rightarrow$ gNB-DU $\rightarrow$ gNB-CU)

- Layers Involved: UE RRC/NAS $\rightarrow$ DU RLC/MAC $\rightarrow$ CU RRC (Signaling Radio Bearer 1 - SRB1).
  
- The Action: The network assigns dedicated radio resources. The UE responds with an RRCSetupComplete message. Piggybacked directly inside this RRC layer is the NAS Registration Request (TS 24.501) containing the user’s subscription details. The gNB-DU receives this on SRB1, maps it to an F1AP UL RRC MESSAGE TRANSFER (TS 38.473 Section 8.6.2), and ships it to the CU.
  
### Step 6: Delivering the Intent to the Core (gNB-CU $\rightarrow$ AMF)

- Layers Involved: gNB-CU NGAP $\rightarrow$ AMF NAS Layer.
- The Action: The gNB-CU extracts the NAS payload from the RRC wrapper, embeds it into an NGAP UPLINK NAS TRANSPORT message (TS 38.413 Section 8.2.2), and passes it to the AMF. The 5G Core now begins authenticating the hardware.
  
## Core Command & Context Enforcement Flow (5G Core $\rightarrow$ gNB-CU $\rightarrow$ gNB-DU $\rightarrow$ UE)

Once the core validates who the user is, it commands the base station to spin up security encryption and build the dedicated radio infrastructure for the subscriber.

```
[ 5G Core (AMF) ]       [ gNB-CU ]               [ gNB-DU ]                  [ UE ]
        │                    │                        │                        │
        │──(1) Initial UE───►│                        │                        │
        │      Context Setup │                        │                        │ 
        │      Request       │                        │                        │
        │      [NGAP: 8.3.1] │──(2) UE Context Setup─►│                        │
        │                    │      Request           │                        │
        │                    │      [F1AP: Sec 8.3.1] │                        │
        │                    │                        │──(3) SecurityMode─────►│
        │                    │                        │      Command & RRC     │
        │                    │                        │      Reconfiguration   │
        │                    │                        │      [Uu: SRB1]        │
        │                    │                        │                        │
        │                    │                        │◄─(4) SecurityMode──────│
        │                    │◄─(5) UE Context Setup──│      Complete &        │
        │                    │      Response          │      ReconfigComplete  │
        │◄─(6) Initial UE────│      [F1AP: Sec 8.3.1] │                        │
        │      Context Setup │                        │                        │
        │      Response      │                        │                        │
        ▼                    ▼                        ▼                        ▼
```      

## Layer-by-Layer Walkthrough

### Step 1: The Core Command (AMF $\rightarrow$ gNB-CU)

- Layers Involved: AMF NGAP $\rightarrow$ gNB-CU NGAP.

- The Action: The AMF approves the registration and triggers the creation of the local session profile. It sends an NGAP INITIAL UE CONTEXT SETUP REQUEST (TS 38.413 Section 8.3.1). This critical message carries the UE's security capabilities, 5G security keys ($K_{gNB}$), Allowed NSSAI (Slicing info), and the NAS Registration Accept payload.

### Step 2: Partitioning the Context to the DU (gNB-CU ──► gNB-DU)
- Layers Involved: gNB-CU F1AP ──► gNB-DU F1AP.

- The Action: The gNB-CU evaluates core metrics and fires an F1AP UE CONTEXT SETUP REQUEST to the DU. This provisions local cell resources, SRB profiles, and maps incoming metrics to the local scheduler configuration (lc_config[lcid].fiveQI).

### Step 3: Activating Radio Security & Reconfiguration (gNB-CU ──► gNB-DU ──► UE)
- Layers Involved: gNB-CU RRC ──► F1AP DL RRC Transport ──► gNB-DU MAC/RLC ──► Uu Interface.
  
- The Action: 
   - The gNB-CU acts as the brain: It compiles a transparent RRC SecurityModeCommand byte block and drops it into an F1AP DL RRC MESSAGE TRANSFER container. The DU ingests this container, strips the F1AP wrapper, and schedules the raw RRC payload across SRB1.
   - Upon successful authentication, the gNB-CU compiles the subsequent RRCReconfiguration message (attaching the core's NAS Registration Accept), tunneling it to the DU via another DL RRC MESSAGE TRANSFER for physical transmission over the airwaves.

### Step 4: Device-Side Execution Complete (UE $\rightarrow$ gNB-DU)

- Layers Involved: UE RRC $\rightarrow$ gNB-DU MAC/RLC.
  
- The Action: The UE turns on its hardware encryption engines, configures its internal radio stack parameters, and fires back an encrypted SecurityModeComplete and RRCReconfigurationComplete verification block to the gNB-DU.
  
### Step 5: DU Loop Closure (gNB-DU $\rightarrow$ gNB-CU)

- Layers Involved: gNB-DU F1AP $\rightarrow$ gNB-CU F1AP.
  
- The Action: The DU registers that the phone has successfully updated its layer state. It responds to the CU with an F1AP UE CONTEXT SETUP RESPONSE (TS 38.473 Section 8.3.1), which includes local physical layer/cell allocation parameters and the uplink/downlink F1-U GTP-U transport addresses for data distribution.
  
### Step 6: Session Established Acknowledgement (gNB-CU $\rightarrow$ AMF)

- Layers Involved: gNB-CU NGAP $\rightarrow$ AMF NGAP.
  
- The Action: The gNB-CU maps the successful DU infrastructure initialization and issues the final NGAP INITIAL UE CONTEXT SETUP RESPONSE (TS 38.413 Section 8.3.1) back to the 5G Core.


