# V2 Verification Evidence

Verification was executed from the repository root using the packaged source tree.

## Release checks
- Repository structural verifier: **VERIFY_OK**
- Python compile/import smoke check: **PASS**
- API module import: **PASS** (`warehouse_control.api:app`)
- SQLite `PRAGMA integrity_check`: **PASS** (performed by `scripts/verify_repo.py`)
- JSON parse and CSV rectangularity checks: **PASS**
- Restricted-role/reference scan: **PASS — zero matches**
- External consequential-control integration: **disabled / not configured**

## Test result
```text
...xxx                                                                   [100%]
=========================== short test summary info ============================
XFAIL tests/test_known_legacy_defects.py::test_allocator_rejects_expired_safety_cert - legacy allocator ignores expired safety certification
XFAIL tests/test_known_legacy_defects.py::test_allocator_respects_payload - legacy allocator has no payload constraint
XFAIL tests/test_known_legacy_defects.py::test_allocator_avoids_congested_zone - legacy allocator is local heuristic, not congestion aware
3 passed, 3 xfailed in 0.28s
```
Expected-failure tests document deliberately preserved legacy limitations; they are not accidental release failures.

## Diagnostic evidence
- `robots`: **712**
- `alias_collisions`: **6**
- `inventory_truth_conflicts`: **7382**
- `wes_fleet_task_conflicts`: **7351**
- `maintenance_availability_conflicts`: **176**
- `expired_safety_cert_but_connected`: **35**
- `duplicate_telemetry_packets`: **80**

## File authentication
`checksums.sha256` contains SHA-256 hashes for the release files. These hashes provide reproducible integrity evidence; this release is not digitally signed and does not claim regulatory certification.
