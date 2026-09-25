import type { FleetIssue } from '@/hooks/use-fleet-issues';

export function FleetOrderImpact({ issue, compact = false }: { issue: FleetIssue; compact?: boolean }) {
  const orders = issue.impacted_orders ?? [];
  if (!orders.length) return null;
  const displayed = compact ? orders.slice(0, 2) : orders;
  return (
    <div className="mt-3 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-sm">
      <p className="font-semibold text-destructive">
        {orders.length} {orders.length === 1 ? 'order waiting' : 'orders waiting'} — P1
      </p>
      {!compact && issue.priority_reason && (
        <p className="mt-1 text-muted-foreground">{issue.priority_reason}</p>
      )}
      <ul className="mt-2 max-h-36 space-y-1 overflow-y-auto">
        {displayed.map(order => (
          <li key={order.order_id} className="break-all font-mono text-xs">
            {order.order_id}
            {!compact && <span className="font-sans text-muted-foreground"> · {order.task_ids.length} waiting {order.task_ids.length === 1 ? 'task' : 'tasks'}</span>}
          </li>
        ))}
      </ul>
      {compact && orders.length > displayed.length && (
        <p className="mt-1 text-xs text-muted-foreground">+{orders.length - displayed.length} more affected orders</p>
      )}
    </div>
  );
}