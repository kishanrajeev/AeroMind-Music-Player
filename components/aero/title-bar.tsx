import { Droplet, Minus, Square, X } from 'lucide-react'

export function TitleBar({ nowPlaying }: { nowPlaying: string }) {
  return (
    <header className="relative flex h-11 items-center justify-between gap-3 px-3">
      <div className="flex min-w-0 items-center gap-2">
        <span className="aero-orb grid size-6 shrink-0 place-items-center" aria-hidden="true">
          <Droplet className="relative size-3.5" fill="currentColor" />
        </span>
        <h1 className="truncate text-sm font-semibold text-[var(--aero-navy)] aero-text-glow">
          Aero Media Player
          <span className="hidden font-normal text-[var(--aero-navy)]/70 sm:inline">{` — ${nowPlaying}`}</span>
        </h1>
      </div>

      <div className="flex shrink-0 items-start self-start" role="group" aria-label="Window controls">
        <button type="button" className="aero-caption w-7 rounded-bl-md border-r-0" aria-label="Minimize">
          <Minus className="size-3" strokeWidth={3} />
        </button>
        <button type="button" className="aero-caption w-7 border-r-0" aria-label="Maximize">
          <Square className="size-2.5" strokeWidth={3} />
        </button>
        <button type="button" className="aero-caption aero-caption-close w-11 rounded-br-md" aria-label="Close">
          <X className="size-3.5" strokeWidth={3} />
        </button>
      </div>
    </header>
  )
}
