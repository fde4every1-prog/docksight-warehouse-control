import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useRoute, useLocation } from 'wouter';
import { useOrder, useOrderAction, useFulfillmentState, type SubOrder, type Task } from '@/hooks/use-fulfillment';
import { usePersona } from '@/contexts/PersonaContext';
import { FulfillmentNav } from './components/FulfillmentNav';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Play, RotateCcw, XCircle, ArrowLeft, Package, Clock, ShieldAlert, CheckCircle2, History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Progress } from '@/components/ui/progress';

const CountdownClockContext = createContext<number | null>(null);

function hasValidRunningWindow(task: Task) {
  if (task.status !== 'running' || !task.started_at || !task.due_at) return false;
  const start = new Date(task.started_at).getTime();
  const due = new Date(task.due_at).getTime();
  return Number.isFinite(start) && Number.isFinite(due) && due > start;
}

function CountdownClockProvider({
  tasks,
  serverTime,
  children,
}: {
  tasks: Task[];
  serverTime?: string;
  children: ReactNode;
}) {
  const [currentServerTime, setCurrentServerTime] = useState(Date.now);
  const enabled = useMemo(() => tasks.some(hasValidRunningWindow), [tasks]);

  useEffect(() => {
    if (!enabled) return;

    const localNow = Date.now();
    const parsedServerTime = serverTime ? new Date(serverTime).getTime() : Number.NaN;
    const serverNow = Number.isFinite(parsedServerTime) ? parsedServerTime : localNow;
    const offset = localNow - serverNow;
    const updateClock = () => setCurrentServerTime(Date.now() - offset);
    updateClock();
    const interval = setInterval(updateClock, 100);
    return () => clearInterval(interval);
  }, [enabled, serverTime]);

  return (
    <CountdownClockContext.Provider value={currentServerTime}>
      {children}
    </CountdownClockContext.Provider>
  );
}

function RunningTaskCountdown({ task }: { task: Task }) {
  const currentServerTime = useContext(CountdownClockContext) ?? Date.now();
  const start = task.started_at ? new Date(task.started_at).getTime() : Number.NaN;
  const due = task.due_at ? new Date(task.due_at).getTime() : Number.NaN;
  const totalMs = due - start;
  const hasValidWindow = Number.isFinite(totalMs) && totalMs > 0;
  if (!hasValidWindow) {
    return (
      <span className="text-xs text-muted-foreground">
        Waiting for timing
      </span>
    );
  }

  const progress = Math.min(100, Math.max(0, ((currentServerTime - start) / totalMs) * 100));
  const remaining = Math.max(0, Math.ceil((due - currentServerTime) / 1000));

  return (
    <div className="flex items-center gap-3 w-48">
      <Progress value={progress} className="h-2 flex-1" />
      <span className="text-xs font-mono font-bold text-blue-600 dark:text-blue-400 w-8">{remaining}s</span>
    </div>
  );
}

function TaskCountdown({ task }: { task: Task }) {
  const status: string = task.status;

  if (status === 'completed') {
    return <Badge className="bg-green-500 hover:bg-green-600">Completed</Badge>;
  }
  if (status === 'failed' || status === 'cancelled') {
    return <Badge variant="destructive">{status}</Badge>;
  }
  if (status === 'pending' || status === 'queued' || status === 'paused') {
    return <Badge variant="secondary" className="uppercase text-[10px]">{status}</Badge>;
  }

  return <RunningTaskCountdown task={task} />;
}

function unique(values: Array<string | undefined | null>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function subOrderLocations(subOrder: SubOrder) {
  const allocations = subOrder.allocations ?? [];
  return {
    warehouses: subOrder.warehouses?.length
      ? subOrder.warehouses
      : unique(allocations.map(allocation => allocation.warehouse_id)),
    zones: subOrder.zones?.length
      ? subOrder.zones
      : unique(allocations.map(allocation => allocation.zone)),
  };
}

function locationLabel(values: string[]) {
  return values.length ? values.join(', ') : 'Unknown';
}

export default function FulfillmentOrderDetails() {
  const [, params] = useRoute('/fulfillment/orders/:id');
  const [, setLocation] = useLocation();
  const id = params?.id || '';
  const { role } = usePersona();
  
  const { data: order, isLoading } = useOrder(id);
  const { data: state } = useFulfillmentState();
  const action = useOrderAction();

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        {role !== 'supervisor' && <FulfillmentNav active="orders" />}
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="p-6 space-y-6">
        {role !== 'supervisor' && <FulfillmentNav active="orders" />}
        <Alert variant="destructive">
          <AlertTitle>Order Not Found</AlertTitle>
          <AlertDescription>Could not retrieve order {id}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {role !== 'supervisor' && <FulfillmentNav active="orders" />}
      
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" aria-label="Back to workspace" onClick={() => setLocation(role === 'supervisor' ? '/fulfillment/orders' : '/workspace/fleet')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-2xl font-bold font-mono tracking-tight">{order.id}</h1>
          <Badge variant={order.priority === 'urgent' ? 'destructive' : order.priority === 'high' ? 'warning' : 'secondary'} className="uppercase">
            {order.priority}
          </Badge>
          <Badge variant="outline" className={cn(
            "uppercase font-bold tracking-widest",
            order.status === 'completed' && "border-green-500 text-green-600",
            order.status === 'partially_fulfilled' && "border-amber-500 text-amber-700",
            ['held', 'recovery_required', 'rejected'].includes(order.status) && "border-red-500 text-red-600",
            ['running', 'queued', 'active'].includes(order.status) && "border-blue-500 text-blue-600",
            order.status === 'cancelled' && "border-slate-500 text-slate-600"
          )}>
            {order.fulfillment_status || order.status}
          </Badge>
        </div>
        
        {role === 'supervisor' && !['completed', 'cancelled', 'recovery_required', 'rejected'].includes(order.status) && (
          <div className="flex gap-2">
            <Button
              variant="outline"
              data-testid="button-trigger-planner"
              title="Recheck inventory and assign eligible resources to waiting tasks for this order."
              onClick={() => action.mutate({ id, action: 'retry' })}
              disabled={action.isPending}
            >
              <RotateCcw className={cn("mr-2 h-4 w-4", action.isPending && action.variables?.action === 'retry' && "animate-spin")} />
              {action.isPending && action.variables?.action === 'retry' ? 'Planning…' : 'Trigger Planner'}
            </Button>
            {['planned'].includes(order.status) && (
              <Button onClick={() => action.mutate({ id, action: 'start' })} disabled={action.isPending} className="bg-blue-600 hover:bg-blue-700 text-white">
                <Play className="mr-2 h-4 w-4" /> Release & Start
              </Button>
            )}
            <Button variant="destructive" onClick={() => {
              if (window.confirm('Cancel remaining work? Unpicked stock will be released. Already-picked stock will stay in recovery and will not be returned to shelves automatically.')) {
                action.mutate({ id, action: 'cancel' });
              }
            }} disabled={action.isPending}>
              <XCircle className="mr-2 h-4 w-4" /> Cancel
            </Button>
          </div>
        )}
      </div>

      {action.isError && (
        <Alert variant="destructive">
          <AlertTitle>Order action failed</AlertTitle>
          <AlertDescription>{action.error.message}</AlertDescription>
        </Alert>
      )}
      {action.isSuccess && action.variables?.action === 'retry' && action.variables.id === id && (
        <Alert role="status">
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>Planner check complete</AlertTitle>
          <AlertDescription>
            Inventory and task assignments were rechecked for this order. Eligible work can proceed;
            any remaining stock, resource, or safety blocks are shown below.
          </AlertDescription>
        </Alert>
      )}
      {order.issues && order.issues.length > 0 && (
        <Alert variant="destructive" className="bg-red-50 border-red-200 text-red-900 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900">
          <ShieldAlert className="h-4 w-4 text-red-600 dark:text-red-400" />
          <AlertTitle>Operational exceptions</AlertTitle>
          <AlertDescription className="mt-2 space-y-1">
            {order.issues.map((issue, i) => (
              <div key={i}>• {issue}</div>
            ))}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid md:grid-cols-3 gap-6">
        <div className="md:col-span-2 space-y-6">
          <Card>
            <CardHeader className="border-b bg-muted/20">
              <CardTitle className="text-lg flex items-center gap-2">
                <Package className="h-5 w-5 text-muted-foreground" /> Order Lines
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y">
                {order.sub_orders && order.sub_orders.length > 0 ? (
                  order.sub_orders.map((so) => {
                    const locations = subOrderLocations(so);
                    return (
                    <div key={so.id} className="p-4 flex flex-col gap-2 hover:bg-muted/50 transition-colors">
                      <div className="flex items-center justify-between">
                        <div className="flex flex-col">
                          <span className="font-mono font-bold text-sm">{so.sku}</span>
                          <span className="text-xs text-muted-foreground">Qty: {so.quantity}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-xs text-muted-foreground text-right flex flex-col">
                            <span data-testid={`text-suborder-warehouses-${so.id}`}>WH: {locationLabel(locations.warehouses)}</span>
                            <span data-testid={`text-suborder-zones-${so.id}`}>Zones: {locationLabel(locations.zones)}</span>
                            <span>Cutoff: {new Date(so.cutoff_at).toLocaleString()} {Intl.DateTimeFormat().resolvedOptions().timeZone}</span>
                             {so.overdue && <span className="font-semibold text-red-600">Overdue</span>}
                          </div>
                          <Badge variant="outline" className={cn(
                            "uppercase text-[10px] w-24 justify-center",
                            so.status === 'completed' && "border-green-500 text-green-600",
                            so.status === 'held' && "border-red-500 text-red-600",
                            ['running', 'queued'].includes(so.status) && "border-blue-500 text-blue-600",
                            so.status === 'cancelled' && "border-slate-500 text-slate-600"
                          )}>
                            {so.fulfillment_status || so.status.replace('_', ' ')}
                          </Badge>
                        </div>
                      </div>
                      
                      {so.allocations && so.allocations.length > 0 && (
                        <div className="mt-2 pl-4 border-l-2 border-muted space-y-1">
                          {so.allocations.map((alloc: any, idx: number) => (
                            <div key={idx} className="text-[10px] font-mono flex items-center gap-4 bg-card border rounded px-2 py-1">
                              <span className="font-bold text-muted-foreground">LOC:</span> {alloc.location} (Zone {alloc.zone})
                              <span className="font-bold text-muted-foreground ml-2">QTY:</span> {alloc.quantity}
                              <span className="font-bold text-muted-foreground ml-2">RSVD:</span> <span className="text-orange-600">{alloc.reserved_qty}</span>
                              <span className="font-bold text-muted-foreground ml-2">PKD:</span> <span className="text-green-600">{alloc.picked_qty}</span>
                              {alloc.wip_stage && <span className="ml-auto uppercase px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">{alloc.wip_stage}</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      {so.fulfillment_history?.length ? (
                        <div className="mt-2 rounded border bg-muted/20 p-3" data-testid={`list-suborder-history-${so.id}`}>
                          <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                            Fulfillment history
                          </div>
                          <ol className="space-y-1">
                            {so.fulfillment_history.map((entry, index) => (
                              <li key={`${entry.at}-${entry.status}-${index}`} className="flex flex-wrap justify-between gap-2 text-xs">
                                <span>{entry.status}</span>
                                <time className="text-muted-foreground">{new Date(entry.at).toLocaleString()}</time>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ) : null}
                    </div>
                    );
                  })
                ) : (
                  order.lines.map((line, i) => (
                    <div key={i} className="p-4 flex items-center justify-between hover:bg-muted/50 transition-colors">
                      <div className="flex flex-col">
                        <span className="font-mono font-bold text-sm">{line.sku}</span>
                        <span className="text-xs text-muted-foreground">Qty: {line.quantity}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b bg-muted/20">
              <CardTitle className="text-lg flex items-center gap-2">
                <History className="h-5 w-5 text-muted-foreground" /> Execution Tasks
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {!order.tasks || order.tasks.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground font-mono text-sm">
                  No tasks generated yet.
                </div>
              ) : (
                <CountdownClockProvider tasks={order.tasks} serverTime={state?.server_time}>
                  <div className="divide-y">
                    {order.tasks.map(task => (
                      <div key={task.id} className="p-4 flex items-center justify-between">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="font-mono">{task.stage}</Badge>
                            <span className="text-xs text-muted-foreground font-mono">{task.id}</span>
                          </div>
                          {task.resource_id && (
                            <div className="text-xs text-muted-foreground">
                              Assigned to: <span className="font-mono text-foreground">{task.resource_id}</span> ({task.resource_type})
                            </div>
                          )}
                        </div>
                        <div className="space-y-1">
                          <TaskCountdown task={task} />
                          {task.wait_reason && <p className="max-w-sm text-xs text-amber-700">{task.wait_reason}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                </CountdownClockProvider>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader className="border-b bg-muted/20">
              <CardTitle className="text-lg">Context</CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              {order.source_order_id && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Source Reference</div>
                  <div className="font-mono text-sm font-medium">
                    {order.source_order_id}
                  </div>
                  {order.order_source && (
                    <div className="text-xs text-muted-foreground mt-1">{order.order_source}</div>
                  )}
                </div>
              )}
              {order.order_service && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Order Service</div>
                  <div className="font-mono text-sm">{order.order_service}</div>
                </div>
              )}
              <div>
                <div className="text-xs text-muted-foreground mb-1">Warehouse</div>
                <div className="font-mono text-sm" data-testid="text-order-warehouses">
                  {locationLabel(order.warehouses?.length
                    ? order.warehouses
                    : unique((order.sub_orders ?? []).flatMap(subOrder => subOrderLocations(subOrder).warehouses)))}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Zones</div>
                <div className="font-mono text-sm" data-testid="text-order-zones">
                  {locationLabel(order.zones?.length
                    ? order.zones
                    : unique((order.sub_orders ?? []).flatMap(subOrder => subOrderLocations(subOrder).zones)))}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Created At</div>
                <div className="text-sm flex items-center gap-2">
                  <Clock className="h-3 w-3 text-muted-foreground" />
                  {new Date(order.created_at).toLocaleString()}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Ship By</div>
                <div className="text-sm font-semibold flex items-center gap-2 text-orange-600 dark:text-orange-400">
                  <Clock className="h-3 w-3" />
                  {new Date(order.ship_by).toLocaleString()}
                </div>
              </div>
              {order.plan && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Plan Summary</div>
                  <pre className="text-[10px] bg-muted p-2 rounded overflow-x-auto">
                    {JSON.stringify(order.plan, null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b bg-muted/20">
              <CardTitle className="text-lg">Event History</CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <div className="space-y-4 relative before:absolute before:inset-0 before:ml-2 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-300 before:to-transparent">
                {order.events?.map((ev, i) => (
                  <div key={i} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    <div className="flex items-center justify-center w-5 h-5 rounded-full border border-white bg-slate-300 group-[.is-active]:bg-primary text-slate-500 group-[.is-active]:text-white shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2">
                      {i === 0 ? <CheckCircle2 className="h-3 w-3" /> : <div className="h-1.5 w-1.5 rounded-full bg-current" />}
                    </div>
                    <div className="w-[calc(100%-2rem)] md:w-[calc(50%-1.5rem)] p-3 rounded border bg-card shadow-sm">
                      <div className="flex items-center justify-between mb-1">
                        <time className="text-[10px] font-mono text-muted-foreground">{new Date(ev.at).toLocaleTimeString()}</time>
                      </div>
                      <div className="text-xs">{ev.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="border-b bg-muted/20">
              <CardTitle className="text-lg">Fulfillment Progress</CardTitle>
              <CardDescription data-testid="text-order-fulfillment-status">
                {order.fulfillment_status || order.status}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-4">
              {order.fulfillment_history?.length ? (
                <ol className="space-y-3">
                  {order.fulfillment_history.map((entry, index) => (
                    <li key={`${entry.at}-${entry.status}-${index}`} className="border-l-2 border-primary/30 pl-3">
                      <div className="text-sm font-medium">{entry.status}</div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(entry.at).toLocaleString()}
                        {entry.sub_order_id ? ` · ${entry.sub_order_id}` : ''}
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-muted-foreground">No fulfillment progress history recorded yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
