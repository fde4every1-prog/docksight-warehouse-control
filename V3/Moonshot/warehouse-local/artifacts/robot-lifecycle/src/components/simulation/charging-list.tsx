import { useState } from 'react';
import {
  getGetResourceLifecycleQueryKey,
  useGetResourceLifecycle,
} from '@workspace/api-client-react';
import { BatteryCharging } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export function ChargingList({ persona }: { persona: string }) {
  const [search, setSearch] = useState('');
  const { data, isLoading, isError, refetch } = useGetResourceLifecycle({
    request: { headers: { 'X-Demo-Persona': persona } },
    query: {
      queryKey: [...getGetResourceLifecycleQueryKey(), persona],
      refetchInterval: 5_000,
      refetchIntervalInBackground: true,
      retry: 2,
    },
  });
  const robots = (data?.resources ?? []).filter(
    resource => resource.resource_kind === 'robot' && resource.Docked_for_charging === 'Y',
  );
  const visible = robots.filter(robot =>
    `${robot.resource_id} ${robot.warehouse_id}`.toLowerCase().includes(search.trim().toLowerCase()),
  );

  return (
    <section className="mt-8 rounded-lg border bg-card" aria-labelledby="charging-heading">
      <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="charging-heading" className="flex items-center gap-2 font-mono text-lg font-bold">
            <BatteryCharging className="h-5 w-5 text-emerald-600" />
            Charging robots
            {data && <span className="text-sm font-normal text-muted-foreground">({robots.length})</span>}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Read-only progress · Updates every 5 seconds · Undocks automatically at 100%
          </p>
        </div>
        <Input
          aria-label="Find a charging robot"
          placeholder="Search robot or warehouse"
          value={search}
          onChange={event => setSearch(event.target.value)}
          className="sm:w-64"
        />
      </div>
      {isError && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 border-b bg-destructive/5 p-4 text-sm text-destructive">
          <span>Charging updates unavailable.{data ? ' Showing last received values; progress may be outdated.' : ''}</span>
          <Button variant="outline" size="sm" onClick={() => void refetch()}>Retry</Button>
        </div>
      )}
      {isLoading && !data ? (
        <p role="status" className="p-6 text-sm text-muted-foreground">Loading charging progress…</p>
      ) : data && visible.length === 0 ? (
        <p className="p-6 text-sm text-muted-foreground">
          {robots.length === 0 ? 'No robots are currently charging.' : 'No charging robots match your search.'}
        </p>
      ) : (
        <ul className="max-h-96 divide-y overflow-y-auto" aria-label="Charging progress">
          {visible.map(robot => (
            <li key={robot.resource_id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:gap-6">
              <div className="sm:w-44 sm:shrink-0">
                <div className="font-mono font-semibold">{robot.resource_id}</div>
                <div className="text-xs text-muted-foreground">{robot.warehouse_id}</div>
              </div>
              <div className="min-w-0 flex-1">
                <div className="mb-2 flex justify-between gap-3 text-sm">
                  <span>Charging</span>
                  <span className="font-mono">{robot.battery_pct === null ? 'Unknown' : `${robot.battery_pct.toFixed(1)}%`} / 100%</span>
                </div>
                <Progress
                  value={robot.battery_pct ?? 0}
                  aria-label={`${robot.resource_id} battery charge`}
                  aria-valuenow={robot.battery_pct ?? undefined}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
              <div className="text-xs text-muted-foreground sm:w-48">
                <div className="font-mono">Docked_for_charging = Y</div>
                <div className="mt-1">Unavailable for task assignment</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}