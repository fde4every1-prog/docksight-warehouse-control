import { useRoute } from 'wouter';
import { useGetBazaarOrder, useRetryBazaarOrder, useGetBazaarCatalog, getGetBazaarOrderQueryKey } from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { AlertCircle, CheckCircle2, Clock, RotateCcw, Package, ArrowLeft, Loader2, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { Link } from 'wouter';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { useMemo } from 'react';

const terminalFulfillmentStatuses = new Set([
  'completed',
  'fulfilled',
  'cancelled',
  'canceled',
  'failed',
]);

export default function Receipt() {
  const [, params] = useRoute('/orders/:id');
  const id = params?.id || '';
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: order, isLoading, error } = useGetBazaarOrder(id, {
    query: {
      enabled: !!id,
      queryKey: getGetBazaarOrderQueryKey(id),
      // Continue through handoff and fulfillment; stop only at a terminal
      // downstream outcome.
      refetchInterval: (query) => {
        const current = query.state?.data;
        if (!current) return 5000;
        if (current.delivery_status === 'pending' || current.delivery_status === 'sending') return 5000;
        const status = current.control_tower_status?.toLowerCase();
        return current.delivery_status === 'sent' && (!status || !terminalFulfillmentStatuses.has(status))
          ? 5000
          : false;
      }
    }
  });

  const { data: catalog } = useGetBazaarCatalog();
  const retryMutation = useRetryBazaarOrder();
  const catalogLookups = useMemo(() => {
    const serviceLabels = new Map<string, string>();
    const skuNames = new Map<string, string>();
    const warehouseNames = new Map<string, string>();

    for (const service of catalog?.services ?? []) {
      if (!serviceLabels.has(service.code)) serviceLabels.set(service.code, service.label);
    }
    for (const sku of catalog?.skus ?? []) {
      if (!skuNames.has(sku.sku)) skuNames.set(sku.sku, sku.name);
    }
    for (const warehouse of catalog?.warehouses ?? []) {
      if (!warehouseNames.has(warehouse.warehouse_id)) {
        warehouseNames.set(warehouse.warehouse_id, warehouse.name);
      }
    }

    return { serviceLabels, skuNames, warehouseNames };
  }, [catalog]);
  const subOrdersBySku = useMemo(() => {
    const lookup = new Map<string, NonNullable<typeof order>['sub_orders'][number]>();
    for (const subOrder of order?.sub_orders ?? []) {
      const sku = subOrder.sku;
      if (sku && !lookup.has(sku)) lookup.set(sku, subOrder);
    }
    return lookup;
  }, [order?.sub_orders]);

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Order Not Found</AlertTitle>
          <AlertDescription>We couldn't find this order's details.</AlertDescription>
        </Alert>
        <div className="mt-4">
          <Link href="/">
            <Button variant="outline"><ArrowLeft className="mr-2 h-4 w-4" /> Back to Orders</Button>
          </Link>
        </div>
      </div>
    );
  }

  const handleRetry = () => {
    retryMutation.mutate({ id }, {
      onSuccess: () => {
        toast({ title: "Retry Initiated", description: "The order delivery is being retried." });
        queryClient.invalidateQueries({ queryKey: getGetBazaarOrderQueryKey(id) });
      },
      onError: (err: any) => {
        toast({ title: "Retry Failed", description: err.message, variant: "destructive" });
      }
    });
  };

  const isFailed = order.delivery_status === 'failed';
  const serviceName = catalogLookups.serviceLabels.get(order.service) || order.service.replace('_', ' ');
  const requestedWarehouse = order.warehouse_id
    ? catalogLookups.warehouseNames.get(order.warehouse_id) || order.warehouse_id
    : null;
  const assignedWarehouseCount = new Set(
    order.sub_orders.map(item => item.warehouse_id).filter(Boolean),
  ).size;

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
      <div className="flex items-center gap-4">
        <Button variant="outline" size="icon" asChild>
          <Link href="/">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Order Receipt</h1>
          <p className="text-sm text-muted-foreground">Fulfillment progress</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Status Card */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Delivery & Handoff Status</CardTitle>
            <CardDescription>Real-time API tracking to DockSight</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between p-4 rounded-lg bg-muted/30 border">
              <div className="space-y-1">
                <span className="text-sm font-medium text-muted-foreground">Online Marketplace Place Status</span>
                <div className="flex items-center gap-2">
                  {order.delivery_status === 'pending' && <Badge variant="secondary"><Clock className="mr-1 h-3 w-3"/> Pending</Badge>}
                  {order.delivery_status === 'sending' && <Badge variant="outline" className="text-blue-600 border-blue-200 bg-blue-50"><Loader2 className="mr-1 h-3 w-3 animate-spin"/> Sending</Badge>}
                  {order.delivery_status === 'sent' && <Badge className="bg-green-600"><CheckCircle2 className="mr-1 h-3 w-3"/> Sent to DockSight</Badge>}
                  {order.delivery_status === 'failed' && <Badge variant="destructive"><AlertCircle className="mr-1 h-3 w-3"/> Failed</Badge>}
                </div>
              </div>
              <Separator orientation="vertical" className="h-10 hidden sm:block" />
              <div className="space-y-1 text-right sm:text-left">
                <span className="text-sm font-medium text-muted-foreground">DockSight Status</span>
                <div className="font-semibold">
                  {order.control_tower_status ? (
                    <Badge variant="outline" className="border-primary text-primary">
                      {order.control_tower_status.toUpperCase()}
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground text-sm">Waiting...</span>
                  )}
                </div>
              </div>
            </div>

            {order.last_error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Handoff Error</AlertTitle>
                <AlertDescription className="mt-1 whitespace-pre-wrap break-words text-sm">
                  {order.last_error}
                </AlertDescription>
              </Alert>
            )}

            {order.sync_error && (
              <Alert variant="destructive" className="border-orange-500 bg-orange-50 text-orange-900 dark:bg-orange-950 dark:text-orange-200">
                <AlertCircle className="h-4 w-4" color="currentColor" />
                <AlertTitle>Sync Error</AlertTitle>
                <AlertDescription className="break-all font-mono text-xs mt-1">
                  {order.sync_error}
                </AlertDescription>
              </Alert>
            )}

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground block mb-1">Created At</span>
                <span className="font-medium">{format(new Date(order.created_at), 'PPpp')}</span>
              </div>
              <div>
                <span className="text-muted-foreground block mb-1">Target Ship By</span>
                <span className="font-medium text-primary">{format(new Date(order.ship_by), 'PPpp')}</span>
              </div>
              <div>
                <span className="text-muted-foreground block mb-1">Delivery Attempts</span>
                <span className="font-medium">{order.attempts}</span>
              </div>
            </div>

            {isFailed && (
              <Button 
                variant="default" 
                className="w-full sm:w-auto" 
                onClick={handleRetry}
                disabled={retryMutation.isPending}
              >
                {retryMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RotateCcw className="mr-2 h-4 w-4" />}
                Retry DockSight Handoff
              </Button>
            )}
            {order.control_tower_order_id && (
              <Button variant="outline" asChild>
                <a href={`/fulfillment/orders/${encodeURIComponent(order.control_tower_order_id)}`}>
                  View exact order in DockSight
                  <ExternalLink className="ml-2 h-4 w-4" />
                </a>
              </Button>
            )}
          </CardContent>
        </Card>

        {/* Details Card */}
        <Card>
          <CardHeader>
            <CardTitle>Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <span className="text-xs text-muted-foreground block mb-1">Service</span>
              <span className="font-medium text-sm">{serviceName}</span>
            </div>
            <Separator />
            <div>
              <span className="text-xs text-muted-foreground block mb-1">Requested Warehouse</span>
              <span className="font-medium text-sm">
                {requestedWarehouse
                  ? `${requestedWarehouse}${requestedWarehouse === order.warehouse_id ? '' : ` · ${order.warehouse_id}`}`
                  : 'Automatic (legacy order)'}
              </span>
            </div>
            <Separator />
            <div>
              <span className="text-xs text-muted-foreground block mb-1">Assignment</span>
              <span className="font-medium text-sm">
                {order.sub_orders.length > 0
                  ? assignedWarehouseCount > 0
                    ? `${assignedWarehouseCount} warehouse${assignedWarehouseCount === 1 ? '' : 's'}`
                    : 'Assignment pending'
                  : order.warehouse_id ? 'Allocation pending' : 'Automatic · pending'}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Lines */}
        <Card className="md:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Package className="h-5 w-5 text-muted-foreground" />
              Order Lines
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border">
              <div className="grid grid-cols-12 gap-4 border-b bg-muted/50 p-3 text-sm font-medium text-muted-foreground">
                <div className="col-span-5">Item</div>
                <div className="col-span-3">Assignment</div>
                <div className="col-span-2">Progress</div>
                <div className="col-span-2 text-right">Qty</div>
              </div>
              <div className="divide-y">
                {order.lines.map((line, i) => {
                  const skuName = catalogLookups.skuNames.get(line.sku) || line.sku;
                  const progress = subOrdersBySku.get(line.sku);
                  const status = progress?.status || (order.delivery_status === 'sent' ? 'accepting' : 'handoff pending');
                  const picked = progress?.allocations?.reduce(
                    (total, allocation) => total + (allocation.picked_qty || 0),
                    0,
                  ) ?? 0;
                  const completed = status.toLowerCase() === 'completed' ? line.quantity : 0;
                  const zones = [...new Set(progress?.allocations?.map(allocation => allocation.zone).filter(Boolean) || [])];
                  const locations = [...new Set(progress?.allocations?.map(allocation => allocation.location).filter(Boolean) || [])];
                  return (
                    <div key={i} className="grid grid-cols-12 gap-4 p-3 text-sm items-center">
                      <div className="col-span-5">
                        <div className="font-medium">{skuName}</div>
                        <div className="font-mono text-xs text-muted-foreground">{line.sku}</div>
                      </div>
                      <div className="col-span-3 text-xs">
                        <div className="font-medium">
                          {progress?.warehouse_id || (order.warehouse_id ? 'Not allocated' : 'Automatic')}
                        </div>
                        {zones.length > 0 && <div className="text-muted-foreground">Zone {zones.join(', ')}</div>}
                        {locations.length > 0 && <div className="text-muted-foreground">Location {locations.join(', ')}</div>}
                      </div>
                      <div className="col-span-2 min-w-0">
                        <Badge variant={status.toLowerCase().includes('held') ? 'destructive' : 'outline'} className="max-w-full">
                          <span className="truncate">{status.replaceAll('_', ' ')}</span>
                        </Badge>
                        {progress?.hold_reason && (
                          <div className="mt-1 truncate text-xs text-destructive" title={progress.hold_reason}>
                            {progress.hold_reason.replaceAll('_', ' ')}
                          </div>
                        )}
                      </div>
                      <div className="col-span-2 text-right font-mono font-medium">
                        {line.quantity}
                        <div className="text-xs font-normal text-muted-foreground">
                          {completed > 0 ? `${completed} complete` : picked > 0 ? `${picked} picked` : 'Not completed'}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <div className="text-sm font-medium">
                Total Items: {order.lines.reduce((acc, l) => acc + l.quantity, 0)}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
