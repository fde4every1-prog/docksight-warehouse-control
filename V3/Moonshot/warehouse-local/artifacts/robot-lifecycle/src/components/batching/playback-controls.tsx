import { Play, Pause, RotateCcw, FastForward } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface PlaybackControlsProps {
  isPlaying: boolean;
  onTogglePlay: () => void;
  onReset: () => void;
  speed: number;
  onSpeedChange: (speed: number) => void;
  currentTime: number;
  maxTime: number;
  onSeek: (time: number) => void;
}

export function PlaybackControls({
  isPlaying,
  onTogglePlay,
  onReset,
  speed,
  onSpeedChange,
  currentTime,
  maxTime,
  onSeek
}: PlaybackControlsProps) {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col gap-2 p-4 border-t bg-card/50">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8 shrink-0 hover-elevate"
          onClick={onTogglePlay}
          disabled={maxTime === 0}
          aria-label={isPlaying ? 'Pause simulation' : 'Resume simulation'}
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          onClick={onReset}
          disabled={maxTime === 0}
          aria-label="Reset simulation"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>

        <div className="flex items-center gap-1 rounded-md border bg-background p-1 text-xs">
          {[1, 5, 10, 30].map(s => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={`px-2 py-1 rounded font-mono ${speed === s ? 'bg-primary text-primary-foreground font-bold' : 'text-muted-foreground hover:bg-muted'}`}
            >
              {s}x
            </button>
          ))}
        </div>

        <div className="flex-1 min-w-[200px] flex items-center gap-3">
          <span className="font-mono text-xs w-12 text-right">{formatTime(currentTime)}</span>
          <input
            type="range"
            min={0}
            max={maxTime}
            step="any"
            value={Math.max(0, Math.min(currentTime, maxTime))}
            disabled={maxTime === 0}
            onChange={(event) => onSeek(event.currentTarget.valueAsNumber)}
            aria-label="Simulation time"
            aria-valuetext={`${formatTime(currentTime)} of ${formatTime(maxTime)}`}
            className="h-5 flex-1 cursor-pointer accent-primary disabled:cursor-not-allowed disabled:opacity-50"
          />
          <span className="font-mono text-xs w-12 text-muted-foreground">{formatTime(maxTime)}</span>
        </div>
      </div>
    </div>
  );
}