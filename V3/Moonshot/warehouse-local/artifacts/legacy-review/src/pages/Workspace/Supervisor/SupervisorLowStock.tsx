import React, { useState, useEffect } from 'react';
import { usePersona } from '@/contexts/PersonaContext';
import { useLowStock, LowStockItem, InterventionIssue } from '@/hooks/use-personas';
import { Search, ChevronLeft, ChevronRight, AlertTriangle, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { CorrectionWorkflow } from '@/components/personas/CorrectionWorkflow';
import { Link } from 'wouter';

export function SupervisorLowStock() {
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [view, setView] = useState<'active' | 'closed'>('active');
  const limit = 10;

  const { role } = usePersona();
  const { data, isLoading, error, refetch } = useLowStock(role, limit, offset, search, view);

  const items = data?.items || [];
  const total = data?.pagination?.total || (error ? 0 : items.length);
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;

  useEffect(() => {
    if (data && !error && offset > 0 && offset >= total) {
      setOffset(Math.max(0, totalPages - 1) * limit);
    }
  }, [data, error, offset, total, totalPages]);

  return (
    <div className="flex flex-col h-full space-y-4 min-w-0">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-2">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold">Low Stock</h2>
          <Link href="/fulfillment/demand-forecasts" className="text-xs text-primary hover:underline">
            View All Demand Forecasts
          </Link>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row">
          <div className="flex rounded-md border p-0.5">
            <Button
              type="button"
              data-testid="button-low-stock-active"
              variant={view === 'active' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 flex-1 px-2 sm:flex-none"
              onClick={() => { setView('active'); setOffset(0); }}
            >
              Active
            </Button>
            <Button
              type="button"
              data-testid="button-low-stock-closed"
              variant={view === 'closed' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 flex-1 px-2 sm:flex-none"
              onClick={() => { setView('closed'); setOffset(0); }}
            >
              Closed
            </Button>
          </div>
          <div className="relative w-full sm:w-56 sm:shrink-0">
            <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
            <Input
              data-testid="input-search-low-stock"
              placeholder="Search SKUs..."
              aria-label={`Search ${view} low stock alerts`}
              className="pl-9 h-8 text-sm"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setOffset(0); }}
            />
          </div>
        </div>
      </div>

      {error ? (
        <div className="flex-1 flex flex-col items-center justify-center border border-destructive/20 bg-destructive/5 rounded-lg p-6 text-center space-y-4">
          <AlertTriangle className="h-8 w-8 text-destructive opacity-80" />
          <div className="space-y-1">
            <h3 className="font-bold text-destructive">Failed to load low stock</h3>
            <p className="text-sm text-destructive/80 text-balance max-w-sm">{error instanceof Error ? error.message : 'Unknown error occurred'}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>Try Again</Button>
        </div>
      ) : isLoading ? (
        <div className="space-y-4" role="status" aria-label="Loading low stock">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : items.length === 0 ? (
        <div className="border border-dashed rounded-lg p-8 text-center text-muted-foreground bg-muted/20">
          {search
            ? `No ${view} stock alerts match your search.`
            : view === 'closed' ? 'No closed low stock alerts.' : 'No active low stock alerts.'}
        </div>
      ) : (
        <div className="space-y-3 flex-1 overflow-y-auto pr-2">
          {items.map((item) => (
            <LowStockCard key={item.id} item={item} />
          ))}
        </div>
      )}

      <nav aria-label="Low stock pages" className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <div className="text-xs text-muted-foreground" aria-live="polite">
            {error ? 'Error' : isLoading ? 'Loading…' : `Showing ${items.length ? offset + 1 : 0}–${items.length ? offset + items.length : 0} of ${total}`}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={isLoading || !!error || offset === 0} className="h-8 px-2" aria-label="Previous page">
              <ChevronLeft className="h-4 w-4" /> Prev
            </Button>
            <span className="text-xs font-mono">{error ? '- / -' : isLoading ? '…' : `${page} / ${totalPages}`}</span>
            <Button variant="outline" size="sm" onClick={() => setOffset(offset + limit)} disabled={isLoading || !!error || offset + limit >= total} className="h-8 px-2" aria-label="Next page">
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
      </nav>
    </div>
  );
}

function LowStockCard({ item }: { item: LowStockItem }) {
  const isP1 = item.priority === 'P1';
  // Location-level replenishment alerts already describe this SKU's shortage.
  // Keep the aggregate alert only when there is no detailed alert to display.
  const alerts = item.interventions.length > 0
    ? item.interventions
    : item.alert ? [item.alert] : [];

  return (
    <div className={cn(
      "w-full border rounded-lg p-4 bg-card relative overflow-hidden flex flex-col gap-3",
      isP1 ? "border-destructive/50" : "border-warning/50"
    )} data-testid={`card-low-stock-group-${item.id}`}>
      <div className={cn(
        "absolute top-0 right-0 w-1 h-full",
        isP1 ? "bg-destructive" : "bg-warning"
      )}></div>
      
      <div className="flex justify-between items-start gap-3">
        <div className="font-bold text-lg flex items-center gap-2 break-all">
          <AlertTriangle className={cn("h-4 w-4 shrink-0", isP1 ? "text-destructive" : "text-warning")} />
          {item.sku}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={isP1 ? "destructive" : "warning"} className="font-bold">
            {item.priority}
          </Badge>
          <Badge variant="outline" className="font-mono">
            {item.warehouse_id}
          </Badge>
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="space-y-3">
          {alerts.map(issue => (
            <LowStockAlertCard
              key={issue.id}
              issue={issue}
              sku={item.sku}
              warehouse_id={item.warehouse_id}
              aggregate={!issue.evidence?.location && !issue.current_state?.location}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LowStockMetrics({ issue }: { issue: InterventionIssue }) {
  const state = issue.current_state || issue.evidence?.current_state || issue.evidence || {};
  const available = state.allocatable_qty ?? state.available;
  const threshold = state.threshold ?? state.forecast_7d ?? issue.evidence?.threshold ?? issue.evidence?.forecast_7d;
  const replenish = typeof available === 'number' && Number.isFinite(available)
    && typeof threshold === 'number' && Number.isFinite(threshold)
    ? Math.max(0, threshold - available)
    : null;

  return (
    <div className="grid grid-cols-2 gap-4 mt-4 text-sm font-mono">
      <div className="space-y-1">
        <div className="text-muted-foreground text-xs uppercase">Allocatable</div>
        <div className="text-lg">{available ?? '-'}</div>
      </div>
      <div className="space-y-1">
        <div className="text-muted-foreground text-xs uppercase">7-Day Demand Threshold</div>
        <div className="text-lg">{threshold ?? '-'}</div>
      </div>
      <div className="space-y-1">
        <div className="text-muted-foreground text-xs uppercase">30-Day Forecast</div>
        <div className="text-lg">{state.forecast_30d ?? issue.evidence?.forecast_30d ?? '-'}</div>
      </div>
      <div className="space-y-1" title="7-day demand minus allocatable stock, with a minimum of zero">
        <div className="text-muted-foreground text-xs uppercase">Replenish at least</div>
        <div className="text-lg font-semibold" data-testid={`text-replenish-quantity-${issue.id}`}>
          {replenish === null ? '-' : `${replenish} units`}
        </div>
      </div>
    </div>
  );
}

function LowStockAlertCard({ issue, aggregate, sku, warehouse_id }: { issue: InterventionIssue; aggregate: boolean; sku: string; warehouse_id: string; }) {
  const [open, setOpen] = useState(false);
  const { role } = usePersona();

  const state = issue.current_state || issue.evidence || {};
  const isP1 = issue.priority === 'P1';
  const isClosed = issue.status === 'resolved';

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button type="button" className={cn(
          "w-full text-left border rounded-lg p-4 hover:border-primary/50 transition-colors bg-card cursor-pointer group relative overflow-hidden",
          isClosed ? "border-green-600/30" : isP1 ? "border-destructive/50" : "border-warning/50"
        )} data-testid={`button-low-stock-alert-${issue.id}`}>
          <div className={cn(
            "absolute top-0 right-0 w-1 h-full",
            isClosed ? "bg-green-600" : isP1 ? "bg-destructive" : "bg-warning"
          )}></div>
          <div className="flex justify-between items-start gap-3 mb-2">
            <div className="font-bold text-lg group-hover:text-primary transition-colors flex items-center gap-2 min-w-0">
              {isClosed
                ? <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
                : <AlertTriangle className={cn("h-4 w-4 shrink-0", isP1 ? "text-destructive" : "text-warning")} />}
              <span className="break-words">{issue.title}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Badge variant={isP1 ? "destructive" : "warning"} className="font-bold">
                {issue.priority}
              </Badge>
              <Badge variant="outline" className="uppercase font-mono">
                {isClosed ? 'closed' : issue.status}
              </Badge>
            </div>
          </div>

          <LowStockMetrics issue={issue} />
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
            SKU: {sku} | Warehouse: {warehouse_id}
            {!aggregate && ` | Location: ${state.location || 'N/A'}`}
          </p>
        </DialogHeader>
        
        <LowStockMetrics issue={issue} />
        <div className="mt-4"><CorrectionWorkflow item={issue} role={role} onSuccess={() => setOpen(false)} /></div>
        <div className="mt-2 border-t pt-4">
          <Link 
            href={`/fulfillment/demand-forecasts?sku=${encodeURIComponent(sku)}&warehouse_id=${encodeURIComponent(warehouse_id)}`} 
            className="inline-flex items-center text-sm font-medium text-primary hover:underline group"
          >
            View Demand Forecast Details
            <ChevronRight className="ml-1 h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      </DialogContent>
    </Dialog>
  );
}
