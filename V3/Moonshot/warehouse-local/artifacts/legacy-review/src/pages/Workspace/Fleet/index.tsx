import { useEffect, useState } from 'react';
import { AlertTriangle, Bot, ChevronLeft, ChevronRight, Search, Wrench } from 'lucide-react';
import { usePersona } from '@/contexts/PersonaContext';
import { type FleetIssue, useFleetIssues } from '@/hooks/use-fleet-issues';
import { FleetRepairDialog } from '@/components/personas/FleetRepairDialog';
import { FleetOrderImpact } from '@/components/personas/FleetOrderImpact';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { WorkspaceQueryError } from '../WorkspaceQueryError';

const PAGE_SIZE = 10;

export default function FleetWorkspace() {
  const { role } = usePersona();
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selectedIssue, setSelectedIssue] = useState<FleetIssue | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const issuesQuery = useFleetIssues(role, offset, search);

  const total = issuesQuery.data?.pagination.total ?? 0;
  const currentOffset = issuesQuery.data?.pagination.offset ?? offset;
  const page = Math.floor(currentOffset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    if (!issuesQuery.data) return;
    if (total > 0 && offset >= total) {
      setOffset(Math.floor((total - 1) / PAGE_SIZE) * PAGE_SIZE);
    } else if (total === 0 && offset !== 0) {
      setOffset(0);
    }
  }, [offset, total, issuesQuery.data]);

  const openIssue = (issue: FleetIssue) => {
    setSelectedIssue(issue);
    setDialogOpen(true);
  };

  if (issuesQuery.error) {
    return <WorkspaceQueryError error={issuesQuery.error} retry={() => { void issuesQuery.refetch(); }} />;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold">
          <Wrench className="h-6 w-6 text-primary" />
          Fleet Operator Workspace
        </h1>
        <p className="mt-1 text-muted-foreground">Review and repair active robot readiness issues.</p>
      </div>

      <section className="space-y-4">
        <div className="flex flex-col justify-between gap-3 border-b pb-3 sm:flex-row sm:items-center">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            <Bot className="h-5 w-5 text-destructive" />
            Active Fleet Issues
            {!issuesQuery.isLoading && <Badge variant="secondary">{total}</Badge>}
          </h2>
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              aria-label="Search active fleet issues"
              placeholder="Search issues or order ID…"
              className="pl-9"
              value={search}
              onChange={event => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
          </div>
        </div>

        {issuesQuery.isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-28 w-full" />)}
          </div>
        ) : issuesQuery.data?.items.length ? (
          <div className="space-y-3">
            {issuesQuery.data.items.map(issue => (
              <FleetIssueCard key={issue.id} issue={issue} onOpen={() => openIssue(issue)} />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed bg-muted/20 p-8 text-center text-muted-foreground">
            {search ? 'No active fleet issues match your search.' : 'No active fleet issues.'}
          </div>
        )}

        <div className="flex flex-col items-center justify-between gap-3 border-t pt-4 sm:flex-row">
          <div className="text-xs text-muted-foreground">
            {total === 0
              ? 'Showing 0 issues'
              : `Showing ${currentOffset + 1}–${Math.min(currentOffset + PAGE_SIZE, total)} of ${total}`}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              aria-label="Previous page"
              onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}
              disabled={offset === 0}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-24 text-center text-xs font-mono">Page {page} of {totalPages}</span>
            <Button
              variant="outline"
              size="sm"
              aria-label="Next page"
              onClick={() => setOffset(value => value + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </section>

      <FleetRepairDialog
        issue={selectedIssue}
        open={dialogOpen}
        role={role}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}

function FleetIssueCard({ issue, onOpen }: { issue: FleetIssue; onOpen: () => void }) {
  const isP1 = issue.priority === 'P1';
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`relative w-full overflow-hidden rounded-lg border bg-card p-4 text-left transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
        isP1 ? 'border-destructive/50' : 'border-amber-500/50'
      }`}
    >
      <span className={`absolute right-0 top-0 h-full w-1 ${isP1 ? 'bg-destructive' : 'bg-amber-500'}`} />
      <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-start">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-bold">
            {isP1 && <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" />}
            <span>{issue.title}</span>
          </div>
          <div className="mt-1 text-sm text-muted-foreground">{issue.entity_id} · {issue.warehouse_id}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant={isP1 ? 'destructive' : 'outline'}>{issue.priority}</Badge>
          <Badge variant="outline" className="uppercase">{issue.status}</Badge>
        </div>
      </div>
      <ul className="mt-3 space-y-1 text-sm text-muted-foreground">
        {issue.blockers.slice(0, 3).map((blocker, index) => <li key={`${blocker}-${index}`}>• {blocker}</li>)}
        {issue.blockers.length > 3 && <li>• {issue.blockers.length - 3} more source blockers</li>}
      </ul>
      <FleetOrderImpact issue={issue} compact />
    </button>
  );
}