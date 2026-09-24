"""Shared read-only monthly comparison, independent of execution databases."""
from fastapi import APIRouter, Header, HTTPException

from monthly_kpi_metrics import aggregate, changes, timestamp
from monthly_kpi_sources import bundle, VERSION

router = APIRouter(prefix="/api/monthly-kpis", tags=["monthly-kpis"])
AS_OF = "2026-09-22T23:59:59+00:00"


def source_coverage(source, warehouse="", month=None, as_of=AS_OF):
    cutoff = timestamp(as_of)
    coverage = {}
    for name, fields in (("orders", ("created_at",)), ("shipments", ("planned_departure", "actual_departure")),
                         ("tasks", ("created_at",))):
        dates = sorted(t for row in source[name] if not warehouse or row["warehouse_id"] == warehouse
                       for field in fields if (t := timestamp(row.get(field))) is not None
                       and t <= cutoff and (month is None or t.strftime("%Y-%m") == month))
        coverage[name] = (dates[0].date().isoformat(), dates[-1].date().isoformat()) if dates else None
    return coverage
DEFINITIONS = [
    ("cycle_time", "Order cycle time", "hours", "lower",
     "Sum(actual carrier departure − matched order creation), in hours / valid matched pairs",
     ["Cohort: order creation month. Only unambiguous one-to-one order/shipment matches in the same warehouse; nonnegative durations.",
      "Missing or invalid departures and conflicting joins are excluded. This is carrier departure, not staging completion.",
       "September samples August's valid pairs and scales each duration by 7.38 hours divided by the unrounded all-warehouse August mean. This targets a 7.38-hour all-warehouse mean while preserving warehouse variation; new arrivals are distributed across September. Sample size is not a volume forecast."]),
    ("on_time_departure", "On-time carrier departure", "%", "higher",
     "100 × departures at or before planned departure / shipments with actual departure timestamps",
     ["Cohort: planned departure month, falling back to actual departure month when planned is missing.",
      "Missing planned timestamps stay in the requested actual-departure denominator but are unknown, not classified late. Missing actual timestamps are excluded.",
      "September assumes a 97% deterministic on-time assignment; individual warehouse rates may vary."]),
    ("inventory_accuracy", "Inventory accuracy", "%", "higher",
     "100 × comparable rows where WMS = ERP = VISION / comparable warehouse + SKU + location rows",
     ["Agreement is not independently verified physical accuracy. Missing, invalid or negative quantities are unknown, never zero.",
      "August assumes the undated source inventory snapshot as an illustrative baseline, not measured August history. No dated September snapshot exists.",
      "September aligns ERP and VISION to WMS for a deterministic 98.5% selection; original aligned rows remain aligned."]),
    ("false_availability", "False availability rate", "%", "lower",
     "100 × unique robots with EXPIRED safety certification and ONLINE or INTERMITTENT connectivity / unique fleet robots",
     ["Connected includes ONLINE and INTERMITTENT; OFFLINE is excluded from the numerator. EXPIRING is not EXPIRED.",
      "Conflicting duplicate robot identities remain in the unique-robot denominator with unknown status; they are not classified safe or expired-connected.",
      "August assumes the undated robot snapshot as an illustrative baseline, not measured August history. No dated September fleet snapshot exists.",
      "September assumes renewal of 90% of expired certificates by deterministic selection; these are not live robot changes."]),
    ("interventions", "Human interventions", "per 1,000 tasks", "lower",
     "1,000 × unique robot tasks with WES OR fleet status BLOCKED/FAILED / all unique robot tasks",
     ["Intervention proxy, not a count of human actions. Each task counts once even if both systems qualify.",
      "Robot task types are PICK, MOVE, PACK_FEED, STAGE and REPLENISH; unassigned blocked work is retained. Other types qualify only with an assigned robot.",
      "Cohort: task creation month. September uses August task rows with new identities and a deterministic 3.5% blocked/failed selection."]),
]


@router.get("")
def monthly_kpis(warehouse: str = "", x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    if x_demo_persona not in {"fleet", "supervisor", "admin"}:
        raise HTTPException(403, "Fleet, supervisor or admin persona required")
    try:
        source, scenario, _manifest = bundle()
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(503, "Monthly KPI source records are unavailable or invalid") from exc
    warehouses = sorted({r["warehouse_id"] for rows in source.values() for r in rows})
    if warehouse and warehouse not in warehouses:
        raise HTTPException(422, "Unknown warehouse")
    august = aggregate(source, "2026-08", warehouse, snapshots=True, as_of=AS_OF)
    september = aggregate(scenario, "2026-09", warehouse, snapshots=True, basis="Generated full-month September scenario")
    observed = aggregate(source, "2026-09", warehouse, as_of=AS_OF)
    ranges = source_coverage(source, warehouse)
    september_ranges = source_coverage(source, warehouse, "2026-09")
    september_dates = [date for span in september_ranges.values() if span for date in span]
    return {
        "note": "Demo comparison — illustrative results.", "warehouses": warehouses, "warehouse": warehouse,
        "periods": {
            "august": {"label": "August 2026", "start": "2026-08-01", "end": "2026-08-31", "basis": "Source records and assumed snapshot baselines"},
            "september": {"label": "September 2026", "start": "2026-09-01", "end": "2026-09-30", "basis": "Full-month illustrative scenario, not observed results"},
            "september_to_date": {"label": "September source coverage",
                                  "start": min(september_dates) if september_dates else None,
                                  "end": max(september_dates) if september_dates else None,
                                  "basis": "Partial source extract, bounded as of September 22, 2026 UTC; not full-month observations"},
        },
        "metrics": [dict(id=key, label=label, unit=unit, direction=direction, formula=formula,
                         details=details, august=august[key], september=september[key],
                         september_to_date=observed[key],
                         change=changes(august[key], september[key], unit == "%"))
                    for key, label, unit, direction, formula, details in DEFINITIONS],
        "provenance": {
            "scenario_version": VERSION,
            "sources": ["Original orders.csv, shipments.csv and tasks.csv observations",
                        "Undated inventory_snapshot.csv and robots.csv baseline assumptions",
                        "Separate 7,000-order archive benchmark audited but excluded; not blended with original records or live execution"],
            "assumptions": ["Offset-free source timestamps interpreted as UTC.",
                            "Comparison reference date: September 22, 2026 (23:59:59 UTC). Source evidence after this cutoff is excluded; later September scenario dates are not already observed.",
                            "September scenario uses new in-memory records. Original outcomes remain unchanged.",
                            "Period coverage is extract coverage, not a claim of current live observation.",
                            "No causal improvement or predictive accuracy is established.",
                            "Change is September minus August; rates show percentage points. Relative change is unavailable for a zero baseline."],
            "source_coverage": {**{name: f"{span[0]} through {span[1]}" if span else "No dated records in scope"
                                   for name, span in ranges.items()},
                                "inventory_and_fleet": "Undated"},
        },
    }