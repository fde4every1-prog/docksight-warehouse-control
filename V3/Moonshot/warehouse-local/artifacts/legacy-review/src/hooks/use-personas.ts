import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Role } from '@/contexts/PersonaContext';

const BASE_URL = '/api/personas';

async function fetchPersona<T>(url: string, role: Role, options: RequestInit = {}): Promise<T> {
  const headers = {
    ...options.headers,
    'X-Demo-Persona': role,
  };
  const res = await fetch(`${BASE_URL}${url}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    let message = text || res.statusText;
    try {
      const body = JSON.parse(text);
      if (typeof body?.detail === 'string') message = body.detail;
      else if (Array.isArray(body?.detail)) {
        message = body.detail.map((item: any) => item?.msg || JSON.stringify(item)).join('; ');
      }
    } catch {
      // The API may return plain text for non-validation failures.
    }
    throw new Error(message);
  }
  return res.json();
}

export interface Intervention {
  id: string;
  kind: 'inventory_mismatch' | 'replenishment_alert' | 'priority_override' | 'fleet_readiness' | 'control_asset_readiness' | 'task_completion_conflict' | 'resource_failure';
  warehouse_id: string;
  entity_id: string;
  title: string;
  description: string;
  owner: 'fleet' | 'supervisor';
  status: 'open' | 'investigating' | 'awaiting_approval' | 'resolved';
  evidence?: Record<string, any>;
  current_state?: Record<string, any> | null;
  linked_work?: any[];
  priority?: 'P1' | 'P2';
  recurrence_count?: number;
  proposed_action?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
  events: {
    at: string;
    persona: string;
    action: string;
    reason: string;
    details?: any;
  }[];
  allowed_actions: string[];
}

export interface InterventionIssue {
  id: string;
  kind: string;
  priority: 'P1' | 'P2';
  warehouse_id: string;
  entity_id: string;
  title: string;
  status: 'open' | 'investigating' | 'awaiting_approval' | 'resolved';
  linked_work: any[];
  current_state: any;
  recurrence_count: number;
  allowed_actions: string[];
  proposed_action?: any;
  evidence?: Record<string, any>;
  description?: string;
  owner?: 'fleet' | 'supervisor';
}

export interface InterventionActionPayload {
  action: 'investigate' | 'propose' | 'approve' | 'verify' | 'handoff' | 'manual_close';
  reason: string;
  evidence?: Record<string, any>;
  value?: any;
  assigned_to?: string;
}

export interface WorkspaceSummary {
  persona: string;
  summary: {
    open: number;
    awaiting_approval: number;
    resolved: number;
  };
  pagination?: {
    limit: number;
    offset: number;
    intervention_total: number;
    issue_total: number;
  };
  interventions: Intervention[];
  issues?: InterventionIssue[];
  correction_capabilities?: any;
  capabilities: string[];
  assumptions: string[];
}

export function useWorkspace(role: Role, limit: number = 250, offset: number = 0, search: string = '', section?: string) {
  return useQuery({
    queryKey: ['personas', role, 'workspace', limit, offset, search, section],
    queryFn: () => {
      const params = new URLSearchParams();
      if (limit) params.set('limit', limit.toString());
      if (offset) params.set('offset', offset.toString());
      if (search.trim()) params.set('q', search.trim());
      if (section) params.set('section', section);
      const qs = params.toString();
      return fetchPersona<WorkspaceSummary>(`/workspace${qs ? `?${qs}` : ''}`, role);
    },
    refetchInterval: 5000,
  });
}

export interface LowStockItem {
  id: string;
  warehouse_id: string;
  sku: string;
  aggregate_alert: { available: number; threshold: number; inventory_policy?: string } | null;
  alert?: InterventionIssue;
  interventions: InterventionIssue[];
  priority: 'P1' | 'P2';
}

export interface LowStockResponse {
  items: LowStockItem[];
  pagination: {
    limit: number;
    offset: number;
    total: number;
  };
}

export function useLowStock(
  role: Role,
  limit: number = 10,
  offset: number = 0,
  search: string = '',
  status: 'active' | 'closed' = 'active',
) {
  return useQuery({
    queryKey: ['personas', role, 'low-stock', limit, offset, search, status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (limit) params.set('limit', limit.toString());
      if (offset) params.set('offset', offset.toString());
      if (search.trim()) params.set('q', search.trim());
      if (status === 'closed') params.set('status', 'closed');
      const qs = params.toString();
      return fetchPersona<LowStockResponse>(`/low-stock${qs ? `?${qs}` : ''}`, role);
    },
    refetchInterval: 5000,
  });
}

export function useIntervention(role: Role, id: string) {
  return useQuery({
    queryKey: ['personas', role, 'interventions', id],
    queryFn: () => fetchPersona<Intervention>(`/interventions/${id}`, role),
    enabled: !!id,
    refetchInterval: 5000,
  });
}

export function useCreateIntervention(role: Role) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { kind: string; warehouse_id: string; entity_id: string; description: string; evidence?: any }) =>
      fetchPersona<Intervention>('/interventions', role, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: (intervention) => {
      queryClient.setQueryData(['personas', role, 'interventions', intervention.id], intervention);
      queryClient.invalidateQueries({ queryKey: ['personas'] });
    },
  });
}

export function useInterventionAction(role: Role, id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: InterventionActionPayload) =>
      fetchPersona<Intervention>(`/interventions/${id}/actions`, role, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }),
    onSuccess: (intervention) => {
      queryClient.setQueryData(['personas', role, 'interventions', id], intervention);
      queryClient.invalidateQueries({ queryKey: ['personas'] });
      queryClient.invalidateQueries({ queryKey: ['fulfillment'] });
    },
  });
}

export function useAuditEvents(role: Role) {
  return useQuery({
    queryKey: ['personas', role, 'audit'],
    queryFn: () => fetchPersona<{ events: any[] }>('/audit', role),
  });
}

export function usePolicyMatrix(role: Role) {
  return useQuery({
    queryKey: ['personas', role, 'policy'],
    queryFn: () => fetchPersona<{ roles: any[] }>('/policy', role),
  });
}

export function useAddResource(role: Role, dataset: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: any) =>
      fetchPersona<any>(`/resources/${dataset}`, role, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fulfillment'] });
      queryClient.invalidateQueries({ queryKey: ['personas'] });
    },
  });
}
