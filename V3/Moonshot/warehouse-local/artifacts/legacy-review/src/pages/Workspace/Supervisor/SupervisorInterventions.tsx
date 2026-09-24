import React, { useState, useEffect } from 'react';
import { usePersona } from '@/contexts/PersonaContext';
import { useWorkspace, InterventionIssue, Intervention } from '@/hooks/use-personas';
import { useCatalog, useFulfillmentState } from '@/hooks/use-fulfillment';
import { Search, ChevronLeft, ChevronRight, Box, AlertTriangle, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { Link } from 'wouter';
import { CorrectionWorkflow } from '@/components/personas/CorrectionWorkflow';

export function SupervisorInterventions() {
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 10;

  const { role } = usePersona();
  const { data: workspace, isLoading, error, refetch } = useWorkspace(role, limit, offset, search, 'discrepancies');

  const issues = workspace?.issues || workspace?.interventions || [];
  const issueTotal = workspace?.pagination?.issue_total ?? workspace?.pagination?.intervention_total ?? (error ? 0 : issues.length);
  const totalPages = Math.max(1, Math.ceil(issueTotal / limit));
  const page = Math.floor(offset / limit) + 1;

  useEffect(() => {
    if (workspace && !error && offset > 0 && offset >= issueTotal) {
      setOffset(Math.max(0, totalPages - 1) * limit);
    }
  }, [workspace, error, offset, issueTotal, totalPages]);

  return (
    <div className="flex flex-col h-full space-y-4 min-w-0">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-2">
        <h2 className="text-lg font-bold">Inventory Discrepancy</h2>
        <div className="relative w-full sm:w-64 sm:shrink-0">
          <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
          <Input 
            placeholder="Search discrepancies..." 
            aria-label="Search all discrepancies"
            className="pl-9 h-8 text-sm"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
          />
        </div>
      </div>

      {error ? (
        <div className="flex-1 flex flex-col items-center justify-center border border-destructive/20 bg-destructive/5 rounded-lg p-6 text-center space-y-4">
          <AlertCircle className="h-8 w-8 text-destructive opacity-80" />
          <div className="space-y-1">
            <h3 className="font-bold text-destructive">Failed to load interventions</h3>
            <p className="text-sm text-destructive/80 text-balance max-w-sm">{error instanceof Error ? error.message : 'Unknown error occurred'}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>Try Again</Button>
        </div>
      ) : isLoading ? (
        <div className="space-y-4" role="status" aria-label="Loading interventions">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : issues.length === 0 ? (
        <div className="border border-dashed rounded-lg p-8 text-center text-muted-foreground bg-muted/20">
          {search ? "No interventions match your search." : "No active interventions require your attention."}
        </div>
      ) : (
        <div className="space-y-3 flex-1 overflow-y-auto pr-2">
          {issues.map((issue: any) => (
            issue.kind === 'inventory_mismatch'
              ? <InventoryIssueCard key={issue.id} issue={issue} />
              : <InterventionCard key={issue.id} intervention={issue} />
          ))}
        </div>
      )}

      <nav aria-label="Intervention pages" className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <div className="text-xs text-muted-foreground" aria-live="polite">
            {error ? 'Error' : isLoading ? 'Loading…' : `Showing ${issues.length ? offset + 1 : 0}–${issues.length ? offset + issues.length : 0} of ${issueTotal}`}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={isLoading || !!error || offset === 0} className="h-8 px-2" aria-label="Previous page">
              <ChevronLeft className="h-4 w-4" /> Prev
            </Button>
            <span className="text-xs font-mono">{error ? '- / -' : isLoading ? '…' : `${page} / ${totalPages}`}</span>
            <Button variant="outline" size="sm" onClick={() => setOffset(offset + limit)} disabled={isLoading || !!error || offset + limit >= issueTotal} className="h-8 px-2" aria-label="Next page">
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
      </nav>
    </div>
  );
}

function InventoryIssueCard({ issue }: { issue: InterventionIssue }) {
  const [open, setOpen] = useState(false);
  const { role } = usePersona();

  const state = issue.current_state || issue.evidence || {};
  const isP1 = issue.priority === 'P1';

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button type="button" className={cn(
          "w-full text-left border rounded-lg p-4 hover:border-primary/50 transition-colors bg-card cursor-pointer group relative overflow-hidden",
          isP1 ? "border-destructive/50" : "border-warning/50"
        )}>
          <div className={cn(
            "absolute top-0 right-0 w-1 h-full",
            isP1 ? "bg-destructive" : "bg-warning"
          )}></div>
          <div className="flex justify-between items-start mb-2">
            <div className="font-bold text-lg group-hover:text-primary transition-colors flex items-center gap-2">
              {isP1 && <AlertTriangle className="h-4 w-4 text-destructive" />}
              {issue.title}
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={isP1 ? "destructive" : "warning"} className="font-bold">
                {issue.priority}
              </Badge>
              <Badge variant="outline" className="uppercase font-mono">
                {issue.status}
              </Badge>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:gap-4 mt-4 text-sm font-mono">
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs uppercase">WMS</div>
              <div className="text-lg text-red-500">{state.wms_qty ?? '-'}</div>
            </div>
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs uppercase">ERP</div>
              <div className="text-lg text-red-500">{state.erp_qty ?? '-'}</div>
            </div>
            <div className="space-y-1">
              <div className="text-muted-foreground text-xs uppercase">Vision</div>
              <div className="text-lg text-red-500">{state.vision_qty ?? '-'}</div>
            </div>
          </div>
          
          {issue.linked_work && issue.linked_work.length > 0 && (
            <div className="mt-4 text-xs text-muted-foreground border-t pt-2">
              <span className="font-bold uppercase">Linked Work:</span> {issue.linked_work.map((w: any) => typeof w === 'object' ? (w.id || w.name || JSON.stringify(w)) : w).join(', ')}
            </div>
          )}
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{issue.title}</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Entity: {issue.entity_id} | Warehouse: {issue.warehouse_id}
          </p>
        </DialogHeader>
        
        <div className="mt-4"><CorrectionWorkflow item={issue} role={role} onSuccess={() => setOpen(false)} /></div>
      </DialogContent>
    </Dialog>
  );
}

function InterventionCard({ intervention }: { intervention: Intervention | InterventionIssue }) {
  const statusColors: Record<string, string> = {
    open: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
    investigating: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
    awaiting_approval: 'bg-purple-500/10 text-purple-500 border-purple-500/20',
    resolved: 'bg-green-500/10 text-green-500 border-green-500/20',
  };

  return (
    <Link href={`/workspace/interventions/${intervention.id}`}>
      <div className="border rounded-lg p-4 hover:border-primary/50 transition-colors bg-card cursor-pointer group relative overflow-hidden">
        {intervention.status === 'awaiting_approval' && (
           <div className="absolute top-0 right-0 w-1 h-full bg-purple-500"></div>
        )}
        <div className="flex justify-between items-start mb-2">
          <div className="font-bold text-lg group-hover:text-primary transition-colors break-all">{intervention.title}</div>
          <Badge variant="outline" className={cn("capitalize font-bold shrink-0", statusColors[intervention.status] || statusColors.open)}>
            {intervention.status === 'resolved' && intervention.evidence?.manual_closure ? 'Closed' : intervention.status.replace('_', ' ')}
          </Badge>
        </div>
        <div className="text-sm text-muted-foreground mb-4 line-clamp-2">{intervention.description}</div>
        <div className="flex justify-between items-center text-xs text-muted-foreground">
          <div className="flex gap-3 font-mono flex-wrap">
            <span className="break-all">ID: {intervention.entity_id}</span>
            <span>WH: {intervention.warehouse_id}</span>
          </div>
           {'updated_at' in intervention && <div>{new Date(intervention.updated_at).toLocaleString()}</div>}
        </div>
      </div>
    </Link>
  );
}
