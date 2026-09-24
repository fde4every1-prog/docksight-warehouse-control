import csv
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[2]

def read(rel):
    with (ROOT/rel).open(encoding="utf-8") as f: return list(csv.DictReader(f))

def run():
    robots=read("data/raw/robots.csv"); aliases=read("data/raw/robot_aliases.csv"); inv=read("data/raw/inventory_snapshot.csv")
    tasks=read("data/raw/tasks.csv"); maint=read("data/raw/maintenance.csv"); tele=read("data/telemetry/robot_telemetry.csv")
    alias_counts=Counter(a['alias'] for a in aliases)
    collisions=sum(1 for _,n in alias_counts.items() if n>1)
    inv_conflicts=sum(1 for r in inv if len({r['wms_qty'],r['erp_qty'],r['vision_qty']})>1)
    task_conflicts=sum(1 for r in tasks if r['wes_status']!=r['fleet_status'])
    maint_conflicts=sum(1 for r in maint if r['cmms_status'] in {'OPEN','IN_PROGRESS'} and r['fleet_availability']=='AVAILABLE')
    unsafe_available=sum(1 for r in robots if r['safety_cert_status']=='EXPIRED' and r['connectivity']!='OFFLINE')
    seen=set(); dup=0
    for r in tele:
        k=(r['robot_id'],r['event_time'],r['zone'],r['battery_soc'],r['speed_mps'])
        if k in seen: dup+=1
        seen.add(k)
    return {'robots':len(robots),'alias_collisions':collisions,'inventory_truth_conflicts':inv_conflicts,
            'wes_fleet_task_conflicts':task_conflicts,'maintenance_availability_conflicts':maint_conflicts,
            'expired_safety_cert_but_connected':unsafe_available,'duplicate_telemetry_packets':dup}
