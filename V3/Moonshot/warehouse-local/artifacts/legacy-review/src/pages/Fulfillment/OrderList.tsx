import { useLocation } from 'wouter';
import { useEffect, useState } from 'react';
import { useAssignTasks, useDownloadOrdersCsv, useOrders, type Order, type SubOrder } from '@/hooks/use-fulfillment';
import { usePersona } from '@/contexts/PersonaContext';
import { FulfillmentNav } from './components/FulfillmentNav';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { ChevronRight, PackageSearch, ArrowLeft, Download, PlayCircle } from 'lucide-react';

function unique(values: Array<string | undefined | null>) {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function allocationLocations(allocations?: any[]) {
  return {
    warehouses: unique((allocations ?? []).map(allocation => allocation.warehouse_id)),
    zones: unique((allocations ?? []).map(allocation => allocation.zone)),
  };
}

function subOrderLocations(subOrder: SubOrder) {
  const fallback = allocationLocations(subOrder.allocations);
  return {
    warehouses: subOrder.warehouses?.length ? subOrder.warehouses : fallback.warehouses,
    zones: subOrder.zones?.length ? subOrder.zones : fallback.zones,
  };
}

function orderLocations(order: Order) {
  const subOrderValues = (order.sub_orders ?? []).map(subOrderLocations);
  return {
    warehouses: order.warehouses?.length ? order.warehouses : unique(subOrderValues.flatMap(value => value.warehouses)),
    zones: order.zones?.length ? order.zones : unique(subOrderValues.flatMap(value => value.zones)),
  };
}

function locationLabel(values: string[]) {
  return values.length ? values.join(', ') : 'Unknown';
}

export default function FulfillmentOrderList() {
  const [, setLocation] = useLocation();
  const [search, setSearch] = useState(() => new URLSearchParams(window.location.search).get('search') ?? '');
  const [query, setQuery] = useState(search);
  const [status, setStatus] = useState(() => new URLSearchParams(window.location.search).get('status') ?? '');
  const [warehouse, setWarehouse] = useState(() => new URLSearchParams(window.location.search).get('warehouse') ?? '');
  const [offset, setOffset] = useState(0);
  const limit = 25;
  useEffect(() => {
    const timer = setTimeout(() => { setQuery(search.trim()); setOffset(0); }, 300);
    return () => clearTimeout(timer);
  }, [search]);
  const { data, isLoading, error, refetch } = useOrders({ search: query, status, warehouse, limit, offset });
  const { role } = usePersona();
  const assignTasks = useAssignTasks(role);
  const downloadCsv = useDownloadOrdersCsv(role);

  if (isLoading && !query && !status && !warehouse && offset === 0 && !search) {
    return (
      <div className="p-6 space-y-6">
        {role === 'supervisor' ? (
          <Button variant="ghost" className="mb-4" onClick={() => setLocation('/fulfillment')}>
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to Order Fulfillment
          </Button>
        ) : (
          <FulfillmentNav active="orders" />
        )}
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  const orders = data?.items ?? [];

  return (
    <div className="p-6 space-y-6">
      {role === 'supervisor' ? (
        <Button variant="ghost" className="mb-4" onClick={() => setLocation('/fulfillment')}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Order Fulfillment
        </Button>
      ) : (
        <FulfillmentNav active="orders" />
      )}
      
      <Card>
        <CardHeader>
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <CardTitle>Network Orders {data ? `(${data.total.toLocaleString()})` : ''}</CardTitle>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => downloadCsv.mutate()}
                disabled={downloadCsv.isPending}
                data-testid="button-download-orders-csv"
              >
                <Download className="mr-2 h-4 w-4" />
                {downloadCsv.isPending ? 'Preparing CSV…' : 'Download all orders CSV'}
              </Button>
              <Button
                onClick={() => assignTasks.mutate()}
                disabled={assignTasks.isPending}
                data-testid="button-assign-tasks"
              >
                <PlayCircle className="mr-2 h-4 w-4" />
                {assignTasks.isPending ? 'Assigning…' : 'Assign Tasks'}
              </Button>
            </div>
          </div>
          {(assignTasks.isError || downloadCsv.isError) && (
            <p className="text-sm text-destructive" role="alert" data-testid="status-orders-action-error">
              {(assignTasks.error ?? downloadCsv.error)?.message}
            </p>
          )}
          {assignTasks.data && (
            <p className="text-sm text-muted-foreground" data-testid="status-assign-tasks-result">
              Assigned {assignTasks.data.assigned}, resumed {assignTasks.data.resumed}, rechecked {assignTasks.data.rechecked};
              {' '}{assignTasks.data.still_waiting} still waiting. Ran {new Date(assignTasks.data.ran_at).toLocaleString()}.
              {' '}Next automatic pass{' '}
              {new Date(assignTasks.data.next_assignment_at).toLocaleString()}.
            </p>
          )}
          {downloadCsv.data && (
            <p className="text-sm text-muted-foreground" data-testid="status-download-orders-result">
              Downloaded {downloadCsv.data}.
            </p>
          )}
        </CardHeader>
        <CardContent>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <Input aria-label="Search orders" data-testid="input-order-search" placeholder="Search order ID, source ID or SKU" value={search} onChange={event => setSearch(event.target.value)} />
            <select aria-label="Order status" data-testid="select-order-status" className="h-10 rounded-md border bg-background px-3 text-sm" value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }}>
              <option value="">All statuses</option>
              {['planned', 'queued', 'running', 'active', 'completed', 'held', 'rejected', 'cancelled', 'partially_fulfilled', 'recovery_required'].map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
            </select>
            <Input aria-label="Warehouse" data-testid="input-order-warehouse" placeholder="Warehouse ID" value={warehouse} onChange={event => { setWarehouse(event.target.value); setOffset(0); }} />
          </div>
          {error && <Alert variant="destructive" className="mb-4" data-testid="error-orders"><AlertDescription>{error instanceof Error ? error.message : 'Unable to load orders.'} <Button variant="outline" size="sm" data-testid="button-retry-orders" onClick={() => refetch()}>Retry</Button></AlertDescription></Alert>}
          {isLoading && <p role="status" data-testid="status-orders-loading">Loading orders…</p>}
          {orders.length === 0 ? (
            <div className="text-center p-12 text-muted-foreground border rounded-md border-dashed">
              <PackageSearch className="h-12 w-12 mx-auto mb-4 opacity-20" />
              <p>{error ? 'Orders unavailable.' : isLoading ? 'Loading…' : 'No orders match these filters.'}</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Order ID</TableHead>
                   <TableHead>Source / Service</TableHead>
                  <TableHead>Locations</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Items</TableHead>
                  <TableHead>Ship By</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => {
                  const locations = orderLocations(order);
                  return (
                  <TableRow key={order.id} data-testid={`row-order-${order.id}`} className="cursor-pointer hover:bg-muted/50" onClick={() => setLocation(`/fulfillment/orders/${encodeURIComponent(order.id)}`)}>
                    <TableCell className="font-mono font-medium" title={order.id}>{order.id.slice(0, 12)}</TableCell>
                     <TableCell>
                       <div className="flex flex-col gap-1 text-xs">
                          {order.source_order_id ? (
                            <span className="font-mono font-medium">
                             {order.source_order_id}
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                          {order.order_source && (
                            <span className="text-muted-foreground">{order.order_source}</span>
                          )}
                          {order.order_service && (
                            <span className="text-muted-foreground">{order.order_service}</span>
                          )}
                       </div>
                     </TableCell>
                    <TableCell className="font-mono text-xs">
                      <div data-testid={`text-order-warehouses-${order.id}`}>WH: {locationLabel(locations.warehouses)}</div>
                      <div className="text-muted-foreground" data-testid={`text-order-zones-${order.id}`}>Zones: {locationLabel(locations.zones)}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={order.priority === 'urgent' ? 'destructive' : order.priority === 'high' ? 'warning' : 'secondary'} className="uppercase text-[10px]">
                        {order.priority}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="uppercase text-[10px]">
                        {order.fulfillment_status || order.status}
                      </Badge>
                      {order.issues?.length ? <p className="mt-1 max-w-xs text-xs text-destructive" data-testid={`text-order-blocker-${order.id}`}>{order.issues.join('; ')}</p> : null}
                      {order.hold_reason && <p className="mt-1 max-w-xs text-xs text-destructive" data-testid={`text-order-hold-${order.id}`}>{order.hold_reason}</p>}
                    </TableCell>
                    <TableCell>{order.lines.length} lines</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(order.ship_by).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" aria-label={`View order ${order.source_order_id || order.id}`} data-testid={`button-order-details-${order.id}`} onClick={event => { event.stopPropagation(); setLocation(`/fulfillment/orders/${encodeURIComponent(order.id)}`); }}>
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground" data-testid="text-orders-pagination">{data ? `${data.total ? offset + 1 : 0}–${Math.min(offset + orders.length, data.total)} of ${data.total.toLocaleString()} orders` : 'Waiting for orders'}</p>
            <div className="flex gap-2">
              <Button variant="outline" data-testid="button-orders-previous" disabled={isLoading || offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Previous</Button>
              <Button variant="outline" data-testid="button-orders-next" disabled={isLoading || !data || offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>Next</Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
