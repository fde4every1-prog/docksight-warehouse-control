import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Clock, Server, CheckCircle2, XCircle, Info, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { MaintenanceModel, MaintenanceEvaluation } from '@/hooks/use-predictive-maintenance';

export function ModelSummaryCard({ model }: { model: MaintenanceModel }) {
  const [expanded, setExpanded] = useState(false);
  const { summary, freshness, evaluation = [] } = model;
  
  if (!summary) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">Model Information</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-muted-foreground italic">
            Summary information is not available.
          </div>
        </CardContent>
      </Card>
    );
  }

  const { snapshot_only, days_since_observation, stale } = freshness;
  const test = summary.metrics?.test?.all;
  const events = summary.metrics?.test_event_level;

  // Render evaluation metrics for validation and test splits
  const renderEvaluation = (evals: MaintenanceEvaluation[]) => {
    if (evals.length === 0) {
      return <div className="text-xs text-muted-foreground italic mt-2">No evaluation metrics recorded.</div>;
    }
    
    return (
      <div className="mt-4 border rounded-md overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-muted text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">Split/Model</th>
              <th className="px-3 py-2 font-medium text-right">Val AP</th>
              <th className="px-3 py-2 font-medium text-right">Test AP</th>
              <th className="px-3 py-2 font-medium text-right">Test AUC</th>
              <th className="px-3 py-2 font-medium text-right">Brier</th>
            </tr>
          </thead>
          <tbody className="divide-y font-mono">
            {evals.map((ev, i) => (
              <tr key={i} className={cn(ev.model === summary.selected_model && "bg-primary/5 font-bold text-foreground")}>
                <td className="px-3 py-2">{ev.model}</td>
                <td className="px-3 py-2 text-right">{ev.validation_average_precision?.toFixed(3) ?? '—'}</td>
                <td className="px-3 py-2 text-right">{ev.test_average_precision?.toFixed(3) ?? '—'}</td>
                <td className="px-3 py-2 text-right">{ev.test_roc_auc?.toFixed(3) ?? '—'}</td>
                <td className="px-3 py-2 text-right">{ev.test_brier_score?.toFixed(3) ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {summary.validation_status !== 'valid' && (
          <div className="p-2 bg-destructive/10 text-destructive text-[10px] font-sans flex items-start gap-1.5 border-t border-destructive/20">
            <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
            <p>
              {summary.validation_status === 'experimental_holdout_lift'
                ? 'Retrospective testing shows lift over baseline, but many alerts are false alarms. This is not operational validation.'
                : 'Performance has not demonstrated sufficient predictive value.'}
              {' '}Do not use for automatic scheduling or robot shutdown.
            </p>
          </div>
        )}
      </div>
    );
  };

  return (
    <Card className="flex flex-col h-full border-primary/20 shadow-sm">
      <CardHeader className="bg-muted/30 pb-4 border-b">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base flex flex-col gap-1">
            <span className="flex items-center gap-2">
              <Server className="h-4 w-4 text-muted-foreground" />
              Model Summary
            </span>
          </CardTitle>
          <Badge variant={summary.validation_status === 'valid' ? 'secondary' : 'destructive'} className="uppercase text-[10px]">
            Experimental
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
          <strong>Advisory Only:</strong> Predictions are unverified experimental insights based on historic snapshots. 
          No physical fitness claims are made.
        </p>
      </CardHeader>
      
      <CardContent className="pt-4 space-y-5 text-sm flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <div>
            <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Status</div>
            <div className="flex items-center gap-1.5">
              {stale ? <XCircle className="w-3.5 h-3.5 text-destructive" /> : <CheckCircle2 className="w-3.5 h-3.5 text-success" />}
              <span className={cn(stale ? "text-destructive font-medium" : "text-success font-medium")}>
                {stale ? 'Stale snapshot' : 'Snapshot ready'}
              </span>
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Freshness</div>
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="font-mono text-xs">
                {days_since_observation != null ? `${days_since_observation}d ago` : 'Unknown'}
              </span>
            </div>
          </div>
          <div className="col-span-2">
            <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Observation Window</div>
            <div className="font-mono text-xs">
              {summary.data_start.slice(0, 10)} to {summary.data_end.slice(0, 10)}
            </div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Horizon</div>
            <div className="font-mono text-xs">{summary.horizon_days} days</div>
          </div>
          <div>
            <div className="text-[10px] text-muted-foreground uppercase font-bold mb-1">Scope</div>
            <div className="font-mono text-xs">{summary.robot_count} robots ({summary.row_count} rows)</div>
          </div>
        </div>

        {snapshot_only && (
          <div className="flex items-start gap-2 text-xs bg-amber-50 text-amber-950 p-3 rounded-md border border-amber-200">
            <Info className="w-4 h-4 shrink-0 mt-0.5" />
            <p><strong>Historic Snapshot:</strong> Current real-time telemetry is not ingested. Risk is based on past states.</p>
          </div>
        )}

        <div className="space-y-1">
          <h4 className="text-xs font-bold uppercase text-muted-foreground">Evaluation Metrics</h4>
          {renderEvaluation(evaluation)}
          {test && (
            <div className="mt-4 space-y-2 text-xs leading-relaxed border rounded-md p-3">
              <p className="font-semibold">What the held-out test means</p>
              <p><strong>{(test.precision_at_threshold * 100).toFixed(1)}%</strong> of flagged robot-days were followed by a failure within seven days, versus a <strong>{(test.prevalence * 100).toFixed(1)}%</strong> underlying rate.</p>
              {events && <p>Warned ahead of <strong>{events.events_detected} of {events.events}</strong> distinct failures ({(events.event_recall * 100).toFixed(1)}%) with a complete seven-day evaluation window.</p>}
              <p className="text-muted-foreground">Repeated daily warnings are not independent events. Risk estimates have not been externally calibrated.</p>
            </div>
          )}
        </div>

        <div className="pt-2 border-t">
          <Button 
            variant="ghost" 
            size="sm" 
            className="w-full flex items-center justify-between text-xs h-8"
            onClick={() => setExpanded(!expanded)}
          >
            <span>Advanced Details</span>
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
          
          {expanded && (
            <div className="mt-3 space-y-4 animate-in slide-in-from-top-2 duration-200">
              <div className="space-y-1.5">
                <div className="text-[10px] text-muted-foreground uppercase font-bold">Top Features</div>
                <div className="flex flex-wrap gap-1.5">
                  {(summary.feature_importance || []).slice(0, 5).map(f => (
                    <Badge key={f.feature} variant="outline" className="font-mono text-[10px]">
                      {f.feature} ({(f.importance * 100).toFixed(1)}%)
                    </Badge>
                  ))}
                  {(!summary.feature_importance || summary.feature_importance.length === 0) && (
                    <span className="text-xs text-muted-foreground italic">None available</span>
                  )}
                </div>
              </div>
              
              {summary.warnings && summary.warnings.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[10px] text-muted-foreground uppercase font-bold text-warning">Warnings</div>
                  <ul className="list-disc pl-4 text-xs text-muted-foreground space-y-1">
                    {summary.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              <div className="space-y-1.5">
                <div className="text-[10px] text-muted-foreground uppercase font-bold">Model ID & Threshold</div>
                <div className="text-xs font-mono text-muted-foreground break-all">
                  {summary.model_id} (th: {summary.threshold.toFixed(2)})
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
