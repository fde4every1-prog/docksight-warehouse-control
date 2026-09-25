# Offline synthetic fleet readiness correction

This maintenance command repairs exactly 800 of the expected 891 current
robot/control-asset readiness issues. It writes approved readiness source
overlays; imported CSV files remain immutable. It does not clear safety holds,
resource blocks, simulator incidents, or alter battery/calibration data.

Stop the API before either command. The API lifetime lock and the command's
exclusive lock fail closed if they overlap.

```sh
python artifacts/api-server/fleet_offline_repair.py --dry-run \
  --fulfillment-db artifacts/api-server/.local/fulfillment.sqlite \
  --bazaar-db artifacts/api-server/.local/bazaar.sqlite

python artifacts/api-server/fleet_offline_repair.py --apply \
  --fulfillment-db artifacts/api-server/.local/fulfillment.sqlite \
  --bazaar-db artifacts/api-server/.local/bazaar.sqlite
```

Apply uses `sqlite3.Connection.backup` and verifies both database copies before
opening its single repair transaction. Backups and `report.json` are stored in
`.local/backups/<UTC timestamp>/`. Keep that directory private. Any count,
truth-projection, remaining-identity, operational-invariant, or injected
failure check rolls back the entire transaction. Dry-run performs the complete
selection and validation path and always rolls back.