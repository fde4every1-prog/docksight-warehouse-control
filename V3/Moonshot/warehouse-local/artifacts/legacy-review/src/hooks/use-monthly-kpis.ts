import { useQuery } from '@tanstack/react-query';
import type { Role } from '@/contexts/PersonaContext';

export type MetricValue = {
  value: number | null;
  numerator: number;
  denominator: number;
  sample_size: number;
  exclusions: Record<string, number>;
  coverage: { start: string | null; end: string | null };
  basis: string;
};

export type Metric = {
  id: string;
  label: string;
  unit: string;
  direction: 'lower' | 'higher';
  formula: string;
  details: string[];
  august: MetricValue;
  september: MetricValue;
  september_to_date: MetricValue;
  change: {
    absolute: number | null;
    percentage_points: number | null;
    relative_percent: number | null;
  };
};

export type MonthlyKpisResponse = {
  note: string;
  warehouses: string[];
  warehouse: string | null;
  periods: {
    august: { label: string; start: string; end: string; basis: string };
    september: { label: string; start: string; end: string; basis: string };
    september_to_date: { label: string; start: string | null; end: string | null; basis: string };
  };
  metrics: Metric[];
  provenance: {
    sources: string[];
    assumptions: string[];
    scenario_version: string;
    source_coverage: Record<string, string>;
  };
};

async function request<T>(path: string, role: Role, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/monthly-kpis${path}`, {
    headers: { 'X-Demo-Persona': role }, signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Unable to load monthly KPIs');
  }
  return response.json();
}

export function useMonthlyKpis(role: Role, warehouse: string) {
  return useQuery({
    queryKey: ['monthly-kpis', role, warehouse],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      if (warehouse && warehouse !== 'all') {
        params.append('warehouse', warehouse);
      }
      return request<MonthlyKpisResponse>(`?${params}`, role, signal);
    },
    staleTime: 300_000,
  });
}