import { useLocation } from 'wouter';
import { useEffect } from 'react';
import { useReplay, useReplayOrderDetail, formatDuration } from './use-replays';
import { FulfillmentNav } from './components/FulfillmentNav';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowLeft, Activity, Box, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

export default function FulfillmentReplayDetails({ runId, orderId }: { runId: string, orderId: string }) {
  const [, setLocation] = useLocation();
  
  // We need the run status to know if we should poll the detail endpoint
  const { data: run } = useReplay(runId);
  const { data, isLoading, isError, error } = useReplayOrderDetail(runId, orderId, run?.status);
  useEffect(() => {
    if (data?.unified_url) setLocation(data.unified_url, { replace: true });
  }, [data?.unified_url, setLocation]);

  if (isLoading || data?.unified_url) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="replays" />
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="replays" />
        <Button variant="ghost" onClick={() => setLocation(`/fulfillment/replays/${encodeURIComponent(runId)}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Replay
        </Button>
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Error loading order details</AlertTitle>
          <AlertDescription>{error instanceof Error ? error.message : 'Failed to load order details for this replay.'}</AlertDescription>
        </Alert>
      </div>
    );
  }

  const { order, tasks, allocations, events } = data;

  return (
    <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-950 min-h-full">
      <FulfillmentNav active="replays" />
      
      <Button variant="ghost" onClick={() => setLocation(`/fulfillment/replays/${encodeURIComponent(runId)}`)} className="-ml-4 mb-2">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Replay Orders
      </Button>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2 font-mono">
            {order.source_order_id}
            <Badge variant="outline" className={cn(
                "uppercase text-xs",
                order.status === 'completed' && "border-green-500 text-green-600",
                order.status === 'held' && "border-red-500 text-red-600",
                order.status === 'rejected' && "border-slate-500 text-slate-600",
                (order.status === 'active' || order.status === 'queued' || order.status === 'running') && "border-blue-500 text-blue-600",
              )}>
              {order.status}
            </Badge>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Simulated Replay Record • Core ID: {order.core_order_id || 'N/A'}
          </p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader>
             <CardTitle className="text-lg">Simulated Fulfillment</CardTitle>
             <CardDescription>DockSight execution results</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
             <div className="grid grid-cols-2 gap-4">
               <div>
                 <div className="text-xs text-muted-foreground mb-1">Status</div>
                 <div className="font-medium capitalize">{order.status}</div>
                 {order.reason && <div className="text-xs text-destructive mt-1">{order.reason}</div>}
               </div>
               <div>
                 <div className="text-xs text-muted-foreground mb-1">Simulated Completion</div>
                 <div className="font-medium text-sm">
                   {order.finished_at ? new Date(order.finished_at).toLocaleString() : 'Not completed'}
                 </div>
               </div>
               <div>
                 <div className="text-xs text-muted-foreground mb-1">Cycle Time</div>
                 <div className="font-medium text-sm">
                   {formatDuration(order.cycle_time_seconds)}
                 </div>
               </div>
               <div>
                 <div className="text-xs text-muted-foreground mb-1">Core Cutoff</div>
                 <div className="font-medium text-sm">
                   {order.cutoff ? new Date(order.cutoff).toLocaleString() : '-'}
                 </div>
               </div>
             </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-100/50 dark:bg-slate-900/50 border-dashed">
          <CardHeader>
             <CardTitle className="text-lg">Reference Benchmark</CardTitle>
             <CardDescription>Supplied baseline, not actual execution</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
             <div className="grid grid-cols-2 gap-4">
               <div>
                 <div className="text-xs text-muted-foreground mb-1">Benchmark Actual Departure</div>
                 <div className="font-medium text-sm">
                   {order.benchmark_actual_departure ? new Date(order.benchmark_actual_departure).toLocaleString() : 'No physical shipment data'}
                 </div>
                 <div className="text-[10px] text-muted-foreground mt-1">Not equivalent to simulated ready-to-ship</div>
               </div>
               <div>
                 <div className="text-xs text-muted-foreground mb-1">Reference Cycle Time</div>
                 <div className="font-medium text-sm">
                   {formatDuration(order.benchmark_cycle_time_seconds)}
                 </div>
               </div>
             </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Allocations</CardTitle>
          <CardDescription>Stock consumed or reserved during simulation</CardDescription>
        </CardHeader>
        <CardContent>
           {allocations && allocations.length > 0 ? (
             <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Warehouse</TableHead>
                    <TableHead>Zone</TableHead>
                    <TableHead>SKU</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {allocations.map((alloc: any, idx: number) => (
                    <TableRow key={idx}>
                      <TableCell className="text-xs">{alloc.warehouse_id || '-'}</TableCell>
                      <TableCell className="text-xs">{alloc.zone || '-'}</TableCell>
                      <TableCell className="text-xs font-mono">{alloc.sku || '-'}</TableCell>
                      <TableCell className="text-xs text-right">{alloc.quantity || alloc.qty || '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
             </Table>
           ) : (
             <div className="text-center p-8 text-muted-foreground border rounded border-dashed">
               <Box className="h-8 w-8 mx-auto mb-2 opacity-20" />
               <p>No allocations recorded for this order in the simulation.</p>
             </div>
           )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Simulated Stages & Resources</CardTitle>
          <CardDescription>Tasks generated during this simulation run</CardDescription>
        </CardHeader>
        <CardContent>
           {tasks && tasks.length > 0 ? (
             <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Resource</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Completed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tasks.map((task: any, idx: number) => (
                    <TableRow key={idx}>
                      <TableCell className="font-medium capitalize">{task.stage}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-[10px] uppercase">{task.status}</Badge>
                      </TableCell>
                      <TableCell className="text-xs font-mono">{task.resource_id || '-'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{task.started_at ? new Date(task.started_at).toLocaleTimeString() : '-'}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{task.completed_at ? new Date(task.completed_at).toLocaleTimeString() : '-'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
             </Table>
           ) : (
             <div className="text-center p-8 text-muted-foreground border rounded border-dashed">
               <Activity className="h-8 w-8 mx-auto mb-2 opacity-20" />
               <p>No tasks recorded for this order in the simulation.</p>
             </div>
           )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Simulation Events</CardTitle>
          <CardDescription>Event log for isolated replay environment</CardDescription>
        </CardHeader>
        <CardContent>
           {events && events.length > 0 ? (
             <div className="space-y-4">
               {events.map((ev: any, idx: number) => (
                 <div key={idx} className="flex gap-4 items-start text-sm">
                   <div className="text-xs text-muted-foreground font-mono whitespace-nowrap min-w-[140px]">
                     {ev.at ? new Date(ev.at).toLocaleString() : '-'}
                   </div>
                   <div className="flex-1">
                     <span className="text-muted-foreground">{ev.message || '-'}</span>
                   </div>
                 </div>
               ))}
             </div>
           ) : (
             <div className="text-center p-4 text-muted-foreground text-sm">No events logged.</div>
           )}
        </CardContent>
      </Card>

    </div>
  );
}
