import React, { useState, useEffect } from 'react';
import { useGetReviewOverview, useInspectLegacyAllocator } from '@workspace/api-client-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CodeBlock } from '@/components/CodeBlock';
import { AlertTriangle, Info, Shield, Check, Settings2, Code2, Link as LinkIcon, Database, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Link } from 'wouter';

export function Allocator() {
  const { data: overview } = useGetReviewOverview();
  const inspectAllocator = useInspectLegacyAllocator();

  const [site, setSite] = useState('');
  const [payloadKg, setPayloadKg] = useState('100');
  const [isStale, setIsStale] = useState(false);

  // Mark results stale if inputs change
  useEffect(() => {
    if (inspectAllocator.data) {
      setIsStale(true);
    }
  }, [site, payloadKg]);

  const handleInspect = () => {
    if (!site || !payloadKg) return;
    setIsStale(false);
    inspectAllocator.mutate({
      data: {
        site,
        payload_kg: Number(payloadKg)
      }
    });
  };

  return (
    <div className="p-6 space-y-8 font-sans max-w-7xl mx-auto h-full flex flex-col">
      <div className="flex flex-col gap-2 border-b pb-6 shrink-0">
        <h1 className="text-3xl font-bold tracking-tight">Legacy Allocator Sandbox</h1>
        <p className="text-muted-foreground max-w-3xl">
          Hypothetical inputs for testing legacy routing rules. This interface NEVER dispatches physical equipment. Site selection purely restricts the inspection set.
        </p>
        <div className="flex gap-2 mt-2">
          <Badge variant="destructive" className="uppercase text-xs flex items-center gap-1">
            <Shield className="h-3 w-3" /> NO DISPATCH (INSPECTION ONLY)
          </Badge>
          <a href="/api/docs" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-mono ml-4">
            <LinkIcon className="h-3 w-3" /> /api/docs (Legacy Logic)
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
        
        {/* Left Column: Input Panel */}
        <div className="xl:col-span-1 space-y-6 flex flex-col">
          <Card className="border-t-4 border-t-primary shadow-md">
            <CardHeader className="bg-muted/30 pb-4 border-b">
              <CardTitle className="text-sm uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                <Settings2 className="h-4 w-4" /> Hypothetical Input
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-6 space-y-6">
              
              <div className="space-y-2">
                <label className="text-xs font-bold text-muted-foreground uppercase font-mono">Target Site (Inspection Set)</label>
                <Select value={site} onChange={(e) => setSite(e.target.value)}>
                  <option value="">Select a site...</option>
                  {overview?.sites.map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
                  <Info className="h-3 w-3 mt-0.5 shrink-0" />
                  Limits evaluation to robots available at this site.
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-bold text-muted-foreground uppercase font-mono">Hypothetical Payload (kg)</label>
                <Input 
                  type="number" 
                  value={payloadKg}
                  onChange={(e) => setPayloadKg(e.target.value)}
                  min="0"
                  max="100000"
                  className="font-mono"
                />
              </div>

              <Button 
                onClick={handleInspect} 
                disabled={!site || !payloadKg || inspectAllocator.isPending}
                className="w-full font-mono font-bold tracking-wider"
              >
                {inspectAllocator.isPending ? 'EVALUATING...' : 'EVALUATE LEGACY RULES'}
              </Button>

            </CardContent>
          </Card>

          <Card className="flex-1 flex flex-col overflow-hidden border">
            <CardHeader className="py-3 px-4 border-b bg-muted/20 shrink-0">
              <CardTitle className="text-xs font-mono uppercase text-muted-foreground flex justify-between items-center">
                <span>Original Source Logic</span>
                <Code2 className="h-4 w-4" />
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 flex-1 overflow-hidden">
              {overview?.allocatorSource ? (
                 <CodeBlock code={overview.allocatorSource} className="border-0 rounded-none h-full" />
              ) : (
                <div className="p-4 text-xs text-muted-foreground font-mono">Source unavailable.</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Output Evaluation */}
        <div className="xl:col-span-2 flex flex-col space-y-4">
          {!inspectAllocator.data && !inspectAllocator.isPending && (
             <div className="flex-1 border-2 border-dashed rounded-sm flex flex-col items-center justify-center text-muted-foreground p-12 bg-muted/10">
                <Database className="h-12 w-12 mb-4 opacity-20" />
                <h3 className="text-lg font-bold mb-2">Awaiting Evaluation</h3>
                <p className="text-sm max-w-sm text-center">
                  Configure hypothetical inputs and click Evaluate to see how the legacy allocator scores available robots.
                </p>
             </div>
          )}

          {inspectAllocator.isPending && (
            <div className="flex-1 border rounded-sm flex flex-col items-center justify-center p-12 bg-muted/5 animate-pulse">
                <Settings2 className="h-10 w-10 animate-spin text-primary opacity-50 mb-4" />
                <p className="text-sm font-mono tracking-widest text-primary">RUNNING LEGACY ALLOCATOR...</p>
            </div>
          )}

          {inspectAllocator.data && (
            <div className={cn("space-y-6 transition-opacity duration-300", isStale ? "opacity-50 grayscale-[50%]" : "opacity-100")}>
              
              {isStale && (
                <div className="bg-warning text-warning-foreground p-3 text-sm font-bold flex items-center justify-center gap-2 rounded-sm shadow-sm animate-pulse">
                  <AlertTriangle className="h-4 w-4" /> 
                  INPUTS CHANGED. RESULTS STALE.
                </div>
              )}

              {/* Header Stats */}
              <div className="grid grid-cols-3 gap-4">
                <div className="border bg-card p-4 rounded-sm flex flex-col justify-center items-center text-center">
                  <span className="text-3xl font-mono font-bold text-primary">{inspectAllocator.data.inputCount}</span>
                  <span className="text-xs uppercase text-muted-foreground tracking-wider font-bold mt-1">Total Checked</span>
                </div>
                <div className="border bg-card p-4 rounded-sm flex flex-col justify-center items-center text-center">
                  <span className="text-3xl font-mono font-bold text-success">{inspectAllocator.data.eligibleCount}</span>
                  <span className="text-xs uppercase text-muted-foreground tracking-wider font-bold mt-1">Eligible</span>
                </div>
                <div className="border bg-card p-4 rounded-sm flex flex-col justify-center items-center text-center">
                  <span className="text-3xl font-mono font-bold">{inspectAllocator.data.taskPayload}</span>
                  <span className="text-xs uppercase text-muted-foreground tracking-wider font-bold mt-1">Task Payload (kg)</span>
                </div>
              </div>

              {/* Selected Result */}
              <Card className={cn(
                "border-2 shadow-md relative overflow-hidden", 
                inspectAllocator.data.selected ? "border-success" : "border-destructive"
              )}>
                <div className={cn(
                  "absolute top-0 right-0 px-4 py-1 text-xs font-bold uppercase tracking-widest rounded-bl-sm",
                  inspectAllocator.data.selected ? "bg-success text-success-foreground" : "bg-destructive text-destructive-foreground"
                )}>
                  {inspectAllocator.data.selected ? 'Selected Candidate' : 'Allocation Failed'}
                </div>
                <CardHeader>
                  <CardTitle className="text-xl font-bold font-mono">Allocation Result</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-sm font-mono text-muted-foreground mb-6 p-4 bg-muted rounded-sm border">
                    <span className="font-bold text-foreground">Explanation:</span> {inspectAllocator.data.explanation}
                  </div>
                  
                  {inspectAllocator.data.selected && (
                    <div className="space-y-4">
                      <div className="flex items-center gap-4 border-b pb-4">
                        <div className="text-4xl font-bold font-mono text-success">
                          {inspectAllocator.data.selected.score.toFixed(2)}
                        </div>
                        <div className="text-sm text-muted-foreground font-mono uppercase">
                          Legacy Score
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                        {Object.entries(inspectAllocator.data.selected.robot).map(([k, v]) => (
                          <div key={k} className="border border-border/50 p-2 rounded-sm bg-muted/20">
                            <div className="text-[10px] text-muted-foreground uppercase">{k}</div>
                            <div className="font-mono text-sm font-bold truncate">{v || 'null'}</div>
                          </div>
                        ))}
                      </div>

                      {inspectAllocator.data.selected.flags.length > 0 && (
                        <div className="mt-4 pt-4 border-t border-dashed">
                          <h4 className="text-xs font-bold text-warning uppercase mb-2">Review Annotations</h4>
                          <div className="flex flex-wrap gap-2">
                            {inspectAllocator.data.selected.flags.map(f => (
                              <Badge key={f} variant="warning" className="text-xs font-mono">{f}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Runner Up Candidates */}
              {inspectAllocator.data.candidates.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-muted-foreground border-b pb-2">
                    Top Candidates (Runner-ups)
                  </h3>
                  <div className="space-y-2">
                    {inspectAllocator.data.candidates.map((candidate, idx) => (
                      <div key={idx} className="bg-card border p-3 rounded-sm flex items-center justify-between hover:bg-muted/50 transition-colors">
                        <div className="flex items-center gap-4">
                          <div className="w-16 text-center font-mono font-bold text-lg bg-muted py-1 rounded-sm">
                            {candidate.score.toFixed(1)}
                          </div>
                          <div className="font-mono text-sm text-muted-foreground">
                            {candidate.robot['id'] || candidate.robot['name'] || `Candidate ${idx+1}`}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          {candidate.flags.length > 0 && (
                             <Badge variant="warning" className="text-[10px]">{candidate.flags.length} FLAGS</Badge>
                          )}
                          <Button variant="ghost" size="sm" className="h-6 text-xs px-2 opacity-50 cursor-default">
                             Legacy Rank #{idx+2}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}

        </div>
      </div>
    </div>
  );
}
