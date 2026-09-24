import { CompareTransferResponse, TransferRun } from '@/hooks/use-transfer-batching';
import { Box, Clock, TrendingDown, TrendingUp, Activity } from 'lucide-react';

export function TransferMetricsSummary({ comparison, currentTime }: { comparison: CompareTransferResponse | null, currentTime: number }) {
  if (!comparison) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center border-t bg-muted/20 border-dashed">
        <p className="text-sm text-muted-foreground font-mono">Run comparison to view metrics</p>
      </div>
    );
  }

  const { baseline, proposed: batched, difference: savings } = comparison;
  
  const isComparable = savings.comparable !== false;
  const isLoss = savings.overall_completion_seconds != null && savings.overall_completion_seconds < 0;
  const absSavings = savings.overall_completion_seconds != null ? Math.abs(savings.overall_completion_seconds) : 0;
  const savingsColor = isLoss ? 'text-destructive' : 'text-emerald-600';
  const SavingsIcon = isLoss ? TrendingUp : TrendingDown;
  
  const makespanSavingsPct = baseline.metrics.overall_completion_seconds > 0 && savings.overall_completion_seconds != null
    ? (absSavings / baseline.metrics.overall_completion_seconds) * 100 
    : 0;

  const completedOrderIds = (run: TransferRun) => {
    const finalTransferByOrder = new Map<string, number>();
    run.timeline
      .filter(event => event.action === 'transfer')
      .forEach(event => event.order_ids.forEach(orderId => {
        finalTransferByOrder.set(orderId, Math.max(finalTransferByOrder.get(orderId) || 0, event.end));
      }));
    return new Set(
      [...finalTransferByOrder.entries()]
        .filter(([, completedAt]) => completedAt <= currentTime)
        .map(([orderId]) => orderId)
    );
  };
  const batchedCompletedIds = completedOrderIds(batched);
  const baselineCompletedIds = completedOrderIds(baseline);
  const liveCompletedOrders = batched.orders.filter(o => batchedCompletedIds.has(o.id));
  const liveTasks = batched.timeline.filter(t => t.end <= currentTime).length;

  const baselineLiveCompletedOrders = baseline.orders.filter(o => baselineCompletedIds.has(o.id));
  const baselineLiveTasks = baseline.timeline.filter(t => t.end <= currentTime).length;
  
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 divide-x border-t bg-card">
      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <Clock className="h-3.5 w-3.5" />
          Overall Completion
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{batched.metrics.overall_completion_seconds}s</span>
          <span className="text-sm text-muted-foreground mb-1 line-through" title="Current Process Completion">
            {baseline.metrics.overall_completion_seconds}s
          </span>
        </div>
        {isComparable && savings.overall_completion_seconds != null ? (
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
          Transfer Service Time
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{batched.metrics.transfer_service_seconds}s</span>
          <span className="text-sm text-muted-foreground mb-1 line-through">{baseline.metrics.transfer_service_seconds}s</span>
        </div>
        {isComparable && savings.transfer_service_seconds != null ? (
          <div className={`text-xs font-mono flex items-center gap-1 ${savings.transfer_service_seconds < 0 ? 'text-destructive' : 'text-emerald-600'}`}>
            {savings.transfer_service_seconds < 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {Math.abs(savings.transfer_service_seconds)}s {savings.transfer_service_seconds < 0 ? 'Loss' : 'Savings'}
          </div>
        ) : null}
      </div>

      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <Box className="h-3.5 w-3.5" />
          Replay Orders & Items
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{liveCompletedOrders.length}</span>
          <span className="text-sm text-muted-foreground mb-1">/ {batched.orders.length} total</span>
        </div>
        <div className="text-[10px] font-mono text-muted-foreground flex justify-between mt-1">
          <span className={batched.metrics.excluded_order_count > 0 ? "text-amber-600 font-bold" : ""}>
            {batched.metrics.excluded_order_count} excluded
          </span>
          <span className={`border-l pl-2 ml-1 ${baseline.metrics.excluded_order_count > 0 ? "text-amber-600 font-bold" : "opacity-70"}`}>
            Base: {baseline.metrics.excluded_order_count} excl
          </span>
        </div>
        <div className="text-[10px] font-mono text-muted-foreground flex justify-between">
          <span>{batched.metrics.transferred_quantities} items</span>
          <span title="Baseline completed orders at replay time" className="opacity-70 border-l pl-2 ml-1">Base: {baselineLiveCompletedOrders.length} complete</span>
        </div>
      </div>

      <div className="p-4 flex flex-col gap-1 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground uppercase">
          <Activity className="h-3.5 w-3.5" />
          Replay Tasks
        </div>
        <div className="flex items-end gap-2 mt-1">
          <span className="text-2xl font-bold tracking-tight">{liveTasks}</span>
          <span className="text-sm text-muted-foreground mb-1">/ {batched.timeline.length} total</span>
        </div>
        <div className="text-xs font-mono text-muted-foreground flex justify-between">
          <span>{batched.metrics.deadline_misses} deadline misses</span>
          <span title="Baseline completed tasks at replay time" className="opacity-70 border-l pl-2 ml-1">Base: {baselineLiveTasks}</span>
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
            const progress = (run: TransferRun) => {
              const outcome = run.orders.find(o => o.id === order.id);
              const active = run.timeline.find(t => t.order_ids.includes(order.id) && t.start <= currentTime && currentTime < t.end);
              const finalTransferAt = Math.max(
                0,
                ...run.timeline
                  .filter(t => t.action === 'transfer' && t.order_ids.includes(order.id))
                  .map(t => t.end)
              );
              return outcome && finalTransferAt > 0 && finalTransferAt <= currentTime
                ? `Complete ${outcome.completed_at}s · ${outcome.on_time ? 'on time' : 'late'}`
                : active ? `${active.action.replace('_', ' ')} · until ${active.end}s` : 'Waiting';
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