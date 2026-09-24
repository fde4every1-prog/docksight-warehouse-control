# Lifecycle UI browser regression

The Fleet Simulator/Core Warehouse lifecycle journey has an isolated Playwright
regression. It starts `artifacts/api-server/lifecycle_ui_fixture.py` and dedicated
Vite servers for each desktop/mobile project; it never uses the operational API
or its databases. Browser API requests are forwarded fail-closed to the fixture
with their persona headers intact.

Run the saved validation from the workspace root:

```sh
pnpm test:lifecycle-ui
```

Use `CHROMIUM_PATH=/path/to/chromium` when Chromium is not available at the
Replit default `/repl/tools/bin/chromium`. A cheap discovery-only check is
`pnpm test:lifecycle-ui:list`.

# Warehouse Workspace

Runs the original uploaded synthetic warehouse Python API alongside a customer-fulfillment simulator and resource scenario editor. Original source data and legacy review views remain unchanged.

Fleet Simulator is a standalone ongoing-functions view, not an order-entry or resource dashboard. New confirmed simulator kills request Core-owned automatic replacement of the exact failed assignment (robot or control asset), restarting only that unfinished stage for 45 seconds. No candidate means waiting for the Core scheduler, not manual task approval. Failed resources remain blocked until explicit Core recovery; source CSV fitness is unchanged. Historical demo failures and ordinary incidents retain their existing manual approval/recovery policy. Normal unrelated assignments retain the 60-second cadence.

## Run & Operate

- The Warehouse Shared API workflow runs the authoritative Python/FastAPI gateway through the retained `@workspace/api-server` package identity, using its injected `PORT`.
- Preview `/` runs Core Warehouse (`artifacts/legacy-review: web`); the legacy overview remains at `/overview`. FDE Bazaar is a separate order-entry app at `/fde-bazaar/` (`artifacts/fde-bazaar: web`), and Robot Fleet Simulator remains at `/robot-lifecycle/`. Original docs remain at `/api/docs`; baseline endpoints are `/api/health`, `/api/diagnostics`, and `/api/robots/{robot_id}`.
- The retired Canvas artifact may remain visible as a registry stub because artifact unregister is unavailable. It has no package, source, workflow, or running service.
- `/api/review` endpoints expose original CSV records, source code, notes and a pure legacy allocator inspection with no side effects.
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-server run dev` (or `start`) — run the Python API gateway
- `pnpm --filter @workspace/api-server run check` — parse-check package-owned Python without importing it or touching operational data; `build` and `typecheck` retain workspace compatibility by delegating to this check
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- The baseline reads its bundled SQLite/CSV data; it does not require or use PostgreSQL.

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- Active API: Python 3.11 / FastAPI; original ZIP source under artifacts/api-server/brownfield.
- The dead Express server/build scaffold has been removed. The shared PostgreSQL/Drizzle libraries remain available to other workspace packages, but this Python API does not use them.
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- API validation/build: side-effect-free Python syntax checking (the interpreted service has no bundle step)

## Where things live

- `artifacts/api-server/baseline_demo.py` — hosting-only adapter.
- `artifacts/api-server/DEMO.md` — demo script and reproduction instructions.
- `artifacts/api-server/brownfield/` — unchanged uploaded source, contracts, tests and data.

## Architecture decisions

- Preserve baseline behavior and archive integrity. The user requested running the ZIP as the current version, not implementing the proposed capstone features or repairing intentional defects.
- The user subsequently requested a UI. The review frontend is explicitly new; original rules and data are not changed. Review annotations are not enforced legacy validations. Do not present the pure allocator inspector as mission execution.

## Product

The default frontend opens Order Fulfillment (`/fulfillment`) for the Supervisor persona; Fleet and Admin retain their own workspace landing pages. The original read-only overview is at `/overview`. New multi-line orders are entered in FDE Bazaar, not Control Tower. Order details and the full list remain accessible from the dashboard queue and View All; Inventory Explorer replaces redundant Supervisor resource navigation. Run Demo is not exposed through the UI or HTTP API, and the maintained Control Tower specification is kept in the Library rather than a Specs UI button. The original imported source remains unchanged.

Fulfillment uses all supplied warehouses, SKUs and resource catalogs, not a handpicked subset. New automatic-mapping orders use conservative minimum(WMS, ERP, vision) free stock. Acceptance debits each free quantity and credits reservations; successful Pick releases the reservation without another source debit. Inventory corrections require explicit evidence, not automatic selection of physical truth. The canonical PRD, architecture and ADR document is `artifacts/api-server/CONTROL_TOWER.md`.

Resources exposes every source column across all 19 datasets. Scenario edits are persistent overrides in the separate POC database, never changes to the imported files. Identity/reference fields and calculated fields remain read-only. Each dataset describes its real planning impact; editing reference-only data does not introduce new scheduling rules.

Scenario edits and restores require no planned, queued or running POC orders, so existing reservations and assignments cannot silently become invalid. Complete active orders or cancel unreleased plans first. Restoring resource values does not erase POC order history or reverse stock consumption from completed tasks.

Every assigned task uses a server-side 45-second simulated completion. New policy-v2 allocations use Pick, Move, Pack_feed and Stage with per-task SKU payloads and no unsafe manual bypass; policy-v1 historical orders retain pick/transfer/pack/dispatch behavior. Inventory `weight_kg` values are synthetic positive finite per-unit demo data, not measured physical weights. Missing or inconsistent weights are not replaced by a global fallback. Existing plans and completed work are not retroactively replanned. No AI model, fleet connection or physical actuation is enabled.

POC state is stored separately in `artifacts/api-server/.local/fulfillment.sqlite`. It survives local process restarts, but it is a shared unauthenticated workspace demo, not production multi-user storage or a certified control system. Do not change or migrate the supplied legacy SQLite snapshot. The API contract and assumptions are documented in `artifacts/api-server/FULFILLMENT_API.md`.

## Persona scope and intervention boundaries

- Persona workspaces are for Asset & Fleet Manager, Order Fulfilment Supervisor and Control Tower Admin. The access-model question was declined; this iteration uses an explicitly labelled demo role switcher, not secure authentication or production RBAC.
- Keep the Legacy Overview, Fleet, Inventory, Tasks, Evidence and Allocator pages unchanged and accessible as legacy inspection views. New persona navigation and interventions are separate from those pages.
- Fulfilment owns inventory mismatch, priority override and task-completion discrepancy resolution. Fleet owns resource-readiness conflicts and resource-failure investigation, handing operational recovery decisions to Fulfilment. Admin manages configuration/resource registration and inspects policies/audits, without operational approval authority.
- Original source files remain immutable. Physical verification in the POC is user-supplied evidence, not an actual sensor or site inspection. Resolving historical task discrepancies must never replay those tasks or consume simulated inventory.
- Explicit source-data exception: the user requested synthetic per-unit SKU weights in `inventory_snapshot.csv`. Its added `weight_kg` column uses random integer values from 1–1500, consistent across every row for the same SKU. Existing fields/rows are preserved. These are synthetic data, not measured weights. Each new/retried/recalculated plan records `payload_kg`, `total_expected_weight_kg`, `weight_source: inventory.weight_kg`, the not-measured `weight_label`, and per-line `weight_lines`; new plans do not include `unit_weight_kg_assumption`. The global `unit_weight_kg` config remains only for compatibility, is deprecated, and has no effect or fallback role.
- Recovery must preserve completed work and must not duplicate stock effects. All resource actions remain simulated; recorded safety evidence is not real-world safety certification.
- Persona API contracts and intervention evidence schemas are documented in `artifacts/api-server/PERSONA_API.md`, with the current policy in `artifacts/api-server/CONTROL_TOWER.md`. New corrections are source-specific and location-scoped, explicitly distinguish free quantities from total on-hand observations, and cannot directly overwrite reservations or picked quantities. Historical aggregate overlays remain compatibility inputs only.
- Supervisor inventory mismatches close with a required comment and atomically synchronize each affected location's app-owned WMS/ERP/Vision free quantities to that row's current maximum. Preserve reserved/picked quantities and allocation safety flags; do not claim external WMS/ERP writes or automatically recover orders. Do not show Report Inventory Mismatch or Report Task Conflict creation options in that workspace; other correction workflows are unchanged.

## FDE Bazaar and Control Tower integration

- FDE Bazaar owns customer order entry and receipt/history views. Control Tower owns operational planning and execution; Bazaar never starts warehouse tasks.
- Create Order shows service selection and SKU lines, without an Origin Warehouse selector or service-description panel. New drafts do not impose a warehouse; Control Tower selects independently per SKU. Saved historical requests retain their immutable bodies for safe replay.
- The separate frontend uses `/api/bazaar`, a separate intake component hosted on the shared Python gateway. Bazaar owns `artifacts/api-server/.local/bazaar.sqlite`, and sends actual HTTP requests to the Control Tower API rather than writing its database directly.
- Each order has a server-generated Bazaar ID, multiple SKU lines, and exactly one of `Next_Day`, `Same_Day`, or `Standard`. Receipt UI hides the heading FBZ ID, Control Tower ID, priority and idempotency key, while showing API delivery separately from per-SKU fulfillment progress.
- Intake saves an order and delivery record atomically before attempting the API handoff. Stable request IDs and persistent retry state protect against duplicate orders when a response is lost.
- New deadlines are original order creation +6 hours (Same_Day), +12 hours (Next_Day), or +24 hours (Standard), stored as UTC instants and unchanged by retries. Historical orders retain their saved deadlines. Their initial priorities are urgent, high and standard respectively. These are demo policies, not guaranteed delivery SLAs.
- API details are in `artifacts/api-server/BAZAAR_API.md`. Both SQLite databases are local shared-demo storage, and the existing persona switcher is still not production authentication.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- The shared Select component is a native-select wrapper, not the Radix compound API. Use `onChange` and native options; do not introduce `SelectTrigger`/`SelectContent` imports or replace the shared primitive, which would affect legacy pages.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
