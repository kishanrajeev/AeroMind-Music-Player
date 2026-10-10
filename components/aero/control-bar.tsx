import { Pause, Play, Repeat, Repeat1, Shuffle, SkipBack, SkipForward, Volume1, Volume2, VolumeX } from 'lucide-react'
import { formatTime } from '@/lib/songs'

export type RepeatMode = 'off' | 'all' | 'one'

type ControlBarProps = {
  isPlaying: boolean
  currentTime: number
  duration: number
  volume: number
  muted: boolean
  shuffle: boolean
  repeat: RepeatMode
  onTogglePlay: () => void
  onPrev: () => void
  onNext: () => void
  onSeek: (time: number) => void
  onVolume: (volume: number) => void
  onToggleMute: () => void
  onToggleShuffle: () => void
  onCycleRepeat: () => void
}

export function ControlBar({
  isPlaying,
  currentTime,
  duration,
  volume,
  muted,
  shuffle,
  repeat,
  onTogglePlay,
  onPrev,
  onNext,
  onSeek,
  onVolume,
  onToggleMute,
  onToggleShuffle,
  onCycleRepeat,
}: ControlBarProps) {
  const progress = duration ? (currentTime / duration) * 100 : 0
  const effectiveVolume = muted ? 0 : volume
  const VolumeIcon = effectiveVolume === 0 ? VolumeX : effectiveVolume < 50 ? Volume1 : Volume2
  const RepeatIcon = repeat === 'one' ? Repeat1 : Repeat
  const repeatLabel = repeat === 'off' ? 'Repeat off' : repeat === 'all' ? 'Repeat all' : 'Repeat one'

  return (
    <section aria-label="Playback controls" className="aero-glass-dark rounded-2xl px-4 pb-4 pt-3 text-white sm:px-6">
      <div className="flex items-center gap-3 text-xs tabular-nums text-cyan-50">
        <span className="w-10 text-right">{formatTime(currentTime)}</span>
        <input
          type="range"
          min={0}
          max={duration}
          step={1}
          value={Math.floor(currentTime)}
          onChange={(e) => onSeek(Number(e.target.value))}
          className="aero-range"
          style={{ '--value': `${progress}%` } as React.CSSProperties}
          aria-label="Seek"
          aria-valuetext={`${formatTime(currentTime)} of ${formatTime(duration)}`}
        />
        <span className="w-10">{formatTime(duration)}</span>
      </div>

      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onToggleShuffle}
            data-active={shuffle}
            aria-pressed={shuffle}
            aria-label="Shuffle"
            className="aero-pill grid h-8 w-11 place-items-center"
          >
            <Shuffle className="size-4" />
          </button>
          <button
            type="button"
            onClick={onCycleRepeat}
            data-active={repeat !== 'off'}
            aria-label={repeatLabel}
            title={repeatLabel}
            className="aero-pill grid h-8 w-11 place-items-center"
          >
            <RepeatIcon className="size-4" />
          </button>
        </div>

        <div className="flex items-center gap-3 sm:gap-4">
          <button type="button" onClick={onPrev} aria-label="Previous track" className="aero-pill grid h-10 w-14 place-items-center">
            <SkipBack className="size-5" fill="currentColor" />
          </button>
          <div className="relative">
            {isPlaying && (
              <>
                <span className="aero-ripple" aria-hidden="true" />
                <span className="aero-ripple" aria-hidden="true" />
              </>
            )}
            <button
              type="button"
              onClick={onTogglePlay}
              aria-label={isPlaying ? 'Pause' : 'Play'}
              className="aero-orb grid size-16 place-items-center"
            >
              {isPlaying ? (
                <Pause className="relative size-7 drop-shadow-[0_1px_2px_rgb(0_40_80/0.8)]" fill="currentColor" />
              ) : (
                <Play className="relative ml-1 size-7 drop-shadow-[0_1px_2px_rgb(0_40_80/0.8)]" fill="currentColor" />
              )}
            </button>
          </div>
          <button type="button" onClick={onNext} aria-label="Next track" className="aero-pill grid h-10 w-14 place-items-center">
            <SkipForward className="size-5" fill="currentColor" />
          </button>
        </div>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onToggleMute}
            aria-label={muted ? 'Unmute' : 'Mute'}
            aria-pressed={muted}
            className="aero-pill grid size-8 shrink-0 place-items-center"
          >
            <VolumeIcon className="size-4" />
          </button>
          <input
            type="range"
            min={0}
            max={100}
            value={effectiveVolume}
            onChange={(e) => onVolume(Number(e.target.value))}
            className="aero-range hidden max-w-28 sm:block"
            style={{ '--value': `${effectiveVolume}%` } as React.CSSProperties}
            aria-label="Volume"
          />
        </div>
      </div>
    </section>
  )
}
