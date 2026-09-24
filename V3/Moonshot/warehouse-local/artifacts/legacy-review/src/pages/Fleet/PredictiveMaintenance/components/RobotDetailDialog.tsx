import React, { useState, useMemo } from 'react';
import { useMaintenanceRobot } from '@/hooks/use-predictive-maintenance';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { AlertTriangle, Bot, Activity, Info, BarChart2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent } from '@/components/ui/chart';
import { ComposedChart, CartesianGrid, XAxis, YAxis, Line, Area } from 'recharts';
import { Select } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { Role } from '@/contexts/PersonaContext';

const METRICS = [
  { key: 'temperature_c', label: 'Temperature (°C)', color: 'hsl(var(--destructive))', type: 'line' },
  { key: 'vibration_rms', label: 'Vibration (RMS)', color: 'hsl(var(--warning))', type: 'area' },
  { key: 'motor_current_a', label: 'Motor Current (A)', color: 'hsl(var(--primary))', type: 'line' },
  { key: 'battery_soh_pct', label: 'Battery SOH (%)', color: 'hsl(var(--success))', type: 'line' },
  { key: 'task_count', label: 'Daily Tasks', color: 'hsl(var(--muted-foreground))', type: 'area' },
  { key: 'fault_count', label: 'Daily Faults', color: 'hsl(var(--destructive))', type: 'area' },
];

export function RobotDetailDialog({
  robotId,
  role,
  open,
  onOpenChange
}: {
  robotId: string;
  role: Role;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: robot, isLoading, error, refetch } = useMaintenanceRobot(role, robotId);
  const [selectedMetric, setSelectedMetric] = useState<string>('temperature_c');

  const chartData = useMemo(() => {
    if (!robot?.history) return [];
    return [...robot.history].sort((a, b) => a.date.localeCompare(b.date));
  }, [robot?.history]);

  const activeMetric = METRICS.find(m => m.key === selectedMetric) || METRICS[0];

  const chartConfig = {
    [activeMetric.key]: { label: activeMetric.label, color: activeMetric.color },
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-2rem)] md:w-[calc(100vw-2rem)] sm:max-w-4xl grid-cols-[minmax(0,1fr)] max-h-[90vh] overflow-y-auto [&>*]:min-w-0">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-3 pr-6 text-xl">
            <Bot className="w-5 h-5 text-primary" />
            <span>Robot Detail: <span className="font-mono">{robotId}</span></span>
            {robot && (
              <Badge variant={
                robot.priority === 'review' ? 'destructive' :
                robot.priority === 'monitor' ? 'warning' : 'secondary'
              } className="uppercase font-mono">
                {robot.priority}
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            Historical signals and predictive risk assessment snapshot.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <div className="flex flex-col items-center justify-center border border-destructive/20 bg-destructive/5 rounded-lg p-8 text-center space-y-4">
            <AlertTriangle className="h-8 w-8 text-destructive opacity-80" />
            <h3 className="font-bold text-destructive">Failed to load robot details</h3>
            <p className="text-sm text-destructive/80 max-w-sm">
              {error instanceof Error ? error.message : 'Unknown error occurred'}
            </p>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>Try Again</Button>
          </div>
        ) : isLoading || !robot ? (
          <div className="space-y-4 pt-4">
            <Skeleton className="h-32 w-full rounded-xl" />
            <Skeleton className="h-[300px] w-full rounded-xl" />
          </div>
        ) : (
          <div className="space-y-6 pt-4 min-w-0 break-words">
            <div className="bg-muted/30 p-3 rounded-lg border text-sm text-muted-foreground flex items-start gap-2">
              <Info className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p>
                  <strong>Descriptive Signals Only.</strong> The observed measurements below are descriptive correlations, 
                  not proven causal explanations for failures.
                </p>
                <p>
                  <strong>Observation Date:</strong> {robot.observation_date} 
                  &nbsp; | &nbsp; <strong>Prediction Window:</strong> {robot.prediction_start} to {robot.prediction_end}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-muted/20 p-4 rounded-lg border">
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Risk Score</div>
                <div className={cn(
                  "font-mono text-2xl font-bold",
                  robot.priority === 'review' ? "text-destructive" :
                  robot.priority === 'monitor' ? "text-warning" : "text-foreground"
                )}>
                  {robot.risk_probability != null ? (robot.risk_probability * 100).toFixed(1) + '%' : 'N/A'}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Status</div>
                <div className="text-sm font-medium">{robot.eligible ? 'Eligible for Scoring' : 'Ineligible'}</div>
                {!robot.eligible && (
                  <div className="text-[10px] text-muted-foreground mt-0.5">{robot.reason}</div>
                )}
              </div>
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Location</div>
                <div className="font-mono text-sm">{robot.warehouse_id}</div>
              </div>
              <div>
                <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Model / Vendor</div>
                <div className="text-sm">{robot.vendor} {robot.robot_type}</div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <h3 className="font-bold text-sm flex items-center gap-2">
                  <BarChart2 className="w-4 h-4 text-muted-foreground" />
                  30-Day Signal History
                </h3>
                <Select 
                  value={selectedMetric} 
                  onChange={(e) => setSelectedMetric(e.target.value)}
                  className="w-[200px] h-8 text-xs"
                >
                  {METRICS.map(m => (
                    <option key={m.key} value={m.key}>{m.label}</option>
                  ))}
                </Select>
              </div>

              {chartData.length === 0 ? (
                <div className="h-64 border border-dashed rounded-lg flex items-center justify-center text-muted-foreground text-sm">
                  No historical data available.
                </div>
              ) : (
                <div className="h-72 w-full border rounded-lg p-4 pt-6 bg-card min-w-0">
                  <ChartContainer config={chartConfig} className="h-full w-full min-w-0">
                    <ComposedChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="date" tickLine={false} axisLine={false} tickFormatter={(val) => val.substring(5)} tick={{ fontSize: 10 }} />
                      <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                      <ChartTooltip 
                        content={
                          <ChartTooltipContent 
                            labelFormatter={(label) => `${label}`} 
                            formatter={(value, name) => (
                              <div className="flex flex-1 justify-between leading-none items-center gap-4">
                                <span className="text-muted-foreground">
                                  {chartConfig[activeMetric.key]?.label || name}
                                </span>
                                <span className="font-mono font-medium tabular-nums text-foreground">
                                  {Number(value).toFixed(2)}
                                </span>
                              </div>
                            )}
                          />
                        } 
                      />
                      <ChartLegend content={<ChartLegendContent />} />
                      
                      {activeMetric.type === 'area' ? (
                        <Area 
                          type="monotone" 
                          dataKey={activeMetric.key} 
                          fill={`var(--color-${activeMetric.key})`} 
                          stroke={`var(--color-${activeMetric.key})`} 
                          fillOpacity={0.1}
                          strokeWidth={2}
                        />
                      ) : (
                        <Line 
                          type="monotone" 
                          dataKey={activeMetric.key} 
                          stroke={`var(--color-${activeMetric.key})`} 
                          dot={false} 
                          strokeWidth={2} 
                        />
                      )}
                    </ComposedChart>
                  </ChartContainer>
                </div>
              )}
            </div>

            {robot.signals && robot.signals.length > 0 && (
              <div className="space-y-3">
                <h3 className="font-bold text-sm">Current Explanatory Signals</h3>
                <div className="border rounded-md overflow-hidden overflow-x-auto">
                  <table className="w-full text-sm text-left whitespace-nowrap">
                    <thead className="bg-muted text-muted-foreground">
                      <tr>
                        <th className="px-4 py-2 font-medium">Signal Name</th>
                        <th className="px-4 py-2 font-medium text-right">Current Value</th>
                        <th className="px-4 py-2 font-medium text-right">7-Day Mean</th>
                        <th className="px-4 py-2 font-medium text-right">30-Day Mean</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y font-mono text-xs">
                      {robot.signals.map((sig) => (
                        <tr key={sig.name} className="hover:bg-muted/50">
                          <td className="px-4 py-2 text-foreground font-sans">{sig.name}</td>
                          <td className="px-4 py-2 text-right">{sig.value.toFixed(3)}</td>
                          <td className="px-4 py-2 text-right text-muted-foreground">{sig.mean_7d.toFixed(3)}</td>
                          <td className="px-4 py-2 text-right text-muted-foreground">{sig.mean_30d.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
