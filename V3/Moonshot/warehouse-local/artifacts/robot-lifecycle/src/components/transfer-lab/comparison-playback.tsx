import { memo, useEffect, useMemo, useRef, useState } from 'react';
import type { CompareTransferResponse, TransferMap, TransferRobot } from '@/hooks/use-transfer-batching';
import { IsometricMap } from './isometric-map';
import { TransferMetricsSummary } from './metrics-summary';
import { PlaybackControls } from '@/components/batching/playback-controls';

const Metrics = memo(TransferMetricsSummary);

/** Keep animation updates out of the upload/editor/fleet-review component tree. */
export function ComparisonPlayback({ comparison, map, robots }: {
  comparison: CompareTransferResponse;
  map: TransferMap;
  robots: TransferRobot[];
}) {
  const [isPlaying, setIsPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const clock = useRef({ time: 0, wall: performance.now() });
  const maxTime = Math.max(
    comparison.baseline.metrics.overall_completion_seconds,
    comparison.proposed.metrics.overall_completion_seconds,
  );
  const boundaries = useMemo(() => [...new Set([
    0, maxTime,
    ...[comparison.baseline, comparison.proposed].flatMap(run =>
      run.timeline.flatMap(event => [event.start, event.end])),
  ])].sort((a, b) => a - b), [comparison, maxTime]);
  // These summaries only change at event boundaries, not every animation frame.
  const metricsTime = boundaries.filter(time => time <= currentTime).at(-1) ?? 0;

  useEffect(() => {
    if (!isPlaying || maxTime <= 0) return;
    let frame = 0;
    let lastPaint = 0;
    clock.current.wall = performance.now();
    const animate = (now: number) => {
      const next = Math.min(maxTime, clock.current.time + (now - clock.current.wall) / 1000 * speed);
      // Render at up to 30fps, without slowing the replay clock on dropped frames.
      if (now - lastPaint >= 1000 / 30 || next >= maxTime) {
        setCurrentTime(next);
        lastPaint = now;
      }
      if (next >= maxTime) {
        clock.current = { time: maxTime, wall: now };
        setIsPlaying(false);
      } else {
        frame = requestAnimationFrame(animate);
      }
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [isPlaying, speed, maxTime]);

  const captureTime = () => isPlaying
    ? Math.min(maxTime, clock.current.time + (performance.now() - clock.current.wall) / 1000 * speed)
    : clock.current.time;
  const seek = (time: number) => {
    const next = Math.max(0, Math.min(time, maxTime));
    clock.current = { time: next, wall: performance.now() };
    setCurrentTime(next);
    if (next >= maxTime) setIsPlaying(false);
  };

  return <>
    <div className="px-4 pt-3 text-xs text-muted-foreground">
      Snapshot replay · not live robot movement. Batched playback uses the validated LLM recommendation.
      <span className="block font-mono text-[10px] mt-1">Plan: {comparison.recommendation_id}</span>
      <span className="block mt-1">1× = one simulated second per second. Each pickup stop takes 7s end to end, including the brief hold at the bin. The same robot stays with the work through pickup and transfer; transfer timing remains 45s + 22.5s per additional grouped order.</span>
    </div>
    <div className="p-4 flex flex-col sm:flex-row gap-4 h-full min-h-[400px]">
      <IsometricMap map={map} run={comparison.baseline} robots={robots} currentTime={currentTime} title="Unbatched (Baseline)" />
      <IsometricMap map={map} run={comparison.proposed} robots={robots} currentTime={currentTime} title="Batched Transfer (LLM Plan)" />
    </div>
    <div className="border-t bg-background shrink-0">
      <PlaybackControls
        isPlaying={isPlaying}
        onTogglePlay={() => {
          const time = captureTime();
          seek(time >= maxTime ? 0 : time);
          setIsPlaying(!isPlaying);
        }}
        onReset={() => { seek(0); setIsPlaying(false); }}
        speed={speed}
        onSpeedChange={nextSpeed => { seek(captureTime()); setSpeed(nextSpeed); }}
        currentTime={currentTime}
        maxTime={maxTime}
        onSeek={seek}
      />
      <Metrics comparison={comparison} currentTime={metricsTime} />
    </div>
  </>;
}