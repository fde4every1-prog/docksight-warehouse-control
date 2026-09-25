import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Role } from '@/contexts/PersonaContext';

const BASE_URL = '/api/personas/fleet/issues';

export type FleetIssueContext = {
  entity_type: 'robot' | 'maintenance' | 'control_asset';
  entity_id: string;
  revision: number;
  values: Record<string, string | null>;
  allowed_values: Record<string, string[]>;
  missing?: boolean;
};

export type FleetIssueEvent = {
  at: string;
  persona: string;
  action: string;
  reason: string;
  details?: unknown;
};

export type FleetIssue = {
  id: string;
  fingerprint: string;
  kind: string;
  entity_id: string;
  warehouse_id: string;
  title: string;
  status: string;
  priority: string;
  priority_reason: string | null;
  impacted_orders: Array<{ order_id: string; task_ids: string[] }>;
  blockers: string[];
  contexts: FleetIssueContext[];
  assignment_blockers: string[];
  events: FleetIssueEvent[];
};

export type FleetIssuesResponse = {
  items: FleetIssue[];
  pagination: { limit: number; offset: number; total: number };
};

export type FleetRepairPayload = {
  fingerprint: string;
  contexts: Array<{
    entity_type: FleetIssueContext['entity_type'];
    entity_id: string;
    revision: number;
    values: Record<string, string>;
  }>;
};

async function request<T>(path: string, role: Role, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      ...options?.headers,
      'X-Demo-Persona': role,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const body = JSON.parse(text);
      if (typeof body?.detail === 'string') message = body.detail;
      else if (Array.isArray(body?.detail)) {
        message = body.detail.map((item: { msg?: string }) => item.msg || 'Invalid value').join('; ');
      }
    } catch {
      // Plain text API errors remain useful as-is.
    }
    throw new Error(message);
  }
  return response.json();
}

export function useFleetIssues(role: Role, offset: number, search: string) {
  return useQuery({
    queryKey: ['personas', role, 'fleet-issues', 10, offset, search],
    queryFn: () => {
      const params = new URLSearchParams({ limit: '10', offset: String(offset) });
      if (search.trim()) params.set('q', search.trim());
      return request<FleetIssuesResponse>(`?${params}`, role);
    },
    refetchInterval: 5000,
  });
}

export function useFleetIssue(role: Role, id: string | null, open: boolean) {
  return useQuery({
    queryKey: ['personas', role, 'fleet-issues', 'detail', id],
    queryFn: () => request<FleetIssue>(`/${encodeURIComponent(id!)}`, role),
    enabled: open && !!id,
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
    refetchInterval: 5000,
    staleTime: 0,
  });
}

export function useRepairFleetIssue(role: Role, id: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FleetRepairPayload) => {
      if (!id) throw new Error('No fleet issue selected.');
      return request<FleetIssue>(`/${encodeURIComponent(id)}/repair`, role, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (issue) => {
      queryClient.setQueryData(['personas', role, 'fleet-issues', 'detail', id], issue);
      queryClient.invalidateQueries({ queryKey: ['personas'] });
      queryClient.invalidateQueries({ queryKey: ['fulfillment'] });
    },
  });
}