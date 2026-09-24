import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usePersona, type Role } from '@/contexts/PersonaContext';

const BASE_URL = '/api/fulfillment';

export type Warehouse = Record<string, string>;
export type Sku = Record<string, string>;
export type DatasetInfo = { name: string; count: number; fields: string[] };

export interface Catalog {
  warehouses: Warehouse[];
  skus: Sku[];
  datasets: DatasetInfo[];
  counts: Record<string, number>;
  assumptions: string[];
  revision?: number;
  scenario_revision?: number;
  scenario_modified_count?: number;
}

export interface ResourceData {
  rows: Record<string, any>[];
  total: number;
  fields: string[];
  editable_fields: string[];
  field_types: Record<string, 'string'|'number'|'boolean'|'json'>;
  revision: number;
  scenario_modified_count: number;
  planning_impact?: string;
}

export interface Task {
  id: string;
  order_id: string;
  sub_order_id?: string;
  stage: string;
  status: 'pending' | 'queued' | 'running' | 'paused' | 'completed' | 'cancelled';
  allocation_id?: string;
  wait_reason?: string;
  resource_id?: string;
  resource_type?: string;
  started_at?: string;
  due_at?: string;
  completed_at?: string;
}

export interface SubOrder {
  id: string;
  order_id: string;
  sku: string;
  quantity: number;
  warehouse_id?: string;
  status: 'held' | 'reserved' | 'queued' | 'running' | 'completed' | 'cancelled' | 'recovery_required';
  hold_reason?: string;
  cutoff_at: string;
  overdue?: boolean;
  allocations?: any[];
  fulfillment_status?: string;
  fulfillment_history?: FulfillmentHistoryEntry[];
  warehouses?: string[];
  zones?: string[];
}

export interface OrderLine {
  sku: string;
  quantity: number;
}

export interface Order {
  id: string;
  source_order_id?: string;
  order_service?: 'Same_Day' | 'Next_Day' | 'Standard';
  order_source?: string;
  warehouse_id?: string; // made optional per-SKU warehouse support
  priority: 'standard' | 'high' | 'urgent';
  ship_by: string;
  status: 'planned' | 'queued' | 'running' | 'completed' | 'held' | 'cancelled' | 'partially_fulfilled' | 'recovery_required' | 'active' | 'rejected';
  created_at: string;
  lines: OrderLine[];
  sub_orders?: SubOrder[];
  plan?: Record<string, any>;
  issues?: string[];
  hold_reason?: string;
  events?: { at: string; message: string }[];
  tasks?: Task[];
  fulfillment_status?: string;
  fulfillment_history?: FulfillmentHistoryEntry[];
  warehouses?: string[];
  zones?: string[];
}

export interface FulfillmentHistoryEntry {
  status: string;
  at: string;
  sub_order_id?: string;
}

export interface AssignTasksResult {
  assigned: number;
  resumed: number;
  rechecked: number;
  still_waiting: number;
  ran_at: string;
  next_assignment_at: string;
}

export interface Config {
  min_stock_threshold: number;
  unit_weight_kg: number;
  staging_capacity: number;
  manual_payload_limit_kg: number;
  task_duration_seconds: number;
  shift: string;
}

export interface Alert {
  warehouse_id: string;
  sku: string;
  available: number;
  threshold: number;
}

export interface StateData {
  total_orders?: number;
  summary?: Record<string, number>;
  orders: Order[];
  tasks: Task[];
  alerts: Alert[];
  config: Config;
  server_time: string;
  assumptions: string[];
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function personaHeaders(role: Role, headers?: HeadersInit): Headers {
  const result = new Headers(headers);
  result.set('X-Demo-Persona', role);
  return result;
}

export interface DemandForecastItem {
  warehouse_id: string;
  sku: string;
  available_qty: number;
  forecast_7d: number;
  forecast_30d: number;
  daily_demand: number;
  history_units: number;
  history_days: number;
  history_status: string;
  low_stock: boolean;
}

export interface DemandForecastRun {
  id?: string;
  lookback_days: number;
  forecast_date: string;
  generated_at: string;
  window_start: string;
  window_end: string;
  method: string;
  scheduled_time: string;
  timezone: string;
  excluded_unassigned_units: number;
  stale: boolean;
}

export interface DemandForecastHistoryItem {
  date: string;
  ordered_units: number;
  rolling_7d: number | null;
}

export interface DemandForecastProjectionItem {
  date: string;
  daily_demand: number;
}

export interface DemandForecastDetailResponse {
  run: DemandForecastRun & { id: string };
  item: DemandForecastItem;
  history_available: boolean;
  history: DemandForecastHistoryItem[];
  projection: DemandForecastProjectionItem[];
  stock_checked_at: string;
  minimum_replenishment: number;
}

export interface DemandForecastResponse {
  items: DemandForecastItem[];
  run: DemandForecastRun | null;
}

export function useDemandForecasts(warehouse_id?: string, search?: string) {
  return useQuery({
    queryKey: ['fulfillment', 'demand-forecasts', warehouse_id, search],
    queryFn: ({ signal }) => {
      const url = new URL(`${window.location.origin}${BASE_URL}/demand-forecasts`);
      if (warehouse_id) url.searchParams.set('warehouse_id', warehouse_id);
      if (search) url.searchParams.set('search', search);
      return fetchJson<DemandForecastResponse>(url.toString(), { signal });
    },
    refetchInterval: 10000,
  });
}

export function useDemandForecastDetail(warehouse_id: string, sku: string, run_id?: string) {
  return useQuery({
    queryKey: ['fulfillment', 'demand-forecasts', 'detail', warehouse_id, sku, run_id],
    queryFn: ({ signal }) => {
      const url = new URL(`${window.location.origin}${BASE_URL}/demand-forecasts/detail`);
      url.searchParams.set('warehouse_id', warehouse_id);
      url.searchParams.set('sku', sku);
      if (run_id) url.searchParams.set('run_id', run_id);
      return fetchJson<DemandForecastDetailResponse>(url.toString(), { signal });
    },
    enabled: !!warehouse_id && !!sku,
    staleTime: 0,
    refetchInterval: 10000,
    retry: false,
  });
}

export function useCatalog() {
  return useQuery({
    queryKey: ['fulfillment', 'catalog'],
    queryFn: () => fetchJson<Catalog>(`${BASE_URL}/catalog`),
  });
}

export function useResources(dataset: string, warehouse_id?: string) {
  return useQuery({
    queryKey: ['fulfillment', 'resources', dataset, warehouse_id],
    queryFn: () => {
      const url = new URL(`${window.location.origin}${BASE_URL}/resources/${dataset}`);
      if (warehouse_id) {
        url.searchParams.set('warehouse_id', warehouse_id);
      }
      return fetchJson<ResourceData>(url.toString());
    },
    enabled: !!dataset,
  });
}

export function useFulfillmentState() {
  return useQuery({
    queryKey: ['fulfillment', 'state'],
    queryFn: () => fetchJson<StateData>(`${BASE_URL}/state`),
    refetchInterval: 2000,
  });
}

export function useOrders(params: { search?: string; status?: string; warehouse?: string; limit: number; offset: number }) {
  return useQuery({
    queryKey: ['fulfillment', 'orders', params],
    queryFn: () => {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== '') query.set(key, String(value));
      });
      return fetchJson<{ items: Order[]; total: number; limit: number; offset: number }>(`${BASE_URL}/orders?${query}`);
    },
    refetchInterval: 5000,
  });
}

export function useOrder(id: string) {
  return useQuery({
    queryKey: ['fulfillment', 'order', id],
    queryFn: () => fetchJson<Order>(`${BASE_URL}/orders/${id}`),
    refetchInterval: 2000,
    enabled: !!id,
  });
}

export function useCreateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { warehouse_id: string; priority: string; ship_by: string; lines: OrderLine[]; request_id: string }) =>
      fetchJson<Order>(`${BASE_URL}/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment', 'state'] });
    },
  });
}

export function useOrderAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'start' | 'retry' | 'cancel' }) =>
      fetchJson<Order>(`${BASE_URL}/orders/${id}/${action}`, {
        method: 'POST',
      }),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment', 'state'] });
      queryClient.invalidateQueries({ queryKey: ['fulfillment', 'order', id] });
    },
  });
}

export function useAssignTasks(role: Role) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      fetchJson<AssignTasksResult>(`${BASE_URL}/assign-tasks`, {
        method: 'POST',
        headers: personaHeaders(role),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment', 'state'] });
      queryClient.invalidateQueries({ queryKey: ['fulfillment', 'order'] });
    },
  });
}

export function useDownloadOrdersCsv(role: Role) {
  return useMutation({
    mutationFn: async () => {
      const response = await fetch(`${BASE_URL}/orders.csv`, {
        headers: personaHeaders(role),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || response.statusText);
      }

      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition');
      const filename = disposition?.match(/filename="?([^"]+)"?/i)?.[1] || 'orders.csv';
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      return filename;
    },
  });
}

export function useUpdateConfig() {
  const queryClient = useQueryClient();
  const { role } = usePersona();
  return useMutation({
    mutationFn: (config: Config) =>
      fetchJson<Config>(`${BASE_URL}/config`, {
        method: 'PUT',
        headers: personaHeaders(role, { 'Content-Type': 'application/json' }),
        body: JSON.stringify(config),
      }),
    onSuccess: (config) => {
      queryClient.setQueryData<StateData>(['fulfillment', 'state'], (current) =>
        current ? { ...current, config } : current,
      );
      queryClient.invalidateQueries({ queryKey: ['fulfillment', 'state'] });
    },
  });
}

export function useUpdateResourceRow(dataset: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, values, revision }: { id: string | number; values: Record<string, any>; revision: number }) =>
      fetchJson<any>(`${BASE_URL}/resources/${dataset}/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values, revision }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment'] });
    },
  });
}

export function useResetResourceRow(dataset: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, revision }: { id: string | number; revision: number }) =>
      fetchJson<any>(`${BASE_URL}/resources/${dataset}/${id}?revision=${revision}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment'] });
    },
  });
}

export function useResetScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ revision }: { revision: number }) =>
      fetchJson<any>(`${BASE_URL}/scenario?revision=${revision}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment'] });
    },
  });
}
