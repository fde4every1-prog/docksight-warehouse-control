import React, { useState, useEffect, useRef } from 'react';
import { useSearch } from 'wouter';
import { useDemandForecasts } from '@/hooks/use-fulfillment';
import { Search, AlertTriangle, Info, RefreshCw, Calendar, History, Box as BoxIcon, Activity, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FulfillmentNav } from './components/FulfillmentNav';
import { DemandForecastDetailDialog } from './components/DemandForecastDetailDialog';

export default function DemandForecasts() {
  const searchString = useSearch();
  const searchParams = new URLSearchParams(searchString);

  const [search, setSearch] = useState(searchParams.get('search') || searchParams.get('sku') || '');
  const [warehouseId, setWarehouseId] = useState(searchParams.get('warehouse_id') || '');
  const [page, setPage] = useState(1);
  const limit = 25;

  const [selectedItem, setSelectedItem] = useState<{warehouse_id: string, sku: string, run_id?: string} | null>(() => {
    const sku = searchParams.get('sku');
    const wh = searchParams.get('warehouse_id');
    return sku && wh ? { warehouse_id: wh, sku: sku, run_id: undefined } : null;
  });

  const triggerRef = useRef<HTMLElement | null>(null);

  const { data, isLoading, error, refetch } = useDemandForecasts(warehouseId || undefined, search || undefined);

  // Auto-open if query requests it
  const [hasAutoOpened, setHasAutoOpened] = useState('');
  useEffect(() => {
    const openSku = searchParams.get('sku');
    const openWh = searchParams.get('warehouse_id');
    const key = `${openWh}-${openSku}`;
    
    if (openSku && openWh && hasAutoOpened !== key && data?.items.length === 1 && data.items[0].sku === openSku && data.items[0].warehouse_id === openWh) {
      setHasAutoOpened(key);
      setSelectedItem({ warehouse_id: openWh, sku: openSku, run_id: data?.run?.id });
    }
  }, [data, searchParams, hasAutoOpened]);

  // Reset page on filter changes
  useEffect(() => {
    setPage(1);
  }, [search, warehouseId]);

  const items = data?.items || [];
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  // Reset page if data changes drastically
  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [total, totalPages, page]);

  const paginatedItems = items.slice((page - 1) * limit, page * limit);

  return (
    <div className="flex flex-col h-full space-y-6 min-w-0 p-6 overflow-y-auto">
      <FulfillmentNav active="demand-forecasts" />
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Demand Forecasts</h1>
          <p className="text-muted-foreground mt-1">Per-warehouse SKU demand forecasting and low stock alerts.</p>
        </div>
        
        <div className="flex flex-col sm:flex-row gap-3 md:items-center">
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search SKUs..."
              aria-label="Search SKUs"
              className="pl-9 h-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="relative w-full sm:w-48">
            <BoxIcon className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Filter by Warehouse..."
              aria-label="Filter by Warehouse"
              className="pl-9 h-9"
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
            />
          </div>
          <Button variant="outline" size="sm" onClick={() => void refetch()} className="h-9">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh Data
          </Button>
        </div>
      </div>

      <p className="rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
        <strong>{data?.run?.lookback_days ?? '—'}-day lookback, not verified coverage.</strong> Only completed IST days before the forecast date count.
        Missing records after an imported dataset ends do not prove zero demand; a zero forecast can mean no history in this window.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          {error ? (
            <div className="flex flex-col items-center justify-center border border-destructive/20 bg-destructive/5 rounded-lg p-8 text-center space-y-4">
              <AlertTriangle className="h-8 w-8 text-destructive opacity-80" />
              <div className="space-y-1">
                <h3 className="font-bold text-destructive">Failed to load forecasts</h3>
                <p className="text-sm text-destructive/80 text-balance max-w-sm">
                  {error instanceof Error ? error.message : 'Unknown error occurred'}
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={() => void refetch()}>Try Again</Button>
            </div>
          ) : isLoading ? (
            <div className="space-y-4">
              <Skeleton className="h-[120px] w-full rounded-xl" />
              <Skeleton className="h-[120px] w-full rounded-xl" />
              <Skeleton className="h-[120px] w-full rounded-xl" />
            </div>
          ) : items.length === 0 ? (
            <div className="border border-dashed rounded-lg p-12 text-center text-muted-foreground bg-muted/20">
              No demand forecasts match your criteria.
            </div>
          ) : (
            <div className="space-y-4">
              {paginatedItems.map((item, idx) => (
                <Card 
                  key={`${item.warehouse_id}-${item.sku}-${idx}`} 
                  className={cn(
                    "overflow-hidden cursor-pointer hover:border-primary/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 group relative", 
                    item.low_stock && "border-warning/50"
                  )}
                  role="button"
                  tabIndex={0}
                  onClick={(e) => {
                    triggerRef.current = e.currentTarget;
                    setSelectedItem({ warehouse_id: item.warehouse_id, sku: item.sku, run_id: data?.run?.id });
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      triggerRef.current = e.currentTarget;
                      setSelectedItem({ warehouse_id: item.warehouse_id, sku: item.sku, run_id: data?.run?.id });
                    }
                  }}
                >
                  <div className="flex flex-col sm:flex-row">
                    <div className="p-5 flex-1 space-y-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-bold text-lg group-hover:text-primary transition-colors">{item.sku}</h3>
                            {item.low_stock && (
                              <Badge variant="warning" className="font-bold uppercase text-[10px]">
                                <AlertTriangle className="w-3 h-3 mr-1" />
                                Low Stock
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground flex items-center gap-1.5 mt-1 font-mono">
                            <BoxIcon className="w-3.5 h-3.5" /> {item.warehouse_id}
                          </p>
                        </div>
                        
                        <div className="text-right">
                          <div className="text-xs text-muted-foreground uppercase font-semibold mb-1 flex items-center justify-end gap-1">
                            Available Qty
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                              </TooltipTrigger>
                              <TooltipContent className="max-w-xs text-xs">
                                availability sum of per-location nonnegative min WMS/ERP/vision free qty, no double subtract reserves
                              </TooltipContent>
                            </Tooltip>
                          </div>
                          <div className="text-2xl font-bold font-mono">{item.available_qty}</div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t">
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Daily Demand</div>
                          <div className="font-mono text-sm">{(item.daily_demand ?? 0).toFixed(1)} / day</div>
                        </div>
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1 flex items-center gap-1">
                            7d Forecast
                            {item.low_stock && <span className="w-2 h-2 rounded-full bg-warning inline-block" />}
                          </div>
                          <div className={cn("font-mono text-sm font-medium", item.low_stock && "text-warning")}>
                            {item.forecast_7d}
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">30d Forecast</div>
                          <div className="font-mono text-sm">{item.forecast_30d}</div>
                        </div>
                        <div>
                          <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">History</div>
                          <div className="font-mono text-sm flex flex-wrap items-center gap-1.5">
                            <span className="whitespace-nowrap">{item.history_days} days</span>
                            {item.history_status === 'no_history' && (
                              <Badge variant="outline" className="text-[10px] uppercase text-muted-foreground whitespace-nowrap px-1 py-0.5">No History</Badge>
                            )}
                            {item.history_status === 'short_history' && (
                              <Badge variant="outline" className="text-[10px] uppercase text-warning border-warning whitespace-nowrap px-1 py-0.5">Short</Badge>
                            )}
                            {item.history_status === 'short_history' || item.history_status === 'no_history' ? (
                              <Tooltip>
                                <TooltipTrigger>
                                  <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />
                                </TooltipTrigger>
                                <TooltipContent>
                                  {item.history_status === 'no_history' ? 'No history coverage (0 returned)' : 'Short history coverage'}
                                </TooltipContent>
                              </Tooltip>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                <div className="text-sm text-muted-foreground">
                  Showing {total === 0 ? 0 : (page - 1) * limit + 1}–{Math.min(page * limit, total)} of {total}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page === 1}
                    onClick={() => setPage(Math.max(1, page - 1))}
                    className="h-8 px-3"
                  >
                    Previous
                  </Button>
                  <span className="text-sm font-mono px-2">{page} / {totalPages}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page === totalPages}
                    onClick={() => setPage(Math.min(totalPages, page + 1))}
                    className="h-8 px-3"
                  >
                    Next
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Forecast Run Status
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {!data?.run ? (
                <div className="text-muted-foreground flex items-center gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Waiting for initial run...
                </div>
              ) : (
                <>
                  <div className="flex justify-between items-center py-2 border-b">
                    <span className="text-muted-foreground">Status</span>
                    <Badge variant={data.run.stale ? "destructive" : "secondary"}>
                      {data.run.stale ? "Stale" : "Up to date"}
                    </Badge>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b">
                    <span className="text-muted-foreground">Schedule</span>
                    <span className="font-mono">{data.run.scheduled_time} {data.run.timezone}</span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b">
                    <span className="text-muted-foreground">Last Generated</span>
                    <span className="font-mono text-xs">{new Date(data.run.generated_at).toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b">
                    <span className="text-muted-foreground">Target Date</span>
                    <span className="font-mono">{data.run.forecast_date}</span>
                  </div>
                  <div className="flex justify-between items-center gap-3 py-2 border-b">
                    <span className="text-muted-foreground">Window</span>
                    <span className="font-mono text-xs text-right">
                      {data.run.window_start.slice(0, 10)} to {data.run.window_end.slice(0, 10)} (exclusive, IST)
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b">
                    <span className="text-muted-foreground">Excluded Unassigned</span>
                    <span className="font-mono text-xs">{data.run.excluded_unassigned_units} units</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Info className="h-4 w-4" />
                Methodology
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground space-y-3 leading-relaxed">
              <p>
                Forecasts are generated using a <strong>simple historical daily-average method</strong>.
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>This is <strong>not</strong> a trained AI model.</li>
                <li>The fixed lookback is the <strong>{data?.run?.lookback_days ?? '—'} completed IST days before the forecast date</strong>. Older imported orders are not counted.</li>
                <li><strong>Coverage is not verified:</strong> missing orders, including days after an imported dataset ends, do not prove zero demand. The calendar-day average is not a guarantee of continuous source coverage.</li>
                <li>Accepted and rejected suborders count once at their original order time; rejected demand is not treated as fulfilled work.</li>
                <li>Cancelled orders are excluded from the demand calculation.</li>
                <li>Demand without an assigned warehouse is excluded (currently {data?.run?.excluded_unassigned_units ?? 0} units excluded).</li>
                <li>The daily demand is averaged over the available historical days and multiplied by the forecast horizon (7 or 30 days), then <strong>ceiled</strong>.</li>
                <li>Items with <strong>no history in this lookback</strong> return a zero forecast, not evidence that future demand is zero.</li>
                <li>The 7-day forecast serves as the threshold for <strong>low stock alerts</strong>.</li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>

      <DemandForecastDetailDialog
        warehouse_id={selectedItem?.warehouse_id || ''}
        sku={selectedItem?.sku || ''}
        run_id={selectedItem?.run_id}
        open={!!selectedItem}
        onOpenChange={(open) => !open && setSelectedItem(null)}
        onCloseAutoFocus={(e) => {
          if (triggerRef.current) {
            e.preventDefault();
            triggerRef.current.focus();
            triggerRef.current = null;
          }
        }}
      />
    </div>
  );
}
