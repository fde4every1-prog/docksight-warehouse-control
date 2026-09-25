import { useEffect, useState } from 'react';
import { useLocation } from 'wouter';
import { FulfillmentNav } from './components/FulfillmentNav';
import { useReplays, useReplay, useReplayOrders, formatDuration } from './use-replays';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ChevronRight, Search, Activity, History, AlertTriangle, CheckCircle, ChevronLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

export default function FulfillmentReplays({ runId: initialRunId }: { runId?: string }) {
  const [, setLocation] = useLocation();
  
  // 1. Fetch collection for the dropdown and to find default activeRunId
  const { data: replaysData, isLoading: replaysLoading, error: replaysError } = useReplays();

  const replays = replaysData?.items || [];
  const sortedReplays = [...replays].sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
  
  const activeRunId = initialRunId || (sortedReplays.length > 0 ? sortedReplays[0].run_id : undefined);

  // 2. Fetch specific run details
  const { data: activeRun, isLoading: runDetailLoading, isError: runDetailError, error: runError } = useReplay(activeRunId || '');

  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [warehouseFilter, setWarehouseFilter] = useState<string>('all');
  const limit = 25;

  // 3. Fetch orders for specific run, polling if preparing/running
  const { data: ordersData, isLoading: ordersLoading, isError: ordersError, error: ordersFetchError } = useReplayOrders(activeRunId || '', {
    limit,
    offset: page * limit,
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    warehouse: warehouseFilter !== 'all' ? warehouseFilter : undefined
  }, activeRun?.status);

  useEffect(() => {
    const target = ordersData?.unified_url || activeRun?.unified_url;
    if (target) setLocation(target, { replace: true });
  }, [activeRun?.unified_url, ordersData?.unified_url, setLocation]);

  if (replaysLoading || (activeRunId && runDetailLoading) || activeRun?.unified_url || ordersData?.unified_url) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="replays" />
        <Skeleton className="h-12 w-[300px]" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (replaysError) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="replays" />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Failed to load replays list</AlertTitle>
          <AlertDescription>{replaysError instanceof Error ? replaysError.message : 'Unknown error'}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (replays.length === 0) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="replays" />
        <Card>
          <CardContent className="p-12 text-center text-muted-foreground border-dashed">
            <History className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>No historical replays available.</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (runDetailError || !activeRun) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="replays" />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Error loading replay details</AlertTitle>
          <AlertDescription>
            {runError instanceof Error ? runError.message : 'Run not found or access denied.'}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const isRunning = activeRun.status === 'preparing' || activeRun.status === 'running';

  return (
    <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-950 min-h-full">
      <FulfillmentNav active="replays" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <History className="h-6 w-6 text-primary" />
            Historical Replays
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Isolated replay. Current orders and inventory are not changed.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Select Run:</span>
          <Select value={activeRun.run_id} onChange={(e) => { setLocation(`/fulfillment/replays/${e.target.value}`); setPage(0); }} className="w-[280px]">
              {sortedReplays.map(r => (
                <option key={r.run_id} value={r.run_id}>
                  {new Date(r.started_at).toLocaleString()} - {r.status.toUpperCase()}
                </option>
              ))}
          </Select>
        </div>
      </div>

      {isRunning ? (
         <Alert className="border-blue-500 bg-blue-50 dark:bg-blue-950/50 text-blue-900 dark:text-blue-200">
           <Activity className="h-4 w-4 text-blue-500 animate-pulse" />
           <AlertTitle>Run in Progress</AlertTitle>
           <AlertDescription>
             This replay is currently {activeRun.status}. Orders: {activeRun.processed_orders} / {activeRun.total_orders}.
           </AlertDescription>
         </Alert>
      ) : activeRun.status === 'failed' ? (
        <Alert variant="destructive">
           <AlertTriangle className="h-4 w-4" />
           <AlertTitle>Run Failed</AlertTitle>
           <AlertDescription>
             {activeRun.error || 'An error occurred during this run.'}
           </AlertDescription>
         </Alert>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
         <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Orders Processed</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {activeRun.processed_orders} / {activeRun.sample_size ?? activeRun.total_orders}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Completed: {activeRun.completed_orders}, Held: {activeRun.held_orders}, Rejected: {activeRun.rejected_orders}
              </p>
              {activeRun.is_full_7000 === false && (
                <Badge variant="secondary" className="mt-2 text-[10px]">PREFLIGHT SAMPLE</Badge>
              )}
            </CardContent>
         </Card>
         <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Avg. Cycle Time (Simulated)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {formatDuration(activeRun.metrics.simulated_average_cycle_seconds)}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                vs Benchmark: {formatDuration(activeRun.metrics.benchmark_average_cycle_seconds)}
              </p>
              <p className="text-xs text-muted-foreground mt-2">Completed orders only: simulated ready-to-ship time versus supplied carrier departure time.</p>
            </CardContent>
         </Card>
         <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">On-Time % (Simulated)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {activeRun.metrics.simulated_on_time_percent != null ? `${activeRun.metrics.simulated_on_time_percent.toFixed(1)}%` : '-'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                vs Benchmark: {activeRun.metrics.benchmark_on_time_percent != null ? `${activeRun.metrics.benchmark_on_time_percent.toFixed(1)}%` : '-'}
              </p>
              <p className="text-xs text-muted-foreground mt-2">Simulation: completed orders versus Core cutoff. Benchmark: supplied departures versus planned departure.</p>
            </CardContent>
         </Card>
         <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Data Period & Config</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-sm font-medium">{new Date(activeRun.source_period.start).toLocaleDateString()}</div>
              <div className="text-sm font-medium mb-2">to {new Date(activeRun.source_period.end).toLocaleDateString()}</div>
              <div className="text-xs text-muted-foreground">
                Task Duration: {activeRun.task_duration_seconds}s
              </div>
            </CardContent>
         </Card>
      </div>

      {(activeRun.checks?.length > 0 || activeRun.warnings?.length > 0) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Provenance & Checks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {activeRun.warnings?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-warning" /> Warnings</h4>
                <ul className="text-sm text-muted-foreground list-disc pl-5">
                  {activeRun.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}
            {activeRun.checks?.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold">Integrity Checks</h4>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {activeRun.checks.map((check, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm border p-2 rounded bg-muted/30">
                      {check.passed ? <CheckCircle className="h-4 w-4 text-green-500 mt-0.5 shrink-0" /> : <AlertTriangle className="h-4 w-4 text-red-500 mt-0.5 shrink-0" />}
                      <div>
                        <div className="font-medium">{check.name}</div>
                        <div className="text-xs text-muted-foreground">{check.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row justify-between gap-4 items-start sm:items-center">
            <CardTitle>Simulated Orders</CardTitle>
            <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
              <div className="relative flex-1 sm:w-48">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search orders..."
                  className="pl-8"
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(0); }}
                />
              </div>
              
              {activeRun.warehouses?.length > 0 && (
                <Select value={warehouseFilter} onChange={(e) => { setWarehouseFilter(e.target.value); setPage(0); }} className="w-[140px]">
                    <option value="all">All WH</option>
                    {activeRun.warehouses.map(w => (
                      <option key={w} value={w}>{w}</option>
                    ))}
                </Select>
              )}

              <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }} className="w-[140px]">
                  <option value="all">All Statuses</option>
                  <option value="completed">Completed</option>
                  <option value="held">Held</option>
                  <option value="rejected">Rejected</option>
                  <option value="active">Active</option>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {ordersError ? (
            <Alert variant="destructive" className="mb-4">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Error loading orders</AlertTitle>
              <AlertDescription>{ordersFetchError instanceof Error ? ordersFetchError.message : 'Failed to fetch orders for this replay.'}</AlertDescription>
            </Alert>
          ) : ordersLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !ordersData || ordersData.items.length === 0 ? (
            <div className="text-center p-8 text-muted-foreground border rounded-md border-dashed">
              <Search className="h-8 w-8 mx-auto mb-2 opacity-20" />
              <p>No orders match the current filters.</p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Source Order ID</TableHead>
                    <TableHead>SKU</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Simulated Finish</TableHead>
                    <TableHead>Cycle Time</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ordersData.items.map(order => (
                    <TableRow key={order.source_order_id} className="cursor-pointer hover:bg-muted/50" onClick={() => setLocation(`/fulfillment/replays/${activeRun.run_id}/orders/${encodeURIComponent(order.source_order_id)}`)}>
                      <TableCell className="font-mono text-xs font-medium">
                        {order.source_order_id}
                        {order.core_order_id && (
                          <div className="text-muted-foreground text-[10px]">Core: {order.core_order_id.slice(0,8)}</div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="text-xs font-medium">{order.sku}</div>
                        <div className="text-[10px] text-muted-foreground">Qty: {order.quantity} | {order.warehouse_id}</div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn(
                            "text-[10px] uppercase",
                            order.status === 'completed' && "border-green-500 text-green-600",
                            order.status === 'held' && "border-red-500 text-red-600",
                            order.status === 'rejected' && "border-slate-500 text-slate-600",
                            (order.status === 'active' || order.status === 'queued' || order.status === 'running') && "border-blue-500 text-blue-600",
                          )}>
                          {order.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={order.priority === 'urgent' ? 'destructive' : order.priority === 'high' ? 'warning' : 'secondary'} className="text-[10px] uppercase">
                          {order.priority}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {order.finished_at ? new Date(order.finished_at).toLocaleString() : '-'}
                      </TableCell>
                      <TableCell className="text-xs">
                        {formatDuration(order.cycle_time_seconds)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon">
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between mt-4">
                <div className="text-sm text-muted-foreground">
                  Showing {page * limit + 1} - {Math.min((page + 1) * limit, ordersData.total)} of {ordersData.total}
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>
                    <ChevronLeft className="h-4 w-4 mr-1" /> Prev
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={(page + 1) * limit >= ordersData.total}>
                    Next <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

    </div>
  );
}
