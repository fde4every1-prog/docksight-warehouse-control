import { useQuery } from '@tanstack/react-query';
import { usePersona } from '@/contexts/PersonaContext';

const BASE_URL = '/api/fulfillment/replays';

async function fetchJson<T>(url: string, headers: HeadersInit): Promise<T> {
  const res = await fetch(url, { headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.redirected) {
    const target = new URL(res.url);
    if (target.origin === window.location.origin && target.pathname.startsWith('/api/fulfillment/orders')) {
      return { unified_url: target.pathname.replace(/^\/api/, '') + target.search } as T;
    }
  }
  return res.json();
}

function getHeaders(role: string): HeadersInit {
  return { 'X-Demo-Persona': role };
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return `${h}h ${remM}m`;
}

export interface ReplaySummary {
  unified_url?: string;
  run_id: string;
  status: 'preparing' | 'running' | 'completed' | 'failed' | string;
  total_orders: number;
  processed_orders: number;
  accepted_orders: number;
  rejected_orders: number;
  completed_orders: number;
  held_orders: number;
  other_orders: number;
  started_at: string;
  finished_at: string | null;
  simulated_at: string | null;
  source_period: {
    start: string;
    end: string;
  };
  task_duration_seconds: number;
  sample_size?: number;
  is_full_7000?: boolean;
  metrics: {
    simulated_average_cycle_seconds: number | null;
    benchmark_average_cycle_seconds: number | null;
    simulated_on_time_percent: number | null;
    benchmark_on_time_percent: number | null;
  };
  checks: {
    name: string;
    passed: boolean;
    detail: string;
  }[];
  warnings: string[];
  warehouses: string[];
  error: string | null;
}

export interface ReplayOrderRow {
  source_order_id: string;
  core_order_id: string | null;
  warehouse_id: string;
  sku: string;
  quantity: number;
  priority: string;
  created_at: string;
  cutoff: string;
  status: string;
  finished_at: string | null;
  cycle_time_seconds: number | null;
  benchmark_actual_departure: string | null;
  benchmark_cycle_time_seconds: number | null;
  reason: string | null;
}

export interface ReplayOrdersResponse {
  unified_url?: string;
  items: ReplayOrderRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReplayOrderDetail {
  unified_url?: string;
  order: ReplayOrderRow;
  tasks: any[];
  allocations: any[];
  events: any[];
  source: any;
  benchmark: any;
}

export function useReplays() {
  const { role } = usePersona();
  return useQuery({
    queryKey: ['fulfillment', 'replays', 'collection', role],
    queryFn: () => fetchJson<{ items: ReplaySummary[] }>(BASE_URL, getHeaders(role)),
    refetchInterval: (query) => {
      const data = query.state.data;
      const isRunning = data?.items.some(r => r.status === 'preparing' || r.status === 'running');
      return isRunning ? 3000 : 10000;
    }
  });
}

export function useReplay(runId: string) {
  const { role } = usePersona();
  return useQuery({
    queryKey: ['fulfillment', 'replays', 'detail', runId, role],
    queryFn: () => fetchJson<ReplaySummary>(`${BASE_URL}/${encodeURIComponent(runId)}`, getHeaders(role)),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'preparing' || status === 'running' ? 3000 : 10000;
    }
  });
}

export function useReplayOrders(runId: string, params: { status?: string; warehouse?: string; search?: string; limit: number; offset: number }, runStatus?: string) {
  const { role } = usePersona();
  return useQuery({
    queryKey: ['fulfillment', 'replays', runId, 'orders', params, role],
    queryFn: () => {
      const url = new URL(`${window.location.origin}${BASE_URL}/${encodeURIComponent(runId)}/orders`);
      if (params.status) url.searchParams.set('status', params.status);
      if (params.warehouse) url.searchParams.set('warehouse', params.warehouse);
      if (params.search) url.searchParams.set('search', params.search);
      url.searchParams.set('limit', params.limit.toString());
      url.searchParams.set('offset', params.offset.toString());
      return fetchJson<ReplayOrdersResponse>(url.toString(), getHeaders(role));
    },
    enabled: !!runId,
    refetchInterval: runStatus === 'preparing' || runStatus === 'running' ? 3000 : 10000,
  });
}

export function useReplayOrderDetail(runId: string, sourceOrderId: string, runStatus?: string) {
  const { role } = usePersona();
  return useQuery({
    queryKey: ['fulfillment', 'replays', runId, 'orders', sourceOrderId, 'detail', role],
    queryFn: () => fetchJson<ReplayOrderDetail>(`${BASE_URL}/${encodeURIComponent(runId)}/orders/${encodeURIComponent(sourceOrderId)}`, getHeaders(role)),
    enabled: !!runId && !!sourceOrderId,
    refetchInterval: runStatus === 'preparing' || runStatus === 'running' ? 3000 : 10000,
  });
}
