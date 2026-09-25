import React, { useState } from 'react';
import { usePersona } from '@/contexts/PersonaContext';
import { useWorkspace, useCreateIntervention } from '@/hooks/use-personas';
import { useCatalog, useFulfillmentState } from '@/hooks/use-fulfillment';
import { Shield, Box, AlertTriangle, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { WorkspaceQueryError } from '../WorkspaceQueryError';
import { SupervisorInterventions } from './SupervisorInterventions';
import { SupervisorLowStock } from './SupervisorLowStock';

export default function SupervisorWorkspace() {
  const { role } = usePersona();
  const { data: workspace, error, isLoading: summaryLoading } = useWorkspace(role, 1, 0, '', 'discrepancies'); // using limit 1 just to get the summary
  const { data: stateData } = useFulfillmentState();
  const { data: catalog } = useCatalog();

  const activeOrders = stateData?.orders?.filter(o => ['planned', 'queued', 'held'].includes(o.status)) || [];

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6 overflow-hidden">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6 text-primary shrink-0" />
            <span className="truncate">Supervisor Workspace</span>
          </h1>
          <p className="text-muted-foreground mt-1 truncate">Manage interventions, priority overrides, and inventory discrepancies.</p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <NewInterventionDialog 
            kind="priority_override" 
            title="Request Priority Override"
            description="Request a priority escalation for an active order."
            warehouses={catalog?.warehouses || []}
            orders={activeOrders}
          />
        </div>
      </div>

      <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col md:flex-row items-center gap-4">
        <h3 className="font-bold text-sm uppercase tracking-widest text-muted-foreground whitespace-nowrap">Workspace Summary</h3>
        <div className="flex flex-1 gap-4 overflow-x-auto w-full">
          {error ? (
            <div className="text-sm text-destructive font-mono p-2">Failed to load summary.</div>
          ) : summaryLoading ? (
            <div className="text-sm text-muted-foreground font-mono p-2">Loading...</div>
          ) : (
            <>
              <div className="bg-muted p-2 px-6 rounded text-center min-w-24">
                <div className="text-2xl font-bold">{workspace?.summary?.open ?? '-'}</div>
                <div className="text-xs text-muted-foreground">Open</div>
              </div>
              <div className="bg-muted p-2 px-6 rounded text-center min-w-24">
                <div className="text-2xl font-bold">{workspace?.summary?.awaiting_approval ?? '-'}</div>
                <div className="text-xs text-muted-foreground">Awaiting</div>
              </div>
              <div className="bg-muted p-2 px-6 rounded text-center min-w-24">
                <div className="text-2xl font-bold">{workspace?.summary?.resolved ?? '-'}</div>
                <div className="text-xs text-muted-foreground">Resolved</div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 min-w-0">
        <div className="border rounded-lg p-4 bg-card shadow-sm h-[600px] flex flex-col min-w-0">
          <SupervisorInterventions />
        </div>
        <div className="border rounded-lg p-4 bg-card shadow-sm h-[600px] flex flex-col min-w-0">
          <SupervisorLowStock />
        </div>
      </div>
    </div>
  );
}

function NewInterventionDialog({ 
  kind, 
  title, 
  description,
  warehouses,
  skus,
  orders,
  tasks
}: { 
  kind: string; 
  title: string; 
  description: string;
  warehouses?: any[];
  skus?: any[];
  orders?: any[];
  tasks?: any[];
}) {
  const { role } = usePersona();
  const createIntervention = useCreateIntervention(role);
  const [open, setOpen] = useState(false);
  const [warehouseId, setWarehouseId] = useState('');
  const [entityId, setEntityId] = useState('');
  const [desc, setDesc] = useState('');

  const isDisabled = 
    (kind === 'priority_override' && (!orders || orders.length === 0)) ||
    (kind === 'task_completion_conflict' && (!tasks || tasks.length === 0));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!warehouseId || !entityId || !desc) return;

    createIntervention.mutate({
      kind,
      warehouse_id: warehouseId,
      entity_id: entityId,
      description: desc,
      evidence: { source: 'manual_supervisor_entry' }
    }, {
      onSuccess: () => {
        setOpen(false);
        setWarehouseId('');
        setEntityId('');
        setDesc('');
      }
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={kind === 'priority_override' ? 'secondary' : 'default'} size="sm" className="gap-2">
          {kind === 'inventory_mismatch' ? <Box className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
          {title}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <p className="text-sm text-muted-foreground">{description}</p>
        </DialogHeader>

        {isDisabled ? (
           <div className="p-4 bg-muted/50 border rounded-md text-center space-y-2">
             <AlertTriangle className="h-8 w-8 text-muted-foreground mx-auto" />
             <div className="font-bold text-sm">Cannot Create Scenario</div>
             <div className="text-xs text-muted-foreground">
               {kind === 'priority_override' 
                 ? "No active orders (planned, queued, or held) available to override."
                 : "No historical or active tasks available to flag a conflict."}
             </div>
           </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 mt-4">
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase text-muted-foreground">Warehouse</label>
              <select 
                value={warehouseId} 
                onChange={(e) => setWarehouseId(e.target.value)}
                required
                className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                <option value="">Select warehouse...</option>
                {warehouses?.map(w => (
                  <option key={w.warehouse_id} value={w.warehouse_id}>{w.warehouse_id}</option>
                ))}
              </select>
            </div>

            {kind === 'inventory_mismatch' && skus && (
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase text-muted-foreground">SKU</label>
                <select 
                  value={entityId} 
                  onChange={(e) => setEntityId(e.target.value)}
                  required
                  className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="">Select SKU...</option>
                  {skus.map(s => (
                    <option key={s.sku} value={s.sku}>
                      {s.sku} ({s.description})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {kind === 'priority_override' && orders && (
               <div className="space-y-2">
                <label className="text-xs font-bold uppercase text-muted-foreground">Target Order</label>
                <select 
                  value={entityId} 
                  onChange={(e) => setEntityId(e.target.value)}
                  required
                  className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="">Select active order...</option>
                  {orders.map(o => (
                    <option key={o.id} value={o.id}>
                      {o.id} (Current: {o.priority})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {kind === 'task_completion_conflict' && tasks && (
               <div className="space-y-2">
                <label className="text-xs font-bold uppercase text-muted-foreground">Target Task</label>
                <select 
                  value={entityId} 
                  onChange={(e) => setEntityId(e.target.value)}
                  required
                  className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="">Select historical or active task...</option>
                  {tasks.map(t => (
                    <option key={t.id} value={t.id}>
                      {t.id} (Status: {t.status})
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="space-y-2">
              <label className="text-xs font-bold uppercase text-muted-foreground">Description / Context</label>
              <Textarea 
                value={desc} 
                onChange={e => setDesc(e.target.value)} 
                placeholder="Describe why this intervention is needed..."
                required
                className="font-mono text-sm min-h-[100px]"
              />
            </div>

            <div className="flex justify-end pt-4">
              <Button type="submit" disabled={createIntervention.isPending || !warehouseId || !entityId || !desc}>
                {createIntervention.isPending ? 'Creating...' : 'Create Scenario'}
              </Button>
            </div>
            {createIntervention.error instanceof Error && (
              <div role="alert" data-testid={`error-create-${kind}`} className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                {createIntervention.error.message}
              </div>
            )}
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

