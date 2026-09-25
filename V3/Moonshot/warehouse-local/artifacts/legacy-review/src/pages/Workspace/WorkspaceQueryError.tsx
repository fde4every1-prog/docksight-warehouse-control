import { Button } from '@/components/ui/button';

export function WorkspaceQueryError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div role="alert" className="m-6 rounded border border-destructive/40 bg-card p-6 space-y-3">
      <h2 className="font-bold">Workspace data could not be loaded</h2>
      <p className="text-sm text-muted-foreground">{error instanceof Error ? error.message : 'Please retry the request.'}</p>
      <Button onClick={retry} variant="outline">Retry</Button>
    </div>
  );
}