# P01-v1-CURRENT_ARCHITECTURE

**Prompt:** 01 — Warehouse Brownfield Forensics  
**Artifact:** Current-state architecture diagram (expanded from `docs/03_current_state_architecture.md`)  
**Baseline frozen:** 2.0.0 — `docs/03` was not edited  
**Rule:** Diagrams show only systems evidenced in this repo. Missing WRCC components are labeled absent, not invented.

Source sketch (unchanged):

```text
ERP → OMS → WMS → WES → Fleet Managers / WCS → Robots / PLCs / Conveyors / ASRS
                         ↘ Vision / Safety / IoT
CMMS ↔ Fleet                  ↓
Labor Mgmt                 Physical warehouse
TMS ← staging/ship confirmation

Shadow layer: CSV/Excel-like exports + emails + radio/manual overrides
```

`docs/03`: **No component has complete warehouse truth.**

---

## 1. Documented as-is flow (same boxes as docs/03)

Happy-path order movement plus side systems. Solid arrows = documented digital flow. Dashed = shadow / unofficial.

```mermaid
flowchart TB
  subgraph enterprise["Enterprise"]
    ERP[ERP books / erp_qty]
    OMS[OMS order + carrier_cutoff]
  end

  subgraph warehouse_sw["Warehouse software"]
    WMS[WMS bins / wms_qty / wms_status]
    WES[WES tasks / wes_status]
  end

  subgraph control["Execution and machines"]
    FLEET[Fleet managers]
    WCS[WCS / PLC]
    ROBOTS[Robots AMR/AGV]
    ASSETS[Conveyors / ASRS / sorters / chargers / docks]
  end

  subgraph sensing["Sensing and safety"]
    VISION[Vision / cameras]
    SAFETY[Safety events / certs]
    IOT[Telemetry / IoT]
  end

  subgraph people["People and maintenance"]
    CMMS[CMMS work orders]
    LABOR[Labor mgmt]
  end

  subgraph ship["Outbound"]
    PHYS[Physical warehouse]
    TMS[TMS shipment / carrier]
  end

  SHADOW[Shadow: emails / Excel / radio]

  ERP --> OMS --> WMS --> WES --> FLEET --> ROBOTS --> PHYS
  WES --> WCS --> ASSETS --> PHYS
  WES --> VISION
  WES --> SAFETY
  IOT --> FLEET
  CMMS <--> FLEET
  LABOR --> PHYS
  PHYS --> TMS
  SHADOW -.-> OMS
  SHADOW -.-> WMS
  SHADOW -.-> FLEET
  VISION -.-> WMS
```

---

## 2. How this repo actually implements it (thin control plane)

There is **no live WarehouseState**, no DecisionEngine, and **no write path to robots**. State is snapshots.

```mermaid
flowchart TB
  subgraph data["data/ snapshots — competing records"]
    ORD[orders.csv\noms_status vs wms_status]
    INV[inventory_snapshot.csv\nwms_qty vs erp_qty vs vision_qty]
    TSK[tasks.csv\nwes_status vs fleet_status]
    RBT[robots.csv + robot_aliases.csv]
    MNT[maintenance.csv vs fleet AVAILABLE]
    ZN[zones.csv RESTRICTED / map_version]
    CHG[charging_state.csv preferred_charger]
    TEL[robot_telemetry.csv event_time vs ingest_time]
    EVT[events.jsonl event_time vs recorded_time]
    SHP[shipments.csv TMS]
    SAF[safety_events.csv]
    LAB[labor_capacity.csv]
    SHD[shadow/ops_emails.txt\nwave_priority_FINAL_v7.csv]
  end

  subgraph baseline["Baseline v2.0.0 — observe only"]
    DIAG[diagnostics.py counters]
    LEGA[legacy allocator\nbattery + ONLINE]
    LEGI[legacy inventory\ntrusts WMS]
    API["FastAPI GET /health /diagnostics /robots\nphysical_control: disabled"]
    DB[(warehouse_legacy.db)]
  end

  subgraph contracts["Contracts — not wired to API"]
    F1[fleet_api_v1.yaml\nno idempotency key]
    F2[fleet_api_v2.yaml\nvehicle_id]
  end

  subgraph absent["Not in this repo"]
    X1[DecisionEngine / Approval / ActionExecutor]
    X2[Copilot / RAG]
    X3[Keep-out polygons / tote model]
    X4[Digital twin runtime]
    X5[specs/ WRCC contract]
  end

  ORD --> DIAG
  INV --> DIAG
  TSK --> DIAG
  RBT --> DIAG
  MNT --> DIAG
  TEL --> DIAG
  INV --> LEGI
  RBT --> LEGA
  DB --> API
  DIAG --> API
  F1 -.->|not implemented| API
  F2 -.->|not implemented| API
```

Runnable surfaces: `python -m warehouse_control.cli diagnostics` and GET-only API. Fleet POST contracts exist as YAML only.

---

## 3. Competing systems of record (why no box is “the truth”)

```mermaid
flowchart LR
  subgraph identity["Robot identity"]
    A1[WMS alias]
    A2[Fleet alias / fleet_id]
    A3[CMMS alias]
    A1 --- A2 --- A3
  end

  subgraph qty["Inventory qty"]
    B1[WMS]
    B2[ERP]
    B3[Vision]
    B4[Operator / email]
    B1 --- B2 --- B3 --- B4
  end

  subgraph task["Task / order status"]
    C1[OMS]
    C2[WMS]
    C3[WES]
    C4[Fleet]
    C1 --- C2 --- C3 --- C4
  end

  subgraph avail["Availability"]
    D1[Fleet AVAILABLE]
    D2[CMMS OPEN]
    D3[Safety cert EXPIRED]
    D1 --- D2 --- D3
  end

  subgraph time["Time / cutoff"]
    E1[OMS SLA table]
    E2[Shadow email cutoff]
    E3[event_time]
    E4[recorded_time / ingest_time]
    E1 --- E2
    E3 --- E4
  end
```

Evidence already counted on baseline 2.0.0: 6 alias collisions, 7,382 inventory fights, 7,351 WES≠fleet, 176 CMMS vs AVAILABLE, 35 expired-cert still connected.

---

## 4. Authority boundary (current)

```mermaid
flowchart LR
  OBS[Observe: diagnostics / GET API] --> REC[Recommend: not implemented]
  REC --> HUM[Human: email / supervisor / safety docs]
  HUM --> X[Execute robot / WMS write]
  X -.->|blocked| STOP[physical_control disabled]
```

`docs/06` and `/health`: safety PLC, e-stop, speed-limit changes stay human. The LLM/copilot is **absent**, so it cannot currently sit on the write path — and must not be added onto `/diagnostics` as a substitute for this architecture.

---

## 5. How to use this with docs/03

| Artifact | Role |
|----------|------|
| `docs/03_current_state_architecture.md` | Frozen baseline sketch |
| This file | Evidence-backed expansion for P01 |
| `P01-v1-CURRENT_STATE.md` | File-level inventory |
| `P01-v1-SDD_GAP_ANALYSIS.md` | WRCC PASS/PARTIAL/FAIL tags |
