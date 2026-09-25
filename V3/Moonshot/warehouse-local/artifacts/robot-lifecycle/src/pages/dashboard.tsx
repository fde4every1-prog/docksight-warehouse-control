import {
  getGetLifecycleTasksQueryKey,
  useGetLifecycleTasks,
} from '@workspace/api-client-react';
import { Box, Radio } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { TaskList } from '@/components/simulation/task-list';
import { ChargingList } from '@/components/simulation/charging-list';
import { usePersona } from '@/hooks/use-persona';

export default function Dashboard() {
  const { persona } = usePersona();
  const {
    data,
    isLoading,
    isError,
    error,
    dataUpdatedAt,
  } = useGetLifecycleTasks({
    request: { headers: { 'X-Demo-Persona': persona } },
    query: {
      queryKey: [...getGetLifecycleTasksQueryKey(), persona],
      refetchInterval: 2_000,
      refetchIntervalInBackground: true,
      retry: 2,
    },
  });

  return (
    <div className="min-h-[100dvh] bg-background">
      <Header />
      <main className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 sm:py-9 lg:px-8">
        <section className="mb-6 flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              <Radio className="h-3.5 w-3.5 text-emerald-600" />
              Live assignment feed
            </div>
            <h1 className="font-mono text-2xl font-bold tracking-tight sm:text-3xl">
              Ongoing functions
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Track running tasks and robot charging. Progress is synchronized
              with DockSight and never advanced by this screen.
            </p>
          </div>
          <div className="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm shadow-sm">
            <Box className="h-4 w-4 text-muted-foreground" />
            <span className="font-mono font-bold">{data?.tasks.length ?? 0}</span>
            <span className="text-muted-foreground">
              {data?.tasks.length === 1 ? 'function' : 'functions'}
            </span>
          </div>
        </section>

        <TaskList
          persona={persona}
          tasks={data?.tasks ?? []}
          serverTime={data?.server_time}
          syncVersion={dataUpdatedAt}
          isLoading={isLoading && !data}
          isError={isError}
          error={error}
        />
        <ChargingList key={persona} persona={persona} />
      </main>
    </div>
  );
}