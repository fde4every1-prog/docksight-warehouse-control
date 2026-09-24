import { FormEvent, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useRecoverLifecycleResource } from '@workspace/api-client-react';
import { AlertTriangle, History, Loader2, RotateCcw, Wrench } from 'lucide-react';
import { Role } from '@/contexts/PersonaContext';
import {
  FleetIssue,
  FleetIssueContext,
  useFleetIssue,
  useRepairFleetIssue,
} from '@/hooks/use-fleet-issues';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { FleetOrderImpact } from './FleetOrderImpact';

type Props = {
  issue: FleetIssue | null;
  open: boolean;
  role: Role;
  onOpenChange: (open: boolean) => void;
};

type Drafts = Record<string, Record<string, string>>;

const contextKey = (context: FleetIssueContext) =>
  `${context.entity_type}:${context.entity_id}:${context.revision}`;

function makeDrafts(issue: FleetIssue): Drafts {
  return Object.fromEntries(issue.contexts.map(context => [
    contextKey(context),
    Object.fromEntries(Object.entries(context.values).map(([field, value]) => [field, value ?? ''])),
  ]));
}

const humanize = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());

export function FleetRepairDialog({ issue, open, role, onOpenChange }: Props) {
  const queryClient = useQueryClient();
  const detail = useFleetIssue(role, issue?.id ?? null, open);
  const repair = useRepairFleetIssue(role, issue?.id ?? null);
  const recover = useRecoverLifecycleResource({
    request: { headers: { 'X-Demo-Persona': role } },
  });
  const [drafts, setDrafts] = useState<Drafts>({});
  const [result, setResult] = useState<FleetIssue | null>(null);
  const [snapshot, setSnapshot] = useState<FleetIssue | null>(null);
  const [initializedFor, setInitializedFor] = useState<string | null>(null);
  const [recoverConfirmOpen, setRecoverConfirmOpen] = useState(false);
  const [recoverySucceeded, setRecoverySucceeded] = useState(false);
  const activeIssue = result ?? snapshot ?? issue;
  // Refresh impact without replacing the operator's edit values/revision baseline.
  const impactIssue = detail.data ?? activeIssue;
  const canEdit = role === 'fleet';
  const hasSimulatorBlock = activeIssue?.assignment_blockers.some(
    blocker => blocker.startsWith('Simulator failure block:'),
  ) ?? false;

  useEffect(() => {
    setDrafts({});
    setResult(null);
    setSnapshot(null);
    setInitializedFor(null);
    setRecoverConfirmOpen(false);
    setRecoverySucceeded(false);
    repair.reset();
    recover.reset();
  }, [open, issue?.id]); // Start each selected opening from its freshly fetched detail.

  useEffect(() => {
    if (detail.data && open && !detail.isFetching && initializedFor !== issue?.id) {
      setDrafts(makeDrafts(detail.data));
      setSnapshot(detail.data);
      setInitializedFor(issue?.id ?? null);
    }
  }, [detail.data, detail.isFetching, initializedFor, issue?.id, open]);

  const changed = useMemo(() => {
    if (!snapshot) return false;
    return snapshot.contexts.some(context =>
      Object.entries(context.values).some(([field, value]) =>
        (drafts[contextKey(context)]?.[field] ?? '') !== (value ?? ''),
      ),
    );
  }, [snapshot, drafts]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!snapshot) return;
    repair.mutate({
      fingerprint: snapshot.fingerprint,
      contexts: snapshot.contexts.map(context => ({
        entity_type: context.entity_type,
        entity_id: context.entity_id,
        revision: context.revision,
        values: Object.fromEntries(
          Object.entries(drafts[contextKey(context)] ?? {}).filter(([field, value]) =>
            value !== (context.values[field] ?? ''),
          ),
        ),
      })),
    }, {
      onSuccess: saved => {
        setResult(saved);
        setSnapshot(saved);
        setDrafts(makeDrafts(saved));
      },
    });
  };

  const reloadLatest = async () => {
    if (changed && !window.confirm('Reloading will replace your unsaved edits with the latest server values. Continue?')) {
      return;
    }
    const refreshed = await detail.refetch();
    if (refreshed.isSuccess && refreshed.data) {
      setDrafts(makeDrafts(refreshed.data));
      setSnapshot(refreshed.data);
      setResult(null);
      setInitializedFor(issue?.id ?? null);
      repair.reset();
    }
  };

  const confirmRecovery = () => {
    if (!activeIssue || role !== 'fleet' || recover.isPending) return;
    recover.mutate({ resourceId: activeIssue.entity_id }, {
      onSuccess: async () => {
        setRecoverConfirmOpen(false);
        setRecoverySucceeded(true);
        const removeSimulatorBlock = (current: FleetIssue | null) => current
          ? {
              ...current,
              assignment_blockers: current.assignment_blockers.filter(
                blocker => !blocker.startsWith('Simulator failure block:'),
              ),
            }
          : current;
        setSnapshot(removeSimulatorBlock);
        setResult(removeSimulatorBlock);
        await queryClient.invalidateQueries({
          queryKey: ['personas', role, 'fleet-issues'],
        });
        const refreshed = await detail.refetch();
        if (refreshed.isSuccess && refreshed.data) {
          setDrafts(makeDrafts(refreshed.data));
          setSnapshot(refreshed.data);
          setResult(null);
          setInitializedFor(issue?.id ?? null);
        }
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] w-[calc(100%-1.5rem)] max-w-2xl overflow-y-auto p-4 sm:p-6">
        <DialogHeader className="pr-7">
          <div className="flex flex-wrap items-center gap-2">
            <DialogTitle>{activeIssue?.title ?? 'Fleet issue'}</DialogTitle>
            {impactIssue && <Badge variant={impactIssue.priority === 'P1' ? 'destructive' : 'outline'}>{impactIssue.priority}</Badge>}
          </div>
          <DialogDescription>
            {activeIssue ? `${activeIssue.entity_id} · ${activeIssue.warehouse_id}` : 'Loading latest issue details…'}
          </DialogDescription>
        </DialogHeader>

        {detail.isLoading && !activeIssue?.contexts?.length ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading current readiness values…
          </div>
        ) : detail.error && !detail.data ? (
          <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {detail.error instanceof Error ? detail.error.message : 'Could not load this fleet issue.'}
          </div>
        ) : activeIssue ? (
          <form onSubmit={submit} className="space-y-5">
            {result && (
              <div className="rounded-md border border-green-600/30 bg-green-600/10 p-3 text-sm text-green-700 dark:text-green-400">
                Repair saved. The latest source and assignment status is shown below.
              </div>
            )}

            {recoverySucceeded && (
              <div className="rounded-md border border-green-600/30 bg-green-600/10 p-3 text-sm text-green-700 dark:text-green-400">
                Simulator failure block removed. Source readiness values were not changed.
              </div>
            )}

            {impactIssue && <FleetOrderImpact issue={impactIssue} />}
            <BlockerList title="Source readiness blockers" blockers={activeIssue.blockers} />
            <BlockerList title="Independent assignment blockers" blockers={activeIssue.assignment_blockers} />

            {hasSimulatorBlock && role === 'fleet' && (
              <section className="space-y-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 sm:p-4">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-bold">
                    <RotateCcw className="h-4 w-4" /> Simulator resource block
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Explicitly unblock this resource after it is safe to return to assignment.
                    This does not edit or attest to source health.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setRecoverConfirmOpen(true)}
                  disabled={recover.isPending}
                >
                  {recover.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Mark resource recovered
                </Button>
                {recover.error && (
                  <p role="alert" className="text-sm text-destructive">
                    {recover.error instanceof Error
                      ? recover.error.message
                      : 'The simulator resource block could not be removed.'}
                  </p>
                )}
              </section>
            )}

            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-bold">
                <Wrench className="h-4 w-4" /> Readiness values
              </h3>
              {activeIssue.contexts.length === 0 ? (
                <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                  No source values require editing.
                </p>
              ) : activeIssue.contexts.map((context, contextIndex) => {
                const key = contextKey(context);
                return (
                  <fieldset key={key} disabled={!canEdit || repair.isPending || !!result} className="space-y-3 rounded-lg border p-3 sm:p-4">
                    <legend className="px-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">
                      {humanize(context.entity_type)} · {context.entity_id}
                    </legend>
                    {context.missing && (
                      <div className="text-xs font-medium text-destructive">Required source data is missing. Supply the readiness values below.</div>
                    )}
                    {Object.entries(context.values).map(([field, original]) => {
                      const allowed = context.allowed_values[field] ?? [];
                      const inputId = `fleet-${contextIndex}-${field}`;
                      const value = drafts[key]?.[field] ?? '';
                      return (
                        <div key={field} className="grid gap-1.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:items-center sm:gap-4">
                          <label htmlFor={inputId} className="text-sm font-medium">{humanize(field)}</label>
                          <div>
                            {allowed.length ? (
                              <select
                                id={inputId}
                                value={value}
                                onChange={event => setDrafts(current => ({
                                  ...current,
                                  [key]: { ...current[key], [field]: event.target.value },
                                }))}
                                className="flex h-9 w-full rounded-sm border border-input bg-transparent px-3 text-sm"
                              >
                                <option value="" disabled>Select a value…</option>
                                {allowed.map(option => <option key={option} value={option}>{option}</option>)}
                              </select>
                            ) : (
                              <Input
                                id={inputId}
                                value={value}
                                placeholder={original === null ? 'Missing — enter a value' : undefined}
                                onChange={event => setDrafts(current => ({
                                  ...current,
                                  [key]: { ...current[key], [field]: event.target.value },
                                }))}
                              />
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </fieldset>
                );
              })}
            </div>

            {repair.error && (
              <div role="alert" className="space-y-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                <p>{repair.error instanceof Error ? repair.error.message : 'The repair could not be saved.'} Your edits have been retained.</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => { void reloadLatest(); }}
                  disabled={detail.isFetching}
                >
                  {detail.isFetching ? 'Reloading…' : 'Reload latest values'}
                </Button>
              </div>
            )}

            {activeIssue.events.length > 0 && (
              <section className="space-y-2">
                <h3 className="flex items-center gap-2 text-sm font-bold"><History className="h-4 w-4" /> History</h3>
                <ol className="space-y-2">
                  {[...activeIssue.events].reverse().map((event, index) => (
                    <li key={`${event.at}-${index}`} className="rounded-md bg-muted/50 p-3 text-xs">
                      <div className="flex flex-wrap justify-between gap-2">
                        <span className="font-semibold">{event.action} · {event.persona}</span>
                        <time className="text-muted-foreground">{new Date(event.at).toLocaleString()}</time>
                      </div>
                      <p className="mt-1 text-muted-foreground">{event.reason}</p>
                      <EventChanges details={event.details} />
                    </li>
                  ))}
                </ol>
              </section>
            )}

            <DialogFooter>
              {!canEdit ? (
                <p className="text-sm text-muted-foreground">Only the Fleet persona can repair readiness values.</p>
              ) : result ? (
                <>
                  {result.blockers.length > 0 && result.contexts.length > 0 && (
                    <Button type="button" variant="outline" onClick={() => setResult(null)}>Continue editing</Button>
                  )}
                  <Button type="button" onClick={() => onOpenChange(false)}>Done</Button>
                </>
              ) : (
                <Button type="submit" disabled={!snapshot || !changed || repair.isPending}>
                  {repair.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {repair.isPending ? 'Saving…' : 'Save repair'}
                </Button>
              )}
            </DialogFooter>
          </form>
        ) : null}
      </DialogContent>

      <AlertDialog open={recoverConfirmOpen} onOpenChange={(nextOpen) => {
        if (!nextOpen && !recover.isPending) setRecoverConfirmOpen(false);
      }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark {activeIssue?.entity_id} recovered?</AlertDialogTitle>
            <AlertDialogDescription>
              This explicit action only removes the Fleet Simulator failure block so the
              resource can be considered for future assignments. It does not change,
              repair, or verify any source health values.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={recover.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={recover.isPending}
              onClick={(event) => {
                event.preventDefault();
                confirmRecovery();
              }}
            >
              {recover.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Mark resource recovered
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}

function EventChanges({ details }: { details: unknown }) {
  if (!details || typeof details !== 'object') return null;
  const changes = (details as { changes?: unknown }).changes;
  if (!Array.isArray(changes) || changes.length === 0) return null;
  const validChanges = changes.filter((change): change is {
    entity_type: string;
    entity_id: string;
    field: string;
    before: unknown;
    after: unknown;
  } => (
    !!change
    && typeof change === 'object'
    && typeof change.entity_type === 'string'
    && typeof change.entity_id === 'string'
    && typeof change.field === 'string'
  ));
  if (!validChanges.length) return null;
  const displayValue = (value: unknown) => value === null || value === undefined || value === ''
    ? 'missing'
    : String(value);
  return (
    <ul className="mt-2 space-y-1 border-t pt-2">
      {validChanges.map((change, index) => (
        <li key={`${change.entity_type}-${change.entity_id}-${change.field}-${index}`} className="text-muted-foreground">
          <span className="font-medium text-foreground">
            {humanize(change.entity_type)} {change.entity_id} · {humanize(change.field)}
          </span>
          {': '}
          <span className="line-through">{displayValue(change.before)}</span>
          {' → '}
          <span className="font-medium text-foreground">{displayValue(change.after)}</span>
        </li>
      ))}
    </ul>
  );
}

function BlockerList({ title, blockers }: { title: string; blockers: string[] }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{title}</h3>
      {blockers.length ? (
        <ul className="space-y-1.5">
          {blockers.map((blocker, index) => (
            <li key={`${blocker}-${index}`} className="flex gap-2 rounded-md bg-amber-500/10 p-2 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              <span>{blocker}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">None</p>
      )}
    </section>
  );
}