/** Market replay: client-side stepping over bars the chart already owns.
 * While active, the REPLAY badge (with cursor date) replaces any live
 * badge and tick updates are suspended — replayed history must never be
 * mistakable for a live tape. */
import { Pause, Play, Square, StepForward } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export interface ReplayState {
  active: boolean;
  cursor: number; // number of bars visible
}

const SPEEDS = [1, 2, 5, 10];
const MIN_BARS = 10;

export function useReplay(totalBars: number) {
  const [active, setActive] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [cursor, setCursor] = useState(totalBars);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = () => {
    setCursor(Math.max(MIN_BARS, Math.floor(totalBars / 4)));
    setActive(true);
    setPlaying(true);
  };
  const stop = () => {
    setActive(false);
    setPlaying(false);
    setCursor(totalBars);
  };

  useEffect(() => {
    if (!active || !playing) return;
    timerRef.current = setInterval(() => {
      setCursor((c) => {
        if (c >= totalBars) {
          setPlaying(false);
          return totalBars;
        }
        return c + 1;
      });
    }, 1000 / speed);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [active, playing, speed, totalBars]);

  return {
    active,
    playing,
    speed,
    cursor: Math.min(cursor, totalBars),
    start,
    stop,
    setPlaying,
    setSpeed,
    setCursor,
  };
}

export function ReplayControls({
  replay,
  totalBars,
  cursorLabel,
}: {
  replay: ReturnType<typeof useReplay>;
  totalBars: number;
  cursorLabel: string | null;
}) {
  if (!replay.active) {
    return (
      <Button size="sm" variant="ghost" onClick={replay.start} disabled={totalBars < MIN_BARS + 5}>
        <Play size={13} /> Replay
      </Button>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="replay-controls">
      <Badge variant="neutral" className="font-bold" data-testid="replay-badge">
        REPLAY {cursorLabel ?? ""}
      </Badge>
      <Button
        size="icon"
        variant="ghost"
        aria-label={replay.playing ? "Pause replay" : "Play replay"}
        onClick={() => replay.setPlaying(!replay.playing)}
      >
        {replay.playing ? <Pause size={13} /> : <Play size={13} />}
      </Button>
      <Button
        size="icon"
        variant="ghost"
        aria-label="Step one bar"
        onClick={() => replay.setCursor(Math.min(replay.cursor + 1, totalBars))}
      >
        <StepForward size={13} />
      </Button>
      {SPEEDS.map((s) => (
        <button
          key={s}
          onClick={() => replay.setSpeed(s)}
          aria-pressed={replay.speed === s}
          className={
            replay.speed === s
              ? "rounded bg-accent-muted px-1.5 text-xs text-accent"
              : "rounded px-1.5 text-xs text-fg-subtle hover:text-fg"
          }
        >
          {s}×
        </button>
      ))}
      <input
        type="range"
        min={MIN_BARS}
        max={totalBars}
        value={replay.cursor}
        onChange={(event) => replay.setCursor(Number(event.target.value))}
        aria-label="Replay position"
        className="w-32 accent-(--accent)"
      />
      <Button size="icon" variant="ghost" aria-label="Exit replay" onClick={replay.stop}>
        <Square size={13} />
      </Button>
    </div>
  );
}
