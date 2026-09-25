# Historical fulfillment replay

Run from `artifacts/api-server`:

```sh
python replay_runner.py
```

For a safe performance sample use `python replay_runner.py --limit 50`. The full
command validates the 7000 orders and 7000 matched shipment benchmarks before
selection. Results are written under `.local/replays/<UUID>/`: `simulation.sqlite`,
`manifest.json`, `live-snapshot.sqlite`, `effective-sources.json`, and `report.csv`.

The command opens the live fulfillment database read-only and uses SQLite backup.
It never changes live orders, configuration, corrections, or source files.
Archive timestamps have no offset and are explicitly interpreted as UTC. Original
strings remain in `input_json` and `benchmark_json`. Carrier cutoff is the simulated
on-time denominator; actual departure is the benchmark comparison. Shipment and
OMS/WMS statuses are observations only, never completion instructions.

The replay initializes opening inventory from immutable source inventory, then
uses captured effective robot, maintenance, and control-asset rows (scenario
overlays followed by durable persona corrections). Core policy-v2 intake,
strict selected-warehouse Bazaar stock gating, task allocation, resource claims,
fitness, lifecycle charging, stock movements, and configured task duration all
remain active. A bounded final drain leaves blocked work held/active rather than
fabricating completion.

Read-only endpoints are under `/api/fulfillment/replays`. They require the existing
`X-Demo-Persona` convention with `supervisor` or `admin`.

Sample manifests set `is_full_7000=false` and `sample_size`; they are never
presented as failed full runs. The replay invokes the existing planner admission
pass at each accelerated arrival, task-due, charging, and bounded-drain boundary.
The simulated on-time metric uses Core's order cutoff. The benchmark on-time
metric uses the archive's actual-versus-planned departure (the supplied 62.2%
baseline), so the UI must label the different deadline denominators explicitly.

The metrics are descriptive simulation-versus-benchmark comparisons. They do not
claim model training validity or infer all warehouse KPIs from the synthetic
historical record.