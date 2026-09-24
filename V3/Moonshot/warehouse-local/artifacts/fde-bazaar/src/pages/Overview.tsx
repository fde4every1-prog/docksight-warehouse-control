import { useState, useEffect } from 'react';
import { Link, useLocation } from 'wouter';
import { useListBazaarOrders, getListBazaarOrdersQueryKey } from '@workspace/api-client-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Plus, Clock, Search, Package, AlertCircle, ArrowRight, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { format } from 'date-fns';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

export default function Overview() {
  const [, setLocation] = useLocation();
  const [offset, setOffset] = useState(0);
  const limit = 10;

  // Fetch orders with finite polling (10s)
  const { data, isLoading, isFetching, error } = useListBazaarOrders(
    { limit, offset },
    { query: { refetchInterval: 10000, queryKey: getListBazaarOrdersQueryKey({ limit, offset }) } }
  );

  const total = data?.total ?? 0;
  const currentCount = data?.orders?.length ?? 0;
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  // Clamp current page when empty due to deletions or boundary shifts
  useEffect(() => {
    if (data && offset > 0 && currentCount === 0) {
      setOffset(Math.max(0, offset - limit));
    }
  }, [data, offset, limit, currentCount]);

  const handleNext = () => {
    if (offset + limit < total) {
      setOffset(offset + limit);
    }
  };

  const handlePrev = () => {
    if (offset - limit >= 0) {
      setOffset(offset - limit);
    }
  };

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Overview</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Manage and track your Online Marketplace Place orders.
          </p>
        </div>
        <Button onClick={() => setLocation('/orders/new')} className="shrink-0 group">
          <Plus className="mr-2 h-4 w-4" />
          Create Order
        </Button>
      </div>

      <div className="grid gap-6 md:grid-cols-4 mb-8">
        <SummaryCard 
          title="Total Orders" 
          value={data?.summary?.total ?? 0} 
          icon={<Package className="h-4 w-4 text-muted-foreground" />} 
          loading={isLoading}
        />
        <SummaryCard 
          title="Pending" 
          value={data?.summary?.pending ?? 0} 
          icon={<Clock className="h-4 w-4 text-muted-foreground" />} 
          loading={isLoading}
        />
        <SummaryCard 
          title="Sent to DockSight"
          value={data?.summary?.sent ?? 0} 
          icon={<ArrowRight className="h-4 w-4 text-muted-foreground" />} 
          loading={isLoading}
        />
        <SummaryCard 
          title="Failed" 
          value={data?.summary?.failed ?? 0} 
          icon={<AlertCircle className="h-4 w-4 text-destructive" />} 
          loading={isLoading}
          isError={(data?.summary?.failed ?? 0) > 0}
        />
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="text-xl font-semibold tracking-tight">Recent Orders</h2>
        
        {error ? (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>Failed to load orders. Please try again later.</AlertDescription>
          </Alert>
        ) : isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <Skeleton key={i} className="h-24 w-full rounded-xl" />
            ))}
          </div>
        ) : !data || data.orders.length === 0 ? (
          <Card className="border-dashed bg-transparent shadow-none">
            <CardContent className="flex flex-col items-center justify-center p-12 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted/50 mb-4">
                <Search className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium">No orders found</h3>
              <p className="mt-1 text-sm text-muted-foreground mb-6 max-w-sm">
                You haven't created any orders yet. Create your first order to get started.
              </p>
              <Button onClick={() => setLocation('/orders/new')}>
                <Plus className="mr-2 h-4 w-4" /> Create First Order
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4">
            {data.orders.map(order => (
              <Link key={order.id} href={`/orders/${order.id}`}>
                <Card className="hover-elevate cursor-pointer transition-colors hover:border-primary/50">
                  <CardContent className="flex flex-col sm:flex-row sm:items-center justify-between p-6 gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-semibold text-primary">{order.id}</span>
                        {order.delivery_status === 'pending' && <Badge variant="secondary">Pending API</Badge>}
                        {order.delivery_status === 'sending' && <Badge variant="outline" className="text-blue-600 border-blue-200 bg-blue-50">Sending</Badge>}
                        {order.delivery_status === 'sent' && <Badge className="bg-green-600 hover:bg-green-700">Sent</Badge>}
                        {order.delivery_status === 'failed' && <Badge variant="destructive">Failed</Badge>}
                      </div>
                      <div className="text-sm text-muted-foreground flex items-center gap-2">
                        <span>{format(new Date(order.created_at), 'MMM d, yyyy HH:mm')}</span>
                        <span>&bull;</span>
                        <span className="flex items-center gap-1">
                          <Package className="h-3 w-3" />
                          {order.lines.reduce((acc, line) => acc + line.quantity, 0)} items across {order.lines.length} SKUs
                        </span>
                      </div>
                    </div>
                    
                    <div className="flex flex-col items-start sm:items-end gap-1">
                      <div className="text-sm font-medium">
                        Service: {order.service.replace('_', ' ')}
                      </div>
                      {order.warehouse_id && (
                        <div className="text-xs text-muted-foreground">
                          Warehouse: <span className="font-medium text-foreground">{order.warehouse_id}</span>
                        </div>
                      )}
                      {order.control_tower_status ? (
                        <div className="text-xs text-muted-foreground flex items-center gap-1">
                          DockSight status:
                          <span className="font-medium text-foreground">
                            {order.control_tower_status}
                          </span>
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground">
                          Awaiting DockSight processing
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <div className="text-sm text-muted-foreground">
                  Showing {offset + 1} to {Math.min(offset + limit, total)} of {total} orders
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handlePrev}
                    disabled={offset === 0}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Previous
                  </Button>
                  <div className="text-sm font-medium mx-2">
                    Page {currentPage} of {totalPages}
                    {isFetching && <Loader2 className="inline ml-2 h-3 w-3 animate-spin text-muted-foreground" />}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleNext}
                    disabled={offset + limit >= total}
                  >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ title, value, icon, loading, isError }: { title: string, value: number, icon: React.ReactNode, loading: boolean, isError?: boolean }) {
  return (
    <Card className={isError ? "border-destructive/50 bg-destructive/5" : ""}>
      <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <div className={`text-2xl font-bold ${isError ? 'text-destructive' : ''}`}>{value}</div>
        )}
      </CardContent>
    </Card>
  );
}
