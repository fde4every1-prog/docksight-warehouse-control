import { useQuery } from '@tanstack/react-query';
import type { Role } from '@/contexts/PersonaContext';

export type MaintenanceSignal = { name: string; value: number; mean_7d: number; mean_30d: number };
export type MaintenancePrediction = {
  robot_id: string; warehouse_id: string; robot_type: string; vendor: string;
  observation_date: string; prediction_start: string; prediction_end: string;
  risk_probability: number | null; priority: 'review' | 'monitor' | 'unavailable';
  eligible: boolean; reason: string | null;
  signals: MaintenanceSignal[];
  history: Array<{ date: string; temperature_c: number; vibration_rms: number; motor_current_a: number;
    battery_soh_pct: number; task_count: number; fault_count: number }>;
};
export type MaintenanceEvaluation = {
  model: string; validation_average_precision: number | null;
  test_average_precision: number | null; test_roc_auc: number | null; test_brier_score: number | null;
};
export type MaintenanceMetrics = {
  test?: { all?: { precision_at_threshold: number; recall_at_threshold: number; prevalence: number; alert_rate: number } };
  test_event_level?: { events: number; events_detected: number; event_recall: number; median_lead_days: number | null };
  [key: string]: unknown;
};
export type MaintenanceModel = {
  available: boolean;
  message?: string;
  summary?: {
    model_id: string; trained_at: string; data_start: string; data_end: string;
    horizon_days: number; robot_count: number; row_count: number; failure_count: number;
    selected_model: string; validation_status: string; threshold: number;
    warnings: string[]; features: string[]; split: unknown; metrics: MaintenanceMetrics;
    feature_importance: Array<{ feature: string; importance: number }>;
  };
  evaluation: MaintenanceEvaluation[];
  warehouses: string[];
  counts: { total: number; review: number; monitor: number; unavailable: number };
  freshness: { snapshot_only: boolean; days_since_observation: number | null; stale: boolean };
};
export type MaintenanceList = {
  items: Array<Omit<MaintenancePrediction, 'history' | 'signals'>>;
  total: number; limit: number; offset: number; model_id: string;
};

async function request<T>(path: string, role: Role, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/predictive-maintenance${path}`, {
    headers: { 'X-Demo-Persona': role }, signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Unable to load predictive maintenance');
  }
  return response.json();
}
export function useMaintenanceModel(role: Role) {
  return useQuery({
    queryKey: ['predictive-maintenance', role, 'model'],
    queryFn: ({ signal }) => request<MaintenanceModel>('/model', role, signal),
    staleTime: 30_000, refetchInterval: 60_000,
  });
}
export function useMaintenancePredictions(role: Role, warehouse: string, search: string, priority: string, offset: number, enabled: boolean) {
  return useQuery({
    queryKey: ['predictive-maintenance', role, 'predictions', warehouse, search, priority, offset],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ warehouse, search, priority, offset: String(offset), limit: '20' });
      return request<MaintenanceList>(`/predictions?${params}`, role, signal);
    },
    enabled, staleTime: 30_000, refetchInterval: 60_000,
  });
}
export function useMaintenanceRobot(role: Role, robotId: string | null) {
  return useQuery({
    queryKey: ['predictive-maintenance', role, 'robot', robotId],
    queryFn: ({ signal }) => request<MaintenancePrediction>(`/robots/${encodeURIComponent(robotId!)}`, role, signal),
    enabled: !!robotId, staleTime: 30_000,
  });
}