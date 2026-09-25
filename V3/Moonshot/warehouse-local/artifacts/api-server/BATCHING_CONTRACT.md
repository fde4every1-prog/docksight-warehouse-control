# Detached batching contract

All Python functions are pure, JSON-compatible and use seconds relative to the
scenario's fixed `clock_start`. No operational modules or databases are imported.

Public imports:
- `from batching_scenario import scenario` → fresh scenario dict.
- `from batching_engine import validate_plan, simulate, enumerate_candidates, compare`
- `validate_plan(scenario, proposal)` → `{"valid":bool,"errors":[str],"batches":[Batch]}`.
  Proposal is `{"scenario_id":str,"batches":[Batch]}`. Batch is
  `{"id":str,"order_ids":[str,...],"reason":str (optional)}`. Only groups of 2–3.
  Ungrouped orders run individually. Invalid inputs are never silently repaired.
- `simulate(scenario, batches)` → Run; raises `ValueError` for invalid plans.
  `batches=[]` is the isolated current-process baseline adapter.
- `enumerate_candidates(scenario)` →
  `{"candidates":[Batch],"exclusions":[{"order_ids":[str],"reason":str}]}`.
  Each candidate is independently feasible with all other orders singleton.
  Combined selections MUST be revalidated (overlap and downstream contention).
- `compare(scenario,batches)` →
  `{"scenario_id":str,"baseline":Run,"batched":Run,"savings":{"service_seconds":number,"makespan_seconds":number}}`.

Scenario:
```
{
 scenario_id, warehouse_id:"DC-01", seed:60, clock_start,
 source:"detached_synthetic", assumptions:[string],
 map:{width:number,height:number,boundary:[{x,y}],zones:[{id,label,x,y,width,height}],
      nodes:[{id,x,y,zone}],edges:[{from,to}],bins:[{id,node_id,zone,sku,stock}],
      destinations:{pick:string,transfer:string,pack_feed:string,stage:string}},
 skus:[{id,unit_weight_kg}],
 orders:[{id,sub_order_id,tote_id,status:"queued",cutoff_seconds,
          lines:[{id,sku,quantity,bin_id}]}],
 robots:[{id,warehouse_id,type,start_node,available,battery_percent,capacity_kg,capabilities:[string],blocked_reason}],
 assets:[{id,warehouse_id,stage,node_id,available}],
 constraints:{base_duration_seconds:45,max_batch_size:3,max_proximity:180}
}
```

Run:
```
{
 mode:"baseline"|"batched", scenario_id,
 timeline:[{id,stage:"pick"|"move"|"pack_feed"|"stage",batch_id:string|null,
   order_ids:[string],line_ids:[string],tote_ids:[string],resource_id,resource_type:"robot"|"asset",
   start:number,end:number,duration:number,payload_kg:number,
   path:[{node_id,x,y,at:number}]}],
 orders:[{id,completed_at:number,cutoff_seconds:number,on_time:boolean}],
 metrics:{completed_orders,completed_tasks,logical_tasks,service_seconds,makespan_seconds,
   deadline_misses,robot_utilization:[{robot_id,busy_seconds,utilization:number}]},
 inventory:[{bin_id,sku,opening,reserved,remaining}]
}
```
Utilization is a fraction 0–1. `completed_tasks` counts actual operations;
`logical_tasks` counts order-stage equivalents. Path points are absolute replay
seconds, assigned across graph edges inside service time, NOT added travel time.

Baseline source: `fulfillment_v2.py` `executor_once`, `_choose`,
`robot_eligibility`, `asset_eligibility`, `STAGES`. Ready queued work is sorted
by cutoff, sub-order ID, stage rank, task ID; compatible robots are selected by
smallest sufficient payload then ID; assets by ID. Stages unlock on completion.
Robots/assets are exclusive, with concurrent operations when resources permit.
First-draft simplifications: one synthetic line/sub-order/pick per order, fixed
readiness and battery (admission strictly above 10%), no failures/recovery,
charging, dynamic arrivals, planner cadence or labor pool. Pack/stage each have
one exclusive asset; their contention is the shared downstream bottleneck.
All payloads are explicit synthetic assumptions, not measured fleet data.
Batching applies T(n)=45+22.5(n−1) separately to pick and move, never downstream.
All orders' full downstream deadlines are checked before accepting a grouped
recommendation. The urgent singleton remains feasible; the heavy singleton
cannot share payload with another order. This sandbox intentionally owns an
independent replay clock, not a second live simulation clock.