import { useEffect, useMemo, useRef, useState } from 'react';
import {
  getGetLifecycleTasksQueryKey,
  LifecycleTask,
  LifecycleTaskKillResult,
  useKillLifecycleTask,
} from '@workspace/api-client-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Box,
  Bot,
  CheckCircle2,
  CircleOff,
  Clock3,
  Cpu,
  Loader2,
  Radio,
  ShieldAlert,
  TimerReset,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

const POLL_INTERVAL_MS = 2_000;
const STALE_AFTER_MS = POLL_INTERVAL_MS * 4;
const DEFAULT_KILL_REASON = 'Fleet Simulator operator killed the active function.';

interface TaskListProps {
  persona: string;
  tasks: LifecycleTask[];
  serverTime?: string;
  syncVersion: number;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
}

interface ServerClock {
  serverMs: number;
  performanceMs: number;
}

function formatFunction(stage: string) {
  return stage.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function mutationErrorMessage(error: unknown) {
  const value = error as { data?: { detail?: unknown }; message?: unknown; status?: number };
  if (typeof value?.data?.detail === 'string') return value.data.detail;
  if (typeof value?.message === 'string') return value.message;
  return 'The function could not be killed. Refresh and try again.';
}

function FunctionTimer({
  task,
  nowMs,
}: {
  task: LifecycleTask;
  nowMs: number;
}) {
  const startedMs = task.started_at ? Date.parse(task.started_at) : Number.NaN;
  const dueMs = task.due_at ? Date.parse(task.due_at) : Number.NaN;
  const hasWindow = Number.isFinite(startedMs) && Number.isFinite(dueMs) && dueMs > startedMs;

  if (!hasWindow) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Clock3 className="h-4 w-4" />
        Waiting for timing data
      </div>
    );
  }

  const remainingSeconds = Math.max(0, Math.ceil((dueMs - nowMs) / 1_000));
  const progress = Math.min(100, Math.max(0, ((nowMs - startedMs) / (dueMs - startedMs)) * 100));

  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          Stage progress
        </span>
        <span className={cn(
          'font-mono text-lg font-bold tabular-nums',
          remainingSeconds === 0 && 'text-amber-700',
        )}>
          {remainingSeconds === 0 ? 'Awaiting Core' : `${remainingSeconds}s`}
        </span>
      </div>
      <Progress value={progress} aria-label={`${Math.round(progress)} percent complete`} />
      {remainingSeconds === 0 && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <TimerReset className="h-3.5 w-3.5" />
          Time is up. Waiting for the backend to confirm the next state.
        </p>
      )}
    </div>
  );
}

function DetailValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/30 p-3">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 truncate font-mono text-sm font-semibold" title={value}>{value}</dd>
    </div>
  );
}

export function TaskList({
  persona,
  tasks,
  serverTime,
  syncVersion,
  isLoading,
  isError,
  error,
}: TaskListProps) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [selectedTask, setSelectedTask] = useState<LifecycleTask | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [feedback, setFeedback] = useState<LifecycleTaskKillResult | null>(null);
  const clockRef = useRef<ServerClock | null>(null);
  const requestIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!serverTime) return;
    const serverMs = Date.parse(serverTime);
    if (!Number.isFinite(serverMs)) return;
    clockRef.current = { serverMs, performanceMs: performance.now() };
    setNowMs(serverMs);
  }, [serverTime, syncVersion]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      const clock = clockRef.current;
      setNowMs(clock
        ? clock.serverMs + (performance.now() - clock.performanceMs)
        : Date.now());
    }, 250);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    setSelectedTask(null);
    setConfirmOpen(false);
  }, [persona]);

  const killTask = useKillLifecycleTask({
    request: { headers: { 'X-Demo-Persona': persona } },
  });

  const connectionState = useMemo(() => {
    if (isError) return 'disconnected';
    const clock = clockRef.current;
    if (!clock || performance.now() - clock.performanceMs > STALE_AFTER_MS) return 'stale';
    return 'live';
  }, [isError, nowMs, serverTime]);

  const openConfirmation = () => {
    if (!selectedTask || persona !== 'fleet' || killTask.isPending) return;
    requestIdRef.current = crypto.randomUUID();
    setConfirmOpen(true);
  };

  const confirmKill = () => {
    if (!selectedTask || !requestIdRef.current || persona !== 'fleet' || killTask.isPending) return;
    const task = selectedTask;
    killTask.mutate({
      taskId: task.task_id,
      data: {
        request_id: requestIdRef.current,
        assignment_token: task.assignment_token,
        reason: DEFAULT_KILL_REASON,
      },
    }, {
      onSuccess: (result) => {
        setConfirmOpen(false);
        setSelectedTask(null);
        setFeedback(result);
        toast({
          title: result.replacement_status === 'replaced'
            ? 'Replacement assigned'
            : 'Function waiting for a replacement',
          description: result.message,
        });
        queryClient.invalidateQueries({ queryKey: getGetLifecycleTasksQueryKey() });
      },
      onError: (killError) => {
        const message = mutationErrorMessage(killError);
        toast({ variant: 'destructive', title: 'Kill command rejected', description: message });
        queryClient.invalidateQueries({ queryKey: getGetLifecycleTasksQueryKey() });
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex min-h-[360px] items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Connecting to DockSight…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {connectionState !== 'live' && (
        <Alert variant={connectionState === 'disconnected' ? 'destructive' : 'default'}>
          {connectionState === 'disconnected'
            ? <CircleOff className="h-4 w-4" />
            : <AlertTriangle className="h-4 w-4" />}
          <AlertTitle>
            {connectionState === 'disconnected' ? 'Disconnected' : 'Updates delayed'}
          </AlertTitle>
          <AlertDescription>
            {connectionState === 'disconnected'
              ? `Live functions may be out of date. ${error instanceof Error ? error.message : ''}`
              : 'The last server clock sync is stale. Timers are estimates until the connection recovers.'}
          </AlertDescription>
        </Alert>
      )}

      {feedback && (
        <Alert className={feedback.replacement_status === 'replaced'
          ? 'border-emerald-300 bg-emerald-50'
          : 'border-amber-300 bg-amber-50'}>
          {feedback.replacement_status === 'replaced'
            ? <CheckCircle2 className="h-4 w-4 text-emerald-700" />
            : <TimerReset className="h-4 w-4 text-amber-700" />}
          <AlertTitle>
            {feedback.replacement_status === 'replaced'
              ? 'Automatic replacement complete'
              : 'Waiting for an eligible replacement'}
          </AlertTitle>
          <AlertDescription>{feedback.message}</AlertDescription>
        </Alert>
      )}

      {tasks.length === 0 ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center rounded-lg border border-dashed bg-card px-6 text-center">
          <div className="mb-4 rounded-full bg-muted p-4">
            <Radio className="h-7 w-7 text-muted-foreground" />
          </div>
          <h2 className="text-lg font-semibold">No ongoing functions</h2>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            DockSight has no robot or control-asset functions running right now.
            New assignments will appear automatically.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {tasks.map((task) => (
            <button
              type="button"
              key={`${task.task_id}:${task.assignment_token}`}
              onClick={() => setSelectedTask(task)}
              className="group rounded-lg border bg-card p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="rounded-md bg-primary/8 p-2.5 text-primary">
                    {task.resource_kind === 'robot'
                      ? <Bot className="h-5 w-5" />
                      : <Cpu className="h-5 w-5" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {task.resource_kind === 'robot' ? 'Robot' : 'Control asset'}
                    </p>
                    <h2 className="truncate font-mono text-base font-bold" title={task.resource_id ?? undefined}>
                      {task.resource_id ?? 'Unassigned'}
                    </h2>
                  </div>
                </div>
                <Badge className="shrink-0 bg-emerald-100 text-emerald-800 hover:bg-emerald-100">
                  Running
                </Badge>
              </div>

              <div className="my-5 grid grid-cols-2 gap-3">
                <DetailValue label="Order" value={task.order_id} />
                <DetailValue label="Function" value={formatFunction(task.stage)} />
              </div>
              <FunctionTimer task={task} nowMs={nowMs} />
              <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
                <span className="truncate font-mono" title={task.task_id}>{task.task_id}</span>
                <span className="font-semibold text-foreground group-hover:underline">View function</span>
              </div>
            </button>
          ))}
        </div>
      )}

      <Dialog
        open={Boolean(selectedTask)}
        onOpenChange={(open) => {
          if (!open && !confirmOpen && !killTask.isPending) setSelectedTask(null);
        }}
      >
        <DialogContent className="sm:max-w-xl">
          {selectedTask && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {selectedTask.resource_kind === 'robot'
                    ? <Bot className="h-5 w-5" />
                    : <Cpu className="h-5 w-5" />}
                  {formatFunction(selectedTask.stage)}
                </DialogTitle>
                <DialogDescription>
                  Ongoing function details from the authoritative DockSight ledger.
                </DialogDescription>
              </DialogHeader>
              <dl className="grid grid-cols-1 gap-3 py-2 sm:grid-cols-2">
                <DetailValue label="Resource" value={selectedTask.resource_id ?? 'Unassigned'} />
                <DetailValue label="Resource kind" value={selectedTask.resource_kind === 'robot' ? 'Robot' : 'Control asset'} />
                <DetailValue label="Order" value={selectedTask.order_id} />
                <DetailValue label="Task" value={selectedTask.task_id} />
                <DetailValue label="Warehouse" value={selectedTask.warehouse_id} />
                <DetailValue label="Status" value={selectedTask.display_status} />
              </dl>
              <FunctionTimer task={selectedTask} nowMs={nowMs} />
              {persona !== 'fleet' && (
                <Alert>
                  <ShieldAlert className="h-4 w-4" />
                  <AlertTitle>Fleet Ops role required</AlertTitle>
                  <AlertDescription>
                    This role can inspect ongoing functions but cannot kill an assignment.
                  </AlertDescription>
                </Alert>
              )}
              <DialogFooter>
                <Button variant="outline" onClick={() => setSelectedTask(null)}>Close</Button>
                {persona === 'fleet' && (
                  <Button variant="destructive" onClick={openConfirmation}>
                    Kill function
                  </Button>
                )}
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmOpen} onOpenChange={(open) => {
        if (!open && !killTask.isPending) setConfirmOpen(false);
      }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Kill this function?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                {selectedTask && (
                  <>
                    <p>
                      Kill <strong>{formatFunction(selectedTask.stage)}</strong> on{' '}
                      <strong className="font-mono">{selectedTask.resource_id}</strong> for order{' '}
                      <strong className="font-mono">{selectedTask.order_id}</strong>?
                    </p>
                    <p>
                      DockSight will block this resource, preserve unfinished work, and
                      immediately seek a different eligible resource. If none is available,
                      the function will wait safely for the scheduler.
                    </p>
                  </>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={killTask.isPending}>Keep running</AlertDialogCancel>
            <AlertDialogAction
              disabled={killTask.isPending}
              onClick={(event) => {
                event.preventDefault();
                confirmKill();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {killTask.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Confirm kill
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}