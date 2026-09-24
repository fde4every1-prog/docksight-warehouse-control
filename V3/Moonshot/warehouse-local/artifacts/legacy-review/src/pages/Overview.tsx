import React from 'react';
import { useGetReviewOverview } from '@workspace/api-client-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { CodeBlock } from '@/components/CodeBlock';
import { AlertCircle, Target, Database, FileWarning, Key } from 'lucide-react';

export function Overview() {
  const { data: overview, isLoading, error } = useGetReviewOverview();

  if (isLoading) {
    return (
      <div className="p-6 space-y-6">
        <h1 className="text-2xl font-bold font-sans">System Diagnostics</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-32 w-full" />)}
        </div>
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  if (error || !overview) {
    return (
      <div className="p-6 text-destructive flex items-center gap-2">
        <AlertCircle /> Failed to load review overview.
      </div>
    );
  }

  const aliasCollisions = overview.diagnostics['alias_collisions'] || 0;

  return (
    <div className="p-6 space-y-8 font-sans max-w-7xl mx-auto">
      <div className="flex flex-col gap-2 border-b pb-6">
        <h1 className="text-3xl font-bold tracking-tight">System Diagnostics</h1>
        <p className="text-muted-foreground max-w-3xl">
          High-level overview of the original synthetic warehouse code state.
          This is a read-only environment to inspect legacy rules and data anomalies.
        </p>
        <div className="flex flex-wrap gap-2 mt-2">
          {overview.sites.map(site => (
            <Badge key={site} variant="outline" className="text-xs bg-muted">SITE: {site}</Badge>
          ))}
          <Badge variant="warning" className="text-xs flex items-center gap-1">
            <Target className="h-3 w-3" /> ALL-SITE SCOPE
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card className="border-t-4 border-t-primary">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono text-muted-foreground uppercase flex justify-between">
              Total Records
              <Database className="h-4 w-4" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono">
              {Object.values(overview.counts).reduce((a, b) => a + b, 0).toLocaleString()}
            </div>
            <div className="text-xs text-muted-foreground mt-2 grid grid-cols-2 gap-1 font-mono">
              {Object.entries(overview.counts).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-border pb-1">
                  <span>{k}</span> <span>{v}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border-t-4 border-t-warning">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono text-muted-foreground uppercase flex justify-between">
              Alias Collisions
              <Key className="h-4 w-4" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold font-mono text-warning">
              {aliasCollisions.toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Repeated alias groups (not proven identity collisions). Check diagnostics for resolution priority.
            </p>
          </CardContent>
        </Card>

        <Card className="border-t-4 border-t-destructive md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono text-muted-foreground uppercase flex justify-between">
              System Limitations
              <FileWarning className="h-4 w-4" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 space-y-1 text-sm font-mono">
              {overview.limitations.map((limit, i) => (
                <li key={i}>{limit}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-4">
          <h2 className="text-xl font-bold tracking-tight">Original Diagnostics</h2>
          <div className="bg-muted p-4 rounded-sm border font-mono text-sm grid grid-cols-2 gap-x-4 gap-y-2">
             {Object.entries(overview.diagnostics).map(([k, v]) => (
                <div key={k} className="flex justify-between py-1 border-b border-border/50">
                  <span className="text-muted-foreground">{k}</span>
                  <span className={v > 0 ? "text-primary font-bold" : ""}>{v}</span>
                </div>
              ))}
          </div>
        </div>
        
        <div className="space-y-4">
          <h2 className="text-xl font-bold tracking-tight">Operational Snapshot</h2>
          <div className="bg-card border p-4 rounded-sm">
            <Badge variant="destructive" className="mb-2 uppercase text-xs">Read Only</Badge>
            <p className="text-sm text-muted-foreground font-mono leading-relaxed whitespace-pre-wrap">
              {overview.snapshot}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
