import React, { useState, useEffect, useRef } from 'react';
import { Header } from '@/components/layout/header';
import { IsometricMap } from '@/components/transfer-lab/isometric-map';
import { 
  useTransferPreview, 
  useImportExcel, 
  useTransferScenario, 
  usePatchScenario,
  useSuggestTransferBatching, 
  useCompareTransferBatching, 
  RowPatch,
  CompareTransferResponse
} from '@/hooks/use-transfer-batching';
import { ComparisonPlayback } from '@/components/transfer-lab/comparison-playback';
import { Loader2, FileUp, AlertTriangle, CheckCircle2, ChevronRight, ChevronLeft, ChevronDown, ChevronUp, Download, Save, Bot, Ban } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { formatApiError } from '@/lib/api-error';

export default function TransferLab() {
  const [mode, setMode] = useState<'live' | 'synthetic_demo'>('live');
  const { data: preview, isLoading: isLoadingPreview, error: previewError, refetch: refetchPreview } = useTransferPreview(mode);
  const importMutation = useImportExcel();
  const patchMutation = usePatchScenario();
  const suggestMutation = useSuggestTransferBatching();
  const compareMutation = useCompareTransferBatching();
  const { toast } = useToast();

  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [isFleetDetailsExpanded, setIsFleetDetailsExpanded] = useState(false);
  const { data: scenario, isLoading: isLoadingScenario } = useTransferScenario(scenarioId);

  // Local state for edits
  const [rowEdits, setRowEdits] = useState<Record<string, RowPatch>>({});
  const scenarioRevisionRef = useRef<number | undefined>(scenario?.revision);
  
  const [suggestion, setSuggestion] = useState<any | null>(null);
  const [comparison, setComparison] = useState<CompareTransferResponse | null>(null);
  
  const generationRef = useRef<number>(0);

  useEffect(() => {
    scenarioRevisionRef.current = scenario?.revision;
  }, [scenario]);

  const handleReset = () => {
    setComparison(null);
  };

  const invalidateResult = () => {
    generationRef.current += 1;
    setSuggestion(null);
    setComparison(null);
    handleReset();
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !preview?.snapshot?.snapshot_id) return;

    invalidateResult();
    const reqGen = generationRef.current;
    importMutation.mutate({ file, snapshot_id: preview.snapshot.snapshot_id }, {
      onSuccess: (data) => {
        if (generationRef.current !== reqGen) return;
        setScenarioId(data.scenario_id);
        setIsFleetDetailsExpanded(false);
        setStep(2);
        toast({ title: 'File uploaded and parsed' });
      },
      onError: (err) => {
        if (generationRef.current !== reqGen) return;
        toast({ title: 'Upload failed', description: err.message, variant: 'destructive' });
      }
    });
    // Reset file input
    e.target.value = '';
  };

  const handleDownloadTemplate = () => {
    if (!preview?.snapshot?.snapshot_id) return;
    window.open(`/api/batching/transfer/template?snapshot_id=${encodeURIComponent(preview.snapshot.snapshot_id)}`, '_blank');
  };

  const handleRowEdit = (rowId: string, field: 'order_id' | 'order_cutoff', value: string) => {
    invalidateResult();
    setRowEdits(prev => ({
      ...prev,
      [rowId]: {
        ...prev[rowId],
        row_id: rowId,
        [field]: value || null
      }
    }));
  };

  const saveRowEdits = () => {
    if (!scenario) return;
    const patches = Object.values(rowEdits);
    if (patches.length === 0) return;

    invalidateResult();
    patchMutation.mutate({
      scenario_id: scenario.scenario_id,
      revision: scenario.revision,
      rows: patches
    }, {
      onSuccess: () => {
        setRowEdits({});
        toast({ title: 'Rows updated' });
      },
      onError: (err) => {
        toast({ title: 'Update failed', description: err.message, variant: 'destructive' });
      }
    });
  };

  const handleRunSuggest = () => {
    if (!scenario) return;
    invalidateResult();
    const reqGen = generationRef.current;

    suggestMutation.mutate({
      scenario_id: scenario.scenario_id,
      revision: scenario.revision
    }, {
      onSuccess: (recData) => {
        if (generationRef.current !== reqGen || recData.revision !== scenarioRevisionRef.current) return;
        setSuggestion(recData);
        toast({ title: 'LLM generated batched plan' });
      },
      onError: (err) => {
        if (generationRef.current !== reqGen) return;
        toast({ title: 'LLM Planning failed', description: err.message, variant: 'destructive' });
      }
    });
  };

  const handleRunCompare = () => {
    if (!scenario || !suggestion) return;
    handleReset();
    const reqGen = generationRef.current;
    
    compareMutation.mutate({
      scenario_id: scenario.scenario_id,
      revision: scenario.revision,
      recommendation_id: suggestion.recommendation_id
    }, {
      onSuccess: (compData) => {
        if (
          generationRef.current !== reqGen ||
          scenarioRevisionRef.current !== scenario.revision ||
          compData.scenario_id !== scenario.scenario_id
        ) return;
        setComparison(compData);
        toast({ title: 'Comparison ready' });
      },
      onError: (err) => {
        if (generationRef.current !== reqGen) return;
        toast({ title: 'Comparison failed', description: err.message, variant: 'destructive' });
      }
    });
  };

  if (isLoadingPreview) {
    return (
      <div className="min-h-[100dvh] bg-background flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (previewError || !preview) {
    return (
      <div className="min-h-[100dvh] bg-background flex flex-col">
        <Header />
        <div className="flex-1 p-8">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Cannot load Transfer Lab</AlertTitle>
            <AlertDescription>{previewError?.message || "Failed to load live snapshot"}</AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  const mapToRender = scenario?.map || preview.map;
  const candidates = preview.robot_candidates || [];
  const eligibleCandidates = candidates.filter(robot => robot.eligible);
  const blockedCandidates = candidates.filter(robot => !robot.eligible);
  const fleetRobots = preview.robots.filter(robot => robot.eligible);
  const hasPendingEdits = Object.keys(rowEdits).length > 0;
  const allRowsValid = scenario
    ? scenario.valid && scenario.errors.length === 0 && scenario.rows.every(row => row.errors.length === 0)
    : false;

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col overflow-hidden">
      <Header />
      <div className="border-b bg-amber-50 px-4 py-2 flex items-center justify-between">
        <div className="text-xs text-amber-950 font-medium">
          DC-01 Transfer Batching Sandbox · {preview.mode === 'synthetic_demo' ? 'Synthetic demo data' : 'Frozen warehouse snapshot'} · {preview.ready ? 'Replay data ready · not live robot control' : 'Not ready'}
        </div>
        <div className="flex items-center gap-2">
          <Button 
            variant="outline" size="sm" className="h-6 text-[10px]" 
            onClick={() => {
              generationRef.current += 1;
              scenarioRevisionRef.current = undefined;
              setMode(prev => prev === 'live' ? 'synthetic_demo' : 'live');
              setScenarioId(null);
              setIsFleetDetailsExpanded(false);
              setRowEdits({});
              setStep(1);
              setSuggestion(null);
              setComparison(null);
              handleReset();
            }}
          >
            {mode === 'live' ? 'Switch to Synthetic Demo' : 'Switch to Live Data'}
          </Button>
          <Button variant="ghost" size="sm" className="h-6 text-[10px]" onClick={() => {
            invalidateResult();
            scenarioRevisionRef.current = undefined;
            setScenarioId(null);
            setIsFleetDetailsExpanded(false);
            setRowEdits({});
            setStep(1);
            void refetchPreview();
          }}>
            Refresh Snapshot
          </Button>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Sidebar: Controls */}
        <div className="w-full lg:w-[450px] border-r bg-card flex flex-col min-h-0 z-10 shrink-0 shadow-sm">
          <div className="p-4 border-b">
            <h2 className="text-lg font-bold font-mono uppercase tracking-tight">Transfer Lab</h2>
            <p className="text-sm text-muted-foreground">Optimize order bin sequences</p>
          </div>
          
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-6">
              
              {/* Step 1: Upload */}
              <div className={`space-y-3 ${step > 1 ? 'opacity-50' : ''}`}>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step >= 1 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>1</div>
                  Upload Orders (XLSX)
                </div>
                {step === 1 && (
                  <Card className="border-dashed bg-muted/30">
                    <CardContent className="p-6 flex flex-col items-center justify-center gap-3 text-center">
                      <FileUp className="h-8 w-8 text-muted-foreground" />
                      <div className="space-y-1">
                        <Label htmlFor="file-upload" className="cursor-pointer text-primary hover:underline font-medium">
                          Click to upload
                        </Label>
                        <input id="file-upload" type="file" accept=".xlsx" className="hidden" onChange={handleFileUpload} />
                        <p className="text-xs text-muted-foreground">Order ID, SKU, Qty, Cut-off</p>
                      </div>
                      <Button variant="outline" size="sm" onClick={handleDownloadTemplate} className="w-full mt-2">
                        <Download className="h-4 w-4 mr-2" /> Download Template
                      </Button>
                      {importMutation.isPending && (
                        <div className="flex items-center gap-2 text-sm text-primary mt-2">
                          <Loader2 className="h-4 w-4 animate-spin" /> Uploading & Validating...
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Step 2: Review & Enrich */}
              <div className={`space-y-3 ${step < 2 ? 'opacity-50' : ''}`}>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step >= 2 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>2</div>
                  Validation & Repair
                </div>
                {step === 2 && scenario && (
                  <div className="space-y-3">
                    <div className="text-[10px] text-muted-foreground border-l-2 border-primary/50 pl-2 py-1">
                      <p><strong>Provenance:</strong> Live DC-01 snapshot</p>
                      <p><strong>Time:</strong> {scenario.clock.at} ({scenario.clock.timezone})</p>
                    </div>
                    
                    {scenario.errors.length > 0 && (
                      <Alert variant="destructive" className="py-2 px-3">
                        <AlertDescription className="text-xs font-mono">
                           {scenario.errors.map((e, i) => <div key={i}>{formatApiError(e)}</div>)}
                        </AlertDescription>
                      </Alert>
                    )}

                    <div className="rounded-md border overflow-hidden text-xs">
                      <table className="w-full">
                        <thead className="bg-muted">
                          <tr>
                            <th className="p-2 text-left">SKU / Qty</th>
                            <th className="p-2 text-left">Stock / Loc</th>
                            <th className="p-2 text-left">Order ID / Cut-off</th>
                            <th className="p-2 text-center">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y bg-card">
                          {scenario.rows.map((r) => {
                            const edit = rowEdits[r.row_id];
                            const currentOrderId = edit?.order_id !== undefined ? edit.order_id : (r.order_id || '');
                            const currentCutoff = edit?.order_cutoff !== undefined ? edit.order_cutoff : (r.order_cutoff || '');
                            const localErrors = edit ? [
                              ...(!(currentOrderId || '').trim() ? ['Order ID is required'] : []),
                              ...(!(currentCutoff || '').trim() ? ['Cut-off is required'] : []),
                            ] : [];
                            
                            return (
                              <tr key={r.row_id} className={(edit ? localErrors.length > 0 : r.errors.length > 0) ? 'bg-red-50/50 dark:bg-red-950/20' : ''}>
                                <td className="p-2 align-top">
                                  <div className="font-mono font-medium truncate max-w-[120px]" title={r.sku}>{r.sku}</div>
                                  <div className="text-muted-foreground">Qty: {r.quantity}</div>
                                </td>
                                <td className="p-2 align-top text-muted-foreground">
                                  {r.allocations?.map((a: any, i: number) => (
                                    <div key={i} className="text-[10px] truncate max-w-[150px]" title={`Allocated: ${a.quantity} from ${a.bin_id} (${a.zone_id})`}>
                                      {a.quantity} @ {a.bin_id} ({a.zone_id})
                                    </div>
                                  ))}
                                  {(!r.allocations || r.allocations.length === 0) && 'No stock allocated'}
                                  <div className="mt-1 text-[10px] font-mono">
                                    {r.unit_weight_kg != null ? `Wt: ${(r.unit_weight_kg * r.quantity).toFixed(1)}kg` : 'Wt: Unknown'}
                                  </div>
                                </td>
                                <td className="p-2 space-y-1 align-top">
                                  <input 
                                    className="w-full bg-background border rounded px-1.5 py-0.5 font-mono text-[10px]"
                                    value={currentOrderId || ''}
                                    placeholder="Order ID"
                                    onChange={(e) => handleRowEdit(r.row_id, 'order_id', e.target.value)}
                                  />
                                  <input 
                                    className="w-full bg-background border rounded px-1.5 py-0.5 font-mono text-[10px]"
                                    value={currentCutoff || ''}
                                    placeholder="YYYY-MM-DDTHH:MM:SSZ"
                                    onChange={(e) => handleRowEdit(r.row_id, 'order_cutoff', e.target.value)}
                                  />
                                </td>
                                <td className="p-2 text-left align-top text-[10px]">
                                  {edit ? (
                                    localErrors.length > 0 ? (
                                      <div className="text-red-600 flex flex-col gap-1">
                                        {localErrors.map(message => (
                                          <span key={message} className="leading-tight block">- {message}</span>
                                        ))}
                                        <span className="text-muted-foreground">Unsaved draft</span>
                                      </div>
                                    ) : (
                                      <div className="text-amber-700 dark:text-amber-400">Unsaved draft · save to validate</div>
                                    )
                                  ) : r.errors.length === 0 ? (
                                    <div className="flex items-center text-emerald-600 justify-center h-full">
                                      <CheckCircle2 className="h-4 w-4" />
                                    </div>
                                  ) : (
                                    <div className="text-red-600 flex flex-col gap-1">
                                      {r.errors.map((e, idx) => (
                                        <span key={idx} className="leading-tight block">- {e.message}</span>
                                      ))}
                                    </div>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    
                    {hasPendingEdits && (
                      <Button size="sm" className="w-full" onClick={saveRowEdits} disabled={patchMutation.isPending}>
                        {patchMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2"/> : <Save className="h-4 w-4 mr-2" />}
                        Save Edits
                      </Button>
                    )}

                    <Button className="w-full" onClick={() => setStep(3)} disabled={hasPendingEdits || !allRowsValid}>
                      Confirm Snapshot <ChevronRight className="h-4 w-4 ml-2" />
                    </Button>
                  </div>
                )}
              </div>

              {/* Step 3: Fleet review */}
              <div className={`space-y-3 ${step < 3 ? 'opacity-50' : ''}`}>
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs ${step >= 3 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>3</div>
                   Review Transfer Fleet
                </div>
                {step === 3 && scenario && (
                  <div className="space-y-3">
                    <div className="rounded-md border bg-muted/30 p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="flex items-center gap-2 text-sm font-medium">
                          <Bot className="h-4 w-4 text-emerald-600" />
                          {eligibleCandidates.length} eligible
                        </span>
                        <span className="flex items-center gap-2 text-sm text-muted-foreground">
                          <Ban className="h-4 w-4" />
                          {blockedCandidates.length} excluded
                        </span>
                      </div>
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        Every eligible DC-01 robot is included automatically in this run.
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="mt-3 w-full justify-between bg-background"
                        aria-expanded={isFleetDetailsExpanded}
                        aria-controls="fleet-candidate-details"
                        onClick={() => setIsFleetDetailsExpanded(prev => !prev)}
                      >
                        <span>{isFleetDetailsExpanded ? 'Hide fleet details' : 'Show fleet details'}</span>
                        {isFleetDetailsExpanded ? (
                          <ChevronUp className="h-4 w-4" aria-hidden="true" />
                        ) : (
                          <ChevronDown className="h-4 w-4" aria-hidden="true" />
                        )}
                      </Button>
                    </div>
                    
                    {scenario.blockers.length > 0 && (
                      <Alert variant="destructive" className="py-2 px-3">
                        <AlertDescription className="text-xs">
                           {scenario.blockers.map((b, i) => <div key={i}>{formatApiError(b)}</div>)}
                        </AlertDescription>
                      </Alert>
                    )}

                    {isFleetDetailsExpanded && (
                      <div id="fleet-candidate-details" className="max-h-[240px] space-y-2 overflow-y-auto pr-1" tabIndex={0} aria-label="Fleet candidate details">
                        {candidates.map((r) => {
                          return (
                             <div key={r.id} className={`flex items-start space-x-3 rounded-md border p-3 ${r.eligible ? 'bg-emerald-50/40 dark:bg-emerald-950/10' : 'bg-muted/40'}`}>
                               <div className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${r.eligible ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                              <div className="grid gap-1.5 leading-none flex-1">
                                 <div className="text-sm font-medium font-mono flex items-center justify-between">
                                  {r.id}
                                   {r.eligible ? (
                                     <span className="text-[10px] text-emerald-700 bg-emerald-100 px-1.5 py-0.5 rounded">Included</span>
                                   ) : (
                                    <span className="text-[10px] text-destructive bg-destructive/10 px-1.5 py-0.5 rounded" title={r.exclusion_reasons?.join(', ')}>
                                       Excluded
                                    </span>
                                  )}
                                 </div>
                                <div className="text-[10px] text-muted-foreground flex justify-between mt-1">
                                  <span className="truncate">Type: {r.type}</span>
                                </div>
                                <div className="text-xs text-muted-foreground flex justify-between">
                                  <span>Cap: {r.capacity_kg != null ? r.capacity_kg + 'kg' : 'N/A'}</span>
                                  <span>Bat: {r.battery_percent != null ? r.battery_percent.toFixed(0) + '%' : 'N/A'}</span>
                                </div>
                                 {!r.eligible && r.exclusion_reasons.length > 0 && (
                                   <div className="mt-1 space-y-1 text-[10px] text-destructive">
                                     {r.exclusion_reasons.map(reason => <div key={reason}>• {reason}</div>)}
                                   </div>
                                 )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    
                    <Button 
                      className="w-full" 
                      onClick={handleRunSuggest}
                      disabled={
                        !scenario.ready_for_planning || 
                        suggestMutation.isPending
                      }
                    >
                      {suggestMutation.isPending ? (
                        <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Batching via LLM...</>
                      ) : (
                        'Generate Batched Plan'
                      )}
                    </Button>

                    <Button variant="outline" className="w-full" onClick={() => setStep(2)}>
                      <ChevronLeft className="mr-2 h-4 w-4" /> Back to review
                    </Button>

                    {suggestMutation.isError && (
                      <Alert variant="destructive" className="mt-2">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>LLM Planning Failed</AlertTitle>
                        <AlertDescription className="text-xs">
                          {suggestMutation.error?.message || 'An unknown error occurred during generation.'}
                        </AlertDescription>
                      </Alert>
                    )}
                  </div>
                )}
              </div>

              {/* Step 4: Plan Review */}
              {suggestion && scenario && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm font-semibold">
                    <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs bg-primary text-primary-foreground">4</div>
                    LLM Proposal
                  </div>
                  <div className="rounded-md border p-3 bg-muted/30 text-xs">
                    <p className="mb-2 italic border-l-2 border-primary/50 pl-2">{suggestion.summary}</p>
                     {suggestion.quality_assessment && (
                       <div className="mb-3 rounded-md border bg-background p-3 space-y-3">
                         <div className="flex items-center justify-between gap-2">
                           <p className="font-semibold">Measured plan quality</p>
                           <span className={`rounded px-2 py-0.5 text-[10px] font-mono font-bold uppercase ${
                             suggestion.quality_assessment.label !== 'improves_baseline'
                               ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300'
                               : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                           }`}>
                             {suggestion.quality_assessment.label.replaceAll('_', ' ')}
                           </span>
                         </div>
                         <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                           {(['baseline', 'proposed'] as const).map((kind) => {
                             const metrics = suggestion.quality_assessment![kind];
                             return (
                               <div key={kind} className="rounded border p-2">
                                 <p className="font-mono font-bold uppercase">{kind}</p>
                                 <div className="mt-1 text-muted-foreground">
                                   <p>Transfer service <span className="font-semibold text-foreground">{metrics.transfer_service_seconds}s</span></p>
                                   <p>Overall completion <span className="font-semibold text-foreground">{metrics.overall_completion_seconds}s</span></p>
                                 </div>
                               </div>
                             );
                           })}
                         </div>
                         <p className="text-muted-foreground">
                           Batching may reduce transfer service time but increase overall completion time.
                         </p>
                         {suggestion.quality_assessment.warnings?.map((warning: string, idx: number) => (
                           <div key={`${warning}-${idx}`} className="flex gap-2 text-amber-700 dark:text-amber-300">
                             <AlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                             <span>{warning}</span>
                           </div>
                         ))}
                       </div>
                     )}
                    <div className="space-y-3">
                      {suggestion.plan.batches.map((b: any) => (
                        <div key={b.batch_id} className="border-t pt-2 mt-2 first:border-0 first:pt-0 first:mt-0">
                          <p className="font-mono font-bold">{b.batch_id} · Robot {b.transfer_robot_id}</p>
                          <p className="text-muted-foreground mt-1">Orders: {b.order_ids.join(', ')}</p>
                          <div className="mt-1 pl-2 border-l-2 border-muted">
                            {b.stops.filter((s: any) => s.action === 'pick' || s.action === 'transfer').map((s: any, idx: number) => (
                              <div key={idx} className="text-[10px]">
                                <span className="uppercase text-muted-foreground mr-1">{s.action}</span>
                                {s.node_id} {s.bin_id ? `(${s.bin_id})` : ''} {s.quantity ? `x${s.quantity}` : ''}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                      {suggestion.plan.excluded_orders?.length > 0 && (
                        <div className="border-t pt-2 mt-2 text-red-700/80 dark:text-red-400">
                          <p className="font-bold">Excluded Orders</p>
                          {suggestion.plan.excluded_orders.map((ex: any, idx: number) => (
                            <p key={idx} className="text-[10px]">- {ex.order_id}: {ex.reason}</p>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <Button 
                    className="w-full" 
                    onClick={handleRunCompare}
                    disabled={compareMutation.isPending}
                  >
                    {compareMutation.isPending ? (
                      <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Comparing...</>
                    ) : (
                      'Compare & Play Simulation'
                    )}
                  </Button>

                  {compareMutation.isError && (
                    <Alert variant="destructive" className="mt-2">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertTitle>Comparison Failed</AlertTitle>
                      <AlertDescription className="text-xs">
                        {compareMutation.error?.message || 'Failed to simulate and compare runs.'}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}

            </div>
          </ScrollArea>
        </div>
        
        {/* Main Area: Map & Playback */}
        <div className="flex-1 flex flex-col bg-muted/10 min-w-0 min-h-0 overflow-y-auto lg:overflow-hidden relative">
          {!comparison ? (
            <div className="flex-1 flex items-stretch text-muted-foreground flex-col gap-4 min-h-[600px]">
              <IsometricMap 
                map={mapToRender}
                robots={fleetRobots}
                currentTime={0}
                title="DC-01 Transfer Map Preview"
              />
              {preview.assumptions && preview.assumptions.length > 0 && (
                <details className="border rounded-md p-2 text-xs text-muted-foreground mx-3 mb-3">
                  <summary className="font-bold cursor-pointer">Snapshot and simulation assumptions</summary>
                  {preview.assumptions.map((a: string, i: number) => <div key={i}>{a}</div>)}
                </details>
              )}
            </div>
          ) : (
            <ComparisonPlayback
              key={comparison.recommendation_id}
              comparison={comparison}
              map={mapToRender}
              robots={fleetRobots}
            />
          )}
        </div>
      </div>
    </div>
  );
}