import { useLocation } from 'wouter';
import { Activity, ServerCrash, PackageOpen } from 'lucide-react';
import { useFulfillmentState } from '@/hooks/use-fulfillment';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { FulfillmentNav } from './components/FulfillmentNav';

export default function FulfillmentDashboard() {
  const { data: state, isLoading, isError, error } = useFulfillmentState();
  const [, setLocation] = useLocation();

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="dashboard" />
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (isError || !state) {
    return (
      <div className="p-6 space-y-6">
        <FulfillmentNav active="dashboard" />
        <Alert variant="destructive">
          <ServerCrash className="h-4 w-4" />
          <AlertTitle>Connection Error</AlertTitle>
          <AlertDescription>
            {error instanceof Error ? error.message : 'Failed to connect to the Fulfillment API.'}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const { orders, tasks, server_time } = state;
  const recentOrders = [...orders]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, 10);

  const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'queued');
  const countStatus = (status: string) => orders.filter(o => o.status === status).length;
  const metrics = [
    { label: 'Total orders', value: state.total_orders ?? state.summary?.total ?? orders.length, note: 'Across the entire network' },
    { label: 'Rejected', value: state.summary?.rejected ?? countStatus('rejected'), note: 'Not accepted; see order for the reason' },
    { label: 'Completed', value: state.summary?.completed ?? countStatus('completed'), note: 'All required items fulfilled' },
    { label: 'On hold', value: state.summary?.on_hold ?? countStatus('held'), note: 'Includes held items in mixed orders' },
    { label: 'Cancelled', value: state.summary?.cancelled ?? countStatus('cancelled'), note: 'Fully cancelled orders' },
    { label: 'Partial fulfillment', value: state.summary?.partially_fulfilled ?? countStatus('partially_fulfilled'), note: 'Not counted as fully completed' },
    { label: 'Active orders', value: state.summary?.active ?? orders.filter(o => ['planned', 'queued', 'running', 'active'].includes(o.status)).length, note: `${activeTasks.length} queued or running tasks in current sample` },
    { label: 'Recovery required', value: state.summary?.recovery_required ?? countStatus('recovery_required'), note: 'Picked stock requires review' },
  ];

  return (
    <div className="p-6 space-y-6 bg-slate-50 dark:bg-slate-950 min-h-full">
      <p className="w-full text-left text-slate-500 dark:text-slate-400 font-mono text-sm mt-1 flex items-center justify-start gap-2">
        <Activity className="h-4 w-4" />
        LIVE SYNC: {new Date(server_time).toLocaleTimeString()}
      </p>

      <FulfillmentNav active="dashboard" />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {metrics.map(metric => (
          <Card key={metric.label} className="border-l-4 border-l-primary">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">{metric.label}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{metric.value}</div>
              <p className="text-xs text-muted-foreground mt-1">{metric.note}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6">
        <Card className="flex flex-col">
          <CardHeader className="border-b bg-muted/40">
            <div className="flex items-center justify-between">
              <CardTitle>Order Queue</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setLocation('/fulfillment/orders')}>View All</Button>
            </div>
            <CardDescription>Recent orders across the network, newest first</CardDescription>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-auto">
            {orders.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground font-mono text-sm">
                <PackageOpen className="h-8 w-8 mx-auto mb-3 opacity-20" />
                No orders in queue.
              </div>
            ) : (
              <div className="divide-y">
                {recentOrders.map((order) => (
                  <div key={order.id} className="p-4 flex flex-col gap-2 hover:bg-muted/50 transition-colors cursor-pointer" onClick={() => setLocation(`/fulfillment/orders/${order.id}`)}>
                    <div className="flex items-center justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-sm" title={order.id}>{order.id.slice(0, 12)}</span>
                          <Badge variant={order.priority === 'urgent' ? 'destructive' : order.priority === 'high' ? 'warning' : 'secondary'} className="text-[10px] uppercase">
                            {order.priority}
                          </Badge>
                          <Badge variant="outline" className={cn(
                            "text-[10px] uppercase",
                            ['completed', 'partially_fulfilled'].includes(order.status) && "border-green-500 text-green-600",
                            ['held', 'recovery_required', 'rejected'].includes(order.status) && "border-red-500 text-red-600",
                            order.status === 'cancelled' && "border-slate-500 text-slate-600",
                            ['running', 'queued', 'active'].includes(order.status) && "border-blue-500 text-blue-600",
                          )}>
                            {order.fulfillment_status || order.status.replace('_', ' ')}
                          </Badge>
                        </div>
                        <div className="text-xs text-muted-foreground flex items-center gap-3">
                          <span>{order.lines.length} items</span>
                          <span>Cutoff: {new Date(order.ship_by).toLocaleString()} {Intl.DateTimeFormat().resolvedOptions().timeZone}</span>
                        </div>
                      </div>
                    </div>
                    
                    {order.sub_orders && order.sub_orders.length > 0 && (
                      <div className="flex gap-1 flex-wrap mt-1">
                        {order.sub_orders.map(so => (
                          <div key={so.id} className={cn(
                            "text-[10px] px-1.5 py-0.5 rounded border font-mono flex items-center gap-1",
                            so.status === 'completed' && "bg-green-50 text-green-700 border-green-200",
                            so.status === 'cancelled' && "bg-slate-50 text-slate-700 border-slate-200",
                            so.status === 'held' && "bg-red-50 text-red-700 border-red-200",
                            ['running', 'queued'].includes(so.status) && "bg-blue-50 text-blue-700 border-blue-200",
                          )}>
                            {so.sku} ({so.fulfillment_status || so.status.replace('_', ' ')})
                            {' · '}
                            {so.warehouses?.length
                              ? so.warehouses.join(', ')
                              : [...new Set((so.allocations ?? []).map(allocation => allocation.warehouse_id).filter(Boolean))].join(', ') || 'location unknown'}
                            {so.overdue && <span className="font-semibold text-red-600">Overdue</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
