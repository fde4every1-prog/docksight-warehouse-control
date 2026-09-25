import { useState } from 'react';
import { Batch, Exclusion, SuggestResponse, Scenario } from '@/hooks/use-batching';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Loader2, Sparkles, Settings2, PlaySquare, ChevronRight, ChevronDown, ListFilter, AlertCircle, Box } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface ProposalSidebarProps {
  scenario: Scenario;
  candidates: Batch[];
  exclusions: Exclusion[];
  suggestResponse: SuggestResponse | null;
  selectedCandidateIds: string[];
  setSelectedCandidateIds: (ids: string[]) => void;
  onSuggest: () => void;
  isSuggesting: boolean;
  onCompare: () => void;
  isComparing: boolean;
}

export function ProposalSidebar({
  scenario,
  candidates,
  exclusions, // Deterministic exclusions passed in
  suggestResponse,
  selectedCandidateIds,
  setSelectedCandidateIds,
  onSuggest,
  isSuggesting,
  onCompare,
  isComparing
}: ProposalSidebarProps) {
  const [showExclusions, setShowExclusions] = useState(false);
  const [showOrders, setShowOrders] = useState(false);
  const [expandedOrders, setExpandedOrders] = useState<string[]>([]);
  const [expandedCandidates, setExpandedCandidates] = useState<string[]>([]);

  const toggleCandidate = (id: string) => {
    const members = candidates.find(c => c.id === id)?.order_ids || [];
    setSelectedCandidateIds(
      selectedCandidateIds.includes(id)
        ? selectedCandidateIds.filter(cid => cid !== id)
        : [...selectedCandidateIds.filter(cid =>
            !candidates.find(c => c.id === cid)?.order_ids.some(o => members.includes(o))), id]
    );
  };

  const clearAll = () => setSelectedCandidateIds([]);

  const toggleOrder = (id: string) => {
    setExpandedOrders(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const toggleCandidateDetail = (id: string) => {
    setExpandedCandidates(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  // Merge deterministic and LLM candidate knowledge
  const mergedCandidates = candidates.map(c => {
    const llmBatch = suggestResponse?.batches?.find(b => b.id === c.id);
    return {
      ...c,
      reason: llmBatch?.reason || c.reason,
      isLlmSuggested: !!llmBatch
    };
  });

  // Combine exclusions
  const allExclusions = [
    ...exclusions.map(e => ({ ...e, source: 'Deterministic' })),
    ...(suggestResponse?.exclusions || []).map(e => ({ ...e, source: 'LLM' }))
  ];

  const hasNoSelections = selectedCandidateIds.length === 0;

  return (
    <div className="w-full lg:w-96 border-b lg:border-b-0 lg:border-r bg-card flex flex-col h-full shrink-0 shadow-sm z-10">
      <div className="p-4 border-b bg-muted/20">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-mono text-lg font-bold flex items-center gap-2">
            Batching Advisor
          </h2>
        </div>
        <div className="text-xs text-muted-foreground flex justify-between items-center bg-background border px-2 py-1 rounded">
          <span>Scenario: <span className="font-bold text-foreground">{scenario.scenario_id}</span></span>
          <span>{scenario.orders.length} orders</span>
        </div>
        
        <div className="mt-3 flex flex-col gap-2">
          <Button 
            className="w-full font-mono font-bold uppercase gap-2 hover-elevate shadow-sm"
            onClick={onSuggest}
            disabled={isSuggesting}
          >
            {isSuggesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {isSuggesting ? 'Analyzing...' : 'Generate LLM Proposal'}
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-6">
        {suggestResponse && (
          <div className="space-y-2">
            <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Sparkles className="h-3 w-3" /> AI Summary
            </h3>
            <div className="bg-primary/5 border border-primary/20 rounded p-3 text-sm leading-relaxed font-serif text-foreground/90 shadow-sm">
              {suggestResponse.summary}
            </div>
            {suggestResponse.cached && (
              <div className="text-[10px] text-muted-foreground font-mono uppercase text-right">
                Using cached AI response
              </div>
            )}
          </div>
        )}

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
              <Settings2 className="h-3 w-3" /> Candidates ({mergedCandidates.length})
            </h3>
            <div className="flex gap-2">
              <button onClick={clearAll} className="text-[10px] uppercase font-mono hover:text-primary transition-colors text-muted-foreground">Clear</button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Select manually for a non-LLM comparison, or generate an AI proposal above. Overlapping groups replace the previous selection.</p>
          
          {mergedCandidates.length === 0 ? (
            <div className="text-sm text-muted-foreground italic flex flex-col items-center p-4 border border-dashed rounded bg-muted/10">
              <ListFilter className="h-6 w-6 mb-2 opacity-20" />
              No feasible batched candidates.
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {mergedCandidates.map(candidate => {
                const isSelected = selectedCandidateIds.includes(candidate.id);
                const isExpanded = expandedCandidates.includes(candidate.id);
                return (
                  <div key={candidate.id} className={`flex flex-col p-2 rounded border transition-colors ${isSelected ? 'bg-primary/5 border-primary/30' : 'bg-card border-border hover:bg-muted/50'}`}>
                    <div className="flex items-center gap-3">
                      <Checkbox 
                        id={`candidate-${candidate.id}`}
                        checked={isSelected}
                        onCheckedChange={() => toggleCandidate(candidate.id)}
                        className="mt-0.5"
                      />
                      <label htmlFor={`candidate-${candidate.id}`} className="flex flex-col cursor-pointer flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium font-mono truncate">{candidate.id}</span>
                          {candidate.isLlmSuggested && (
                            <span title="LLM Selected"><Sparkles className="h-3 w-3 text-accent shrink-0" /></span>
                          )}
                        </div>
                        <span className="text-[10px] text-muted-foreground truncate">Orders: {candidate.order_ids.join(', ')}</span>
                      </label>
                      <button onClick={(e) => { e.preventDefault(); toggleCandidateDetail(candidate.id); }} className="p-1 hover:bg-muted rounded text-muted-foreground">
                        {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </button>
                    </div>
                    {isExpanded && (
                      <div className="mt-2 pt-2 border-t text-xs space-y-2 pl-7">
                        {candidate.reason && (
                          <div>
                            <span className="font-bold text-muted-foreground mr-1">Reason:</span>
                            <span className="font-serif italic text-foreground/90">{candidate.reason}</span>
                          </div>
                        )}
                        <div className="text-[10px] bg-muted/30 p-1.5 rounded text-muted-foreground font-mono">
                          Order Count: {candidate.order_ids.length}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="space-y-3">
          <button 
            onClick={() => setShowExclusions(!showExclusions)}
            className="font-mono text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center justify-between w-full p-2 hover:bg-muted/30 rounded border transition-colors"
          >
            <span className="flex items-center gap-2"><AlertCircle className="h-3 w-3" /> Exclusions ({allExclusions.length})</span>
            {showExclusions ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
          
          {showExclusions && allExclusions.length > 0 && (
            <div className="flex flex-col gap-2">
              {allExclusions.map((excl, i) => (
                <div key={i} className="p-2 bg-destructive/5 rounded border border-destructive/20 text-xs">
                  <div className="flex justify-between items-start mb-1">
                    <div className="font-mono font-medium text-destructive">{excl.order_ids.join(', ')}</div>
                    <span className="text-[9px] uppercase tracking-wider bg-background px-1 rounded border opacity-50">{excl.source}</span>
                  </div>
                  <div className="text-muted-foreground text-[10px] leading-relaxed">{excl.reason}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-3">
          <button 
            onClick={() => setShowOrders(!showOrders)}
            className="font-mono text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center justify-between w-full p-2 hover:bg-muted/30 rounded border transition-colors"
          >
            <span className="flex items-center gap-2"><Box className="h-3 w-3" /> Seed Orders ({scenario.orders.length})</span>
            {showOrders ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
          
          {showOrders && (
            <div className="flex flex-col gap-2">
              {scenario.orders.map((order, i) => {
                const isExpanded = expandedOrders.includes(order.id);
                return (
                  <div key={i} className="bg-card rounded border text-xs overflow-hidden">
                    <button 
                      onClick={() => toggleOrder(order.id)}
                      className="w-full text-left p-2 hover:bg-muted/50 flex justify-between items-center"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-medium">{order.id}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[9px] uppercase ${order.status === 'queued' ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}`}>{order.status}</span>
                      </div>
                      {isExpanded ? <ChevronDown className="h-3 w-3 opacity-50" /> : <ChevronRight className="h-3 w-3 opacity-50" />}
                    </button>
                    {isExpanded && (
                      <div className="p-2 bg-muted/20 border-t space-y-2">
                        <p className="font-mono break-all">{order.sub_order_id} · {order.tote_id}</p>
                        <div className="flex justify-between text-muted-foreground">
                          <span>Cutoff: <span className="font-mono text-foreground">{order.cutoff_seconds}s</span></span>
                          <span>{order.lines.length} lines</span>
                        </div>
                        <div className="space-y-1">
                          {order.lines.map(line => (
                            <div key={line.id} className="text-[10px] flex justify-between items-center bg-background border px-1.5 py-1 rounded">
                              <span className="font-mono mr-2">{line.id}<br />{line.sku}</span>
                              <span className="shrink-0">x{line.quantity} ({line.bin_id})</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <div className="p-4 border-t bg-card mt-auto space-y-3">
        <div className="bg-muted/30 rounded p-3 text-xs font-mono mb-3">
          <div className="font-bold mb-1">Batching Formula:</div>
          <div className="text-muted-foreground">T(n) = 45 + 22.5(n-1)</div>
          <div className="text-muted-foreground mt-1">3 orders: <span className="line-through opacity-70">135s</span> → <span className="text-emerald-600 font-bold">90s</span></div>
          <p className="mt-1 text-emerald-700">45s saved · 33.3% less service per grouped operation.</p>
          {scenario.assumptions && scenario.assumptions.length > 0 && (
            <div className="mt-2 pt-2 border-t border-muted-foreground/20">
              <div className="font-bold mb-1">Assumptions:</div>
              <ul className="list-disc pl-4 text-muted-foreground space-y-1 text-[10px] leading-relaxed">
                {scenario.assumptions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </div>
          )}
        </div>

        {hasNoSelections && suggestResponse && (
          <Alert variant="default" className="py-2 px-3 text-xs bg-muted/50 border-dashed">
            <AlertCircle className="h-3 w-3" />
            <AlertDescription className="text-[10px]">
              No batches selected. Comparison will run against the current process unchanged.
            </AlertDescription>
          </Alert>
        )}

        <Button 
          className="w-full font-mono font-bold uppercase gap-2 hover-elevate"
          onClick={onCompare}
          disabled={isComparing || isSuggesting}
          variant={hasNoSelections ? "secondary" : "default"}
        >
          {isComparing ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlaySquare className="h-4 w-4" />}
          Run Comparison
        </Button>
      </div>
    </div>
  );
}