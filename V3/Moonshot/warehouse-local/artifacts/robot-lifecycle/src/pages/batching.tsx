import { useState, useEffect, useRef } from 'react';
import { Header } from '@/components/layout/header';
import { useScenario, useSuggestBatching, useCompareBatching, SuggestResponse, CompareResponse } from '@/hooks/use-batching';
import { ProposalSidebar } from '@/components/batching/proposal-sidebar';
import { MapPanel } from '@/components/batching/map-panel';
import { PlaybackControls } from '@/components/batching/playback-controls';
import { MetricsSummary } from '@/components/batching/metrics-summary';
import { Loader2, AlertCircle } from 'lucide-react';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';

export default function BatchingAdvisor() {
  const { data: scenarioData, isLoading: isLoadingScenario, error: scenarioError } = useScenario();
  const suggestMutation = useSuggestBatching();
  const compareMutation = useCompareBatching();
  const { toast } = useToast();

  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [suggestResponse, setSuggestResponse] = useState<SuggestResponse | null>(null);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const requestRef = useRef<number | undefined>(undefined);
  const previousTimeRef = useRef<number | undefined>(undefined);

  const scenarioId = scenarioData?.scenario.scenario_id;
  useEffect(() => {
    setSelectedCandidateIds([]);
    setSuggestResponse(null);
    setComparison(null);
    setCurrentTime(0);
    setIsPlaying(false);
    previousTimeRef.current = undefined;
  }, [scenarioId]);

  useEffect(() => {
    const previous = document.title;
    document.title = 'Batching Advisor · Robot Fleet Simulator';
    return () => { document.title = previous; };
  }, []);

  const maxTime = comparison ? Math.max(
    comparison.baseline.metrics.makespan_seconds,
    comparison.batched.metrics.makespan_seconds
  ) : 0;

  const animate = (time: number) => {
    if (previousTimeRef.current != undefined) {
      const deltaTime = (time - previousTimeRef.current) / 1000; // seconds
      setCurrentTime(prevTime => {
        const nextTime = prevTime + deltaTime * speed;
        if (nextTime >= maxTime) {
          setIsPlaying(false);
          return maxTime;
        }
        return nextTime;
      });
    }
    previousTimeRef.current = time;
    if (isPlaying) {
      requestRef.current = requestAnimationFrame(animate);
    }
  };

  useEffect(() => {
    previousTimeRef.current = undefined;
    if (isPlaying) {
      requestRef.current = requestAnimationFrame(animate);
    } else {
      previousTimeRef.current = undefined;
    }
    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, [isPlaying, speed, maxTime]);

  const handleReset = () => {
    previousTimeRef.current = undefined;
    setCurrentTime(0);
    setIsPlaying(false);
  };

  const handleSelectionChange = (ids: string[]) => {
    setSuggestResponse(null);
    setSelectedCandidateIds(ids);
    if (comparison) {
      setComparison(null);
      handleReset();
    }
  };

  const handleSuggest = () => {
    if (!scenarioData) return;
    
    // Reset any stale comparison state when generating new proposal
    setComparison(null);
    setSuggestResponse(null);
    setSelectedCandidateIds([]);
    handleReset();
    
    suggestMutation.mutate({ scenario_id: scenarioData.scenario.scenario_id }, {
      onSuccess: (data) => {
        if (data.scenario_id !== scenarioId) return;
        setSuggestResponse(data);
        setSelectedCandidateIds(data.selected_candidate_ids || []);
        toast({
          title: "AI Proposal Generated",
          description: data.selected_candidate_ids.length > 0 
            ? "Candidate batches selected based on LLM suggestions."
            : "LLM suggested no feasible batched candidates.",
        });
      },
      onError: (err) => {
        toast({
          title: "Failed to generate proposal",
          description: err.message,
          variant: "destructive"
        });
      }
    });
  };

  const handleCompare = () => {
    if (!scenarioData) return;
    compareMutation.mutate({
      scenario_id: scenarioData.scenario.scenario_id,
      candidate_ids: selectedCandidateIds // allow empty array to compare "no batches"
    }, {
      onSuccess: (data) => {
        if (data.scenario_id !== scenarioId) return;
        previousTimeRef.current = undefined;
        setComparison(data);
        setCurrentTime(0);
        setIsPlaying(true);
        toast({
          title: "Comparison Ready",
          description: "Simulation playing. View metrics below.",
        });
      },
      onError: (err) => {
        toast({
          title: "Comparison Failed",
          description: err.message,
          variant: "destructive"
        });
      }
    });
  };

  if (isLoadingScenario) {
    return (
      <div className="min-h-[100dvh] bg-background flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (scenarioError || !scenarioData) {
    return (
      <div className="min-h-[100dvh] bg-background flex flex-col">
        <Header />
        <div className="flex-1 p-8 max-w-3xl mx-auto w-full">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error loading scenario</AlertTitle>
            <AlertDescription>{scenarioError?.message || "Failed to load"}</AlertDescription>
          </Alert>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col overflow-hidden">
      <Header />
      <div className="border-b bg-teal-50 px-4 py-2 text-xs text-teal-950">
        Synthetic DC-01 sandbox · Assumed timing, not observed savings · No live dispatch or physical equipment control
      </div>
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        <ProposalSidebar 
          scenario={scenarioData.scenario}
          candidates={scenarioData.candidates}
          exclusions={scenarioData.exclusions}
          suggestResponse={suggestResponse}
          selectedCandidateIds={selectedCandidateIds}
          setSelectedCandidateIds={handleSelectionChange}
          onSuggest={handleSuggest}
          isSuggesting={suggestMutation.isPending}
          onCompare={handleCompare}
          isComparing={compareMutation.isPending}
        />
        
        <div className="flex-1 flex flex-col bg-muted/10 min-w-0 min-h-0 overflow-y-auto lg:overflow-hidden">
          <div className="p-4 flex flex-col sm:flex-row gap-4">
            <MapPanel 
              map={scenarioData.scenario.map}
              run={comparison?.baseline}
              robots={scenarioData.scenario.robots}
              currentTime={currentTime}
              title="Current Process (Singletons)"
            />
            <MapPanel 
              map={scenarioData.scenario.map}
              run={comparison?.batched}
              robots={scenarioData.scenario.robots}
              currentTime={currentTime}
              title="Batched Proposal"
            />
          </div>

          <PlaybackControls 
            isPlaying={isPlaying}
            onTogglePlay={() => {
              if (currentTime >= maxTime) setCurrentTime(0);
              setIsPlaying(!isPlaying);
            }}
            onReset={handleReset}
            speed={speed}
            onSpeedChange={setSpeed}
            currentTime={currentTime}
            maxTime={maxTime}
            onSeek={(t) => {
              previousTimeRef.current = undefined;
              setCurrentTime(t);
              if (t >= maxTime) setIsPlaying(false);
            }}
          />
          <MetricsSummary comparison={comparison} currentTime={currentTime} />
        </div>
      </div>
    </div>
  );
}