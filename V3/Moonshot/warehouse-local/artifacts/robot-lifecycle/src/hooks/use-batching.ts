import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { formatApiError } from '@/lib/api-error';

export interface Batch {
  id: string;
  order_ids: string[];
  reason?: string;
}

export interface Exclusion {
  order_ids: string[];
  reason: string;
}

export interface ScenarioMapNode {
  id: string;
  x: number;
  y: number;
  zone?: string;
}

export interface ScenarioMapZone {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ScenarioMapEdge {
  from: string;
  to: string;
}

export interface ScenarioMapBin {
  id: string;
  node_id: string;
  zone: string;
  sku: string;
  stock: number;
}

export interface ScenarioMap {
  width: number;
  height: number;
  boundary: { x: number; y: number }[];
  zones: ScenarioMapZone[];
  nodes: ScenarioMapNode[];
  edges: ScenarioMapEdge[];
  bins: ScenarioMapBin[];
  destinations: {
    pick: string;
    transfer: string;
    pack_feed: string;
    stage: string;
  };
}

export interface ScenarioOrderLine {
  id: string;
  sku: string;
  quantity: number;
  bin_id: string;
}

export interface ScenarioOrder {
  id: string;
  sub_order_id?: string;
  tote_id?: string;
  status: string;
  cutoff_seconds: number;
  lines: ScenarioOrderLine[];
}

export interface ScenarioRobot {
  id: string;
  warehouse_id: string;
  type: string;
  start_node: string;
  available: boolean;
  battery_percent: number;
  capacity_kg: number;
  capabilities: string[];
  blocked_reason?: string;
  eligible?: boolean;
  exclusion_reasons?: string[];
}

export interface Scenario {
  scenario_id: string;
  warehouse_id: string;
  seed: number;
  clock_start: string;
  source: string;
  assumptions: string[];
  map: ScenarioMap;
  skus: { id: string; unit_weight_kg: number }[];
  orders: ScenarioOrder[];
  robots: ScenarioRobot[];
  assets: any[];
  constraints: {
    base_duration_seconds: number;
    max_batch_size: number;
    max_proximity: number;
  };
}

export interface GetScenarioResponse {
  scenario: Scenario;
  candidates: Batch[];
  exclusions: Exclusion[];
}

export interface SuggestRequest {
  scenario_id: string;
}

export interface SuggestResponse {
  scenario_id: string;
  batches: Batch[];
  selected_candidate_ids: string[];
  summary: string;
  exclusions: Exclusion[];
  source: string;
  cached: boolean;
}

export interface CompareRequest {
  scenario_id: string;
  candidate_ids: string[];
}

export interface PathPoint {
  node_id: string;
  x: number;
  y: number;
  at: number;
}

export interface TimelineEvent {
  id: string;
  stage: "pick" | "move" | "pack_feed" | "stage";
  batch_id: string | null;
  order_ids: string[];
  line_ids: string[];
  tote_ids: string[];
  resource_id: string;
  resource_type: "robot" | "asset";
  start: number;
  end: number;
  duration: number;
  payload_kg: number;
  path: PathPoint[];
}

export interface RunOrder {
  id: string;
  completed_at: number;
  cutoff_seconds: number;
  on_time: boolean;
}

export interface RobotUtilization {
  robot_id: string;
  busy_seconds: number;
  utilization: number;
}

export interface RunMetrics {
  completed_orders: number;
  completed_tasks: number;
  logical_tasks: number;
  service_seconds: number;
  makespan_seconds: number;
  deadline_misses: number;
  robot_utilization: RobotUtilization[];
}

export interface Run {
  mode: "baseline" | "batched";
  scenario_id: string;
  timeline: TimelineEvent[];
  orders: RunOrder[];
  metrics: RunMetrics;
  inventory: any[];
}

export interface CompareResponse {
  scenario_id: string;
  baseline: Run;
  batched: Run;
  savings: {
    service_seconds: number;
    makespan_seconds: number;
    comparable?: boolean;
    label?: string;
  };
}

const fetchJson = async (url: string, options?: RequestInit) => {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = "An error occurred";
    try {
      const data = await res.json();
      detail = formatApiError(data, detail);
    } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
};

export function useScenario() {
  return useQuery<GetScenarioResponse, Error>({
    queryKey: ['batching', 'scenario'],
    queryFn: () => fetchJson('/api/batching/scenario')
  });
}

export function useSuggestBatching() {
  return useMutation<SuggestResponse, Error, SuggestRequest>({
    mutationFn: (req) => fetchJson('/api/batching/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    })
  });
}

export function useCompareBatching() {
  return useMutation<CompareResponse, Error, CompareRequest>({
    mutationFn: (req) => fetchJson('/api/batching/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req)
    })
  });
}
