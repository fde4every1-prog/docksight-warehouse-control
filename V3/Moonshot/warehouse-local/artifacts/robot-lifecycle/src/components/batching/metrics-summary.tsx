import { CompareResponse } from '@/hooks/use-batching';
import { Box, Clock, TrendingDown, TrendingUp, Activity } from 'lucide-react';

export function MetricsSummary({ comparison, currentTime }: { comparison: CompareResponse | null, currentTime: number }) {
  if (!comparison) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center border-t bg-muted/20 border-dashed">
        <p className="text-sm text-muted-foreground font-mono">Run comparison to view metrics</p>
      </div>
    );
  }

  const { baseline, batched, savings } = comparison;
  
  const isComparable = savings.comparable !== false;
  const isLoss = savings.makespan_seconds < 0;
  const absSavings = Math.abs(savings.makespan_seconds);
  const savingsColor = isLoss ? 'text-destructive' : 'text-emerald-600';
  const SavingsIcon = isLoss ? TrendingUp : TrendingDown;
  
  const makespanSavingsPct = baseline.metrics.makespan_seconds > 0 
    ? (absSavings / baseline.metrics.makespan_seconds) * 100 
    : 0;

  const liveCompletedOrders = batched.orders.filter(o => o.completed_at <= currentTime);
  const liveTasks = batched.timeline.filter(t => t.end <= currentTime).length;

  const baselineLiveCompletedOrders = baseline.orders.filter(o => o.completed_at <= currentTime);
  const baselineLiveTasks = baseline.timeline.filter(t => t.end <= currentTime).length;
  
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 divide-x border-t bg-card">
      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <Clock className="h-3.5 w-3.5" />
          Makespan (Projected)
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{batched.metrics.makespan_seconds}s</span>
          <span className="text-sm text-muted-foreground mb-1 line-through" title="Current Process Makespan">
            {baseline.metrics.makespan_seconds}s
          </span>
        </div>
        {isComparable ? (
          <div className={`text-xs font-mono flex items-center gap-1 ${savingsColor}`}>
            <SavingsIcon className="h-3 w-3" />
            {absSavings}s {isLoss ? 'slower' : 'saved'} ({makespanSavingsPct.toFixed(1)}%)
          </div>
        ) : (
          <div className="text-xs font-mono flex items-center gap-1 text-amber-600">
            Not Comparable (Exclusions differ)
          </div>
        )}
      </div>

      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <TrendingDown className="h-3.5 w-3.5" />
          Service Time (Projected)
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{batched.metrics.service_seconds}s</span>
          <span className="text-sm text-muted-foreground mb-1 line-through">{baseline.metrics.service_seconds}s</span>
        </div>
        <div className={`text-xs font-mono flex items-center gap-1 ${savings.service_seconds < 0 ? 'text-destructive' : 'text-emerald-600'}`}>
          {savings.service_seconds < 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {Math.abs(savings.service_seconds)}s {savings.service_seconds < 0 ? 'Loss' : 'Savings'}
        </div>
      </div>

      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <Box className="h-3.5 w-3.5" />
          Live Orders
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{liveCompletedOrders.length}</span>
          <span className="text-sm text-muted-foreground mb-1">/ {batched.orders.length} total</span>
        </div>
        <div className="text-xs font-mono text-muted-foreground flex justify-between">
          <span>{liveCompletedOrders.filter(o => o.on_time).length} on time</span>
          <span title="Current Process Live Orders" className="opacity-70 border-l pl-2 ml-1">Base: {baselineLiveCompletedOrders.length}</span>
        </div>
      </div>

      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <Activity className="h-3.5 w-3.5" />
          Live Tasks
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{liveTasks}</span>
          <span className="text-sm text-muted-foreground mb-1">/ {batched.timeline.length} total</span>
        </div>
        <div className="text-xs font-mono text-muted-foreground flex justify-between">
          <span>Final: {batched.metrics.completed_tasks} tasks</span>
          <span title="Current Process Live Tasks" className="opacity-70 border-l pl-2 ml-1">Base: {baselineLiveTasks}</span>
        </div>
      </div>
      
      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors col-span-full border-t">
        <div className="flex flex-col gap-2">
          <div className="text-xs font-mono text-muted-foreground uppercase">Projected Robot Utilization</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {batched.metrics.robot_utilization.map(ru => {
              const bl = baseline.metrics.robot_utilization.find(r => r.robot_id === ru.robot_id);
              return (
                <div key={ru.robot_id} className="flex flex-col gap-1">
                  <div className="text-[10px] font-mono font-bold uppercase">{ru.robot_id}</div>
                  <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                    <div 
                      className="bg-accent h-full"
                      style={{ width: `${ru.utilization * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[9px] font-mono text-muted-foreground">
                    <span>Batched: {(ru.utilization * 100).toFixed(1)}%</span>
                    {bl && <span>Base: {(bl.utilization * 100).toFixed(1)}%</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="col-span-full p-4 border-t">
        <h3 className="text-xs font-mono font-bold mb-2">Order progress · shared replay clock</h3>
        <p className="text-xs text-muted-foreground mb-3">
          Final deadline misses: current process {baseline.metrics.deadline_misses} · batched {batched.metrics.deadline_misses}
        </p>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <strong>Order</strong><strong>Current process</strong><strong>Batched</strong>
          {batched.orders.map(order => {
            const progress = (run: typeof baseline) => {
              const outcome = run.orders.find(o => o.id === order.id);
              const active = run.timeline.find(t => t.order_ids.includes(order.id) && t.start <= currentTime && currentTime < t.end);
              return outcome && outcome.completed_at <= currentTime
                ? `Complete ${outcome.completed_at}s · ${outcome.on_time ? 'on time' : 'late'}`
                : active ? `${active.stage.replace('_', ' ')} · until ${active.end}s` : 'Waiting';
            };
            return [
              <span key={`${order.id}-name`} className="font-mono">{order.id}<small className="block text-muted-foreground">Cutoff {order.cutoff_seconds}s</small></span>,
              <span key={`${order.id}-base`}>{progress(baseline)}</span>,
              <span key={`${order.id}-batch`}>{progress(batched)}</span>,
            ];
          })}
        </div>
      </div>
    </div>
  );
}