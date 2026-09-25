# Current-state architecture

```text
ERP → OMS → WMS → WES → Fleet Managers / WCS → Robots / PLCs / Conveyors / ASRS
                         ↘ Vision / Safety / IoT
CMMS ↔ Fleet                  ↓
Labor Mgmt                 Physical warehouse
TMS ← staging/ship confirmation

Shadow layer: CSV/Excel-like exports + emails + radio/manual overrides
```

No component has complete warehouse truth.
