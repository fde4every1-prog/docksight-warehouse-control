import React, { useState, useEffect, useRef } from 'react';
import { useSearch } from 'wouter';
import { usePersona } from '@/contexts/PersonaContext';
import { 
  useMaintenanceModel, 
  useMaintenancePredictions 
} from '@/hooks/use-predictive-maintenance';
import { 
  Search, 
  AlertTriangle, 
  Info, 
  RefreshCw, 
  Activity,
  Bot,
  Filter
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Select } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { ModelSummaryCard } from './components/ModelSummaryCard';
import { RobotDetailDialog } from './components/RobotDetailDialog';

export default function PredictiveMaintenance() {
  const { role } = usePersona();
  const searchString = useSearch();
  const searchParams = new URLSearchParams(searchString);

  const [warehouse, setWarehouse] = useState(searchParams.get('warehouse') || 'all');
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [priority, setPriority] = useState(searchParams.get('priority') || 'all');
  const [page, setPage] = useState(1);
  const limit = 20;

  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null);

  const { data: model, isLoading: modelLoading, error: modelError, refetch: refetchModel } = useMaintenanceModel(role);

  // Reset page on filter changes
  useEffect(() => {
    setPage(1);
  }, [warehouse, search, priority]);

  const offset = (page - 1) * limit;
  const enabled = !!model?.available;
  const { data: list, isLoading: listLoading, error: listError, refetch: refetchList } = 
    useMaintenancePredictions(role, warehouse === 'all' ? '' : warehouse, search, priority === 'all' ? '' : priority, offset, enabled);

  const handleRefresh = () => {
    refetchModel();
    if (enabled) refetchList();
  };

  const total = list?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const items = list?.items || [];

  return (
    <div className="flex flex-col h-full min-w-0 p-6 overflow-y-auto space-y-6">
      <div className="flex flex-col gap-1 border-b pb-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            Predictive Maintenance Advisory
          </h1>
          <Button variant="outline" size="sm" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
        <p className="text-muted-foreground max-w-3xl">
          Experimental predictive advisory scores for fleet robots based on uploaded historical telemetry snapshots.
        </p>
        {model?.summary && (
          <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
            Observations through <strong>{model.summary.data_end}</strong>. Seven-day risk estimates only;
            data provenance is unverified. Scores do not change robot availability or scheduling.
          </p>
        )}
      </div>

      {modelError ? (
        <div className="flex flex-col items-center justify-center border border-destructive/20 bg-destructive/5 rounded-lg p-8 text-center space-y-4">
          <AlertTriangle className="h-8 w-8 text-destructive opacity-80" />
          <h3 className="font-bold text-destructive">Failed to load predictive model</h3>
          <p className="text-sm text-destructive/80 max-w-md">{modelError instanceof Error ? modelError.message : 'Unknown error'}</p>
          <Button variant="outline" size="sm" onClick={() => refetchModel()}>Try Again</Button>
        </div>
      ) : modelLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full rounded-xl" />
          <Skeleton className="h-[400px] w-full rounded-xl" />
        </div>
      ) : !model?.available ? (
        <div className="flex flex-col items-center justify-center border rounded-lg p-12 text-center bg-muted/20 space-y-4">
          <Info className="h-10 w-10 text-muted-foreground opacity-50" />
          <div className="space-y-1">
            <h3 className="text-lg font-medium text-foreground">Model Unavailable</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              {model?.message || 'A predictive maintenance model is currently not available, training, or failed to initialize.'}
            </p>
          </div>
          <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded-md border mt-2">
            A background task may be training the model. Real-time fallback is not available.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 flex flex-col space-y-4">
            
            <div className="flex flex-col sm:flex-row gap-3 border rounded-lg bg-card p-3 shadow-sm">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search robot ID or vendor..."
                  className="pl-9 h-9"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <Select 
                value={warehouse} 
                onChange={(e) => setWarehouse(e.target.value)} 
                className="w-full sm:w-[180px] h-9"
              >
                <option value="all">All Warehouses</option>
                {model.warehouses.map(w => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </Select>
              <Select 
                value={priority} 
                onChange={(e) => setPriority(e.target.value)} 
                className="w-full sm:w-[160px] h-9"
              >
                <option value="all">All Priorities</option>
                <option value="review">Review ({model.counts.review})</option>
                <option value="monitor">Monitor ({model.counts.monitor})</option>
                <option value="unavailable">Unavailable</option>
              </Select>
            </div>

            {listError ? (
               <div className="border border-destructive/20 bg-destructive/5 rounded-lg p-6 text-center text-sm text-destructive">
                 Failed to load predictions: {listError instanceof Error ? listError.message : 'Unknown error'}
               </div>
            ) : listLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-20 w-full rounded-lg" />
                <Skeleton className="h-20 w-full rounded-lg" />
                <Skeleton className="h-20 w-full rounded-lg" />
              </div>
            ) : items.length === 0 ? (
              <div className="border border-dashed rounded-lg p-12 text-center text-muted-foreground bg-muted/10">
                No predictions match your search criteria.
              </div>
            ) : (
              <div className="space-y-3">
                {items.map((item) => (
                  <Card 
                    key={item.robot_id} 
                    className={cn(
                      "cursor-pointer transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      item.priority === 'review' ? "border-destructive/30 bg-destructive/5" :
                      item.priority === 'monitor' ? "border-warning/30 bg-warning/5" : ""
                    )}
                    onClick={() => setSelectedRobotId(item.robot_id)}
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setSelectedRobotId(item.robot_id);
                      }
                    }}
                  >
                    <CardContent className="p-4 flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
                      <div className="flex items-start gap-3 min-w-0">
                        <div className="mt-1 flex-shrink-0">
                          <Bot className="h-5 w-5 text-muted-foreground" />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-bold text-base truncate">{item.robot_id}</h3>
                            {item.priority === 'review' && (
                              <Badge variant="destructive" className="uppercase text-[10px] tracking-wider">Review Suggested</Badge>
                            )}
                            {item.priority === 'monitor' && (
                              <Badge variant="warning" className="uppercase text-[10px] tracking-wider">Monitor</Badge>
                            )}
                            {item.priority === 'unavailable' && (
                              <Badge variant="secondary" className="uppercase text-[10px] tracking-wider text-muted-foreground">Unavailable</Badge>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1 flex items-center gap-2 flex-wrap">
                            <span className="font-mono bg-muted px-1.5 py-0.5 rounded">{item.warehouse_id}</span>
                            <span>•</span>
                            <span className="truncate">{item.vendor} {item.robot_type}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4 shrink-0 sm:text-right w-full sm:w-auto border-t sm:border-0 pt-3 sm:pt-0">
                        {item.eligible ? (
                          <div>
                            <div className="text-[10px] uppercase font-bold text-muted-foreground mb-0.5">Risk Score</div>
                            <div className={cn(
                              "font-mono text-lg font-bold",
                              item.priority === 'review' ? "text-destructive" :
                              item.priority === 'monitor' ? "text-warning" : "text-foreground"
                            )}>
                              {item.risk_probability != null ? (item.risk_probability * 100).toFixed(1) + '%' : '—'}
                            </div>
                          </div>
                        ) : (
                          <div className="text-xs text-muted-foreground max-w-[150px] italic">
                            {item.reason || 'Insufficient data'}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}

                <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                  <div className="text-sm text-muted-foreground">
                    Showing {(page - 1) * limit + 1}–{Math.min(page * limit, total)} of {total}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Prev</Button>
                    <span className="text-sm font-mono px-2">{page} / {totalPages}</span>
                    <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>Next</Button>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <ModelSummaryCard model={model} />
          </div>
        </div>
      )}

      {selectedRobotId && (
        <RobotDetailDialog 
          robotId={selectedRobotId} 
          role={role}
          open={!!selectedRobotId} 
          onOpenChange={(open) => !open && setSelectedRobotId(null)} 
        />
      )}
    </div>
  );
}
