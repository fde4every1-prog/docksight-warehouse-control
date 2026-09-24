import React, { useMemo } from 'react';
import { useDemandForecastDetail } from '@/hooks/use-fulfillment';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { AlertTriangle, Info, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent } from '@/components/ui/chart';
import { ComposedChart, CartesianGrid, XAxis, YAxis, Bar, Line, ReferenceLine } from 'recharts';

export function DemandForecastDetailDialog({ 
  warehouse_id, 
  sku, 
  run_id, 
  open, 
  onOpenChange,
  onCloseAutoFocus
}: { 
  warehouse_id: string; 
  sku: string; 
  run_id?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCloseAutoFocus?: (e: Event) => void;
}) {
  const { data: detail, isLoading, error, refetch } = useDemandForecastDetail(warehouse_id, sku, run_id);

  const showRolling = detail ? detail.item.history_days >= 7 : false;

  const chartData = useMemo(() => {
    if (!detail) return [];
    const { history, projection, item } = detail;
    const combined = [];
    
    if (detail.history_available) {
      const sortedHistory = [...history].sort((a, b) => a.date.localeCompare(b.date));
      for (const h of sortedHistory) {
        combined.push({
          date: h.date,
          ordered_units: h.ordered_units,
          rolling_7d: showRolling ? h.rolling_7d : null,
          baseline: item.daily_demand
        });
      }
    }
    
    const sortedProjection = [...projection].sort((a, b) => a.date.localeCompare(b.date));
    for (const p of sortedProjection) {
      combined.push({
        date: p.date,
        daily_demand: p.daily_demand
      });
    }
    return combined;
  }, [detail]);

  const chartConfig = {
    ordered_units: { label: "Daily Orders", color: "hsl(var(--primary))" },
    rolling_7d: { label: "7-Day Avg", color: "hsl(var(--muted-foreground))" },
    baseline: { label: "Saved Baseline", color: "hsl(var(--warning))" },
    daily_demand: { label: "Prediction", color: "hsl(var(--destructive))" },
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent 
        className="w-[calc(100vw-2rem)] md:w-[calc(100vw-2rem)] sm:max-w-5xl grid-cols-[minmax(0,1fr)] max-h-[90vh] overflow-y-auto [&>*]:min-w-0"
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3 pr-6 text-xl break-words">
            <span>Forecast Details: <span className="font-mono break-all">{sku}</span></span>
            <Badge variant="outline" className="font-mono shrink-0">{warehouse_id}</Badge>
          </DialogTitle>
          <DialogDescription>
            Demand forecast details, historical patterns, and stock threshold analysis.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <div className="flex flex-col items-center justify-center border border-destructive/20 bg-destructive/5 rounded-lg p-8 text-center space-y-4">
            <AlertTriangle className="h-8 w-8 text-destructive opacity-80" />
            <div className="space-y-1">
              <h3 className="font-bold text-destructive">Failed to load detail</h3>
              <p className="text-sm text-destructive/80 text-balance max-w-sm">
                {error instanceof Error ? error.message : 'Unknown error occurred'}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>Try Again</Button>
          </div>
        ) : isLoading || !detail ? (
          <div className="space-y-4 pt-4">
            <Skeleton className="h-[200px] w-full rounded-xl" />
            <Skeleton className="h-[200px] w-full rounded-xl" />
          </div>
        ) : (
          <div className="space-y-6 pt-4 min-w-0 break-words">
            {/* Warnings */}
            <div className="flex flex-wrap gap-2 [&>*]:whitespace-normal [&>*]:max-w-full">
              {detail.item.history_status === 'no_history' && (
                <Badge variant="destructive" className="flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> No history coverage
                </Badge>
              )}
              {detail.item.history_status === 'short_history' && (
                <Badge variant="warning" className="flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Short history coverage
                </Badge>
              )}
              {detail.run.stale && (
                <Badge variant="destructive" className="flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Stale Run
                </Badge>
              )}
              {detail.run.excluded_unassigned_units > 0 && (
                <Badge variant="warning" className="flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Excluded {detail.run.excluded_unassigned_units} unassigned units
                </Badge>
              )}
              <Badge variant="secondary" className="flex items-center gap-1">
                <Info className="w-3 h-3" /> Unverified source coverage
              </Badge>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 bg-muted/20 p-4 rounded-lg border">
              <div className="min-w-0">
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1 truncate">Live Stock vs Threshold</div>
                <div className="flex items-end gap-2 flex-wrap" title={`Checked at ${new Date(detail.stock_checked_at).toLocaleString()}`}>
                  <div className="font-mono text-xl">{detail.item.available_qty}</div>
                  <div className="text-sm text-muted-foreground mb-0.5">/ {detail.item.forecast_7d}</div>
                </div>
                <div className="text-[10px] text-muted-foreground mt-1 break-words">
                  Live warehouse-wide allocatable stock: sum of each location's nonnegative minimum WMS/ERP/vision free quantity. Reservations are not subtracted twice.<br/>
                  Checked: {new Date(detail.stock_checked_at).toLocaleString()}
                </div>
              </div>
              <div className="min-w-0">
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1 truncate">Min Replenishment</div>
                <div className="font-mono text-xl text-primary truncate">{detail.minimum_replenishment}</div>
                <div className="text-[10px] text-muted-foreground mt-1 break-words">max(0, threshold - live stock)</div>
              </div>
              <div className="min-w-0">
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1 truncate">Forecast Horizons</div>
                <div className="font-mono text-sm truncate">
                  7d: {detail.item.forecast_7d} | 30d: {detail.item.forecast_30d}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1 break-words">
                  Saved baseline: {detail.item.daily_demand} units/day. Multiply by 7 or 30, then round up to a whole unit (ceiling).<br/>
                  Flat projection, not trend.
                </div>
              </div>
              <div className="min-w-0">
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1 truncate">Run Details</div>
                <div className="font-mono text-[10px] truncate max-w-full" title={detail.run.id}>{detail.run.id}</div>
                <div className="text-[10px] text-muted-foreground mt-1 break-words">
                  Target: {detail.run.forecast_date}<br/>
                  Gen (IST): {new Date(detail.run.generated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}<br/>
                  Window (IST): {detail.run.window_start.slice(0, 10)} to {detail.run.window_end.slice(0, 10)} (end exclusive)
                </div>
              </div>
            </div>

            {/* Methodology Note */}
            <div className="text-sm text-muted-foreground bg-muted/10 p-4 rounded-lg border leading-relaxed space-y-2">
              <p>
                <strong>Methodology:</strong> The saved baseline daily demand is calculated as total ordered units ({detail.item.history_units}) 
                divided by the available history days ({detail.item.history_days}), up to a maximum lookback of {detail.run.lookback_days} days.
              </p>
              {showRolling ? (
                <p>
                  The 7-day rolling mean shown on the chart is illustrative of recent volatility; the actual baseline uses the full average over the available lookback window.
                </p>
              ) : detail.history_available && detail.item.history_days > 0 ? (
                <p>
                  A 7-day rolling mean is not shown because the available history ({detail.item.history_days} days) is less than 7 days.
                </p>
              ) : null}
              <p>
                Zero fill assumptions apply to days inside the window without records. However, unverified source coverage means missing legacy data (no history) is not proof of zero demand.
              </p>
            </div>

            {/* Chart */}
            <div className="space-y-3 min-w-0">
              <h3 className="font-bold flex items-center gap-2">
                <Calendar className="w-4 h-4 text-muted-foreground" />
                History & Projection (Units/Day)
              </h3>
              
              {!detail.history_available && (
                <div className="border border-dashed border-warning/50 bg-warning/5 text-warning-foreground p-4 rounded-lg text-sm break-words">
                  <strong className="flex items-center gap-2 mb-1 flex-wrap"><AlertTriangle className="w-4 h-4 shrink-0" /> History unavailable for this legacy record</strong>
                  Daily inputs were not captured for this run and are not reconstructed from later orders. An operator can use the documented offline forecast refresh after stopping application writers; it creates a backup and preserves the superseded run. Opening this chart never refreshes forecasts. The projection below uses only the saved baseline.
                </div>
              )}

              <div className="h-72 w-full border rounded-lg p-4 pt-6 bg-card min-w-0">
                <ChartContainer config={chartConfig} className="h-full w-full min-w-0">
                  <ComposedChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={(val) => val.substring(5)} tick={{ fontSize: 10 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                    <ChartTooltip 
                      content={
                        <ChartTooltipContent 
                          labelFormatter={(label) => `${label} (IST)`} 
                          formatter={(value, name, item) => (
                            <>
                              <div
                                className="h-2.5 w-2.5 shrink-0 rounded-[2px] bg-[--color-bg]"
                                style={{ '--color-bg': item.color || item.payload?.fill } as React.CSSProperties}
                              />
                              <div className="flex flex-1 justify-between leading-none items-center gap-4">
                                <span className="text-muted-foreground">
                                  {(chartConfig as any)[String(item.dataKey)]?.label || name}
                                </span>
                                <span className="font-mono font-medium tabular-nums text-foreground">
                                  {value != null ? `${Number(value).toLocaleString()} ${item.dataKey === 'ordered_units' ? 'units' : 'units/day'}` : '-'}
                                </span>
                              </div>
                            </>
                          )}
                        />
                      } 
                    />
                    <ChartLegend content={<ChartLegendContent className="flex-wrap" />} />
                    
                    {detail.history_available && (
                      <>
                        <Bar dataKey="ordered_units" fill="var(--color-ordered_units)" name="Ordered Units" radius={[2, 2, 0, 0]} maxBarSize={40} />
                        {showRolling && (
                          <Line type="monotone" dataKey="rolling_7d" stroke="var(--color-rolling_7d)" dot={false} strokeWidth={2} name="7-Day Avg (Illustrative)" />
                        )}
                        <Line type="stepAfter" dataKey="baseline" stroke="var(--color-baseline)" dot={false} strokeWidth={2} name="Saved Baseline (History)" />
                      </>
                    )}
                    
                    <Line type="stepAfter" dataKey="daily_demand" stroke="var(--color-daily_demand)" dot={false} strokeWidth={2} name="Flat Prediction (30d)" strokeDasharray="5 5" />
                    
                    {detail.item.history_days > 0 && (
                      <ReferenceLine 
                        x={detail.run.window_end.slice(0, 10)} 
                        stroke="hsl(var(--muted-foreground))" 
                        strokeDasharray="3 3" 
                        label={{ position: 'top', value: 'Forecast starts', fill: 'hsl(var(--muted-foreground))', fontSize: 10 }} 
                      />
                    )}
                  </ComposedChart>
                </ChartContainer>
              </div>
            </div>

            {/* Data Table */}
            <div className="space-y-3">
              <h3 className="font-bold text-sm" id="forecast-data-table-title">Raw Data (IST)</h3>
              <div 
                className="border rounded-md overflow-hidden overflow-x-auto max-h-64 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                tabIndex={0}
                role="region"
                aria-labelledby="forecast-data-table-title"
              >
                <table className="w-full text-sm text-left whitespace-nowrap">
                  <thead className="bg-muted text-muted-foreground sticky top-0 z-10 shadow-sm">
                    <tr>
                      <th className="px-4 py-2 font-medium">Date (IST)</th>
                      {detail.history_available && <th className="px-4 py-2 font-medium text-right">Orders</th>}
                      {detail.history_available && showRolling && <th className="px-4 py-2 font-medium text-right">7-Day Avg</th>}
                      {detail.history_available && <th className="px-4 py-2 font-medium text-right">Baseline</th>}
                      <th className="px-4 py-2 font-medium text-right">Prediction</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {chartData.map((row) => (
                      <tr key={row.date} className="hover:bg-muted/50">
                        <td className="px-4 py-2 font-mono text-xs">{row.date}</td>
                        {detail.history_available && <td className="px-4 py-2 text-right">{row.ordered_units ?? '-'}</td>}
                        {detail.history_available && showRolling && <td className="px-4 py-2 text-right">{row.rolling_7d != null ? row.rolling_7d.toFixed(2) : '-'}</td>}
                        {detail.history_available && <td className="px-4 py-2 text-right">{row.baseline != null ? row.baseline.toFixed(2) : '-'}</td>}
                        <td className="px-4 py-2 text-right">{row.daily_demand != null ? row.daily_demand.toFixed(2) : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
