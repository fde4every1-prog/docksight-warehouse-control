import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ScenarioMap, ScenarioRobot, TimelineEvent, RunMetrics, CompareResponse } from './use-batching';
import { formatApiError } from '@/lib/api-error';

export interface TransferMapZone {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface TransferMapNode {
  id: string;
  x: number;
  y: number;
  zone_id?: string;
}

export interface TransferMap {
  width: number;
  height: number;
  zones: TransferMapZone[];
  nodes: TransferMapNode[];
  edges: { from: string; to: string }[];
  conveyor: {
    id: string;
    node_id: string;
    label: string;
  };
}

export interface TransferRobot {
  id: string;
  type: string;
  capacity_kg: number | null;
  battery_percent: number | null;
  state: string;
  available: boolean;
  capabilities: string[];
  start_node: string;
  eligible: boolean;
  exclusion_reasons: string[];
  source_id: string;
}
export interface TransferRobotCandidate extends TransferRobot {}

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

export interface TransferPreview {
  warehouse_id: string;
  mode: string;
  ready: boolean;
  blockers: string[];
  snapshot: {
    snapshot_id: string;
    snapshot_at: string;
    expires_at: string;
    source_version: string;
    clock: { at: string; timezone: string; source: string };
  };
  map: TransferMap;
  robots: TransferRobot[];
  robot_candidates: TransferRobotCandidate[];
  inventory_summary: any;
  assumptions: string[];
}

export interface TransferTimelineEvent {
  event_id: string;
  batch_id: string | null;
  action: "pick" | "transfer";
  robot_id: string;
  donor_robot_id?: string;
  order_ids: string[];
  line_id: string | null;
  quantity: number | null;
  node_id: string;
  path: string[];
  start: number;
  end: number;
  carried_kg: number;
  state: string;
}

export interface TransferRunMetrics {
  transfer_service_seconds: number;
  overall_completion_seconds: number;
  deadline_misses: number;
  transferred_quantities: number;
  completed_order_count: number;
  excluded_order_count: number;
  robot_utilization: {
    robot_id: string;
    busy_seconds: number;
    utilization: number;
  }[];
}

export interface TransferRunOrder {
  id: string;
  completed_at: number;
  cutoff_seconds: number;
  on_time: boolean;
}

export interface TransferRun {
  timeline: TransferTimelineEvent[];
  orders: TransferRunOrder[];
  excluded_orders?: { order_id: string, reason: string }[];
  metrics: TransferRunMetrics;
}

export interface CompareTransferResponse {
  scenario_id: string;
  recommendation_id: string;
  baseline: TransferRun;
  proposed: TransferRun;
  difference: {
    transfer_service_seconds: number | null;
    overall_completion_seconds: number | null;
    label: string;
    comparable?: boolean;
    baseline_excluded_order_count?: number;
    proposed_excluded_order_count?: number;
  };
  assumptions: {
    transfer_service: string;
    picking: string;
    endpoint: string;
  };
}

export interface RowError {
  code: string;
  field: string;
  message: string;
}

export interface TransferRow {
  row_id: string;
  source_row: number;
  order_id: string | null;
  sku: string;
  quantity: number;
  order_cutoff: string | null;
  cutoff_timezone: string;
  allocations: any[];
  unit_weight_kg: number | null;
  total_weight_kg: number | null;
  errors: RowError[];
  warnings: any[];
  provenance: any;
}

export interface TransferScenario {
  scenario_id: string;
  snapshot_id: string;
  revision: number;
  valid: boolean;
  ready_for_planning: boolean;
  rows: TransferRow[];
  errors: (string | RowError)[];
  blockers: (string | RowError)[];
  map: TransferMap;
  robots: TransferRobot[];
  clock: { at: string; timezone: string; source: string };
  mode: string;
  snapshot: any;
}

export interface SuggestResponse {
  recommendation_id: string;
  scenario_id: string;
  revision: number;
  source: string;
  summary: string;
  plan: {
    batches: {
      batch_id: string;
      order_ids: string[];
      transfer_robot_id: string;
      pick_robot_ids: string[];
      execution_order: number;
      order_sequence: string[];
      stops: {
        sequence: number;
        action: "pick" | "transfer";
        robot_id: string;
        node_id: string;
        line_id?: string;
        inventory_source_id?: string;
        bin_id?: string;
        quantity?: number;
      }[];
      rationale: string;
    }[];
    excluded_orders: {
      order_id: string;
      reason: string;
    }[];
  };
  validation: { valid: boolean; errors: any[] };
  /**
   * Optional deterministic assessment supplied by the service. Older API
   * responses do not include this field, so the proposal remains usable
   * without presenting an inferred assessment.
   */
  quality_assessment?: {
    label: string;
    baseline: {
      transfer_service_seconds: number;
      overall_completion_seconds: number;
    };
    proposed: {
      transfer_service_seconds: number;
      overall_completion_seconds: number;
    };
    warnings?: string[];
  };
}

export function useTransferPreview(mode: 'live' | 'synthetic_demo') {
  return useQuery<TransferPreview, Error>({
    queryKey: ['transfer-lab', 'preview', mode],
    queryFn: () => fetchJson(`/api/batching/transfer/preview?mode=${mode}`)
  });
}

export function useImportExcel() {
  const queryClient = useQueryClient();
  return useMutation<TransferScenario, Error, { file: File, snapshot_id: string }>({
    mutationFn: async ({ file, snapshot_id }) => {
      const res = await fetch(`/api/batching/transfer/imports?snapshot_id=${encodeURIComponent(snapshot_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
        body: file,
      });
      if (!res.ok) {
        let detail = "Upload failed";
        try {
          const data = await res.json();
          detail = formatApiError(data, detail);
        } catch (e) {}
        throw new Error(detail);
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['transfer-lab', 'scenario', data.scenario_id], data);
    }
  });
}

export function useTransferScenario(scenario_id: string | null) {
  return useQuery<TransferScenario, Error>({
    queryKey: ['transfer-lab', 'scenario', scenario_id],
    queryFn: () => fetchJson(`/api/batching/transfer/scenarios/${encodeURIComponent(scenario_id!)}`),
    enabled: !!scenario_id,
  });
}

export interface RowPatch {
  row_id: string;
  order_id?: string | null;
  order_cutoff?: string | null;
}

export interface PatchScenarioRequest {
  scenario_id: string;
  revision: number;
  rows?: RowPatch[];
}

export function usePatchScenario() {
  const queryClient = useQueryClient();
  return useMutation<TransferScenario, Error, PatchScenarioRequest>({
    mutationFn: (req) => fetchJson(`/api/batching/transfer/scenarios/${encodeURIComponent(req.scenario_id)}/rows`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        revision: req.revision,
        rows: req.rows || []
      })
    }),
    onSuccess: (data) => {
      queryClient.setQueryData(['transfer-lab', 'scenario', data.scenario_id], data);
    }
  });
}

export function useSuggestTransferBatching() {
  return useMutation<SuggestResponse, Error, { scenario_id: string, revision: number }>({
    mutationFn: (req) => fetchJson(`/api/batching/transfer/scenarios/${encodeURIComponent(req.scenario_id)}/suggest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revision: req.revision })
    })
  });
}

export function useCompareTransferBatching() {
  return useMutation<CompareTransferResponse, Error, { scenario_id: string, revision: number, recommendation_id: string }>({
    mutationFn: (req) => fetchJson(`/api/batching/transfer/scenarios/${encodeURIComponent(req.scenario_id)}/compare`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revision: req.revision, recommendation_id: req.recommendation_id })
    })
  });
}
